"""Local content-addressed inputs, using existing inventories and owner locators.

This module never downloads, guesses a filename, or writes an input. Locator
paths are deliberately absent from its public records and error messages.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re


class ContractError(ValueError):
    def __init__(self, code, role=None):
        self.code, self.role = code, role
        super().__init__(code + (f" [{role}]" if role else ""))


def read_json(path, *, role="json", limit=32 * 1024 * 1024):
    try:
        p = Path(path)
        if not p.is_file() or p.stat().st_size > limit:
            raise ContractError("missing_or_oversized_json", role)
        return json.loads(p.read_text(), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except ContractError:
        raise
    except (OSError, ValueError, UnicodeError):
        raise ContractError("invalid_json", role) from None


def file_identity(path, role):
    try:
        p = Path(path)
        if not p.is_file():
            raise ContractError("missing_dependency", role)
        digest = hashlib.sha256()
        count = 0
        with p.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                count += len(block)
                digest.update(block)
        return {"sha256": digest.hexdigest(), "bytes": count}
    except OSError:
        raise ContractError("unreadable_dependency", role) from None


def relative_path(value, role):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ContractError("unsupported_relative_path", role)
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts or p.as_posix() != value or ":" in value:
        raise ContractError("unsupported_relative_path", role)
    return p


def inventory_rows(document):
    """Read existing catalog, approval/registry, source and FX receipt shapes."""
    if isinstance(document, list):
        return document
    if isinstance(document, dict):
        for key in ("objects", "files", "sources"):
            if isinstance(document.get(key), list):
                return document[key]
    raise ContractError("unsupported_inventory_schema")


class MediaResolver:
    def __init__(self, repo_root, locations=None, inventories=()):
        self.repo_root = Path(repo_root).resolve()
        self.locations = locations or {"objects": {}, "collections": {}}
        if not isinstance(self.locations, dict) or any(
            not isinstance(self.locations.get(key, {}), dict) for key in ("objects", "collections")
        ):
            raise ContractError("invalid_locations_schema")
        self.sizes = {}
        for document in inventories:
            for row in inventory_rows(document):
                if not isinstance(row, dict):
                    raise ContractError("invalid_inventory_row")
                ref = self.reference(row, "inventory", require_size=True)
                prior = self.sizes.setdefault(ref["sha256"], ref["bytes"])
                if prior != ref["bytes"]:
                    raise ContractError("conflicting_inventory_identity")
        self.records, self._verified = [], {}

    def reference(self, ref, role, *, require_size=False):
        if not isinstance(ref, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(ref.get("sha256", ""))):
            raise ContractError("invalid_sha256_reference", role)
        size = ref.get("bytes", self.sizes.get(ref["sha256"]))
        if size is None and not require_size and "bytes" not in ref:
            return {"sha256": ref["sha256"]}
        if type(size) is not int or size < 0:
            raise ContractError("missing_or_invalid_byte_count", role)
        if ref["sha256"] in self.sizes and self.sizes[ref["sha256"]] != size:
            raise ContractError("inventory_binding_conflict", role)
        return {"sha256": ref["sha256"], "bytes": size}

    @staticmethod
    def _one_location(value, role):
        candidates = value if isinstance(value, list) else [value] if value is not None else []
        if any(not isinstance(p, str) or not Path(p).is_absolute() for p in candidates):
            raise ContractError("invalid_local_location", role)
        paths = sorted({str(Path(p).resolve()) for p in candidates})
        if not paths:
            raise ContractError("missing_location", role)
        if len(paths) != 1:
            raise ContractError("ambiguous_locations", role)
        return Path(paths[0])

    def verify(self, path, ref, role):
        expected = self.reference(ref, role)
        path = Path(path).resolve()
        cached = next((key for key in self._verified if key[0] == path and key[1] == expected["sha256"]
                       and ("bytes" not in expected or key[2] == expected["bytes"])), None)
        if cached is None:
            actual = file_identity(path, role)
            if any(actual[k] != value for k, value in expected.items()):
                raise ContractError("input_identity_mismatch", role)
            key = (path, actual["sha256"], actual["bytes"])
            self._verified[key] = role
        else:
            actual = {"sha256": cached[1], "bytes": cached[2]}
        record = {"role": role, **actual, "local_identity_verified": True}
        if record not in self.records:
            self.records.append(record)
        return path

    def resolve(self, ref, role):
        expected = self.reference(ref, role)
        if ref.get("repo_path") is not None:
            relative = relative_path(ref["repo_path"], role)
            path = (self.repo_root / relative).resolve()
            if not path.is_relative_to(self.repo_root):
                raise ContractError("repository_path_escape", role)
        else:
            path = self._one_location(self.locations.get("objects", {}).get(expected["sha256"]), role)
        return self.verify(path, expected, role)

    def collection(self, receipt_ref, required):
        receipt_path = self.resolve(receipt_ref, "asset_receipt")
        document = read_json(receipt_path, role="asset_receipt")
        root = self._one_location(self.locations.get("collections", {}).get(receipt_ref["sha256"]), "assets")
        rows = {}
        for row in inventory_rows(document):
            name = str(relative_path(row.get("path"), "asset_member"))
            if name in rows:
                raise ContractError("duplicate_asset_member")
            rows[name] = row
        indices = {name: index for index, name in enumerate(sorted(rows))}
        for name in sorted(set(required)):
            relative = relative_path(name, "asset_member")
            path = (root / relative).resolve()
            if not path.is_relative_to(root) or name not in rows:
                raise ContractError("missing_or_unsafe_asset_member")
            self.verify(path, rows[name], f"asset-{indices[name]:03}")
        return root

    def recheck(self):
        for (path, digest, count), role in self._verified.items():
            if file_identity(path, role) != {"sha256": digest, "bytes": count}:
                raise ContractError("input_changed_during_execution", role)
