"""F02 never promotes draft/history into source-bound human qualification."""
import copy
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
STUDIES = ROOT/"compositions/comp-001/studies"
SOURCE = {"sha256":"a"*64,"frame_count":300,"fps":{"numerator":30,"denominator":1}}


def fixture():
    unit = dict(id="fixture",source_sha256="a"*64,frame_span=[155,210],
        sample_span_44k1=[227850,308700],sample_span_48k=[248000,336000],
        case_type="quiet_speech",draft_transcript="draft only")
    review = dict(unit_id="fixture",case_type="quiet_speech",source_sha256="a"*64,frame_span=[155,210],
        reviewed_heard_wording=None,dispositions={axis:{"status":"pending","evidence":{}}
            for axis in ("audio","image","action","annotation")})
    benchmark = dict(schema="amps.god_here.benchmark.v1",source=copy.deepcopy(SOURCE),units=[unit])
    reviews = dict(schema="amps.god_here.units_review.v1",source=copy.deepcopy(SOURCE),units=[review])
    return benchmark,reviews


class BenchmarkEvidenceTests(unittest.TestCase):
    def audit(self, benchmark, reviews):
        from amp.studies.benchmark import audit_benchmark
        return audit_benchmark(benchmark,reviews,source=SOURCE)

    def test_committed_heard_wording_has_no_unrecorded_listening_promotion(self):
        for name in ("benchmark.json","units.review.json"):
            document=json.loads((STUDIES/name).read_text())
            for unit in document["units"]:
                with self.subTest(document=name,unit=unit.get("id",unit.get("unit_id"))):
                    self.assertIsNone(unit.get("reviewed_heard_wording"))
                    self.assertEqual(unit.get("dispositions",{}).get("audio",{}).get("status"),"pending")
            self.assertEqual(len(document.get("historical_unverified_units",[])),24)

    def test_sample_maps_share_exact_source_frame_boundaries(self):
        benchmark=json.loads((STUDIES/"benchmark.json").read_text())
        first=benchmark["units"][0]
        self.assertEqual(first["frame_span"],[155,210])
        self.assertEqual(first["sample_span_44k1"],[227850,308700])
        self.assertEqual(first["sample_span_48k"],[248000,336000])

    def test_pending_confidence_and_playback_flags_never_admit_words(self):
        benchmark,reviews=fixture()
        reviews["units"][0].update(confidence=1.0,playback_completed=True,reviewed_heard_wording="unverified claim")
        result=self.audit(benchmark,reviews)
        self.assertEqual(result["vocabulary"],[])
        self.assertEqual(result["usable_case_types"],[])
        self.assertEqual(result["missing_case_types"],["occlusion_cut","overlap","quiet_speech","semantic_exchange","simple_surface","visible_object_sound"])
        self.assertFalse(result["complete"])

    def test_words_require_independent_listened_and_annotation_evidence(self):
        benchmark,reviews=fixture();review=reviews["units"][0]
        review["reviewed_heard_wording"]="actually recorded words"
        review["dispositions"]["audio"]={"status":"verified","evidence":{
            aspect:{"method":"listened","reviewer":"fixture-human","evidence_id":"private-fixture-review"}
            for aspect in ("words","speaker","boundaries")}}
        self.assertEqual(self.audit(benchmark,reviews)["vocabulary"],[])
        review["dispositions"]["annotation"]={"status":"verified","evidence":{
            "method":"compared_to_source","reviewer":"fixture-human","evidence_id":"private-fixture-annotation"}}
        result=self.audit(benchmark,reviews)
        self.assertEqual(result["vocabulary"],[{"unit_id":"fixture","heard_wording":"actually recorded words"}])
        self.assertEqual(result["usable_case_types"],["quiet_speech"])
        self.assertEqual(result["units"][0]["dispositions"]["image"],"pending")
        self.assertFalse(result["complete"])
        for aspect in ("words","speaker","boundaries"):
            with self.subTest(missing=aspect):
                broken=copy.deepcopy(reviews)
                del broken["units"][0]["dispositions"]["audio"]["evidence"][aspect]
                with self.assertRaises(ValueError):self.audit(benchmark,broken)

    def test_stale_or_duplicate_review_cannot_qualify_other_content(self):
        benchmark,reviews=fixture()
        mutations=[lambda r:r["source"].update(sha256="b"*64),
            lambda r:r["units"][0].update(source_sha256="b"*64),
            lambda r:r["units"][0].update(frame_span=[154,210]),
            lambda r:r["units"].append(copy.deepcopy(r["units"][0])),
            lambda r:r["units"][0].update(unit_id="other")]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                broken=copy.deepcopy(reviews);mutate(broken)
                with self.assertRaises(ValueError):self.audit(benchmark,broken)

    def test_bad_maps_and_non_listened_verification_are_rejected(self):
        benchmark,reviews=fixture()
        benchmark["units"][0]["sample_span_48k"]=[248016,336000]
        with self.assertRaises(ValueError):self.audit(benchmark,reviews)
        benchmark,reviews=fixture()
        for axis in ("audio","image","action","annotation"):
            with self.subTest(axis=axis):
                broken=copy.deepcopy(reviews)
                broken["units"][0]["dispositions"][axis]={"status":"verified","evidence":{"method":"played","reviewer":"fixture","evidence_id":"flag"}}
                with self.assertRaises(ValueError):self.audit(benchmark,broken)

    def test_committed_proposals_have_zero_qualified_vocabulary_or_case_coverage(self):
        from amp.studies.benchmark import audit_benchmark
        benchmark=json.loads((STUDIES/"benchmark.json").read_text())
        reviews=json.loads((STUDIES/"units.review.json").read_text())
        registered=json.loads((STUDIES.parent/"source-registration.json").read_text())["sources"][0]
        result=audit_benchmark(benchmark,reviews,source=registered)
        self.assertEqual(len(result["units"]),24)
        self.assertEqual(result["vocabulary"],[])
        self.assertEqual(len(result["missing_case_types"]),6)
        self.assertFalse(result["complete"])

    def test_verified_audio_cannot_leave_heard_wording_unreviewed(self):
        benchmark,reviews=fixture();review=reviews["units"][0]
        review["dispositions"]["audio"]={"status":"verified","evidence":{
            aspect:{"method":"listened","reviewer":"fixture-human","evidence_id":"fixture"}
            for aspect in ("words","speaker","boundaries")}}
        with self.assertRaises(ValueError):self.audit(benchmark,reviews)

    def test_review_category_binding_cannot_be_reused_for_a_new_claim(self):
        benchmark,reviews=fixture()
        reviews["units"][0]["case_type"]="overlap"
        with self.assertRaises(ValueError):self.audit(benchmark,reviews)

    def test_spine_cannot_contradict_source_clock_or_sample_domains(self):
        benchmark,reviews=fixture()
        benchmark["spine"]={"fps":30,"total_frames":300,"native_audio_rate_hz":44100,
            "native_total_samples":441000,"derivative_audio_rate_hz":48000,"derivative_total_samples":480000}
        self.assertEqual(len(self.audit(benchmark,reviews)["units"]),1)
        for key,value in (("fps",29),("total_frames",301),("native_audio_rate_hz",48000),
                ("native_total_samples",441001),("derivative_audio_rate_hz",44100),
                ("derivative_total_samples",480001)):
            with self.subTest(field=key):
                changed=copy.deepcopy(benchmark);changed["spine"][key]=value
                with self.assertRaises(ValueError):self.audit(changed,reviews)
