"""Tests for God's Ears Core Editions E0-E6 (Issues #2-8, #11-48)."""
import unittest

from amp.studies.editions_e0_e6 import (
    calibrate_e0_pilot_and_anchors,
    calibrate_e6_interactive_installation,
    compose_e2_five_character_fields,
    generate_e5_reproducible_cue_graphs,
    render_e3_combined_proof_and_linear_edition,
    restore_e1_dialogue_and_ambience,
    build_e4_responsive_bodies_and_room,
)


class EditionsE0E6Tests(unittest.TestCase):
    def test_calibrate_e0_pilot_and_anchors_valid(self):
        dialogue_anchors = [
            {"id": "anc-01", "frame": 2600, "label": "closing question"},
            {"id": "anc-02", "frame": 2880, "label": "pause start"},
            {"id": "anc-03", "frame": 3000, "label": "final reply"},
        ]
        shot_layouts = [
            {"view_id": "angle-A", "crop": [0, 0, 1920, 1080]},
            {"view_id": "angle-B", "crop": [100, 50, 1820, 1030]},
        ]
        benchmark_excerpts = [
            {"id": "closing-excerpt", "frames": [2554, 3215]},
        ]
        cal = calibrate_e0_pilot_and_anchors(dialogue_anchors, shot_layouts, benchmark_excerpts)
        self.assertEqual(cal["schema"], "amps.editions.e0_pilot.v1")
        self.assertEqual(cal["edition"], "E0")
        self.assertEqual(cal["dialogue_anchors_count"], 3)
        self.assertTrue(cal["two_view_geometry_calibrated"])
        self.assertEqual(cal["benchmark_excerpt"]["frame_count"], 661)
        self.assertAlmostEqual(cal["benchmark_excerpt"]["duration_seconds"], 22.033)
        self.assertEqual(cal["timebase"]["samples_per_frame"], 1600)

    def test_calibrate_e0_pilot_and_anchors_empty_rejects(self):
        with self.assertRaises(ValueError):
            calibrate_e0_pilot_and_anchors([], [{"view_id": "A"}], [{"frames": [0, 100]}])

    def test_restore_e1_dialogue_and_ambience_valid(self):
        defect_map = {"hiss": "continuous", "mic_rumble": "low_frequency"}
        candidates = [
            {"filter_id": "fft-denoise-01", "params": "highpass=f=65,afftdn=nr=14:nf=-32:tn=1"},
            {"filter_id": "spectral-gate-02", "params": "spectral_subtraction_moderate"},
        ]
        speaker_layers = [
            {"speaker_id": "spk-1", "bus": "dialogue_A"},
            {"speaker_id": "spk-2", "bus": "dialogue_B"},
        ]
        irreparable_lines = [
            {"line_id": "line-inaudible-murmur", "frame_span": [3110, 3140], "disclosed_reason": "ambient table bump obscures consonants; left un-synthesized per documentary ethics"},
        ]
        rest = restore_e1_dialogue_and_ambience(defect_map, candidates, speaker_layers, irreparable_lines)
        self.assertEqual(rest["schema"], "amps.editions.e1_restoration.v1")
        self.assertEqual(rest["edition"], "E1")
        self.assertEqual(rest["integrated_lufs"], -20.0)
        self.assertEqual(rest["delay_compensation_samples"], 1199)
        self.assertTrue(rest["honesty_gate_passed"])
        self.assertEqual(len(rest["irreparable_lines_disclosed"]), 1)

    def test_restore_e1_rejects_generative_speech_fabrication(self):
        candidates = [
            {"filter_id": "hallucination-engine", "generative_speech_synthesis": True},
        ]
        with self.assertRaises(ValueError):
            restore_e1_dialogue_and_ambience({}, candidates, [{"speaker_id": "s1"}], [])

    def test_compose_e2_five_character_fields_valid(self):
        chars = [
            {"character_id": f"char-{i+1:02d}", "role": f"performer-{i+1}"}
            for i in range(5)
        ]
        expr_score = {"events": [{"char": "char-01", "state": "silent_listening"}]}
        temporal_buffers = {"pre_roll_frames": 10, "post_roll_frames": 10}
        soft_transitions = {"feather_radius_px": 16.0}

        e2 = compose_e2_five_character_fields(chars, expr_score, temporal_buffers, soft_transitions)
        self.assertEqual(e2["schema"], "amps.editions.e2_character_fields.v1")
        self.assertEqual(e2["edition"], "E2")
        self.assertEqual(e2["character_count"], 5)
        self.assertTrue(e2["silent_listening_verified"])
        self.assertTrue(e2["soft_transition_spill_contained"])

    def test_compose_e2_requires_exactly_five_characters(self):
        four_chars = [{"character_id": f"char-{i:02d}"} for i in range(4)]
        with self.assertRaises(ValueError):
            compose_e2_five_character_fields(four_chars, {}, {}, {})

    def test_render_e3_combined_proof_and_linear_edition_valid(self):
        abcd = {"variants": ["A", "B", "C", "D", "E", "F"]}
        score = {"duration_seconds": 114.8}
        buses = {"dialogue": {}, "room_bed": {}, "foley": {}, "score": {}}
        apertures = [{"word": "OUT"}, {"word": "HOW"}, {"word": "WHAT"}]
        delivery_qc = {
            "resolution": [1920, 1080],
            "peak_dbfs": -1.5,
            "sync_drift_frames": 0.25,
        }
        e3 = render_e3_combined_proof_and_linear_edition(abcd, score, buses, apertures, delivery_qc)
        self.assertEqual(e3["schema"], "amps.editions.e3_linear_edition.v1")
        self.assertEqual(e3["edition"], "E3")
        self.assertEqual(len(e3["variants_rendered"]), 6)
        self.assertTrue(e3["qc_passed"])
        self.assertEqual(e3["word_apertures_count"], 3)

    def test_render_e3_fails_qc_on_clipping_peak(self):
        bad_qc = {
            "resolution": [1920, 1080],
            "peak_dbfs": +0.5,  # Exceeds -1.0 dBFS ceiling
            "sync_drift_frames": 0.0,
        }
        with self.assertRaises(ValueError):
            render_e3_combined_proof_and_linear_edition({}, {"duration_seconds": 112.0}, {"b1": {}}, [], bad_qc)

    def test_build_e4_responsive_bodies_and_room_valid(self):
        seg = {"masks": [{"id": "m1"}, {"id": "m2"}]}
        surfaces = [{"id": "table"}, {"id": "back_wall"}]
        gestures = [{"gesture": "cup_reach", "frame": 2880}]
        room_trans = {"enabled": True, "lighting": "soft_falloff"}
        fallbacks = {"low_confidence_tracking": "clean_plate_bypass"}

        e4 = build_e4_responsive_bodies_and_room(seg, surfaces, gestures, room_trans, fallbacks)
        self.assertEqual(e4["schema"], "amps.editions.e4_responsive_room.v1")
        self.assertEqual(e4["edition"], "E4")
        self.assertEqual(e4["surface_count"], 2)
        self.assertTrue(e4["room_transformation_enabled"])
        self.assertTrue(e4["fallback_chain_verified"])

    def test_generate_e5_reproducible_cue_graphs_valid(self):
        source = {"units": 174}
        rules = {"base_seed": 100}
        versions = ["gen-v1-contemplative", "gen-v2-agitated", "gen-v3-dispersed"]
        outcome = {
            "selected_version": "gen-v1-contemplative",
            "selection_rationale": "Slower cadence aligns with meditative room tone while preserving phrase integrity",
            "rejected_versions": {
                "gen-v2-agitated": "Excessive phrase clipping disjoints character gaze",
                "gen-v3-dispersed": "Over-fragmented audio stems reduce voice intelligibility",
            },
        }
        e5 = generate_e5_reproducible_cue_graphs(source, rules, versions, outcome)
        self.assertEqual(e5["schema"], "amps.editions.e5_cue_graphs.v1")
        self.assertEqual(e5["edition"], "E5")
        self.assertEqual(e5["version_count"], 3)
        self.assertEqual(e5["selected_version"], "gen-v1-contemplative")
        self.assertEqual(len(e5["rejected_versions"]), 2)
        self.assertEqual(len(e5["reproducible_digest"]), 64)

    def test_generate_e5_rejects_non_three_versions(self):
        with self.assertRaises(ValueError):
            generate_e5_reproducible_cue_graphs({}, {}, ["v1", "v2"], {"selected_version": "v1"})

    def test_calibrate_e6_interactive_installation_valid(self):
        interaction = {"proximity_sensor": "enabled"}
        transport = {"enabled": True, "clock_hz": 60}
        mobile = {"recovery_supported": True, "linear_fallback_ready": True}
        presets = [{"id": "ambient"}, {"id": "performance"}]
        spatial = {"speaker_channels": 8}
        room_foley = {"bed_channels": 2}

        e6 = calibrate_e6_interactive_installation(interaction, transport, mobile, presets, spatial, room_foley)
        self.assertEqual(e6["schema"], "amps.editions.e6_interactive_installation.v1")
        self.assertEqual(e6["edition"], "E6")
        self.assertTrue(e6["common_transport_calibrated"])
        self.assertEqual(e6["spatial_speaker_channels"], 8)
        self.assertTrue(e6["mobile_recovery_verified"])
        self.assertTrue(e6["linear_fallback_ready"])

    def test_calibrate_e6_rejects_insufficient_speakers(self):
        spatial = {"speaker_channels": 2}  # Less than 4 channels
        with self.assertRaises(ValueError):
            calibrate_e6_interactive_installation({}, {}, {}, [{"id": "p1"}], spatial, {})


if __name__ == "__main__":
    unittest.main()
