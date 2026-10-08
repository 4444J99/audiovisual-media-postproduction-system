"""Source-pause inventory and deterministic, nonperiodic room-tone assembly.

Speech detection is a screening aid, never a claim that a pause is certified clean.
No recorded utterance is used intentionally. Every candidate pause has a disposition.
"""
import json
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.ndimage import maximum_filter1d, uniform_filter1d

from .audio import RATE, load_audio, save_audio
from .core import sha256, write_json


def runs(mask):
    edges = np.diff(np.r_[False, np.asarray(mask, bool), False].astype(np.int8))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def speech_probabilities(samples, model):
    """Author's Silero ONNX recurrent interface: 512 new samples + 64 context."""
    import onnxruntime as ort
    mono = signal.resample_poly(samples.mean(axis=1), 1, 3).astype(np.float32)
    options = ort.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(model), sess_options=options, providers=["CPUExecutionProvider"])
    state = np.zeros((2, 1, 128), np.float32)
    context = np.zeros((1, 64), np.float32)
    probabilities = []
    for i in range(0, len(mono), 512):
        chunk = np.zeros((1, 512), np.float32)
        segment = mono[i:i + 512]
        chunk[0, :len(segment)] = segment
        value = np.concatenate([context, chunk], axis=1)
        probability, state = session.run(None, {"input": value, "state": state,
                                                "sr": np.array(16000, np.int64)})
        probabilities.append(float(probability.ravel()[0]))
        context = value[:, -64:].copy()
    return np.asarray(probabilities), 512 / 16000


def pause_inventory(samples, segments, probabilities, hop, *, start=5.033333, end=107.166667):
    """Keep all provisional transcript gaps, then screen their interior at 10 ms."""
    step = .01
    count = int(np.ceil(len(samples) / RATE / step))
    t = (np.arange(count) + .5) * step
    asr = np.zeros(count, bool)
    for s in segments:
        asr |= (t >= s["start"]) & (t < s["end"])
    p = np.interp(t, (np.arange(len(probabilities)) + .5) * hop, probabilities)
    # A low threshold and margins protect quiet short replies and word endings.
    detected = p >= .12
    protected = maximum_filter1d((asr | detected).astype(np.uint8), size=41, mode="constant") > 0
    eligible = (~protected) & (t >= start + .15) & (t < end - .15)
    # Reject bursts (clinks/movement/breath); put them in the inventory for foley review.
    mono = samples.mean(axis=1)
    chunk = int(RATE * step)
    padded = np.pad(mono, (0, count * chunk - len(mono)))
    rms = np.sqrt(np.mean(padded.reshape(count, chunk) ** 2, axis=1) + 1e-15)
    candidates = rms[eligible]
    if len(candidates) == 0:
        raise ValueError("No screened room-tone material; require a recording or manual review")
    floor = float(np.quantile(candidates, .40))
    smooth = uniform_filter1d(rms, size=15, mode="nearest")
    transient = (rms > max(floor * 2.8, 1e-5)) | (rms > smooth * 2.3)
    transient = maximum_filter1d(transient.astype(np.uint8), size=11) > 0
    eligible &= ~transient
    regions = [(a, b) for a, b in runs(eligible) if (b - a) * step >= .13]
    inventory = []
    for index, (a, b) in enumerate(runs((~asr) & (t >= start) & (t < end))):
        portions = []
        for c, d in regions:
            left, right = max(a, c), min(b, d)
            if right > left:
                portions.append({"start": round(left * step, 6), "end": round(right * step, 6)})
        inventory.append({"id": f"PAUSE{index + 1:03d}", "start": round(a * step, 6),
                          "end": round(b * step, 6), "duration": round((b - a) * step, 6),
                          "vad_max_probability": round(float(p[a:b].max()), 6),
                          "usable_portions": portions,
                          "disposition": "assembled" if portions else "excluded",
                          "reason": "protected phrase margins / detected voice / transient / too short" if not portions else
                          "low VAD probability, phrase margins retained, transient-screened; audition pending"})
    return regions, inventory, {"step_seconds": step, "vad_threshold": .12,
             "speech_protection_each_side_seconds": .20, "transient_guard_each_side_seconds": .05,
             "minimum_fragment_seconds": .13, "pool_floor_rms": floor}


def assemble(samples, regions, *, duration, seed=6971, step=.01,
             crossfade_seconds=(.045, .075), cosine=False):
    """Random-order fragment overlap-add, with bounded speed/gain variation.

    Every accepted source portion contributes before any portion is reused. Source
    samples can recur; there is no repeating loop, tiled master, or periodic reset.
    """
    if not regions:
        raise ValueError("No source fragments")
    fragments = [samples[round(a * step * RATE):round(b * step * RATE)].copy() for a, b in regions]
    rms = np.array([np.sqrt(np.mean(f.astype(np.float64) ** 2) + 1e-15) for f in fragments])
    target = float(np.quantile(rms, .45))
    rng = np.random.default_rng(seed)
    length = round(duration * RATE)
    bed = np.zeros((length, 2), np.float64)
    weight = np.zeros(length, np.float64)
    position, cycle, previous = 0, 0, None
    edits = []
    while position < length:
        order = list(rng.permutation(len(fragments)))
        if len(order) > 1 and order[0] == previous:
            order[0], order[1] = order[1], order[0]
        for index in order:
            if position >= length:
                break
            fragment = fragments[index]
            speed = float(rng.uniform(.965, 1.035))
            # Interpolation is deliberately slight; it is not voice synthesis.
            new_length = max(2, round(len(fragment) / speed))
            points = np.linspace(0, len(fragment) - 1, new_length)
            stretch = np.column_stack([np.interp(points, np.arange(len(fragment)), fragment[:, c]) for c in range(2)])
            gain = float(np.clip(target / rms[index], .60, 1.60) * 10 ** (rng.uniform(-.7, .7) / 20))
            fade = min(round(rng.uniform(*crossfade_seconds) * RATE), new_length // 3)
            window = np.ones(new_length)
            if cosine:
                window[:fade] = .5 - .5 * np.cos(np.linspace(0, np.pi, fade))
                window[-fade:] = .5 + .5 * np.cos(np.linspace(0, np.pi, fade))
            else:
                window[:fade] = np.linspace(0, 1, fade, endpoint=False)
                window[-fade:] = np.linspace(1, 0, fade)
            stop = min(length, position + new_length)
            n = stop - position
            bed[position:stop] += stretch[:n] * gain * window[:n, None]
            weight[position:stop] += window[:n]
            a, b = regions[index]
            edits.append({"source_start": round(a * step, 6), "source_end": round(b * step, 6),
                          "output_start": round(position / RATE, 6), "output_end": round(stop / RATE, 6),
                          "speed": round(speed, 8), "gain": round(gain, 8), "crossfade_samples": fade,
                          "source_fragment": int(index), "pass": cycle})
            previous = index
            position += max(1, new_length - fade)
        cycle += 1
    bed /= np.maximum(weight[:, None], 1e-8)
    # Preserve native mono-like perspective; no invented widening or new hum.
    ramp = min(round(.20 * RATE), length // 2)
    bed[:ramp] *= np.linspace(0, 1, ramp)[:, None]
    bed[-ramp:] *= np.linspace(1, 0, ramp)[:, None]
    return bed.astype(np.float32), edits


def create_roomtone(source, transcript, model, out, *, duration=112, seed=6971):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    x = load_audio(source)
    probabilities, hop = speech_probabilities(x, model)
    regions, inventory, settings = pause_inventory(x, transcript["segments"], probabilities, hop)
    bed, edits = assemble(x, regions, duration=duration, seed=seed, step=settings["step_seconds"])
    save_audio(out / "room-tone-nonlooping.wav", bed)
    # Diagnostic plays the eligible pauses once, separated by 150 ms silence.
    audition = []
    for a, b in regions:
        audition.extend([x[round(a * .01 * RATE):round(b * .01 * RATE)], np.zeros((7200, 2), np.float32)])
    save_audio(out / "source-pause-audition.wav", np.concatenate(audition))
    write_json(out / "vad-probabilities.json", {"hop_seconds": hop, "probabilities": probabilities.tolist()})
    record = {"source_sha256": sha256(source), "model_sha256": sha256(model), "vad_model": "Silero VAD ONNX",
              "sample_rate": RATE, "channels": 2, "duration_seconds": len(bed) / RATE, "seed": seed,
              "construction": "Crossfaded source-pause montage; random order without adjacent reuse; bounded playback-speed/gain variation",
              "source_sample_reuse": True, "fixed_loop": False, "every_eligible_portion_used":
              len(set(e["source_fragment"] for e in edits)) == len(regions),
              "pause_count": len(inventory), "eligible_portion_count": len(regions),
              "eligible_source_seconds": sum((b - a) * .01 for a, b in regions),
              "settings": settings, "pauses": inventory, "edit_map": edits,
              "sha256": sha256(out / "room-tone-nonlooping.wav"),
              "listening_acceptance": "pending: screen for quiet words, breaths, clinks and audible joins"}
    write_json(out / "room-tone-report.json", record)
    return record
