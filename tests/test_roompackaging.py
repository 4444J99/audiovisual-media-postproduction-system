"""Regression checks for truncated FLACs that an encoder exit did not catch."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

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

    def test_source_identity_mismatch_is_rejected_before_render_lookup(self):
        refinement, audit, baseline = [self.root / name for name in ("refinement", "audit", "baseline")]
        for directory, name in ((refinement, "room-refinement-report.json"),
                                (audit, "portion-review.json"),
                                (baseline, "room-rack-report.json")):
            directory.mkdir()
            (directory / name).write_text(json.dumps({"source_sha256": "0" * 64}))
        with self.assertRaisesRegex(ValueError, "another source"):
            packaging.validate_inputs(self.source, refinement, audit, baseline, self.source)


if __name__ == "__main__":
    unittest.main()
