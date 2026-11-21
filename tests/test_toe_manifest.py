"""The packaged toe must contain the current controller and panel source.

Saving the project bakes each file-linked DAT's text into transcoder.toe, so
a toe saved before the last source edit ships stale logic (0.1.2 shipped a
toe that predated three fixes). The old check compared file modification
times, which a git checkout scrambles: it failed on every CI run and every
fresh clone, whatever the toe contained.

scripts/toe_manifest.py reads the text actually baked into the toe (with
TouchDesigner's toeexpand) and records its SHA-256 in
transcoder.toe.sources.json. The release check below compares the repo
sources with those hashes and needs no TouchDesigner.

It is a release gate, not a per-commit check: between releases the source
legitimately runs ahead of the toe, and contributors cannot rebuild it. It
runs when VCON_RELEASE_CHECK=1 (set by CI on tag pushes; see PUBLISHING.md).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import struct
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOE = ROOT / "src" / "vcon" / "data" / "transcoder.toe"
MANIFEST = TOE.with_name("transcoder.toe.sources.json")


def _script():
    spec = importlib.util.spec_from_file_location(
        "toe_manifest", ROOT / "scripts" / "toe_manifest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _expanded_text_file(text: bytes) -> bytes:
    """An expanded <dat>.text file: 23-byte header, length, text."""
    return b"2\n*" + b"\x00" * 20 + struct.pack(">I", len(text)) + text


def test_dat_text_reads_the_expanded_layout():
    text = b'"""module"""\nx = 1\n'
    assert _script().dat_text(_expanded_text_file(text), "d") == text


def test_dat_text_rejects_a_length_that_does_not_match():
    raw = _expanded_text_file(b"abc") + b"extra"
    with pytest.raises(ValueError, match="length field"):
        _script().dat_text(raw, "d")


def test_hashes_ignore_line_endings():
    """Windows checkouts may turn LF into CRLF; that is not a stale toe."""
    h = _script().normalized_sha256
    assert h(b"a\r\nb\r\n") == h(b"a\nb\n")


def test_manifest_lists_every_baked_source():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert set(m["sources"]) == set(_script().BAKED.values())


@pytest.mark.skipif(os.environ.get("VCON_RELEASE_CHECK") != "1",
                    reason="release gate: set VCON_RELEASE_CHECK=1 "
                           "(CI sets it on tag pushes)")
def test_packaged_toe_matches_its_source():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    toe_sha = hashlib.sha256(TOE.read_bytes()).hexdigest()
    assert toe_sha == m["toe_sha256"], (
        "transcoder.toe.sources.json describes a different toe. After "
        "saving the toe, run: python scripts/toe_manifest.py")
    norm = _script().normalized_sha256
    stale = [src for src, digest in m["sources"].items()
             if norm((ROOT / src).read_bytes()) != digest]
    assert not stale, (
        f"transcoder.toe was saved before the latest edits to "
        f"{', '.join(stale)} — it would ship stale logic. Rebuild and save "
        f"it in TouchDesigner (PUBLISHING.md steps 2-3), then re-run "
        f"scripts/toe_manifest.py.")
