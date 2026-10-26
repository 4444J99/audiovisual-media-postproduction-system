"""F02 source-bound benchmark audit; recorded reviews are not new listening.

The caller supplies independently registered source identity. This validator does
not authenticate a reviewer or retrieve private evidence; it validates bindings,
methods and independent dispositions without treating historical text as proof.
"""
from __future__ import annotations

from fractions import Fraction

from amp.qualification import _source, _evidence, _identity

AXES = ("audio", "image", "action", "annotation")
CASE_AXES = {
    "quiet_speech": ("audio", "annotation"),
    "overlap": ("audio", "annotation"),
    "visible_object_sound": AXES,
    "simple_surface": ("image", "annotation"),
    "occlusion_cut": ("image", "action", "annotation"),
    "semantic_exchange": AXES,
}
METHODS = {"image":"viewed", "action":"observed", "annotation":"compared_to_source"}
STATUSES = {"pending", "uncertain", "verified", "rejected"}


def object_value(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def records(value, label):
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def frame_span(value, count):
    if not isinstance(value, list) or len(value) != 2 or any(type(x) is not int for x in value):
        raise ValueError("frame_span requires two integer endpoints")
    start, end = value
    if not 0 <= start < end <= count:
        raise ValueError("frame_span is outside the registered source")
    return start, end


def dispositions(review):
    values = object_value(review.get("dispositions", {}), "dispositions")
    if set(values)-set(AXES):
        raise ValueError("Unknown benchmark disposition axis")
    result = {}
    for axis in AXES:
        value = object_value(values.get(axis, {"status":"pending"}), axis)
        status = value.get("status")
        if not isinstance(status, str) or status not in STATUSES:
            raise ValueError("Invalid benchmark disposition")
        evidence = object_value(value.get("evidence", {}), "evidence")
        if status == "verified":
            if axis == "audio":
                _evidence(evidence, "audio", required=True)
            else:
                if evidence.get("method") != METHODS[axis]:
                    raise ValueError(f"{axis} requires {METHODS[axis]} evidence")
                _identity(evidence.get("reviewer"), "reviewer")
                _identity(evidence.get("evidence_id"), "evidence_id")
        result[axis] = status
    return result


def audit_benchmark(benchmark, reviews, *, source):
    """Return qualified wording/category coverage, preserving independent axes.

    Audio verification requires listened words, speaker and boundaries evidence.
    Other axes require their own source observation. Every review binds source hash
    and exact frame interval. Draft text, confidence, playback flags and historical
    records have no qualification effect. Sample maps use exact frame time, with
    each sample endpoint floored in its independently declared 44100/48000 domain.
    """
    benchmark = object_value(benchmark, "benchmark")
    reviews = object_value(reviews, "reviews")
    if benchmark.get("schema") != "amps.god_here.benchmark.v1" or reviews.get("schema") != "amps.god_here.units_review.v1":
        raise ValueError("Unsupported benchmark or review schema")
    registered = _source(source, "source")
    for document in (benchmark, reviews):
        if _source(document.get("source"), "document.source") != registered:
            raise ValueError("Benchmark source identity or timebase is stale")
    fps = Fraction(registered["fps"]["numerator"], registered["fps"]["denominator"])
    if "spine" in benchmark:
        spine = object_value(benchmark["spine"], "spine")
        rate = spine.get("fps")
        if type(rate) not in (int, float) or Fraction(str(rate)) != fps:
            raise ValueError("Benchmark spine fps contradicts registered source")
        expected_spine = dict(total_frames=registered["frame_count"],native_audio_rate_hz=44100,
            derivative_audio_rate_hz=48000,
            native_total_samples=int(Fraction(registered["frame_count"]*44100, 1)/fps),
            derivative_total_samples=int(Fraction(registered["frame_count"]*48000, 1)/fps))
        if any(type(spine.get(key)) is not int or spine[key] != value for key,value in expected_spine.items()):
            raise ValueError("Benchmark spine contradicts registered frame/sample domains")
    units = {}
    for value in records(benchmark.get("units"), "benchmark.units"):
        unit = object_value(value, "unit")
        unit_id = _identity(unit.get("id"), "unit.id")
        if unit_id in units:
            raise ValueError("Duplicate benchmark unit")
        if unit.get("source_sha256") != registered["sha256"]:
            raise ValueError("Benchmark unit source identity is stale")
        span = frame_span(unit.get("frame_span"), registered["frame_count"])
        case = unit.get("case_type")
        if case is not None and (not isinstance(case, str) or case not in CASE_AXES):
            raise ValueError("Unknown benchmark case type")
        for rate, key in ((44100,"sample_span_44k1"),(48000,"sample_span_48k")):
            actual = unit.get(key)
            expected = [int(Fraction(frame*rate, 1)/fps) for frame in span]
            if not isinstance(actual, list) or any(type(x) is not int for x in actual) or actual != expected:
                raise ValueError("Sample map does not match exact source frame boundaries")
        units[unit_id] = unit
    bound_reviews = {}
    for value in records(reviews.get("units"), "reviews.units"):
        review = object_value(value, "review")
        unit_id = _identity(review.get("unit_id"), "review.unit_id")
        if unit_id in bound_reviews or unit_id not in units:
            raise ValueError("Duplicate or unknown benchmark review")
        if review.get("source_sha256") != registered["sha256"] or frame_span(review.get("frame_span"),registered["frame_count"]) != tuple(units[unit_id]["frame_span"]):
            raise ValueError("Benchmark review source or interval is stale")
        if review.get("case_type") != units[unit_id].get("case_type"):
            raise ValueError("Benchmark review case assignment is stale")
        bound_reviews[unit_id] = review
    reports, vocabulary, usable = [], [], set()
    for unit_id, unit in units.items():
        review = bound_reviews.get(unit_id, {})
        axes = dispositions(review)
        wording = review.get("reviewed_heard_wording")
        if wording is not None and not isinstance(wording, str):
            raise ValueError("Heard wording must be text or null")
        if axes["audio"] == "verified" and wording is None:
            raise ValueError("Verified audio requires reviewed heard wording, including empty text for no speech")
        words_verified = axes["audio"] == "verified" and axes["annotation"] == "verified"
        if words_verified and wording is not None and wording.strip():
            vocabulary.append({"unit_id":unit_id,"heard_wording":wording})
        case_type = unit["case_type"]
        case_usable = case_type is not None and all(axes[axis] == "verified" for axis in CASE_AXES[case_type])
        if case_usable:
            usable.add(case_type)
        reports.append(dict(unit_id=unit_id,frame_span=list(unit["frame_span"]),case_type=case_type,
            dispositions=axes,words_verified=words_verified,case_usable=case_usable))
    missing = sorted(set(CASE_AXES)-usable)
    return dict(schema="amps.benchmark-audit.v1",source=registered,units=reports,vocabulary=vocabulary,
        usable_case_types=sorted(usable),missing_case_types=missing,
        complete=bool(units) and not missing and all(all(x=="verified" for x in unit["dispositions"].values()) for unit in reports))
