import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner
from splitforge import __version__
from splitforge.cli import app


class CLITests(unittest.TestCase):
    def test_web_command_preserves_custom_state_and_demo_options(self):
        with patch("splitforge.web.server.serve") as serve:
            result = CliRunner().invoke(app, ["--state", "/root/private.json", "web", "--demo", "--port", "9000"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(serve.call_args.args, (Path("/root/private.json"),))
        self.assertEqual(serve.call_args.kwargs["port"], 9000)
        self.assertTrue(serve.call_args.kwargs["demo"])

    def test_update_command_passes_prefix_and_state_to_updater(self):
        with patch("splitforge.core.updater.update") as update:
            result = CliRunner().invoke(app, ["--state", "/root/custom-state.json", "update", "--prefix", "/opt/custom", "--force"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(update.call_args.args, (Path("/root/custom-state.json"),))
        self.assertEqual(update.call_args.kwargs["prefix"], Path("/opt/custom"))
        self.assertTrue(update.call_args.kwargs["force"])

    def test_help_and_version_do_not_mutate_state(self):
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("profile", result.output)
        result = runner.invoke(app, ["--version"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(__version__, result.output.strip())

    def test_empty_profile_list_is_valid_json_and_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "absent.json"
            result = CliRunner().invoke(app, ["--state", str(state), "profile", "list", "--json"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(json.loads(result.output), [])
            self.assertFalse(state.exists())

    @unittest.skipUnless(os.name == "posix", "State writes use POSIX locks")
    def test_register_root_command_preserves_command_arguments(self):
        with tempfile.TemporaryDirectory() as directory, patch("splitforge.cli.require_root"):
            state = Path(directory) / "state.json"
            result = CliRunner().invoke(app, ["--state", str(state), "app", "add", "root-bot", "--user", "root",
                "--cwd", "/root", "--", "/usr/bin/python3", "/root/bot.py", "--some-option", "literal value"])
            self.assertEqual(result.exit_code, 0, f"{result.output}: {result.exception}")
            record = next(iter(json.loads(state.read_text())["apps"].values()))
            self.assertEqual(record["user"], "root")
            self.assertEqual(record["argv"][-3:], ["/root/bot.py", "--some-option", "literal value"])
