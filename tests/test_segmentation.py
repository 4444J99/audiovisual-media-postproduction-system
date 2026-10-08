import unittest

import numpy as np

from amp.segmentation import PersonMask, nms, preserve_bodies, union_alpha


class SegmentationTests(unittest.TestCase):
    def test_empty_frame_does_not_reuse_prior_person(self):
        self.assertTrue(np.array_equal(union_alpha([], (4, 6)), np.zeros((4, 6))))

    def test_union_and_body_recovery(self):
        alpha = np.zeros((4, 6), np.float32)
        alpha[1:3, 2:4] = 1
        person = PersonMask(np.array([2, 1, 4, 3]), .9, alpha)
        union = union_alpha([person], (4, 6))
        source = np.full((4, 6, 3), 200, np.uint8)
        treatment = np.full((4, 6, 3), 20, np.uint8)
        output = preserve_bodies(source, treatment, union)
        np.testing.assert_array_equal(output[1:3, 2:4], source[1:3, 2:4])
        np.testing.assert_array_equal(output[0], treatment[0])

    def test_fractional_alpha_and_bad_geometry(self):
        source = np.full((2, 2, 3), 200, np.uint8)
        treatment = np.zeros_like(source)
        output = preserve_bodies(source, treatment, np.full((2, 2), .5))
        self.assertEqual(int(output[0, 0, 0]), 100)
        with self.assertRaises(ValueError):
            preserve_bodies(source, treatment, np.zeros((3, 2)))

    def test_nms_retains_distinct_people(self):
        boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11], [30, 0, 40, 10]], dtype=float)
        self.assertEqual(nms(boxes, np.array([.9, .8, .7]), .6), [0, 2])


if __name__ == "__main__":
    unittest.main()
