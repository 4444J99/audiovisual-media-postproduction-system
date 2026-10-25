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


class DependencyClosureError(ContractError):
    def __init__(self, report, role="closure"):
        self.report = report
        super().__init__("dependency_closure_failed", role)


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
    def __init__(self, repo_root, locations=None, inventories=(), *, project_root=None, media_root=None):
        self.repo_root = Path(repo_root).resolve()
        self.project_root = Path(project_root).resolve() if project_root is not None else None
        self.media_root = Path(media_root).resolve() if media_root is not None else None
        self.locations = locations or {"objects": {}, "collections": {}}
        if not isinstance(self.locations, dict) or any(
            not isinstance(self.locations.get(key, {}), dict) for key in ("objects", "collections")
        ):
            raise ContractError("invalid_locations_schema")
        if self.project_root is None and "project_root" in self.locations:
            self.project_root = Path(self.locations["project_root"]).resolve()
        if self.media_root is None and "media_root" in self.locations:
            self.media_root = Path(self.locations["media_root"]).resolve()
        if self.media_root is None:
            self.media_root = self.project_root or self.repo_root
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
        return Path(candidates[0])

    def verify(self, path, ref, role):
        expected = self.reference(ref, role)
        resolved_path = Path(path).resolve()
        cached = next((key for key in self._verified if key[0] == resolved_path and key[1] == expected["sha256"]
                       and ("bytes" not in expected or key[2] == expected["bytes"])), None)
        if cached is None:
            actual = file_identity(resolved_path, role)
            if any(actual[k] != value for k, value in expected.items()):
                raise ContractError("input_identity_mismatch", role)
            key = (resolved_path, actual["sha256"], actual["bytes"])
            self._verified[key] = role
        else:
            actual = {"sha256": cached[1], "bytes": cached[2]}
        record = {"role": role, **actual, "local_identity_verified": True}
        if record not in self.records:
            self.records.append(record)
        return Path(path)

    def resolve_private_path(self, path, *, role="private_path"):
        if not isinstance(path, (str, Path)):
            raise ContractError("invalid_path", role)
        raw_str = str(path).strip()
        if not raw_str:
            raise ContractError("empty_path", role)
        raw_path = Path(path)

        comp_boundary = (self.project_root or (self.repo_root / "compositions/comp-001")).resolve()

        if not raw_path.is_absolute():
            if ".." in raw_path.parts:
                raise ContractError("unsupported_relative_path", role)
            candidates = []
            if self.media_root:
                candidates.append(self.media_root / raw_path)
            if self.project_root:
                candidates.append(self.project_root / raw_path)
            candidates.append(self.repo_root / "compositions/comp-001" / raw_path)
            candidates.append(self.repo_root / raw_path)

            for cand in candidates:
                cand_res = cand.resolve()
                if cand_res.exists():
                    if self.project_root and not cand_res.is_relative_to(self.project_root) and not cand_res.is_relative_to(self.media_root) and not cand_res.is_relative_to(self.repo_root):
                        raise ContractError("boundary_escape", role)
                    return cand

            raise ContractError("missing_dependency", role)

        if raw_path.exists():
            resolved = raw_path.resolve()
            if "projects/god-here" in raw_str or "compositions/comp-001" in raw_str:
                if not resolved.is_relative_to(comp_boundary):
                    raise ContractError("boundary_escape", role)
            return raw_path

        parts = raw_path.parts
        alias_idx = -1
        for idx in range(len(parts) - 1):
            if (parts[idx] == "compositions" and parts[idx + 1] == "comp-001") or \
               (parts[idx] == "projects" and parts[idx + 1] == "god-here"):
                alias_idx = idx + 1
                break

        if alias_idx != -1:
            remainder = Path(*parts[alias_idx + 1:])
            cand1 = comp_boundary / remainder
            if cand1.resolve().exists():
                return cand1
            if self.media_root:
                cand2 = self.media_root / remainder
                if cand2.resolve().exists():
                    return cand2
            cand3 = self.repo_root / "compositions/comp-001" / remainder
            if cand3.resolve().exists():
                return cand3

        if self.media_root:
            cand = self.media_root / raw_path.name
            if cand.resolve().exists():
                return cand
            for marker in ("packages", "sequences", "portable-study-02"):
                if marker in parts:
                    idx = parts.index(marker)
                    sub = Path(*parts[idx:])
                    cand = self.media_root / sub
                    if cand.resolve().exists():
                        return cand

        if self.project_root:
            cand = self.project_root / raw_path.name
            if cand.resolve().exists():
                return cand

        raise ContractError("missing_dependency", role)

    def resolve(self, ref, role):
        expected = self.reference(ref, role)
        if ref.get("project_path") is not None:
            rel = relative_path(ref["project_path"], role)
            base = self.project_root or (self.repo_root / "compositions/comp-001")
            path = (base / rel).resolve()
            alias_root = (self.repo_root / "compositions/comp-001").resolve()
            if not path.is_relative_to(base.resolve()) and not path.is_relative_to(alias_root):
                raise ContractError("boundary_escape", role)
        elif ref.get("repo_path") is not None:
            relative = relative_path(ref["repo_path"], role)
            path = (self.repo_root / relative).resolve()
            if not path.is_relative_to(self.repo_root):
                raise ContractError("repository_path_escape", role)
        elif ref.get("private_path") is not None or ref.get("path") is not None:
            path = self.resolve_private_path(ref.get("private_path") or ref.get("path"), role=role)
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
            if not path.is_relative_to(root.resolve()) or name not in rows:
                raise ContractError("missing_or_unsafe_asset_member")
            self.verify(path, rows[name], f"asset-{indices[name]:03}")
        return root

    def recheck(self):
        for (resolved_path, digest, count), role in self._verified.items():
            if file_identity(resolved_path, role) != {"sha256": digest, "bytes": count}:
                raise ContractError("input_changed_during_execution", role)


def check_dependency_closure(
    *,
    sequences=None,
    dat_files=None,
    fonts=None,
    files=None,
    resolver=None,
    raise_on_error=True,
):
    report = {
        "valid": True,
        "missing": [],
        "sequences": [],
        "dat_files": [],
        "fonts": [],
        "files": [],
    }

    for seq in (sequences or []):
        seq_cfg = seq if isinstance(seq, dict) else {"path": seq}
        raw_path = seq_cfg.get("path")
        if not raw_path:
            report["missing"].append({"kind": "sequence", "reason": "empty sequence path"})
            report["valid"] = False
            continue

        resolved_dir = None
        if resolver is not None:
            try:
                resolved_dir = resolver.resolve_private_path(raw_path, role="sequence")
            except ContractError as err:
                report["missing"].append({
                    "kind": "sequence",
                    "path": str(raw_path),
                    "reason": f"unresolvable sequence directory ({err.code})"
                })
                report["valid"] = False
                continue
        else:
            resolved_dir = Path(raw_path)

        if not resolved_dir.is_dir():
            report["missing"].append({
                "kind": "sequence",
                "path": str(raw_path),
                "resolved_path": str(resolved_dir),
                "reason": "sequence directory does not exist or is not a directory"
            })
            report["sequences"].append({
                "path": str(raw_path),
                "resolved_path": str(resolved_dir),
                "valid": False,
                "frames": 0,
                "bytes": 0,
            })
            report["valid"] = False
            continue

        frame_files = sorted([
            f for f in resolved_dir.iterdir()
            if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in {".png", ".jpg", ".jpeg", ".exr", ".tiff", ".tga", ".dpx"}
        ])
        if not frame_files:
            frame_files = sorted([f for f in resolved_dir.iterdir() if f.is_file() and not f.name.startswith(".")])

        frame_count = len(frame_files)
        total_bytes = sum(f.stat().st_size for f in frame_files)
        expected_frames = seq_cfg.get("expected_frames") or seq_cfg.get("frames")

        seq_valid = True
        seq_reason = None

        if frame_count == 0:
            seq_valid = False
            seq_reason = "empty sequence directory (0 frames)"
        elif expected_frames is not None and frame_count != expected_frames:
            seq_valid = False
            seq_reason = f"absent sequence frame: found {frame_count} frames, expected {expected_frames}"
        else:
            frame_numbers = []
            for f in frame_files:
                matches = re.findall(r'(\d+)', f.stem)
                if matches:
                    frame_numbers.append(int(matches[-1]))
            if len(frame_numbers) == frame_count and frame_count > 1:
                for a, b in zip(frame_numbers, frame_numbers[1:]):
                    if b - a != 1:
                        seq_valid = False
                        seq_reason = f"absent sequence frame: gap between frame {a} and {b}"
                        break

        seq_record = {
            "path": str(raw_path),
            "resolved_path": str(resolved_dir),
            "frames": frame_count,
            "bytes": total_bytes,
            "valid": seq_valid,
        }
        if not seq_valid:
            report["valid"] = False
            seq_record["reason"] = seq_reason
            report["missing"].append({
                "kind": "sequence",
                "path": str(raw_path),
                "resolved_path": str(resolved_dir),
                "reason": seq_reason,
                "frames_found": frame_count,
                "payload_bytes": total_bytes,
            })
        report["sequences"].append(seq_record)

    for dat in (dat_files or []):
        dat_cfg = dat if isinstance(dat, dict) else {"path": dat}
        raw_path = dat_cfg.get("path")
        if not raw_path:
            continue
        resolved_file = None
        if resolver is not None:
            try:
                resolved_file = resolver.resolve_private_path(raw_path, role="native_dat")
            except ContractError:
                resolved_file = Path(raw_path)
        else:
            resolved_file = Path(raw_path)

        if resolved_file.is_file():
            ident = file_identity(resolved_file, "native_dat")
            report["dat_files"].append({
                "path": str(raw_path),
                "resolved_path": str(resolved_file),
                "valid": True,
                **ident,
            })
        else:
            report["valid"] = False
            report["missing"].append({
                "kind": "native_dat",
                "path": str(raw_path),
                "resolved_path": str(resolved_file),
                "reason": "missing file",
            })
            report["dat_files"].append({
                "path": str(raw_path),
                "resolved_path": str(resolved_file),
                "valid": False,
            })

    for font in (fonts or []):
        font_cfg = font if isinstance(font, dict) else {"path": font}
        raw_path = font_cfg.get("path")
        if not raw_path:
            continue
        resolved_font = None
        if resolver is not None:
            try:
                resolved_font = resolver.resolve_private_path(raw_path, role="font")
            except ContractError:
                resolved_font = Path(raw_path)
        else:
            resolved_font = Path(raw_path)

        if resolved_font.is_file():
            ident = file_identity(resolved_font, "font")
            report["fonts"].append({
                "path": str(raw_path),
                "resolved_path": str(resolved_font),
                "valid": True,
                **ident,
            })
        else:
            report["valid"] = False
            report["missing"].append({
                "kind": "font",
                "path": str(raw_path),
                "resolved_path": str(resolved_font),
                "reason": "missing font file",
            })
            report["fonts"].append({
                "path": str(raw_path),
                "resolved_path": str(resolved_font),
                "valid": False,
            })

    for fl in (files or []):
        fl_cfg = fl if isinstance(fl, dict) else {"path": fl}
        raw_path = fl_cfg.get("path")
        if not raw_path:
            continue
        resolved = None
        if resolver is not None:
            try:
                resolved = resolver.resolve_private_path(raw_path, role="file")
            except ContractError:
                resolved = Path(raw_path)
        else:
            resolved = Path(raw_path)

        if resolved.is_file():
            ident = file_identity(resolved, "file")
            report["files"].append({
                "path": str(raw_path),
                "resolved_path": str(resolved),
                "valid": True,
                **ident,
            })
        else:
            report["valid"] = False
            report["missing"].append({
                "kind": "file",
                "path": str(raw_path),
                "resolved_path": str(resolved),
                "reason": "missing file",
            })
            report["files"].append({
                "path": str(raw_path),
                "resolved_path": str(resolved),
                "valid": False,
            })

    report["valid"] = (len(report["missing"]) == 0)
    if not report["valid"] and raise_on_error:
        raise DependencyClosureError(report)
    return report
