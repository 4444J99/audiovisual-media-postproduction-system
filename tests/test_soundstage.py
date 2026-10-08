import unittest
import numpy as np
from amp.audio import RATE
from amp.soundstage import scene_envelope


class SoundStageTests(unittest.TestCase):
    def test_bed_outside_scene_and_smooth_handles(self):
        e = scene_envelope(RATE * 112)
        self.assertTrue((e[:round(5.033333 * RATE)] == 0).all())
        self.assertTrue((e[round(107.166667 * RATE):] == 0).all())
        self.assertEqual(e[60 * RATE], 1)
        self.assertLess(np.max(np.abs(np.diff(e))), .001)


if __name__ == "__main__":
    unittest.main()
