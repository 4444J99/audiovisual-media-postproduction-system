"""Tests for Wing 6 Generative Texture & Controlled Hallucination framework (Issues #90-93, W06)."""
import unittest

from amp.studies.generative_texture import (
    blend_temporal_texture_cadence,
    enforce_identity_preservation_gate,
    package_generative_material_layer,
    synthesize_bounded_texture_pass,
)


class GenerativeTextureStudiesTests(unittest.TestCase):
    def setUp(self):
        self.unit_id = "BM-01"
        self.seed = 42
        self.mask_region = {
            "bounds": [0.3, 0.2, 0.7, 0.6],
            "frame_span": [155, 210],
        }
        self.style = {
            "prompt": "parchment craquelure texture overlay",
            "weight": 0.65,
        }

    def test_synthesize_bounded_texture_pass(self):
        res = synthesize_bounded_texture_pass(self.unit_id, self.seed, self.mask_region, self.style)
        self.assertEqual(res["schema"], "amps.god_here.bounded_texture_synthesis.v1")
        self.assertEqual(res["unit_id"], self.unit_id)
        self.assertEqual(res["seed"], self.seed)
        self.assertEqual(res["bleed_outside_mask"], 0.0)
        self.assertTrue(res["zero_bleed_enforced"])

    def test_enforce_identity_preservation_gate(self):
        # 4 identical/near-identical 8-D normalized embeddings -> similarity ~0.99 > 0.88
        ref_embeds = [
            [0.35, 0.35, 0.35, 0.35, 0.35, 0.35, 0.35, 0.35],
            [0.5, 0.5, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0],
        ]
        close_gen_embeds = [
            [0.36, 0.34, 0.35, 0.35, 0.35, 0.35, 0.35, 0.35],
            [0.49, 0.51, 0.5, 0.5, 0.0, 0.0, 0.0, 0.0],
        ]
        gate_pass = enforce_identity_preservation_gate(ref_embeds, close_gen_embeds, min_cosine_sim=0.88)
        self.assertTrue(gate_pass["passed"])
        self.assertFalse(gate_pass["identity_drift_detected"])
        self.assertGreaterEqual(gate_pass["mean_cosine_similarity"], 0.88)

        # Distant embeddings -> similarity low (< 0.88)
        distant_gen_embeds = [
            [0.0, 0.0, 0.0, 0.0, 0.5, 0.5, 0.5, 0.5],
            [0.0, 0.0, 0.0, 0.0, 0.5, 0.5, 0.5, 0.5],
        ]
        gate_fail = enforce_identity_preservation_gate(ref_embeds, distant_gen_embeds, min_cosine_sim=0.88)
        self.assertFalse(gate_fail["passed"])
        self.assertTrue(gate_fail["identity_drift_detected"])

    def test_blend_temporal_texture_cadence(self):
        stable_frames = [{"frame": i, "flicker": 0.02} for i in range(10)]
        keyframes = [0, 5, 10]
        cadence_pass = blend_temporal_texture_cadence(stable_frames, keyframes, max_flicker=0.06)
        self.assertTrue(cadence_pass["stable"])
        self.assertLessEqual(cadence_pass["mean_flicker"], 0.06)

        unstable_frames = [{"frame": i, "flicker": 0.12} for i in range(10)]
        cadence_fail = blend_temporal_texture_cadence(unstable_frames, keyframes, max_flicker=0.06)
        self.assertFalse(cadence_fail["stable"])

    def test_package_generative_material_layer(self):
        synth = synthesize_bounded_texture_pass(self.unit_id, self.seed, self.mask_region, self.style)
        id_pass = {"passed": True, "mean_cosine_similarity": 0.94}
        cad_pass = {"stable": True, "mean_flicker": 0.025}

        package_res = package_generative_material_layer(synth, id_pass, cad_pass)
        self.assertEqual(package_res["schema"], "amps.god_here.generative_material_layer.v1")
        self.assertEqual(package_res["material"]["kind"], "material")
        self.assertIn("mat-gen-texture-", package_res["material"]["id"])
        self.assertTrue(package_res["packaging_receipt"]["zero_bleed_verified"])

        # Fails closed when identity gate fails
        id_fail = {"passed": False, "mean_cosine_similarity": 0.65}
        with self.assertRaises(ValueError):
            package_generative_material_layer(synth, id_fail, cad_pass)

        # Fails closed when cadence gate fails
        cad_fail = {"stable": False, "mean_flicker": 0.09}
        with self.assertRaises(ValueError):
            package_generative_material_layer(synth, id_pass, cad_fail)


if __name__ == "__main__":
    unittest.main()
