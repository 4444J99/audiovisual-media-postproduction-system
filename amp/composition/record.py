"""Durable performance record contract (T11 M0).

Encapsulates frozen performance state, performer cues, and study execution results.
"""
from __future__ import annotations

import math
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple

from .containers import (
    SourceSpan,
    StudyResult,
    Timebase,
    _reject_command_or_url,
)


def _is_finite_real(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


@dataclass(frozen=True)
class PerformanceRecord:
    record_id: str
    composition_id: str
    span: SourceSpan
    timebase: Timebase
    performer_states: Mapping[str, float] = field(default_factory=dict)
    results: Tuple[StudyResult, ...] = ()
    timestamp: Optional[str] = None
    provenance: Mapping[str, Any] = field(default_factory=dict)
    runtime: Optional[Mapping[str, Any]] = None

    def __post_init__(self):
        if not isinstance(self.record_id, str) or not self.record_id.strip():
            raise ValueError("PerformanceRecord record_id must be a non-empty string")
        _reject_command_or_url(self.record_id, "record_id")

        if not isinstance(self.composition_id, str) or not self.composition_id.strip():
            raise ValueError("PerformanceRecord composition_id must be a non-empty string")
        _reject_command_or_url(self.composition_id, "composition_id")

        if not isinstance(self.span, SourceSpan):
            object.__setattr__(self, "span", SourceSpan.from_dict(self.span))

        if not isinstance(self.timebase, Timebase):
            object.__setattr__(self, "timebase", Timebase.from_dict(self.timebase))

        # Validate performer states: performer -> intensity in [0, 1]
        for p, intensity in self.performer_states.items():
            if not isinstance(p, str) or not p.strip():
                raise ValueError("Performer identity must be a non-empty string")
            _reject_command_or_url(p, "performer identity")
            if not _is_finite_real(intensity) or not 0 <= intensity <= 1:
                raise ValueError(f"Performer {p!r} intensity must be a finite float in [0, 1], got {intensity!r}")

        valid_results = []
        for r in self.results:
            if isinstance(r, StudyResult):
                valid_results.append(r)
            elif isinstance(r, Mapping):
                valid_results.append(StudyResult.from_dict(r))
            else:
                raise ValueError(f"Expected StudyResult, got {type(r).__name__}")
        object.__setattr__(self, "results", tuple(valid_results))

        if self.timestamp is not None:
            _reject_command_or_url(self.timestamp, "timestamp")

        _reject_command_or_url(self.provenance, "provenance")
        if self.runtime is not None:
            from .novelty import validate_runtime
            snapshot = json.loads(json.dumps(self.runtime, allow_nan=False))
            validate_runtime(snapshot, duration_frames=self.span.duration_frames)
            object.__setattr__(self, "runtime", snapshot)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "record_id": self.record_id,
            "composition_id": self.composition_id,
            "span": self.span.to_dict(),
            "timebase": self.timebase.to_dict(),
            "performer_states": dict(self.performer_states),
            "results": [r.to_dict() for r in self.results],
        }
        if self.timestamp is not None:
            data["timestamp"] = self.timestamp
        if self.provenance:
            data["provenance"] = dict(self.provenance)
        if self.runtime is not None:
            data["runtime"] = json.loads(json.dumps(self.runtime, allow_nan=False))
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PerformanceRecord:
        if isinstance(data, PerformanceRecord):
            return data
        span = SourceSpan.from_dict(data["span"])
        tb = Timebase.from_dict(data["timebase"])
        results = [StudyResult.from_dict(r) for r in data.get("results", ())]
        return cls(
            record_id=data["record_id"],
            composition_id=data["composition_id"],
            span=span,
            timebase=tb,
            performer_states=data.get("performer_states", {}),
            results=tuple(results),
            timestamp=data.get("timestamp"),
            provenance=data.get("provenance", {}),
            runtime=data.get("runtime"),
        )
