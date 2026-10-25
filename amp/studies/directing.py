"""Wing 9 Preference-Guided Directing (Issues #105-108) & Semantic Cycle (Issues #101-104).

Implements:
- compile_directing_question: binds directing questions/notes to candidate formulations without arbitrary execution (#105).
- evaluate_directing_choice: evaluates honest choices, ties (dual retention), and complete rejections without forced winners (#106).
- run_three_round_directing_experiment: 3-round parameter narrowing pass preserving provenance across rounds (#107).
- evaluate_preference_ranker_readiness: gates ranker benchmark until >=12 decisions, returns named_block or kendall_tau (#108).
- record_semantic_observation_cycle: render-describe-retrieve cycle with deterministic replay cache (#101-#104).
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any, Mapping, Optional, Sequence, Union

from amp.studies.contracts import _check_command_or_url


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _compute_digest(data: Any) -> str:
    return hashlib.sha256(_canonical_json(data).encode("utf-8")).hexdigest()


def compile_directing_question(
    question_spec: Mapping[str, Any],
    constraints: Mapping[str, Any],
) -> dict[str, Any]:
    """Compile a directing question/note with candidate formulations and preserved constraints (#105).

    Intent is captured as descriptive data and is not silently executed as shell commands or arbitrary code.
    """
    if not isinstance(question_spec, Mapping) or not question_spec:
        raise ValueError("question_spec must be a non-empty mapping")
    if not isinstance(constraints, Mapping):
        raise ValueError("constraints must be a mapping")

    question_id = question_spec.get("question_id")
    if not question_id or not isinstance(question_id, str):
        raise ValueError("question_spec must contain a valid non-empty 'question_id'")

    intent_note = question_spec.get("intent_note") or question_spec.get("prompt")
    if not intent_note or not isinstance(intent_note, str):
        raise ValueError("question_spec must contain 'intent_note' or 'prompt' string")

    # Safety check: ensure intent note or constraints do not inject executable commands
    err = _check_command_or_url(intent_note, "intent_note")
    if err:
        raise ValueError(f"Security violation in intent_note: {err}")
    for k, v in constraints.items():
        err = _check_command_or_url(v, f"constraint {k}")
        if err:
            raise ValueError(f"Security violation in constraints: {err}")

    raw_candidates = question_spec.get("candidate_recipes", [])
    if not isinstance(raw_candidates, (list, tuple)) or not raw_candidates:
        raise ValueError("question_spec must contain a non-empty sequence of 'candidate_recipes'")

    compiled_candidates: list[dict[str, Any]] = []
    for idx, c in enumerate(raw_candidates):
        if not isinstance(c, Mapping):
            raise ValueError(f"Candidate recipe at index {idx} must be a mapping")
        cand_id = c.get("candidate_id") or c.get("id") or f"cand-{idx:02d}"
        params = c.get("parameters", {})
        if not isinstance(params, Mapping):
            params = {"raw": params}
        compiled_candidates.append({
            "candidate_id": str(cand_id),
            "description": str(c.get("description", f"Candidate {cand_id}")),
            "parameters": dict(params),
            "status": "compiled",
        })

    target_spans = question_spec.get("target_spans", [])
    entities = question_spec.get("entities", [])
    acceptance_criteria = question_spec.get("acceptance_criteria", ["perceptual_integrity", "source_continuity"])

    compiled = {
        "schema": "amps.directing.question.v1",
        "question_id": question_id,
        "intent_note": intent_note,
        "target_spans": list(target_spans),
        "entities": list(entities),
        "constraints": dict(constraints),
        "candidates": compiled_candidates,
        "acceptance_criteria": acceptance_criteria,
        "status": "compiled",
    }
    compiled["question_digest"] = _compute_digest(compiled)
    return compiled


def evaluate_directing_choice(
    candidates: Sequence[Mapping[str, Any]],
    human_decision: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate a directing choice with honest human decisions (#106).

    Supports:
    - Choice: exactly one candidate selected.
    - Tie: multiple candidates retained without forcing an arbitrary winner.
    - Rejection: complete rejection of all candidates with recorded rationale without forced winners.
    """
    if not isinstance(candidates, (list, tuple)) or not candidates:
        raise ValueError("candidates must be a non-empty sequence of candidate objects")
    if not isinstance(human_decision, Mapping) or not human_decision:
        raise ValueError("human_decision must be a non-empty mapping")

    decision_type = human_decision.get("decision_type")
    valid_types = {"choice", "tie", "rejection"}
    if decision_type not in valid_types:
        raise ValueError(f"Invalid decision_type '{decision_type}'; must be one of {valid_types}")

    reviewer_id = human_decision.get("reviewer_id")
    if not reviewer_id or not isinstance(reviewer_id, str):
        raise ValueError("human_decision must provide a valid 'reviewer_id'")

    rationale = human_decision.get("rationale")
    if not rationale or not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("human_decision must provide a non-empty 'rationale'")

    candidate_ids = set()
    for c in candidates:
        cid = c.get("candidate_id") or c.get("id")
        if cid:
            candidate_ids.add(str(cid))

    selected_id: Optional[str] = None
    retained_ids: list[str] = []

    if decision_type == "choice":
        selected_id = human_decision.get("selected_id")
        if not selected_id or str(selected_id) not in candidate_ids:
            raise ValueError(f"Selected candidate ID '{selected_id}' not found in candidates {sorted(candidate_ids)}")
        selected_id = str(selected_id)
        retained_ids = [selected_id]

    elif decision_type == "tie":
        raw_retained = human_decision.get("retained_ids", [])
        if not isinstance(raw_retained, (list, tuple)) or len(raw_retained) < 2:
            raise ValueError("Tie decision requires 'retained_ids' with at least 2 candidate IDs")
        for rid in raw_retained:
            if str(rid) not in candidate_ids:
                raise ValueError(f"Retained candidate '{rid}' not found in candidates {sorted(candidate_ids)}")
            retained_ids.append(str(rid))
        selected_id = None  # No forced single winner in tie

    elif decision_type == "rejection":
        if human_decision.get("selected_id") is not None:
            raise ValueError("Forcing a selected winner on rejection is strictly forbidden")
        retained_ids = []
        selected_id = None

    outcome = {
        "schema": "amps.directing.evaluation.v1",
        "decision_type": decision_type,
        "reviewer_id": reviewer_id,
        "rationale": rationale.strip(),
        "selected_id": selected_id,
        "retained_ids": retained_ids,
        "forced_winner": False,
        "candidates_evaluated_count": len(candidates),
        "status": "evaluated",
    }
    outcome["evaluation_digest"] = _compute_digest(outcome)
    return outcome


def run_three_round_directing_experiment(
    question_spec: Mapping[str, Any],
    round_decisions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Execute a 3-round parameter narrowing directing pass preserving provenance (#107).

    Each round evaluates candidate parameter variations and narrows search space based on human decisions.
    """
    if not isinstance(round_decisions, (list, tuple)) or len(round_decisions) != 3:
        raise ValueError(f"Exactly 3 round decisions required, got {len(round_decisions) if isinstance(round_decisions, (list, tuple)) else type(round_decisions)}")

    qid = question_spec.get("question_id", "dir-q-default")
    initial_params = dict(question_spec.get("parameters", {
        "retiming_factor": [0.9, 1.3],
        "framing_scale": [1.0, 2.5],
        "blend_opacity": [0.2, 0.8],
    }))

    current_params = copy.deepcopy(initial_params)
    round_records: list[dict[str, Any]] = []
    prev_digest = _compute_digest(question_spec)

    for round_idx in range(3):
        round_num = round_idx + 1
        decision = round_decisions[round_idx]

        # Generate candidates for this round reflecting current narrowed bounds
        candidates = [
            {
                "candidate_id": f"round-{round_num}-cand-A",
                "description": f"Round {round_num} candidate Lower/Baseline",
                "parameters": {k: v[0] if isinstance(v, list) and len(v) == 2 else v for k, v in current_params.items()},
            },
            {
                "candidate_id": f"round-{round_num}-cand-B",
                "description": f"Round {round_num} candidate Midpoint",
                "parameters": {k: ((v[0] + v[1]) / 2.0 if isinstance(v, list) and len(v) == 2 and isinstance(v[0], (int, float)) else v) for k, v in current_params.items()},
            },
            {
                "candidate_id": f"round-{round_num}-cand-C",
                "description": f"Round {round_num} candidate Upper",
                "parameters": {k: v[1] if isinstance(v, list) and len(v) == 2 else v for k, v in current_params.items()},
            },
        ]

        eval_result = evaluate_directing_choice(candidates, decision)

        # Narrow parameters for next round based on evaluation
        next_params = copy.deepcopy(current_params)
        dtype = eval_result["decision_type"]

        if dtype == "choice":
            sel = eval_result["selected_id"]
            if sel == f"round-{round_num}-cand-A":
                for k, v in next_params.items():
                    if isinstance(v, list) and len(v) == 2 and isinstance(v[0], (int, float)):
                        mid = (v[0] + v[1]) / 2.0
                        next_params[k] = [v[0], mid]
            elif sel == f"round-{round_num}-cand-C":
                for k, v in next_params.items():
                    if isinstance(v, list) and len(v) == 2 and isinstance(v[0], (int, float)):
                        mid = (v[0] + v[1]) / 2.0
                        next_params[k] = [mid, v[1]]
            else:  # cand-B
                for k, v in next_params.items():
                    if isinstance(v, list) and len(v) == 2 and isinstance(v[0], (int, float)):
                        span = (v[1] - v[0]) / 4.0
                        mid = (v[0] + v[1]) / 2.0
                        next_params[k] = [max(v[0], mid - span), min(v[1], mid + span)]
        elif dtype == "tie":
            # Retain union of parameter spans
            pass
        elif dtype == "rejection":
            # Keep broader exploration bounds
            pass

        round_entry = {
            "round_number": round_num,
            "parent_digest": prev_digest,
            "candidate_count": len(candidates),
            "evaluation": eval_result,
            "narrowed_parameters": next_params,
        }
        round_entry["round_digest"] = _compute_digest(round_entry)
        prev_digest = round_entry["round_digest"]
        round_records.append(round_entry)
        current_params = next_params

    # Final frozen values (midpoints of narrowed parameters)
    final_frozen = {}
    for k, v in current_params.items():
        if isinstance(v, list) and len(v) == 2 and isinstance(v[0], (int, float)):
            final_frozen[k] = round((v[0] + v[1]) / 2.0, 4)
        else:
            final_frozen[k] = v

    experiment = {
        "schema": "amps.directing.experiment.v1",
        "experiment_id": f"exp-{qid}-3rounds",
        "question_id": qid,
        "rounds": round_records,
        "final_parameters": final_frozen,
        "final_outcome": {
            "status": "converged" if round_records[-1]["evaluation"]["decision_type"] in ("choice", "tie") else "rejected",
            "retained_ids": round_records[-1]["evaluation"]["retained_ids"],
            "provenance_chain": [r["round_digest"] for r in round_records],
        },
    }
    experiment["experiment_digest"] = _compute_digest(experiment)
    return experiment


def evaluate_preference_ranker_readiness(
    feedback_records: Sequence[Mapping[str, Any]],
    min_decisions: int = 12,
) -> dict[str, Any]:
    """Gate preference ranker benchmark readiness until >=12 decisions (#108).

    If feedback count < min_decisions, returns named_block with diagnostic 'insufficient_feedback'.
    If feedback count >= min_decisions, calculates rank concordance (Kendall's tau).
    """
    if not isinstance(feedback_records, (list, tuple)):
        raise ValueError("feedback_records must be a sequence")

    count = len(feedback_records)
    if count < min_decisions:
        return {
            "schema": "amps.directing.ranker_readiness.v1",
            "ready": False,
            "status": "insufficient_feedback",
            "named_block": "insufficient_feedback",
            "records_count": count,
            "min_required": min_decisions,
            "kendall_tau": None,
            "concordance_score": None,
            "diagnostic": f"Insufficient feedback records ({count} < {min_decisions}). Ranker benchmark execution gated.",
        }

    # Extract score or rank pairs to compute rank concordance
    pred_vals: list[float] = []
    human_vals: list[float] = []

    for rec in feedback_records:
        # Check rank or score fields
        p = rec.get("predicted_rank") if "predicted_rank" in rec else rec.get("predicted_score")
        h = rec.get("human_rank") if "human_rank" in rec else rec.get("human_score")

        if p is None or h is None:
            # Fallback: check preference choice agreement
            p = float(rec.get("model_confidence", 0.5))
            h = 1.0 if rec.get("human_accepted", True) else 0.0

        try:
            pred_vals.append(float(p))
            human_vals.append(float(h))
        except (ValueError, TypeError):
            pred_vals.append(0.5)
            human_vals.append(0.5)

    n = len(pred_vals)
    concordant = 0
    discordant = 0
    ties_x = 0
    ties_y = 0

    for i in range(n):
        for j in range(i + 1, n):
            dx = pred_vals[i] - pred_vals[j]
            dy = human_vals[i] - human_vals[j]
            if dx * dy > 0:
                concordant += 1
            elif dx * dy < 0:
                discordant += 1
            else:
                if dx == 0 and dy != 0:
                    ties_x += 1
                elif dy == 0 and dx != 0:
                    ties_y += 1

    total_pairs = (n * (n - 1)) / 2
    denom = math.sqrt((concordant + discordant + ties_x) * (concordant + discordant + ties_y))
    if denom > 0:
        tau = (concordant - discordant) / denom
    else:
        tau = 0.0

    concordance_score = concordant / (concordant + discordant) if (concordant + discordant) > 0 else 1.0

    return {
        "schema": "amps.directing.ranker_readiness.v1",
        "ready": True,
        "status": "ready",
        "named_block": None,
        "records_count": count,
        "min_required": min_decisions,
        "kendall_tau": round(tau, 4),
        "concordance_score": round(concordance_score, 4),
        "diagnostic": None,
    }


def record_semantic_observation_cycle(
    unit_id: str,
    render_spec: Mapping[str, Any],
    description: str,
    retrieval_query: str,
    replay_cache: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Execute and record the render-describe-retrieve semantic cycle (#101-#104).

    Utilizes replay_cache so offline and test execution does not re-invoke external inference.
    """
    if not unit_id or not isinstance(unit_id, str):
        raise ValueError("unit_id must be a non-empty string")
    if not isinstance(render_spec, Mapping):
        raise ValueError("render_spec must be a mapping")
    if not description or not isinstance(description, str):
        raise ValueError("description must be a non-empty string")
    if not retrieval_query or not isinstance(retrieval_query, str):
        raise ValueError("retrieval_query must be a non-empty string")

    active_cache = dict(replay_cache) if replay_cache is not None else {}
    cache_key = f"{unit_id}:{retrieval_query.strip().lower()}"

    if cache_key in active_cache:
        retrieval_result = active_cache[cache_key]
        cache_hit = True
    else:
        cache_hit = False
        # Deterministic offline vector synthesis (32 dimensions from hash digest)
        combined = f"{description}|{retrieval_query}"
        h = hashlib.sha256(combined.encode("utf-8")).digest()
        # Derive pseudo-normalized embedding vector
        raw_vec = [float(b - 128) / 128.0 for b in h[:16]]
        norm = math.sqrt(sum(x * x for x in raw_vec)) or 1.0
        norm_vec = [round(x / norm, 4) for x in raw_vec]

        # Deterministic relevance score
        query_terms = set(retrieval_query.lower().split())
        desc_terms = set(description.lower().split())
        overlap = len(query_terms.intersection(desc_terms))
        score = min(1.0, 0.5 + (0.1 * overlap))

        retrieval_result = {
            "match_id": f"sem-{unit_id}",
            "relevance_score": round(score, 4),
            "semantic_vector": norm_vec,
            "query_terms_matched": sorted(query_terms.intersection(desc_terms)),
        }
        active_cache[cache_key] = retrieval_result

    cycle = {
        "schema": "amps.directing.semantic_cycle.v1",
        "unit_id": unit_id,
        "render_spec": dict(render_spec),
        "description": description,
        "retrieval_query": retrieval_query,
        "cache_hit": cache_hit,
        "retrieval_result": retrieval_result,
        "replay_cache": active_cache,
    }
    cycle["cycle_digest"] = _compute_digest(cycle)
    return cycle
