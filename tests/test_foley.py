"""Foley provenance and timeline checks, not a claim of listening quality."""
import unittest

import numpy as np

from amp.foley import RATE, synth_event, validate_score


class FoleyTest(unittest.TestCase):
    def event(self):
        return {"id":"F001","start":1.25,"end":1.65,"kind":"glass_set","bus":"glass","pan":-.3,
                "peak_dbfs":-35,"sound_origin":"procedural_authored_addition",
                "visual_evidence":"Cup meets table in source frame review","timing_confidence":"medium"}

    def test_invalid_recovery_claim_is_rejected(self):
        e=self.event();e["sound_origin"]="recovered"
        with self.assertRaises(ValueError):
            validate_score({"sample_rate":RATE,"duration_seconds":4,"events":[e]})

    def test_seed_repeats_recipe_but_distinct_event_varies(self):
        e=self.event()
        a=synth_event(e,100);b=synth_event(e,100);c=synth_event(e,101)
        self.assertTrue(np.array_equal(a,b));self.assertFalse(np.array_equal(a,c))
        self.assertEqual(a.shape,(round(.4*RATE),2))
        self.assertLess(np.max(np.abs(a)),.03)

    def test_out_of_range_event_is_rejected(self):
        e=self.event();e["end"]=5
        with self.assertRaises(ValueError):
            validate_score({"sample_rate":RATE,"duration_seconds":4,"events":[e]})

    def test_all_categories_have_finite_edges(self):
        for kind in ["cloth","chair","glass_handle","glass_set","sip","stove"]:
            e=self.event();e["kind"]=kind
            x=synth_event(e,124)
            self.assertTrue(np.isfinite(x).all(),kind)
            self.assertLess(np.max(np.abs(x[-1])),1e-5,kind)


if __name__=="__main__":
    unittest.main()
