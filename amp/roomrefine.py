"""Controlled comparisons for the existing God-here room rack.

A remains the existing rendered rack. B changes only fragment scheduling; C
bypasses B's FX. D and E explicitly synthesize spectral textures and discard
source event envelopes. Measurements do not certify silence or naturalness.
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import tempfile
from pathlib import Path

import numpy as np
import scipy
from scipy import signal
from scipy.ndimage import gaussian_filter1d

from .audio import RATE, load_audio, measure, save_audio
from .core import sha256
from .roomrack import BANDS, compress, effect, split_bands, stabilize_fragment
from .roomtone import assemble


DURATION = 112
SHARED_SEED = BANDS["low"]["seed"]
SYNTHESIS_SEED = 697140
PROFILE_FFT = 8192
SYNTHESIS_FFT = 65536
FILENAMES = {
    "A": "A-existing-rack.wav",
    "B": "B-shared-schedule.wav",
    "C": "C-shared-dry.wav",
    "D": "D-sustained-mid-high.wav",
    "E": "E-static-spectrum.wav",
}
LABELS = {
    "A": "Existing independent-band rack with its original FX",
    "B": "Shared fragment schedule; original band dynamics and FX",
    "C": "Same shared schedule and dynamics; all band FX bypassed",
    "D": "Source low band with synthesized, slowly sustained mid/high spectra",
    "E": "Synthesized stationary texture from the pooled source spectra",
}


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def _finite_audio(value, label, length=None):
    value = np.asarray(value)
    if value.ndim != 2 or value.shape[1] != 2 or not len(value):
        raise ValueError(f"{label} must be nonempty stereo audio")
    if length is not None and len(value) != length:
        raise ValueError(f"{label} has {len(value)} samples; expected {length}")
    if not np.isfinite(value).all():
        raise ValueError(f"{label} contains non-finite samples")
    return value


def rms(samples):
    value = float(np.sqrt(np.mean(np.asarray(samples, np.float64) ** 2)))
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Cannot measure or match an empty/silent/non-finite bed")
    return value


def pcm_sha256(samples):
    return hashlib.sha256(np.asarray(samples, dtype="<f4").tobytes()).hexdigest()


def measurements(samples):
    """Report FFmpeg's measured INPUT values, not loudnorm's predicted output."""
    _finite_audio(samples, "Measurement input")
    result = {
        "rms_dbfs": float(20 * np.log10(rms(samples))),
        "sample_peak_dbfs": float(20 * np.log10(np.max(np.abs(samples)))),
        "bs1770_integrated_lufs": None,
        "true_peak_dbtp": None,
        "loudness_range_lu": None,
    }
    try:
        measured = measure(samples)
        for target, key in [
            ("bs1770_integrated_lufs", "input_i"),
            ("true_peak_dbtp", "input_tp"),
            ("loudness_range_lu", "input_lra"),
        ]:
            value = float(measured[key])
            result[target] = value if math.isfinite(value) else None
        result["loudness_method"] = "FFmpeg loudnorm input BS.1770 measurement; no normalization filter applied to output"
    except (RuntimeError, OSError, KeyError, ValueError) as error:
        result["loudness_method"] = "unavailable; RMS fallback only"
        result["loudness_error"] = str(error)
    return result


def match_reference(samples, reference_measurement):
    """One fixed gain: prefer integrated loudness; retain RMS as a separate fact."""
    before = measurements(samples)
    source_i = before["bs1770_integrated_lufs"]
    target_i = reference_measurement["bs1770_integrated_lufs"]
    if source_i is not None and target_i is not None:
        gain_db = target_i - source_i
        method = "fixed BS.1770 integrated-loudness gain"
    else:
        gain_db = reference_measurement["rms_dbfs"] - before["rms_dbfs"]
        method = "fixed RMS gain; integrated loudness unavailable"
    matched = (samples * 10 ** (gain_db / 20)).astype(np.float32)
    after = measurements(matched)
    if np.max(np.abs(matched)) >= 1:
        raise ValueError("Reference matching would clip; no limiter was silently introduced")
    if target_i is not None and after["bs1770_integrated_lufs"] is not None:
        error_lu = after["bs1770_integrated_lufs"] - target_i
        if abs(error_lu) > .1:
            raise ValueError(f"Fixed-gain loudness match exceeds 0.1 LU: {error_lu:+.3f}")
    else:
        error_lu = None
    return matched, {
        "method": method, "gain_db": float(gain_db), "before": before,
        "after": after, "integrated_loudness_error_lu": error_lu,
        "dynamic_normalization": False, "limiter": False,
    }


def inventory_portions(inventory, source_length):
    """Validate the existing screened pool without upgrading listening status."""
    if inventory.get("sample_rate") != RATE or inventory.get("channels") != 2:
        raise ValueError("Inventory must identify the existing 48 kHz stereo source")
    portions = []
    seen = set()
    previous_end = -1
    for pause in inventory.get("pauses", []):
        pause_id = pause.get("id")
        if not isinstance(pause_id, str) or not pause_id:
            raise ValueError("Missing stable pause ID")
        for index, value in enumerate(pause.get("usable_portions", []), 1):
            portion_id = f"{pause_id}-{index:02d}"
            start, end = float(value["start"]), float(value["end"])
            if portion_id in seen or not (math.isfinite(start) and math.isfinite(end)):
                raise ValueError("Duplicate or non-finite source portion")
            if not 0 <= start < end <= source_length / RATE:
                raise ValueError("Source portion outside decoded source")
            if start < previous_end or end - start < .13 - 1e-8:
                raise ValueError("Overlapping or undersized source portion")
            if any(abs(v * 100 - round(v * 100)) > 1e-6 for v in (start, end)):
                raise ValueError("Existing assembler requires source boundaries on the 10 ms grid")
            portions.append({"portion_id": portion_id, "pause_id": pause_id,
                             "start": start, "end": end, "action": "keep",
                             "status": "algorithmic_candidate", "listening_acceptance": "pending"})
            seen.add(portion_id)
            previous_end = end
    if not portions:
        raise ValueError("No screened source portions; no fallback material is invented")
    return portions


def shared_layers(bands, portions, *, duration=DURATION):
    """Reuse the original assembler with the SAME RNG seed in every band.

    Its RNG calls do not depend on sample values. Timing/order/speed/crossfades
    therefore agree exactly while existing per-band gain stabilization remains.
    """
    regions = [(round(p["start"] * 100), round(p["end"] * 100)) for p in portions]
    dry, wet, info = {}, {}, {}
    shared_timing = None
    for name, config in BANDS.items():
        raw = bands[name]
        pool = np.concatenate([raw[a * 480:b * 480] for a, b in regions])
        target = rms(pool)
        stable = np.zeros_like(raw)
        for a, b in regions:
            stable[a * 480:b * 480] = stabilize_fragment(
                raw[a * 480:b * 480], target, config["stabilization_s"])
        assembled, edits = assemble(stable, regions, duration=duration,
                                   seed=SHARED_SEED, crossfade_seconds=(.12, .22), cosine=True)
        timing = [{k: e[k] for k in e if k != "gain"} for e in edits]
        if shared_timing is not None and timing != shared_timing:
            raise RuntimeError("Band schedules diverged; controlled comparison is invalid")
        shared_timing = timing
        compressed, dynamics = compress(assembled, config)
        effected = effect(compressed, name, config["seed"])
        trim = 10 ** (config["trim_db"] / 20)
        dry[name] = (compressed * trim).astype(np.float32)
        wet[name] = ((.75 * compressed + .25 * effected) * trim).astype(np.float32)
        info[name] = {
            "original_band_configuration": dict(config), "assembly_seed": SHARED_SEED,
            "fx_seed": config["seed"], "source_band_pool_rms": target,
            "dynamics": dynamics, "edit_map": edits,
            "fx_enabled_blend": .25, "fx_bypass_replaces_wet_with_unity_dry": True,
            "source_portion_ids": [p["portion_id"] for p in portions],
        }
    return dry, wet, info


def spectral_profiles(samples, portions):
    """Capture source color, discarding each portion's original event envelope.

    Median Welch power estimates and log-power smoothing reduce the influence
    of impulses/narrow resonances. Each snapshot has equal total power. Mid/side
    power retains the source's approximate stereo width; exact mono stays mono.
    """
    profiles = []
    frequencies = np.fft.rfftfreq(PROFILE_FFT, 1 / RATE)
    for portion in portions:
        a, b = round(portion["start"] * RATE), round(portion["end"] * RATE)
        fragment = samples[a:b]
        mid_side = np.column_stack(((fragment[:, 0] + fragment[:, 1]) * .5,
                                    (fragment[:, 0] - fragment[:, 1]) * .5))
        channels = []
        for component in mid_side.T:
            if np.mean(component ** 2) <= 1e-24:
                channels.append(np.zeros(len(frequencies)))
                continue
            nperseg = min(4096, len(component))
            _, power = signal.welch(component, fs=RATE, nperseg=nperseg,
                                    noverlap=nperseg // 2, nfft=PROFILE_FFT,
                                    detrend="constant", average="median")
            power = np.exp(gaussian_filter1d(np.log(np.maximum(power, 1e-30)), 3))
            power[0] = 0
            channels.append(power)
        profile = np.asarray(channels)
        total = float(profile.sum())
        if not math.isfinite(total) or total <= 0:
            raise ValueError("A source portion has no usable spectral energy")
        profiles.append(profile / total)
    return frequencies, np.asarray(profiles)


def spectral_texture(frequencies, profiles, length, *, seed, mode):
    """Render a non-repeating, phase-resynthesized spectral sustain or static bed.

    Sustain traverses the source snapshots once with slow cosine morphs over the
    output duration. Static uses their robust median throughout. Neither mode
    replays source samples, source phase, or source event timing. Synthesis-frame
    overlap is variance-normalized rather than amplifying periodic frame edges.
    """
    if mode not in {"sustain", "static"}:
        raise ValueError("Unknown spectral texture mode")
    frequencies = np.asarray(frequencies)
    profiles = np.asarray(profiles, np.float64)
    if profiles.ndim != 3 or profiles.shape[1:] != (2, len(frequencies)) or not len(profiles):
        raise ValueError("Spectral profiles must be portion × mid/side × frequency")
    if not np.isfinite(profiles).all() or (profiles < 0).any() or np.any(profiles.sum(axis=(1, 2)) <= 0):
        raise ValueError("Invalid spectral profile energy")
    if length < 2 or len(frequencies) < 2 or np.any(np.diff(frequencies) <= 0):
        raise ValueError("Invalid synthesis length or frequency axis")
    profiles = profiles / profiles.sum(axis=(1, 2))[:, None, None]
    if mode == "static":
        profile = np.median(profiles, axis=0)
        if profile.sum() <= 0:
            raise ValueError("Robust pooled spectrum is empty")
        profiles = (profile / profile.sum())[None]
    nfft, hop = SYNTHESIS_FFT, SYNTHESIS_FFT // 2
    pad = nfft
    total = length + 2 * pad
    output = np.zeros((total, 2), np.float64)
    weights = np.zeros(total, np.float64)
    window = np.sin(np.pi * (np.arange(nfft) + .5) / nfft)
    fft_frequencies = np.fft.rfftfreq(nfft, 1 / RATE)
    rng = np.random.default_rng(seed)
    frames = 0
    for position in range(0, total - nfft + 1, hop):
        center = position + nfft / 2 - pad
        coordinate = np.clip(center / max(1, length - 1), 0, 1) * (len(profiles) - 1)
        left = int(np.floor(coordinate))
        right = min(left + 1, len(profiles) - 1)
        blend = .5 - .5 * np.cos(np.pi * (coordinate - left))
        power = profiles[left] * (1 - blend) + profiles[right] * blend
        interpolated = np.asarray([np.interp(fft_frequencies, frequencies, channel) for channel in power])
        phase = rng.uniform(0, 2 * np.pi, interpolated.shape)
        spectrum = np.sqrt(interpolated) * np.exp(1j * phase)
        spectrum[:, 0] = 0
        spectrum[:, -1] = 0
        frame = np.fft.irfft(spectrum, n=nfft, axis=1).T
        output[position:position + nfft] += frame * window[:, None]
        weights[position:position + nfft] += window ** 2
        frames += 1
    mid_side = output[pad:pad + length] / np.sqrt(np.maximum(weights[pad:pad + length, None], 1e-12))
    value = np.column_stack((mid_side[:, 0] + mid_side[:, 1],
                             mid_side[:, 0] - mid_side[:, 1]))
    ramp = min(round(.2 * RATE), length // 2)
    value[:ramp] *= np.linspace(0, 1, ramp)[:, None]
    value[-ramp:] *= np.linspace(1, 0, ramp)[:, None]
    value = (value / rms(value)).astype(np.float32)
    return value, {
        "mode": mode, "seed": int(seed), "synthesis_fft_samples": nfft,
        "synthesis_hop_samples": hop, "synthesis_frames": frames,
        "source_snapshot_count": len(profiles),
        "snapshot_output_centers_seconds": np.linspace(0, length / RATE, len(profiles)).tolist(),
        "morph": "one slow cosine traversal of source spectral snapshots" if mode == "sustain" else "constant robust pooled spectrum",
        "source_pcm_replayed": False, "source_event_envelope_retained": False,
        "source_phase_retained": False, "synthesized_texture": True,
        "stereo_model": "source-derived mid/side power; independent synthesized phases",
        "fixed_loop": False, "global_rms_before_band_level": 1,
    }


def _reference(baseline_dir, source_hash, inventory_hash, portions):
    baseline_dir = Path(baseline_dir)
    report_path = baseline_dir / "room-rack-report.json"
    report = json.loads(report_path.read_text())
    if report.get("source_sha256") != source_hash:
        raise ValueError("Baseline rack belongs to another source")
    if report.get("pause_inventory_sha256") != inventory_hash:
        raise ValueError("Baseline pause-inventory SHA does not match; original inventory bytes are required")
    expected = [{"start": p["start"], "end": p["end"]} for p in portions]
    if report.get("source_portions") != expected:
        raise ValueError("Baseline source portions do not match the supplied inventory")
    if (report.get("sample_rate"), report.get("channels"), report.get("duration_seconds")) != (RATE, 2, DURATION):
        raise ValueError("Baseline must be the source-length 48 kHz stereo rack")
    path = next((baseline_dir / name for name in ["room-tone-layered.wav", "room-tone-layered.flac"]
                 if (baseline_dir / name).is_file()), None)
    if path is None:
        raise ValueError("Baseline rack audio is unavailable")
    value = _finite_audio(load_audio(path), "Baseline rack", round(DURATION * RATE))
    return value, {
        "audio_filename": path.name, "audio_sha256": sha256(path),
        "decoded_float32_pcm_sha256": pcm_sha256(value), "report_sha256": sha256(report_path),
        "pause_inventory_sha256": report["pause_inventory_sha256"],
        "source_sha256": report["source_sha256"], "reference_samples_preserved": True,
        "original_report": report,
    }


def _sum_layers(layers):
    return sum(np.asarray(value, np.float64) for value in layers.values()).astype(np.float32)


def build(source, inventory_path, out, *, baseline_dir=None, dialogue_path=None,
          selection_path=None, write_stems=False):
    source, inventory_path, out = Path(source), Path(inventory_path), Path(out)
    inventory = json.loads(inventory_path.read_text())
    source_hash, inventory_hash = sha256(source), sha256(inventory_path)
    if source_hash != inventory.get("source_sha256"):
        raise ValueError("Pause inventory belongs to another source")
    for protected in [source, inventory_path, dialogue_path, baseline_dir, selection_path]:
        if protected is not None and Path(protected).resolve().is_relative_to(out.resolve()):
            raise ValueError("Output directory cannot contain an input or the recovered baseline")
    x = _finite_audio(load_audio(source), "Decoded source")
    length = round(DURATION * RATE)
    if len(x) < length:
        raise ValueError("Source is shorter than the 112-second composition")
    originals = inventory_portions(inventory, len(x))
    selected = originals
    selection = None
    if selection_path is not None:
        from .roomaudit import resolve_selection
        selection = json.loads(Path(selection_path).read_text())
        selected = resolve_selection(inventory, selection, source_sha256=source_hash,
                                     pause_inventory_sha256=inventory_hash)
        if not selected:
            raise ValueError("Selection excludes every source portion")
    selection_changed = [(p["portion_id"], p["start"], p["end"]) for p in selected] != [
        (p["portion_id"], p["start"], p["end"]) for p in originals]
    out.mkdir(parents=True, exist_ok=True)
    if baseline_dir is None:
        from .roomrack import build as build_original
        with tempfile.TemporaryDirectory(prefix="roomrefine-baseline-") as directory:
            build_original(source, inventory_path, directory)
            reference, reference_info = _reference(directory, source_hash, inventory_hash, originals)
        reference_info["origin"] = "Fresh execution of unchanged amp.roomrack.build"
    else:
        reference, reference_info = _reference(baseline_dir, source_hash, inventory_hash, originals)
        reference_info["origin"] = "Recovered existing rack; decoded without level or effect changes"
    reference_measurement = measurements(reference)
    filtered = signal.sosfiltfilt(signal.butter(2, 25, "highpass", fs=RATE, output="sos"), x, axis=0)
    del x
    bands = split_bands(filtered)
    del filtered
    dry, wet, shared_report = shared_layers(bands, selected)
    profiles = {}
    frequencies = None
    for name, raw in bands.items():
        frequencies, profiles[name] = spectral_profiles(raw, selected)
    del bands, raw
    profile_path = out / "source-spectral-profiles.npz"
    np.savez_compressed(profile_path, frequency_hz=frequencies, **profiles)
    static, sustained, synthesis_report = {}, {"low": dry["low"]}, {}
    for index, name in enumerate(BANDS):
        static[name], static_info = spectral_texture(frequencies, profiles[name], length,
                                                     seed=SYNTHESIS_SEED + index, mode="static")
        static[name] *= rms(dry[name])
        synthesis_report[name] = {"static": static_info, "target_raw_band_rms_dbfs": float(20 * np.log10(rms(dry[name])))}
        if name != "low":
            sustained[name], sustain_info = spectral_texture(frequencies, profiles[name], length,
                                                             seed=SYNTHESIS_SEED + 10 + index, mode="sustain")
            sustained[name] *= rms(dry[name])
            synthesis_report[name]["sustain"] = sustain_info
    layers = {"B": wet, "C": dry, "D": sustained, "E": static}
    report = {
        "schema_version": "amps.room-refinement.v1", "source_sha256": source_hash,
        "pause_inventory_sha256": inventory_hash, "duration_seconds": DURATION,
        "sample_rate": RATE, "channels": 2, "samples_per_channel": length,
        "status": "rendered comparisons; human listening and artistic acceptance pending",
        "original_default_changed": False, "original_source_preserved": True,
        "reference": reference_info, "reference_measurement": reference_measurement,
        "original_portions": originals, "selected_portions": selected,
        "selection_changed_source_pool": selection_changed,
        "selection_sha256": sha256(selection_path) if selection_path else None,
        "selection_status": "unchanged screened candidates; listening pending" if selection is None else selection.get("status", "explicit supplied selection"),
        "comparison_limit": "A/B also differ in the selected source pool" if selection_changed else "A/B differ in scheduling; B/C differ in FX; D/E explicitly change the synthesis method",
        "shared_schedule": {"seed": SHARED_SEED, "band_timing_verified_identical": True, "bands": shared_report},
        "spectral_synthesis": {
            "profile_filename": profile_path.name, "profile_sha256": sha256(profile_path),
            "analysis_fft_samples": PROFILE_FFT, "welch_segment_samples_maximum": 4096,
            "welch_statistic": "median", "log_power_smoothing_sigma_bins": 3,
            "profiles_equal_power": True, "source_portion_ids": [p["portion_id"] for p in selected],
            "profile_axis_order": ["source portion", "mid/side", "frequency"],
            "bands": synthesis_report, "source_recording_recovery_claim": False,
            "D_low_origin": "C low before per-candidate fixed listening gain",
        },
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "candidates": {},
    }
    for key in FILENAMES:
        if key == "A":
            matched = reference
            match_info = {"method": "unchanged reference", "gain_db": 0,
                          "before": reference_measurement, "after": reference_measurement,
                          "integrated_loudness_error_lu": 0, "dynamic_normalization": False, "limiter": False}
        else:
            matched, match_info = match_reference(_sum_layers(layers[key]), reference_measurement)
        path = out / FILENAMES[key]
        save_audio(path, matched)
        candidate = {
            "label": LABELS[key], "filename": path.name, "sha256": sha256(path),
            "decoded_float32_pcm_sha256": pcm_sha256(matched), "matching": match_info,
            "sample_count": len(matched), "synthesized_texture": key in {"D", "E"},
            "listening_acceptance": "pending",
        }
        if key == "A" and candidate["decoded_float32_pcm_sha256"] != reference_info["decoded_float32_pcm_sha256"]:
            raise RuntimeError("Reference samples changed during comparison export")
        if write_stems and key in layers:
            candidate["stems"] = {}
            for name, value in layers[key].items():
                stem = out / "stems" / key / f"{name}.wav"
                save_audio(stem, value * 10 ** (match_info["gain_db"] / 20))
                candidate["stems"][name] = {"filename": str(stem.relative_to(out)), "sha256": sha256(stem)}
        report["candidates"][key] = candidate
    if dialogue_path is not None:
        from .soundstage import scene_envelope
        dialogue = _finite_audio(load_audio(dialogue_path), "Dialogue core", length)
        env = scene_envelope(length)[:, None]
        peaks = []
        for candidate in report["candidates"].values():
            mixed = dialogue + load_audio(out / candidate["filename"]) * env
            measured = measurements(mixed)
            peaks.append(measured["true_peak_dbtp"] if measured["true_peak_dbtp"] is not None else measured["sample_peak_dbfs"])
        trim_db = min(0., -1.2 - max(peaks))
        context = {"dialogue_sha256": sha256(dialogue_path), "dialogue_pcm_sha256": pcm_sha256(dialogue),
                   "dialogue_origin": "caller-supplied existing dialogue core; source incidental activity may remain",
                   "global_fixed_trim_db": trim_db, "identical_dialogue_gain_in_every_mix": True,
                   "room_scene_seconds": [5.033333, 107.166667], "scene_fade_seconds": .35,
                   "foley_or_expression_added": False, "mixes": {}}
        for key, candidate in report["candidates"].items():
            mixed = (dialogue + load_audio(out / candidate["filename"]) * env) * 10 ** (trim_db / 20)
            path = out / ("mix-" + candidate["filename"])
            save_audio(path, mixed)
            context["mixes"][key] = {"filename": path.name, "sha256": sha256(path), "measurement": measurements(mixed)}
        report["dialogue_context"] = context
    _write_json(out / "room-refinement-report.json", report)
    return report
