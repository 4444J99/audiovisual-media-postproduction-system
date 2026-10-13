"""Synthetic evidence tests; these do not certify a real source transcript."""

from copy import deepcopy
import unittest

from amp.qualification import audit_qualification, require_linguistic_units


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "sha256": "a" * 64,
            "frame_count": 90,
            "fps": {"numerator": 30000, "denominator": 1001},
        }
        self.units = [{
            "id": "unit-a", "source_sha256": "a" * 64,
            "start_frame": 0, "end_frame": 30, "eligible": True,
        }]
        self.review = {
            "unit_id": "unit-a", "source_sha256": "a" * 64,
            "start_frame": 0, "end_frame": 30, "disposition": "verified",
            "evidence": {
                aspect: {"method": "listened", "reviewer": "synthetic-reviewer",
                         "evidence_id": f"synthetic-fixture:{aspect}"}
                for aspect in ("words", "speaker", "boundaries")
            },
        }
        self.document = {
            "schema_version": "1.0", "source": deepcopy(self.source),
            "intervals": [
                {"id": "first", "start_frame": 0, "end_frame": 30,
                 "disposition": "verified"},
                {"id": "remaining", "start_frame": 30, "end_frame": 90,
                 "disposition": "pending"},
            ],
            "unit_reviews": [deepcopy(self.review)],
        }

    def audit(self, document=None, units=None, source=None):
        return audit_qualification(
            self.document if document is None else document,
            source=self.source if source is None else source,
            units=self.units if units is None else units,
        )

    def test_qualified_subset_and_coverage_preserve_inputs(self):
        before = deepcopy((self.document, self.units, self.source))
        result = self.audit()
        self.assertEqual(result["qualified_unit_ids"], ["unit-a"])
        self.assertEqual(result["excluded_units"], [])
        self.assertEqual(result["coverage"]["frames_by_disposition"]["verified"], 30)
        self.assertEqual(result["coverage"]["frames_by_disposition"]["pending"], 60)
        self.assertEqual((self.document, self.units, self.source), before)
        self.assertEqual(require_linguistic_units(
            self.document, source=self.source, units=self.units), ["unit-a"])

    def test_legacy_eligible_flag_never_qualifies_a_unit(self):
        self.document["unit_reviews"] = []
        self.assertEqual(self.audit()["qualified_unit_ids"], [])
        self.assertIn("no_review", self.audit()["excluded_units"][0]["reasons"])
        with self.assertRaisesRegex(ValueError, "No source units"):
            require_linguistic_units(self.document, source=self.source, units=self.units)

    def test_nonverified_unit_dispositions_remain_excluded(self):
        for status in ("pending", "uncertain", "texture_only", "non_speech"):
            with self.subTest(status=status):
                self.document["unit_reviews"][0]["disposition"] = status
                self.assertEqual(self.audit()["qualified_unit_ids"], [])

    def test_all_overlapped_intervals_must_be_verified(self):
        self.units[0]["end_frame"] = 31
        self.document["unit_reviews"][0]["end_frame"] = 31
        for status in ("pending", "uncertain", "texture_only", "non_speech"):
            with self.subTest(status=status):
                self.document["intervals"][1]["disposition"] = status
                self.assertEqual(self.audit()["qualified_unit_ids"], [])
        self.document["intervals"][1]["disposition"] = "verified"
        self.assertEqual(self.audit()["qualified_unit_ids"], ["unit-a"])

    def test_each_listened_evidence_aspect_is_required(self):
        for aspect in ("words", "speaker", "boundaries"):
            with self.subTest(aspect=aspect):
                doc = deepcopy(self.document)
                del doc["unit_reviews"][0]["evidence"][aspect]
                with self.assertRaisesRegex(ValueError, "requires listened evidence"):
                    self.audit(doc)

    def test_evidence_requires_listening_and_nonempty_provenance(self):
        changes = [
            ("method", "automatic"), ("method", True),
            ("reviewer", ""), ("reviewer", "   "), ("reviewer", None),
            ("evidence_id", ""), ("evidence_id", True),
        ]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                doc = deepcopy(self.document)
                doc["unit_reviews"][0]["evidence"]["words"][field] = value
                with self.assertRaises(ValueError):
                    self.audit(doc)

    def test_pending_partial_evidence_is_retained_without_admission(self):
        review = self.document["unit_reviews"][0]
        review["disposition"] = "pending"
        del review["evidence"]["speaker"]
        self.assertEqual(self.audit()["qualified_unit_ids"], [])

    def test_gap_overlap_missing_final_tail_and_empty_coverage_rejected(self):
        variants = [
            [],
            [{"id": "one", "start_frame": 0, "end_frame": 89, "disposition": "pending"}],
            [{"id": "one", "start_frame": 1, "end_frame": 90, "disposition": "pending"}],
        ]
        for start in (29, 31):
            intervals = deepcopy(self.document["intervals"])
            intervals[1]["start_frame"] = start
            variants.append(intervals)
        for intervals in variants:
            with self.subTest(intervals=intervals):
                doc = deepcopy(self.document)
                doc["intervals"] = intervals
                with self.assertRaisesRegex(ValueError, "every frame"):
                    self.audit(doc)

    def test_partition_order_has_no_semantic_effect(self):
        self.document["intervals"].reverse()
        self.assertEqual(self.audit()["qualified_unit_ids"], ["unit-a"])

    def test_review_bounds_cannot_follow_rebound_units_silently(self):
        for field, value in (("start_frame", 1), ("end_frame", 29)):
            with self.subTest(field=field):
                units = deepcopy(self.units)
                units[0][field] = value
                with self.assertRaisesRegex(ValueError, "stale unit bounds"):
                    self.audit(units=units)

    def test_source_hash_frame_count_and_timebase_must_match(self):
        for field, value in (
            ("sha256", "b" * 64), ("frame_count", 91),
            ("fps", {"numerator": 30, "denominator": 1}),
        ):
            with self.subTest(field=field):
                doc = deepcopy(self.document)
                doc["source"][field] = value
                with self.assertRaisesRegex(ValueError, "identity or timebase is stale"):
                    self.audit(doc)

    def test_equivalent_rational_timebase_is_accepted_and_reduced(self):
        self.document["source"]["fps"] = {"numerator": 60000, "denominator": 2002}
        self.assertEqual(self.audit()["source"]["fps"], self.source["fps"])

    def test_unit_and_review_source_hashes_are_bound_separately(self):
        for target in ("unit", "review"):
            with self.subTest(target=target):
                units = deepcopy(self.units)
                doc = deepcopy(self.document)
                record = units[0] if target == "unit" else doc["unit_reviews"][0]
                record["source_sha256"] = "b" * 64
                with self.assertRaisesRegex(ValueError, "different source"):
                    self.audit(doc, units=units)

    def test_duplicate_interval_unit_and_review_ids_rejected(self):
        doc = deepcopy(self.document)
        doc["intervals"][1]["id"] = "first"
        with self.assertRaisesRegex(ValueError, "Duplicate interval"):
            self.audit(doc)
        with self.assertRaisesRegex(ValueError, "Duplicate unit id"):
            self.audit(units=self.units * 2)
        doc = deepcopy(self.document)
        doc["unit_reviews"] *= 2
        with self.assertRaisesRegex(ValueError, "Duplicate unit review"):
            self.audit(doc)

    def test_unknown_or_renamed_unit_review_rejected(self):
        self.document["unit_reviews"][0]["unit_id"] = "old-id"
        with self.assertRaisesRegex(ValueError, "unknown unit"):
            self.audit()

    def test_bool_float_nonfinite_and_negative_frame_fields_rejected(self):
        for value in (True, False, 1.0, float("nan"), float("inf"), -1, "0"):
            for collection, key in (("intervals", "start_frame"), ("unit_reviews", "end_frame")):
                with self.subTest(value=value, collection=collection):
                    doc = deepcopy(self.document)
                    doc[collection][0][key] = value
                    with self.assertRaises(ValueError):
                        self.audit(doc)
            with self.subTest(value=value, collection="units"):
                units = deepcopy(self.units)
                units[0]["start_frame"] = value
                with self.assertRaises(ValueError):
                    self.audit(units=units)

    def test_source_integer_fields_reject_invalid_json_numbers(self):
        for value in (True, False, 0, -1, 30.0, float("nan"), float("inf"), "30"):
            for field in ("frame_count", "numerator", "denominator"):
                with self.subTest(value=value, field=field):
                    source = deepcopy(self.source)
                    target = source if field == "frame_count" else source["fps"]
                    target[field] = value
                    with self.assertRaises(ValueError):
                        self.audit(source=source)

    def test_empty_reversed_and_outside_bounds_rejected(self):
        for start, end in ((10, 10), (20, 10), (0, 91)):
            with self.subTest(start=start, end=end):
                units = deepcopy(self.units)
                units[0].update(start_frame=start, end_frame=end)
                with self.assertRaisesRegex(ValueError, "bounds"):
                    self.audit(units=units)

    def test_malformed_schema_types_hashes_and_dispositions_rejected(self):
        for field, value in (("schema_version", 1.0), ("intervals", {}),
                             ("unit_reviews", None), ("source", [])):
            with self.subTest(field=field):
                doc = deepcopy(self.document)
                doc[field] = value
                with self.assertRaises(ValueError):
                    self.audit(doc)
        for value in ("", "a" * 63, "A" * 64, "g" * 64, True):
            with self.subTest(sha=value):
                source = deepcopy(self.source)
                source["sha256"] = value
                with self.assertRaises(ValueError):
                    self.audit(source=source)
        for collection in ("intervals", "unit_reviews"):
            doc = deepcopy(self.document)
            doc[collection][0]["disposition"] = "eligible"
            with self.assertRaisesRegex(ValueError, "recognized disposition"):
                self.audit(doc)


if __name__ == "__main__":
    unittest.main()
