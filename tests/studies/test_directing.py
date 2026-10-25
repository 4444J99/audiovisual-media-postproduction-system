"""Tests for Wing 9 Preference-Guided Directing (Issues #105-108) & Semantic Cycle (Issues #101-104)."""
import unittest

from amp.studies.directing import (
    compile_directing_question,
    evaluate_directing_choice,
    evaluate_preference_ranker_readiness,
    record_semantic_observation_cycle,
    run_three_round_directing_experiment,
)


class DirectingStudiesTests(unittest.TestCase):
    def setUp(self):
        self.question_spec = {
            "question_id": "dir-q-closing-01",
            "intent_note": "Hold closing exchange 2 seconds longer, pan to cup then face, animate OUT/HOW/WHAT graphics",
            "target_spans": [[2554, 3215]],
            "entities": ["cup", "face", "ensemble"],
            "parameters": {
                "duration_factor": [1.0, 1.4],
                "framing_scale": [1.0, 2.5],
            },
            "candidate_recipes": [
                {"candidate_id": "recipe-A", "description": "Candidate A reference timing", "parameters": {"duration_factor": 1.0}},
                {"candidate_id": "recipe-B", "description": "Candidate B moderate stretch", "parameters": {"duration_factor": 1.2}},
                {"candidate_id": "recipe-C", "description": "Candidate C full stretch", "parameters": {"duration_factor": 1.4}},
            ],
            "acceptance_criteria": ["intelligible_speech", "lip_sync_preserved"],
        }
        self.constraints = {
            "preserve_source_truth": True,
            "max_retiming_ratio": 1.5,
        }

    def test_compile_directing_question_valid(self):
        compiled = compile_directing_question(self.question_spec, self.constraints)
        self.assertEqual(compiled["schema"], "amps.directing.question.v1")
        self.assertEqual(compiled["question_id"], "dir-q-closing-01")
        self.assertEqual(len(compiled["candidates"]), 3)
        self.assertEqual(compiled["status"], "compiled")
        self.assertEqual(len(compiled["question_digest"]), 64)

    def test_compile_directing_question_rejects_command_injection(self):
        bad_spec = dict(self.question_spec)
        bad_spec["intent_note"] = "rm -rf /; echo hack"
        with self.assertRaises(ValueError):
            compile_directing_question(bad_spec, self.constraints)

    def test_compile_directing_question_validation_errors(self):
        with self.assertRaises(ValueError):
            compile_directing_question({}, self.constraints)
        with self.assertRaises(ValueError):
            compile_directing_question({"question_id": "q1"}, self.constraints)

    def test_evaluate_directing_choice_honest_selection(self):
        candidates = self.question_spec["candidate_recipes"]
        decision = {
            "decision_type": "choice",
            "reviewer_id": "dir-reviewer-01",
            "rationale": "Candidate B has ideal balance between dialogue pacing and lingering gaze",
            "selected_id": "recipe-B",
        }
        outcome = evaluate_directing_choice(candidates, decision)
        self.assertEqual(outcome["schema"], "amps.directing.evaluation.v1")
        self.assertEqual(outcome["decision_type"], "choice")
        self.assertEqual(outcome["selected_id"], "recipe-B")
        self.assertEqual(outcome["retained_ids"], ["recipe-B"])
        self.assertFalse(outcome["forced_winner"])

    def test_evaluate_directing_choice_tie_dual_retention(self):
        candidates = self.question_spec["candidate_recipes"]
        decision = {
            "decision_type": "tie",
            "reviewer_id": "dir-reviewer-01",
            "rationale": "Both Candidate B and C deliver viable artistic interpretations; retain both for moving-footage review",
            "retained_ids": ["recipe-B", "recipe-C"],
        }
        outcome = evaluate_directing_choice(candidates, decision)
        self.assertEqual(outcome["decision_type"], "tie")
        self.assertIsNone(outcome["selected_id"])
        self.assertEqual(outcome["retained_ids"], ["recipe-B", "recipe-C"])
        self.assertFalse(outcome["forced_winner"])

    def test_evaluate_directing_choice_rejection_without_forcing(self):
        candidates = self.question_spec["candidate_recipes"]
        decision = {
            "decision_type": "rejection",
            "reviewer_id": "dir-reviewer-01",
            "rationale": "All candidates introduce excessive dialogue stretch artifacts; reject all and request re-render",
        }
        outcome = evaluate_directing_choice(candidates, decision)
        self.assertEqual(outcome["decision_type"], "rejection")
        self.assertIsNone(outcome["selected_id"])
        self.assertEqual(outcome["retained_ids"], [])
        self.assertFalse(outcome["forced_winner"])

    def test_evaluate_directing_choice_rejects_forced_winner_on_rejection(self):
        candidates = self.question_spec["candidate_recipes"]
        decision = {
            "decision_type": "rejection",
            "reviewer_id": "dir-reviewer-01",
            "rationale": "Rejecting all candidates",
            "selected_id": "recipe-A",  # Illegal: forcing a winner when rejecting
        }
        with self.assertRaises(ValueError):
            evaluate_directing_choice(candidates, decision)

    def test_run_three_round_directing_experiment(self):
        decisions = [
            {
                "decision_type": "choice",
                "reviewer_id": "reviewer-1",
                "rationale": "Round 1 prefers midpoint",
                "selected_id": "round-1-cand-B",
            },
            {
                "decision_type": "choice",
                "reviewer_id": "reviewer-1",
                "rationale": "Round 2 prefers upper refined bracket",
                "selected_id": "round-2-cand-C",
            },
            {
                "decision_type": "choice",
                "reviewer_id": "reviewer-1",
                "rationale": "Round 3 settles on optimal fine parameter",
                "selected_id": "round-3-cand-B",
            },
        ]
        exp = run_three_round_directing_experiment(self.question_spec, decisions)
        self.assertEqual(exp["schema"], "amps.directing.experiment.v1")
        self.assertEqual(len(exp["rounds"]), 3)
        self.assertEqual(exp["final_outcome"]["status"], "converged")
        self.assertEqual(len(exp["final_outcome"]["provenance_chain"]), 3)
        self.assertIn("duration_factor", exp["final_parameters"])

    def test_run_three_round_directing_experiment_requires_three_rounds(self):
        with self.assertRaises(ValueError):
            run_three_round_directing_experiment(self.question_spec, [{"decision_type": "choice"}])

    def test_evaluate_preference_ranker_readiness_gated_below_12(self):
        # 5 feedback records (< 12)
        records = [
            {"predicted_score": 0.8, "human_score": 0.9}
            for _ in range(5)
        ]
        res = evaluate_preference_ranker_readiness(records, min_decisions=12)
        self.assertEqual(res["schema"], "amps.directing.ranker_readiness.v1")
        self.assertFalse(res["ready"])
        self.assertEqual(res["named_block"], "insufficient_feedback")
        self.assertIsNone(res["kendall_tau"])
        self.assertEqual(res["records_count"], 5)

    def test_evaluate_preference_ranker_readiness_sufficient_above_12(self):
        # 14 feedback records (>= 12)
        records = [
            {"predicted_score": float(i) / 14.0, "human_score": float(i) / 14.0 + 0.05}
            for i in range(14)
        ]
        res = evaluate_preference_ranker_readiness(records, min_decisions=12)
        self.assertTrue(res["ready"])
        self.assertIsNone(res["named_block"])
        self.assertEqual(res["records_count"], 14)
        self.assertIsNotNone(res["kendall_tau"])
        self.assertGreaterEqual(res["kendall_tau"], 0.9)  # Highly concordant

    def test_record_semantic_observation_cycle_offline_cache(self):
        unit_id = "unit-phrase-2880-3000"
        render_spec = {"frames": [2880, 3000], "stems": ["dialogue", "room_tone"]}
        desc = "performer pauses at table holding cup before turning gaze toward window"
        query = "pause holding cup gaze window"

        # Pass 1: Cold cache -> cache_hit False, updates cache
        pass1 = record_semantic_observation_cycle(unit_id, render_spec, desc, query, replay_cache=None)
        self.assertEqual(pass1["schema"], "amps.directing.semantic_cycle.v1")
        self.assertFalse(pass1["cache_hit"])
        self.assertIn("semantic_vector", pass1["retrieval_result"])
        cache = pass1["replay_cache"]
        self.assertGreater(len(cache), 0)

        # Pass 2: Warm cache -> cache_hit True, reuses vector without new inference
        pass2 = record_semantic_observation_cycle(unit_id, render_spec, desc, query, replay_cache=cache)
        self.assertTrue(pass2["cache_hit"])
        self.assertEqual(pass1["retrieval_result"], pass2["retrieval_result"])


if __name__ == "__main__":
    unittest.main()
