"""Local model candidate admission and resource capping framework (Issue #67, F04).

Enforces:
- Verification of candidate_id against models.lock.json (R01-R12)
- Zero cloud spend (cloud_spend_usd == 0.0) and auto_download is False
- Host RAM / VRAM / disk capping against context budget
- Explicit not_tested / named_block / admitted status reporting
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any, Mapping, Optional

from amp.composition.containers import (
    MaterialRef,
    SourceSpan,
    StudyBinding,
    StudyContext,
    StudyResult,
)

DEFAULT_LOCK_PATH = Path("compositions/comp-001/studies/models.lock.json")


def load_models_lock(lock_path: Optional[Path] = None) -> dict[str, Any]:
    if lock_path is None:
        lock_path = DEFAULT_LOCK_PATH

    path = Path(lock_path)
    if not path.is_absolute() and not path.exists():
        candidates = [Path(__file__).resolve().parents[2] / path]
        for c in candidates:
            if c.exists():
                path = c
                break

    if not path.exists():
        raise FileNotFoundError(f"models.lock.json not found at {path}")

    return json.loads(path.read_text())


def admit_model(
    binding: StudyBinding,
    context: StudyContext,
    lock_path: Optional[Path] = None,
) -> StudyResult:
    if not isinstance(binding, StudyBinding):
        raise ValueError(f"Expected StudyBinding, got {type(binding).__name__}")
    if not isinstance(context, StudyContext):
        raise ValueError(f"Expected StudyContext, got {type(context).__name__}")

    lock_data = load_models_lock(lock_path)
    candidates = lock_data.get("candidates", {})

    # Extract candidate_id
    candidate_id = (
        binding.parameters.get("candidate_id")
        or binding.parameters.get("model_id")
        or getattr(binding, "provenance", {}).get("model_id")
        or context.parameters.get("candidate_id")
        or context.parameters.get("model_id")
    )

    if not candidate_id or not isinstance(candidate_id, str):
        raise ValueError("candidate_id must be provided in binding or context parameters")

    if candidate_id not in candidates:
        raise ValueError(f"Unknown or unpinned model candidate: {candidate_id!r}")

    cand = candidates[candidate_id]

    from .admission_evidence import preflight
    checked, verified_facts = preflight(binding, context, candidate_id, cand)
    if isinstance(checked, StudyResult):
        return checked
    cand = checked

    # Enforce zero cloud spend
    cloud_spend = binding.parameters.get(
        "cloud_spend_usd", cand.get("cloud_spend_usd", 0.0)
    )
    if cloud_spend != 0.0 or cloud_spend > 0.0:
        raise ValueError(f"Cloud spend forbidden: cloud_spend_usd must be 0.0, got {cloud_spend}")

    # Enforce auto_download is False
    auto_download = binding.parameters.get(
        "auto_download", cand.get("auto_download", False)
    )
    if auto_download is not False:
        raise ValueError("Forbidden auto-download: auto_download must be false")

    diagnostics: list[str] = []
    status = "admitted"

    # Enforce resource caps against context budget
    budget_ram = context.parameters.get("max_ram_gb") or context.parameters.get("host_ram_gb")
    if budget_ram is not None and cand.get("max_ram_gb", 0) > budget_ram:
        status = "named_block"
        diagnostics.append(
            f"RAM cap exceeded: candidate {candidate_id} requires {cand['max_ram_gb']} GB, budget is {budget_ram} GB"
        )

    budget_vram = context.parameters.get("max_vram_gb") or context.parameters.get("host_vram_gb")
    if budget_vram is not None and cand.get("max_vram_gb", 0) > budget_vram:
        status = "named_block"
        diagnostics.append(
            f"VRAM cap exceeded: candidate {candidate_id} requires {cand['max_vram_gb']} GB, budget is {budget_vram} GB"
        )

    budget_disk = context.parameters.get("max_disk_gb") or context.parameters.get("host_disk_gb")
    if budget_disk is not None and cand.get("max_disk_gb", 0) > budget_disk:
        status = "named_block"
        diagnostics.append(
            f"Disk cap exceeded: candidate {candidate_id} requires {cand['max_disk_gb']} GB, budget is {budget_disk} GB"
        )

    # Inspect host environment presence (weights, cuda, runtime)
    weights_available = context.parameters.get(
        "weights_available", binding.parameters.get("weights_available")
    )
    weights_path = context.parameters.get("weights_path") or binding.parameters.get("weights_path")
    if weights_available is False:
        diagnostics.append(f"Local weights absent on host for candidate {candidate_id}")
        if context.parameters.get("prefer_not_tested", False):
            status = "not_tested"
        else:
            status = "named_block"
    elif weights_path is not None and not Path(weights_path).exists():
        diagnostics.append("local_weights_unavailable")
        status = "named_block"

    cuda_available = context.parameters.get(
        "cuda_available", binding.parameters.get("cuda_available")
    )
    if cuda_available is False and cand.get("requires_cuda") is True:
        diagnostics.append(f"CUDA acceleration absent on host for candidate {candidate_id}")
        if status != "not_tested":
            status = "named_block"

    runtime_env_available = context.parameters.get(
        "runtime_env_available", binding.parameters.get("runtime_env_available")
    )
    if runtime_env_available is False:
        diagnostics.append(
            f"Runtime environment {cand.get('runtime_env')!r} absent on host for candidate {candidate_id}"
        )
        if status != "not_tested":
            status = "named_block"

    # Explicit override for not_tested status
    if context.parameters.get("status") == "not_tested" or binding.parameters.get("status") == "not_tested":
        status = "not_tested"

    span = binding.span or context.span or SourceSpan(0, 3360, context.timebase)

    public_record = {"candidate_id": candidate_id, "status": status, **verified_facts}
    payload = json.dumps(public_record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    product_ref = MaterialRef(
        id=f"model-admission-{candidate_id.lower()}",
        sha256=hashlib.sha256(payload).hexdigest(),
        kind="metadata",
        bytes=len(payload),
        metadata=public_record,
    )

    return StudyResult(
        study_id=context.study_id,
        operator=binding.operator,
        span=span,
        products=(product_ref,),
        metadata={
            "candidate_id": candidate_id,
            "name": cand["name"],
            "wing": cand["wing"],
            "status": status,
            "admitted": (status == "admitted"),
            "diagnostics": diagnostics,
            "weights_sha256": cand["weights_sha256"],
            "runtime_env": cand["runtime_env"],
            "max_ram_gb": cand["max_ram_gb"],
            "max_vram_gb": cand["max_vram_gb"],
            "max_disk_gb": cand["max_disk_gb"],
            **verified_facts,
        },
    )
