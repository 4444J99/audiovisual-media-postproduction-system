#!/usr/bin/env python3
"""Create the browser projection of the public God-here recovery manifests.

This reads public manifests and media bytes to verify SHA-256 identities.
It does not copy, transform, or publish media.
The full content-addressed catalog remains authoritative; this is a view of it.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from image_supplement import validate_image_supplement
from reproduction_availability import ADDENDUM_PATH, RECEIPT_PATH, apply_to_projection, validate_addendum, validate_projection
from retained_execution_availability import (
    ADDENDUM_PATH as RETAINED_PATH, load_inputs as load_retained_inputs,
    validate_addendum as validate_retained_addendum, apply_to_projection as apply_retained,
    validate_projection as validate_retained_projection,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--expectations", type=Path, required=True)
    parser.add_argument("--workbench-root", type=Path, required=True, help="The current Site checkout; links are enabled only after its bytes match the object hash")
    parser.add_argument("--room-media-receipt", type=Path, help="Optional completed full-download receipt for the registered R2 files")
    parser.add_argument("--image-validation-supplement", type=Path, help="Optional later image decode evidence bound to the frozen catalog")
    parser.add_argument("--reproduction-availability-addendum", type=Path, help="Defaults to the canonical sibling availability addendum when present")
    parser.add_argument("--reproduction-receipt", type=Path, help="Defaults to the canonical baseline reproduction receipt")
    parser.add_argument("--retained-execution-availability-addendum", type=Path, help="Defaults to the canonical retained-execution addendum when present; receipt inputs remain repository-bound")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.catalog.read_bytes()
    catalog = json.loads(raw)
    expectations_raw = args.expectations.read_bytes()
    expectations = json.loads(expectations_raw)
    origins = {origin["origin_id"]: origin for origin in catalog["origins"]}
    supplemental_images = {}
    image_validation = None
    if args.image_validation_supplement:
        supplement_bytes = args.image_validation_supplement.read_bytes()
        supplement = json.loads(supplement_bytes)
        validated = validate_image_supplement(supplement, catalog, hashlib.sha256(raw).hexdigest())
        supplemental_images = validated['additions']
        image_validation = {
            "supplement_sha256": hashlib.sha256(supplement_bytes).hexdigest(),
            "finished_at_utc": supplement["finished_at_utc"],
            **{key: validated[key] for key in ('frozen_passes', 'additional_passes', 'passed', 'failed', 'pending')},
            "scope": "Later decode evidence over frozen identities; artistic acceptance remains separate.",
        }
    repository_root = args.catalog.resolve().parents[2]
    addendum_path = args.reproduction_availability_addendum or repository_root / ADDENDUM_PATH
    reproduction_addendum = None
    reproduction_addendum_sha = None
    if addendum_path.is_file():
        addendum_raw = addendum_path.read_bytes()
        reproduction_addendum = json.loads(addendum_raw)
        reproduction_receipt_raw = (args.reproduction_receipt or repository_root / RECEIPT_PATH).read_bytes()
        validate_addendum(reproduction_addendum, json.loads(reproduction_receipt_raw), catalog, expectations,
                          hashlib.sha256(raw).hexdigest(), hashlib.sha256(expectations_raw).hexdigest(),
                          hashlib.sha256(reproduction_receipt_raw).hexdigest(), len(reproduction_receipt_raw))
        reproduction_addendum_sha = hashlib.sha256(addendum_raw).hexdigest()
    elif args.reproduction_availability_addendum or args.reproduction_receipt:
        raise ValueError('Requested reproduction availability addendum is missing')
    objects, linked_hashes = [], {}
    workbench_root = args.workbench_root.resolve()
    static_root = next((workbench_root / p for p in ("public", "dist/client", "dist") if (workbench_root / p / "index.html").is_file()), None)
    if static_root is None:
        raise ValueError("Expected the current Site checkout with public/index.html, dist/client/index.html or dist/index.html")
    manifest_path = workbench_root / "lib/room-media-manifest.json"
    registry_rows = json.loads(manifest_path.read_bytes()) if manifest_path.is_file() else []
    room_media = {row["path"]: row for row in registry_rows}
    if len(room_media) != len(registry_rows) or len({row['id'] for row in registry_rows}) != len(registry_rows):
        raise ValueError('Media registry repeats a path or ID')
    verified_downloads = {}
    if args.room_media_receipt:
        receipt = json.loads(args.room_media_receipt.read_bytes())
        if (receipt.get("origin") != "https://god-here-five-realities.ajpadavano.chatgpt.site"
                or receipt.get("verification") != "full"
                or receipt.get("status") != "verified"
                or receipt.get("manifest_sha256") != hashlib.sha256(manifest_path.read_bytes()).hexdigest()):
            raise ValueError("Expected a completed full-download receipt for this Site and media manifest")
        registered_ids = {row["id"] for row in room_media.values()}
        selected_ids = receipt.get("selected_ids", [])
        registered_bytes = sum(row["bytes"] for row in room_media.values())
        if (len(registered_ids) != len(room_media) or len(receipt.get("files", [])) != len(room_media)
                or len(selected_ids) != len(registered_ids) or set(selected_ids) != registered_ids
                or receipt.get("selected_count") != len(room_media) or receipt.get("verified_count") != len(room_media)
                or receipt.get("selected_bytes") != registered_bytes or receipt.get("verified_bytes") != registered_bytes
                or receipt.get("unprocessed_ids") or not receipt.get("finished_at")):
            raise ValueError("Complete media receipt has inconsistent coverage, totals or completion")
        seen_ids = set()
        for row in receipt["files"]:
            original = room_media.get(row.get("path"))
            if (not original or row.get("id") in seen_ids or row["path"] in verified_downloads
                    or any(row.get(key) != original[key] for key in ("id", "path", "sha256", "bytes"))
                    or row.get("status") != "verified"
                    or not all(row.get(key) is True for key in ("head_verified", "range_verified", "full_download_verified"))
                    or row.get("download_sha256") != original["sha256"] or row.get("download_bytes") != original["bytes"]):
                raise ValueError("Complete media receipt includes duplicate, unfinished or mismatched evidence")
            seen_ids.add(row["id"])
            verified_downloads[row["path"]] = row
        if seen_ids != registered_ids:
            raise ValueError("Complete media receipt does not cover every registration")
    pending_downloads, available_downloads, static_paths = set(), set(), set()

    def matches(target, root, expected_sha):
        target = target.resolve()
        if not target.is_relative_to(root.resolve()):
            raise ValueError("A media path escapes its source tree")
        if not target.is_file():
            return False
        if target not in linked_hashes:
            hasher = hashlib.sha256()
            with target.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    hasher.update(block)
            linked_hashes[target] = hasher.hexdigest()
        return linked_hashes[target] == expected_sha

    for obj in catalog["objects"]:
        links, code_urls = {}, []
        download_pending = False
        for origin_id in obj["origin_ids"]:
            origin = origins[origin_id]
            path = origin.get("source_path", "")
            if origin.get("site_label") == "canonical-workbench" and origin.get("access") == "public" and path.startswith("dist/"):
                public_path = PurePosixPath(path.removeprefix("dist/"))
                if public_path.is_absolute() or ".." in public_path.parts:
                    raise ValueError(f"Unsafe public path for {obj['sha256']}")
                if obj["type"] in {"audio", "video", "image"} and obj["verification"].get("full_decode_status") != "failed":
                    registered = room_media.get("/" + str(public_path))
                    if registered:
                        source_root = workbench_root / "room-media-source"
                        if registered["sha256"] != obj["sha256"] or registered["bytes"] != obj["bytes"] or not matches(source_root / str(public_path), source_root, obj["sha256"]):
                            raise ValueError("A registered media source does not match the frozen identity")
                        verified = verified_downloads.get(registered["path"], {})
                        available = (verified.get("sha256") == obj["sha256"] and verified.get("download_sha256") == obj["sha256"] and verified.get("bytes") == obj["bytes"] and verified.get("download_bytes") == obj["bytes"])
                        if available:
                            available_downloads.add(registered["path"])
                        else:
                            pending_downloads.add(registered["path"])
                            download_pending = True
                    else:
                        available = matches(static_root / str(public_path), static_root, obj["sha256"])
                        if available:
                            static_paths.add(str(public_path))
                    if available:
                        href = "../" + quote(str(public_path), safe="/")
                        links[href] = {"href": href, "label": "Open preserved workbench media ↗"}
            if origin.get("kind") == "github_blob" and origin.get("access") == "public" and origin.get("url", "").startswith("https://github.com/4444J99/audiovisual-media-postproduction-system/blob/"):
                code_urls.append(origin["url"])
        decode = obj["verification"].get("image_decode_status", "not_verified") if obj["type"] == "image" else obj["verification"]["full_decode_status"]
        supplemental = supplemental_images.get(obj["sha256"], {})
        if supplemental.get("status") in {"passed", "failed"}:
            decode = supplemental["status"]
        objects.append({
            "sha256": obj["sha256"], "bytes": obj["bytes"], "names": obj["logical_names"],
            "type": obj["type"], "occurrences": obj["file_occurrence_count"],
            "decode": decode if decode in {"passed", "failed", "not_applicable"} else "pending",
            "image_verification": ({"passed": "Complete image decoding passed; visual and artistic acceptance remain separate.", "failed": "Complete image decoding failed; the preserved bytes remain available for diagnosis."}.get(decode, "Image byte identity is verified; complete image decoding remains pending.")) if obj["type"] == "image" else None,
            "download_pending": download_pending,
            "links": list(links.values()), "code_url": sorted(code_urls)[0] if code_urls else None,
        })
    objects.sort(key=lambda row: (0 if row["type"] in {"audio", "video"} else 1, row["names"][0].casefold(), row["sha256"]))
    excluded_categories = {"test_or_example", "recovered_document_test_or_example", "parameterized", "runtime_export_contract"}
    historical = [{
        "id": row["expectation_id"], "name": row["logical_name"],
        "expected_sha256": row.get("expected_sha256"), "expected_bytes": row.get("expected_bytes"),
        "status": row["status"], "matched_sha256": row.get("matched_sha256"),
        "category": row["category"], "candidates": row.get("candidate_sha256s", []),
        "qualification": row.get("qualification"),
    } for row in expectations["expectations"] if row["category"] not in excluded_categories]
    historical.sort(key=lambda row: (row["status"] == "exact_hash_recovered", row["name"].casefold(), row["id"]))
    result = {
        "schema_version": "god-here.workbench-recovery.v1",
        "generated_at_utc": catalog["generated_at_utc"],
        "source_catalog_sha256": hashlib.sha256(raw).hexdigest(),
        "source_expectations_sha256": hashlib.sha256(expectations_raw).hexdigest(),
        "delivery": {"static_source_root": str(static_root.relative_to(workbench_root)), "verified_static_media_paths": len(static_paths), "registered_downloads_verified": len(available_downloads), "registered_downloads_pending": len(pending_downloads), "room_media_receipt_sha256": hashlib.sha256(args.room_media_receipt.read_bytes()).hexdigest() if args.room_media_receipt else None},
        "scope": catalog["scope"], "counts": catalog["counts"], "image_validation": image_validation,
        "objects": objects, "expectations": historical,
    }
    if reproduction_addendum is not None:
        apply_to_projection(result, reproduction_addendum, reproduction_addendum_sha)
        validate_projection(result, reproduction_addendum, reproduction_addendum_sha, expectations)
    retained_path = args.retained_execution_availability_addendum or repository_root / RETAINED_PATH
    if retained_path.is_file():
        retained_raw = retained_path.read_bytes()
        retained = json.loads(retained_raw)
        records, descriptors = load_retained_inputs(repository_root)
        validate_retained_addendum(retained, records, descriptors)
        apply_retained(result, retained, hashlib.sha256(retained_raw).hexdigest())
        validate_retained_projection(result, retained, hashlib.sha256(retained_raw).hexdigest(), reproduction_addendum, reproduction_addendum_sha, expectations)
    elif args.retained_execution_availability_addendum:
        raise ValueError('Requested retained execution availability addendum is missing')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"objects": len(objects), "historical_references": len(historical), "bytes": args.output.stat().st_size, "output": str(args.output)}))


if __name__ == "__main__":
    main()
