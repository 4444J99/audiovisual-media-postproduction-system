"""Exercise the native callback's recovery boundary without native operators."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import fx_audio
import scene_fx_model


class FxAudioRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.position = 36750
        self.calls = []
        test = self

        class Stream:
            @property
            def position(self):
                return test.position

            def process(self, kind, audio, params):
                test.calls.append(audio.copy())
                test.position += audio.shape[1]
                return audio*2

        self.record = {'stream': Stream(), 'frame': None, 'recovery_audio_boundary': True}
        self.owner = SimpleNamespace(id=17, par=SimpleNamespace(
            Active=True, Bypass=False, Wet=.5, Type='delay', Intensity=1),
            fetch=lambda key: {'params': [], 'macro': []})
        self.movie = SimpleNamespace(trueIndex=637.5)
        event = {'start_frame': 613, 'end_frame': 800, 'speed': 1, 'output_start': 0}
        controller = SimpleNamespace(op=lambda path: self.movie,
                                     fetch=lambda key: {'score': {'events': [event]}, 'index': 0})
        helpers = {'text_runtime': SimpleNamespace(module=SimpleNamespace(controller=lambda scene: controller)),
                   'text_fx_model': SimpleNamespace(module=scene_fx_model)}
        scene = SimpleNamespace(op=lambda name: helpers[name])
        self.rack = SimpleNamespace(par=SimpleNamespace(Ownedtransport=True, Play=True),
                                    parent=lambda: scene, op=lambda name: None)
        self.source = SimpleNamespace(start=12345, numpyArray=lambda: self.audio)
        self.output = SimpleNamespace(inputs=[self.source], clear=lambda: None,
                                      copyNumpyArray=self.copy)
        self.audio = np.arange(2*5145, dtype=np.float32).reshape(2, 5145)/20000
        self.addCleanup(patch.stopall)
        patch.object(fx_audio, 'STATES', {17: self.record}).start()
        patch.object(fx_audio, 'CORE', SimpleNamespace()).start()
        patch.object(fx_audio, 'parent', SimpleNamespace(Fx=self.owner, Fxrack=self.rack), create=True).start()
        patch.object(fx_audio, 'root', SimpleNamespace(time=SimpleNamespace(rate=60)), create=True).start()
        self.time = SimpleNamespace(frame=100)
        patch.object(fx_audio, 'absTime', self.time, create=True).start()

    def copy(self, data):
        self.result = data.copy()
        self.output.start = 0  # Native copyNumpyArray resets this metadata.

    def test_duplicate_phase_holds_dsp_then_normal_slice_resumes(self):
        fx_audio.onCook(self.output)
        self.assertEqual(self.position, 36750)
        self.assertFalse(self.calls)
        self.assertEqual(np.count_nonzero(self.result), 0)
        self.assertEqual(self.output.start, self.source.start)
        self.movie.trueIndex = 638
        self.time.frame += 1
        self.audio = self.audio[:, -735:]
        fx_audio.onCook(self.output)
        np.testing.assert_array_equal(self.result, self.audio*1.5)
        self.assertEqual(self.position, 37485)
        self.assertNotIn('recovery_audio_boundary', self.record)

    def test_restore_gap_is_silent_and_only_fresh_suffix_enters_dsp(self):
        self.position = 36015
        fx_audio.onCook(self.output)
        self.assertEqual(len(self.calls), 1)
        np.testing.assert_array_equal(self.calls[0], self.audio[:, -735:])
        self.assertEqual(np.count_nonzero(self.result[:, :-735]), 0)
        np.testing.assert_array_equal(self.result[:, -735:], self.audio[:, -735:]*1.5)
        self.assertEqual(self.position, 36750)

    def test_ordinary_audio_retains_entire_native_slice(self):
        self.record.pop('recovery_audio_boundary')
        fx_audio.onCook(self.output)
        np.testing.assert_array_equal(self.calls[0], self.audio)
        np.testing.assert_array_equal(self.result, self.audio*1.5)
        self.assertEqual(self.position, 36750+5145)

    def test_paused_recovery_does_not_advance_or_discard_boundary(self):
        self.rack.par.Ownedtransport = False
        fx_audio.onCook(self.output)
        self.assertFalse(self.calls)
        self.assertEqual(self.position, 36750)
        self.assertTrue(self.record['recovery_audio_boundary'])


if __name__ == '__main__':
    unittest.main()
