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


# ----------------------------------------------------------------------
# #2 — `done` must describe what was actually produced
# ----------------------------------------------------------------------


class _FakeFfmpeg:
    """Replaces subprocess.Popen for the mux/extract: writes ``log`` to the
    process log, creates the output on success, exits with ``rc``."""

    def __init__(self, rc, log=b""):
        self.rc, self.log = rc, log
        self.calls = []

    def __call__(self, cmd, stdout=None, stderr=None, stdin=None):
        import types
        from pathlib import Path

        self.calls.append(cmd)
        if stdout is not None:
            stdout.write(self.log)
            stdout.flush()
        if self.rc == 0:
            Path(cmd[-1]).write_bytes(b"muxed")
        return types.SimpleNamespace(poll=lambda: self.rc, kill=lambda: None)


@pytest.fixture
def ffmpeg(monkeypatch):
    """Install a fake ffmpeg; returns a setter for its exit code/log."""
    import subprocess

    state = {}

    def install(rig, rc, log=b""):
        fake = _FakeFfmpeg(rc, log)
        monkeypatch.setattr(subprocess, "Popen", fake)
        rig.mod.VconExt._ffmpeg_cache = "/fake/ffmpeg"
        state["fake"] = fake
        return fake

    return install


def test_done_reports_frames_written_and_no_warnings(media):
    src, out_dir = media
    rig = Rig(frames=12)
    rig.submit(src, out_dir / "a.mov")
    rig.run()

    done = rig.events("done")[-1]
    assert done["frames_written"] == 12 and done["total_frames"] == 12
    assert done["warnings"] == []
    assert rig.ext.last_result["ok"] is True


def test_missing_output_fails_instead_of_reporting_done(media):
    src, out_dir = media
    rig = Rig(frames=5)
    rig.movieout.create_files = False
    rig.submit(src, out_dir / "a.mov")
    rig.run(max_ticks=2000)

    assert not rig.events("done")
    assert rig.events("error")[-1]["code"] == "output-error"
    assert rig.ext.last_result["ok"] is False


def test_failed_mux_is_done_with_a_warning(media, ffmpeg):
    src, out_dir = media
    rig = Rig(frames=5, has_audio=True)
    ffmpeg(rig, rc=1, log=b"...\nConversion failed!\n")
    out = out_dir / "a.mov"
    rig.submit(src, out, audio="pcm_s24le")
    rig.run()

    done = rig.events("done")[-1]
    assert len(done["warnings"]) == 1
    assert "audio mux failed (ffmpeg exit 1): Conversion failed!" \
        in done["warnings"][0]
    assert rig.ext.last_result["warnings"] == done["warnings"]
    assert out.exists()                  # the video-only file is kept


def test_successful_mux_has_no_warnings(media, ffmpeg):
    src, out_dir = media
    rig = Rig(frames=5, has_audio=True)
    ffmpeg(rig, rc=0)
    out = out_dir / "a.mov"
    rig.submit(src, out, audio="pcm_s24le")
    rig.run()

    assert rig.events("done")[-1]["warnings"] == []
    assert out.read_bytes() == b"muxed"


@pytest.mark.parametrize("audio, warned", [("auto", False), ("copy", False),
                                           ("aac", True)])
def test_silent_source_warns_only_when_audio_was_requested(
        media, ffmpeg, audio, warned):
    src, out_dir = media
    rig = Rig(frames=5)
    ffmpeg(rig, rc=1, log=b"Stream map '1:a:0' matches no streams.\n")
    rig.submit(src, out_dir / "a.mov", audio=audio)
    rig.run()

    warnings = rig.events("done")[-1]["warnings"]
    assert bool(warnings) is warned
    if warned:
        assert "source has no audio track" in warnings[0]


def test_missing_ffmpeg_warns_when_source_has_audio(media):
    src, out_dir = media
    rig = Rig(frames=5, has_audio=True)  # fakes find no ffmpeg by default
    rig.submit(src, out_dir / "a.mov")
    rig.run()

    warnings = rig.events("done")[-1]["warnings"]
    assert warnings and "ffmpeg not found" in warnings[0]


def test_warnings_do_not_leak_into_the_next_job(media, ffmpeg):
    src, out_dir = media
    rig = Rig(frames=5, has_audio=True)
    ffmpeg(rig, rc=1, log=b"Conversion failed!\n")
    rig.submit(src, out_dir / "a.mov", audio="aac")
    rig.run()
    ffmpeg(rig, rc=0)
    rig.submit(src, out_dir / "b.mov", audio="aac")
    rig.run()

    assert rig.events("done")[-1]["warnings"] == []


def test_last_result_records_cancel_and_rejected_submit(media):
    src, out_dir = media
    rig = Rig(frames=50)
    rig.submit(src, out_dir / "a.mov")
    rig.tick_until("encoding")
    rig.ext.Cancel()
    assert rig.ext.last_result["code"] == "cancelled"

    rig.submit(out_dir / "missing.mov", out_dir / "b.mov")
    assert rig.ext.last_result == {**rig.ext.last_result, "ok": False,
                                   "code": "input-missing"}
    assert rig.ext.last_result["output"] == str(out_dir / "b.mov")


# ----------------------------------------------------------------------
# #1 — an input Movie File In could not open must not "encode"
# ----------------------------------------------------------------------


def test_unopenable_input_fails_instead_of_encoding_placeholder(media):
    """Found live: a corrupt file showed TD's 256x256 placeholder with
    numImages 1, and the job wrote that one frame and reported done."""
    src, out_dir = media
    rig = Rig(frames=48)
    rig.moviein.opens = False
    out = out_dir / "a.mov"
    rig.submit(src, out)
    rig.run()

    assert not rig.events("done")
    err = rig.events("error")[-1]
    assert err["code"] == "input-error"
    assert "could not open the input" in err["message"]
    assert str(out) not in rig.movieout.files       # recording never began
    assert rig.ext.last_result["ok"] is False


def test_true_length_zero_alone_also_fails(media):
    """Second signal, for builds whose warning text differs."""
    src, out_dir = media
    rig = Rig(frames=48)
    rig.moviein.opens = False
    rig.moviein.warnings = lambda: ""
    rig.submit(src, out_dir / "a.mov")
    rig.run()

    assert rig.events("error")[-1]["code"] == "input-error"
