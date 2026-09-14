"""MockDriver: message stream shape, output materialization, failure injection."""

from __future__ import annotations

import asyncio

import pytest

from vcon.driver import DriverContext
from vcon.mock_driver import MockDriver, make_mock_context
from vcon.queue_manager import QueueManager


async def _run_with_queue(jobs_ctx, specs, **ctx_extra):
    """Run mock driver + queue together; returns (queue, messages)."""
    from vcon.events import EventBus
    from vcon.registry import Registry

    bus = EventBus()
    queue = QueueManager(bus, registry=Registry())
    jobs = [queue.submit(s) for s in specs]

    driver = MockDriver(make_mock_context(jobs_ctx["workdir"], **ctx_extra))
    messages = []
    driver.set_on_message(lambda m: messages.append(m))
    await driver.run(jobs)
    await driver.shutdown()
    return queue, messages


@pytest.fixture
def jobs_ctx(tmp_path):
    return {"workdir": tmp_path}


def test_mock_stream_shape(sample_spec, jobs_ctx):
    queue, messages = asyncio.run(
        _run_with_queue(jobs_ctx, [sample_spec], sleep=0.0)
    )
    types = [m["type"] for m in messages]
    assert types[0] == "hello"
    assert types[1] == "accepted"
    assert "progress" in types
    assert types[-1] == "done"


def test_mock_writes_output_file(sample_spec, jobs_ctx):
    queue, messages = asyncio.run(_run_with_queue(jobs_ctx, [sample_spec], sleep=0.0))
    assert sample_spec.output.exists()
    # The mock emits a minimal QuickTime container whose stsd fourcc reads as
    # NotchLC, so the pipeline's real codec verification is exercised too.
    from vcon.codec_probe import probe_codec

    info = probe_codec(sample_spec.output)
    assert info is not None and info.is_notchlc


def test_mock_progress_monotonic(sample_spec, jobs_ctx):
    _, messages = asyncio.run(_run_with_queue(jobs_ctx, [sample_spec], sleep=0.0))
    frames = [m["frame"] for m in messages if m["type"] == "progress"]
    assert frames == sorted(frames)
    assert frames[0] == 1
    total = [m for m in messages if m["type"] == "accepted"][0]["total_frames"]
    assert frames[-1] == total


def test_mock_multi_output_sequential(sample_input, jobs_ctx, tmp_path):
    from vcon.models import JobSpec

    specs = [
        JobSpec(input=sample_input, output=tmp_path / f"out{i}.nlc.mov")
        for i in range(3)
    ]
    queue, messages = asyncio.run(_run_with_queue(jobs_ctx, specs, sleep=0.0))
    dones = [m for m in messages if m["type"] == "done"]
    assert len(dones) == 3
    for i in range(3):
        assert (tmp_path / f"out{i}.nlc.mov").exists()


def test_mock_fail_injection(sample_spec, jobs_ctx):
    queue, messages = asyncio.run(
        _run_with_queue(jobs_ctx, [sample_spec], sleep=0.0, fail_on_job="j1")
    )
    # The injected job errors instead of encoding.
    assert messages[-1]["type"] == "error"
    assert messages[-1]["code"] == "mock-injected"
    assert not sample_spec.output.exists()


def test_make_mock_context_builder(tmp_path):
    ctx = make_mock_context(tmp_path, sleep=0.1)
    assert ctx.workdir == tmp_path
    assert ctx.extra["sleep"] == 0.1


def test_mock_cancel_path(sample_spec, jobs_ctx):
    async def scenario():
        from vcon.events import EventBus
        from vcon.registry import Registry

        bus = EventBus()
        queue = QueueManager(bus, registry=Registry())
        job = queue.submit(sample_spec)
        driver = MockDriver(make_mock_context(jobs_ctx["workdir"], sleep=0.0))
        await driver.cancel(job.id)
        messages = []
        driver.set_on_message(lambda m: messages.append(m))
        await driver.run([job])
        await driver.shutdown()
        return messages

    messages = asyncio.run(scenario())
    err = [m for m in messages if m["type"] == "error"]
    assert err and err[0]["code"] == "cancelled"