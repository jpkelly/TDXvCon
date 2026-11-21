"""Transcoder — the orchestrator the CLI (and future GUI) talks to.

Wires queue + driver together and runs one *batch* to completion:

    t = Transcoder(options)
    t.add(spec)  # or many
    await t.run()

Emits the full event stream on its bus. The CLI subscribes and renders; a
future GUI subscribes and renders. The core never prints.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vcon.config import Config
from vcon.driver import Driver, DriverContext
from vcon.errors import DriverError
from vcon.events import EventBus
from vcon.mock_driver import MockDriver
from vcon.models import Job, JobSpec, JobStatus
from vcon.queue_manager import QueueManager, QueueOptions
from vcon.registry import Registry
from vcon.td_driver import TouchDesignerDriver


@dataclass
class TranscoderOptions:
    """Everything the orchestrator needs, minus the jobs themselves."""

    backend: str = "touchdesigner"  # "touchdesigner" | "mock"
    workdir: Path = field(default_factory=lambda: Path.cwd() / ".vcon")
    td_path: Path | None = None
    toe_path: Path | None = None
    port: int = 7999
    watchdog_timeout: float = 120.0
    state_path: Path | None = None
    fail_fast: bool = False  # stop the batch on first job error (like ffmpeg)
    config: Config | None = None


_DRIVER_BACKENDS = {"touchdesigner": TouchDesignerDriver, "mock": MockDriver}


def _make_driver(opts: TranscoderOptions, ctx: DriverContext) -> Driver:
    try:
        cls = _DRIVER_BACKENDS[opts.backend]
    except KeyError:
        raise DriverError(f"unknown backend {opts.backend!r}") from None
    return cls(ctx)


class Transcoder:
    """One-shot batch runner over the queue + a driver backend."""

    def __init__(self, options: TranscoderOptions | None = None) -> None:
        self.options = options or TranscoderOptions()
        self.bus = EventBus()
        self.registry = Registry()
        self.queue = QueueManager(
            self.bus,
            registry=self.registry,
            options=QueueOptions(state_path=self.options.state_path),
        )
        self._specs: list[JobSpec] = []

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def add(self, spec: JobSpec) -> Job:
        """Validate + queue one output spec (may raise before anything starts)."""
        return self.queue.submit(spec)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def run(self) -> int:
        """Run all queued jobs to completion; returns process exit code.

        0 = everything encoded; 1 = one or more jobs failed; 2 = backend died
        (nothing can be trusted after that); 3 = everything encoded, but at
        least one output fell short of the request (job warnings, e.g. the
        audio mux failed and the file is video-only).
        """
        jobs = [j for j in self.queue.jobs if not j.is_terminal]
        if not jobs:
            self.bus.queue_idle()
            return 0

        ctx = DriverContext(
            workdir=self.options.workdir,
            td_path=self.options.td_path,
            toe_path=self.options.toe_path,
            port=self.options.port,
            watchdog_timeout=self.options.watchdog_timeout,
        )
        driver = _make_driver(self.options, ctx)
        driver.set_on_message(self.queue.handle_message)
        # TD driver polls this to keep submits strictly sequential.
        if hasattr(driver, "set_completion_hook"):
            driver.set_completion_hook(
                lambda jid: (job := self.queue.job(jid)) is not None
                and (job.is_terminal or self.queue.job(jid).status == "cancelled")
            )

        started = time.time()
        try:
            await driver.run(jobs)
        except Exception as exc:  # backend death — fail everything pending
            for job in jobs:
                if not job.is_terminal:
                    job.status = JobStatus.FAILED
                    job.error = f"backend failure: {exc}"
                    self.bus.job_event(
                        "job_error", job.id, message=job.error, code="backend-dead"
                    )
            self.bus.log("error", f"backend failed: {exc}")
            self.bus.queue_idle()
            return 2
        finally:
            await driver.shutdown()

        self.bus.log(
            "info",
            f"batch finished in {time.time() - started:.1f}s — "
            + ", ".join(f"{k}={v}" for k, v in self.queue.counts().items() if v),
        )
        self.bus.queue_idle()
        if self.queue.failed_jobs():
            return 1
        return 3 if self.queue.warned_jobs() else 0

    # ------------------------------------------------------------------
    # Introspection (GUI seam)
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        return self.queue.snapshot()

    def results(self) -> list[dict[str, Any]]:
        """Terminal-state summary rows, in submission order."""
        return [
            {
                "id": j.id,
                "status": j.status,
                "output": str(j.spec.output),
                "error": j.error,
            }
            for j in self.queue.jobs
        ]