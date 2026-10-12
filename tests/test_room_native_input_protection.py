"""Native room producers preserve source, inventory and model bytes on collisions."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from amp import roomrack, roomtone
from amp.audio import save_audio
from amp.core import sha256


class RoomNativeInputProtectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="room-input-protection-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.samples = np.random.default_rng(413).normal(0, .004, (4800, 2)).astype(np.float32)

    def inputs(self, folder):
        folder.mkdir(parents=True)
        source, model, inventory = folder / "source.wav", folder / "vad.onnx", folder / "inventory.json"
        save_audio(source, self.samples)
        model.write_bytes(b"model bytes must never change")
        inventory.write_text(json.dumps({"source_sha256": sha256(source),
                                         "pauses": [{"usable_portions": [{"start": 0, "end": .08}]}]}))
        return source, model, inventory

    def collide(self, protected, target, kind):
        if kind == "direct":
            target.write_bytes(protected.read_bytes())
            return target
        if kind == "symlink":
            target.symlink_to(protected)
        else:
            target.hardlink_to(protected)
        return protected

    def test_roomtone_rejects_source_and_model_aliases_for_every_output_before_processing(self):
        names = ["room-tone-nonlooping.wav", "source-pause-audition.wav", "vad-probabilities.json", "room-tone-report.json"]
        for index, (name, role, kind) in enumerate((n, r, k) for n in names
                                                  for r in ("source", "model") for k in ("direct", "symlink", "hardlink")):
            with self.subTest(output=name, input=role, alias=kind):
                source, model, _ = self.inputs(self.root / str(index))
                out = source.parent / "output"
                out.mkdir()
                if role == "source":
                    source = self.collide(source, out / name, kind)
                else:
                    model = self.collide(model, out / name, kind)
                before = {path: path.read_bytes() for path in (source, model)}
                with mock.patch.object(roomtone, "load_audio") as decode, mock.patch.object(roomtone, "speech_probabilities") as model_run:
                    with self.assertRaisesRegex(ValueError, "overwrite an input"):
                        roomtone.create_roomtone(source, {"segments": []}, model, out)
                    decode.assert_not_called()
                    model_run.assert_not_called()
                for path, content in before.items():
                    self.assertEqual(path.read_bytes(), content)

    def test_roomrack_rejects_source_and_inventory_aliases_for_every_output_before_processing(self):
        names = [f"{band}-{kind}.wav" for band in ("low", "mid", "high")
                 for kind in ("dry", "compressed", "fx-return", "layer", "dry-contribution")]
        names += [f"{band}-{kind}.flac" for band in ("low", "mid", "high")
                  for kind in ("layer", "dry-contribution", "fx-return")]
        names += ["room-tone-layered.wav", "room-tone-layered.flac", "room-rack-report.json"]
        for index, (name, role, kind) in enumerate((n, r, k) for n in names
                                                  for r in ("source", "inventory") for k in ("direct", "symlink", "hardlink")):
            with self.subTest(output=name, input=role, alias=kind):
                source, _, inventory = self.inputs(self.root / str(index))
                out = source.parent / "output"
                out.mkdir()
                if role == "source":
                    source = self.collide(source, out / name, kind)
                else:
                    inventory = self.collide(inventory, out / name, kind)
                before = {path: path.read_bytes() for path in (source, inventory)}
                with mock.patch.object(roomrack, "load_audio") as decode, mock.patch.object(roomrack, "run") as encode:
                    with self.assertRaisesRegex(ValueError, "overwrite an input"):
                        roomrack.build(source, inventory, out)
                    decode.assert_not_called()
                    encode.assert_not_called()
                for path, content in before.items():
                    self.assertEqual(path.read_bytes(), content)

    def roomtone_processing(self):
        return [mock.patch.object(roomtone, "speech_probabilities", return_value=(np.array([0.]), .032)),
                mock.patch.object(roomtone, "pause_inventory", return_value=([(0, 8)], [], {"step_seconds": .01})),
                mock.patch.object(roomtone, "assemble", return_value=(self.samples.copy(), [{"source_fragment": 0}]))]

    def test_roomtone_allows_shared_directory_and_replacing_unrelated_derived_output(self):
        source, model, _ = self.inputs(self.root / "shared")
        out = source.parent
        original = {path: path.read_bytes() for path in (source, model)}
        (out / "room-tone-nonlooping.wav").write_bytes(b"old derived audio")
        patches = self.roomtone_processing()
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        report = roomtone.create_roomtone(source, {"segments": []}, model, out, duration=.1)
        self.assertEqual(report["source_sha256"], sha256(source))
        self.assertEqual(report["model_sha256"], sha256(model))
        for path, content in original.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertNotEqual((out / "room-tone-nonlooping.wav").read_bytes(), b"old derived audio")
        self.assertTrue((out / "room-tone-report.json").is_file())

    def test_roomrack_allows_shared_directory_and_replacing_unrelated_derived_output(self):
        source, _, inventory = self.inputs(self.root / "shared")
        out = source.parent
        original = {path: path.read_bytes() for path in (source, inventory)}
        (out / "room-tone-layered.wav").write_bytes(b"old derived audio")
        with mock.patch.object(roomrack, "assemble", return_value=(self.samples.copy(), [{"source_fragment": 0}])), \
                mock.patch.object(roomrack, "measure", return_value={"input_tp": -20.}):
            report = roomrack.build(source, inventory, out)
        self.assertEqual(report["pause_inventory_sha256"], sha256(inventory))
        for path, content in original.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertNotEqual((out / "room-tone-layered.wav").read_bytes(), b"old derived audio")
        self.assertTrue((out / "room-tone-layered.flac").is_file())
        self.assertTrue((out / "room-rack-report.json").is_file())
        self.assertFalse(list(out.glob(".room-rack-*")))

    def test_roomtone_rechecks_destination_after_processing_before_writing(self):
        source, model, _ = self.inputs(self.root / "shared")
        out = source.parent
        original = source.read_bytes()
        for patch in self.roomtone_processing()[1:]:
            patch.start()
            self.addCleanup(patch.stop)

        def alias_after_initial_check(*_):
            (out / "room-tone-nonlooping.wav").symlink_to(source)
            return np.array([0.]), .032

        with mock.patch.object(roomtone, "speech_probabilities", side_effect=alias_after_initial_check):
            with self.assertRaisesRegex(ValueError, "overwrite an input"):
                roomtone.create_roomtone(source, {"segments": []}, model, out)
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse((out / "room-tone-report.json").exists())

    def test_roomrack_stages_flac_and_rechecks_alias_before_publication(self):
        source, _, inventory = self.inputs(self.root / "shared")
        out = source.parent
        original = source.read_bytes()

        def encode_then_alias(command):
            staged = Path(command[-1])
            self.assertNotEqual(staged.parent, out)
            staged.write_bytes(b"encoded staged FLAC")
            (out / staged.name).hardlink_to(source)

        with mock.patch.object(roomrack, "assemble", return_value=(self.samples.copy(), [{"source_fragment": 0}])), \
                mock.patch.object(roomrack, "measure", return_value={"input_tp": -20.}), \
                mock.patch.object(roomrack, "run", side_effect=encode_then_alias):
            with self.assertRaisesRegex(ValueError, "overwrite an input"):
                roomrack.build(source, inventory, out)
        self.assertEqual(source.read_bytes(), original)
        self.assertFalse((out / "room-rack-report.json").exists())
        self.assertFalse(list(out.glob(".room-rack-*")))


if __name__ == "__main__":
    unittest.main()
