"""Event bus: subscription fan-out, job vocabulary guard, snapshot shapes."""

from __future__ import annotations

import pytest

from vcon.events import QUEUE_IDLE, Event, EventBus, status_of_event
from vcon.models import JobStatus


def test_subscribe_and_emit():
    bus = EventBus()
    seen = []
    bus.subscribe("job_started", lambda e: seen.append(e.type))
    bus.job_event("job_started", "j1", total_frames=10)
    assert seen == ["job_started"]


def test_wildcard_subscriber_gets_everything():
    bus = EventBus()
    seen = []
    bus.subscribe("*", lambda e: seen.append(e.type))
    bus.job_event("job_submitted", "j1")
    bus.queue_idle()
    assert seen == ["job_submitted", QUEUE_IDLE]


def test_subscribe_jobs_covers_lifecycle():
    bus = EventBus()
    seen = []
    bus.subscribe_jobs(lambda e: seen.append(e.type))
    for t in ("job_submitted", "job_started", "job_progress", "job_done"):
        bus.job_event(t, "j1")
    bus.job_event("job_error", "j2")
    assert seen == [
        "job_submitted", "job_started", "job_progress", "job_done", "job_error",
    ]


def test_unknown_job_event_rejected():
    bus = EventBus()
    with pytest.raises(ValueError, match="unknown job event"):
        bus.job_event("job_exploded", "j1")


def test_event_payload_and_serialization():
    bus = EventBus()
    captured = []
    bus.subscribe("job_progress", captured.append)
    bus.job_event("job_progress", "j1", frame=5, total_frames=10)
    ev = captured[0]
    assert ev.job_id == "j1"
    assert ev.data == {"frame": 5, "total_frames": 10}
    d = ev.as_dict()
    assert d["type"] == "job_progress"
    assert d["data"]["frame"] == 5


def test_status_of_event_mapping():
    assert status_of_event("job_submitted") == JobStatus.QUEUED
    assert status_of_event("job_started") == JobStatus.RUNNING
    assert status_of_event("job_done") == JobStatus.DONE
    assert status_of_event("job_error") == JobStatus.FAILED


def test_log_events_flow():
    bus = EventBus()
    msgs = []
    bus.subscribe("log", lambda e: msgs.append(e.data["message"]))
    bus.log("info", "hello")
    assert msgs == ["hello"]