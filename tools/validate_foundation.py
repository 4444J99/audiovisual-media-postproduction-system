#!/usr/bin/env python3
"""Validate foundation records only; never process media or approve creative work."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def load(path: str) -> dict:
    def reject_constant(value: str) -> None:
        raise ValueError(f"Non-finite JSON value: {value}")
    def unique_keys(pairs: list) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads((ROOT / path).read_text(encoding="utf-8"),
                      parse_constant=reject_constant, object_pairs_hook=unique_keys)


def check_graph(rows: list[dict], dependency_key: str) -> None:
    by_id = {row["id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError("Duplicate IDs")
    visited: set[str] = set()
    active: set[str] = set()
    def visit(identifier: str) -> None:
        if identifier not in by_id:
            raise ValueError(f"Unknown dependency: {identifier}")
        if identifier in active:
            raise ValueError("Dependency cycle")
        if identifier in visited:
            return
        active.add(identifier)
        for dependency in by_id[identifier][dependency_key]:
            visit(dependency)
        active.remove(identifier)
        visited.add(identifier)
    for identifier in by_id:
        visit(identifier)


def check_proposal(proposal: dict, validator: Draft202012Validator) -> None:
    validator.validate(proposal)
    target_ids = {target["id"] for target in proposal["targets"]}
    if len(target_ids) != len(proposal["targets"]):
        raise ValueError("Duplicate target IDs")
    for target in proposal["targets"]:
        if target["end_tick"] <= target["start_tick"]:
            raise ValueError("End must be after start")
    for operation in proposal["operations"]:
        if operation["target_id"] not in target_ids:
            raise ValueError("Unknown operation target")
    check_graph(proposal["operations"], "depends_on")


def main() -> None:
    schema = load("schemas/revision-proposal.schema.json")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    proposal = load("examples/revision-proposal.json")
    check_proposal(proposal, validator)
    negative_cases = []
    bad = copy.deepcopy(proposal); bad["execution_allowed"] = True
    negative_cases.append(bad)
    bad = copy.deepcopy(proposal); bad["targets"][0]["end_tick"] = 1
    negative_cases.append(bad)
    bad = copy.deepcopy(proposal); bad["operations"][0]["target_id"] = "missing"
    negative_cases.append(bad)
    bad = copy.deepcopy(proposal); bad["operations"][0]["depends_on"] = ["listener-emphasis"]
    negative_cases.append(bad)
    bad = copy.deepcopy(proposal); bad["review"]["accepted_by"] = "invented-reviewer"
    negative_cases.append(bad)
    bad = copy.deepcopy(proposal); bad["operations"][0]["kind"] = "shell-command"
    negative_cases.append(bad)
    for candidate in negative_cases:
        try:
            check_proposal(candidate, validator)
        except (ValueError, __import__("jsonschema").exceptions.ValidationError):
            continue
        raise ValueError("Negative proposal unexpectedly accepted")
    backlog = load("planning/epics.json")
    if backlog["status"] != "planned" or backlog["github_issues_created"]:
        raise ValueError("Backlog state is inconsistent with this foundation")
    if backlog["historical_backlog_imported"]:
        raise ValueError("Historical import has not been verified")
    check_graph(backlog["epics"], "depends_on")
    for epic in backlog["epics"]:
        if (epic["status"] != "planned" or epic["github_issue_number"] is not None
                or not 0 <= epic["first_circle"] <= 6
                or not epic["work_items"] or not epic["acceptance_criteria"]):
            raise ValueError(f"Invalid epic: {epic['id']}")
    link_count = 0
    for path in ROOT.rglob("*.md"):
        if ".venv" in path.parts:
            continue
        for href in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" in href or href.startswith("#"):
                continue
            target = (path.parent / href.split("#", 1)[0]).resolve()
            if not target.is_relative_to(ROOT) or not target.exists():
                raise ValueError(f"Broken local link in {path}: {href}")
            link_count += 1
    print(json.dumps({"status": "passed", "schema_valid": True,
                      "illustrative_proposal_valid": True,
                      "negative_cases_rejected": len(negative_cases),
                      "epics": len(backlog["epics"]),
                      "work_items": sum(len(e["work_items"]) for e in backlog["epics"]),
                      "local_links_checked": link_count,
                      "media_operations_executed": False,
                      "creative_acceptance": False}, indent=2))


if __name__ == "__main__":
    main()
