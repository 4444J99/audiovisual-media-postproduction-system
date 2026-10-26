import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from amp.composition.novelty import canonical_identity
from amp.composition.performance_cli import retained_engine_identity
from tests.composition.fixtures import corpus, profile

ROOT = Path(__file__).resolve().parents[2]


class PerformanceCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "composition"
        self.project.mkdir()
        (self.project / "composition.json").write_text(json.dumps({"composition_id": "synthetic-composition"}))
        data = corpus()
        data["engine_sha256"] = retained_engine_identity()
        self.corpus = self.root / "corpus.json"
        self.corpus.write_text(json.dumps(data))
        self.profile = self.root / "profile.json"
        self.profile.write_text(json.dumps(profile()))
        self.history = self.root / "history.sqlite3"

    def cli(self, *arguments):
        return subprocess.run([sys.executable, "-m", "amp.cli", "performance", "--composition", str(self.project),
                               *map(str, arguments)], cwd=ROOT, capture_output=True, text=True, timeout=20)

    def new(self, output, *arguments):
        return self.cli("--operation", "new", "--corpus", self.corpus, "--profile", self.profile,
                        "--history", self.history, "--duration-frames", 120, "--seed", 11,
                        "--output", output, *arguments)

    def test_new_reserves_then_replay_intentionally_reproduces_the_record(self):
        first, second = self.root / "first.json", self.root / "second.json"
        created = self.new(first)
        self.assertEqual(created.returncode, 0, created.stderr + created.stdout)
        receipt = json.loads(created.stdout)
        self.assertEqual(receipt["status"], "planned")
        self.assertFalse(receipt["prepared_media_verified"])
        self.assertTrue(receipt["engine_identity_verified"])
        saved = json.loads(first.read_text())
        self.assertEqual(receipt["identity"], canonical_identity(saved))
        self.assertEqual(first.stat().st_mode & 0o077, 0)
        duplicate = self.new(second)
        self.assertEqual(duplicate.returncode, 2)
        self.assertEqual(json.loads(duplicate.stdout)["error"]["code"], "duplicate-performance")
        self.assertFalse(second.exists())
        replay = self.cli("--operation", "replay", "--session", first, "--output", second)
        self.assertEqual(replay.returncode, 0, replay.stdout + replay.stderr)
        self.assertFalse(json.loads(replay.stdout)["new_decisions_resolved"])
        self.assertEqual(json.loads(second.read_text()), saved)
        inspected = self.cli("--operation", "inspect", "--session", second)
        self.assertEqual(inspected.returncode, 0)
        self.assertEqual(json.loads(inspected.stdout)["identity"], receipt["identity"])

    def test_existing_outputs_and_source_history_aliases_are_not_overwritten(self):
        existing = self.root / "existing.json"
        existing.write_bytes(b"keep this exact artifact")
        result = self.new(existing)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(existing.read_bytes(), b"keep this exact artifact")
        self.assertFalse(self.history.exists())
        source_bytes = self.corpus.read_bytes()
        self.history.hardlink_to(self.corpus)
        result = self.new(self.root / "output.json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.corpus.read_bytes(), source_bytes)

    def test_engine_mismatch_and_private_errors_do_not_create_history_or_leak_paths(self):
        data = json.loads(self.corpus.read_text())
        data["engine_sha256"] = "f" * 64
        self.corpus.write_text(json.dumps(data))
        result = self.new(self.root / "output.json")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(str(self.root), result.stdout)
        self.assertFalse(self.history.exists())
        missing = self.cli("--operation", "inspect", "--session", self.root / "private-missing.json")
        self.assertEqual(missing.returncode, 2)
        self.assertNotIn("private-missing", missing.stdout)
        self.assertNotIn("Traceback", missing.stderr)

    def test_dry_run_and_inspection_are_explicit_and_do_not_reserve(self):
        result = self.cli("--operation", "new", "--corpus", self.corpus, "--profile", self.profile,
                          "--duration-frames", 120, "--seed", 12, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "planned")
        self.assertFalse(self.history.exists())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["composition", "corpus.json", "profile.json"])

    def test_new_requires_explicit_duration_and_protects_record_from_inspect_output(self):
        missing = self.cli("--operation", "new", "--corpus", self.corpus, "--profile", self.profile,
                           "--history", self.history, "--output", self.root / "new.json")
        self.assertEqual(missing.returncode, 2)
        self.assertFalse(self.history.exists())
        saved = self.root / "new.json"
        self.assertEqual(self.new(saved).returncode, 0)
        before = saved.read_bytes()
        result = self.cli("--operation", "inspect", "--session", saved, "--output", saved)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(saved.read_bytes(), before)

    def test_a_profile_flag_does_not_claim_actual_playback_admission(self):
        settings = profile()
        settings.update(admitted=True, byte_caps={
            "decoded_audio_bytes": 10000000, "texture_bytes": 10000000, "event_history_bytes": 10000000,
        })
        self.profile.write_text(json.dumps(settings))
        result = self.new(self.root / "not-played.json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        receipt = json.loads(result.stdout)
        self.assertFalse(receipt["playback_admitted"])
        self.assertTrue(receipt["profile_admitted"])


if __name__ == "__main__":
    unittest.main()
