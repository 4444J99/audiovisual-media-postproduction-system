#!/usr/bin/env python3
"""Deterministic receipt/projection corruption probes; no media or network.

Actual completed evidence provides the positive control. Invalid variations
exist only in memory and are never installed as completed production receipts.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from retained_execution_availability import (
    ADDENDUM_PATH, derive_loaded, load_inputs, validate_addendum, validate_projection,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    records, descriptors = load_inputs(root)
    raw = (root / ADDENDUM_PATH).read_bytes()
    addendum = json.loads(raw)
    addendum_sha = hashlib.sha256(raw).hexdigest()
    projection_raw = (root / 'web/recovery/catalog.json').read_bytes()
    projection = json.loads(projection_raw)
    results = []

    def positive(name, operation):
        try:
            operation()
            results.append({'name': name, 'passed': True, 'expected': 'valid metadata accepted'})
        except Exception as exc:
            results.append({'name': name, 'passed': False, 'expected': 'valid metadata accepted', 'error': str(exc)})

    def reject(name, target, change):
        try:
            if target in records:
                edited = dict(records)
                edited[target] = copy.deepcopy(records[target])
                change(edited[target])
                derive_loaded(edited, descriptors)
            elif target == 'addendum':
                edited = copy.deepcopy(addendum)
                change(edited)
                validate_addendum(edited, records, descriptors)
            else:
                edited = copy.deepcopy(projection)
                change(edited)
                validate_projection(edited, addendum, addendum_sha, records['baseline'], descriptors['baseline']['sha256'], records['expectations'])
            results.append({'name': name, 'passed': False, 'expected': 'invalid metadata rejected', 'error': 'invalid metadata was accepted'})
        except ValueError as exc:
            results.append({'name': name, 'passed': True, 'expected': 'invalid metadata rejected', 'rejection': str(exc)})
        except Exception as exc:
            results.append({'name': name, 'passed': False, 'expected': 'invalid metadata rejected', 'error': 'unexpected exception: ' + type(exc).__name__ + ': ' + str(exc)})

    positive('actual_completed_addendum', lambda: validate_addendum(addendum, records, descriptors))
    positive('actual_completed_projection', lambda: validate_projection(projection, addendum, addendum_sha, records['baseline'], descriptors['baseline']['sha256'], records['expectations']))
    run = lambda d, key: next(r for r in d['runs'] if r['binding_id'] == key)
    out = lambda d, key, name: next(r for r in d['outputs'] if r['binding_id'] == key and r['file'] == name)
    first_audio = lambda d: out(d, 'fx-demo-delay', 'render.wav')
    reject('duplicate_run', 'identity', lambda d: d['runs'].append(copy.deepcopy(d['runs'][0])))
    reject('missing_run', 'identity', lambda d: d['runs'].pop())
    reject('native_render_never_executed', 'identity', lambda d: d['runs'][0].update(native_render_executed=False))
    reject('native_render_string_true', 'identity', lambda d: d['runs'][0].update(native_render_executed='true'))
    reject('unverified_required_set', 'identity', lambda d: d['runs'][0].update(technical_status='preflight_complete'))
    reject('room_original_status_rewritten', 'identity', lambda d: run(d, 'room-stretch-full').update(original_execution_status='render_verified'))
    reject('room_false_new_render', 'identity', lambda d: run(d, 'room-stretch-full').update(new_native_execution_for_later_verification=True))
    reject('room_verifier_replaced_by_producer', 'identity', lambda d: run(d, 'room-stretch-full').update(verification_code=copy.deepcopy(run(d, 'room-stretch-full')['producing_code'])))
    reject('reference_producer_misattributed', 'identity', lambda d: run(d, 'direction-proof-reference')['producing_code'].update(git_commit='7469ea42e2a7058d9846ac8032e03075dabc9647'))
    reject('run_source_identity_changed', 'identity', lambda d: d['runs'][0]['clocks']['source'].update(sha256='0' * 64))
    reject('run_source_frame_count_changed', 'identity', lambda d: d['runs'][0]['clocks']['source'].update(frames=3361))
    reject('run_output_frames_changed', 'identity', lambda d: d['runs'][0]['clocks']['output'].update(frames=686))
    reject('run_frame_map_gap', 'identity', lambda d: d['runs'][0]['clocks']['source_output_map'][1].update(output_start=327))
    reject('room_reel_map_gap', 'identity', lambda d: run(d, 'room-stretch-full')['clocks']['source_reel_map'][1].update(reel_start_sample=12961))
    reject('fx_original_claimed_consumed', 'identity', lambda d: run(d, 'fx-demo-delay')['clocks'].update(source_consumption='Original movie consumed'))
    reject('repeated_producing_code_file', 'identity', lambda d: d['runs'][0]['producing_code']['files'].append(copy.deepcopy(d['runs'][0]['producing_code']['files'][0])))
    reject('different_producing_code_hash', 'identity', lambda d: d['runs'][0]['producing_code']['files'][0].update(sha256='0' * 64))
    reject('different_executed_binding', 'identity', lambda d: d['runs'][0]['binding'].update(sha256='0' * 64))
    reject('public_closure_not_equal', 'equivalence', lambda d: d['mappings'][0]['native_closures'][0].update(all_files_byte_equal=False))
    reject('public_closure_file_not_equal', 'equivalence', lambda d: d['mappings'][0]['native_closures'][0]['files'][0].update(byte_equal=False))
    reject('public_binding_not_equal', 'equivalence', lambda d: d['mappings'][0]['bindings'][1].update(byte_equal=False))
    reject('repeated_public_commit_mapping', 'equivalence', lambda d: d['mappings'].append(copy.deepcopy(d['mappings'][0])))
    reject('required_output_missing', 'identity', lambda d: d['outputs'].pop())
    reject('required_output_path_repeated', 'identity', lambda d: d['outputs'].append(copy.deepcopy(d['outputs'][0])))
    reject('required_output_identity_repeated', 'identity', lambda d: d['outputs'][1].update(sha256=d['outputs'][0]['sha256']))
    reject('required_output_unknown_binding', 'identity', lambda d: d['outputs'][0].update(binding_id='unknown'))
    reject('required_output_unsafe_path', 'identity', lambda d: d['outputs'][0].update(file='../render.mp4'))
    reject('required_output_short_hash', 'identity', lambda d: d['outputs'][0].update(sha256='1234'))
    reject('required_output_boolean_bytes', 'identity', lambda d: d['outputs'][0].update(bytes=True))
    reject('required_output_changed_size', 'identity', lambda d: d['outputs'][0].update(bytes=d['outputs'][0]['bytes'] + 1))
    reject('new_output_falsely_already_custodied', 'identity', lambda d: d['outputs'][0].update(existing_exact_custody_recorded=True))
    reject('existing_output_false_new', 'identity', lambda d: out(d, 'directed-integrated-excerpt', 'render.mp4').update(existing_exact_custody_recorded=False))
    reject('technical_failure_conflict_hidden', 'identity', lambda d: d['outputs'][0].update(existing_technical_status_conflict=True))
    reject('media_decode_failed', 'identity', lambda d: d['outputs'][0].update(full_decode='failed'))
    reject('audio_not_finite', 'identity', lambda d: first_audio(d)['audio_decode'].update(finite=False))
    reject('audio_finite_integer', 'identity', lambda d: first_audio(d)['audio_decode'].update(finite=1))
    reject('audio_sample_count_wrong', 'identity', lambda d: first_audio(d)['audio_decode'].update(decoded_samples_per_channel=292001))
    reject('audio_pcm_padding_invented', 'identity', lambda d: first_audio(d)['audio_decode'].update(decoded_samples_per_channel=292001, codec_tail_padding_samples=1))
    reject('audio_lossless_duration_wrong', 'identity', lambda d: first_audio(d)['streams'][0].update(duration_ts=292001))
    reject('audio_rate_mismatch', 'identity', lambda d: first_audio(d)['audio_decode'].update(sample_rate=48000))
    reject('picture_frame_mismatch', 'identity', lambda d: d['outputs'][0]['streams'][0].update(nb_read_frames='684'))
    reject('picture_clock_tolerance_unbounded', 'identity', lambda d: d['outputs'][0]['picture_presentation'].update(end_tolerance_seconds=1000))
    reject('audio_clock_tolerance_unbounded', 'identity', lambda d: d['outputs'][0]['audio_presentation'].update(end_tolerance_seconds=1000))
    reject('fake_artistic_acceptance', 'identity', lambda d: d.update(artistic_acceptance='accepted'))
    reject('unsupported_numerical_parity', 'identity', lambda d: d.update(numerical_parity_claimed=True))
    for key in records['identity']['counts']:
        reject('identity_count_' + key, 'identity', lambda d, key=key: d['counts'].update({key: d['counts'][key] + 1}))
    reject('original_failure_omitted', 'identity', lambda d: d.update(failed_native_attempts=[]))
    reject('original_failure_promoted', 'identity', lambda d: d['failed_native_attempts'][0].update(status='passed'))
    reject('unsupported_failure_cause', 'identity', lambda d: d['failed_native_attempts'][0].update(cause='known hardware failure'))
    reject('incidental_file_promoted', 'identity', lambda d: d['incidental_outputs']['incidental_outputs'][0].update(accepted_for_delivery=True))
    reject('incidental_file_claims_decode', 'identity', lambda d: d['incidental_outputs']['incidental_outputs'][0].update(full_decode='passed'))
    reject('preservation_pending', 'preservation', lambda d: d.update(status='pending'))
    reject('preservation_bound_wrong_snapshot', 'preservation', lambda d: d['identity_snapshot'].update(sha256='0' * 64))
    reject('preservation_bound_wrong_source_equivalence', 'preservation', lambda d: d['public_source_equivalence'].update(sha256='0' * 64))
    for key in ('all_volumes_saved', 'all_saved_files_have_local_identity_metadata', 'all_volume_identities_rechecked_after_save', 'concatenated_saved_volume_identities_match_archive', 'all_required_output_identities_accounted_for'):
        reject(key + '_false', 'preservation', lambda d, key=key: d.update({key: False}))
    reject('archive_integrity_false', 'preservation', lambda d: d['archive'].update(all_member_crc_sha256_bytes_verified=False))
    reject('archive_member_count_conflict', 'preservation', lambda d: d['archive'].update(member_count=1))
    reject('volume_missing', 'preservation', lambda d: d['ordered_volumes'].pop())
    reject('volume_duplicate', 'preservation', lambda d: d['ordered_volumes'].append(copy.deepcopy(d['ordered_volumes'][0])))
    reject('volume_order_wrong', 'preservation', lambda d: d['ordered_volumes'][1].update(order=1))
    reject('volume_offset_wrong', 'preservation', lambda d: d['ordered_volumes'][1].update(offset=0))
    reject('volume_size_wrong', 'preservation', lambda d: d['ordered_volumes'][1].update(bytes=24999999))
    reject('volume_not_saved', 'preservation', lambda d: d['ordered_volumes'][1].update(status='pending'))
    reject('restore_manifest_not_saved', 'preservation', lambda d: d['reconstruction_manifest'].update(status='pending'))
    reject('preserved_output_missing', 'preservation', lambda d: d['new_required_outputs'].pop())
    reject('preserved_output_duplicate', 'preservation', lambda d: d['new_required_outputs'].append(copy.deepcopy(d['new_required_outputs'][0])))
    reject('preserved_output_size_changed', 'preservation', lambda d: d['new_required_outputs'][0].update(bytes=1))
    reject('preserved_output_member_traversal', 'preservation', lambda d: d['new_required_outputs'][0].update(archive_member='../private.mp4'))
    reject('preserved_failed_member_omitted', 'preservation', lambda d: d.update(failed_artifacts_preserved_separately=[]))
    reject('incidental_bytes_claimed_retained', 'preservation', lambda d: d['incidental_intermediates'].update(bytes_retained=True))
    reject('private_outputs_claimed_public', 'preservation', lambda d: d['privacy'].update(new_public_media_delivery_performed=True))
    reject('preservation_before_identity_snapshot', 'preservation', lambda d: d.update(completed_at_utc='2020-01-01T00:00:00+00:00'))
    reject('pr49_font_substituted', 'inputs', lambda d: d.update(font_substitution=True))
    reject('pr49_input_missing', 'inputs', lambda d: d['inputs'].pop())
    reject('pr49_preservation_pending', 'inputs', lambda d: d['durable_preservation'].update(status='pending'))
    reject('pr49_volume_offset_wrong', 'inputs', lambda d: d['durable_preservation']['volumes'][1].update(offset=0))
    for key in addendum['counts']:
        if type(addendum['counts'][key]) is int:
            reject('addendum_count_' + key, 'addendum', lambda d, key=key: d['counts'].update({key: d['counts'][key] + 1}))
    reject('addendum_input_claims_original_retrieval', 'addendum', lambda d: d['additional_input_objects'][0].update(historical_original_retrieval=True))
    reject('addendum_loses_posthoc_qualification', 'addendum', lambda d: d.update(room_verification_qualification='All native runs completed successfully'))
    reject('projection_summary_removed', 'projection', lambda d: d.pop('retained_execution_availability'))
    reject('projection_new_outputs_missing', 'projection', lambda d: d['retained_outputs'].pop())
    reject('projection_new_outputs_duplicate', 'projection', lambda d: d['retained_outputs'].append(copy.deepcopy(d['retained_outputs'][0])))
    reject('projection_private_output_link', 'projection', lambda d: d['retained_outputs'][0].update(links=[{'href': '../private.mp4', 'label': 'Play'}]))
    reject('projection_private_input_link', 'projection', lambda d: d['retained_inputs'][0].update(links=[{'href': '../private.wav'}]))
    reject('projection_retained_byte_size', 'projection', lambda d: d['retained_outputs'][0].update(bytes=1))
    reject('projection_retained_decode_status', 'projection', lambda d: d['retained_outputs'][0].update(decode='pending'))
    reject('projection_retained_count', 'projection', lambda d: d['retained_execution_availability']['counts'].update(new_required_output_identities=36))
    later_ref = lambda d: next(r for r in d['expectations'] if r.get('reproduction_scope') == 'retained_native_execution')
    reject('projection_later_reference_still_missing', 'projection', lambda d: later_ref(d).update(status='unavailable'))
    reject('projection_later_reference_wrong_hash', 'projection', lambda d: later_ref(d).update(matched_sha256='0' * 64))
    reject('projection_later_reference_wrong_scope', 'projection', lambda d: later_ref(d).update(reproduction_scope='baseline'))
    reject('projection_later_reference_original_retrieval', 'projection', lambda d: later_ref(d).update(historical_original_retrieval=True))
    reject('projection_later_reference_size', 'projection', lambda d: later_ref(d).update(expected_bytes=1))
    reject('projection_baseline_summary_changed', 'projection', lambda d: d['reproduction_availability']['counts'].update(supplemental_new_unique_outputs=59))
    reject('projection_baseline_rows_changed', 'projection', lambda d: d['reproductions'][0].update(bytes=1))
    report = {'schema_version': 'god-here.retained-availability-probes.v1',
        'status': 'passed' if all(r['passed'] for r in results) else 'failed',
        'scope': 'Deterministic metadata-only positive and corruption probes over actual completed receipts. No fixture is installed as production evidence; no media, native execution, network or deployment is tested.',
        'inputs': descriptors, 'addendum': {'path': ADDENDUM_PATH, 'sha256': addendum_sha, 'bytes': len(raw)},
        'projection_sha256': hashlib.sha256(projection_raw).hexdigest(),
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'checks': len(results), 'passed': sum(r['passed'] for r in results), 'failed': sum(not r['passed'] for r in results), 'results': results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('status', 'checks', 'passed', 'failed')}, indent=2))
    for row in results:
        if not row['passed']:
            print(json.dumps(row))
    raise SystemExit(0 if report['status'] == 'passed' else 1)


if __name__ == '__main__':
    main()
