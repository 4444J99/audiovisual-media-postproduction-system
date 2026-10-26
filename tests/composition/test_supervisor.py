import copy
import json
import unittest

from amp.composition.novelty import canonical_identity
from amp.composition.supervisor import PerformanceBlocked, PerformanceSupervisor, plan_performance
from tests.composition.fixtures import corpus, profile


def performance(seed=1, duration=600):
    return plan_performance(corpus(), profile(), seed=seed, duration_frames=duration,
                            record_id="synthetic-performance")


class PerformancePlannerTests(unittest.TestCase):
    def test_three_distinct_graphs_with_varied_returns_reuse_and_two_way_coupling(self):
        records = [performance(seed) for seed in (1, 2, 3)]
        self.assertEqual(len({canonical_identity(record) for record in records}), 3)
        runtime = records[0].to_dict()["runtime"]
        self.assertGreater(len({e["end_frame"] - e["start_frame"] for e in runtime["events"]}), 3)
        self.assertTrue(any("reused_from" in e for e in runtime["events"]))
        leaves = [e for e in runtime["events"] if e["kind"] == "material"]
        self.assertEqual({e["scale"] for e in leaves}, {"scene", "phrase", "shot"})
        pair = leaves[:2]
        self.assertEqual(pair[0]["couplings"][0]["source_event_id"], pair[1]["id"])
        self.assertEqual(pair[1]["couplings"][0]["source_event_id"], pair[0]["id"])
        self.assertTrue(all(edge["lag_frames"] >= 1 for e in leaves for edge in e["couplings"]))

    def test_seed_reproduces_complete_decisions_without_claiming_actual_runtime(self):
        first = performance().to_dict()
        self.assertEqual(first, performance().to_dict())
        self.assertEqual(first["runtime"]["initial_state"], {"frame": 0, "playing": False})
        self.assertFalse(first["runtime"]["profile"]["admitted"])
        json.dumps(first, allow_nan=False)

    def test_malformed_and_unqualified_corpus_is_rejected(self):
        for mutation in (
            lambda c: c["materials"][0]["metadata"]["qualification"].update(technical="pending"),
            lambda c: c.update(reference={"material_id": "missing", "clock": {}}),
            lambda c: c["materials"].append(copy.deepcopy(c["materials"][0])),
            lambda c: c["materials"][0]["metadata"].update(audio_sample_rate=None),
        ):
            changed = corpus()
            mutation(changed)
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                plan_performance(changed, profile(), seed=1, duration_frames=600, record_id="test")


class PerformanceSupervisorTests(unittest.TestCase):
    def test_pending_horizon_and_active_resource_counts_are_bounded(self):
        supervisor = PerformanceSupervisor(performance(), simulation=True)
        supervisor.resume()
        for frame in range(0, 600, 7):
            state = supervisor.advance(frame)
            self.assertLessEqual(state["audio_voices"], 24)
            self.assertLessEqual(state["visual_instances"], 12)
            self.assertLessEqual(len(state["pending"]), 256)
            self.assertTrue(all(frame < e["start_frame"] <= frame + 300 for e in state["pending"]))
            self.assertIsNotNone(state["reference"])
            self.assertEqual({e["scale"] for e in state["active"]}, {"scene", "phrase", "shot"})
        self.assertEqual(supervisor.advance(600)["status"], "finished")

    def test_checkpoint_restores_graph_clock_and_explicit_play_intent(self):
        supervisor = PerformanceSupervisor(performance(), simulation=True)
        supervisor.resume()
        before = supervisor.advance(117)
        saved = supervisor.checkpoint()
        restored = PerformanceSupervisor.restore(saved, simulation=True)
        self.assertEqual(restored.snapshot()["frame"], 117)
        self.assertFalse(restored.snapshot()["playing"])
        self.assertTrue(restored.snapshot()["resume_intent"])
        restored.resume()
        after = restored.advance(117)
        self.assertEqual(before["active"], after["active"])
        self.assertEqual(canonical_identity(saved["record"]), canonical_identity(restored.record))

    def test_pause_seek_and_cancel_do_not_restart_or_reorder_events(self):
        supervisor = PerformanceSupervisor(performance(), simulation=True)
        supervisor.resume()
        supervisor.advance(150)
        supervisor.pause()
        self.assertEqual(supervisor.advance(200)["frame"], 150)
        supervisor.seek(30)
        self.assertFalse(supervisor.snapshot()["playing"])
        supervisor.resume()
        self.assertEqual(supervisor.advance(31)["frame"], 31)
        with self.assertRaises(ValueError):
            supervisor.advance(20)
        supervisor.cancel()
        self.assertEqual(supervisor.snapshot()["status"], "cancelled")
        self.assertEqual(supervisor.snapshot()["active"], [])
        with self.assertRaises(ValueError):
            supervisor.resume()

    def test_each_count_limit_degrades_explicitly_to_prepared_fallback(self):
        for key in ("audio_voices", "visual_instances", "pending_events"):
            saved = performance().to_dict()
            saved["runtime"]["profile"][key] = 1
            with self.subTest(key=key):
                supervisor = PerformanceSupervisor(saved, simulation=True)
                supervisor.resume()
                state = supervisor.advance(0)
                self.assertEqual(state["status"], "degraded")
                self.assertIn(key, state["degradation_reasons"])
                self.assertEqual(state["fallback_material_id"], "clip")
                self.assertEqual(state["pending"], [])
                self.assertIsNotNone(state["reference"])

    def test_playback_admission_requires_real_profile_and_measured_byte_counts(self):
        supervisor = PerformanceSupervisor(performance())
        with self.assertRaises(PerformanceBlocked):
            supervisor.resume()
        saved = performance().to_dict()
        saved["runtime"]["profile"].update(admitted=True, byte_caps={
            "decoded_audio_bytes": 1000, "texture_bytes": 1000, "event_history_bytes": 1000000,
        })
        supervisor = PerformanceSupervisor(saved)
        with self.assertRaises(PerformanceBlocked):
            supervisor.admit({})
        supervisor.admit({"decoded_audio_bytes": 800, "texture_bytes": 800,
                          "event_history_bytes": 500000})
        supervisor.resume()
        supervisor.observe_resources({"decoded_audio_bytes": 1001, "texture_bytes": 800,
                                      "event_history_bytes": 500000})
        state = supervisor.advance(1)
        self.assertEqual(state["status"], "degraded")
        self.assertIn("decoded_audio_bytes", state["degradation_reasons"])

    def test_tampered_checkpoint_and_invalid_clocks_are_rejected(self):
        supervisor = PerformanceSupervisor(performance(), simulation=True)
        saved = supervisor.checkpoint()
        saved["state"]["frame"] = 33
        with self.assertRaises(ValueError):
            PerformanceSupervisor.restore(saved, simulation=True)
        for frame in (-1, 1.5, True, 601):
            with self.subTest(frame=frame), self.assertRaises(ValueError):
                supervisor.seek(frame)

    def test_resume_and_seek_never_expose_over_capacity_scheduling(self):
        saved = performance().to_dict()
        saved["runtime"]["profile"]["audio_voices"] = 1
        supervisor = PerformanceSupervisor(saved, simulation=True)
        self.assertEqual(supervisor.resume()["status"], "degraded")
        self.assertLessEqual(supervisor.seek(100)["audio_voices"], 1)

    def test_terminal_cancel_and_end_cannot_be_resurrected_by_late_observations(self):
        supervisor = PerformanceSupervisor(performance(), simulation=True)
        supervisor.resume()
        supervisor.cancel()
        supervisor.observe_resources({})
        self.assertEqual(supervisor.snapshot()["status"], "cancelled")
        with self.assertRaises(ValueError):
            supervisor.recover({"decoded_audio_bytes": 0, "texture_bytes": 0, "event_history_bytes": 0})
        with self.assertRaises(ValueError):
            supervisor.resume()
        another = PerformanceSupervisor(performance(), simulation=True)
        another.resume()
        end = another.seek(600)
        self.assertFalse(end["playing"])
        self.assertEqual(end["audio_voices"], 0)

    def test_simulation_checkpoint_cannot_be_promoted_to_actual_playback_evidence(self):
        supervisor = PerformanceSupervisor(performance(), simulation=True)
        supervisor.resume()
        supervisor.advance(30)
        saved = supervisor.checkpoint()
        self.assertEqual(saved["observation_mode"], "simulation")
        self.assertEqual(saved["record"]["runtime"]["execution"]["observation_mode"], "simulation")
        with self.assertRaises(PerformanceBlocked):
            PerformanceSupervisor.restore(saved)

    def test_renaming_reused_event_labels_does_not_create_a_new_composition(self):
        original = performance().to_dict()
        renamed = copy.deepcopy(original)
        aliases = {e["id"]: "renamed-" + str(i) for i, e in enumerate(renamed["runtime"]["events"])}
        for event in renamed["runtime"]["events"]:
            event["id"] = aliases[event["id"]]
            if event["parent_id"] is not None:
                event["parent_id"] = aliases[event["parent_id"]]
            if "reused_from" in event:
                event["reused_from"] = aliases[event["reused_from"]]
            for edge in event.get("couplings", []):
                edge["source_event_id"] = aliases[edge["source_event_id"]]
        self.assertEqual(canonical_identity(original), canonical_identity(renamed))

    def test_invalid_native_audio_and_reuse_bindings_are_rejected(self):
        original = performance().to_dict()
        leaf_index = next(i for i, e in enumerate(original["runtime"]["events"]) if e["kind"] == "material")
        for mutation in (
            lambda e: e["audio_clock"].update(start_sample=10**12),
            lambda e: e["audio_clock"].update(sample_rate=48000),
            lambda e: e.update(reused_from="nonexistent"),
            lambda e: e["couplings"][0].update(source_event_id="edition"),
        ):
            saved = copy.deepcopy(original)
            mutation(saved["runtime"]["events"][leaf_index])
            with self.subTest(mutation=mutation.__code__.co_firstlineno), self.assertRaises(ValueError):
                PerformanceSupervisor(saved, simulation=True)

    def test_delayed_two_way_controls_are_saved_and_replayed_without_new_decisions(self):
        supervisor = PerformanceSupervisor(performance(), simulation=True)
        before = supervisor.resume()
        values = {event["id"]: 0.8 if event["picture"] else 0.4 for event in before["active"]}
        supervisor.observe_controls(0, values)
        after = supervisor.advance(1)
        self.assertTrue(all(event["effective_gain"] > event["gain"] for event in after["active"]))
        saved = supervisor.checkpoint()
        self.assertEqual(saved["record"]["runtime"]["execution"]["control_samples"][0]["values"], values)
        replay = PerformanceSupervisor.restore(saved, simulation=True)
        replay.resume()
        self.assertEqual(replay.advance(1)["active"], after["active"])
        changed = dict(values)
        changed[next(iter(changed))] = 0.9
        with self.assertRaises(ValueError):
            supervisor.observe_controls(0, changed)

    def test_recovery_does_not_late_start_events_suppressed_by_pressure(self):
        saved = performance().to_dict()
        saved["runtime"]["profile"].update(admitted=True, byte_caps={
            "decoded_audio_bytes": 1000, "texture_bytes": 1000, "event_history_bytes": 1000000,
        })
        supervisor = PerformanceSupervisor(saved)
        measurements = {"decoded_audio_bytes": 800, "texture_bytes": 800, "event_history_bytes": 500000}
        supervisor.admit(measurements)
        original = supervisor.resume()["active"]
        supervisor.observe_resources({**measurements, "texture_bytes": 1001})
        supervisor.advance(5)
        supervisor.recover(measurements)
        recovered = supervisor.advance(6)
        self.assertFalse({e["id"] for e in original} & {e["id"] for e in recovered["active"]})
        self.assertIsNotNone(recovered["reference"])

    def test_missing_or_nonfinite_controls_are_not_relabelled_as_measurements(self):
        supervisor = PerformanceSupervisor(performance(), simulation=True)
        before = supervisor.resume()
        self.assertTrue(all(e["coupling_observations"][0]["state"] == "initial" for e in before["active"]))
        values = {event["id"]: 0.5 for event in before["active"]}
        for bad in ({}, {**values, next(iter(values)): float("nan")}, {"unknown": 0.1}):
            with self.subTest(keys=list(bad)), self.assertRaises(ValueError):
                supervisor.observe_controls(0, bad)

    def test_replay_reproduces_saved_pressure_windows_and_their_recovery(self):
        saved = performance().to_dict()
        saved["runtime"]["profile"].update(admitted=True, byte_caps={
            "decoded_audio_bytes": 1000, "texture_bytes": 1000, "event_history_bytes": 1000000,
        })
        supervisor = PerformanceSupervisor(saved, simulation=True)
        supervisor.resume()
        good = {"decoded_audio_bytes": 100, "texture_bytes": 100, "event_history_bytes": 1000}
        supervisor.observe_resources({**good, "texture_bytes": 1001})
        supervisor.advance(5)
        supervisor.recover(good)
        expected = supervisor.advance(6)
        replay = PerformanceSupervisor(supervisor.checkpoint()["record"], simulation=True)
        self.assertEqual(replay.resume()["status"], "degraded")
        self.assertEqual(replay.advance(4)["fallback_material_id"], "clip")
        self.assertEqual(replay.advance(6)["active"], expected["active"])
        self.assertNotEqual(replay.snapshot()["status"], "degraded")

    def test_execution_history_shapes_are_checked_before_recovery(self):
        supervisor = PerformanceSupervisor(performance(), simulation=True)
        supervisor.resume()
        supervisor.observe_controls(0, {e["id"]: 0.5 for e in supervisor.snapshot()["active"]})
        original = supervisor.checkpoint()["record"]
        for mutate in (
            lambda r: r["runtime"]["execution"]["control_samples"][0].update(frame=-1),
            lambda r: r["runtime"]["execution"]["control_samples"][0].update(values={"unknown": 0.5}),
            lambda r: r["runtime"]["execution"].update(degradation_windows=[{"start_frame": 5, "end_frame": 1, "reasons": []}]),
            lambda r: r["runtime"]["execution"].update(observation_mode="unverified"),
        ):
            changed = copy.deepcopy(original)
            mutate(changed)
            with self.subTest(case=mutate.__code__.co_firstlineno), self.assertRaises(ValueError):
                PerformanceSupervisor(changed, simulation=True)


if __name__ == "__main__":
    unittest.main()
