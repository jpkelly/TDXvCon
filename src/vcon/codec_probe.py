"""QuickTime codec probe.

Reads the real video codec fourcc out of a .mov/.mp4 by walking the atom tree
to the sample-description (``stsd``) box.

Why this exists: TouchDesigner menu parameters silently fall back to entry 0
when handed a value that is not in the menu. For ``videocodec`` that entry is
``rle``, so a wrong codec token produces a perfectly valid file in the WRONG
codec and nothing anywhere reports an error. vcon verifies its own output
instead of trusting the request.
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from pathlib import Path

#: fourcc → (friendly name, is_it_notchlc)
KNOWN_FOURCCS: dict[bytes, str] = {
    b"rle ": "QuickTime Animation (RLE)",
    b"mjpa": "Motion JPEG A",
    b"mjp b": "Motion JPEG B",
    b"jpeg": "JPEG",
    b"cvid": "Cinepak",
    b"mp4v": "MPEG-4 Video",
    b"avc1": "H.264/AVC",
    b"hvc1": "H.265/HEVC",
    b"hev1": "H.265/HEVC",
    b"av01": "AV1",
    b"vp08": "VP8",
    b"vp09": "VP9",
    b"ap4h": "Apple ProRes 4444",
    b"ap4x": "Apple ProRes 4444 XQ",
    b"apch": "Apple ProRes 422 HQ",
    b"apcn": "Apple ProRes 422",
    b"apcs": "Apple ProRes 422 LT",
    b"apco": "Apple ProRes 422 Proxy",
    b"cfhd": "CineForm",
    # Hap marks its variant, alpha included, in the fourcc. Hap1/Hap5/HapY/
    # HapM verified on TouchDesigner 2025.33230 encodes; the rest are from
    # the Hap specification.
    b"Hap1": "Hap",
    b"Hap5": "Hap Alpha",
    b"HapY": "Hap Q",
    b"HapM": "Hap Q Alpha",
    b"HapA": "Hap Alpha-Only",
    b"Hap7": "Hap R",
    b"HapH": "Hap HDR",
    b"lc  ": "NotchLC",   # observed form in some builds
    b"nclc": "NotchLC",   # observed form in others
    b"Notc": "NotchLC",
}

#: Any fourcc we accept as NotchLC (builds differ in the token they write).
NOTCHLC_FOURCCS = {b"lc  ", b"nclc", b"Notc", b"LC  ", b"NCLC"}

#: Registry codec name → the fourccs a correct encode may write.
#:
#: Used by the pipeline to verify the OUTPUT matches the codec the user
#: REQUESTED. Without this, verification could only ever check NotchLC and
#: would wrongly fail every valid ProRes/Hap/H.264 job.
#:
#: Multiple fourccs per codec where the container may legitimately differ
#: (Hap writes a different fourcc per variant and alpha: see KNOWN_FOURCCS).
FOURCCS_BY_CODEC: dict[str, set[bytes]] = {
    "notchlc": NOTCHLC_FOURCCS,
    "prores": {b"apco", b"apcs", b"apcn", b"apch", b"ap4h", b"ap4x"},
    "hap": {b"Hap1", b"Hap5", b"HapY", b"HapM", b"HapA", b"Hap7", b"HapH"},
    "cineform": {b"cfhd", b"CFHD"},
    "h264": {b"avc1", b"avc3"},
    "h265": {b"hvc1", b"hev1"},
    "av1": {b"av01"},
    "vp8": {b"vp08"},
    "vp9": {b"vp09"},
    "mpeg4": {b"mp4v"},
    "mjpa": {b"mjpa", b"jpeg"},
    "rle": {b"rle "},
    "gif": {b"gif "},
    # vvc: fourcc varies by encoder implementation; skip strict checking.
}


def fourccs_for_codec(name: str) -> set[bytes] | None:
    """Expected output fourccs for a registry codec name (None = unchecked)."""
    return FOURCCS_BY_CODEC.get(name)


@dataclass(frozen=True)
class CodecInfo:
    """Result of probing a movie file."""

    fourcc: bytes
    name: str
    raw_offset: int

    @property
    def is_notchlc(self) -> bool:
        return self.fourcc in NOTCHLC_FOURCCS or self.name == "NotchLC"

    def describe(self) -> str:
        token = self.fourcc.decode("latin-1").strip() or repr(self.fourcc)
        return f"{self.name} ({token!r})"


def _read_at(fh, offset: int, count: int) -> bytes:
    """Read exactly ``count`` bytes at ``offset`` (shorter near EOF)."""
    fh.seek(offset)
    return fh.read(count)


def _iter_atoms_fh(fh, start: int, end: int, limit: int = 64):
    """Yield (atom_type, body_start, body_end) by SEEKING, not reading.

    ``end`` may exceed the real file size (atoms can extend past our window);
    it is clamped by the caller. A ``limit`` guards against pathological
    structures so a corrupt file cannot spin forever.
    """
    pos = start
    seen = 0
    while pos + 8 <= end and seen < limit:
        seen += 1
        header = _read_at(fh, pos, 8)
        if len(header) < 8:
            return
        size = struct.unpack(">I", header[:4])[0]
        atype = header[4:8]
        if size == 1:  # 64-bit extended size
            ext = _read_at(fh, pos + 8, 8)
            if len(ext) < 8:
                return
            size = struct.unpack(">Q", ext)[0]
            body = pos + 16
        elif size == 0:  # extends to end of file
            size = max(8, end - pos)
            body = pos + 8
        else:
            body = pos + 8
        if size < 8:
            return
        yield atype, body, min(pos + size, end)
        pos += size


def probe_codec(path: str | Path) -> CodecInfo | None:
    """Find the first video sample description's fourcc, or None.

    Walks moov → trak → mdia → minf → stbl → stsd using seeks. This matters:
    the ``moov`` atom sits AFTER ``mdat``, so on a multi-gigabyte file the
    codec is at the very END. Reading the whole file (the original
    implementation) exhausted memory on a 31 GB encode.
    """
    p = Path(path)
    if not p.exists():
        return None
    file_size = p.stat().st_size
    if file_size < 16:
        return None

    with p.open("rb") as fh:
        # Top-level scan. 'wide'/'free' padding atoms are skipped naturally.
        for atype, body, body_end in _iter_atoms_fh(fh, 0, file_size):
            if atype == b"moov":
                return _scan_for_stsd(fh, body, body_end)
        # Some writers put moov first but behind a huge mdat: fall back to
        # scanning the tail of the file for a literal 'moov' box.
        return _scan_tail_for_moov(fh, file_size)


def _scan_tail_for_moov(fh, file_size: int, window: int = 1 << 22):
    """Last resort: look for a 'moov' box near the end of the file."""
    start = max(0, file_size - window)
    blob = _read_at(fh, start, file_size - start)
    idx = blob.rfind(b"moov")
    if idx < 4:
        return None
    # The box size precedes the type.
    size = struct.unpack(">I", blob[idx - 4:idx])[0]
    if size < 8:
        return None
    body = start + idx + 4
    return _scan_for_stsd(fh, body, min(body + size - 8, file_size))


def _scan_for_stsd(fh, start: int, end: int) -> CodecInfo | None:
    """Recursively look for an stsd box and read the first entry's fourcc."""
    for atype, body, body_end in _iter_atoms_fh(fh, start, end):
        if atype == b"stsd":
            return _read_stsd(fh, body, body_end)
        if atype in (b"trak", b"mdia", b"minf", b"stbl", b"edts"):
            found = _scan_for_stsd(fh, body, body_end)
            if found is not None:
                return found
    return None


def _read_stsd(fh, body: int, end: int) -> CodecInfo | None:
    """stsd = version(1) flags(3) entryCount(4) then sample entries.

    Each entry: size(4) format(4) ... — we want the format fourcc.
    """
    head = _read_at(fh, body, 16)
    if len(head) < 16:
        return None
    # head[0:4] = version+flags, head[4:8] = entry count, head[8:16] = entry
    entry_size = struct.unpack(">I", head[8:12])[0]
    fourcc = head[12:16]
    if entry_size < 8:
        return None
    name = KNOWN_FOURCCS.get(fourcc)
    if name is None:
        name = f"unknown ({fourcc.decode('latin-1')!r})"
    return CodecInfo(fourcc=fourcc, name=name, raw_offset=body + 12)


def _child(fh, start: int, end: int, kind: bytes):
    """(body, body_end) of the first direct child atom of ``kind``, or None."""
    for atype, body, body_end in _iter_atoms_fh(fh, start, end):
        if atype == kind:
            return body, body_end
    return None


def _descend(fh, start: int, end: int, kinds: tuple[bytes, ...]):
    """Follow a path of child atoms (e.g. minf → stbl); None if absent."""
    span = (start, end)
    for kind in kinds:
        span = _child(fh, span[0], span[1], kind)
        if span is None:
            return None
    return span


def _video_stbl(fh, start: int, end: int):
    """Span of the first VIDEO trak's sample table (``stbl``), or None.

    The handler matters: after the audio mux a file holds a sound trak
    too, and it may come first. ``hdlr`` carries the handler type at body
    offset 8 in both QuickTime (component subtype) and ISO MP4
    (handler_type).
    """
    for atype, body, body_end in _iter_atoms_fh(fh, start, end):
        if atype != b"trak":
            continue
        mdia = _child(fh, body, body_end, b"mdia")
        if mdia is None:
            continue
        hdlr = _child(fh, mdia[0], mdia[1], b"hdlr")
        if hdlr is None or _read_at(fh, hdlr[0] + 8, 4) != b"vide":
            continue
        return _descend(fh, mdia[0], mdia[1], (b"minf", b"stbl"))
    return None


def _video_frames_in_moov(fh, start: int, end: int) -> int | None:
    """Sample count of the first video trak (a sound trak's is not a
    frame count)."""
    stbl = _video_stbl(fh, start, end)
    if stbl is not None:
        # stsz / stz2: version+flags(4), size-or-reserved(4), count(4)
        for kind in (b"stsz", b"stz2"):
            box = _child(fh, stbl[0], stbl[1], kind)
            if box is not None:
                head = _read_at(fh, box[0], 12)
                if len(head) == 12:
                    return struct.unpack(">I", head[8:12])[0]
        # stts: version+flags(4), entries(4), then (count, delta) pairs
        box = _child(fh, stbl[0], stbl[1], b"stts")
        if box is not None:
            head = _read_at(fh, box[0], 8)
            if len(head) == 8:
                n = struct.unpack(">I", head[4:8])[0]
                table = _read_at(fh, box[0] + 8, 8 * n)
                if len(table) == 8 * n:
                    return sum(struct.unpack(">I", table[i:i + 4])[0]
                               for i in range(0, 8 * n, 8))
    return None


def probe_video_frames(path: str | Path) -> int | None:
    """Number of frames in a .mov/.mp4's video track, or None if unreadable.

    Reads the sample table rather than decoding, using seeks like
    :func:`probe_codec`, so it is cheap on multi-gigabyte files. None means
    "could not tell" (incomplete file, other container), never zero.
    """
    p = Path(path)
    if not p.exists():
        return None
    file_size = p.stat().st_size
    if file_size < 16:
        return None
    with p.open("rb") as fh:
        for atype, body, body_end in _iter_atoms_fh(fh, 0, file_size):
            if atype == b"moov":
                return _video_frames_in_moov(fh, body, body_end)
    return None


#: Hap says whether it carries alpha in the fourcc. TouchDesigner writes
#: depth 24 into Hap's sample entry with or without alpha (2025.33230).
HAP_ALPHA_FOURCCS = {b"Hap5", b"HapM", b"HapA"}
HAP_OPAQUE_FOURCCS = {b"Hap1", b"HapY", b"Hap7", b"HapH"}

#: Fourccs whose sample entry cannot show alpha: TouchDesigner writes
#: NotchLC as depth 24 whether or not the file has alpha (2025.33230).
ALPHA_UNKNOWN_FOURCCS = NOTCHLC_FOURCCS

#: Offset of the 16-bit ``depth`` field in a QuickTime/ISO visual sample
#: entry: size(4) format(4) reserved(6) data_ref(2) version/revision/vendor
#: or pre_defined(16) width(2) height(2) hres(4) vres(4) data_size(4)
#: frame_count(2) compressor_name(32).
_DEPTH_AT = 82


def video_sample_entry(path: str | Path) -> tuple[bytes, int] | None:
    """(fourcc, depth) of the first video track's sample entry, or None."""
    p = Path(path)
    if not p.exists() or p.stat().st_size < 16:
        return None
    file_size = p.stat().st_size
    with p.open("rb") as fh:
        for atype, body, body_end in _iter_atoms_fh(fh, 0, file_size):
            if atype != b"moov":
                continue
            stbl = _video_stbl(fh, body, body_end)
            box = stbl and _child(fh, stbl[0], stbl[1], b"stsd")
            if not box:
                return None
            # stsd: version+flags(4), entry count(4), then the first entry.
            entry = _read_at(fh, box[0] + 8, _DEPTH_AT + 2)
            if len(entry) < _DEPTH_AT + 2:
                return None
            depth = struct.unpack(">H", entry[_DEPTH_AT:_DEPTH_AT + 2])[0]
            return entry[4:8], depth
    return None


def source_has_alpha(path: str | Path) -> bool | None:
    """Whether a movie's video carries alpha: True, False, or None (unknown).

    Read from the video sample entry, without decoding: Hap by its fourcc,
    other QuickTime/MP4 video by the depth field (32 = alpha, 24 = none),
    the convention ProRes 4444 and Animation follow. None for NotchLC,
    whose sample entry looks the same either way, for other containers,
    and for unreadable files.
    """
    found = video_sample_entry(path)
    if found is None:
        return None
    fourcc, depth = found
    if fourcc in HAP_ALPHA_FOURCCS:
        return True
    if fourcc in HAP_OPAQUE_FOURCCS:
        return False
    if fourcc in ALPHA_UNKNOWN_FOURCCS:
        return None
    if depth == 32:
        return True
    if depth == 24:
        return False
    return None


def verify_frame_count(path: str | Path, expected: int) -> tuple[bool, str]:
    """Check the output's video frame count; returns (ok, human message).

    Run after :func:`verify_output` has seen a readable ``moov``. A count
    that cannot be read (e.g. a container without a QuickTime sample
    table) passes with a note: this check only fails on a real mismatch.
    """
    found = probe_video_frames(path)
    if found is None:
        return True, "frame count not readable, not checked"
    if found != expected:
        return False, (
            f"output has {found} video frames but {expected} were written "
            f"— the file is incomplete or frames were dropped"
        )
    return True, f"{found} frames"


def verify_output(
    path: str | Path,
    *,
    expect_notchlc: bool = True,
    expect_fourccs: set[bytes] | None = None,
    retries: int = 5,
    retry_delay: float = 0.4,
) -> tuple[bool, str]:
    """Verify an encoded file's codec; returns (ok, human message).

    RETRIES matter here: TouchDesigner writes the ``moov`` index (which holds
    the codec) when it CLOSES the file, and on a large encode that final flush
    can still be in progress when ``done`` arrives. A single attempt raced it
    and reported "could not read the video codec" on a perfectly good 45 GB
    ProRes file. We wait for the atom tree to become parseable.
    """
    p = Path(path)
    if not p.exists():
        return False, f"output file missing: {p}"

    last = "could not read the video codec from the output file " \
           "(container may be incomplete or unrecognised)"

    for attempt in range(max(1, retries)):
        size = p.stat().st_size
        if size == 0:
            last = f"output file is empty: {p}"
        else:
            info = probe_codec(p)
            if info is not None:
                if expect_fourccs is not None:
                    if info.fourcc in expect_fourccs:
                        return True, f"output codec verified: {info.describe()}"
                    return False, (
                        f"output is {info.describe()}, but "
                        f"{sorted(f.decode('latin-1') for f in expect_fourccs)} "
                        f"was requested — TouchDesigner fell back to another codec"
                    )
                if expect_notchlc and not info.is_notchlc:
                    return False, (
                        f"output is {info.describe()}, NOT NotchLC — "
                        f"TouchDesigner rejected the codec value and fell "
                        f"back to its default"
                    )
                return True, f"output codec verified: {info.describe()}"
        if attempt + 1 < retries:
            time.sleep(retry_delay)

    return False, last
