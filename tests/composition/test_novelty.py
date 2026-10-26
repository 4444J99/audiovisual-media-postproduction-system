import copy
import gc
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
import warnings

from amp.composition import PerformanceRecord, SourceSpan, Timebase
from amp.composition.novelty import DuplicatePerformance, PerformanceHistory, canonical_identity
from tests.composition.fixtures import record, runtime


class PerformanceNoveltyTests(unittest.TestCase):
    def test_seed_labels_orientation_and_metadata_cannot_disguise_duplicate(self):
        original = record().to_dict()
        renamed = copy.deepcopy(original)
        renamed["record_id"] = "another-id"
        renamed["timestamp"] = "2026-10-26T00:00:00Z"
        renamed["provenance"] = {"orientation": "portrait"}
        renamed["runtime"]["seed"] = 99
        renamed["runtime"]["events"][0]["id"] = "renamed-parent"
        renamed["runtime"]["events"][1].update(id="renamed-shot", parent_id="renamed-parent")
        renamed["runtime"]["materials"][0]["id"] = "renamed-material"
        renamed["runtime"]["reference"]["material_id"] = "renamed-material"
        renamed["runtime"]["fallback_material_id"] = "renamed-material"
        renamed["runtime"]["events"][1]["material_id"] = "renamed-material"
        self.assertEqual(canonical_identity(original), canonical_identity(renamed))

    def test_actual_clock_or_material_changes_change_identity(self):
        original = record().to_dict()
        changed = copy.deepcopy(original)
        changed["runtime"]["events"][1]["picture_clock"]["start_frame"] += 1
        self.assertNotEqual(canonical_identity(original), canonical_identity(changed))
        changed = copy.deepcopy(original)
        changed["runtime"]["materials"][0]["sha256"] = "e" * 64
        self.assertNotEqual(canonical_identity(original), canonical_identity(changed))

    def test_history_reserves_atomically_and_replays_complete_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.sqlite3"
            saved = record()
            def reserve(_):
                try:
                    return PerformanceHistory(path).reserve(saved)
                except DuplicatePerformance:
                    return None
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(reserve, range(2)))
            identities = [value for value in results if value is not None]
            self.assertEqual(len(identities), 1)
            self.assertEqual(PerformanceHistory(path).load(identities[0]).to_dict(), saved.to_dict())
            with self.assertRaises(DuplicatePerformance):
                PerformanceHistory(path).reserve(record("different-label"))

    def test_runtime_roundtrip_preserves_decisions_and_copies_input(self):
        data = runtime()
        saved = PerformanceRecord(record_id="saved", composition_id="synthetic-composition",
                                  span=SourceSpan(0, 180), timebase=Timebase(30), runtime=data)
        data["events"][1]["gain"] = 0.99
        self.assertEqual(saved.to_dict()["runtime"]["events"][1]["gain"], 0.5)
        self.assertEqual(PerformanceRecord.from_dict(saved.to_dict()).to_dict(), saved.to_dict())
        legacy = PerformanceRecord("legacy", "composition", SourceSpan(0, 30), Timebase(30))
        self.assertNotIn("runtime", legacy.to_dict())

    def test_malformed_graphs_and_nonfinite_records_cannot_be_reserved(self):
        original = record().to_dict()
        for mutate in (
            lambda r: r["runtime"]["events"][1].update(parent_id="absent"),
            lambda r: r["runtime"]["events"][1].update(material_id="absent"),
            lambda r: r["runtime"]["events"][1].update(gain=float("nan")),
            lambda r: r["runtime"]["events"][1].update(id="edition"),
            lambda r: r["runtime"]["events"][1].update(start_frame=-1),
            lambda r: r["runtime"]["events"][1].update(parent_id="shot"),
        ):
            changed = copy.deepcopy(original)
            mutate(changed)
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    canonical_identity(changed)

    def test_unavailable_or_corrupt_history_is_not_silently_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.sqlite3"
            path.write_bytes(b"not a database")
            path.chmod(0o600)
            with warnings.catch_warnings(record=True) as emitted:
                warnings.simplefilter("always", ResourceWarning)
                with self.assertRaises(sqlite3.DatabaseError):
                    PerformanceHistory(path).reserve(record())
                gc.collect()
            self.assertFalse([warning for warning in emitted if warning.category is ResourceWarning])
            self.assertEqual(path.read_bytes(), b"not a database")

    def test_history_rejects_tampered_decisions_without_repairing_them(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "history.sqlite3"
            history = PerformanceHistory(path)
            identity = history.reserve(record())
            connection = sqlite3.connect(path)
            changed = record().to_dict()
            changed["runtime"]["events"][1]["gain"] = 0.9
            connection.execute("UPDATE performances SET record_json = ?", (json.dumps(changed),))
            connection.commit()
            connection.close()
            with self.assertRaisesRegex(ValueError, "canonical identity"):
                history.load(identity)

    def test_replay_cannot_create_an_empty_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "absent.sqlite3"
            with self.assertRaises(FileNotFoundError):
                PerformanceHistory(path).load(canonical_identity(record()))
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
