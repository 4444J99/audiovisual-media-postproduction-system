"""Typed M0 containers and contracts for composition studies.

Provides immutable data structures with strict domain validation:
- integer half-open [start, end) frame/sample domains
- rational timebase (num > 0, den > 0)
- fixed operator allowlists (rejecting arbitrary command or remote-URL execution)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple


ALLOWED_OPERATORS = frozenset({
    "amp.roomstretch.v1",
    "amp.roomrefine.v1",
    "amp.roomtone.v1",
    "amp.foley.v1",
    "amp.render.v1",
    "amp.direction.v1",
    "amp.segmentation.v1",
    "amp.revision.v1",
    "fx.rack.v1",
    "touchdesigner.material_workspace.v1",
    "pressure",
    "lag",
    "refraction",
    "residue",
    "erosion",
    "cutout",
    "passthrough",
    "neutral_playback",
})

ALLOWED_MATERIAL_KINDS = frozenset({
    "audio",
    "video",
    "image",
    "sequence",
    "material",
    "font",
    "dat",
    "metadata",
})

FORBIDDEN_COMMAND_PATTERNS = [
    re.compile(r"^\s*(sh|bash|zsh|python[0-9.]*|perl|ruby|php|node|curl|wget|nc|netcat|rm|cat|kill)\b", re.IGNORECASE),
    re.compile(r"[;|`&$><]"),
]


def _reject_command_or_url(val: Any, role: str = "parameter") -> None:
    if isinstance(val, str):
        low = val.lower().strip()
        for proto in ("http://", "https://", "ftp://", "file://", "javascript:", "data:"):
            if low.startswith(proto):
                raise ValueError(f"Remote URLs are forbidden in {role}: {val}")
        for pat in FORBIDDEN_COMMAND_PATTERNS:
            if pat.search(val):
                raise ValueError(f"Arbitrary command execution is forbidden in {role}: {val}")
    elif isinstance(val, Mapping):
        for k, v in val.items():
            _reject_command_or_url(k, f"{role} key")
            _reject_command_or_url(v, f"{role} value")
    elif isinstance(val, (list, tuple, set, frozenset)):
        for item in val:
            _reject_command_or_url(item, f"{role} item")


def _validate_operator(operator: str) -> str:
    if not isinstance(operator, str) or not operator.strip():
        raise ValueError("Operator must be a non-empty string")
    _reject_command_or_url(operator, "operator")
    if operator not in ALLOWED_OPERATORS:
        raise ValueError(f"Operator {operator!r} not in fixed operator allowlist")
    return operator


@dataclass(frozen=True)
class Timebase:
    num: int
    den: int = 1

    def __post_init__(self):
        if isinstance(self.num, bool) or not isinstance(self.num, int) or self.num <= 0:
            raise ValueError(f"Timebase numerator must be a positive integer, got {self.num!r}")
        if isinstance(self.den, bool) or not isinstance(self.den, int) or self.den <= 0:
            raise ValueError(f"Timebase denominator must be a positive integer, got {self.den!r}")

    @property
    def fps(self) -> float:
        return self.num / self.den

    def as_fraction(self) -> Fraction:
        return Fraction(self.num, self.den)

    def to_dict(self) -> dict[str, int]:
        return {"num": self.num, "den": self.den}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Timebase:
        if isinstance(data, Timebase):
            return data
        return cls(num=data["num"], den=data.get("den", 1))


@dataclass(frozen=True)
class SourceSpan:
    start: int
    end: int
    timebase: Optional[Timebase] = None

    def __post_init__(self):
        if isinstance(self.start, bool) or not isinstance(self.start, int) or self.start < 0:
            raise ValueError(f"Span start must be a non-negative integer, got {self.start!r}")
        if isinstance(self.end, bool) or not isinstance(self.end, int) or self.end <= self.start:
            raise ValueError(f"Span end must be an integer strictly greater than start ({self.start}), got {self.end!r}")
        if self.timebase is not None and not isinstance(self.timebase, Timebase):
            object.__setattr__(self, "timebase", Timebase.from_dict(self.timebase))

    @property
    def duration_frames(self) -> int:
        return self.end - self.start

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.timebase is None:
            return None
        return (self.end - self.start) * self.timebase.den / self.timebase.num

    def contains(self, index: int) -> bool:
        if isinstance(index, bool) or not isinstance(index, int):
            return False
        return self.start <= index < self.end

    def overlaps(self, other: SourceSpan) -> bool:
        return max(self.start, other.start) < min(self.end, other.end)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"start": self.start, "end": self.end}
        if self.timebase is not None:
            result["timebase"] = self.timebase.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SourceSpan:
        if isinstance(data, SourceSpan):
            return data
        tb = Timebase.from_dict(data["timebase"]) if "timebase" in data and data["timebase"] is not None else None
        return cls(start=data["start"], end=data["end"], timebase=tb)


@dataclass(frozen=True)
class MaterialRef:
    id: str
    sha256: str
    kind: str
    bytes: Optional[int] = None
    path: Optional[str] = None
    origin: Optional[str] = None
    span: Optional[SourceSpan] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("MaterialRef id must be a non-empty string")
        _reject_command_or_url(self.id, "material id")

        if not isinstance(self.sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError(f"MaterialRef sha256 must be 64 hex characters, got {self.sha256!r}")

        if not isinstance(self.kind, str) or self.kind not in ALLOWED_MATERIAL_KINDS:
            raise ValueError(f"MaterialRef kind must be one of {sorted(ALLOWED_MATERIAL_KINDS)}, got {self.kind!r}")

        if self.bytes is not None:
            if isinstance(self.bytes, bool) or not isinstance(self.bytes, int) or self.bytes < 0:
                raise ValueError(f"MaterialRef bytes must be a non-negative integer, got {self.bytes!r}")

        if self.path is not None:
            if not isinstance(self.path, str) or not self.path.strip():
                raise ValueError("MaterialRef path must be a non-empty string when provided")
            _reject_command_or_url(self.path, "material path")

        if self.origin is not None:
            _reject_command_or_url(self.origin, "material origin")

        if self.span is not None and not isinstance(self.span, SourceSpan):
            object.__setattr__(self, "span", SourceSpan.from_dict(self.span))

        _reject_command_or_url(self.metadata, "material metadata")

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "sha256": self.sha256,
            "kind": self.kind,
        }
        if self.bytes is not None:
            data["bytes"] = self.bytes
        if self.path is not None:
            data["path"] = self.path
        if self.origin is not None:
            data["origin"] = self.origin
        if self.span is not None:
            data["span"] = self.span.to_dict()
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MaterialRef:
        if isinstance(data, MaterialRef):
            return data
        span = SourceSpan.from_dict(data["span"]) if data.get("span") is not None else None
        return cls(
            id=data["id"],
            sha256=data["sha256"],
            kind=data["kind"],
            bytes=data.get("bytes"),
            path=data.get("path"),
            origin=data.get("origin"),
            span=span,
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True)
class StudyBinding:
    operator: str
    materials: Tuple[MaterialRef, ...] = ()
    parameters: Mapping[str, Any] = field(default_factory=dict)
    span: Optional[SourceSpan] = None
    timebase: Optional[Timebase] = None

    def __post_init__(self):
        object.__setattr__(self, "operator", _validate_operator(self.operator))

        # Validate materials
        valid_mats = []
        for m in self.materials:
            if isinstance(m, MaterialRef):
                valid_mats.append(m)
            elif isinstance(m, Mapping):
                valid_mats.append(MaterialRef.from_dict(m))
            else:
                raise ValueError(f"Expected MaterialRef, got {type(m).__name__}")
        object.__setattr__(self, "materials", tuple(valid_mats))

        _reject_command_or_url(self.parameters, "study parameters")

        if self.span is not None and not isinstance(self.span, SourceSpan):
            object.__setattr__(self, "span", SourceSpan.from_dict(self.span))

        if self.timebase is not None and not isinstance(self.timebase, Timebase):
            object.__setattr__(self, "timebase", Timebase.from_dict(self.timebase))

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "operator": self.operator,
            "materials": [m.to_dict() for m in self.materials],
            "parameters": dict(self.parameters),
        }
        if self.span is not None:
            data["span"] = self.span.to_dict()
        if self.timebase is not None:
            data["timebase"] = self.timebase.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StudyBinding:
        if isinstance(data, StudyBinding):
            return data
        mats = [MaterialRef.from_dict(m) for m in data.get("materials", ())]
        span = SourceSpan.from_dict(data["span"]) if data.get("span") is not None else None
        tb = Timebase.from_dict(data["timebase"]) if data.get("timebase") is not None else None
        return cls(
            operator=data["operator"],
            materials=tuple(mats),
            parameters=data.get("parameters", {}),
            span=span,
            timebase=tb,
        )


@dataclass(frozen=True)
class StudyContext:
    study_id: str
    composition_id: str
    bindings: Tuple[StudyBinding, ...] = ()
    timebase: Timebase = field(default_factory=lambda: Timebase(30, 1))
    span: Optional[SourceSpan] = None
    media_root: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.study_id, str) or not self.study_id.strip():
            raise ValueError("StudyContext study_id must be a non-empty string")
        _reject_command_or_url(self.study_id, "study_id")

        if not isinstance(self.composition_id, str) or not self.composition_id.strip():
            raise ValueError("StudyContext composition_id must be a non-empty string")
        _reject_command_or_url(self.composition_id, "composition_id")

        valid_bindings = []
        for b in self.bindings:
            if isinstance(b, StudyBinding):
                valid_bindings.append(b)
            elif isinstance(b, Mapping):
                valid_bindings.append(StudyBinding.from_dict(b))
            else:
                raise ValueError(f"Expected StudyBinding, got {type(b).__name__}")
        object.__setattr__(self, "bindings", tuple(valid_bindings))

        if not isinstance(self.timebase, Timebase):
            object.__setattr__(self, "timebase", Timebase.from_dict(self.timebase))

        if self.span is not None and not isinstance(self.span, SourceSpan):
            object.__setattr__(self, "span", SourceSpan.from_dict(self.span))

        if self.media_root is not None:
            _reject_command_or_url(self.media_root, "media_root")

        _reject_command_or_url(self.metadata, "context metadata")

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "study_id": self.study_id,
            "composition_id": self.composition_id,
            "bindings": [b.to_dict() for b in self.bindings],
            "timebase": self.timebase.to_dict(),
        }
        if self.span is not None:
            data["span"] = self.span.to_dict()
        if self.media_root is not None:
            data["media_root"] = self.media_root
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StudyContext:
        if isinstance(data, StudyContext):
            return data
        bindings = [StudyBinding.from_dict(b) for b in data.get("bindings", ())]
        tb = Timebase.from_dict(data["timebase"]) if "timebase" in data else Timebase(30, 1)
        span = SourceSpan.from_dict(data["span"]) if data.get("span") is not None else None
        return cls(
            study_id=data["study_id"],
            composition_id=data["composition_id"],
            bindings=tuple(bindings),
            timebase=tb,
            span=span,
            media_root=data.get("media_root"),
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True)
class StudyResult:
    study_id: str
    operator: str
    span: SourceSpan
    products: Tuple[MaterialRef, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not isinstance(self.study_id, str) or not self.study_id.strip():
            raise ValueError("StudyResult study_id must be a non-empty string")
        _reject_command_or_url(self.study_id, "study_id")

        object.__setattr__(self, "operator", _validate_operator(self.operator))

        if not isinstance(self.span, SourceSpan):
            object.__setattr__(self, "span", SourceSpan.from_dict(self.span))

        valid_products = []
        for p in self.products:
            if isinstance(p, MaterialRef):
                valid_products.append(p)
            elif isinstance(p, Mapping):
                valid_products.append(MaterialRef.from_dict(p))
            else:
                raise ValueError(f"Expected MaterialRef product, got {type(p).__name__}")
        object.__setattr__(self, "products", tuple(valid_products))

        _reject_command_or_url(self.metadata, "result metadata")

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "study_id": self.study_id,
            "operator": self.operator,
            "span": self.span.to_dict(),
            "products": [p.to_dict() for p in self.products],
        }
        if self.metadata:
            data["metadata"] = dict(self.metadata)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StudyResult:
        if isinstance(data, StudyResult):
            return data
        span = SourceSpan.from_dict(data["span"])
        products = [MaterialRef.from_dict(p) for p in data.get("products", ())]
        return cls(
            study_id=data["study_id"],
            operator=data["operator"],
            span=span,
            products=tuple(products),
            metadata=data.get("metadata", {}),
        )
