import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from amp.audio import RATE
from amp.roomstretch import (build, cumulative_sum, loop_to_duration, original_gain_stacks,
                             smooth_seams, source_reel, spectral_cycle,
                             varispeed_cycle)


class RoomStretchTests(unittest.TestCase):
    def test_reel_has_exact_raw_source_samples_and_unshortened_processed_length(self):
        source = np.random.default_rng(3).normal(0, .02, (RATE, 2)).astype(np.float32)
        portions = [{"portion_id": "ONE", "start": .1, "end": .4},
                    {"portion_id": "TWO", "start": .5, "end": .9}]
        raw, processed, report = source_reel(source, portions)
        expected = np.concatenate((source[4800:19200], source[24000:43200]))
        np.testing.assert_array_equal(raw, expected)
        self.assertEqual(len(processed), round(.7 * RATE))
        self.assertEqual(report["duration_seconds"], .7)
        self.assertFalse(report["source_samples_outside_selected_portions_used"])

    def test_crossfade_reduces_join_step_without_shrinking_or_touching_other_samples(self):
        source = np.column_stack((np.r_[np.ones(100), -np.ones(100)],) * 2)
        output, joins = smooth_seams(source, [0, 100], 10)
        self.assertEqual(output.shape, source.shape)
        np.testing.assert_array_equal(output[10:90], source[10:90])
        np.testing.assert_array_equal(output[110:190], source[110:190])
        for join in joins:
            self.assertLess(join["join_step_after"], join["join_step_before"] / 10)
        np.testing.assert_array_equal(output[:, 0], output[:, 1])

    def test_varispeed_shifts_a_known_frequency_and_preserves_channel_ratio(self):
        frames = RATE // 5
        phase = np.arange(frames) / RATE
        tone = .1 * np.sin(2 * np.pi * 1000 * phase)
        source = np.column_stack((tone, tone * .5)).astype(np.float32)
        output = varispeed_cycle(source, frames * 8)
        frequencies = np.fft.rfftfreq(len(output), 1 / RATE)
        peak = frequencies[np.argmax(np.abs(np.fft.rfft(output[:, 0])))]
        self.assertAlmostEqual(peak, 125., places=8)
        np.testing.assert_array_equal(output[:, 1], output[:, 0] * .5)

    def test_84_second_loop_uses_exact_period_and_truncates_second_cycle(self):
        # Samples stand in for seconds; this verifies the same period arithmetic.
        cycle = np.column_stack((np.arange(84), np.arange(84))).astype(np.float32)
        output, loops = loop_to_duration(cycle, 112)
        np.testing.assert_array_equal(output[:84], cycle)
        np.testing.assert_array_equal(output[84:], cycle[:28])
        self.assertEqual([entry["output_start_sample"] for entry in loops], [0, 84])
        self.assertTrue(loops[-1]["truncated"])
        self.assertEqual(loops[-1]["cycle_samples_used"], 28)

    def test_spectral_stretch_keeps_frequency_range_and_mono_with_new_phases(self):
        count = RATE // 2
        tone = .1 * np.sin(2 * np.pi * 3000 * np.arange(count) / RATE)
        source = np.column_stack((tone, tone)).astype(np.float32)
        output, report = spectral_cycle(source, count * 4, seed=8, fft_size=4096)
        same, _ = spectral_cycle(source, count * 4, seed=8, fft_size=4096)
        other, _ = spectral_cycle(source, count * 4, seed=9, fft_size=4096)
        np.testing.assert_array_equal(output, same)
        np.testing.assert_array_equal(output[:, 0], output[:, 1])
        self.assertFalse(np.array_equal(output, other))
        power = np.abs(np.fft.rfft(output[:, 0])) ** 2
        bins = np.fft.rfftfreq(len(output), 1 / RATE)
        self.assertGreater(power[np.abs(bins - 3000) < 100].sum() / power.sum(), .99)
        self.assertTrue(report["phase_randomized"])
        self.assertFalse(report["source_event_waveforms_preserved"])
        self.assertFalse(report["fft_bin_frequencies_shifted"])

    def test_sum_is_reconstructible_and_rejects_different_lengths(self):
        a = np.random.default_rng(4).normal(0, .002, (1000, 2)).astype(np.float32)
        b = a * .5
        summed = cumulative_sum([a, b])
        np.testing.assert_allclose(summed, a + b, atol=1e-9)
        with self.assertRaisesRegex(ValueError, "lengths differ"):
            cumulative_sum([a, b[:-1]])

    def test_original_relative_gain_stack_reads_raw_stems_and_matches_only_the_sum(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = {"production_target_lufs": -40.37, "audition_boost_db": 14,
                      "samples_per_channel": 100, "stacks": [], "layers": [
                          {"id": "V112", "mode": "literal_varispeed", "raw_stem_wav": "raw-one.wav",
                           "raw_to_production_gain_db": -3.},
                          {"id": "V84", "mode": "literal_varispeed", "raw_stem_wav": "raw-two.wav",
                           "raw_to_production_gain_db": -5.}]}
            raw_one = np.full((100, 2), .01, np.float32)
            raw_two = np.full((100, 2), .02, np.float32)
            expected_sum = raw_one + raw_two
            with mock.patch("amp.roomstretch.load_audio", side_effect=[raw_one, raw_two]) as read, \
                    mock.patch("amp.roomstretch.match_reference", return_value=(expected_sum * .5,
                               {"gain_db": 20 * np.log10(.5)})) as match, \
                    mock.patch("amp.roomstretch._media", return_value={}):
                original_gain_stacks(root, report)
            self.assertEqual(read.call_args_list, [mock.call(root / "raw-one.wav"), mock.call(root / "raw-two.wav")])
            np.testing.assert_allclose(match.call_args.args[0], expected_sum, atol=1e-9)
            self.assertEqual(match.call_count, 1)
            stack = report["stacks"][0]
            self.assertEqual(stack["id"], "V2R")
            self.assertEqual(stack["member_input_kind"], "raw_stems")
            self.assertEqual(stack["member_gains_db"], {"V112": 0., "V84": 0.})
            self.assertEqual(stack["equivalent_production_stem_gains_db"], {"V112": 3., "V84": 5.})

    def test_invalid_seams_and_nonfinite_audio_are_rejected(self):
        audio = np.zeros((100, 2))
        for boundaries in [[0, 0], [100], [0, 5]]:
            with self.assertRaises(ValueError):
                smooth_seams(audio, boundaries, 5)
        audio[20, 0] = np.nan
        with self.assertRaisesRegex(ValueError, "non-finite"):
            varispeed_cycle(audio, 200)

    def test_wrong_source_identity_stops_before_decoding_or_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, inventory, output = root / "source.wav", root / "inventory.json", root / "out"
            source.write_bytes(b"wrong source")
            inventory.write_text(json.dumps({"source_sha256": "0" * 64}))
            with mock.patch("amp.roomstretch.load_audio") as decode:
                with self.assertRaisesRegex(ValueError, "another source"):
                    build(source, inventory, output)
                decode.assert_not_called()
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
