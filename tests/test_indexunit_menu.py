"""Regression tests for the Movie File In TOP's indexunit menu write.

The controller and the build script used to write the literal token
``"index"`` straight to ``moviein.par.indexunit``. Live TouchDesigner builds
expose ``indices`` (not ``index``); the unknown token silently fell back to
menu entry 0, which only happened to be the right unit by luck. A menu
reorder would silently switch units and time-stretch the encode.

These tests load the controller source directly from disk, with no
TouchDesigner runtime, and exercise the menu-verified write helper.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

_TOE = Path(__file__).resolve().parent.parent / "toe"


def _load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, _TOE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_controller():
    return _load_module("vcon_controller_under_test", "vcon_controller.py")


class _FakePar:
    """Minimal stand-in for a TD menu parameter."""

    def __init__(self, menu):
        self.menuNames = menu
        self.val = None
        self.name = "indexunit"


@pytest.fixture
def ext():
    controller = _load_controller()
    return controller.VconExt(ownerComp=object())


def test_set_indexunit_menu_prefers_indices(ext):
    """Modern TD menu uses 'indices' — that is the token to write."""
    par = _FakePar(["indices", "frames", "seconds", "fraction"])
    written = ext._set_indexunit_menu(par)
    assert written == "indices"
    assert par.val == "indices"


def test_set_indexunit_menu_accepts_legacy_index(ext):
    """Older TD builds used 'index'; still accepted for compatibility."""
    par = _FakePar(["index", "frames", "seconds", "fraction"])
    written = ext._set_indexunit_menu(par)
    assert written == "index"
    assert par.val == "index"


def test_set_indexunit_menu_fails_loudly_when_neither_present(ext):
    """No known token in the live menu must raise, never silently fall back."""
    par = _FakePar(["frames", "seconds", "fraction"])
    with pytest.raises(ValueError):
        ext._set_indexunit_menu(par)
    assert par.val is None


def test_load_input_uses_verified_indexunit_write(ext):
    """_load_input must route through the menu-verified write, not a literal."""
    indexunit_par = _FakePar(["indices", "frames", "seconds", "fraction"])
    playmode_par = _FakePar(["locked", "specify", "sequential", "timecodeop"])
    moviepar = SimpleNamespace(
        file=None,
        playmode=playmode_par,
        indexunit=indexunit_par,
        index=None,
        prereadframes=None,
    )
    moviein = SimpleNamespace(par=moviepar)

    class _FakeOwner:
        def op(self, name):
            return moviein if name == "moviein" else None

    ext.ownerComp = _FakeOwner()
    ext._load_input({"input": "clip.mov"})
    assert indexunit_par.val == "indices"
    assert playmode_par.val == "specify"


def test_build_script_menu_set_strict_prefers_indices():
    build = _load_module("build_network_under_test", "build_network.py")
    par = _FakePar(["indices", "frames", "seconds", "fraction"])
    assert build.menu_set_strict(par, ["indices", "index"], "moviein.indexunit") \
        == "indices"
    assert par.val == "indices"


def test_build_script_menu_set_strict_accepts_legacy_index():
    build = _load_module("build_network_under_test", "build_network.py")
    par = _FakePar(["index", "frames", "seconds", "fraction"])
    assert build.menu_set_strict(par, ["indices", "index"]) == "index"
    assert par.val == "index"


def test_build_script_menu_set_strict_empty_menu_uses_preferred():
    """Build-time Movie File In menu may be empty; write the preferred token."""
    build = _load_module("build_network_under_test", "build_network.py")
    par = _FakePar([])
    assert build.menu_set_strict(par, ["indices", "index"]) == "indices"
    assert par.val == "indices"


def test_build_script_menu_set_strict_fails_loudly():
    build = _load_module("build_network_under_test", "build_network.py")
    par = _FakePar(["frames", "seconds", "fraction"])
    with pytest.raises(ValueError):
        build.menu_set_strict(par, ["indices", "index"], "moviein.indexunit")
    assert par.val is None
