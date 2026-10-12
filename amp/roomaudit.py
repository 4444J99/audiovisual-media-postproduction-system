"""Measure and expose the original room-pause pool without certifying silence.

The audit never silently removes a source portion. Metrics describe amplitude and
spectral variation, not the presence or absence of a word, breath, or action.
Original and suggested subregion manifests remain explicitly unaccepted until a
listener records a decision. All times refer to the decoded 48 kHz source clock.
"""
from __future__ import annotations

import copy
import json
import math
import struct
import subprocess
from pathlib import Path

import numpy as np
from scipy import signal

from .audio import RATE, load_audio, save_audio
from .core import run, sha256, write_json


SCHEMA = "amps.room-selection.v1"
MINIMUM_SECONDS = .13
GRID_SECONDS = .01
LIMITATION = ("Algorithmic diagnostics only. Amplitude and spectral statistics do not "
              "establish that speech, breaths, clinks, or other recognizable actions are absent.")


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _on_grid(value):
    return abs(value / GRID_SECONDS - round(value / GRID_SECONDS)) < 1e-6


def inventory_portions(inventory):
    """Flatten only previously inventoried usable portions, with stable IDs."""
    portions = []
    for pause in inventory["pauses"]:
        for index, bounds in enumerate(pause["usable_portions"], 1):
            start = _number(bounds["start"], "source_start")
            end = _number(bounds["end"], "source_end")
            if start < 0 or end - start < MINIMUM_SECONDS - 1e-8:
                raise ValueError("Invalid original source portion")
            if not _on_grid(start) or not _on_grid(end):
                raise ValueError("Original portion is not on the inventory's 10 ms grid")
            portions.append({"portion_id": f"{pause['id']}-{index:02d}", "pause_id": pause["id"],
                             "source_start": start, "source_end": end})
    if not portions or len({p["portion_id"] for p in portions}) != len(portions):
        raise ValueError("Original portion IDs must be nonempty and unique")
    intervals = sorted((p["source_start"], p["source_end"]) for p in portions)
    if any(right > next_left + 1e-8 for (_, right), (next_left, _) in zip(intervals, intervals[1:])):
        raise ValueError("Original portions overlap; duplicate source time would inflate the pool")
    return portions


def resolve_selection(inventory, manifest, *, source_sha256=None, pause_inventory_sha256=None):
    """Validate an explicit keep/exclude/subregion manifest and return selected spans.

    Returns ``[{portion_id, pause_id, start, end, action, status}, ...]`` in original
    inventory order. Excluded portions stay documented in the manifest. Supply the
    exact file hashes at the rendering boundary to bind decisions to both inputs.
    """
    if manifest.get("schema_version") != SCHEMA:
        raise ValueError("Unsupported room selection schema")
    for key in ("source_sha256", "pause_inventory_sha256"):
        value = manifest.get(key, "")
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError(f"Invalid {key}")
    expected_source = source_sha256 or inventory.get("source_sha256")
    if expected_source and manifest["source_sha256"] != expected_source:
        raise ValueError("Selection source hash mismatch")
    if inventory.get("source_sha256") and manifest["source_sha256"] != inventory["source_sha256"]:
        raise ValueError("Selection source differs from inventory source")
    if pause_inventory_sha256 and manifest["pause_inventory_sha256"] != pause_inventory_sha256:
        raise ValueError("Selection inventory hash mismatch")
    originals = inventory_portions(inventory)
    selected = manifest.get("portions")
    if not isinstance(selected, list) or len(selected) != len(originals):
        raise ValueError("Selection must explicitly cover every original portion")
    ids = [p.get("portion_id") for p in selected]
    if len(set(ids)) != len(ids) or set(ids) != {p["portion_id"] for p in originals}:
        raise ValueError("Selection contains duplicate, missing, or unknown portion IDs")
    by_id = {p["portion_id"]: p for p in selected}
    resolved = []
    for original in originals:
        p = by_id[original["portion_id"]]
        if p.get("pause_id") != original["pause_id"]:
            raise ValueError("Selection changes the parent pause identity")
        for key in ("source_start", "source_end"):
            if abs(_number(p.get(key), key) - original[key]) > 1e-8:
                raise ValueError("Selection must preserve original source bounds")
        action, status = p.get("action"), p.get("status")
        if action not in {"keep", "exclude", "subregion"}:
            raise ValueError("Unknown selection action")
        if status not in {"algorithmic_candidate", "human_accepted", "human_rejected"}:
            raise ValueError("Unknown selection status")
        if status.startswith("human_") and any(not isinstance(p.get(k), str) or not p[k].strip()
                                               for k in ("reviewed_by", "reviewed_at", "review_notes")):
            raise ValueError("Human decisions require reviewer, date, and listening notes")
        if status == "human_rejected" and action != "exclude":
            raise ValueError("A human-rejected portion cannot be used")
        if action == "exclude":
            if p.get("selected_start") is not None or p.get("selected_end") is not None:
                raise ValueError("Excluded portions must have null selected bounds")
            if not p.get("reason"):
                raise ValueError("Exclusion requires an explicit reason")
            continue
        start = _number(p.get("selected_start"), "selected_start")
        end = _number(p.get("selected_end"), "selected_end")
        if not original["source_start"] <= start < end <= original["source_end"]:
            raise ValueError("Selected subregion must stay inside its original portion")
        if not _on_grid(start) or not _on_grid(end) or end - start < MINIMUM_SECONDS - 1e-8:
            raise ValueError("Selected spans require a 10 ms grid and at least 130 ms")
        same = abs(start - original["source_start"]) < 1e-8 and abs(end - original["source_end"]) < 1e-8
        if (action == "keep") != same:
            raise ValueError("Use keep for unchanged bounds and subregion for reduced bounds")
        resolved.append({"portion_id": p["portion_id"], "pause_id": p["pause_id"],
                         "start": start, "end": end, "action": action, "status": status})
    if not resolved:
        raise ValueError("Selection leaves no source material")
    return resolved


def _frames(samples, rate):
    width, hop = max(2, round(.020 * rate)), max(1, round(.010 * rate))
    if len(samples) < width:
        return samples[None, :, :], width, hop
    windows = np.lib.stride_tricks.sliding_window_view(samples, width, axis=0)[::hop]
    return windows.transpose(0, 2, 1), width, hop


def _db(amplitude):
    return 20 * np.log10(np.maximum(amplitude, 1e-9))


def portion_metrics(samples, rate=RATE):
    """Level-independent variation and level measurements; no speech classifier."""
    x = np.asarray(samples, dtype=np.float64)
    if x.ndim != 2 or x.shape[1] != 2 or len(x) < 2 or not np.isfinite(x).all():
        raise ValueError("Metrics require finite stereo samples")
    if not isinstance(rate, int) or rate < 100:
        raise ValueError("Invalid sample rate")
    frames, width, hop = _frames(x, rate)
    frame_rms = np.sqrt(np.mean(frames ** 2, axis=(1, 2)))
    frame_db = _db(frame_rms)
    window = np.hanning(frames.shape[1])
    spectra = np.mean(abs(np.fft.rfft(frames * window[None, :, None], axis=1)) ** 2, axis=2)
    frequency = np.fft.rfftfreq(frames.shape[1], 1 / rate)
    shaped = spectra / np.maximum(spectra.sum(axis=1, keepdims=True), 1e-30)
    flux = np.maximum(0, np.diff(shaped, axis=0)).sum(axis=1)
    p = spectra.mean(axis=0)
    energy = max(float(p.sum()), 1e-30)
    rms, peak = float(np.sqrt(np.mean(x ** 2))), float(np.max(abs(x)))
    corr = float(np.corrcoef(x[:, 0], x[:, 1])[0, 1]) if min(x.std(axis=0)) > 1e-12 else None
    band_fraction = {name: round(float(p[(frequency >= lo) & (frequency < hi)].sum()) / energy, 7)
                     for name, lo, hi in [("below_25_hz", 0, 25), ("low_25_180_hz", 25, 180),
                                          ("mid_180_2400_hz", 180, 2400),
                                          ("high_2400_nyquist_hz", 2400, rate / 2 + 1)]}
    return {"duration_seconds": len(x) / rate, "sample_count": len(x),
            "rms_dbfs": round(float(_db(rms)), 4), "peak_dbfs": round(float(_db(peak)), 4),
            "crest_db": round(float(_db(peak) - _db(rms)), 4),
            "frame_rms_p90_p10_db": round(float(np.quantile(frame_db, .9) - np.quantile(frame_db, .1)), 4),
            "frame_rms_peak_above_median_db": round(float(frame_db.max() - np.median(frame_db)), 4),
            "positive_spectral_flux_p95": round(float(np.quantile(flux, .95)) if len(flux) else 0., 6),
            "spectral_centroid_hz": round(float((frequency * p).sum() / energy), 2),
            "stereo_correlation": round(corr, 7) if corr is not None else None,
            "spectral_band_energy_fraction": band_fraction,
            "analysis_frame_seconds": width / rate, "analysis_hop_seconds": hop / rate,
            "analysis_frame_count": len(frames),
            "frame_rms_dbfs": np.round(frame_db, 4).tolist()}


def propose_subregion(samples, portion, *, rate=RATE):
    """Suggest a retained 70% interval only for demonstrably lower level variation.

    At least 250 ms must remain. The p90-p10 frame-level spread must fall by at
    least 1.5 dB without a higher p95 spectral flux or a >3 dB level reduction.
    These deliberately conservative criteria do not certify perceptual calmness.
    """
    a, b = portion["source_start"], portion["source_end"]
    full = samples[round(a * rate):round(b * rate)]
    baseline = portion_metrics(full, rate)
    duration = b - a
    kept = max(.25, math.ceil(duration * .7 / GRID_SECONDS - 1e-8) * GRID_SECONDS)
    if duration - kept < .04 - 1e-8:
        return None
    candidates = []
    for offset in np.arange(0, duration - kept + 1e-8, GRID_SECONDS):
        start, end = round(a + float(offset), 6), round(a + float(offset) + kept, 6)
        m = portion_metrics(samples[round(start * rate):round(end * rate)], rate)
        reduction = baseline["frame_rms_p90_p10_db"] - m["frame_rms_p90_p10_db"]
        flux_ok = m["positive_spectral_flux_p95"] <= baseline["positive_spectral_flux_p95"]
        level_ok = abs(m["rms_dbfs"] - baseline["rms_dbfs"]) <= 3 and m["rms_dbfs"] > -100
        if reduction >= 1.5 and flux_ok and level_ok:
            candidates.append({"selected_start": start, "selected_end": end,
                               "retained_fraction": round(kept / duration, 6), "metrics": m,
                               "frame_rms_spread_reduction_db": round(reduction, 4),
                               "status": "algorithmic_candidate", "listening_acceptance": "pending"})
    return min(candidates, key=lambda c: (c["metrics"]["frame_rms_p90_p10_db"],
                                          c["metrics"]["positive_spectral_flux_p95"],
                                          c["selected_start"])) if candidates else None


def _add_wav_cues(path, positions):
    """Append standard RIFF cue points; the float WAV audio samples stay unchanged."""
    body = struct.pack("<I", len(positions))
    for index, position in enumerate(positions, 1):
        body += struct.pack("<II4sIII", index, position, b"data", 0, 0, position)
    chunk = b"cue " + struct.pack("<I", len(body)) + body
    with open(path, "r+b") as f:
        if f.read(4) != b"RIFF":
            raise ValueError("Cue annotations require RIFF WAV")
        f.seek(0, 2)
        f.write(chunk)
        size = f.tell()
        f.seek(4)
        f.write(struct.pack("<I", size - 8))


def _verify_review_mp3(path, expected_samples):
    """Require a nonempty file and a complete decoded timeline before publishing."""
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("Review MP3 encoder produced an empty file")
    raw = subprocess.check_output(["ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
                                   "-map", "0:a:0", "-ar", str(RATE), "-ac", "2", "-f", "f32le", "-"])
    if len(raw) != expected_samples * 2 * 4:
        raise ValueError("Review MP3 decoded timeline differs from the WAV")
    if not np.isfinite(np.frombuffer(raw, "<f4")).all():
        raise ValueError("Review MP3 decoded audio is nonfinite")
    return {"byte_size": path.stat().st_size, "sample_rate": RATE, "channels": 2,
            "decoded_sample_count": expected_samples,
            "decoded_duration_seconds": expected_samples / RATE, "sample_count_matches_wav": True}


def _diagnostic_png(path, samples, records, rate=RATE):
    # Rendering uses the repository's existing Pillow dependency, not a new GUI.
    from PIL import Image, ImageDraw, ImageFont
    width, row_height, margin, plot_width = 1500, 260, 90, 1320
    canvas = Image.new("RGB", (width, 145 + row_height * len(records)), "#101a25")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
        large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except OSError:
        font = small = large = ImageFont.load_default()
    draw.text((margin, 22), "Original room-tone portions: source audit", font=large, fill="#f0f5fa")
    draw.text((margin, 67), "Teal = original portion; amber = suggested subregion. Handles retain surrounding activity.",
              font=font, fill="#ced8e3")
    draw.text((margin, 96), "Common waveform scale; spectral display -90 to -20 dBFS, 100-12,000 Hz. Listening acceptance pending.",
              font=small, fill="#b6c5d7")
    max_amp = max(float(np.max(abs(samples[round(r['handle_start'] * rate):round(r['handle_end'] * rate)]))) for r in records)
    for index, record in enumerate(records):
        top = 145 + index * row_height
        a, b = record["handle_start"], record["handle_end"]
        x = samples[round(a * rate):round(b * rate)]
        duration = len(x) / rate
        m = record["metrics"]
        draw.text((margin, top), f"{record['portion_id']}  |  {record['source_start']:.2f}-{record['source_end']:.2f}s  |  "
                  f"{m['rms_dbfs']:.1f} dBFS RMS  |  level spread {m['frame_rms_p90_p10_db']:.1f} dB  |  "
                  f"flux {m['positive_spectral_flux_p95']:.3f}", font=font, fill="#e6edf3")
        y0, wh, sh = top + 36, 67, 92
        draw.rectangle((margin, y0, margin + plot_width, y0 + wh), fill="#1a2939")
        mono = x.mean(axis=1)
        for pixel in range(plot_width):
            s, e = int(pixel * len(x) / plot_width), max(1, int((pixel + 1) * len(x) / plot_width))
            cell = mono[s:e]
            if len(cell):
                yy = y0 + wh / 2
                scale = (wh / 2 - 2) / max(max_amp, 1e-9)
                draw.line((margin + pixel, yy - float(cell.max()) * scale,
                           margin + pixel, yy - float(cell.min()) * scale), fill="#9dafc7")
        f, _, z = signal.stft(mono, fs=rate, nperseg=1024, noverlap=768, boundary=None)
        freq_axis = np.geomspace(100, min(12000, rate / 2), sh)[::-1]
        spectrum = 20 * np.log10(np.maximum(abs(z), 1e-9))
        colors = np.empty((sh, spectrum.shape[1]), dtype=float)
        for column in range(spectrum.shape[1]):
            colors[:, column] = np.interp(freq_axis, f, spectrum[:, column])
        value = np.clip((colors + 90) / 70, 0, 1)
        rgb = np.stack((40 + value * 205, 27 + value * 175, 65 + value * 80), axis=2).astype(np.uint8)
        img = Image.fromarray(rgb).resize((plot_width, sh))
        canvas.paste(img, (margin, y0 + wh + 5))
        for key, color in [("source", "#51e2ca"), ("candidate", "#ffc46a")]:
            proposed = record.get("suggested_subregion")
            if key == "candidate" and proposed is None:
                continue
            left, right = ((record["source_start"], record["source_end"]) if key == "source" else
                           (proposed["selected_start"], proposed["selected_end"]))
            for time in (left, right):
                px = margin + round((time - a) / duration * plot_width)
                draw.line((px, y0 - 2, px, y0 + wh + sh + 8), fill=color, width=2)
        for fraction in (0., .25, .5, .75, 1.):
            px = margin + int(fraction * plot_width)
            draw.text((min(px, margin + plot_width - 70), y0 + wh + sh + 15),
                      f"{a + duration * fraction:.2f}s", font=small, fill="#c3d1df")
    canvas.save(path)


def build_audit(source, inventory_path, out, *, handles=1., review_rms_dbfs=-24., mp3=True):
    """Render source review excerpts, exact cue maps, diagnostics, and decisions."""
    handles = _number(handles, "handles")
    review_rms_dbfs = _number(review_rms_dbfs, "review_rms_dbfs")
    if handles < 0 or handles > 10 or not -60 <= review_rms_dbfs <= -6:
        raise ValueError("Use 0-10 second handles and a -60 to -6 dBFS review target")
    source, inventory_path, out = Path(source), Path(inventory_path), Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError("Audit output directory must be empty; preserve earlier audits separately")
    inventory = json.loads(inventory_path.read_text())
    source_hash, inventory_hash = sha256(source), sha256(inventory_path)
    if inventory.get("source_sha256") != source_hash:
        raise ValueError("Source bytes differ from the existing pause inventory")
    portions = inventory_portions(inventory)
    x = load_audio(source)
    if not np.isfinite(x).all():
        raise ValueError("Decoded audio has nonfinite samples")
    if max(p["source_end"] for p in portions) > len(x) / RATE:
        raise ValueError("Inventory extends beyond decoded source")
    out.mkdir(parents=True, exist_ok=True)
    records, clips = [], []
    manifest = {"schema_version": SCHEMA, "source_sha256": source_hash,
                "pause_inventory_sha256": inventory_hash, "listening_acceptance": "pending",
                "purpose": "Preserve the existing pool while making each portion reviewable", "portions": []}
    for portion in portions:
        a, b = portion["source_start"], portion["source_end"]
        start, end = max(0, round((a - handles) * RATE)), min(len(x), round((b + handles) * RATE))
        clip = x[start:end].copy()
        clips.append(clip)
        metrics = portion_metrics(x[round(a * RATE):round(b * RATE)])
        flags = ["listening_review_pending"]
        if b - a < .3:
            flags.append("short_portion_reuse_signature_risk")
        if metrics["frame_rms_p90_p10_db"] >= 3.:
            flags.append("frame_level_spread_at_least_3_db")
        record = {**portion, "handle_start": start / RATE, "handle_end": end / RATE,
                  "metrics": metrics, "flags": flags,
                  "suggested_subregion": propose_subregion(x, portion),
                  "semantic_content_assessed": False, "listening_acceptance": "pending"}
        records.append(record)
        manifest["portions"].append({**portion, "action": "keep", "selected_start": a, "selected_end": b,
                                     "status": "algorithmic_candidate",
                                     "reason": "Retain original screened portion; perceptual qualification pending"})
    peak = max(float(np.max(abs(c))) for c in clips)
    pool_rms = float(np.sqrt(sum(float(np.sum(c.astype(float) ** 2)) for c in clips) /
                             sum(c.size for c in clips)))
    gain_db = min(review_rms_dbfs - float(_db(pool_rms)), -2. - float(_db(peak)), 18.)
    gain = 10 ** (gain_db / 20)
    montage, labels, cues, cursor = [], [], [], 0
    for record, clip in zip(records, clips):
        offset_a = round(record["source_start"] * RATE) - round(record["handle_start"] * RATE)
        offset_b = round(record["source_end"] * RATE) - round(record["handle_start"] * RATE)
        # Fade only the far ends of review handles, never a source portion itself.
        # This prevents montage-to-silence clicks being mistaken for source events.
        review = clip * gain
        fade_in = min(round(.005 * RATE), offset_a)
        fade_out = min(round(.005 * RATE), len(clip) - offset_b)
        if fade_in:
            review[:fade_in] *= (.5 - .5 * np.cos(np.linspace(0, np.pi, fade_in)))[:, None]
        if fade_out:
            review[-fade_out:] *= (.5 + .5 * np.cos(np.linspace(0, np.pi, fade_out)))[:, None]
        name = f"{record['portion_id']}-with-handles-review.wav"
        save_audio(out / name, review)
        _add_wav_cues(out / name, [offset_a, offset_b])
        record["review_audio"] = {"path": name, "sha256": sha256(out / name), "gain_db": gain_db,
                                   "portion_start_sample": offset_a, "portion_end_sample": offset_b,
                                   "portion_start_seconds": offset_a / RATE,
                                   "portion_end_seconds": offset_b / RATE,
                                   "outer_handle_fades_samples": [fade_in, fade_out],
                                   "source_portion_changed_beyond_common_gain": False}
        record["montage"] = {"clip_start_sample": cursor, "clip_end_sample": cursor + len(clip),
                              "portion_start_sample": cursor + offset_a, "portion_end_sample": cursor + offset_b,
                              "clip_start_seconds": cursor / RATE,
                              "portion_start_seconds": (cursor + offset_a) / RATE,
                              "portion_end_seconds": (cursor + offset_b) / RATE}
        labels.append(f"{(cursor + offset_a) / RATE:.9f}\t{(cursor + offset_b) / RATE:.9f}\t"
                      f"{record['portion_id']} | source {record['source_start']:.2f}-{record['source_end']:.2f}s")
        cues.extend([cursor + offset_a, cursor + offset_b])
        montage.extend([review, np.zeros((RATE, 2), np.float32)])
        cursor += len(clip) + RATE
    joined = np.concatenate(montage[:-1])
    wav_path = out / "source-portions-with-handles-review.wav"
    save_audio(wav_path, joined)
    _add_wav_cues(wav_path, cues)
    (out / "source-portions-montage-labels.txt").write_text("\n".join(labels) + "\n")
    mp3_validation = None
    if mp3:
        # Publish only after complete decode validation. A reader never sees a
        # zero-byte or partially encoded replacement of an existing review MP3.
        temporary_mp3 = out / "source-portions-with-handles-review.tmp.mp3"
        try:
            run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", wav_path, "-map", "0:a:0",
                 "-map_metadata", "-1", "-c:a", "libmp3lame", "-b:a", "192k", temporary_mp3])
            mp3_validation = _verify_review_mp3(temporary_mp3, len(joined))
            temporary_mp3.replace(out / "source-portions-with-handles-review.mp3")
        finally:
            temporary_mp3.unlink(missing_ok=True)
    _diagnostic_png(out / "source-portions-diagnostics.png", x, records)
    resolve_selection(inventory, manifest, source_sha256=source_hash, pause_inventory_sha256=inventory_hash)
    write_json(out / "selection-original-pending.json", manifest)
    candidate_manifest = copy.deepcopy(manifest)
    changes = []
    for decision, record in zip(candidate_manifest["portions"], records):
        proposed = record["suggested_subregion"]
        if proposed:
            decision.update(action="subregion", selected_start=proposed["selected_start"],
                            selected_end=proposed["selected_end"], reason=
                            "Algorithmic candidate: >=1.5 dB less frame-level spread with no higher p95 flux; listening pending")
            changes.append(record["portion_id"])
    if changes:
        candidate_manifest["purpose"] = "Optional comparison pool; statistically steadier subregions, not listening-approved"
        resolve_selection(inventory, candidate_manifest, source_sha256=source_hash, pause_inventory_sha256=inventory_hash)
        write_json(out / "selection-subregions-candidate.json", candidate_manifest)
    report = {"schema_version": "amps.room-pause-audit.v1", "source_sha256": source_hash,
              "pause_inventory_sha256": inventory_hash, "sample_rate": RATE, "channels": 2,
              "source_decoded_sample_count": len(x), "original_portion_count": len(portions),
              "original_pool_seconds": round(sum(p["source_end"] - p["source_start"] for p in portions), 6),
              "original_pool_preserved": True, "limitation": LIMITATION, "listening_acceptance": "pending",
              "measurement_gain": 1., "review_common_gain_db": gain_db,
              "review_gain_basis": "One fixed gain across every handled source excerpt; no per-portion normalization",
              "review_edge_fades": "At most 5 ms at far ends of handles only; original portions are not faded",
              "review_only": True, "handles_requested_seconds": handles,
              "montage_gap_seconds": 1., "montage_duration_seconds": len(joined) / RATE,
              "boundary_annotations": "WAV cue points, sample offsets in this JSON, and Audacity label file; no marker sounds mixed in",
              "mp3_timing_note": "Use WAV/sample offsets for precise cuts; MP3 is a listening convenience",
              "review_mp3_validation": mp3_validation,
              "subregion_criterion": {"retained_fraction_minimum": .7, "minimum_seconds": .25,
                                     "minimum_frame_level_spread_reduction_db": 1.5,
                                     "p95_flux_must_not_increase": True,
                                     "maximum_absolute_rms_change_db": 3.},
              "suggested_changed_portions": changes, "portions": records,
              "files": [{"path": p.name, "byte_size": p.stat().st_size, "sha256": sha256(p)} for p in sorted(out.iterdir()) if p.is_file()
                        and p.name != "portion-review.json"]}
    write_json(out / "portion-review.json", report)
    return report
