"""Tests for study contract and schema validation pack (Issue #66, F03)."""
import unittest

from amp.composition.containers import MaterialRef, SourceSpan, StudyBinding, Timebase
from amp.composition.record import PerformanceRecord
from amp.studies.contracts import (
    REQUIRED_PROVENANCE_FIELDS,
    STATUS_AXIS,
    validate_binding,
    validate_dependency_dag,
    validate_mask_to_body_span,
    validate_material,
    validate_performance,
)


class StudyContractsTests(unittest.TestCase):
    def setUp(self):
        self.timebase = Timebase(30, 1)
        self.span = SourceSpan(start=0, end=90, timebase=self.timebase)
        self.provenance = {
            "source_id": "SRC-002",
            "unit_id": "BM-01",
            "model_id": "R01",
            "seed": 42,
        }
        self.material = MaterialRef(
            id="mat-01",
            sha256="a" * 64,
            kind="video",
            bytes=2048,
        )

    def test_valid_binding(self):
        binding = StudyBinding(
            operator="amp.roomstretch.v1",
            materials=(self.material,),
            span=self.span,
            status="admitted",
            provenance=self.provenance,
            parameters={"mode": "fine"},
        )
        errors = validate_binding(binding)
        self.assertEqual(errors, ())

    def test_binding_dict_validation(self):
        raw = {
            "operator": "amp.foley.v1",
            "parameters": {"gain": 1.0},
            "span": {"start": 10, "end": 50},
            "status": "executed",
            "provenance": self.provenance,
        }
        errors = validate_binding(raw)
        self.assertEqual(errors, ())

    def test_interval_validation_non_integer_and_inverted(self):
        # Non-integer / boolean start
        errors_bool = validate_binding({
            "operator": "amp.foley.v1",
            "parameters": {},
            "span": {"start": True, "end": 50},
            "status": "not_tested",
            "provenance": self.provenance,
        })
        self.assertTrue(any("start must be an integer (not bool)" in e for e in errors_bool))

        # Inverted / equal interval: end <= start
        errors_inverted = validate_binding({
            "operator": "amp.foley.v1",
            "parameters": {},
            "span": {"start": 50, "end": 50},
            "status": "not_tested",
            "provenance": self.provenance,
        })
        self.assertTrue(any("must be strictly greater than start" in e for e in errors_inverted))

        errors_negative = validate_binding({
            "operator": "amp.foley.v1",
            "parameters": {},
            "span": {"start": -5, "end": 50},
            "status": "not_tested",
            "provenance": self.provenance,
        })
        self.assertTrue(any("start must be non-negative" in e for e in errors_negative))

    def test_provenance_explicit_requirements(self):
        # Missing required field 'seed'
        bad_prov = {
            "source_id": "SRC-002",
            "unit_id": "BM-01",
            "model_id": "R01",
        }
        errors = validate_binding({
            "operator": "amp.foley.v1",
            "parameters": {},
            "status": "not_tested",
            "provenance": bad_prov,
        })
        self.assertTrue(any("missing required field: 'seed'" in e for e in errors))

        # Non-integer seed
        bad_seed_prov = {
            "source_id": "SRC-002",
            "unit_id": "BM-01",
            "model_id": "R01",
            "seed": "not-an-int",
        }
        errors2 = validate_binding({
            "operator": "amp.foley.v1",
            "parameters": {},
            "status": "not_tested",
            "provenance": bad_seed_prov,
        })
        self.assertTrue(any("seed must be an integer" in e for e in errors2))

    def test_status_axis(self):
        for valid_status in STATUS_AXIS:
            binding = {
                "operator": "amp.foley.v1",
                "parameters": {},
                "status": valid_status,
                "provenance": self.provenance,
            }
            self.assertEqual(validate_binding(binding), ())

        # Invalid status
        bad_status_binding = {
            "operator": "amp.foley.v1",
            "parameters": {},
            "status": "completely_unauthorized_status",
            "provenance": self.provenance,
        }
        errors = validate_binding(bad_status_binding)
        self.assertTrue(any("not in valid status axis" in e for e in errors))

    def test_mask_to_body_span_coupling_defaults_to_the_same_bound_span(self):
        bound=dict(start=0,end=90,timebase={'num':30,'den':1},source_sha256='a'*64,clock_kind='video_frame')
        coupling_errors = validate_mask_to_body_span(
            mask_span=bound,
            body_span=bound,
            target_body="performer_P01_face",
            on_screen=True,
        )
        self.assertEqual(coupling_errors, ())

    def test_mask_to_body_span_coupling_out_of_bounds(self):
        # Out-of-bounds start: mask starts at -5 (or before body start 10)
        errors1 = validate_mask_to_body_span(
            mask_span=(5, 40),
            body_span=(10, 90),
            target_body="performer_P01_face",
            on_screen=True,
        )
        self.assertTrue(any("earlier than body interval start" in e for e in errors1))

        # Out-of-bounds end: mask ends at 100 but body ends at 90
        errors2 = validate_mask_to_body_span(
            mask_span=(20, 100),
            body_span=(10, 90),
            target_body="performer_P01_face",
            on_screen=True,
        )
        self.assertTrue(any("exceeds body interval end" in e for e in errors2))

    def test_mask_targets_off_screen_body_rejection(self):
        # Off-screen target rejection
        errors = validate_mask_to_body_span(
            mask_span=(10, 40),
            body_span=(0, 90),
            target_body="offscreen_narrator",
            on_screen=False,
        )
        self.assertTrue(any("off-screen" in e for e in errors))

        # In binding parameters
        binding = {
            "operator": "amp.foley.v1",
            "parameters": {
                "mask_coupling": {
                    "target_body": "offscreen_narrator",
                    "on_screen": False,
                    "mask_span": {"start": 10, "end": 40},
                    "body_span": {"start": 0, "end": 90},
                }
            },
            "status": "not_tested",
            "provenance": self.provenance,
        }
        errors_binding = validate_binding(binding)
        self.assertTrue(any("off-screen" in e for e in errors_binding))

    def test_dependency_dag_acyclic(self):
        b1 = {"id": "b1", "dependencies": []}
        b2 = {"id": "b2", "dependencies": ["b1"]}
        b3 = {"id": "b3", "dependencies": ["b2", "b1"]}
        errors = validate_dependency_dag([b1, b2, b3])
        self.assertEqual(errors, ())

    def test_dependency_dag_cycle_detection(self):
        b1 = {"id": "b1", "dependencies": ["b3"]}
        b2 = {"id": "b2", "dependencies": ["b1"]}
        b3 = {"id": "b3", "dependencies": ["b2"]}
        errors = validate_dependency_dag([b1, b2, b3])
        self.assertTrue(len(errors) > 0)
        self.assertTrue(any("Dependency cycle detected" in e for e in errors))

        with self.assertRaises(ValueError):
            validate_dependency_dag([b1, b2, b3], raise_on_cycle=True)

    def test_validate_material_and_performance(self):
        # Material
        mat_errors = validate_material(self.material)
        self.assertEqual(mat_errors, ())

        bad_mat = {"id": "bad", "sha256": "123", "kind": "unsupported"}
        self.assertTrue(len(validate_material(bad_mat)) > 0)

        # Performance
        perf = PerformanceRecord(
            record_id="perf-01",
            composition_id="comp-001",
            span=self.span,
            timebase=self.timebase,
            performer_states={"P01": 0.8},
        )
        perf_errors = validate_performance(perf)
        self.assertEqual(perf_errors, ())


if __name__ == "__main__":
    unittest.main()
