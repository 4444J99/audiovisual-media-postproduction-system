"""Tests for Wing 8 Voice, Breath, Room Acoustics & Score framework (Issues #98-101, W08)."""
import unittest

from amp.studies.voice_acoustics import (
    align_score_cues_to_breath_cadence,
    convolve_acoustic_space_match,
    estimate_room_impulse_profile,
    extract_vocal_prosody_and_breath,
)


class VoiceAcousticsStudiesTests(unittest.TestCase):
    def setUp(self):
        self.unit_id = "BM-01"
        self.audio_stem = {
            "stem_id": "STEM-VOICE-01",
            "sample_rate_hz": 48000,
            "f0_hz_contour": [130.0, 138.5, 142.0, 140.0, 135.0],
            "breath_intervals": [
                {"type": "intake", "start_frame": 210, "end_frame": 230, "intensity": 0.5},
                {"type": "exhale", "start_frame": 285, "end_frame": 295, "intensity": 0.3},
            ],
            "rms_envelope_db": [-22.0, -18.0, -14.0, -16.0, -20.0],
        }
        self.residue_stem = {
            "rt60_sec": 0.68,
            "early_decay_time_sec": 0.44,
            "direct_to_reverberant_db": -5.2,
            "spectral_coloration": {"bass_ratio": 1.12, "treble_ratio": 0.88},
        }

    def test_extract_vocal_prosody_and_breath(self):
        res = extract_vocal_prosody_and_breath(self.unit_id, self.audio_stem)
        self.assertEqual(res["schema"], "amps.god_here.vocal_prosody.v1")
        self.assertEqual(res["unit_id"], self.unit_id)
        self.assertEqual(len(res["breath_intervals"]), 2)
        self.assertAlmostEqual(res["f0_hz_stats"]["mean_f0_hz"], 137.1, places=1)
        self.assertEqual(res["f0_hz_stats"]["min_f0_hz"], 130.0)
        self.assertEqual(res["f0_hz_stats"]["max_f0_hz"], 142.0)

    def test_estimate_room_impulse_profile(self):
        profile = estimate_room_impulse_profile(self.unit_id, self.residue_stem)
        self.assertEqual(profile["schema"], "amps.god_here.room_impulse_profile.v1")
        self.assertEqual(profile["unit_id"], self.unit_id)
        self.assertEqual(profile["rt60_sec"], 0.68)
        self.assertEqual(profile["early_decay_time_sec"], 0.44)
        self.assertIn("bass_ratio", profile["spectral_coloration"])

        # Rejection of invalid rt60
        bad_residue = {"rt60_sec": -0.5, "early_decay_time_sec": 0.4}
        with self.assertRaises(ValueError):
            estimate_room_impulse_profile(self.unit_id, bad_residue)

    def test_convolve_acoustic_space_match_peak_safety(self):
        profile = estimate_room_impulse_profile(self.unit_id, self.residue_stem)

        # Hot dry stem (-0.2 dBFS) that would clip without safety limiter
        hot_stem = {"stem_id": "STEM-HOT", "peak_dbfs": -0.2}
        match_hot = convolve_acoustic_space_match(hot_stem, profile)
        self.assertEqual(match_hot["schema"], "amps.god_here.acoustic_space_match.v1")
        self.assertTrue(match_hot["peak_safe"])
        self.assertLessEqual(match_hot["peak_dbfs"], -1.0)
        self.assertGreater(match_hot["attenuation_applied_db"], 0.0)

        # Quiet dry stem (-12 dBFS)
        quiet_stem = {"stem_id": "STEM-QUIET", "peak_dbfs": -12.0}
        match_quiet = convolve_acoustic_space_match(quiet_stem, profile)
        self.assertTrue(match_quiet["peak_safe"])
        self.assertLessEqual(match_quiet["peak_dbfs"], -1.0)
        self.assertEqual(match_quiet["attenuation_applied_db"], 0.0)

    def test_align_score_cues_to_breath_cadence(self):
        breath_intervals = [
            {"type": "intake", "start_frame": 210, "end_frame": 230},
            {"type": "exhale", "start_frame": 500, "end_frame": 520},
        ]
        # Cue 1 starts at frame 215 (within 15 frames of breath at 210 -> snaps to 210)
        # Cue 2 starts at frame 400 (far from any breath -> does not snap)
        cues = [
            {"cue_id": "CUE-01", "start_frame": 215, "duration_frames": 90},
            {"cue_id": "CUE-02", "start_frame": 400, "duration_frames": 60},
        ]

        alignment = align_score_cues_to_breath_cadence(breath_intervals, cues)
        self.assertEqual(alignment["schema"], "amps.god_here.score_breath_alignment.v1")
        self.assertEqual(alignment["cue_count"], 2)

        c1 = alignment["aligned_cues"][0]
        self.assertTrue(c1["aligned_to_breath"])
        self.assertEqual(c1["aligned_start_frame"], 210)
        self.assertEqual(c1["adjustment_frames"], -5)

        c2 = alignment["aligned_cues"][1]
        self.assertFalse(c2["aligned_to_breath"])
        self.assertEqual(c2["aligned_start_frame"], 400)
        self.assertEqual(c2["adjustment_frames"], 0)


if __name__ == "__main__":
    unittest.main()
