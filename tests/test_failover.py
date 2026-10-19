import dataclasses
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from splitforge.core.failover import FailoverMonitor, unit_name
from splitforge.core.runner import Runner
from splitforge.protocols.manager import ProtocolManager
from splitforge.state import AppBinding, Profile, StateStore


class FailoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = StateStore(Path(self.temp.name) / 'state.json')
        self.primary = self.store.save_profile(Profile('primary', 'socks5', {}))
        self.backup = self.store.save_profile(Profile('backup', 'socks5', {}))
        self.app = AppBinding('worker', ['/usr/bin/sleep', '300'], profile_id=self.primary.id, enabled=True,
                              primary_profile_id=self.primary.id, backup_profile_id=self.backup.id, failover_enabled=True)
        self.store.save_app(self.app)
        self.manager = Mock()
        self.manager.status.return_value = {'active': True, 'namespace': True}
        self.runner = Mock()
        self.runner.running.return_value = True
        def bind(app_id, profile_id, *, preserve_failover, expected):
            if self.store.app(app_id) != expected:
                raise RuntimeError('Changed policy')
            updated = dataclasses.replace(expected, profile_id=profile_id)
            self.store.save_app(updated)
            return updated
        self.runner.bind.side_effect = bind
        self.guard = patch('splitforge.core.failover.namespace_checks', return_value=[('guard', True, '')])
        self.guard.start()

    def tearDown(self):
        self.guard.stop()
        self.temp.cleanup()

    def test_two_failed_checks_switch_to_backup_then_keep_healthy_backup(self):
        self.manager.test.side_effect = lambda value, **kwargs: (_ for _ in ()).throw(RuntimeError('Down')) if value == self.primary.id else {}
        monitor = FailoverMonitor(self.store, self.manager, self.runner, report=lambda message: None)
        monitor.cycle()
        self.runner.bind.assert_not_called()
        monitor.cycle()
        self.assertEqual(self.store.app(self.app.id).profile_id, self.backup.id)
        self.runner.bind.assert_called_once_with(self.app.id, self.backup.id, preserve_failover=True, expected=self.app)
        monitor.cycle()
        self.assertEqual(self.runner.bind.call_count, 1)
        self.assertEqual(self.store.app(self.app.id).primary_profile_id, self.primary.id)

    def test_both_failed_suspend_and_retain_intent_without_direct_fallback(self):
        self.manager.test.side_effect = RuntimeError('No egress')
        monitor = FailoverMonitor(self.store, self.manager, self.runner, threshold=1, report=lambda message: None)
        monitor.cycle()
        self.runner.suspend.assert_called_once_with(self.app)
        self.runner.bind.assert_not_called()
        self.assertTrue(self.store.app(self.app.id).enabled)
        self.assertEqual(self.store.app(self.app.id).profile_id, self.primary.id)

    def test_stopped_app_is_not_restarted_and_missing_guard_is_not_accepted(self):
        self.store.save_app(dataclasses.replace(self.app, enabled=False))
        monitor = FailoverMonitor(self.store, self.manager, self.runner, threshold=1, report=lambda message: None)
        monitor.cycle()
        self.manager.test.assert_not_called()
        self.store.save_app(self.app)
        with patch('splitforge.core.failover.namespace_checks', return_value=[('guard', False, 'Broken')]):
            monitor.cycle()
        self.runner.bind.assert_not_called()
        self.runner.suspend.assert_called_once()

    def test_backup_and_primary_references_prevent_profile_deletion(self):
        self.store.save_app(dataclasses.replace(self.app, profile_id=self.backup.id))
        for profile in (self.primary, self.backup):
            with self.assertRaisesRegex(ValueError, 'assigned'):
                self.store.delete_profile(profile.id)
        self.assertEqual(len(self.store.profiles()), 2)
        manager = ProtocolManager(self.store)
        with patch('splitforge.protocols.manager.require_root'), patch.object(manager, 'stop') as stop, \
                patch('splitforge.protocols.manager.Path') as path:
            path.return_value.exists.return_value = True
            with self.assertRaises(ValueError):
                manager.remove(self.primary.id)
        stop.assert_not_called()
        path.assert_not_called()

    def test_stale_probe_cannot_override_a_manual_stop(self):
        self.store.save_app(dataclasses.replace(self.app, enabled=False))
        runner = Runner(self.store, self.manager)
        with patch('splitforge.core.runner.require_root'), patch('splitforge.core.runner.run') as command:
            with self.assertRaisesRegex(RuntimeError, 'assignment changed'):
                runner.bind(self.app.id, self.backup.id, preserve_failover=True, expected=self.app)
        command.assert_not_called()
        self.assertFalse(self.store.app(self.app.id).enabled)

    def test_manual_direct_assignment_disables_policy(self):
        runner = Runner(self.store, self.manager)
        path = Path(self.temp.name) / 'unit.service'
        def command(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 1 if 'is-active' in argv or 'is-enabled' in argv else 0, stdout='', stderr='')
        with patch('splitforge.core.runner.require_root'), patch.object(runner, '_path', return_value=path), \
                patch('splitforge.core.runner.run', side_effect=command):
            runner.bind(self.app.id, None)
        app = self.store.app(self.app.id)
        self.assertFalse(app.failover_enabled)
        self.assertIsNone(app.profile_id)
        self.assertIsNone(app.backup_profile_id)

    def test_policy_validation_and_monitor_identity(self):
        with self.assertRaises(ValueError):
            dataclasses.replace(self.app, profile_id=None)
        with self.assertRaises(ValueError):
            dataclasses.replace(self.app, kill_switch=False)
        with self.assertRaises(ValueError):
            dataclasses.replace(self.app, backup_profile_id=self.primary.id)
        self.assertNotEqual(unit_name(self.store), unit_name(StateStore(Path(self.temp.name) / 'other.json')))

    def test_unavailable_primary_can_start_with_verified_backup(self):
        self.store.save_app(dataclasses.replace(self.app, failover_enabled=False, primary_profile_id=None,
                                               backup_profile_id=None, profile_id=None))
        runner = Runner(self.store, self.manager)
        self.manager.start.side_effect = [RuntimeError('Primary down'), None]
        path = Path(self.temp.name) / 'unit.service'
        command = lambda argv, **kwargs: subprocess.CompletedProcess(argv, 1 if 'is-active' in argv or 'is-enabled' in argv else 0,
                                                                     stdout='', stderr='')
        with patch('splitforge.core.runner.require_root'), patch('splitforge.core.failover.ensure_service'), \
                patch.object(runner, '_path', return_value=path), patch('splitforge.core.runner.run', side_effect=command), \
                patch('splitforge.core.diagnostics.namespace_checks', return_value=[('guard', True, '')]):
            updated = runner.bind(self.app.id, self.primary.id, backup_profile_name=self.backup.id)
        self.assertEqual(updated.profile_id, self.backup.id)
        self.assertEqual(updated.primary_profile_id, self.primary.id)
        self.assertEqual(updated.backup_profile_id, self.backup.id)

    def test_initial_both_down_saves_blocked_policy_instead_of_retaining_direct(self):
        self.store.save_app(dataclasses.replace(self.app, failover_enabled=False, primary_profile_id=None,
                                               backup_profile_id=None, profile_id=None))
        runner = Runner(self.store, self.manager)
        self.manager.start.side_effect = RuntimeError('Both down')
        path = Path(self.temp.name) / 'unit.service'
        command = lambda argv, **kwargs: subprocess.CompletedProcess(argv, 1 if 'is-active' in argv or 'is-enabled' in argv else 0,
                                                                     stdout='', stderr='')
        with patch('splitforge.core.runner.require_root'), patch('splitforge.core.failover.ensure_service'), \
                patch.object(runner, '_path', return_value=path), patch('splitforge.core.runner.run', side_effect=command) as execute:
            updated = runner.bind(self.app.id, self.primary.id, backup_profile_name=self.backup.id)
        self.assertTrue(updated.enabled)
        self.assertTrue(updated.failover_enabled)
        self.assertEqual(updated.profile_id, self.primary.id)
        self.assertIn(self.primary.namespace, path.read_text())
        self.assertTrue(any(call.args[0][:2] == ['systemctl', 'stop'] for call in execute.call_args_list))
        self.assertFalse(any(call.args[0][:2] == ['systemctl', 'start'] for call in execute.call_args_list))
