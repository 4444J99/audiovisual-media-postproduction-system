"""Audit source-frame coverage and admit explicitly reviewed linguistic units.

This module validates recorded evidence, not the truth of a listening decision.
All frame intervals are half-open. Historical ``eligible`` flags have no effect.
The caller must supply the independently bound source and current unit records;
copying the document's own source into that argument does not verify identity.
"""

from fractions import Fraction
import re
from typing import Any


DISPOSITIONS = frozenset({
    "pending", "uncertain", "texture_only", "verified", "non_speech",
})
EVIDENCE_ASPECTS = ("words", "speaker", "boundaries")


def _object(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _list(value: Any, label: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def _identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a non-empty, trimmed string")
    return value


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    # bool is an int subclass; frame and timebase fields must never accept it.
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{label} must be a lowercase SHA256 identity")
    return value


def _source(value: Any, label: str) -> dict:
    value = _object(value, label)
    sha256 = _sha256(value.get("sha256"), f"{label}.sha256")
    frame_count = _integer(value.get("frame_count"), f"{label}.frame_count", 1)
    fps = _object(value.get("fps"), f"{label}.fps")
    numerator = _integer(fps.get("numerator"), f"{label}.fps.numerator", 1)
    denominator = _integer(fps.get("denominator"), f"{label}.fps.denominator", 1)
    rate = Fraction(numerator, denominator)
    return {
        "sha256": sha256,
        "frame_count": frame_count,
        "fps": {"numerator": rate.numerator, "denominator": rate.denominator},
    }


def _bounds(value: dict, frame_count: int, label: str) -> tuple[int, int]:
    start = _integer(value.get("start_frame"), f"{label}.start_frame")
    end = _integer(value.get("end_frame"), f"{label}.end_frame", 1)
    if start >= end or end > frame_count:
        raise ValueError(f"{label} has empty, reversed, or out-of-source bounds")
    return start, end


def _disposition(value: Any, label: str) -> str:
    if not isinstance(value, str) or value not in DISPOSITIONS:
        raise ValueError(f"{label} must be a recognized disposition")
    return value


def _evidence(value: Any, label: str, *, required: bool) -> None:
    evidence = _object(value, label)
    unknown = set(evidence) - set(EVIDENCE_ASPECTS)
    if unknown:
        raise ValueError(f"{label} contains unknown evidence aspects")
    for aspect in EVIDENCE_ASPECTS:
        if aspect not in evidence:
            if required:
                raise ValueError(f"{label}.{aspect} requires listened evidence")
            continue
        record = _object(evidence[aspect], f"{label}.{aspect}")
        if record.get("method") != "listened":
            raise ValueError(f"{label}.{aspect} requires method 'listened'")
        _identity(record.get("reviewer"), f"{label}.{aspect}.reviewer")
        _identity(record.get("evidence_id"), f"{label}.{aspect}.evidence_id")


def audit_qualification(document: dict, *, source: dict, units: list[dict]) -> dict:
    """Return coverage and admitted IDs, raising ValueError for invalid records.

    ``source`` contains sha256, frame_count and fps {numerator, denominator}.
    Each current unit contains id, source_sha256, start_frame and end_frame.
    The version 1.0 document contains the same source, a complete ``intervals``
    partition (id, start_frame, end_frame, disposition), and ``unit_reviews``.
    Reviews bind unit_id, source_sha256 and exact bounds, with a disposition.
    Verified reviews require words/speaker/boundaries evidence, each containing
    method="listened", reviewer and evidence_id. Evidence references may point
    to private custody; this API never reads or publishes their contents.

    A well-formed pending review is retained but never admitted. Reviewed units
    overlapping any interval that is not verified are also excluded. Coverage
    alone is never evidence that a unit's language was checked. Inputs are not
    changed and no file or network operations are performed.
    """
    document = _object(document, "qualification")
    if document.get("schema_version") != "1.0":
        raise ValueError("Unsupported qualification schema_version")
    bound_source = _source(source, "source")
    if _source(document.get("source"), "qualification.source") != bound_source:
        raise ValueError("Qualification source identity or timebase is stale")
    frame_count = bound_source["frame_count"]

    coverage = []
    interval_ids = set()
    frames_by_disposition = {name: 0 for name in sorted(DISPOSITIONS)}
    for index, value in enumerate(_list(document.get("intervals"), "intervals")):
        label = f"intervals[{index}]"
        interval = _object(value, label)
        interval_id = _identity(interval.get("id"), f"{label}.id")
        if interval_id in interval_ids:
            raise ValueError(f"Duplicate interval id: {interval_id}")
        interval_ids.add(interval_id)
        start, end = _bounds(interval, frame_count, label)
        disposition = _disposition(interval.get("disposition"), f"{label}.disposition")
        coverage.append((start, end, disposition))
        frames_by_disposition[disposition] += end - start
    cursor = 0
    for start, end, _ in sorted(coverage):
        if start != cursor:
            raise ValueError("Source intervals must cover every frame without gaps or overlaps")
        cursor = end
    if cursor != frame_count:
        raise ValueError("Source intervals must cover every frame through the final tail")

    current_units = {}
    for index, value in enumerate(_list(units, "units")):
        label = f"units[{index}]"
        unit = _object(value, label)
        unit_id = _identity(unit.get("id"), f"{label}.id")
        if unit_id in current_units:
            raise ValueError(f"Duplicate unit id: {unit_id}")
        if _sha256(unit.get("source_sha256"), f"{label}.source_sha256") != bound_source["sha256"]:
            raise ValueError(f"Unit {unit_id} is bound to a different source")
        current_units[unit_id] = _bounds(unit, frame_count, label)

    reviews = {}
    for index, value in enumerate(_list(document.get("unit_reviews"), "unit_reviews")):
        label = f"unit_reviews[{index}]"
        review = _object(value, label)
        unit_id = _identity(review.get("unit_id"), f"{label}.unit_id")
        if unit_id in reviews:
            raise ValueError(f"Duplicate unit review: {unit_id}")
        if unit_id not in current_units:
            raise ValueError(f"Review references unknown unit: {unit_id}")
        if _sha256(review.get("source_sha256"), f"{label}.source_sha256") != bound_source["sha256"]:
            raise ValueError(f"Review for {unit_id} is bound to a different source")
        if _bounds(review, frame_count, label) != current_units[unit_id]:
            raise ValueError(f"Review for {unit_id} has stale unit bounds")
        disposition = _disposition(review.get("disposition"), f"{label}.disposition")
        _evidence(review.get("evidence", {}), f"{label}.evidence", required=disposition == "verified")
        reviews[unit_id] = disposition

    qualified = []
    excluded = []
    for unit_id, (start, end) in current_units.items():
        reasons = []
        if unit_id not in reviews:
            reasons.append("no_review")
        elif reviews[unit_id] != "verified":
            reasons.append(f"unit_disposition:{reviews[unit_id]}")
        overlapping = {
            disposition for left, right, disposition in coverage
            if left < end and right > start and disposition != "verified"
        }
        reasons.extend(f"interval_disposition:{value}" for value in sorted(overlapping))
        if reasons:
            excluded.append({"unit_id": unit_id, "reasons": reasons})
        else:
            qualified.append(unit_id)

    return {
        "schema_version": "1.0",
        "source": bound_source,
        "coverage": {
            "frame_count": frame_count,
            "frames_by_disposition": frames_by_disposition,
        },
        "qualified_unit_ids": qualified,
        "excluded_units": excluded,
    }


def require_linguistic_units(document: dict, *, source: dict, units: list[dict]) -> list[str]:
    """Return explicitly admitted IDs or fail closed when none are qualified."""
    result = audit_qualification(document, source=source, units=units)
    if not result["qualified_unit_ids"]:
        raise ValueError("No source units have complete linguistic qualification")
    return result["qualified_unit_ids"]
