"""Resolve explicit compositions or a checkout's declared compatibility default.

The processor package contains no artwork identity or bundled composition data.
Legacy recipe fields and explicit --project paths keep their original meaning.

Also exports typed M0 shared foundation contracts:
- SourceSpan
- MaterialRef
- StudyBinding
- StudyContext
- StudyResult
- PerformanceRecord
- Timebase
"""
from __future__ import annotations

import json
from pathlib import Path

from .containers import (
    ALLOWED_OPERATORS,
    MaterialRef,
    SourceSpan,
    StudyBinding,
    StudyContext,
    StudyResult,
    Timebase,
)
from .record import PerformanceRecord


def resolve_composition(selection=None, *, root=None):
    root = Path.cwd() if root is None else Path(root)
    if selection is not None:
        explicit = Path(selection)
        explicit = explicit if explicit.is_absolute() else root / explicit
        if explicit.is_dir():
            return explicit
    manifest_path = root / "ace-manifest.json"
    if not manifest_path.is_file():
        raise ValueError("Select a composition directory with --composition (legacy --project is supported)")
    document = json.loads(manifest_path.read_text())
    if document.get("schema_version") != "1.0.0" or document.get("system_id") != "audiovisual-composition-system":
        raise ValueError("Unsupported composition registry")
    selected = selection if selection is not None else document.get("defaults", {}).get("composition_id")
    matches = [item for item in document.get("compositions", [])
               if selected and (item.get("id") == selected or selected in item.get("aliases", [])
                                 or selected in item.get("legacy_paths", []))]
    if len(matches) != 1:
        raise ValueError("Select exactly one registered composition or an explicit composition directory")
    relative = Path(matches[0]["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Registered composition paths must remain inside the registry directory")
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_dir():
        raise ValueError("Registered composition directory is unavailable or outside the registry")
    return path


__all__ = [
    "resolve_composition",
    "SourceSpan",
    "MaterialRef",
    "StudyBinding",
    "StudyContext",
    "StudyResult",
    "PerformanceRecord",
    "Timebase",
    "ALLOWED_OPERATORS",
]
