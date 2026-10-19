"""Rate validation and namespace-only command generation."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from splitforge.core.speed import MAX_RATE, apply, validate_rate
from splitforge.core.runner import Runner
from splitforge.core.traffic import empty_data, new_row, validate_data
from splitforge.state import Profile


class SpeedTests(unittest.TestCase):
    def test_proxychains_cannot_bypass_a_configured_profile_limit(self):
        runner = Runner(Mock(), Mock())
        profile = Profile('limited', 'socks5', {})
        runner.store.profile.return_value = profile
        runner._identity = Mock()
        for row in ({'quota': 1024}, {'download_bps': 1000}, {'upload_bps': 1000}):
            with self.subTest(row=row), patch('splitforge.core.runner.require_root'), \
                    patch('splitforge.core.traffic.TrafficStore') as meter:
                meter.return_value.snapshot.return_value = {'profiles': {profile.id: row}}
                with self.assertRaisesRegex(ValueError, 'namespace execution'):
                    runner.proxychains(profile.id, ['id'])
        runner.manager.start.assert_not_called()

    def test_validation_and_old_backup_compatibility(self):
        for value in (-1, True, 1.5, '1000', MAX_RATE + 1, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_rate(value)
        for value in (0, 1000, MAX_RATE):
            self.assertEqual(validate_rate(value), value)
        data = empty_data()
        data['profiles']['aa000001'] = new_row()
        validate_data(data)  # Old backups omit speed fields.
        data['profiles']['aa000001']['download_bps'] = True
        with self.assertRaises(ValueError):
            validate_data(data)

    @patch('splitforge.core.speed.require_root')
    def test_only_profile_namespace_is_changed_and_owned_rules_are_removed(self, _):
        profile = Profile('speed', 'socks5', {})
        netns = Mock()
        netns.command.return_value = SimpleNamespace(stdout='[]')
        apply(profile, 2000000, 1000000, netns=netns)
        calls = [call.args for call in netns.command.call_args_list]
        self.assertTrue(all(call[0] == profile for call in calls))
        self.assertTrue(any('tbf' in call and '1000000bit' in call for call in calls))
        self.assertTrue(any('police' in call and '2000000bit' in call for call in calls))
        netns.reset_mock()
        netns.command.side_effect = [SimpleNamespace(stdout=json.dumps([
            {'root': True, 'handle': '7f00:', 'kind': 'tbf'}, {'kind': 'ingress'}])),
            SimpleNamespace(stdout=''), SimpleNamespace(stdout='[{"pref":49152}]'), SimpleNamespace(stdout='')]
        apply(profile, netns=netns)
        calls = [call.args for call in netns.command.call_args_list]
        self.assertTrue(any('del' in call and '7f00:' in call for call in calls))
        self.assertTrue(any('del' in call and '49152' in call for call in calls))
