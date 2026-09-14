"""Transcoder orchestration + config/TD discovery."""

from __future__ import annotations

import json

import pytest

from vcon.config import Config, find_touchdesigner, load_config, save_config
from vcon.errors import ConfigError
from vcon.models import JobStatus
from vcon.transcoder import Transcoder, TranscoderOptions


# ----------------------------------------------------------------------
# Transcoder end-to-end on the mock backend
# ----------------------------------------------------------------------


def test_run_batch_mock_success(tmp_path, sample_input):
    out = tmp_path / "clip.nlc.mov"
    t = Transcoder(TranscoderOptions(backend="mock", workdir=tmp_path / "w"))
    t.add(__import__("vcon.models", fromlist=["JobSpec"]).JobSpec(
        input=sample_input, output=out, codec="notchlc", quality="optimal"
    ))
    code = __import__("asyncio").run(t.run())
    assert code == 0
    assert out.exists()
    counts = t.queue.counts()
    assert counts[JobStatus.DONE] == 1


def test_run_empty_batch_is_idle(tmp_path):
    t = Transcoder(TranscoderOptions(backend="mock", workdir=tmp_path / "w"))
    code = __import__("asyncio").run(t.run())
    assert code == 0


def test_results_rows(tmp_path, sample_input):
    out = tmp_path / "clip.nlc.mov"
    t = Transcoder(TranscoderOptions(backend="mock", workdir=tmp_path / "w"))
    t.add(__import__("vcon.models", fromlist=["JobSpec"]).JobSpec(
        input=sample_input, output=out
    ))
    __import__("asyncio").run(t.run())
    rows = t.results()
    assert rows[0]["status"] == "done"
    assert rows[0]["output"] == str(out)


def test_snapshot_serializable_midflight(tmp_path, sample_input):
    t = Transcoder(TranscoderOptions(backend="mock", workdir=tmp_path / "w"))
    t.add(__import__("vcon.models", fromlist=["JobSpec"]).JobSpec(
        input=sample_input, output=tmp_path / "o.mov"
    ))
    snap = t.snapshot()
    json.dumps(snap)  # must not raise
    assert snap["counts"]["queued"] == 1


def test_unknown_backend_rejected(tmp_path):
    from vcon.errors import DriverError
    from vcon.models import JobSpec

    t = Transcoder(TranscoderOptions(backend="carrier-pigeon", workdir=tmp_path / "w"))
    t.add(JobSpec(
        input=write_input(tmp_path), output=tmp_path / "o.nlc.mov"
    ))
    with pytest.raises(DriverError, match="unknown backend"):
        __import__("asyncio").run(t.run())


def write_input(tmp_path):
    src = tmp_path / "in.mov"
    src.write_bytes(b"x" * 60)
    return src


# ----------------------------------------------------------------------
# Config + TD discovery
# ----------------------------------------------------------------------


def test_find_td_flag_wins(tmp_path, monkeypatch):
    fake = tmp_path / "TouchDesigner"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setenv("VCON_TDPATH", "/nope/td")
    p = find_touchdesigner(flag_path=fake)
    assert p == fake


def test_find_td_env_var(tmp_path, monkeypatch):
    fake = tmp_path / "td"
    fake.write_text("")
    monkeypatch.setenv("VCON_TDPATH", str(fake))
    assert find_touchdesigner() == fake


def test_find_td_env_var_missing_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("VCON_TDPATH", str(tmp_path / "ghost"))
    with pytest.raises(ConfigError, match="VCON_TDPATH"):
        find_touchdesigner()


def test_find_td_config_file(tmp_path, monkeypatch):
    monkeypatch.delenv("VCON_TDPATH", raising=False)
    fake = tmp_path / "td-configured"
    fake.write_text("")
    p = tmp_path / "config.json"
    save_config(Config(td_path=str(fake)), p)
    monkeypatch.setattr("vcon.config.config_path", lambda: p)
    assert find_touchdesigner() == fake


def test_find_td_none_when_nothing_set(tmp_path, monkeypatch):
    monkeypatch.delenv("VCON_TDPATH", raising=False)
    empty = tmp_path / "empty-config.json"
    empty.write_text("{}")
    monkeypatch.setattr("vcon.config.config_path", lambda: empty)
    # On dev machines standard locations may hit; force a clean slate
    monkeypatch.setattr("vcon.config._TD_CANDIDATES", {})
    assert find_touchdesigner() is None


def test_config_roundtrip(tmp_path):
    p = tmp_path / "config.json"
    save_config(Config(td_path="/opt/td", port=8001), p)
    cfg = load_config(p)
    assert cfg.td_path == "/opt/td"
    assert cfg.port == 8001


def test_load_missing_config_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "does-not-exist.json")
    assert cfg.td_path is None
    assert cfg.port == 7999


def test_load_corrupt_config_raises(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{not json")
    with pytest.raises(ConfigError, match="unreadable"):
        load_config(p)