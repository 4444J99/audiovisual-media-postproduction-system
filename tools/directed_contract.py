"""Canonical delivery intent shared by the proof producer and its validator."""
import copy
import hashlib
import json


def json_sha256(value):
    # Matches the native revision receipt's existing JSON identity format.
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def delivery_inputs(config):
    base = {'schema_version': '1.0', 'source_sha256': config['source_sha256'],
            'original_note': 'Let the closing disclosure register before the group resumes its word game.',
            'intent': 'Test changed reception through an extended gap, reaction emphasis, and persistent words.',
            'source_wording': 'No invented or reconstructed dialogue; inherited ASR gaps are provisional.',
            'review_status': 'candidate; owner acceptance pending',
            'segments': [{'source_start_frame': 2554, 'source_end_frame': 3215, 'output_frames': 661}],
            'fine_layers': True, 'animated_typography': True}
    gap = [{'source_start_frame': 2554, 'source_end_frame': 2955, 'output_frames': 401},
           {'source_start_frame': 2955, 'source_end_frame': 2979, 'output_frames': 42},
           {'source_start_frame': 2979, 'source_end_frame': 3215, 'output_frames': 236}]
    recipes = {'gap': copy.deepcopy(base), 'reaction': copy.deepcopy(base)}
    recipes['gap']['segments'] = gap
    recipes['reaction']['camera'] = {'start_frame': 2850, 'end_frame': 3215, 'max_zoom': 1.45}
    recipes['integrated'] = copy.deepcopy(recipes['reaction'])
    recipes['integrated']['segments'] = copy.deepcopy(gap)
    full = copy.deepcopy(recipes['integrated'])
    full['segments'] = [{'source_start_frame': 0, 'source_end_frame': 2955, 'output_frames': 2955},
                        copy.deepcopy(gap[1]),
                        {'source_start_frame': 2979, 'source_end_frame': 3360, 'output_frames': 381}]
    session = {'schema_version': '1.0', 'project': config['project'], 'score_version': config['score_version'],
               'source_sha256': config['source_sha256'], 'reduced_motion': False,
               'capture_kind': 'Authored replay fixture; not a claimed audience session',
               'events': [{'source_time': 85.133333, 'selected': 'P01', 'amount': .8},
                          {'source_time': 90, 'selected': 'P04', 'amount': .7},
                          {'source_time': 97.5, 'selected': 'P05', 'amount': .85},
                          {'source_time': 102, 'selected': None, 'amount': 0}]}
    return base, recipes, full, session


def delivery_plan(config):
    base, recipes, full, session = delivery_inputs(config)
    plan = {}
    for label, candidate, fields in [('A', 'A', False), ('B', 'B', False), ('C', 'B', True)]:
        plan[f'proof-{label}.mp4'] = {'frames': 661, 'audio': f'candidate-{candidate}.wav',
                                    'fields': fields}
    for name, recipe in recipes.items():
        plan[f'directed-{name}.mp4'] = {'frames': sum(s['output_frames'] for s in recipe['segments']),
                                      'audio': 'candidate-B.wav', 'recipe': recipe, 'session': None}
    plan['god-here-directed-passage.mp4'] = {'frames': 679, 'audio': 'expressive-mix.wav',
                                            'recipe': recipes['integrated'], 'session': None}
    plan['attention-replay.mp4'] = {'frames': 661, 'audio': 'candidate-B.wav', 'recipe': base, 'session': session}
    plan['god-here-directed-full-workprint.mp4'] = {'frames': 3378, 'audio': 'expressive-mix.wav',
                                                   'recipe': full, 'session': None}
    return plan
