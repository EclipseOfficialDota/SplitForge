"""Actual per-service cgroup counters: two root apps in the same tunnel."""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from helpers import TLSFixture
from splitforge.core.netns import run
from splitforge.core.runner import Runner
from splitforge.core.traffic import TrafficMonitor, TrafficStore, unit_name
from splitforge.protocols.manager import ProtocolManager
from splitforge.state import AppBinding, StateStore


@unittest.skipUnless(os.environ.get('SPLITFORGE_INTEGRATION') == '1' and os.geteuid() == 0,
                     'Opt-in root/systemd independent traffic integration')
class TrafficLinuxTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('xray') and shutil.which('tun2socks'), 'Verified proxy cores required')
    def test_independent_root_counters_restart_and_app_and_tunnel_quotas(self):
        before = run(['ip', '-j', '-4', 'route', 'show', 'table', 'main']).stdout
        with tempfile.TemporaryDirectory(prefix='splitforge-traffic-') as directory:
            base = Path(directory)
            with TLSFixture(base) as fixture:
                with socket.socket() as reservation:
                    reservation.bind(('127.0.0.1', 0))
                    port = reservation.getsockname()[1]
                config = base / 'server.json'
                config.write_text(json.dumps({'log': {'loglevel': 'warning'}, 'inbounds': [
                    {'listen': '127.0.0.1', 'port': port, 'protocol': 'socks', 'settings': {'udp': True}}],
                    'outbounds': [{'protocol': 'freedom', 'settings': {'redirect': f'127.0.0.1:{fixture.port}'}}]}))
                server = subprocess.Popen(['xray', 'run', '-config', str(config)],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                store = StateStore(base / 'state.json')
                manager = ProtocolManager(store)
                runner = Runner(store, manager)
                meter = TrafficStore(store)
                monitor = TrafficMonitor(store, manager, runner)
                profile = None
                backup = None
                apps = []
                try:
                    for _ in range(50):
                        try:
                            with socket.create_connection(('127.0.0.1', port), timeout=0.1):
                                break
                        except OSError:
                            time.sleep(0.1)
                    profile = manager.import_profile(f'socks5://127.0.0.1:{port}', name='meter-tunnel')
                    store.save_profile(fixture.configure(profile))
                    from splitforge.core.speed import set_limits
                    # Persist both limits before activation; startup must apply
                    # the saved tc policy before admitting managed workloads.
                    meter.set_quota('profiles', profile.id, 16 * 1048576)
                    set_limits(store, profile.id, 8000000, 8000000)
                    script = base / 'client.py'
                    script.write_text('''import ssl,sys,time,urllib.request
from pathlib import Path
prefix,ca,size=sys.argv[1:]
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=ca)))
for index in range(2):
    while not Path(prefix+'-go'+str(index)).exists(): time.sleep(0.02)
    with opener.open('https://probe.splitforge.test/bytes/'+size,timeout=10) as response: response.read()
    Path(prefix+'-done'+str(index)).write_text('ok')
time.sleep(120)
''')
                    for index, size in enumerate((131072, 65536)):
                        app = AppBinding(f'root-meter-{index}', [sys.executable, str(script), str(base / str(index)),
                                         str(fixture.cert), str(size)], user='root')
                        store.save_app(app)
                        apps.append(app)
                        runner.bind(app.id, profile.id)
                    self.assertEqual(run(['systemctl', 'is-active', unit_name(store)]).stdout.strip(), 'active')
                    qdiscs = json.loads(manager.netns.command(profile, 'tc', '-j', 'qdisc', 'show', 'dev', profile.interface).stdout)
                    self.assertTrue(any(q['kind'] == 'tbf' for q in qdiscs))
                    expected_namespace = Path('/run/netns', profile.namespace).stat().st_ino
                    for app in apps:
                        pid = run(['systemctl', 'show', runner.unit(app), '-p', 'MainPID', '--value']).stdout.strip()
                        self.assertEqual(Path(f'/proc/{pid}/ns/net').stat().st_ino, expected_namespace)
                    baseline_second = meter.app_sample(runner, apps[1])

                    def wait_for(predicate):
                        deadline = time.monotonic() + 15
                        while time.monotonic() < deadline:
                            if predicate():
                                return
                            time.sleep(0.05)
                        self.fail('Controlled traffic fixture did not reach its expected state')

                    (base / '0-go0').touch()
                    wait_for(lambda: (base / '0-done0').exists())
                    first = meter.app_sample(runner, apps[0])
                    second = meter.app_sample(runner, apps[1])
                    self.assertGreaterEqual(first[1], 131072)
                    self.assertEqual(second[1:], baseline_second[1:], 'Waiting app must not receive another app\'s usage')
                    (base / '1-go0').touch()
                    wait_for(lambda: (base / '1-done0').exists())
                    second = meter.app_sample(runner, apps[1])
                    self.assertGreaterEqual(second[1], 65536)
                    self.assertLess(second[1], first[1])
                    monitor.cycle()
                    self.assertGreaterEqual(meter.snapshot()['apps'][apps[1].id]['rx'], second[1])
                    self.assertLessEqual(meter.snapshot()['apps'][apps[1].id]['rx'], meter.app_sample(runner, apps[1])[1])
                    meter.set_quota('apps', apps[0].id, 4096, reset=True)
                    (base / '0-go1').touch()
                    wait_for(lambda: (base / '0-done1').exists() or not runner.running(apps[0]))
                    monitor.cycle()
                    self.assertFalse(runner.running(apps[0]))
                    self.assertFalse(store.app(apps[0].id).enabled)
                    self.assertTrue(runner.running(apps[1]))
                    with self.assertRaisesRegex(RuntimeError, 'Traffic quota'):
                        runner.bind(apps[0].id, profile.id)
                    run(['systemctl', 'start', runner.unit(apps[0])], check=False)
                    self.assertFalse(runner.running(apps[0]), 'ExecCondition must also block direct systemctl restarts')
                    lifetime = meter.snapshot()['apps'][apps[0].id]['rx']
                    for path in base.glob('0-go*'):
                        path.unlink()
                    meter.set_quota('apps', apps[0].id, 4096, reset=True)
                    runner.bind(apps[0].id, profile.id)
                    self.assertTrue(runner.running(apps[0]))
                    self.assertGreaterEqual(meter.snapshot()['apps'][apps[0].id]['rx'], lifetime)
                    meter.set_quota('profiles', profile.id, 4096, reset=True)
                    (base / '1-go1').touch()
                    wait_for(lambda: (base / '1-done1').exists() or not runner.running(apps[1]))
                    monitor.cycle()
                    self.assertFalse(manager.netns.exists(profile))
                    self.assertFalse(runner.running(apps[1]))
                    with self.assertRaisesRegex(RuntimeError, 'Traffic quota'):
                        manager.start(profile.id)
                    backup = manager.import_profile(f'socks5://127.0.0.1:{port}', name='meter-backup')
                    store.save_profile(fixture.configure(backup))
                    # A tunnel budget blocks that tunnel, not an allowed backup.
                    # The new unit condition must check its selected backup, not
                    # the previous assignment still on disk during the swap.
                    updated = runner.bind(apps[1].id, profile.id, backup_profile_name=backup.id)
                    self.assertEqual(updated.profile_id, backup.id)
                    self.assertTrue(runner.running(updated))
                    self.assertEqual(run(['ip', '-j', '-4', 'route', 'show', 'table', 'main']).stdout, before)
                finally:
                    for app in store.apps():
                        runner.remove(app.id)
                    if profile is not None:
                        manager.remove(profile.id)
                    if backup is not None:
                        manager.remove(backup.id)
                    server.terminate()
                    server.wait(timeout=10)
                self.assertFalse(Path('/etc/systemd/system', unit_name(store)).exists())
