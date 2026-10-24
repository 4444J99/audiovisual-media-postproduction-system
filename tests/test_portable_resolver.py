"""Unit tests for portable private path resolver and dependency closure (T03)."""
import os
import shutil
import unittest
from pathlib import Path

from amp.media_resolver import (
    ContractError,
    DependencyClosureError,
    MediaResolver,
    check_dependency_closure,
)


class PortableResolverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(os.environ.get("PYTEST_TMPDIR", "/tmp")) / f"portable-res-test-{os.getpid()}"
        if self.tmp.exists():
            shutil.rmtree(self.tmp)
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.comp_dir = self.repo / "compositions" / "comp-001"
        self.comp_dir.mkdir(parents=True)
        # Create compatibility alias projects/god-here -> compositions/comp-001
        self.projects_dir = self.repo / "projects"
        self.projects_dir.mkdir()
        (self.projects_dir / "god-here").symlink_to("../compositions/comp-001")

        self.media_root = self.tmp / "media_root"
        self.media_root.mkdir()

    def tearDown(self):
        if self.tmp.exists():
            shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_file_fails_closed(self):
        resolver = MediaResolver(self.repo, media_root=self.media_root, project_root=self.comp_dir)
        with self.assertRaises(ContractError) as ctx:
            resolver.resolve_private_path("non_existent_material.wav")
        self.assertEqual(ctx.exception.code, "missing_dependency")

        # Dependency closure reports structured missing report
        with self.assertRaises(DependencyClosureError) as exc_ctx:
            check_dependency_closure(
                files=["missing_sound.wav"],
                dat_files=["missing_dat.py"],
                fonts=["missing_font.ttf"],
                resolver=resolver,
                raise_on_error=True,
            )
        report = exc_ctx.exception.report
        self.assertFalse(report["valid"])
        self.assertEqual(len(report["missing"]), 3)
        kinds = {m["kind"] for m in report["missing"]}
        self.assertEqual(kinds, {"file", "native_dat", "font"})

    def test_absent_sequence_frame_detected(self):
        seq_dir = self.media_root / "layer_seq_01"
        seq_dir.mkdir()
        (seq_dir / "frame_001.png").write_bytes(b"frame 1 data")
        # Frame 002 is absent!
        (seq_dir / "frame_003.png").write_bytes(b"frame 3 data")

        resolver = MediaResolver(self.repo, media_root=self.media_root)

        # check_dependency_closure should fail closed due to gap
        with self.assertRaises(DependencyClosureError) as ctx:
            check_dependency_closure(
                sequences=[{"path": seq_dir, "expected_frames": 3}],
                resolver=resolver,
            )
        report = ctx.exception.report
        self.assertFalse(report["valid"])
        missing_seq = report["missing"][0]
        self.assertEqual(missing_seq["kind"], "sequence")
        self.assertIn("absent sequence frame", missing_seq["reason"])
        self.assertEqual(missing_seq["frames_found"], 2)
        self.assertEqual(missing_seq["payload_bytes"], len(b"frame 1 data") + len(b"frame 3 data"))

        # Empty sequence directory is also rejected
        empty_dir = self.media_root / "empty_seq"
        empty_dir.mkdir()
        report_empty = check_dependency_closure(
            sequences=[empty_dir],
            resolver=resolver,
            raise_on_error=False,
        )
        self.assertFalse(report_empty["valid"])
        self.assertIn("empty sequence", report_empty["missing"][0]["reason"])

    def test_relocated_root_resolution(self):
        old_root = self.tmp / "old_machine" / "media"
        old_root.mkdir(parents=True)
        old_seq = old_root / "packages" / "pkg123" / "sequences" / "seq456"
        old_seq.mkdir(parents=True)
        (old_seq / "frame_01.png").write_bytes(b"frame 1")
        (old_seq / "frame_02.png").write_bytes(b"frame 2")

        # Now simulate moving or mounting under new_media_root
        new_media_root = self.tmp / "new_machine" / "media"
        new_media_root.mkdir(parents=True)
        new_seq = new_media_root / "packages" / "pkg123" / "sequences" / "seq456"
        new_seq.parent.mkdir(parents=True)
        shutil.copytree(old_seq, new_seq)

        # Delete old files to guarantee they only exist at the relocated destination
        shutil.rmtree(old_root)

        resolver = MediaResolver(self.repo, media_root=new_media_root)

        # Resolving old absolute path resolves to new_media_root
        resolved = resolver.resolve_private_path(old_seq / "frame_01.png")
        self.assertTrue(resolved.exists())
        self.assertEqual(resolved.resolve(), (new_seq / "frame_01.png").resolve())

        # Sequence check on old path resolves through relocated root
        report = check_dependency_closure(
            sequences=[{"path": old_seq, "expected_frames": 2}],
            resolver=resolver,
            raise_on_error=True,
        )
        self.assertTrue(report["valid"])
        self.assertEqual(report["sequences"][0]["frames"], 2)
        self.assertEqual(report["sequences"][0]["bytes"], len(b"frame 1") + len(b"frame 2"))

    def test_valid_portable_resolution_and_boundary_checks(self):
        # Create media file in media_root
        audio_file = self.media_root / "audio" / "dialogue.wav"
        audio_file.parent.mkdir(parents=True)
        audio_file.write_bytes(b"RIFF....WAVEfmt ....data....")

        # Create project file in comp-001
        score_file = self.comp_dir / "score.json"
        score_file.write_text('{"score": 1}')

        # Create code file
        code_file = self.repo / "native" / "touchdesigner" / "material_workspace" / "controls.py"
        code_file.parent.mkdir(parents=True)
        code_file.write_text("# controls")

        # Create font file
        font_file = self.media_root / "fonts" / "DejaVuSans.ttf"
        font_file.parent.mkdir(parents=True)
        font_file.write_bytes(b"dummy font data")

        # Create sequence in media_root
        seq_dir = self.media_root / "sequences" / "matte_seq"
        seq_dir.mkdir(parents=True)
        for i in range(1, 4):
            (seq_dir / f"frame_{i:03d}.png").write_bytes(f"f{i}".encode())

        resolver = MediaResolver(self.repo, media_root=self.media_root, project_root=self.comp_dir)

        # 1. Resolve relative media path
        res_audio = resolver.resolve_private_path("audio/dialogue.wav")
        self.assertEqual(res_audio.resolve(), audio_file.resolve())

        # 2. Resolve relative project path
        res_score = resolver.resolve_private_path("score.json")
        self.assertEqual(res_score.resolve(), score_file.resolve())

        # 3. Resolve compatibility alias path: projects/god-here/score.json
        alias_path = self.projects_dir / "god-here" / "score.json"
        res_alias = resolver.resolve_private_path(alias_path)
        self.assertEqual(res_alias.resolve(), score_file.resolve())

        # 4. Escaping relative path rejected
        with self.assertRaises(ContractError) as ctx:
            resolver.resolve_private_path("../outside.wav")
        self.assertEqual(ctx.exception.code, "unsupported_relative_path")

        # 5. Full closure check passes cleanly
        report = check_dependency_closure(
            sequences=[{"path": "sequences/matte_seq", "expected_frames": 3}],
            dat_files=["native/touchdesigner/material_workspace/controls.py"],
            fonts=["fonts/DejaVuSans.ttf"],
            files=["audio/dialogue.wav"],
            resolver=resolver,
            raise_on_error=True,
        )
        self.assertTrue(report["valid"])
        self.assertEqual(len(report["missing"]), 0)
        self.assertEqual(report["sequences"][0]["frames"], 3)
        self.assertEqual(report["sequences"][0]["bytes"], 6)  # f1, f2, f3 = 2 bytes each
        self.assertTrue(report["dat_files"][0]["valid"])
        self.assertTrue(report["fonts"][0]["valid"])
        self.assertTrue(report["files"][0]["valid"])


if __name__ == "__main__":
    unittest.main()
