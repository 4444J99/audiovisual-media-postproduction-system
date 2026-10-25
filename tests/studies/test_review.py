"""Unit tests for common comparison & qualification harness (Issue #69, F06)."""
import os
import shutil
import unittest
from pathlib import Path

import numpy as np

from amp.composition.containers import (
    MaterialRef,
    SourceSpan,
    StudyBinding,
    StudyContext,
    StudyResult,
    Timebase,
)
from amp.studies import (
    build_review,
    compute_loudness_matching_gain,
    map_retimed_moments,
    verify_finite_samples,
)


class StudyReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(os.environ.get("PYTEST_TMPDIR", "/tmp")) / f"study-review-test-{os.getpid()}"
        if self.tmp.exists():
            shutil.rmtree(self.tmp)
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.output_dir = self.tmp / "build"
        self.output_dir.mkdir(parents=True)

        self.timebase = Timebase(30, 1)
        self.span = SourceSpan(start=0, end=150, timebase=self.timebase)

    def tearDown(self):
        if self.tmp.exists():
            shutil.rmtree(self.tmp, ignore_errors=True)

    def test_finite_samples_verification_and_rejection(self):
        rng = np.random.default_rng(42)
        valid_audio = rng.normal(0, 0.1, 1000).astype(np.float64)

        # Valid array passes
        verified = verify_finite_samples(valid_audio, "test_audio")
        self.assertIs(verified, valid_audio)

        # NaN rejection
        bad_nan = valid_audio.copy()
        bad_nan[50] = np.nan
        with self.assertRaisesRegex(ValueError, "non-finite samples"):
            verify_finite_samples(bad_nan)

        # Inf rejection
        bad_inf = valid_audio.copy()
        bad_inf[100] = np.inf
        with self.assertRaisesRegex(ValueError, "non-finite samples"):
            verify_finite_samples(bad_inf)

        # Negative Inf rejection
        bad_neginf = valid_audio.copy()
        bad_neginf[200] = -np.inf
        with self.assertRaisesRegex(ValueError, "non-finite samples"):
            verify_finite_samples(bad_neginf)

        # Zero RMS rejection
        zero_audio = np.zeros(1000, dtype=np.float64)
        with self.assertRaisesRegex(ValueError, "zero active RMS"):
            verify_finite_samples(zero_audio)

    def test_loudness_matching_within_half_lu_and_raw_stem_immutability(self):
        rng = np.random.default_rng(123)
        baseline = rng.normal(0, 0.10, 5000).astype(np.float64)
        # Candidate at 0.096 (very close: diff < 0.5 LU)
        candidate_close = rng.normal(0, 0.097, 5000).astype(np.float64)
        original_copy = candidate_close.copy()

        result = compute_loudness_matching_gain(candidate_close, baseline, tolerance_lu=0.5)

        self.assertFalse(result["raw_stem_mutated"])
        self.assertTrue(result["within_tolerance"])
        self.assertLessEqual(result["diff_lu"], 0.5)

        # Verify candidate array was NOT mutated in-place
        self.assertTrue(np.array_equal(candidate_close, original_copy))

        # Check that matched copy achieves loudness parity
        matched = result["matched_copy"]
        rms_matched = float(np.sqrt(np.mean(matched ** 2)))
        rms_baseline = float(np.sqrt(np.mean(baseline ** 2)))
        self.assertAlmostEqual(rms_matched, rms_baseline, places=6)

        # Candidate with larger difference (> 0.5 LU) is correctly flagged
        candidate_far = rng.normal(0, 0.05, 5000).astype(np.float64)
        result_far = compute_loudness_matching_gain(candidate_far, baseline, tolerance_lu=0.5)
        self.assertFalse(result_far["within_tolerance"])
        self.assertGreater(result_far["diff_lu"], 0.5)
        self.assertFalse(result_far["raw_stem_mutated"])

    def test_retimed_moment_mapping(self):
        c_span = SourceSpan(start=0, end=100)
        b_span = SourceSpan(start=100, end=200)

        # Linear proportional fallback: 50 -> 150
        self.assertEqual(map_retimed_moments(50.0, c_span, b_span), 150.0)
        self.assertEqual(map_retimed_moments(0.0, c_span, b_span), 100.0)
        self.assertEqual(map_retimed_moments(100.0, c_span, b_span), 200.0)

        # With piecewise linear retiming map (2x slow-down in first span)
        retiming_map = [
            {"output_start": 0, "output_end": 40, "source_start": 100, "source_end": 120},
            {"output_start": 40, "output_end": 100, "source_start": 120, "source_end": 200},
        ]
        # Midpoint of span 1: 20 output -> 110 source
        self.assertEqual(map_retimed_moments(20.0, c_span, b_span, retiming_map), 110.0)
        # Midpoint of span 2: 70 output -> 160 source
        self.assertEqual(map_retimed_moments(70.0, c_span, b_span, retiming_map), 160.0)

        # Out-of-bounds or non-finite time raises ValueError
        with self.assertRaises(ValueError):
            map_retimed_moments(150.0, c_span, b_span)
        with self.assertRaises(ValueError):
            map_retimed_moments(float("nan"), c_span, b_span)

    def test_build_review_dispatch(self):
        rng = np.random.default_rng(999)
        cand_samples = rng.normal(0, 0.1, 1000).tolist()
        base_samples = rng.normal(0, 0.1, 1000).tolist()

        mat_ref = MaterialRef(id="cand-01", sha256="d" * 64, kind="audio")

        binding = StudyBinding(
            operator="passthrough",
            materials=(mat_ref,),
            parameters={
                "workstream_id": "speech-review",
                "case_id": "case-rev-01",
                "candidate_samples": cand_samples,
                "baseline_samples": base_samples,
            },
            span=self.span,
            timebase=self.timebase,
        )

        ctx = StudyContext(
            study_id="review-f06",
            composition_id="comp-001",
            bindings=(binding,),
            timebase=self.timebase,
            output_dir=str(self.output_dir),
        )

        result = build_review(binding, ctx)
        self.assertIsInstance(result, StudyResult)
        self.assertEqual(result.study_id, "review-f06")
        self.assertFalse(result.metadata["raw_stem_mutated"])
        self.assertEqual(len(result.products), 1)

        product = result.products[0]
        self.assertTrue(Path(product.path).is_file())


if __name__ == "__main__":
    unittest.main()
