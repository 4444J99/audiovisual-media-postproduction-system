#!/usr/bin/env python3
"""Verify published recovery evidence and its workbench projection without media access.

This checks recorded evidence, not live delivery, new decoding or artistic quality.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re

from image_supplement import validate_image_supplement
from reproduction_availability import ADDENDUM_PATH, same_json, validate_addendum, validate_projection
from retained_execution_availability import (
    ADDENDUM_PATH as RETAINED_PATH, load_inputs as load_retained_inputs,
    validate_addendum as validate_retained_addendum, validate_projection as validate_retained_projection,
)
from verify_deployed_text import TEXT_ROUTES, REDIRECT_ROUTES, REDIRECT_STATUSES


def verify(root):
    root = Path(root).resolve()
    errors = []
    checks = 0

    def require(condition, message):
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(message)

    def local(path):
        candidate = (root / path).resolve()
        if not candidate.is_relative_to(root) or Path(path).is_absolute():
            raise ValueError('Evidence path escapes the repository')
        return candidate

    def read(path):
        return json.loads(local(path).read_text())

    def digest(path):
        return hashlib.sha256(local(path).read_bytes()).hexdigest()

    def evidence(entry):
        path = entry['path']
        data = local(path).read_bytes()
        require(len(data) == entry['bytes'], 'Evidence byte count differs: ' + path)
        require(hashlib.sha256(data).hexdigest() == entry['sha256'], 'Evidence SHA-256 differs: ' + path)

    def walk(value):
        if isinstance(value, dict):
            if {'public_log_path', 'public_log_sha256', 'public_log_bytes'} <= value.keys():
                evidence({'path': value['public_log_path'], 'sha256': value['public_log_sha256'], 'bytes': value['public_log_bytes']})
            if {'path', 'sha256', 'bytes'} <= value.keys() and isinstance(value['path'], str) and value['path'].startswith(('docs/recovery/evidence/', 'docs/engineering-integration/', 'manifests/')):
                evidence(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    catalog_path = 'manifests/artifacts/god-here-recovery-catalog.json'
    expectations_path = 'manifests/artifacts/god-here-recovery-expectations.json'
    checkpoint = read('manifests/acceptance/god-here-consolidation-checkpoint.json')
    publication = read('manifests/acceptance/god-here-workbench-publication.json')
    payload = read('manifests/acceptance/god-here-public-media-delivery-review.json')
    projection = read('web/recovery/catalog.json')
    catalog = read(catalog_path)
    expectations = read(expectations_path)

    for label, record in [('checkpoint', checkpoint), ('publication', publication)]:
        require(record['catalog_sha256'] == digest(catalog_path), label + ' catalog binding differs')
        require(record['expectations_sha256'] == digest(expectations_path), label + ' expectations binding differs')
    require(projection['source_catalog_sha256'] == digest(catalog_path), 'Workbench catalog binding differs')
    require(projection['source_expectations_sha256'] == digest(expectations_path), 'Workbench expectations binding differs')
    require(projection['counts'] == catalog['counts'], 'Workbench frozen counts differ')
    require(checkpoint['catalog_counts'] == catalog['counts'], 'Checkpoint frozen counts differ')
    require({r['sha256'] for r in projection['objects']} == {r['sha256'] for r in catalog['objects']}, 'Workbench object identities differ')
    require(len(projection['objects']) == len(catalog['objects']), 'Workbench repeats object identities')
    originals = {r['sha256']: r for r in catalog['objects']}
    expected_decodes = {}
    for sha, row in originals.items():
        state = row['verification'].get('image_decode_status') if row['type'] == 'image' else row['verification']['full_decode_status']
        expected_decodes[sha] = state if state in {'passed', 'failed', 'not_applicable'} else 'pending'

    require(bool(projection.get('image_validation')) == bool(checkpoint.get('image_validation_supplement')), 'Image supplement must be bound in both checkpoint and projection')
    if projection.get('image_validation'):
        supplement_entry = checkpoint['image_validation_supplement']
        supplement = read(supplement_entry['path'])
        summary = projection['image_validation']
        require(summary['supplement_sha256'] == digest(supplement_entry['path']), 'Workbench image evidence binding differs')
        validated = validate_image_supplement(supplement, catalog, digest(catalog_path))
        checks += validated['checks']
        for row in validated['additions'].values():
            if row['status'] in {'passed', 'failed'}:
                expected_decodes[row['sha256']] = row['status']
        for key in ('frozen_passes', 'additional_passes', 'passed', 'pending', 'failed'):
            require(summary.get(key) == validated[key], 'Image summary differs: ' + key)
        require(summary.get('finished_at_utc') == supplement['finished_at_utc'], 'Image summary finish timestamp differs')
    for row in projection['objects']:
        original = originals.get(row['sha256'], {})
        require(row['type'] == original.get('type') and row['bytes'] == original.get('bytes') and row['occurrences'] == original.get('file_occurrence_count'), 'Workbench object fields differ: ' + row['sha256'])
        require(row['decode'] == expected_decodes.get(row['sha256']), 'Workbench decode differs from evidence: ' + row['sha256'])

    has_reproduction_addendum = local(ADDENDUM_PATH).is_file()
    has_retained_addendum = local(RETAINED_PATH).is_file()
    require(bool(projection.get('retained_execution_availability')) == has_retained_addendum,
            'Retained execution availability must be bound in both addendum and projection')
    if not has_retained_addendum:
        require(not projection.get('retained_outputs') and not projection.get('retained_inputs'), 'Unbound retained identities appear in the projection')
    require(bool(projection.get('reproduction_availability')) == has_reproduction_addendum,
            'Reproduction availability must be bound in both addendum and projection')
    if has_reproduction_addendum and projection.get('reproduction_availability'):
        addendum = read(ADDENDUM_PATH)
        reproduction_entry = addendum['reproduction_receipt']
        evidence(reproduction_entry)
        reproduction_receipt = read(reproduction_entry['path'])
        validate_addendum(addendum, reproduction_receipt, catalog, expectations, digest(catalog_path),
                          digest(expectations_path), digest(reproduction_entry['path']),
                          len(local(reproduction_entry['path']).read_bytes()))
        if has_retained_addendum:
            retained = read(RETAINED_PATH)
            retained_records, retained_descriptors = load_retained_inputs(root)
            validate_retained_addendum(retained, retained_records, retained_descriptors)
            validate_retained_projection(projection, retained, digest(RETAINED_PATH), addendum, digest(ADDENDUM_PATH), expectations)
            expected_entry = {'path': RETAINED_PATH, 'sha256': digest(RETAINED_PATH), 'bytes': len(local(RETAINED_PATH).read_bytes())}
            require(same_json(checkpoint.get('retained_execution_availability'), expected_entry), 'Checkpoint retained availability evidence binding differs')
            require(same_json(checkpoint.get('current_retained_availability'), retained['counts']), 'Checkpoint retained availability counts differ')
        else:
            validate_projection(projection, addendum, digest(ADDENDUM_PATH), expectations)

    for path in sorted((root / 'manifests/acceptance').glob('*.json')):
        walk(json.loads(path.read_text()))
    for test in checkpoint.get('tests', []):
        if test.get('evidence_path'):
            require(local(test['evidence_path']).is_file(), 'Test evidence missing: ' + test['evidence_path'])

    require(publication['current_deployment']['status'] == 'succeeded', 'Publication has no successful deployment')
    require(publication['site_version']['source']['commit_sha'] == publication['source_commit'], 'Saved version source differs')
    require(publication['current_deployment']['version_id'] == publication['site_version']['id'], 'Deployment version differs')

    text_delivery = publication['text_delivery']
    text_receipt = read(text_delivery['evidence']['path'])
    require(text_receipt.get('schema') == 'god-here.deployed-text-verification.v1'
            and text_receipt.get('status') == text_delivery.get('status') == 'passed', 'Published text receipt is not complete and passed')
    started = datetime.datetime.fromisoformat(text_receipt['started_at_utc'])
    finished = datetime.datetime.fromisoformat(text_receipt['finished_at_utc'])
    require(started.utcoffset() is not None and finished.utcoffset() is not None and finished >= started,
            'Published text receipt lacks an ordered completed interval')
    require(text_receipt.get('origin') == publication['production_url']
            and text_receipt.get('request_method') == 'GET'
            and text_receipt.get('redirects_followed') is False, 'Text receipt origin or request scope differs')
    require(text_delivery.get('source_commit') == publication['source_commit'], 'Text publication source differs')
    environment_revision = publication['current_deployment']['env_set_revision']
    require(type(environment_revision) is int
            and same_json(text_delivery.get('tested_environment_revision'), environment_revision)
            and same_json(text_delivery.get('current_environment_revision'), environment_revision), 'Text publication environment differs')
    if 'source_commit' in text_receipt:
        require(text_receipt['source_commit'] == publication['source_commit'], 'Text receipt source differs')
    if 'environment_revision' in text_receipt:
        require(same_json(text_receipt['environment_revision'], environment_revision), 'Text receipt environment differs')
    text_routes, redirects = dict(TEXT_ROUTES), dict(REDIRECT_ROUTES)
    text_checks = text_receipt['checks']
    expected_routes = {('exact_text_bytes', route) for route in text_routes} | {('canonical_redirect', route) for route in redirects}
    observed_routes = {(row.get('kind'), row.get('route')) for row in text_checks}
    require(len(text_checks) == len(expected_routes) and observed_routes == expected_routes,
            'Text receipt repeats or omits a required route')
    derived_text_counts = {
        'checks_passed': sum(row.get('status') == 'passed' for row in text_checks),
        'checks_failed': sum(row.get('status') != 'passed' for row in text_checks),
        'full_text_body_checks': sum(row.get('kind') == 'exact_text_bytes' for row in text_checks),
        'canonical_redirect_checks': sum(row.get('kind') == 'canonical_redirect' for row in text_checks),
    }
    require(all(same_json(text_delivery.get(key), value) for key, value in derived_text_counts.items()), 'Published text counters differ from checked rows')
    recovery_sources = {
        '/recovery/': 'web/recovery/index.html', '/recovery/catalog.json': 'web/recovery/catalog.json',
        '/recovery/recovery.js': 'web/recovery/recovery.js', '/recovery/recovery.css': 'web/recovery/recovery.css',
    }
    for row in text_checks:
        route, kind = row.get('route'), row.get('kind')
        require(row.get('status') == 'passed', 'Text receipt contains an unfinished or failed check')
        if kind == 'exact_text_bytes':
            require(row.get('source_path') == text_routes.get(route), 'Text source path differs from its canonical route')
            require(type(row.get('http_status')) is int and row['http_status'] == 200
                    and type(row.get('expected_http_status')) is int and row['expected_http_status'] == 200
                    and row.get('response_complete') is True, 'Text response is incomplete or has an unexpected status')
            require(isinstance(row.get('expected_sha256'), str)
                    and re.fullmatch(r'[0-9a-f]{64}', row['expected_sha256']) is not None
                    and row.get('actual_sha256') == row['expected_sha256']
                    and type(row.get('expected_bytes')) is int and row['expected_bytes'] > 0
                    and same_json(row.get('observed_bytes'), row['expected_bytes']), 'Text response identity or byte count differs')
            if route in recovery_sources:
                source_raw = local(recovery_sources[route]).read_bytes()
                require(row.get('expected_sha256') == hashlib.sha256(source_raw).hexdigest()
                        and same_json(row.get('expected_bytes'), len(source_raw)), 'Published recovery text differs from current repository source: ' + route)
        elif kind == 'canonical_redirect':
            require(same_json(row.get('accepted_http_statuses'), list(REDIRECT_STATUSES))
                    and type(row.get('http_status')) is int and row['http_status'] in REDIRECT_STATUSES
                    and row.get('location_matches_expected') is True
                    and row.get('expected_location') == row.get('actual_location') == redirects.get(route), 'Canonical redirect status or target differs')

    delivery = publication['registered_delivery']
    entry = delivery.get('full_verification_evidence') or delivery['raw_interrupted_evidence']
    receipt = read(entry['path'])
    require(receipt['origin'] == publication['production_url'] == payload['destination'], 'Media origin differs')
    require(receipt['manifest_sha256'] == delivery['registry_sha256'] == payload['source_registry_sha256'], 'Media registry binding differs')
    registered = {r['id']: r for r in payload['files']}
    require(len(registered) == len(payload['files']) == payload['registered_count'], 'Payload ID count differs')
    require(sum(r['bytes'] for r in registered.values()) == payload['registered_bytes'], 'Payload byte total differs')
    require(delivery['registered_count'] == len(registered) and delivery['registered_bytes'] == payload['registered_bytes'], 'Publication registration totals differ')
    completed = {}
    for row in receipt['files']:
        if row.get('status') != 'verified':
            continue
        require(row['id'] not in completed, 'Duplicate completed media ID')
        completed[row['id']] = row
        original = registered.get(row['id'])
        require(original is not None, 'Receipt contains an unregistered media ID')
        if original is None:
            continue
        require(all(row[k] == original[k] for k in ('path', 'bytes', 'sha256')), 'Receipt identity differs: ' + row['id'])
        require(all(row.get(k) is True for k in ('head_verified', 'range_verified', 'full_download_verified')), 'Incomplete media evidence: ' + row['id'])
        require(row.get('download_bytes') == original['bytes'] and row.get('download_sha256') == original['sha256'], 'Full-download identity differs: ' + row['id'])
    require(delivery['full_verified_count'] == len(completed), 'Published verified-media count differs')
    require(delivery['full_verified_bytes'] == sum(r['bytes'] for r in completed.values()), 'Published verified-media bytes differ')
    require(delivery['not_fully_verified_count'] == len(registered) - len(completed), 'Published pending-media count differs')
    current = checkpoint['current_workbench_delivery']
    require(current['registered_media_verified'] == len(completed) and current['registered_media_unverified'] == len(registered) - len(completed), 'Checkpoint delivery totals differ')
    require(current['source_commit'] == publication['source_commit'] and current['version_number'] == publication['site_version']['version_number'], 'Checkpoint publication source/version differs')
    require(current['deployed_environment_revision'] == publication['current_deployment']['env_set_revision'], 'Checkpoint environment revision differs')
    if receipt['status'] == 'verified':
        require(set(completed) == set(registered), 'Complete receipt does not cover the approved payload')
        require(len(receipt['files']) == len(registered) and all(r['status'] == 'verified' for r in receipt['files']), 'Complete receipt includes unfinished or repeated records')
        require(receipt['selected_count'] == receipt['verified_count'] == len(registered), 'Complete receipt has inconsistent counts')
        require(receipt['selected_bytes'] == receipt['verified_bytes'] == payload['registered_bytes'], 'Complete receipt has inconsistent byte totals')
        require(len(receipt['selected_ids']) == len(registered) and set(receipt['selected_ids']) == set(registered), 'Complete receipt selection differs')
        require(not receipt.get('unprocessed_ids') and bool(receipt.get('finished_at')), 'Complete receipt has unfinished work')
        require(receipt['verification'] == 'full', 'Complete receipt lacks full verification')
        require(projection['delivery']['registered_downloads_verified'] == len(registered), 'Workbench omits completed registrations')
        require(projection['delivery']['registered_downloads_pending'] == 0, 'Workbench retains stale pending registrations')
        require(projection['delivery']['room_media_receipt_sha256'] == digest(entry['path']), 'Workbench full receipt binding differs')
        require(payload['completed_verified_count'] == len(registered) and payload['not_fully_verified_count'] == 0, 'Payload retains stale completion counts')
        require(publication['temporary_upload_access']['removed'] is True and publication['temporary_upload_access']['applied_deployment_status'] == 'succeeded', 'Temporary upload access removal is not applied')
    else:
        require(projection['delivery']['registered_downloads_verified'] == 0, 'Incomplete batch enables registered links')
        require(projection['delivery']['registered_downloads_pending'] == len(registered), 'Incomplete batch lacks pending-link states')
    return {'status': 'failed' if errors else 'passed', 'checks': checks, 'errors': errors,
            'scope': 'Committed metadata and evidence consistency; no live-media or artistic certification'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    try:
        result = verify(args.root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {'status': 'failed', 'errors': ['Cannot validate checkpoint: ' + str(exc)]}
    print(json.dumps(result, indent=2))
    raise SystemExit(result['status'] != 'passed')


if __name__ == '__main__':
    main()
