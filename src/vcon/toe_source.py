"""Is a packaged transcoder.toe built from the current controller and panel source?

Saving the project in TouchDesigner bakes the text of the file-linked
controller and panel DATs into the toe. scripts/release_toe.py records
what it baked (the toe's SHA-256 and each source's) in
``transcoder.toe.sources.json`` beside the toe. Comparing that manifest
with the source files says whether the toe is current, without
TouchDesigner. File dates cannot: a git checkout gives every file an
arbitrary modification time (#18).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

MANIFEST_NAME = "transcoder.toe.sources.json"

#: How to bring a stale toe up to date in a source checkout.
REBUILD_HINT = ("rebuild it in TouchDesigner (the builders save "
                "dev/TDXvCon-dev.toe), then run python scripts/release_toe.py "
                "(PUBLISHING.md, step 3)")


def normalized_sha256(data: bytes) -> str:
    """SHA-256 with line endings normalized (git may check out CRLF)."""
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def find_checkout(toe_path: Path) -> Path | None:
    """The source checkout a toe belongs to: the nearest ancestor folder
    holding toe/vcon_controller.py. None for an installed package."""
    for parent in list(toe_path.resolve().parents)[:5]:
        if (parent / "toe" / "vcon_controller.py").is_file():
            return parent
    return None


def toe_freshness(toe_path: Path) -> tuple[bool, str]:
    """(ok, message) for vcon -doctor."""
    toe_path = Path(toe_path)
    root = find_checkout(toe_path)
    if root is None:
        return True, "installed package (no sources to compare)"
    manifest = toe_path.with_name(MANIFEST_NAME)
    if not manifest.is_file():
        return True, (f"not checked: {toe_path.name} has no {MANIFEST_NAME} "
                      f"(only the packaged toe made by release_toe.py has one)")
    try:
        recorded = json.loads(manifest.read_text(encoding="utf-8"))
        toe_sha = hashlib.sha256(toe_path.read_bytes()).hexdigest()
    except (OSError, ValueError) as exc:
        return False, f"cannot read {MANIFEST_NAME}: {exc}"
    if toe_sha != recorded.get("toe_sha256"):
        return False, (f"{toe_path.name} is not the toe {MANIFEST_NAME} "
                       f"describes (saved over by hand?); {REBUILD_HINT}")
    stale = []
    for source, digest in sorted((recorded.get("sources") or {}).items()):
        path = root / source
        if not path.is_file() or normalized_sha256(path.read_bytes()) != digest:
            stale.append(source)
    if stale:
        return False, (f"STALE: built before the latest edits to "
                       f"{', '.join(stale)}; {REBUILD_HINT}")
    return True, "built from the current controller and panel source"
