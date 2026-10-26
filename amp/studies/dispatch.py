"""Study execution dispatch framework (Issue #68, F05).

Implements STUDY_BINDING_FAMILY = "amps.study.v1" and run_study dispatch.
Enforces deterministic directory resolution and fail-closed validation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping, Optional, Tuple

from amp.composition.containers import (
    ALLOWED_OPERATORS,
    MaterialRef,
    SourceSpan,
    StudyBinding,
    StudyContext,
    StudyResult,
    Timebase,
)

STUDY_BINDING_FAMILY = "amps.study.v1"


def resolve_study_output_dir(context: StudyContext, workstream_id: str, case_id: str) -> Path:
    if not isinstance(workstream_id, str) or not workstream_id.strip():
        raise ValueError("workstream_id must be a non-empty string")
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("case_id must be a non-empty string")
    if not isinstance(context.study_id, str) or not context.study_id.strip():
        raise ValueError("study_id must be a non-empty string")

    for name, val in [("workstream_id", workstream_id), ("case_id", case_id), ("study_id", context.study_id)]:
        if ".." in val or "/" in val or "\\" in val:
            raise ValueError(f"Invalid path characters in {name}: {val!r}")

    base = Path(context.output_dir) if context.output_dir else Path("build")
    if base.name == "build":
        out_dir = base / "god-here" / "studies" / workstream_id / context.study_id / case_id
    elif "build" in base.parts:
        out_dir = base / "god-here" / "studies" / workstream_id / context.study_id / case_id
    else:
        out_dir = base / "build" / "god-here" / "studies" / workstream_id / context.study_id / case_id

    return out_dir


def validate_study_parameters(parameters: Mapping[str, any]) -> None:
    if not isinstance(parameters, Mapping):
        raise ValueError("parameters must be a mapping")


def run_study(binding: StudyBinding, context: StudyContext) -> StudyResult:
    """Execute verified artifacts through the same fixed dispatch as the CLI."""
    if not isinstance(binding,StudyBinding) or not isinstance(context,StudyContext):raise ValueError('StudyBinding and StudyContext required')
    from .clock_contracts import validate_context_contract
    validate_context_contract(binding,context)
    if isinstance(binding,StudyBinding) and binding.operator=='amp.review.v1':
        from .review import build_review
        return build_review(binding,context)
    from .execution_artifacts import build_executed_study
    return build_executed_study(binding,context)


def build_study_manifest(binding: StudyBinding, context: StudyContext) -> StudyResult:
    """Legacy planning metadata only; this does not execute a media operator."""
    if not isinstance(binding, StudyBinding):
        raise ValueError(f"Expected StudyBinding, got {type(binding).__name__}")
    if not isinstance(context, StudyContext):
        raise ValueError(f"Expected StudyContext, got {type(context).__name__}")

    # Validate workstream_id, case_id, study_id
    workstream_id = context.parameters.get("workstream_id") or binding.parameters.get("workstream_id")
    if not workstream_id or not isinstance(workstream_id, str) or not workstream_id.strip():
        raise ValueError("workstream_id must be provided in context.parameters or binding.parameters")

    case_id = binding.parameters.get("case_id") or context.parameters.get("case_id")
    if not case_id or not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("case_id must be provided in binding.parameters or context.parameters")

    if not context.study_id or not isinstance(context.study_id, str) or not context.study_id.strip():
        raise ValueError("study_id must be a non-empty string")

    # Timebase compatibility
    if binding.timebase is not None:
        if binding.timebase.num != context.timebase.num or binding.timebase.den != context.timebase.den:
            raise ValueError(
                f"Incompatible Timebase: binding ({binding.timebase.num}/{binding.timebase.den}) "
                f"differs from context ({context.timebase.num}/{context.timebase.den})"
            )

    # Validate binding.inputs
    if not binding.inputs:
        raise ValueError("StudyBinding requires at least one input MaterialRef")

    for inp in binding.inputs:
        if not isinstance(inp, MaterialRef):
            raise ValueError(f"Expected MaterialRef input, got {type(inp).__name__}")

    # Validate parameters
    validate_study_parameters(binding.parameters)
    validate_study_parameters(context.parameters)
    # Resolve output directory
    output_dir = resolve_study_output_dir(context, workstream_id, case_id)
    output_dir.mkdir(parents=True, exist_ok=False)

    # Determine span
    span = binding.span or context.span or SourceSpan(0, 3360, context.timebase)

    # Deterministic execution artifact
    manifest_data = {
        "schema_version": "amps.study-result.v1",
        "family": STUDY_BINDING_FAMILY,
        "workstream_id": workstream_id,
        "study_id": context.study_id,
        "case_id": case_id,
        "composition_id": context.composition_id,
        "operator": binding.operator,
        "status": "planned",
        "execution_performed": False,
        "span": span.to_dict(),
        "timebase": context.timebase.to_dict(),
        "inputs": [inp.to_dict() for inp in binding.inputs],
        "parameters": dict(binding.parameters),
    }

    manifest_bytes = json.dumps(manifest_data, indent=2, sort_keys=True).encode("utf-8")
    manifest_path = output_dir / "study-manifest.json"
    with manifest_path.open('xb') as stream:stream.write(manifest_bytes)

    manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
    product_ref = MaterialRef(
        id=f"prod-{manifest_sha[:12]}",
        sha256=manifest_sha,
        kind="metadata",
        bytes=len(manifest_bytes),
        path=str(manifest_path),
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
            "output_dir": str(output_dir),
            "manifest_sha256": manifest_sha,
            "status": "planned",
            "execution_performed": False,
        },
    )
