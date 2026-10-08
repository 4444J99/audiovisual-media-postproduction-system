#!/usr/bin/env python3
"""Download pinned DTLN weights and render matched, reversible trials."""
import argparse
import json
from pathlib import Path
import sys
import time
import urllib.request

import numpy as np
from scipy import signal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from amp.audio import load_audio, save_audio, speech_mask, measure, match, RATE
from amp.core import run, sha256, write_json
from amp.neural_audio import (enhance_48k, verify_models, MODEL_REVISION,
                              MODEL_SHA256, MODEL_RATE, STREAM_OFFSET)


def acquire(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name in [*MODEL_SHA256, "LICENSE"]:
        destination = directory / name
        if destination.exists():
            continue
        repository_path = "pretrained_model/" + name if name.endswith(".onnx") else name
        url = f"https://raw.githubusercontent.com/breizhn/DTLN/{MODEL_REVISION}/{repository_path}"
        with urllib.request.urlopen(url, timeout=90) as response:
            payload = response.read()
        destination.write_bytes(payload)
    verify_models(directory)


def lags(reference, candidate):
    result = []
    for center in [8.5, 37, 58, 86, 104.5]:
        a, b = round((center - .6) * RATE), round((center + .6) * RATE)
        x = signal.resample_poly(reference[a:b].mean(axis=1), 1, 6)
        y = signal.resample_poly(candidate[a:b].mean(axis=1), 1, 6)
        corr = signal.correlate(y - y.mean(), x - x.mean(), mode="full", method="fft")
        shifts = signal.correlation_lags(len(y), len(x), mode="full")
        allowed = np.abs(shifts) <= 640
        peak = int(shifts[allowed][np.argmax(corr[allowed])])
        result.append({"source_center_s": center, "lag_at_8k_samples": peak,
                       "lag_ms": peak / 8})
    return result


def write_evaluation(out, name, samples, mask, target, suffix=""):
    matched, before, gain_db = match(samples, mask, target)
    filename = f"candidate-{name}{suffix}.wav"
    save_audio(out / filename, matched)
    run(["ffmpeg", "-v", "error", "-y", "-i", out / filename,
         "-c:a", "flac", "-sample_fmt", "s32", out / filename.replace(".wav", ".flac")])
    return matched, {"file": filename, "gain_db": gain_db,
                     "before_active": before, "after_active": measure(matched[mask]),
                     "full_program": measure(matched), "samples": len(matched),
                     "sha256": sha256(out / filename)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--transcript", required=True)
    parser.add_argument("--dsp-candidate", required=True,
                        help="Unmatched conservative DSP WAV for a fair comparison")
    parser.add_argument("--model-directory", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    acquire(args.model_directory)
    source = load_audio(args.source)
    segments = json.loads(Path(args.transcript).read_text())["segments"]
    mask = speech_mask(len(source), segments)
    start = time.perf_counter()
    restrained, raw_neural = enhance_48k(source, args.model_directory)
    inference_s = time.perf_counter() - start
    save_audio(out / "dtln-estimate-unmatched.wav", raw_neural)
    save_audio(out / "dtln-restrained-unmatched.wav", restrained)
    full = source.copy()
    a, b = round(5.033333 * RATE), round(107.166667 * RATE)
    full[a:b] = raw_neural[a:b]
    fade = round(.15 * RATE)
    for start_idx, values in [(a, np.linspace(0, 1, fade)),
                              (b-fade, np.linspace(1, 0, fade))]:
        full[start_idx:start_idx+fade] = (source[start_idx:start_idx+fade] * (1-values[:, None])
                                         + raw_neural[start_idx:start_idx+fade] * values[:, None])
    candidates = {"original": source, "dsp": load_audio(args.dsp_candidate),
                  "dtln70": restrained, "dtln100": full}
    active = {name: measure(value[mask]) for name, value in candidates.items()}
    target = min([-16.5] + [active[name]["input_i"] + (-1.4 - measure(value)["input_tp"])
                           for name, value in candidates.items()])
    report = {
        "source_sha256": sha256(args.source), "source_sample_rate": RATE,
        "model": {"name": "DTLN two-stage 500-hour DNS pretrained model",
                  "repository": "https://github.com/breizhn/DTLN",
                  "revision": MODEL_REVISION, "license": "MIT; upstream LICENSE retained",
                  "model_sample_rate": MODEL_RATE, "files": MODEL_SHA256},
        "runtime": {"engine": "onnxruntime", "provider": "CPUExecutionProvider",
                    "intra_op_threads": 1, "inter_op_threads": 1,
                    "inference_seconds_two_channels": inference_s},
        "processing": {"mixture_channels": 2, "independent_voice_isolation": False,
                       "neural_blend": .70, "dry_blend": .30,
                       "sample_rate_conversion": "zero-phase polyphase 48k -> 16k -> 48k",
                       "stream_offset_compensated_samples_at_16k": STREAM_OFFSET,
                       "stream_offset_compensated_ms": STREAM_OFFSET / 16,
                       "tail_flush": True, "retained_source_samples": len(source),
                       "model_bandwidth_note": "DTLN is 16 kHz; original upper frequencies survive only in the dry portion of dtln70.",
                       "outside_dialogue_scene": "untreated source; 150 ms handovers"},
        "active_speech_mask": "Union of provisional automatic transcript intervals; evaluation definition, not certified speech labels",
        "full_scene_common_active_target_lufs": target,
        "alignment_checks": {"dtln100": lags(source, full),
                             "dtln70": lags(source, restrained)},
        "listening_acceptance": "pending; metrics do not establish intelligibility or naturalness",
        "candidates": {}, "pilot": {}, "benchmarks": [],
    }
    matched_candidates = {}
    for name, value in candidates.items():
        matched_candidates[name], record = write_evaluation(out, name, value, mask, target)
        report["candidates"][name] = record
        print(f"matched full {name}", flush=True)
    # Same exact picture interval as the original A/B/C/D proof, with no reordering.
    pa, pb = round(85.1333333333 * RATE), round(107.166666667 * RATE)
    pilot_values = {name: value[pa:pb] for name, value in candidates.items()}
    pilot_mask = mask[pa:pb]
    pilot_active = {name: measure(value[pilot_mask]) for name, value in pilot_values.items()}
    pilot_target = min([-16.5] + [pilot_active[name]["input_i"] + (-1.4 - measure(value)["input_tp"])
                                  for name, value in pilot_values.items()])
    for name, value in pilot_values.items():
        matched, record = write_evaluation(out, name, value, pilot_mask, pilot_target, "-pilot")
        run(["ffmpeg", "-v", "error", "-y", "-i", out / record["file"],
             "-c:a", "aac", "-b:a", "192k", out / f"trial-{name}.m4a"])
        decoded = load_audio(out / f"trial-{name}.m4a")[:len(pilot_mask)]
        record["aac_active"] = measure(decoded[pilot_mask])
        report["pilot"][name] = record
    report["pilot_source_interval_s"] = [pa / RATE, pb / RATE]
    report["pilot_common_active_target_lufs"] = pilot_target
    report["pilot_delivered_active_spread_lu"] = max(record["aac_active"]["input_i"] for record in report["pilot"].values()) - min(record["aac_active"]["input_i"] for record in report["pilot"].values())
    for label, a, b in [("opening", 5.03, 9.8), ("distant-quiet", 13.2, 20.5),
                        ("raised", 33.4, 42.9), ("brief", 47.4, 55.4),
                        ("corrections", 55.4, 64), ("overlap", 73.9, 78),
                        ("inbox", 81.6, 88.233), ("ending", 95, 107.167)]:
        for name in ["dtln70", "dtln100"]:
            path = out / "benchmarks" / f"{label}-{name}.m4a"
            path.parent.mkdir(exist_ok=True)
            run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-i",
                 out / report["candidates"][name]["file"], "-t", str(b-a),
                 "-c:a", "aac", "-b:a", "192k", path])
        report["benchmarks"].append({"label": label, "source_interval_s": [a, b],
                                     "matching": "shared full-scene active-speech target"})
    write_json(out / "neural-audio-report.json", report)
    print(json.dumps({"model_ran": True, "inference_s": inference_s,
                      "samples": len(source), "full_target_lufs": target,
                      "pilot_spread_lu": report["pilot_delivered_active_spread_lu"]}), flush=True)


if __name__ == "__main__":
    main()
