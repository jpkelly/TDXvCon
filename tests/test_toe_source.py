"""vcon -doctor's toe freshness, from the manifest instead of file dates (#18)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from vcon.toe_source import MANIFEST_NAME, normalized_sha256, toe_freshness

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ("toe/vcon_controller.py", "toe/vcon_panel_callbacks.py")


def _checkout(tmp_path, *, manifest=True):
    """A minimal source checkout whose packaged toe matches its sources."""
    for rel in SOURCES:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(f"# {rel}\nx = 1\n".encode())
    toe = tmp_path / "src" / "vcon" / "data" / "transcoder.toe"
    toe.parent.mkdir(parents=True)
    toe.write_bytes(b"toe bytes")
    if manifest:
        (toe.parent / MANIFEST_NAME).write_text(json.dumps({
            "toe_sha256": hashlib.sha256(b"toe bytes").hexdigest(),
            "sources": {rel: normalized_sha256((tmp_path / rel).read_bytes())
                        for rel in SOURCES},
        }), encoding="utf-8")
    return toe


def test_current_toe_passes_even_when_older_than_its_sources(tmp_path):
    """The old check compared dates and failed on every fresh checkout."""
    toe = _checkout(tmp_path)
    os.utime(toe, (1_000, 1_000))
    for rel in SOURCES:
        os.utime(tmp_path / rel, (2_000_000_000, 2_000_000_000))
    ok, note = toe_freshness(toe)
    assert ok and "current" in note


def test_edited_source_is_stale_and_named(tmp_path):
    toe = _checkout(tmp_path)
    (tmp_path / SOURCES[1]).write_text("# edited\n", encoding="utf-8")
    ok, note = toe_freshness(toe)
    assert not ok and "vcon_panel_callbacks.py" in note
    assert "release_toe.py" in note and "build_network" not in note


def test_crlf_checkout_is_not_stale(tmp_path):
    toe = _checkout(tmp_path)
    for rel in SOURCES:
        path = tmp_path / rel
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert toe_freshness(toe)[0]


def test_toe_saved_over_by_hand_is_reported(tmp_path):
    toe = _checkout(tmp_path)
    toe.write_bytes(b"a different save")
    ok, note = toe_freshness(toe)
    assert not ok and "saved over by hand" in note


def test_toe_without_manifest_is_not_checked(tmp_path):
    toe = _checkout(tmp_path, manifest=False)
    ok, note = toe_freshness(toe)
    assert ok and "not checked" in note


def test_installed_package_has_nothing_to_compare(tmp_path):
    toe = tmp_path / "site-packages" / "vcon" / "data" / "transcoder.toe"
    toe.parent.mkdir(parents=True)
    toe.write_bytes(b"toe bytes")
    assert toe_freshness(toe) == (True, "installed package (no sources to compare)")


def test_hash_matches_the_release_script():
    """doctor and scripts/toe_manifest.py must hash sources identically."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "toe_manifest", ROOT / "scripts" / "toe_manifest.py")
    tm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tm)
    for data in (b"a\nb\n", b"a\r\nb\r\n", b""):
        assert tm.normalized_sha256(data) == normalized_sha256(data)


@pytest.mark.skipif(not (ROOT / "src/vcon/data" / MANIFEST_NAME).is_file(),
                    reason="needs the repo's packaged toe and manifest")
def test_repo_toe_is_checked_against_its_manifest():
    ok, note = toe_freshness(ROOT / "src" / "vcon" / "data" / "transcoder.toe")
    assert note.startswith(("built from", "STALE"))
