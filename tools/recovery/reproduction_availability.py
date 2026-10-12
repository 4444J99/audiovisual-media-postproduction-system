#!/usr/bin/env python3
"""Build and validate private reproduction availability over frozen metadata.

Only receipts and JSON indexes are read. This does not recover historical
originals, open media, infer artistic acceptance, or enable playback links.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


ADDENDUM_PATH = 'manifests/artifacts/god-here-reproduction-availability.json'
RECEIPT_PATH = 'manifests/acceptance/god-here-baseline-reproduction.json'
EXCLUDED_CATEGORIES = {'test_or_example', 'recovered_document_test_or_example', 'parameterized', 'runtime_export_contract'}
CURRENT_STATUS = 'exact_hash_reproduced'
QUALIFICATION = ('Exact matching bytes are now privately preserved through execution of the retained baseline recipe. '
                 'This is reproduction evidence; this operation did not retrieve the historical original copy. '
                 'Artistic acceptance and public delivery of the reproduced copy are not established.')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError('Reproduction availability: ' + message)


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def same_json(left, right):
    """Compare JSON values without treating booleans as integer counts."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return set(left) == set(right) and all(same_json(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(same_json(a, b) for a, b in zip(left, right))
    return left == right


def safe_relative(value):
    return (isinstance(value, str) and bool(value) and '\\' not in value
            and not PurePosixPath(value).is_absolute() and '..' not in PurePosixPath(value).parts
            and ':' not in value)


def derive_addendum(receipt, catalog, expectations, catalog_sha256, expectations_sha256, receipt_sha256, receipt_bytes):
    require(receipt.get('schema') == 'god-here.baseline-reproduction-proof.v1', 'unsupported receipt schema')
    require(receipt.get('status') == 'technically_reproduced_and_verified', 'recipe is not technically complete')
    require(receipt.get('production_code_modified') is False, 'baseline code was modified')
    require(receipt.get('artist_acceptance') == 'not_assessed' and receipt.get('listening_acceptance') == 'not_assessed', 'receipt grants unsupported acceptance')
    require(re.fullmatch(r'[0-9a-f]{40}', receipt.get('pinned_revision', '')) is not None, 'missing pinned code revision')
    objects = {row['sha256']: row for row in catalog['objects']}
    require(len(objects) == len(catalog['objects']), 'frozen object identities repeat')
    source = receipt['source']
    source_obj = objects.get(source.get('sha256'), {})
    require(source.get('unchanged_after_execution') is True and integer(source.get('bytes'), 1)
            and source_obj.get('bytes') == source['bytes'], 'source identity differs from the frozen catalog')
    steps = receipt['completed_attempt']['steps']
    require([row.get('step') for row in steps] == ['validate', 'audio', 'render', 'finish']
            and all(type(row.get('exit_code')) is int and row['exit_code'] == 0
                    and type(row.get('stderr_bytes')) is int and row['stderr_bytes'] == 0 for row in steps), 'recipe steps are missing, repeated, or unsuccessful')
    require(receipt['completed_attempt'].get('worktree_clean') is True and bool(receipt['completed_attempt'].get('finished_at_utc')), 'completed attempt lacks clean completion evidence')
    durable = receipt['durable_preservation']
    require(durable.get('status') == 'complete' and durable.get('all_volumes_saved') is True
            and durable.get('complete_archive_member_crc_and_sha256_verified') is True
            and valid_hash(durable.get('archive_sha256')) and integer(durable.get('archive_bytes'), 1), 'durable private preservation is incomplete')
    verification = receipt['verification']
    stabilization = verification['post_exit_stabilization']
    require(verification.get('files_stable_through_complete_validation') is True
            and stabilization.get('passed') is True and stabilization.get('changed_paths') == [], 'output identities did not remain stable')

    paths, grouped = {}, {}
    suffix_types = {'.wav': 'audio', '.m4a': 'audio', '.mp4': 'video', '.json': 'metadata'}
    for row in receipt['files']:
        path, sha, size = row['path'], row['sha256'], row['bytes']
        require(safe_relative(path) and path not in paths, 'output path is unsafe or repeated')
        require(valid_hash(sha) and integer(size, 1), 'output hash or size is invalid')
        suffix = PurePosixPath(path).suffix.lower()
        require(suffix in suffix_types, 'unsupported output type')
        kind = suffix_types[suffix]
        required_status = 'bytes_inventoried' if kind == 'metadata' else 'passed'
        require(row.get('status') == required_status, 'output status contradicts its technical gate')
        if sha in objects:
            require(objects[sha]['bytes'] == size, 'output size conflicts with its frozen hash identity')
            require(objects[sha]['type'] == kind, 'output type conflicts with its frozen hash identity')
            require(kind == 'metadata' or objects[sha]['verification'].get('full_decode_status') != 'failed', 'reproduction contradicts a frozen decode failure')
        prior = grouped.get(sha)
        if prior:
            require(prior['bytes'] == size and prior['type'] == kind, 'same output hash has conflicting size or type')
            prior['output_paths'].append(path)
        else:
            grouped[sha] = {'sha256': sha, 'bytes': size, 'type': kind, 'output_paths': [path], 'full_decode_status': 'not_applicable' if kind == 'metadata' else 'passed', 'present_in_frozen_catalog': sha in objects, 'provenance': 'retained_baseline_recipe_reproduction', 'availability': 'privately_preserved', 'historical_original_retrieval': False, 'public_delivery': 'not_established_by_this_receipt', 'artistic_acceptance': 'not_assessed'}
        paths[path] = row
    file_types = Counter(PurePosixPath(path).suffix.lower() for path in paths if PurePosixPath(path).suffix.lower() != '.json')
    media_count = sum(file_types.values())
    require(verification.get('generated_file_count') == len(paths) and stabilization.get('initial_file_count') == len(paths), 'generated file count differs')
    require(verification.get('generated_file_bytes') == sum(row['bytes'] for row in paths.values()), 'generated byte total differs')
    require(verification.get('media_file_count') == media_count and verification.get('media_types') == dict(file_types), 'media file totals differ')
    video_paths = {path for path in paths if PurePosixPath(path).suffix.lower() == '.mp4'}
    video_records = receipt['videos']
    require(len(video_records) == len(video_paths) and {row['path'] for row in video_records} == video_paths, 'video evidence is incomplete or repeated')
    for row in video_records:
        original = paths[row['path']]
        require(row.get('sha256') == original['sha256'] and row.get('bytes') == original['bytes'] and row.get('full_decode') == 'passed', 'video evidence identity or status differs')
    require(verification.get('expected_video_count') == len(video_paths), 'expected video count differs')
    audio_candidates = receipt['historical_audio_candidates']
    require(set(audio_candidates) == {'A', 'B', 'S', 'F'}, 'historical audio candidate labels differ from the fixed baseline')
    for label, row in audio_candidates.items():
        candidate = paths.get('audio/candidate-' + label + '.wav')
        require(candidate is not None and valid_hash(row.get('actual_sha256')) and valid_hash(row.get('expected_sha256'))
                and row.get('byte_identical') is True
                and row['actual_sha256'] == row['expected_sha256'] == candidate['sha256'], 'historical audio hash assertion differs')

    expected_rows = {row['expectation_id']: row for row in expectations['expectations']}
    require(len(expected_rows) == len(expectations['expectations']), 'frozen expectation IDs repeat')
    expected_hashes = {row['expected_sha256'] for row in expected_rows.values() if row.get('expected_sha256')}
    missing_hashes = expected_hashes - set(objects)
    require(len(missing_hashes) == expectations['counts']['unique_expected_sha256s_unrecovered'], 'frozen unmatched checksum count differs')
    new_hashes = set(grouped) - set(objects)
    newly_available_expected = missing_hashes & set(grouped)
    updates = []
    for row in expected_rows.values():
        sha = row.get('expected_sha256')
        if sha not in newly_available_expected:
            continue
        output = grouped[sha]
        require(row.get('expected_bytes') is None or row['expected_bytes'] == output['bytes'], 'expected size conflicts with reproduced identity')
        require(row['status'] != 'exact_hash_recovered', 'new reproduction recounts a recovered expectation')
        updates.append({'expectation_id': row['expectation_id'], 'expected_sha256': sha, 'matched_bytes': output['bytes'], 'frozen_status': row['status'], 'current_status': CURRENT_STATUS, 'output_paths': sorted(output['output_paths']), 'availability': 'privately_preserved', 'historical_original_retrieval': False, 'qualification': QUALIFICATION})
    outputs = sorted(grouped.values(), key=lambda row: row['sha256'])
    for row in outputs:
        row['output_paths'].sort()
    new_outputs = [row for row in outputs if row['sha256'] in new_hashes]
    new_types = Counter(row['type'] for row in new_outputs)
    counts = {
        'frozen_catalog_unique_objects': catalog['counts']['unique_sha256_objects'],
        'frozen_catalog_file_occurrences': catalog['counts']['file_occurrences'],
        'reproduced_output_file_occurrences': len(paths), 'reproduced_unique_output_hashes': len(grouped),
        'reproduced_media_file_occurrences': media_count, 'reproduced_output_file_bytes': sum(row['bytes'] for row in paths.values()),
        'reproduced_identities_already_in_frozen_catalog': len(set(grouped) & set(objects)),
        'supplemental_new_unique_outputs': len(new_hashes), 'supplemental_new_output_bytes': sum(row['bytes'] for row in new_outputs),
        'supplemental_new_outputs_by_type': dict(sorted(new_types.items())),
        'supplemental_new_audio_video_decode_passes': sum(row['type'] in {'audio', 'video'} for row in new_outputs),
        'frozen_plus_this_reproduction_unique_objects': len(set(objects) | set(grouped)),
        'frozen_unmatched_expected_hashes': len(missing_hashes),
        'previously_unmatched_hashes_now_reproduced': len(newly_available_expected),
        'remaining_unmatched_expected_hashes': len(missing_hashes - set(grouped)),
        'expectation_records_with_availability_updates': len(updates), 'historical_originals_retrieved_by_this_operation': 0,
        'new_output_playback_links': 0, 'artistic_acceptance_added': 0,
    }
    return {
        'schema_version': 'god-here.reproduction-availability.v1', 'recorded_at_utc': receipt['recorded_at_utc'],
        'frozen_catalog_sha256': catalog_sha256, 'frozen_expectations_sha256': expectations_sha256, 'frozen_files_unchanged': True,
        'reproduction_receipt': {'path': RECEIPT_PATH, 'sha256': receipt_sha256, 'bytes': receipt_bytes},
        'scope': 'Additive availability of outputs from one retained baseline recipe; frozen recovery records remain unchanged. Output counts exclude custody-carrier archives/volumes and other post-snapshot source changes.',
        'provenance': {'repository': receipt['repository'], 'pinned_revision': receipt['pinned_revision'], 'source_sha256': source['sha256'], 'source_bytes': source['bytes'], 'method': 'reproduction_from_verified_source_and_pinned_code', 'historical_original_retrieval': False},
        'private_preservation': {'status': 'complete', 'archive_sha256': durable['archive_sha256'], 'archive_bytes': durable['archive_bytes'], 'public_media_links': []},
        'counts': counts, 'output_objects': outputs, 'expectation_updates': sorted(updates, key=lambda row: row['expectation_id']),
        'interpretation': QUALIFICATION,
    }


def validate_addendum(addendum, receipt, catalog, expectations, catalog_sha256, expectations_sha256, receipt_sha256, receipt_bytes):
    expected = derive_addendum(receipt, catalog, expectations, catalog_sha256, expectations_sha256, receipt_sha256, receipt_bytes)
    for key in expected:
        require(same_json(addendum.get(key), expected[key]), 'addendum differs from bound evidence: ' + key)
    require(set(addendum) == set(expected), 'addendum has unrecognized fields')
    return expected


def apply_to_projection(projection, addendum, addendum_sha256):
    require(projection.get('source_catalog_sha256') == addendum['frozen_catalog_sha256'] and projection.get('source_expectations_sha256') == addendum['frozen_expectations_sha256'], 'projection frozen bindings differ')
    output_map = {row['sha256']: row for row in addendum['output_objects']}
    summary = {'addendum_sha256': addendum_sha256, 'receipt_sha256': addendum['reproduction_receipt']['sha256'], 'counts': copy.deepcopy(addendum['counts']), 'pinned_revision': addendum['provenance']['pinned_revision'], 'availability': 'privately_preserved', 'historical_original_retrieval': False, 'artistic_acceptance': 'not_assessed', 'scope': addendum['scope']}
    projection['reproduction_availability'] = summary
    projection['reproductions'] = [{
        'sha256': row['sha256'], 'bytes': row['bytes'], 'names': row['output_paths'], 'type': row['type'],
        'occurrences': len(row['output_paths']), 'decode': row['full_decode_status'], 'links': [], 'code_url': None,
        'download_pending': False, 'availability': row['availability'], 'historical_original_retrieval': False,
        'artistic_acceptance': 'not_assessed', 'provenance': row['provenance'], 'frozen_catalog_member': False,
    } for row in addendum['output_objects'] if not row['present_in_frozen_catalog']]
    projection['reproductions'].sort(key=lambda row: (row['names'][0].casefold(), row['sha256']))
    for row in projection['objects']:
        if row['sha256'] in output_map:
            row['baseline_reproduction'] = {'receipt_sha256': summary['receipt_sha256'], 'pinned_revision': summary['pinned_revision'], 'availability': 'additional_private_copy', 'historical_original_retrieval': False}
        else:
            row.pop('baseline_reproduction', None)
    updates = {row['expectation_id']: row for row in addendum['expectation_updates']}
    for row in projection['expectations']:
        update = updates.get(row['id'])
        if update:
            row['frozen_status'] = update['frozen_status']
            row['status'] = update['current_status']
            row['matched_sha256'] = update['expected_sha256']
            row['availability'] = update['availability']
            row['historical_original_retrieval'] = False
            row['reproduced_names'] = update['output_paths']
            row['qualification'] = update['qualification']
    return projection


def validate_projection(projection, addendum, addendum_sha256, expectations, later_expectation_updates=()):
    rebuilt = apply_to_projection(copy.deepcopy(projection), addendum, addendum_sha256)
    require(same_json(projection.get('reproduction_availability'), rebuilt['reproduction_availability']), 'projection reproduction summary differs')
    require(same_json(projection.get('reproductions'), rebuilt['reproductions']), 'projection reproduced identities, statuses or private-link rules differ')
    require(len({row['sha256'] for row in projection['reproductions']}) == len(projection['reproductions']), 'projection repeats a reproduced identity')
    require(not ({row['sha256'] for row in projection['objects']} & {row['sha256'] for row in projection['reproductions']}), 'projection counts a frozen identity as supplemental')
    for actual, expected in zip(projection['objects'], rebuilt['objects']):
        require(same_json(actual.get('baseline_reproduction'), expected.get('baseline_reproduction')), 'projection baseline reproduction annotation differs')
    updates = {row['expectation_id']: row for row in addendum['expectation_updates']}
    later = {row['expectation_id']: row for row in later_expectation_updates}
    require(len(later) == len(later_expectation_updates) and not (set(later) & set(updates)), 'later expectation updates repeat or overwrite baseline matches')
    updates.update(later)
    frozen = {row['expectation_id']: row for row in expectations['expectations'] if row['category'] not in EXCLUDED_CATEGORIES}
    actual = {row['id']: row for row in projection['expectations']}
    require(len(actual) == len(projection['expectations']) and set(actual) == set(frozen), 'projection reference IDs are missing or repeated')
    for identity, row in actual.items():
        original = frozen[identity]
        require(row['expected_sha256'] == original.get('expected_sha256')
                and same_json(row['expected_bytes'], original.get('expected_bytes'))
                and row['category'] == original['category'], 'projection reference identity or size differs')
        update = updates.get(identity)
        if update:
            require(update['expected_sha256'] == original.get('expected_sha256')
                    and update['frozen_status'] == original['status']
                    and (original.get('expected_bytes') is None or same_json(update['matched_bytes'], original['expected_bytes'])), 'later expectation update conflicts with frozen identity')
        require(row['status'] == (CURRENT_STATUS if update else original['status']), 'projection reference availability differs')
        require(row.get('matched_sha256') == (update['expected_sha256'] if update else original.get('matched_sha256')), 'projection reference match differs')
        if update:
            require(row.get('frozen_status') == original['status'] and row.get('availability') == 'privately_preserved'
                    and row.get('historical_original_retrieval') is False and row.get('reproduced_names') == update['output_paths']
                    and row.get('qualification') == update['qualification'], 'projection exact-reproduction provenance differs')
        expected_row = {
            'id': identity, 'name': original['logical_name'],
            'expected_sha256': original.get('expected_sha256'), 'expected_bytes': original.get('expected_bytes'),
            'status': CURRENT_STATUS if update else original['status'],
            'matched_sha256': update['expected_sha256'] if update else original.get('matched_sha256'),
            'category': original['category'], 'candidates': original.get('candidate_sha256s', []),
            'qualification': update['qualification'] if update else original.get('qualification'),
        }
        if update:
            expected_row.update({'frozen_status': original['status'], 'availability': 'privately_preserved',
                                 'historical_original_retrieval': False, 'reproduced_names': update['output_paths']})
            if identity in later:
                expected_row['reproduction_scope'] = update['reproduction_scope']
        require(same_json(row, expected_row), 'projection reference fields differ from frozen or reproduced evidence')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--apply-to-projection', action='store_true', help='Update only the additive layer of the existing canonical projection; no media access')
    args = parser.parse_args()
    root = args.root.resolve()
    catalog_raw = (root / 'manifests/artifacts/god-here-recovery-catalog.json').read_bytes()
    expectations_raw = (root / 'manifests/artifacts/god-here-recovery-expectations.json').read_bytes()
    receipt_raw = (root / RECEIPT_PATH).read_bytes()
    catalog, expectations, receipt = map(json.loads, (catalog_raw, expectations_raw, receipt_raw))
    result = derive_addendum(receipt, catalog, expectations, digest(catalog_raw), digest(expectations_raw), digest(receipt_raw), len(receipt_raw))
    raw = (json.dumps(result, indent=2) + '\n').encode()
    (root / ADDENDUM_PATH).write_bytes(raw)
    if args.apply_to_projection:
        path = root / 'web/recovery/catalog.json'
        projection = apply_to_projection(json.loads(path.read_bytes()), result, digest(raw))
        from retained_execution_availability import ADDENDUM_PATH as RETAINED_PATH
        if (root / RETAINED_PATH).is_file():
            from retained_execution_availability import load_inputs, validate_addendum as check_retained, apply_to_projection as apply_retained, validate_projection as check_projection
            records, descriptors = load_inputs(root)
            retained_raw = (root / RETAINED_PATH).read_bytes()
            retained = json.loads(retained_raw)
            check_retained(retained, records, descriptors)
            apply_retained(projection, retained, digest(retained_raw))
            check_projection(projection, retained, digest(retained_raw), result, digest(raw), expectations)
        else:
            validate_projection(projection, result, digest(raw), expectations)
        path.write_text(json.dumps(projection, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(json.dumps({'addendum_sha256': digest(raw), 'bytes': len(raw), 'counts': result['counts']}, indent=2))


if __name__ == '__main__':
    main()
