#!/usr/bin/env python3
"""Run the existing God-here baseline recipe without changing production code."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

EXPECTED_SOURCE_SHA256 = "bde1c7e0910941f8ca3bce06e8c2ddb3a31da4335b544fd041d84e97d1060225"
PINNED_COMMIT = "b8c9b3c6ac5fc428c8895b56f4dcfcf8989766f0"


def sha256(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def timestamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    repo, source, output, evidence = (value.resolve() for value in (
        args.repo, args.source, args.output, args.evidence))
    evidence.mkdir(parents=True, exist_ok=True)
    if output.exists() and any(output.iterdir()):
        raise SystemExit("Output must be a fresh empty directory.")
    output.mkdir(parents=True, exist_ok=True)
    receipt_path = evidence / "execution-receipt.json"
    if receipt_path.exists():
        raise SystemExit("Preserve the existing execution receipt; use a new evidence directory.")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    worktree = subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True)
    source_hash = sha256(source)
    if commit != PINNED_COMMIT or worktree or source_hash != EXPECTED_SOURCE_SHA256:
        raise SystemExit("Pinned commit, clean worktree, and expected source SHA256 are required.")
    environment = os.environ.copy()
    for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        environment[key] = "2"
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=repo).decode().split("\0")
    tracked_hashes = {name: sha256(repo / name) for name in tracked if name}
    commands = [
        ("validate", [sys.executable, "-m", "amp.cli", "validate"]),
        ("audio", [sys.executable, "-m", "amp.cli", "audio", "--source", str(source),
                   "--output", str(output / "audio")]),
        ("render", [sys.executable, "-m", "amp.cli", "render", "--source", str(source),
                    "--audio", str(output / "audio/candidate-B.wav"), "--output",
                    str(output / "god-here-linear-picture.mp4"), "--start", "0",
                    "--end", "112", "--width", "1280", "--mode", "hard", "--typography"]),
        ("finish", [sys.executable, "tools/finish_production.py", str(source), str(output)]),
    ]
    def logical_command(command):
        return [part.replace(str(output), "${OUTPUT}").replace(str(source), "${SOURCE}")
                .replace(sys.executable, "${PYTHON}") for part in command]
    versions = {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "Pillow", "setuptools")}
    for name in ("ffmpeg", "ffprobe"):
        versions[name] = subprocess.check_output([name, "-version"], text=True).splitlines()[0]
    font = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    receipt = {
        "schema": "god-here.existing-recipe-execution.v1",
        "started_at_utc": timestamp(), "finished_at_utc": None, "status": "running",
        "repository": "4444J99/audiovisual-media-postproduction-system",
        "pinned_main_commit": commit, "worktree_initially_clean": not worktree,
        "source_logical_path": "project_sources/02-2020-04-26-god-s-ears-second-draft.mp4",
        "source_sha256": source_hash, "source_bytes": source.stat().st_size,
        "tracked_file_sha256": tracked_hashes,
        "python": sys.version, "platform": platform.platform(), "versions": versions,
        "explicit_environment": {key: environment[key] for key in (
            "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")},
        "font": {"name": "DejaVuSans.ttf", "present": font.is_file(),
                 "sha256": sha256(font) if font.is_file() else None},
        "recipe": ["README.md Run section", "tools/finish_production.py"],
        "scope": {"source_start_frame": 0, "source_end_frame_exclusive": 3360,
                  "width": 1280, "height": 720, "fps": 30, "duration_seconds": 112,
                  "fields": True, "boundary_mode": "hard", "typography": True,
                  "fine_layers_baseline": False, "existing_finish_recipe_seeds": [17, 29, 43]},
        "code_modified": False, "model_downloads": False, "paid_services": False,
        "artistic_acceptance": "not_assessed", "historical_byte_identity": "pending_comparison",
        "commands_planned": [{"step": name, "argv": logical_command(command)} for name, command in commands],
        "steps": [],
    }
    def save():
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    save()
    for name, command in commands:
        print(json.dumps({"step": name, "status": "started", "at": timestamp()}), flush=True)
        started = time.monotonic()
        with (evidence / (name + ".stdout.log")).open("wb") as stdout, (evidence / (name + ".stderr.log")).open("wb") as stderr:
            process = subprocess.run(command, cwd=repo, env=environment, stdout=stdout, stderr=stderr)
        step = {"step": name, "argv": logical_command(command), "exit_code": process.returncode,
                "elapsed_seconds": round(time.monotonic() - started, 3), "finished_at_utc": timestamp(),
                "stdout_log": name + ".stdout.log", "stderr_log": name + ".stderr.log"}
        receipt["steps"].append(step)
        save()
        print(json.dumps(step), flush=True)
        if process.returncode:
            receipt.update(status="failed", failed_step=name, finished_at_utc=timestamp())
            save()
            return process.returncode
    receipt.update(status="recipe_completed_validation_pending", finished_at_utc=timestamp(),
                   source_unchanged=sha256(source) == source_hash,
                   worktree_finally_clean=not subprocess.check_output(
                       ["git", "status", "--porcelain"], cwd=repo, text=True))
    save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
