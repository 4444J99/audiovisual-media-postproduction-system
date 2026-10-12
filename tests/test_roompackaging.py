"""Regression checks for truncated FLACs that an encoder exit did not catch."""
import json
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

from amp.audio import RATE, save_audio
from amp.core import sha256
from tools import package_room_refinement as packaging


class RoomPackagingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="roompackaging-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source.wav"
        self.samples = np.random.default_rng(6971).normal(0, .003, (RATE, 2)).astype(np.float32)
        save_audio(self.source, self.samples)

    def test_valid_flac_fully_decodes_to_exact_source_duration(self):
        target = self.root / "valid.flac"
        receipt = packaging.encode(self.source, target, "flac")
        self.assertEqual(receipt["source_samples"], RATE)
        self.assertEqual(receipt["decoded_samples"], RATE)
        self.assertEqual(receipt["tail_padding_samples"], 0)
        self.assertTrue(receipt["full_decode_verified"])
        self.assertEqual(packaging.validate_encoded(target, RATE, "flac"), receipt)

    def test_truncated_flac_is_rejected_even_with_a_zero_decoder_exit(self):
        target = self.root / "truncated.flac"
        packaging.encode(self.source, target, "flac")
        contents = target.read_bytes()
        target.write_bytes(contents[:len(contents) // 2])
        decoded = subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-i", str(target),
             "-vn", "-ar", str(RATE), "-ac", "2", "-f", "f32le", "-"],
            capture_output=True,
        )
        # The fixture actually loses decoded samples; no invented corrupt payload.
        self.assertLess(len(decoded.stdout), RATE * 2 * 4)
        with self.assertRaises((ValueError, subprocess.CalledProcessError)):
            packaging.validate_encoded(target, RATE, "flac")
        # Explicitly exercise the observed failure mode even if a future FFmpeg
        # version changes its return code for this damaged stream.
        success_exit = subprocess.CompletedProcess(decoded.args, 0, decoded.stdout, decoded.stderr)
        with mock.patch.object(packaging.subprocess, "run", return_value=success_exit):
            with self.assertRaisesRegex(ValueError, "full decode|truncated or invalid"):
                packaging.validate_encoded(target, RATE, "flac")

    def test_short_decode_without_a_warning_still_fails_exact_flac_length(self):
        target = self.root / "short.flac"
        packaging.encode(self.source, target, "flac")
        decoded = subprocess.CompletedProcess([], 0, self.samples[:-1].astype("<f4").tobytes(), b"")
        with mock.patch.object(packaging.subprocess, "run", return_value=decoded):
            with self.assertRaisesRegex(ValueError, "truncated or invalid"):
                packaging.validate_encoded(target, RATE, "flac")

    def test_failed_staged_validation_preserves_existing_valid_target(self):
        target = self.root / "published.flac"
        packaging.encode(self.source, target, "flac")
        original = target.read_bytes()
        original_hash = sha256(target)
        alternate = self.root / "alternate.wav"
        save_audio(alternate, self.samples * .25)
        with mock.patch.object(packaging, "validate_encoded", side_effect=ValueError("Rejected staged output")):
            with self.assertRaisesRegex(ValueError, "Rejected staged output"):
                packaging.encode(alternate, target, "flac")
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(sha256(target), original_hash)
        self.assertTrue(packaging.validate_encoded(target, RATE, "flac")["full_decode_verified"])
        self.assertFalse(list(self.root.glob(".room-encode-*")))

    def test_copied_stem_rejects_missing_tail_and_preserves_existing_target(self):
        source = self.root / "original.flac"
        target = self.root / "retained.flac"
        packaging.encode(self.source, source, "flac")
        packaging.copy_verified_flac(source, target, RATE)
        original = target.read_bytes()
        # A valid shorter file still cannot stand in for a full-length stem.
        with self.assertRaisesRegex(ValueError, "truncated or invalid"):
            packaging.copy_verified_flac(source, target, 2 * RATE)
        self.assertEqual(target.read_bytes(), original)
        self.assertFalse(list(self.root.glob(".room-copy-*")))

    def test_expected_full_length_mismatch_preserves_existing_encoded_target(self):
        target = self.root / "full-length.flac"
        packaging.encode(self.source, target, "flac")
        original = target.read_bytes()
        with self.assertRaisesRegex(ValueError, "wrong full-length sample count"):
            packaging.encode(self.source, target, "flac", expected_samples=2 * RATE)
        self.assertEqual(target.read_bytes(), original)
        self.assertFalse(list(self.root.glob(".room-encode-*")))

    def test_copied_stem_rejects_nonfinite_complete_decode(self):
        source = self.root / "original.flac"
        packaging.encode(self.source, source, "flac")
        invalid = self.samples.copy()
        invalid[-1, 0] = np.nan
        decoded = subprocess.CompletedProcess([], 0, invalid.astype("<f4").tobytes(), b"")
        target = self.root / "retained.flac"
        with mock.patch.object(packaging.subprocess, "run", return_value=decoded):
            with self.assertRaisesRegex(ValueError, "truncated or invalid"):
                packaging.copy_verified_flac(source, target, RATE)
        self.assertFalse(target.exists())

    def test_export_records_transcoded_core_identity_and_validates_retained_stems(self):
        refinement, audit, baseline, output = [self.root / name for name in
                                              ("refinement", "audit", "baseline", "output")]
        for path in (refinement, audit, baseline, output):
            path.mkdir()
        source_stem = refinement / "stem.wav"
        source_stem.write_bytes(self.source.read_bytes())
        item = {"filename": "stem.wav", "sha256": sha256(source_stem)}
        report = {"candidates": {key: {"stems": {band: item for band in ("low", "mid", "high")}}
                                 for key in ("B", "C", "D", "E")}}
        (refinement / "room-refinement-report.json").write_text(json.dumps(report))
        (audit / "portion-review.json").write_text(json.dumps({"files": [], "portions": []}))
        (baseline / "room-rack-report.json").write_text("{}")
        stem = baseline / "low-dry-contribution.flac"
        packaging.encode(self.source, stem, "flac")
        for band in ("low", "mid", "high"):
            for kind in ("dry-contribution", "fx-return"):
                (baseline / f"{band}-{kind}.flac").write_bytes(stem.read_bytes())
        receipt = packaging.export_edit_assets(refinement, audit, baseline, self.source, output, RATE)
        self.assertEqual(receipt["dialogue_source_sha256"], sha256(self.source))
        self.assertEqual(receipt["dialogue_file_sha256"], sha256(output / "full-length/dialogue-core.flac"))
        self.assertNotEqual(receipt["dialogue_file_sha256"], receipt["dialogue_source_sha256"])
        self.assertEqual(len(receipt["editable_audio_verification"]), 19)
        for audio_receipt in receipt["editable_audio_verification"].values():
            self.assertTrue(audio_receipt["full_decode_verified"])
            self.assertEqual(audio_receipt["decoded_samples"], RATE)

    def test_audit_export_omits_unlisted_private_and_stale_files(self):
        audit, target = self.root / "audit", self.root / "delivery/source-pause-review"
        audit.mkdir()
        (audit / "review.wav").write_bytes(self.source.read_bytes())
        (audit / "private-notes.txt").write_text("Private material unrelated to the audit")
        (audit / "external-link").symlink_to(self.source)
        report = {"files": [{"path": "review.wav", "sha256": sha256(audit / "review.wav")}], "portions": []}
        (audit / "portion-review.json").write_text(json.dumps(report))
        target.mkdir(parents=True)
        (target / "old-private.txt").write_text("Unlisted artifact from an earlier copy")
        packaging.copy_audit_artifacts(audit, target, sha256(audit / "portion-review.json"))
        self.assertEqual({p.name for p in target.iterdir()}, {"review.wav", "portion-review.json"})
        self.assertEqual(sha256(target / "review.wav"), report["files"][0]["sha256"])
        self.assertFalse(list(target.parent.glob(".room-audit-*")))

    def test_tampered_listed_audit_file_is_rejected_without_replacing_export(self):
        audit, target = self.root / "audit", self.root / "export"
        audit.mkdir()
        (audit / "review.wav").write_bytes(self.source.read_bytes())
        report = {"files": [{"path": "review.wav", "sha256": sha256(audit / "review.wav")}], "portions": []}
        (audit / "portion-review.json").write_text(json.dumps(report))
        packaging.copy_audit_artifacts(audit, target)
        original = (target / "review.wav").read_bytes()
        (audit / "review.wav").write_bytes(b"replacement payload")
        with self.assertRaisesRegex(ValueError, "Audit artifact changed"):
            packaging.copy_audit_artifacts(audit, target)
        self.assertEqual((target / "review.wav").read_bytes(), original)

    def test_audit_receipts_cannot_traverse_or_follow_symlinks(self):
        audit = self.root / "audit"
        audit.mkdir()
        (audit / "link.wav").symlink_to(self.source)
        (audit / "linked-directory").symlink_to(self.root, target_is_directory=True)
        for relative in ("../source.wav", str(self.source), "link.wav", "linked-directory/source.wav"):
            with self.subTest(relative=relative):
                report = {"files": [{"path": relative, "sha256": sha256(self.source)}], "portions": []}
                (audit / "portion-review.json").write_text(json.dumps(report))
                with self.assertRaisesRegex(ValueError, "Unsafe|symlink|escaping"):
                    packaging.copy_audit_artifacts(audit, self.root / "export")
                self.assertFalse((self.root / "export").exists())

    def test_changed_audit_report_and_unlisted_pause_reference_are_rejected(self):
        audit = self.root / "audit"
        audit.mkdir()
        report_path = audit / "portion-review.json"
        report_path.write_text(json.dumps({"files": [], "portions": []}))
        report_hash = sha256(report_path)
        report = {"files": [], "portions": [{"review_audio": {"path": "private.wav", "sha256": "0" * 64}}]}
        report_path.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, "Audit report changed"):
            packaging.copy_audit_artifacts(audit, self.root / "export", report_hash)
        with self.assertRaisesRegex(ValueError, "lacks a matching audit receipt"):
            packaging.copy_audit_artifacts(audit, self.root / "export")

    def test_shared_gain_bounds_coincident_stem_peaks(self):
        # Sparse coincident transients have enough crest factor for headroom,
        # rather than the -24 LUFS listening target, to determine the gain.
        layer = np.zeros((RATE, 2), dtype=np.float32)
        layer[100:148] = .25
        stems = {str(i): layer for i in range(6)}
        summed = sum(stems.values())
        gain = packaging.shared_stem_gain(stems, summed)
        measured = packaging.measure(summed * 10 ** (gain / 20))
        self.assertLessEqual(measured["input_tp"], -1.49)
        old_gain = min(-24 - packaging.measure(summed)["input_i"],
                       -1.5 - packaging.measure(layer)["input_tp"])
        self.assertGreater(old_gain, gain + 1)

    def test_poster_falls_back_when_dejavu_is_unavailable(self):
        truetype = packaging.ImageFont.truetype

        def missing_dejavu(name, *args, **kwargs):
            if isinstance(name, str) and name.startswith("DejaVuSans"):
                raise OSError("DejaVu is not installed")
            return truetype(name, *args, **kwargs)

        output = self.root / "poster.png"
        with mock.patch.object(packaging.ImageFont, "truetype", side_effect=missing_dejavu):
            packaging.poster(output, Image.new("RGB", (640, 360)), "A", "Existing room rack",
                             "Recorded room tone", "ROOM ONLY", "00:28-00:40")
        with Image.open(output) as rendered:
            self.assertEqual(rendered.size, (1280, 720))

    def test_source_identity_mismatch_is_rejected_before_render_lookup(self):
        refinement, audit, baseline = [self.root / name for name in ("refinement", "audit", "baseline")]
        for directory, name in ((refinement, "room-refinement-report.json"),
                                (audit, "portion-review.json"),
                                (baseline, "room-rack-report.json")):
            directory.mkdir()
            (directory / name).write_text(json.dumps({"source_sha256": "0" * 64}))
        with self.assertRaisesRegex(ValueError, "another source"):
            packaging.validate_inputs(self.source, refinement, audit, baseline, self.source)

    def test_archive_is_verified_before_replacing_existing_delivery(self):
        output = self.root / "delivery"
        output.mkdir()
        (output / "notes.md").write_text("Verified comparison notes")
        (output / "working").mkdir()
        (output / "working" / "intermediate.wav").write_bytes(b"working material")
        (output / ".room-encode-interrupted").mkdir()
        (output / ".room-encode-interrupted" / "partial.flac").write_bytes(b"staged material")
        target = packaging.archive_delivery(output)
        original = target.read_bytes()
        original_manifest = (output / "delivery-manifest.json").read_bytes()
        with zipfile.ZipFile(target) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(set(archive.namelist()), {"notes.md", "delivery-manifest.json"})
        (output / "notes.md").write_text("New notes awaiting archive validation")
        with mock.patch.object(zipfile.ZipFile, "testzip", return_value="notes.md"):
            with self.assertRaisesRegex(ValueError, "Archive member failed validation"):
                packaging.archive_delivery(output)
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual((output / "delivery-manifest.json").read_bytes(), original_manifest)
        self.assertFalse(list(self.root.glob(".room-package-*")))

    def test_failed_first_archive_does_not_publish_a_manifest(self):
        output = self.root / "delivery"
        output.mkdir()
        (output / "notes.md").write_text("Unverified comparison notes")
        with mock.patch.object(zipfile.ZipFile, "testzip", return_value="notes.md"):
            with self.assertRaisesRegex(ValueError, "Archive member failed validation"):
                packaging.archive_delivery(output)
        self.assertFalse((output / "delivery-manifest.json").exists())
        self.assertFalse((output / "god-here-room-tone-processing-comparisons.zip").exists())


if __name__ == "__main__":
    unittest.main()
