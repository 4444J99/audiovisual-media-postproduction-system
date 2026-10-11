"""Package media into the existing god-here room-tone Site's source layout.

This only prepares files in an already opened Sites checkout. The Sites source
workflow owns synchronization and publication. All context movies share one
picture stream and one fixed dialogue gain; no JavaScript audio mix is required.
Legacy static checkouts use dist/. Vinext/R2 checkouts keep browser assets in
public/ and lossless downloads in room-media-source/, outside generated dist/.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from amp.audio import RATE, load_audio, measure, save_audio
from amp.core import sha256
from amp.soundstage import scene_envelope
from tools.package_room_refinement import validate_encoded

DURATION = 112
SAMPLES = DURATION * RATE
INSPECTION_DB = 14.0
PERIODS = [112, 84, 56, 28, 14]
SITE_ID = "appgprj_6ac71699c8fc81919b030dcf9ad112e4"


@dataclass(frozen=True)
class SiteTargets:
    assets: Path
    downloads: Path
    storage: str

    @property
    def room(self):
        return self.assets / "room-tone"


def site_targets(site):
    """Resolve only the two supported source layouts of the existing Site."""
    hosting = json.loads((site / ".openai/hosting.json").read_text())
    static = hosting.get("static") or {}
    if hosting.get("project_id") == SITE_ID and isinstance(static, dict):
        if static.get("directory") == "dist" and not hosting.get("r2"):
            assets = site / "dist"
            return SiteTargets(assets, assets / "room-tone/downloads", "static")
        if not static and hosting.get("r2") == "ROOM_MEDIA":
            return SiteTargets(site / "public", site / "room-media-source/room-tone/downloads", "r2")
    raise ValueError("Expected the existing god-here Site with static.directory='dist' "
                     "or a Worker using r2='ROOM_MEDIA'")


def validate_static_assets(targets):
    """Keep R2 source files out of the browser asset package; check its limits."""
    files = sorted(path for path in targets.assets.rglob("*") if path.is_file())
    if targets.storage == "r2":
        lossless = [path.relative_to(targets.assets).as_posix()
                    for path in files if path.suffix.lower() == ".flac"]
        if lossless:
            raise ValueError("Worker public assets contain FLACs; use room-media-source/room-tone/downloads: "
                             + ", ".join(lossless))
    oversize = [path.relative_to(targets.assets).as_posix()
                for path in files if path.stat().st_size > 25 * 1024 ** 2]
    if oversize:
        raise ValueError("Assets exceed the 25 MiB static-file limit: " + ", ".join(oversize))


def copy_lossless_download(source, relative, targets):
    """Store the FLAC in its source tree while returning its unchanged URL."""
    relative = PurePosixPath(relative)
    if relative.is_absolute() or ".." in relative.parts or relative.suffix != ".flac":
        raise ValueError("Lossless downloads require a relative FLAC path")
    checked_copy(source, targets.downloads.joinpath(*relative.parts))
    return "downloads/" + relative.as_posix()


def run(args):
    result = subprocess.run([str(x) for x in args], capture_output=True, check=True)
    if result.stderr.strip():
        raise RuntimeError(result.stderr.decode(errors="replace"))
    return result


def atomic_encode(source, target, *, gain_db=0.0):
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = len(load_audio(source))
    with tempfile.TemporaryDirectory(prefix=".encode-", dir=target.parent) as temp:
        staged = Path(temp) / target.name
        run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", source,
             "-map", "0:a:0", "-vn", "-map_chapters", "-1", "-af", f"volume={gain_db}dB",
             "-c:a", "aac", "-b:a", "160k", "-ar", RATE, "-ac", 2,
             "-movflags", "+faststart", staged])
        receipt = validate_encoded(staged, expected, "aac")
        decoded = load_audio(staged)[:expected]
        if float(np.max(np.abs(decoded))) >= 1:
            raise ValueError(f"Encoded clipping: {target.name}")
        receipt.update(measure(decoded))
        with staged.open("rb") as handle:
            os.fsync(handle.fileno())
        staged.replace(target)
    return receipt


def checked_copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == target.resolve():
        return
    shutil.copy2(source, target)
    if sha256(source) != sha256(target):
        raise ValueError(f"Copy changed {source.name}")


def prepare(source, prior, site, working):
    targets = site_targets(site)
    validate_static_assets(targets)
    report = json.loads((prior / "listening-package-report.json").read_text())
    if sha256(source) != report["source_sha256"]:
        raise ValueError("The source differs from the earlier room-tone source")
    base = targets.room
    media, records = base / "media", base / "records"
    media.mkdir(parents=True, exist_ok=True)
    records.mkdir(exist_ok=True)
    working.mkdir(parents=True, exist_ok=True)
    picture = media / "source-picture.mp4"
    if not picture.exists():
        with tempfile.TemporaryDirectory(prefix=".picture-", dir=media) as temp:
            stage = Path(temp) / picture.name
            run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", source,
                 "-map", "0:v:0", "-an", "-vf", "scale=854:480,setsar=1",
                 "-t", DURATION, "-r", 30, "-c:v", "libx264", "-preset", "veryfast",
                 "-crf", 27, "-pix_fmt", "yuv420p", "-movflags", "+faststart", stage])
            run(["ffmpeg", "-nostdin", "-v", "error", "-i", stage, "-f", "null", "-"])
            stage.replace(picture)
    run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", 35, "-i", source,
         "-frames:v", 1, "-vf", "scale=854:480,setsar=1", "-q:v", 3, media / "room-poster.jpg"])
    tasks = []
    for key in "ABCDE":
        path = prior / "full-length" / f"{key}-room.flac"
        if sha256(path) != report["versions"][key]["full_room_flac_sha256"]:
            raise ValueError(f"Earlier bed {key} has changed")
        for mode, gain in [("room", 0), ("inspection", INSPECTION_DB)]:
            tasks.append((path, media / f"{mode}-{key}.m4a", gain))
    encodes = {}
    for src, dst, gain in tasks:
        encodes[dst.name] = atomic_encode(src, dst, gain_db=gain)
    for path in sorted((prior / "auditions").glob("PAUSE*-with-handles.m4a")):
        checked_copy(path, media / path.name)
    for path in sorted((prior / "auditions").glob("original-*.m4a")):
        checked_copy(path, media / path.name)
    for name in ["god-here-room-tone-quick-comparison.mp4", "god-here-room-tone-dialogue-comparison.mp4"]:
        checked_copy(prior / name, media / name)
    checked_copy(prior / "source-pause-review/source-portions-diagnostics.png", media / "source-portions-diagnostics.png")
    for path in sorted((prior / "source-pause-review").glob("*")):
        if path.is_file():
            checked_copy(path, records / "source-pause-review" / path.name)
    for path in sorted((prior / "reproduction").glob("*")):
        if path.is_file():
            checked_copy(path, records / "previous-processing" / path.name)
    checked_copy(prior / "listening-package-report.json", records / "previous-listening-package-report.json")
    checked_copy(prior / "god-here-room-tone-processing-notes.md", records / "previous-processing-notes.md")
    (working / "prior-site-encodes.json").write_text(json.dumps(encodes, indent=2) + "\n")
    validate_static_assets(targets)
    return base


def contextual_video(picture, wave, target, scalar):
    with tempfile.TemporaryDirectory(prefix=".context-", dir=target.parent) as temp:
        staged = Path(temp) / target.name
        run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", picture, "-i", wave,
             "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-af", f"volume={scalar:.15g}",
             "-c:a", "aac", "-b:a", "160k", "-ar", RATE, "-ac", 2, "-t", DURATION,
             "-movflags", "+faststart", staged])
        receipt = validate_encoded(staged, SAMPLES, "aac")
        decoded = load_audio(staged)[:SAMPLES]
        receipt.update(measure(decoded))
        if float(np.max(np.abs(decoded))) >= 1:
            raise ValueError(f"Clipping in {target.name}")
        with staged.open("rb") as handle:
            os.fsync(handle.fileno())
        staged.replace(target)
    return receipt


def catalog(manifest):
    esc = html.escape
    out = ["<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
           "<title>God’s Ears · all room-tone files</title><style>html{color-scheme:dark;font:17px/1.6 system-ui;background:#080808;color:#f3efe7}body{max-width:980px;margin:auto;padding:24px}a{color:#d8b58c}video,audio{width:100%;max-height:60vh}summary{padding:16px;cursor:pointer}article{border-top:1px solid #555;padding:16px 0}li{padding:5px 0}button{font:inherit}</style>",
           "<p><a href='./'>← Room-tone workbench</a> · <a href='../review.html'>Sound and picture review</a></p><h1>All room-tone files</h1>",
           "<p>These ordinary media controls and direct links work without the comparison script. Context movies include synchronized full-frame picture and dialogue. Room inspection adds 14 dB; use context to judge the actual scene balance.</p>"]
    for track in manifest["tracks"]:
        out.append(f"<article><h2>{esc(track['id'])} · {esc(track['title'])}</h2><p>{esc(track['description'])}</p><ul>")
        for mode, media in track["media"].items():
            out.append(f"<li><a href='{esc(media['url'], quote=True)}'>{esc(mode.title())} — open media</a></li>")
        out.append("</ul>")
        chosen = track["media"].get("context") or track["media"].get("inspection") or next(iter(track["media"].values()))
        tag = "video" if chosen["type"].startswith("video/") else "audio"
        out.append(f"<details><summary>Show native player</summary><{tag} controls playsinline preload='none' src='{esc(chosen['url'], quote=True)}'></{tag}></details></article>")
    out.append("<h2>Original source portions</h2>")
    for pause in manifest["pauses"]:
        out.append(f"<article><h3>{esc(pause['title'])}</h3><p>Selected source {pause['sourceStart']:.2f}–{pause['sourceEnd']:.2f} s; the file includes surrounding context.</p><audio controls preload='none' src='{esc(pause['url'], quote=True)}'></audio><a href='{esc(pause['url'], quote=True)}'>Open source portion</a></article>")
    out.append("<h2>Comparison films and records</h2><ul>")
    for item in [*manifest["videos"], *manifest["downloads"]]:
        out.append(f"<li><a href='{esc(item['url'], quote=True)}'>{esc(item['title'])}</a></li>")
    out.append("</ul></html>")
    return "\n".join(out)


def finish(source, prior, stretch, site, working):
    targets = site_targets(site)
    validate_static_assets(targets)
    base = targets.room
    media, records = base / "media", base / "records"
    prior_report = json.loads((prior / "listening-package-report.json").read_text())
    report = json.loads((stretch / "room-stretch-report.json").read_text())
    if report["source_sha256"] != prior_report["source_sha256"]:
        raise ValueError("Stretch source differs from recovered room-tone source")
    manifest = {"schemaVersion": 1, "source": {"url": "media/source-picture.mp4", "posterUrl": "media/room-poster.jpg", "duration": DURATION},
                "defaultTrack": "V5R", "inspectionGainDb": INSPECTION_DB, "tracks": [], "pauses": [], "videos": [], "downloads": []}
    beds = {}
    for key in "ABCDE":
        entry = prior_report["versions"][key]
        beds[key] = prior / "full-length" / f"{key}-room.flac"
        manifest["tracks"].append({"id": key, "group": "rack", "kind": "mix", "title": entry["title"], "description": entry["description"],
                                   "sourceStart": 0, "duration": DURATION, "media": {}})
    # The rendering report owns filenames and gains; no guessed filesystem glob.
    for entry in [*report["layers"], *report["stacks"]]:
        raw_id = entry["id"]
        is_layer = "period_seconds" in entry
        if is_layer:
            prefix = "V" if raw_id.startswith("V") else "P"
            key = prefix + "L" + str(PERIODS.index(entry["period_seconds"]) + 1)
            title = f"{entry['period_seconds']:g}-second layer"
            description = ("Literal slowdown; pitch falls with speed. " if prefix == "V" else "Spectral stretch retains the frequency range and generates new phase. ") + "Repeated to fill the 112-second film."
            track = {"id": key, "group": "varispeed" if prefix == "V" else "spectral", "kind": "layer", "title": title, "description": description,
                     "periodSeconds": entry["period_seconds"], "sourceStart": 0, "duration": DURATION, "media": {}}
        else:
            key = raw_id
            periods = [float(str(x)[1:]) for x in entry["member_ids"]]
            raw_stack = entry.get("member_input_kind") == "raw_stems"
            title = ("Five layers, original relative gain" if raw_stack else f"{len(periods)} stacked layer{'s' if len(periods) != 1 else ''}")
            balance = "Original source-level layers at equal gain; one final loudness adjustment." if raw_stack else "Individually calibrated layers, with one final loudness adjustment."
            track = {"id": key, "group": "varispeed" if key.startswith("V") else "spectral", "kind": "mix", "title": title,
                     "description": " + ".join(f"{x:g} s" for x in periods) + ". " + balance,
                     "stackPeriods": periods, "sourceStart": 0, "duration": DURATION, "media": {}}
        for mode, field in [("room", "production_aac"), ("inspection", "audition_aac")]:
            checked_copy(stretch / entry[field], media / f"{mode}-{key}.m4a")
            track["media"][mode] = {"url": f"media/{mode}-{key}.m4a", "type": "audio/mp4"}
        lossless = stretch / entry["stem_flac"]
        lossless_url = copy_lossless_download(lossless, f"stretched/{key}.flac", targets)
        manifest["downloads"].append({"title": f"{key} · {track['title']} · lossless FLAC", "url": lossless_url})
        if not is_layer:
            beds[key] = stretch / entry["stem_wav"]
        manifest["tracks"].append(track)
    for track in manifest["tracks"]:
        if track["id"] in "ABCDE" and len(track["id"]) == 1:
            for mode in ["room", "inspection"]:
                track["media"][mode] = {"url": f"media/{mode}-{track['id']}.m4a", "type": "audio/mp4"}
    manifest["tracks"].append({"id": "CORE", "group": "control", "kind": "mix", "title": "Dialogue only", "description": "The same recovered 70% enhanced / 30% original dialogue core, with no added room bed.", "sourceStart": 0, "duration": DURATION, "media": {}})
    core_path = prior / "full-length/dialogue-core.flac"
    if sha256(core_path) != prior_report["dialogue_file_sha256"]:
        raise ValueError("Dialogue core changed")
    core = load_audio(core_path)
    if len(core) != SAMPLES or not np.isfinite(core).all():
        raise ValueError("Invalid dialogue core")
    envelope = scene_envelope(SAMPLES)[:, None]
    mix_paths = {}
    peak = measure(core)["input_tp"]
    for key, path in beds.items():
        bed = load_audio(path)
        if len(bed) != SAMPLES or not np.isfinite(bed).all():
            raise ValueError(f"Invalid bed {key}")
        mixed = core + bed * envelope
        peak = max(peak, measure(mixed)["input_tp"])
        mix_paths[key] = working / f"context-{key}.wav"
        save_audio(mix_paths[key], mixed)
    mix_paths["CORE"] = core_path
    trim_db = min(0.0, -1.5 - peak)
    scalar = 10 ** (trim_db / 20)
    receipts = {}
    for key, path in mix_paths.items():
        receipts[key] = contextual_video(media / "source-picture.mp4", path, media / f"context-{key}.mp4", scalar)
    for track in manifest["tracks"]:
        key = track["id"]
        if key in mix_paths:
            track["media"]["context"] = {"url": f"media/context-{key}.mp4", "type": "video/mp4"}
    audit = json.loads((prior / "source-pause-review/portion-review.json").read_text())
    for entry in audit["portions"]:
        key = entry["portion_id"]
        manifest["pauses"].append({"id": key, "title": key, "url": f"media/{key}-with-handles.m4a", "duration": entry["handle_end"] - entry["handle_start"],
                                  "sourceStart": entry["source_start"], "sourceEnd": entry["source_end"], "handleStart": entry["handle_start"]})
    for key, title, seconds in [("quick", "Earlier A–E room-only comparison", 60), ("dialogue", "Earlier A–E dialogue comparison", 150)]:
        manifest["videos"].append({"id": key, "title": title, "url": f"media/god-here-room-tone-{key}-comparison.mp4", "description": f"{seconds} seconds. Earlier room-only excerpts use their original louder inspection level."})
    for path in sorted((media).glob("original-*.m4a")):
        manifest["downloads"].append({"title": "Earlier rack contribution: " + path.stem.removeprefix("original-"), "url": f"media/{path.name}"})
    for folder in ["full-length", "stems", "original-room-rack"]:
        for path in sorted((prior / folder).rglob("*.flac")):
            if any(part.startswith(".") for part in path.relative_to(prior).parts):
                continue
            url = copy_lossless_download(path, PurePosixPath("previous") / path.relative_to(prior), targets)
            manifest["downloads"].append({"title": "Earlier lossless asset · " + path.relative_to(prior).as_posix(), "url": url})
    checked_copy(stretch / "room-stretch-report.json", records / "room-stretch-report.json")
    for field in ["source_reel_raw", "source_reel_processed"]:
        path = stretch / report[field]["file"]
        checked_copy(path, records / path.name)
    atomic_encode(stretch / report["source_reel_raw"]["file"], media / "source-reel-raw.m4a")
    manifest["downloads"] += [
        {"title": "4.42-second source reel, exact original portions (WAV)", "url": "records/" + Path(report["source_reel_raw"]["file"]).name},
        {"title": "4.42-second source reel, joins smoothed for stretching (WAV)", "url": "records/" + Path(report["source_reel_processed"]["file"]).name},
        {"title": "Stretch construction and measurements", "url": "records/room-stretch-report.json"},
        {"title": "Earlier processing notes", "url": "records/previous-processing-notes.md"},
        {"title": "Earlier A–E measurements", "url": "records/previous-listening-package-report.json"},
        {"title": "Source portions: waveform and spectrum", "url": "media/source-portions-diagnostics.png"}]
    manifest["commonDialogueTrimDb"] = trim_db
    (base / "media.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (base / "catalog.html").write_text(catalog(manifest))
    receipt = {"source_sha256": sha256(source), "common_dialogue_trim_db": trim_db, "identical_dialogue_gain": True,
               "scene_envelope_seconds": [5.033333, 107.166667], "scene_envelope_fade_seconds": 0.35,
               "context_encoding": receipts, "browser_playback_verified": False, "listening_acceptance": "pending"}
    (records / "site-media-verification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    validate_static_assets(targets)
    print(json.dumps({"tracks": len(manifest["tracks"]), "context_movies": len(receipts), "common_dialogue_trim_db": trim_db,
                      "output": str(base), "lossless_output": str(targets.downloads), "lossless_storage": targets.storage}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "finish"])
    for name in ["source", "prior", "stretch", "site", "working"]:
        parser.add_argument("--" + name, type=Path, required=name != "stretch")
    args = parser.parse_args()
    if args.phase == "prepare":
        print(prepare(args.source, args.prior, args.site, args.working))
    else:
        if args.stretch is None:
            parser.error("finish requires --stretch")
        finish(args.source, args.prior, args.stretch, args.site, args.working)


if __name__ == "__main__":
    main()
