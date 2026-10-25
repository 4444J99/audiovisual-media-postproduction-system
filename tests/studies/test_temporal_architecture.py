"""Tests for Wing 10 Long-Take Temporal Architecture & Retiming framework (Issues #106-109, W10)."""
import unittest

from amp.studies.temporal_architecture import (
    build_piecewise_retime_curve,
    compile_macro_section_arc,
    detect_phase_lock_conjunctions,
    enforce_long_take_continuity_budget,
)


class TemporalArchitectureStudiesTests(unittest.TestCase):
    def setUp(self):
        self.frame_span = (0, 100)
        self.control_points = [
            {"comp_frame": 0, "source_frame": 0.0},
            {"comp_frame": 50, "source_frame": 50.0},
            {"comp_frame": 100, "source_frame": 105.0},
        ]

    def test_build_piecewise_retime_curve(self):
        curve = build_piecewise_retime_curve(self.frame_span, self.control_points)
        self.assertEqual(curve["schema"], "amps.god_here.retime_curve.v1")
        self.assertTrue(curve["monotonic"])
        self.assertEqual(len(curve["sample_points"]), 100)

        # Non-monotonic control point rejection
        bad_points = [
            {"comp_frame": 0, "source_frame": 0.0},
            {"comp_frame": 50, "source_frame": 40.0},
            {"comp_frame": 100, "source_frame": 30.0},  # Backwards in source time
        ]
        with self.assertRaises(ValueError) as cm:
            build_piecewise_retime_curve(self.frame_span, bad_points)
        self.assertIn("non-monotonic source_frame", str(cm.exception))

    def test_detect_phase_lock_conjunctions(self):
        streams = [
            {"stream_id": "performer_footsteps", "event_frames": [15, 45, 75]},
            {"stream_id": "percussion_accent", "event_frames": [16, 45, 90]},
        ]
        conj = detect_phase_lock_conjunctions(streams, tolerance_frames=1)
        self.assertEqual(conj["schema"], "amps.god_here.phase_lock_conjunctions.v1")
        # Frame 15 & 16 match (diff 1), Frame 45 & 45 match (diff 0), Frame 75 & 90 don't match
        self.assertEqual(conj["conjunction_count"], 2)
        frames = [c["conjunction_frame"] for c in conj["conjunctions"]]
        self.assertIn(15, frames)
        self.assertIn(45, frames)

    def test_enforce_long_take_continuity_budget(self):
        curve = build_piecewise_retime_curve(self.frame_span, self.control_points)
        budget = enforce_long_take_continuity_budget(curve, max_acceleration=0.15)
        self.assertEqual(budget["schema"], "amps.god_here.long_take_continuity_budget.v1")
        self.assertTrue(budget["passed"])
        self.assertEqual(budget["violation_frames"], [])

        # Sharp discontinuous curve with spike acceleration
        spike_points = [
            {"comp_frame": 0, "source_frame": 0.0},
            {"comp_frame": 49, "source_frame": 49.0},
            {"comp_frame": 50, "source_frame": 90.0},  # Sudden 41-frame leap
            {"comp_frame": 100, "source_frame": 100.0},
        ]
        spike_curve = build_piecewise_retime_curve(self.frame_span, spike_points)
        spike_budget = enforce_long_take_continuity_budget(spike_curve, max_acceleration=0.15)
        self.assertFalse(spike_budget["passed"])
        self.assertGreater(len(spike_budget["violation_frames"]), 0)

    def test_compile_macro_section_arc(self):
        sections = [
            {"section_id": "SEC-01", "start": 0, "end": 900, "tension": 0.3},
            {"section_id": "SEC-02", "start": 900, "end": 1800, "tension": 0.7},
            {"section_id": "SEC-03", "start": 1800, "end": 2700, "tension": 0.9},
        ]
        arc = compile_macro_section_arc(sections)
        self.assertEqual(arc["schema"], "amps.god_here.macro_section_arc.v1")
        self.assertTrue(arc["contiguous"])
        self.assertEqual(arc["total_frames"], 2700)
        self.assertEqual(arc["section_count"], 3)

        # Gap / overlap rejection
        broken_sections = [
            {"section_id": "SEC-01", "start": 0, "end": 900},
            {"section_id": "SEC-02", "start": 950, "end": 1800},  # 50 frame gap
        ]
        with self.assertRaises(ValueError) as cm:
            compile_macro_section_arc(broken_sections)
        self.assertIn("Section gap/overlap", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
