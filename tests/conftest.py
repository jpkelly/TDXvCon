"""Shared test fixtures."""

from __future__ import annotations

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