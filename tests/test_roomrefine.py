import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from amp.audio import RATE
from amp.core import sha256
from amp.roomrack import split_bands
from amp.roomrefine import (build, inventory_portions, match_reference, rms,
                            shared_layers, spectral_profiles, spectral_texture)


class RoomRefinementTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(82)
        mono = rng.normal(0, .004, RATE * 2)
        self.audio = np.column_stack((mono, mono)).astype(np.float32)
        self.portions = [
            {"portion_id": "PAUSE001-01", "start": .1, "end": .5},
            {"portion_id": "PAUSE002-01", "start": .8, "end": 1.5},
        ]

    def test_shared_schedule_stays_identical_despite_band_energy_differences(self):
        bands = split_bands(self.audio)
        bands["high"] *= 37
        dry, wet, report = shared_layers(bands, self.portions, duration=3)
        timing = lambda name: [{k: v for k, v in e.items() if k != "gain"}
                               for e in report[name]["edit_map"]]
        self.assertEqual(timing("low"), timing("mid"))
        self.assertEqual(timing("mid"), timing("high"))
        self.assertFalse(np.array_equal(dry["mid"], wet["mid"]))
        self.assertEqual(dry["low"].shape, (3 * RATE, 2))

    def test_synthesis_is_deterministic_and_does_not_invent_stereo_width(self):
        frequencies, profiles = spectral_profiles(self.audio, self.portions)
        a, report = spectral_texture(frequencies, profiles, RATE * 2, seed=31, mode="sustain")
        b, _ = spectral_texture(frequencies, profiles, RATE * 2, seed=31, mode="sustain")
        other, _ = spectral_texture(frequencies, profiles, RATE * 2, seed=32, mode="sustain")
        np.testing.assert_array_equal(a, b)
        np.testing.assert_array_equal(a[:, 0], a[:, 1])
        self.assertFalse(np.array_equal(a, other))
        self.assertFalse(report["source_pcm_replayed"])
        self.assertFalse(report["source_event_envelope_retained"])
        self.assertAlmostEqual(rms(a), 1, places=6)

    def test_equal_power_profiles_remove_source_fragment_amplitude_differences(self):
        louder = self.audio.copy()
        louder[int(.8 * RATE):int(1.5 * RATE)] *= 20
        _, plain = spectral_profiles(self.audio, self.portions)
        _, modified = spectral_profiles(louder, self.portions)
        np.testing.assert_allclose(plain, modified, rtol=2e-4, atol=1e-8)

    def test_sustain_morphs_spectral_color_while_static_does_not(self):
        frequencies = np.linspace(0, RATE / 2, 4097)
        low = np.exp(-.5 * ((frequencies - 700) / 100) ** 2)
        high = np.exp(-.5 * ((frequencies - 7000) / 300) ** 2)
        profiles = np.array([[low, low * 0], [high, high * 0]])
        moving, _ = spectral_texture(frequencies, profiles, RATE * 8, seed=4, mode="sustain")
        static, _ = spectral_texture(frequencies, profiles, RATE * 8, seed=4, mode="static")
        def centroid(piece):
            power = np.abs(np.fft.rfft(piece[:, 0])) ** 2
            bins = np.fft.rfftfreq(len(piece), 1 / RATE)
            return float(np.sum(power * bins) / power.sum())
        first, last = slice(RATE, RATE * 2), slice(RATE * 6, RATE * 7)
        self.assertGreater(centroid(moving[last]) - centroid(moving[first]), 3500)
        self.assertLess(abs(centroid(static[last]) - centroid(static[first])), 500)

    def test_loudness_match_uses_one_fixed_gain_and_reports_rms_separately(self):
        before = {"rms_dbfs": -42., "bs1770_integrated_lufs": -39.}
        after = {"rms_dbfs": -45., "bs1770_integrated_lufs": -42.}
        with mock.patch("amp.roomrefine.measurements", side_effect=[before, after]):
            output, report = match_reference(self.audio, {"rms_dbfs": -43., "bs1770_integrated_lufs": -42.})
        np.testing.assert_allclose(output, self.audio * 10 ** (-3 / 20), rtol=1e-6)
        self.assertEqual(report["gain_db"], -3)
        self.assertEqual(report["after"]["rms_dbfs"], -45)
        self.assertFalse(report["dynamic_normalization"])

    def test_source_hash_mismatch_stops_before_decoding_or_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, inventory, out = root / "source.wav", root / "inventory.json", root / "result"
            source.write_bytes(b"not decoded when identity is wrong")
            inventory.write_text(json.dumps({"source_sha256": "0" * 64}))
            with mock.patch("amp.roomrefine.load_audio") as decode:
                with self.assertRaisesRegex(ValueError, "another source"):
                    build(source, inventory, out)
                decode.assert_not_called()
            self.assertFalse(out.exists())
            self.assertNotEqual(sha256(source), "0" * 64)

    def test_invalid_or_empty_portions_are_rejected(self):
        inventory = {"sample_rate": RATE, "channels": 2, "pauses": []}
        with self.assertRaisesRegex(ValueError, "No screened"):
            inventory_portions(inventory, RATE * 2)
        inventory["pauses"] = [{"id": "PAUSE001", "usable_portions": [{"start": .1, "end": .111}]}]
        with self.assertRaises(ValueError):
            inventory_portions(inventory, RATE * 2)
        inventory["pauses"][0]["usable_portions"] = [{"start": .101, "end": .5}]
        with self.assertRaisesRegex(ValueError, "10 ms"):
            inventory_portions(inventory, RATE * 2)


if __name__ == "__main__":
    unittest.main()
