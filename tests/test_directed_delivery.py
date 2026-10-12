"""Delivery provenance must match the intended project, not merely itself."""
import copy
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from amp.core import sha256, write_json
from amp.revision import timing_map
from tools.directed_contract import delivery_inputs, delivery_plan, json_sha256
from tools.validate_directed import REPO_ROOT, expected_delivery_inputs, validate_outputs


class DirectedDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config, _, _ = expected_delivery_inputs()
        self.plan = delivery_plan(self.config)
        audio = self.root / 'audio'
        audio.mkdir()
        for name in ('candidate-A.wav', 'candidate-B.wav', 'expressive-mix.wav'):
            (audio / name).write_bytes(name.encode())
        self.track = {'schema_version': '1.0', 'source_sha256': self.config['source_sha256'],
                      'start_frame': 2850, 'end_frame': 3215, 'fps': 30, 'seed_roi': [.61, .30, .75, .52],
                      'method': 'fixture tracking', 'review_status': 'pending',
                      'rows': [{'source_frame': frame, 'center': [.68, .41], 'accepted': True}
                               for frame in range(2850, 3215)]}
        write_json(self.root / 'reaction.track.json', self.track)
        _, recipes, full, session = delivery_inputs(self.config)
        for name, recipe in recipes.items():
            write_json(self.root / f'{name}.recipe.json', recipe)
        write_json(self.root / 'full-edition.recipe.json', full)
        write_json(self.root / 'attention-demo.json', session)
        for name, spec in self.plan.items():
            path = self.root / name
            path.write_bytes(name.encode())
            receipt = {'output_sha256': sha256(path), 'source_sha256': self.config['source_sha256'],
                       'audio_sha256': sha256(audio / spec['audio']),
                       'composition_sha256': json_sha256(self.config), 'frames': spec['frames'], 'fps': 30,
                       'core_code_sha256': sha256(REPO_ROOT / 'amp/core.py')}
            if 'recipe' not in spec:
                receipt.update({'render_code_sha256': sha256(REPO_ROOT / 'amp/render.py'),
                                'source_start_frame': 2554, 'source_end_frame_exclusive': 3215,
                                'duration_seconds': 661 / 30, 'fields': spec['fields'],
                                'boundary_mode': 'hard', 'fine_layers': False, 'expressive_typography': False})
            else:
                recipe, session = spec['recipe'], spec['session']
                tracked = bool(recipe.get('camera'))
                receipt.update({'recipe': recipe, 'recipe_sha256': json_sha256(recipe), 'session': session,
                                'session_sha256': json_sha256(session) if session else None,
                                'track_sha256': json_sha256(self.track) if tracked else None,
                                'tracking': {'method': self.track['method'], 'review_status': self.track['review_status']} if tracked else None,
                                'time_map': timing_map(recipe, 30),
                                'revision_code_sha256': sha256(REPO_ROOT / 'amp/revision.py'),
                                'direction_code_sha256': sha256(REPO_ROOT / 'amp/direction.py')})
            write_json(self.receipt_path(name), receipt)

    def receipt_path(self, name):
        return (self.root / name).with_suffix('.render.json' if name.startswith('proof-') else '.revision.json')

    def edit_receipt(self, name, updates):
        path = self.receipt_path(name)
        data = json.loads(path.read_text())
        data.update(updates)
        write_json(path, data)

    def validate(self, *, error=None):
        def media_info(path):
            frames = self.plan[Path(path).name]['frames']
            return {'streams': [{'codec_type': 'video', 'nb_frames': str(frames),
                                 'width': 1280, 'height': 720, 'duration': str(frames / 30)}]}
        with ExitStack() as stack:
            cache = stack.enter_context(patch('tools.build_directed_proof.verify_audio_cache'))
            probe = stack.enter_context(patch('tools.validate_directed.probe', side_effect=media_info))
            stack.enter_context(patch('tools.validate_directed.run'))
            stack.enter_context(patch('tools.validate_directed.load_audio', return_value=np.zeros((4, 2))))
            stack.enter_context(patch('tools.validate_directed.measure', return_value={'input_tp': -2, 'input_i': -20}))
            stack.enter_context(patch('tools.validate_directed.subprocess.check_output', return_value='ffmpeg fixture\n'))
            if error:
                with self.assertRaisesRegex(ValueError, error):
                    validate_outputs(self.root)
                probe.assert_not_called()
                return
            record = validate_outputs(self.root)
            config, transcript, samples = expected_delivery_inputs()
            cache.assert_called_once_with(self.root / 'audio', config, transcript, config['source_sha256'], samples)
            self.assertEqual(probe.call_count, 9)
            return record

    def test_complete_bound_delivery_validates_registered_source(self):
        record = self.validate()
        self.assertEqual(record['source_sha256'], self.config['source_sha256'])
        self.assertEqual(len(record['outputs']), 9)
        self.assertTrue(record['delivery_input_binding'].startswith('passed'))

    def test_self_consistent_other_source_film_and_receipt_are_rejected(self):
        name = 'proof-A.mp4'
        (self.root / name).write_bytes(b'a different film with a matching output digest')
        self.edit_receipt(name, {'output_sha256': sha256(self.root / name), 'source_sha256': '0' * 64})
        self.validate(error='incompatible source_sha256')

    def test_wrong_audio_candidate_is_rejected(self):
        self.edit_receipt('proof-A.mp4', {'audio_sha256': sha256(self.root / 'audio/candidate-B.wav')})
        self.validate(error='incompatible audio_sha256')

    def test_wrong_recipe_with_matching_hash_is_rejected(self):
        wrong = copy.deepcopy(self.plan['directed-gap.mp4']['recipe'])
        wrong['animated_typography'] = False
        self.edit_receipt('directed-gap.mp4', {'recipe': wrong, 'recipe_sha256': json_sha256(wrong)})
        self.validate(error='incompatible recipe')

    def test_substituting_adjacent_recipe_cannot_change_expected_delivery(self):
        wrong = copy.deepcopy(self.plan['directed-gap.mp4']['recipe'])
        wrong['animated_typography'] = False
        write_json(self.root / 'gap.recipe.json', wrong)
        self.edit_receipt('directed-gap.mp4', {'recipe': wrong, 'recipe_sha256': json_sha256(wrong)})
        self.validate(error='expected recipe/session')

    def test_wrong_session_with_matching_hash_is_rejected(self):
        wrong = copy.deepcopy(self.plan['attention-replay.mp4']['session'])
        wrong['events'][0]['amount'] = .1
        self.edit_receipt('attention-replay.mp4', {'session': wrong, 'session_sha256': json_sha256(wrong)})
        self.validate(error='incompatible session')

    def test_changed_tracking_input_is_rejected(self):
        self.track['rows'][0]['center'] = [.2, .8]
        write_json(self.root / 'reaction.track.json', self.track)
        self.validate(error='incompatible track_sha256')

    def test_stale_producing_code_and_composition_are_rejected(self):
        cases = [('proof-C.mp4', 'render_code_sha256'), ('proof-C.mp4', 'core_code_sha256'),
                 ('directed-gap.mp4', 'revision_code_sha256'), ('directed-gap.mp4', 'direction_code_sha256'),
                 ('attention-replay.mp4', 'composition_sha256')]
        for name, key in cases:
            with self.subTest(name=name, key=key):
                path = self.receipt_path(name)
                original = path.read_text()
                self.edit_receipt(name, {key: '0' * 64})
                self.validate(error=f'incompatible {key}')
                path.write_text(original)


if __name__ == '__main__':
    unittest.main()
