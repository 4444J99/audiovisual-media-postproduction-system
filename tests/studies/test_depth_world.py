"""Tests for Wing 4 Depth, Geometry & World Reconstruction framework (Issues #82-85, W04)."""
import unittest

from amp.studies.depth_world import (
    estimate_metric_depth_consistency,
    project_relighting_pass,
    reconstruct_room_proxy_geometry,
    validate_parallax_camera_move,
)


class DepthWorldStudiesTests(unittest.TestCase):
    def setUp(self):
        self.shot_id = "SHOT-DEPTH-01"
        self.consistent_depth_frames = [
            {"frame": 10, "depth_scale_factor": 1.0, "boundary_sharpness": 0.88, "depth_map_min_m": 1.1, "depth_map_max_m": 5.8},
            {"frame": 11, "depth_scale_factor": 1.02, "boundary_sharpness": 0.86, "depth_map_min_m": 1.1, "depth_map_max_m": 5.85},
            {"frame": 12, "depth_scale_factor": 1.01, "boundary_sharpness": 0.87, "depth_map_min_m": 1.12, "depth_map_max_m": 5.82},
            {"frame": 13, "depth_scale_factor": 0.99, "boundary_sharpness": 0.89, "depth_map_min_m": 1.09, "depth_map_max_m": 5.81},
        ]
        self.intrinsics = {
            "fx": 1200.0,
            "fy": 1200.0,
            "width": 1920,
            "height": 1080,
        }

    def test_estimate_metric_depth_consistency_valid(self):
        result = estimate_metric_depth_consistency(self.shot_id, self.consistent_depth_frames)
        self.assertEqual(result["schema"], "amps.god_here.depth_consistency.v1")
        self.assertTrue(result["valid"])
        self.assertLessEqual(result["scale_drift_ratio"], 0.12)
        self.assertGreaterEqual(result["occlusion_boundary_sharpness"], 0.70)

    def test_estimate_metric_depth_consistency_drift_violation(self):
        drift_frames = [
            {"frame": 10, "depth_scale_factor": 1.0, "boundary_sharpness": 0.88, "depth_map_min_m": 1.0, "depth_map_max_m": 5.0},
            {"frame": 11, "depth_scale_factor": 1.30, "boundary_sharpness": 0.85, "depth_map_min_m": 1.0, "depth_map_max_m": 5.0},  # 30% jump
        ]
        result = estimate_metric_depth_consistency(self.shot_id, drift_frames)
        self.assertFalse(result["valid"])
        self.assertGreater(result["scale_drift_ratio"], 0.12)

    def test_reconstruct_room_proxy_geometry(self):
        summary = estimate_metric_depth_consistency(self.shot_id, self.consistent_depth_frames)
        proxy = reconstruct_room_proxy_geometry(summary, self.intrinsics)

        self.assertEqual(proxy["schema"], "amps.god_here.room_proxy.v1")
        self.assertIn("floor_plane", proxy)
        self.assertIn("wall_planes", proxy)
        self.assertEqual(len(proxy["depth_layers"]), 3)
        self.assertEqual(len(proxy["bounding_box_m"]), 6)

        # Rejection of invalid intrinsics
        with self.assertRaises(ValueError):
            reconstruct_room_proxy_geometry(summary, {"fx": -100.0})

    def test_project_relighting_pass(self):
        summary = estimate_metric_depth_consistency(self.shot_id, self.consistent_depth_frames)
        proxy = reconstruct_room_proxy_geometry(summary, self.intrinsics)

        light_rig = {
            "lights": [
                {"type": "key", "pos": [0.5, 1.8, 2.0], "intensity": 2.5, "color": [1.0, 0.95, 0.8]},
                {"type": "fill", "pos": [-1.0, 1.2, 1.5], "intensity": 0.8, "color": [0.8, 0.85, 1.0]},
            ]
        }

        report = project_relighting_pass(proxy, light_rig)
        self.assertEqual(report["schema"], "amps.god_here.relighting_pass.v1")
        self.assertTrue(report["subject_identity_preserved"])
        self.assertTrue(report["shadow_attenuation_verified"])
        self.assertEqual(report["light_count"], 2)
        self.assertGreater(len(report["layer_irradiances"]), 0)

    def test_validate_parallax_camera_move(self):
        summary = estimate_metric_depth_consistency(self.shot_id, self.consistent_depth_frames)
        proxy = reconstruct_room_proxy_geometry(summary, self.intrinsics)

        # Safe small move (max displacement 0.15m at 5.8m depth -> 0.025 < 0.08)
        safe_path = [
            {"frame": 10, "translation": [0.0, 0.0, 0.0]},
            {"frame": 11, "translation": [0.05, 0.01, 0.02]},
            {"frame": 12, "translation": [0.12, 0.02, 0.04]},
        ]
        res_safe = validate_parallax_camera_move(proxy, safe_path)
        self.assertTrue(res_safe["safe"])
        self.assertTrue(res_safe["disocclusion_safe_frustum"])
        self.assertEqual(res_safe["out_of_frustum_frames"], [])

        # Excessive lateral translation (1.0m at 5.8m depth -> ~0.17 > 0.08)
        unsafe_path = [
            {"frame": 10, "translation": [0.0, 0.0, 0.0]},
            {"frame": 11, "translation": [1.0, 0.0, 0.0]},
        ]
        res_unsafe = validate_parallax_camera_move(proxy, unsafe_path)
        self.assertFalse(res_unsafe["safe"])
        self.assertFalse(res_unsafe["disocclusion_safe_frustum"])
        self.assertIn(11, res_unsafe["out_of_frustum_frames"])


if __name__ == "__main__":
    unittest.main()
