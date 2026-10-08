"""Deterministic, source-timed procedural foley studies.

These sounds are authored additions, not recovered location recordings.  The
score stores visual evidence separately from the origin of the sound.  The
optional stove bed is excluded from the main stem until its scene fit is heard.
"""
import json
from pathlib import Path

import numpy as np
from scipy import signal

from .audio import RATE, save_audio
from .core import run, sha256, write_json

KINDS = {"cloth", "chair", "glass_handle", "glass_set", "sip", "stove"}
BUSES = {"movement", "glass", "sip", "stove"}


def validate_score(score):
    """Reject scores that cannot preserve the source timeline or provenance."""
    if score.get("sample_rate") != RATE:
        raise ValueError("Foley delivery must use 48 kHz")
    end = score["duration_seconds"]
    seen = set()
    for event in score["events"]:
        if event["id"] in seen:
            raise ValueError("Duplicate foley event id")
        seen.add(event["id"])
        if not (0 <= event["start"] < event["end"] <= end):
            raise ValueError("Foley event outside the source timeline")
        if event["kind"] not in KINDS or event["bus"] not in BUSES:
            raise ValueError("Unknown foley operation or bus")
        if not (-1 <= event["pan"] <= 1):
            raise ValueError("Foley pan must be between -1 and 1")
        if event.get("sound_origin") != "procedural_authored_addition":
            raise ValueError("This renderer cannot claim recovered sound")
        if event.get("optional", False) and event["bus"] != "stove":
            raise ValueError("Optional staging is reserved for the stove study")
        if not event.get("visual_evidence") or not event.get("timing_confidence"):
            raise ValueError("Foley events require evidence and timing confidence")
    return True


def _noise(rng, n, lo, hi):
    noise = rng.standard_normal(n)
    sos = signal.butter(2, [lo, hi], "bandpass", fs=RATE, output="sos")
    return signal.sosfilt(sos, noise)


def _edge(n, attack=.012, release=.04):
    env = np.ones(n)
    a, b = min(round(attack * RATE), n // 2), min(round(release * RATE), n // 2)
    if a:
        env[:a] = np.sin(np.linspace(0, np.pi / 2, a)) ** 2
    if b:
        env[-b:] = np.cos(np.linspace(0, np.pi / 2, b)) ** 2
    return env


def _modes(t, frequencies, rng, decay=.12):
    out = np.zeros(len(t))
    for i, frequency in enumerate(frequencies):
        # Inharmonic modes and random phase make different touches distinct.
        out += np.sin(2 * np.pi * frequency * t + rng.uniform(-.12, .12)) * np.exp(-t / (decay / (1 + .27 * i))) / (1 + i)
    return out


def synth_event(event, seed):
    """Create a unique waveform for one scored gesture; never reuse a loop."""
    n = round((event["end"] - event["start"]) * RATE)
    t = np.arange(n) / RATE
    rng = np.random.default_rng(seed)
    kind = event["kind"]
    if kind == "cloth":
        x = _noise(rng, n, 260, 6200)
        cycles = rng.uniform(1.6, 3.1)
        shape = (.25 + .75 * np.sin(np.pi * np.linspace(0, cycles, n)) ** 2)
        x *= shape * _edge(n, .045, .09)
    elif kind == "chair":
        x = .48 * _noise(rng, n, 95, 1500)
        sweep = signal.chirp(t, f0=rng.uniform(160, 230), f1=rng.uniform(95, 160), t1=max(t[-1], .01))
        irregular = .25 + .75 * np.sin(2 * np.pi * rng.uniform(7, 12) * t) ** 4
        x += sweep * irregular * .3
        x *= np.sin(np.pi * np.linspace(0, 1, n)) ** 1.5
    elif kind == "glass_handle":
        # Finger/contact friction; no invented tabletop impact on a held cup.
        x = .75 * _noise(rng, n, 950, 7000) + .06 * _modes(t, [2400, 3670, 5150], rng, .035)
        x *= _edge(n, .02, .045) * np.exp(-t / .28)
    elif kind == "glass_set":
        # Damped glass contact plus the softer table body; not a cartoon bell.
        scale = rng.uniform(.94, 1.06)
        x = .33 * _modes(t, np.array([1730, 2690, 3970, 5870]) * scale, rng, .10)
        x += .65 * _modes(t, [145, 238, 389], rng, .045)
        x += .18 * _noise(rng, n, 800, 8000) * np.exp(-t / .006)
        x *= _edge(n, .0005, .04)
    elif kind == "sip":
        # Quiet liquid/lip support.  No synthetic breath or spoken phoneme.
        x = _noise(rng, n, 650, 4200)
        shape = np.sin(np.pi * np.linspace(0, 1, n)) ** 2
        x *= shape * (.22 + .20 * np.sin(2 * np.pi * 9.7 * t) ** 2)
        for q in rng.uniform(.10, max(.11, event["end"] - event["start"] - .08), 4):
            a = round(q * RATE)
            count = min(round(.07 * RATE), n - a)
            if count > 0:
                tt = np.arange(count) / RATE
                x[a:a+count] += .06 * signal.chirp(tt, f0=rng.uniform(350, 600), f1=180, t1=.07) * np.exp(-tt/.014)
        x *= _edge(n, .04, .06)
    else:
        # An optional interpretation of the screenplay's stove, not an observed
        # burner recording.  Random excitation is continuous, with no period.
        x = _noise(rng, n, 220, 9200)
        knots = rng.uniform(.55, 1, max(4, round(t[-1]) + 2))
        x *= np.interp(t, np.linspace(0, max(t[-1], .01), len(knots)), knots)
        pops = np.zeros(n)
        count = round(t[-1] * 5)
        positions = rng.integers(0, max(1, n - 300), count)
        for a in positions:
            tt = np.arange(min(300, n-a)) / RATE
            pops[a:a+len(tt)] += rng.uniform(.4, 1.2) * np.sin(2 * np.pi * rng.uniform(1100, 3400) * tt) * np.exp(-tt/.0018)
        x = .26 * x + .22 * pops
        x *= _edge(n, .8, .8)
    peak = np.max(np.abs(x))
    if peak:
        x *= 10 ** (event["peak_dbfs"] / 20) / peak
    pan = event["pan"]
    stereo = x[:, None] * np.array([np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)])[None, :]
    # Two very quiet, bounded early reflections; no changing global reverb bed.
    wet = stereo.copy()
    for delay, gain in [(.023, .10), (.047, .055)]:
        d = round(delay * RATE)
        if n > d:
            wet[d:] += stereo[:-d, ::-1] * gain
    wet *= _edge(n, .0005, .015)[:, None]
    return wet.astype(np.float32)


def build_foley(score, out, source=None):
    validate_score(score)
    if source is not None and sha256(source) != score["source_sha256"]:
        raise ValueError("Foley source identity does not match its score")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    length = round(score["duration_seconds"] * RATE)
    buses = {bus: np.zeros((length, 2), np.float32) for bus in sorted(BUSES)}
    events = []
    for index, event in enumerate(score["events"]):
        seed = score["seed"] + index * 1009
        audio = synth_event(event, seed)
        a = round(event["start"] * RATE)
        b = min(length, a + len(audio))
        buses[event["bus"]][a:b] += audio[:b-a]
        events.append({**event, "seed": seed, "start_sample": a, "end_sample": b,
                       "rendered_peak_dbfs": float(20*np.log10(max(1e-12,np.max(np.abs(audio)))))})
    buses["foley-main"] = buses["movement"] + buses["glass"] + buses["sip"]
    buses["foley-with-stove-option"] = buses["foley-main"] + buses["stove"]
    files = []
    for name, audio in buses.items():
        wav = out / f"{name}.wav"
        flac = out / f"{name}.flac"
        save_audio(wav, audio)
        run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-c:a", "flac", "-sample_fmt", "s32", "-bits_per_raw_sample", "24", flac])
        files.append({"bus": name, "wav": wav.name, "flac": flac.name,
                      "samples": len(audio), "sample_rate": RATE,
                      "rms_dbfs": float(20*np.log10(max(1e-12,np.sqrt(np.mean(audio.astype(np.float64)**2))))),
                      "peak_dbfs": float(20*np.log10(max(1e-12,np.max(np.abs(audio))))),
                      "wav_sha256": sha256(wav), "flac_sha256": sha256(flac)})
    manifest = {"source_sha256": score["source_sha256"], "duration_seconds": score["duration_seconds"],
                "sample_rate": RATE, "origin": "Procedural authored foley additions; no source speech used",
                "dialogue_recovery": False, "main_mix_buses": ["movement", "glass", "sip"],
                "stove": "Optional screenplay-based bed; no visible burner or location sound verified",
                "listening_acceptance": "pending", "visual_timing": "Inspected video frames at 0.4 s spacing around drinks; timing tolerance about +/-0.2 s",
                "events": events, "files": files}
    write_json(out / "foley-manifest.json", manifest)
    return manifest


def review_montage(source, out, score):
    """Foley-only audition with source images and explicit provenance labels."""
    out = Path(out)
    # A single source input and audio input keeps the concatenation exact.
    windows = [(8.4,13.3,"P04 cup and sip"),(14.4,17.2,"P01 sip"),
               (41.4,44.6,"P01 sip and movement"),(60.6,66.8,"P03 cup sip and set down"),
               (66.8,69.8,"P01 sip"),(81.6,85.6,"P03 gesture and glass contact"),
               (91.6,95,"P04 sip"),(95,101.4,"P03 sip"),(33.4,39.4,"Optional stove interpretation")]
    filters = []
    inputs = []
    for i, (a, b, label) in enumerate(windows):
        va, vb = round(a*30), round(b*30)
        aa, ab = va*1600, vb*1600
        text = f"{label} | source {a:.1f}-{b:.1f}s | authored foley only +12dB"
        filters.append(f"[0:v]trim=start_frame={va}:end_frame={vb},setpts=PTS-STARTPTS,scale=854:480,drawtext=text='{text}':fontsize=15:fontcolor=white:x=12:y=h-30:box=1:boxcolor=black@0.8[v{i}]")
        input_bus = "[2:a]" if i == len(windows)-1 else "[1:a]"
        filters.append(f"{input_bus}atrim=start_sample={aa}:end_sample={ab},asetpts=PTS-STARTPTS,volume=12dB[a{i}]")
        inputs.append(f"[v{i}][a{i}]")
    filters.append("".join(inputs)+f"concat=n={len(windows)}:v=1:a=1[v][a]")
    path = out / "foley-review.mp4"
    run(["ffmpeg","-v","error","-y","-i",source,"-i",out/"foley-main.wav","-i",out/"stove.wav",
         "-filter_complex",";".join(filters),"-map","[v]","-map","[a]","-c:v","libx264","-crf","23",
         "-preset","fast","-threads","2","-c:a","aac","-b:a","192k","-movflags","+faststart",path])
    run(["ffmpeg","-v","error","-i",path,"-f","null","-"])
    write_json(out / "review-windows.json", {"audition_gain_db":12,"sound_origin":"Procedural authored additions",
               "windows":[{"start":a,"end":b,"label":label} for a,b,label in windows],"sha256":sha256(path)})
    return path
