"""MockDriver — runs the whole pipeline without TouchDesigner.

Simulates the controller's message stream (hello handshake, accepted with a
plausible frame count, progress ticks, done) so queue/CLI/protocol logic is
fully testable and developable on machines without TD.

Set ``ctx.extra["sleep"]`` to slow ticks (integration feel), and
``ctx.fail_on_job`` to inject a per-job error and verify failure paths.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from vcon.driver import Driver, DriverContext
from vcon.models import Job


def _guess_total_frames(input_path: Path) -> int:
    """Deterministic pseudo frame count from file size (10 fps/s assumed).

    Real totals come from TouchDesigner's Movie File In info. The mock only
    needs something plausible and stable for tests.
    """
    size = input_path.stat().st_size
    return max(2, min(240, size % 239 + 24))


def _fake_notchlc_mov(frames: int) -> bytes:
    """Smallest QuickTime file whose stsd fourcc reads as NotchLC.

    Not a playable movie — just enough atom structure for the real codec
    probe to exercise its parsing path in tests without TouchDesigner.
    """
    import struct

    def atom(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload) + 8) + kind + payload

    ftyp = atom(b"ftyp", b"qt  " + struct.pack(">I", 0x200) + b"qt  ")
    mdat = atom(b"mdat", b"\x00" * min(frames, 64))
    # stsd: version/flags(4) entryCount(4) then one entry: size(4) fourcc(4)
    entry = struct.pack(">I", 16) + b"nclc" + b"\x00" * 8
    stsd = atom(b"stsd", b"\x00\x00\x00\x00" + struct.pack(">I", 1) + entry)
    # stsz: version/flags(4) uniform size(4) count(4) — the frame count the
    # real probe checks against the controller's frames_written.
    stsz = atom(b"stsz", b"\x00" * 4 + struct.pack(">II", 1, frames))
    stbl = atom(b"stbl", stsd + stsz)
    minf = atom(b"minf", stbl)
    # hdlr marks this trak as video: version/flags(4) type(4) subtype(4)
    hdlr = atom(b"hdlr", b"\x00" * 4 + b"mhlr" + b"vide" + b"\x00" * 12)
    mdia = atom(b"mdia", hdlr + minf)
    trak = atom(b"trak", mdia)
    moov = atom(b"moov", trak)
    return ftyp + mdat + moov


class MockDriver(Driver):
    """Fake encoder backend."""

    def __init__(self, ctx: DriverContext) -> None:
        super().__init__(ctx)
        self._cancelled: set[str] = set()
        self._paused: set[str] = set()
        self._pause_star = False
        self._active: str | None = None
        self._stop = asyncio.Event()
        self._fail_on_job: str | None = ctx.fail_on_job

    async def run(self, jobs: list[Job]) -> None:
        self._emit({"type": "hello", "version": 1})
        for job in jobs:
            if self._fail_on_job == job.id:
                self._emit_simple(
                    job.id, "error",
                    message="injected failure", code="mock-injected",
                )
                continue
            if job.id in self._cancelled:
                self._emit_simple(job.id, "error", message="cancelled", code="cancelled")
                continue
            await self._run_one(job)

    async def _run_one(self, job: Job) -> None:
        # "open" the input; a missing file at this stage is a driver-level bug
        # (CLI validates earlier) but guard anyway.
        if not job.spec.input.exists():
            self._emit_simple(
                job.id, "error", message=f"input vanished: {job.spec.input}",
                code="input-missing",
            )
            return

        total = _guess_total_frames(job.spec.input)
        self._active = job.id
        self._emit_simple(job.id, "accepted", total_frames=total)

        tick = float(self.ctx.extra.get("sleep", 0.005))
        for frame in range(1, total + 1):
            if self._stop.is_set() or job.id in self._cancelled:
                self._emit_simple(job.id, "error", message="cancelled", code="cancelled")
                return
            await asyncio.sleep(tick)
            # Check pause AFTER the sleep: a pause that arrives mid-sleep
            # must suppress this frame's progress, not leak one more event
            # (which made early pause tests race by a single frame).
            while ((job.id in self._paused or self._pause_star)
                   and not self._stop.is_set()):
                # Paused: hold at this frame (no progress) until resumed.
                await asyncio.sleep(tick)
                if job.id in self._cancelled:
                    self._emit_simple(job.id, "error", message="cancelled",
                                      code="cancelled")
                    return
            self._emit_simple(job.id, "progress", frame=frame, total_frames=total)

        # Materialize output so overwrite/verification logic is exercised.
        # A minimal QuickTime container carrying an 'nclc' video sample
        # description, so the real codec probe has something honest to read.
        try:
            job.spec.output.parent.mkdir(parents=True, exist_ok=True)
            job.spec.output.write_bytes(_fake_notchlc_mov(total))
        except OSError as exc:
            self._emit_simple(job.id, "error", message=str(exc), code="output-error")
            return

        self._emit_simple(
            job.id, "done", path=str(job.spec.output), total_frames=total,
            seconds=round(total * tick, 3),
        )
        self._active = None

    async def cancel(self, job_id: str) -> None:
        """Test seam; the real driver forwards a protocol cancel to the toe."""
        self._cancelled.add(job_id)

    async def pause(self, job_id: str) -> None:
        """Test seam; the real driver forwards a protocol pause to the toe.
        job_id "*" pauses whichever job is currently emitting progress."""
        self._paused.add(job_id)
        if job_id == "*":
            # target the active job — resolved lazily by _run_one's check
            self._pause_star = True

    async def resume(self, job_id: str) -> None:
        self._paused.discard(job_id)
        if job_id == "*":
            self._pause_star = False

    async def shutdown(self) -> None:
        self._stop.set()


def make_mock_context(workdir: Path, **extra: object) -> DriverContext:
    """Convenience builder for tests and the CLI's ``--mock`` flag."""
    fail = extra.pop("fail_on_job", None)
    return DriverContext(workdir=workdir, extra=dict(extra), fail_on_job=fail)