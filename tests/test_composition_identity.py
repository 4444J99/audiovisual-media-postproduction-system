"""Compatibility paths and a second composition exercise the same processor."""
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import numpy as np
from PIL import Image
from scipy.io import wavfile

from amp.cli import main
from amp.composition import resolve_composition
from amp.core import composite, sha256, validate
from amp.render import render
from amp.workstation import export_workstation

ROOT = Path(__file__).resolve().parents[1]


def second_composition():
    return {"schema_version": "1.0", "project": "synthetic-two-region-study",
            "fps": 30, "source_sha256": "a" * 64, "history_frames": 20,
            "performers": {"left": {"style": "pressure"}, "right": {"style": "erosion"}},
            "layouts": {"view": {"registered": True, "fields": [
                {"performer": "left", "span": [0, .4]},
                {"performer": "right", "span": [.6, 1]}]}},
            "shots": [{"id": "single-view", "start": 0, "end": .1, "layout": "view"}],
            "cues": [{"performer": "left", "start": 0, "end": .1, "intensity": .8,
                      "attack": 0, "release": 0}], "layers": [], "typography": []}


class CompositionIdentityTests(unittest.TestCase):
    def test_retained_paths_and_every_migrated_byte_match(self):
        inventory = json.loads((ROOT / "docs/architecture/composition-migration.json").read_text())
        self.assertEqual((ROOT / "projects/god-here").resolve(), (ROOT / "compositions/comp-001").resolve())
        for record in inventory["files"]:
            with self.subTest(path=record["from"]):
                current = (ROOT / record["to"]).read_bytes()
                expected_hash=record["sha256"]
                if 'preserved_original' in record:
                    original=(ROOT/record['preserved_original']).read_bytes()
                    self.assertEqual(hashlib.sha256(original).hexdigest(),record['sha256'])
                    self.assertTrue((ROOT/record['reconciliation_evidence']).is_file())
                    corrected=json.loads(original)
                    self.assertTrue(record['corrections'])
                    for correction in record['corrections']:
                        parent=corrected
                        for key in correction['json_path'][:-1]:parent=parent[key]
                        key=correction['json_path'][-1]
                        self.assertEqual(parent[key],correction['before']);parent[key]=correction['after']
                    self.assertEqual(json.loads(current),corrected)
                    expected_hash=record['reconciled_sha256']
                self.assertEqual(hashlib.sha256(current).hexdigest(),expected_hash)
                self.assertEqual((ROOT / record["from"]).read_bytes(), current)

    def test_default_id_and_legacy_selections_resolve_one_composition(self):
        expected = (ROOT / "compositions/comp-001").resolve()
        for selection in (None, "comp-001", "god-here", "projects/god-here", "compositions/comp-001"):
            self.assertEqual(resolve_composition(selection, root=ROOT).resolve(), expected)

    def test_installed_consumer_has_no_implicit_artwork(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Select a composition"):
                resolve_composition(root=directory)
            root = Path(directory)
            (root / "independent").mkdir()
            self.assertEqual(resolve_composition("independent", root=root), root / "independent")

    def test_registry_rejects_escaping_paths_and_duplicate_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in ("../outside", "/outside"):
                document = {"schema_version": "1.0.0", "system_id": "audiovisual-composition-system",
                            "compositions": [{"id": "comp-test", "path": path}]}
                (root / "ace-manifest.json").write_text(json.dumps(document))
                with self.assertRaisesRegex(ValueError, "inside"):
                    resolve_composition("comp-test", root=root)
            document["compositions"] *= 2
            (root / "ace-manifest.json").write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError, "exactly one"):
                resolve_composition("comp-test", root=root)

    def test_source_labels_preserve_existing_ids_and_original_bindings(self):
        registry = json.loads((ROOT / "ace-manifest.json").read_text())
        original = json.loads((ROOT / "compositions/comp-001/planning-source-manifest.json").read_text())
        expected = {item["id"]: item for item in original["sources"]}
        self.assertEqual({item["id"] for item in registry["source_media"]}, set(expected))
        for item in registry["source_media"]:
            for field in ("id", "original_filename", "sha256", "bytes"):
                self.assertEqual(item[field], expected[item["id"]][field])

    def test_two_region_composition_keeps_containment_and_rejects_identity_loss(self):
        config = second_composition()
        self.assertTrue(validate(config)["valid"])
        image = Image.fromarray(np.random.default_rng(4).integers(0, 256, (90, 160, 3), dtype=np.uint8))
        result = np.asarray(composite(image, [image], config, .05))
        self.assertFalse(np.array_equal(result[:, :64], np.asarray(image)[:, :64]))
        self.assertTrue(np.array_equal(result[:, 64:], np.asarray(image)[:, 64:]))
        for fields in ([], config["layouts"]["view"]["fields"][:1],
                       [config["layouts"]["view"]["fields"][0]] * 2):
            broken = copy.deepcopy(config)
            broken["layouts"]["view"]["fields"] = fields
            with self.assertRaisesRegex(ValueError, "identities"):
                validate(broken)
        config["performers"] = {}
        with self.assertRaisesRegex(ValueError, "at least one"):
            validate(config)

    def test_workstation_names_follow_composition_and_legacy_names_stay_available(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clean, returns, video = root / 'clean.wav', root / 'returns.wav', root / 'movie.mp4'
            for path in (clean, returns, video):
                path.write_bytes(b'structural-export-fixture')
            recipe = {'segments': [{'source_start_frame': 0, 'source_end_frame': 3, 'output_frames': 3}]}
            for project in ('god-here', 'synthetic-two-region-study'):
                config = second_composition()
                config['project'] = project
                with patch('amp.workstation.probe', return_value={'streams': [{'codec_type': 'video', 'nb_frames': 3}]}):
                    output = export_workstation(recipe, config, clean, returns, {'Study': video}, root / project)
                self.assertTrue((output / f'{project}-directed-audio.rpp').is_file())
                self.assertTrue((output / f'{project}-variant-review.comp').is_file())
                if project != 'god-here':
                    self.assertNotIn('god-here', (output / 'OPEN-FIRST.md').read_text())
                    self.assertFalse(any('god-here' in path.name for path in output.iterdir()))
            with self.assertRaisesRegex(ValueError, 'filename component'):
                export_workstation(recipe, config, clean, returns, {'Study': video}, root / 'escape', filename_prefix='../escape')

    def test_explicit_second_composition_validates_and_schedules_with_both_cli_options(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "composition.json").write_text(json.dumps(second_composition()))
            units = [{"id": str(i), "start": i, "end": i + 1, "eligible": True,
                      "allowed_next": [str(j) for j in range(3) if i != j]} for i in range(3)]
            (root / "units.json").write_text(json.dumps({"units": units}))
            for option in ("--composition", "--project"):
                for command in (["validate"], ["generate", "--dry-run"]):
                    out = io.StringIO()
                    with patch.object(sys, "argv", ["amp", *command, option, directory]), redirect_stdout(out):
                        main()
                    result = json.loads(out.getvalue())
                    self.assertTrue(result.get("valid", len(result.get("events", [])) == 5))
                    self.assertNotIn("god-here", out.getvalue())

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg unavailable")
    def test_second_composition_renders_actual_synthetic_media(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, audio = root / "test-pattern.mp4", root / "silence.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=160x90:rate=30:duration=0.1", "-c:v", "libx264",
                            "-threads", "1", str(source)], check=True)
            wavfile.write(audio, 48000, np.zeros((4800, 2), dtype=np.float32))
            config = second_composition()
            config["source_sha256"] = sha256(source)
            report = render(source, audio, config, root / "two-region-study.mp4", end=.1, width=160)
            self.assertEqual(report["frames"], 3)
            self.assertEqual(report["output_sha256"], sha256(root / "two-region-study.mp4"))
