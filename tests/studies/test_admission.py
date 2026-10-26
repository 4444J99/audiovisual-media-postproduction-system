"""Tests for model admission and resource pinning (Issue #67, F04)."""
import unittest
from pathlib import Path

from amp.composition.containers import MaterialRef, SourceSpan, StudyBinding, StudyContext, Timebase
from amp.studies.admission import admit_model, load_models_lock


class ModelAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.lock_path = Path(__file__).resolve().parents[2] / "compositions/comp-001/studies/models.lock.json"
        self.timebase = Timebase(30, 1)
        self.span = SourceSpan(start=0, end=90, timebase=self.timebase)
        self.mat = MaterialRef(
            id="src-01",
            sha256="b" * 64,
            kind="audio",
        )

    def test_load_models_lock_all_12_candidates(self):
        lock = load_models_lock(self.lock_path)
        candidates = lock["candidates"]
        self.assertEqual(len(candidates), 12)
        for i in range(1, 13):
            cid = f"R{i:02d}"
            self.assertIn(cid, candidates)
            cand = candidates[cid]
            self.assertEqual(cand["cloud_spend_usd"], 0.0)
            self.assertFalse(cand["auto_download"])
            self.assertIsNone(cand["weights_sha256"])
            self.assertEqual(cand["status"], "not_tested")

    def test_host_budget_alone_does_not_provision_any_candidate(self):
        for i in range(1, 13):
            cid = f"R{i:02d}"
            binding = StudyBinding(
                operator="amp.roomstretch.v1",
                materials=(self.mat,),
                parameters={"candidate_id": cid},
                span=self.span,
            )
            ctx = StudyContext(
                study_id=f"study-admit-{cid}",
                composition_id="comp-001",
                parameters={"host_ram_gb": 64.0, "host_vram_gb": 32.0, "host_disk_gb": 100.0},
            )
            result = admit_model(binding, ctx, lock_path=self.lock_path)
            self.assertEqual(result.metadata["status"], "not_tested")
            self.assertFalse(result.metadata["admitted"])
            self.assertEqual(result.metadata["candidate_id"], cid)

    def test_partial_ram_budget_keeps_unpinned_proposal_not_tested(self):
        binding = StudyBinding(
            operator="amp.roomstretch.v1",
            materials=(self.mat,),
            parameters={"candidate_id": "R09"},
        )
        ctx = StudyContext(
            study_id="study-cap-ram",
            composition_id="comp-001",
            parameters={"max_ram_gb": 16.0},
        )
        result = admit_model(binding, ctx, lock_path=self.lock_path)
        self.assertEqual(result.metadata["status"], "not_tested")
        self.assertFalse(result.metadata["admitted"])
        self.assertIn("host_vram_cap_missing", result.metadata["diagnostics"])

    def test_partial_vram_budget_keeps_unpinned_proposal_not_tested(self):
        binding = StudyBinding(
            operator="amp.roomstretch.v1",
            materials=(self.mat,),
            parameters={"candidate_id": "R05"},
        )
        ctx = StudyContext(
            study_id="study-cap-vram",
            composition_id="comp-001",
            parameters={"max_vram_gb": 8.0},
        )
        result = admit_model(binding, ctx, lock_path=self.lock_path)
        self.assertEqual(result.metadata["status"], "not_tested")
        self.assertFalse(result.metadata["admitted"])
        self.assertIn("host_ram_cap_missing", result.metadata["diagnostics"])

    def test_missing_local_weights_handling(self):
        binding = StudyBinding(
            operator="amp.roomstretch.v1",
            materials=(self.mat,),
            parameters={"candidate_id": "R01"},
        )
        # Context indicates weights are absent
        ctx_blocked = StudyContext(
            study_id="study-weights-missing",
            composition_id="comp-001",
            parameters={"weights_available": False},
        )
        res_blocked = admit_model(binding, ctx_blocked, lock_path=self.lock_path)
        self.assertEqual(res_blocked.metadata["status"], "named_block")
        self.assertIn("local_weights_absent", res_blocked.metadata["diagnostics"])

        # Status explicitly requested as not_tested
        ctx_not_tested = StudyContext(
            study_id="study-not-tested",
            composition_id="comp-001",
            parameters={"weights_available": False, "prefer_not_tested": True},
        )
        res_not_tested = admit_model(binding, ctx_not_tested, lock_path=self.lock_path)
        self.assertEqual(res_not_tested.metadata["status"], "not_tested")

    def test_missing_cuda_handling(self):
        binding = StudyBinding(
            operator="amp.roomstretch.v1",
            materials=(self.mat,),
            parameters={"candidate_id": "R03"},
        )
        ctx_no_cuda = StudyContext(
            study_id="study-no-cuda",
            composition_id="comp-001",
            parameters={"cuda_available": False},
        )
        res = admit_model(binding, ctx_no_cuda, lock_path=self.lock_path)
        self.assertEqual(res.metadata["status"], "named_block")
        self.assertIn("cuda_acceleration_absent", res.metadata["diagnostics"])

    def test_forbidden_cloud_spend_rejection(self):
        binding = StudyBinding(
            operator="amp.roomstretch.v1",
            materials=(self.mat,),
            parameters={"candidate_id": "R01", "cloud_spend_usd": 5.0},
        )
        ctx = StudyContext(study_id="study-cloud-forbidden", composition_id="comp-001")
        with self.assertRaises(ValueError) as cm:
            admit_model(binding, ctx, lock_path=self.lock_path)
        self.assertIn("Cloud spend forbidden", str(cm.exception))

    def test_forbidden_auto_download_rejection(self):
        binding = StudyBinding(
            operator="amp.roomstretch.v1",
            materials=(self.mat,),
            parameters={"candidate_id": "R01", "auto_download": True},
        )
        ctx = StudyContext(study_id="study-auto-dl-forbidden", composition_id="comp-001")
        with self.assertRaises(ValueError) as cm:
            admit_model(binding, ctx, lock_path=self.lock_path)
        self.assertIn("Forbidden auto-download", str(cm.exception))

    def test_unknown_candidate_rejection(self):
        binding = StudyBinding(
            operator="amp.roomstretch.v1",
            materials=(self.mat,),
            parameters={"candidate_id": "R99_UNKNOWN"},
        )
        ctx = StudyContext(study_id="study-unknown-cand", composition_id="comp-001")
        with self.assertRaises(ValueError) as cm:
            admit_model(binding, ctx, lock_path=self.lock_path)
        self.assertIn("Unknown or unpinned model candidate", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
