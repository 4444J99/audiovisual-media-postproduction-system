"""Bounded source-mixture schedules and explicit linguistic admission."""
from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import math
import random

from .qualification import require_linguistic_units


def frame_units(units, source):
    """Adapt existing seconds records without silently snapping a phrase edge."""
    fps_record = source["fps"]
    for value in (fps_record["numerator"], fps_record["denominator"], source["frame_count"]):
        if type(value) is not int or value <= 0:
            raise ValueError("Source timebase requires positive integers")
    fps = Fraction(fps_record["numerator"], fps_record["denominator"])
    result = []
    for unit in units:
        bounds = []
        for name in ("start", "end"):
            value = unit[name]
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("Source bounds must be finite numbers")
            exact = Fraction(str(value)) * fps
            frame = round(exact)
            if abs(exact - frame) > Fraction(1, 1000000):
                raise ValueError("Source bound is not on the registered frame grid")
            bounds.append(frame)
        binding = {"source_sha256": source["sha256"], "start_frame": bounds[0], "end_frame": bounds[1]}
        for key, value in binding.items():
            if key in unit and (type(unit[key]) is not type(value) or unit[key] != value):
                raise ValueError("Existing source unit binding conflicts with registered frame mapping")
        result.append({**unit, **binding})
    return result


def generate_schedule(units, seed, count=5, *, generation_mode="source-mixture",
                      qualification=None, source=None):
    if type(count) is not int or not 1 <= count <= 256:
        raise ValueError("Schedule count must be an integer between 1 and 256")
    if generation_mode not in {"source-mixture", "linguistic"}:
        raise ValueError("Unknown generation mode")
    ids = [u["id"] for u in units]
    if any(not isinstance(uid, str) or not uid for uid in ids) or len(set(ids)) != len(ids):
        raise ValueError("Source unit IDs must be nonempty and unique")
    if generation_mode == "linguistic":
        if qualification is None or source is None:
            raise ValueError("Linguistic generation requires source-bound qualification")
        adapted = frame_units(units, source)
        admitted = set(require_linguistic_units(qualification, source=source, units=adapted))
        units = [{**u, "eligible": u.get("eligible") is True and u["id"] in admitted} for u in units]
    elif qualification is not None:
        raise ValueError("Qualification requires explicit linguistic generation mode")
    rng = random.Random(seed)
    by_id = {u["id"]: u for u in units}
    eligible = [u for u in units if u.get("eligible") is True]
    if len(eligible) < 2:
        raise ValueError("Not enough admitted source units")
    selected = eligible[0]
    events, clock = [], 0.0
    for i in range(count):
        if any(type(selected[k]) not in (int, float) or not math.isfinite(selected[k]) for k in ("start", "end")) or not 0 <= selected["start"] < selected["end"]:
            raise ValueError("Invalid source unit")
        duration = selected["end"] - selected["start"]
        events.append({"unit": selected["id"], "source_start": selected["start"], "source_end": selected["end"],
                       "output_start": round(clock, 6), "output_end": round(clock + duration, 6)})
        clock += duration
        choices = [by_id[x] for x in selected["allowed_next"] if x in by_id and by_id[x].get("eligible") is True]
        choices = [x for x in choices if sum(e["unit"] == x["id"] for e in events) < 2]
        if i < count - 2:
            nonterminals = [x for x in choices if not x.get("terminal")]
            if nonterminals:
                choices = nonterminals
        elif i == count - 2:
            terminals = [x for x in choices if x.get("terminal")]
            if terminals:
                choices = terminals
        if not choices and i + 1 < count:
            raise ValueError("Transition grammar exhausted")
        if choices:
            selected = rng.choice(choices)
    result = {"schema_version": "1.0", "seed": seed, "rules_version": "1.0", "authored_reordering": True,
            "text_verification": "provisional; no invented wording", "events": events, "duration": round(clock, 6)}
    if generation_mode == "linguistic":
        result.update({"generation_mode": "linguistic", "source": source,
                       "qualification_sha256": hashlib.sha256(json.dumps(qualification, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
                       "text_verification": "source-bound listened review records; artistic acceptance separate"})
        by_frame_id = {unit["id"]: unit for unit in adapted}
        output_frame = 0
        for event in events:
            unit = by_frame_id[event["unit"]]
            frames = unit["end_frame"] - unit["start_frame"]
            event.update({"source_start_frame": unit["start_frame"], "source_end_frame": unit["end_frame"],
                          "output_start_frame": output_frame, "output_end_frame": output_frame + frames})
            output_frame += frames
    return result
