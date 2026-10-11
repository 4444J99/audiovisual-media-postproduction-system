"""Build portable listening comparisons from the opt-in room refinement outputs.

The production beds keep their measured gain. Solo auditions use a declared,
fixed gain per excerpt; dialogue comparisons share one headroom trim. No
limiter, denoiser, or adaptive volume is added by this packaging step.
"""
from __future__ import annotations

import argparse
import base64
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


def encode(path, out, codec="aac"):
    path, out = Path(path), Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    expected_samples = len(load_audio(path))
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
    return ImageFont.truetype(name, size)


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


def data_audio(path):
    return "data:audio/mp4;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


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
    track_data = {key: {"title": title, "description": detail,
                       "room": data_audio(out / "auditions" / f"{key}-room-30s.m4a"),
                       "mix": data_audio(out / "auditions" / f"{key}-dialogue-30s.m4a")}
                  for key, (_, title, detail) in VERSIONS.items()}
    layer_data = {name: data_audio(path) for name, path in layers.items()}
    audit = json.loads((audit_path / "portion-review.json").read_text())
    pause_data = []
    for portion in audit["portions"]:
        target = out / "auditions" / f"{portion['portion_id']}-with-handles.m4a"
        encode(audit_path / portion["review_audio"]["path"], target)
        pause_data.append({"id": portion["portion_id"], "source_start": portion["source_start"],
                           "source_end": portion["source_end"], "source_offset": portion["handle_start"],
                           "selected_start": portion["review_audio"]["portion_start_seconds"],
                           "selected_end": portion["review_audio"]["portion_end_seconds"],
                           "audio": data_audio(target)})
    image_data = "data:image/png;base64," + base64.b64encode((audit_path / "source-portions-diagnostics.png").read_bytes()).decode("ascii")
    body = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>God's Ears — room-tone review</title><style>
:root{color-scheme:dark;font:17px/1.55 system-ui,sans-serif;background:#101921;color:#f1eee5}body{max-width:980px;margin:0 auto;padding:24px}h1{font-size:clamp(28px,5vw,46px);line-height:1.15;margin:.5em 0}h2{font-size:23px;margin-top:32px}.eyebrow{color:#bbd9b6;letter-spacing:.12em;font-size:12px}p{max-width:75ch}.muted{color:#a5b3bd}button,select,textarea,input{font:inherit;color:inherit;background:#1d2b37;border:1px solid #506273;border-radius:8px;padding:12px}button{cursor:pointer}button:focus-visible,select:focus-visible,textarea:focus-visible{outline:3px solid #bbd9b6;outline-offset:3px}.controls{display:flex;gap:10px;flex-wrap:wrap}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:10px;margin:18px 0}.cards button{text-align:left;min-height:120px}.cards button[aria-pressed=true]{border:2px solid #bbd9b6;background:#253d38}.cards strong{display:block;font-size:22px;color:#bbd9b6}.cards span{font-size:14px}audio{width:100%;margin:15px 0}textarea{display:block;width:100%;box-sizing:border-box;min-height:110px}a{color:#bbd9b6}.panel{padding:18px;border:1px solid #304350;border-radius:12px;margin-top:18px}#status{min-height:3em}small{display:block}.pause-note{border-top:1px solid #304350;padding:12px 0}
</style><p class="eyebrow">GOD'S EARS / COMPARATIVE LISTENING / 11 OCTOBER 2026</p>
<h1>Let the room become still.</h1><p>Five versions of the same room material. A preserves the previous render. B and C test timing and effects. D and E synthesize new texture from the recorded pauses. These are audition candidates; no naturalness or clean-silence acceptance is implied.</p>
<div class="panel"><div class="controls"><label for="mode">Listen to</label><select id="mode"><option value="room">Room alone — raised to a listening level</option><option value="mix">Dialogue plus room — production level</option></select><button id="restart">Restart excerpt</button><button id="core">Dialogue only</button></div>
<p class="muted">Every main excerpt covers source 00:28–00:58. Switching a version keeps the excerpt position. Room-only clips are matched near −24 LUFS with a fixed gain; this is louder than their production level. Dialogue retains the same gain across versions.</p>
<div class="cards" id="choices"></div><p id="status" aria-live="polite"></p><audio id="player" controls preload="metadata"></audio><p id="position" class="muted"></p>
<label for="notes">What draws attention, repeats, or sounds like an action?</label><textarea id="notes" placeholder="Example: C at source 00:35 — still a scraping shape in the middle band."></textarea><button id="save" style="margin-top:12px">Download listening notes</button></div>
<h2>Locate the activity in the earlier rack</h2><p class="muted">These six existing contributions use one shared audition gain. Their relative levels remain intact. They are the original dry contributions and effect returns.</p><div id="layers" class="controls"></div>
<h2>Source pauses</h2><p>Eight portions totaling 4.42 seconds remain available. Each button plays a portion with one second of surrounding context on either side. The selected interval is shown below the player. All excerpts share one fixed review gain; statistical screening has not certified any portion as free of activity.</p><div id="pauses" class="controls"></div><details style="margin-top:18px"><summary>Open the waveform and spectrogram review sheet</summary><img src="__IMAGE__" alt="Eight source portions with selected boundaries, surrounding handles, waveforms and spectrograms" style="width:100%;height:auto;margin-top:14px"></details><p class="muted">Full 112-second lossless beds, underlying stems, full-length dialogue comparisons, cued source-pause WAVs, measurements, and reproduction instructions are in the accompanying ZIP. This self-contained player contains short comparisons and source-pause excerpts. The original room and activity already embedded in the dialogue core remain audible in that control.</p>
<script>const tracks=__TRACKS__;const layers=__LAYERS__;const pauses=__PAUSES__;const core=__CORE__;const player=document.querySelector('#player'),mode=document.querySelector('#mode'),status=document.querySelector('#status');let key='A',active={kind:'candidate',id:'A',mode:'room',source_offset:28};
function position(){const t=player.currentTime||0;let value='Source position '+(active.source_offset+t).toFixed(2)+' s';if(active.kind==='source-portion'){const within=t>=active.selected_start&&t<active.selected_end;value+=' · Selected portion '+active.selected_start.toFixed(2)+'–'+active.selected_end.toFixed(2)+' s in this excerpt · '+(within?'INSIDE SELECTED PORTION':'surrounding handle');}document.querySelector('#position').textContent=value;}
function clearChoice(){document.querySelectorAll('[data-key]').forEach(b=>b.setAttribute('aria-pressed','false'));}
function load(url,text,descriptor,keep=true){const at=keep?(player.currentTime||0):0,playing=!player.paused;player.pause();active=descriptor;player.src=url;player.onloadedmetadata=()=>{player.currentTime=Math.min(at,Math.max(0,player.duration-.05));position();if(playing)player.play().catch(()=>{});};status.textContent=text;position();}
function choose(k,keep=true){keep=keep&&active.source_offset===28&&active.kind!=='source-portion';key=k;document.querySelectorAll('[data-key]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.key===key));load(tracks[k][mode.value],k+' — '+tracks[k].title+'. '+tracks[k].description,{kind:'candidate',id:k,mode:mode.value,source_offset:28},keep);}
Object.entries(tracks).forEach(([k,v])=>{const b=document.createElement('button');b.dataset.key=k;b.setAttribute('aria-pressed','false');const strong=document.createElement('strong');strong.textContent=k;const span=document.createElement('span');span.textContent=v.title;b.append(strong,span);b.onclick=()=>choose(k);document.querySelector('#choices').append(b);});
Object.entries(layers).forEach(([name,url])=>{const b=document.createElement('button');b.textContent=name;b.onclick=()=>{clearChoice();load(url,'Original rack contribution: '+name+'. Shared audition gain.',{kind:'original-contribution',id:name,mode:'shared-solo-gain',source_offset:28},active.source_offset===28&&active.kind!=='source-portion');};document.querySelector('#layers').append(b);});
pauses.forEach(p=>{const b=document.createElement('button');b.textContent=p.id+' · '+p.source_start.toFixed(2)+'–'+p.source_end.toFixed(2)+' s';b.onclick=()=>{clearChoice();load(p.audio,'Source '+p.id+' with surrounding handles. Selected source interval '+p.source_start.toFixed(2)+'–'+p.source_end.toFixed(2)+' s; listening review pending.',{kind:'source-portion',id:p.id,mode:'common-review-gain',source_offset:p.source_offset,selected_start:p.selected_start,selected_end:p.selected_end},false);player.scrollIntoView({behavior:'smooth',block:'center'});};document.querySelector('#pauses').append(b);});
document.querySelector('#core').onclick=()=>{clearChoice();load(core,'Dialogue core alone, at the same production gain used in every dialogue comparison. Original embedded room/activity remain.',{kind:'dialogue-core',id:'dialogue-only',mode:'production',source_offset:28},active.source_offset===28&&active.kind!=='source-portion');};player.ontimeupdate=position;mode.onchange=()=>choose(key);document.querySelector('#restart').onclick=()=>{player.currentTime=0;player.play().catch(()=>{});};document.querySelector('#save').onclick=()=>{const data={project:'god-here',study:'room-tone-refinement-20261011',track:{...active},excerpt_time_seconds:player.currentTime||0,source_time_seconds:active.source_offset+(player.currentTime||0),notes:document.querySelector('#notes').value,recorded_at:new Date().toISOString(),human_acceptance:'unspecified'};const u=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download='god-here-room-listening-notes.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);};choose('A',false);
</script></html>"""
    body = body.replace("__TRACKS__", json.dumps(track_data)).replace("__LAYERS__", json.dumps(layer_data))
    body = body.replace("__PAUSES__", json.dumps(pause_data)).replace("__IMAGE__", image_data)
    body = body.replace("__CORE__", json.dumps(data_audio(out / "auditions" / "dialogue-only-30s.m4a")))
    (out / "god-here-room-tone-review.html").write_text(body)


def export_edit_assets(refinement, audit, baseline, dialogue, out):
    """Retain source reviews and editable contributions with the comparison."""
    refinement, audit, baseline, dialogue, out = map(Path, (refinement, audit, baseline, dialogue, out))
    report = json.loads((refinement / "room-refinement-report.json").read_text())
    for key in ("B", "C", "D", "E"):
        stems = report["candidates"][key].get("stems", {})
        if set(stems) != {"low", "mid", "high"}:
            raise ValueError("Run room refinement with --stems before packaging the editable comparison")
        for band, item in stems.items():
            path = refinement / item["filename"]
            if sha256(path) != item["sha256"]:
                raise ValueError(f"Stem {key}/{band} changed after rendering")
            encode(path, out / "stems" / key / f"{band}.flac", "flac")
    shutil.copytree(audit, out / "source-pause-review", dirs_exist_ok=True)
    reference = out / "original-room-rack"
    reference.mkdir(exist_ok=True)
    for band in ("low", "mid", "high"):
        for kind in ("dry-contribution", "fx-return"):
            filename = f"{band}-{kind}.flac"
            shutil.copy2(baseline / filename, reference / filename)
    shutil.copy2(baseline / "room-rack-report.json", reference / "room-rack-report.json")
    if dialogue.suffix.lower() == ".flac":
        shutil.copy2(dialogue, out / "full-length" / "dialogue-core.flac")
    else:
        encode(dialogue, out / "full-length" / "dialogue-core.flac", "flac")
    metadata = out / "reproduction"
    metadata.mkdir(exist_ok=True)
    for filename in ("room-refinement-report.json", "source-spectral-profiles.npz", "stem-sum-validation.json"):
        if (refinement / filename).exists():
            shutil.copy2(refinement / filename, metadata / filename)
    instructions = Path(__file__).resolve().parents[1] / "docs" / "ROOM-REFINEMENT.md"
    if instructions.exists():
        shutil.copy2(instructions, metadata / "ROOM-REFINEMENT.md")


def archive_delivery(out):
    """Exclude working renders; hash every published member before archiving."""
    out = Path(out)
    target = out / "god-here-room-tone-processing-comparisons.zip"
    manifest_path = out / "delivery-manifest.json"
    def include(path):
        relative = path.relative_to(out)
        return (path.is_file() and path not in (target, manifest_path)
                and relative.parts[0] != "working"
                and not (relative.parts[0] == "auditions" and path.suffix == ".wav"))
    files = [p for p in sorted(out.rglob("*")) if include(p)]
    manifest = {"schema_version": "amps.room-delivery.v1", "listening_acceptance": "pending",
                "files": [{"path": str(p.relative_to(out)), "bytes": p.stat().st_size,
                           "sha256": sha256(p)} for p in files]}
    write_json(manifest_path, manifest)
    with tempfile.TemporaryDirectory(prefix=".room-package-", dir=out.parent) as directory:
        staged = Path(directory) / target.name
        with zipfile.ZipFile(staged, "w", allowZip64=True) as archive:
            for path in [*files, manifest_path]:
                compressed = path.suffix.lower() in {".flac", ".m4a", ".mp4", ".mp3", ".npz", ".png"}
                archive.write(path, path.relative_to(out),
                              compress_type=zipfile.ZIP_STORED if compressed else zipfile.ZIP_DEFLATED)
        with zipfile.ZipFile(staged) as archive:
            damaged_member = archive.testzip()
            if damaged_member is not None:
                raise ValueError(f"Archive member failed validation: {damaged_member}")
        staged.replace(target)
    return target


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
    report = {**identity, "dialogue_file_sha256": sha256(dialogue),
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
    reference_level = measure(beds['A'][a:b])
    layer_gain = min(-24 - reference_level['input_i'], -1.5 - max(measure(x)['input_tp'] for x in raw_layers.values()))
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
    write_json(out / "listening-package-report.json", report)
    export_edit_assets(refinement, audit, baseline, dialogue, out)
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
