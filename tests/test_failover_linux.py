"""Real failover namespaces, root workload identity and persistent monitor service."""
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import TLSFixture
from splitforge.core.failover import FailoverMonitor, ensure_service, unit_name
from splitforge.core.netns import run
from splitforge.core.runner import Runner
from splitforge.protocols.manager import ProtocolManager
from splitforge.state import AppBinding, StateStore


@unittest.skipUnless(os.environ.get('SPLITFORGE_INTEGRATION') == '1' and os.geteuid() == 0,
                     'Opt-in root/systemd failover integration required')
class FailoverLinuxTests(unittest.TestCase):
    def test_actual_monitor_service_is_enabled_and_stops_cleanly(self):
        with tempfile.TemporaryDirectory(prefix='splitforge-monitor-') as directory:
            store = StateStore(Path(directory) / 'state.json')
            with store.operation():
                store._write({'version': 1, 'profiles': {}, 'apps': {}, 'users': {}})
            unit = unit_name(store)
            path = Path('/etc/systemd/system', unit)
            try:
                ensure_service(store)
                self.assertEqual(run(['systemctl', 'is-enabled', unit]).stdout.strip(), 'enabled')
                self.assertEqual(run(['systemctl', 'is-active', unit]).stdout.strip(), 'active')
                run(['systemctl', 'stop', unit], timeout=10)
                self.assertNotEqual(run(['systemctl', 'is-active', '--quiet', unit], check=False).returncode, 0)
            finally:
                run(['systemctl', 'disable', '--now', unit], check=False)
                path.unlink(missing_ok=True)
                run(['systemctl', 'daemon-reload'])

    @unittest.skipUnless(shutil.which('xray') and shutil.which('tun2socks'), 'Verified proxy cores required')
    def test_primary_loss_switches_real_root_namespace_and_both_down_stays_stopped(self):
        baseline = run(['ip', '-j', '-4', 'route', 'show', 'table', 'main']).stdout
        with tempfile.TemporaryDirectory(prefix='splitforge-failover-') as directory:
            base = Path(directory)
            with TLSFixture(base) as fixture:
                store = StateStore(base / 'state.json')
                manager = ProtocolManager(store)
                runner = Runner(store, manager)
                profiles, servers = [], []
                app = AppBinding('failover-root', ['/usr/bin/sleep', '300'], user='root')
                store.save_app(app)
                try:
                    for index in range(2):
                        with socket.socket() as reservation:
                            reservation.bind(('127.0.0.1', 0))
                            port = reservation.getsockname()[1]
                        config = base / f'server-{index}.json'
                        config.write_text(json.dumps({'log': {'loglevel': 'warning'}, 'inbounds': [
                            {'listen': '127.0.0.1', 'port': port, 'protocol': 'socks', 'settings': {'udp': True}}],
                            'outbounds': [{'protocol': 'freedom', 'settings': {'redirect': f'127.0.0.1:{fixture.port}'}}]}))
                        server = subprocess.Popen(['xray', 'run', '-config', str(config)],
                                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        servers.append(server)
                        for attempt in range(50):
                            try:
                                with socket.create_connection(('127.0.0.1', port), timeout=0.1):
                                    break
                            except OSError:
                                time.sleep(0.1)
                        profile = manager.import_profile(f'socks5://127.0.0.1:{port}', name=f'failover-{index}')
                        store.save_profile(fixture.configure(profile))
                        profiles.append(profile)
                    with patch('splitforge.core.failover.ensure_service'):
                        runner.bind(app.id, profiles[0].id, backup_profile_name=profiles[1].id)
                    old_pid = run(['systemctl', 'show', runner.unit(app), '-p', 'MainPID', '--value']).stdout.strip()
                    manager.stop(profiles[0].id)
                    monitor = FailoverMonitor(store, manager, runner, report=lambda message: None)
                    monitor.cycle()
                    self.assertEqual(store.app(app.id).profile_id, profiles[0].id)
                    monitor.cycle()
                    assigned = store.app(app.id)
                    self.assertEqual(assigned.profile_id, profiles[1].id)
                    self.assertTrue(assigned.failover_enabled)
                    self.assertTrue(runner.running(assigned))
                    pid = run(['systemctl', 'show', runner.unit(app), '-p', 'MainPID', '--value']).stdout.strip()
                    self.assertNotEqual(pid, old_pid)
                    self.assertEqual(Path(f'/proc/{pid}/ns/net').stat().st_ino,
                                     Path('/run/netns', profiles[1].namespace).stat().st_ino)
                    self.assertEqual(manager.test(profiles[1].id)['exit_ip'], '192.0.2.80')
                    for server in servers:
                        server.terminate()
                        server.wait(timeout=10)
                    manager.stop(profiles[1].id)
                    monitor.cycle()
                    monitor.cycle()
                    blocked = store.app(app.id)
                    self.assertTrue(blocked.enabled)
                    self.assertEqual(blocked.profile_id, profiles[1].id)
                    self.assertFalse(runner.running(blocked))
                    self.assertEqual(run(['systemctl', 'show', runner.unit(app), '-p', 'MainPID', '--value']).stdout.strip(), '0')
                    self.assertEqual(run(['ip', '-j', '-4', 'route', 'show', 'table', 'main']).stdout, baseline)
                finally:
                    try:
                        runner.remove(app.id)
                        for profile in reversed(profiles):
                            manager.remove(profile.id)
                    finally:
                        for server in servers:
                            if server.poll() is None:
                                server.terminate()
                                server.wait(timeout=10)
