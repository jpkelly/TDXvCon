"""QueueManager — owns job lifecycle, validation, and state snapshots.

Pure orchestration: it knows nothing about TouchDesigner or the mock. The
Transcoder hands it validated jobs; the driver's protocol messages flow back
through ``handle_message`` and become bus events + job state updates.

State is queryable at any time via :meth:`snapshot` — the seam a future GUI
renders from.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vcon.errors import InputError, OutputError
from vcon.events import EventBus
from vcon.models import Job, JobSpec, JobStatus
from vcon.registry import Registry


@dataclass
class QueueOptions:
    """Behavior knobs (defaults are the product decisions)."""

    #: Refuse to overwrite existing outputs (ffmpeg -n).
    no_overwrite: bool = False
    #: Overwrite without prompting (ffmpeg -y). Implied in non-TTY contexts.
    yes: bool = False
    #: Where to persist a crash-resume state file (None → in-memory only).
    state_path: Path | None = None


class QueueManager:
    """Job registry + lifecycle. Not thread-safe; single event loop owns it."""

    def __init__(
        self,
        bus: EventBus,
        registry: Registry | None = None,
        options: QueueOptions | None = None,
    ) -> None:
        self.bus = bus
        self.registry = registry or Registry()
        self.options = options or QueueOptions()
        self._jobs: dict[str, Job] = {}
        self._next_id = 1
        self._state: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------

    def submit(self, spec: JobSpec, *, job_id: str | None = None) -> Job:
        """Validate a spec and admit it to the queue.

        Raises InputError/OutputError/CodecError before anything is queued —
        fail fast on the CLI's side of the wire.
        """
        spec.validate_paths()

        codec = self.registry.get(spec.codec)
        # Validate codec grammar (subtype/quality) — these raise CodecError
        # on junk values; defaults are validated too so registry changes
        # can't silently admit an unknown default.
        codec.resolve_subtype(spec.subtype)
        codec.resolve_quality(spec.quality)  # strict: None → default resolved later

        if spec.fps != "auto" and not spec.fps.replace(".", "", 1).isdigit():
            raise InputError(f"invalid fps {spec.fps!r} (expected 'auto' or a number)")

        if self.options.no_overwrite and spec.output.exists():
            raise OutputError(
                f"output exists and -n was given: {spec.output}"
            )
        if not self.options.no_overwrite and not self.options.yes and spec.output.exists():
            raise OutputError(
                f"output exists: {spec.output} (use -y to overwrite, -n to abort)"
            )
        job_id = job_id or self._mint_id()
        # Bake the registry-resolved Movie File Out parameters into the spec
        # so the driver can forward them verbatim. The toe has no codec
        # knowledge — without this the params dict would be empty.
        spec.extra["td_params"] = codec.td_params(
            subtype=spec.subtype,
            quality=spec.quality,
            fps=spec.fps,
            alpha=spec.alpha,
            resolution=spec.resolution,
            fit=spec.fit,
        )
        job = Job(spec=spec, id=job_id)
        self._jobs[job_id] = job
        self.bus.job_event(
            "job_submitted",
            job_id,
            output=str(spec.output),
            codec=spec.codec,
            position=len(self._jobs),
        )
        self._persist()
        return job

    def _mint_id(self) -> str:
        jid = f"j{self._next_id}"
        self._next_id += 1
        return jid

    # ------------------------------------------------------------------
    # Lifecycle (driver messages → events + state)
    # ------------------------------------------------------------------

    def handle_message(self, msg: dict[str, Any]) -> None:
        """Feed one decoded protocol message into the queue state.

        Unknown message types are ignored (forward compatibility), except they
        are surfaced as debug logs.
        """
        mtype = msg.get("type")
        jid = msg.get("id")

        if mtype == "hello":
            self.bus.log("debug", f"controller hello v{msg.get('version')}")
            return

        if mtype not in ("accepted", "progress", "done", "error"):
            self.bus.log("debug", f"ignoring message type {mtype!r}")
            return

        if jid not in self._jobs:
            self.bus.log("warning", f"message for unknown job {jid!r}")
            return

        job = self._jobs[jid]

        if mtype == "accepted":
            job.total_frames = int(msg.get("total_frames", 0)) or None
            job.status = JobStatus.RUNNING
            job.started_at = time.time()
            self.bus.job_event("job_started", jid, input=str(job.spec.input),
                               total_frames=job.total_frames or 0)
        elif mtype == "progress":
            job.progress_frame = int(msg.get("frame", job.progress_frame))
            if msg.get("total_frames"):
                job.total_frames = int(msg["total_frames"])
            self.bus.job_event(
                "job_progress", jid, frame=job.progress_frame,
                total_frames=job.total_frames or 0,
            )
        elif mtype == "done":
            job.status = JobStatus.DONE
            job.progress_frame = job.total_frames or job.progress_frame
            job.finished_at = time.time()
            # Verify the output is actually in the requested codec. TD menu
            # parameters silently fall back to entry 0 on a bad value, which
            # yields a valid file in the WRONG codec with no error anywhere.
            job.verified, job.verify_note = self._verify_output(job)
            if not job.verified:
                job.status = JobStatus.FAILED
                job.error = job.verify_note
                self.bus.job_event("job_error", jid, message=job.verify_note,
                                   code="codec-mismatch")
                self._persist()
                return
            self.bus.job_event(
                "job_done", jid, output=str(job.spec.output),
                total_frames=job.total_frames or 0,
                seconds=float(msg.get("seconds", 0.0)) or None,
                codec_note=job.verify_note,
            )
        elif mtype == "error":
            job.status = JobStatus.FAILED
            job.error = str(msg.get("message", "unknown error"))
            job.finished_at = time.time()
            self.bus.job_event(
                "job_error", jid, message=job.error,
                code=str(msg.get("code", "driver-error")),
            )
        self._persist()

    # ------------------------------------------------------------------
    # Output verification
    # ------------------------------------------------------------------

    def _verify_output(self, job: Job) -> tuple[bool, str]:
        """Confirm the encoded file is really in the requested codec.

        Uses a real atom-level probe rather than trusting the request —
        TouchDesigner falls back to menu entry 0 for an unrecognised
        videocodec value and reports no error.

        Checks against the codec the user ASKED for; a hardcoded NotchLC
        check would flag every valid ProRes/Hap job as a failure.
        """
        from vcon.codec_probe import fourccs_for_codec, verify_output

        name = job.spec.codec
        expect = fourccs_for_codec(name)
        # A couple of retries: TouchDesigner writes the moov index at file
        # close, which on a big encode can still be flushing when 'done'
        # arrives. Without this we raced a 45 GB ProRes file and reported a
        # false failure on a perfectly good output.
        if expect is None:
            return verify_output(job.spec.output, expect_notchlc=False,
                                 retries=3, retry_delay=0.2)
        return verify_output(
            job.spec.output,
            expect_notchlc=(name == "notchlc"),
            expect_fourccs=expect,
            retries=3,
            retry_delay=0.2,
        )

    # ------------------------------------------------------------------
    # State API (future GUI renders from this)
    # ------------------------------------------------------------------

    @property
    def jobs(self) -> list[Job]:
        return list(self._jobs.values())

    def job(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def snapshot(self) -> dict[str, Any]:
        """Full serializable queue state."""
        return {
            "jobs": [j.as_dict() for j in self._jobs.values()],
            "counts": self.counts(),
        }

    def counts(self) -> dict[str, int]:
        c = {s: 0 for s in JobStatus.ALL}
        for j in self._jobs.values():
            c[j.status] += 1
        return c

    def has_pending(self) -> bool:
        return any(not j.is_terminal for j in self._jobs.values())

    def failed_jobs(self) -> list[Job]:
        return [j for j in self._jobs.values() if j.status == JobStatus.FAILED]

    # ------------------------------------------------------------------
    # Persistence (crash resume — cheap insurance, ffmpeg-free)
    # ------------------------------------------------------------------

    def _persist(self) -> None:
        if self.options.state_path is None:
            return
        import json

        data = {"version": 1, "jobs": [j.as_dict() for j in self._jobs.values()]}
        try:
            self.options.state_path.write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
        except OSError:
            pass  # state persistence is best-effort
