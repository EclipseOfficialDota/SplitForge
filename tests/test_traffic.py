"""Counter arithmetic checks run without Linux, privilege or network access."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from splitforge.core.traffic import MAX_COUNTER, TrafficMonitor, empty_data, new_row, update_row, used, validate_data


class TrafficCounterTests(unittest.TestCase):
    def test_budget_stops_only_the_exhausted_application(self):
        store, manager, runner = Mock(), Mock(), Mock()
        store.apps.return_value = [SimpleNamespace(id='aa000001', enabled=True), SimpleNamespace(id='aa000002', enabled=True)]
        store.profiles.return_value = []
        monitor = TrafficMonitor(store, manager, runner)
        monitor.traffic = Mock()
        monitor.traffic.snapshot.return_value = empty_data()
        monitor.traffic.record_app.side_effect = [{'blocked': True}, {'blocked': False}]
        monitor.cycle()
        runner.stop.assert_called_once_with('aa000001')
        manager.stop.assert_not_called()

    def test_persistence_failure_keeps_quota_protection_and_unlimited_app_separate(self):
        store, manager, runner = Mock(), Mock(), Mock()
        store.apps.return_value = [SimpleNamespace(id='aa000001', enabled=True), SimpleNamespace(id='aa000002', enabled=True)]
        store.profiles.return_value = []
        monitor = TrafficMonitor(store, manager, runner)
        monitor.traffic = Mock()
        data = empty_data()
        data['apps']['aa000001'] = dict(new_row(), quota=1024)
        monitor.traffic.snapshot.return_value = data
        monitor.traffic.record_app.side_effect = OSError('Read-only filesystem')
        with patch('splitforge.core.traffic.logging.exception'):
            monitor.cycle()
        runner.stop.assert_called_once_with('aa000001')

    def test_two_apps_keep_independent_counters_across_restart_and_stale_samples(self):
        first, second = new_row(), new_row()
        update_row(first, ('first-invocation', 100, 30), 1)
        update_row(second, ('separate-app-same-uid-and-namespace', 700, 9), 1)
        update_row(first, ('first-invocation', 150, 50), 2)
        self.assertEqual((first['rx'], first['tx']), (150, 50))
        self.assertEqual((second['rx'], second['tx']), (700, 9))
        update_row(first, ('second-invocation', 20, 5), 3)
        update_row(first, ('first-invocation', 170, 60), 4)  # final old invocation
        update_row(first, ('first-invocation', 150, 50), 5)  # stale read cannot rewind it
        update_row(first, ('first-invocation', 170, 60), 6)  # duplicate final
        self.assertEqual((first['rx'], first['tx']), (190, 65))
        first['baseline'] = 200
        self.assertEqual(used(first), 55)

    def test_unavailable_and_invalid_counters_never_become_fake_zero_usage(self):
        for value in (MAX_COUNTER, -1, True, 0.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                update_row(new_row(), ('invocation', value, 0), 1)
        row = update_row(new_row(), ('invocation', 0, 0), 1)
        self.assertTrue(row['available'])
        self.assertTrue(row['supported'])

    def test_bounded_history_and_quota_schema_validation(self):
        row = new_row()
        for counter in range(150):
            update_row(row, ('invocation', counter, counter * 2), counter * 5)
        self.assertEqual(len(row['history']), 120)
        data = empty_data()
        data['apps']['aa000001'] = row
        self.assertEqual(validate_data(data), data)
        for change in ({'baseline': 999999}, {'quota': True}, {'quota': 0}, {'warn_percent': 100},
                       {'history': [[float('nan'), 0, 0]]}):
            broken = copy.deepcopy(data)
            broken['apps']['aa000001'].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_data(broken)
