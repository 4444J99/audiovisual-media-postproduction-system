"""Tests for Wing 5 Object Insertion, Removal & Counterfactuals framework (Issues #86-89, W05)."""
import unittest

from amp.studies.counterfactuals import (
    audit_counterfactual_seam_integrity,
    insert_diegetic_object,
    register_counterfactual_branch,
    remove_transient_distractor,
)


class CounterfactualsStudiesTests(unittest.TestCase):
    def setUp(self):
        self.shot_id = "SHOT-CF-01"
        self.background_plate = {
            "plate_id": "PLATE-01",
            "body_span": {"start":100,"end":200,"timebase":{"num":30,"den":1},"source_sha256":"a"*64,"clock_kind":"video_frame"},
            "target_body": "stage_background",
            "on_screen": True,
            "temporal_continuity": 0.95,
        }

    def test_remove_transient_distractor_valid(self):
        # Mask [120, 150) inside body [100, 200)
        mask={**self.background_plate['body_span'],'start':120,'end':150}
        self.background_plate['mask_clock_operation']={'operator':'mask.independent-clock.v1','reason':'Authored mask subspan','mask_span':mask,'body_span':self.background_plate['body_span']}
        res = remove_transient_distractor(self.shot_id,mask,self.background_plate)
        self.assertEqual(res["schema"], "amps.god_here.distractor_removal.v1")
        self.assertEqual(res['frames_requested'],30)
        self.assertIsNone(res["frames_inpainted"])
        self.assertIsNone(res["seam_verified"])
        self.assertFalse(res['execution_performed'])

    def test_remove_transient_distractor_coupling_violation(self):
        # Mask starts before body span (90 < 100)
        with self.assertRaises(ValueError) as cm:
            remove_transient_distractor(self.shot_id, (90, 150), self.background_plate)
        self.assertIn("Mask-to-body coupling violation", str(cm.exception))

    def test_insert_diegetic_object_valid_and_out_of_bounds(self):
        obj_spec = {
            "object_id": "OBJ-MIC-STAND-01",
            "position_m": [0.5, -0.8, 2.2],
        }
        depth_layer = {"name": "midground", "z_min": 1.5, "z_max": 3.5}
        light_rig = {"lights": [{"intensity": 1.0}]}

        res = insert_diegetic_object(self.shot_id, obj_spec, depth_layer, light_rig)
        self.assertEqual(res["schema"], "amps.god_here.diegetic_insertion.v1")
        self.assertTrue(res["contact_shadow_consistency"])

        # Object at z=5.0m outside layer [1.5, 3.5]
        bad_obj = {"object_id": "OBJ-BAD", "position_m": [0.0, 0.0, 5.0]}
        with self.assertRaises(ValueError) as cm:
            insert_diegetic_object(self.shot_id, bad_obj, depth_layer, light_rig)
        self.assertIn("falls outside depth layer", str(cm.exception))

    def test_audit_counterfactual_seam_integrity(self):
        orig = [{"frame": i} for i in range(5)]
        passing_edits = [{"boundary_gradient_diff": 0.015, "temporal_edge_stability": 0.96} for _ in range(5)]
        boundary = {"width": 1920, "height": 1080}

        report_pass = audit_counterfactual_seam_integrity(orig, passing_edits, boundary)
        self.assertTrue(report_pass["passed"])
        self.assertLessEqual(report_pass["seam_artifact_score"], 0.05)

        # High seam artifact score (> 0.05)
        failing_edits = [{"boundary_gradient_diff": 0.09, "temporal_edge_stability": 0.85} for _ in range(5)]
        report_fail = audit_counterfactual_seam_integrity(orig, failing_edits, boundary)
        self.assertFalse(report_fail["passed"])

    def test_register_counterfactual_branch(self):
        edit_rec = {
            "edit_type": "distractor_removal",
            "source_id": "SRC-002",
            "parameters": {"tool": "inpainting_r10"},
        }
        branch = register_counterfactual_branch("BM-01", edit_rec)
        self.assertEqual(branch["schema"], "amps.god_here.counterfactual_branch.v1")
        self.assertTrue(branch["is_counterfactual"])
        self.assertTrue(branch["preserves_truthful_lineage"])
        self.assertEqual(branch["parent_unit_id"], "BM-01")
        self.assertIn("CF-BRANCH-", branch["branch_id"])


if __name__ == "__main__":
    unittest.main()
