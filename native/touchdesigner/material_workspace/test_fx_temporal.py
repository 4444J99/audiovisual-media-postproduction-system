"""Clock-domain checks independent of the TouchDesigner runtime."""
import unittest

from fx_temporal import plan


class TemporalPlanTests(unittest.TestCase):
    def test_delay_keeps_full_requested_history(self):
        result = plan('delay', {'time': 2, 'taps': 8}, 20)
        self.assertEqual(result['seconds'], 16)
        self.assertEqual(result['ages'], [2, 4, 6, 8, 10, 12, 14, 16])

    def test_stutter_captures_then_holds(self):
        params = {'capture': 2, 'window': .5, 'rate': 1, 'gap': .1}
        self.assertTrue(plan('stutter', params, 2.25)['capture'])
        held = plan('stutter', params, 2.75)
        self.assertFalse(held['capture'])
        self.assertAlmostEqual(held['ages'][0], .25)

    def test_reverse_reads_only_history(self):
        for speed in (.25, 1, 3):
            for step in range(1000):
                result = plan('reverse', {'span': 2.2, 'speed': speed}, step / 30)
                self.assertGreaterEqual(result['ages'][0], 0)
                self.assertLessEqual(result['ages'][0], result['seconds'])

    def test_typography_history_is_separate_from_picture(self):
        params = {'mode': 2, 'copies': 32}
        self.assertEqual(plan('typography', params, 10, 0)['seconds'], 0)
        text = plan('typography', params, 10, 1)
        self.assertEqual(len(text['ages']), 32)
        self.assertAlmostEqual(text['seconds'], 9.92)

    def test_queue_exposes_every_capacity_slot(self):
        result = plan('queue', {'capacity': 24, 'rate': 20, 'burst': 5}, 3)
        self.assertEqual(len(result['ages']), 24)
        self.assertTrue(all(0 <= age <= result['seconds'] for age in result['ages']))


if __name__ == '__main__':
    unittest.main()
