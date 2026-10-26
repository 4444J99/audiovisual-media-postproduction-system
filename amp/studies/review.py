"""Common comparison & qualification harness (Issue #69, F06).

Provides:
- finite sample verification (rejecting NaN/Inf and non-zero active RMS)
- RMS-only gain estimates; actual BS.1770 comparison copies use review_artifacts
- retimed content moment mapping between candidate and baseline spans
- build_review dispatch helper returning StudyResult
"""
from __future__ import annotations

import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from amp.composition.containers import (
    MaterialRef,
    SourceSpan,
    StudyBinding,
    StudyContext,
    StudyResult,
    Timebase,
)
from amp.studies.dispatch import resolve_study_output_dir


def verify_finite_samples(samples: np.ndarray, role: str = "audio", min_rms: float = 1e-9) -> np.ndarray:
    if not isinstance(samples, np.ndarray):
        raise ValueError(f"Expected numpy.ndarray for {role}, got {type(samples).__name__}")
    if samples.dtype.kind not in "fiu" or samples.ndim not in (1, 2):
        raise ValueError(f"{role} must contain real audio samples")
    if type(min_rms) not in (int, float) or not math.isfinite(min_rms) or min_rms <= 0:
        raise ValueError("min_rms must be finite and positive")
    if not np.all(np.isfinite(samples)):
        raise ValueError(f"{role} contains non-finite samples (NaN or Inf)")
    if samples.size == 0:
        raise ValueError(f"{role} sample array is empty")

    peak = float(np.max(np.abs(samples.astype(np.float64))))
    rms = peak * float(np.sqrt(np.mean((samples.astype(np.float64)/peak) ** 2))) if peak else 0.0
    if rms < min_rms:
        raise ValueError(f"{role} contains zero active RMS ({rms:.3e} < {min_rms:.3e})")
    return samples


def compute_loudness_matching_gain(
    candidate: np.ndarray,
    baseline: np.ndarray,
    tolerance_lu: float = 0.5,
) -> dict[str, Any]:
    c = verify_finite_samples(candidate, "candidate")
    b = verify_finite_samples(baseline, "baseline")

    peak_c = float(np.max(np.abs(c.astype(np.float64))))
    peak_b = float(np.max(np.abs(b.astype(np.float64))))
    rms_c = peak_c * float(np.sqrt(np.mean((c.astype(np.float64)/peak_c) ** 2)))
    rms_b = peak_b * float(np.sqrt(np.mean((b.astype(np.float64)/peak_b) ** 2)))

    gain_linear = rms_b / rms_c
    gain_db = 20.0 * math.log10(gain_linear)
    if not math.isfinite(gain_linear) or type(tolerance_lu) not in (int, float) or not math.isfinite(tolerance_lu) or tolerance_lu < 0:
        raise ValueError("Invalid RMS gain or comparison threshold")

    matched_copy = candidate.copy() * gain_linear
    if not np.isfinite(matched_copy).all():
        raise ValueError("RMS-matched estimate is not finite")

    return {
        "gain_db": round(gain_db, 4),
        "gain_linear": gain_linear,
        "rms_gain_db": round(gain_db, 4),
        "diff_lu": None,
        "within_tolerance": None,
        "method": "RMS-estimate-only; no BS.1770 or active-speech measurement",
        "raw_stem_mutated": False,
        "matched_copy": matched_copy,
    }


def validated_retiming_map(candidate_span, baseline_span, mapping):
    if not isinstance(mapping, (list, tuple)) or not mapping:
        raise ValueError("Explicit retiming map must be nonempty")
    rows = []
    cursor = Fraction(candidate_span.start)
    for spec in mapping:
        if not isinstance(spec, Mapping):
            raise ValueError("Retiming segment must be an object")
        values = []
        for snake, camel in (("output_start","outputStart"),("output_end","outputEnd"),
                             ("source_start","sourceStart"),("source_end","sourceEnd")):
            value = spec.get(snake, spec.get(camel))
            if snake in spec and camel in spec and spec[snake] != spec[camel]:
                raise ValueError("Conflicting retiming aliases")
            try:
                valid = type(value) in (int,float) and math.isfinite(value)
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError("Retiming endpoints must be finite real coordinates")
            values.append(Fraction(str(value)))
        a,b,c,d = values
        if a != cursor or b <= a or b > candidate_span.end or not all(baseline_span.start <= x <= baseline_span.end for x in (c,d)):
            raise ValueError("Retiming map is gapped, overlapping or outside declared spans")
        rows.append((a,b,c,d));cursor = b
    if cursor != candidate_span.end:
        raise ValueError("Retiming map must cover the full candidate span")
    return rows


def map_retimed_moments(
    candidate_time: float,
    candidate_span: SourceSpan,
    baseline_span: SourceSpan,
    retiming_map: Optional[Sequence[Mapping[str, float]]] = None,
) -> float:
    if isinstance(candidate_time, bool) or not isinstance(candidate_time, (int, float)) or not math.isfinite(candidate_time):
        raise ValueError(f"candidate_time must be a finite real number, got {candidate_time!r}")

    if not isinstance(candidate_span, SourceSpan) or not isinstance(baseline_span, SourceSpan):
        raise ValueError("candidate_span and baseline_span must be SourceSpan instances")

    c_start = candidate_span.start
    c_end = candidate_span.end
    if not c_start <= candidate_time <= c_end:
        raise ValueError(f"Candidate time {candidate_time} outside candidate span [{c_start}, {c_end}]")

    if retiming_map is not None:
        for o_start,o_end,s_start,s_end in validated_retiming_map(candidate_span,baseline_span,retiming_map):
            if o_start <= candidate_time < o_end or candidate_time == c_end == o_end:
                fraction = (Fraction(str(candidate_time))-o_start)/(o_end-o_start)
                return float(s_start+fraction*(s_end-s_start))
        raise ValueError("Candidate position is not mapped")

    # Proportional fallback
    if c_end == c_start:
        return float(baseline_span.start)
    fraction = (candidate_time - c_start) / (c_end - c_start)
    return float(baseline_span.start + fraction * (baseline_span.end - baseline_span.start))


def build_review(binding: StudyBinding, context: StudyContext) -> StudyResult:
    if not isinstance(binding, StudyBinding):
        raise ValueError(f"Expected StudyBinding, got {type(binding).__name__}")
    if not isinstance(context, StudyContext):
        raise ValueError(f"Expected StudyContext, got {type(context).__name__}")
    if binding.operator == "amp.review.v1":
        from .review_artifacts import build_measured_review
        return build_measured_review(binding, context)

    workstream_id = context.parameters.get("workstream_id") or binding.parameters.get("workstream_id", "review")
    case_id = binding.parameters.get("case_id") or context.parameters.get("case_id", "case-01")

    out_dir = resolve_study_output_dir(context, workstream_id, case_id)
    out_dir.mkdir(parents=True, exist_ok=False)

    span = binding.span or context.span or SourceSpan(0, 3360, context.timebase)

    review_report: dict[str, Any] = {
        "schema_version": "amps.review-result.v1",
        "study_id": context.study_id,
        "operator": binding.operator,
        "span": span.to_dict(),
        "workstream_id": workstream_id,
        "case_id": case_id,
        "raw_stem_mutated": False,
        "matching": {},
    }

    # If samples are provided in parameters, compute loudness matching
    candidate_samples = binding.parameters.get("candidate_samples")
    baseline_samples = binding.parameters.get("baseline_samples")

    if candidate_samples is not None and baseline_samples is not None:
        c_arr = np.asarray(candidate_samples, dtype=np.float64)
        b_arr = np.asarray(baseline_samples, dtype=np.float64)
        matching = compute_loudness_matching_gain(c_arr, b_arr)
        review_report["matching"] = {
            "gain_db": matching["gain_db"],
            "diff_lu": matching["diff_lu"],
            "within_tolerance": matching["within_tolerance"],
            "raw_stem_mutated": matching["raw_stem_mutated"],
            "rms_gain_db": matching["rms_gain_db"],
            "method": matching["method"],
        }
    else:
        review_report["matching"] = {
            "gain_db": None,
            "diff_lu": None,
            "within_tolerance": None,
            "method": "not_tested; complete measured media inputs absent",
            "raw_stem_mutated": False,
        }

    report_bytes = json.dumps(review_report, indent=2, sort_keys=True).encode("utf-8")
    report_file = out_dir / "review-result.json"
    report_file.write_bytes(report_bytes)

    report_sha = hashlib.sha256(report_bytes).hexdigest()
    product_ref = MaterialRef(
        id=f"rev-{report_sha[:12]}",
        sha256=report_sha,
        kind="metadata",
        bytes=len(report_bytes),
        path=str(report_file),
        span=span,
    )

    return StudyResult(
        study_id=context.study_id,
        operator=binding.operator,
        span=span,
        products=(product_ref,),
        metadata={
            "workstream_id": workstream_id,
            "case_id": case_id,
            "output_dir": str(out_dir),
            "raw_stem_mutated": False,
            "review_sha256": report_sha,
            "technical": "not_tested",
        },
    )
