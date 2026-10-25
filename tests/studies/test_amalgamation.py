"""Tests for Wing 9 Multi-Frame Amalgamation & Spatial Tiling framework (Issues #102-105, W09)."""
import unittest

from amp.studies.amalgamation import (
    balance_cross_cell_luminance_and_gaze,
    compose_diptych_triptych_grid,
    export_amalgamated_study_timeline,
    route_polyphonic_cell_audio,
)


class AmalgamationStudiesTests(unittest.TestCase):
    def setUp(self):
        self.unit_ids_diptych = ["BM-01", "BM-02"]
        self.unit_ids_triptych = ["BM-01", "BM-02", "BM-03"]
        self.frame_span = (155, 210)

    def test_compose_diptych_grid(self):
        grid = compose_diptych_triptych_grid(self.unit_ids_diptych, "diptych_horizontal", self.frame_span)
        self.assertEqual(grid["schema"], "amps.god_here.amalgamation_grid.v1")
        self.assertEqual(grid["cell_count"], 2)
        c0, c1 = grid["cells"][0], grid["cells"][1]
        self.assertEqual(c0["viewport"], [0.0, 0.0, 0.5, 1.0])
        self.assertEqual(c1["viewport"], [0.5, 0.0, 0.5, 1.0])

    def test_compose_grid_unit_count_mismatch_rejection(self):
        with self.assertRaises(ValueError) as cm:
            compose_diptych_triptych_grid(["BM-01"], "diptych_horizontal", self.frame_span)
        self.assertIn("requires exactly 2 units", str(cm.exception))

    def test_balance_cross_cell_luminance_and_gaze(self):
        grid = compose_diptych_triptych_grid(self.unit_ids_diptych, "diptych_horizontal", self.frame_span)
        balance = balance_cross_cell_luminance_and_gaze(grid["cells"])
        self.assertEqual(balance["schema"], "amps.god_here.cross_cell_balance.v1")
        self.assertTrue(balance["balanced"])
        self.assertTrue(balance["gaze_converging"])
        self.assertLessEqual(balance["luminance_ratio"], 1.25)

    def test_route_polyphonic_cell_audio(self):
        grid = compose_diptych_triptych_grid(self.unit_ids_diptych, "diptych_horizontal", self.frame_span)
        routing = route_polyphonic_cell_audio(grid["cells"], max_active_stems=2)
        self.assertEqual(routing["schema"], "amps.god_here.polyphonic_audio_routing.v1")
        self.assertTrue(routing["peak_safe"])
        self.assertLessEqual(routing["master_peak_dbfs"], 0.0)

        # Check panning: left cell pan < 0, right cell pan > 0
        r0 = routing["stem_routes"][0]
        r1 = routing["stem_routes"][1]
        self.assertLess(r0["pan"], 0.0)
        self.assertGreater(r1["pan"], 0.0)

    def test_export_amalgamated_study_timeline(self):
        grid = compose_diptych_triptych_grid(self.unit_ids_diptych, "diptych_horizontal", self.frame_span)
        routing = route_polyphonic_cell_audio(grid["cells"])
        res = export_amalgamated_study_timeline(grid, routing)
        self.assertEqual(res.metadata["wing"], "wing_9_amalgamation")
        self.assertEqual(len(res.products), 2)
        kinds = [p.kind for p in res.products]
        self.assertIn("video", kinds)
        self.assertIn("audio", kinds)


if __name__ == "__main__":
    unittest.main()
