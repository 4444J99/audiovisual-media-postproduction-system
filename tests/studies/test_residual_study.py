"""Tests for Wing 7 Residual Core Study Integration framework (Issues #94-97, W07)."""
import unittest
import numpy as np

from amp.studies.residual_study import (
    classify_residual_regime,
    compute_study_residual_envelope,
    sonify_or_visualize_residual_layer,
    verify_residual_conservation,
)


class ResidualStudyTests(unittest.TestCase):
    def setUp(self):
        self.unit_id = "BM-01"
        np.random.seed(42)
        # Synthetic clean sine + noise as original
        t = np.linspace(0, 1.0, 4800, endpoint=False)
        self.orig = np.sin(2 * np.pi * 220.0 * t) + 0.1 * np.random.randn(4800)
        # Reconstruction captures the sine wave
        self.recon = np.sin(2 * np.pi * 220.0 * t)

    def test_compute_study_residual_envelope(self):
        env = compute_study_residual_envelope(self.unit_id, self.orig, self.recon, frame_size=1600)
        self.assertEqual(env["schema"], "amps.god_here.study_residual_envelope.v1")
        self.assertEqual(env["unit_id"], self.unit_id)
        self.assertEqual(env["sample_count"], 4800)
        self.assertEqual(env["frame_count"], 3)
        self.assertGreater(env["l2_residual_norm"], 0.0)
        self.assertGreater(env["spectral_flatness"], 0.0)

        # Mismatch rejection
        with self.assertRaises(ValueError):
            compute_study_residual_envelope(self.unit_id, self.orig[:100], self.recon[:200])

    def test_classify_residual_regime(self):
        env = compute_study_residual_envelope(self.unit_id, self.orig, self.recon, frame_size=1600)
        regime = classify_residual_regime(env)
        self.assertEqual(regime["schema"], "amps.god_here.residual_regime.v1")
        self.assertIn("primary_regime", regime)
        self.assertIn(regime["primary_regime"], [
            "structured_performance_trace",
            "room_grain_noise",
            "model_failure_artifact",
        ])
        dist = regime["regime_distribution"]
        self.assertAlmostEqual(sum(dist.values()), 1.0, places=2)

    def test_sonify_or_visualize_residual_layer(self):
        env = compute_study_residual_envelope(self.unit_id, self.orig, self.recon, frame_size=1600)

        # Mode both
        res_both = sonify_or_visualize_residual_layer(env, mode="both")
        self.assertEqual(res_both["schema"], "amps.god_here.residual_layer.v1")
        self.assertEqual(res_both["product_count"], 2)
        kinds = [p["kind"] for p in res_both["products"]]
        self.assertIn("audio", kinds)
        self.assertIn("material", kinds)

        # Mode audio only
        res_audio = sonify_or_visualize_residual_layer(env, mode="audio")
        self.assertEqual(res_audio["product_count"], 1)
        self.assertEqual(res_audio["products"][0]["kind"], "audio")

        # Invalid mode
        with self.assertRaises(ValueError):
            sonify_or_visualize_residual_layer(env, mode="unsupported_mode")

    def test_verify_residual_conservation(self):
        orig_e = 100.0
        recon_e = 80.0
        res_e = 20.0
        report_conserved = verify_residual_conservation(orig_e, recon_e, res_e, tol=1e-4)
        self.assertEqual(report_conserved["schema"], "amps.god_here.residual_conservation.v1")
        self.assertTrue(report_conserved["conserved"])
        self.assertAlmostEqual(report_conserved["energy_difference"], 0.0)

        # Energy leak / conservation violation
        res_e_leak = 15.0  # 80 + 15 = 95 != 100
        report_leaked = verify_residual_conservation(orig_e, recon_e, res_e_leak, tol=1e-4)
        self.assertFalse(report_leaked["conserved"])
        self.assertGreater(report_leaked["energy_difference"], 1e-4)


if __name__ == "__main__":
    unittest.main()
