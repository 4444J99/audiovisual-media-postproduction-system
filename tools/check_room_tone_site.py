"""Check hosted room-tone media contracts without claiming browser playback QA."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.package_room_refinement import validate_encoded


def run(args):
    return subprocess.run([str(x) for x in args], check=True, capture_output=True).stdout


def probe(path):
    return json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path]))


def video_hash(path):
    return run(["ffmpeg", "-nostdin", "-v", "error", "-i", path, "-map", "0:v:0", "-c", "copy", "-f", "hash", "-hash", "sha256", "-"]).decode().strip()


def resolve_url(base, value):
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        raise ValueError(f"Room-tone manifest requires ordinary local media URLs: {value}")
    path = (base / unquote(parsed.path)).resolve()
    if not path.is_relative_to(base.resolve()) or not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Missing or out-of-route asset: {value}")
    return path


def check(site):
    base = site / "dist/room-tone"
    manifest = json.loads((base / "media.json").read_text())
    if manifest["schemaVersion"] != 1 or manifest["inspectionGainDb"] != 14:
        raise ValueError("Unexpected manifest or inspection gain")
    expected = {"A", "B", "C", "D", "E", "CORE", "V1", "V2", "V3", "V4", "V5", "P5", "V5R", "P5R", *[f"VL{i}" for i in range(1, 6)], *[f"PL{i}" for i in range(1, 6)]}
    keys = [item["id"] for item in manifest["tracks"]]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError(f"Unexpected track inventory: {keys}")
    if manifest["defaultTrack"] not in expected:
        raise ValueError("Unknown default track")
    source = resolve_url(base, manifest["source"]["url"])
    source_info = probe(source)
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
            path = resolve_url(base, medium["url"])
            data = probe(path)
            audio = [s for s in data["streams"] if s["codec_type"] == "audio"]
            if len(audio) != 1 or audio[0]["codec_name"] != "aac" or int(audio[0]["sample_rate"]) != 48000 or audio[0]["channels"] != 2:
                raise ValueError(f"Invalid mobile audio encoding: {path.name}")
            if abs(float(audio[0]["duration"]) - 112) > .024 or abs(float(audio[0].get("start_time", 0))) > .001:
                raise ValueError(f"Audio timeline mismatch: {path.name}")
            decoded = validate_encoded(path, 112 * 48000, "aac")
            final_audio_decodes.append({"file": medium["url"], "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), **decoded})
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
            path = resolve_url(base, item["url"])
            verified.append(item["url"])
    for prefix in ["V", "P"]:
        periods = [next(item for item in manifest["tracks"] if item["id"] == f"{prefix}L{i}")["periodSeconds"] for i in range(1, 6)]
        if periods != [112, 84, 56, 28, 14]:
            raise ValueError("Layer duration order changed")
    if len(manifest["pauses"]) != 8:
        raise ValueError("The original eight portions must remain accessible")
    for route in ["index.html", "review.html"]:
        if 'href="room-tone/"' not in (site / "dist" / route).read_text():
            raise ValueError(f"No discoverable room-tone link in {route}")
    if "data:audio/" in (base / "index.html").read_text():
        raise ValueError("Embedded base64 media reintroduced")
    too_large = [p.relative_to(site).as_posix() for p in (site / "dist").rglob("*") if p.is_file() and p.stat().st_size > 25 * 1024 ** 2]
    if too_large:
        raise ValueError(f"Static asset limit exceeded: {too_large}")
    return {"track_count": len(keys), "unique_media_and_download_urls_verified": len(set(verified)), "context_movies": movies,
            "final_audio_decodes": final_audio_decodes,
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
