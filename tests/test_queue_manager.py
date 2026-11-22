"""QueueManager: submission validation, message handling, snapshots, persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vcon.errors import CodecError, InputError, OutputError
from vcon.models import JobSpec, JobStatus
from vcon.queue_manager import QueueManager, QueueOptions


def test_submit_valid_spec(queue, sample_spec):
    job = queue.submit(sample_spec)
    assert job.id == "j1"
    assert job.status == JobStatus.QUEUED
    assert queue.counts()[JobStatus.QUEUED] == 1


def test_submit_rejects_missing_input(queue, tmp_path):
    spec = JobSpec(input=tmp_path / "ghost.mov", output=tmp_path / "o.mov")
    with pytest.raises(InputError, match="not found"):
        queue.submit(spec)


def test_submit_rejects_unknown_codec(queue, sample_spec):
    bad = JobSpec(
        input=sample_spec.input, output=sample_spec.output, codec="prores999"
    )
    with pytest.raises(CodecError, match="unknown codec"):
        queue.submit(bad)


def test_submit_rejects_bad_quality(queue, sample_spec):
    bad = JobSpec(
        input=sample_spec.input, output=sample_spec.output,
        codec="notchlc", quality="ultra",
    )
    with pytest.raises(CodecError, match="quality"):
        queue.submit(bad)


def test_submit_rejects_bad_quality_even_when_output_exists(sample_input, tmp_path, bus, registry):
    """Codec validation must precede the overwrite check."""
    existing = tmp_path / "already.mov"
    existing.write_bytes(b"x")
    bad = JobSpec(
        input=sample_input, output=existing, codec="notchlc", quality="ultra",
    )
    q = QueueManager(bus, registry=registry, options=QueueOptions(yes=True))
    with pytest.raises(CodecError, match="quality"):
        q.submit(bad)


def test_submit_rejects_existing_output_unless_yes(sample_input, tmp_path, bus, registry):
    existing = tmp_path / "already.mov"
    existing.write_bytes(b"x")
    spec = JobSpec(input=sample_input, output=existing)

    q = QueueManager(bus, registry=registry, options=QueueOptions())
    with pytest.raises(OutputError, match="use -y to overwrite"):
        q.submit(spec)

    q_yes = QueueManager(bus, registry=registry, options=QueueOptions(yes=True))
    job = q_yes.submit(JobSpec(input=sample_input, output=existing))
    assert job.status == JobStatus.QUEUED


def test_submit_no_overwrite_mode(sample_input, tmp_path, bus, registry):
    existing = tmp_path / "already.mov"
    existing.write_bytes(b"x")
    q = QueueManager(bus, registry=registry, options=QueueOptions(no_overwrite=True))
    spec = JobSpec(input=sample_input, output=existing)
    with pytest.raises(OutputError, match="-n was given"):
        q.submit(spec)


def test_submit_bakes_td_params_into_spec(queue, sample_spec):
    """The toe has no codec knowledge — params must be resolved at submit."""
    job = queue.submit(sample_spec)
    params = job.spec.extra.get("td_params")
    assert isinstance(params, dict)
    # lowercase menu token, NOT the "NotchLC" display label
    assert params["videocodec"] == "notchlc"
    assert params["quality"] == 0.862   # 'optimal' → MvO slider float
    assert params["moviecontainer"] == "mov"


def test_submit_td_params_respect_quality_override(queue, sample_input, tmp_path):
    spec = JobSpec(input=sample_input, output=tmp_path / "o.mov",
                   codec="notchlc", quality="best")
    job = queue.submit(spec)
    assert job.spec.extra["td_params"]["quality"] == 1.0   # 'best' → 1.0


def test_handle_message_lifecycle(queue, sample_spec):
    # Verification reads the output file, so give it a real (tiny) one.
    from tests.test_codec_probe import _mov_with_fourcc

    job = queue.submit(sample_spec)
    jid = job.id

    queue.handle_message({"type": "hello", "version": 1})
    queue.handle_message({"type": "accepted", "id": jid, "total_frames": 100})
    assert job.status == JobStatus.RUNNING
    assert job.total_frames == 100

    queue.handle_message({"type": "progress", "id": jid, "frame": 50, "total_frames": 100})
    assert job.progress_frame == 50
    assert job.percent == 50.0

    job.spec.output.write_bytes(_mov_with_fourcc(b"nclc"))
    queue.handle_message({"type": "done", "id": jid, "path": str(job.spec.output),
                          "total_frames": 100, "seconds": 12.5})
    assert job.status == JobStatus.DONE
    assert job.is_terminal
    assert job.verified is True
    assert "NotchLC" in job.verify_note


def test_done_rejected_when_output_is_wrong_codec(queue, sample_spec):
    """The bug that shipped: valid file, wrong codec, no error reported."""
    from tests.test_codec_probe import _mov_with_fourcc

    job = queue.submit(sample_spec)
    job.spec.output.write_bytes(_mov_with_fourcc(b"rle "))
    queue.handle_message({"type": "accepted", "id": job.id, "total_frames": 10})
    queue.handle_message({"type": "done", "id": job.id, "total_frames": 10})

    assert job.status == JobStatus.FAILED
    assert "fell back to another codec" in (job.error or "")
    assert job.verified is False


def test_handle_message_error_path(queue, sample_spec):
    job = queue.submit(sample_spec)
    queue.handle_message({"type": "accepted", "id": job.id, "total_frames": 10})
    queue.handle_message({"type": "error", "id": job.id, "message": "gpu melted",
                          "code": "gpu-error"})
    assert job.status == JobStatus.FAILED
    assert job.error == "gpu melted"
    assert queue.failed_jobs() == [job]


def test_handle_message_ignores_unknown(queue, sample_spec):
    job = queue.submit(sample_spec)
    queue.handle_message({"type": "future_msg", "id": job.id})
    queue.handle_message({"type": "progress", "id": "ghost", "frame": 1})
    assert job.status == JobStatus.QUEUED


def test_snapshot_shape(queue, sample_spec):
    job = queue.submit(sample_spec)
    snap = queue.snapshot()
    assert snap["counts"][JobStatus.QUEUED] == 1
    assert snap["jobs"][0]["id"] == job.id
    # round-trippable as JSON
    json.dumps(snap)


def test_state_persistence(tmp_path, sample_spec, bus, registry):
    state = tmp_path / "state.json"
    q = QueueManager(bus, registry=registry, options=QueueOptions(state_path=state))
    job = q.submit(sample_spec)
    q.handle_message({"type": "accepted", "id": job.id, "total_frames": 50})

    data = json.loads(state.read_text())
    assert data["version"] == 1
    assert data["jobs"][0]["total_frames"] == 50


def test_has_pending_and_results(queue, sample_spec):
    job = queue.submit(sample_spec)
    assert queue.has_pending()
    queue.handle_message({"type": "done", "id": job.id, "total_frames": 5})
    assert not queue.has_pending()

# ----------------------------------------------------------------------
# #2 — done carries warnings and is checked against the file's frames
# ----------------------------------------------------------------------


def _video_mov(frames):
    from tests.test_codec_probe import _mov, _trak

    return _mov(_trak(b"vide", frames))


def _capture(bus):
    seen = []
    bus.subscribe_jobs(lambda e: seen.append((e.type, e.data)))
    return seen


def test_done_with_warnings_stays_done_and_reports_them(bus, queue, sample_spec):
    seen = _capture(bus)
    job = queue.submit(sample_spec)
    queue.handle_message({"type": "accepted", "id": job.id, "total_frames": 48})
    job.spec.output.write_bytes(_video_mov(48))
    queue.handle_message({"type": "done", "id": job.id,
                          "path": str(job.spec.output), "total_frames": 48,
                          "frames_written": 48, "seconds": 1.0,
                          "warnings": ["audio mux failed — video-only"]})

    assert job.status == JobStatus.DONE
    assert job.warnings == ["audio mux failed — video-only"]
    assert queue.warned_jobs() == [job]
    done = [d for t, d in seen if t == "job_done"][-1]
    assert done["warnings"] == ["audio mux failed — video-only"]
    assert "48 frames" in job.verify_note


def test_done_fails_when_file_has_fewer_frames_than_written(bus, queue, sample_spec):
    seen = _capture(bus)
    job = queue.submit(sample_spec)
    queue.handle_message({"type": "accepted", "id": job.id, "total_frames": 48})
    job.spec.output.write_bytes(_video_mov(40))
    queue.handle_message({"type": "done", "id": job.id,
                          "path": str(job.spec.output), "total_frames": 48,
                          "frames_written": 48, "seconds": 1.0, "warnings": []})

    assert job.status == JobStatus.FAILED
    assert "40 video frames but 48 were written" in job.error
    err = [d for t, d in seen if t == "job_error"][-1]
    assert err["code"] == "frame-count-mismatch"


def test_done_from_older_controller_checks_total_frames(queue, sample_spec):
    """No frames_written field: total_frames is what it set out to write."""
    job = queue.submit(sample_spec)
    job.spec.output.write_bytes(_video_mov(47))
    queue.handle_message({"type": "done", "id": job.id,
                          "path": str(job.spec.output), "total_frames": 48,
                          "seconds": 1.0})
    assert job.status == JobStatus.FAILED


# ----------------------------------------------------------------------
# #4: alpha=None ("follow source") is decided at submit, from the input
# ----------------------------------------------------------------------


def _warnings(bus):
    from vcon.events import LOG

    seen = []
    bus.subscribe(LOG, lambda e: seen.append(e.data))
    return seen


def _prores4444(src, tmp_path, name="out.mov", alpha=None):
    return JobSpec(input=src, output=tmp_path / name, codec="prores",
                   subtype="4444", alpha=alpha)


def test_follow_source_keeps_alpha_from_an_alpha_source(queue, bus, make_movie, tmp_path):
    logs = _warnings(bus)
    job = queue.submit(_prores4444(make_movie("a.mov", b"ap4h", 32), tmp_path))
    assert job.spec.extra["td_params"]["moviepixelformat"] == "yuva444412bit"
    assert not [m for m in logs if m["level"] == "warning"]


def test_follow_source_opaque_source_gets_the_opaque_format(queue, make_movie, tmp_path):
    job = queue.submit(_prores4444(make_movie("o.mov", b"ap4h", 24), tmp_path))
    assert job.spec.extra["td_params"]["moviepixelformat"] == "yuv44410bit"


def test_follow_source_unknown_encodes_opaque_and_warns(queue, bus, make_movie, tmp_path):
    logs = _warnings(bus)
    job = queue.submit(_prores4444(make_movie("n.mov", b"nclc", 24), tmp_path))
    assert job.spec.extra["td_params"]["moviepixelformat"] == "yuv44410bit"
    warned = [m["message"] for m in logs if m["level"] == "warning"]
    assert warned and "n.mov" in warned[0]


def test_follow_source_ignores_alpha_a_codec_cannot_carry(queue, bus, make_movie, tmp_path):
    """An alpha source into H.264 is not an error, nor worth a warning."""
    logs = _warnings(bus)
    spec = JobSpec(input=make_movie("a.mov", b"ap4h", 32),
                   output=tmp_path / "o.mp4", codec="h264")
    job = queue.submit(spec)
    assert job.spec.extra["td_params"]["moviepixelformat"] == "yuv420"
    assert not [m for m in logs if m["level"] == "warning"]


def test_no_alpha_overrides_an_alpha_source(queue, make_movie, tmp_path):
    job = queue.submit(_prores4444(make_movie("a.mov", b"ap4h", 32), tmp_path,
                                   alpha=False))
    assert job.spec.extra["td_params"]["moviepixelformat"] == "yuv44410bit"


def test_variable_frame_rate_source_warns_at_submit(queue, bus, make_movie, tmp_path):
    """#9: frames are written in order at a constant rate, so a VFR
    source's video drifts against its copied audio."""
    src = make_movie("phone.mov", b"avc1", 24,
                     stts=[(150, 1000), (150, 3000)])   # 30 fps, then 10 fps
    logs = _warnings(bus)
    queue.submit(JobSpec(input=src, output=tmp_path / "o.mov", codec="prores"))
    warned = [m["message"] for m in logs if m["level"] == "warning"]
    assert any("phone.mov has a variable frame rate" in w for w in warned)


def test_constant_frame_rate_source_does_not_warn(queue, bus, make_movie, tmp_path):
    src = make_movie("cfr.mov", b"avc1", 24, stts=[(48, 512)])
    logs = _warnings(bus)
    queue.submit(JobSpec(input=src, output=tmp_path / "o.mov", codec="prores"))
    assert not [m for m in logs if "variable frame rate" in m["message"]]


def test_alpha_flag_keeps_alpha_the_source_cannot_show(queue, bus, make_movie, tmp_path):
    """#15: NotchLC sources look the same with or without alpha; -alpha
    (alpha=True) forces it, with no "cannot tell" warning."""
    logs = _warnings(bus)
    job = queue.submit(_prores4444(make_movie("n.mov", b"nclc", 24), tmp_path,
                                   alpha=True))
    assert job.spec.extra["td_params"]["moviepixelformat"] == "yuva444412bit"
    assert not [m for m in logs if m["level"] == "warning"]


def test_alpha_flag_on_a_codec_without_alpha_fails_before_encoding(
        queue, make_movie, tmp_path):
    spec = JobSpec(input=make_movie("a.mov", b"ap4h", 32),
                   output=tmp_path / "o.mp4", codec="h264", alpha=True)
    with pytest.raises(CodecError, match="cannot encode alpha"):
        queue.submit(spec)


def test_unknown_alpha_warning_mentions_the_flag(queue, bus, make_movie, tmp_path):
    logs = _warnings(bus)
    queue.submit(_prores4444(make_movie("n.mov", b"nclc", 24), tmp_path))
    warned = [m["message"] for m in logs if m["level"] == "warning"]
    assert warned and "-alpha" in warned[0]



@pytest.mark.parametrize("machine, refused", [
    ("mac", True), ("windows", False), ("other", False)])
def test_submit_refuses_what_this_platform_cannot_encode(
        queue, sample_input, tmp_path, monkeypatch, machine, refused):
    """#16: refused on mac before encoding; never on "other" platforms,
    where TouchDesigner does not run (mock backend, Linux CI)."""
    import vcon.queue_manager as qm

    monkeypatch.setattr(qm, "platform_of_current_machine", lambda: machine)
    spec = JobSpec(input=sample_input, output=tmp_path / "o.mov",
                   codec="hap", subtype="hapr")
    if refused:
        with pytest.raises(CodecError, match="not available on mac"):
            queue.submit(spec)
    else:
        assert queue.submit(spec).spec.extra["td_params"]["videocodectype"] == "hapr"
