"""Recorded multiscale planning and bounded supervision of prepared materials.

No renderer, model invocation, source extraction or media locator lives here.
Planning is distinct from admitted playback and from artistic acceptance.
"""
from __future__ import annotations

import copy
from bisect import bisect_right
from fractions import Fraction
import hashlib
import json
import random
from typing import Any, Mapping

from .containers import MaterialRef, SourceSpan, Timebase
from .novelty import FX_TYPES, RUNTIME_SCHEMA, _id, _integer, _number, canonical_identity, canonical_json, validate_runtime
from .record import PerformanceRecord

BYTE_RESOURCES = ("decoded_audio_bytes", "texture_bytes", "event_history_bytes")


class PerformanceBlocked(ValueError):
    """A factual input or admission requirement is unavailable."""


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def plan_performance(corpus: Mapping[str, Any], profile: Mapping[str, Any], *,
                     seed: int, duration_frames: int, record_id: str) -> PerformanceRecord:
    """Resolve the complete finite graph; the supervisor queues only its horizon."""
    if not isinstance(corpus, Mapping) or corpus.get("schema") != "amps.performance-corpus.v1":
        raise ValueError("An explicit prepared performance corpus is required")
    _integer(seed, "seed")
    _integer(duration_frames, "duration_frames", minimum=1)
    _id(record_id, "record id")
    timebase = Timebase.from_dict(corpus["timebase"])
    runtime = {
        "schema": RUNTIME_SCHEMA, "seed": seed, "duration_frames": duration_frames,
        "engine_sha256": corpus["engine_sha256"], "rules_sha256": _hash(profile),
        "corpus_sha256": _hash(corpus), "profile": copy.deepcopy(profile),
        "materials": copy.deepcopy(corpus["materials"]), "reference": copy.deepcopy(corpus["reference"]),
        "fallback_material_id": corpus.get("fallback_material_id"),
        "events": [{"id": "edition", "parent_id": None, "kind": "container", "scale": "edition",
                    "depth": 0, "start_frame": 0, "end_frame": duration_frames}],
        "initial_state": {"frame": 0, "playing": False},
    }
    validate_runtime(runtime, duration_frames=duration_frames)
    materials = [MaterialRef.from_dict(raw) for raw in runtime["materials"]]
    if runtime["fallback_material_id"] not in {material.id for material in materials}:
        raise ValueError("A qualified prepared fallback must be explicit")
    for material in materials:
        _integer(material.metadata.get("audio_sample_rate"), "prepared audio sample rate", minimum=1)
        _integer(material.metadata.get("audio_origin_sample"), "prepared audio origin")
        _integer(material.metadata.get("audio_sample_count"), "prepared audio sample count", minimum=1)
    layers = profile.get("layers")
    if not isinstance(layers, list) or not layers:
        raise ValueError("Authored temporal layers are required")
    layer_ids = set()
    rng = random.Random(seed)
    for layer_index, layer in enumerate(layers):
        name = _id(layer.get("id"), "layer id")
        if name in layer_ids or layer.get("scale") not in {"scene", "phrase", "shot", "frame"}:
            raise ValueError("Temporal layer IDs and scales must be valid and unique")
        layer_ids.add(name)
        durations = layer.get("duration_frames")
        if not isinstance(durations, list) or len(durations) != 2:
            raise ValueError("Layer duration range is required")
        low, high = (_integer(value, "layer duration", minimum=1) for value in durations)
        if high < low:
            raise ValueError("Layer duration range is reversed")
        for key in ("gain", "intensity"):
            values = layer.get(key)
            if not isinstance(values, list) or len(values) != 2:
                raise ValueError(f"Layer {key} range is required")
            for value in values:
                _number(value, key, 0, 1)
            if values[1] < values[0]:
                raise ValueError(f"Layer {key} range is reversed")
        choices = layer.get("fx_types")
        if not isinstance(choices, list) or not choices or any(kind not in FX_TYPES for kind in choices):
            raise ValueError("Layer FX choices must use retained operators")
        reuse_every = _integer(layer.get("reuse_every"), "reuse cadence", minimum=1)
        coupling = _number(layer.get("coupling_amount", 0.25), "coupling amount", -1, 1)
        lag = _integer(layer.get("coupling_lag_frames", 1), "coupling lag", minimum=1)
        clock, index, first = 0, 0, None
        while clock < duration_frames:
            reuse = first is not None and index % reuse_every == 0
            length = first["length"] if reuse else rng.randint(low, high)
            length = min(length, duration_frames - clock)
            parent_id = f"{name}-{index}"
            parent = {"id": parent_id, "parent_id": "edition", "kind": "container",
                      "scale": layer["scale"], "depth": 1, "start_frame": clock, "end_frame": clock + length}
            if reuse:
                parent["reused_from"] = first["parent_id"]
            runtime["events"].append(parent)
            pair = []
            for output in ("audio", "picture"):
                if reuse:
                    event = copy.deepcopy(first[output])
                    event["reused_from"] = event["id"]
                    event.update(id=f"{parent_id}-{output}", parent_id=parent_id,
                                 start_frame=clock, end_frame=clock + length)
                else:
                    material = rng.choice(materials)
                    start = rng.randrange(material.span.start, material.span.end)
                    sample_rate = material.metadata["audio_sample_rate"]
                    audio_origin = material.metadata["audio_origin_sample"]
                    sample = rng.randrange(audio_origin, audio_origin + material.metadata["audio_sample_count"])
                    event = {
                        "id": f"{parent_id}-{output}", "parent_id": parent_id, "kind": "material",
                        "scale": layer["scale"], "depth": 2, "start_frame": clock, "end_frame": clock + length,
                        "material_id": material.id,
                        "picture_clock": {"start_frame": start, "rate_num": 1, "rate_den": 1, "mode": "loop"},
                        "matte_clock": {"start_frame": start, "rate_num": 1, "rate_den": 1, "mode": "loop"},
                        "audio_clock": {"start_sample": sample, "sample_rate": sample_rate,
                                        "rate_num": 1, "rate_den": 1, "mode": "loop"},
                        "audio": output == "audio", "picture": output == "picture",
                        "gain": round(rng.uniform(*layer["gain"]), 6), "z_index": layer_index,
                        "fx": {"type": rng.choice(choices), "intensity": round(rng.uniform(*layer["intensity"]), 6)},
                        "couplings": [],
                    }
                pair.append(event)
            for target, source in ((pair[0], pair[1]), (pair[1], pair[0])):
                target["couplings"] = [{"source_event_id": source["id"], "lag_frames": lag, "amount": coupling}]
            runtime["events"].extend(pair)
            if first is None:
                first = {"length": length, "parent_id": parent_id,
                         "audio": copy.deepcopy(pair[0]), "picture": copy.deepcopy(pair[1])}
            clock += length
            index += 1
    validate_runtime(runtime, duration_frames=duration_frames)
    return PerformanceRecord(record_id=record_id, composition_id=corpus["composition_id"],
                             span=SourceSpan(0, duration_frames), timebase=timebase, runtime=runtime,
                             provenance={"runtime_status": "planned", "artistic_acceptance": "pending"})


class PerformanceSupervisor:
    """One record, explicit clock and recoverable bounded scheduling state."""
    def __init__(self, record: PerformanceRecord | Mapping[str, Any], *, simulation: bool = False):
        data = record.to_dict() if isinstance(record, PerformanceRecord) else record
        self.record = PerformanceRecord.from_dict(copy.deepcopy(data))
        self.runtime = self.record.to_dict()["runtime"]
        self.profile = self.runtime["profile"]
        self.materials = {m["id"]: MaterialRef.from_dict(m) for m in self.runtime["materials"]}
        self.events = [event for event in self.runtime["events"] if event["kind"] == "material"]
        self.duration = self.runtime["duration_frames"]
        self.simulation = simulation is True
        self.admitted = self.simulation
        self.frame = 0
        self.playing = False
        self.resume_intent = False
        self.status = "paused"
        self.reasons = []
        execution = self.runtime.get("execution", {})
        if execution.get("observation_mode") == "simulation" and not self.simulation:
            raise PerformanceBlocked("simulation-record-is-not-playback-evidence")
        self.windows = copy.deepcopy(execution.get("degradation_windows", []))
        self.transitions = copy.deepcopy(execution.get("transitions", []))
        self.controls = copy.deepcopy(execution.get("control_samples", []))
        self._control_frames = [sample["frame"] for sample in self.controls]
        self.resource_maxima = copy.deepcopy(execution.get("resource_maxima", {}))
        self._last_active = set()

    def _frame(self, value):
        _integer(value, "output frame")
        if value > self.duration:
            raise ValueError("Output frame exceeds the recorded duration")
        return value

    def _measurements(self, values):
        if not isinstance(values, Mapping) or any(name not in values for name in BYTE_RESOURCES):
            raise PerformanceBlocked("resource-measurement-unavailable")
        return {name: _integer(values[name], name) for name in BYTE_RESOURCES}

    def admit(self, measurements):
        if self.status in {"cancelled", "finished"}:
            raise ValueError("A terminal performance cannot acquire new playback admission")
        caps = self.profile["byte_caps"]
        if self.profile.get("admitted") is not True:
            raise PerformanceBlocked("performance-profile-not-admitted")
        if any(name not in caps or type(caps[name]) is not int or caps[name] <= 0 for name in BYTE_RESOURCES):
            raise PerformanceBlocked("playback-byte-caps-missing")
        values = self._measurements(measurements)
        self.admitted = True
        self.observe_resources(values)

    def _degrade(self, reason):
        if self.status in {"cancelled", "finished"}:
            return
        window = next((value for value in self.windows if value["start_frame"] <= self.frame and value["end_frame"] is None), None)
        if window is None:
            window = {"start_frame": self.frame, "end_frame": None, "reasons": []}
            self.windows.append(window)
        if reason not in window["reasons"]:
            window["reasons"].append(reason)
        self.reasons = self._reasons_at(self.frame)
        self.status = "degraded"

    def _reasons_at(self, frame):
        return sorted({reason for window in self.windows if window["start_frame"] <= frame
                       and (window["end_frame"] is None or frame < window["end_frame"])
                       for reason in window["reasons"]})

    def observe_resources(self, measurements):
        try:
            values = self._measurements(measurements)
        except (ValueError, PerformanceBlocked):
            self._degrade("resource-measurement-unavailable")
            return
        for name, value in values.items():
            self.resource_maxima[name] = max(value, self.resource_maxima.get(name, 0))
            cap = self.profile["byte_caps"].get(name)
            if cap is not None and value > cap:
                self._degrade(name)

    def recover(self, measurements):
        if self.status in {"cancelled", "finished"}:
            raise ValueError("A terminal performance cannot be recovered implicitly")
        values = self._measurements(measurements)
        caps = self.profile["byte_caps"]
        if not self.admitted or any(name not in caps or value > caps[name] for name, value in values.items()):
            raise PerformanceBlocked("resource-pressure-not-cleared")
        for window in self.windows:
            if window["start_frame"] <= self.frame and window["end_frame"] is None:
                window["end_frame"] = max(self.frame, window["start_frame"] + 1)
        self.reasons = self._reasons_at(self.frame)
        self.status = "degraded" if self.reasons else "playing" if self.playing else "paused"

    def observe_controls(self, frame, values):
        frame = self._frame(frame)
        if self.status in {"cancelled", "finished"} or frame != self.frame:
            raise ValueError("Control observation must bind the current live output frame")
        expected = {event["id"] for event in self.snapshot()["active"]}
        if not isinstance(values, Mapping) or set(values) != expected:
            raise ValueError("Control observation must cover every active resolved event")
        observed = {identifier: _number(value, "observed control", 0, 1) for identifier, value in values.items()}
        index = bisect_right(self._control_frames, frame)
        sample = {"frame": frame, "values": observed}
        if index and self._control_frames[index - 1] == frame:
            if self.controls[index - 1] != sample:
                raise ValueError("Recorded control observations cannot be rewritten")
            return
        if index != len(self.controls):
            raise ValueError("New observations cannot be inserted into saved future history")
        if observed:
            self.controls.append(sample)
            self._control_frames.append(frame)

    def resume(self):
        if self.status in {"cancelled", "finished"}:
            raise ValueError("Start or explicitly seek a performance before resuming")
        if not self.admitted:
            raise PerformanceBlocked("performance-playback-not-admitted")
        self.playing = True
        self.resume_intent = True
        self.status = "degraded" if self.reasons else "playing"
        return self.advance(self.frame)

    def pause(self):
        self.playing = False
        self.resume_intent = False
        if self.status not in {"cancelled", "finished"}:
            self.status = "degraded" if self.reasons else "paused"
        return self.snapshot()

    def cancel(self):
        self.playing = False
        self.resume_intent = False
        self.status = "cancelled"
        self._last_active = set()
        return self.snapshot()

    def seek(self, frame):
        if self.status == "cancelled":
            raise ValueError("A cancelled performance cannot be restarted")
        self.frame = self._frame(frame)
        self.reasons = self._reasons_at(frame)
        self._last_active = set()
        self.status = "finished" if frame == self.duration else "degraded" if self.reasons else "playing" if self.playing else "paused"
        if frame == self.duration:
            self.playing = self.resume_intent = False
        self.transitions.append({"kind": "seek", "frame": frame, "playing": self.playing})
        return self.advance(frame) if self.playing else self.snapshot()

    def _omitted(self, event):
        return any(self.frame >= window["start_frame"] and event["end_frame"] > window["start_frame"]
                   and event["start_frame"] < (window["end_frame"] if window["end_frame"] is not None else self.frame + 1)
                   for window in self.windows)

    def _positions(self, event):
        material = self.materials[event["material_id"]]
        source_fps = material.span.timebase.as_fraction()
        elapsed = Fraction(self.frame - event["start_frame"], 1) / self.record.timebase.as_fraction()
        result = copy.deepcopy(event)
        for name in ("picture_clock", "matte_clock"):
            clock = event[name]
            value = clock["start_frame"] + int(elapsed * source_fps * Fraction(clock["rate_num"], clock["rate_den"]))
            result[name + "_position"] = (material.span.start + (value - material.span.start) % material.span.duration_frames
                                                 if clock["mode"] == "loop" else min(value, material.span.end - 1))
        clock = event["audio_clock"]
        origin = material.metadata.get("audio_origin_sample", int(material.span.start / source_fps * clock["sample_rate"]))
        count = material.metadata.get("audio_sample_count", int(material.span.duration_frames / source_fps * clock["sample_rate"]))
        value = clock["start_sample"] + int(elapsed * clock["sample_rate"] * Fraction(clock["rate_num"], clock["rate_den"]))
        result["audio_clock_position"] = origin + (value - origin) % count if clock["mode"] == "loop" else min(value, origin + count - 1)
        observations = []
        modulation = 0
        for edge in event["couplings"]:
            index = bisect_right(self._control_frames, self.frame - edge["lag_frames"]) - 1
            sample = self.controls[index] if index >= 0 else None
            observed = sample["values"].get(edge["source_event_id"]) if sample else None
            observations.append({"source_event_id": edge["source_event_id"],
                                 "observation_frame": sample["frame"] if observed is not None else None,
                                 "value": observed, "state": "observed" if observed is not None else "initial"})
            if observed is not None:
                modulation += edge["amount"] * observed
        result["coupling_observations"] = observations
        result["effective_gain"] = min(1, max(0, event["gain"] * (1 + modulation)))
        result["effective_intensity"] = min(1, max(0, event["fx"]["intensity"] * (1 + modulation)))
        return result

    def snapshot(self):
        reference = copy.deepcopy(self.runtime["reference"])
        material = self.materials[reference["material_id"]]
        phase = int(Fraction(min(self.frame, self.duration - 1), 1) / self.record.timebase.as_fraction()
                    * material.span.timebase.as_fraction())
        reference["source_frame"] = (material.span.start + phase % material.span.duration_frames
                                     if reference["clock"]["mode"] == "loop" else min(material.span.start + phase, material.span.end - 1))
        terminal = self.status in {"cancelled", "finished"}
        active = [] if terminal or self.reasons else [self._positions(e) for e in self.events
                  if e["start_frame"] <= self.frame < e["end_frame"] and not self._omitted(e)]
        pending = [] if terminal or self.reasons else [copy.deepcopy(e) for e in self.events
                   if self.frame < e["start_frame"] <= min(self.duration, self.frame + self.profile["lookahead_frames"])]
        return {"frame": self.frame, "status": self.status, "playing": self.playing,
                "resume_intent": self.resume_intent, "mode": "simulation" if self.simulation else "playback",
                "reference": reference, "active": active, "pending": pending,
                "audio_voices": (1 if self.playing and self.reasons else sum(e["audio"] for e in active) if self.playing else 0),
                "visual_instances": sum(e["picture"] for e in active),
                "fallback_material_id": self.runtime.get("fallback_material_id") if self.reasons else None,
                "degradation_reasons": list(self.reasons), "resource_maxima": dict(self.resource_maxima)}

    def advance(self, frame):
        frame = self._frame(frame)
        if not self.playing or self.status in {"cancelled", "finished"}:
            return self.snapshot()
        if frame < self.frame:
            raise ValueError("Use an explicit seek for a backward clock change")
        previous = self.frame
        self.frame = frame
        self.reasons = self._reasons_at(frame)
        if frame == self.duration:
            self.playing = False
            self.resume_intent = False
            self.status = "finished"
        else:
            self.status = "degraded" if self.reasons else "playing"
        state = self.snapshot()
        for name, observed, cap in (("audio_voices", state["audio_voices"], self.profile["audio_voices"]),
                                    ("visual_instances", state["visual_instances"], self.profile["visual_instances"]),
                                    ("pending_events", len(state["pending"]), self.profile["pending_events"])):
            if observed > cap:
                self._degrade(name)
        state = self.snapshot()
        active = {event["id"] for event in state["active"]}
        if active != self._last_active or (frame > previous + 1 and not self.reasons):
            self.transitions.append({"kind": "tick", "frame": frame,
                                     "started": sorted(active - self._last_active),
                                     "ended": sorted(self._last_active - active),
                                     "unobserved_frames": max(0, frame - previous - 1)})
        self._last_active = active
        return state

    def checkpoint(self):
        record = self.record.to_dict()
        record["runtime"]["execution"] = {"degradation_windows": copy.deepcopy(self.windows),
                                          "observation_mode": "simulation" if self.simulation else "playback",
                                          "transitions": copy.deepcopy(self.transitions),
                                          "control_samples": copy.deepcopy(self.controls),
                                          "resource_maxima": dict(self.resource_maxima)}
        packet = {"schema": "amps.performance-checkpoint.v1", "record": record,
                  "observation_mode": "simulation" if self.simulation else "playback",
                  "identity": canonical_identity(record),
                  "state": {"frame": self.frame, "playing": self.playing, "resume_intent": self.resume_intent,
                            "status": self.status, "degradation_reasons": list(self.reasons)}}
        return {**packet, "sha256": _hash(packet)}

    @classmethod
    def restore(cls, checkpoint, *, simulation=False):
        packet = copy.deepcopy(checkpoint)
        expected = packet.pop("sha256", None)
        if packet.get("schema") != "amps.performance-checkpoint.v1" or expected != _hash(packet):
            raise ValueError("Checkpoint digest or schema mismatch")
        if packet.get("observation_mode") == "simulation" and not simulation:
            raise PerformanceBlocked("simulation-checkpoint-is-not-playback-evidence")
        restored = cls(packet["record"], simulation=simulation)
        if canonical_identity(restored.record) != packet.get("identity"):
            raise ValueError("Checkpoint composition identity mismatch")
        state = packet["state"]
        restored.frame = restored._frame(state["frame"])
        if type(state.get("playing")) is not bool or type(state.get("resume_intent")) is not bool:
            raise ValueError("Checkpoint play intent is invalid")
        restored.resume_intent = state["playing"] or state["resume_intent"]
        restored.playing = False
        restored.reasons = list(state.get("degradation_reasons", []))
        restored.status = state["status"] if state["status"] in {"cancelled", "finished", "degraded"} else "paused"
        return restored
