import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from splitforge.core.updater import REPOSITORY, update
from splitforge.state import Profile, StateStore


@unittest.skipUnless(os.name == "posix", "POSIX update locks")
class UpdaterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.prefix = self.base / "custom-install"
        binaries = self.prefix / "venv/bin"
        binaries.mkdir(parents=True)
        for name in ("python", "splitforge"):
            (binaries / name).write_text("test binary")
        self.state = self.base / "custom-state.json"
        StateStore(self.state).save_profile(Profile("private", "socks5", {"password": "test-only-secret"}))
        self.revision = "a" * 40
        self.messages = []
        for target, options in (
            ("splitforge.core.updater.require_root", {}),
            ("splitforge.core.updater.shutil.which", {"return_value": "/usr/bin/git"}),
            ("splitforge.core.updater.BACKUP_ROOT", {"new": self.base / "backups"}),
            ("splitforge.core.updater.run", {"side_effect": self.git}),
        ):
            context = patch(target, **options)
            context.start()
            self.addCleanup(context.stop)

    def git(self, argv, **kwargs):
        if "clone" in argv:
            self.assertIn(REPOSITORY, argv)
            source = Path(argv[-1])
            for relative in ("install.sh", "pyproject.toml", "requirements.lock", "splitforge/__init__.py"):
                path = source / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("test source")
            return subprocess.CompletedProcess(argv, 0, "", "")
        return subprocess.CompletedProcess(argv, 0, self.revision + "\n", "")

    def test_update_backs_up_state_preserves_prefix_and_restores_using_the_same_state(self):
        original = self.state.read_bytes()
        with patch("splitforge.core.updater.subprocess.run", return_value=subprocess.CompletedProcess([], 0)) as installer:
            update(self.state, prefix=self.prefix, report=self.messages.append)
        args = installer.call_args.args[0]
        self.assertIn(str(self.prefix), args)
        for flag in ("--upgrade", "--restore", "--skip-proxy-cores"):
            self.assertIn(flag, args)
        self.assertEqual(installer.call_args.kwargs["env"]["SPLITFORGE_STATE"], str(self.state))
        backups = list((self.base / "backups").glob("*/state.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual(backups[0].parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.state.read_bytes(), original)
        self.assertEqual((self.prefix / ".splitforge-revision").read_text().strip(), self.revision)
        self.assertFalse(Path(args[1]).exists(), "Temporary source should be cleaned up")

    def test_same_revision_does_not_restart_workloads(self):
        (self.prefix / ".splitforge-revision").write_text(self.revision)
        with patch("splitforge.core.updater.subprocess.run") as installer:
            update(self.state, prefix=self.prefix, report=self.messages.append)
        installer.assert_not_called()
        self.assertFalse((self.base / "backups").exists())
        self.assertIn("Already up to date", self.messages[-1])

    def test_failed_install_retains_backup_and_does_not_claim_success(self):
        with patch("splitforge.core.updater.subprocess.run", return_value=subprocess.CompletedProcess([], 9)), \
             self.assertRaisesRegex(RuntimeError, "Workloads may remain stopped"):
            update(self.state, prefix=self.prefix, report=self.messages.append)
        self.assertEqual(len(list((self.base / "backups").glob("*/state.json"))), 1)
        self.assertFalse((self.prefix / ".splitforge-revision").exists())

    def test_download_failure_does_not_run_the_installer_or_change_state(self):
        original = self.state.read_bytes()
        with patch("splitforge.core.updater.run", side_effect=RuntimeError("clone failed")), \
             patch("splitforge.core.updater.subprocess.run") as installer, self.assertRaises(RuntimeError):
            update(self.state, prefix=self.prefix, report=self.messages.append)
        installer.assert_not_called()
        self.assertEqual(self.state.read_bytes(), original)

    def test_second_update_is_rejected_while_the_installation_is_locked(self):
        import fcntl
        with (self.prefix / ".update.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch("splitforge.core.updater.subprocess.run") as installer, self.assertRaisesRegex(RuntimeError, "already running"):
                update(self.state, prefix=self.prefix, report=self.messages.append)
            installer.assert_not_called()
