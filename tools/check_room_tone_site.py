"""Check room-tone Site sources (static or Vinext/R2), without claiming live QA."""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.package_room_refinement import validate_encoded
from tools.package_room_stretch_site import PERIODS, R2_ROOM_MOVIE_URLS, site_targets, validate_static_assets
from amp.core import sha256

RATE = 48000


def run(args):
    return subprocess.run([str(x) for x in args], check=True, capture_output=True).stdout


def probe(path):
    return json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path]))


def video_hash(path):
    return run(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-map", "0:v:0", "-c", "copy", "-f", "hash", "-hash", "sha256", "-"]).decode().strip()


def resolve_url(base, value, *, downloads=None):
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        raise ValueError(f"Room-tone manifest requires ordinary local media URLs: {value}")
    relative = unquote(parsed.path)
    root = base
    if downloads is not None and (relative == "downloads" or relative.startswith("downloads/")):
        root = downloads
        relative = relative[len("downloads"):].removeprefix("/")
    elif downloads is not None and relative in R2_ROOM_MOVIE_URLS:
        root = downloads.parent
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Missing or out-of-route asset: {value}")
    return path


def require_identity(path, expected):
    if not expected or sha256(path) != expected:
        raise ValueError(f"Media receipt missing or identity changed: {path.name}")


def read_bound_record(base, relative, expected):
    path = resolve_url(base, relative)
    require_identity(path, expected)
    return json.loads(path.read_text())


def verify_media_decode(path, samples, codec, *, video=False):
    """Inspect the clock/encoding and fully decode; a matching digest alone is insufficient."""
    if not isinstance(samples, int) or samples <= 0:
        raise ValueError(f"Missing expected sample count: {path.name}")
    data = probe(path)
    audio = [stream for stream in data["streams"] if stream["codec_type"] == "audio"]
    pictures = [stream for stream in data["streams"] if stream["codec_type"] == "video"]
    if (len(audio) != 1 or len(pictures) != int(video) or
            int(audio[0].get("sample_rate", 0)) != RATE or audio[0].get("channels") != 2):
        raise ValueError(f"Invalid media streams: {path.name}")
    stream = audio[0]
    actual_codec = stream.get("codec_name", "")
    if actual_codec != codec and not (codec == "pcm" and actual_codec.startswith("pcm_")):
        raise ValueError(f"Unexpected audio codec: {path.name}")
    seconds = samples / RATE
    duration = float(stream.get("duration", data.get("format", {}).get("duration", "nan")))
    start = float(stream.get("start_time", 0))
    tolerance = .024 if codec == "aac" else 1 / RATE
    if not math.isfinite(duration) or not math.isfinite(start) or abs(duration - seconds) > tolerance or abs(start) > .001:
        raise ValueError(f"Media timeline mismatch: {path.name}")
    # validate_encoded treats FLAC as exact-length PCM. The same zero-padding
    # rule applies to WAV exports, even though their probe codec is pcm_*.
    decoded = validate_encoded(path, samples, "aac" if codec == "aac" else "flac")
    if video:
        picture = pictures[0]
        picture_duration = float(picture.get("duration", "nan"))
        picture_start = float(picture.get("start_time", 0))
        if (picture.get("codec_name") != "h264" or picture.get("pix_fmt") != "yuv420p" or
                picture.get("r_frame_rate") != "30/1" or int(picture.get("nb_frames", -1)) != round(seconds * 30) or
                not math.isfinite(picture_duration) or abs(picture_duration - seconds) > .001 or
                not math.isfinite(picture_start) or abs(picture_start) > .001):
            raise ValueError(f"Comparison picture timeline/encoding mismatch: {path.name}")
        result = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-err_detect", "explode",
                                 "-i", str(path), "-map", "0:v:0", "-f", "null", "-"],
                                capture_output=True, check=True)
        if result.stderr.strip():
            raise ValueError(f"Comparison picture failed full decoding: {path.name}")
    return {**decoded, "audio_codec": actual_codec, "picture_fully_decoded": video}


def receipt_digest(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Missing or invalid receipt digest: " + label)
    return value


def load_media_receipts(base):
    """Follow producer-owned identities, never promote current media hashes to evidence."""
    verification = json.loads(resolve_url(base, "records/site-media-verification.json").read_text())
    preparation = read_bound_record(base, "records/site-preparation.json", verification.get("preparation_receipt_sha256"))
    prior = read_bound_record(base, "records/previous-listening-package-report.json", verification.get("prior_report_sha256"))
    stretch = read_bound_record(base, "records/room-stretch-report.json", verification.get("stretch_report_sha256"))
    if preparation.get("prior_report_sha256") != verification["prior_report_sha256"]:
        raise ValueError("Prepared media and comparison report identities disagree")
    delivery = read_bound_record(base, "records/previous-delivery-manifest.json", preparation.get("comparison_receipt_sha256"))
    if delivery.get("schema_version") != "amps.room-delivery.v1" or not isinstance(delivery.get("files"), list):
        raise ValueError("Invalid prior delivery receipt")
    prior_hashes = {}
    for entry in delivery["files"]:
        name = entry["path"]
        if name in prior_hashes:
            raise ValueError("Ambiguous prior delivery receipt: " + name)
        prior_hashes[name] = entry.get("sha256")
    if prior_hashes.get("listening-package-report.json") != verification["prior_report_sha256"]:
        raise ValueError("Prior delivery receipt belongs to another comparison report")
    audit = read_bound_record(base, "records/source-pause-review/portion-review.json", prior.get("input_report_sha256", {}).get("audit"))
    for field in ["source_sha256", "pause_inventory_sha256"]:
        expected = receipt_digest(verification.get(field), "verification " + field)
        for label, record in [("preparation", preparation), ("prior", prior), ("stretch", stretch), ("source-pause", audit)]:
            if receipt_digest(record.get(field), label + " " + field) != expected:
                raise ValueError("Media receipt identities disagree: " + label + " " + field)
    return {"verification": verification, "preparation": preparation, "prior": prior,
            "stretch": stretch, "audit": audit, "prior_hashes": prior_hashes}


def stretch_track_entries(stretch):
    """Map report IDs to public labels without allowing mislabeled periods or stacks."""
    entries, raw_layers = {}, {}
    for entry in stretch["layers"]:
        raw_id, period = entry["id"], entry["period_seconds"]
        if (period not in PERIODS or raw_id not in {f"V{period:g}", f"P{period:g}"} or
                raw_id in raw_layers):
            raise ValueError("Invalid or duplicate stretch layer identity")
        key = raw_id[0] + "L" + str(PERIODS.index(period) + 1)
        raw_layers[raw_id] = entry
        entries[key] = entry
    for entry in stretch["stacks"]:
        key = entry["id"]
        if key not in {"V1", "V2", "V3", "V4", "V5", "P5", "V5R", "P5R"} or key in entries:
            raise ValueError("Invalid or duplicate stretch stack identity")
        members = [f"{key[0]}{period:g}" for period in PERIODS[:int(key[1])]]
        raw = entry.get("member_input_kind") == "raw_stems"
        if entry.get("member_ids") != members or any(member not in raw_layers for member in members) or raw != key.endswith("R"):
            raise ValueError("Stretch stack membership differs from its label: " + key)
        entries[key] = entry
    return entries


def authenticate_track_media(base, manifest, records, *, downloads=None):
    """Authenticate every label, input and output before any media probe or decode."""
    verification, preparation, prior, stretch = (records[name] for name in ["verification", "preparation", "prior", "stretch"])
    picture_url = "media/source-picture.mp4"
    picture_digest = receipt_digest(preparation.get("files", {}).get(picture_url), "source picture")
    if manifest["source"].get("url") != picture_url or manifest["source"].get("duration") != 112:
        raise ValueError("Source picture URL/clock differs from preparation")
    source = resolve_url(base, picture_url, downloads=downloads)
    require_identity(source, picture_digest)
    entries = stretch_track_entries(stretch)
    context_keys = {"A", "B", "C", "D", "E", "CORE", *[key for key, entry in entries.items() if "period_seconds" not in entry]}
    contexts = verification.get("context_encoding", {})
    if set(contexts) != context_keys:
        raise ValueError("Context producing receipt inventory differs from tracks")
    trim = verification.get("common_dialogue_trim_db")
    if not isinstance(trim, (int, float)) or not math.isfinite(trim) or trim > 0 or manifest.get("commonDialogueTrimDb") != trim:
        raise ValueError("Context dialogue gain differs from producing receipt")
    dialogue = receipt_digest(prior.get("dialogue_file_sha256"), "dialogue core")
    media = {}
    for item in manifest["tracks"]:
        key = item["id"]
        if item.get("duration") != 112 or item.get("sourceStart") != 0:
            raise ValueError("Full-film comparisons must retain the 112-second source clock")
        modes = {"room", "inspection"} if key != "CORE" else set()
        if key in context_keys:
            modes.add("context")
        if set(item["media"]) != modes:
            raise ValueError("Track media modes differ from producing receipts: " + key)
        entry = entries.get(key)
        if key in "ABCDE" and len(key) == 1:
            version = prior.get("versions", {}).get(key, {})
            for field in ["title", "description"]:
                if field not in version or item.get(field) != version[field]:
                    raise ValueError("Prior track label differs from producing receipt: " + key)
            bed = receipt_digest(version.get("full_room_flac_sha256"), "prior bed " + key)
        elif key == "CORE":
            bed = None
        elif entry is None:
            raise ValueError("Track has no producing receipt: " + key)
        elif "period_seconds" in entry:
            if (item.get("periodSeconds") != entry["period_seconds"] or item.get("kind") != "layer" or
                    item.get("title") != f"{entry['period_seconds']:g}-second layer"):
                raise ValueError("Layer period/label differs from producing receipt: " + key)
        else:
            periods = [float(member[1:]) for member in entry["member_ids"]]
            title = ("Five layers, original relative gain" if key.endswith("R") else
                     f"{len(periods)} stacked layer{'s' if len(periods) != 1 else ''}")
            if item.get("stackPeriods") != periods or item.get("kind") != "mix" or item.get("title") != title:
                raise ValueError("Stack periods/label differ from producing receipt: " + key)
            bed = receipt_digest(entry.get("receipts", {}).get("wav", {}).get("sha256"), "stretch bed " + key)
        if entry and item.get("group") != ("varispeed" if key.startswith("V") else "spectral"):
            raise ValueError("Stretch group differs from producing receipt: " + key)
        for mode, medium in item["media"].items():
            url = f"media/{mode}-{key}.{'mp4' if mode == 'context' else 'm4a'}"
            if medium.get("url") != url or medium.get("type") != ("video/mp4" if mode == "context" else "audio/mp4"):
                raise ValueError("Track URL/mode differs from producing receipt: " + key + " " + mode)
            if mode == "context":
                receipt = contexts[key]
                bindings = {"url": url, "track_id": key, "mode": mode,
                            "source_sha256": verification["source_sha256"], "source_picture_sha256": picture_digest,
                            "pause_inventory_sha256": verification["pause_inventory_sha256"],
                            "dialogue_sha256": dialogue, "bed_sha256": bed, "dialogue_gain_db": trim}
                if any(field not in receipt or receipt[field] != value for field, value in bindings.items()):
                    raise ValueError("Context input or label differs from producing receipt: " + key)
                digest = receipt.get("sha256")
            elif entry is not None:
                field = "production_aac" if mode == "room" else "audition_aac"
                digest = entry.get("receipts", {}).get(field, {}).get("sha256")
            else:
                digest = preparation.get("files", {}).get(url)
            receipt_digest(digest, key + " " + mode)
            path = resolve_url(base, url, downloads=downloads)
            require_identity(path, digest)
            media[(key, mode)] = (path, digest)
    return source, media


def verify_nontrack_media(base, manifest, *, downloads=None, records=None):
    """Bind every pause, comparison and audio download to its producing receipt."""
    records = records or load_media_receipts(base)
    preparation, stretch, audit, prior_hashes = (records[name] for name in ["preparation", "stretch", "audit", "prior_hashes"])
    portions = {entry["portion_id"]: entry for entry in audit["portions"]}
    if len(portions) != len(audit["portions"]):
        raise ValueError("Ambiguous source-pause receipt")
    specs = {}
    for item in manifest["pauses"]:
        entry = portions.get(item["id"])
        if entry is None:
            raise ValueError("Pause has no source receipt: " + item["id"])
        duration = entry["handle_end"] - entry["handle_start"]
        for field, expected in [("duration", duration), ("handleStart", entry["handle_start"]),
                                ("sourceStart", entry["source_start"]), ("sourceEnd", entry["source_end"])]:
            if not math.isfinite(item[field]) or abs(item[field] - expected) > 1 / RATE:
                raise ValueError("Source-pause clock differs from receipt: " + item["id"])
        url = f"media/{item['id']}-with-handles.m4a"
        if item["url"] != url:
            raise ValueError("Source-pause URL differs from receipt: " + item["id"])
        specs[url] = (preparation.get("files", {}).get(url), round(duration * RATE), "aac", False)
    for item in manifest["videos"]:
        seconds = {"quick": 60, "dialogue": 150}.get(item["id"])
        name = f"god-here-room-tone-{item['id']}-comparison.mp4"
        url = "media/" + name
        if seconds is None or item["url"] != url:
            raise ValueError("Unknown inherited comparison movie")
        digest = prior_hashes.get(name)
        if not digest or preparation.get("files", {}).get(url) != digest:
            raise ValueError("Comparison movie receipt missing or disagrees: " + name)
        specs[url] = (digest, seconds * RATE, "aac", True)
    for entry in [*stretch["layers"], *stretch["stacks"]]:
        key = entry["id"]
        if "period_seconds" in entry:
            key = key[0] + "L" + str(PERIODS.index(entry["period_seconds"]) + 1)
        specs[f"downloads/stretched/{key}.flac"] = (entry.get("receipts", {}).get("flac", {}).get("sha256"), 112 * RATE, "flac", False)
    for field in ["source_reel_raw", "source_reel_processed"]:
        entry = stretch[field]
        specs["records/" + Path(entry["file"]).name] = (entry.get("sha256"), entry.get("samples_per_channel"), "pcm", False)
    for name, digest in prior_hashes.items():
        if name.endswith(".flac") and name.split("/")[0] in {"full-length", "stems", "original-room-rack"}:
            specs["downloads/previous/" + name] = (digest, 112 * RATE, "flac", False)
        elif name.startswith("auditions/original-") and name.endswith(".m4a"):
            specs["media/" + Path(name).name] = (digest, 30 * RATE, "aac", False)
    decoded = []
    for group in ["pauses", "videos", "downloads"]:
        for item in manifest[group]:
            url = item["url"]
            path = resolve_url(base, url, downloads=downloads)
            if path.suffix.lower() not in {".aac", ".m4a", ".mp3", ".mp4", ".wav", ".flac"}:
                continue
            if url not in specs:
                raise ValueError("No producing receipt for media: " + url)
            digest, samples, codec, is_video = specs[url]
            require_identity(path, digest)
            receipt = verify_media_decode(path, samples, codec, video=is_video)
            decoded.append({"file": url, "sha256": digest, "expected_source_samples": samples, **receipt})
    return decoded


def check(site):
    targets = site_targets(site)
    validate_static_assets(targets)
    base = targets.room
    manifest = json.loads((base / "media.json").read_text())
    if manifest["schemaVersion"] != 1 or manifest["inspectionGainDb"] != 14:
        raise ValueError("Unexpected manifest or inspection gain")
    expected = {"A", "B", "C", "D", "E", "CORE", "V1", "V2", "V3", "V4", "V5", "P5", "V5R", "P5R", *[f"VL{i}" for i in range(1, 6)], *[f"PL{i}" for i in range(1, 6)]}
    keys = [item["id"] for item in manifest["tracks"]]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError(f"Unexpected track inventory: {keys}")
    if manifest["defaultTrack"] not in expected:
        raise ValueError("Unknown default track")
    records = load_media_receipts(base)
    source, authenticated_media = authenticate_track_media(base, manifest, records, downloads=targets.downloads)
    picture_hash = video_hash(source)
    # One full picture decode plus equality of every copied H.264 packet stream.
    result = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(source), "-map", "0:v:0", "-f", "null", "-"], capture_output=True, check=True)
    if result.stderr.strip():
        raise ValueError("Source picture failed full decoding")
    verified, movies, final_audio_decodes = [], [], []
    for item in manifest["tracks"]:
        if item["duration"] != 112 or item["sourceStart"] != 0:
            raise ValueError("Full-film comparisons must retain the 112-second source clock")
        for mode, medium in item["media"].items():
            path, digest = authenticated_media[(item["id"], mode)]
            data = probe(path)
            audio = [s for s in data["streams"] if s["codec_type"] == "audio"]
            if len(audio) != 1 or audio[0]["codec_name"] != "aac" or int(audio[0]["sample_rate"]) != 48000 or audio[0]["channels"] != 2:
                raise ValueError(f"Invalid mobile audio encoding: {path.name}")
            if abs(float(audio[0]["duration"]) - 112) > .024 or abs(float(audio[0].get("start_time", 0))) > .001:
                raise ValueError(f"Audio timeline mismatch: {path.name}")
            decoded = validate_encoded(path, 112 * 48000, "aac")
            final_audio_decodes.append({"file": medium["url"], "sha256": digest,
                                        "track_id": item["id"], "mode": mode, **decoded})
            verified.append(medium["url"])
            if mode == "context":
                video = [s for s in data["streams"] if s["codec_type"] == "video"]
                if len(video) != 1:
                    raise ValueError(f"Context comparison lacks its picture: {path.name}")
                v = video[0]
                if v["codec_name"] != "h264" or v["pix_fmt"] != "yuv420p" or v["width"] != 854 or v["height"] != 480:
                    raise ValueError(f"Unexpected picture encoding: {path.name}")
                if v["r_frame_rate"] != "30/1" or int(v["nb_frames"]) != 3360 or abs(float(v["duration"]) - 112) > .001 or abs(float(v.get("start_time", 0))) > .001:
                    raise ValueError(f"Video clock/frame mismatch: {path.name}")
                if video_hash(path) != picture_hash:
                    raise ValueError(f"Picture stream differs: {path.name}")
                movies.append({"id": item["id"], "file": medium["url"], "frames": 3360, "duration_seconds": 112, "audio_video_start_seconds": 0, "same_picture_packets": True})
    for group in ["pauses", "videos", "downloads"]:
        for item in manifest[group]:
            path = resolve_url(base, item["url"], downloads=targets.downloads)
            verified.append(item["url"])
    nontrack_media_decodes = verify_nontrack_media(base, manifest, downloads=targets.downloads, records=records)
    for prefix in ["V", "P"]:
        periods = [next(item for item in manifest["tracks"] if item["id"] == f"{prefix}L{i}")["periodSeconds"] for i in range(1, 6)]
        if periods != [112, 84, 56, 28, 14]:
            raise ValueError("Layer duration order changed")
    if len(manifest["pauses"]) != 8:
        raise ValueError("The original eight portions must remain accessible")
    for route in ["index.html", "review.html"]:
        if 'href="room-tone/"' not in (targets.assets / route).read_text():
            raise ValueError(f"No discoverable room-tone link in {route}")
    if "data:audio/" in (base / "index.html").read_text():
        raise ValueError("Embedded base64 media reintroduced")
    return {"track_count": len(keys), "unique_media_and_download_urls_verified": len(set(verified)), "context_movies": movies,
            "static_source_root": str(targets.assets), "lossless_source_root": str(targets.downloads), "lossless_storage": targets.storage,
            "final_audio_decodes": final_audio_decodes,
            "nontrack_media_decodes": nontrack_media_decodes,
            "source_picture_fully_decoded": True, "source_picture_packet_sha256": picture_hash,
            "all_context_movies_share_picture_and_source_clock": True,
            "all_static_assets_under_25_mib": True,
            "real_browser_or_device_playback_verified": False,
            "verification_limit": "Managed Sites environment has no control-browser capability; no browser or device playback test was performed.",
            "audio_audition_performed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = check(args.site)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"tracks": receipt["track_count"], "context_movies": len(receipt["context_movies"]), "verified_urls": receipt["unique_media_and_download_urls_verified"]}))


if __name__ == "__main__":
    main()
