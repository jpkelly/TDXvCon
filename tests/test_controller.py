"""Behavioural tests for toe/vcon_controller.py, run against TD fakes.

These drive the real controller state machine (submit → loading → encoding
→ finishing → done) through tests/td_fakes.py, so regressions in job
lifecycle logic are caught without TouchDesigner. They do not cover GPU
decode/encode, codec menus beyond the captured ones, or the panel.
"""

from __future__ import annotations

from pathlib import Path

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

    assert rig.movieout.files[rig.mod.partial_path(str(out))] == list(range(12))
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

    partial = rig.mod.partial_path
    assert rig.movieout.files[partial(str(second))] == list(range(20))
    assert len(rig.movieout.files[partial(str(first))]) < 20


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
        # A list gives one (rc, log) per call, for the copy-then-fallback
        # retry; a single value applies to every call.
        self.results = rc if isinstance(rc, list) else None
        self.rc, self.log = rc, log
        self.calls = []

    def __call__(self, cmd, stdout=None, stderr=None, stdin=None):
        import types
        from pathlib import Path

        rc, log = self.rc, self.log
        if self.results is not None:
            rc, log = self.results[min(len(self.calls), len(self.results) - 1)]
        self.calls.append(cmd)
        if stdout is not None:
            stdout.write(log)
            stdout.flush()
        if rc == 0:
            Path(cmd[-1]).write_bytes(b"muxed")
        return types.SimpleNamespace(poll=lambda: rc, kill=lambda: None)


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
    assert rig.mod.partial_path(str(out)) not in rig.movieout.files  # never began
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


# ----------------------------------------------------------------------
# #6 — codecs that cannot encode odd sizes get an even one from vCon
# (TD 2025.33230: H.264/H.265 silently cropped a pixel, VVC wrote nothing)
# ----------------------------------------------------------------------


def _sized(rig):
    """(MvO input name, fit mode, fit custom W, H) after the job ran."""
    f = rig.fit
    src = rig.movieout.inputs[0].name if rig.movieout.inputs else None
    return (src, f.par.fit.eval(), f.par.outputresolution.eval(),
            f.par.resolutionw.eval(), f.par.resolutionh.eval())


def _done_warnings(rig):
    done = rig.events("done")
    return done[-1].get("warnings", []) if done else None


def test_scale_token_on_odd_result_is_evened_with_fill(media):
    src, out_dir = media
    rig = Rig(width=1080, height=1350)
    rig.submit(src, out_dir / "a.mp4", videocodec="h264", even_dims=True,
               scale="half", fit="fitbest")
    rig.run()
    assert _sized(rig) == ("fit", "fill", "custom", 540, 674)
    assert _done_warnings(rig) == []


def test_typed_odd_size_is_evened_and_reported(media):
    src, out_dir = media
    rig = Rig()
    rig.submit(src, out_dir / "a.mp4", videocodec="h264", even_dims=True,
               resolution="1281x721", fit="fitbest")
    rig.run()
    assert _sized(rig) == ("fit", "fitbest", "custom", 1280, 720)
    warnings = _done_warnings(rig)
    assert warnings and "1281x721" in warnings[0] and "1280x720" in warnings[0]


def test_odd_source_without_resize_is_evened(media):
    src, out_dir = media
    rig = Rig(width=1281, height=721)
    rig.submit(src, out_dir / "a.mp4", videocodec="h264", even_dims=True)
    rig.run()
    assert _sized(rig) == ("fit", "fill", "custom", 1280, 720)
    assert _done_warnings(rig) == []


def test_even_source_without_resize_bypasses_the_fit(media):
    src, out_dir = media
    rig = Rig(width=1920, height=1080)
    rig.submit(src, out_dir / "a.mp4", videocodec="h264", even_dims=True)
    rig.run()
    assert rig.movieout.inputs[0].name == "moviein"


def test_codecs_that_write_odd_sizes_keep_them(media):
    """NotchLC, ProRes, Hap... wrote 1281x721 exactly: no rounding."""
    src, out_dir = media
    rig = Rig()
    rig.submit(src, out_dir / "a.mov", resolution="1281x721", fit="fill")
    rig.run()
    assert _sized(rig)[3:] == (1281, 721)
    assert _done_warnings(rig) == []


# ----------------------------------------------------------------------
# #8 — only a finished job leaves a file at the output name
# ----------------------------------------------------------------------


def test_finished_job_moves_its_partial_to_the_output_name(media):
    src, out_dir = media
    rig = Rig(frames=12)
    out = out_dir / "clip.notchlc.mov"
    rig.submit(src, out)
    rig.run()

    assert out.exists()
    assert not Path(rig.mod.partial_path(str(out))).exists()
    assert rig.ext.last_result["output"] == str(out)


def test_cancel_leaves_no_file_at_either_name(media):
    src, out_dir = media
    rig = Rig(frames=50)
    out = out_dir / "clip.notchlc.mov"
    rig.submit(src, out)
    rig.tick_until("encoding")
    for _ in range(5):
        rig.ext.onFrame()
    partial = Path(rig.mod.partial_path(str(out)))
    assert partial.exists() and not out.exists()   # recording under .partial

    rig.ext.Cancel()

    assert not partial.exists() and not out.exists()
    assert rig.events("error")[-1]["code"] == "cancelled"


def test_cancelled_reencode_keeps_the_existing_output(media):
    """With -y the old file used to be overwritten from the first frame."""
    src, out_dir = media
    rig = Rig(frames=50)
    out = out_dir / "clip.notchlc.mov"
    out.write_bytes(b"the earlier, complete encode")
    rig.submit(src, out)
    rig.tick_until("encoding")
    rig.ext.Cancel()

    assert out.read_bytes() == b"the earlier, complete encode"


def test_failed_job_removes_its_partial(media):
    src, out_dir = media
    rig = Rig(frames=20)
    out = out_dir / "a.mov"
    _fail_mid_encode(rig, src, out)

    assert not Path(rig.mod.partial_path(str(out))).exists()
    assert not out.exists()


def test_partial_name_keeps_the_extension_last(media):
    rig = Rig()
    assert rig.mod.partial_path("/x/clip.prores.mov") == "/x/clip.prores.partial.mov"
    assert rig.mod.partial_path("/x/loop.gif") == "/x/loop.partial.gif"


# ----------------------------------------------------------------------
# #7 — 'auto' keeps the source audio, in every track
# ----------------------------------------------------------------------


def _audio_codec(cmd):
    return cmd[cmd.index("-c:a") + 1]


@pytest.mark.parametrize("name, codec", [
    ("a.mov", "copy"), ("a.mkv", "copy"), ("a.webm", "copy"), ("a.mp4", "aac")])
def test_auto_audio_copies_except_into_mp4(media, ffmpeg, name, codec):
    src, out_dir = media
    rig = Rig(frames=5, has_audio=True)
    fake = ffmpeg(rig, rc=0)
    rig.submit(src, out_dir / name)
    rig.run()

    cmd = fake.calls[0]
    assert _audio_codec(cmd) == codec
    assert cmd[cmd.index("-map", cmd.index("0:v:0")) + 1] == "1:a"  # all tracks
    assert rig.events("done")[-1]["warnings"] == []


def test_auto_audio_skips_gif(media, ffmpeg):
    src, out_dir = media
    rig = Rig(frames=5, has_audio=True)
    fake = ffmpeg(rig, rc=0)
    rig.submit(src, out_dir / "a.gif")
    rig.run()
    assert fake.calls == [] and rig.events("done")[-1]["warnings"] == []


@pytest.mark.parametrize("name, fallback", [("a.mov", "pcm_s24le"),
                                            ("a.webm", "libopus")])
def test_auto_copy_that_fails_is_reencoded_quietly(media, ffmpeg, name, fallback):
    src, out_dir = media
    rig = Rig(frames=5, has_audio=True)
    fake = ffmpeg(rig, rc=[(1, b"opus only supported in MP4.\n"), (0, b"")])
    out = out_dir / name
    rig.submit(src, out)
    rig.run()

    assert [_audio_codec(c) for c in fake.calls] == ["copy", fallback]
    assert rig.events("done")[-1]["warnings"] == []
    assert out.read_bytes() == b"muxed"


def test_explicit_copy_that_fails_is_reencoded_with_a_warning(media, ffmpeg):
    src, out_dir = media
    rig = Rig(frames=5, has_audio=True)
    ffmpeg(rig, rc=[(1, b"opus only supported in MP4.\n"), (0, b"")])
    rig.submit(src, out_dir / "a.mov", audio="copy")
    rig.run()

    warnings = rig.events("done")[-1]["warnings"]
    assert len(warnings) == 1 and "re-encoded as pcm_s24le" in warnings[0]


def test_fallback_that_also_fails_warns_once_and_keeps_video(media, ffmpeg):
    src, out_dir = media
    rig = Rig(frames=5, has_audio=True)
    fake = ffmpeg(rig, rc=1, log=b"Conversion failed!\n")
    out = out_dir / "a.mov"
    rig.submit(src, out)
    rig.run()

    assert len(fake.calls) == 2                       # copy, then one retry
    warnings = rig.events("done")[-1]["warnings"]
    assert len(warnings) == 1 and "audio mux failed" in warnings[0]
    assert out.exists()


_TWO_TRACKS = (b"Input #0, mov,mp4, from 'src.mov':\n"
               b"  Stream #0:0[0x1]: Video: prores\n"
               b"  Stream #0:1[0x2]: Audio: pcm_s24le, 48000 Hz, stereo\n"
               b"  Stream #0:2[0x3]: Audio: pcm_s24le, 48000 Hz, mono\n"
               b"Output #0, wav, to 'a.wav':\n"
               b"  Stream #0:0: Audio: pcm_s16le\n")


@pytest.mark.parametrize("fmt, ext, amap, warned", [
    ("wav16", ".wav", "0:a:0", True), ("copy", ".mka", "0:a", False)])
def test_separate_audio_names_its_track_and_warns_on_dropped_ones(
        media, ffmpeg, fmt, ext, amap, warned):
    src, out_dir = media
    rig = Rig(frames=5)                              # silent: no mux step
    fake = ffmpeg(rig, rc=0, log=_TWO_TRACKS)
    rig.submit(src, out_dir / "a.mov", audio="none", audio_sep=fmt)
    rig.run()

    cmd = fake.calls[-1]
    assert cmd[-1].endswith(ext)
    assert cmd[cmd.index("-map") + 1] == amap
    warnings = rig.events("done")[-1]["warnings"]
    assert bool(warnings) is warned
    if warned:
        assert "2 audio tracks" in warnings[0]


# ----------------------------------------------------------------------
# Movie File Out keeps writing after record=0 (VP9/VVC, TD 2025.33230)
# ----------------------------------------------------------------------


def test_done_waits_until_movie_file_out_has_finished_writing(media):
    src, out_dir = media
    rig = Rig(frames=5, flush_cooks=40)
    out = out_dir / "a.webm"
    rig.submit(src, out)
    rig.tick_until("finishing")
    for _ in range(30):
        rig.ext.onFrame()
    assert rig.ext.state == "finishing" and not rig.events("done")
    assert not out.exists()                    # not renamed while writing

    rig.run()
    assert rig.events("done") and out.exists()
    assert rig.mvo_info.flush_left == 0


def test_cancel_while_movie_file_out_is_still_writing(media):
    src, out_dir = media
    rig = Rig(frames=5, flush_cooks=-1)        # still writing, indefinitely
    out = out_dir / "a.webm"
    rig.submit(src, out)
    rig.tick_until("finishing")
    for _ in range(20):
        rig.ext.onFrame()
    assert rig.ext.state == "finishing"
    rig.ext.Cancel()
    assert not Path(rig.mod.partial_path(str(out))).exists()
    assert rig.ext.state == "idle"
    assert rig.events("error")[-1]["code"] == "cancelled"


def test_a_file_that_never_finishes_fails_after_the_timeout(media):
    src, out_dir = media
    rig = Rig(frames=5, flush_cooks=-1)        # never reaches 0
    rig.ext.FINALIZE_TIMEOUT = 0
    rig.submit(src, out_dir / "a.webm")
    rig.run()
    err = rig.events("error")[-1]
    assert err["code"] == "output-error" and "still writing" in err["message"]
    assert not rig.events("done")


# ----------------------------------------------------------------------
# #11 — only this machine may drive the encoder
# ----------------------------------------------------------------------


def test_controller_binds_an_open_tcp_server_to_loopback():
    rig = Rig()
    rig.ext.onInitTD()
    assert rig.tcp.par.localaddress.eval() == "127.0.0.1"


def test_controller_keeps_an_address_set_on_purpose():
    rig = Rig()
    rig.tcp.par.localaddress.val = "10.0.0.5"
    rig.ext.onInitTD()
    assert rig.tcp.par.localaddress.eval() == "10.0.0.5"


@pytest.mark.parametrize("address, allowed", [
    ("127.0.0.1", True), ("::1", True), ("::ffff:127.0.0.1", True),
    ("192.168.1.20", False), ("10.0.0.5", False), ("", False)])
def test_peer_allowed(address, allowed):
    assert Rig().ext.peer_allowed(address) is allowed


def test_callbacks_refuse_and_ignore_remote_peers():
    """The callbacks DAT text from build_network.py, run against fakes."""
    import importlib.util
    import types

    spec = importlib.util.spec_from_file_location(
        "build_network_under_test",
        Path(__file__).resolve().parent.parent / "toe" / "build_network.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)

    rig = Rig()
    calls = []
    rig.ext.onConnect = lambda: calls.append("connect")
    rig.ext.onReceive = lambda m: calls.append(m)
    ns = {"parent": lambda: types.SimpleNamespace(
              ext=types.SimpleNamespace(Vcon=rig.ext)),
          "debug": lambda *a, **k: None}
    exec(build.TCP_CALLBACKS_SRC, ns)

    closed = []
    remote = types.SimpleNamespace(address="192.168.1.20",
                                   close=lambda: closed.append(True))
    local = types.SimpleNamespace(address="127.0.0.1", close=lambda: None)

    assert ns["onConnect"](None, remote) == 0 and closed == [True]
    ns["onReceive"](None, 0, '{"type": "ping"}', b"", remote)
    assert calls == []

    assert ns["onConnect"](None, local) == 1
    ns["onReceive"](None, 0, '{"type": "ping"}', b"", local)
    assert calls == ["connect", '{"type": "ping"}']


# ----------------------------------------------------------------------
# #16 — a codec TD cannot encode here fails at once, with TD's reason
# ----------------------------------------------------------------------

_CINEFORM_ERROR = ("/project1/vcon/movieout:  Error: Cineform not supported "
                   "in this OS. (/project1/vcon/movieout)")


def test_recording_that_never_opens_fails_early_with_tds_error(media):
    src, out_dir = media
    rig = Rig(frames=100, flush_cooks=0)
    rig.movieout.fail_open = True
    rig.movieout.error_text = _CINEFORM_ERROR
    rig.submit(src, out_dir / "a.mov", videocodec="cineform")
    rig.run()

    err = rig.events("error")[-1]
    assert err["code"] == "codec-unavailable"
    assert 'TouchDesigner says "Cineform not supported in this OS".' in err["message"]
    assert rig.ext.frame == 0 and rig.ext.state == "idle"
    assert not rig.events("done")


def test_silent_refusal_is_reported_too(media):
    """Hap R on macOS: no recording, and no error text from TD."""
    src, out_dir = media
    rig = Rig(frames=100, flush_cooks=0)
    rig.movieout.fail_open = True
    rig.movieout.par.videocodectype.menuNames = ["hap", "hapq", "hapr",
                                                 "haphdr"]
    rig.submit(src, out_dir / "a.mov", videocodec="hap",
               videocodectype="hapr")
    rig.run()

    err = rig.events("error")[-1]
    assert err["code"] == "codec-unavailable"
    assert "hap (hapr)" in err["message"] and "gave no error" in err["message"]


def test_working_codec_passes_the_recording_check(media):
    src, out_dir = media
    rig = Rig(frames=20, flush_cooks=0)
    rig.submit(src, out_dir / "a.mov")
    rig.run()
    assert rig.events("done") and not rig.events("error")


def test_toe_without_mvo_info_skips_the_check(media):
    """Older toes cannot tell; they keep the end-of-job file check."""
    src, out_dir = media
    rig = Rig(frames=20)                      # no mvo_info
    rig.movieout.fail_open = True
    rig.movieout.error_text = _CINEFORM_ERROR
    rig.submit(src, out_dir / "a.mov", videocodec="cineform")
    rig.run(max_ticks=2000)
    err = rig.events("error")[-1]
    assert err["code"] == "output-error"
    assert "(TouchDesigner: Cineform not supported in this OS.)" in err["message"]


@pytest.mark.parametrize("raw, clean", [
    ("/project1/vcon/movieout:  Error: Cineform not supported in this OS. "
     "(/project1/vcon/movieout)", "Cineform not supported in this OS."),
    ("  Error: NVIDIA AV1 codec is not supported on this OS. "
     "(/project1/vcon/movieout)", "NVIDIA AV1 codec is not supported on this OS."),
    ("Codec: something odd", "Codec: something odd"),
    ("", "")])
def test_movie_file_out_error_text_is_cleaned(raw, clean):
    rig = Rig()
    rig.movieout.error_text = raw
    assert rig.ext._mvo_errors() == clean
