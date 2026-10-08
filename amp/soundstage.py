"""Separately controllable scene bed, foley, and expressive returns."""
from pathlib import Path
import numpy as np

from .audio import RATE, load_audio, measure, save_audio
from .core import sha256, write_json


def scene_envelope(length, start=5.033333, end=107.166667, fade=.35):
    env = np.zeros(length, np.float32)
    a, b = round(start * RATE), min(length, round(end * RATE))
    if a < 0 or b <= a:
        raise ValueError("Invalid scene range")
    env[a:b] = 1
    n = min(round(fade * RATE), (b - a) // 2)
    env[a:a + n] = .5 - .5 * np.cos(np.linspace(0, np.pi, n))
    env[b - n:b] = .5 + .5 * np.cos(np.linspace(0, np.pi, n))
    return env


def rms_level(samples, target_db):
    rms = np.sqrt(np.mean(np.asarray(samples, np.float64) ** 2))
    if not np.isfinite(rms) or rms <= 0:
        raise ValueError("Empty or non-finite room bed")
    gain = 10 ** (target_db / 20) / rms
    return samples * gain, 20 * np.log10(gain)


def assemble_soundstage(dialogue, roomtone, foley, returns, out, *, bed_rms_db=-42, foley_gain_db=9):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    dry = load_audio(dialogue)
    length = round(112 * RATE)
    dry = dry[:length]
    tracks = {}
    for name, path in [("room", roomtone), ("foley", foley), ("returns", returns)]:
        value = load_audio(path)
        if len(value) < length:
            raise ValueError(f"{name} shorter than composition")
        tracks[name] = value[:length]
    bed, bed_gain = rms_level(tracks["room"], bed_rms_db)
    bed *= scene_envelope(length)[:, None]
    effects = tracks["foley"] * 10 ** (foley_gain_db / 20)
    expressive = tracks["returns"]
    versions = {"dialogue-with-room": dry + bed,
                "dialogue-room-foley": dry + bed + effects,
                "composed-mix": dry + bed + effects + expressive}
    # One fixed trim for all layers keeps stem summation exact and avoids pumping.
    peak = max(measure(v)["input_tp"] for v in versions.values())
    trim = min(0., -1.2 - peak)
    scalar = 10 ** (trim / 20)
    stem_values = {"dialogue-core": dry, "room-bed": bed, "foley-support": effects, "expression-return": expressive}
    for name, value in stem_values.items():
        save_audio(out / f"{name}.wav", value * scalar)
    report = {"duration_seconds": 112, "sample_rate": RATE, "channels": 2,
              "dialogue_origin": "70% DTLN enhanced shared recording plus 30% dry; no isolated performer stems",
              "room_target_rms_dbfs_before_scene_envelope": bed_rms_db, "room_gain_db": bed_gain,
              "foley_trim_db": foley_gain_db, "global_fixed_trim_db": trim,
              "room_role": "Subtle continuous support; original room and incidental sounds also remain in the dialogue mixture",
              "foley_role": "Newly authored support; captured incidental sounds have not been surgically erased",
              "listening_acceptance": "pending", "versions": {}, "stems": {}}
    for name, value in versions.items():
        save_audio(out / f"{name}.wav", value * scalar)
        report["versions"][name] = {"measurement": measure(value * scalar), "sha256": sha256(out / f"{name}.wav")}
    for name in stem_values:
        report["stems"][name] = {"sha256": sha256(out / f"{name}.wav")}
    write_json(out / "soundstage-report.json", report)
    return report
