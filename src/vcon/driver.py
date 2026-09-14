"""Driver interface: the backend boundary.

A Driver takes a *run* — a set of validated jobs sharing one backend session
(one TouchDesigner launch, or one mock pass) — executes them, reports
progress, and returns. Drivers receive resolved parameters and emit protocol
messages; they do not know about codecs, the registry, or the CLI.

This is the seam that makes mock/TouchDesigner/future-APT interchangeable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from vcon.models import Job

#: Callback drivers call with every decoded controller message:
#:   on_msg(dict)  — {"type": "accepted"|"progress"|"done"|"error", ...}
OnMessage = Callable[[dict[str, Any]], None]


@dataclass
class DriverContext:
    """Everything a driver may need, injected by the caller."""

    #: Directory for driver scratch (logs, temp).
    workdir: Path
    #: Path to the TouchDesigner executable (TD-family drivers only).
    td_path: Path | None = None
    #: Path to the transcoder toe, if the driver needs one.
    toe_path: Path | None = None
    #: TCP port for the JSON-lines protocol (TD-family drivers).
    port: int = 7999
    #: Extra flags forwarded to the TD executable.
    td_flags: list[str] = field(default_factory=list)
    #: Kill the backend if it produces no message for this many seconds.
    #: Applies per job, not per batch. Generous enough for large files,
    #: short enough that a wedged controller doesn't look like a hang.
    watchdog_timeout: float = 120.0
    #: Simulated failure injected by the mock driver (test seam).
    fail_on_job: str | None = None
    #: Extra driver-specific knobs (kept open for future drivers).
    extra: dict[str, Any] = field(default_factory=dict)


class Driver(ABC):
    """Backend contract: run jobs, report messages, clean up."""

    def __init__(self, ctx: DriverContext) -> None:
        self.ctx = ctx
        self._on_msg: OnMessage | None = None
        self._completion_hook = None

    def set_on_message(self, fn: OnMessage) -> None:
        """Install the callback that receives controller messages."""
        self._on_msg = fn

    def set_completion_hook(self, fn) -> None:
        """Install a poll callback ``(job_id) -> bool`` for job completion.

        The TouchDesigner driver uses this to keep its submit stream strictly
        sequential (wait for done/error before sending the next submit)."""
        self._completion_hook = fn

    # Helpers ----------------------------------------------------------

    def _emit(self, msg: dict[str, Any]) -> None:
        if self._on_msg is not None:
            self._on_msg(msg)

    def _emit_simple(self, job_id: str, type_: str, **fields: Any) -> None:
        msg: dict[str, Any] = {"type": type_, "id": job_id}
        msg.update(fields)
        self._emit(msg)

    # Contract ---------------------------------------------------------

    @abstractmethod
    async def run(self, jobs: list[Job]) -> None:
        """Encode every job; call ``_emit_simple``-style messages as you go.

        Implementations must:

        - emit ``accepted`` (with total_frames) before the first ``progress``
        - emit ``done`` or ``error`` for every job, even on failure
        - not raise for per-job failures; reserve exceptions for backend death
        """
        raise NotImplementedError

    @abstractmethod
    async def shutdown(self) -> None:
        """Release the backend session (terminate process, close sockets)."""
        raise NotImplementedError