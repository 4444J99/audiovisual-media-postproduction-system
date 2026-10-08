import copy
import json
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from amp.core import composite, generate_schedule, shot_at, validate

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "projects/god-here/composition.json").read_text())


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.fromarray(np.random.default_rng(4).integers(0, 256, (90, 160, 3), dtype=np.uint8))
        self.history = [self.image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)] * 20 + [self.image]

    def test_neutral_is_source_exact(self):
        for t in [10, 40, 90, 98]:
            out = composite(self.image, self.history, CONFIG, t, overrides=dict.fromkeys(CONFIG["performers"], 0))
            self.assertTrue(np.array_equal(out, self.image))

    def test_single_effect_cannot_change_neighbor_or_shared_room(self):
        for t in [10, 40]:
            shot = shot_at(CONFIG, t)
            fields = CONFIG["layouts"][shot["layout"]]["fields"]
            for field in fields:
                values = dict.fromkeys(CONFIG["performers"], 0)
                values[field["performer"]] = .8
                out = np.asarray(composite(self.image, self.history, CONFIG, t, overrides=values))
                a, b = [round(x * 160) for x in field["span"]]
                self.assertTrue(np.array_equal(out[:, :a], np.asarray(self.image)[:, :a]))
                self.assertTrue(np.array_equal(out[:, b:], np.asarray(self.image)[:, b:]))
                self.assertFalse(np.array_equal(out[:, a:b], np.asarray(self.image)[:, a:b]))

    def test_unregistered_or_unknown_shot_falls_back(self):
        cfg = copy.deepcopy(CONFIG)
        cfg["layouts"]["B"]["registered"] = False
        self.assertTrue(np.array_equal(composite(self.image, self.history, cfg, 40), self.image))
        self.assertTrue(np.array_equal(composite(self.image, self.history, cfg, 3), self.image))
        cfg["shots"][1]["layout"] = "unavailable"
        self.assertTrue(np.array_equal(composite(self.image, self.history, cfg, 40), self.image))

    def test_cut_retains_identity_with_different_position(self):
        a = CONFIG["layouts"]["A"]["fields"]
        b = CONFIG["layouts"]["B"]["fields"]
        self.assertEqual({f["performer"] for f in a}, {f["performer"] for f in b})
        self.assertNotEqual(a[0]["performer"], b[0]["performer"])
        self.assertEqual(shot_at(CONFIG, 95)["id"], "SHOT-06")

    def test_invalid_geometry_rejected(self):
        cfg = copy.deepcopy(CONFIG)
        cfg["layouts"]["A"]["fields"][1]["span"][0] = .01
        with self.assertRaises(ValueError):
            validate(cfg)

    def test_seeded_generation_is_reproducible_and_bounded(self):
        units = json.loads((ROOT / "projects/god-here/units.json").read_text())["units"]
        first = generate_schedule(units, 17)
        self.assertEqual(first, generate_schedule(units, 17))
        self.assertNotEqual(first, generate_schedule(units, 29))
        by_id = {u["id"]: u for u in units}
        for a, b in zip(first["events"], first["events"][1:]):
            self.assertIn(b["unit"], by_id[a["unit"]]["allowed_next"])
            self.assertEqual(a["output_end"], b["output_start"])


if __name__ == "__main__":
    unittest.main()
