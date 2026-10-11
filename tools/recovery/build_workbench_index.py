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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--expectations", type=Path, required=True)
    parser.add_argument("--workbench-root", type=Path, required=True, help="The current Site checkout; links are enabled only after its bytes match the object hash")
    parser.add_argument("--room-media-receipt", type=Path, help="Optional completed full-download receipt for the registered R2 files")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.catalog.read_bytes()
    catalog = json.loads(raw)
    expectations = json.loads(args.expectations.read_bytes())
    origins = {origin["origin_id"]: origin for origin in catalog["origins"]}
    objects, linked_hashes = [], {}
    workbench_root = args.workbench_root.resolve()
    static_root = next((workbench_root / p for p in ("public", "dist/client", "dist") if (workbench_root / p / "index.html").is_file()), None)
    if static_root is None:
        raise ValueError("Expected the current Site checkout with public/index.html, dist/client/index.html or dist/index.html")
    manifest_path = workbench_root / "lib/room-media-manifest.json"
    room_media = {row["path"]: row for row in json.loads(manifest_path.read_bytes())} if manifest_path.is_file() else {}
    verified_downloads = {}
    if args.room_media_receipt:
        receipt = json.loads(args.room_media_receipt.read_bytes())
        if (receipt.get("origin") != "https://god-here-five-realities.ajpadavano.chatgpt.site"
                or receipt.get("verification") != "full"
                or receipt.get("status") != "verified"
                or receipt.get("manifest_sha256") != hashlib.sha256(manifest_path.read_bytes()).hexdigest()):
            raise ValueError("Expected a completed full-download receipt for this Site and media manifest")
        verified_downloads = {row["path"]: row for row in receipt["files"] if row.get("status") == "verified" and row.get("head_verified") is True and row.get("range_verified") is True and row.get("full_download_verified") is True}
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
        objects.append({
            "sha256": obj["sha256"], "bytes": obj["bytes"], "names": obj["logical_names"],
            "type": obj["type"], "occurrences": obj["file_occurrence_count"],
            "decode": decode if decode in {"passed", "failed", "not_applicable"} else "pending",
            "image_verification": ("Complete image decoding passed; visual and artistic acceptance remain separate." if decode == "passed" else "Image byte identity is verified; complete image decoding remains pending.") if obj["type"] == "image" else None,
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
        "source_expectations_sha256": hashlib.sha256(args.expectations.read_bytes()).hexdigest(),
        "delivery": {"static_source_root": str(static_root.relative_to(workbench_root)), "verified_static_media_paths": len(static_paths), "registered_downloads_verified": len(available_downloads), "registered_downloads_pending": len(pending_downloads), "room_media_receipt_sha256": hashlib.sha256(args.room_media_receipt.read_bytes()).hexdigest() if args.room_media_receipt else None},
        "scope": catalog["scope"], "counts": catalog["counts"], "objects": objects, "expectations": historical,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"objects": len(objects), "historical_references": len(historical), "bytes": args.output.stat().st_size, "output": str(args.output)}))


if __name__ == "__main__":
    main()
