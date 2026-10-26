"""Validated decision records and local, atomic composition-identity history."""
from __future__ import annotations

import copy
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping

from .containers import MaterialRef, SourceSpan, Timebase

RUNTIME_SCHEMA = "amps.performance-runtime.v1"
SCALES = frozenset({"edition", "scene", "phrase", "shot", "frame"})
FX_TYPES = frozenset({"routing", "delay", "stutter", "granular", "reverse", "freeze",
                      "feedback", "queue", "gate", "displacement", "exchange", "typography", "damage"})
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")


def canonical_json(value: Any) -> str:
    """Finite JSON only; serialization is also a defensive copy boundary."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _integer(value: Any, role: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{role} must be an integer >= {minimum}")
    return value


def _number(value: Any, role: str, minimum: float, maximum: float) -> float:
    if type(value) not in (int, float) or not minimum <= value <= maximum:
        raise ValueError(f"{role} must be a finite number in {minimum}..{maximum}")
    return value


def _id(value: Any, role: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError(f"{role} must be a public-safe identifier")
    return value


def _public_json(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str) or key.lower() in {"path", "locator", "location", "url", "token"}:
                raise ValueError("Runtime records cannot contain private locators or credentials")
            _public_json(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _public_json(child)
    elif isinstance(value, str) and (value.startswith(("/", "~/", "http://", "https://", "file://"))):
        raise ValueError("Runtime records cannot contain private locators or URLs")


def validate_runtime(runtime: Mapping[str, Any], *, duration_frames: int | None = None) -> None:
    """Validate public-safe graph facts, independently from playback admission."""
    if not isinstance(runtime, Mapping) or runtime.get("schema") != RUNTIME_SCHEMA:
        raise ValueError("Unsupported performance runtime record")
    canonical_json(runtime)
    _public_json(runtime)
    duration = _integer(runtime.get("duration_frames"), "duration_frames", minimum=1)
    if duration_frames is not None and duration != duration_frames:
        raise ValueError("Runtime duration disagrees with the shared performance span")
    _integer(runtime.get("seed"), "seed")
    for name in ("engine_sha256", "rules_sha256", "corpus_sha256"):
        if not isinstance(runtime.get(name), str) or not HASH.fullmatch(runtime[name]):
            raise ValueError(f"{name} must bind the actual public-safe revision")
    profile = runtime.get("profile")
    if not isinstance(profile, Mapping):
        raise ValueError("A performance resource profile is required")
    for name in ("max_depth", "audio_voices", "visual_instances", "pending_events", "lookahead_frames"):
        _integer(profile.get(name), name, minimum=1)
    if type(profile.get("admitted")) is not bool or not isinstance(profile.get("byte_caps"), Mapping):
        raise ValueError("Profile admission and byte caps must be explicit")
    for value in profile["byte_caps"].values():
        _integer(value, "byte cap")
    materials = runtime.get("materials")
    if not isinstance(materials, list) or not materials:
        raise ValueError("Prepared materials are required")
    by_material = {}
    for raw in materials:
        if not isinstance(raw, Mapping):
            raise ValueError("Every prepared material must be a record")
        material = MaterialRef.from_dict(raw)
        _id(material.id, "material id")
        if material.id in by_material or material.span is None or material.span.timebase is None:
            raise ValueError("Prepared material IDs must be unique and clocks explicit")
        qualification = material.metadata.get("qualification", {})
        if qualification.get("technical") != "passed" or "performance" not in qualification.get("allowed_uses", []):
            raise ValueError("Prepared material is not qualified for performance use")
        by_material[material.id] = material
    reference = runtime.get("reference")
    if not isinstance(reference, Mapping) or reference.get("material_id") not in by_material:
        raise ValueError("A protected reference material is required")
    ref = by_material[reference["material_id"]]
    clock = reference.get("clock", {})
    if ref.kind not in {"video", "image", "material"} or clock.get("mode") not in {"loop", "hold"}:
        raise ValueError("Protected reference requires an explicit picture clock")
    if clock.get("start_frame") != ref.span.start or clock.get("end_frame") != ref.span.end:
        raise ValueError("Protected reference clock must preserve the full registered span")
    events = runtime.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("Resolved events are required; a seed alone is not a record")
    seen = {}
    roots = 0
    for event in events:
        if not isinstance(event, Mapping):
            raise ValueError("Every resolved event must be a record")
        identifier = _id(event.get("id"), "event id")
        if identifier in seen:
            raise ValueError("Duplicate event ID")
        start = _integer(event.get("start_frame"), "event start")
        end = _integer(event.get("end_frame"), "event end", minimum=1)
        depth = _integer(event.get("depth"), "event depth")
        if not start < end <= duration or depth > profile["max_depth"] or event.get("scale") not in SCALES:
            raise ValueError("Invalid event span, scale or recursion depth")
        parent_id = event.get("parent_id")
        if parent_id is None:
            roots += 1
            if depth != 0 or event.get("kind") != "container" or start != 0 or end != duration:
                raise ValueError("Only the complete edition container may be a root")
        else:
            parent = seen.get(parent_id)
            if parent is None or parent.get("kind") != "container":
                raise ValueError("Parent must precede its child; cycles and forward parents are invalid")
            if depth != parent["depth"] + 1 or start < parent["start_frame"] or end > parent["end_frame"]:
                raise ValueError("Child escapes its parent span or depth")
        kind = event.get("kind")
        if kind == "material":
            material = by_material.get(event.get("material_id"))
            if material is None:
                raise ValueError("Event uses an unknown prepared material")
            for name in ("picture_clock", "matte_clock", "audio_clock"):
                c = event.get(name)
                if not isinstance(c, Mapping) or c.get("mode") not in {"loop", "hold"}:
                    raise ValueError(f"Explicit {name} is required")
                _integer(c.get("rate_num"), name + " rate numerator", minimum=1)
                _integer(c.get("rate_den"), name + " rate denominator", minimum=1)
                if name == "audio_clock":
                    _integer(c.get("start_sample"), "audio sample")
                    _integer(c.get("sample_rate"), "native audio sample rate", minimum=1)
                else:
                    position = _integer(c.get("start_frame"), name + " position")
                    if not material.span.contains(position):
                        raise ValueError(f"{name} lies outside the prepared material")
            if type(event.get("audio")) is not bool or type(event.get("picture")) is not bool:
                raise ValueError("Event output decisions must be explicit booleans")
            _number(event.get("gain"), "gain", 0, 1)
            _integer(event.get("z_index"), "z index")
            fx = event.get("fx")
            if not isinstance(fx, Mapping) or fx.get("type") not in FX_TYPES:
                raise ValueError("Only retained FX operators may be selected")
            _number(fx.get("intensity"), "FX intensity", 0, 1)
            if not isinstance(event.get("couplings"), list):
                raise ValueError("Event coupling decisions must be explicit")
        elif kind != "container":
            raise ValueError("Unknown resolved event kind")
        seen[identifier] = event
    if roots != 1:
        raise ValueError("Exactly one edition root is required")
    for event in events:
        for edge in event.get("couplings", []):
            if not isinstance(edge, Mapping) or edge.get("source_event_id") not in seen:
                raise ValueError("Unknown coupling source")
            _integer(edge.get("lag_frames"), "coupling delay", minimum=1)
            _number(edge.get("amount"), "coupling amount", -1, 1)
    initial = runtime.get("initial_state")
    if not isinstance(initial, Mapping) or initial.get("frame") != 0 or type(initial.get("playing")) is not bool:
        raise ValueError("Initial clock and play intent must be explicit")


def _record(value: Any) -> dict:
    data = value.to_dict() if hasattr(value, "to_dict") else value
    if not isinstance(data, Mapping):
        raise ValueError("A shared performance record is required")
    data = json.loads(canonical_json(data))
    _id(data.get("composition_id"), "composition id")
    span = SourceSpan.from_dict(data["span"])
    Timebase.from_dict(data["timebase"])
    validate_runtime(data.get("runtime"), duration_frames=span.duration_frames)
    return data


def canonical_identity(record: Any) -> str:
    """Normalize labels/seed/UI metadata while retaining all realized decisions."""
    data = _record(record)
    runtime = copy.deepcopy(data["runtime"])
    event_ids = {event["id"]: index for index, event in enumerate(runtime["events"])}
    material_ids = {material["id"]: {key: value for key, value in material.items()
                                   if key not in {"id", "origin", "metadata", "bytes"}}
                    for material in runtime["materials"]}
    for event in runtime["events"]:
        event["id"] = event_ids[event["id"]]
        if event["parent_id"] is not None:
            event["parent_id"] = event_ids[event["parent_id"]]
        if "material_id" in event:
            event["material_id"] = material_ids[event["material_id"]]
        for edge in event.get("couplings", []):
            edge["source_event_id"] = event_ids[edge["source_event_id"]]
    reference = dict(runtime["reference"])
    reference["material_id"] = material_ids[reference["material_id"]]
    identity = {"composition_id": data["composition_id"], "timebase": data["timebase"],
                "duration_frames": runtime["duration_frames"], "engine_sha256": runtime["engine_sha256"],
                "reference": reference, "events": runtime["events"]}
    return hashlib.sha256(canonical_json(identity).encode()).hexdigest()


class DuplicatePerformance(ValueError):
    """The complete realized graph already exists in the available history."""


class PerformanceHistory:
    def __init__(self, path: str | Path, *, busy_timeout_seconds: float = 5):
        self.path = Path(path)
        if type(busy_timeout_seconds) not in (int, float) or not math.isfinite(busy_timeout_seconds) or busy_timeout_seconds <= 0:
            raise ValueError("History lock timeout must be positive and finite")
        self.busy_timeout_seconds = busy_timeout_seconds

    def _connect(self, *, create=True):
        if create:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
        stat = self.path.lstat()
        if self.path.is_symlink() or not self.path.is_file() or stat.st_uid != os.getuid() or stat.st_mode & 0o077:
            raise ValueError("Performance history must be an owned private regular file")
        connection = sqlite3.connect(self.path.resolve().as_uri() + "?mode=rw", uri=True,
                                     timeout=self.busy_timeout_seconds)
        if create:
            connection.execute("CREATE TABLE IF NOT EXISTS performances (identity TEXT PRIMARY KEY, record_json TEXT NOT NULL, created_at TEXT NOT NULL)")
        return connection

    def reserve(self, record: Any) -> str:
        data = _record(record)
        identity = canonical_identity(data)
        with closing(self._connect()) as connection, connection:
            try:
                connection.execute("INSERT INTO performances VALUES (?, ?, ?)",
                                   (identity, canonical_json(data), datetime.now(timezone.utc).isoformat()))
            except sqlite3.IntegrityError as exc:
                raise DuplicatePerformance(identity) from exc
        return identity

    def load(self, identity: str):
        if not isinstance(identity, str) or not HASH.fullmatch(identity):
            raise ValueError("A canonical composition identity is required")
        with closing(self._connect(create=False)) as connection, connection:
            row = connection.execute("SELECT record_json FROM performances WHERE identity = ?", (identity,)).fetchone()
        if row is None:
            raise KeyError(identity)
        data = json.loads(row[0])
        if canonical_identity(data) != identity:
            raise ValueError("Stored performance no longer matches its canonical identity")
        from .record import PerformanceRecord
        return PerformanceRecord.from_dict(data)
