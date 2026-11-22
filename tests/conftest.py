"""Shared test fixtures."""

from __future__ import annotations

import struct

import pytest

from vcon.events import EventBus
from vcon.models import JobSpec
from vcon.queue_manager import QueueManager
from vcon.registry import Registry


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def registry() -> Registry:
    return Registry()


@pytest.fixture
def queue(bus: EventBus, registry: Registry) -> QueueManager:
    return QueueManager(bus, registry=registry)


@pytest.fixture
def sample_input(tmp_path):
    p = tmp_path / "clip.mov"
    p.write_bytes(b"fake-video-content-0123456789")
    return p


@pytest.fixture
def sample_spec(sample_input, tmp_path) -> JobSpec:
    return JobSpec(
        input=sample_input,
        output=tmp_path / "clip.nlc.mov",
        codec="notchlc",
        quality="optimal",
    )

def _atom(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload) + 8) + kind + payload


def video_sample_entry_bytes(fourcc: bytes, depth: int) -> bytes:
    """A QuickTime visual sample entry; ``depth`` sits at byte 82."""
    body = (b"\x00" * 6 + struct.pack(">H", 1)          # reserved, data ref
            + b"\x00" * 16                              # version..spatial q
            + struct.pack(">HH", 160, 120)
            + struct.pack(">II", 0x480000, 0x480000)    # 72 dpi
            + b"\x00" * 4 + struct.pack(">H", 1)        # data size, frames
            + b"\x00" * 32                              # compressor name
            + struct.pack(">hh", depth, -1))            # depth, color table
    return struct.pack(">I", 8 + len(body)) + fourcc + body


def movie_bytes(fourcc: bytes, depth: int, *, audio_first: bool = False,
                stts: list[tuple[int, int]] | None = None) -> bytes:
    """A minimal .mov whose video track has the given sample entry and,
    optionally, frame-duration runs ``stts`` [(count, duration), ...]."""
    def trak(handler: bytes, entry: bytes, extra: bytes = b"") -> bytes:
        hdlr = _atom(b"hdlr", b"\x00" * 4 + b"mhlr" + handler + b"\x00" * 12)
        stsd = _atom(b"stsd", b"\x00" * 4 + struct.pack(">I", 1) + entry)
        minf = _atom(b"minf", _atom(b"stbl", stsd + extra))
        return _atom(b"trak", _atom(b"mdia", hdlr + minf))

    table = b""
    if stts:
        table = _atom(b"stts", b"\x00" * 4 + struct.pack(">I", len(stts))
                      + b"".join(struct.pack(">II", c, d) for c, d in stts))
    traks = [trak(b"vide", video_sample_entry_bytes(fourcc, depth), table)]
    if audio_first:
        audio = struct.pack(">I", 16) + b"lpcm" + b"\x00" * 8
        traks.insert(0, trak(b"soun", audio))
    ftyp = _atom(b"ftyp", b"qt  " + struct.pack(">I", 0x200) + b"qt  ")
    return ftyp + _atom(b"mdat", b"\x00" * 32) + _atom(b"moov", b"".join(traks))


@pytest.fixture
def make_movie(tmp_path):
    """make_movie(name, fourcc, depth) -> Path of a minimal .mov."""
    def make(name: str, fourcc: bytes, depth: int, **kw):
        p = tmp_path / name
        p.write_bytes(movie_bytes(fourcc, depth, **kw))
        return p
    return make
