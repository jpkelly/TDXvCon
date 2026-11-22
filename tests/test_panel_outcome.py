"""Panel row outcome (issue #2): rows follow the controller's verdict.

The panel module imports without TouchDesigner (TD globals are only used
inside functions), so the pure decision logic is testable here.
"""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path

import pytest

PANEL = Path(__file__).resolve().parent.parent / "toe" / "vcon_panel_callbacks.py"


@pytest.fixture(scope="module")
def panel():
    spec = importlib.util.spec_from_file_location("panel_under_test", PANEL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.note = lambda *a, **k: None
    return mod


def _row(tmp_path, exists=True):
    out = tmp_path / "clip.notchlc.mov"
    if exists:
        out.write_bytes(b"partial")
    return {"input": str(tmp_path / "clip.mov"), "output": str(out),
            "status": "running"}


def _ctrl(**result):
    return types.SimpleNamespace(last_result=result or None)


def test_failed_job_with_partial_file_is_error_not_done(panel, tmp_path):
    """The old rule ('output exists' → done) passed failed and cancelled
    jobs, whose partial file Movie File Out finalizes."""
    row = _row(tmp_path)
    e = _ctrl(output=row["output"], ok=False, code="encode-error",
              message="frame 7 write failed", warnings=[])
    assert panel._job_outcome(e, row) == "error"
    assert row["error"] == "frame 7 write failed"


def test_done_with_warnings_is_warning(panel, tmp_path):
    row = _row(tmp_path)
    e = _ctrl(output=row["output"], ok=True, code="", message="",
              warnings=["audio mux failed — output is video-only"])
    assert panel._job_outcome(e, row) == "warning"
    assert row["warnings"] == ["audio mux failed — output is video-only"]


def test_clean_done(panel, tmp_path):
    row = _row(tmp_path)
    e = _ctrl(output=row["output"], ok=True, code="", message="", warnings=[])
    assert panel._job_outcome(e, row) == "done"


def test_no_verdict_for_row_is_error_not_stuck_running(panel, tmp_path):
    row = _row(tmp_path, exists=False)
    e = _ctrl(output=str(tmp_path / "other.mov"), ok=True, warnings=[])
    assert panel._job_outcome(e, row) == "error"


def test_older_controller_falls_back_to_file_existence(panel, tmp_path):
    old = types.SimpleNamespace()               # no last_result attribute
    assert panel._job_outcome(old, _row(tmp_path)) == "done"
    assert panel._job_outcome(old, _row(tmp_path / "..", exists=False)) is None



# #16: the menus leave out what this machine cannot encode.

@pytest.mark.parametrize("machine, cineform_listed, hap_subs", [
    ("mac", False, ["hap", "hapq"]),
    ("windows", True, ["hap", "hapq", "hapr", "haphdr"])])
def test_menus_follow_the_platform(panel, monkeypatch, machine,
                                   cineform_listed, hap_subs):
    monkeypatch.setattr(panel, "_platform", lambda: machine)
    assert ("cineform" in panel._container_codecs("mov")) is cineform_listed
    assert ("av1" in panel._container_codecs("mp4")) is cineform_listed
    assert panel._subtypes_here("hap") == hap_subs
    expected = "hapr" if machine == "windows" else None
    assert panel._validate_choice("hap", "subtype", "hapr") == expected
