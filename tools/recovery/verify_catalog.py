#!/usr/bin/env python3
"""Check a public God-here catalog and expectations without private storage access.

Usage: python verify_catalog.py --catalog CATALOG.json --expectations EXPECTATIONS.json
The checker validates inventory consistency and publication privacy. It does not
open media, substitute for decode receipts, execute recipes, or grant acceptance.
"""
import argparse
import collections
import json
from pathlib import Path
import re


def verify(catalog, expectations):
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    objects = catalog.get("objects", [])
    by_hash = {}
    for obj in objects:
        sha = obj.get("sha256", "")
        require(bool(re.fullmatch(r"[0-9a-f]{64}", sha)), "Object has malformed SHA-256")
        require(sha not in by_hash, "Duplicate object SHA-256: " + sha)
        require(type(obj.get("bytes")) is int and obj["bytes"] >= 0, "Invalid object size: " + sha)
        require(bool(obj.get("logical_names")), "Object has no logical name: " + sha)
        acceptance = obj.get("artistic_acceptance", {})
        require(acceptance.get("status") != "accepted" or bool(acceptance.get("evidence")), "Artistic acceptance lacks explicit evidence: " + sha)
        by_hash[sha] = obj
    origins = catalog.get("origins", [])
    by_origin = {o.get("origin_id"): o for o in origins}
    require(len(by_origin) == len(origins), "Duplicate origin IDs")
    owners = {}
    for obj in objects:
        oids = obj.get("origin_ids", [])
        require(obj.get("file_occurrence_count") == len(oids), "Object occurrence count mismatch: " + obj["sha256"])
        for oid in oids:
            require(oid in by_origin, "Object references absent origin: " + oid)
            require(oid not in owners, "Origin assigned to multiple objects: " + oid)
            owners[oid] = obj["sha256"]
    require(set(owners) == set(by_origin), "Unassigned origin records")
    for origin in origins:
        if origin.get("kind") == "archive_member":
            container = origin.get("container_sha256")
            require(container in by_hash, "Archive member has no verified outer object: " + origin["origin_id"])
            require(origin.get("container_identity_verified") is True, "Archive origin is not marked verified: " + origin["origin_id"])
            require(bool(origin.get("member_path")), "Archive member has no locator or redacted locator: " + origin["origin_id"])
    counts = catalog.get("counts", {})
    require(counts.get("unique_sha256_objects") == len(objects), "Unique-object count mismatch")
    require(counts.get("file_occurrences") == len(origins), "File-occurrence count mismatch")
    require(counts.get("unique_object_bytes") == sum(o["bytes"] for o in objects), "Unique-object byte count mismatch")
    require(counts.get("file_occurrence_bytes") == sum(by_hash[h]["bytes"] for h in owners.values()), "Occurrence byte count mismatch")
    av = [o for o in objects if {"audio", "video"} & set(o.get("types", []))]
    require(counts.get("unique_audio_video_objects") == len(av), "Audio/video denominator mismatch")
    for label, status in [("passes", "passed"), ("failures", "failed"), ("pending", "not_yet_verified")]:
        actual = sum(o.get("verification", {}).get("full_decode_status") == status for o in av)
        require(counts.get("audio_video_full_decode_" + label) == actual, "Audio/video decode count mismatch: " + label)
    require(counts.get("artistic_accepted_objects") == sum(o.get("artistic_acceptance", {}).get("status") == "accepted" for o in objects), "Artistic acceptance count mismatch")
    for group in ("expectations", "reference_records"):
        for row in expectations.get(group, []):
            expected, matched, status = row.get("expected_sha256"), row.get("matched_sha256"), row.get("status")
            if status == "exact_hash_recovered":
                require(bool(expected) and matched == expected and matched in by_hash, "Exact-hash status without matching recovered object")
                if row.get("expected_bytes") is not None and matched in by_hash:
                    require(row["expected_bytes"] == by_hash[matched]["bytes"], "Expected SHA-256 has a byte-size conflict")
            elif status == "identity_unresolved_name_candidates":
                require(expected is None and matched is None, "Name candidate promoted to byte identity")
                require(bool(row.get("candidate_sha256s")), "Name-candidate status without candidates")
            for candidate in row.get("candidate_sha256s", []):
                require(candidate in by_hash, "Candidate hash does not identify a recovered object")
    text = json.dumps([catalog, expectations], ensure_ascii=False)
    for pattern in [r"/workspace/", r"/Users/", r"/root/", r"sandbox:", r"chatgpt\.com/(?:c|space)/",
                    r"drive\.google\.com/", r"libfile_[a-zA-Z0-9]", r"library-file:", r"appgprj_[a-zA-Z0-9]",
                    r"file_000000", r"X-Amz-", r"[?&]sig=", r"Bearer\s+",
                    r"god-here-evaluation\.ajpadavano\.chatgpt\.site"]:
        require(not re.search(pattern, text, re.I), "Public privacy boundary violation: " + pattern)
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--expectations", type=Path, required=True)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text())
    expectations = json.loads(args.expectations.read_text())
    errors = verify(catalog, expectations)
    result = {"status": "failed" if errors else "passed", "errors": errors,
              "unique_objects": len(catalog.get("objects", [])), "file_occurrences": len(catalog.get("origins", [])),
              "expectation_records": len(expectations.get("expectations", [])),
              "reference_records": len(expectations.get("reference_records", []))}
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
