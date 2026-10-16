"""Transport cancellation must win over an outstanding movie cue."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import passage_runtime


class PassageTransportTests(unittest.TestCase):
    def setUp(self):
        self.storage = {
            'pending_cue': {'index': 2550, 'play': True, 'frames': 0},
            'previous_program': 'composition',
        }
        self.movie = SimpleNamespace(
            par=SimpleNamespace(cue=True),
            isFullyPreRead=True,
            lastIndexUploaded=2550,
        )
        self.passage = SimpleNamespace(
            par=SimpleNamespace(Play=False, Time=85.0, End=107.0, Loop=False,
                                Status='Cueing source 85.000'),
            op=lambda name: self.movie if name == 'track_camera/movie_material' else None,
            fetch=lambda key, default=None: self.storage.get(key, default),
            store=lambda key, value: self.storage.__setitem__(key, value),
            unstore=lambda key: self.storage.pop(key, None),
        )
        self.workspace = SimpleNamespace(par=SimpleNamespace(Program='passage'))
        self.parent_patch = patch.object(
            passage_runtime, 'parent',
            SimpleNamespace(Passage=self.passage, Materials=self.workspace),
            create=True,
        )
        self.parent_patch.start()
        self.addCleanup(self.parent_patch.stop)

    def assert_cancelled(self):
        self.assertNotIn('pending_cue', self.storage)
        self.assertFalse(self.movie.par.cue)
        self.assertFalse(self.passage.par.Play)

    def test_pause_while_cueing_cannot_restart_on_next_frame(self):
        passage_runtime.onPulse(SimpleNamespace(name='Stop'))
        passage_runtime.tick(self.passage)
        self.assert_cancelled()
        self.assertTrue(self.passage.par.Status.startswith('Paused'))

    def test_return_while_cueing_stays_in_previous_program(self):
        passage_runtime.onPulse(SimpleNamespace(name='Return'))
        passage_runtime.tick(self.passage)
        self.assert_cancelled()
        self.assertEqual(self.workspace.par.Program, 'composition')

    def test_selecting_another_program_cancels_pending_play(self):
        self.workspace.par.Program = 'original'
        passage_runtime.tick(self.passage)
        self.assert_cancelled()
        self.assertEqual(self.workspace.par.Program, 'original')

    def test_completed_cue_still_starts_requested_passage(self):
        passage_runtime.tick(self.passage)
        self.assertNotIn('pending_cue', self.storage)
        self.assertFalse(self.movie.par.cue)
        self.assertTrue(self.passage.par.Play)
        self.assertEqual(self.passage.par.Status, 'Playing')


if __name__ == '__main__':
    unittest.main()
