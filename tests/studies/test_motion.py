"""Tests for Wing 3 Motion & Gesture Decomposition framework (Issues #78-81, W03)."""
import unittest

from amp.studies.motion import (
    couple_gesture_to_sound_events,
    decompose_motion_field,
    extract_gesture_phrasing,
    retarget_motion_envelope,
)


class MotionStudiesTests(unittest.TestCase):
    def setUp(self):
        self.shot_id = "SHOT-001"
        self.frame_span = (155, 210)
        # 10 synthetic optical flow frames with both camera pan and subject gesture
        self.samples = [
            {"frame": 155, "dx": 2.0, "dy": 0.5, "camera_dx": 2.0, "camera_dy": 0.0, "joint_or_region": "arm"},
            {"frame": 156, "dx": 2.2, "dy": 0.8, "camera_dx": 2.0, "camera_dy": 0.0, "joint_or_region": "arm"},
            {"frame": 157, "dx": 3.5, "dy": 1.5, "camera_dx": 2.0, "camera_dy": 0.0, "joint_or_region": "arm"},
            {"frame": 158, "dx": 4.8, "dy": 2.2, "camera_dx": 2.0, "camera_dy": 0.0, "joint_or_region": "arm"},
            {"frame": 159, "dx": 2.5, "dy": 0.5, "camera_dx": 2.0, "camera_dy": 0.0, "joint_or_region": "arm"},
            {"frame": 160, "dx": 2.0, "dy": 0.0, "camera_dx": 2.0, "camera_dy": 0.0, "joint_or_region": "arm"},
            {"frame": 161, "dx": 2.0, "dy": 0.0, "camera_dx": 2.0, "camera_dy": 0.0, "joint_or_region": "head"},
            {"frame": 162, "dx": 2.1, "dy": 0.9, "camera_dx": 2.0, "camera_dy": 0.0, "joint_or_region": "head"},
            {"frame": 163, "dx": 3.0, "dy": 1.8, "camera_dx": 2.0, "camera_dy": 0.0, "joint_or_region": "head"},
            {"frame": 164, "dx": 2.0, "dy": 0.0, "camera_dx": 2.0, "camera_dy": 0.0, "joint_or_region": "head"},
        ]

    def test_decompose_motion_field(self):
        result = decompose_motion_field(self.shot_id, self.frame_span, self.samples)
        self.assertEqual(result["schema"], "amps.god_here.motion_field.v1")
        self.assertEqual(result["shot_id"], self.shot_id)
        self.assertEqual(len(result["camera_trajectory"]), 10)
        self.assertEqual(len(result["local_gesture_vectors"]), 10)
        self.assertGreater(result["residual_energy"], 0.0)

        # Check that camera translation was subtracted
        # Sample 0 had dx=2.0, camera_dx=2.0 -> local_dx should be 0.0
        s0 = result["local_gesture_vectors"][0]
        self.assertAlmostEqual(s0["local_dx"], 0.0)
        self.assertAlmostEqual(s0["local_dy"], 0.5)

    def test_extract_gesture_phrasing(self):
        motion_field = decompose_motion_field(self.shot_id, self.frame_span, self.samples)
        phrases = extract_gesture_phrasing(motion_field, threshold=0.6)
        self.assertGreaterEqual(len(phrases), 1)

        p0 = phrases[0]
        self.assertIn("onset_frame", p0)
        self.assertIn("peak_frame", p0)
        self.assertIn("release_frame", p0)
        self.assertLess(p0["onset_frame"], p0["release_frame"])
        self.assertGreater(p0["kinematic_impulse"], 0.0)
        self.assertGreaterEqual(p0["peak_magnitude"], 0.6)

    def test_retarget_motion_envelope(self):
        motion_field = decompose_motion_field(self.shot_id, self.frame_span, self.samples)
        phrases = extract_gesture_phrasing(motion_field, threshold=0.5)

        spec = {
            "parameter_name": "filter_cutoff_hz",
            "min_val": 200.0,
            "max_val": 4000.0,
            "curve": "exponential",
        }
        envelope = retarget_motion_envelope(phrases, spec)
        self.assertEqual(envelope["schema"], "amps.god_here.retargeted_envelope.v1")
        self.assertEqual(envelope["parameter_name"], "filter_cutoff_hz")
        for pt in envelope["envelope_points"]:
            self.assertGreaterEqual(pt["value"], 200.0)
            self.assertLessEqual(pt["value"], 4000.0)

        # Rejection of invalid bounds
        with self.assertRaises(ValueError):
            retarget_motion_envelope(phrases, {"parameter_name": "gain", "min_val": 5.0, "max_val": 1.0})

    def test_couple_gesture_to_sound_events(self):
        motion_field = decompose_motion_field(self.shot_id, self.frame_span, self.samples)
        phrases = extract_gesture_phrasing(motion_field, threshold=0.5)

        fake_palette = {
            "entries": [
                {
                    "stem_id": "STEM-IMPACT-01",
                    "category": "impact",
                    "span": {"start": 158, "end": 170},
                }
            ]
        }

        coupling = couple_gesture_to_sound_events(phrases, fake_palette, max_drift_frames=1)
        self.assertEqual(coupling["schema"], "amps.god_here.gesture_sound_coupling.v1")
        self.assertTrue(coupling["sync_verified"])
        self.assertLessEqual(coupling["max_observed_drift_frames"], 1)
        self.assertIn("performance_record", coupling)
        self.assertIn("perf-gesture-sync", coupling["performance_record"]["record_id"])


if __name__ == "__main__":
    unittest.main()
