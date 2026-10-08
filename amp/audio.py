"""Conservative DSP trials, matched to active-speech intervals.

These are candidate repairs. Automated measurements cannot certify intelligibility.
"""
import json
import re
import subprocess
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile

from .core import run, write_json, sha256

RATE = 48000


def load_audio(path):
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ar", str(RATE),
                                   "-ac", "2", "-f", "f32le", "-"])
    return np.frombuffer(raw, "<f4").reshape(-1, 2).copy()


def save_audio(path, samples):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(str(path), RATE, np.asarray(samples, dtype=np.float32))


def speech_mask(length, segments):
    mask = np.zeros(length, dtype=bool)
    for s in segments:
        mask[max(0, round(s["start"] * RATE)):min(length, round(s["end"] * RATE))] = True
    return mask


def measure(samples):
    with subprocess.Popen(["ffmpeg", "-hide_banner", "-f", "f32le", "-ar", str(RATE), "-ac", "2", "-i", "-",
                           "-af", "loudnorm=I=-16:TP=-1:LRA=11:print_format=json", "-f", "null", "-"],
                          stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE) as p:
        _, log = p.communicate(np.asarray(samples, dtype="<f4").tobytes())
        if p.returncode:
            raise RuntimeError(log.decode())
    blocks = re.findall(r'\{\s*"input_i".*?\}', log.decode(), re.S)
    if not blocks:
        raise RuntimeError("Loudness measurement unavailable")
    parsed = json.loads(blocks[-1])
    return {k: (v if k == "normalization_type" else float(v)) for k, v in parsed.items()}


def repair(samples, segments, strength):
    # Near-mono input is treated as a mixture, never a set of isolated voices.
    sos = signal.butter(2, 65, "highpass", fs=RATE, output="sos")
    filtered = signal.sosfiltfilt(sos, samples, axis=0).astype(np.float32)
    _, t, z = signal.stft(filtered.T, fs=RATE, nperseg=1024, noverlap=768, boundary="zeros")
    active = np.zeros(len(t), bool)
    for s in segments:
        active |= (t >= s["start"] - .12) & (t <= s["end"] + .12)
    # Estimate the noise floor inside the dialogue scene; do not use title silence.
    pause = (~active) & (t >= 5.05) & (t < 107.15)
    if pause.sum() < 10:
        raise ValueError("Insufficient pause samples for a noise-floor trial")
    power = np.abs(z) ** 2
    noise = np.quantile(power[:, :, pause], .30, axis=-1)[:, :, None]
    gain = np.sqrt(np.maximum(10 ** (-strength * 12 / 10), 1 - strength * noise / np.maximum(power, 1e-12)))
    # Time/frequency smoothing avoids a rapidly switching binary gate.
    from scipy.ndimage import uniform_filter
    gain = uniform_filter(gain, size=(1, 3, 5), mode="nearest")
    _, cleaned = signal.istft(z * gain, fs=RATE, nperseg=1024, noverlap=768, boundary=True)
    cleaned = cleaned.T[:len(samples)]
    # Retain original title/credits and use a gentle handover into the dialogue.
    env = np.zeros(len(samples))
    a, b = round(5.033333 * RATE), round(107.166667 * RATE)
    env[a:b] = 1
    n = round(.15 * RATE)
    env[a:a+n] = np.linspace(0, 1, n)
    env[b-n:b] = np.linspace(1, 0, n)
    return samples * (1 - env[:, None]) + cleaned * env[:, None]


def match(samples, mask, target):
    before = measure(samples[mask])
    gain_db = target - before["input_i"]
    return samples * 10 ** (gain_db / 20), before, gain_db


def make_candidates(source, transcript, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    x = load_audio(source)
    segments = transcript["segments"]
    mask = speech_mask(len(x), segments)
    save_audio(out / "reference-decoded.wav", x)
    conservative = repair(x, segments, .55)
    stronger = repair(x, segments, 1.05)
    save_audio(out / "removed-residual.wav", x - conservative)
    save_audio(out / "conservative-unmatched.wav", conservative)
    run(["ffmpeg", "-v", "error", "-y", "-i", out / "reference-decoded.wav", "-af",
         "highpass=f=65,afftdn=nr=14:nf=-32:tn=1", "-c:a", "pcm_f32le", out / "fft-denoise-unmatched.wav"])
    candidates = {"A": x, "B": conservative, "S": stronger, "F": load_audio(out / "fft-denoise-unmatched.wav")}
    # Choose a common feasible target using peak headroom across every candidate.
    measured = {k: measure(v[mask]) for k, v in candidates.items()}
    target = min([-16.5] + [m["input_i"] + (-1.4 - measure(candidates[k])["input_tp"]) for k, m in measured.items()])
    record = {"sample_rate": RATE, "source_sha256": sha256(source), "active_speech_definition":
              "Union of provisional automatic transcript intervals; an evaluation mask, not certified VAD",
              "common_active_target_lufs": target, "latency_samples": 0,
              "latency_basis": "STFT reconstruction retains sample count; no offset introduced by slicing",
              "listening_acceptance": "pending", "provisional_workprint_choice": "B", "candidates": {}}
    for name, value in candidates.items():
        matched, before, gain = match(value, mask, target)
        save_audio(out / f"candidate-{name}.wav", matched)
        record["candidates"][name] = {"gain_db": gain, "before_active": before,
                                     "after_active": measure(matched[mask]), "full_program": measure(matched),
                                     "samples": len(matched), "sha256": sha256(out / f"candidate-{name}.wav")}
    write_json(out / "audio-report.json", record)
    return record


def expressive_audio(clean, config, out):
    x = load_audio(clean)
    t = np.arange(len(x)) / RATE
    buses = {}
    for pid, performer in config["performers"].items():
        env = np.zeros(len(x))
        for cue in config["cues"]:
            if cue["performer"] != pid:
                continue
            a, b = cue["start"], cue["end"]
            q = np.minimum(1, np.minimum((t - a) / max(.01, cue.get("attack", .3)),
                                        (b - t) / max(.01, cue.get("release", .6))))
            q = np.where((t >= a) & (t < b), np.maximum(0, q), 0)
            env = np.maximum(env, cue["intensity"] * (.5 - .5 * np.cos(np.pi * q)))
        # Return buses derive from the shared mix. They are not solo character stems.
        delay = {"pressure": .09, "lag": .36, "refraction": .18, "residue": .64, "erosion": .82}[performer["style"]]
        n = round(delay * RATE)
        shifted = np.zeros_like(x)
        for shot in config["shots"]:
            a, b = round(shot["start"] * RATE), min(len(x), round(shot["end"] * RATE))
            if b - a > n:
                shifted[a+n:b] = x[a:b-n]
        if performer["style"] == "refraction":
            shifted = shifted[:, ::-1]
        shifted = signal.sosfilt(signal.butter(2, 2400, "lowpass", fs=RATE, output="sos"), shifted, axis=0)
        bus = shifted * env[:, None] * .105
        pan = (int(pid[-1]) - 3) * .2
        bus[:, 0] *= 1 - max(0, pan)
        bus[:, 1] *= 1 + min(0, pan)
        buses[pid] = bus
        save_audio(Path(out) / f"return-{pid}.wav", bus)
    total = sum(buses.values())
    save_audio(Path(out) / "expressive-returns.wav", total)
    mix = x + total
    # Fixed global trim protects headroom without ducking the dialogue dynamically.
    peak = measure(mix)["input_tp"]
    trim = min(0, -1.1 - peak)
    mix *= 10 ** (trim / 20)
    save_audio(Path(out) / "expressive-mix.wav", mix)
    write_json(Path(out) / "expressive-report.json", {"origin": "Shared repaired mixture, shot-local delays",
               "individual_voice_isolation": False, "global_trim_db": trim, "measurement": measure(mix),
               "listening_acceptance": "pending"})
    return mix
