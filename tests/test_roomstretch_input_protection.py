"""Direct room renders cannot replace owner inputs through any output alias."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np

from amp.audio import RATE, load_audio, save_audio
from amp.core import sha256
from amp.roomstretch import _encode, _save_wav, _write_json, build


class RoomStretchInputProtectionTests(unittest.TestCase):
    def all_targets(self):
        targets = ["source-reel-raw.wav", "source-reel-seam-smoothed.wav", "room-stretch-report.json"]
        for mode in ("V", "P"):
            for period in ("1", "0.5"):
                name = mode + period
                targets += [f"raw-stems/{name}.wav", f"stems/{name}.wav", f"stems/{name}.flac",
                            f"web/{name}-production.m4a", f"web/{name}-audition.m4a"]
            stacks = [f"{mode}{count}-stack" for count in ((1, 2) if mode == "V" else (2,))]
            stacks.append(mode + "2R")
            for name in stacks:
                targets += [f"stacks/{name}.wav", f"stacks/{name}.flac",
                            f"web/{name}-production.m4a", f"web/{name}-audition.m4a"]
        return targets

    def assert_rejected_without_reads(self, source, inventory, output):
        source_bytes, inventory_bytes = source.read_bytes(), inventory.read_bytes()
        with mock.patch("amp.roomstretch.sha256") as digest, mock.patch("amp.roomstretch.load_audio") as decode, \
                mock.patch("amp.roomstretch.json.loads") as parse:
            with self.assertRaisesRegex(ValueError, "overwrite an input"):
                build(source, inventory, output, duration=1, periods=(1, .5), spectral=True)
            digest.assert_not_called()
            decode.assert_not_called()
            parse.assert_not_called()
        self.assertEqual(source.read_bytes(), source_bytes)
        self.assertEqual(inventory.read_bytes(), inventory_bytes)

    def test_every_selected_native_target_rejects_source_or_inventory_alias_before_reads(self):
        for name in self.all_targets():
            for role in ("source", "inventory"):
                with self.subTest(name=name, role=role), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    output = root / "output"
                    paths = {"source": root / "owner.wav", "inventory": root / "owner.json"}
                    paths[role] = output / name
                    for label, filename in paths.items():
                        filename.parent.mkdir(parents=True, exist_ok=True)
                        filename.write_bytes(("unchanged owner " + label).encode())
                    before = {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}
                    self.assert_rejected_without_reads(paths["source"], paths["inventory"], output)
                    self.assertEqual({str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}, before)

    def test_existing_symlink_and_hardlink_destinations_cannot_alias_either_input(self):
        for name in ("source-reel-raw.wav", "room-stretch-report.json", "web/P2R-audition.m4a"):
            for role in ("source", "inventory"):
                for alias in ("symlink", "hardlink"):
                    with self.subTest(name=name, role=role, alias=alias), tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        source, inventory, output = root / "owner.wav", root / "owner.json", root / "output"
                        source.write_bytes(b"owner audio")
                        inventory.write_bytes(b"owner inventory")
                        protected = source if role == "source" else inventory
                        destination = output / name
                        destination.parent.mkdir(parents=True)
                        if alias == "symlink":
                            destination.symlink_to(protected)
                        else:
                            os.link(protected, destination)
                        self.assert_rejected_without_reads(source, inventory, output)
                        self.assertTrue(destination.samefile(protected))

    def test_shared_folder_and_unselected_mode_name_still_render_and_replace_derived_files(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            # P1 is never produced when spectral=False, so this shared-folder
            # source remains valid while actual V outputs can be refreshed.
            source = output / "stems/P1.wav"
            samples = np.random.default_rng(71).normal(0, .002, (RATE, 2)).astype(np.float32)
            save_audio(source, samples)
            inventory = output / "owner-inventory.json"
            inventory.write_text(json.dumps({"source_sha256": sha256(source), "sample_rate": RATE, "channels": 2,
                "pauses": [{"id": "fixture", "usable_portions": [{"start": .1, "end": .3}]}]}))
            source_before, inventory_before = source.read_bytes(), inventory.read_bytes()
            stale = output / "source-reel-raw.wav"
            stale.write_bytes(b"old derived reel")
            report = build(source, inventory, output, duration=1, periods=(1,), spectral=False, audition_boost_db=0)
            self.assertEqual(report["status"], "rendered and technically verified; human listening pending")
            self.assertNotEqual(stale.read_bytes(), b"old derived reel")
            self.assertEqual(source.read_bytes(), source_before)
            self.assertEqual(inventory.read_bytes(), inventory_before)
            self.assertTrue((output / "web/V1R-audition.m4a").is_file())

    def test_wav_writer_rechecks_late_input_alias_before_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / "owner.wav", root / "derived.wav"
            source.write_bytes(b"owner original")
            from scipy.io import wavfile
            read = wavfile.read
            def introduce_alias(filename):
                result = read(filename)
                destination.symlink_to(source)
                return result
            with mock.patch("amp.roomstretch.wavfile.read", side_effect=introduce_alias):
                with self.assertRaisesRegex(ValueError, "overwrite an input"):
                    _save_wav(destination, np.ones((100, 2), np.float32) * .01, protected_inputs=(source,))
            self.assertEqual(source.read_bytes(), b"owner original")
            self.assertTrue(destination.is_symlink())

    def test_json_writer_rechecks_late_input_alias_before_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / "owner.json", root / "derived.json"
            source.write_bytes(b"owner inventory")
            dumps = json.dumps
            def introduce_alias(*args, **kwargs):
                destination.symlink_to(source)
                return dumps(*args, **kwargs)
            with mock.patch("amp.roomstretch.json.dumps", side_effect=introduce_alias):
                with self.assertRaisesRegex(ValueError, "overwrite an input"):
                    _write_json(destination, {"new": "report"}, protected_inputs=(source,))
            self.assertEqual(source.read_bytes(), b"owner inventory")
            self.assertTrue(destination.is_symlink())

    def test_encoder_rechecks_late_input_alias_before_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / "owner.wav", root / "derived.flac"
            samples = np.random.default_rng(12).normal(0, .002, (4800, 2)).astype(np.float32)
            save_audio(source, samples)
            before = source.read_bytes()
            def introduce_alias(filename):
                result = load_audio(filename)
                destination.symlink_to(source)
                return result
            with mock.patch("amp.roomstretch.load_audio", side_effect=introduce_alias):
                with self.assertRaisesRegex(ValueError, "overwrite an input"):
                    _encode(source, destination, len(samples), "flac", protected_inputs=(source,))
            self.assertEqual(source.read_bytes(), before)
            self.assertTrue(destination.is_symlink())
