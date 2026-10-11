"""Check additive image evidence against frozen public custody metadata.

This validates the internal evidence graph, not image bytes or artistic quality.
Both the checkpoint verifier and browser projection use these same invariants.
"""
from collections import Counter
from datetime import datetime


def validate_image_supplement(supplement, catalog, catalog_sha256):
    checks = 0

    def require(condition, message):
        nonlocal checks
        checks += 1
        if not condition:
            raise ValueError('Image supplement: ' + message)

    def integer(value, minimum=0):
        return type(value) is int and value >= minimum

    def unique_list(values, label):
        require(isinstance(values, list) and all(isinstance(v, str) for v in values), label + ' is not an identity list')
        require(len(values) == len(set(values)), label + ' repeats an identity')
        return set(values)

    def timestamp(value, label):
        try:
            result = datetime.fromisoformat(value)
        except (TypeError, ValueError):
            raise ValueError('Image supplement: invalid ' + label) from None
        require(result.tzinfo is not None, label + ' lacks a timezone')
        return result

    require(supplement.get('schema_version') == 'god-here.supplemental-image-validation.v1', 'unsupported evidence schema')
    require(supplement.get('frozen_catalog_sha256') == catalog_sha256 and supplement.get('frozen_catalog_unchanged') is True, 'does not bind the unchanged frozen catalog')
    expected_boundary = {'unique_objects': catalog['counts']['unique_sha256_objects'], 'file_occurrences': catalog['counts']['file_occurrences']}
    require(supplement.get('frozen_catalog_counts_unchanged') == expected_boundary, 'frozen count boundary differs')
    require(supplement.get('artistic_acceptance') == 'pending_for_all_objects', 'technical evidence must not grant artistic acceptance')
    started = timestamp(supplement.get('started_at_utc'), 'start timestamp')
    finished = timestamp(supplement.get('finished_at_utc'), 'finish timestamp')
    require(started <= finished, 'finish precedes start')

    objects = {row['sha256']: row for row in catalog['objects']}
    origins = {row['origin_id']: row for row in catalog['origins']}
    require(len(objects) == len(catalog['objects']), 'frozen object list repeats an identity')
    require(len(origins) == len(catalog['origins']), 'frozen origin list repeats an identity')
    images = {sha: row for sha, row in objects.items() if row['type'] == 'image'}
    prior_passes = {sha for sha, row in images.items() if row['verification'].get('image_decode_status') == 'passed'}
    prior_failures = {sha for sha, row in images.items() if row['verification'].get('image_decode_status') == 'failed'}
    prior_pending = set(images) - prior_passes - prior_failures
    require(len(images) == catalog['counts']['unique_image_objects'], 'frozen image total differs from identities')
    require(len(prior_passes) == catalog['counts']['image_decode_passes'] and len(prior_pending) == catalog['counts']['image_decode_pending'], 'frozen image status totals differ')

    containers = {}
    for row in supplement['containers']:
        sha = row['sha256']
        require(sha not in containers, 'container list repeats an identity')
        obj = objects.get(sha, {})
        require(obj.get('type') == 'archive' and obj.get('bytes') == row['bytes'] and integer(row['bytes'], 1), 'container identity differs')
        require(integer(row.get('image_occurrences')), 'container occurrence count is invalid')
        containers[sha] = row
    occurrences = Counter()
    memberships = {}
    for sha, obj in images.items():
        for origin_id in obj['origin_ids']:
            origin = origins[origin_id]
            container = origin.get('container_sha256')
            if origin.get('kind') == 'archive_member' and container in containers:
                require(origin.get('container_identity_verified') is True and origin.get('crc_status') == 'passed_on_stream_to_EOF', 'member lacks frozen container/CRC evidence')
                occurrences[container] += 1
                memberships.setdefault(sha, set()).add(container)
    for sha, row in containers.items():
        require(row['image_occurrences'] == occurrences[sha], 'container occurrence count differs from frozen membership')
        expected_status = 'exact_frozen_container_sha256_verified' if occurrences[sha] else 'previously_verified_copy_present_no_image_members_in_scope'
        require(row.get('status') == expected_status, 'container verification status differs from its scope')

    reused = unique_list(supplement['reused_prior_pass_sha256s'], 'reused prior passes')
    require(reused <= prior_passes, 'reused pass lacks frozen passing evidence')
    additions = {}
    for row in supplement['new_image_results']:
        sha = row['sha256']
        require(sha not in additions, 'new image results repeat an identity')
        require(sha in prior_pending and sha not in reused, 'new image changes or recounts a prior status')
        require(integer(row.get('bytes'), 1) and row['bytes'] == images[sha]['bytes'], 'new image byte identity differs')
        require(row.get('matched_frozen_catalog') is True and row.get('prior_image_gate') == 'checksum_only', 'new image identity qualification differs')
        require(row.get('artistic_acceptance') == 'not_established', 'image row grants unsupported artistic acceptance')
        require(row.get('status') in {'passed', 'failed', 'not_verified'}, 'unknown image result status')
        member_containers = unique_list(row['verified_container_sha256s'], 'verified image containers')
        require(bool(member_containers) and member_containers == memberships.get(sha), 'verified containers differ from frozen image membership')
        checked = timestamp(row.get('checked_at_utc'), 'image check timestamp')
        require(started <= checked <= finished, 'image check falls outside the recorded operation')
        require(isinstance(row.get('method'), str) and bool(row['method'].strip()), 'image row lacks its method')
        require(isinstance(row.get('format'), str) and bool(row['format']), 'image row lacks its format')
        if row['status'] == 'passed':
            frames = row.get('frame_count')
            require(integer(frames, 1) and type(row.get('frames_decoded')) is int and row['frames_decoded'] == frames, 'pass lacks complete frame evidence')
            sizes, modes = row.get('decoded_frame_sizes'), row.get('decoded_frame_modes')
            require(isinstance(sizes, list) and len(sizes) == frames and all(isinstance(size, list) and len(size) == 2 and all(integer(n, 1) for n in size) for size in sizes), 'decoded frame sizes do not cover every frame')
            require(isinstance(modes, list) and len(modes) == frames and all(isinstance(mode, str) and bool(mode) for mode in modes), 'decoded frame modes do not cover every frame')
            require(integer(row.get('width'), 1) and integer(row.get('height'), 1) and sizes[0] == [row['width'], row['height']], 'first-frame dimensions differ')
            require(row.get('mode') == modes[0], 'first-frame mode differs')
        else:
            require(isinstance(row.get('reason') or row.get('error'), str) and bool(row.get('reason') or row.get('error')), 'unfinished or failed image lacks a reason')
        additions[sha] = row
    require(set(additions) | reused == set(memberships), 'available image identities differ from declared container scope')
    require(not (set(additions) & reused), 'available image groups overlap')
    outstanding = unique_list(supplement['outstanding_image_sha256s_in_available_archives'], 'outstanding images')
    require(outstanding == {sha for sha, row in additions.items() if row['status'] == 'not_verified'}, 'outstanding image list differs from results')

    new_passes = sum(row['status'] == 'passed' for row in additions.values())
    new_failures = sum(row['status'] == 'failed' for row in additions.values())
    passed = len(prior_passes) + new_passes
    pending = len(prior_pending) - new_passes - new_failures
    failed = len(prior_failures) + new_failures
    expected_counts = {
        'archive_copies_considered': len(containers),
        'archive_copies_with_image_members': sum(n > 0 for n in occurrences.values()),
        'image_file_occurrences_identity_verified': sum(occurrences.values()),
        'unique_image_identities_available': len(memberships),
        'prior_image_passes_reused': len(reused),
        'new_image_identities_processed': len(additions),
        'new_full_decode_passes': new_passes,
        'new_full_decode_failures': new_failures,
        'new_image_identities_not_fully_decoded': len(outstanding),
        'frozen_unique_image_objects': len(images),
        'frozen_image_passes': len(prior_passes),
        'frozen_image_checksum_only': len(prior_pending),
        'supplemented_unique_image_passes': passed,
        'remaining_checksum_only_images_after_supplement': pending,
        'supplemented_failed_image_identities': failed,
    }
    for key, expected in expected_counts.items():
        require(integer(supplement['counts'].get(key)) and supplement['counts'][key] == expected, 'count differs: ' + key)
    all_rasters_passed = all(row['status'] == 'passed' or row['format'].upper() == 'SVG' for row in additions.values())
    require(supplement['counts'].get('all_available_raster_frames_decoded') is all_rasters_passed, 'raster completion flag differs')
    require(passed + pending + failed == len(images), 'image statuses do not partition frozen identities')
    return {'additions': additions, 'frozen_passes': len(prior_passes), 'additional_passes': new_passes, 'passed': passed, 'failed': failed, 'pending': pending, 'checks': checks}
