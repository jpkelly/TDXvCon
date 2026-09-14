"""Typed event bus.

The core *never* prints. It emits typed events; frontends (CLI today, GUI or
daemon later) subscribe and render. The event vocabulary mirrors the wire
protocol messages from the TouchDesigner controller so events can pass through
unchanged.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from vcon.models import JobStatus

# Events that carry a job id, in wire vocabulary. (job_submitted / job_started /
# job_progress / job_done / job_error mirror the TD controller's messages.)
_JOB_EVENTS = ("job_submitted", "job_started", "job_progress", "job_done", "job_error")

#: Emitted once all queued jobs have reached a terminal state.
QUEUE_IDLE = "queue_idle"

#: Diagnostic chatter (never user-visible unless -loglevel debug).
LOG = "log"


@dataclass(frozen=True)
class Event:
    """A single immutable event emitted by the core.

    ``data`` payloads per type::

        job_submitted  {output, codec, position}
        job_started    {input, total_frames}
        job_progress   {frame, total_frames}
        job_done       {output, total_frames, seconds}
        job_error      {message, code, recoverable}
        queue_idle     {}
        log            {level, message}
    """

    type: str
    job_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict[str, Any]:
        """Serializable form (for tests, logging, future daemon wire format)."""
        return {
            "type": self.type,
            "job_id": self.job_id,
            "data": self.data,
            "ts": self.ts.isoformat(),
        }


Subscriber = Callable[[Event], None]


class EventBus:
    """Minimal synchronous pub/sub."""

    def __init__(self) -> None:
        self._subs: dict[str, list[Subscriber]] = {}

    def subscribe(self, event_type: str, fn: Subscriber) -> None:
        """Register ``fn`` for events of ``event_type`` (or "job" for all)."""
        self._subs.setdefault(event_type, []).append(fn)

    def emit(self, event: Event) -> None:
        """Notify subscribers for the event type and "*" (all)."""
        for fn in self._subs.get(event.type, ()):
            fn(event)
        for fn in self._subs.get("*", ()):
            fn(event)

    # Convenience factory -----------------------------------------------

    def job_event(self, event_type: str, job_id: str, **data: Any) -> None:
        """Emit a job-lifecycle event. Asserts vocabulary for safety."""
        if event_type not in _JOB_EVENTS:
            raise ValueError(f"unknown job event type: {event_type}")
        self.emit(Event(event_type, job_id=job_id, data=dict(data)))

    def queue_idle(self) -> None:
        self.emit(Event(QUEUE_IDLE))

    def log(self, level: str, message: str) -> None:
        self.emit(Event(LOG, data={"level": level, "message": message}))

    def subscribe_jobs(self, fn: Subscriber) -> None:
        """Subscribe to every job-lifecycle event."""
        for t in _JOB_EVENTS:
            self.subscribe(t, fn)


def log_to_stderr(
    bus: EventBus, *, level: str = "info", prefix: str = "[vcon]"
) -> None:
    """Developer convenience: dump all events to stderr (like -loglevel debug)."""
    order = {"debug": 0, "info": 1, "warning": 2, "error": 3, "quiet": 99}
    if order.get(level, 1) > 1:
        return

    def _print(event: Event) -> None:
        if event.type == LOG:
            if order.get(event.data.get("level", "info"), 1) <= order.get(level, 1):
                print(f"{prefix} {event.data['message']}", file=sys.stderr)
        else:
            print(f"{prefix} {event.type} {event.as_dict()}", file=sys.stderr)

    bus.subscribe("*", _print)


def status_of_event(event_type: str) -> JobStatus:
    """Map a lifecycle event to the job status it represents."""
    return {
        "job_submitted": JobStatus.QUEUED,
        "job_started": JobStatus.RUNNING,
        "job_done": JobStatus.DONE,
        "job_error": JobStatus.FAILED,
    }[event_type]