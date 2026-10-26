"""CLI planning/replay over the existing composition and FX contracts."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import uuid

from ..runtime import runtime_path
from . import resolve_composition
from .novelty import DuplicatePerformance, PerformanceHistory, _id, canonical_identity, canonical_json
from .record import PerformanceRecord
from .supervisor import plan_performance

ENGINE_FILES = ("web/fx/core.mjs", "web/fx/catalog.mjs", "web/fx/visual-engine.mjs", "web/fx/audio-engine.mjs")
PERFORMANCE_OPTIONS = {"--operation", "--corpus", "--profile", "--history", "--duration-frames", "--identity"}


class PerformanceCommandError(ValueError):
    pass


def retained_engine_identity(root=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    hashes = {logical: hashlib.sha256(runtime_path(root, logical).read_bytes()).hexdigest() for logical in ENGINE_FILES}
    return hashlib.sha256(canonical_json(hashes).encode()).hexdigest()


def _read(path):
    if not path:
        raise PerformanceCommandError("performance-input-required")
    try:
        return json.loads(Path(path).read_text())
    except (OSError, UnicodeError, ValueError) as exc:
        raise PerformanceCommandError("performance-input-unavailable") from exc


def _project_identity(selection):
    project = resolve_composition(selection).resolve()
    for root in (Path.cwd(), project.parent, project.parent.parent):
        manifest = root / "ace-manifest.json"
        if manifest.is_file():
            rows = _read(manifest).get("compositions", [])
            matches = [row["id"] for row in rows if (root / row["path"]).resolve() == project]
            if len(matches) == 1:
                return _id(matches[0], "composition id")
    config = _read(project / "composition.json")
    identifier = config.get("composition_id", config.get("id"))
    if identifier is None:
        raise PerformanceCommandError("composition-identity-unavailable")
    return _id(identifier, "composition id")


def _distinct(inputs, outputs):
    paths = [Path(value).expanduser().resolve() for value in [*inputs, *outputs] if value]
    for index, path in enumerate(paths):
        for other in paths[:index]:
            if path == other or (path.exists() and other.exists() and path.samefile(other)):
                raise PerformanceCommandError("performance-path-overlap")


def _fresh_output(path):
    if not path or Path(path).suffix.lower() != ".json":
        raise PerformanceCommandError("fresh-json-output-required")
    destination = Path(path).expanduser()
    if destination.exists() or destination.is_symlink():
        raise PerformanceCommandError("performance-output-exists")
    return destination


def _write(destination, record):
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = (json.dumps(record, indent=2, allow_nan=False) + "\n").encode()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(destination, flags, 0o600), "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    if destination.read_bytes() != payload:
        raise PerformanceCommandError("performance-output-readback-failed")
    return hashlib.sha256(payload).hexdigest()


def run(args, supplied_options):
    receipt = {"schema": "amps.performance-command.v1", "operation": args.operation,
               "prepared_media_verified": False, "artistic_acceptance": "pending",
               "new_decisions_resolved": False}
    reserved_identity = None
    try:
        allowed = PERFORMANCE_OPTIONS | {"--composition", "--project", "--seed", "--session", "--output", "--dry-run"}
        if supplied_options - allowed:
            raise PerformanceCommandError("unsupported-performance-option")
        project_id = _project_identity(args.project)
        if args.operation == "new":
            if args.duration_frames is None:
                raise PerformanceCommandError("performance-duration-required")
            if args.session or args.identity:
                raise PerformanceCommandError("new-performance-cannot-replace-saved-decisions")
            corpus, profile = _read(args.corpus), _read(args.profile)
            if corpus.get("composition_id") != project_id:
                raise PerformanceCommandError("performance-composition-mismatch")
            if corpus.get("engine_sha256") != retained_engine_identity():
                raise PerformanceCommandError("performance-engine-mismatch")
            seed = args.seed if "--seed" in supplied_options else secrets.randbits(32)
            saved = plan_performance(corpus, profile, seed=seed, duration_frames=args.duration_frames,
                                     record_id="performance-" + uuid.uuid4().hex)
            receipt.update(status="planned", new_decisions_resolved=True, engine_identity_verified=True)
            if not args.dry_run:
                if not args.history:
                    raise PerformanceCommandError("performance-history-required")
                destination = _fresh_output(args.output)
                _distinct((args.corpus, args.profile), (args.history, destination))
                reserved_identity = PerformanceHistory(args.history).reserve(saved)
                receipt["record_sha256"] = _write(destination, saved.to_dict())
        else:
            if args.corpus or args.profile or args.duration_frames is not None or "--seed" in supplied_options or args.dry_run:
                raise PerformanceCommandError("replay-consumes-saved-decisions-only")
            if bool(args.session) == bool(args.identity):
                raise PerformanceCommandError("select-one-saved-performance")
            if args.identity:
                if not args.history:
                    raise PerformanceCommandError("performance-history-required")
                saved = PerformanceHistory(args.history).load(args.identity)
            else:
                data = _read(args.session)
                if data.get("schema") == "amps.performance-checkpoint.v1":
                    from .supervisor import PerformanceSupervisor
                    saved = PerformanceSupervisor.restore(data, simulation=data.get("observation_mode") == "simulation").record
                else:
                    saved = PerformanceRecord.from_dict(data)
            if saved.composition_id != project_id:
                raise PerformanceCommandError("performance-composition-mismatch")
            actual_engine = retained_engine_identity()
            receipt["engine_identity_verified"] = saved.runtime["engine_sha256"] == actual_engine
            receipt["status"] = "record-ready" if receipt["engine_identity_verified"] else "engine-mismatch"
            if args.operation == "replay":
                if not receipt["engine_identity_verified"]:
                    raise PerformanceCommandError("performance-engine-mismatch")
                destination = _fresh_output(args.output)
                _distinct((args.session, args.history), (destination,))
                receipt["record_sha256"] = _write(destination, saved.to_dict())
            elif args.output:
                raise PerformanceCommandError("inspection-is-read-only")
        receipt.update(identity=canonical_identity(saved), duration_frames=saved.runtime["duration_frames"],
                       resolved_events=len(saved.runtime["events"]), seed=saved.runtime["seed"],
                       profile_admitted=saved.runtime["profile"]["admitted"], playback_admitted=False)
        print(json.dumps(receipt, indent=2, allow_nan=False))
        return 0
    except DuplicatePerformance as exc:
        receipt.update(status="blocked", error={"code": "duplicate-performance"}, identity=str(exc))
    except PerformanceCommandError as exc:
        receipt.update(status="blocked", error={"code": str(exc)})
    except sqlite3.DatabaseError:
        receipt.update(status="blocked", error={"code": "performance-history-unavailable"})
    except (OSError, ValueError, KeyError, TypeError, AttributeError, UnicodeError):
        receipt.update(status="blocked", error={"code": "invalid-performance-contract"})
    if reserved_identity is not None:
        receipt["reserved_identity"] = reserved_identity
        receipt["record_retained_in_history"] = True
    print(json.dumps(receipt, indent=2, allow_nan=False))
    return 2
