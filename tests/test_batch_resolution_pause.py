"""Tests for the controller-work additions: batch scan, resolution, pause."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from vcon.batch import (
    BatchItem,
    MOVIE_EXTENSIONS,
    derive_outputs,
    is_movie,
    scan_folder,
)
from vcon.models import JobSpec
from vcon.protocol import Cancel, Pause, Resume, Submit, decode_msg, encode_msg
from vcon.registry import Registry


# ----------------------------------------------------------------------
# batch scanning
# ----------------------------------------------------------------------

def test_movie_extensions_cover_td_file_types():
    """The extension set matches TD's official movie import list."""
    assert "mov" in MOVIE_EXTENSIONS
    assert "mp4" in MOVIE_EXTENSIONS
    assert "mkv" in MOVIE_EXTENSIONS
    assert "mxf" in MOVIE_EXTENSIONS
    assert "r3d" in MOVIE_EXTENSIONS
    # NOT movie extensions (image/text formats TD reads otherwise)
    assert "png" not in MOVIE_EXTENSIONS
    assert "txt" not in MOVIE_EXTENSIONS
    assert "wav" not in MOVIE_EXTENSIONS


def test_is_movie_case_insensitive(tmp_path: Path):
    (tmp_path / "a.MOV").touch()
    assert is_movie(tmp_path / "a.MOV")
    assert not is_movie(tmp_path / "b.xyz")


def _make_tree(root: Path):
    (root / "sub").mkdir()
    for name in ("a.mov", "b.mp4", "note.txt", "c.png"):
        (root / name).write_bytes(b"x")
    (root / "sub" / "d.mov").write_bytes(b"x")
    (root / "sub" / "e.mkv").write_bytes(b"x")


def test_scan_folder_keeps_structure(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    _make_tree(src)
    items = scan_folder(src, tmp_path / "dst")
    assert [i.relpath for i in items] == ["a.mov", "b.mp4", "sub/d.mov", "sub/e.mkv"]
    assert items[0].output == tmp_path / "dst" / "a.mov"
    assert items[2].output == tmp_path / "dst" / "sub" / "d.mov"


def test_scan_folder_flat_and_nonrecursive(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    _make_tree(src)
    flat = scan_folder(src, tmp_path / "dst", keep_structure=False)
    assert all(i.output.parent == tmp_path / "dst" for i in flat)
    top = scan_folder(src, tmp_path / "dst", recursive=False)
    assert [i.relpath for i in top] == ["a.mov", "b.mp4"]


def test_scan_folder_rejects_non_folder(tmp_path: Path):
    f = tmp_path / "file.mov"
    f.write_bytes(b"x")
    with pytest.raises(NotADirectoryError):
        scan_folder(f, tmp_path)


def test_derive_outputs_remaps_destination(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    _make_tree(src)
    items = scan_folder(src, tmp_path / "old")
    moved = derive_outputs(items, tmp_path / "new",
                           suffix="notchlc", extension=".mov")
    assert moved[0].output == tmp_path / "new" / "a.notchlc.mov"
    assert moved[2].output == tmp_path / "new" / "sub" / "d.notchlc.mov"
    # inputs untouched
    assert moved[0].input == src / "a.mov"


def test_batch_item_roundtrip():
    item = BatchItem(input=Path("/a/b.mov"), output=Path("/c/b.mov"), relpath="b.mov")
    assert item.relpath == "b.mov"


# ----------------------------------------------------------------------
# resolution / fit in specs and wire payloads
# ----------------------------------------------------------------------

def test_spec_resolution_validation():
    spec = JobSpec(input=Path("/i.mov"), output=Path("/o.mov"),
                   resolution="1280x720", fit="cover")
    spec.validate_resolution()   # ok

    bad_res = JobSpec(input=Path("/i.mov"), output=Path("/o.mov"),
                      resolution="720")
    with pytest.raises(Exception, match="WxH"):
        bad_res.validate_resolution()

    bad_nums = JobSpec(input=Path("/i.mov"), output=Path("/o.mov"),
                       resolution="0x1080")
    with pytest.raises(Exception, match="positive"):
        bad_nums.validate_resolution()

    bad_fit = JobSpec(input=Path("/i.mov"), output=Path("/o.mov"),
                      resolution="1280x720", fit="squash")
    with pytest.raises(Exception, match="fit mode"):
        bad_fit.validate_resolution()


def test_spec_serialization_roundtrips_resolution():
    spec = JobSpec(input=Path("/i.mov"), output=Path("/o.mov"),
                   resolution="1920x1080", fit="fitwidth")
    d = spec.as_dict()
    assert d["resolution"] == "1920x1080"
    assert d["fit"] == "fitwidth"
    back = JobSpec.from_dict(d)
    assert back.resolution == "1920x1080"
    assert back.fit == "fitwidth"
    # defaults survive a dict that omits the new fields (older state files)
    legacy = JobSpec.from_dict({"input": "/i.mov", "output": "/o.mov"})
    assert legacy.resolution == "auto"
    assert legacy.fit == "stretch"


def test_td_params_auto_resolution_sends_nothing():
    reg = Registry()
    params = reg.get("notchlc").td_params()
    assert "resolution" not in params
    assert "fit" not in params


def test_td_params_custom_resolution():
    reg = Registry()
    params = reg.get("notchlc").td_params(resolution="1280x720", fit="cover")
    assert params["resolution"] == "1280x720"
    assert params["fit"] == "cover"


# ----------------------------------------------------------------------
# pause / resume protocol messages
# ----------------------------------------------------------------------

def test_pause_resume_encode_decode():
    line = encode_msg(Pause())
    assert decode_msg(line) == {"type": "pause", "id": "*"}
    line = encode_msg(Resume("j3"))
    assert decode_msg(line) == {"type": "resume", "id": "j3"}
    # existing messages unaffected
    assert decode_msg(encode_msg(Cancel("j1"))) == {"type": "cancel", "id": "j1"}
    assert decode_msg(encode_msg(Submit(job_id="j1", input="a", output="b",
                                        params={}))).get("type") == "submit"


def test_mock_driver_pause_holds_progress(tmp_path: Path, monkeypatch):
    from vcon.mock_driver import MockDriver, make_mock_context
    from vcon.models import Job
    from vcon.queue_manager import QueueManager
    from vcon.events import EventBus

    src = tmp_path / "in.mov"
    # ~23 bytes of payload → mock derives ~26 frames from file size
    src.write_bytes(b"x" * 23)
    ctx = make_mock_context(tmp_path)
    ctx.extra["sleep"] = 0.001
    drv = MockDriver(ctx)
    events: list[dict] = []
    drv.set_on_message(lambda m: events.append(m))

    spec = JobSpec(input=src, output=tmp_path / "out.mov")
    job = Job(spec=spec, id="j1")

    async def scenario():
        task = asyncio.ensure_future(drv.run([job]))
        await asyncio.sleep(0.02)
        await drv.pause("j1")
        n_at_pause = sum(1 for e in events if e["type"] == "progress")
        await asyncio.sleep(0.03)
        n_during = sum(1 for e in events if e["type"] == "progress")
        assert n_during == n_at_pause, "progress advanced while paused"
        await drv.resume("j1")
        await task
    asyncio.run(scenario())
    assert any(e["type"] == "done" for e in events)