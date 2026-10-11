#!/usr/bin/env python3
"""Merge completed God-here recovery receipts without opening or fetching media.

The output catalog is an inventory of bytes, not an artistic acceptance ledger.
Every input is explicit; broad Library searches and runtime session inventories
are intentionally excluded from the private custody deliverable as well.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import unicodedata
from urllib.parse import unquote, urlsplit, urlunsplit

REPOSITORY = "4444J99/audiovisual-media-postproduction-system"
SHA = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
INPUTS = [
    "local-audit/supplied-file-inventory.json",
    "local-audit/recovered-top-level-inventory.json",
    "local-audit/media-validation.json",
    "local-audit/zip-integrity-and-extraction.json",
    "local-audit/historical-22-comparison.json",
    "local-audit/canonical-site-media-validation.json",
    "local-audit/retained-image-and-evaluation-validation.json",
    "local-audit/historical-site-media-validation.json",
    "local-audit/verification-methods-and-versions.json",
    "site-media-audit/media-validation-cache.json",
    "recovery-audit/artifact-inventory.json",
    "recovery-audit/media-validation-cache.json",
    "recovery-audit/image-validation-cache.json",
    "recovery-audit/failed-media-identities.json",
    "recovery-audit/verified-file-records.json",
    "recovery-audit/FINAL-SUMMARY.json",
    "recovery-audit/archive-validation.json",
    "recovery-audit/private-input-locations.json",
    "recovery-audit/local-copy-release.json",
    "recovery-audit/document-reference-index.json",
    "recovery-audit/site-media-validation.json",
    "repo-audit/branch-blob-inventory.json",
    "repo-audit/site-file-inventory.json",
    "repo-audit/site-history-file-inventory.json",
    "repo-audit/site-history-artifact-reference-records.json",
    "repo-audit/site-history-coverage.json",
    "repo-audit/evaluation-site-file-inventory.json",
    "repo-audit/evaluation-private-archive-member-inventory.json",
    "repo-audit/evaluation-private-original-reference-records.json",
    "repo-audit/evaluation-site-artifact-reference-records.json",
    "repo-audit/evaluation-site-validation.json",
    "repo-audit/artifact-reference-records.json",
    "repo-audit/site-artifact-reference-records.json",
    "repo-audit/parameterized-reference-records.json",
    "repo-audit/github-history-coverage.json",
    "repo-audit/github-history-file-inventory.json",
    "repo-audit/historical-commit-artifact-reference-records.json",
    "history-audit/recovery-index-flat.json",
    "history-audit/god-here-historical-paths-earlier.json",
    "history-audit/reported-artifact-labels.json",
    "history-audit/page-artifact-references.json",
    "history-audit/page-ref-ghere-zip.json",
    "history-audit/coverage-summary.json",
    "history-audit/unresolved-native-register.json",
    "catalog-additions.json",
]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def valid_sha(value):
    return isinstance(value, str) and bool(SHA.fullmatch(value))


def unwrap(value):
    while isinstance(value, dict) and isinstance(value.get("structuredContent"), dict):
        value = value["structuredContent"]
    return value


def array(value, key=None):
    if key and isinstance(value, dict):
        value = value.get(key, [])
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return []


def logical_name(value):
    """Publish a filename/label, never an original private URI or path."""
    value = str(value or "unnamed-reference").strip()
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value):
        value = unquote(urlsplit(value).path)
    value = value.split("?", 1)[0].split("#", 1)[0].replace("\\", "/")
    value = value.rsplit("/", 1)[-1]
    value = re.sub(r"[\x00-\x1f\x7f]", "", value).strip()
    if re.search(r"(?:libfile_|appgprj_|file_000000|library-file:|Bearer )", value, re.I):
        return "private-reference-" + digest(value)[:16]
    return value[:280] or "unnamed-reference"


def norm_name(value):
    value = unicodedata.normalize("NFKC", logical_name(value)).casefold()
    return re.sub(r"[^\w.]+", "", value)


def file_type(name, mime=None):
    ext = Path(name).suffix.casefold()
    if ext in {".zip", ".tar", ".gz", ".tgz", ".7z"}:
        return "archive"
    if ext in {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}:
        return "video"
    if ext in {".wav", ".m4a", ".mp3", ".aac", ".flac", ".ogg", ".aiff", ".opus"}:
        return "audio"
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff", ".svg", ".heic"}:
        return "image"
    if ext in {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".css", ".html", ".sh", ".ipynb"}:
        return "code"
    if ext in {".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".lock", ".patch"}:
        return "metadata"
    if ext in {".md", ".txt", ".pdf", ".docx", ".rtf"}:
        return "document"
    if ext in {".csv", ".tsv", ".xlsx", ".parquet", ".npy", ".npz"}:
        return "data"
    if ext in {".onnx", ".pth", ".pt", ".safetensors", ".tflite"}:
        return "model"
    if mime and mime.startswith("image/"):
        return "image"
    return "other"


def private_clean(value):
    """Keep stable private locators, remove ephemeral signed URL credentials."""
    if isinstance(value, dict):
        return {k: private_clean(v) for k, v in value.items()
                if k.lower() not in {"download_url", "authorization", "access_token", "refresh_token", "api_key"}}
    if isinstance(value, list):
        return [private_clean(v) for v in value]
    if isinstance(value, str):
        def redact_url(match):
            parts = urlsplit(match.group(0))
            if re.search(r"(?:sig=|token=|x-amz-|signature=|credential=)", parts.query, re.I):
                return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
            return match.group(0)
        return re.sub(r"https?://[^\s<>\"']+", redact_url, value)
    return value


class Compiler:
    def __init__(self, base, out):
        self.base, self.out = base.resolve(), out.resolve()
        self.now = dt.datetime.now(dt.timezone.utc).isoformat()
        self.data, self.input_evidence = {}, []
        self.objects, self.origins, self.private_origins = {}, {}, {}
        self.errors, self.warnings, self.unhashed = [], [], []
        self.raw_expectations, self.references = [], []
        self.private_expectations, self.private_references = [], []
        self.parameterized_references = []
        self.private_object_names = {}
        self.document_records, self.document_references = [], []
        self.archive_checks, self.media_checks = {}, {}
        self.image_checks, self.failure_categories = {}, {}
        self.release_by_hash = collections.defaultdict(list)
        self.flat_by_path = collections.defaultdict(list)
        self.flat_by_logical = collections.defaultdict(list)
        self.input_snapshots = []

    def read_inputs(self):
        for rel in INPUTS:
            p = self.base / rel
            if not p.exists():
                continue
            raw = p.read_bytes()
            value = json.loads(raw)
            self.data[rel] = value
            self.input_evidence.append({"input": rel, "sha256": hashlib.sha256(raw).hexdigest(),
                                        "bytes": len(raw), "updated_at_utc": value.get("updated_at_utc") if isinstance(value, dict) else None})
            self.input_snapshots.append((rel, private_clean(value)))
        for row in array(self.data.get("history-audit/recovery-index-flat.json")):
            self.flat_by_path[str(row.get("local_path", ""))].append(row)
            self.flat_by_logical[self.locator_logical(row)].append(row)
        for row in array(self.data.get("recovery-audit/local-copy-release.json"), "records"):
            if valid_sha(row.get("sha256")):
                self.release_by_hash[row["sha256"]].append(row)
        self.media_checks.update(self.data.get("recovery-audit/media-validation-cache.json", {}).get("entries", {}))
        for sha, row in self.data.get("site-media-audit/media-validation-cache.json", {}).get("entries", {}).items():
            previous = self.media_checks.get(sha, {})
            old = previous.get("full_decode", {}).get("status")
            new = row.get("full_decode", {}).get("status")
            if old and new and old != new:
                self.errors.append({"kind": "conflicting_full_decode_receipts", "sha256": sha, "statuses": [old, new]})
            self.media_checks.setdefault(sha, row)
        self.image_checks.update(self.data.get("recovery-audit/image-validation-cache.json", {}).get("entries", {}))
        self.failure_categories.update({r["sha256"]: r.get("category") for r in array(self.data.get("recovery-audit/failed-media-identities.json"), "failures")})
        supplied_hashes = {r["logical_path"]: r["sha256"] for r in array(self.data.get("local-audit/supplied-file-inventory.json"), "files")}
        for row in array(self.data.get("local-audit/media-validation.json"), "results"):
            if row.get("logical_path") in supplied_hashes:
                self.media_checks.setdefault(supplied_hashes[row["logical_path"]], row)
        for row in array(self.data.get("recovery-audit/archive-validation.json"), "entries"):
            if valid_sha(row.get("sha256")):
                self.archive_checks[row["sha256"]] = row
        supplied_zip = self.data.get("local-audit/zip-integrity-and-extraction.json", {})
        if valid_sha(supplied_zip.get("sha256")):
            self.archive_checks[supplied_zip["sha256"]] = {
                "status": "passed" if supplied_zip.get("extraction_status") == "completed_safe" else "not_verified",
                "member_files": supplied_zip.get("member_count"), "all_members_streamed_to_EOF": True,
                "crc_failures": [] if supplied_zip.get("crc_failure_member") is None else [supplied_zip["crc_failure_member"]],
                "media_validation_complete": True,
            }
        evaluation_members = self.data.get("repo-audit/evaluation-private-archive-member-inventory.json", {})
        evaluation_validation = self.data.get("repo-audit/evaluation-site-validation.json", {})
        evaluation_summary = evaluation_validation.get("summary", {})
        if valid_sha(evaluation_members.get("archive_sha256")) and evaluation_summary.get("archive_crc_passed") is True:
            self.archive_checks[evaluation_members["archive_sha256"]] = {
                "status": "passed", "member_files": evaluation_summary.get("archive_members"),
                "all_members_streamed_to_EOF": True, "crc_failures": [], "media_validation_complete": True,
            }

    def physical(self, logical):
        if not logical or "!/" in logical:
            return None
        if logical.startswith("sources/"):
            return str(self.base.parent / "project_sources" / logical.split("/", 1)[1])
        if logical.startswith("bundles/god-here-eight-suggestions/"):
            return str(self.base / "local-audit/extracted-eight-suggestions" / logical.rsplit("/", 1)[1])
        if logical.startswith("/"):
            return logical
        return str(self.base / logical)

    def locator_logical(self, row):
        if row.get("logical_path"):
            return row["logical_path"]
        path = str(row.get("local_path", "")).replace("\\", "/")
        if "/recovered/" in path:
            return "recovered/" + path.split("/recovered/", 1)[1]
        return row.get("logical_title", logical_name(path))

    def add(self, row, key, origin, private):
        sha = row.get("sha256")
        size = row.get("bytes", row.get("observed_size_bytes", row.get("declared_size_bytes")))
        if not valid_sha(sha):
            self.unhashed.append({"record": private_clean(row), "reason": "no_complete_computed_sha256_receipt"})
            return
        if not isinstance(size, int) or size < 0:
            self.errors.append({"kind": "invalid_size", "sha256": sha, "origin_key": key})
            return
        declared = row.get("expected_bytes", row.get("declared_size_bytes"))
        if isinstance(declared, int) and declared != size:
            self.errors.append({"kind": "declared_size_mismatch", "sha256": sha, "observed": size, "declared": declared, "origin_key": key})
        if sha in self.objects and self.objects[sha]["bytes"] != size:
            self.errors.append({"kind": "same_sha256_size_conflict", "sha256": sha, "sizes": [self.objects[sha]["bytes"], size], "origin_key": key})
            return
        name = logical_name(row.get("logical_title") or row.get("filename") or row.get("logical_path") or row.get("path") or row.get("repository_path"))
        obj = self.objects.setdefault(sha, {"sha256": sha, "bytes": size, "logical_names": set(), "types": set(), "origin_ids": set(), "roles": set()})
        obj["logical_names"].add(name)
        obj["types"].add(file_type(name, row.get("mime_type")))
        obj["roles"].add("original_source" if name in {"01-God-s-Ears-First-Draft-May-21-2020.txt", "02-2020-04-26-god-s-ears-second-draft.mp4"} else "preserved_for_recovery_review")
        if name == "historical-download-receipts-earlier.json":
            obj["roles"].add("cross_project_recovery_evidence")
        oid = "origin-" + digest(key)[:24]
        obj["origin_ids"].add(oid)
        origin = dict(origin, origin_id=oid)
        private = dict(private, origin_id=oid, sha256=sha, bytes=size)
        if oid in self.origins and self.private_origins[oid]["sha256"] != sha:
            self.errors.append({"kind": "same_location_conflicting_sha256", "origin_id": oid, "hashes": [sha, self.private_origins[oid]["sha256"]]})
            return
        if oid not in self.origins:
            self.origins[oid], self.private_origins[oid] = origin, private
        else:
            self.origins[oid].update(origin)
            self.private_origins[oid].update(private)

    def add_local(self, row):
        logical = row.get("logical_path", "")
        member = row.get("kind") == "archive_member" or bool(row.get("container_sha256"))
        if member:
            container, path = row.get("container_sha256"), row.get("member_path")
            if not path and "!/" in logical:
                path = logical.split("!/", 1)[1]
            if not path:
                self.errors.append({"kind": "missing_archive_member_path", "sha256": row.get("sha256")})
                return
            safe = not str(path).startswith(("/", "\\")) and ".." not in PurePosixPath(str(path).replace("\\", "/")).parts
            public_path = str(path) if safe else logical_name(path)
            origin = {"kind": "archive_member", "container_sha256": container, "member_path": public_path,
                      "member_path_safe": safe, "access": "private_custody_reference", "crc_status": row.get("crc_validation", "passed" if row.get("byte_match_to_archive") else "not_yet_verified")}
            # One identical archive member is one occurrence even when its container has several copies.
            key = ["archive_member", container, path]
            private = {"kind": "archive_member", "logical_path": logical, "container_sha256": container, "member_path": path,
                       "crc32": row.get("crc32"), "compressed_bytes": row.get("compressed_bytes"), "audit_record": row}
        else:
            physical = self.physical(logical)
            locators = self.flat_by_path.get(physical, []) or self.flat_by_logical.get(logical, [])
            if locators and locators[0].get("local_path"):
                physical = locators[0]["local_path"]
            present = bool(physical and Path(physical).is_file())
            released = bool(self.release_by_hash.get(row.get("sha256")))
            local_state = "present" if present else ("released_after_verified_recovery" if released else "not_currently_materialized")
            if present and released:
                local_state = "present_after_recorded_release"
                self.warnings.append({"kind": "local_copy_visible_after_release_receipt", "sha256": row.get("sha256"),
                                      "qualification": "Compiler observed an existing path; no file was downloaded or restored by the compiler"})
            origin = {"kind": "supplied_file" if row.get("kind") == "mounted_supplied_file" else "preserved_file",
                      "locator_types": sorted({r.get("locator_type", "local_audit") for r in locators}) or ["user_supplied" if row.get("kind") == "mounted_supplied_file" else "local_audit"],
                      "logical_name": logical_name(logical), "access": "private", "local_copy_status": local_state}
            key = ["local_file", logical]
            private = {"kind": origin["kind"], "logical_path": logical, "physical_path": physical,
                       "local_copy_status": local_state, "locators": locators, "audit_record": row}
            if released:
                private["release_receipts"] = self.release_by_hash[row["sha256"]]
        self.add(row, key, origin, private)

    def collect_objects(self):
        for row in array(self.data.get("local-audit/supplied-file-inventory.json"), "files"):
            self.add_local(row)
        for row in array(self.data.get("local-audit/recovered-top-level-inventory.json"), "verified_file_records"):
            self.add_local(row)
        for row in array(self.data.get("recovery-audit/artifact-inventory.json"), "entries"):
            self.add_local(row)
        for row in array(self.data.get("recovery-audit/verified-file-records.json"), "verified_file_records"):
            self.add_local(row)
        # Small later additions can have complete SHA receipts before the main streaming audit reaches them.
        for row in array(self.data.get("history-audit/recovery-index-flat.json")):
            if not valid_sha(row.get("sha256")):
                continue
            logical = self.locator_logical(row)
            local = dict(row, logical_path=logical, kind="top_level_recovered_file", bytes=row.get("observed_size_bytes", row.get("declared_size_bytes")))
            self.add_local(local)
        for row in array(self.data.get("repo-audit/branch-blob-inventory.json")):
            commit, path, branch = row.get("commit_sha"), row.get("repository_path"), row.get("branch")
            origin = {"kind": "github_blob", "repository": REPOSITORY, "commit_sha": commit, "repository_path": path,
                      "branch": branch, "access": "public", "url": f"https://github.com/{REPOSITORY}/blob/{commit}/{path}"}
            self.add(row, ["github", branch, commit, path], origin, {"kind": "github_blob", "record": row})
        for row in array(self.data.get("repo-audit/github-history-coverage.json"), "blob_versions"):
            if row.get("in_any_branch_head"):
                continue
            commit, path = row.get("source_commit"), row.get("repository_path")
            origin = {"kind": "historical_github_blob", "repository": REPOSITORY, "commit_sha": commit,
                      "repository_path": path, "access": "public", "url": f"https://github.com/{REPOSITORY}/blob/{commit}/{path}"}
            materialized = [r for r in array(self.data.get("repo-audit/github-history-file-inventory.json"), "files")
                            if r.get("sha256") == row.get("sha256") and r.get("repository_path") == path]
            self.add(row, ["historical_github_blob", path, row.get("sha256")], origin,
                     {"kind": "historical_github_blob", "record": row, "materialized_file_receipts": materialized})
        for rel, label, access in [
            ("repo-audit/site-file-inventory.json", "canonical-workbench", "public"),
            ("repo-audit/evaluation-site-file-inventory.json", "device-audience-study", "private"),
        ]:
            for row in array(self.data.get(rel), "files"):
                origin = {"kind": "site_source_file", "site_label": label, "source_commit": row.get("source_commit"),
                          "logical_name": logical_name(row.get("path")), "access": access,
                          "source_version_matches_recorded_commit": row.get("matches_source_commit"),
                          "deployment_status": row.get("deployment_status", "not_verified")}
                if access == "public":
                    origin["source_path"] = row.get("path")
                self.add(row, ["site", label, row.get("source_commit"), row.get("path")], origin, {"kind": "site_source_file", "site_label": label, "record": row})
        for row in array(self.data.get("repo-audit/site-history-file-inventory.json"), "files"):
            private = row.get("audience") not in {"public", "PUBLIC"}
            label = "device-audience-study" if private else "canonical-workbench"
            origin = {"kind": "historical_site_source_file", "site_label": label, "source_scope": "historical",
                      "source_commit": row.get("source_commit"), "logical_name": logical_name(row.get("path")),
                      "access": "private" if private else "public", "active_at_pinned_head": False,
                      "deployment_status": "historical_source_preserved_current_url_not_identity_evidence"}
            if not private:
                origin["historical_source_path"] = row.get("path")
            self.add(row, ["historical_site", label, row.get("source_commit"), row.get("path")], origin,
                     {"kind": "historical_site_source_file", "site_label": label, "record": row})
        for row in array(self.data.get("repo-audit/evaluation-private-archive-member-inventory.json"), "members"):
            self.add_local(dict(row, kind="archive_member", container_sha256=row.get("archive_sha256"),
                                member_path=row.get("path"), logical_path=row.get("archive_path", "") + "!/" + row.get("path", ""),
                                crc_validation="passed_on_stream_to_EOF"))
        for row in array(self.data.get("local-audit/canonical-site-media-validation.json"), "verified_file_records"):
            if not row.get("logical_path", "").startswith("playback-repair/"):
                continue
            origin = {"kind": "canonical_working_tree_file", "site_label": "canonical-workbench", "logical_name": logical_name(row["logical_path"]),
                      "source_path": "dist/media/dialogue-reference.mp4", "access": "public",
                      "access_qualification": "authorized destination audience; deployment completion is a separate gate",
                      "deployment_status": "restored_working_tree_not_yet_deployed", "source_commit": None}
            self.add(row, ["playback-repair", row["logical_path"]], origin,
                     {"kind": "canonical_working_tree_file", "physical_path": str(self.base / "workbench/dist/media/dialogue-reference.mp4"),
                      "preservation_keeper_path": self.physical(row["logical_path"]), "record": row})
        for row in array(self.data.get("catalog-additions.json"), "artifacts"):
            self.add(row, ["coordinator_addition", row.get("origin_key", row.get("local_path", row.get("logical_title")))],
                     row.get("public_origin", {"kind": "coordinator_verified_addition", "access": "private"}),
                     {"kind": "coordinator_verified_addition", "record": row})

    def evidence(self, records):
        out = []
        for row in records or []:
            entry = {"pointer": row.get("pointer")}
            commit, path, url = row.get("commit_sha"), row.get("repository_path"), row.get("url", "")
            if url.startswith(f"https://github.com/{REPOSITORY}/"):
                entry.update({"repository": REPOSITORY, "url": url.split("?", 1)[0]})
                if COMMIT.fullmatch(str(commit or "")):
                    entry["commit_sha"] = commit
                if path and not str(path).startswith(("/", "sandbox:")):
                    entry["repository_path"] = path
                if row.get("branch"):
                    entry["branch"] = row["branch"]
            else:
                entry.update({"source": "canonical-site-source" if row.get("source_control_system") == "Sites Git" else "private-project-record",
                              "source_record_id": "evidence-" + digest(row)[:20]})
                if COMMIT.fullmatch(str(commit or "")):
                    entry["source_commit"] = commit
                if path:
                    entry["logical_name"] = logical_name(path)
            out.append(entry)
        return out

    def reference_scope(self, row):
        raw = str(row.get("path_or_logical_id", ""))
        declared_scope = row.get("reference_scope", "")
        if "parameterized" in declared_scope or "filename-template" in row.get("status", ""):
            return "parameterized"
        if "runtime export contract" in row.get("status", "") or "runtime-export" in declared_scope:
            return "runtime_export_contract"
        if row.get("reference_scope") == "test-or-example-only":
            return "test_or_example"
        if re.search(r"(?:\$\{|\{\{|<[^>]+>|\[[^\]]*(?:0-9|index|frame)[^\]]*\])", raw):
            return "parameterized"
        ev = row.get("evidence", [])
        if ev and all(re.search(r"(?:^|/)(?:tests?|fixtures?|examples?)/|\.test\.", str(e.get("repository_path", ""))) for e in ev):
            return "test_or_example"
        if row.get("reference_kind") == "code-config-or-receipt":
            return "code_metadata_or_dependency"
        return "production_or_documentary"

    def expectation(self, rid, name, expected, size, category, raw, evidence=None, scope="god-here"):
        public = {"expectation_id": "expectation-" + digest(rid)[:24], "source_record_id": rid,
                  "logical_name": logical_name(name), "expected_sha256": expected if valid_sha(expected) else None,
                  "expected_bytes": size if isinstance(size, int) else None,
                  "category": category, "project_scope": scope, "evidence": evidence or []}
        self.raw_expectations.append(public)
        self.private_expectations.append(dict(public, original_record=private_clean(raw)))

    def collect_expectations(self):
        for row in array(self.data.get("history-audit/god-here-historical-paths-earlier.json")):
            rid = "historical-uri-" + digest([row.get("sandbox"), row.get("chat"), row.get("message_id")])[:24]
            self.expectation(rid, row.get("name"), row.get("sha256"), row.get("bytes", row.get("expected_bytes")),
                             "historical_file", row, [{"source": "earlier-recovery-receipt", "source_record_id": rid}])
        for row in array(self.data.get("local-audit/historical-22-comparison.json"), "rows"):
            rid = "historical-mounted-" + digest([row.get("historical_filename"), row.get("sha256")])[:24]
            self.expectation(rid, row.get("historical_filename"), row.get("sha256"), row.get("bytes"),
                             "historical_22_file_inventory", row, [{"source": "historical-22-file-inventory", "source_record_id": rid}])
        for i, row in enumerate(array(self.data.get("history-audit/reported-artifact-labels.json"))):
            rid = "page-label-" + digest([row.get("page_id"), row.get("logical_label"), row.get("prompt_excerpt"), i])[:24]
            self.expectation(rid, row.get("logical_label"), None, None, "reported_deliverable_label", row,
                             [{"source": "project-conversation-report", "source_record_id": rid}])
        repository_references = {r["reference_id"]: dict(r) for r in array(self.data.get("repo-audit/artifact-reference-records.json"), "records")}
        for row in array(self.data.get("repo-audit/historical-commit-artifact-reference-records.json"), "records"):
            existing = repository_references.get(row["reference_id"])
            if existing:
                combined = list(existing.get("evidence", [])) + list(row.get("evidence", []))
                existing["evidence"] = list({digest(e): e for e in combined}.values())
            else:
                repository_references[row["reference_id"]] = row
        canonical_references = {r["reference_id"]: dict(r) for r in array(self.data.get("repo-audit/site-artifact-reference-records.json"), "records")}
        evaluation_references = {r["reference_id"]: dict(r) for r in array(self.data.get("repo-audit/evaluation-site-artifact-reference-records.json"), "records")}
        for row in array(self.data.get("repo-audit/site-history-artifact-reference-records.json"), "records"):
            groups = collections.defaultdict(list)
            for evidence in row.get("evidence", []):
                groups["private" if evidence.get("audience") == "owner-only" else "public"].append(evidence)
            for audience, evidence in groups.items():
                target = evaluation_references if audience == "private" else canonical_references
                existing = target.get(row["reference_id"])
                if existing:
                    combined = list(existing.get("evidence", [])) + evidence
                    existing["evidence"] = list({digest(e): e for e in combined}.values())
                else:
                    target[row["reference_id"]] = dict(row, evidence=evidence)
        for rows, surface in [(list(repository_references.values()), "github_repository"),
                              (list(canonical_references.values()), "canonical_site"),
                              (list(evaluation_references.values()), "private_evaluation_site")]:
            for row in rows:
                rid = surface + ":" + row["reference_id"]
                scope = self.reference_scope(row)
                reference = {"reference_id": rid, "source_reference_id": row["reference_id"], "source_surface": surface,
                             "logical_name": logical_name(row.get("filename") or row.get("path_or_logical_id")),
                             "expected_sha256": row.get("expected_sha256") if valid_sha(row.get("expected_sha256")) else None,
                             "reference_kind": row.get("reference_kind"), "reference_scope": scope,
                             "evidence": self.evidence(row.get("evidence")), "workstreams": row.get("workstreams", [])}
                self.references.append(reference)
                self.private_references.append(dict(reference, original_record=private_clean(row)))
                declared = row.get("declared") or {}
                size = declared.get("bytes", declared.get("size_bytes", declared.get("byte_size")))
                self.expectation(rid, reference["logical_name"], reference["expected_sha256"], size, scope, row, reference["evidence"])
        for row in array(self.data.get("repo-audit/evaluation-private-original-reference-records.json"), "records"):
            rid = "private-performer-original-" + digest([row.get("filename"), row.get("expected_sha256")])[:24]
            locations = row.get("verified_locations", [])
            self.expectation(rid, row.get("filename"), row.get("expected_sha256"), locations[0].get("bytes") if locations else None,
                             "private_performer_original", row, [{"source": "private-performer-reference-manifest", "source_record_id": rid}])
        for i, row in enumerate(array(self.data.get("repo-audit/parameterized-reference-records.json"))):
            rid = "parameterized-" + digest([row.get("path"), row.get("evidence"), i])[:24]
            self.parameterized_references.append({"reference_id": rid, "logical_name": logical_name(row.get("path")),
                                                   "reference_scope": "parameterized", "status": "not_an_individual_artifact",
                                                   "evidence": self.evidence([row.get("evidence", {})])})
            self.private_references.append({"reference_id": rid, "original_record": private_clean(row)})
        # Readable metadata proves this ZIP is named and accessible to the Page, not recovered binary bytes.
        zipped = unwrap(self.data.get("history-audit/page-ref-ghere-zip.json", {}))
        if zipped:
            self.expectation("page-native-ghere-003-zip", "ghere-003-audioscrape.zip", None, zipped.get("byte_size"),
                             "page_native_binary_unavailable", zipped, [{"source": "page-linked-file-metadata", "source_record_id": "page-native-ghere-003-zip"}])
        for row in array(self.data.get("history-audit/unresolved-native-register.json"), "records"):
            rid = "native-register-" + digest(row.get("expected_sha256"))[:24]
            self.expectation(rid, row.get("logical_name"), row.get("expected_sha256"), row.get("expected_bytes"),
                             "native_register_unavailable", row,
                             [{"source": "archive-gap-project-report-and-current-runtime-health", "source_record_id": rid}],
                             scope="cross_project_recovery_register")

    def collect_document_references(self):
        """Preserve the bounded static scan, including its unexecuted/inline limits."""
        extension = re.compile(r"\.(?:mp4|mkv|mov|webm|m4a|wav|flac|mp3|zip|tar|png|jpe?g|webp|pdf|json|jsonl|csv|tsv|txt|md|py|mjs|js|html|css|onnx|xlsx)$", re.I)
        for row in array(self.data.get("recovery-audit/document-reference-index.json"), "entries"):
            sha, logical = row.get("sha256"), row.get("logical_path", "")
            did = "document-" + digest([sha, logical])[:24]
            entries = []
            for i, value in enumerate(row.get("literal_relative_html_dependencies", [])):
                entries.append(("html_literal_dependency", i, value, None))
            for i, command in enumerate(row.get("candidate_command_lines_not_executed", [])):
                try:
                    tokens = shlex.split(command)
                except ValueError:
                    tokens = re.findall(r"[^\s]+", command)
                for j, token in enumerate(tokens):
                    candidate = token.strip("'\"`,;()")
                    if extension.search(candidate):
                        entries.append(("unexecuted_command_path", f"{i}:{j}", candidate, command))
            for i, value in enumerate(row.get("external_urls_without_queries", [])):
                entries.append(("external_resource_locator", i, value, None))
            reference_ids = []
            for kind, position, value, command in entries:
                rid = "document-ref-" + digest([did, kind, position, value])[:24]
                name = logical_name(value)
                directory = str(value).endswith("/") and kind == "html_literal_dependency"
                template = bool(re.search(r"(?:/path/|/path/to/|\$\{|<[^>]+>|\{[^}]+\})", str(value)))
                scope = "directory_dependency" if directory else ("test_or_example" if template or row.get("test_file_candidate") else kind)
                reference = {"reference_id": rid, "source_surface": "recovered_document", "document_record_id": did,
                             "document_sha256": sha, "logical_name": name, "expected_sha256": None,
                             "reference_scope": scope, "reference_kind": kind,
                             "evidence": [{"source": "recovered-document-static-index", "document_sha256": sha,
                                           "source_record_id": did, "pointer": f"{kind}:{position}"}]}
                if directory:
                    reference.update(status="documented_directory_dependency", matched_sha256=None, candidate_sha256s=[])
                elif kind == "external_resource_locator" and not extension.search(name):
                    reference.update(status="documented_external_resource_not_a_file_identity", matched_sha256=None, candidate_sha256s=[])
                else:
                    self.expectation(rid, name, None, None, "recovered_document_" + scope,
                                     {"document_sha256": sha, "document_logical_path": logical, "reference": value, "command_not_executed": command},
                                     reference["evidence"])
                self.document_references.append(reference)
                self.private_references.append(dict(reference, original_reference=value, original_document_path=logical, command_not_executed=command))
                reference_ids.append(rid)
            self.document_records.append({"document_record_id": did, "sha256": sha, "logical_name": logical_name(logical),
                "source_code_or_review_page": row.get("source_code_or_review_page", False),
                "python_main_entrypoint": row.get("python_main_entrypoint", False), "test_file_candidate": row.get("test_file_candidate", False),
                "unexecuted_candidate_commands": len(row.get("candidate_command_lines_not_executed", [])),
                "literal_html_dependencies": len(row.get("literal_relative_html_dependencies", [])),
                "external_resource_locators": len(row.get("external_urls_without_queries", [])),
                "inline_media_data_url_markers": row.get("inline_media_data_url_markers", 0),
                "inline_media_identity_status": "preserved_within_document_bytes_not_independently_extracted_or_hashed",
                "reference_ids": reference_ids,
                "scope": "Recorded static fields only; commands remain unexecuted and dynamic references require runtime binding"})

    def finalize_objects(self):
        media_members = collections.defaultdict(list)
        for oid, origin in self.origins.items():
            if origin["kind"] == "archive_member":
                outer = origin.get("container_sha256")
                origin["container_identity_verified"] = outer in self.objects
                if outer not in self.objects:
                    self.errors.append({"kind": "archive_member_without_verified_container", "origin_id": oid, "container_sha256": outer})
                released = bool(self.release_by_hash.get(outer))
                origin["access_path_status"] = "remote_container_preserved_local_release_recorded" if released else "verified_container_reference"
                sha = self.private_origins[oid]["sha256"]
                if {"audio", "video"} & self.objects[sha]["types"]:
                    media_members[outer].append(sha)
        finalized = []
        for sha, obj in sorted(self.objects.items()):
            kinds = sorted(obj.pop("types"))
            av = bool({"audio", "video"} & set(kinds))
            check = self.media_checks.get(sha, {})
            decode = check.get("full_decode", {})
            status = "not_applicable" if not av else "not_yet_verified"
            if decode.get("status") == "passed":
                status = "passed"
            elif decode and (decode.get("exit_code") not in (None, 0) or decode.get("status") in {"failed", "failed_or_requires_review"}):
                status = "failed"
            verification = {"content_identity": "sha256_computed_or_source_bytes_matched_provider_sha256",
                            "full_decode_status": status, "media_probe_status": "passed" if check.get("probe_exit_code") == 0 else ("failed" if check.get("probe_exit_code") is not None else ("not_yet_verified" if av else "not_applicable")),
                            "browser_playback": "not_established_by_hash_or_decode", "render_reproducibility": "not_established_by_hash_or_decode"}
            if check:
                streams = (check.get("probe") or {}).get("streams", [])
                verification["media_streams"] = [{k: s[k] for k in ["codec_type", "codec_name", "width", "height", "sample_rate", "channels", "duration", "avg_frame_rate"] if k in s} for s in streams]
                verification["full_decode_exit_code"] = decode.get("exit_code")
                error = str(decode.get("error_output", "")) + str(check.get("probe_stderr", ""))
                verification["failure_categories"] = [label for pattern, label in [("moov atom not found", "missing_moov_atom"), ("corrupt input packet", "corrupt_input_packet"), ("Invalid data found", "invalid_media_data"), ("premature", "premature_end")] if pattern in error]
                if self.failure_categories.get(sha):
                    verification["failure_categories"].append(self.failure_categories[sha])
            if "image" in kinds:
                image_check = self.image_checks.get(sha, {})
                verification["image_decode_status"] = image_check.get("status", "passed" if status == "passed" else "not_yet_verified")
                verification["image_decode_method"] = image_check.get("method", "ffmpeg_full_image_decode" if status == "passed" else None)
                for field in ("width", "height", "format"):
                    if field in image_check:
                        verification["image_" + field] = image_check[field]
            if sha in self.archive_checks:
                arc = self.archive_checks[sha]
                member_hashes = media_members.get(sha, [])
                unique = set(member_hashes)
                passed = sum(self.media_checks.get(h, {}).get("full_decode", {}).get("status") == "passed" for h in unique)
                failed = sorted(h for h in unique if self.media_checks.get(h, {}).get("full_decode", {}).get("status") in {"failed", "failed_or_requires_review"})
                verification["archive"] = {"crc_status": arc.get("status", "not_verified"), "member_files": arc.get("member_files", arc.get("member_count")),
                    "all_members_streamed_to_eof": arc.get("all_members_streamed_to_EOF", False), "crc_failure_count": len(arc.get("crc_failures", [])),
                    "audio_video_member_occurrences": len(member_hashes), "unique_audio_video_objects": len(unique),
                    "unique_audio_video_decode_passes": passed, "unique_audio_video_decode_failures": len(failed),
                    "unique_audio_video_not_yet_verified": len(unique) - passed - len(failed), "failed_member_sha256s": failed,
                    "qualification": "ZIP CRC preservation does not establish that an embedded media file is complete or usable"}
            origin_ids = sorted(obj.pop("origin_ids"))
            roles = sorted(obj.pop("roles"))
            names = sorted(obj.pop("logical_names"))
            preservation = "preserved_but_decode_failed" if status == "failed" else "byte_identity_preserved"
            if sha in self.release_by_hash:
                preservation += ";remote_original_preserved_with_local_release_receipt"
            obj.update({"logical_names": names, "type": kinds[0] if len(kinds) == 1 else "mixed_extension_identity", "types": kinds,
                        "roles": roles, "origin_ids": origin_ids, "file_occurrence_count": len(origin_ids), "verification": verification,
                        "preservation_status": preservation, "retention": {"status": "retained_for_recovery_review", "production_disposition": "pending"},
                        "artistic_acceptance": {"status": "pending", "evidence": []}, "canonical_workbench_integration": "not_established_by_preservation"})
            finalized.append(obj)
        return finalized

    def resolve(self, row, name_index):
        expected = row.get("expected_sha256")
        if expected:
            obj = self.objects.get(expected)
            if obj:
                size = row.get("expected_bytes")
                if size is not None and size != obj["bytes"]:
                    row.update({"status": "expected_size_conflict", "matched_sha256": expected, "candidate_sha256s": []})
                    self.errors.append({"kind": "expected_sha256_size_conflict", "expected_bytes": size, "observed_bytes": obj["bytes"], "sha256": expected, "record_id": row.get("expectation_id", row.get("reference_id"))})
                else:
                    row.update({"status": "exact_hash_recovered", "matched_sha256": expected, "candidate_sha256s": [],
                                "recovered_object_usability": obj["verification"]["full_decode_status"]})
            else:
                row.update({"status": "unavailable", "matched_sha256": None, "candidate_sha256s": sorted(name_index.get(norm_name(row["logical_name"]), [])),
                            "qualification": "Expected byte identity was not recovered in the inspected surfaces; a search miss is not proof of nonexistence"})
        else:
            candidates = sorted(name_index.get(norm_name(row["logical_name"]), []))
            row.update({"status": "identity_unresolved_name_candidates" if candidates else "unavailable", "matched_sha256": None, "candidate_sha256s": candidates,
                        "qualification": "Filename or label similarity does not prove historical byte identity"})
        return row

    def pseudonymize_private_evaluation(self):
        """Publish private performer-reference identity without original aliases."""
        sensitive, public_names = set(), collections.defaultdict(set)
        private_photo_name = re.compile(r"^(?:IMG_[0-9]+|imagejpeg[_-]?[0-9]*)|(?:chris|enrique).*(?:reference|photo)", re.I)
        for oid, origin in self.origins.items():
            sha = self.private_origins[oid]["sha256"]
            if origin["kind"] in {"site_source_file", "historical_site_source_file"} and origin.get("site_label") == "device-audience-study":
                sensitive.add(sha)
            if origin.get("access") == "public":
                for key in ("logical_name", "repository_path", "source_path", "historical_source_path"):
                    if origin.get(key):
                        public_names[sha].add(logical_name(origin[key]))
        private_container = self.data.get("repo-audit/evaluation-private-archive-member-inventory.json", {}).get("archive_sha256")
        for oid, origin in self.origins.items():
            if origin.get("container_sha256") == private_container:
                sensitive.add(self.private_origins[oid]["sha256"])
        evaluation_sensitive = set(sensitive)
        safe_aliases = collections.defaultdict(set)
        for sha, obj in self.objects.items():
            if public_names.get(sha):
                continue
            if any(private_photo_name.search(name) for name in obj["logical_names"]):
                sensitive.add(sha)
                if sha not in evaluation_sensitive:
                    safe_aliases[sha].update(name for name in obj["logical_names"] if not private_photo_name.search(name))

        def alias(sha, name, fallback=None):
            if sha and public_names.get(sha):
                return sorted(public_names[sha])[0]
            if sha and safe_aliases.get(sha):
                return sorted(safe_aliases[sha])[0]
            suffix = Path(logical_name(name)).suffix.lower()
            if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
                suffix = ".bin"
            return "private-performer-reference-" + (sha or digest(fallback or name))[:16] + suffix

        for sha, obj in self.objects.items():
            self.private_object_names[sha] = list(obj["logical_names"])
            if sha in sensitive:
                replacement = sorted(public_names.get(sha, set()) or safe_aliases.get(sha, set()))
                obj["logical_names"] = replacement or sorted({alias(sha, name) for name in obj["logical_names"]})
                obj["private_aliases_redacted"] = True
        for oid, origin in self.origins.items():
            sha = self.private_origins[oid]["sha256"]
            if sha not in sensitive:
                continue
            if origin.get("access") == "public":
                continue
            if "logical_name" in origin:
                origin["logical_name"] = alias(sha, origin["logical_name"])
            if "member_path" in origin:
                origin["member_path"] = alias(sha, origin["member_path"])
                origin["member_path_redacted"] = True
        for row in self.references + self.raw_expectations:
            sensitive_surface = row.get("source_surface") == "private_evaluation_site" or row.get("source_record_id", "").startswith("private_evaluation_site:") or row.get("category") == "private_performer_original"
            sha = row.get("expected_sha256") or row.get("matched_sha256")
            private_named = bool(private_photo_name.search(row["logical_name"])) and not public_names.get(sha)
            if sensitive_surface or private_named:
                row["logical_name"] = alias(sha, row["logical_name"], row.get("reference_id", row.get("expectation_id")))
                row["private_alias_redacted"] = True
                for evidence in row.get("evidence", []):
                    if evidence.get("source") != "canonical-site-source":
                        continue
                    evidence["source"] = "private-evaluation-site-source"
                    if "logical_name" in evidence:
                        evidence["logical_name"] = "private-source-reference"
        for row in self.document_records:
            if row.get("sha256") in sensitive:
                row["logical_name"] = alias(row["sha256"], row["logical_name"])
                row["private_alias_redacted"] = True
        for row in self.document_references:
            if row.get("document_sha256") in sensitive:
                row["logical_name"] = alias(None, row["logical_name"], row["reference_id"])
                row["private_alias_redacted"] = True

    def build(self):
        self.read_inputs()
        self.collect_objects()
        self.collect_expectations()
        self.collect_document_references()
        objects = self.finalize_objects()
        names = collections.defaultdict(set)
        for obj in objects:
            for name in obj["logical_names"]:
                names[norm_name(name)].add(obj["sha256"])
        for row in self.raw_expectations:
            self.resolve(row, names)
        for row in self.references:
            self.resolve(row, names)
        for row in self.document_references:
            if "status" not in row:
                self.resolve(row, names)
        self.pseudonymize_private_evaluation()
        counts = {
            "unique_sha256_objects": len(objects), "file_occurrences": len(self.origins),
            "unique_object_bytes": sum(o["bytes"] for o in objects),
            "file_occurrence_bytes": sum(v["bytes"] for v in self.private_origins.values()),
            "objects_by_type": dict(sorted(collections.Counter(o["type"] for o in objects).items())),
            "occurrences_by_origin_kind": dict(sorted(collections.Counter(o["kind"] for o in self.origins.values()).items())),
            "unique_audio_video_objects": sum(bool({"audio", "video"} & set(o["types"])) for o in objects),
            "unique_media_objects_including_images": sum(bool({"audio", "video", "image"} & set(o["types"])) for o in objects),
            "unique_image_objects": sum("image" in o["types"] for o in objects),
            "unique_code_objects": sum("code" in o["types"] for o in objects),
            "unique_archive_objects": sum("archive" in o["types"] for o in objects),
            "archive_objects_with_crc_receipts": len(self.archive_checks),
            "audio_video_full_decode_passes": sum(o["verification"]["full_decode_status"] == "passed" and bool({"audio", "video"} & set(o["types"])) for o in objects),
            "audio_video_full_decode_failures": sum(o["verification"]["full_decode_status"] == "failed" and bool({"audio", "video"} & set(o["types"])) for o in objects),
            "audio_video_full_decode_pending": sum(o["verification"]["full_decode_status"] == "not_yet_verified" and bool({"audio", "video"} & set(o["types"])) for o in objects),
            "image_decode_passes": sum(o["verification"].get("image_decode_status") == "passed" for o in objects),
            "image_decode_pending": sum(o["verification"].get("image_decode_status") == "not_yet_verified" for o in objects),
            "artistic_accepted_objects": 0,
            "historical_and_reference_expectation_records": len(self.raw_expectations),
            "repository_reference_records": sum(r["source_surface"] == "github_repository" for r in self.references),
            "canonical_site_reference_records": sum(r["source_surface"] == "canonical_site" for r in self.references),
            "private_evaluation_site_reference_records": sum(r["source_surface"] == "private_evaluation_site" for r in self.references),
            "separate_parameterized_reference_occurrences": len(self.parameterized_references),
            "reachable_historical_git_reference_records_inspected": len(array(self.data.get("repo-audit/historical-commit-artifact-reference-records.json"), "records")),
            "historical_site_reference_records_inspected": len(array(self.data.get("repo-audit/site-history-artifact-reference-records.json"), "records")),
            "recovered_document_records": len(self.document_records),
            "recovered_document_reference_records": len(self.document_references),
            "embedded_media_markers_in_document_occurrences": sum(r["inline_media_data_url_markers"] for r in self.document_records),
            "unhashed_materialization_records": len(self.unhashed),
        }
        definitions = {
            "object": "One complete byte string identified by its full SHA-256 and byte count. Revisions with different hashes remain separate.",
            "file_occurrence": "One recovered file location, branch-tip path, source-site path, or container-SHA/member-path pair; multiple receipt rows for the same occurrence are merged.",
            "archive_member": "An independently hashed byte string contained in a verified outer archive. Member bytes and outer archive bytes are separately counted, so totals are not disk usage.",
            "code": "Preserved code file bytes. Their existence does not prove executable dependencies, deterministic rendering, or artistic acceptance.",
            "original_source": "User-supplied screenplay or source video identity retained unchanged and joined by exact SHA-256.",
            "reference_record": "A textual citation or checksum assertion from a report/code/document. References never inflate the recovered-object denominator.",
            "name_candidate": "Potential filename/normalized-label match, never a byte-identity resolution.",
            "archive_crc": "Successful ZIP container/member integrity checks can coexist with intrinsically incomplete or damaged media members.",
            "acceptance": "Preservation, full decode, browser playback, reproducible rendering, and artistic acceptance are separate gates.",
        }
        public_inputs = [{k: v for k, v in x.items() if v is not None} for x in self.input_evidence]
        catalog = {"schema_version": "god-here.recovery-catalog.v1", "generated_at_utc": self.now,
                   "project": "god-here", "scope": "Bounded currently accessible project recovery surfaces; historical recovery and artistic acceptance remain open",
                   "definitions": definitions, "counts": counts, "inputs": public_inputs,
                   "objects": objects, "origins": sorted(self.origins.values(), key=lambda x: x["origin_id"]),
                   "acceptance_default": "pending; no test or technical validation is treated as user artistic approval"}
        exp_counts = {"expectation_records": len(self.raw_expectations), "reference_records": len(self.references),
                      "expectations_by_status": dict(collections.Counter(r["status"] for r in self.raw_expectations)),
                      "expectations_by_category": dict(collections.Counter(r["category"] for r in self.raw_expectations)),
                      "references_by_scope": dict(collections.Counter(r["reference_scope"] for r in self.references)),
                      "distinct_expected_sha256s": len({r["expected_sha256"] for r in self.raw_expectations if r["expected_sha256"]}),
                      "unique_expected_sha256s_unrecovered": len({r["expected_sha256"] for r in self.raw_expectations if r["expected_sha256"] and r["status"] == "unavailable"}),
                      "unique_expected_sha256s_recovered": len({r["expected_sha256"] for r in self.raw_expectations if r["expected_sha256"] and r["status"] == "exact_hash_recovered"}),
                      "unique_production_or_historical_expected_sha256s_unrecovered": len({r["expected_sha256"] for r in self.raw_expectations if r["expected_sha256"] and r["status"] == "unavailable" and r["category"] in {"historical_file", "historical_22_file_inventory", "production_or_documentary", "private_performer_original"}}),
                      "test_example_parameterized_or_runtime_export_records_excluded_from_production_artifact_denominator": len(self.parameterized_references) + sum(r["reference_scope"] in {"test_or_example", "parameterized", "runtime_export_contract"} for r in self.references)}
        expectations = {"schema_version": "god-here.recovery-expectations.v1", "generated_at_utc": self.now,
                        "definitions": definitions, "counts": exp_counts, "expectations": self.raw_expectations,
                        "reference_records": self.references,
                        "parameterized_reference_occurrences": self.parameterized_references,
                        "recovered_document_reference_records": self.document_references,
                        "qualification": "Expectation/reference occurrence counts are not unique artifact counts. Unknown hashes remain unresolved even when names match. Cross-project native-register evidence is separately scoped."}
        custody = {"schema_version": "god-here.private-custody-index.v1", "generated_at_utc": self.now,
                   "classification": "PRIVATE: exact Library/Drive/Page/chat/source locators; do not commit or publish",
                   "counts": counts, "inputs": self.input_evidence,
                   "objects": [{"sha256": o["sha256"], "bytes": o["bytes"], "logical_names": self.private_object_names[o["sha256"]], "origin_ids": o["origin_ids"]} for o in objects],
                   "origins": sorted(self.private_origins.values(), key=lambda x: x["origin_id"]),
                   "selected_remote_file_locators": self.data.get("history-audit/recovery-index-flat.json", []),
                   "historical_expectation_records": [dict(p, resolution={k: r[k] for k in ("status", "matched_sha256", "candidate_sha256s", "recovered_object_usability") if k in r})
                                                       for p, r in zip(self.private_expectations, self.raw_expectations)],
                   "reference_records": self.private_references,
                   "unhashed_materializations": self.unhashed,
                   "release_receipts": self.data.get("recovery-audit/local-copy-release.json", {}),
                   "warnings": self.warnings}
        self.out.mkdir(parents=True, exist_ok=True)
        self.write("compilation-checks.json", {"generated_at_utc": self.now, "errors": self.errors, "warnings": self.warnings, "counts": counts})
        if self.errors:
            raise RuntimeError(f"Catalog integrity checks failed: {len(self.errors)}; inspect compilation-checks.json")
        for name, content in [("god-here-recovery-catalog.json", catalog), ("expectations.json", expectations)]:
            self.assert_public_safe(content)
            self.write(name, content)
        self.write("private-custody-index.json", private_clean(custody))
        document_register = {"schema_version": "god-here.recovered-document-reference-register.v1", "generated_at_utc": self.now,
                             "documents": self.document_records, "references": self.document_references,
                             "counts": {"documents": len(self.document_records), "references": len(self.document_references),
                                        "inline_media_data_url_markers": sum(r["inline_media_data_url_markers"] for r in self.document_records)},
                             "qualification": "These are bounded static reference records. Embedded payload bytes are preserved within document identity; their markers are not additional independently hashed artifact objects. Commands were not executed."}
        self.assert_public_safe(document_register)
        self.write("recovered-document-reference-register.json", document_register)
        snapshot_index = []
        original_inputs = {x["input"]: x for x in self.input_evidence}
        for rel, content in self.input_snapshots:
            stored = self.write("private-input-evidence/" + rel, content)
            original = original_inputs[rel]
            snapshot_index.append({"input": rel, "original_sha256": original["sha256"], "original_bytes": original["bytes"],
                                   "stored_path": "private-input-evidence/" + rel, "stored_sha256": stored["sha256"], "stored_bytes": stored["bytes"],
                                   "normalization": "Parsed JSON serialized with stable indentation; ephemeral signed URL credentials removed"})
        self.write("snapshot-index.json", {"schema_version": "god-here.private-input-snapshot-index.v1", "generated_at_utc": self.now,
                                          "inputs": snapshot_index,
                                          "replay_input_base": "private-input-evidence",
                                          "reproduction_scope": "Object SHA/byte identities and semantic counts; timestamps, observed local availability and input-file serialization hashes are expected to differ"})
        self.write("counts.json", {"catalog": counts, "expectations": exp_counts})
        print(json.dumps({"output_directory": str(self.out), "counts": counts, "expectations": exp_counts}, indent=2))

    def write(self, name, value):
        path = self.out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
        temporary.replace(path)
        raw = path.read_bytes()
        return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

    def assert_public_safe(self, value):
        text = json.dumps(value, ensure_ascii=False)
        forbidden = [r"/workspace/", r"/Users/", r"/root/", r"sandbox:", r"chatgpt\.com/(?:c|space)/", r"drive\.google\.com/",
                     r"libfile_", r"library-file:", r"appgprj_", r"file_000000", r"X-Amz-", r"[?&]sig=", r"Bearer\s+",
                     r"god-here-evaluation\.ajpadavano\.chatgpt\.site"]
        found = [pattern for pattern in forbidden if re.search(pattern, text, re.I)]
        if found:
            raise RuntimeError("Public-output privacy guard rejected patterns: " + ", ".join(found))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    Compiler(args.base, args.output_dir or args.base / "compiled").build()


if __name__ == "__main__":
    main()
