import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from splitforge.core import backup
from splitforge.core.netns import run
from splitforge.core.runner import Runner
from splitforge.protocols.manager import ProtocolManager
from splitforge.state import AppBinding, StateStore


@unittest.skipUnless(os.environ.get('SPLITFORGE_INTEGRATION') == '1' and os.geteuid() == 0,
                     'Opt-in root/systemd backup restoration')
class BackupLinuxTests(unittest.TestCase):
    def test_real_root_restore_stopped_and_failed_restart_recovery(self):
        before = run(['ip', '-j', '-4', 'route', 'show', 'table', 'main']).stdout
        with tempfile.TemporaryDirectory(prefix='splitforge-backup-') as directory:
            base = Path(directory)
            store = StateStore(base / 'state.json')
            manager = ProtocolManager(store)
            runner = Runner(store, manager)
            binding = AppBinding('backup-root', ['/usr/bin/sleep', '300'], user='root')
            store.save_app(binding)
            password = 'integration-only-backup-password'
            with patch.object(backup, 'BACKUPS', base / 'recovery'), patch('splitforge.web.setup.load_settings', return_value=None):
                try:
                    runner.bind(binding.id, None)
                    original = store.snapshot()
                    path = backup.export_backup(store, base / 'export.sfb', password)
                    document = backup.read_backup(path, password)
                    recovery = backup.restore_backup(store, manager, runner, document, password, start=False, report=lambda _: None)
                    self.assertFalse(runner.running(binding))
                    self.assertEqual(store.snapshot(), original)
                    self.assertEqual(backup.read_backup(recovery, password)['state'], original)
                    runner.restore()
                    self.assertTrue(runner.running(binding))
                    broken = copy.deepcopy(document)
                    broken['state']['apps'][binding.id]['argv'] = ['/splitforge-test-nonexistent-executable']
                    with self.assertRaisesRegex(RuntimeError, 'previous configuration and enabled workloads were restored'):
                        backup.restore_backup(store, manager, runner, broken, password, start=True, report=lambda _: None)
                    self.assertEqual(store.snapshot(), original)
                    self.assertTrue(runner.running(binding))
                    self.assertEqual(run(['ip', '-j', '-4', 'route', 'show', 'table', 'main']).stdout, before)
                finally:
                    for app in store.apps():
                        runner.remove(app.id)
