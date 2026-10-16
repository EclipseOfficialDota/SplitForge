import contextlib
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from splitforge.core.runner import Runner
from splitforge.state import AppBinding, Profile


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.root = types.SimpleNamespace(pw_uid=0)
        self.user = types.SimpleNamespace(pw_uid=1000)
        self.passwords = patch.dict(sys.modules, {"pwd": types.SimpleNamespace(
            getpwnam=lambda name: {"root": self.root, "worker": self.user}[name],
            getpwuid=lambda uid: {0: self.root, 1000: self.user}[uid])})
        self.passwords.start()
        self.addCleanup(self.passwords.stop)
        self.store, self.manager = Mock(), Mock()
        self.runner = Runner(self.store, self.manager)
        self.profile = Profile("test", "socks5", {}, slot=1)

    def test_root_and_numeric_service_identity_are_supported(self):
        self.assertEqual(self.runner._identity("root").pw_uid, 0)
        self.assertEqual(self.runner._identity("0").pw_uid, 0)
        with self.assertRaises(KeyError):
            self.runner._identity("missing")
        content = self.runner._render(AppBinding("root-app", ["/usr/bin/python3", "/root/app.py"], user="root"), self.profile)
        self.assertIn("User=root", content)
        self.assertIn(f"NetworkNamespacePath=/run/netns/{self.profile.namespace}", content)
        self.assertIn("NoNewPrivileges=yes", content)
        self.assertIn("CapabilityBoundingSet=\n", content)

    def test_services_with_implicit_explicit_or_numeric_root(self):
        app = AppBinding("worker", service="worker.service", user="root")
        for user in ("", "root", "0"):
            with self.subTest(user=user), patch("splitforge.core.runner.run", return_value=subprocess.CompletedProcess(
                    [], 0, f"LoadState=loaded\nUser={user}\nId=worker.service\nNames=worker.service\nTriggeredBy=\n", "")):
                self.runner._validate_service(app)
        with patch("splitforge.core.runner.run", return_value=subprocess.CompletedProcess(
                [], 0, "LoadState=loaded\nUser=worker\n", "")), self.assertRaises(ValueError):
            self.runner._validate_service(app)

    def test_ssh_alias_and_host_network_services_remain_protected(self):
        for name in ("ssh.service", "sshd.service", "ssh@22.service", "systemd-networkd.service", "NetworkManager.service"):
            properties = f"LoadState=loaded\nUser=root\nId={name}\nNames=alias.service {name}\n"
            with self.subTest(name=name), patch("splitforge.core.runner.run", return_value=subprocess.CompletedProcess([], 0, properties, "")):
                with self.assertRaisesRegex(ValueError, "SSH and host networking"):
                    self.runner._validate_service(AppBinding("alias", service="alias.service", user="root"))

    def test_explicit_direct_does_not_inherit_root_user_mapping(self):
        self.store.snapshot.return_value = {"users": {"root": self.profile.id}}
        with patch("splitforge.core.runner.require_root"), patch("shutil.which", return_value="/usr/bin/id"), patch("subprocess.call", return_value=0) as execute:
            self.assertEqual(self.runner.execute(["id"], profile_name="direct", user="root", cwd="/root"), 0)
        self.manager.start.assert_not_called()
        args = execute.call_args.args[0]
        self.assertIn("--uid=root", args)
        self.assertFalse(any("NetworkNamespacePath=" in value for value in args))

    def test_one_off_root_retains_namespace_and_literal_arguments(self):
        self.store.snapshot.return_value = {"users": {}}
        self.store.profile.return_value = self.profile
        with patch("splitforge.core.runner.require_root"), patch("shutil.which", return_value="/usr/bin/echo"), patch("subprocess.call", return_value=0) as execute:
            self.runner.execute(["echo", "$HOME"], profile_name="test", user="root")
        args = execute.call_args.args[0]
        self.assertIn(f"--property=NetworkNamespacePath=/run/netns/{self.profile.namespace}", args)
        self.assertIn("--property=NoNewPrivileges=yes", args)
        self.assertEqual(args[-1], "$$HOME")
        self.assertEqual(sum(arg.startswith("--property=BindReadOnlyPaths=") for arg in args), 1)

    def test_root_does_not_enable_uid_wide_user_manager_binding(self):
        with patch("splitforge.core.runner.require_root"), self.assertRaisesRegex(ValueError, "non-system"):
            self.runner.bind_user("root", "test")
        self.manager.start.assert_not_called()

    def test_failed_swap_restores_unit_and_assignment(self):
        old = AppBinding("worker", ["/usr/bin/true"], user="root")
        self.store.profile.return_value = self.profile
        self.store.app.return_value = old
        self.store.operation.side_effect = lambda *args: contextlib.nullcontext()
        failed = False

        def command(argv, **kwargs):
            nonlocal failed
            if argv[:2] == ["systemctl", "start"] and not failed:
                failed = True
                raise RuntimeError("Simulated start failure")
            return subprocess.CompletedProcess(argv, 0, "", "")

        with tempfile.TemporaryDirectory() as directory:
            unit = Path(directory) / "worker.service"
            unit.write_text("original unit")
            def write(path, content, mode=0o600):
                path.write_text(content)
            with patch("splitforge.core.runner.require_root"), patch.object(self.runner, "_path", return_value=unit), \
                 patch.object(self.runner, "running", side_effect=[True, False]), \
                 patch("splitforge.core.runner.atomic_secret", side_effect=write), patch("splitforge.core.runner.run", side_effect=command):
                with self.assertRaisesRegex(RuntimeError, "previous assignment restored"):
                    self.runner.bind(old.id, "test")
            self.assertEqual(unit.read_text(), "original unit")
        self.store.save_app.assert_called_with(old)

    def test_registered_but_unbound_application_can_be_stopped(self):
        app = AppBinding("registered-only", ["/usr/bin/true"], user="root")
        self.store.app.return_value = app
        self.store.operation.side_effect = lambda *args: contextlib.nullcontext()
        with tempfile.TemporaryDirectory() as directory, patch("splitforge.core.runner.require_root"), \
             patch.object(self.runner, "_path", return_value=Path(directory) / "absent.service"), \
             patch("splitforge.core.runner.run") as command:
            self.runner.stop(app.id)
        command.assert_not_called()
        self.assertFalse(self.store.save_app.call_args.args[0].enabled)
