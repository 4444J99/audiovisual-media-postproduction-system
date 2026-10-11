#!/usr/bin/env python3
"""Deterministic metadata-only regression probes for the recovery checkpoint.

Copies committed metadata to a temporary directory. Deliberately corrupts one
invariant at a time, preserving hash bindings so semantic failures are tested.
Synthetic builder fixtures are not delivery evidence. No network or media bytes
are accessed, and repository files are never changed by these probes.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from reproduction_availability import ADDENDUM_PATH, RECEIPT_PATH as REPRODUCTION_RECEIPT_PATH


CHECKPOINT = 'manifests/acceptance/god-here-consolidation-checkpoint.json'
PUBLICATION = 'manifests/acceptance/god-here-workbench-publication.json'
CATALOG = 'manifests/artifacts/god-here-recovery-catalog.json'
EXPECTATIONS = 'manifests/artifacts/god-here-recovery-expectations.json'
PROJECTION = 'web/recovery/catalog.json'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')


def run(command):
    result = subprocess.run(command, text=True, capture_output=True, timeout=30)
    try:
        data = json.loads(result.stdout)
        errors = data.get('errors', [])
    except json.JSONDecodeError:
        data = None
        errors = [result.stderr.strip().splitlines()[-1]] if result.stderr.strip() else []
    return {'exit_code': result.returncode, 'status': data.get('status') if data else None, 'errors': errors, 'reported_checks': data.get('checks') if data else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scratch-root', type=Path, help='Optional parent for temporary metadata copies')
    args = parser.parse_args()
    root = args.root.resolve()
    script_dir = Path(__file__).resolve().parent
    results = []

    with tempfile.TemporaryDirectory(prefix='god-here-negative-probes-', dir=args.scratch_root) as temporary:
        work = Path(temporary)
        fixture = work / 'repository'
        for relative in ('manifests', 'docs/recovery/evidence', 'docs/engineering-integration'):
            source = root / relative
            if source.is_dir():
                shutil.copytree(source, fixture / relative)
        for relative in (PROJECTION, 'web/recovery/index.html', 'web/recovery/recovery.js', 'web/recovery/recovery.css'):
            (fixture / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / relative, fixture / relative)
        for test in read(fixture / CHECKPOINT).get('tests', []):
            relative = test.get('evidence_path')
            if relative and not (fixture / relative).is_file():
                source = (root / relative).resolve()
                if not source.is_relative_to(root) or not source.is_file():
                    raise ValueError('Invalid baseline test-evidence path')
                (fixture / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, fixture / relative)
        forbidden = {'.mp4', '.m4a', '.mov', '.wav', '.flac', '.mp3', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.zip', '.tar'}
        if any(p.suffix.lower() in forbidden for p in fixture.rglob('*') if p.is_file()):
            raise ValueError('Probe metadata fixture unexpectedly contains media or an archive')
        original = {str(p.relative_to(fixture)): p.read_bytes() for p in fixture.rglob('*') if p.is_file()}
        checkpoint = read(fixture / CHECKPOINT)
        publication = read(fixture / PUBLICATION)
        text_receipt_path = publication['text_delivery']['evidence']['path']
        supplement_path = checkpoint['image_validation_supplement']['path']
        receipt_entry = publication['registered_delivery']['full_verification_evidence']
        receipt_path = receipt_entry['path']
        if read(fixture / receipt_path).get('status') != 'verified':
            raise ValueError('These completion probes require a consistent completed baseline receipt')
        verify_command = [sys.executable, str(script_dir / 'verify_checkpoint.py'), '--root', str(fixture)]
        baseline = run(verify_command)
        results.append({'case': 'checkpoint_positive_control', 'expected': 'passed', 'passed': baseline['exit_code'] == 0 and baseline['status'] == 'passed', **baseline})
        if not results[-1]['passed']:
            raise ValueError('Baseline checkpoint is inconsistent; no negative probes were run')

        def restore():
            for relative, data in original.items():
                target = fixture / relative
                if target.read_bytes() != data:
                    target.write_bytes(data)

        def rebind(rebind_text=True):
            # Rebind changed fixture references; a rejection must name the actual
            # invariant instead of succeeding merely through a stale file hash.
            json_paths = [fixture / p for p in original if p.endswith('.json')]
            for unused in range(8):
                changed = False
                for path in json_paths:
                    value = read(path)
                    before = copy.deepcopy(value)

                    def visit(node):
                        if isinstance(node, dict):
                            if {'path', 'sha256', 'bytes'} <= node.keys() and isinstance(node['path'], str):
                                target = fixture / node['path']
                                if node['path'] in original and target.is_file():
                                    data = target.read_bytes()
                                    node['sha256'], node['bytes'] = sha(data), len(data)
                            for child in node.values():
                                visit(child)
                        elif isinstance(node, list):
                            for child in node:
                                visit(child)

                    visit(value)
                    if rebind_text and path == fixture / text_receipt_path:
                        # Only synthetic fixture response assertions are rebound.
                        # Production HTTP evidence is never edited by this suite.
                        recovery_sources = {
                            '/recovery/': 'web/recovery/index.html', '/recovery/catalog.json': PROJECTION,
                            '/recovery/recovery.js': 'web/recovery/recovery.js', '/recovery/recovery.css': 'web/recovery/recovery.css',
                        }
                        for row in value.get('checks', []):
                            relative = recovery_sources.get(row.get('route'))
                            if row.get('kind') == 'exact_text_bytes' and relative:
                                data = (fixture / relative).read_bytes()
                                row['expected_sha256'] = row['actual_sha256'] = sha(data)
                                row['expected_bytes'] = row['observed_bytes'] = len(data)
                    if path == fixture / PROJECTION:
                        if value.get('image_validation'):
                            value['image_validation']['supplement_sha256'] = sha((fixture / supplement_path).read_bytes())
                        if value.get('delivery', {}).get('room_media_receipt_sha256'):
                            value['delivery']['room_media_receipt_sha256'] = sha((fixture / receipt_path).read_bytes())
                        if value.get('reproduction_availability'):
                            value['reproduction_availability']['addendum_sha256'] = sha((fixture / ADDENDUM_PATH).read_bytes())
                            value['reproduction_availability']['receipt_sha256'] = sha((fixture / REPRODUCTION_RECEIPT_PATH).read_bytes())
                        for row in value.get('objects', []):
                            if row.get('baseline_reproduction'):
                                row['baseline_reproduction']['receipt_sha256'] = sha((fixture / REPRODUCTION_RECEIPT_PATH).read_bytes())
                    if value != before:
                        write(path, value)
                        changed = True
                if not changed:
                    return
            raise ValueError('Fixture evidence bindings did not converge')

        def checkpoint_case(name, relative, mutate, error_fragment):
            restore()
            value = read(fixture / relative)
            mutate(value)
            write(fixture / relative, value)
            rebind(rebind_text=relative != text_receipt_path)
            observed = run(verify_command)
            rejected = observed['exit_code'] != 0 and observed['status'] == 'failed' and any(error_fragment in message for message in observed['errors'])
            results.append({'case': name, 'expected': 'semantic_rejection', 'expected_error_fragment': error_fragment, 'passed': rejected, **observed})

        def first_image(value):
            return next(row for row in value['objects'] if row['type'] == 'image')

        def first_failed_av(value):
            return next(row for row in value['objects'] if row['type'] in {'audio', 'video'} and row['decode'] == 'failed')

        checkpoint_case('missing_image_projection', PROJECTION, lambda d: d.pop('image_validation'), 'Image supplement must be bound')
        checkpoint_case('projected_image_type_changed', PROJECTION, lambda d: first_image(d).__setitem__('type', 'code'), 'Workbench object fields differ')
        checkpoint_case('failed_av_marked_passed', PROJECTION, lambda d: first_failed_av(d).__setitem__('decode', 'passed'), 'Workbench decode differs')
        checkpoint_case('projected_size_changed', PROJECTION, lambda d: d['objects'][0].__setitem__('bytes', d['objects'][0]['bytes'] + 1), 'Workbench object fields differ')
        checkpoint_case('projected_occurrences_changed', PROJECTION, lambda d: d['objects'][0].__setitem__('occurrences', d['objects'][0]['occurrences'] + 1), 'Workbench object fields differ')
        checkpoint_case('projected_identity_repeated', PROJECTION, lambda d: d['objects'].append(copy.deepcopy(d['objects'][0])), 'Workbench repeats object identities')
        checkpoint_case('checkpoint_frozen_total_changed', CHECKPOINT, lambda d: d['catalog_counts'].__setitem__('unique_sha256_objects', d['catalog_counts']['unique_sha256_objects'] + 1), 'Checkpoint frozen counts differ')
        checkpoint_case('publication_registered_count_changed', PUBLICATION, lambda d: d['registered_delivery'].__setitem__('registered_count', d['registered_delivery']['registered_count'] - 1), 'Publication registration totals differ')
        checkpoint_case('publication_registered_bytes_changed', PUBLICATION, lambda d: d['registered_delivery'].__setitem__('registered_bytes', d['registered_delivery']['registered_bytes'] - 1), 'Publication registration totals differ')
        checkpoint_case('checkpoint_delivery_count_changed', CHECKPOINT, lambda d: d['current_workbench_delivery'].__setitem__('registered_media_verified', d['current_workbench_delivery']['registered_media_verified'] - 1), 'Checkpoint delivery totals differ')
        checkpoint_case('complete_receipt_missing_row', receipt_path, lambda d: d['files'].pop(), 'Complete receipt does not cover')
        checkpoint_case('complete_receipt_repeated_id', receipt_path, lambda d: d['files'].append(copy.deepcopy(d['files'][0])), 'Duplicate completed media ID')
        checkpoint_case('complete_receipt_false_download_hash', receipt_path, lambda d: d['files'][0].__setitem__('download_sha256', '0' * 64), 'Full-download identity differs')
        checkpoint_case('complete_receipt_missing_finish', receipt_path, lambda d: d.pop('finished_at'), 'Complete receipt has unfinished work')

        checkpoint_case('text_receipt_missing_route', text_receipt_path, lambda d: d['checks'].pop(), 'Text receipt repeats or omits a required route')
        checkpoint_case('text_receipt_repeated_route', text_receipt_path, lambda d: d['checks'].__setitem__(1, copy.deepcopy(d['checks'][0])), 'Text receipt repeats or omits a required route')
        checkpoint_case('text_body_hash_mismatch', text_receipt_path, lambda d: d['checks'][0].__setitem__('actual_sha256', '0' * 64), 'Text response identity or byte count differs')
        checkpoint_case('text_body_count_mismatch', text_receipt_path, lambda d: d['checks'][0].__setitem__('observed_bytes', d['checks'][0]['expected_bytes'] + 1), 'Text response identity or byte count differs')
        checkpoint_case('text_body_incomplete', text_receipt_path, lambda d: d['checks'][0].__setitem__('response_complete', False), 'Text response is incomplete or has an unexpected status')
        checkpoint_case('text_receipt_falsely_passed_row', text_receipt_path, lambda d: d['checks'][0].__setitem__('status', 'running'), 'Text receipt contains an unfinished or failed check')
        checkpoint_case('text_summary_count_changed', PUBLICATION, lambda d: d['text_delivery'].__setitem__('checks_passed', d['text_delivery']['checks_passed'] - 1), 'Published text counters differ')
        checkpoint_case('text_summary_source_changed', PUBLICATION, lambda d: d['text_delivery'].__setitem__('source_commit', '0' * 40), 'Text publication source differs')
        checkpoint_case('text_summary_environment_changed', PUBLICATION, lambda d: d['text_delivery'].__setitem__('tested_environment_revision', d['text_delivery']['tested_environment_revision'] - 1), 'Text publication environment differs')
        checkpoint_case('text_redirect_target_changed', text_receipt_path, lambda d: next(row for row in d['checks'] if row['kind'] == 'canonical_redirect').__setitem__('actual_location', '/wrong-fixture-target/'), 'Canonical redirect status or target differs')
        restore()
        (fixture / 'web/recovery/recovery.js').write_bytes(original['web/recovery/recovery.js'] + b'\n// Deliberately changed temporary source fixture.\n')
        rebind(rebind_text=False)
        observed = run(verify_command)
        fragment = 'Published recovery text differs from current repository source: /recovery/recovery.js'
        results.append({'case': 'unpublished_recovery_source_changed', 'expected': 'semantic_rejection', 'expected_error_fragment': fragment, 'passed': observed['exit_code'] != 0 and observed['status'] == 'failed' and any(fragment in message for message in observed['errors']), **observed})
        restore()

        def image_cases():
            return [
                ('repeated_reused_image', lambda d: d['reused_prior_pass_sha256s'].append(d['reused_prior_pass_sha256s'][0]), 'reused prior passes repeats an identity'),
                ('repeated_new_image', lambda d: d['new_image_results'].append(copy.deepcopy(d['new_image_results'][0])), 'new image results repeat an identity'),
                ('invented_reused_image', lambda d: d['reused_prior_pass_sha256s'].__setitem__(0, '0' * 64), 'reused pass lacks frozen passing evidence'),
                ('processed_image_total_changed', lambda d: d['counts'].__setitem__('new_image_identities_processed', d['counts']['new_image_identities_processed'] + 1), 'count differs: new_image_identities_processed'),
                ('reused_image_total_changed', lambda d: d['counts'].__setitem__('prior_image_passes_reused', d['counts']['prior_image_passes_reused'] + 1), 'count differs: prior_image_passes_reused'),
                ('available_image_total_changed', lambda d: d['counts'].__setitem__('unique_image_identities_available', d['counts']['unique_image_identities_available'] + 1), 'count differs: unique_image_identities_available'),
                ('pending_image_total_changed', lambda d: d['counts'].__setitem__('new_image_identities_not_fully_decoded', d['counts']['new_image_identities_not_fully_decoded'] + 1), 'count differs: new_image_identities_not_fully_decoded'),
                ('missing_frame_size_evidence', lambda d: d['new_image_results'][0].__setitem__('decoded_frame_sizes', []), 'decoded frame sizes do not cover every frame'),
                ('missing_frame_mode_evidence', lambda d: d['new_image_results'][0].__setitem__('decoded_frame_modes', []), 'decoded frame modes do not cover every frame'),
                ('boolean_frame_count', lambda d: d['new_image_results'][0].__setitem__('frame_count', True), 'pass lacks complete frame evidence'),
                ('invented_container_membership', lambda d: d['new_image_results'][0].__setitem__('verified_container_sha256s', ['0' * 64]), 'verified containers differ'),
                ('container_occurrence_total_changed', lambda d: d['containers'][0].__setitem__('image_occurrences', d['containers'][0]['image_occurrences'] + 1), 'container occurrence count differs'),
                ('unknown_image_status', lambda d: d['new_image_results'][0].__setitem__('status', 'complete'), 'unknown image result status'),
                ('missing_outstanding_image', lambda d: d['outstanding_image_sha256s_in_available_archives'].clear(), 'outstanding image list differs'),
            ]

        for name, mutate, fragment in image_cases():
            checkpoint_case('checkpoint_' + name, supplement_path, mutate, fragment)
        restore()

        reproduction_present = ADDENDUM_PATH in original
        if reproduction_present:
            new_output_path = next(row['output_paths'][0] for row in read(fixture / ADDENDUM_PATH)['output_objects'] if not row['present_in_frozen_catalog'])

            def conflicting_reproduction_size(value):
                row = copy.deepcopy(next(row for row in value['files'] if row['path'] == new_output_path))
                row['path'] = 'audio/negative-probe-duplicate.wav'
                row['bytes'] += 1
                value['files'].append(row)

            def first_reproduced_reference(value):
                return next(row for row in value['expectations'] if row['status'] == 'exact_hash_reproduced')

            def reproduction_cases():
                return [
                    ('repeated_reproduced_output_path', REPRODUCTION_RECEIPT_PATH, lambda d: d['files'].append(copy.deepcopy(d['files'][0])), 'output path is unsafe or repeated'),
                    ('reproduced_hash_size_conflict', REPRODUCTION_RECEIPT_PATH, conflicting_reproduction_size, 'same output hash has conflicting size or type'),
                    ('reproduction_private_preservation_incomplete', REPRODUCTION_RECEIPT_PATH, lambda d: d['durable_preservation'].__setitem__('status', 'incomplete'), 'durable private preservation is incomplete'),
                    ('reproduction_false_media_decode', REPRODUCTION_RECEIPT_PATH, lambda d: next(row for row in d['files'] if row['path'].endswith('.wav')).__setitem__('status', 'bytes_inventoried'), 'output status contradicts its technical gate'),
                    ('reproduction_output_count_changed', REPRODUCTION_RECEIPT_PATH, lambda d: d['verification'].__setitem__('generated_file_count', d['verification']['generated_file_count'] + 1), 'generated file count differs'),
                    ('reproduction_source_size_changed', REPRODUCTION_RECEIPT_PATH, lambda d: d['source'].__setitem__('bytes', d['source']['bytes'] + 1), 'source identity differs from the frozen catalog'),
                    ('reproduction_missing_candidate_hashes', REPRODUCTION_RECEIPT_PATH, lambda d: d['historical_audio_candidates'].__setitem__('MISSING', {'byte_identical': True}), 'historical audio candidate labels differ from the fixed baseline'),
                    ('reproduction_candidate_hash_fields_absent', REPRODUCTION_RECEIPT_PATH, lambda d: d['historical_audio_candidates'].__setitem__('A', {'byte_identical': True}), 'historical audio hash assertion differs'),
                    ('addendum_new_identity_count_changed', ADDENDUM_PATH, lambda d: d['counts'].__setitem__('supplemental_new_unique_outputs', d['counts']['supplemental_new_unique_outputs'] + 1), 'addendum differs from bound evidence: counts'),
                    ('addendum_boolean_retrieval_count', ADDENDUM_PATH, lambda d: d['counts'].__setitem__('historical_originals_retrieved_by_this_operation', False), 'addendum differs from bound evidence: counts'),
                    ('addendum_output_size_changed', ADDENDUM_PATH, lambda d: d['output_objects'][0].__setitem__('bytes', d['output_objects'][0]['bytes'] + 1), 'addendum differs from bound evidence: output_objects'),
                    ('addendum_expected_hash_changed', ADDENDUM_PATH, lambda d: d['expectation_updates'][0].__setitem__('expected_sha256', '0' * 64), 'addendum differs from bound evidence: expectation_updates'),
                    ('addendum_claims_original_retrieval', ADDENDUM_PATH, lambda d: d['provenance'].__setitem__('historical_original_retrieval', True), 'addendum differs from bound evidence: provenance'),
                ]

            for name, relative, mutate, fragment in reproduction_cases():
                checkpoint_case('checkpoint_' + name, relative, mutate, fragment)
            checkpoint_case('missing_reproduction_projection', PROJECTION, lambda d: d.pop('reproduction_availability'), 'Reproduction availability must be bound')
            checkpoint_case('projected_reproduction_identity_repeated', PROJECTION, lambda d: d['reproductions'].append(copy.deepcopy(d['reproductions'][0])), 'projection reproduced identities, statuses or private-link rules differ')
            checkpoint_case('projected_reproduction_size_changed', PROJECTION, lambda d: d['reproductions'][0].__setitem__('bytes', d['reproductions'][0]['bytes'] + 1), 'projection reproduced identities, statuses or private-link rules differ')
            checkpoint_case('projected_private_output_link_added', PROJECTION, lambda d: d['reproductions'][0]['links'].append({'href': '../private-output.mp4', 'label': 'Synthetic invalid link'}), 'projection reproduced identities, statuses or private-link rules differ')
            checkpoint_case('projected_reproduction_claims_original_retrieval', PROJECTION, lambda d: d['reproductions'][0].__setitem__('historical_original_retrieval', True), 'projection reproduced identities, statuses or private-link rules differ')
            checkpoint_case('exact_reproduction_still_unavailable', PROJECTION, lambda d: first_reproduced_reference(d).__setitem__('status', 'unavailable'), 'projection reference availability differs')
            checkpoint_case('reproduction_remaining_count_stale', PROJECTION, lambda d: d['reproduction_availability']['counts'].__setitem__('remaining_unmatched_expected_hashes', 194), 'projection reproduction summary differs')
            checkpoint_case('reproduction_existing_identity_annotation_missing', PROJECTION, lambda d: next(row for row in d['objects'] if row.get('baseline_reproduction')).pop('baseline_reproduction'), 'projection baseline reproduction annotation differs')
            checkpoint_case('reproduction_reference_id_repeated', PROJECTION, lambda d: d['expectations'].append(copy.deepcopy(first_reproduced_reference(d))), 'projection reference IDs are missing or repeated')
            restore()

        # The builder fixture deliberately has no source media. Its registrations
        # are unrelated synthetic rows, so even the valid metadata control opens
        # no media file and enables no media link.
        site = work / 'synthetic-site'
        (site / 'public').mkdir(parents=True)
        (site / 'public/index.html').write_text('<!doctype html><title>Metadata probe fixture</title>')
        registry = [{'id': 'probe-a', 'path': '/probe-a.flac', 'bytes': 7, 'sha256': '1' * 64}, {'id': 'probe-b', 'path': '/probe-b.mp4', 'bytes': 11, 'sha256': '2' * 64}]
        registry_path = site / 'lib/room-media-manifest.json'
        write(registry_path, registry)
        synthetic_receipt = {
            'schema_version': 'test_fixture_not_delivery_evidence', 'origin': 'https://god-here-five-realities.ajpadavano.chatgpt.site',
            'manifest_sha256': sha(registry_path.read_bytes()), 'verification': 'full', 'status': 'verified',
            'selected_ids': ['probe-a', 'probe-b'], 'selected_count': 2, 'verified_count': 2,
            'selected_bytes': 18, 'verified_bytes': 18, 'finished_at': '2000-01-01T00:00:00+00:00', 'unprocessed_ids': [],
            'files': [{**row, 'status': 'verified', 'head_verified': True, 'range_verified': True, 'full_download_verified': True, 'download_bytes': row['bytes'], 'download_sha256': row['sha256']} for row in registry],
        }
        synthetic_path = work / 'synthetic-receipt.json'
        write(synthetic_path, synthetic_receipt)
        builder_command = [sys.executable, str(script_dir / 'build_workbench_index.py'), '--catalog', str(fixture / CATALOG), '--expectations', str(fixture / EXPECTATIONS), '--image-validation-supplement', str(fixture / supplement_path), '--workbench-root', str(site), '--room-media-receipt', str(synthetic_path), '--output', str(work / 'builder-output.json')]
        baseline = run(builder_command)
        results.append({'case': 'builder_metadata_positive_control', 'expected': 'passed', 'passed': baseline['exit_code'] == 0, **baseline})
        if not results[-1]['passed']:
            raise ValueError('Baseline builder metadata fixture failed')

        for name, mutate, fragment in image_cases():
            restore()
            value = read(fixture / supplement_path)
            mutate(value)
            write(fixture / supplement_path, value)
            observed = run(builder_command)
            results.append({'case': 'builder_' + name, 'expected': 'semantic_rejection', 'expected_error_fragment': fragment, 'passed': observed['exit_code'] != 0 and any(fragment in message for message in observed['errors']), **observed})
        restore()

        if reproduction_present:
            for name, relative, mutate, fragment in reproduction_cases():
                restore()
                value = read(fixture / relative)
                mutate(value)
                write(fixture / relative, value)
                rebind()
                observed = run(builder_command)
                results.append({'case': 'builder_' + name, 'expected': 'semantic_rejection', 'expected_error_fragment': fragment, 'passed': observed['exit_code'] != 0 and any(fragment in message for message in observed['errors']), **observed})
            restore()

        media_cases = [
            ('partial_complete_batch', lambda d: d['files'].pop(), 'inconsistent coverage'),
            ('duplicate_complete_row', lambda d: d['files'].__setitem__(1, copy.deepcopy(d['files'][0])), 'duplicate, unfinished or mismatched'),
            ('duplicate_selected_id', lambda d: d['selected_ids'].__setitem__(1, d['selected_ids'][0]), 'inconsistent coverage'),
            ('false_complete_count', lambda d: d.__setitem__('verified_count', 3), 'inconsistent coverage'),
            ('false_complete_bytes', lambda d: d.__setitem__('verified_bytes', 19), 'inconsistent coverage'),
            ('missing_complete_finish', lambda d: d.pop('finished_at'), 'inconsistent coverage'),
            ('unfinished_complete_row', lambda d: d['files'][0].__setitem__('status', 'running'), 'duplicate, unfinished or mismatched'),
            ('false_complete_download', lambda d: d['files'][0].__setitem__('download_sha256', '0' * 64), 'duplicate, unfinished or mismatched'),
        ]
        for name, mutate, fragment in media_cases:
            value = copy.deepcopy(synthetic_receipt)
            mutate(value)
            write(synthetic_path, value)
            observed = run(builder_command)
            results.append({'case': 'builder_' + name, 'expected': 'semantic_rejection', 'expected_error_fragment': fragment, 'passed': observed['exit_code'] != 0 and any(fragment in message for message in observed['errors']), **observed})
        write(synthetic_path, synthetic_receipt)
        duplicate_registry = copy.deepcopy(registry)
        duplicate_registry[1]['path'] = duplicate_registry[0]['path']
        write(registry_path, duplicate_registry)
        observed = run(builder_command)
        results.append({'case': 'builder_duplicate_registry_path', 'expected': 'semantic_rejection', 'expected_error_fragment': 'Media registry repeats a path or ID', 'passed': observed['exit_code'] != 0 and any('Media registry repeats a path or ID' in message for message in observed['errors']), **observed})

        input_hashes = {relative: sha(original[relative]) for relative in (CATALOG, EXPECTATIONS, CHECKPOINT, PUBLICATION, PROJECTION, supplement_path, receipt_path, text_receipt_path, 'web/recovery/index.html', 'web/recovery/recovery.js', 'web/recovery/recovery.css')}
        if reproduction_present:
            input_hashes.update({relative: sha(original[relative]) for relative in (ADDENDUM_PATH, REPRODUCTION_RECEIPT_PATH)})
        script_hashes = {path.name: sha(path.read_bytes()) for path in [script_dir / name for name in ('verify_checkpoint.py', 'build_workbench_index.py', 'image_supplement.py', 'reproduction_availability.py', 'verify_deployed_text.py', 'probe_checkpoint_negatives.py')]}
    report = {'schema_version': 'god-here.checkpoint-negative-probes.v1', 'status': 'passed' if all(row['passed'] for row in results) else 'failed', 'scope': 'Deterministic temporary metadata mutations and synthetic builder fixtures; no network, media access, decoding, publication, or artistic acceptance.', 'repository_files_modified': False, 'input_sha256': input_hashes, 'script_sha256': script_hashes, 'positive_controls': sum(row['expected'] == 'passed' for row in results), 'negative_cases': sum(row['expected'] == 'semantic_rejection' for row in results), 'cases_passed': sum(row['passed'] for row in results), 'cases_failed': sum(not row['passed'] for row in results), 'results': results}
    write(args.output, report)
    print(json.dumps({'status': report['status'], 'positive_controls': report['positive_controls'], 'negative_cases': report['negative_cases'], 'cases_passed': report['cases_passed'], 'cases_failed': report['cases_failed']}, indent=2))
    raise SystemExit(report['status'] != 'passed')


if __name__ == '__main__':
    main()
