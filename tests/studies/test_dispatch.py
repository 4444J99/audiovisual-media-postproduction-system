"""Unit tests for study execution dispatch framework (Issue #68, F05)."""
import os
import shutil
import unittest
from pathlib import Path

from amp.composition.containers import (
    MaterialRef,
    SourceSpan,
    StudyBinding,
    StudyContext,
    StudyResult,
    Timebase,
)
from amp.execution import execute_study, is_study_binding
from amp.studies import (
    STUDY_BINDING_FAMILY,
    resolve_study_output_dir,
    run_study,
)


class StudyDispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(os.environ.get("PYTEST_TMPDIR", "/tmp")) / f"study-dispatch-test-{os.getpid()}"
        if self.tmp.exists():
            shutil.rmtree(self.tmp)
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.output_dir = self.tmp / "build"
        self.output_dir.mkdir(parents=True)

        self.timebase = Timebase(30, 1)
        self.span = SourceSpan(start=0, end=300, timebase=self.timebase)
        self.mat_ref = MaterialRef(
            id="src-mat-01",
            sha256="c" * 64,
            kind="audio",
            bytes=4096,
            span=self.span,
        )

    def tearDown(self):
        if self.tmp.exists():
            shutil.rmtree(self.tmp, ignore_errors=True)

    def test_deterministic_output_directory_layout(self):
        ctx = StudyContext(
            study_id="study-alpha",
            composition_id="comp-001",
            timebase=self.timebase,
            output_dir=str(self.output_dir),
        )
        resolved = resolve_study_output_dir(ctx, "w01-speech", "case-01")
        expected = self.output_dir / "god-here" / "studies" / "w01-speech" / "study-alpha" / "case-01"
        self.assertEqual(resolved, expected)

    def test_valid_study_dispatch(self):
        binding = StudyBinding(
            operator="passthrough",
            materials=(self.mat_ref,),
            parameters={"case_id": "case-dense-01", "gain": 1.0},
            span=self.span,
            timebase=self.timebase,
        )
        ctx = StudyContext(
            study_id="study-f05",
            composition_id="comp-001",
            bindings=(binding,),
            timebase=self.timebase,
            output_dir=str(self.output_dir),
            parameters={"workstream_id": "audio-restoration"},
        )

        result = run_study(binding, ctx)
        self.assertIsInstance(result, StudyResult)
        self.assertEqual(result.study_id, "study-f05")
        self.assertEqual(result.operator, "passthrough")
        self.assertEqual(result.span, self.span)
        self.assertEqual(len(result.products), 1)

        product = result.products[0]
        self.assertTrue(Path(product.path).is_file())
        self.assertEqual(product.kind, "metadata")

        expected_dir = self.output_dir / "god-here" / "studies" / "audio-restoration" / "study-f05" / "case-dense-01"
        self.assertEqual(Path(result.metadata["output_dir"]), expected_dir)

    def test_fail_closed_on_missing_identifiers(self):
        binding = StudyBinding(
            operator="passthrough",
            materials=(self.mat_ref,),
            parameters={},
        )
        ctx = StudyContext(
            study_id="study-test",
            composition_id="comp-001",
            timebase=self.timebase,
            output_dir=str(self.output_dir),
        )

        # Missing workstream_id
        with self.assertRaisesRegex(ValueError, "workstream_id"):
            run_study(binding, ctx)

        # Missing case_id
        ctx_with_ws = StudyContext(
            study_id="study-test",
            composition_id="comp-001",
            timebase=self.timebase,
            output_dir=str(self.output_dir),
            parameters={"workstream_id": "speech"},
        )
        with self.assertRaisesRegex(ValueError, "case_id"):
            run_study(binding, ctx_with_ws)

    def test_fail_closed_on_incompatible_timebase(self):
        binding = StudyBinding(
            operator="passthrough",
            materials=(self.mat_ref,),
            parameters={"case_id": "c1", "workstream_id": "w1"},
            timebase=Timebase(24, 1),  # Incompatible with context (30, 1)
        )
        ctx = StudyContext(
            study_id="study-test",
            composition_id="comp-001",
            timebase=Timebase(30, 1),
            output_dir=str(self.output_dir),
            parameters={"workstream_id": "w1"},
        )
        with self.assertRaisesRegex(ValueError, "Incompatible Timebase"):
            run_study(binding, ctx)

    def test_fail_closed_on_empty_inputs(self):
        binding = StudyBinding(
            operator="passthrough",
            materials=(),
            parameters={"case_id": "c1", "workstream_id": "w1"},
        )
        ctx = StudyContext(
            study_id="study-test",
            composition_id="comp-001",
            timebase=self.timebase,
            output_dir=str(self.output_dir),
            parameters={"workstream_id": "w1"},
        )
        with self.assertRaisesRegex(ValueError, "at least one input"):
            run_study(binding, ctx)

    def test_fail_closed_on_path_traversal(self):
        ctx = StudyContext(
            study_id="study-test",
            composition_id="comp-001",
            timebase=self.timebase,
            output_dir=str(self.output_dir),
        )
        with self.assertRaisesRegex(ValueError, "Invalid path characters"):
            resolve_study_output_dir(ctx, "../escape", "c1")
        with self.assertRaisesRegex(ValueError, "Invalid path characters"):
            resolve_study_output_dir(ctx, "w1", "subdir/c1")

    def test_execution_wiring(self):
        self.assertTrue(is_study_binding({"schema_version": STUDY_BINDING_FAMILY}))
        self.assertFalse(is_study_binding({"schema_version": "amps.execution.v1"}))

        binding_dict = {
            "operator": "passthrough",
            "inputs": [self.mat_ref.to_dict()],
            "parameters": {"case_id": "c01", "workstream_id": "ws01"},
            "timebase": {"num": 30, "den": 1},
        }
        ctx_dict = {
            "study_id": "study-wiring",
            "composition_id": "comp-001",
            "timebase": {"num": 30, "den": 1},
            "output_dir": str(self.output_dir),
            "parameters": {"workstream_id": "ws01"},
        }
        res = execute_study(binding_dict, ctx_dict)
        self.assertEqual(res.study_id, "study-wiring")
        self.assertEqual(res.operator, "passthrough")


if __name__ == "__main__":
    unittest.main()
