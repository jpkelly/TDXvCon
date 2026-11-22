"""TouchDesignerDriver — spawn the toe, speak JSON-lines over TCP.

Responsibilities:

1. Find/launch the TouchDesigner binary with ``transcoder.toe``.
2. Connect to the toe's TCP listener (it sends ``hello`` on ready).
3. Stream ``submit`` messages for each job; relay controller messages back
   through the driver callback.
4. Watchdog: if the controller goes silent mid-job, fail loudly rather than
   hang forever.
5. On completion (or fatal error) terminate the TD process and clean up.

Phase-1 note: this module is fully implemented and unit-tested against a
*fake controller server* (see tests/test_td_driver.py), because the real
``transcoder.toe`` arrives in phase 2. The wire behavior it exercises is the
contract the toe must implement.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from vcon.config import find_touchdesigner, resolve_toe_path
from vcon.driver import Driver, DriverContext
from vcon.models import Job
from vcon.protocol import (
    Cancel,
    MAX_LINE,
    PROTOCOL_PORT,
    Submit,
    decode_msg,
    encode_msg,
    is_hello,
    make_hello,
)


class TDProcessError(Exception):
    """The TouchDesigner process died or never became ready."""


class TouchDesignerDriver(Driver):
    def __init__(self, ctx: DriverContext) -> None:
        super().__init__(ctx)
        self._proc: asyncio.subprocess.Process | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._hello: asyncio.Future[None] | None = None
        #: True when we connected to a controller we did NOT start.
        self._attached = False
        #: Version string reported by the controller's hello, if it sent one.
        self.controller_version: str | None = None

    def _hello_future(self) -> asyncio.Future[None]:
        """Create the hello future lazily so it belongs to the running loop."""
        if self._hello is None:
            self._hello = asyncio.get_running_loop().create_future()
        return self._hello

    # ------------------------------------------------------------------
    # Process + connection
    # ------------------------------------------------------------------

    async def run(self, jobs: list[Job]) -> None:
        try:
            if not jobs:
                return  # nothing to do; never launch TD for empty batches
            # If a controller is ALREADY listening (e.g. the user has TD open
            # with the toe loaded), attach to it — spawning a second instance
            # would fight over port 7999 and leave an orphan process. We then
            # do not own that process and must not terminate it on exit.
            if not await self._attach_if_running():
                await self._launch_td()
            await self._start_session()
            await self._hello_future()
            await self._drive(jobs)
        finally:
            await self.shutdown()

    async def _attach_if_running(self) -> bool:
        """Try once to connect to an existing controller. True if attached."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", self.ctx.port), timeout=1.0
            )
        except (OSError, asyncio.TimeoutError):
            return False
        self._attached = True
        return True

    async def _start_session(self) -> None:
        """Connect to the controller and start consuming its messages.

        The socket reader MUST be running before anything awaits the hello
        handshake — otherwise the handshake line sits unread in the kernel
        buffer and every awaiter deadlocks. Tests use this same entry point
        to skip _launch_td (no TouchDesigner install needed).
        """
        if self._reader is None:
            await self._connect_with_retry()
        if self._reader_task is None:
            self._reader_task = asyncio.create_task(self._read_loop())

    async def _launch_td(self) -> None:
        td = self.ctx.td_path or find_touchdesigner()
        if td is None:
            raise TDProcessError(
                "TouchDesigner not found — pass -td-path or set VCON_TDPATH"
            )
        toe = self.ctx.toe_path or resolve_toe_path()
        if not toe.exists():
            raise TDProcessError(
                f"transcoder.toe not found at {toe} — rebuild it by running "
                f"toe/build_network.py inside TouchDesigner"
            )

        # Pass the project path and nothing else. TouchDesigner treats any
        # argument it does not know as fatal: it shows an "unknown argument"
        # dialog and exits, so vCon sees TD quit before opening its port.
        # TD 2025.33230 rejects '-quiet' that way (vCon passed it until
        # 1.0.0, so the CLI could never launch TD itself), and no build has
        # a '-perform' switch: Perform Mode is a project setting (Window
        # COMP → Start in Perform Mode); the toe handles its own windowing.
        args: list[str] = [str(td)]
        args += list(self.ctx.td_flags)   # extra flags, caller-controlled
        args.append(str(toe))

        creationflags = 0x08000000 if sys.platform.startswith("win") else 0

        # Mark the process as vCon-launched. The controller checks this to
        # arm its orphan cleanup — if this driver dies (SIGKILL, crash), the
        # spawned TD quits itself after the idle timeout instead of holding
        # port 7999 forever. A TD the USER opened themselves lacks the
        # variable and can never be quit by vCon. Process provenance, not
        # a preference — this is the sole reason the toggle-free design works.
        launch_env = dict(os.environ)
        launch_env["VCON_LAUNCHED"] = "1"

        self._proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=launch_env,
            creationflags=creationflags,
        )
        # NOTE: intentionally NOT awaiting proc.wait() here — the process
        # must stay alive for the whole session; readiness is signaled by
        # the controller opening its TCP listener (see _connect_with_retry).

    async def _connect_with_retry(self) -> None:
        """The toe opens its TCP listener during startup; retry for ~15s."""
        host, port = "127.0.0.1", self.ctx.port
        deadline = asyncio.get_event_loop().time() + 15.0
        last_err: Exception | None = None
        while asyncio.get_event_loop().time() < deadline:
            if self._proc is not None and self._proc.returncode is not None:
                raise TDProcessError(
                    f"TouchDesigner exited before opening port {port} "
                    f"(code {self._proc.returncode})"
                )
            try:
                self._reader, self._writer = await asyncio.open_connection(host, port)
                return
            except OSError as exc:
                last_err = exc
                await asyncio.sleep(0.25)
        raise TDProcessError(f"could not connect to controller at {host}:{port} ({last_err})")

    # ------------------------------------------------------------------
    # Reader loop
    # ------------------------------------------------------------------

    async def _read_loop(self) -> None:
        """Consume controller lines → decode → emit; resolves the hello future."""
        assert self._reader is not None
        try:
            while True:
                raw = await asyncio.wait_for(self._reader.readline(), timeout=self.ctx.watchdog_timeout)
                if not raw:
                    break
                if len(raw) > MAX_LINE:
                    raise TDProcessError("oversized line from controller")
                msg = decode_msg(raw)
                if is_hello(msg):
                    self.controller_version = msg.get("controller_version")
                    fut = self._hello_future()
                    if not fut.done():
                        fut.set_result(None)
                    continue
                self._emit(msg)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError) as exc:
            raise TDProcessError(f"controller went silent: {exc}") from exc
        finally:
            fut = self._hello
            if fut is not None and not fut.done():
                fut.set_exception(TDProcessError("controller closed before hello"))

    # ------------------------------------------------------------------
    # Driving jobs
    # ------------------------------------------------------------------

    async def _drive(self, jobs: list[Job]) -> None:
        """Stream submits strictly sequentially, awaiting each completion."""
        assert self._writer is not None
        try:
            for job in jobs:
                # The toe encodes strictly sequentially; no pipelining.
                params = job.spec.extra.get("td_params")
                if not isinstance(params, dict):
                    params = {}
                msg = Submit(
                    job_id=job.id,
                    input=str(job.spec.input.resolve()),
                    output=str(job.spec.output.resolve()),
                    params=params,
                )
                self._writer.write(encode_msg(msg))
                await self._writer.drain()
                # Wait for done/error before the next submit — keeps the
                # wire strictly sequential (the toe encodes one at a time).
                try:
                    await self._await_completion(job.id)
                except asyncio.CancelledError:
                    await self._cancel_in_td(job.id)
                    raise
        except (ConnectionError, BrokenPipeError) as exc:
            raise TDProcessError(f"controller connection lost: {exc}") from exc

    async def _cancel_in_td(self, job_id: str, wait: float = 2.0) -> None:
        """Ctrl-C: cancel the running job in TouchDesigner as well.

        Otherwise the controller kept encoding after vcon exited and moved
        the finished file to the output name, unseen. A cancelled job
        deletes its .partial recording, so give the controller a moment to
        acknowledge before the driver shuts down (and, if it launched TD,
        terminates it). Best effort: the connection may already be gone.
        """
        try:
            assert self._writer is not None
            self._writer.write(encode_msg(Cancel(job_id=job_id)))
            await asyncio.wait_for(self._writer.drain(), timeout=1.0)
            loop = asyncio.get_running_loop()
            deadline = loop.time() + wait
            while loop.time() < deadline:
                if self._completion_hook is not None and self._completion_hook(job_id):
                    return
                await asyncio.sleep(0.02)
        except Exception:  # noqa: BLE001 — shutting down either way
            pass

    async def _await_completion(self, job_id: str) -> None:
        """Poll the completion hook until the job is terminal, or watchdog."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.ctx.watchdog_timeout
        while loop.time() < deadline:
            if self._completion_hook is not None and self._completion_hook(job_id):
                return
            await asyncio.sleep(0.01)
        raise TDProcessError(
            f"watchdog: job {job_id} did not complete in "
            f"{self.ctx.watchdog_timeout:.0f}s"
        )

    async def shutdown(self) -> None:
        """Terminate TD and close the socket; safe to call twice."""
        task = self._reader_task
        self._reader_task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except BaseException:
                pass  # cancelled, or died with TDProcessError — either is fine
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except (ConnectionError, OSError):
                pass
            self._writer = None
        proc = self._proc
        self._proc = None
        # Only terminate TouchDesigner if WE launched it. When we attached to
        # a user's already-running session, leaving it alone is correct.
        if proc is not None and proc.returncode is None and not self._attached:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except TimeoutError:
                proc.kill()
        self._attached = False
        fut = self._hello
        if fut is not None and not fut.done():
            fut.set_exception(TDProcessError("shut down before hello"))