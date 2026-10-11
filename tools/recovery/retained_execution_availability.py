#!/usr/bin/env python3
"""Account for verified retained executions without rewriting frozen recovery.

Only public metadata is read. Private carrier/member custody is established by
the separately completed preservation receipt, not by a filename or render exit.
"""
import argparse
from collections import Counter
import copy
import datetime
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re

from reproduction_availability import (
    ADDENDUM_PATH as BASELINE_PATH, RECEIPT_PATH as BASELINE_RECEIPT_PATH, EXCLUDED_CATEGORIES, digest, integer,
    safe_relative, same_json, valid_hash, validate_projection as validate_baseline_projection,
    validate_addendum as validate_baseline_addendum,
)

ADDENDUM_PATH = 'manifests/artifacts/god-here-retained-execution-availability.json'
IDENTITY_PATH = 'manifests/acceptance/god-here-retained-execution-identities.json'
PRESERVATION_PATH = 'manifests/acceptance/god-here-retained-execution-preservation.json'
EQUIVALENCE_PATH = 'manifests/acceptance/god-here-retained-execution-code-equivalence.json'
INPUT_PATH = 'manifests/acceptance/god-here-direction-exact-input-recovery.json'
CATALOG_PATH = 'manifests/artifacts/god-here-recovery-catalog.json'
EXPECTATIONS_PATH = 'manifests/artifacts/god-here-recovery-expectations.json'
CURRENT_STATUS = 'exact_hash_reproduced'
QUALIFICATION = (
    'Exact matching bytes are privately preserved from a verified retained native execution. '
    'This operation reproduced the identity; it did not retrieve the historical original copy. '
    'The frozen recovery and baseline reproduction records remain unchanged. '
    'Artistic acceptance and public delivery of these new private outputs are not established.'
)
REPOSITORY = 'https://github.com/4444J99/audiovisual-media-postproduction-system'


def require(condition, message):
    if not condition:
        raise ValueError('Retained execution availability: ' + message)


def identity_descriptor(row, label):
    require(isinstance(row, dict) and valid_hash(row.get('sha256'))
            and integer(row.get('bytes'), 1), label + ' lacks a complete byte identity')
    return {'sha256': row['sha256'], 'bytes': row['bytes']}


def finite(value):
    return type(value) in {int, float} and math.isfinite(value)


def expected_output_sets():
    layers = [mode + str(length) for mode in ('P', 'V') for length in (112, 84, 56, 28, 14)]
    stacks = ['P5-stack', 'P5R', 'V1-stack', 'V2-stack', 'V3-stack', 'V4-stack', 'V5-stack', 'V5R']
    room = {'room-stretch-report.json', 'source-reel-raw.wav', 'source-reel-seam-smoothed.wav'}
    room.update('raw-stems/' + label + '.wav' for label in layers)
    room.update('stems/' + label + suffix for label in layers for suffix in ('.wav', '.flac'))
    room.update('stacks/' + label + suffix for label in stacks for suffix in ('.wav', '.flac'))
    room.update('web/' + label + '-' + mix + '.m4a' for label in layers + stacks for mix in ('audition', 'production'))
    return {
        'direction-proof-directed': ('amp.direction.v1', {'render.mp4', 'render.render.json'}),
        'direction-proof-reference': ('amp.direction.v1', {'render.mp4', 'render.render.json'}),
        'directed-integrated-excerpt': ('amp.revision.v1', {'render.mp4', 'render.revision.json'}),
        'fx-demo-delay': ('fx.rack.v1', {'render.mp4', 'render.wav', 'render.patch.json', 'render.render.json'}),
        'room-stretch-full': ('amp.roomstretch.v1', room),
    }


def source_code_anchor(run, which, equivalence):
    code = run[which]
    commit = code.get('git_commit')
    require(isinstance(commit, str) and re.fullmatch('[0-9a-f]{40}', commit), which + ' commit is invalid')
    mappings = equivalence.get('mappings', [])
    require(len({r.get('local_commit') for r in mappings}) == len(mappings), 'code-equivalence commits repeat')
    match = [r for r in mappings if r.get('local_commit') == commit]
    require(len(match) == 1, which + ' has no exact public-code equivalence record')
    mapping = match[0]
    require(isinstance(mapping.get('public_commit'), str) and re.fullmatch('[0-9a-f]{40}', mapping['public_commit']), 'public code anchor is invalid')
    closures = [r for r in mapping['native_closures'] if r.get('adapter') == run['adapter']]
    require(len(closures) == 1 and closures[0].get('all_files_byte_equal') is True, 'native code closure is missing or unverified')
    files = code.get('files', [])
    expected = closures[0]['files']
    require(files and len({r.get('path') for r in files}) == len(files)
            and len({r.get('path') for r in expected}) == len(expected), 'native code file identities repeat or are absent')
    require(all(safe_relative(r.get('path')) and r.get('byte_equal') is True for r in expected), 'public code equivalence has an unsafe or unequal file')
    for row in files + expected:
        identity_descriptor(row, 'native code file')
    clean = lambda rows: sorted([{'path': r['path'], **identity_descriptor(r, 'code')} for r in rows], key=lambda r: r['path'])
    require(same_json(clean(files), clean(expected)), 'native code closure differs from public equivalence evidence')
    binding_path = 'projects/god-here/executions/' + run['binding_id'] + '.json'
    bindings = [r for r in mapping['bindings'] if r.get('path') == binding_path]
    require(len(bindings) == 1 and bindings[0].get('byte_equal') is True
            and same_json(identity_descriptor(bindings[0], 'public binding'), identity_descriptor(run['binding'], 'executed binding')), 'executed binding differs from its public code anchor')
    return {'actual_commit': commit, 'public_commit_with_equal_declared_files': mapping['public_commit'],
            'public_code_url': REPOSITORY + '/tree/' + mapping['public_commit'],
            'equivalence_scope': 'Declared native code closure and binding bytes only; complete Git trees are not asserted equal.'}


def validate_output_media(row, run):
    suffix = PurePosixPath(row['file']).suffix
    kind = {'.json': 'metadata', '.mp4': 'video', '.wav': 'audio', '.flac': 'audio', '.m4a': 'audio'}.get(suffix)
    require(kind is not None, 'unsupported required output type')
    if kind == 'metadata':
        require('full_decode' not in row, 'JSON output claims media decoding')
        return kind
    require(row.get('full_decode') == 'passed', 'required media has not passed complete decoding')
    streams = row.get('streams', [])
    audio = [r for r in streams if r.get('codec_type') == 'audio']
    video = [r for r in streams if r.get('codec_type') == 'video']
    require(len(audio) == 1 and len(video) == (1 if kind == 'video' else 0), 'required media stream set differs')
    output = run['clocks']['output']
    if run['binding_id'] == 'room-stretch-full':
        rate = output['sample_rate']
        samples = run['clocks']['source_reel_samples'] if row['file'].startswith('source-reel-') else output['samples_per_channel']
    else:
        rate, samples = output['audio_sample_rate'], output['pcm_samples_per_channel']
    require(integer(rate, 1) and integer(samples, 1), 'required audio clock is invalid')
    decode = row.get('audio_decode', {})
    require(decode.get('finite') is True and same_json(decode.get('sample_rate'), rate)
            and same_json(decode.get('channels'), 2) and same_json(decode.get('expected_pcm_samples_per_channel'), samples), 'audio decode evidence differs from the native clock')
    actual = decode.get('decoded_samples_per_channel')
    padding = decode.get('codec_tail_padding_samples')
    require(integer(actual, 1) and integer(padding) and actual - samples == padding, 'audio sample/padding accounting differs')
    codec = audio[0].get('codec_name')
    require(padding < 1024 if codec == 'aac' else padding == 0, 'audio codec padding exceeds its declared allowance')
    require(str(audio[0].get('sample_rate')) == str(rate) and same_json(audio[0].get('channels'), 2), 'audio stream metadata differs')
    presentation = row.get('audio_presentation', {})
    expected_end = samples / rate
    tolerance = 1024 / rate if codec == 'aac' else max(1e-6, 1 / rate)
    if suffix in {'.wav', '.flac'}:
        require(presentation.get('basis') == 'decoded sample-domain WAV/FLAC; no container start timestamp required'
                and integer(audio[0].get('duration_ts'), 1)
                and Fraction(audio[0]['duration_ts']) * Fraction(audio[0]['time_base']) == Fraction(samples, rate),
                'sample-domain lossless duration differs from decoded PCM accounting')
    else:
        for key in ('start_seconds', 'end_seconds', 'expected_end_seconds', 'start_tolerance_seconds', 'end_tolerance_seconds'):
            require(finite(presentation.get(key)), 'audio presentation is incomplete or nonfinite')
        require(abs(presentation['expected_end_seconds'] - expected_end) <= 1e-9
                and 0 <= presentation['end_tolerance_seconds'] <= tolerance + 1e-9
                and 0 <= presentation['start_tolerance_seconds'] <= max(1e-6, 1 / rate) + 1e-9
                and abs(presentation['start_seconds']) <= presentation['start_tolerance_seconds'] + 1e-9
                and abs(presentation['end_seconds'] - expected_end) <= presentation['end_tolerance_seconds'] + 1e-9, 'audio presentation does not meet its bounded clock')
    if kind == 'video':
        fps = Fraction(output['frame_rate']['num'], output['frame_rate']['den'])
        require(integer(output['frames'], 1) and Fraction(str(video[0].get('avg_frame_rate'))) == fps
                and str(video[0].get('nb_read_frames')) == str(output['frames'])
                and [video[0].get('width'), video[0].get('height')] == output['dimensions'], 'decoded picture dimensions, frames or rate differ')
        require(Fraction(output['frames'], 1) / fps * rate == samples, 'picture and PCM target clocks disagree')
        timing = row.get('picture_presentation', {})
        end = float(Fraction(output['frames'], 1) / fps)
        require(all(finite(timing.get(k)) for k in ('start_seconds', 'end_seconds', 'expected_end_seconds', 'start_tolerance_seconds', 'end_tolerance_seconds'))
                and abs(timing['expected_end_seconds'] - end) <= 1e-9
                and 0 <= timing['start_tolerance_seconds'] <= 1 / float(fps)
                and 0 <= timing['end_tolerance_seconds'] <= 1 / float(fps)
                and abs(timing['start_seconds']) <= timing['start_tolerance_seconds'] + 1e-9
                and abs(timing['end_seconds'] - end) <= timing['end_tolerance_seconds'] + 1e-9, 'picture presentation does not meet its bounded clock')
    return kind


def validate_native_clock(run):
    clocks, key = run['clocks'], run['binding_id']
    if key == 'room-stretch-full':
        require(same_json(clocks.get('output'), {'sample_rate': 48000, 'samples_per_channel': 5376000, 'channels': 2})
                and same_json(clocks.get('source_reel_samples'), 212160), 'room source/output sample clocks differ')
        end = 0
        for segment in clocks.get('source_reel_map', []):
            require(all(integer(segment.get(k)) for k in ('source_start_sample', 'source_end_sample', 'reel_start_sample', 'reel_end_sample')),
                    'room source-reel coordinates are invalid')
            require(segment['reel_start_sample'] == end and segment['source_end_sample'] > segment['source_start_sample']
                    and segment['source_end_sample'] <= 5376000
                    and segment['reel_end_sample'] - end == segment['source_end_sample'] - segment['source_start_sample'], 'room source-reel map has a gap or differing span')
            end = segment['reel_end_sample']
        require(end == 212160, 'room source-reel spans do not cover the declared reel')
    elif key == 'fx-demo-delay':
        require(clocks.get('source_consumption') == 'Derived asset collection; original movie hash is lineage, not a consumed input.'
                and isinstance(clocks.get('source_output_map'), str) and 'no single linear' in clocks['source_output_map'], 'FX derived-source or nonlinear clock qualification is absent')
        require(same_json(clocks['output'], {'frame_rate': {'num': 12, 'den': 1}, 'frames': 146,
                'dimensions': [480, 270], 'audio_sample_rate': 24000, 'pcm_samples_per_channel': 292000}), 'retained FX output clock differs')
    else:
        required_frames = {'direction-proof-directed': 685, 'direction-proof-reference': 661, 'directed-integrated-excerpt': 679}[key]
        require(same_json(clocks['output'].get('frames'), required_frames)
                and same_json(clocks['output'].get('frame_rate'), {'num': 30, 'den': 1}), 'retained direction/revision frame clock differs')
        end, prior_source_end = 0, 0
        for segment in clocks.get('source_output_map', []):
            names = ('source_start_frame', 'source_end_frame', 'output_start_frame', 'output_end_frame') if key == 'directed-integrated-excerpt' else ('source_start', 'source_end', 'output_start', 'output_end')
            require(all(integer(segment.get(k)) for k in names), 'source/output segment coordinates are invalid')
            ss, se, os, oe = (segment[k] for k in names)
            require(os == end and oe > os and ss >= prior_source_end and 0 <= ss < se <= 3360, 'native source/output map is discontinuous or out of bounds')
            if key != 'directed-integrated-excerpt':
                require(same_json(segment.get('output_frames'), oe - os), 'native mapped frame count differs')
            end, prior_source_end = oe, se
        require(end == required_frames, 'native source/output map does not cover the output')


def validate_identity_receipt(identity, catalog, baseline, inputs, equivalence):
    require(identity.get('schema_version') == 'amps.retained-execution-identity-addendum.v1', 'unsupported identity receipt')
    require(identity.get('artistic_acceptance') == 'pending' and identity.get('numerical_parity_claimed') is False, 'identity receipt grants unsupported artistic or numerical acceptance')
    require(equivalence.get('schema_version') == 'amps.public-source-equivalence.v1'
            and equivalence.get('repository') == REPOSITORY, 'unsupported public-code equivalence')
    expected = expected_output_sets()
    runs = {r['binding_id']: r for r in identity['runs']}
    require(len(runs) == len(identity['runs']) and set(runs) == set(expected), 'retained binding set is incomplete or repeated')
    known = {r['sha256']: r for r in catalog['objects']}
    require(len(known) == len(catalog['objects']), 'frozen identities repeat')
    for row in baseline['output_objects']:
        if row['sha256'] in known:
            require(known[row['sha256']]['bytes'] == row['bytes'], 'baseline/frozen byte conflict')
        known[row['sha256']] = row
    before_inputs = set(known)
    require(inputs.get('status') == 'all_required_input_identities_verified' and inputs.get('artistic_acceptance') == 'pending'
            and inputs.get('new_render_executed') is False and inputs.get('font_substitution') is False, 'PR49 input recovery scope or identity is unsupported')
    preserved_inputs = inputs.get('durable_preservation', {})
    require(preserved_inputs.get('status') == 'saved_verified_archive_in_four_ordered_volumes', 'PR49 input preservation is incomplete')
    archive = identity_descriptor(preserved_inputs.get('archive'), 'PR49 input archive')
    input_volumes = preserved_inputs.get('volumes', [])
    offset = 0
    for n, row in enumerate(input_volumes, 1):
        identity_descriptor(row, 'PR49 volume')
        require(same_json(row.get('order'), n) and same_json(row.get('offset'), offset), 'PR49 volume order/offset differs')
        offset += row['bytes']
    require(len(input_volumes) == 4 and offset == archive['bytes'], 'PR49 volume coverage differs')
    require(len({r.get('sha256') for r in input_volumes}) == 4, 'PR49 volumes repeat')
    identity_descriptor(preserved_inputs.get('restore_manifest'), 'PR49 restore manifest')
    additional_inputs = []
    roles = {r['role']: r for r in inputs['inputs']}
    require(len(roles) == len(inputs['inputs']) and set(roles) == {'source', 'recipe', 'fields', 'audio', 'reference_audio', 'font'}, 'PR49 input roles differ')
    for row in inputs['inputs']:
        identity_descriptor(row, 'PR49 input')
        require(safe_relative(row.get('logical_path')), 'PR49 logical input path is unsafe')
        sha = row['sha256']
        if sha in known:
            require(known[sha]['bytes'] == row['bytes'], 'PR49 input size conflicts with existing identity')
        else:
            require(row['role'] in {'audio', 'reference_audio', 'font'}, 'unexpected new PR49 input role')
            require(row.get('expected_historical_sha256', sha) == sha, 'PR49 historical input hash differs')
            if row['role'] != 'font':
                require(row.get('full_decode') == 'passed' and same_json(row.get('sample_rate'), 48000)
                        and same_json(row.get('channels'), 2) and same_json(row.get('pcm_frames_per_channel'), 5376627), 'PR49 input audio verification differs')
            additional_inputs.append({'sha256': sha, 'bytes': row['bytes'], 'names': [row['logical_path']],
                'type': 'font' if row['role'] == 'font' else 'audio', 'decode': 'not_applicable' if row['role'] == 'font' else 'passed',
                'role': row['role'], 'provenance': row['origin'], 'availability': 'privately_preserved', 'links': [],
                'historical_original_retrieval': False, 'exact_dependency_bytes_retrieved': row['role'] == 'font',
                'artistic_acceptance': 'pending'})
        known[sha] = row
    require(len(additional_inputs) == 3, 'PR49 supplemental identity count differs')
    grouped, seen_paths = {}, set()
    per_run = {key: [] for key in runs}
    for row in identity['outputs']:
        key = (row.get('binding_id'), row.get('file'))
        require(key[0] in runs and safe_relative(key[1]) and key not in seen_paths, 'required output binding/path is unsafe or repeated')
        seen_paths.add(key)
        identity_descriptor(row, 'required output')
        require(row['sha256'] not in grouped, 'required output identity repeats in this fixed execution set')
        require(row.get('existing_technical_status_conflict') is False, 'retained output conflicts with recorded technical failure')
        existing = row['sha256'] in known
        require(row.get('existing_exact_custody_recorded') is existing, 'existing-output split differs from exact known identities')
        if existing:
            old = known[row['sha256']]
            require(old['bytes'] == row['bytes'], 'retained output size conflicts with existing identity')
            require(old.get('verification', {}).get('full_decode_status') != 'failed', 'retained output relabels a preserved decode failure')
        kind = validate_output_media(row, runs[key[0]])
        grouped[row['sha256']] = {'sha256': row['sha256'], 'bytes': row['bytes'], 'type': kind,
            'binding_id': key[0], 'file': key[1], 'names': [key[0] + '/' + key[1]],
            'full_decode_status': 'not_applicable' if kind == 'metadata' else 'passed',
            'present_before_retained_executions': existing, 'present_in_frozen_catalog': row['sha256'] in {r['sha256'] for r in catalog['objects']},
            'availability': 'privately_preserved', 'historical_original_retrieval': False,
            'public_delivery': 'not_established_by_this_receipt', 'artistic_acceptance': 'pending'}
        per_run[key[0]].append(grouped[row['sha256']])
    summaries = []
    for key, run in runs.items():
        require(run.get('adapter') == expected[key][0] and {r['file'] for r in per_run[key]} == expected[key][1], 'required native output set differs for ' + key)
        require(run.get('native_render_executed') is True and run.get('new_native_execution_for_later_verification') is False
                and run.get('technical_status') == 'required_native_outputs_verified', 'run lacks qualified native execution evidence')
        identity_descriptor(run.get('native_execution_receipt'), 'native execution receipt')
        identity_descriptor(run.get('verification_receipt'), 'verification receipt')
        require(run.get('original_execution_status') == ('execution_failed' if key == 'room-stretch-full' else 'render_verified'), 'original execution status was rewritten')
        producer = source_code_anchor(run, 'producing_code', equivalence)
        verifier = source_code_anchor(run, 'verification_code', equivalence)
        if key == 'room-stretch-full':
            require(producer['actual_commit'] != verifier['actual_commit'] and run['native_execution_receipt'] != run['verification_receipt'], 'room post-hoc verification must preserve separate producer and verifier')
        else:
            require(same_json(run['producing_code'], run['verification_code']) and same_json(run['native_execution_receipt'], run['verification_receipt']), 'inline verification provenance differs')
        source = run['clocks'].get('source', {})
        require(source.get('sha256') == baseline['provenance']['source_sha256'] and same_json(source.get('frames'), 3360)
                and same_json(source.get('frame_rate'), {'num': 30, 'den': 1}), 'native source lineage/clock differs')
        validate_native_clock(run)
        require(run.get('runtime') and isinstance(run['runtime'], dict), 'native runtime provenance is absent')
        decoded = sum(r['type'] != 'metadata' for r in per_run[key])
        require(same_json(run.get('required_output_count'), len(per_run[key])) and same_json(run.get('decoded_media_count'), decoded), 'per-run required or decode count differs')
        summaries.append({'binding_id': key, 'adapter': run['adapter'], 'status': 'required_native_outputs_verified',
            'original_execution_status': run['original_execution_status'], 'verification_mode': 'post_hoc_existing_products' if key == 'room-stretch-full' else 'native_execution_with_output_verification',
            'new_render_for_later_verification': False, 'producing_source': producer, 'verification_source': verifier,
            'native_execution_receipt': run['native_execution_receipt'], 'verification_receipt': run['verification_receipt'],
            'binding': run['binding'], 'clocks': run['clocks'], 'runtime': run['runtime'], 'native_options': run['native_options'],
            'required_output_identities': len(per_run[key]), 'full_decode_passes': decoded,
            'existing_exact_identities': sum(r['present_before_retained_executions'] for r in per_run[key]),
            'new_output_identities': sum(not r['present_before_retained_executions'] for r in per_run[key]),
            'required_output_bytes': sum(r['bytes'] for r in per_run[key]), 'artistic_acceptance': 'pending'})
    failures = identity.get('failed_native_attempts', [])
    require(len(failures) == 1 and failures[0].get('binding_id') == 'directed-integrated-excerpt'
            and failures[0].get('status') == 'failed_not_accepted' and failures[0].get('cause') == 'not established', 'failed initial attempt is absent or relabeled')
    for key in ('execution_receipt', 'integrity_observation', 'observed_file'):
        identity_descriptor(failures[0].get(key), 'failed initial attempt ' + key)
    require(failures[0]['observed_file']['sha256'] not in grouped, 'failed initial bytes are counted as a successful output')
    new = [r for r in grouped.values() if not r['present_before_retained_executions']]
    derived_counts = {'bound_retained_recipes': len(runs), 'native_renderer_families': len({r['adapter'] for r in runs.values()}),
        'native_execution_attempts': len(runs) + len(failures), 'successful_required_product_sets': len(runs),
        'required_output_occurrences': len(identity['outputs']), 'unique_required_output_identities': len(grouped),
        'fully_decoded_required_media': sum(r['type'] != 'metadata' for r in grouped.values()),
        'existing_custody_matches': len(grouped) - len(new), 'new_required_output_identities': len(new),
        'new_required_output_bytes': sum(r['bytes'] for r in new)}
    require(all(same_json(identity.get('counts', {}).get(k), v) for k, v in derived_counts.items()), 'identity receipt derived counts disagree')
    return {'outputs': sorted(grouped.values(), key=lambda r: r['sha256']), 'new_outputs': new,
            'inputs': sorted(additional_inputs, key=lambda r: r['sha256']), 'known_before_inputs': before_inputs,
            'runs': sorted(summaries, key=lambda r: r['binding_id']), 'counts': derived_counts}


def validate_preservation(preservation, identity, validated, descriptors):
    require(preservation.get('schema_version') == 'amps.retained-execution-preservation.v1'
            and preservation.get('status') == 'complete', 'private retained-output preservation is incomplete')
    require(same_json(identity_descriptor(preservation.get('identity_snapshot'), 'preserved identity snapshot'),
                      identity_descriptor(descriptors['identity'], 'identity source')),
            'preservation receipt is not bound to these execution identities')
    require(same_json(identity_descriptor(preservation.get('public_source_equivalence'), 'preserved source equivalence'),
                      identity_descriptor(descriptors['equivalence'], 'source equivalence')),
            'preservation receipt is not bound to this source equivalence')
    for key in ('all_volumes_saved', 'all_saved_files_have_local_identity_metadata', 'all_volume_identities_rechecked_after_save',
                'concatenated_saved_volume_identities_match_archive', 'all_required_output_identities_accounted_for'):
        require(preservation.get(key) is True, 'preservation gate is incomplete: ' + key)
    archive = identity_descriptor(preservation.get('archive'), 'retained output archive')
    require(preservation['archive'].get('all_member_crc_sha256_bytes_verified') is True
            and integer(preservation['archive'].get('member_count'), 1)
            and same_json(preservation['archive'].get('zip_members'), preservation['archive']['member_count']), 'archive integrity/member count evidence differs')
    volumes = preservation.get('ordered_volumes', [])
    require(volumes and len({r.get('sha256') for r in volumes}) == len(volumes)
            and len({r.get('file_name') for r in volumes}) == len(volumes), 'preservation volumes are absent or repeated')
    offset = 0
    for order, volume in enumerate(volumes, 1):
        identity_descriptor(volume, 'retained volume')
        require(same_json(volume.get('order'), order) and same_json(volume.get('offset'), offset)
                and volume['bytes'] <= 25000000 and safe_relative(volume.get('file_name'))
                and volume.get('status') == 'succeeded' and volume.get('local_metadata_applied') is True,
                'volume order, offset, size or successful custody differs')
        offset += volume['bytes']
    require(offset == archive['bytes'], 'saved volume byte total does not cover the archive')
    restore = preservation.get('reconstruction_manifest', {})
    identity_descriptor(restore, 'retained reconstruction manifest')
    require(restore.get('status') == 'succeeded' and safe_relative(restore.get('file_name')), 'reconstruction manifest was not saved')
    identity_descriptor(preservation.get('archive_validation'), 'archive validation receipt')
    expected = {r['sha256']: r for r in validated['new_outputs']}
    saved = preservation.get('new_required_outputs', [])
    require(len(saved) == len(expected) and {r.get('sha256') for r in saved} == set(expected), 'preservation output coverage is incomplete or repeated')
    members = set()
    for row in saved:
        original = expected[row['sha256']]
        require(all(same_json(row.get(k), original[k]) for k in ('sha256', 'bytes', 'file', 'binding_id'))
                and row.get('technical_status') == 'required_native_output_verified'
                and row.get('artistic_acceptance') == 'pending' and row.get('preservation') == 'new_identity_in_this_archive', 'preserved output identity, size or status differs')
        member = row.get('archive_member')
        require(safe_relative(member) and member.startswith('objects/' + row['sha256'] + '.')
                and member not in members, 'preserved output member path is unsafe, repeated or not identity-addressed')
        members.add(member)
    counts = validated['counts']
    require(same_json(preservation.get('new_required_output_count'), len(saved))
            and same_json(preservation.get('new_required_output_bytes'), sum(r['bytes'] for r in saved))
            and same_json(preservation.get('existing_custody_match_count'), counts['existing_custody_matches']), 'preservation counts or byte totals differ')
    failed = preservation.get('failed_artifacts_preserved_separately', [])
    original_failure = identity['failed_native_attempts'][0]
    require(len(failed) == 1 and failed[0].get('binding_id') == original_failure['binding_id']
            and same_json(identity_descriptor(failed[0], 'preserved failed output'), original_failure['observed_file'])
            and failed[0].get('status') == 'failed_not_accepted' and failed[0].get('cause') == 'not established'
            and safe_relative(failed[0].get('archive_member')) and failed[0]['archive_member'].startswith('failed-not-accepted/')
            and failed[0]['archive_member'] not in members, 'failed original output preservation is absent or relabeled')
    require(preservation['archive']['member_count'] >= len(members) + len(failed), 'archive cannot contain its declared required and failed members')
    incidental = identity.get('incidental_outputs', {})
    incidental_rows = incidental.get('incidental_outputs', [])
    require(incidental.get('binding_id') == 'room-stretch-full' and same_json(incidental.get('required_output_count'), 85)
            and same_json(incidental.get('observed_file_count'), 85 + len(incidental_rows)), 'incidental room-product scope differs')
    require(len({r.get('file') for r in incidental_rows}) == len(incidental_rows), 'incidental paths repeat')
    for row in incidental_rows:
        identity_descriptor(row, 'incidental file')
        require(safe_relative(row.get('file')) and row.get('classification') == 'native_temporary_file'
                and row.get('full_decode') == 'not_checked_not_a_required_deliverable'
                and row.get('disposition') == 'reconstructible_intermediate_not_retained'
                and row.get('accepted_for_delivery') is False, 'incidental file was promoted to retained/accepted media')
    note = preservation.get('incidental_intermediates', {})
    require(same_json(note.get('count'), len(incidental_rows)) and same_json(note.get('bytes'), sum(r['bytes'] for r in incidental_rows))
            and note.get('identities_and_dispositions_recorded') is True and note.get('bytes_retained') is False
            and same_json(identity['counts'].get('incidental_files'), len(incidental_rows))
            and same_json(identity['counts'].get('incidental_bytes'), note['bytes']), 'incidental preservation counts or disposition differ')
    privacy = preservation.get('privacy', {})
    require(privacy.get('private_preservation_only') is True and privacy.get('new_public_media_delivery_performed') is False
            and privacy.get('original_source_binaries_copied') is False, 'private retained-output preservation is mislabeled as public delivery')
    try:
        completed = datetime.datetime.fromisoformat(preservation['completed_at_utc'])
        identified = datetime.datetime.fromisoformat(identity['created_at_utc'])
        require(completed.tzinfo is not None and identified.tzinfo is not None and completed >= identified, 'preservation completion predates the identity snapshot')
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('Retained execution availability: preservation completion timestamp is invalid') from exc
    return {'archive': archive, 'saved_volume_count': len(volumes), 'new_required_outputs': saved,
            'failed_artifacts_preserved_separately': failed, 'incidental_intermediates': note}


def derive_addendum(identity, preservation, inputs, equivalence, catalog, expectations, baseline, descriptors):
    require(baseline.get('frozen_catalog_sha256') == descriptors['catalog']['sha256']
            and baseline.get('frozen_expectations_sha256') == descriptors['expectations']['sha256'], 'frozen/baseline evidence bindings differ')
    verified = validate_identity_receipt(identity, catalog, baseline, inputs, equivalence)
    saved = validate_preservation(preservation, identity, verified, descriptors)
    frozen = {r['sha256']: r for r in catalog['objects']}
    expected_rows = {r['expectation_id']: r for r in expectations['expectations']}
    require(len(expected_rows) == len(expectations['expectations']), 'expectation IDs repeat')
    expected_hashes = {r['expected_sha256'] for r in expected_rows.values() if r.get('expected_sha256')}
    missing = expected_hashes - set(frozen)
    baseline_hashes = {r['sha256'] for r in baseline['output_objects']}
    prior = set(frozen) | baseline_hashes
    input_hashes = {r['sha256'] for r in verified['inputs']}
    require(len(missing) == expectations['counts']['unique_expected_sha256s_unrecovered']
            and len(missing - baseline_hashes) == baseline['counts']['remaining_unmatched_expected_hashes'], 'frozen/baseline unmatched counts differ')
    outputs = {r['sha256']: r for r in verified['outputs']}
    new_hashes = set(outputs) - prior - input_hashes
    newly_matched = missing - baseline_hashes - input_hashes
    newly_matched &= set(outputs)
    updates = []
    for row in expected_rows.values():
        sha = row.get('expected_sha256')
        if sha not in newly_matched:
            continue
        output = outputs[sha]
        require(row.get('expected_bytes') is None or same_json(row['expected_bytes'], output['bytes']), 'historical expectation size conflicts with retained bytes')
        require(row['status'] != 'exact_hash_recovered', 'retained execution recounts a frozen recovery match')
        updates.append({'expectation_id': row['expectation_id'], 'expected_sha256': sha, 'matched_bytes': output['bytes'],
            'frozen_status': row['status'], 'current_status': CURRENT_STATUS, 'output_paths': output['names'],
            'binding_id': output['binding_id'], 'availability': 'privately_preserved', 'historical_original_retrieval': False,
            'reproduction_scope': 'retained_native_execution', 'qualification': QUALIFICATION})
    require(not (input_hashes & (missing - baseline_hashes)), 'new PR49 matches require a distinct input-availability update')
    counts = {
        'frozen_catalog_unique_objects': len(frozen), 'frozen_catalog_file_occurrences': catalog['counts']['file_occurrences'],
        'baseline_additional_unique_outputs': baseline['counts']['supplemental_new_unique_outputs'],
        'additional_exact_pr49_input_identities': len(input_hashes),
        **verified['counts'],
        'new_required_outputs_by_type': dict(sorted(Counter(outputs[s]['type'] for s in new_hashes).items())),
        'new_required_media_decode_passes': sum(outputs[s]['type'] != 'metadata' for s in new_hashes),
        'frozen_unmatched_expected_hashes': len(missing),
        'unmatched_after_baseline_reproduction': len(missing - baseline_hashes),
        'additional_expected_hashes_reproduced': len(newly_matched), 'expectation_rows_updated': len(updates),
        'remaining_unmatched_expected_hashes': len(missing - baseline_hashes - input_hashes - set(outputs)),
        'frozen_baseline_pr49_retained_scoped_identity_union': len(prior | input_hashes | set(outputs)),
        'historical_original_outputs_retrieved_by_this_operation': 0, 'new_public_output_links': 0, 'artistic_acceptance_added': 0,
    }
    return {'schema_version': 'god-here.retained-execution-availability.v1',
        'recorded_at_utc': preservation['completed_at_utc'],
        'scope': 'Five retained native bindings across four renderer families, with exact PR49 supporting-input recovery. This additive view excludes carrier archives/volumes, incidental files, and unrelated post-snapshot changes from object counts.',
        'frozen_catalog_sha256': descriptors['catalog']['sha256'], 'frozen_expectations_sha256': descriptors['expectations']['sha256'],
        'frozen_files_unchanged': True, 'baseline_addendum_unchanged': True,
        'evidence': {key: descriptors[key] for key in ('baseline', 'identity', 'preservation', 'inputs', 'equivalence')},
        'counts': counts, 'runs': verified['runs'], 'required_output_objects': verified['outputs'],
        'additional_input_objects': verified['inputs'], 'expectation_updates': sorted(updates, key=lambda r: r['expectation_id']),
        'private_preservation': {'status': 'complete', 'archive': saved['archive'], 'saved_volume_count': saved['saved_volume_count'], 'new_public_media_links': []},
        'failed_attempts': copy.deepcopy(identity['failed_native_attempts']),
        'failed_artifacts_preserved_separately': saved['failed_artifacts_preserved_separately'],
        'incidental_intermediates': saved['incidental_intermediates'],
        'interpretation': QUALIFICATION,
        'room_verification_qualification': 'The room outputs were produced at the original recorded commit and verified later with corrected wrapper rules. The original failed execution receipt remains failed; the later check did not execute a new native render.',
    }


def load_inputs(root):
    paths = {'catalog': CATALOG_PATH, 'expectations': EXPECTATIONS_PATH, 'baseline': BASELINE_PATH,
             'baseline_receipt': BASELINE_RECEIPT_PATH, 'identity': IDENTITY_PATH, 'preservation': PRESERVATION_PATH,
             'inputs': INPUT_PATH, 'equivalence': EQUIVALENCE_PATH}
    records, descriptors = {}, {}
    for key, relative in paths.items():
        raw = (root / relative).read_bytes()
        records[key] = json.loads(raw)
        descriptors[key] = {'path': relative, 'sha256': digest(raw), 'bytes': len(raw)}
    return records, descriptors


def derive_loaded(records, descriptors):
    validate_baseline_addendum(records['baseline'], records['baseline_receipt'], records['catalog'], records['expectations'],
        descriptors['catalog']['sha256'], descriptors['expectations']['sha256'],
        descriptors['baseline_receipt']['sha256'], descriptors['baseline_receipt']['bytes'])
    return derive_addendum(*(records[k] for k in ('identity', 'preservation', 'inputs', 'equivalence', 'catalog', 'expectations', 'baseline')), descriptors)


def validate_addendum(addendum, records, descriptors):
    expected = derive_loaded(records, descriptors)
    require(same_json(addendum, expected), 'addendum differs from its exact bound evidence')
    return expected


def apply_to_projection(projection, addendum, addendum_sha256):
    require(projection.get('source_catalog_sha256') == addendum['frozen_catalog_sha256']
            and projection.get('source_expectations_sha256') == addendum['frozen_expectations_sha256'], 'projection frozen bindings differ')
    require(projection.get('reproduction_availability', {}).get('addendum_sha256') == addendum['evidence']['baseline']['sha256'], 'projection baseline binding differs')
    projection['retained_execution_availability'] = {
        'addendum_sha256': addendum_sha256, 'evidence': copy.deepcopy(addendum['evidence']), 'counts': copy.deepcopy(addendum['counts']),
        'runs': copy.deepcopy(addendum['runs']), 'availability': 'privately_preserved', 'artistic_acceptance': 'pending',
        'scope': addendum['scope'], 'room_verification_qualification': addendum['room_verification_qualification'],
        'failed_attempts': copy.deepcopy(addendum['failed_attempts']), 'incidental_intermediates': copy.deepcopy(addendum['incidental_intermediates']),
    }
    projection['retained_outputs'] = sorted([{
        'sha256': r['sha256'], 'bytes': r['bytes'], 'names': r['names'], 'type': r['type'], 'occurrences': 1,
        'binding_id': r['binding_id'], 'decode': r['full_decode_status'], 'links': [], 'code_url': None,
        'download_pending': False, 'availability': 'privately_preserved', 'historical_original_retrieval': False,
        'artistic_acceptance': 'pending', 'provenance': 'retained_native_execution', 'frozen_catalog_member': False,
    } for r in addendum['required_output_objects'] if not r['present_before_retained_executions']], key=lambda r: (r['names'][0], r['sha256']))
    projection['retained_inputs'] = copy.deepcopy(addendum['additional_input_objects'])
    updates = {r['expectation_id']: r for r in addendum['expectation_updates']}
    for row in projection['expectations']:
        update = updates.get(row['id'])
        if update:
            row.update({'frozen_status': update['frozen_status'], 'status': update['current_status'],
                'matched_sha256': update['expected_sha256'], 'availability': 'privately_preserved',
                'historical_original_retrieval': False, 'reproduced_names': update['output_paths'],
                'reproduction_scope': update['reproduction_scope'], 'qualification': update['qualification']})
    return projection


def validate_projection(projection, addendum, addendum_sha256, baseline, baseline_sha256, expectations):
    rebuilt = apply_to_projection(copy.deepcopy(projection), addendum, addendum_sha256)
    for key in ('retained_execution_availability', 'retained_outputs', 'retained_inputs'):
        require(same_json(projection.get(key), rebuilt[key]), 'projection retained layer differs: ' + key)
    require(len({r['sha256'] for r in projection['retained_outputs']}) == len(projection['retained_outputs']), 'projection repeats retained output identities')
    groups = [{r['sha256'] for r in projection[key]} for key in ('objects', 'reproductions', 'retained_outputs', 'retained_inputs')]
    require(sum(len(group) for group in groups) == len(set().union(*groups)), 'projection double-counts an identity across layers')
    validate_baseline_projection(projection, baseline, baseline_sha256, expectations, addendum['expectation_updates'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--apply-to-projection', action='store_true', help='Update only additive metadata; no media access')
    args = parser.parse_args()
    root = args.root.resolve()
    records, descriptors = load_inputs(root)
    result = derive_loaded(records, descriptors)
    raw = (json.dumps(result, indent=2) + '\n').encode()
    (root / ADDENDUM_PATH).write_bytes(raw)
    if args.apply_to_projection:
        path = root / 'web/recovery/catalog.json'
        projection = apply_to_projection(json.loads(path.read_bytes()), result, digest(raw))
        validate_projection(projection, result, digest(raw), records['baseline'], descriptors['baseline']['sha256'], records['expectations'])
        path.write_text(json.dumps(projection, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(json.dumps({'addendum_sha256': digest(raw), 'bytes': len(raw), 'counts': result['counts']}, indent=2))


if __name__ == '__main__':
    main()
