import copy
import hashlib
import json
import struct
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.io import wavfile

from amp.roomaudit import (SCHEMA, _add_wav_cues, build_audit, inventory_portions,
                           _verify_review_mp3, portion_metrics, propose_subregion, resolve_selection)


class RoomAuditTests(unittest.TestCase):
    def setUp(self):
        self.inventory = {"source_sha256": "a" * 64, "pauses": [
            {"id": "PAUSE001", "usable_portions": []},
            {"id": "PAUSE002", "usable_portions": [{"start": .2, "end": 1.2},
                                                      {"start": 2.2, "end": 2.4}]}]}
        self.manifest = {"schema_version": SCHEMA, "source_sha256": "a" * 64,
                         "pause_inventory_sha256": "b" * 64, "portions": [
            {**p, "action": "keep", "selected_start": p["source_start"], "selected_end": p["source_end"],
             "status": "algorithmic_candidate"} for p in inventory_portions(self.inventory)]}

    def resolve(self, manifest=None):
        return resolve_selection(self.inventory, manifest or self.manifest,
                                 source_sha256="a" * 64, pause_inventory_sha256="b" * 64)

    def test_original_pool_resolves_without_pretending_human_approval(self):
        rows = self.resolve()
        self.assertEqual([r["portion_id"] for r in rows], ["PAUSE002-01", "PAUSE002-02"])
        self.assertEqual(rows[0]["status"], "algorithmic_candidate")
        self.assertAlmostEqual(sum(r["end"] - r["start"] for r in rows), 1.2)

    def test_exclusion_and_subregion_preserve_traceability(self):
        first, second = self.manifest["portions"]
        first.update(action="subregion", selected_start=.3, selected_end=1.)
        second.update(action="exclude", selected_start=None, selected_end=None, reason="Comparison only")
        rows = self.resolve()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["start"], .3)
        self.assertEqual(first["source_start"], .2)

    def test_hash_mismatch_rejected(self):
        for key in ("source_sha256", "pause_inventory_sha256"):
            bad = copy.deepcopy(self.manifest)
            bad[key] = "c" * 64
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "hash mismatch"):
                self.resolve(bad)

    def test_duplicate_missing_unknown_and_changed_original_bounds_rejected(self):
        bad = copy.deepcopy(self.manifest)
        bad["portions"][1] = copy.deepcopy(bad["portions"][0])
        with self.assertRaises(ValueError):
            self.resolve(bad)
        bad = copy.deepcopy(self.manifest)
        bad["portions"].pop()
        with self.assertRaises(ValueError):
            self.resolve(bad)
        bad = copy.deepcopy(self.manifest)
        bad["portions"][0]["source_start"] = .19
        with self.assertRaises(ValueError):
            self.resolve(bad)

    def test_subregion_cannot_escape_grid_or_be_too_short(self):
        for start, end in ((.19, .8), (.201, .9), (.3, .42), (.8, 1.21), (.9, .4), (float('nan'), .9)):
            bad = copy.deepcopy(self.manifest)
            bad["portions"][0].update(action="subregion", selected_start=start, selected_end=end)
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                self.resolve(bad)

    def test_human_status_requires_actual_review_record(self):
        first = self.manifest["portions"][0]
        first["status"] = "human_accepted"
        with self.assertRaisesRegex(ValueError, "reviewer"):
            self.resolve()
        first.update(reviewed_by="Test listener", reviewed_at="2026-10-11", review_notes="Fixture decision")
        self.assertEqual(self.resolve()[0]["status"], "human_accepted")
        first["status"] = "human_rejected"
        with self.assertRaisesRegex(ValueError, "rejected"):
            self.resolve()

    def test_all_exclusions_do_not_create_empty_render_pool(self):
        for row in self.manifest["portions"]:
            row.update(action="exclude", selected_start=None, selected_end=None, reason="Fixture")
        with self.assertRaisesRegex(ValueError, "no source"):
            self.resolve()

    def test_variation_metric_responds_to_known_envelope(self):
        rate = 4000
        t = np.arange(rate) / rate
        base = .01 * np.sin(2 * np.pi * 500 * t)
        stable = np.column_stack([base, base])
        moving = stable * np.where(t < .5, 1., 4.)[:, None]
        a, b = portion_metrics(stable, rate), portion_metrics(moving, rate)
        self.assertLess(a["frame_rms_p90_p10_db"], .1)
        self.assertGreater(b["frame_rms_p90_p10_db"], 11)
        self.assertAlmostEqual(a["stereo_correlation"], 1.)
        self.assertEqual(a["analysis_frame_count"], 99)

    def test_metric_rejects_nonfinite_audio_and_handles_silence(self):
        bad = np.zeros((100, 2))
        bad[0, 1] = np.nan
        with self.assertRaises(ValueError):
            portion_metrics(bad, 4000)
        clean = portion_metrics(np.zeros((100, 2)), 4000)
        self.assertEqual(clean["frame_rms_p90_p10_db"], 0.)
        self.assertIsNone(clean["stereo_correlation"])

    def test_candidate_is_contained_and_does_not_trim_stable_noise(self):
        rate = 4000
        t = np.arange(rate * 2) / rate
        mono = .01 * np.sin(2 * np.pi * 500 * t)
        x = np.column_stack([mono, mono])
        portion = {"source_start": .2, "source_end": 1.2}
        self.assertIsNone(propose_subregion(x, portion, rate=rate))
        x[round(.2 * rate):round(.45 * rate)] *= 1.7
        candidate = propose_subregion(x, portion, rate=rate)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["status"], "algorithmic_candidate")
        self.assertGreaterEqual(candidate["selected_start"], .2)
        self.assertLessEqual(candidate["selected_end"], 1.2)
        self.assertGreaterEqual(candidate["frame_rms_spread_reduction_db"], 1.5)

    def test_wav_cues_preserve_audio_bytes_and_mark_exact_samples(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "review.wav"
            samples = np.zeros((400, 2), np.float32)
            wavfile.write(path, 4000, samples)
            before = path.read_bytes()
            _add_wav_cues(path, [40, 120])
            data = path.read_bytes()
            self.assertEqual(data[8:len(before)], before[8:])
            self.assertEqual(struct.unpack("<I", data[4:8])[0], len(data) - 8)
            start = data.index(b"cue ")
            self.assertEqual(struct.unpack("<I", data[start + 8:start + 12])[0], 2)
            self.assertEqual(struct.unpack("<I", data[start + 32:start + 36])[0], 40)
            self.assertEqual(struct.unpack("<I", data[start + 56:start + 60])[0], 120)

    def test_empty_or_truncated_mp3_cannot_pass_delivery_validation(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bad.mp3"
            path.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "empty"):
                _verify_review_mp3(path, 100)
            path.write_bytes(b"not a real mp3")
            with patch("amp.roomaudit.subprocess.check_output", return_value=bytes(99 * 8)):
                with self.assertRaisesRegex(ValueError, "timeline"):
                    _verify_review_mp3(path, 100)

    def test_rendered_review_keeps_source_portions_and_exact_boundaries(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            source, inventory_path = base / "source.mp4", base / "inventory.json"
            source.write_bytes(b"source identity fixture")
            inventory = copy.deepcopy(self.inventory)
            inventory["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            inventory_path.write_text(json.dumps(inventory))
            t = np.arange(48000 * 3) / 48000
            mono = (.02 * np.sin(2 * np.pi * 500 * t)).astype(np.float32)
            samples = np.column_stack([mono, mono])
            with patch("amp.roomaudit.load_audio", return_value=samples):
                report = build_audit(source, inventory_path, base / "review", mp3=False)
            self.assertTrue(report["original_pool_preserved"])
            self.assertEqual(report["listening_acceptance"], "pending")
            gain = 10 ** (report["review_common_gain_db"] / 20)
            for record in report["portions"]:
                meta = record["review_audio"]
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", wavfile.WavFileWarning)
                    rate, actual = wavfile.read(base / "review" / meta["path"])
                start, end = meta["portion_start_sample"], meta["portion_end_sample"]
                expected = samples[round(record["source_start"] * rate):round(record["source_end"] * rate)] * gain
                np.testing.assert_array_equal(actual[start:end], expected)
                np.testing.assert_array_equal(actual[[0, -1]], np.zeros((2, 2)))


if __name__ == "__main__":
    unittest.main()
