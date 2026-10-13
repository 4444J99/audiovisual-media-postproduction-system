import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from amp.generation import frame_units, generate_schedule

ROOT = Path(__file__).resolve().parents[1]
SOURCE = {"sha256": "a" * 64, "frame_count": 90, "fps": {"numerator": 30, "denominator": 1}}
UNITS = [{"id": str(i), "start": i, "end": i + 1, "eligible": True,
          "allowed_next": [str(j) for j in range(3) if j != i]} for i in range(3)]


def reviewed():
    return {"schema_version": "1.0", "source": copy.deepcopy(SOURCE),
            "intervals": [{"id": "synthetic", "start_frame": 0, "end_frame": 90, "disposition": "verified"}],
            "unit_reviews": [{"unit_id": u["id"], "source_sha256": SOURCE["sha256"],
                              "start_frame": u["start_frame"], "end_frame": u["end_frame"], "disposition": "verified",
                              "evidence": {aspect: {"method": "listened", "reviewer": "synthetic-test",
                                                    "evidence_id": "synthetic-only"}
                                           for aspect in ("words", "speaker", "boundaries")}}
                             for u in frame_units(UNITS, SOURCE)]}


class GenerationAdmissionTests(unittest.TestCase):
    def test_legacy_remains_provisional(self):
        units = json.loads((ROOT / "projects/god-here/units.json").read_text())["units"]
        result = generate_schedule(units, 17)
        self.assertIn("provisional", result["text_verification"])
        self.assertNotIn("generation_mode", result)
        self.assertEqual(result, generate_schedule(units, 17))

    def test_linguistic_requires_explicit_reviews(self):
        with self.assertRaises(ValueError):
            generate_schedule(UNITS, 17, generation_mode="linguistic")
        document = reviewed()
        document["unit_reviews"] = []
        with self.assertRaises(ValueError):
            generate_schedule(UNITS, 17, generation_mode="linguistic", source=SOURCE, qualification=document)

    def test_only_reviewed_units_can_enter_schedule(self):
        document = reviewed()
        document["unit_reviews"][0]["disposition"] = "texture_only"
        result = generate_schedule(UNITS, 17, count=2, generation_mode="linguistic", source=SOURCE, qualification=document)
        self.assertNotIn("0", [e["unit"] for e in result["events"]])
        self.assertEqual(result["events"][0]["output_start_frame"], 0)
        self.assertEqual(result["events"][-1]["output_end_frame"], 60)
        self.assertEqual(len(result["qualification_sha256"]), 64)

    def test_rebound_and_off_grid_units_rejected(self):
        for field, value in (("source_sha256", "b" * 64), ("start_frame", 1), ("start", .01), ("end", float("nan"))):
            units = copy.deepcopy(UNITS)
            units[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                generate_schedule(units, 17, generation_mode="linguistic", source=SOURCE, qualification=reviewed())

    def test_modes_and_resource_bounds_fail_closed(self):
        for count in (True, 0, -1, 257, 2.5):
            with self.subTest(count=count), self.assertRaises(ValueError):
                generate_schedule(UNITS, 17, count=count)
        with self.assertRaises(ValueError):
            generate_schedule(UNITS, 17, qualification=reviewed())
        with self.assertRaises(ValueError):
            generate_schedule(UNITS + [UNITS[0]], 17)

    def test_one_event_accepts_one_reviewed_unit_without_a_transition(self):
        document = reviewed()
        document["unit_reviews"] = document["unit_reviews"][:1]
        try:
            result = generate_schedule(UNITS[:1], 17, count=1, generation_mode="linguistic",
                                       source=SOURCE, qualification=document)
        except ValueError as exc:
            self.fail(f"A single reviewed excerpt was rejected: {exc}")
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["unit"], "0")
        self.assertEqual(result["duration"], 1)

    def test_cli_real_source_audit_and_generation_are_distinct(self):
        audit = subprocess.run([sys.executable, "-m", "amp.cli", "qualify"], cwd=ROOT,
                               capture_output=True, text=True, timeout=10)
        self.assertEqual(audit.returncode, 0, audit.stderr)
        record = json.loads(audit.stdout)
        self.assertEqual(record["coverage"]["frames_by_disposition"]["pending"], 3360)
        self.assertEqual(record["qualified_unit_ids"], [])
        blocked = subprocess.run([sys.executable, "-m", "amp.cli", "generate", "--generation-mode", "linguistic", "--dry-run"],
                                 cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(blocked.returncode, 2, blocked.stderr)
        self.assertEqual(json.loads(blocked.stdout)["status"], "blocked")
        legacy = subprocess.run([sys.executable, "-m", "amp.cli", "generate", "--dry-run"],
                                cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(legacy.returncode, 0, legacy.stderr)
        self.assertEqual(len(json.loads(legacy.stdout)["events"]), 5)

    def test_remix_rejects_media_binding_mismatch_before_execution(self):
        from amp.render import remix
        schedule = generate_schedule(UNITS, 17, count=2, generation_mode="linguistic", source=SOURCE, qualification=reviewed())
        cases = [("b" * 64, "30/1", "90"), ("a" * 64, "24/1", "90"),
                 ("a" * 64, "30/1", "89"), ("a" * 64, "30/1", None)]
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "new" / "out.mp4"
            for digest, fps, frames in cases:
                stream = {"codec_type": "video", "avg_frame_rate": fps}
                if frames is not None:
                    stream["nb_frames"] = frames
                with self.subTest(digest=digest, fps=fps, frames=frames), \
                        patch("amp.render.sha256", return_value=digest), \
                        patch("amp.render.probe", return_value={"streams": [stream]}), \
                        patch("amp.render.run") as run:
                    with self.assertRaises(ValueError):
                        remix(Path(directory) / "source.mp4", schedule, destination)
                    run.assert_not_called()
                    self.assertFalse(destination.parent.exists())

    def test_remix_rejects_changed_seconds_or_frame_provenance(self):
        from amp.render import remix
        original = generate_schedule(UNITS, 17, count=2, generation_mode="linguistic", source=SOURCE, qualification=reviewed())
        changes = [("source_start", .5), ("source_end", .5),
                   ("source_start_frame", True), ("source_end_frame", 91),
                   ("output_start_frame", 1), ("output_end_frame", 2),
                   ("output_start", .5), ("source_start", float("nan"))]
        with tempfile.TemporaryDirectory() as directory:
            for index, (field, value) in enumerate(changes):
                schedule = copy.deepcopy(original)
                schedule["events"][0][field] = value
                destination = Path(directory) / f"{index}-{field}" / "out.mp4"
                # Substitute only external media reads/encoding. Old code completes
                # successfully, so the expected rejection detects the real gap.
                def encode(args):
                    Path(args[-1]).write_bytes(b"synthetic encoded output")
                with self.subTest(field=field, value=value), \
                        patch("amp.render.sha256", return_value=SOURCE["sha256"]), \
                        patch("amp.render.probe", return_value={"streams": [{"codec_type": "video", "avg_frame_rate": "30/1", "nb_frames": "90"}]}), \
                        patch("amp.render.run", side_effect=encode) as run:
                    with self.assertRaises(ValueError):
                        remix(Path(directory) / "source.mp4", schedule, destination)
                    run.assert_not_called()
                    self.assertFalse(destination.parent.exists())

    def test_linguistic_remix_renders_exact_frame_order(self):
        import numpy as np
        from amp.core import sha256
        from amp.render import remix
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source.mp4", root / "output.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=red:s=160x90:r=30:d=0.1",
                            "-f", "lavfi", "-i", "color=blue:s=160x90:r=30:d=0.1",
                            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-filter_complex",
                            "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]", "-map", "2:a",
                            "-t", "0.2", "-c:v", "libx264", "-threads", "1", "-c:a", "aac", str(source)],
                           check=True, timeout=20)
            schedule = {"generation_mode": "linguistic", "source": {"sha256": sha256(source), "frame_count": 6,
                        "fps": {"numerator": 30, "denominator": 1}}, "duration": .2,
                        "events": [{"source_start": .1, "source_end": .2, "source_start_frame": 3, "source_end_frame": 6,
                                    "output_start": 0, "output_end": .1, "output_start_frame": 0, "output_end_frame": 3},
                                   {"source_start": 0, "source_end": .1, "source_start_frame": 0, "source_end_frame": 3,
                                    "output_start": .1, "output_end": .2, "output_start_frame": 3, "output_end_frame": 6}]}
            remix(source, schedule, output)
            pixels = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(output), "-map", "0:v:0",
                                              "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], timeout=20)
            frames = np.frombuffer(pixels, dtype=np.uint8).reshape((-1, 90, 160, 3))
            self.assertEqual(len(frames), 6)
            self.assertGreater(int(frames[0, 45, 80, 2]), 200)
            self.assertLess(int(frames[0, 45, 80, 0]), 25)
            self.assertGreater(int(frames[3, 45, 80, 0]), 200)
            self.assertLess(int(frames[3, 45, 80, 2]), 25)


if __name__ == "__main__":
    unittest.main()
