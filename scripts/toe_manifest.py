#!/usr/bin/env python3
"""Record which source text is baked into transcoder.toe.

Saving the project in TouchDesigner bakes the CURRENT text of each
file-linked DAT into the .toe. A toe saved before the last source edit
ships stale logic. File modification times cannot detect that: a git
checkout gives every file an arbitrary mtime, so the old mtime check failed
on every CI run and on fresh clones.

This script reads the text actually stored in the toe, using TouchDesigner's
``toeexpand`` tool (which ships with TouchDesigner), and writes its SHA-256
next to the toe as ``transcoder.toe.sources.json``. The test
``test_packaged_toe_matches_its_source`` compares those hashes with the repo
sources without needing TouchDesigner.

Run after saving the toe (PUBLISHING.md, step 3):

    python scripts/toe_manifest.py            # writes the manifest
    python scripts/toe_manifest.py --check    # exit 1 if stale, writes nothing

Set TOEEXPAND, or pass --toeexpand, if the tool is not found automatically.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOE = REPO / "src" / "vcon" / "data" / "transcoder.toe"
MANIFEST = TOE.with_name("transcoder.toe.sources.json")

#: DAT name inside the toe → the repo file it is linked to.
BAKED = {
    "vcon_controller": "toe/vcon_controller.py",
    "panel_callbacks": "toe/vcon_panel_callbacks.py",
}

#: Expanded text-DAT layout: a 23-byte TD header, a 4-byte big-endian
#: length, then the text. Verified on toes saved by TD 2025.33230.
_LEN_AT, _TEXT_AT = 23, 27


def normalized_sha256(text: bytes) -> str:
    """Hash text with line endings normalized (git may check out CRLF)."""
    return hashlib.sha256(text.replace(b"\r\n", b"\n")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def find_toeexpand(explicit: str | None) -> str:
    for cand in (explicit, os.environ.get("TOEEXPAND")):
        if cand:
            return cand
    patterns = [
        "/Applications/TouchDesigner*.app/Contents/MacOS/toeexpand",
        r"C:\Program Files\Derivative\TouchDesigner*\bin\toeexpand.exe",
    ]
    for pat in patterns:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    found = shutil.which("toeexpand")
    if found:
        return found
    sys.exit("toeexpand not found: install TouchDesigner, or set TOEEXPAND")


def dat_text(raw: bytes, name: str) -> bytes:
    """The text stored in an expanded ``<name>.text`` file."""
    if len(raw) < _TEXT_AT or not raw.startswith(b"2\n*"):
        raise ValueError(f"{name}.text: unrecognized header")
    (length,) = struct.unpack(">I", raw[_LEN_AT:_TEXT_AT])
    if _TEXT_AT + length != len(raw):
        raise ValueError(f"{name}.text: length field {length} does not match "
                         f"file size {len(raw)}")
    return raw[_TEXT_AT:]


def baked_hashes(toe: Path, toeexpand: str) -> dict[str, str]:
    """{repo source path: sha256 of the text baked into the toe}."""
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "t.toe"
        shutil.copyfile(toe, copy)
        # toeexpand exits 1 even when it succeeds (TD 2025.33230), so the
        # expanded folder, not the exit status, says whether it worked.
        proc = subprocess.run([toeexpand, copy.name], cwd=tmp,
                              capture_output=True, text=True)
        expanded = Path(tmp) / "t.toe.dir"
        if not expanded.is_dir():
            raise RuntimeError(f"toeexpand failed (exit {proc.returncode}): "
                               f"{(proc.stderr or proc.stdout).strip()}")
        out = {}
        for dat, source in BAKED.items():
            hits = list(expanded.rglob(f"{dat}.text"))
            if len(hits) != 1:
                raise ValueError(f"expected one {dat}.text in the toe, "
                                 f"found {len(hits)}")
            text = dat_text(hits[0].read_bytes(), dat)
            out[source] = normalized_sha256(text)
        return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--toe", type=Path, default=TOE)
    ap.add_argument("--toeexpand")
    ap.add_argument("--check", action="store_true",
                    help="report stale sources and exit 1; write nothing")
    args = ap.parse_args()

    baked = baked_hashes(args.toe, find_toeexpand(args.toeexpand))
    stale = [src for src, digest in baked.items()
             if normalized_sha256((REPO / src).read_bytes()) != digest]
    for src in BAKED.values():
        print(f"{'STALE' if src in stale else 'ok   '}  {src}")
    if args.check:
        return 1 if stale else 0

    manifest = {
        "toe_sha256": file_sha256(args.toe),
        "sources": baked,
        "generated_by": "scripts/toe_manifest.py",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {MANIFEST.relative_to(REPO)}")
    if stale:
        print("warning: the toe does not contain the current source of: "
              + ", ".join(stale) + " — rebuild and save it before releasing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
