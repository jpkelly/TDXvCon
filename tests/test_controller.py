"""Behavioural tests for toe/vcon_controller.py, run against TD fakes.

These drive the real controller state machine (submit → loading → encoding
→ finishing → done) through tests/td_fakes.py, so regressions in job
lifecycle logic are caught without TouchDesigner. They do not cover GPU
decode/encode, codec menus beyond the captured ones, or the panel.
"""

from __future__ import annotations

import pytest

from td_fakes import Rig


@pytest.fixture
def media(tmp_path):
    src = tmp_path / "clip.mov"
    src.write_bytes(b"source")
    return src, tmp_path


# ----------------------------------------------------------------------
# Baseline: the harness drives a whole job
# ----------------------------------------------------------------------


def test_job_writes_every_source_frame_once(media):
    src, out_dir = media
    rig = Rig(frames=12, rate=24.0)
    out = out_dir / "clip.notchlc.mov"
    rig.submit(src, out)
    rig.run()

    assert rig.movieout.files[str(out)] == list(range(12))
    done = rig.events("done")
    assert len(done) == 1 and done[0]["path"] == str(out)
    assert rig.movieout.par.record.eval() == 0


# ----------------------------------------------------------------------
# #5 — Movie File In menu tokens are menu-verified
# ----------------------------------------------------------------------


def test_load_sets_live_indexunit_and_playmode_tokens(media):
    src, out_dir = media
    rig = Rig()
    rig.submit(src, out_dir / "a.mov")

    assert rig.moviein.par.indexunit.writes[-1] == "indices"
    assert rig.moviein.par.playmode.writes[-1] == "specify"


def test_load_accepts_index_alias_on_builds_that_use_it(media):
    src, out_dir = media
    rig = Rig()
    rig.moviein.par.indexunit.menuNames = ["index", "frames", "seconds",
                                           "fraction"]
    rig.submit(src, out_dir / "a.mov")

    assert rig.moviein.par.indexunit.writes[-1] == "index"


def test_unknown_indexunit_menu_fails_job_instead_of_falling_back(media):
    """With neither token available TD would fall back to entry 0 —
    here 'frames', the 2.5x time-stretch bug. The job must fail."""
    src, out_dir = media
    rig = Rig()
    rig.moviein.par.indexunit.menuNames = ["frames", "seconds", "fraction"]
    rig.submit(src, out_dir / "a.mov")

    assert rig.ext.state == "idle"
    errors = rig.events("error")
    assert errors and errors[-1]["code"] == "input-error"
    assert "indexunit" in errors[-1]["message"]
    assert "frames" not in rig.moviein.par.indexunit.writes
