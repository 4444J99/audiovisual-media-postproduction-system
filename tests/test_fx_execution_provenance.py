"""Execution receipts bind the asset identity implementation they consume."""
from pathlib import Path
import tempfile
import unittest

from amp.execution import code_provenance


class FxExecutionProvenanceTests(unittest.TestCase):
    def test_changed_asset_pack_changes_execution_code_identity(self):
        root = Path(__file__).resolve().parents[1]
        original = code_provenance(root, "fx.rack.v1")
        original_files = {item["path"]: item for item in original["files"]}
        target = "web/fx/asset-pack.mjs"
        self.assertIn(target, original_files)
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory)
            for name in original_files:
                destination = copied / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((root / name).read_bytes())
            before = {item["path"]: item for item in code_provenance(copied, "fx.rack.v1")["files"]}
            self.assertEqual(before, original_files)
            with (copied / target).open("a", encoding="utf-8") as stream:
                stream.write("\n// Changed asset identity implementation.\n")
            after = {item["path"]: item for item in code_provenance(copied, "fx.rack.v1")["files"]}
            self.assertNotEqual(after[target]["sha256"], before[target]["sha256"])
            for name in original_files:
                if name != target:
                    self.assertEqual(after[name], before[name])
