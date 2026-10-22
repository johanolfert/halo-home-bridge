"""Regression tests for delayed cloud responses and fast successive commands."""
import importlib
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if 'halo_under_test' not in sys.modules:
    package = types.ModuleType('halo_under_test')
    package.__path__ = [str(ROOT / 'custom_components' / 'halo_home_bridge')]
    sys.modules[package.__name__] = package
tracking = importlib.import_module('halo_under_test.state_tracking')


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.now = 1
        self.tracker = tracking.StateTracker(clock=lambda: self.now)
        self.old = '2026-10-12T03:00:00+00:00'
        self.new = '2026-10-12T03:00:03+00:00'
        self.read(3000, self.old, 0)

    def read(self, kelvin, stamp, started):
        return self.tracker.reconcile('lamp', {'kelvin': kelvin}, {'kelvin': stamp}, started)

    def test_accepted_command_is_not_undone_by_old_get(self):
        self.tracker.accept('lamp', 'white', '4000')
        self.assertEqual(self.read(3000, self.old, 2)['kelvin'], 4000)
        self.assertEqual(self.tracker.attributes('lamp')['pending_confirmation'], ['kelvin'])

    def test_matching_new_cloud_snapshot_confirms_command(self):
        self.tracker.accept('lamp', 'white', '4000')
        self.assertEqual(self.read(4000, self.new, 2)['kelvin'], 4000)
        self.assertFalse(self.tracker.has_pending({'lamp'}))
        self.assertEqual(self.tracker.attributes('lamp')['command_readback']['kelvin'], 'confirmed')

    def test_old_snapshot_after_confirmation_cannot_revert_ui(self):
        self.tracker.accept('lamp', 'white', '4000')
        self.read(4000, self.new, 2)
        self.assertEqual(self.read(3000, self.old, 3)['kelvin'], 4000)

    def test_inflight_read_from_before_command_cannot_confirm_it(self):
        self.tracker.accept('lamp', 'white', '4000')
        self.read(4000, self.new, 0.5)
        self.assertTrue(self.tracker.has_pending({'lamp'}))

    def test_out_of_order_get_is_rejected_even_with_equal_timestamp(self):
        self.read(4000, self.new, 3)
        self.assertEqual(self.read(3000, self.new, 2)['kelvin'], 4000)

    def test_last_of_rapid_commands_wins(self):
        self.tracker.accept('lamp', 'white', '4000')
        self.now = 2
        self.tracker.accept('lamp', 'white', '5000')
        self.assertEqual(self.read(4000, self.new, 3)['kelvin'], 5000)
        self.assertTrue(self.tracker.has_pending({'lamp'}))
        self.assertEqual(self.read(5000, '2026-10-12T03:00:05+00:00', 4)['kelvin'], 5000)
        self.assertFalse(self.tracker.has_pending({'lamp'}))

    def test_return_to_baseline_waits_for_new_readback(self):
        self.tracker.accept('lamp', 'white', '4000')
        self.now = 2
        self.tracker.accept('lamp', 'white', '3000')
        self.read(3000, self.old, 3)
        self.assertTrue(self.tracker.has_pending({'lamp'}))
        self.read(3000, self.new, 4)
        self.assertFalse(self.tracker.has_pending({'lamp'}))

    def test_timeout_restores_cloud_value_instead_of_faking_success(self):
        self.tracker.accept('lamp', 'white', '4000')
        self.now = 32
        self.assertEqual(self.read(3000, self.old, 31)['kelvin'], 3000)
        self.assertEqual(self.tracker.attributes('lamp')['command_readback']['kelvin'], 'not_confirmed')

    def test_rerender_does_not_poison_cloud_baseline(self):
        self.tracker.accept('lamp', 'white', '4000')
        self.tracker.reconcile('lamp', {'kelvin': 4000}, {'kelvin': self.old})
        self.assertEqual(self.tracker.observed[('lamp', 'kelvin')][0], 3000)
        self.now = 32
        self.assertEqual(self.read(3000, self.old, 31)['kelvin'], 3000)

    def test_failed_command_is_not_recorded_as_confirmed(self):
        self.tracker.accept('lamp', 'white', '4000')
        self.tracker.fail('lamp')
        self.assertFalse(self.tracker.has_pending({'lamp'}))
        self.assertEqual(self.tracker.attributes('lamp')['command_readback']['kelvin'], 'not_confirmed')

    def test_dimming_percentage_and_on_off_conversion(self):
        self.assertEqual(tracking.command_value('dim', '50%'), 128)
        self.assertEqual(tracking.command_value('on_off', 'off'), False)

    def test_external_change_with_newer_timestamp_is_visible(self):
        self.tracker.accept('lamp', 'white', '4000')
        self.read(4000, self.new, 2)
        self.assertEqual(self.read(2700, '2026-10-12T03:00:20+00:00', 20)['kelvin'], 2700)


if __name__ == '__main__':
    unittest.main()
