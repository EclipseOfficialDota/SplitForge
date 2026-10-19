import copy
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from splitforge.core.diagnostics import diagnose, guard_valid
from splitforge.state import AppBinding, Profile
from splitforge.web.server import Panel


class DiagnosticTests(unittest.TestCase):
    def profile_guard(self):
        profile = Profile('guard', 'wireguard', {}, slot=1)
        entries = [{'chain': {'name': name, 'hook': name, 'type': 'filter', 'policy': 'drop'}}
                   for name in ('input', 'output', 'forward')]
        entries.append({'rule': {'chain': 'output', 'expr': [
            {'match': {'op': '==', 'left': {'meta': {'key': 'oifname'}}, 'right': profile.interface}}, {'accept': None}]}})
        return profile, {'nftables': entries}

    def test_guard_rejects_unconditional_accept_jump_and_unhooked_policy(self):
        profile, document = self.profile_guard()
        self.assertTrue(guard_valid(document, profile))
        for expression in ({'accept': None}, {'jump': {'target': 'allow_everything'}}):
            changed = copy.deepcopy(document)
            changed['nftables'].append({'rule': {'chain': 'output', 'expr': [expression]}})
            self.assertFalse(guard_valid(changed, profile))
        document['nftables'][1]['chain'].pop('hook')
        self.assertFalse(guard_valid(document, profile))

    def fixture(self):
        profile = Profile('fixture', 'socks5', {})
        app = AppBinding('bot', ['/bin/sleep', '100'], profile_id=profile.id, enabled=True)
        store = Mock()
        store.profiles.return_value = [profile]
        store.apps.return_value = [app]
        store.snapshot.return_value = {'users': {}}
        manager = Mock()
        manager.status.return_value = {'active': True, 'namespace': True}
        manager.test.return_value = {'exit_ip': '192.0.2.1'}
        runner = Mock()
        runner.running.return_value = True
        return profile, app, store, manager, runner

    def command(self, argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1 if 'is-enabled' in argv else 0,
                                           stdout='[]' if argv[0] == 'ip' else 'resolver-ok', stderr='')

    @patch('splitforge.web.setup.load_settings', return_value=None)
    @patch('splitforge.core.diagnostics.shutil.which', return_value=None)
    @patch('splitforge.core.diagnostics.require_root')
    @patch('splitforge.core.diagnostics.run')
    @patch('splitforge.core.diagnostics.dependencies.component_installed', return_value=True)
    def test_scan_does_not_install_restart_or_rebind(self, installed, command, root, which, settings):
        profile, app, store, manager, runner = self.fixture()
        command.side_effect = self.command
        with patch('splitforge.core.diagnostics.namespace_checks', return_value=[('firewall', False, 'Guard failed')]), \
                patch('splitforge.core.diagnostics.dependencies.install') as install:
            result = diagnose(store, manager, runner, report=lambda message: None)
        install.assert_not_called()
        manager.start.assert_not_called()
        manager.stop.assert_not_called()
        runner.bind.assert_not_called()
        self.assertGreater(result['errors'], 0)
        self.assertTrue(any(row['category'] == 'firewall' and row['status'] == 'error' for row in result['checks']))

    @patch('splitforge.web.setup.load_settings', return_value=None)
    @patch('splitforge.core.diagnostics.shutil.which', return_value=None)
    @patch('splitforge.core.diagnostics.require_root')
    @patch('splitforge.core.diagnostics.run')
    @patch('splitforge.core.diagnostics.dependencies.component_installed', return_value=True)
    def test_repair_rebuilds_namespace_then_restarts_same_tunnel_assignments(self, installed, command, root, which, settings):
        profile, app, store, manager, runner = self.fixture()
        command.side_effect = self.command
        sequence = []
        manager.stop.side_effect = lambda value: sequence.append(('stop', value))
        manager.start.side_effect = lambda value: sequence.append(('start', value))
        runner.bind.side_effect = lambda app_id, profile_id, **kwargs: sequence.append(('bind', app_id, profile_id))
        with patch('splitforge.core.diagnostics.namespace_checks', side_effect=[
                [('dns', False, 'Wrong resolver')], [('dns', True, '')]]):
            result = diagnose(store, manager, runner, repair=True, report=lambda message: None)
        self.assertEqual(sequence, [('stop', profile.id), ('start', profile.id), ('bind', app.id, profile.id)])
        self.assertTrue(any(row['repaired'] for row in result['checks']))
        self.assertFalse(any(call.args[1] is None for call in runner.bind.call_args_list))

    def test_panel_validates_repair_and_exposes_structured_result(self):
        panel = SimpleNamespace(store=Mock(), manager=Mock(), runner=Mock(), route_baseline='[]',
                                lock=__import__('threading').Lock(), _text=Panel._text)
        with patch('splitforge.core.diagnostics.diagnose', return_value={'errors': 0, 'warnings': 1}) as check:
            Panel._dispatch(panel, {'action': 'diagnostics.run', 'repair': False}, lambda message: None)
            self.assertFalse(check.call_args.kwargs['repair'])
            self.assertEqual(panel.diagnostics['warnings'], 1)
            with self.assertRaises(ValueError):
                Panel._dispatch(panel, {'action': 'diagnostics.run', 'repair': 'false'}, lambda message: None)
