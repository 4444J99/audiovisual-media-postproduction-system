"""Locate identical adapter code in a checkout or an installed wheel.

Receipts retain repository-relative logical names. Wheels place external
producers in amp/_runtime so they never occupy generic tools/web packages.
Project recipes, media, fonts and private locators are not runtime resources.
"""
from pathlib import Path

from .media_resolver import relative_path


def runtime_path(root, logical_path):
    root = Path(root)
    relative = relative_path(logical_path, "producing_code")
    packaged = root / "amp" / "_runtime"
    if relative.parts[0] in ("tools", "web") and packaged.is_dir():
        # Do not fall back to an unrelated sibling tools/web installation when
        # a packaged producer is missing: its identity check must fail closed.
        return packaged / relative
    return root / relative
