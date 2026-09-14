"""Codec probe: reads the real fourcc from a movie's stsd atom.

These tests exist because the first "successful" transcode produced a
perfectly valid QuickTime file in the WRONG codec (rle instead of NotchLC)
and nothing reported an error. Verification is now part of the pipeline.
"""

from __future__ import annotations

import struct

import pytest

from vcon.codec_probe import (
    CodecInfo,
    KNOWN_FOURCCS,
    probe_codec,
    verify_output,
)


def _atom(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload) + 8) + kind + payload


def _mov_with_fourcc(fourcc: bytes) -> bytes:
    ftyp = _atom(b"ftyp", b"qt  " + struct.pack(">I", 0x200) + b"qt  ")
    mdat = _atom(b"mdat", b"\x00" * 32)
    entry = struct.pack(">I", 16) + fourcc + b"\x00" * 8
    stsd = _atom(b"stsd", b"\x00\x00\x00\x00" + struct.pack(">I", 1) + entry)
    stbl = _atom(b"stbl", stsd)
    minf = _atom(b"minf", stbl)
    mdia = _atom(b"mdia", minf)
    trak = _atom(b"trak", mdia)
    moov = _atom(b"moov", trak)
    return ftyp + mdat + moov


def test_probe_detects_notchlc(tmp_path):
    p = tmp_path / "a.nlc.mov"
    p.write_bytes(_mov_with_fourcc(b"nclc"))
    info = probe_codec(p)
    assert info is not None
    assert info.is_notchlc
    assert info.name == "NotchLC"


def test_probe_detects_rle(tmp_path):
    """The exact failure mode that shipped: a 'valid' file in the wrong codec."""
    p = tmp_path / "wrong.mov"
    p.write_bytes(_mov_with_fourcc(b"rle "))
    info = probe_codec(p)
    assert info is not None
    assert not info.is_notchlc
    assert "Animation" in info.name


def test_probe_detects_prores_and_h264(tmp_path):
    for fourcc, expect in ((b"ap4h", "ProRes 4444"), (b"avc1", "H.264")):
        p = tmp_path / f"{fourcc.decode().strip()}.mov"
        p.write_bytes(_mov_with_fourcc(fourcc))
        info = probe_codec(p)
        assert info is not None and expect in info.name


def test_probe_returns_none_for_garbage(tmp_path):
    p = tmp_path / "junk.mov"
    p.write_bytes(b"not a movie at all, definitely not")
    assert probe_codec(p) is None


def test_probe_returns_none_for_missing_file(tmp_path):
    assert probe_codec(tmp_path / "nope.mov") is None


def test_verify_output_accepts_notchlc(tmp_path):
    p = tmp_path / "good.mov"
    p.write_bytes(_mov_with_fourcc(b"nclc"))
    ok, msg = verify_output(p)
    assert ok
    assert "NotchLC" in msg


def test_verify_output_rejects_wrong_codec(tmp_path):
    p = tmp_path / "bad.mov"
    p.write_bytes(_mov_with_fourcc(b"rle "))
    ok, msg = verify_output(p)
    assert not ok
    assert "NOT NotchLC" in msg
    assert "rle" in msg.lower() or "Animation" in msg


def test_verify_output_reports_missing_file(tmp_path):
    ok, msg = verify_output(tmp_path / "absent.mov")
    assert not ok
    assert "missing" in msg


def test_verify_output_reports_empty_file(tmp_path):
    p = tmp_path / "empty.mov"
    p.write_bytes(b"")
    ok, msg = verify_output(p)
    assert not ok
    assert "empty" in msg or "codec" in msg


def test_verify_output_reports_unreadable(tmp_path):
    p = tmp_path / "junk.mov"
    p.write_bytes(b"garbage" * 20)
    ok, msg = verify_output(p)
    assert not ok
    assert "could not read" in msg


def test_verify_output_can_skip_notchlc_expectation(tmp_path):
    p = tmp_path / "anything.mov"
    p.write_bytes(_mov_with_fourcc(b"ap4h"))
    ok, msg = verify_output(p, expect_notchlc=False)
    assert ok


def test_codec_info_describe():
    info = CodecInfo(fourcc=b"nclc", name="NotchLC", raw_offset=100)
    assert "NotchLC" in info.describe()


def test_known_fourcc_table_has_no_duplicate_names_for_notchlc():
    """Several builds write different tokens; all must map to NotchLC."""
    tokens = [cc for cc, name in KNOWN_FOURCCS.items() if name == "NotchLC"]
    assert len(tokens) >= 2
    for t in tokens:
        assert CodecInfo(fourcc=t, name="NotchLC", raw_offset=0).is_notchlc


# ----------------------------------------------------------------------
# Codec-aware verification (a NotchLC-only check would fail valid ProRes)
# ----------------------------------------------------------------------


def test_fourccs_for_each_registry_codec():
    from vcon.codec_probe import fourccs_for_codec

    assert b"ap4x" in fourccs_for_codec("prores")
    assert b"ap4h" in fourccs_for_codec("prores")
    assert b"Hap5" in fourccs_for_codec("hap")
    assert b"avc1" in fourccs_for_codec("h264")
    assert fourccs_for_codec("notchlc") is not None
    assert fourccs_for_codec("no-such-codec") is None


def test_verify_accepts_prores_when_prores_requested(tmp_path):
    """The real bug: a 45GB ProRes 4444 XQ file was rejected by a
    NotchLC-only verifier."""
    p = tmp_path / "out.mov"
    p.write_bytes(_mov_with_fourcc(b"ap4x"))
    from vcon.codec_probe import fourccs_for_codec

    ok, msg = verify_output(p, expect_notchlc=False,
                            expect_fourccs=fourccs_for_codec("prores"))
    assert ok
    assert "ProRes" in msg


def test_verify_rejects_wrong_codec_against_expected_set(tmp_path):
    p = tmp_path / "out.mov"
    p.write_bytes(_mov_with_fourcc(b"rle "))
    from vcon.codec_probe import fourccs_for_codec

    ok, msg = verify_output(p, expect_notchlc=False,
                            expect_fourccs=fourccs_for_codec("prores"))
    assert not ok
    assert "fell back to another codec" in msg


def test_verify_retries_until_moov_is_readable(tmp_path, monkeypatch):
    """TouchDesigner writes moov at file close; a big encode can still be
    flushing when 'done' arrives. One attempt raced it and produced a false
    failure — verification must wait."""
    import vcon.codec_probe as cp

    calls = {"n": 0}
    real = cp.probe_codec

    def flaky(path):
        calls["n"] += 1
        if calls["n"] < 3:
            return None          # simulate truncated / still-flushing moov
        return real(path)

    p = tmp_path / "out.mov"
    p.write_bytes(_mov_with_fourcc(b"nclc"))
    monkeypatch.setattr(cp, "probe_codec", flaky)

    ok, msg = cp.verify_output(p, retries=5, retry_delay=0.01)
    assert ok, msg
    assert calls["n"] == 3
