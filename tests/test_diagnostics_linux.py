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
from splitforge.core.diagnostics import diagnose, guard_valid
from splitforge.core.netns import run
from splitforge.core.runner import Runner
from splitforge.protocols.manager import ProtocolManager
from splitforge.state import AppBinding, StateStore


@unittest.skipUnless(os.environ.get('SPLITFORGE_INTEGRATION') == '1' and os.geteuid() == 0
                     and shutil.which('xray') and shutil.which('tun2socks'), 'Opt-in root proxy integration required')
class DiagnosticLinuxTests(unittest.TestCase):
    def test_real_dns_guard_detection_and_repair_restores_root_workload(self):
        before = run(['ip', '-j', '-4', 'route', 'show', 'table', 'main']).stdout
        with tempfile.TemporaryDirectory(prefix='splitforge-diag-') as directory:
            base = Path(directory)
            with TLSFixture(base) as fixture:
                with socket.socket() as reservation:
                    reservation.bind(('127.0.0.1', 0))
                    port = reservation.getsockname()[1]
                config = base / 'xray.json'
                config.write_text(json.dumps({'log': {'loglevel': 'warning'}, 'inbounds': [
                    {'listen': '127.0.0.1', 'port': port, 'protocol': 'socks', 'settings': {'udp': True}}],
                    'outbounds': [{'protocol': 'freedom', 'settings': {'redirect': f'127.0.0.1:{fixture.port}'}}]}))
                server = subprocess.Popen(['xray', 'run', '-config', str(config)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                store = StateStore(base / 'state.json')
                manager = ProtocolManager(store)
                runner = Runner(store, manager)
                profile = manager.import_profile(f'socks5://127.0.0.1:{port}', name='diagnostic-proxy')
                store.save_profile(fixture.configure(profile))
                app = AppBinding('diagnostic-root', ['/usr/bin/sleep', '300'], user='root')
                store.save_app(app)
                try:
                    for attempt in range(50):
                        try:
                            with socket.create_connection(('127.0.0.1', port), timeout=0.1):
                                break
                        except OSError:
                            time.sleep(0.1)
                    runner.bind(app.id, profile.id)
                    rules = json.loads(manager.netns.command(profile, 'nft', '-j', 'list', 'table', 'inet', 'splitforge').stdout)
                    self.assertTrue(guard_valid(rules, profile))
                    manager.netns.command(profile, 'nft', 'add', 'rule', 'inet', 'splitforge', 'output', 'accept')
                    rules = json.loads(manager.netns.command(profile, 'nft', '-j', 'list', 'table', 'inet', 'splitforge').stdout)
                    self.assertFalse(guard_valid(rules, profile))
                    Path('/etc/netns', profile.namespace, 'resolv.conf').write_text('nameserver 192.0.2.1\n')
                    with patch('splitforge.web.setup.load_settings', return_value=None):
                        result = diagnose(store, manager, runner, repair=True, report=lambda message: None, route_baseline=before)
                    relevant = [row for row in result['checks'] if row['scope'] in {profile.name, app.name}]
                    self.assertTrue(relevant)
                    self.assertTrue(all(row['status'] == 'ok' for row in relevant), relevant)
                    self.assertTrue(any(row['repaired'] for row in relevant))
                    self.assertTrue(runner.running(store.app(app.id)))
                    self.assertEqual(store.app(app.id).profile_id, profile.id)
                    self.assertEqual(run(['ip', '-j', '-4', 'route', 'show', 'table', 'main']).stdout, before)
                finally:
                    try:
                        runner.remove(app.id)
                        manager.remove(profile.id)
                    finally:
                        server.terminate()
                        server.wait(timeout=10)
