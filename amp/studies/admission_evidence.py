"""Read-only F04 verification over pinned local inputs and workload evidence.

This verifies a producing executor's recorded workload, not a new inference run.
The private StudyContext owns locators; none are projected into public results.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
from pathlib import Path
import re
import subprocess
import stat
import time

from amp.composition.containers import SourceSpan, StudyResult

HASH = re.compile(r"[0-9a-f]{64}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
PRIVATE = {"weights_path", "model_code_root", "environment_root", "workload_receipt_path", "probe_output_path"}
PROBE = '''import json,sys
kind=sys.argv[1]
devices=["cpu"]
version=sys.version.split()[0]
if kind=="pytorch":
 import torch
 version=torch.__version__
 if torch.cuda.is_available(): devices.append("cuda")
 if hasattr(torch.backends,"mps") and torch.backends.mps.is_available(): devices.append("mps")
elif kind=="jax_flax":
 import jax,flax
 version=jax.__version__
 devices=sorted(set(x.platform for x in jax.devices()))
elif kind!="python_fixture":
 raise ValueError("unsupported fixed backend")
print(json.dumps(dict(prefix=sys.prefix,version=version,devices=devices)))
'''


class EvidenceUnavailable(ValueError):
    pass


def number(value, role, minimum=0):
    try:
        valid = type(value) in (int, float) and math.isfinite(value) and value >= minimum
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{role} must be a finite nonnegative number")
    return value


def finite_json(payload):
    def invalid(_value):
        raise EvidenceUnavailable("nonfinite_evidence")
    return json.loads(payload, parse_constant=invalid)


def file_identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def remember_input(value, snapshots):
    locator = Path(value).absolute()
    resolved = locator.resolve(strict=True)
    snapshots.append((locator, resolved, file_identity(resolved.stat())))


def revalidate_inputs(snapshots, deadline):
    for locator, resolved, identity in snapshots:
        if time.monotonic() >= deadline:
            raise EvidenceUnavailable("verification_deadline_exhausted")
        if locator.resolve(strict=True) != resolved or file_identity(resolved.stat()) != identity:
            raise EvidenceUnavailable("artifact_changed_during_verification")


def verify_code(code_root, expected, deadline, snapshots):
    argv = ["git", "--no-replace-objects", "-C", str(code_root)]
    if run([*argv, "rev-parse", "HEAD"], deadline) != expected:
        raise EvidenceUnavailable("code_identity_mismatch")
    if run([*argv, "status", "--porcelain=v1", "--untracked-files=all"], deadline):
        raise EvidenceUnavailable("code_identity_mismatch")
    # Read the pinned tree and actual bytes: index visibility flags are not proof.
    tree = run([*argv, "ls-tree", "-rz", "--full-tree", expected], deadline)
    for entry in tree.split("\0"):
        if not entry:
            continue
        description, name = entry.split("\t", 1)
        mode, kind, expected_blob = description.split(" ")
        path = code_root / name
        if kind != "blob" or mode not in {"100644", "100755"} or path.is_symlink():
            raise EvidenceUnavailable("code_tree_entry_unsupported")
        remember_input(str(path), snapshots)
        blob, _ = sha_file(str(path), deadline, git_blob=True)
        executable = bool(path.stat().st_mode & 0o111)
        if blob != expected_blob or executable != (mode == "100755"):
            raise EvidenceUnavailable("code_identity_mismatch")


def sha_file(value, deadline, *, maximum=None, git_blob=False):
    if not isinstance(value, str) or not value:
        raise EvidenceUnavailable("local_artifact_unavailable")
    path = Path(value).resolve(strict=True)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or maximum is not None and before.st_size > maximum:
            raise EvidenceUnavailable("artifact_size_invalid")
        digest = hashlib.sha1() if git_blob else hashlib.sha256()
        if git_blob:
            digest.update(f"blob {before.st_size}\0".encode())
        consumed=0
        while True:
            if time.monotonic() >= deadline:
                raise EvidenceUnavailable("verification_deadline_exhausted")
            block = stream.read(1024 * 1024 if maximum is None else min(1024 * 1024,maximum-consumed+1))
            if not block:
                break
            consumed+=len(block)
            if maximum is not None and consumed>maximum:raise EvidenceUnavailable("artifact_size_invalid")
            digest.update(block)
        after = os.fstat(stream.fileno())
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise EvidenceUnavailable("artifact_changed_during_verification")
    current = path.stat()
    if (current.st_dev,current.st_ino,current.st_size,current.st_mtime_ns,current.st_ctime_ns) != (
            after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
        raise EvidenceUnavailable("artifact_changed_during_verification")
    return digest.hexdigest(), after.st_size


def run(argv, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise EvidenceUnavailable("verification_deadline_exhausted")
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        out, _ = process.communicate(timeout=min(remaining, 10))
    except BaseException:
        import signal
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=1)
        except ProcessLookupError:
            process.wait()
        raise
    if process.returncode:
        raise EvidenceUnavailable("local_probe_failed")
    return out.decode().strip()


def read_receipt(value, expected, deadline):
    if not isinstance(value,str) or not value or not isinstance(expected,str) or not HASH.fullmatch(expected):
        raise EvidenceUnavailable("workload_receipt_identity_unavailable")
    path = Path(value).resolve(strict=True)
    with os.fdopen(os.open(path,os.O_RDONLY|os.O_NONBLOCK),"rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size>1024*1024:
            raise EvidenceUnavailable("workload_receipt_size_invalid")
        payload = stream.read(1024*1024+1)
        after = os.fstat(stream.fileno())
    if time.monotonic()>=deadline or len(payload)>1024*1024:
        raise EvidenceUnavailable("workload_receipt_size_or_deadline_exceeded")
    if (before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns) or hashlib.sha256(payload).hexdigest()!=expected:
        raise EvidenceUnavailable("workload_receipt_identity_mismatch")
    return finite_json(payload)


def preflight(binding, context, candidate_id, candidate):
    """Return a blocked StudyResult or verified candidate/public facts for success."""
    parameters = context.parameters
    if PRIVATE.intersection(binding.parameters):
        raise ValueError("Private model locators belong to StudyContext")
    identities = [source[key] for source in (candidate, binding.parameters, binding.provenance, parameters)
                  for key in ("candidate_id", "model_id") if source.get(key) is not None]
    if any(value != candidate_id for value in identities):
        raise ValueError("Conflicting model candidate identities")
    for source in (candidate, binding.parameters, parameters):
        if "cloud_spend_usd" in source:
            value = number(source["cloud_spend_usd"], "cloud_spend_usd")
            if value != 0:
                raise ValueError("Cloud spend forbidden")
        if source.get("auto_download", False) is not False:
            raise ValueError("Forbidden auto-download")
    for key in ("weights_available", "runtime_env_available", "cuda_available", "prefer_not_tested"):
        for source in (binding.parameters, parameters):
            if key in source and type(source[key]) is not bool:
                raise ValueError("Availability declarations must be explicit booleans")
    budgets, reasons = {}, []
    for kind in ("ram", "vram", "disk"):
        values = [number(parameters[key], key) for key in (f"max_{kind}_gb", f"host_{kind}_gb") if key in parameters]
        if not values:
            reasons.append(f"host_{kind}_cap_missing")
        else:
            budgets[kind] = min(values)
    requested = parameters.get("intended_use", "local-research")
    if requested not in {"local-research", "test", "performance"}:
        raise ValueError("Unsupported intended model use")
    pinned = candidate.get("status") == "pinned"
    if not pinned:
        reasons.append("candidate_not_pinned")
    for key, pattern in (("weights_sha256", HASH), ("environment_sha256", HASH),
                         ("python_sha256", HASH), ("code_commit", COMMIT)):
        if not isinstance(candidate.get(key), str) or not pattern.fullmatch(candidate[key]):
            reasons.append(f"{key}_unavailable")
    for key in ("code_terms", "weight_terms"):
        terms = candidate.get(key)
        if not isinstance(terms, dict) or terms.get("reviewed") is not True or not isinstance(terms.get("license_id"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .+_-]{0,127}", terms["license_id"]) or terms.get("use") != requested:
            reasons.append(f"{key}_unreviewed")
    explicit_block = False
    for key, diagnostic in (("weights_available", "local_weights_absent"),
                            ("runtime_env_available", "runtime_environment_absent")):
        if any(source.get(key) is False for source in (parameters, binding.parameters)):
            reasons.append(diagnostic); explicit_block = True
    if candidate.get("requires_cuda") is True and any(source.get("cuda_available") is False for source in (parameters,binding.parameters)):
        reasons.append("cuda_acceleration_absent");explicit_block = True
    forced_not_tested = parameters.get("status") == "not_tested" or binding.parameters.get("status") == "not_tested"
    if forced_not_tested:
        reasons.append("operator_not_tested_disposition")
    if any(not isinstance(parameters.get(key),str) or not parameters[key] for key in PRIVATE):
        reasons.append("private_evidence_locators_missing")
    facts = {}
    if not reasons:
        deadline = time.monotonic() + 30
        try:
            snapshots = []
            environment = Path(parameters.get("environment_root", "")).resolve(strict=True)
            code_root = Path(parameters.get("model_code_root", "")).resolve(strict=True)
            python = environment / "bin/python"
            for path in [*(parameters[key] for key in PRIVATE),
                         str(environment / "pyvenv.cfg"), str(environment / "environment-lock.json"),
                         str(python)]:
                remember_input(path, snapshots)
            weights_sha, weights_bytes = sha_file(parameters.get("weights_path"), deadline)
            if weights_sha != candidate["weights_sha256"]:
                raise EvidenceUnavailable("weights_identity_mismatch")
            if weights_bytes > budgets["disk"] * 1024 ** 3:
                raise EvidenceUnavailable("disk_cap_exceeded")
            verify_code(code_root, candidate["code_commit"], deadline, snapshots)
            observed_commit = candidate["code_commit"]
            if not (environment / "pyvenv.cfg").is_file():
                raise EvidenceUnavailable("dedicated_environment_unavailable")
            env_sha, _ = sha_file(str(environment / "environment-lock.json"), deadline, maximum=1024*1024)
            python_sha, _ = sha_file(str(python), deadline)
            if env_sha != candidate["environment_sha256"] or python_sha != candidate["python_sha256"]:
                raise EvidenceUnavailable("environment_identity_mismatch")
            receipt_path = parameters.get("workload_receipt_path")
            receipt_sha = parameters.get("workload_receipt_sha256")
            report = read_receipt(receipt_path, receipt_sha, deadline)
            if not isinstance(report, dict):
                raise EvidenceUnavailable("workload_receipt_shape_invalid")
            if report.get("schema") != "amps.model-workload.v1" or report.get("status") != "completed" or type(report.get("exit_code")) is not int or report["exit_code"] != 0 or report.get("candidate_id") != candidate_id:
                raise EvidenceUnavailable("workload_not_completed")
            host = dict(node=platform.node(),system=platform.system(),machine=platform.machine())
            host_sha = hashlib.sha256(json.dumps(host,sort_keys=True,separators=(",",":")).encode()).hexdigest()
            if report.get("host_fingerprint") != host_sha:
                raise EvidenceUnavailable("workload_host_mismatch")
            for key in ("weights_sha256", "environment_sha256", "python_sha256", "code_commit", "runtime_env"):
                if report.get(key) != candidate[key]:
                    raise EvidenceUnavailable("workload_input_identity_mismatch")
            observations = report.get("observations", {})
            if not isinstance(observations, dict):
                raise EvidenceUnavailable("workload_observations_shape_invalid")
            for key in ("peak_ram_gb", "peak_vram_gb", "disk_gb", "duration_seconds"):
                number(observations.get(key), key)
            observations = {key: observations[key] for key in ("peak_ram_gb", "peak_vram_gb", "disk_gb", "duration_seconds")}
            if observations["duration_seconds"] <= 0 or observations["peak_ram_gb"] <= 0:
                raise EvidenceUnavailable("workload_measurements_invalid")
            for kind,key in (("ram","peak_ram_gb"),("vram","peak_vram_gb"),("disk","disk_gb")):
                if observations[key] > budgets[kind]:
                    raise EvidenceUnavailable(f"{kind}_cap_exceeded")
            output_sha, output_bytes = sha_file(parameters.get("probe_output_path"), deadline)
            if not output_bytes or report.get("output") != {"sha256":output_sha,"bytes":output_bytes}:
                raise EvidenceUnavailable("workload_output_identity_mismatch")
            backend = candidate["runtime_env"]
            scope = report.get("evidence_scope")
            if backend not in {"pytorch", "jax_flax", "python_fixture"} or scope not in {"representative-model-workload", "synthetic-contract"}:
                raise EvidenceUnavailable("runtime_evidence_scope_invalid")
            if backend == "python_fixture" and (scope != "synthetic-contract" or not candidate["name"].startswith("synthetic-")):
                raise EvidenceUnavailable("fixture_backend_is_not_a_production_model")
            if backend != "python_fixture" and scope != "representative-model-workload":
                raise EvidenceUnavailable("production_workload_scope_required")
            probe = finite_json(run([str(python), "-I", "-c", PROBE, backend], deadline))
            if Path(probe["prefix"]).resolve() != environment or report.get("device") not in probe["devices"]:
                raise EvidenceUnavailable("runtime_device_identity_mismatch")
            if report.get("backend_version") != probe["version"]:
                raise EvidenceUnavailable("runtime_version_mismatch")
            if candidate.get("requires_cuda") is True and report.get("device") != "cuda":
                raise EvidenceUnavailable("cuda_acceleration_absent")
            verify_code(code_root, candidate["code_commit"], deadline, snapshots)
            revalidate_inputs(snapshots, deadline)
            facts = dict(weights_verified=True, code_verified=True, environment_verified=True,
                weights_sha256=weights_sha, runtime_env=backend,
                workload_evidence_verified=True, workload_receipt_sha256=receipt_sha,
                evidence_scope=scope, device=report["device"], backend_version=probe["version"],
                host_fingerprint=host_sha,
                observations=dict(observations), code_commit=observed_commit,
                environment_sha256=env_sha, python_sha256=python_sha,
                code_terms={key:candidate["code_terms"][key] for key in ("reviewed","license_id","use")},
                weight_terms={key:candidate["weight_terms"][key] for key in ("reviewed","license_id","use")},
                output_qualified=False, artistically_accepted=False, distribution_authorized=False)
            candidate = {**candidate, "max_ram_gb":observations["peak_ram_gb"],
                         "max_vram_gb":observations["peak_vram_gb"], "max_disk_gb":observations["disk_gb"]}
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
            reasons.append(str(error) if isinstance(error, EvidenceUnavailable) else "local_evidence_unavailable")
            explicit_block = True
    if reasons:
        status = "named_block" if pinned or explicit_block else "not_tested"
        if forced_not_tested or not pinned and parameters.get("prefer_not_tested") is True:
            status = "not_tested"
        return StudyResult(study_id=context.study_id, operator=binding.operator,
            span=binding.span or context.span or SourceSpan(0,3360,context.timebase), products=(),
            metadata=dict(candidate_id=candidate_id, name=candidate.get("name",candidate_id), status=status,
                          admitted=False, diagnostics=sorted(set(reasons)), weights_verified=False,
                          environment_verified=False, workload_evidence_verified=False)), None
    return candidate, facts
