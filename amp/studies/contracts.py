"""Study contract and schema validation pack (Issue #66, F03).

Enforces:
- Integer half-open frame intervals [start, end) (start >= 0, end > start, int not bool)
- Acyclic static dependency graph check across study bindings
- Explicit provenance (source_id, unit_id, model_id, seed)
- Status axis (not_tested, named_block, admitted, executed, accepted, rejected)
- Mask-to-body span coupling (within body bounds, valid on-screen target)
"""
from __future__ import annotations

import math
import re
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

from amp.composition.containers import (
    ALLOWED_MATERIAL_KINDS,
    ALLOWED_OPERATORS,
    MaterialRef,
    SourceSpan,
    StudyBinding,
    Timebase,
)
from amp.composition.record import PerformanceRecord

STATUS_AXIS: Tuple[str, ...] = (
    "not_tested",
    "named_block",
    "admitted",
    "executed",
    "accepted",
    "rejected",
)

REQUIRED_PROVENANCE_FIELDS: Tuple[str, ...] = (
    "source_id",
    "unit_id",
    "model_id",
    "seed",
)

FORBIDDEN_COMMAND_PATTERNS = [
    re.compile(r"^\s*(sh|bash|zsh|python[0-9.]*|perl|ruby|php|node|curl|wget|nc|netcat|rm|cat|kill)\b", re.IGNORECASE),
    re.compile(r"[;|`&$><]"),
]


def _check_command_or_url(val: Any, role: str = "field") -> Optional[str]:
    if isinstance(val, str):
        low = val.lower().strip()
        for proto in ("http://", "https://", "ftp://", "file://", "javascript:", "data:"):
            if low.startswith(proto):
                return f"Remote URLs are forbidden in {role}: {val}"
        for pat in FORBIDDEN_COMMAND_PATTERNS:
            if pat.search(val):
                return f"Arbitrary command execution is forbidden in {role}: {val}"
    elif isinstance(val, Mapping):
        for k, v in val.items():
            err = _check_command_or_url(k, f"{role} key")
            if err:
                return err
            err = _check_command_or_url(v, f"{role} value")
            if err:
                return err
    elif isinstance(val, (list, tuple, set, frozenset)):
        for item in val:
            err = _check_command_or_url(item, f"{role} item")
            if err:
                return err
    return None


def _validate_interval(
    start: Any,
    end: Any,
    role: str = "Span",
) -> list[str]:
    errors = []
    if isinstance(start, bool) or not isinstance(start, int):
        errors.append(f"{role} start must be an integer (not bool), got {start!r}")
    elif start < 0:
        errors.append(f"{role} start must be non-negative, got {start}")

    if isinstance(end, bool) or not isinstance(end, int):
        errors.append(f"{role} end must be an integer (not bool), got {end!r}")
    elif not isinstance(start, bool) and isinstance(start, int) and end <= start:
        errors.append(f"{role} end ({end}) must be strictly greater than start ({start})")

    return errors


def validate_mask_to_body_span(
    mask_span: Any,
    body_span: Any,
    target_body: Any,
    on_screen: bool = True,
) -> tuple[str, ...]:
    errors: list[str] = []

    # Check target body
    if not isinstance(target_body, str) or not target_body.strip():
        errors.append("Target body must be a non-empty string identifier")

    # Check on_screen requirement
    if not on_screen or on_screen is not True:
        errors.append(f"Mask targets an off-screen body or off-screen flag is True: {target_body!r}")

    # Unpack mask span
    m_start: Any = None
    m_end: Any = None
    if isinstance(mask_span, SourceSpan):
        m_start, m_end = mask_span.start, mask_span.end
    elif isinstance(mask_span, (tuple, list)) and len(mask_span) == 2:
        m_start, m_end = mask_span[0], mask_span[1]
    elif isinstance(mask_span, Mapping) and "start" in mask_span and "end" in mask_span:
        m_start, m_end = mask_span["start"], mask_span["end"]
    else:
        errors.append(f"Invalid mask span format: {mask_span!r}")

    if m_start is not None and m_end is not None:
        errors.extend(_validate_interval(m_start, m_end, role="Mask span"))

    # Unpack body span
    b_start: Any = None
    b_end: Any = None
    if isinstance(body_span, SourceSpan):
        b_start, b_end = body_span.start, body_span.end
    elif isinstance(body_span, (tuple, list)) and len(body_span) == 2:
        b_start, b_end = body_span[0], body_span[1]
    elif isinstance(body_span, Mapping) and "start" in body_span and "end" in body_span:
        b_start, b_end = body_span["start"], body_span["end"]
    elif body_span is not None:
        errors.append(f"Invalid body span format: {body_span!r}")

    if b_start is not None and b_end is not None:
        errors.extend(_validate_interval(b_start, b_end, role="Body span"))

    # Coupling: mask span must lie strictly within body span [b_start, b_end)
    if (
        m_start is not None
        and m_end is not None
        and b_start is not None
        and b_end is not None
        and not isinstance(m_start, bool)
        and isinstance(m_start, int)
        and not isinstance(m_end, bool)
        and isinstance(m_end, int)
        and not isinstance(b_start, bool)
        and isinstance(b_start, int)
        and not isinstance(b_end, bool)
        and isinstance(b_end, int)
    ):
        if m_start < b_start:
            errors.append(
                f"Mask span start ({m_start}) is earlier than body interval start ({b_start})"
            )
        if m_end > b_end:
            errors.append(
                f"Mask span end ({m_end}) exceeds body interval end ({b_end})"
            )

    return tuple(errors)


def validate_binding(binding: Union[StudyBinding, Mapping[str, Any]]) -> tuple[str, ...]:
    errors: list[str] = []

    # Normalize access whether StudyBinding or dict
    if isinstance(binding, StudyBinding):
        operator = binding.operator
        parameters = binding.parameters
        span = binding.span
        status = getattr(binding, "status", "not_tested")
        provenance = getattr(binding, "provenance", {})
        dependencies = getattr(binding, "dependencies", ())
        mask_coupling = parameters.get("mask_coupling")
    elif isinstance(binding, Mapping):
        operator = binding.get("operator")
        parameters = binding.get("parameters", {})
        span = binding.get("span")
        status = binding.get("status", parameters.get("status", "not_tested"))
        provenance = binding.get("provenance", parameters.get("provenance", {}))
        dependencies = binding.get("dependencies", parameters.get("dependencies", ()))
        mask_coupling = binding.get("mask_coupling", parameters.get("mask_coupling"))
    else:
        return (f"Expected StudyBinding or Mapping, got {type(binding).__name__}",)

    # 1. Operator validation
    if not isinstance(operator, str) or not operator.strip():
        errors.append("Operator must be a non-empty string")
    else:
        err = _check_command_or_url(operator, "operator")
        if err:
            errors.append(err)
        elif operator not in ALLOWED_OPERATORS:
            errors.append(f"Operator {operator!r} not in fixed operator allowlist")

    # 2. Parameters validation
    if not isinstance(parameters, Mapping):
        errors.append(f"Parameters must be a mapping, got {type(parameters).__name__}")
    else:
        err = _check_command_or_url(parameters, "parameters")
        if err:
            errors.append(err)

    # 3. Span validation: integer half-open [start, end)
    b_span_tuple: Optional[tuple[int, int]] = None
    if span is not None:
        if isinstance(span, SourceSpan):
            errors.extend(_validate_interval(span.start, span.end, role="Binding span"))
            b_span_tuple = (span.start, span.end)
        elif isinstance(span, Mapping):
            start = span.get("start")
            end = span.get("end")
            errors.extend(_validate_interval(start, end, role="Binding span"))
            if (
                isinstance(start, int)
                and not isinstance(start, bool)
                and isinstance(end, int)
                and not isinstance(end, bool)
            ):
                b_span_tuple = (start, end)
        else:
            errors.append(f"Invalid span type: {type(span).__name__}")

    # 4. Provenance validation: explicit (source_id, unit_id, model_id, seed)
    if not isinstance(provenance, Mapping):
        errors.append(f"Provenance must be a mapping, got {type(provenance).__name__}")
    else:
        err = _check_command_or_url(provenance, "provenance")
        if err:
            errors.append(err)
        for req_field in REQUIRED_PROVENANCE_FIELDS:
            if req_field not in provenance:
                errors.append(f"Provenance missing required field: {req_field!r}")
            else:
                val = provenance[req_field]
                if req_field == "seed":
                    if isinstance(val, bool) or not isinstance(val, int):
                        errors.append(f"Provenance seed must be an integer, got {val!r}")
                else:
                    if not isinstance(val, str) or not val.strip():
                        errors.append(f"Provenance {req_field} must be a non-empty string, got {val!r}")

    # 5. Status axis validation
    if not isinstance(status, str) or status not in STATUS_AXIS:
        errors.append(f"Status {status!r} not in valid status axis: {STATUS_AXIS}")

    # 6. Mask-to-body span coupling validation
    if mask_coupling is not None:
        if not isinstance(mask_coupling, Mapping):
            errors.append(f"mask_coupling must be a mapping, got {type(mask_coupling).__name__}")
        else:
            m_target = mask_coupling.get("target_body")
            m_on_screen = mask_coupling.get("on_screen", True)
            m_span = mask_coupling.get("mask_span")
            b_span = mask_coupling.get("body_span") or b_span_tuple
            coupling_errors = validate_mask_to_body_span(
                mask_span=m_span,
                body_span=b_span,
                target_body=m_target,
                on_screen=m_on_screen,
            )
            errors.extend(coupling_errors)

    # Also check if mask_span or target_body specified directly in parameters
    elif "mask_span" in parameters or "target_body" in parameters:
        m_target = parameters.get("target_body")
        m_on_screen = parameters.get("on_screen", True)
        m_span = parameters.get("mask_span")
        b_span = parameters.get("body_span") or b_span_tuple
        coupling_errors = validate_mask_to_body_span(
            mask_span=m_span,
            body_span=b_span,
            target_body=m_target,
            on_screen=m_on_screen,
        )
        errors.extend(coupling_errors)

    return tuple(errors)


def validate_material(material: Union[MaterialRef, Mapping[str, Any]]) -> tuple[str, ...]:
    errors: list[str] = []

    if isinstance(material, MaterialRef):
        m_id = material.id
        m_sha = material.sha256
        m_kind = material.kind
        m_bytes = material.bytes
        m_path = material.path
        m_span = material.span
    elif isinstance(material, Mapping):
        m_id = material.get("id")
        m_sha = material.get("sha256")
        m_kind = material.get("kind")
        m_bytes = material.get("bytes")
        m_path = material.get("path")
        m_span = material.get("span")
    else:
        return (f"Expected MaterialRef or Mapping, got {type(material).__name__}",)

    if not isinstance(m_id, str) or not m_id.strip():
        errors.append("MaterialRef id must be a non-empty string")
    else:
        err = _check_command_or_url(m_id, "material id")
        if err:
            errors.append(err)

    if not isinstance(m_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", m_sha):
        errors.append(f"MaterialRef sha256 must be 64 hex characters, got {m_sha!r}")

    if not isinstance(m_kind, str) or m_kind not in ALLOWED_MATERIAL_KINDS:
        errors.append(f"MaterialRef kind must be one of {sorted(ALLOWED_MATERIAL_KINDS)}, got {m_kind!r}")

    if m_bytes is not None:
        if isinstance(m_bytes, bool) or not isinstance(m_bytes, int) or m_bytes < 0:
            errors.append(f"MaterialRef bytes must be a non-negative integer, got {m_bytes!r}")

    if m_path is not None:
        if not isinstance(m_path, str) or not m_path.strip():
            errors.append("MaterialRef path must be a non-empty string when provided")
        else:
            err = _check_command_or_url(m_path, "material path")
            if err:
                errors.append(err)

    if m_span is not None:
        if isinstance(m_span, SourceSpan):
            errors.extend(_validate_interval(m_span.start, m_span.end, role="Material span"))
        elif isinstance(m_span, Mapping):
            errors.extend(_validate_interval(m_span.get("start"), m_span.get("end"), role="Material span"))

    return tuple(errors)


def validate_performance(performance: Union[PerformanceRecord, Mapping[str, Any]]) -> tuple[str, ...]:
    errors: list[str] = []

    if isinstance(performance, PerformanceRecord):
        p_id = performance.record_id
        c_id = performance.composition_id
        p_states = performance.performer_states
        span = performance.span
        provenance = performance.provenance
    elif isinstance(performance, Mapping):
        p_id = performance.get("record_id")
        c_id = performance.get("composition_id")
        p_states = performance.get("performer_states", {})
        span = performance.get("span")
        provenance = performance.get("provenance", {})
    else:
        return (f"Expected PerformanceRecord or Mapping, got {type(performance).__name__}",)

    if not isinstance(p_id, str) or not p_id.strip():
        errors.append("Performance record_id must be a non-empty string")
    else:
        err = _check_command_or_url(p_id, "record_id")
        if err:
            errors.append(err)

    if not isinstance(c_id, str) or not c_id.strip():
        errors.append("Performance composition_id must be a non-empty string")
    else:
        err = _check_command_or_url(c_id, "composition_id")
        if err:
            errors.append(err)

    if span is not None:
        if isinstance(span, SourceSpan):
            errors.extend(_validate_interval(span.start, span.end, role="Performance span"))
        elif isinstance(span, Mapping):
            errors.extend(_validate_interval(span.get("start"), span.get("end"), role="Performance span"))
    else:
        errors.append("Performance span is required")

    if not isinstance(p_states, Mapping):
        errors.append("performer_states must be a mapping")
    else:
        for p, val in p_states.items():
            if not isinstance(p, str) or not p.strip():
                errors.append(f"Performer identity must be non-empty string, got {p!r}")
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val) or not 0 <= val <= 1:
                errors.append(f"Performer {p!r} intensity must be a finite float in [0, 1], got {val!r}")

    if provenance:
        err = _check_command_or_url(provenance, "performance provenance")
        if err:
            errors.append(err)

    return tuple(errors)


def validate_dependency_dag(
    bindings: Sequence[Union[StudyBinding, Mapping[str, Any]]],
    raise_on_cycle: bool = False,
) -> tuple[str, ...]:
    errors: list[str] = []

    # Map binding identities to their declared dependency identities
    adj: dict[str, list[str]] = {}
    node_names: set[str] = set()

    for idx, b in enumerate(bindings):
        b_id: Optional[str] = None
        deps: list[str] = []

        if isinstance(b, StudyBinding):
            b_id = getattr(b, "id", None) or b.parameters.get("id") or b.parameters.get("binding_id") or f"binding_{idx}"
            declared_deps = getattr(b, "dependencies", ()) or b.parameters.get("dependencies", ()) or b.parameters.get("depends_on", ())
            if isinstance(declared_deps, (list, tuple)):
                deps.extend(str(d) for d in declared_deps)
            elif isinstance(declared_deps, str):
                deps.append(declared_deps)
        elif isinstance(b, Mapping):
            b_id = b.get("id") or b.get("binding_id") or b.get("parameters", {}).get("id") or f"binding_{idx}"
            declared_deps = b.get("dependencies") or b.get("depends_on") or b.get("parameters", {}).get("dependencies", ())
            if isinstance(declared_deps, (list, tuple)):
                deps.extend(str(d) for d in declared_deps)
            elif isinstance(declared_deps, str):
                deps.append(declared_deps)

        b_id = str(b_id)
        node_names.add(b_id)
        if b_id not in adj:
            adj[b_id] = []
        adj[b_id].extend(deps)

    # Cycle detection via 3-color DFS
    # 0 = unvisited, 1 = visiting, 2 = visited
    state: dict[str, int] = {node: 0 for node in node_names}
    path: list[str] = []

    def dfs(u: str) -> bool:
        state[u] = 1
        path.append(u)
        for v in adj.get(u, []):
            if v not in state:
                # Dependency node might not be in the list, skip or treat as external
                continue
            if state[v] == 1:
                # Cycle found!
                cycle_slice = path[path.index(v):] + [v]
                cycle_str = " -> ".join(cycle_slice)
                errors.append(f"Dependency cycle detected: {cycle_str}")
                return True
            if state[v] == 0:
                if dfs(v):
                    return True
        path.pop()
        state[u] = 2
        return False

    for node in node_names:
        if state[node] == 0:
            if dfs(node):
                break

    if errors and raise_on_cycle:
        raise ValueError("; ".join(errors))

    return tuple(errors)
