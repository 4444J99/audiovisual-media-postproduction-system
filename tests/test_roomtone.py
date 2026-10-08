import unittest
import numpy as np
from amp.roomtone import assemble, pause_inventory, runs
from amp.audio import RATE


class RoomToneTests(unittest.TestCase):
    def test_all_fragments_seed_and_no_adjacent_reuse(self):
        x = np.random.default_rng(4).normal(0, .003, (RATE * 2, 2)).astype(np.float32)
        regions = [(10, 40), (50, 90), (120, 160)]
        a, edits = assemble(x, regions, duration=4, seed=12)
        b, same = assemble(x, regions, duration=4, seed=12)
        np.testing.assert_array_equal(a, b)
        self.assertEqual(edits, same)
        self.assertEqual(a.shape, (RATE * 4, 2))
        self.assertEqual(set(e["source_fragment"] for e in edits), {0, 1, 2})
        self.assertTrue(all(a["source_fragment"] != b["source_fragment"] for a, b in zip(edits, edits[1:])))
        self.assertTrue(np.isfinite(a).all())

    def test_quiet_words_and_transients_excluded(self):
        x = np.random.default_rng(5).normal(0, .002, (RATE * 4, 2)).astype(np.float32)
        x[int(2.5 * RATE):int(2.52 * RATE)] = .1
        p = np.zeros(125)
        p[31:40] = .3  # Quiet voice excluded even outside transcript.
        regions, inventory, _ = pause_inventory(x, [{"start": .4, "end": .8}], p, .032, start=0, end=4)
        for a, b in regions:
            self.assertFalse(a * .01 < 1.28 and b * .01 > .99)
            self.assertFalse(a * .01 < 2.52 and b * .01 > 2.5)
        self.assertTrue(inventory)

    def test_no_empty_pool_synthesis(self):
        with self.assertRaises(ValueError):
            assemble(np.zeros((100, 2)), [], duration=1)


if __name__ == "__main__":
    unittest.main()
