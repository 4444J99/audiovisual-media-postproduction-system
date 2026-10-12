"""Receipt binding and full-decoding regressions for room media."""
import contextlib
import json
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
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
        inventory = "b" * 64
        self.verification = {"pause_inventory_sha256": inventory}
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
        self.audit = {"source_sha256": source, "pause_inventory_sha256": inventory, "portions": [{"portion_id": "PAUSE001-01", "handle_start": 4.,
                      "handle_end": 6., "source_start": 4.5, "source_end": 5.5}]}
        self.prior = {"source_sha256": source, "pause_inventory_sha256": inventory}
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
        self.stretch = {"source_sha256": source, "pause_inventory_sha256": inventory, "layers": [{"id": "V112", "period_seconds": 112,
                        "receipts": {"flac": {"sha256": sha256(self.media_paths["downloads/stretched/VL1.flac"])}}}],
                        "stacks": []}
        for field, filename in [("source_reel_raw", "source-reel-raw.wav"),
                                ("source_reel_processed", "source-reel-seam-smoothed.wav")]:
            self.stretch[field] = {"file": filename, "samples_per_channel": 212160,
                                   "sha256": sha256(self.media_paths["records/" + filename])}
        self.preparation = {"source_sha256": source, "pause_inventory_sha256": inventory, "files": {url: sha256(path) for url, path in self.media_paths.items()
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
            "source_sha256": self.prior.get("source_sha256"), "prior_report_sha256": sha256(prior_path),
            "stretch_report_sha256": sha256(stretch_path), "preparation_receipt_sha256": sha256(preparation_path),
            **self.verification})

    def track_fixtures(self):
        self.fixtures()
        picture = self.write("media/source-picture.mp4", b"authenticated source picture")
        self.preparation["files"]["media/source-picture.mp4"] = sha256(picture)
        self.manifest.update(schemaVersion=1, inspectionGainDb=14, defaultTrack="V5R", commonDialogueTrimDb=-2.,
                             source={"url": "media/source-picture.mp4", "duration": 112}, tracks=[])
        self.prior.update(versions={}, dialogue_file_sha256="c" * 64)
        self.verification.update(context_encoding={}, common_dialogue_trim_db=-2.)
        self.stretch.update(layers=[], stacks=[])
        for prefix in ["V", "P"]:
            for period in checker.PERIODS:
                self.stretch["layers"].append({"id": f"{prefix}{period:g}", "period_seconds": period, "receipts": {}})
        for key in ["V1", "V2", "V3", "V4", "V5", "P5", "V5R", "P5R"]:
            self.stretch["stacks"].append({"id": key, "member_ids": [f"{key[0]}{period:g}" for period in checker.PERIODS[:int(key[1])]],
                                          "member_input_kind": "raw_stems" if key.endswith("R") else "calibrated_production_stems",
                                          "receipts": {"wav": {"sha256": sha256(self.write(f"fixture/{key}.wav", key.encode()))}}})
        entries = {entry["id"][0] + "L" + str(checker.PERIODS.index(entry["period_seconds"]) + 1): entry
                   for entry in self.stretch["layers"]}
        entries.update({entry["id"]: entry for entry in self.stretch["stacks"]})
        for key in [*"ABCDE", *entries, "CORE"]:
            track = {"id": key, "title": "Title " + key, "description": "Description " + key,
                     "duration": 112, "sourceStart": 0, "media": {}}
            if key in "ABCDE":
                bed = sha256(self.write(f"fixture/{key}.flac", key.encode()))
                self.prior["versions"][key] = {"title": track["title"], "description": track["description"], "full_room_flac_sha256": bed}
            elif key == "CORE":
                bed = None
            else:
                entry = entries[key]
                track["group"] = "varispeed" if key.startswith("V") else "spectral"
                track["kind"] = "layer" if "period_seconds" in entry else "mix"
                if track["kind"] == "layer":
                    track["periodSeconds"] = entry["period_seconds"]
                    track["title"] = f"{entry['period_seconds']:g}-second layer"
                else:
                    track["stackPeriods"] = [float(member[1:]) for member in entry["member_ids"]]
                    track["title"] = ("Five layers, original relative gain" if key.endswith("R") else
                                      f"{len(track['stackPeriods'])} stacked layer{'s' if len(track['stackPeriods']) != 1 else ''}")
                    bed = entry["receipts"]["wav"]["sha256"]
            modes = ([] if key == "CORE" else ["room", "inspection"]) + ([] if key in entries and "period_seconds" in entries[key] else ["context"])
            for mode in modes:
                url = f"media/{mode}-{key}.{'mp4' if mode == 'context' else 'm4a'}"
                path = self.downloads.parent / url if url in checker.R2_ROOM_MOVIE_URLS else self.base / url
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(("producer output " + url).encode())
                self.media_paths[url] = path
                self.expected[str(path.resolve())] = (112 * checker.RATE, "aac", mode == "context")
                track["media"][mode] = {"url": url, "type": "video/mp4" if mode == "context" else "audio/mp4"}
                if mode == "context":
                    self.verification["context_encoding"][key] = {
                        "sha256": sha256(path), "url": url, "track_id": key, "mode": mode,
                        "source_sha256": self.prior["source_sha256"], "pause_inventory_sha256": self.prior["pause_inventory_sha256"],
                        "source_picture_sha256": sha256(picture), "dialogue_sha256": self.prior["dialogue_file_sha256"],
                        "bed_sha256": bed, "dialogue_gain_db": -2.}
                elif key in entries:
                    entries[key]["receipts"]["production_aac" if mode == "room" else "audition_aac"] = {"sha256": sha256(path)}
                else:
                    self.preparation["files"][url] = sha256(path)
            self.manifest["tracks"].append(track)
        entries["VL1"]["receipts"]["flac"] = {"sha256": sha256(self.media_paths["downloads/stretched/VL1.flac"])}
        # The check() smoke test needs the complete eight-portion public inventory.
        for index in range(2, 9):
            key = f"PAUSE{index:03d}-01"
            url = f"media/{key}-with-handles.m4a"
            path = self.write(url, key.encode())
            self.preparation["files"][url] = sha256(path)
            self.expected[str(path.resolve())] = (2 * checker.RATE, "aac", False)
            self.audit["portions"].append({**self.audit["portions"][0], "portion_id": key})
            self.manifest["pauses"].append({**self.manifest["pauses"][0], "id": key, "url": url})
        self.bind_records()
        self.json("media.json", self.manifest)
        self.write("index.html", b"Room tone")
        for name in ["index.html", "review.html"]:
            (self.base.parent / name).write_text('<a href="room-tone/">Room tone</a>')

    def authenticate_tracks(self):
        return checker.authenticate_track_media(self.base, self.manifest, checker.load_media_receipts(self.base), downloads=self.downloads)

    @contextlib.contextmanager
    def site_layout(self):
        targets = SimpleNamespace(room=self.base, assets=self.base.parent, downloads=self.downloads, storage="r2")
        with mock.patch.object(checker, "site_targets", return_value=targets), mock.patch.object(checker, "validate_static_assets"):
            yield

    def assert_track_trust_failure(self):
        self.json("media.json", self.manifest)
        with self.site_layout(), self.decoders() as (probe, audio, video), \
                mock.patch.object(checker, "video_hash") as packet_hash, self.assertRaises(ValueError):
            checker.check(self.root)
        probe.assert_not_called()
        audio.assert_not_called()
        video.assert_not_called()
        packet_hash.assert_not_called()

    def probe(self, path):
        samples, codec, video = self.expected[str(path.resolve())]
        seconds = samples / checker.RATE
        streams = [{"codec_type": "audio", "codec_name": "pcm_f32le" if codec == "pcm" else codec,
                    "channels": 2, "sample_rate": "48000", "duration": str(seconds), "start_time": "0"}]
        if video:
            streams.append({"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p",
                            "width": 854, "height": 480,
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

    def test_all_sixty_track_outputs_are_bound_then_decoded_with_their_expected_identities(self):
        self.track_fixtures()
        with self.site_layout(), self.decoders(), mock.patch.object(checker, "video_hash", return_value="same picture packets"):
            result = checker.check(self.root)
        self.assertEqual(result["track_count"], 24)
        self.assertEqual(len(result["context_movies"]), 14)
        self.assertEqual(len(result["final_audio_decodes"]), 60)
        _, authenticated = self.authenticate_tracks()
        for row in result["final_audio_decodes"]:
            self.assertEqual(row["sha256"], authenticated[(row["track_id"], row["mode"])][1])
            self.assertTrue(row["full_decode_verified"])

    def test_any_track_byte_replacement_fails_before_any_probe_or_decode(self):
        self.track_fixtures()
        _, authenticated = self.authenticate_tracks()
        for key, (path, _) in authenticated.items():
            with self.subTest(track=key):
                original = path.read_bytes()
                path.write_bytes(b"different render with the same codec and duration")
                self.assert_track_trust_failure()
                path.write_bytes(original)
        picture = self.base / "media/source-picture.mp4"
        picture.write_bytes(b"different source picture")
        self.assert_track_trust_failure()

    def test_swapped_urls_bytes_or_modes_cannot_relabel_a_valid_render(self):
        for variation in ["A/B urls", "A/B bytes", "room/inspection", "context url", "layer url", "missing mode"]:
            with self.subTest(variation=variation):
                self.track_fixtures()
                tracks = {track["id"]: track for track in self.manifest["tracks"]}
                if variation == "A/B urls":
                    tracks["A"]["media"]["room"], tracks["B"]["media"]["room"] = tracks["B"]["media"]["room"], tracks["A"]["media"]["room"]
                elif variation == "A/B bytes":
                    a, b = self.media_paths["media/room-A.m4a"], self.media_paths["media/room-B.m4a"]
                    first, second = a.read_bytes(), b.read_bytes()
                    a.write_bytes(second)
                    b.write_bytes(first)
                elif variation == "room/inspection":
                    tracks["V5"]["media"]["room"] = tracks["V5"]["media"]["inspection"]
                elif variation == "context url":
                    tracks["A"]["media"]["context"] = tracks["B"]["media"]["context"]
                elif variation == "layer url":
                    tracks["VL1"]["media"]["room"] = tracks["VL2"]["media"]["room"]
                else:
                    tracks["CORE"]["media"].clear()
                self.assert_track_trust_failure()

    def test_missing_prepared_stretch_or_context_digest_cannot_be_recreated_from_current_files(self):
        for variation in ["prepared", "stretch", "context", "all contexts", "picture"]:
            with self.subTest(variation=variation):
                self.track_fixtures()
                if variation == "prepared":
                    self.preparation["files"].pop("media/room-A.m4a")
                elif variation == "stretch":
                    self.stretch["layers"][0]["receipts"]["production_aac"].pop("sha256")
                elif variation == "context":
                    self.verification["context_encoding"]["A"].pop("sha256")
                elif variation == "all contexts":
                    self.verification.pop("context_encoding")
                else:
                    self.preparation["files"].pop("media/source-picture.mp4")
                self.bind_records()
                self.assert_track_trust_failure()

    def test_context_receipt_binds_label_mode_picture_dialogue_bed_inventory_and_gain(self):
        for field in ["track_id", "mode", "url", "source_sha256", "source_picture_sha256", "pause_inventory_sha256",
                      "dialogue_sha256", "bed_sha256", "dialogue_gain_db"]:
            for missing in [False, True]:
                with self.subTest(field=field, missing=missing):
                    self.track_fixtures()
                    receipt = self.verification["context_encoding"]["V5"]
                    if missing:
                        receipt.pop(field)
                    else:
                        receipt[field] = -3. if field == "dialogue_gain_db" else "different input or label"
                    self.bind_records()
                    self.assert_track_trust_failure()
        self.track_fixtures()
        self.verification["context_encoding"]["CORE"]["bed_sha256"] = "f" * 64
        self.bind_records()
        self.assert_track_trust_failure()

    def test_receipt_chain_rejects_another_or_missing_source_or_pause_inventory(self):
        for label in ["verification", "preparation", "prior", "stretch", "audit"]:
            for field in ["source_sha256", "pause_inventory_sha256"]:
                for value in [None, "not a digest", "f" * 64]:
                    with self.subTest(label=label, field=field, value=value):
                        self.track_fixtures()
                        record = getattr(self, label)
                        if value is None:
                            record.pop(field, None)
                            # bind_records supplies verification's source by default.
                            if label == "verification" and field == "source_sha256":
                                record[field] = None
                        else:
                            record[field] = value
                        # Preserve the verification source when changing the prior.
                        if label == "prior" and field == "source_sha256":
                            self.verification["source_sha256"] = "a" * 64
                        self.bind_records()
                        self.assert_track_trust_failure()

    def test_manifest_and_report_cannot_change_layer_stack_or_prior_labels(self):
        for variation in ["layer period", "layer title", "layer group", "stack periods", "stack title", "prior title", "prior description",
                          "raw layer id", "duplicate layer", "stack members", "stack member order", "stack input kind"]:
            with self.subTest(variation=variation):
                self.track_fixtures()
                tracks = {track["id"]: track for track in self.manifest["tracks"]}
                if variation == "layer period":
                    tracks["VL1"]["periodSeconds"] = 84
                elif variation == "layer title":
                    tracks["VL1"]["title"] = tracks["VL2"]["title"]
                elif variation == "layer group":
                    tracks["VL1"]["group"] = "spectral"
                elif variation == "stack periods":
                    tracks["V5"]["stackPeriods"] = [112]
                elif variation == "stack title":
                    tracks["V5"]["title"] = tracks["V1"]["title"]
                elif variation.startswith("prior "):
                    tracks["A"][variation.split()[1]] = tracks["B"][variation.split()[1]]
                elif variation == "raw layer id":
                    self.stretch["layers"][0]["id"] = "V84"
                elif variation == "duplicate layer":
                    self.stretch["layers"].append(self.stretch["layers"][0])
                elif variation == "stack members":
                    self.stretch["stacks"][0]["member_ids"] = ["P112"]
                elif variation == "stack member order":
                    self.stretch["stacks"][1]["member_ids"].reverse()
                else:
                    self.stretch["stacks"][0]["member_input_kind"] = "raw_stems"
                self.bind_records()
                self.assert_track_trust_failure()

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
