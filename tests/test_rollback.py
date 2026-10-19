import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from splitforge.core import updater
from splitforge.state import Profile, StateStore


@unittest.skipUnless(os.name == 'posix', 'POSIX install snapshots and locks')
class RollbackTests(unittest.TestCase):
    def test_matching_environment_state_and_revision_restore_and_failed_activation_recovery(self):
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                prefix = base / 'install'
                binaries = prefix / 'venv/bin'
                binaries.mkdir(parents=True)
                for name in ('python', 'splitforge'):
                    (binaries / name).write_text('old environment')
                state = base / 'state.json'
                store = StateStore(state)
                store.save_profile(Profile('old', 'socks5', {}))
                original = state.read_text()
                (prefix / '.splitforge-revision').write_text('a' * 40)
                with patch.object(updater, 'BACKUP_ROOT', base / 'backups'), patch.object(updater, 'require_root'):
                    snapshot = updater.snapshot_installation(prefix, state)
                    for name in ('python', 'splitforge'):
                        (binaries / name).write_text('new environment')
                    (prefix / '.splitforge-revision').write_text('b' * 40)
                    store.save_profile(Profile('new', 'socks5', {}))
                    current = state.read_text()
                    calls = []
                    def command(argv, **kwargs):
                        calls.append(argv)
                        if argv[-1] == 'restore' and (binaries / 'python').read_text() == 'old environment':
                            self.assertEqual(state.read_text(), original)
                            if fail:
                                raise RuntimeError('Old workload failed to start')
                        return subprocess.CompletedProcess(argv, 1 if argv[0] == 'systemctl' else 0, '', '')
                    with patch.object(updater, 'run', side_effect=command):
                        if fail:
                            with self.assertRaisesRegex(RuntimeError, 'current installation retained'):
                                updater.rollback(state, prefix=prefix, backup_id=snapshot.name, report=lambda _: None)
                        else:
                            updater.rollback(state, prefix=prefix, backup_id=snapshot.name, report=lambda _: None)
                    self.assertEqual((binaries / 'python').read_text(), 'new environment' if fail else 'old environment')
                    self.assertEqual(state.read_text(), current if fail else original)
                    self.assertEqual((prefix / '.splitforge-revision').read_text().strip(), ('b' if fail else 'a') * 40)
                    self.assertTrue(any(argv[-2:] == ['stop-all', '--preserve'] for argv in calls))
                    self.assertGreaterEqual(len(updater.available_backups(prefix, state)), 2)
                    self.assertFalse(list(prefix.glob('.rollback-*')))

    def test_foreign_backup_selection_is_rejected_before_stopping_anything(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'venv/bin').mkdir(parents=True)
            for name in ('python', 'splitforge'):
                (base / 'venv/bin' / name).write_text('test')
            with patch.object(updater, 'require_root'), patch.object(updater, 'BACKUP_ROOT', base / 'backups'), \
                 patch.object(updater, 'run') as command, self.assertRaisesRegex(ValueError, 'No matching'):
                updater.rollback(base / 'state.json', prefix=base, backup_id='../unrelated')
            command.assert_not_called()
