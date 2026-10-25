"""Wing 10 Long-Take Temporal Architecture & Retiming framework (Issues #106-109, W10).

Implements:
- build_piecewise_retime_curve: constructs monotonic time-warping curve mapping composition time to source moments.
- detect_phase_lock_conjunctions: identifies timestamps where independent streams reach rhythmic/kinematic conjunction.
- enforce_long_take_continuity_budget: validates retiming acceleration budget (max_acceleration <= 0.15).
- compile_macro_section_arc: assembles contiguous multi-minute macro-sections with tension profile.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

from amp.composition.containers import SourceSpan


def build_piecewise_retime_curve(
    frame_span: Union[Tuple[int, int], Sequence[int], Mapping[str, Any], SourceSpan],
    control_points: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if isinstance(frame_span, SourceSpan):
        start, end = frame_span.start, frame_span.end
    elif isinstance(frame_span, (tuple, list)) and len(frame_span) == 2:
        start, end = frame_span[0], frame_span[1]
    elif isinstance(frame_span, Mapping) and "start" in frame_span and "end" in frame_span:
        start, end = frame_span["start"], frame_span["end"]
    else:
        raise ValueError(f"Invalid frame span: {frame_span!r}")

    if end <= start:
        raise ValueError(f"Invalid frame span interval: [{start}, {end}]")

    if not isinstance(control_points, (list, tuple)) or len(control_points) < 2:
        raise ValueError("control_points must have at least 2 points")

    # Validate strict monotonicity
    prev_comp = -1
    prev_source = -1.0
    validated_points = []

    for idx, cp in enumerate(control_points):
        if not isinstance(cp, Mapping):
            raise ValueError(f"Control point {idx} must be a mapping")

        comp_f = cp.get("comp_frame")
        src_f = cp.get("source_frame")

        if isinstance(comp_f, bool) or not isinstance(comp_f, int):
            raise ValueError(f"comp_frame must be integer at point {idx}, got {comp_f!r}")
        if isinstance(src_f, bool) or not isinstance(src_f, (int, float)):
            raise ValueError(f"source_frame must be numeric at point {idx}, got {src_f!r}")

        src_f = float(src_f)

        if comp_f <= prev_comp:
            raise ValueError(f"Non-monotonic comp_frame at point {idx}: {comp_f} <= {prev_comp}")
        if src_f < prev_source:
            raise ValueError(f"Inverted / non-monotonic source_frame at point {idx}: {src_f} < {prev_source}")

        prev_comp = comp_f
        prev_source = src_f
        validated_points.append({"comp_frame": comp_f, "source_frame": src_f})

    # Sample piecewise linear points across [start, end)
    sample_points: list[dict[str, Any]] = []
    pt_idx = 0

    for f in range(start, end):
        while pt_idx < len(validated_points) - 2 and validated_points[pt_idx + 1]["comp_frame"] <= f:
            pt_idx += 1

        p0 = validated_points[pt_idx]
        p1 = validated_points[pt_idx + 1]

        c0, s0 = p0["comp_frame"], p0["source_frame"]
        c1, s1 = p1["comp_frame"], p1["source_frame"]

        if c1 == c0:
            mapped_src = s0
        else:
            alpha = (f - c0) / (c1 - c0)
            mapped_src = s0 + alpha * (s1 - s0)

        sample_points.append({"comp_frame": f, "source_moment": round(mapped_src, 4)})

    return {
        "schema": "amps.god_here.retime_curve.v1",
        "span": {"start": start, "end": end},
        "control_points": validated_points,
        "sample_points": sample_points,
        "monotonic": True,
    }


def detect_phase_lock_conjunctions(
    streams: Sequence[Mapping[str, Any]],
    tolerance_frames: int = 1,
) -> dict[str, Any]:
    if not isinstance(streams, (list, tuple)) or len(streams) < 2:
        raise ValueError("streams must be a sequence of at least 2 stream mappings")

    # Each stream has a stream_id and event_frames list
    stream_events = []
    for s in streams:
        sid = s.get("stream_id", "stream")
        events = sorted(s.get("event_frames", []))
        stream_events.append((sid, events))

    conjunctions: list[dict[str, Any]] = []
    primary_sid, primary_events = stream_events[0]

    for p_frame in primary_events:
        matched_streams = {primary_sid: p_frame}
        all_matched = True

        for other_sid, other_events in stream_events[1:]:
            # Find closest frame within tolerance
            closest = None
            min_diff = 999999
            for o_frame in other_events:
                diff = abs(p_frame - o_frame)
                if diff < min_diff:
                    min_diff = diff
                    closest = o_frame

            if closest is not None and min_diff <= tolerance_frames:
                matched_streams[other_sid] = closest
            else:
                all_matched = False
                break

        if all_matched:
            conjunctions.append({
                "conjunction_frame": p_frame,
                "participating_streams": matched_streams,
                "tolerance_frames": tolerance_frames,
            })

    return {
        "schema": "amps.god_here.phase_lock_conjunctions.v1",
        "tolerance_frames": tolerance_frames,
        "stream_count": len(streams),
        "conjunction_count": len(conjunctions),
        "conjunctions": conjunctions,
    }


def enforce_long_take_continuity_budget(
    retime_curve: Mapping[str, Any],
    max_acceleration: float = 0.15,
) -> dict[str, Any]:
    if not isinstance(retime_curve, Mapping):
        raise ValueError("retime_curve must be a mapping")

    sample_points = retime_curve.get("sample_points", [])
    if len(sample_points) < 3:
        raise ValueError("retime_curve must contain at least 3 sample points")

    # Compute velocity (1st diff) and acceleration (2nd diff)
    velocities: list[float] = []
    for i in range(len(sample_points) - 1):
        v = sample_points[i + 1]["source_moment"] - sample_points[i]["source_moment"]
        velocities.append(v)

    accelerations: list[float] = []
    violations: list[int] = []

    for i in range(len(velocities) - 1):
        acc = abs(velocities[i + 1] - velocities[i])
        accelerations.append(round(acc, 5))
        if acc > max_acceleration:
            frame = sample_points[i + 1]["comp_frame"]
            violations.append(frame)

    max_observed_acc = max(accelerations) if accelerations else 0.0
    passed = len(violations) == 0

    return {
        "schema": "amps.god_here.long_take_continuity_budget.v1",
        "max_acceleration_threshold": max_acceleration,
        "max_observed_acceleration": max_observed_acc,
        "passed": passed,
        "violation_frames": violations,
    }


def compile_macro_section_arc(
    sections: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not isinstance(sections, (list, tuple)) or not sections:
        raise ValueError("sections must be a non-empty sequence")

    total_duration = 0
    prev_end = None
    arc_points = []

    for idx, sec in enumerate(sections):
        if not isinstance(sec, Mapping):
            raise ValueError(f"Section {idx} must be a mapping")

        start = sec.get("start")
        end = sec.get("end")
        if start is None or end is None or end <= start:
            raise ValueError(f"Section {idx} missing valid [start, end) interval")

        # Contiguity check: section i.start == section (i-1).end
        if prev_end is not None and start != prev_end:
            raise ValueError(f"Section gap/overlap at index {idx}: start {start} != previous end {prev_end}")

        prev_end = end
        duration = end - start
        total_duration += duration

        tension = float(sec.get("tension", 0.5))
        arc_points.append({
            "section_id": sec.get("section_id", f"SEC-{idx:02d}"),
            "start": start,
            "end": end,
            "duration_frames": duration,
            "tension": tension,
        })

    return {
        "schema": "amps.god_here.macro_section_arc.v1",
        "section_count": len(sections),
        "total_frames": total_duration,
        "contiguous": True,
        "sections": arc_points,
    }
