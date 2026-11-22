"""TouchDesignerDriver against a FAKE controller server.

The fake controller implements the toe-side contract: listen, send hello,
accept submit lines, stream accepted/progress/done. Everything (server +
driver) runs on ONE asyncio loop per test — matching production, where the
real toe is a separate process but the driver talks to it over TCP.

These tests pin the wire behavior the real transcoder.toe must satisfy in
phase 2: skip _launch_td (no TD install needed) and drive the connection
steps directly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from vcon.driver import DriverContext
from vcon.models import Job, JobSpec
from vcon.td_driver import TDProcessError, TouchDesignerDriver


class FakeController:
    """In-process stand-in for the transcoder.toe TCP server."""

    def __init__(self, port: int = 0):
        self.port = port
        self.server: asyncio.AbstractServer | None = None
        self.received: list[dict] = []
        self.responses = {
            # job_id -> list of messages to send back
        }

    async def start(self):
        self.server = await asyncio.start_server(
            self._handle, "127.0.0.1", self.port
        )
        sock = self.server.sockets[0]
        self.port = sock.getsockname()[1]
        return self

    async def _handle(self, reader, writer):
        # hello handshake
        hello = b'{"type": "hello", "version": 1}\n'
        writer.write(hello)
        await writer.drain()
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                from vcon.protocol import decode_msg

                msg = decode_msg(line)
                self.received.append(msg)
                script = self.responses.get(msg.get("id"), _default_script(msg))
                for reply in script:
                    payload = reply(msg) if callable(reply) else reply
                    writer.write(payload + b"\n")
                    await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()


def _default_script(msg):
    """Standard reply sequence for one submit."""
    import json

    jid = msg["id"]
    total = 12
    out = []

    def accepted(m):
        return json.dumps({"type": "accepted", "id": jid, "total_frames": total}).encode()

    def progress(i):
        def _p(m):
            return json.dumps(
                {"type": "progress", "id": jid, "frame": i, "total_frames": total}
            ).encode()

        return _p

    def done(m):
        return json.dumps({
            "type": "done", "id": jid, "path": m["output"],
            "total_frames": total, "seconds": 1.5,
        }).encode()

    out = [accepted, progress(4), progress(8), progress(12), done]
    return out


@pytest.fixture
def fake_controller():
    """Server whose lifecycle is managed inside each test's event loop."""
    fc = FakeController()
    yield fc


def _make_jobs(tmp_path: Path, n: int = 1) -> list[Job]:
    src = tmp_path / "in.mov"
    src.write_bytes(b"x" * 50)
    jobs = []
    for i in range(n):
        spec = JobSpec(input=src, output=tmp_path / f"out{i}.nlc.mov")
        jobs.append(Job(spec=spec, id=f"j{i + 1}"))
    return jobs


def test_driver_relays_messages(tmp_path, fake_controller):
    async def scenario():
        await fake_controller.start()
        try:
            ctx = DriverContext(
                workdir=tmp_path, td_path=None, toe_path=None,
                port=fake_controller.port, watchdog_timeout=5.0,
            )
            driver = TouchDesignerDriver(ctx)
            messages = []
            driver.set_on_message(lambda m: messages.append(m))
            driver.set_completion_hook(lambda jid: any(
                m.get("id") == jid and m["type"] in ("done", "error")
                for m in messages
            ))
            jobs = _make_jobs(tmp_path)
            await driver._start_session()
            await driver._hello_future()
            await driver._drive(jobs)
            return messages
        finally:
            await driver.shutdown()
            await fake_controller.stop()

    messages = asyncio.run(scenario())
    types = [m["type"] for m in messages]
    assert types == ["accepted", "progress", "progress", "progress", "done"]
    assert messages[-1]["total_frames"] == 12


def test_driver_sends_submit_wire_messages(tmp_path, fake_controller):
    async def scenario():
        await fake_controller.start()
        driver = None
        try:
            ctx = DriverContext(
                workdir=tmp_path, port=fake_controller.port, watchdog_timeout=5.0,
            )
            driver = TouchDesignerDriver(ctx)
            seen: list[dict] = []
            driver.set_on_message(lambda m: seen.append(m))
            driver.set_completion_hook(lambda jid: any(
                m.get("id") == jid and m["type"] in ("done", "error")
                for m in seen
            ))
            jobs = _make_jobs(tmp_path, n=2)
            await driver._start_session()
            await driver._hello_future()
            await driver._drive(jobs)
        finally:
            if driver is not None:
                await driver.shutdown()
            await fake_controller.stop()

    asyncio.run(scenario())
    submits = [m for m in fake_controller.received if m["type"] == "submit"]
    assert len(submits) == 2
    assert submits[0]["id"] == "j1"
    assert submits[1]["id"] == "j2"


def _free_port() -> int:
    """An unused localhost port.

    Tests must NOT use the default 7999: if the developer has TouchDesigner
    open with the toe loaded, the driver's attach-to-running-controller path
    would connect to that live session and start driving real jobs.
    """
    import socket as _socket

    with _socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_driver_missing_toe_fails_cleanly(tmp_path):
    async def scenario():
        fake_td = tmp_path / "TouchDesigner"
        fake_td.write_text("#!/bin/sh\n")  # must exist so the toe check is reached
        ctx = DriverContext(
            workdir=tmp_path, td_path=fake_td,
            toe_path=tmp_path / "nonexistent.toe", port=_free_port(),
        )
        driver = TouchDesignerDriver(ctx)
        try:
            await driver.run(_make_jobs(tmp_path))
        except TDProcessError as exc:
            return str(exc)
        finally:
            await driver.shutdown()
        return "no-error"

    msg = asyncio.run(scenario())
    assert "transcoder.toe not found" in msg


def test_shutdown_is_idempotent(tmp_path):
    async def scenario():
        ctx = DriverContext(workdir=tmp_path, port=_free_port())
        driver = TouchDesignerDriver(ctx)
        await driver.shutdown()
        await driver.shutdown()

    asyncio.run(scenario())


def test_attach_only_when_controller_is_listening(tmp_path, fake_controller):
    """With nothing listening, _attach_if_running must return False (so the
    driver proceeds to launch TD) — and must not raise."""
    async def scenario():
        ctx = DriverContext(workdir=tmp_path, port=_free_port())
        driver = TouchDesignerDriver(ctx)
        attached = await driver._attach_if_running()
        await driver.shutdown()
        return attached

    assert asyncio.run(scenario()) is False


def test_attach_true_when_controller_present(tmp_path, fake_controller):
    """With a controller listening, the driver attaches and does NOT own it."""
    async def scenario():
        await fake_controller.start()
        try:
            ctx = DriverContext(
                workdir=tmp_path, port=fake_controller.port,
                watchdog_timeout=5.0,
            )
            driver = TouchDesignerDriver(ctx)
            attached = await driver._attach_if_running()
            await driver.shutdown()
            return attached, driver._attached
        finally:
            await fake_controller.stop()

    attached, still_attached = asyncio.run(scenario())
    assert attached is True
    # shutdown() resets the flag; no process was launched or killed
    assert still_attached is False

def test_launch_passes_only_the_project_path(tmp_path, monkeypatch):
    """TouchDesigner exits on any argument it does not know ('-quiet' on
    2025.33230), so the launch line is the binary, any caller flags, and
    the toe — nothing else."""
    td = tmp_path / "TouchDesigner"
    toe = tmp_path / "transcoder.toe"
    td.write_text("")
    toe.write_text("")
    seen = {}

    async def fake_exec(*args, **kwargs):
        seen["args"] = list(args)
        seen["env"] = kwargs.get("env") or {}
        return object()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    ctx = DriverContext(workdir=tmp_path, td_path=td, toe_path=toe,
                        td_flags=["-n", "1"])
    asyncio.run(TouchDesignerDriver(ctx)._launch_td())

    assert seen["args"] == [str(td), "-n", "1", str(toe)]
    assert seen["env"].get("VCON_LAUNCHED") == "1"
