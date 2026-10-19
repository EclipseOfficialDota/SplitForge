import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from splitforge.core import backup
from splitforge.state import AppBinding, Profile, StateStore


@unittest.skipUnless(os.name == 'posix', 'POSIX state and file permissions')
class BackupTests(unittest.TestCase):
    password = 'test-only-long-backup-password'

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.store = StateStore(self.base / 'state.json')
        profile = self.store.save_profile(Profile('private', 'socks5', {'password': 'secret-test-value'}))
        self.store.save_app(AppBinding('worker', ['/usr/bin/sleep', '60'], profile_id=profile.id))
        with patch('splitforge.web.setup.load_settings', return_value=None), patch.object(backup, 'run', return_value=Mock(returncode=1)):
            self.document = backup.capture(self.store)

    def test_roundtrip_unique_salts_and_tamper_wrong_password_rejection(self):
        first = backup.encrypt(self.document, self.password)
        self.assertNotIn('secret-test-value', first)
        self.assertNotEqual(first, backup.encrypt(self.document, self.password))
        self.assertEqual(backup.decrypt(first, self.password), self.document)
        damaged = first[:-8] + ('A' if first[-8] != 'A' else 'B') + first[-7:]
        for text, password in [(first, 'wrong-password-long'), (damaged, self.password)]:
            with self.assertRaisesRegex(ValueError, 'Incorrect backup password or damaged'):
                backup.decrypt(text, password)
        with self.assertRaises(ValueError):
            backup.encrypt(self.document, 'short')

    def test_invalid_state_and_external_certificate_paths_are_not_accepted(self):
        document = copy.deepcopy(self.document)
        document['state']['apps'][next(iter(document['state']['apps']))]['profile_id'] = '12345678'
        with self.assertRaises(ValueError):
            backup.decrypt(backup.encrypt(document, self.password), self.password)
        document = copy.deepcopy(self.document)
        profile = next(iter(document['state']['profiles'].values()))
        profile['tls_ca_file'] = '/etc/shadow'
        with self.assertRaisesRegex(ValueError, 'missing a referenced CA'):
            backup.validate(document)
        for text in ('plaintext', backup.MAGIC + 'not-base64!'):
            with self.assertRaises(ValueError):
                backup.decrypt(text, self.password)

    def test_export_is_private_and_never_overwrites_a_file_or_symlink(self):
        path = self.base / 'private.sfb'
        with patch.object(backup, 'require_root'), patch.object(backup, 'capture', return_value=self.document):
            backup.export_backup(self.store, path, self.password)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(backup.read_backup(path, self.password), self.document)
            with self.assertRaises(ValueError):
                backup.export_backup(self.store, path, self.password)
            link = self.base / 'link'
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                backup.export_backup(self.store, link, self.password)

    def test_invalid_restore_does_not_stop_workloads(self):
        runner, manager = Mock(), Mock()
        with patch.object(backup, 'require_root'), self.assertRaises(ValueError):
            backup.restore_backup(self.store, manager, runner, {'format': 999}, self.password)
        runner.remove.assert_not_called()
        manager.remove.assert_not_called()

