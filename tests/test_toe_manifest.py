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

The shipped toe must also lack /TDMCP, the development-only MCP server that
lives in the local dev toe. scripts/release_toe.py strips it; the manifest
records the toe's top-level operators so the release check can confirm it.

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


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _script():
    return _load("toe_manifest")


def _release():
    return _load("release_toe")


def _fake_expanded(tmp_path, files):
    """An expanded toe: t.toe.dir/<files> plus the t.toe.toc listing them."""
    expanded = tmp_path / "t.toe.dir"
    for rel, body in files.items():
        path = expanded / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    (tmp_path / "t.toe.toc").write_text(
        "".join(f"{rel}\n" for rel in [".build", *files]), encoding="utf-8")
    return expanded


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


def test_top_level_lists_one_entry_per_operator(tmp_path):
    expanded = _fake_expanded(tmp_path, {
        "project1.n": b"", "project1.parm": b"", "project1/vcon.n": b"",
        "TDMCP.n": b"", "local.n": b""})
    assert _script().top_level_in(expanded) == ["TDMCP", "local", "project1"]


def test_strip_removes_only_the_dev_component(tmp_path):
    expanded = _fake_expanded(tmp_path, {
        "TDMCP.n": b"", "TDMCP.parm": b"Port 13315", "TDMCP.vfs": b"",
        "TDMCP/View.n": b"", "TDMCP/server/x.text": b"code",
        "TDMCPlike.n": b"", "project1.n": b"", "project1/vcon.n": b""})
    removed = _release().strip_components(expanded, ("TDMCP",))

    assert sorted(removed) == ["TDMCP.n", "TDMCP.parm", "TDMCP.vfs",
                               "TDMCP/View.n", "TDMCP/server/x.text"]
    left = sorted(str(p.relative_to(expanded)) for p in expanded.rglob("*")
                  if p.is_file())
    assert left == ["TDMCPlike.n", "project1.n", "project1/vcon.n"]
    toc = (tmp_path / "t.toe.toc").read_text(encoding="utf-8").split()
    assert toc == [".build", "TDMCPlike.n", "project1.n", "project1/vcon.n"]


def test_strip_refuses_a_toe_that_still_refers_to_it(tmp_path):
    """A DAT calling op('/TDMCP') would break once the component is gone."""
    expanded = _fake_expanded(tmp_path, {
        "TDMCP.n": b"", "project1/start.text": b"op('/TDMCP').par.Active = 1"})
    with pytest.raises(RuntimeError, match="project1/start.text"):
        _release().strip_components(expanded, ("TDMCP",))


@pytest.mark.skipif(os.environ.get("VCON_RELEASE_CHECK") != "1",
                    reason="release gate: set VCON_RELEASE_CHECK=1 "
                           "(CI sets it on tag pushes)")
def test_packaged_toe_has_no_dev_server():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert "top_level" in m, (
        "the manifest predates the dev-server check. Make the toe with "
        "scripts/release_toe.py (PUBLISHING.md step 3)")
    shipped = [n for n in _script().DEV_ONLY if n in m["top_level"]]
    assert not shipped, (
        f"transcoder.toe contains the development-only /{shipped[0]} "
        f"component. Make it with scripts/release_toe.py, which removes it.")


@pytest.mark.skipif(os.environ.get("VCON_RELEASE_CHECK") != "1",
                    reason="release gate: set VCON_RELEASE_CHECK=1 "
                           "(CI sets it on tag pushes)")
def test_packaged_toe_matches_its_source():
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    toe_sha = hashlib.sha256(TOE.read_bytes()).hexdigest()
    assert toe_sha == m["toe_sha256"], (
        "transcoder.toe.sources.json describes a different toe. Make the "
        "toe with: python scripts/release_toe.py")
    norm = _script().normalized_sha256
    stale = [src for src, digest in m["sources"].items()
             if norm((ROOT / src).read_bytes()) != digest]
    assert not stale, (
        f"transcoder.toe was saved before the latest edits to "
        f"{', '.join(stale)} — it would ship stale logic. Rebuild and save "
        f"the dev toe in TouchDesigner, then run scripts/release_toe.py "
        f"(PUBLISHING.md steps 2-3).")
