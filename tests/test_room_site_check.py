"""Receipt binding and full-decoding regressions for non-track room media."""
import contextlib
import json
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest import mock

from amp.core import sha256
from tools import check_room_tone_site as checker


class RoomSiteCheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="room-site-check-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.base = self.root / "public/room-tone"
        self.downloads = self.root / "room-media-source/room-tone/downloads"

    def write(self, relative, data):
        path = self.base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def json(self, relative, value):
        return self.write(relative, json.dumps(value).encode())

    def fixtures(self):
        source = "a" * 64
        self.manifest = {
            "pauses": [{"id": "PAUSE001-01", "url": "media/PAUSE001-01-with-handles.m4a",
                        "duration": 2., "handleStart": 4., "sourceStart": 4.5, "sourceEnd": 5.5}],
            "videos": [{"id": "dialogue", "url": "media/god-here-room-tone-dialogue-comparison.mp4"}],
            "downloads": [{"url": url} for url in [
                "downloads/previous/full-length/A-room.flac",
                "downloads/previous/original-room-rack/low-fx-return.flac",
                "downloads/stretched/VL1.flac", "media/original-low-fx-return.m4a",
                "records/source-reel-raw.wav", "records/source-reel-seam-smoothed.wav",
                "records/notes.md"]],
        }
        self.expected = {}
        self.media_paths = {}
        for group in self.manifest.values():
            for item in group:
                url = item["url"]
                if url.startswith("downloads/"):
                    path = self.downloads / url.removeprefix("downloads/")
                elif url in checker.R2_ROOM_MOVIE_URLS:
                    path = self.downloads.parent / url
                else:
                    path = self.base / url
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(url.encode())
                if path.suffix == ".md":
                    continue
                samples = (2 if "PAUSE" in url else 150 if path.suffix == ".mp4" else
                           4.42 if path.suffix == ".wav" else 30 if path.suffix == ".m4a" else 112) * checker.RATE
                codec = "flac" if path.suffix == ".flac" else "pcm" if path.suffix == ".wav" else "aac"
                self.expected[str(path.resolve())] = (round(samples), codec, path.suffix == ".mp4")
                self.media_paths[url] = path
        self.audit = {"source_sha256": source, "portions": [{"portion_id": "PAUSE001-01", "handle_start": 4.,
                      "handle_end": 6., "source_start": 4.5, "source_end": 5.5}]}
        self.prior = {"source_sha256": source}
        self.delivery = {"schema_version": "amps.room-delivery.v1", "files": []}
        for url, path in self.media_paths.items():
            if url.startswith("downloads/previous/"):
                name = url.removeprefix("downloads/previous/")
            elif "original-" in url:
                name = "auditions/" + path.name
            elif path.suffix == ".mp4":
                name = path.name
            else:
                continue
            self.delivery["files"].append({"path": name, "sha256": sha256(path)})
        self.stretch = {"source_sha256": source, "layers": [{"id": "V112", "period_seconds": 112,
                        "receipts": {"flac": {"sha256": sha256(self.media_paths["downloads/stretched/VL1.flac"])}}}],
                        "stacks": []}
        for field, filename in [("source_reel_raw", "source-reel-raw.wav"),
                                ("source_reel_processed", "source-reel-seam-smoothed.wav")]:
            self.stretch[field] = {"file": filename, "samples_per_channel": 212160,
                                   "sha256": sha256(self.media_paths["records/" + filename])}
        self.preparation = {"source_sha256": source, "files": {url: sha256(path) for url, path in self.media_paths.items()
                            if "PAUSE" in url or path.suffix == ".mp4"}}
        self.bind_records()

    def bind_records(self):
        audit_path = self.json("records/source-pause-review/portion-review.json", self.audit)
        self.prior["input_report_sha256"] = {"audit": sha256(audit_path)}
        prior_path = self.json("records/previous-listening-package-report.json", self.prior)
        self.delivery["files"] = [entry for entry in self.delivery["files"] if entry["path"] != "listening-package-report.json"]
        self.delivery["files"].append({"path": "listening-package-report.json", "sha256": sha256(prior_path)})
        delivery_path = self.json("records/previous-delivery-manifest.json", self.delivery)
        self.preparation.update(prior_report_sha256=sha256(prior_path), comparison_receipt_sha256=sha256(delivery_path))
        preparation_path = self.json("records/site-preparation.json", self.preparation)
        stretch_path = self.json("records/room-stretch-report.json", self.stretch)
        self.json("records/site-media-verification.json", {
            "source_sha256": self.prior["source_sha256"], "prior_report_sha256": sha256(prior_path),
            "stretch_report_sha256": sha256(stretch_path), "preparation_receipt_sha256": sha256(preparation_path)})

    def probe(self, path):
        samples, codec, video = self.expected[str(path.resolve())]
        seconds = samples / checker.RATE
        streams = [{"codec_type": "audio", "codec_name": "pcm_f32le" if codec == "pcm" else codec,
                    "channels": 2, "sample_rate": "48000", "duration": str(seconds), "start_time": "0"}]
        if video:
            streams.append({"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p",
                            "r_frame_rate": "30/1", "nb_frames": str(round(seconds * 30)),
                            "duration": str(seconds), "start_time": "0"})
        return {"streams": streams, "format": {"duration": str(seconds)}}

    @contextlib.contextmanager
    def decoders(self):
        with mock.patch.object(checker, "probe", side_effect=self.probe) as probe, \
                mock.patch.object(checker, "validate_encoded", side_effect=lambda _p, samples, _c:
                                  {"full_decode_verified": True, "decoded_samples": samples}) as audio, \
                mock.patch.object(checker.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"", b"")) as video:
            yield probe, audio, video

    def verify(self):
        return checker.verify_nontrack_media(self.base, self.manifest, downloads=self.downloads)

    def test_every_nontrack_media_asset_is_receipt_checked_probed_and_fully_decoded(self):
        self.fixtures()
        with self.decoders() as (probe, audio, video):
            receipts = self.verify()
        self.assertEqual(len(receipts), 8)
        self.assertEqual(probe.call_count, 8)
        self.assertEqual(audio.call_count, 8)
        self.assertEqual(video.call_count, 1)
        for receipt in receipts:
            path = self.media_paths[receipt["file"]]
            self.assertEqual(receipt["sha256"], sha256(path))
            self.assertTrue(receipt["full_decode_verified"])
        movie = next(row for row in receipts if row["file"].endswith(".mp4"))
        self.assertTrue(movie["picture_fully_decoded"])
        self.assertIn("room-media-source", str(self.media_paths[movie["file"]]))

    def test_changed_pause_movie_flac_and_wav_fail_before_decoding_the_changed_file(self):
        self.fixtures()
        for url in list(self.media_paths):
            with self.subTest(url=url):
                self.fixtures()
                path = self.media_paths[url]
                path.write_bytes(b"same-format replacement")
                with self.decoders() as (probe, _, _), self.assertRaisesRegex(ValueError, "identity changed"):
                    self.verify()
                self.assertNotIn(mock.call(path.resolve()), probe.call_args_list)

    def test_missing_receipts_fail_closed_for_pause_comparison_and_lossless(self):
        for group in ["pause", "movie", "prior-flac", "stretch-flac", "reel"]:
            with self.subTest(group=group):
                self.fixtures()
                if group == "pause":
                    self.preparation["files"].pop("media/PAUSE001-01-with-handles.m4a")
                elif group in {"movie", "prior-flac"}:
                    name = "god-here-room-tone-dialogue-comparison.mp4" if group == "movie" else "full-length/A-room.flac"
                    self.delivery["files"] = [entry for entry in self.delivery["files"] if entry["path"] != name]
                elif group == "stretch-flac":
                    self.stretch["layers"][0]["receipts"]["flac"].pop("sha256")
                else:
                    self.stretch["source_reel_raw"].pop("samples_per_channel")
                self.bind_records()
                with self.decoders(), self.assertRaisesRegex(ValueError, "receipt|sample count"):
                    self.verify()

    def test_missing_or_replaced_bound_record_is_not_an_optional_check(self):
        for relative in ["records/site-preparation.json", "records/previous-delivery-manifest.json",
                         "records/previous-listening-package-report.json", "records/room-stretch-report.json"]:
            for absent in [True, False]:
                with self.subTest(relative=relative, absent=absent):
                    self.fixtures()
                    path = self.base / relative
                    path.unlink() if absent else path.write_text("{}")
                    with self.decoders(), self.assertRaisesRegex(ValueError, "Missing|identity changed"):
                        self.verify()

    def test_pause_clock_and_audio_probe_must_match_the_recorded_portion(self):
        self.fixtures()
        self.manifest["pauses"][0]["duration"] = 1.
        with self.decoders(), self.assertRaisesRegex(ValueError, "clock differs"):
            self.verify()
        for field, value in [("duration", "1"), ("duration", "nan"), ("start_time", "nan"),
                             ("codec_name", "mp3"), ("sample_rate", "44100"), ("channels", 1)]:
            with self.subTest(field=field):
                self.fixtures()
                data = self.probe(self.media_paths["media/PAUSE001-01-with-handles.m4a"])
                data["streams"][0][field] = value
                with self.decoders(), mock.patch.object(checker, "probe", return_value=data), self.assertRaises(ValueError):
                    self.verify()

    def test_movie_video_decode_error_cannot_be_reported_as_verified(self):
        self.fixtures()
        with self.decoders() as (_, _, video):
            video.return_value.stderr = b"corrupt packet at end of stream"
            with self.assertRaisesRegex(ValueError, "picture failed full decoding"):
                self.verify()

    def test_real_truncated_aac_and_lossless_audio_fail_even_when_probe_claims_expected_duration(self):
        source = self.root / "short.wav"
        with wave.open(str(source), "wb") as stream:
            stream.setnchannels(2)
            stream.setsampwidth(2)
            stream.setframerate(checker.RATE)
            stream.writeframes(b"\0" * (4800 * 4))
        flac = self.root / "short.flac"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source), str(flac)], check=True)
        aac = self.root / "short.m4a"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(source), "-c:a", "aac", str(aac)], check=True)
        for path, codec, actual_codec in [(source, "pcm", "pcm_s16le"), (flac, "flac", "flac"), (aac, "aac", "aac")]:
            with self.subTest(codec=codec):
                data = {"streams": [{"codec_type": "audio", "codec_name": actual_codec,
                                     "sample_rate": "48000", "channels": 2, "duration": ".2", "start_time": "0"}]}
                with mock.patch.object(checker, "probe", return_value=data), self.assertRaisesRegex(ValueError, "truncated or invalid"):
                    checker.verify_media_decode(path, 9600, codec)


if __name__ == "__main__":
    unittest.main()
