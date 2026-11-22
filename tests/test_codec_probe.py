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
    # Hap Q with alpha (measured on TD 2025.33230); was missing, so a
    # correct hapq+alpha encode failed verification as the wrong codec.
    assert b"HapM" in fourccs_for_codec("hap")
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


# ----------------------------------------------------------------------
# Frame count (issue #2): the file must hold every frame that was written
# ----------------------------------------------------------------------


def _trak(handler: bytes, frames: int, table: bytes = b"stsz") -> bytes:
    hdlr = _atom(b"hdlr", b"\x00" * 4 + b"mhlr" + handler + b"\x00" * 12)
    entry = struct.pack(">I", 16) + (b"nclc" if handler == b"vide"
                                     else b"lpcm") + b"\x00" * 8
    stsd = _atom(b"stsd", b"\x00" * 4 + struct.pack(">I", 1) + entry)
    if table == b"stsz":
        counts = _atom(b"stsz", b"\x00" * 4 + struct.pack(">II", 0, frames)
                       + struct.pack(">I", 100) * frames)
    else:  # stts only: two runs that add up to `frames`
        first = frames // 2
        counts = _atom(b"stts", b"\x00" * 4 + struct.pack(">I", 2)
                       + struct.pack(">II", first, 1000)
                       + struct.pack(">II", frames - first, 1001))
    stbl = _atom(b"stbl", stsd + counts)
    mdia = _atom(b"mdia", hdlr + _atom(b"minf", stbl))
    return _atom(b"trak", mdia)


def _mov(*traks: bytes) -> bytes:
    ftyp = _atom(b"ftyp", b"qt  " + struct.pack(">I", 0x200) + b"qt  ")
    return ftyp + _atom(b"mdat", b"\x00" * 32) + _atom(b"moov", b"".join(traks))


def test_probe_video_frames_reads_stsz(tmp_path):
    from vcon.codec_probe import probe_video_frames

    p = tmp_path / "v.mov"
    p.write_bytes(_mov(_trak(b"vide", 48)))
    assert probe_video_frames(p) == 48


def test_probe_video_frames_skips_audio_track(tmp_path):
    """After the audio mux the file has a sound trak; its sample count is
    not a frame count, even when it comes first."""
    from vcon.codec_probe import probe_video_frames

    p = tmp_path / "av.mov"
    p.write_bytes(_mov(_trak(b"soun", 96000), _trak(b"vide", 48)))
    assert probe_video_frames(p) == 48


def test_probe_video_frames_falls_back_to_stts(tmp_path):
    from vcon.codec_probe import probe_video_frames

    p = tmp_path / "t.mov"
    p.write_bytes(_mov(_trak(b"vide", 49, table=b"stts")))
    assert probe_video_frames(p) == 49


def test_probe_video_frames_unreadable_is_none_not_zero(tmp_path):
    from vcon.codec_probe import probe_video_frames

    p = tmp_path / "plain.mov"
    p.write_bytes(_mov_with_fourcc(b"nclc"))     # no hdlr / sample table
    assert probe_video_frames(p) is None
    assert probe_video_frames(tmp_path / "missing.mov") is None


def test_verify_frame_count(tmp_path):
    from vcon.codec_probe import verify_frame_count

    p = tmp_path / "v.mov"
    p.write_bytes(_mov(_trak(b"vide", 48)))
    assert verify_frame_count(p, 48) == (True, "48 frames")
    ok, note = verify_frame_count(p, 50)
    assert not ok and "48 video frames but 50 were written" in note

    plain = tmp_path / "plain.mov"
    plain.write_bytes(_mov_with_fourcc(b"nclc"))
    ok, note = verify_frame_count(plain, 50)
    assert ok and "not checked" in note


@pytest.mark.skipif(__import__("shutil").which("ffmpeg") is None,
                    reason="needs ffmpeg to make real movie files")
@pytest.mark.parametrize("name, args", [
    ("prores_pcm.mov", ["-c:v", "prores_ks", "-c:a", "pcm_s24le"]),
    ("h264_bframes.mp4", ["-c:v", "libx264", "-bf", "2", "-c:a", "aac"]),
    ("audio_first.mov", ["-map", "1:a", "-map", "0:v", "-c:v", "libx264",
                         "-c:a", "aac"]),
    ("faststart.mp4", ["-c:v", "libx264", "-c:a", "aac",
                       "-movflags", "+faststart"]),
])
def test_probe_video_frames_on_real_files(tmp_path, name, args):
    import subprocess

    from vcon.codec_probe import probe_video_frames

    out = tmp_path / name
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "lavfi", "-i", "testsrc2=size=160x120:rate=24",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
         "-frames:v", "48", "-t", "2", *args, str(out)],
        check=True)
    assert probe_video_frames(out) == 48


def test_hap_fourcc_names_match_the_variants_td_writes():
    """TD 2025.33230: hap rgb → Hap1, hap rgba → Hap5, hapq rgb → HapY,
    hapq rgba → HapM."""
    assert KNOWN_FOURCCS[b"Hap1"] == "Hap"
    assert KNOWN_FOURCCS[b"Hap5"] == "Hap Alpha"
    assert KNOWN_FOURCCS[b"HapY"] == "Hap Q"
    assert KNOWN_FOURCCS[b"HapM"] == "Hap Q Alpha"


# ----------------------------------------------------------------------
# Source alpha (issue #4): "follow source" needs to know, before the job
# starts, whether the input carries alpha.
# ----------------------------------------------------------------------


@pytest.mark.parametrize("fourcc, depth, expected", [
    (b"ap4h", 32, True),      # ProRes 4444 with alpha (ffmpeg and TD)
    (b"ap4h", 24, False),
    (b"rle ", 32, True),      # QuickTime Animation follows the same rule
    (b"avc1", 24, False),
    (b"Hap5", 24, True),      # Hap: the fourcc decides; TD writes depth 24
    (b"HapM", 24, True),
    (b"Hap1", 24, False),
    (b"HapY", 24, False),
    (b"nclc", 24, None),      # NotchLC: TD writes 24 with or without alpha
    (b"ap4h", 0, None),       # a depth that follows no convention
])
def test_source_has_alpha_from_sample_entry(make_movie, fourcc, depth, expected):
    from vcon.codec_probe import source_has_alpha

    assert source_has_alpha(make_movie("s.mov", fourcc, depth)) is expected


def test_source_has_alpha_reads_the_video_track_not_the_first(make_movie):
    from vcon.codec_probe import video_sample_entry

    p = make_movie("av.mov", b"ap4h", 32, audio_first=True)
    assert video_sample_entry(p) == (b"ap4h", 32)


def test_source_has_alpha_unknown_for_other_files(tmp_path):
    from vcon.codec_probe import source_has_alpha

    junk = tmp_path / "clip.webm"
    junk.write_bytes(b"\x1aE\xdf\xa3" + b"\x00" * 64)
    assert source_has_alpha(junk) is None
    assert source_has_alpha(tmp_path / "missing.mov") is None


@pytest.mark.skipif(__import__("shutil").which("ffmpeg") is None,
                    reason="needs ffmpeg to make real movie files")
@pytest.mark.parametrize("pix_fmt, expected", [
    ("yuva444p10le", True), ("yuv444p10le", False)])
def test_source_has_alpha_on_real_prores(tmp_path, pix_fmt, expected):
    import subprocess

    from vcon.codec_probe import source_has_alpha

    out = tmp_path / f"{pix_fmt}.mov"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
         "-i", "testsrc2=size=160x120:rate=24", "-frames:v", "4",
         "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", pix_fmt,
         str(out)], check=True)
    assert source_has_alpha(out) is expected
