"""Source-bound resumable audio must survive neither stale nor damaged caches."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from amp.audio import RATE, load_audio, save_audio
from amp.core import sha256, write_json
from tools import build_directed_proof as directed


class DirectedAudioCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="directed-audio-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.audio = self.root / "audio"
        self.source = self.root / "source.wav"
        self.samples = np.random.default_rng(113).normal(0, .003, (4800, 2)).astype(np.float32)
        save_audio(self.source, self.samples)
        self.config = {"source_sha256": sha256(self.source), "performers": {"P01": {}, "P02": {}}, "cues": []}
        self.transcript = {"segments": [{"start": 0, "end": .1}]}
        # Isolate the tests from parallel edits to the tool while preserving the
        # production helper's explicit producing-code comparison.
        self.producer = mock.patch.object(directed, "_audio_producer", return_value={"amp/audio.py": "a" * 64})
        self.producer_mock = self.producer.start()
        self.addCleanup(self.producer.stop)
        self.candidates = mock.patch.object(directed, "make_candidates", side_effect=self.make_candidates).start()
        self.expressive = mock.patch.object(directed, "expressive_audio", side_effect=self.make_expressive).start()
        self.addCleanup(mock.patch.stopall)

    def make_candidates(self, source, transcript, out):
        out = Path(out)
        samples = load_audio(source)
        report = {"source_sha256": sha256(source), "sample_rate": RATE, "candidates": {}}
        for name, gain in (("A", 1), ("B", .8)):
            path = out / f"candidate-{name}.wav"
            save_audio(path, samples * gain)
            report["candidates"][name] = {"sha256": sha256(path), "samples": len(samples)}
        write_json(out / "audio-report.json", report)

    def make_expressive(self, clean, config, out):
        samples = load_audio(clean)
        total = np.zeros_like(samples)
        for pid in config["performers"]:
            bus = samples * .1
            total += bus
            save_audio(Path(out) / f"return-{pid}.wav", bus)
        save_audio(Path(out) / "expressive-returns.wav", total)
        save_audio(Path(out) / "expressive-mix.wav", samples + total)
        write_json(Path(out) / "expressive-report.json", {"global_trim_db": 0, "listening_acceptance": "pending"})

    def prepare(self, config=None, transcript=None):
        return directed.prepare_audio(self.source, transcript or self.transcript, config or self.config, self.audio)

    def verify(self, config=None):
        return directed.verify_audio_cache(self.audio, config or self.config, self.transcript,
                                           sha256(self.source), len(self.samples))

    def reset_calls(self):
        self.candidates.reset_mock()
        self.expressive.reset_mock()

    def test_valid_complete_cache_is_authenticated_and_reused(self):
        receipt = self.prepare()
        self.assertEqual(receipt["source_audio"]["samples"], len(self.samples))
        verified = self.verify()
        self.assertEqual(verified["candidates"]["preparation_inputs"]["source_sha256"], sha256(self.source))
        self.assertEqual(len(verified["expressive"]["audio_assets"]), 4)
        self.reset_calls()
        self.prepare()
        self.candidates.assert_not_called()
        self.expressive.assert_not_called()

    def test_missing_expressive_mix_rebuilds_only_expressive_stage(self):
        self.prepare()
        (self.audio / "expressive-mix.wav").unlink()
        self.reset_calls()
        self.prepare()
        self.candidates.assert_not_called()
        self.expressive.assert_called_once()
        self.verify()

    def test_stale_same_length_candidate_rebuilds_both_stages(self):
        self.prepare()
        save_audio(self.audio / "candidate-B.wav", self.samples * .2)
        with self.assertRaisesRegex(ValueError, "changed after its receipt"):
            self.verify()
        self.reset_calls()
        self.prepare()
        self.candidates.assert_called_once()
        self.expressive.assert_called_once()
        self.verify()

    def test_truncated_candidate_is_rejected_even_with_updated_file_hash(self):
        self.prepare()
        path = self.audio / "candidate-A.wav"
        save_audio(path, self.samples[:-1])
        report_path = self.audio / "audio-report.json"
        report = json.loads(report_path.read_text())
        report["candidates"]["A"]["sha256"] = sha256(path)
        report["audio_assets"][path.name]["sha256"] = sha256(path)
        write_json(report_path, report)
        with self.assertRaisesRegex(ValueError, "wrong decoded sample count"):
            self.verify()
        self.reset_calls()
        self.prepare()
        self.candidates.assert_called_once()
        self.expressive.assert_called_once()
        self.verify()

    def test_nonfinite_performer_return_is_rejected_even_with_updated_hash(self):
        self.prepare()
        path = self.audio / "return-P01.wav"
        samples = self.samples.copy()
        samples[-1, 1] = np.nan
        save_audio(path, samples)
        report_path = self.audio / "expressive-report.json"
        report = json.loads(report_path.read_text())
        report["audio_assets"][path.name]["sha256"] = sha256(path)
        write_json(report_path, report)
        with self.assertRaisesRegex(ValueError, "nonfinite samples"):
            self.verify()
        self.reset_calls()
        self.prepare()
        self.candidates.assert_not_called()
        self.expressive.assert_called_once()
        self.verify()

    def test_config_change_rebuilds_expressive_audio_only(self):
        self.prepare()
        config = copy.deepcopy(self.config)
        config["cues"] = [{"performer": "P01", "start": 0, "end": .1, "intensity": .8}]
        with self.assertRaisesRegex(ValueError, "composition"):
            self.verify(config)
        self.reset_calls()
        self.prepare(config=config)
        self.candidates.assert_not_called()
        self.expressive.assert_called_once()
        self.verify(config)

    def test_transcript_and_producing_code_changes_invalidate_candidates(self):
        self.prepare()
        transcript = {"segments": [{"start": .02, "end": .08}]}
        self.reset_calls()
        self.prepare(transcript=transcript)
        self.candidates.assert_called_once()
        self.expressive.assert_called_once()
        self.reset_calls()
        self.producer_mock.return_value = {"amp/audio.py": "b" * 64}
        self.prepare(transcript=transcript)
        self.candidates.assert_called_once()
        self.expressive.assert_called_once()

    def test_candidate_source_binding_is_required_for_expressive_cache(self):
        self.prepare()
        path = self.audio / "expressive-report.json"
        report = json.loads(path.read_text())
        report["preparation_inputs"]["candidate_sha256"] = "0" * 64
        write_json(path, report)
        self.reset_calls()
        self.prepare()
        self.candidates.assert_not_called()
        self.expressive.assert_called_once()
        self.verify()

    def test_invalid_regeneration_preserves_existing_verified_candidate_cache(self):
        self.prepare()
        original_audio = (self.audio / "candidate-B.wav").read_bytes()
        original_report = (self.audio / "audio-report.json").read_bytes()

        def truncated_generator(source, transcript, out):
            self.make_candidates(source, transcript, out)
            path = Path(out) / "candidate-B.wav"
            save_audio(path, self.samples[:-1])
            report_path = Path(out) / "audio-report.json"
            report = json.loads(report_path.read_text())
            report["candidates"]["B"]["sha256"] = sha256(path)
            write_json(report_path, report)

        self.candidates.side_effect = truncated_generator
        with self.assertRaisesRegex(ValueError, "wrong decoded sample count"):
            self.prepare(transcript={"segments": []})
        self.assertEqual((self.audio / "candidate-B.wav").read_bytes(), original_audio)
        self.assertEqual((self.audio / "audio-report.json").read_bytes(), original_report)
        self.assertFalse(list(self.root.glob(".directed-candidates-*")))
        self.verify()


if __name__ == "__main__":
    unittest.main()
