"""Admission facts must bind actual bytes and a measured run, not availability flags."""
import copy
import hashlib
import json
import math
import os
import platform
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import venv
from unittest.mock import patch

import amp.studies.admission_evidence as ev

from amp.composition.containers import MaterialRef, StudyBinding, StudyContext
from amp.studies.admission import admit_model, load_models_lock

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "compositions/comp-001/studies/models.lock.json"


class AdmissionEvidenceTests(unittest.TestCase):
    def binding(self, **parameters):
        return StudyBinding(operator="amp.roomstretch.v1", materials=(MaterialRef(
            id="source", sha256="a" * 64, kind="audio"),), parameters={"candidate_id": "R01", **parameters})

    def context(self, **parameters):
        return StudyContext(study_id="admission-fixture", composition_id="comp-001", parameters=parameters)

    def test_unknown_host_and_availability_flags_cannot_admit_proposals(self):
        for flags in ({}, {"weights_available": True, "runtime_env_available": True, "cuda_available": True},
                      {"host_ram_gb": 64, "host_vram_gb": 32, "host_disk_gb": 100}):
            result = admit_model(self.binding(), self.context(**flags), LOCK)
            self.assertFalse(result.metadata["admitted"])
            self.assertEqual(result.metadata["status"], "not_tested")

    def test_source_candidate_inventory_is_preserved_as_unpinned(self):
        lock = load_models_lock(LOCK)
        expected = {"R01": "SAM Audio", "R02": "Layered Neural Atlases", "R03": "CoDeF",
                    "R04": "VideoPrism", "R05": "Temporal Cycle-Consistency",
                    "R06": "Learning-based Video Motion Magnification", "R07": "CoTracker",
                    "R08": "Light-A-Video", "R09": "Omnimatte", "R10": "Visual Acoustic Matching / AViTAR",
                    "R11": "Self-Supervised Visual Acoustic Matching", "R12": "Qwen3-VL-4B-Instruct"}
        self.assertEqual({key: value["name"] for key, value in lock["candidates"].items()}, expected)
        self.assertTrue(all(value["status"] == "not_tested" and value["weights_sha256"] is None
                            for value in lock["candidates"].values()))
        self.assertEqual(len(lock["historical_unverified_candidates"]), 12)

    def test_invalid_or_conflicting_limits_are_not_treated_as_an_unlimited_host(self):
        for value in (True, "64", math.nan, math.inf, -1, 10**1000):
            with self.subTest(value=value), self.assertRaises(ValueError):
                admit_model(self.binding(), self.context(host_ram_gb=value), LOCK)
        with self.assertRaises(ValueError):
            admit_model(self.binding(), self.context(candidate_id="R02"), LOCK)

    def test_cloud_and_download_rules_cannot_be_overridden_or_coerced(self):
        for value in (True, "0", math.nan):
            with self.assertRaises(ValueError):
                admit_model(self.binding(cloud_spend_usd=value), self.context(), LOCK)

    def test_completed_synthetic_workload_verifies_bytes_and_caps_without_claiming_a_real_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            code = root / "code"; code.mkdir()
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=code, text=True).strip()
            git("init", "-q"); git("config", "user.email", "fixture@example.invalid");git("config", "user.name", "Fixture")
            (code / "model.py").write_text("from pathlib import Path\nimport sys\nPath(sys.argv[2]).write_bytes(Path(sys.argv[1]).read_bytes()[::-1])\n")
            git("add", "model.py");git("commit", "-qm", "synthetic fixture")
            revision = git("rev-parse", "HEAD")
            weights = root / "weights.bin";weights.write_bytes(b"synthetic-fixture-weights")
            environment = root / "environment";venv.EnvBuilder(with_pip=False).create(environment)
            python = environment / "bin/python"
            env_lock = environment / "environment-lock.json";env_lock.write_text(json.dumps({"python": sys.version, "backend": "python_fixture"}))
            output = root / "output.bin"
            started = time.monotonic()
            pid = os.posix_spawn(str(python), [str(python), "-I", str(code / "model.py"), str(weights), str(output)], os.environ)
            _, wait_status, usage = os.wait4(pid, 0)
            self.assertEqual(os.waitstatus_to_exitcode(wait_status), 0)
            duration = time.monotonic() - started
            ram = usage.ru_maxrss * (1 if sys.platform == "darwin" else 1024) / 1024**3
            sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
            candidate = dict(candidate_id="R01", name="synthetic-verifier-contract", wing="fixture",
                status="pinned", weights_sha256=sha(weights), code_commit=revision, environment_sha256=sha(env_lock),
                python_sha256=sha(python.resolve()), runtime_env="python_fixture", cloud_spend_usd=0, auto_download=False,
                code_terms={"reviewed":True,"license_id":"CC0-1.0","use":"test"},
                weight_terms={"reviewed":True,"license_id":"CC0-1.0","use":"test"})
            report = dict(schema="amps.model-workload.v1", candidate_id="R01", status="completed", exit_code=0,
                code_commit=revision, weights_sha256=sha(weights), environment_sha256=sha(env_lock),
                python_sha256=sha(python.resolve()), runtime_env="python_fixture", device="cpu",
                backend_version=sys.version.split()[0],
                host_fingerprint=hashlib.sha256(json.dumps(dict(node=platform.node(),system=platform.system(),machine=platform.machine()),sort_keys=True,separators=(",",":")).encode()).hexdigest(),
                evidence_scope="synthetic-contract", output={"sha256":sha(output),"bytes":output.stat().st_size},
                observations={"peak_ram_gb":ram,"peak_vram_gb":0,"disk_gb":sum(p.lstat().st_size for p in root.rglob("*") if p.is_file())/1024**3,"duration_seconds":duration})
            evidence = root / "workload.json";evidence.write_text(json.dumps(report))
            lock = root / "models.lock.json";lock.write_text(json.dumps({"candidates":{"R01":candidate}}))
            params = dict(host_ram_gb=1,host_vram_gb=0,host_disk_gb=1,weights_path=str(weights),
                model_code_root=str(code),environment_root=str(environment),workload_receipt_path=str(evidence),
                workload_receipt_sha256=sha(evidence),probe_output_path=str(output),intended_use="test")
            result = admit_model(self.binding(), self.context(**params), lock)
            self.assertTrue(result.metadata["admitted"])
            self.assertTrue(result.metadata["weights_verified"])
            self.assertEqual(result.metadata["evidence_scope"], "synthetic-contract")
            self.assertNotIn(str(root), json.dumps(result.to_dict()))
            self.check_review_counterexamples(code, git, weights, environment, output, evidence, lock, candidate, report, params)
            for mutation in (lambda: weights.write_bytes(b"changed"), lambda: output.write_bytes(b"changed"),
                             lambda: (code / "model.py").write_text("changed source")):
                before = {p: p.read_bytes() for p in (weights,output,code / "model.py")}
                mutation()
                denied = admit_model(self.binding(), self.context(**params), lock)
                self.assertFalse(denied.metadata["admitted"])
                self.assertNotIn(str(root), json.dumps(denied.to_dict()))
                for p,data in before.items():p.write_bytes(data)
            for key in ("host_ram_gb","host_vram_gb","host_disk_gb"):
                missing = {k:v for k,v in params.items() if k!=key}
                self.assertFalse(admit_model(self.binding(),self.context(**missing),lock).metadata["admitted"])
            zero = {**params,"host_ram_gb":0}
            self.assertFalse(admit_model(self.binding(),self.context(**zero),lock).metadata["admitted"])
            explicit_zero = {**params,"max_ram_gb":0}
            self.assertFalse(admit_model(self.binding(),self.context(**explicit_zero),lock).metadata["admitted"])
            for field,value in (("host_fingerprint","0"*64),("backend_version","wrong-version")):
                changed = {**report,field:value};evidence.write_text(json.dumps(changed))
                changed_params = {**params,"workload_receipt_sha256":sha(evidence)}
                self.assertFalse(admit_model(self.binding(),self.context(**changed_params),lock).metadata["admitted"])
            evidence.write_text(json.dumps(report))

    def check_review_counterexamples(self, code, git, weights, environment, output, evidence, lock, candidate, report, params):
        sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        def admit():
            return admit_model(self.binding(), self.context(**{**params, "workload_receipt_sha256":sha(evidence)}), lock)
        with self.subTest(review="catalogue identity"):
            lock.write_text(json.dumps({"candidates":{"R01":{**candidate,"candidate_id":"R99"}}}))
            try:
                with self.assertRaises(ValueError):
                    admit()
            finally:
                lock.write_text(json.dumps({"candidates":{"R01":candidate}}))
        for shape in ([], {**report,"observations":None}):
            with self.subTest(review="receipt mapping", shape=type(shape).__name__):
                evidence.write_text(json.dumps(shape))
                try:
                    try:
                        denied = admit()
                    except Exception as error:
                        self.fail(f"malformed receipt escaped blocked-result contract: {type(error).__name__}")
                    self.assertFalse(denied.metadata["admitted"])
                finally:
                    evidence.write_text(json.dumps(report))
        original_run = ev.run
        with self.subTest(review="path replacement with identical bytes"):
            original = weights.read_bytes(); replaced = False
            def replace_path(argv, deadline):
                nonlocal replaced
                result = original_run(argv, deadline)
                if not replaced and argv[-1] == "python_fixture":
                    temporary = weights.with_suffix(".replacement")
                    temporary.write_bytes(original)
                    temporary.replace(weights)
                    replaced = True
                return result
            with patch.object(ev,"run",side_effect=replace_path):
                self.assertFalse(admit().metadata["admitted"])
            self.assertTrue(replaced)
        with self.subTest(review="production scope"):
            lock.write_text(json.dumps({"candidates":{"R01":{**candidate,"runtime_env":"pytorch","name":"production-candidate"}}}))
            evidence.write_text(json.dumps({**report,"runtime_env":"pytorch"}))
            def available_backend(argv, deadline):
                if argv[-1] == "pytorch":
                    return json.dumps(dict(prefix=str(environment),version=report["backend_version"],devices=["cpu"]))
                return original_run(argv,deadline)
            try:
                with patch.object(ev,"run",side_effect=available_backend):
                    self.assertFalse(admit().metadata["admitted"])
            finally:
                lock.write_text(json.dumps({"candidates":{"R01":candidate}}))
                evidence.write_text(json.dumps(report))
        with self.subTest(review="replacement Git objects are not the pinned tree"):
            model = code/"model.py"; revision = git("rev-parse","HEAD")
            model.write_text("replacement implementation")
            git("add","model.py");git("commit","-qm","replacement tree")
            replacement = git("rev-parse","HEAD")
            git("reset","--hard",revision)
            git("replace",revision,replacement)
            model.write_text("replacement implementation")
            git("add","model.py")
            try:
                self.assertFalse(admit().metadata["admitted"])
            finally:
                git("replace","-d",revision)
                git("reset","--hard",revision)
        for flag in ("assume-unchanged", "skip-worktree"):
            with self.subTest(review="hidden tracked bytes", flag=flag):
                model = code / "model.py"; previous = model.read_bytes()
                git("update-index",f"--{flag}","model.py")
                model.write_bytes(b"changed tracked source")
                try:
                    self.assertFalse(admit().metadata["admitted"])
                finally:
                    model.write_bytes(previous)
                    git("update-index",f"--no-{flag}","model.py")
        targets = [weights, environment/"environment-lock.json", environment/"pyvenv.cfg", evidence, output, code/"model.py"]
        for target in targets:
            for moment in ("first-git", "after-probe"):
                with self.subTest(review="verification interleaving", target=target.name, moment=moment):
                    previous = target.read_bytes(); changed = False
                    def interleave(argv, deadline):
                        nonlocal changed
                        result = original_run(argv,deadline)
                        if not changed and ((moment=="first-git" and argv[0]=="git") or (moment=="after-probe" and argv[-1]=="python_fixture")):
                            target.write_bytes(previous+b"changed")
                            changed = True
                        return result
                    try:
                        with patch.object(ev,"run",side_effect=interleave):
                            denied = admit()
                        self.assertTrue(changed)
                        self.assertFalse(denied.metadata["admitted"])
                    finally:
                        target.write_bytes(previous)
