"""Source-layout regression checks; media encoding is replaced with tiny fixtures."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from amp.core import sha256
from tools import package_room_stretch_site as packaging
from tools.check_room_tone_site import resolve_url


class RoomSitePackagingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="room-site-packaging-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write(self, path, data=b"fixture bytes"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def site(self, name, config):
        site = self.root / name
        self.write(site / ".openai/hosting.json", json.dumps(config).encode())
        return site

    def test_accepts_only_the_existing_project_and_supported_unambiguous_layouts(self):
        static = self.site("static", {"project_id": packaging.SITE_ID, "static": {"directory": "dist"}})
        worker = self.site("worker", {"project_id": packaging.SITE_ID, "r2": "ROOM_MEDIA", "d1": None})
        self.assertEqual(packaging.site_targets(static).room, static / "dist/room-tone")
        self.assertEqual(packaging.site_targets(static).downloads, static / "dist/room-tone/downloads")
        self.assertEqual(packaging.site_targets(worker).room, worker / "public/room-tone")
        self.assertEqual(packaging.site_targets(worker).downloads, worker / "room-media-source/room-tone/downloads")
        for index, config in enumerate([
            {"project_id": "another-site", "r2": "ROOM_MEDIA"},
            {"project_id": packaging.SITE_ID, "r2": "OTHER_BUCKET"},
            {"project_id": packaging.SITE_ID, "static": {"directory": "public"}},
            {"project_id": packaging.SITE_ID, "static": {"directory": "dist"}, "r2": "ROOM_MEDIA"},
            {"project_id": packaging.SITE_ID},
        ]):
            bad = self.site(f"unsupported-{index}", config)
            with self.assertRaisesRegex(ValueError, "existing god-here Site"):
                packaging.site_targets(bad)
            # Both CLI phases reject the layout before reading inputs or writing.
            with self.assertRaises(ValueError):
                packaging.prepare(None, None, bad, None)
            with self.assertRaises(ValueError):
                packaging.finish(None, None, None, bad, None)
            self.assertFalse((bad / "public").exists())
            self.assertFalse((bad / "dist").exists())

    def render_fixtures(self):
        """Build the complete export inventory without generating audio/video."""
        source = self.write(self.root / "source.mp4", b"source identity fixture")
        prior, stretch = self.root / "prior", self.root / "stretch"
        prior_report = {"source_sha256": sha256(source), "versions": {}}
        for key in "ABCDE":
            path = self.write(prior / "full-length" / f"{key}-room.flac", f"earlier bed {key}".encode())
            prior_report["versions"][key] = {"title": f"Earlier {key}", "description": key,
                                             "full_room_flac_sha256": sha256(path)}
        core = self.write(prior / "full-length/dialogue-core.flac", b"dialogue core")
        prior_report["dialogue_file_sha256"] = sha256(core)
        for key in "BCDE":
            for band in ["low", "mid", "high"]:
                self.write(prior / "stems" / key / f"{band}.flac", f"{key} {band}".encode())
        for band in ["low", "mid", "high"]:
            for contribution in ["dry-contribution", "fx-return"]:
                self.write(prior / "original-room-rack" / f"{band}-{contribution}.flac")
        self.write(prior / "listening-package-report.json", json.dumps(prior_report).encode())
        self.write(prior / "god-here-room-tone-processing-notes.md", b"earlier notes")
        self.write(prior / "reproduction/settings.json", b"{}")
        for name in ["quick", "dialogue"]:
            self.write(prior / f"god-here-room-tone-{name}-comparison.mp4")
        self.write(prior / "source-pause-review/source-portions-diagnostics.png")
        portions = []
        for index in range(8):
            key = f"PAUSE{index:03d}-01"
            self.write(prior / "auditions" / f"{key}-with-handles.m4a")
            portions.append({"portion_id": key, "handle_start": index,
                             "handle_end": index + 1, "source_start": index + .2, "source_end": index + .5})
        self.write(prior / "source-pause-review/portion-review.json", json.dumps({"portions": portions}).encode())

        report = {"source_sha256": sha256(source), "layers": [], "stacks": [],
                  "source_reel_raw": {"file": "source-reel-raw.wav"},
                  "source_reel_processed": {"file": "source-reel-seam-smoothed.wav"}}
        for field in ["source_reel_raw", "source_reel_processed"]:
            self.write(stretch / report[field]["file"])
        for prefix in ["V", "P"]:
            for period in [112, 84, 56, 28, 14]:
                report["layers"].append({"id": f"{prefix}{period}", "period_seconds": period})
        for count in range(1, 6):
            report["stacks"].append({"id": f"V{count}",
                                     "member_ids": [f"V{period}" for period in [112, 84, 56, 28, 14][:count]]})
        for key in ["P5", "V5R", "P5R"]:
            report["stacks"].append({"id": key, "member_ids": [f"{key[0]}{period}" for period in [112, 84, 56, 28, 14]],
                                     "member_input_kind": "raw_stems" if key.endswith("R") else "calibrated_production_stems"})
        for entry in report["layers"] + report["stacks"]:
            for field, suffix in [("production_aac", "-production.m4a"), ("audition_aac", "-audition.m4a"),
                                  ("stem_flac", ".flac"), ("stem_wav", ".wav")]:
                entry[field] = "exports/" + entry["id"] + suffix
                self.write(stretch / entry[field], entry[field].encode())
        self.write(stretch / "room-stretch-report.json", json.dumps(report).encode())
        return source, prior, stretch

    def package_fixtures(self, source, prior, stretch, site, asset_directory):
        assets = site / asset_directory
        self.write(assets / "room-tone/media/source-picture.mp4", b"shared picture")
        working = self.root / f"working-{site.name}"

        def encode(_source, target, **_options):
            self.write(target, b"preview audio")
            return {"full_decode_verified": True}

        def video(_picture, _wave, target, _scalar):
            self.write(target, b"picture plus dialogue")
            return {"full_decode_verified": True}

        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(packaging, "SAMPLES", 16))
            stack.enter_context(mock.patch.object(packaging, "load_audio", return_value=np.zeros((16, 2), dtype=np.float32)))
            stack.enter_context(mock.patch.object(packaging, "scene_envelope", return_value=np.ones(16)))
            stack.enter_context(mock.patch.object(packaging, "measure", return_value={"input_tp": -20.0}))
            stack.enter_context(mock.patch.object(packaging, "save_audio", side_effect=lambda path, _data: self.write(path)))
            stack.enter_context(mock.patch.object(packaging, "atomic_encode", side_effect=encode))
            stack.enter_context(mock.patch.object(packaging, "contextual_video", side_effect=video))
            stack.enter_context(mock.patch.object(packaging, "run", side_effect=lambda command: self.write(Path(command[-1]))))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            self.assertEqual(packaging.prepare(source, prior, site, working), assets / "room-tone")
            packaging.finish(source, prior, stretch, site, working)
        return json.loads((assets / "room-tone/media.json").read_text())

    def test_both_phases_keep_identical_urls_while_all_42_worker_flacs_stay_outside_public(self):
        source, prior, stretch = self.render_fixtures()
        legacy = self.site("legacy", {"project_id": packaging.SITE_ID, "static": {"directory": "dist"}})
        worker = self.site("worker", {"project_id": packaging.SITE_ID, "r2": "ROOM_MEDIA"})
        sentinel = self.write(worker / "dist/generated-output.txt", b"do not edit generated output")
        old_manifest = self.package_fixtures(source, prior, stretch, legacy, "dist")
        new_manifest = self.package_fixtures(source, prior, stretch, worker, "public")
        self.assertEqual(new_manifest, old_manifest)
        self.assertEqual(len(new_manifest["tracks"]), 24)
        lossless = [item["url"] for item in new_manifest["downloads"] if item["url"].endswith(".flac")]
        self.assertEqual(len(lossless), 42)
        self.assertEqual(len(set(lossless)), 42)
        self.assertFalse(list((worker / "public").rglob("*.flac")))
        self.assertFalse((worker / "public/room-tone/downloads").exists())
        self.assertEqual(len(list((worker / "room-media-source").rglob("*.flac"))), 42)
        self.assertEqual(sentinel.read_bytes(), b"do not edit generated output")
        self.assertEqual(list((worker / "dist").iterdir()), [sentinel])
        self.assertFalse((legacy / "room-media-source").exists())
        targets = packaging.site_targets(worker)
        for item in [*new_manifest["downloads"], *new_manifest["videos"]]:
            previous = resolve_url(legacy / "dist/room-tone", item["url"])
            current = resolve_url(worker / "public/room-tone", item["url"], downloads=targets.downloads)
            self.assertEqual(previous.read_bytes(), current.read_bytes(), item["url"])
        movie = "room-tone/media/god-here-room-tone-dialogue-comparison.mp4"
        self.assertFalse((worker / "public" / movie).exists())
        self.assertTrue((worker / "room-media-source" / movie).is_file())
        self.assertTrue((worker / "public/room-tone/catalog.html").is_file())
        self.assertTrue((worker / "public/room-tone/records/site-media-verification.json").is_file())

    def test_worker_checker_never_uses_stale_static_downloads_or_crosses_source_roots(self):
        site = self.site("worker", {"project_id": packaging.SITE_ID, "r2": "ROOM_MEDIA"})
        base = site / "public/room-tone"
        downloads = site / "room-media-source/room-tone/downloads"
        self.write(base / "downloads/stretched/V1.flac", b"stale static copy")
        with self.assertRaisesRegex(ValueError, "Missing"):
            resolve_url(base, "downloads/stretched/V1.flac", downloads=downloads)
        target = self.write(downloads / "stretched/V1.flac", b"registered source")
        self.assertEqual(resolve_url(base, "downloads/stretched/V1.flac", downloads=downloads), target)
        preview = self.write(base / "media/room-V1.m4a")
        self.assertEqual(resolve_url(base, "media/room-V1.m4a", downloads=downloads), preview)
        for url in ["downloads/../../../public/room-tone/media/room-V1.m4a",
                    "downloads/%2e%2e/%2e%2e/%2e%2e/public/room-tone/media/room-V1.m4a",
                    "/room-tone/media/room-V1.m4a", "https://other.example/file.flac"]:
            with self.assertRaises(ValueError):
                resolve_url(base, url, downloads=downloads)

    def test_static_limit_applies_to_public_assets_not_r2_sources_or_generated_dist(self):
        site = self.site("worker", {"project_id": packaging.SITE_ID, "r2": "ROOM_MEDIA"})
        targets = packaging.site_targets(site)
        for path in [site / "dist/generated.bin", targets.downloads / "large.flac"]:
            self.write(path)
            with path.open("r+b") as stream:
                stream.truncate(26 * 1024 ** 2)
        packaging.validate_static_assets(targets)
        bad = self.write(site / "public/room-tone/downloads/stale.FLAC")
        with self.assertRaisesRegex(ValueError, "public assets contain FLACs"):
            packaging.validate_static_assets(targets)
        bad.unlink()
        large_preview = self.write(site / "public/room-tone/media/large.mp4")
        with large_preview.open("r+b") as stream:
            stream.truncate(26 * 1024 ** 2)
        with self.assertRaisesRegex(ValueError, "25 MiB"):
            packaging.validate_static_assets(targets)

    def test_registered_r2_movie_requires_its_source_and_cannot_leak_into_public(self):
        site = self.site("worker", {"project_id": packaging.SITE_ID, "r2": "ROOM_MEDIA"})
        targets = packaging.site_targets(site)
        url = "media/god-here-room-tone-dialogue-comparison.mp4"
        stale = self.write(targets.room / url, b"stale static movie")
        with self.assertRaisesRegex(ValueError, "registered R2 movies"):
            packaging.validate_static_assets(targets)
        with self.assertRaisesRegex(ValueError, "Missing"):
            resolve_url(targets.room, url, downloads=targets.downloads)
        source = self.write(targets.downloads.parent / url, b"registered movie")
        self.assertEqual(resolve_url(targets.room, url, downloads=targets.downloads), source)
        stale.unlink()
        packaging.validate_static_assets(targets)

    def test_download_writer_rejects_paths_outside_the_download_tree(self):
        site = self.site("worker", {"project_id": packaging.SITE_ID, "r2": "ROOM_MEDIA"})
        targets = packaging.site_targets(site)
        source = self.write(self.root / "fixture.flac")
        for path in ["../escape.flac", "/absolute.flac", "sub/../../escape.flac", "stretched/V1.m4a"]:
            with self.assertRaises(ValueError):
                packaging.copy_lossless_download(source, path, targets)
        self.assertFalse((site / "room-media-source").exists())


if __name__ == "__main__":
    unittest.main()
