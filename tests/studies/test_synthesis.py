"""Tests for Cross-Wing Composition Synthesis & Master Assembly framework (Issues #114-116, Synthesis)."""
import unittest

from amp.studies.synthesis import (
    ALL_WINGS,
    assemble_comp001_master_synthesis,
    collect_accepted_wing_materials,
    resolve_cross_wing_conflicts,
)


class SynthesisStudiesTests(unittest.TestCase):
    def setUp(self):
        self.comp_id = "comp-001"
        self.dummy_results = [
            {
                "study_id": "study-w01",
                "metadata": {"status": "executed", "wing": "W01"},
                "products": [{"id": "mat-voice-01", "kind": "audio", "metadata": {"category": "voice_speech"}}],
            },
            {
                "study_id": "study-w07",
                "metadata": {"status": "promoted", "wing": "W07"},
                "products": [{"id": "mat-residual-01", "kind": "audio", "metadata": {"category": "residual_trace"}}],
            },
            {
                "study_id": "study-w02",
                "metadata": {"status": "accepted", "wing": "W02"},
                "products": [{"id": "mat-surface-01", "kind": "material", "metadata": {"category": "surface_atlas"}}],
            },
            {
                "study_id": "study-w06",
                "metadata": {"status": "promoted", "wing": "W06"},
                "products": [{"id": "mat-texture-01", "kind": "material", "metadata": {"category": "generative_texture"}}],
            },
            # Rejected study that must be filtered out
            {
                "study_id": "study-rejected",
                "metadata": {"status": "rejected", "wing": "W05"},
                "products": [{"id": "mat-bad-01", "kind": "material"}],
            },
        ]
        self.sealed_ledger = {
            "sealed": True,
            "ledger_sha256": "e" * 64,
        }

    def test_collect_accepted_wing_materials(self):
        collected = collect_accepted_wing_materials(self.dummy_results)
        self.assertEqual(collected["schema"], "amps.god_here.collected_materials.v1")
        # 4 accepted products collected, rejected one filtered out
        self.assertEqual(collected["total_materials"], 4)
        mat_ids = [m["id"] for m in collected["materials"]]
        self.assertIn("mat-voice-01", mat_ids)
        self.assertIn("mat-residual-01", mat_ids)
        self.assertNotIn("mat-bad-01", mat_ids)

    def test_resolve_cross_wing_conflicts_priority(self):
        collected = collect_accepted_wing_materials(self.dummy_results)
        resolved = resolve_cross_wing_conflicts(collected)
        self.assertEqual(resolved["schema"], "amps.god_here.resolved_materials.v1")
        self.assertEqual(resolved["resolved_layer_count"], 4)

        layers = resolved["layers"]
        # Highest priority first: voice > residual > surface > texture
        self.assertEqual(layers[0]["material_id"], "mat-voice-01")
        self.assertEqual(layers[1]["material_id"], "mat-residual-01")
        self.assertEqual(layers[2]["material_id"], "mat-surface-01")
        self.assertEqual(layers[3]["material_id"], "mat-texture-01")

        self.assertEqual(layers[0]["ducking_attenuation_db"], 0.0)  # Voice untouched
        self.assertLess(layers[3]["ducking_attenuation_db"], 0.0)  # Texture ducked

    def test_assemble_comp001_master_synthesis(self):
        collected = collect_accepted_wing_materials(self.dummy_results)
        resolved = resolve_cross_wing_conflicts(collected)
        synthesis = assemble_comp001_master_synthesis(self.comp_id, resolved, self.sealed_ledger)

        self.assertEqual(synthesis["schema"], "amps.comp001.synthesis.v1")
        self.assertEqual(synthesis["composition_id"], "comp-001")
        self.assertTrue(synthesis["ready_for_render"])
        self.assertEqual(len(synthesis["synthesis_digest"]), 64)
        self.assertEqual(synthesis["wings_covered"], list(ALL_WINGS))
        self.assertEqual(len(synthesis["wings_covered"]), 11)


if __name__ == "__main__":
    unittest.main()
