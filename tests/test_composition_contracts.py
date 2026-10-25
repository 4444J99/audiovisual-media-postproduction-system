"""Unit tests for T11 M0 shared foundation compatibility migration & typed contracts (Issues #64, #66)."""
import unittest

# 1. Compatibility migration test: legacy import from amp.composition
from amp.composition import (
    ALLOWED_OPERATORS,
    MaterialRef,
    PerformanceRecord,
    SourceSpan,
    StudyBinding,
    StudyContext,
    StudyResult,
    Timebase,
    resolve_composition,
)
# Submodule imports
from amp.composition.containers import (
    ALLOWED_MATERIAL_KINDS,
    MaterialRef as ContainerMaterialRef,
    SourceSpan as ContainerSourceSpan,
    StudyBinding as ContainerStudyBinding,
    StudyContext as ContainerStudyContext,
    StudyResult as ContainerStudyResult,
    Timebase as ContainerTimebase,
)
from amp.composition.record import PerformanceRecord as ModulePerformanceRecord


class CompositionContractsTests(unittest.TestCase):
    def test_legacy_resolve_composition_export_preserved(self):
        # Verify callable and identical reference
        self.assertTrue(callable(resolve_composition))
        import amp.composition
        self.assertIs(amp.composition.resolve_composition, resolve_composition)
        self.assertIs(ContainerSourceSpan, SourceSpan)
        self.assertIs(ModulePerformanceRecord, PerformanceRecord)

    def test_timebase_validation(self):
        tb = Timebase(30, 1)
        self.assertEqual(tb.fps, 30.0)
        self.assertEqual(tb.to_dict(), {"num": 30, "den": 1})
        self.assertEqual(Timebase.from_dict({"num": 24000, "den": 1001}).as_fraction().numerator, 24000)

        # Rejects invalid rational timebases
        for bad_num in [0, -1, 30.5, True, False, "30"]:
            with self.assertRaises(ValueError):
                Timebase(bad_num, 1)
        for bad_den in [0, -1, 1.5, True, False, "1"]:
            with self.assertRaises(ValueError):
                Timebase(30, bad_den)

    def test_source_span_integer_half_open_domain(self):
        tb = Timebase(30, 1)
        span = SourceSpan(start=0, end=90, timebase=tb)
        self.assertEqual(span.duration_frames, 90)
        self.assertEqual(span.duration_seconds, 3.0)
        self.assertTrue(span.contains(0))
        self.assertTrue(span.contains(89))
        self.assertFalse(span.contains(90))  # Half-open: end is excluded!
        self.assertFalse(span.contains(-1))

        other = SourceSpan(start=50, end=100)
        self.assertTrue(span.overlaps(other))
        disjoint = SourceSpan(start=100, end=200)
        self.assertFalse(span.overlaps(disjoint))

        # Roundtrip
        self.assertEqual(SourceSpan.from_dict(span.to_dict()), span)

        # Validation rejects non-integers, negative start, start >= end, bools
        for bad_start in [-1, 10.5, True, False, "0"]:
            with self.assertRaises(ValueError):
                SourceSpan(start=bad_start, end=100)
        for bad_end in [0, 50, 49, 50.5, True, False, "100"]:
            with self.assertRaises(ValueError):
                SourceSpan(start=50, end=bad_end)

    def test_material_ref_validation_and_url_rejection(self):
        sha = "a" * 64
        ref = MaterialRef(id="mat-01", sha256=sha, kind="video", bytes=1024, path="assets/clip.mp4")
        self.assertEqual(ref.to_dict()["id"], "mat-01")
        self.assertEqual(MaterialRef.from_dict(ref.to_dict()), ref)

        # Rejects invalid sha256
        with self.assertRaises(ValueError):
            MaterialRef(id="mat-01", sha256="not-hex", kind="video")
        with self.assertRaises(ValueError):
            MaterialRef(id="mat-01", sha256="a" * 63, kind="video")

        # Rejects invalid kind
        with self.assertRaises(ValueError):
            MaterialRef(id="mat-01", sha256=sha, kind="unsupported_arbitrary_kind")

        # Rejects negative or boolean bytes
        with self.assertRaises(ValueError):
            MaterialRef(id="mat-01", sha256=sha, kind="video", bytes=-5)
        with self.assertRaises(ValueError):
            MaterialRef(id="mat-01", sha256=sha, kind="video", bytes=True)

        # Rejects remote URLs in path or id
        with self.assertRaises(ValueError):
            MaterialRef(id="mat-01", sha256=sha, kind="video", path="https://example.com/stream.mp4")
        with self.assertRaises(ValueError):
            MaterialRef(id="mat-01", sha256=sha, kind="video", path="http://remote.host/video.m4v")

        # Rejects arbitrary shell command injection
        with self.assertRaises(ValueError):
            MaterialRef(id="mat-01", sha256=sha, kind="video", path="clip.mp4; rm -rf /")
        with self.assertRaises(ValueError):
            MaterialRef(id="mat-01", sha256=sha, kind="video", path="clip.mp4 | cat")

    def test_study_binding_operator_allowlist(self):
        sha = "b" * 64
        mat = MaterialRef(id="src-01", sha256=sha, kind="audio")
        binding = StudyBinding(operator="amp.roomstretch.v1", materials=(mat,), parameters={"factor": 1.5})
        self.assertEqual(binding.operator, "amp.roomstretch.v1")
        self.assertEqual(StudyBinding.from_dict(binding.to_dict()), binding)

        # Rejects operators outside fixed allowlist
        with self.assertRaises(ValueError):
            StudyBinding(operator="arbitrary_unauthorized_operator", materials=(mat,))

        # Rejects remote URLs or shell commands in operator or parameters
        with self.assertRaises(ValueError):
            StudyBinding(operator="https://remote-runner.internal/exec", materials=(mat,))
        with self.assertRaises(ValueError):
            StudyBinding(operator="amp.roomstretch.v1", parameters={"cmd": "bash -c malicious"})
        with self.assertRaises(ValueError):
            StudyBinding(operator="amp.roomstretch.v1", parameters={"url": "http://evil.internal/hook"})

    def test_study_context_and_result(self):
        sha = "c" * 64
        mat = MaterialRef(id="src-02", sha256=sha, kind="video")
        binding = StudyBinding(operator="passthrough", materials=(mat,))
        ctx = StudyContext(study_id="study-01", composition_id="comp-001", bindings=(binding,))
        self.assertEqual(ctx.study_id, "study-01")
        self.assertEqual(StudyContext.from_dict(ctx.to_dict()), ctx)

        # StudyResult
        span = SourceSpan(start=0, end=60)
        res = StudyResult(study_id="study-01", operator="passthrough", span=span, products=(mat,))
        self.assertEqual(res.operator, "passthrough")
        self.assertEqual(StudyResult.from_dict(res.to_dict()), res)

        # Context rejects remote URLs in media_root or study_id
        with self.assertRaises(ValueError):
            StudyContext(study_id="study-01", composition_id="comp-001", media_root="http://external-storage")

    def test_performance_record_validation(self):
        span = SourceSpan(start=100, end=500, timebase=Timebase(30, 1))
        tb = Timebase(30, 1)
        record = PerformanceRecord(
            record_id="perf-001",
            composition_id="comp-001",
            span=span,
            timebase=tb,
            performer_states={"P01": 0.8, "P02": 0.0, "P03": 1.0},
            timestamp="2026-10-24T12:00:00Z",
            provenance={"commit": "abc1234"},
        )
        self.assertEqual(record.performer_states["P01"], 0.8)
        self.assertEqual(PerformanceRecord.from_dict(record.to_dict()), record)

        # Rejects invalid performer intensities (outside [0, 1], bools, non-finite)
        for bad_intensity in [-0.1, 1.1, float("nan"), float("inf"), True, False, "0.5"]:
            with self.assertRaises(ValueError):
                PerformanceRecord(
                    record_id="perf-001",
                    composition_id="comp-001",
                    span=span,
                    timebase=tb,
                    performer_states={"P01": bad_intensity},
                )

        # Rejects remote URLs or commands in provenance
        with self.assertRaises(ValueError):
            PerformanceRecord(
                record_id="perf-001",
                composition_id="comp-001",
                span=span,
                timebase=tb,
                provenance={"source_url": "http://untrusted-source/leak"},
            )


if __name__ == "__main__":
    unittest.main()
