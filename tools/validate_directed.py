"""Validate finalized directed films without rerendering or accepting artwork."""
import json
import math
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from amp.audio import RATE, load_audio, measure
from amp.core import probe,run,sha256,write_json
from amp.revision import timing_map, validate_camera_track
from tools.directed_contract import delivery_inputs, delivery_plan, json_sha256

REPO_ROOT = Path(__file__).resolve().parents[1]


def expected_delivery_inputs():
    """Use registered project inputs, never a delivery's self-reported source."""
    project = REPO_ROOT / 'projects/god-here'
    config = json.loads((project / 'composition.json').read_text())
    transcript = json.loads((project / 'transcript.provisional.json').read_text())
    source_audio = json.loads((project / 'audio-report.json').read_text())
    samples = {item['samples'] for item in source_audio['candidates'].values()}
    if source_audio['source_sha256'] != config['source_sha256'] or len(samples) != 1:
        raise ValueError('Registered source audio identity is inconsistent')
    return config, transcript, samples.pop()


def require_identity(data, key, expected, name):
    if key not in data or data[key] != expected:
        raise ValueError(f'Delivery {name} has incompatible {key}')


def validate_receipt(data, name, spec, config, audio, track):
    """Bind output receipts to the intended delivery, including native code."""
    common = {'source_sha256': config['source_sha256'], 'audio_sha256': sha256(audio / spec['audio']),
              'composition_sha256': json_sha256(config), 'frames': spec['frames'], 'fps': config['fps'],
              'core_code_sha256': sha256(REPO_ROOT / 'amp/core.py')}
    if 'recipe' not in spec:
        common.update({'render_code_sha256': sha256(REPO_ROOT / 'amp/render.py'),
                       'source_start_frame': 2554, 'source_end_frame_exclusive': 3215,
                       'duration_seconds': spec['frames'] / config['fps'], 'fields': spec['fields'],
                       'boundary_mode': 'hard', 'fine_layers': False, 'expressive_typography': False})
    else:
        recipe, session = spec['recipe'], spec['session']
        expected_track = track if recipe.get('camera') else None
        common.update({'recipe': recipe, 'recipe_sha256': json_sha256(recipe), 'session': session,
                       'session_sha256': json_sha256(session) if session is not None else None,
                       'track_sha256': json_sha256(expected_track) if expected_track is not None else None,
                       'tracking': {'method': track['method'], 'review_status': track['review_status']} if expected_track else None,
                       'time_map': timing_map(recipe, config['fps']),
                       'revision_code_sha256': sha256(REPO_ROOT / 'amp/revision.py'),
                       'direction_code_sha256': sha256(REPO_ROOT / 'amp/direction.py')})
    for key, expected in common.items():
        require_identity(data, key, expected, name)


def validate_audio_clock(info, wave, frames, fps, name):
    """Allow an AAC padding block, but never missing source-clock samples."""
    streams = [stream for stream in info.get('streams', []) if stream.get('codec_type') == 'audio']
    if len(streams) != 1:
        raise ValueError(f'Delivery must contain exactly one audio stream: {name}')
    stream = streams[0]
    if (stream.get('codec_name') != 'aac' or int(stream.get('sample_rate', 0)) != RATE
            or stream.get('channels') != 2):
        raise ValueError(f'Incorrect delivered audio encoding/clock: {name}')
    expected = round(frames / fps * RATE)
    # AAC-LC uses 1024-sample blocks. MP4 edit metadata normally trims the
    # endpoint, while the decoded final block can retain encoder padding.
    padding = 1024
    # The MP4 edit-list clock can round an endpoint to milliseconds even when
    # all expected decoded samples are present (the retained excerpts do so).
    endpoint_rounding = 1 / 1000
    if wave.ndim != 2 or wave.shape[1] != 2 or not expected <= len(wave) <= expected + padding:
        raise ValueError(f'Incorrect delivered audio sample count: {name}')
    try:
        start = float(stream['start_time'])
        duration = float(stream['duration'])
    except (KeyError, TypeError, ValueError):
        raise ValueError(f'Missing or invalid delivered audio endpoint: {name}') from None
    endpoint = start + duration
    seconds = frames / fps
    if (not all(math.isfinite(value) for value in (start, duration, endpoint))
            or abs(start) > 1 / RATE or endpoint < seconds - endpoint_rounding
            or endpoint > seconds + padding / RATE):
        raise ValueError(f'Incorrect delivered audio endpoint: {name}')
    return {'expected_samples': expected, 'decoded_samples': len(wave), 'sample_rate': RATE,
            'start_seconds': start, 'end_seconds': endpoint, 'expected_end_seconds': seconds,
            'maximum_codec_padding_samples': padding, 'endpoint_rounding_tolerance_seconds': endpoint_rounding,
            'missing_tail_samples': 0, 'passed': True}


def validate_outputs(root):
    root=Path(root)
    config, transcript, source_samples = expected_delivery_inputs()
    expected = delivery_plan(config)
    receipts = {}
    # Reject absent or swapped outputs before expensive media/cache decoding.
    for name in expected:
        path=root/name
        suffix='.render.json' if name.startswith('proof-') else '.revision.json'
        receipt=path.with_suffix(suffix)
        if not receipt.is_file():
            raise ValueError(f'Missing render receipt: {name}')
        data=json.loads(receipt.read_text())
        digest=sha256(path)
        if data.get('output_sha256')!=digest:
            raise ValueError(f'Delivery changed after render receipt: {name}')
        receipts[name] = data
    from tools.build_directed_proof import verify_audio_cache
    verify_audio_cache(root / 'audio', config, transcript, config['source_sha256'], source_samples)
    _, recipes, full, session = delivery_inputs(config)
    for filename, value in [(f'{name}.recipe.json', recipe) for name, recipe in recipes.items()] + [
            ('full-edition.recipe.json', full), ('attention-demo.json', session)]:
        if json.loads((root / filename).read_text()) != value:
            raise ValueError(f'Delivery input differs from the expected recipe/session: {filename}')
    track=json.loads((root/'reaction.track.json').read_text())
    validate_camera_track(track, recipes['reaction']['camera'], config, 3360)
    if track['start_frame'] != 2850 or track['end_frame'] != 3215 or track.get('seed_roi') != [.61,.30,.75,.52]:
        raise ValueError('Delivery tracking differs from the expected source interval/target')
    for name, spec in expected.items():
        validate_receipt(receipts[name], name, spec, config, root / 'audio', track)
    rows=[]
    for name,spec in expected.items():
        frames=spec['frames'];path=root/name
        info=probe(path)
        video=next(s for s in info['streams'] if s['codec_type']=='video')
        if int(video['nb_frames'])!=frames or [video['width'],video['height']]!=[1280,720]:
            raise ValueError(f'Incorrect delivered frame count/geometry: {name}')
        if abs(float(video['duration'])-frames/30)>1/300:
            raise ValueError(f'Incorrect picture duration: {name}')
        run(['ffmpeg','-v','error','-xerror','-i',path,'-f','null','-'])
        wave=load_audio(path)
        audio_clock=validate_audio_clock(info, wave, frames, config['fps'], name)
        audio=measure(wave)
        if not np.isfinite(wave).all() or not all(math.isfinite(audio[key]) for key in ('input_tp', 'input_i')):
            raise ValueError(f'Delivered audio contains nonfinite samples or measurements: {name}')
        if audio['input_tp']>=0:
            raise ValueError(f'Delivered true peak lacks headroom: {name}')
        rows.append({'file':name,'frames':frames,'duration':float(video['duration']),
                     'dimensions':[1280,720],'sha256':sha256(path),'full_decode':'passed',
                     'render_receipt_sha256':sha256(path.with_suffix('.render.json' if name.startswith('proof-') else '.revision.json')),
                     'delivered_audio':audio,'audio_clock':audio_clock})
        print(f'Validated {name}',flush=True)
    levels=[row['delivered_audio']['input_i'] for row in rows if row['file'] in ['proof-A.mp4','proof-B.mp4','proof-C.mp4']]
    spread=max(levels)-min(levels)
    if spread>.5:
        raise ValueError('Original/restored comparisons exceed provisional 0.5 LU tolerance')
    record={'outputs':rows,'original_restored_comparison_spread_lu':spread,'within_0_5_lu':True,
            'source_sha256':config['source_sha256'],'composition_sha256':json_sha256(config),
            'delivery_input_binding':'passed; registered source, authenticated audio, canonical recipes/session, tracking and current producing code',
            'tracking_accepted_frames':sum(r['accepted'] for r in track['rows']),
            'tracking_total_frames':len(track['rows']),'python_version':platform.python_version(),
            'ffmpeg_version':subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0],
            'added_duration_seconds':.6,'provisional_pause_source_seconds':[98.5,99.3],
            'perceptual_audio_review':'pending','artist_acceptance':'pending',
            'native_application_import':'pending; generated projects require native import review',
            'browser_runtime_qa':'not assessed by media validator',
            'learned_enhancement_segmentation':'not run by this extension'}
    write_json(root/'directed-validation.json',record)
    return record


if __name__=='__main__':
    validate_outputs(sys.argv[1])
