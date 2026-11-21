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


# ----------------------------------------------------------------------
# #3 — a failed encode must stop Movie File Out
# ----------------------------------------------------------------------


def _fail_mid_encode(rig, src, out):
    rig.submit(src, out)
    rig.tick_until("encoding")
    rig.ext.onFrame()                    # write a frame or two
    rig.movieout.fail_addframe = True
    rig.ext.onFrame()                    # this write raises
    rig.movieout.fail_addframe = False


def test_failure_mid_encode_stops_recording(media):
    src, out_dir = media
    rig = Rig(frames=20)
    _fail_mid_encode(rig, src, out_dir / "a.mov")

    assert rig.ext.state == "idle"
    assert rig.events("error")[-1]["code"] == "encode-error"
    assert rig.movieout.par.record.eval() == 0


def test_job_after_a_failure_starts_its_own_file(media):
    """Before the fix record stayed 1, so the next job's record=1 was no
    off→on edge: its frames went into the failed job's file."""
    src, out_dir = media
    rig = Rig(frames=20)
    first, second = out_dir / "a.mov", out_dir / "b.mov"
    _fail_mid_encode(rig, src, first)

    rig.submit(src, second)
    rig.run()

    assert rig.movieout.files[str(second)] == list(range(20))
    assert len(rig.movieout.files[str(first)]) < 20


class _FakeProc:
    def __init__(self):
        self.killed = False

    def kill(self):
        self.killed = True

    def poll(self):
        return None


class _FakeLog:
    def close(self):
        pass


def test_failure_while_muxing_kills_ffmpeg_and_removes_temp_files(media):
    src, out_dir = media
    rig = Rig()
    tmp = out_dir / "a.muxing.mov"
    tmp.write_bytes(b"partial")
    proc = _FakeProc()
    rig.ext.job = {"id": "j", "input": str(src), "output": str(tmp),
                   "params": {}, "origin": "tcp"}
    rig.ext.state = "muxing"
    rig.ext._mux = {"proc": proc, "log": _FakeLog(), "tmp": str(tmp),
                    "prog": str(out_dir / "a.muxing.progress"),
                    "log_path": str(out_dir / "a.muxing.log"),
                    "out": str(out_dir / "a.mov")}

    rig.ext._fail("boom", "controller-error")

    assert proc.killed
    assert not tmp.exists()
    assert rig.ext._mux is None and rig.ext.state == "idle"


def test_failure_resets_pause_and_progress(media):
    src, out_dir = media
    rig = Rig(frames=20)
    rig.submit(src, out_dir / "a.mov")
    rig.tick_until("encoding")
    rig.ext.Pause()
    rig.comp.par.Progress.val = 0.4
    rig.ext._fail("boom", "encode-error")

    assert rig.ext._paused is False
    assert rig.comp.par.Progress.eval() == 0.0
