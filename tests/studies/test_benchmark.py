"""Validation tests for shared benchmark set, reviewed vocabulary, and reuse map (Issue #65, F02)."""
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STUDIES_DIR = REPO_ROOT / "projects" / "god-here" / "studies"


class BenchmarkValidationTests(unittest.TestCase):
    def setUp(self):
        self.benchmark_path = STUDIES_DIR / "benchmark.json"
        self.review_path = STUDIES_DIR / "units.review.json"
        self.reuse_path = STUDIES_DIR / "reuse-map.json"

        self.assertTrue(self.benchmark_path.is_file(), "benchmark.json must exist")
        self.assertTrue(self.review_path.is_file(), "units.review.json must exist")
        self.assertTrue(self.reuse_path.is_file(), "reuse-map.json must exist")

        self.benchmark = json.loads(self.benchmark_path.read_text(encoding="utf-8"))
        self.review = json.loads(self.review_path.read_text(encoding="utf-8"))
        self.reuse_map = json.loads(self.reuse_path.read_text(encoding="utf-8"))

    def test_benchmark_contains_exactly_24_units(self):
        units = self.benchmark.get("units", [])
        self.assertEqual(len(units), 24, "Benchmark must define exactly 24 units")
        review_units = self.review.get("units", [])
        self.assertEqual(len(review_units), 24, "Units review must define exactly 24 units")

    def test_all_six_case_types_covered(self):
        required_case_types = {
            "intelligible_foreground_speech",
            "room_dense_invocation",
            "cut_boundary_transition",
            "breath_pause_punctuation",
            "movement_impact_transient",
            "reverb_tail_hold",
        }
        covered_types = {u["case_type"] for u in self.benchmark["units"]}
        self.assertEqual(covered_types, required_case_types, "All 6 shared case types must be covered")

        review_types = {u["case_type"] for u in self.review["units"]}
        self.assertEqual(review_types, required_case_types, "All 6 shared case types must be covered in units.review.json")

    def test_frame_bounds_inside_valid_spine(self):
        total_frames = self.benchmark.get("spine", {}).get("total_frames", 3360)
        self.assertEqual(total_frames, 3360)

        for u in self.benchmark["units"]:
            f_start, f_end = u["frame_span"]
            self.assertIsInstance(f_start, int)
            self.assertIsInstance(f_end, int)
            self.assertFalse(isinstance(f_start, bool))
            self.assertFalse(isinstance(f_end, bool))
            self.assertGreaterEqual(f_start, 0, f"Unit {u['id']} start frame must be >= 0")
            self.assertLess(f_start, f_end, f"Unit {u['id']} start frame must be < end frame")
            self.assertLessEqual(f_end, 3360, f"Unit {u['id']} end frame must be <= 3360")

    def test_distinct_44k1_and_48k_sample_counts(self):
        total_samples_44k1 = self.benchmark["spine"]["native_total_samples"]
        total_samples_48k = self.benchmark["spine"]["derivative_total_samples"]
        self.assertEqual(total_samples_44k1, 4939200)
        self.assertEqual(total_samples_48k, 5376000)

        for u in self.benchmark["units"]:
            s44_start, s44_end = u["sample_span_44k1"]
            s48_start, s48_end = u["sample_span_48k"]

            self.assertGreaterEqual(s44_start, 0)
            self.assertLessEqual(s44_end, 4939200)
            self.assertGreaterEqual(s48_start, 0)
            self.assertLessEqual(s48_end, 5376000)

            count_44k1 = s44_end - s44_start
            count_48k = s48_end - s48_start

            self.assertGreater(count_44k1, 0)
            self.assertGreater(count_48k, 0)
            self.assertNotEqual(
                count_44k1,
                count_48k,
                f"Unit {u['id']} 44.1kHz sample count ({count_44k1}) must differ from 48kHz count ({count_48k})",
            )

    def test_draft_transcript_and_reviewed_heard_wording_kept_separate(self):
        for u in self.benchmark["units"]:
            self.assertIn("draft_transcript", u)
            self.assertIn("reviewed_heard_wording", u)
            self.assertIsInstance(u["draft_transcript"], str)
            self.assertIsInstance(u["reviewed_heard_wording"], str)

        for ru in self.review["units"]:
            self.assertIn("draft_transcript", ru)
            self.assertIn("reviewed_heard_wording", ru)

    def test_reuse_map_manifest_structure(self):
        self.assertEqual(self.reuse_map.get("schema"), "amps.god_here.reuse_map.v1")
        entries = self.reuse_map.get("entries", [])
        self.assertGreaterEqual(len(entries), 4)

        required_keys = {"sha256", "size", "role", "custody_status", "producer", "reuse_disposition"}
        movie_sha = "bde1c7e0910941f8ca3bce06e8c2ddb3a31da4335b544fd041d84e97d1060225"
        found_movie = False

        for entry in entries:
            self.assertEqual(set(entry.keys()), required_keys)
            self.assertIsInstance(entry["sha256"], str)
            self.assertEqual(len(entry["sha256"]), 64)
            self.assertIsInstance(entry["size"], int)
            self.assertGreater(entry["size"], 0)
            if entry["sha256"] == movie_sha:
                found_movie = True
                self.assertEqual(entry["custody_status"], "privately_preserved")
                self.assertEqual(entry["size"], 12636527)

        self.assertTrue(found_movie, "Supplied movie hash must be registered in reuse map")


if __name__ == "__main__":
    unittest.main()
