"""Build portable listening comparisons from the opt-in room refinement outputs.

The production beds keep their measured gain. Solo auditions use a declared,
fixed gain per excerpt; dialogue comparisons share one headroom trim. No
limiter, denoiser, or adaptive volume is added by this packaging step.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from amp.audio import RATE, load_audio, measure, save_audio
from amp.core import sha256, write_json
from amp.soundstage import scene_envelope


VERSIONS = {
    "A": ("A-existing-rack.wav", "Existing room rack", "Original separate band sequences and effects"),
    "B": ("B-shared-schedule.wav", "Shared timing", "One source sequence across all three bands; same effects"),
    "C": ("C-shared-dry.wav", "Shared timing / dry", "Same sequence as B; the room effects are bypassed"),
    "D": ("D-sustained-mid-high.wav", "Sustained middle and air", "Recorded low band; slowly evolving synthesized mid and high"),
    "E": ("E-static-spectrum.wav", "Stationary room texture", "A continuous synthesized texture shaped by the source pauses"),
}


def run(args):
    subprocess.run([str(a) for a in args], check=True, stdout=subprocess.DEVNULL)


def validate_encoded(path, expected_samples, codec):
    """A successful encoder exit alone does not prove a complete audio file."""
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Empty encoded audio: {path.name}")
    decoded = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
                              "-vn", "-ar", str(RATE), "-ac", "2", "-f", "f32le", "-"],
                             capture_output=True, check=True)
    if decoded.stderr.strip() or len(decoded.stdout) % 8:
        raise ValueError(f"Encoded audio failed full decode: {path.name}")
    samples = np.frombuffer(decoded.stdout, dtype="<f4").reshape(-1, 2)
    # AAC's final compressed frame may include presentation-trimmed tail padding.
    padding_limit = 0 if codec == "flac" else 1023
    if not expected_samples <= len(samples) <= expected_samples + padding_limit or not np.isfinite(samples).all():
        raise ValueError(f"Encoded audio is truncated or invalid: {path.name}")
    return {"source_samples": expected_samples, "decoded_samples": len(samples),
            "tail_padding_samples": len(samples) - expected_samples, "full_decode_verified": True}


def encode(path, out, codec="aac", expected_samples=None):
    path, out = Path(path), Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    source_audio = load_audio(path)
    if expected_samples is None:
        expected_samples = len(source_audio)
    if len(source_audio) != expected_samples or not np.isfinite(source_audio).all():
        raise ValueError(f"Source audio has invalid samples or the wrong full-length sample count: {path.name}")
    args = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", path,
            "-map", "0:a:0", "-map_chapters", "-1", "-vn", "-ar", RATE, "-ac", 2]
    if codec == "flac":
        args += ["-c:a", "flac", "-sample_fmt", "s32"]
    else:
        args += ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]
    with tempfile.TemporaryDirectory(prefix=".room-encode-", dir=out.parent) as directory:
        staged = Path(directory) / out.name
        run(args + [staged])
        receipt = validate_encoded(staged, expected_samples, codec)
        staged.replace(out)
    return receipt


def copy_verified_flac(path, out, expected_samples):
    """Publish a retained lossless stem only after validating all its samples."""
    path, out = Path(path), Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".room-copy-", dir=out.parent) as directory:
        staged = Path(directory) / out.name
        shutil.copy2(path, staged)
        receipt = validate_encoded(staged, expected_samples, "flac")
        if sha256(staged) != sha256(path):
            raise ValueError(f"Retained audio changed while copying: {path.name}")
        staged.replace(out)
    return receipt


def levels(x):
    m = measure(x)
    block = RATE // 10
    y = x[:len(x) // block * block].reshape(-1, block, 2)
    rms = np.sqrt(np.mean(y.astype(np.float64) ** 2, axis=(1, 2)))
    db = 20 * np.log10(np.maximum(rms, 1e-12))
    return {"integrated_lufs": m["input_i"], "true_peak_dbtp": m["input_tp"],
            "rms_dbfs": float(20 * np.log10(np.sqrt(np.mean(x.astype(np.float64) ** 2)) + 1e-15)),
            "envelope_100ms_p95_minus_p05_db": float(np.percentile(db, 95) - np.percentile(db, 5))}


def audition(x, out, target_lufs=-24.):
    before = measure(x)
    gain = min(target_lufs - before["input_i"], -1.5 - before["input_tp"])
    if not math.isfinite(gain):
        raise ValueError("Cannot level-match a silent or invalid audition")
    y = x * 10 ** (gain / 20)
    wav = out.with_suffix(".wav")
    save_audio(wav, y)
    encode(wav, out)
    measured = levels(load_audio(out)[:len(x)])
    return {"file": out.name, "fixed_gain_db": gain, "target_lufs": target_lufs,
            "encoded_measurement": measured, "samples_before_encode": len(x)}


def font(size, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    try:
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


def wrapped(draw, text, xy, width, size, fill, line_spacing=10):
    face = font(size)
    words = text.split()
    lines, line = [], ""
    for word in words:
        candidate = (line + " " + word).strip()
        if draw.textbbox((0, 0), candidate, font=face)[2] > width and line:
            lines.append(line)
            line = word
        else:
            line = candidate
    lines.append(line)
    for i, value in enumerate(lines):
        draw.text((xy[0], xy[1] + i * (size + line_spacing)), value, font=face, fill=fill)


def poster(path, frame, key, title, detail, mode, interval):
    bg = Image.new("RGB", (1280, 720), "#101921")
    draw = ImageDraw.Draw(bg)
    white, muted, accent = "#f1eee5", "#a5b3bd", "#bbd9b6"
    draw.text((32, 22), "GOD'S EARS  /  ROOM TONE", font=font(27, True), fill=white)
    draw.text((965, 27), "COMPARISON 2026-10-11", font=font(16), fill=muted)
    bg.paste(frame.resize((896, 504)), (32, 82))
    draw.rectangle((32, 82, 927, 585), outline="#304350", width=2)
    draw.text((964, 75), key, font=font(94, True), fill=accent)
    wrapped(draw, title, (964, 197), 280, 30, white)
    wrapped(draw, detail, (964, 315), 280, 21, muted, 8)
    draw.line((32, 617, 1248, 617), fill="#304350", width=2)
    draw.text((32, 643), mode, font=font(26, True), fill=white)
    draw.text((32, 686), f"Same source interval: {interval}   |   Listening selection remains open", font=font(16), fill=muted)
    bg.save(path)


def make_video(source, artwork, target, seconds, start, moving):
    # Silent, frame-exact parts avoid independent AAC priming at every join.
    if moving:
        command = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", start, "-i", source,
                   "-loop", 1, "-framerate", 30, "-i", artwork,
                   "-filter_complex", "[0:v]scale=896:504,setsar=1[v];[1:v][v]overlay=32:82:shortest=1[out]",
                   "-map", "[out]"]
    else:
        command = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-loop", 1, "-framerate", 30,
                   "-i", artwork, "-map", "0:v:0"]
    run(command + ["-t", seconds, "-r", 30, "-c:v", "libx264", "-preset", "veryfast", "-crf", 21,
                   "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", target])


def concatenate(paths, audio_paths, target):
    listing = paths[0].parent / (target.stem + ".concat.txt")
    listing.write_text("\n".join("file '" + str(p.resolve()).replace("'", "'\\''") + "'" for p in paths) + "\n")
    continuous_audio = paths[0].parent / (target.stem + ".wav")
    joined = np.concatenate([load_audio(path) for path in audio_paths])
    save_audio(continuous_audio, joined)
    run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "concat", "-safe", 0,
         "-i", listing, "-i", continuous_audio, "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", len(joined) / RATE,
         "-movflags", "+faststart", target])


def validate_inputs(source, refinement, audit, baseline, dialogue):
    """Bind the listening labels to the exact verified source and renders."""
    reports = {
        "refinement": refinement / "room-refinement-report.json",
        "audit": audit / "portion-review.json",
        "baseline": baseline / "room-rack-report.json",
    }
    data = {name: json.loads(path.read_text()) for name, path in reports.items()}
    source_hash = sha256(source)
    for name, report in data.items():
        if report.get("source_sha256") != source_hash:
            raise ValueError(f"{name} report belongs to another source")
    if len({report.get("pause_inventory_sha256") for report in data.values()}) != 1:
        raise ValueError("Refinement, audit and baseline inventories disagree")
    reference = data["refinement"]["reference"]
    if sha256(baseline / reference["audio_filename"]) != reference["audio_sha256"]:
        raise ValueError("Recovered reference audio differs from the refinement reference")
    if sha256(reports["baseline"]) != reference["report_sha256"]:
        raise ValueError("Recovered reference report has changed")
    for key, (filename, _, _) in VERSIONS.items():
        candidate = data["refinement"]["candidates"][key]
        if filename != candidate["filename"] or sha256(refinement / filename) != candidate["sha256"]:
            raise ValueError(f"Candidate {key} differs from its verified render")
    context = data["refinement"].get("dialogue_context", {})
    if sha256(dialogue) != context.get("dialogue_sha256"):
        raise ValueError("Dialogue differs from the core used for the refinement context")
    for item in data["audit"]["files"]:
        if sha256(audit / item["path"]) != item["sha256"]:
            raise ValueError(f"Audit artifact changed: {item['path']}")
    return {"source_sha256": source_hash,
            "input_report_sha256": {name: sha256(path) for name, path in reports.items()},
            "pause_inventory_sha256": data["refinement"]["pause_inventory_sha256"],
            "input_identity_verified": True}


def write_player(out, layers, audit_path):
    """Keep the downloadable HTML as a small native gateway to the live Site.

    The earlier embedded player relied on JavaScript in a downloaded HTML preview.
    Hosted comparisons now own interactive playback; direct media stays usable
    without its comparison script. Preserve handled AAC exports for the archive.
    """
    audit = json.loads((audit_path / "portion-review.json").read_text())
    for portion in audit["portions"]:
        encode(audit_path / portion["review_audio"]["path"],
               out / "auditions" / f"{portion['portion_id']}-with-handles.m4a")
    write_hosted_gateway(out / "god-here-room-tone-review.html")


def write_hosted_gateway(path):
    """A script-independent entry point for downloaded-file previews."""
    origin = "https://god-here-five-realities.ajpadavano.chatgpt.site/room-tone/"
    body = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>God’s Ears · room-tone workbench</title>
<style>html{{color-scheme:dark;background:#080808;color:#f3efe7;font:18px/1.6 system-ui}}body{{max-width:900px;padding:24px;margin:auto}}a{{color:#d8b58c}}video{{width:100%;height:auto}}.open{{display:inline-block;border:1px solid #d8b58c;padding:16px;margin:12px 0}}</style>
<h1>Room-tone comparisons are on the project site.</h1>
<p><a class="open" href="{origin}">Open the room-tone workbench →</a></p>
<p>Compare the original A–E treatments, the 112 / 84 / 56 / 28 / 14-second stretched layers, their stacked mixes, and dialogue alone. The same site also provides the assembled 4.42-second source and lossless downloads.</p>
<video controls playsinline preload="none" poster="{origin}media/room-poster.jpg" src="{origin}media/context-V5R.mp4"></video>
<p><a href="{origin}media/context-V5R.mp4">Open the full slowdown stack as an ordinary video</a></p>
<p><a href="{origin}catalog.html">Open all files and native players</a></p>
<p>If this app displays the HTML as a document, use the links above to open the site. No script in this downloaded file is required.</p>
</html>"""
    Path(path).write_text(body)


def export_edit_assets(refinement, audit, baseline, dialogue, out, expected_samples=112 * RATE):
    """Retain source reviews and editable contributions with the comparison."""
    refinement, audit, baseline, dialogue, out = map(Path, (refinement, audit, baseline, dialogue, out))
    report = json.loads((refinement / "room-refinement-report.json").read_text())
    receipts = {}
    for key in ("B", "C", "D", "E"):
        stems = report["candidates"][key].get("stems", {})
        if set(stems) != {"low", "mid", "high"}:
            raise ValueError("Run room refinement with --stems before packaging the editable comparison")
        for band, item in stems.items():
            path = refinement / item["filename"]
            if sha256(path) != item["sha256"]:
                raise ValueError(f"Stem {key}/{band} changed after rendering")
            target = out / "stems" / key / f"{band}.flac"
            receipt = encode(path, target, "flac", expected_samples)
            receipts[str(target.relative_to(out))] = receipt
    shutil.copytree(audit, out / "source-pause-review", dirs_exist_ok=True)
    reference = out / "original-room-rack"
    reference.mkdir(exist_ok=True)
    for band in ("low", "mid", "high"):
        for kind in ("dry-contribution", "fx-return"):
            filename = f"{band}-{kind}.flac"
            receipts[f"original-room-rack/{filename}"] = copy_verified_flac(
                baseline / filename, reference / filename, expected_samples)
    shutil.copy2(baseline / "room-rack-report.json", reference / "room-rack-report.json")
    if dialogue.suffix.lower() == ".flac":
        receipt = copy_verified_flac(dialogue, out / "full-length" / "dialogue-core.flac", expected_samples)
    else:
        receipt = encode(dialogue, out / "full-length" / "dialogue-core.flac", "flac", expected_samples)
    receipts["full-length/dialogue-core.flac"] = receipt
    metadata = out / "reproduction"
    metadata.mkdir(exist_ok=True)
    for filename in ("room-refinement-report.json", "source-spectral-profiles.npz", "stem-sum-validation.json"):
        if (refinement / filename).exists():
            shutil.copy2(refinement / filename, metadata / filename)
    instructions = Path(__file__).resolve().parents[1] / "docs" / "ROOM-REFINEMENT.md"
    if instructions.exists():
        shutil.copy2(instructions, metadata / "ROOM-REFINEMENT.md")
    return {"dialogue_source_sha256": sha256(dialogue),
            "dialogue_file_sha256": sha256(out / "full-length" / "dialogue-core.flac"),
            "editable_audio_verification": receipts}


def archive_delivery(out):
    """Exclude working renders; hash every published member before archiving."""
    out = Path(out)
    target = out / "god-here-room-tone-processing-comparisons.zip"
    manifest_path = out / "delivery-manifest.json"
    def include(path):
        relative = path.relative_to(out)
        return (path.is_file() and path not in (target, manifest_path)
                and not any(part.startswith(".") for part in relative.parts)
                and relative.parts[0] != "working"
                and not (relative.parts[0] == "auditions" and path.suffix == ".wav"))
    files = [p for p in sorted(out.rglob("*")) if include(p)]
    manifest = {"schema_version": "amps.room-delivery.v1", "listening_acceptance": "pending",
                "files": [{"path": str(p.relative_to(out)), "bytes": p.stat().st_size,
                           "sha256": sha256(p)} for p in files]}
    with tempfile.TemporaryDirectory(prefix=".room-package-", dir=out.parent) as directory:
        staged = Path(directory) / target.name
        staged_manifest = Path(directory) / manifest_path.name
        write_json(staged_manifest, manifest)
        with zipfile.ZipFile(staged, "w", allowZip64=True) as archive:
            members = [(path, path.relative_to(out)) for path in files]
            members.append((staged_manifest, Path(manifest_path.name)))
            for path, relative in members:
                compressed = path.suffix.lower() in {".flac", ".m4a", ".mp4", ".mp3", ".npz", ".png"}
                archive.write(path, relative,
                              compress_type=zipfile.ZIP_STORED if compressed else zipfile.ZIP_DEFLATED)
        with zipfile.ZipFile(staged) as archive:
            damaged_member = archive.testzip()
            if damaged_member is not None:
                raise ValueError(f"Archive member failed validation: {damaged_member}")
        staged.replace(target)
        staged_manifest.replace(manifest_path)
    return target


def shared_stem_gain(raw_layers, reference):
    """One gain keeps both isolated contributions and their sum below -1.5 dBTP."""
    layers = list(raw_layers.values())
    summed = sum(layers)
    peak = max(measure(x)["input_tp"] for x in [summed, *layers])
    gain = min(-24 - measure(reference)["input_i"], -1.5 - peak)
    if not math.isfinite(gain):
        raise ValueError("Cannot level-match silent or invalid original stems")
    return gain


def build(source, refinement, audit, baseline, dialogue, out):
    source, refinement, audit, baseline, dialogue, out = map(Path, (source, refinement, audit, baseline, dialogue, out))
    identity = validate_inputs(source, refinement, audit, baseline, dialogue)
    out.mkdir(parents=True, exist_ok=True)
    temp = out / "working"
    temp.mkdir(exist_ok=True)
    length = 112 * RATE
    a, b = 28 * RATE, 58 * RATE
    beds = {k: load_audio(refinement / spec[0]) for k, spec in VERSIONS.items()}
    core = load_audio(dialogue)
    if any(len(x) != length or not np.isfinite(x).all() for x in [core, *beds.values()]):
        raise ValueError("All comparison beds and the recovered dialogue must be finite and exactly 112 seconds")
    envelope = scene_envelope(length)[:, None]
    mixes = {k: core + bed * envelope for k, bed in beds.items()}
    peak = max(measure(x)["input_tp"] for x in [core, *mixes.values()])
    trim = min(0., -1.5 - peak)
    scalar = 10 ** (trim / 20)
    report = {**identity, "dialogue_source_sha256": sha256(dialogue),
              "excerpt_source_seconds": [28, 58], "quick_excerpt_source_seconds": [28, 40],
              "common_dialogue_headroom_trim_db": trim, "listening_acceptance": "pending",
              "dialogue_note": "Recovered 70% DTLN / 30% original shared mixture; original room/activity remain in this core.",
              "versions": {}, "existing_layers": {}}
    for key, bed in beds.items():
        print(f"Packaging {key}", flush=True)
        full = out / "full-length" / f"{key}-room.flac"
        encode(refinement / VERSIONS[key][0], full, "flac")
        mix = mixes[key] * scalar
        mix_wav = temp / f"{key}-dialogue.wav"
        save_audio(mix_wav, mix)
        encode(mix_wav, out / "full-length" / f"{key}-dialogue.m4a")
        room_clip = audition(bed[a:b], out / "auditions" / f"{key}-room-30s.m4a")
        quick = audition(bed[a:a + 12 * RATE], out / "auditions" / f"{key}-room-12s.m4a")
        mix_clip_wav = out / "auditions" / f"{key}-dialogue-30s.wav"
        save_audio(mix_clip_wav, mix[a:b])
        encode(mix_clip_wav, mix_clip_wav.with_suffix(".m4a"))
        report["versions"][key] = {"title": VERSIONS[key][1], "description": VERSIONS[key][2],
                                    "production_room": levels(bed), "dialogue_mix": levels(mix),
                                    "solo_30s": room_clip, "solo_12s": quick,
                                    "dialogue_excerpt_encoded": levels(load_audio(mix_clip_wav.with_suffix('.m4a'))[:b-a]),
                                    "full_room_flac_sha256": sha256(full)}
    save_audio(temp / "dialogue-only.wav", core * scalar)
    encode(temp / "dialogue-only.wav", out / "full-length" / "dialogue-only.m4a")
    save_audio(out / "auditions" / "dialogue-only-30s.wav", core[a:b] * scalar)
    encode(out / "auditions" / "dialogue-only-30s.wav", out / "auditions" / "dialogue-only-30s.m4a")
    layer_names = [f"{band}-{kind}" for band in ("low", "mid", "high") for kind in ("dry-contribution", "fx-return")]
    raw_layers = {name: load_audio(baseline / f"{name}.flac")[a:b] for name in layer_names}
    # One scalar for all six contributions, bounded by headroom at their sum.
    layer_gain = shared_stem_gain(raw_layers, beds['A'][a:b])
    layer_paths = {}
    for name, x in raw_layers.items():
        wav = out / "auditions" / f"original-{name}.wav"
        save_audio(wav, x * 10 ** (layer_gain / 20))
        target = wav.with_suffix(".m4a")
        encode(wav, target)
        layer_paths[name] = target
        report['existing_layers'][name] = {"shared_gain_db": layer_gain, "measurement": levels(load_audio(target)[:b-a])}
    report['original_six_stem_sum_max_abs_error'] = float(np.max(np.abs(sum(raw_layers.values()) - beds['A'][a:b])))
    still = temp / "source-frame.png"
    run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-ss", 28, "-i", source, "-frames:v", 1, still])
    frame = Image.open(still).convert("RGB")
    room_parts, context_parts = [], []
    for key, (_, title, detail) in VERSIONS.items():
        print(f"Rendering review video {key}", flush=True)
        card = temp / f"{key}-room-card.png"
        poster(card, frame, key, title, detail, "ROOM ONLY  /  fixed listening level near -24 LUFS", "00:28-00:40")
        clip = temp / f"{key}-room.mp4"
        make_video(source, card, clip, 12, 28, False)
        room_parts.append(clip)
        context_card = temp / f"{key}-context-card.png"
        poster(context_card, frame, key, title, detail, "DIALOGUE + ROOM  /  production balance", "00:28-00:58")
        context_clip = temp / f"{key}-context.mp4"
        make_video(source, context_card, context_clip, 30, 28, True)
        context_parts.append(context_clip)
    concatenate(room_parts, [out / "auditions" / f"{key}-room-12s.wav" for key in VERSIONS],
                out / "god-here-room-tone-quick-comparison.mp4")
    concatenate(context_parts, [out / "auditions" / f"{key}-dialogue-30s.wav" for key in VERSIONS],
                out / "god-here-room-tone-dialogue-comparison.mp4")
    report["video_audio_assembly"] = "Single continuous AAC encode from exact-length PCM excerpts; video-only parts concatenated at exact frame boundaries"
    write_player(out, layer_paths, audit)
    report.update(export_edit_assets(refinement, audit, baseline, dialogue, out, length))
    write_json(out / "listening-package-report.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "refinement", "audit", "baseline", "dialogue", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--archive", action="store_true", help="Also create the complete listening ZIP")
    args = parser.parse_args()
    build(args.source, args.refinement, args.audit, args.baseline, args.dialogue, args.output)
    if args.archive:
        archive_delivery(args.output)
