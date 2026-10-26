"""Tests for Integration I01-I08 (Issues #109-116) & Master Program (Issue #63)."""
import unittest

from amp.studies.integration import (
    NINE_METHODS,
    build_edition_level_comparison,
    close_clean_environment_replay_accounting,
    compose_residue_semantic_feedback_artwork,
    connect_multiscale_recursive_composition,
    integrate_priority_proofs,
    register_nine_method_collection,
    verify_bounded_live_performance,
    verify_owner_hosted_device_behavior,
)


class IntegrationStudiesTests(unittest.TestCase):
    def setUp(self):
        self.proof_w01 = {
            "wing": "W01",
            "study_id": "study-w01-sound-separation",
            "status": "accepted",
            "snr_improvement_db": 14.2,
            "voice_intelligibility_preserved": True,
        }
        self.proof_w02 = {
            "wing": "W02",
            "study_id": "study-w02-surface-atlas",
            "status": "promoted",
            "canonical_surface_verified": True,
        }
        self.proof_w07 = {
            "wing": "W07",
            "study_id": "study-w07-residual-core",
            "status": "accepted",
            "conservation_ratio": 0.98,
            "max_residual_energy": 0.22,
        }

    def test_integrate_priority_proofs_valid(self):
        proofs = [self.proof_w01, self.proof_w02, self.proof_w07]
        integrated = integrate_priority_proofs(proofs)
        self.assertEqual(integrated["schema"], "amps.integration.priority_proofs.v1")
        self.assertEqual(integrated["priority_order"], ["W01", "W07", "W02"])
        self.assertTrue(integrated["precedence_verified"])
        self.assertTrue(integrated["overall_valid"])
        self.assertEqual(len(integrated["proof_digest"]), 64)

    def test_integrate_priority_proofs_missing_wing_raises(self):
        # Missing W07
        proofs = [self.proof_w01, self.proof_w02]
        with self.assertRaises(ValueError):
            integrate_priority_proofs(proofs)

    def test_integrate_priority_proofs_degraded_voice_snr_raises(self):
        bad_w01 = dict(self.proof_w01)
        bad_w01["snr_improvement_db"] = -3.5  # Degraded voice
        with self.assertRaises(ValueError):
            integrate_priority_proofs([bad_w01, self.proof_w02, self.proof_w07])

    def test_compose_residue_semantic_feedback_artwork(self):
        residual_env = {
            "mean_residual_energy": 0.18,
            "max_residual_energy": 0.32,
            "conservation_ratio": 0.96,
        }
        semantic_cycle = {
            "unit_id": "unit-phrase-03",
            "description": "actor reaches for coffee cup while glancing at speaker",
            "retrieval_query": "coffee cup glance",
            "retrieval_result": {"relevance_score": 0.85},
        }
        artwork = compose_residue_semantic_feedback_artwork(residual_env, semantic_cycle)
        self.assertEqual(artwork["schema"], "amps.integration.residue_semantic.v1")
        self.assertIn("sonification_params", artwork)
        self.assertIn("visualization_params", artwork)
        self.assertTrue(artwork["conservation_verified"])
        self.assertGreater(artwork["residual_coupling"]["feedback_gain"], 0.0)

    def test_register_nine_method_collection(self):
        coll = register_nine_method_collection()
        self.assertEqual(coll["schema"], "amps.integration.nine_methods.v1")
        self.assertEqual(coll["total_methods"], 9)
        self.assertTrue(coll["all_registered"])
        self.assertTrue(coll["comparison_complete"])
        for m in NINE_METHODS:
            self.assertIn(m, coll["methods"])
            self.assertGreater(len(coll["methods"][m]["comparison_criteria"]), 0)

    def test_connect_multiscale_recursive_composition_valid(self):
        prep_materials = {"materials": [{"id": "m1"}, {"id": "m2"}]}
        hierarchy = {
            "edition": {"id": "ed-master", "span": [0, 3360]},
            "scenes": [
                {"id": "sc-01", "span": [0, 1680]},
                {"id": "sc-02", "span": [1680, 3360]},
            ],
            "phrases": [
                {"id": "ph-01", "span": [0, 800]},
                {"id": "ph-02", "span": [800, 1680]},
            ],
            "shots": [
                {"id": "sh-01", "span": [0, 400]},
                {"id": "sh-02", "span": [400, 800]},
            ],
        }
        comp = connect_multiscale_recursive_composition(prep_materials, hierarchy)
        self.assertEqual(comp["schema"], "amps.integration.multiscale_composition.v1")
        self.assertEqual(comp["total_frames"], 3360)
        self.assertTrue(comp["boundary_integrity_pass"])
        self.assertEqual(len(comp["scales"]), 5)

    def test_connect_multiscale_recursive_composition_boundary_violation(self):
        hierarchy = {
            "edition": {"id": "ed-master", "span": [0, 3360]},
            "scenes": [{"id": "sc-01", "span": [0, 4000]}],  # Overflows edition
        }
        with self.assertRaises(ValueError):
            connect_multiscale_recursive_composition({}, hierarchy)

    def test_verify_bounded_live_performance_pass(self):
        telemetry = [
            {"render_time_ms": 21.5, "novelty_divergence": 0.08, "replay_divergence": 0.0, "dropped_frames_recovered": 0},
            {"render_time_ms": 24.0, "novelty_divergence": 0.12, "replay_divergence": 0.0, "dropped_frames_recovered": 1},
            {"render_time_ms": 19.8, "novelty_divergence": 0.05, "replay_divergence": 0.0, "dropped_frames_recovered": 0},
        ]
        res = verify_bounded_live_performance(telemetry)
        self.assertTrue(res["overall_pass"])
        self.assertTrue(res["latency_pass"])
        self.assertTrue(res["novelty_pass"])
        self.assertTrue(res["replay_pass"])
        self.assertTrue(res["recovery_pass"])

    def test_verify_bounded_live_performance_latency_fail(self):
        telemetry = [
            {"render_time_ms": 45.0, "novelty_divergence": 0.08, "replay_divergence": 0.0, "dropped_frames_recovered": 0},
        ]
        res = verify_bounded_live_performance(telemetry)
        self.assertFalse(res["overall_pass"])
        self.assertFalse(res["latency_pass"])

    def test_live_performance_requires_each_measurement(self):
        complete = {
            "render_time_ms": 20,
            "novelty_divergence": 0.1,
            "replay_divergence": 0,
            "dropped_frames_recovered": 0,
        }
        for field in complete:
            with self.subTest(field=field):
                sample = dict(complete)
                del sample[field]
                with self.assertRaisesRegex(ValueError, field):
                    verify_bounded_live_performance([complete, sample])

    def test_live_performance_rejects_invalid_measurements_in_every_sample(self):
        complete = {
            "render_time_ms": 20,
            "novelty_divergence": 0.1,
            "replay_divergence": 0,
            "dropped_frames_recovered": 0,
        }
        invalid = (None, True, False, "0", "NaN", float("nan"), float("inf"), -float("inf"), -1)
        for field in complete:
            for value in invalid:
                with self.subTest(field=field, value=value):
                    sample = dict(complete, **{field: value})
                    with self.assertRaisesRegex(ValueError, field):
                        verify_bounded_live_performance({"samples": [complete, sample]})

    def test_live_performance_requires_integer_recovery_count(self):
        for count in (0.5, 1.0, 3.9):
            with self.subTest(count=count):
                with self.assertRaisesRegex(ValueError, "dropped_frames_recovered"):
                    verify_bounded_live_performance({
                        "render_time_ms": 20,
                        "novelty_divergence": 0.1,
                        "replay_divergence": 0,
                        "dropped_frames_recovered": count,
                    })

    def test_live_performance_rejects_malformed_sample_collections(self):
        for samples in (None, "samples", {}, {"latency_ms": 20}, [None], [3], ["sample"]):
            with self.subTest(samples=samples):
                with self.assertRaisesRegex(ValueError, "samples|sample"):
                    verify_bounded_live_performance({"samples": samples})

    def test_live_performance_preserves_aliases_and_observed_zeroes(self):
        result = verify_bounded_live_performance({
            "latency_ms": 0,
            "novelty": 0,
            "replay_divergence": 0,
            "dropped_frames_recovered": 0,
        })
        self.assertTrue(result["overall_pass"])
        self.assertEqual(result["telemetry_summary"]["mean_latency_ms"], 0)
        self.assertEqual(result["telemetry_summary"]["max_novelty"], 0)

    def test_live_performance_finite_out_of_budget_measurements_fail(self):
        complete = {
            "render_time_ms": 20,
            "novelty_divergence": 0.1,
            "replay_divergence": 0,
            "dropped_frames_recovered": 0,
        }
        for field, value in (("render_time_ms", 40), ("novelty_divergence", 0.36),
                             ("replay_divergence", 0.001), ("dropped_frames_recovered", 4)):
            with self.subTest(field=field):
                result = verify_bounded_live_performance(dict(complete, **{field: value}))
                self.assertFalse(result["overall_pass"])
                self.assertEqual(result["status"], "failed")

    def test_live_performance_large_finite_measurements_have_finite_summary(self):
        import json
        import sys

        sample = {
            "render_time_ms": 1e308,
            "novelty_divergence": 0,
            "replay_divergence": 0,
            "dropped_frames_recovered": 0,
        }
        result = verify_bounded_live_performance([sample, sample])
        self.assertFalse(result["overall_pass"])
        json.dumps(result, allow_nan=False)

        sample["render_time_ms"] = sys.float_info.max
        result = verify_bounded_live_performance([sample, sample, sample])
        self.assertFalse(result["overall_pass"])
        self.assertEqual(result["telemetry_summary"]["mean_latency_ms"], sys.float_info.max)
        json.dumps(result, allow_nan=False)

    def test_build_edition_level_comparison(self):
        baseline = {
            "edition_id": "ed-source-112",
            "duration_seconds": 112.0,
            "total_frames": 3360,
            "integrated_lufs": -20.0,
            "resolution": [1920, 1080],
        }
        study = {
            "edition_id": "ed-retimed-closing",
            "duration_seconds": 114.8,
            "total_frames": 3444,
            "integrated_lufs": -20.0,
            "resolution": [1920, 1080],
            "framing_scale": 1.25,
            "retiming_map": [[2554, 2554], [2880, 2880], [3000, 3084], [3215, 3299]],
        }
        comp = build_edition_level_comparison(baseline, study)
        self.assertEqual(comp["schema"], "amps.integration.edition_comparison.v1")
        self.assertEqual(comp["frame_delta"], 84)
        self.assertAlmostEqual(comp["duration_delta_seconds"], 2.8)
        self.assertTrue(comp["loudness_matched"])
        self.assertTrue(comp["retiming_verified"])

    def test_verify_owner_hosted_device_behavior_compliant(self):
        profiles = [
            {"device_type": "desktop", "viewport_width": 1920, "viewport_height": 1080, "fps": 30, "audio_channels": 2},
            {"device_type": "projection", "viewport_width": 3840, "viewport_height": 2160, "fps": 60, "audio_channels": 8},
            {"device_type": "tablet", "viewport_width": 820, "viewport_height": 1180, "fps": 30, "touch_enabled": True, "mobile_memory_bounded": True},
        ]
        res = verify_owner_hosted_device_behavior(profiles)
        self.assertEqual(res["schema"], "amps.integration.device_behavior.v1")
        self.assertTrue(res["required_devices_present"])
        self.assertTrue(res["all_profiles_compliant"])

    def test_verify_owner_hosted_device_behavior_missing_profile(self):
        # Missing tablet profile
        profiles = [
            {"device_type": "desktop", "viewport_width": 1920, "viewport_height": 1080, "fps": 30, "audio_channels": 2},
            {"device_type": "projection", "viewport_width": 1920, "viewport_height": 1080, "fps": 30, "audio_channels": 4},
        ]
        res = verify_owner_hosted_device_behavior(profiles)
        self.assertFalse(res["required_devices_present"])
        self.assertFalse(res["all_profiles_compliant"])
        self.assertIn("tablet", res["missing_device_types"])

    def test_close_clean_environment_replay_accounting_valid(self):
        manifest = {
            "network_calls_count": 0,
            "zero_network_verified": True,
            "deterministic_match": True,
            "replay_hashes": {f"file_{i}": f"hash_{i}" for i in range(10)},
        }
        ledger = {
            "tasks": [f"task-{i:02d}" for i in range(53)],
            "deliverables": [f"deliv-{i:02d}" for i in range(38)],
        }
        acc = close_clean_environment_replay_accounting(manifest, ledger)
        self.assertEqual(acc["schema"], "amps.integration.replay_accounting.v1")
        self.assertTrue(acc["complete"])
        self.assertTrue(acc["clean_zero_network"])
        self.assertTrue(acc["replay_deterministic"])
        self.assertEqual(acc["total_tasks_accounted"], 53)
        self.assertEqual(acc["total_deliverables_accounted"], 38)

    def test_close_clean_environment_replay_accounting_network_leak_rejected(self):
        manifest = {
            "network_calls_count": 1,  # Network leak
            "zero_network_verified": False,
        }
        ledger = {
            "total_tasks": 53,
            "total_deliverables": 38,
        }
        with self.assertRaises(ValueError):
            close_clean_environment_replay_accounting(manifest, ledger)


if __name__ == "__main__":
    unittest.main()
