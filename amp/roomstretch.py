"""Stretch the existing room-pause reel into exact-period, stackable layers.

V is literal varispeed: time and pitch change together. P is a separately
labelled, phase-randomized spectral stretch that retains the frequency range.
Neither mode recovers missing recordings or certifies perceptual room silence.
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import scipy
from scipy import signal
from scipy.io import wavfile

from .audio import RATE, load_audio, save_audio
from .core import require_distinct_outputs, sha256
from .roomrefine import inventory_portions, match_reference, measurements


PERIODS = (112., 84., 56., 28., 14.)
TARGET_LUFS = -40.37
AUDITION_BOOST_DB = 14.
SPECTRAL_FFT = 65536
SPECTRAL_SEED = 697221


def _audio(value, label="audio"):
    value = np.asarray(value)
    if value.ndim != 2 or value.shape[1] != 2 or not len(value):
        raise ValueError(f"{label} must be nonempty stereo audio")
    if not np.isfinite(value).all():
        raise ValueError(f"{label} contains non-finite samples")
    return value


def _integer(value, name, minimum=1):
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


def _write_json(path, value, *, protected_inputs=()):
    path = Path(path)
    require_distinct_outputs(protected_inputs, (path,))
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".room-stretch-", dir=path.parent) as directory:
        temporary = Path(directory) / path.name
        temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
        require_distinct_outputs(protected_inputs, (path,))
        temporary.replace(path)


def pcm_sha256(samples):
    return hashlib.sha256(np.asarray(samples, dtype="<f4").tobytes()).hexdigest()


def smooth_seams(samples, boundaries, half_width):
    """Length-preserving cosine crossfades using reflected in-pool handles.

At each boundary, mirror the outgoing half-window forward and the incoming
half-window backward. Crossfade those two handles across the original window.
No samples outside this reel are introduced; duration and all other samples
stay unchanged. Boundary zero addresses the cyclic end/start join.
"""
    source = _audio(samples)
    half_width = _integer(half_width, "half_width")
    if 2 * half_width >= len(source):
        raise ValueError("Crossfade must be shorter than the reel")
    boundary_list = list(boundaries)
    if not boundary_list or len(set(boundary_list)) != len(boundary_list):
        raise ValueError("Boundaries must be nonempty and unique")
    boundaries = sorted(_integer(v, "boundary", minimum=0) for v in boundary_list)
    if boundaries[-1] >= len(source):
        raise ValueError("Boundary is outside the reel")
    gaps = np.diff(boundaries + [boundaries[0] + len(source)])
    if np.any(gaps < 2 * half_width):
        raise ValueError("Crossfade neighborhoods overlap")
    output = source.astype(np.float64, copy=True)
    ramp = (.5 - .5 * np.cos(np.linspace(0, np.pi, 2 * half_width)))[:, None]
    report = []
    for boundary in boundaries:
        left_indices = (np.arange(boundary - half_width, boundary) % len(source))
        right_indices = (np.arange(boundary, boundary + half_width) % len(source))
        left, right = source[left_indices], source[right_indices]
        outgoing = np.concatenate((left, left[::-1]))
        incoming = np.concatenate((right[::-1], right))
        indices = np.concatenate((left_indices, right_indices))
        output[indices] = outgoing * (1 - ramp) + incoming * ramp
        before = float(np.max(np.abs(source[(boundary - 1) % len(source)] - source[boundary])))
        after = float(np.max(np.abs(output[(boundary - 1) % len(source)] - output[boundary])))
        report.append({"boundary_sample": boundary, "half_width_samples": half_width,
                       "wraps_end_start": boundary == 0,
                       "join_step_before": before, "join_step_after": after})
    return output.astype(np.float32), report


def source_reel(source, portions, *, seam_seconds=.005):
    """Keep a raw exact concatenation and an explicitly processed cyclic reel."""
    source = _audio(source, "source")
    fragments, records, cursor = [], [], 0
    for portion in portions:
        a, b = round(portion["start"] * RATE), round(portion["end"] * RATE)
        if not 0 <= a < b <= len(source):
            raise ValueError("Source portion lies outside source audio")
        fragment = source[a:b]
        fragments.append(fragment)
        records.append({"portion_id": portion["portion_id"],
                        "source_start_sample": a, "source_end_sample": b,
                        "source_start_seconds": a / RATE, "source_end_seconds": b / RATE,
                        "reel_start_sample": cursor, "reel_end_sample": cursor + len(fragment)})
        cursor += len(fragment)
    if not fragments:
        raise ValueError("No selected source portions")
    raw = np.concatenate(fragments).astype(np.float32)
    if not math.isfinite(seam_seconds) or seam_seconds <= 0:
        raise ValueError("seam_seconds must be positive")
    half_width = max(2, round(seam_seconds * RATE / 2))
    if any(len(fragment) < 2 * half_width for fragment in fragments):
        raise ValueError("A source fragment is shorter than the seam neighborhood")
    processed, joins = smooth_seams(raw, [r["reel_start_sample"] for r in records], half_width)
    dc = processed.astype(np.float64).mean(axis=0)
    processed = (processed.astype(np.float64) - dc).astype(np.float32)
    return raw, processed, {"raw_samples_per_channel": len(raw),
                            "processed_samples_per_channel": len(processed),
                            "duration_seconds": len(raw) / RATE, "portions": records,
                            "seam_method": "length-preserving reflected-handle cosine crossfade",
                            "seam_window_seconds": 2 * half_width / RATE,
                            "seams": joins, "dc_removed_per_channel": dc.tolist(),
                            "samples_outside_seams": "unchanged except one constant DC subtraction per channel",
                            "source_samples_outside_selected_portions_used": False,
                            "raw_pcm_sha256": pcm_sha256(raw),
                            "processed_pcm_sha256": pcm_sha256(processed)}


def varispeed_cycle(reel, period_samples):
    """Band-limited periodic resampling; the output sample rate stays 48 kHz."""
    reel = _audio(reel, "reel")
    period_samples = _integer(period_samples, "period_samples")
    if period_samples < len(reel):
        raise ValueError("This experiment requires slowing, not speeding up")
    # Fourier resampling matches a cyclic reel exactly and moves every source
    # frequency by the playback-speed ratio; it is not a phase vocoder.
    output = signal.resample(reel.astype(np.float64), period_samples, axis=0)
    return _audio(output.astype(np.float32), "varispeed output")


def spectral_cycle(reel, period_samples, *, seed=SPECTRAL_SEED, fft_size=SPECTRAL_FFT):
    """Paulstretch-style spectral progression with shared L/R phase rotations.

The analysis cursor traverses the source once over the requested output period.
FFT bin frequencies stay unchanged. New random phases discard event waveform
timing. Applying the same unit rotation to both channels preserves each frame's
complex L/R spectral relationship; mono therefore remains exactly mono.
"""
    reel = _audio(reel, "reel").astype(np.float64)
    period_samples = _integer(period_samples, "period_samples")
    fft_size = _integer(fft_size, "fft_size", minimum=16)
    if fft_size % 2 or fft_size > len(reel):
        raise ValueError("Spectral FFT must be even and no longer than the source reel")
    if period_samples < len(reel):
        raise ValueError("Spectral comparison requires a stretch")
    hop = fft_size // 2
    window = np.sin(np.pi * (np.arange(fft_size) + .5) / fft_size)
    local = np.arange(fft_size) - hop
    rng = np.random.default_rng(seed)
    output = np.zeros((period_samples, 2), np.float64)
    variance = np.zeros(period_samples, np.float64)
    cursor_ratio = len(reel) / period_samples
    frames = 0
    # Frames on either side provide complete overlap support at both ends.
    for center in range(0, period_samples + hop, hop):
        position = (center * cursor_ratio + local) % len(reel)
        lower = np.floor(position).astype(np.int64)
        fraction = (position - lower)[:, None]
        frame = reel[lower] * (1 - fraction) + reel[(lower + 1) % len(reel)] * fraction
        spectrum = np.fft.rfft(frame * window[:, None], axis=0)
        rotation = np.exp(1j * rng.uniform(-np.pi, np.pi, len(spectrum)))
        rotation[0] = 0  # DC is not part of the retained room color.
        rotation[-1] = rng.choice([-1., 1.])  # A real Nyquist bin is required.
        chunk = np.fft.irfft(spectrum * rotation[:, None], n=fft_size, axis=0)
        a, b = max(0, center - hop), min(period_samples, center + hop)
        first, last = a - (center - hop), b - (center - hop)
        output[a:b] += chunk[first:last] * window[first:last, None]
        variance[a:b] += window[first:last] ** 2
        frames += 1
    if np.any(variance <= 0):
        raise RuntimeError("Spectral overlap has an uncovered sample")
    # Independent randomized phases call for power/variance normalization,
    # not amplitude normalization of the two overlapping noise windows.
    output /= np.sqrt(variance[:, None])
    return _audio(output.astype(np.float32), "spectral output"), {
        "algorithm": "phase-randomized spectral time stretch",
        "seed": seed, "fft_size": fft_size, "output_hop_samples": hop,
        "analysis_window_seconds": fft_size / RATE, "synthesis_frames": frames,
        "source_cursor_samples_per_output_sample": cursor_ratio,
        "source_cursor_traversals_per_cycle": 1,
        "phase_randomized": True, "source_event_waveforms_preserved": False,
        "fft_bin_frequencies_shifted": False,
        "stereo_method": "identical random unit-phase rotation applied to both complex channel spectra",
        "overlap_normalization": "variance based; no signal-dependent gain",
    }


def loop_to_duration(cycle, output_samples):
    """Repeat the already seam-smoothed cycle without overlap/period drift."""
    cycle = _audio(cycle, "cycle")
    output_samples = _integer(output_samples, "output_samples")
    repeats = math.ceil(output_samples / len(cycle))
    output = np.tile(cycle, (repeats, 1))[:output_samples].copy()
    intervals = [{"cycle_index": index, "output_start_sample": start,
                  "output_end_sample": min(output_samples, start + len(cycle)),
                  "cycle_samples_used": min(len(cycle), output_samples - start),
                  "truncated": start + len(cycle) > output_samples}
                 for index, start in enumerate(range(0, output_samples, len(cycle)))]
    return output, intervals


def cumulative_sum(layers):
    if not layers:
        raise ValueError("A stack needs at least one layer")
    shape = _audio(layers[0]).shape
    output = np.zeros(shape, np.float64)
    for layer in layers:
        layer = _audio(layer)
        if layer.shape != shape:
            raise ValueError("Stack layer lengths differ")
        output += layer
    return output.astype(np.float32)


def _save_wav(path, samples, *, protected_inputs=()):
    path = Path(path)
    require_distinct_outputs(protected_inputs, (path,))
    samples = _audio(samples).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".room-stretch-", dir=path.parent) as directory:
        temporary = Path(directory) / path.name
        save_audio(temporary, samples)
        rate, decoded = wavfile.read(temporary)
        if rate != RATE or not np.array_equal(samples, decoded):
            raise ValueError(f"Float WAV verification failed: {path.name}")
        require_distinct_outputs(protected_inputs, (path,))
        temporary.replace(path)
    return {"sha256": sha256(path), "pcm_sha256": pcm_sha256(samples),
            "samples_per_channel": len(samples), "duration_seconds": len(samples) / RATE,
            "full_decode_verified": True, "finite": True}


def _encode(path, output, expected_samples, codec, *, protected_inputs=()):
    output = Path(output)
    require_distinct_outputs(protected_inputs, (output,))
    output.parent.mkdir(parents=True, exist_ok=True)
    arguments = ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(path),
                 "-map", "0:a:0", "-map_metadata", "-1", "-map_chapters", "-1",
                 "-vn", "-ar", str(RATE), "-ac", "2"]
    if codec == "flac":
        arguments += ["-c:a", "flac", "-sample_fmt", "s32"]
    elif codec == "aac":
        arguments += ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]
    else:
        raise ValueError("Unsupported output codec")
    with tempfile.TemporaryDirectory(prefix=".room-stretch-", dir=output.parent) as directory:
        temporary = Path(directory) / output.name
        subprocess.run(arguments + [str(temporary)], check=True, capture_output=True)
        decoded_run = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(temporary),
                                      "-vn", "-ar", str(RATE), "-ac", "2", "-f", "f32le", "-"],
                                     check=True, capture_output=True)
        if decoded_run.stderr.strip() or len(decoded_run.stdout) % 8:
            raise ValueError(f"Encoded audio contains a decoding error: {output.name}")
        decoded = _audio(np.frombuffer(decoded_run.stdout, "<f4").reshape(-1, 2))
        padding = len(decoded) - expected_samples
        if not 0 <= padding <= (1023 if codec == "aac" else 0):
            raise ValueError(f"Encoded audio has an incorrect duration: {output.name}")
        if np.max(np.abs(decoded)) >= 1:
            raise ValueError(f"Encoded audio clips: {output.name}")
        # Quantized lossless renders must agree with the float source within
        # one 24-bit PCM step; duration alone would miss wrong-file exports.
        error = None
        if codec == "flac":
            source = load_audio(path)
            error = float(np.max(np.abs(source - decoded)))
            if error > 2 ** -23 + 1e-9:
                raise ValueError(f"Lossless render differs beyond PCM quantization: {output.name}")
        require_distinct_outputs(protected_inputs, (output,))
        temporary.replace(output)
    return {"sha256": sha256(output), "bytes": output.stat().st_size,
            "source_samples": expected_samples, "decoded_samples": len(decoded),
            "tail_padding_samples": padding, "finite": True, "full_decode_verified": True,
            "sample_peak_dbfs": float(20 * np.log10(np.max(np.abs(decoded)))),
            "float_source_max_absolute_error": error}


def _media_paths(output, identifier, kind):
    folder = "stems" if kind == "layer" else "stacks"
    return (output / folder / f"{identifier}.wav", output / folder / f"{identifier}.flac",
            output / "web" / f"{identifier}-production.m4a", output / "web" / f"{identifier}-audition.m4a")


def _native_output_paths(output, periods, spectral):
    """Enumerate only destinations produced by the requested modes and periods."""
    paths = [output / "source-reel-raw.wav", output / "source-reel-seam-smoothed.wav",
             output / "room-stretch-report.json"]
    for mode in ("V", "P") if spectral else ("V",):
        for period in periods:
            identifier = f"{mode}{period:g}"
            paths.append(output / "raw-stems" / f"{identifier}.wav")
            paths.extend(_media_paths(output, identifier, "layer"))
        for count in range(1, len(periods) + 1) if mode == "V" else [len(periods)]:
            paths.extend(_media_paths(output, f"{mode}{count}-stack", "stack"))
        paths.extend(_media_paths(output, f"{mode}{len(periods)}R", "stack"))
    return paths


def _media(output, identifier, samples, *, kind, audition_boost_db, protected_inputs=()):
    """Publish a float stem/mix, quantized lossless copy and streaming variants."""
    wav, flac, production, audition = _media_paths(output, identifier, kind)
    require_distinct_outputs(protected_inputs, (wav, flac, production, audition))
    raised = (samples * 10 ** (audition_boost_db / 20)).astype(np.float32)
    if np.max(np.abs(raised)) >= 10 ** (-1.5 / 20):
        raise ValueError("Common audition boost exceeds -1.5 dBFS headroom; choose a lower shared boost")
    wav_receipt = _save_wav(wav, samples, protected_inputs=protected_inputs)
    flac_receipt = _encode(wav, flac, len(samples), "flac", protected_inputs=protected_inputs)
    production_receipt = _encode(wav, production, len(samples), "aac", protected_inputs=protected_inputs)
    with tempfile.TemporaryDirectory(prefix=".room-audition-", dir=output) as directory:
        raised_wav = Path(directory) / "audition.wav"
        save_audio(raised_wav, raised)
        audition_receipt = _encode(raised_wav, audition, len(samples), "aac", protected_inputs=protected_inputs)
    return {"stem_wav": str(wav.relative_to(output)),
            "stem_flac": str(flac.relative_to(output)),
            **({"mix_wav": str(wav.relative_to(output)),
                "mix_flac": str(flac.relative_to(output))} if kind == "stack" else {}),
            "production_aac": str(production.relative_to(output)),
            "audition_aac": str(audition.relative_to(output)),
            "audition_boost_db": audition_boost_db,
            "receipts": {"wav": wav_receipt, "flac": flac_receipt,
                         "production_aac": production_receipt, "audition_aac": audition_receipt}}


def original_gain_stacks(output, report, *, progress=None, protected_inputs=()):
    """Add full-stack controls that preserve the raw layers' relative gains."""
    output = Path(output)
    reference = {"bs1770_integrated_lufs": report["production_target_lufs"], "rms_dbfs": -42.}
    existing = {entry["id"] for entry in report["stacks"]}
    for mode, mode_name in [("V", "literal_varispeed"), ("P", "spectral_stretch")]:
        members = [entry for entry in report["layers"] if entry["mode"] == mode_name]
        if not members:
            continue
        identifier = f"{mode}{len(members)}R"
        if identifier in existing:
            continue
        if progress:
            progress(f"Rendering {identifier}: original relative gains")
        summed = np.zeros((report["samples_per_channel"], 2), np.float64)
        for entry in members:
            summed += load_audio(output / entry["raw_stem_wav"])
        summed = summed.astype(np.float32)
        stacked, gain = match_reference(summed, reference)
        media = _media(output, identifier, stacked, kind="stack",
                       audition_boost_db=report["audition_boost_db"], protected_inputs=protected_inputs)
        error = float(np.max(np.abs(stacked - summed * 10 ** (gain["gain_db"] / 20))))
        if error > 1e-7:
            raise ValueError("Original-relative-gain stack fails reconstruction")
        report["stacks"].append({"id": identifier, "mode": mode,
                                 "title": f"{len(members)} layers, original relative gain",
                                 "member_ids": [entry["id"] for entry in members],
                                 "member_input_kind": "raw_stems",
                                 "member_gains_db": {entry["id"]: 0. for entry in members},
                                 "equivalent_production_stem_gains_db": {
                                     entry["id"]: -entry["raw_to_production_gain_db"] for entry in members},
                                 "mix_gain_db": gain["gain_db"], "level_match": gain,
                                 "stem_sum_max_absolute_error": error,
                                 "reconstruction": "sum raw_stem_wav files at unity, then apply mix_gain_db once",
                                 **media})
        _write_json(output / "room-stretch-report.json", report, protected_inputs=protected_inputs)
    return report


def build(source_path, inventory_path, output_dir, *, duration=112., periods=PERIODS,
          target_lufs=TARGET_LUFS, audition_boost_db=AUDITION_BOOST_DB,
          spectral=True, progress=None):
    """Render explicit varispeed/spectral comparisons from the existing pool."""
    source_path, inventory_path, output = map(Path, (source_path, inventory_path, output_dir))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("duration must be positive")
    if not math.isfinite(target_lufs) or not math.isfinite(audition_boost_db):
        raise ValueError("Requested gains must be finite")
    periods = tuple(float(value) for value in periods)
    if not periods or len(set(periods)) != len(periods) or any(
            not math.isfinite(value) or not 0 < value <= duration for value in periods):
        raise ValueError("Periods must be unique positive values no longer than the film")
    if len({round(period * RATE) for period in periods}) != len(periods) or len({f"{period:g}" for period in periods}) != len(periods):
        raise ValueError("Periods must have distinct sample counts and output identifiers")
    protected_inputs = (source_path, inventory_path)
    require_distinct_outputs(protected_inputs, _native_output_paths(output, periods, spectral))
    inventory = json.loads(inventory_path.read_text())
    source_hash, inventory_hash = sha256(source_path), sha256(inventory_path)
    if inventory.get("source_sha256") != source_hash:
        raise ValueError("Inventory identifies another source; refusing to render")
    source = load_audio(source_path)
    output_samples = round(duration * RATE)
    source_decoded_samples = len(source)
    source_probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
        "stream=codec_name,sample_rate", "-of", "json", str(source_path)], text=True))["streams"][0]
    # The supplied 44.1 kHz AAC decodes with 627 resampled tail samples beyond
    # the 112-second picture. Only codec-frame tail padding may be trimmed.
    padding_limit = (math.ceil(1024 * RATE / int(source_probe["sample_rate"]))
                     if source_probe.get("codec_name") == "aac" else 0)
    if not output_samples <= len(source) <= output_samples + padding_limit:
        raise ValueError("Film duration differs from the decoded source beyond codec tail padding")
    source = source[:output_samples]
    portions = inventory_portions(inventory, len(source))
    raw_reel, reel, reel_report = source_reel(source, portions)
    if any(round(period * RATE) < len(reel) for period in periods):
        raise ValueError("All periods must slow the source reel")
    output.mkdir(parents=True, exist_ok=True)
    raw_receipt = _save_wav(output / "source-reel-raw.wav", raw_reel, protected_inputs=protected_inputs)
    processed_receipt = _save_wav(output / "source-reel-seam-smoothed.wav", reel, protected_inputs=protected_inputs)
    reference = {"bs1770_integrated_lufs": target_lufs, "rms_dbfs": -42.}
    report = {"schema_version": "amps.room-stretch.v1", "sample_rate": RATE, "channels": 2,
              "source_sha256": source_hash, "pause_inventory_sha256": inventory_hash,
              "source_decoded_samples": source_decoded_samples,
              "source_codec_tail_samples_trimmed": source_decoded_samples - output_samples,
              "source_audio_stream": source_probe,
              "duration_seconds": duration, "samples_per_channel": output_samples,
              "source_reel": reel_report,
              "source_reel_raw": {"file": "source-reel-raw.wav", **raw_receipt},
              "source_reel_processed": {"file": "source-reel-seam-smoothed.wav", **processed_receipt},
              "production_target_lufs": target_lufs,
              "audition_boost_db": audition_boost_db,
              "audition_target_lufs": target_lufs + audition_boost_db,
              "default_changed": False, "human_listening_acceptance": "pending",
              "stereo_linked": True, "limiter": False, "dynamic_normalization": False,
              "status": "rendering", "layers": [], "stacks": [],
              "environment": {"python": platform.python_version(), "numpy": np.__version__,
                              "scipy": scipy.__version__,
                              "ffmpeg": subprocess.check_output(["ffmpeg", "-version"], text=True).splitlines()[0]}}
    write_report = lambda: _write_json(output / "room-stretch-report.json", report, protected_inputs=protected_inputs)
    write_report()
    mode_layers = {}
    for mode in ("V", "P") if spectral else ("V",):
        mode_layers[mode] = []
        for period in periods:
            identifier = f"{mode}{period:g}"
            if progress:
                progress(f"Rendering {identifier}")
            period_samples = round(period * RATE)
            speed = len(reel) / period_samples
            if mode == "V":
                cycle = varispeed_cycle(reel, period_samples)
                processing = {"algorithm": "periodic band-limited Fourier varispeed resampling",
                              "phase_randomized": False,
                              "source_event_waveforms_preserved": "slowed and band-limited; seam regions processed",
                              "stereo_method": "same resampling transform and time coordinates in both channels"}
                cycle_seams = []  # Its source loop has already been crossfaded.
            else:
                cycle, processing = spectral_cycle(reel, period_samples)
                # Randomized first/last synthesis frames do not naturally join.
                # The in-place crossfade retains the exact requested period.
                cycle, cycle_seams = smooth_seams(cycle, [0], round(.1 * RATE))
            raw_layer, loops = loop_to_duration(cycle, output_samples)
            # Only the film boundaries have 10 ms edge fades. Internal repeats
            # use the prepared cycle seam and keep sample-exact period lengths.
            edge = min(round(.01 * RATE), output_samples // 4)
            ramp = (.5 - .5 * np.cos(np.linspace(0, np.pi, edge))).astype(np.float32)
            raw_layer[:edge] *= ramp[:, None]
            raw_layer[-edge:] *= ramp[::-1, None]
            raw_path = output / "raw-stems" / f"{identifier}.wav"
            raw_receipt = _save_wav(raw_path, raw_layer, protected_inputs=protected_inputs)
            layer, gain = match_reference(raw_layer, reference)
            media = _media(output, identifier, layer, kind="layer", audition_boost_db=audition_boost_db, protected_inputs=protected_inputs)
            record = {"id": identifier, "mode": "literal_varispeed" if mode == "V" else "spectral_stretch",
                      "period_seconds": period_samples / RATE, "period_samples": period_samples,
                      "film_fraction": period_samples / output_samples,
                      "source_reel_seconds": len(reel) / RATE,
                      "speed_ratio": speed, "stretch_factor": 1 / speed,
                      "pitch_shift_semitones": 12 * math.log2(speed) if mode == "V" else 0.,
                      "pitch_label": "pitch falls with playback speed" if mode == "V" else
                                     "FFT frequency range retained; source phase and event waveform randomized",
                      "cycles_within_film": output_samples / period_samples,
                      "loops": loops, "cycle_seams": cycle_seams,
                      "film_edge_fade_seconds": edge / RATE,
                      "cycle_wrap_sample_step": float(np.max(np.abs(cycle[-1] - cycle[0]))),
                      "processing": processing, "raw_stem_wav": str(raw_path.relative_to(output)),
                      "raw_stem_receipt": raw_receipt,
                      "raw_to_production_gain_db": gain["gain_db"], "level_match": gain,
                      **media}
            report["layers"].append(record)
            mode_layers[mode].append((identifier, layer))
            write_report()
        # V1..V5 reveal each added layer. P5 supplies the full spectral control.
        counts = range(1, len(periods) + 1) if mode == "V" else [len(periods)]
        for count in counts:
            identifier = f"{mode}{count}"
            if progress:
                progress(f"Rendering {identifier}")
            members = mode_layers[mode][:count]
            summed = cumulative_sum([layer for _, layer in members])
            stacked, gain = match_reference(summed, reference)
            media = _media(output, f"{identifier}-stack", stacked, kind="stack", audition_boost_db=audition_boost_db, protected_inputs=protected_inputs)
            reconstructed = cumulative_sum([layer for _, layer in members]) * 10 ** (gain["gain_db"] / 20)
            summation_error = float(np.max(np.abs(stacked - reconstructed)))
            if summation_error > 1e-7:
                raise ValueError("Stack cannot be reconstructed from its exported production stems")
            report["stacks"].append({"id": identifier, "mode": mode,
                                     "title": f"{count} layer{'s' if count != 1 else ''}, calibrated solo levels",
                                     "member_ids": [name for name, _ in members],
                                     "member_input_kind": "calibrated_production_stems",
                                     "member_gains_db": {name: 0. for name, _ in members},
                                     "equivalent_production_stem_gains_db": {name: 0. for name, _ in members},
                                     "mix_gain_db": gain["gain_db"], "level_match": gain,
                                     "stem_sum_max_absolute_error": summation_error,
                                     "reconstruction": "sum exported float production stems, then apply mix_gain_db once",
                                     **media})
            write_report()
    original_gain_stacks(output, report, progress=progress, protected_inputs=protected_inputs)
    report["status"] = "rendered and technically verified; human listening pending"
    report["interpretation"] = [
        "Literal varispeed changes both duration and pitch; the longest layer moves much source energy below ordinary speech frequencies.",
        "Spectral stretch is an additional phase-randomized comparison, not a transparent or event-preserving time stretch.",
        "All production layers and standalone stacks receive one fixed gain toward the same integrated loudness.",
        "Interactive recombination must sum production stems with the documented stack gain; audition files add the same declared boost.",
        "The additional V5R and P5R controls instead sum the raw source-level layers at unity before applying one final fixed matching gain.",
        "Layer repetition is intentional and exact. The 84-second layer repeats once and uses only the first 28 seconds of its second cycle.",
        "Numerical checks establish file and signal properties; they do not establish naturalness or the absence of recognizable activity.",
    ]
    write_report()
    return report
