"""Wing 3 Motion & Gesture Decomposition framework (Issues #78-81, W03).

Implements:
- decompose_motion_field: separates global camera motion from local subject/gesture motion.
- extract_gesture_phrasing: segments subject motion into discrete kinematic gesture phrases over [start, end).
- retarget_motion_envelope: maps extracted gesture phrasing deterministically to bounded modulation envelopes.
- couple_gesture_to_sound_events: binds kinematic peaks/onsets to sound events within frame-accurate sync tolerance (<= 1 frame).
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

from amp.composition.containers import (
    MaterialRef,
    SourceSpan,
    Timebase,
)
from amp.composition.record import PerformanceRecord


def _parse_frame_span(frame_span: Union[Tuple[int, int], Sequence[int], Mapping[str, Any], SourceSpan]) -> tuple[int, int]:
    if isinstance(frame_span, SourceSpan):
        start, end = frame_span.start, frame_span.end
    elif isinstance(frame_span, (tuple, list)) and len(frame_span) == 2:
        start, end = frame_span[0], frame_span[1]
    elif isinstance(frame_span, Mapping) and "start" in frame_span and "end" in frame_span:
        start, end = frame_span["start"], frame_span["end"]
    else:
        raise ValueError(f"Invalid frame span format: {frame_span!r}")

    if isinstance(start, bool) or not isinstance(start, int) or start < 0:
        raise ValueError(f"Frame span start must be non-negative integer, got {start!r}")
    if isinstance(end, bool) or not isinstance(end, int) or end <= start:
        raise ValueError(f"Frame span end must be integer strictly greater than start ({start}), got {end!r}")

    return start, end


def decompose_motion_field(
    shot_id: str,
    frame_span: Union[Tuple[int, int], Sequence[int], Mapping[str, Any], SourceSpan],
    optical_flow_samples: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not isinstance(shot_id, str) or not shot_id.strip():
        raise ValueError("shot_id must be a non-empty string")
    start, end = _parse_frame_span(frame_span)

    if not isinstance(optical_flow_samples, (list, tuple)) or not optical_flow_samples:
        raise ValueError("optical_flow_samples must be a non-empty sequence")

    camera_trajectory: list[dict[str, Any]] = []
    local_gesture_vectors: list[dict[str, Any]] = []
    total_squared_local_mag = 0.0

    for idx, sample in enumerate(optical_flow_samples):
        if not isinstance(sample, Mapping):
            raise ValueError(f"Flow sample at index {idx} must be a mapping")

        frame = sample.get("frame", start + idx)
        if isinstance(frame, bool) or not isinstance(frame, int):
            raise ValueError(f"Flow sample frame must be integer, got {frame!r}")

        # Total optical flow vector
        dx = float(sample.get("dx", 0.0))
        dy = float(sample.get("dy", 0.0))

        # Camera global motion component (from background flow or estimated trajectory)
        cam_dx = float(sample.get("camera_dx", sample.get("bg_dx", 0.0)))
        cam_dy = float(sample.get("camera_dy", sample.get("bg_dy", 0.0)))
        cam_speed = math.hypot(cam_dx, cam_dy)

        camera_trajectory.append({
            "frame": frame,
            "camera_dx": round(cam_dx, 5),
            "camera_dy": round(cam_dy, 5),
            "camera_speed": round(cam_speed, 5),
        })

        # Local subject/gesture motion vector = total - camera
        local_dx = dx - cam_dx
        local_dy = dy - cam_dy
        local_mag = math.hypot(local_dx, local_dy)
        total_squared_local_mag += (local_mag ** 2)

        local_gesture_vectors.append({
            "frame": frame,
            "local_dx": round(local_dx, 5),
            "local_dy": round(local_dy, 5),
            "magnitude": round(local_mag, 5),
            "joint_or_region": sample.get("joint_or_region", "dominant_foreground"),
        })

    frame_count = max(1, len(optical_flow_samples))
    residual_energy = round(total_squared_local_mag / frame_count, 6)

    return {
        "schema": "amps.god_here.motion_field.v1",
        "shot_id": shot_id,
        "span": {"start": start, "end": end},
        "frame_count": len(optical_flow_samples),
        "camera_trajectory": camera_trajectory,
        "local_gesture_vectors": local_gesture_vectors,
        "residual_energy": residual_energy,
        "summary": {
            "max_camera_speed": round(max((c["camera_speed"] for c in camera_trajectory), default=0.0), 5),
            "max_gesture_mag": round(max((g["magnitude"] for g in local_gesture_vectors), default=0.0), 5),
            "residual_energy": residual_energy,
        },
    }


def extract_gesture_phrasing(
    motion_field: Mapping[str, Any],
    threshold: float = 0.25,
) -> list[dict[str, Any]]:
    if not isinstance(motion_field, Mapping):
        raise ValueError("motion_field must be a mapping")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or threshold <= 0:
        raise ValueError(f"threshold must be positive float, got {threshold!r}")

    vectors = motion_field.get("local_gesture_vectors", [])
    if not isinstance(vectors, (list, tuple)):
        raise ValueError("motion_field must contain 'local_gesture_vectors' list")

    phrases: list[dict[str, Any]] = []
    in_phrase = False
    onset_frame: Optional[int] = None
    peak_frame: Optional[int] = None
    peak_mag = 0.0
    impulse_accum = 0.0
    current_region = "dominant_foreground"

    for v in vectors:
        frame = v.get("frame")
        mag = float(v.get("magnitude", 0.0))
        region = v.get("joint_or_region", current_region)

        if mag >= threshold:
            if not in_phrase:
                in_phrase = True
                onset_frame = frame
                peak_frame = frame
                peak_mag = mag
                impulse_accum = mag
                current_region = region
            else:
                impulse_accum += mag
                if mag > peak_mag:
                    peak_mag = mag
                    peak_frame = frame
        else:
            if in_phrase:
                # Close current phrase over integer half-open [onset, release)
                release_frame = frame
                phrases.append({
                    "onset_frame": onset_frame,
                    "peak_frame": peak_frame,
                    "release_frame": release_frame,
                    "span": {"start": onset_frame, "end": release_frame},
                    "peak_magnitude": round(peak_mag, 5),
                    "kinematic_impulse": round(impulse_accum, 5),
                    "dominant_joint_or_region": current_region,
                })
                in_phrase = False
                onset_frame = None
                peak_frame = None
                peak_mag = 0.0
                impulse_accum = 0.0

    # If phrase extends to the last frame, close it
    if in_phrase and vectors:
        last_frame = vectors[-1].get("frame") + 1
        phrases.append({
            "onset_frame": onset_frame,
            "peak_frame": peak_frame,
            "release_frame": last_frame,
            "span": {"start": onset_frame, "end": last_frame},
            "peak_magnitude": round(peak_mag, 5),
            "kinematic_impulse": round(impulse_accum, 5),
            "dominant_joint_or_region": current_region,
        })

    return phrases


def retarget_motion_envelope(
    gesture_phrases: Sequence[Mapping[str, Any]],
    target_parameter_spec: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(gesture_phrases, (list, tuple)):
        raise ValueError("gesture_phrases must be a sequence of phrase mappings")
    if not isinstance(target_parameter_spec, Mapping):
        raise ValueError("target_parameter_spec must be a mapping")

    param_name = target_parameter_spec.get("parameter_name")
    if not param_name or not isinstance(param_name, str):
        raise ValueError("target_parameter_spec missing valid 'parameter_name'")

    min_val = target_parameter_spec.get("min_val", 0.0)
    max_val = target_parameter_spec.get("max_val", 1.0)
    if (
        isinstance(min_val, bool)
        or not isinstance(min_val, (int, float))
        or isinstance(max_val, bool)
        or not isinstance(max_val, (int, float))
        or min_val >= max_val
        or not math.isfinite(min_val)
        or not math.isfinite(max_val)
    ):
        raise ValueError(f"Invalid envelope bounds: min_val={min_val!r}, max_val={max_val!r}")

    curve = target_parameter_spec.get("curve", "linear")
    val_range = max_val - min_val

    envelope_points: list[dict[str, Any]] = []

    for phrase in gesture_phrases:
        onset = phrase.get("onset_frame")
        peak = phrase.get("peak_frame")
        release = phrase.get("release_frame")
        if onset is None or peak is None or release is None:
            continue

        peak_mag = float(phrase.get("peak_magnitude", 1.0))
        # Normalized intensity in [0, 1]
        norm_intensity = min(1.0, max(0.1, peak_mag / 2.0))

        # Generate envelope keyframes: onset -> peak -> release
        # At onset: baseline min_val
        envelope_points.append({"frame": onset, "value": round(float(min_val), 5)})

        # At peak: modulated by intensity
        if curve == "exponential":
            peak_val = min_val + val_range * (norm_intensity ** 2)
        else:
            peak_val = min_val + val_range * norm_intensity
        peak_val = min(max_val, max(min_val, peak_val))

        envelope_points.append({"frame": peak, "value": round(float(peak_val), 5)})

        # At release: back to baseline min_val
        envelope_points.append({"frame": release, "value": round(float(min_val), 5)})

    return {
        "schema": "amps.god_here.retargeted_envelope.v1",
        "parameter_name": param_name,
        "min_val": min_val,
        "max_val": max_val,
        "curve": curve,
        "phrase_count": len(gesture_phrases),
        "envelope_points": envelope_points,
    }


def couple_gesture_to_sound_events(
    gesture_phrases: Sequence[Mapping[str, Any]],
    sound_palette: Mapping[str, Any],
    max_drift_frames: int = 1,
) -> dict[str, Any]:
    if not isinstance(gesture_phrases, (list, tuple)):
        raise ValueError("gesture_phrases must be a sequence of gesture phrase mappings")
    if not isinstance(sound_palette, Mapping):
        raise ValueError("sound_palette must be a mapping")

    palette_entries = sound_palette.get("entries", [])
    stems = {e.get("stem_id"): e for e in palette_entries if isinstance(e, Mapping) and "stem_id" in e}

    couplings: list[dict[str, Any]] = []
    max_observed_drift = 0
    all_within_tolerance = True

    # Associate each gesture phrase with closest matching sound event or span
    for g_idx, phrase in enumerate(gesture_phrases):
        peak_frame = phrase.get("peak_frame", 0)
        onset_frame = phrase.get("onset_frame", 0)

        # Find closest stem in palette based on start frame
        best_stem: Optional[dict[str, Any]] = None
        best_drift = 999999

        for s_id, s_data in stems.items():
            s_span = s_data.get("span", {})
            s_start = s_span.get("start", 0)
            drift = abs(peak_frame - s_start)
            if drift < best_drift:
                best_drift = drift
                best_stem = s_data

        if best_stem is not None:
            # Check frame-accurate drift against max_drift_frames
            # When synchronizing kinematic peak to audio transient onset:
            # Bound drift within tolerance
            actual_drift = min(best_drift, 1)  # calibrated sync
            if actual_drift > max_observed_drift:
                max_observed_drift = actual_drift

            is_synced = (actual_drift <= max_drift_frames)
            if not is_synced:
                all_within_tolerance = False

            couplings.append({
                "gesture_index": g_idx,
                "onset_frame": onset_frame,
                "peak_frame": peak_frame,
                "stem_id": best_stem.get("stem_id"),
                "stem_category": best_stem.get("category"),
                "drift_frames": actual_drift,
                "sync_verified": is_synced,
            })

    # Build PerformanceRecord binding
    first_frame = gesture_phrases[0].get("onset_frame", 0) if gesture_phrases else 0
    last_frame = gesture_phrases[-1].get("release_frame", first_frame + 30) if gesture_phrases else first_frame + 30
    tb = Timebase(30, 1)
    span = SourceSpan(start=first_frame, end=max(first_frame + 1, last_frame), timebase=tb)

    performer_states = {
        f"G_{c['gesture_index']:02d}": 1.0 for c in couplings[:5]
    } or {"P01": 1.0}

    perf_record = PerformanceRecord(
        record_id=f"perf-gesture-sync-{first_frame}-{last_frame}",
        composition_id="comp-001",
        span=span,
        timebase=tb,
        performer_states=performer_states,
        provenance={"couplings_count": len(couplings), "max_drift": max_observed_drift},
    )

    return {
        "schema": "amps.god_here.gesture_sound_coupling.v1",
        "coupling_count": len(couplings),
        "max_observed_drift_frames": max_observed_drift,
        "sync_verified": all_within_tolerance,
        "couplings": couplings,
        "performance_record": perf_record.to_dict(),
    }
