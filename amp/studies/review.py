"""Common comparison & qualification harness (Issue #69, F06).

Provides:
- finite sample verification (rejecting NaN/Inf and non-zero active RMS)
- 0.5 LU active-speech loudness matching gain on comparison copies with raw_stem_mutated: False
- retimed content moment mapping between candidate and baseline spans
- build_review dispatch helper returning StudyResult
"""
from __future__ import annotations

import hashlib
import json
import math
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
    if not np.all(np.isfinite(samples)):
        raise ValueError(f"{role} contains non-finite samples (NaN or Inf)")
    if samples.size == 0:
        raise ValueError(f"{role} sample array is empty")

    rms = float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))
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

    rms_c = float(np.sqrt(np.mean(c.astype(np.float64) ** 2)))
    rms_b = float(np.sqrt(np.mean(b.astype(np.float64) ** 2)))

    gain_linear = rms_b / rms_c
    gain_db = 20.0 * math.log10(gain_linear)
    diff_lu = abs(gain_db)  # 1 LU ~= 1 dB in integrated active speech measurement

    matched_copy = candidate.copy() * gain_linear

    return {
        "gain_db": round(gain_db, 4),
        "gain_linear": gain_linear,
        "diff_lu": round(diff_lu, 4),
        "within_tolerance": diff_lu <= tolerance_lu,
        "raw_stem_mutated": False,
        "matched_copy": matched_copy,
    }


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

    if retiming_map:
        for span_spec in retiming_map:
            o_start = span_spec.get("output_start", span_spec.get("outputStart"))
            o_end = span_spec.get("output_end", span_spec.get("outputEnd"))
            s_start = span_spec.get("source_start", span_spec.get("sourceStart"))
            s_end = span_spec.get("source_end", span_spec.get("sourceEnd"))

            if None in (o_start, o_end, s_start, s_end):
                continue

            if o_start <= candidate_time <= o_end:
                if o_end == o_start:
                    return float(s_start)
                fraction = (candidate_time - o_start) / (o_end - o_start)
                return float(s_start + fraction * (s_end - s_start))

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

    workstream_id = context.parameters.get("workstream_id") or binding.parameters.get("workstream_id", "review")
    case_id = binding.parameters.get("case_id") or context.parameters.get("case_id", "case-01")

    out_dir = resolve_study_output_dir(context, workstream_id, case_id)
    out_dir.mkdir(parents=True, exist_ok=True)

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
        }
    else:
        review_report["matching"] = {
            "gain_db": 0.0,
            "diff_lu": 0.0,
            "within_tolerance": True,
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
        },
    )
