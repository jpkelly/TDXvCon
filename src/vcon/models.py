"""Job models.

A *spec* is the user's request (input file + codec settings). A *job* is a
spec that has entered the queue, been validated against the codec registry,
and carries a runtime status.

JobSpec / Job are both serializable: the wire protocol round-trips them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vcon.errors import InputError, OutputError


class JobStatus:
    """String constants (serializes trivially, no enum ceremony)."""

    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"

    ALL = (QUEUED, RUNNING, DONE, FAILED, CANCELLED)


#: Fit TOP's ACTUAL menu tokens — live-verified by build_network.py on
#: JP's TD (the docs' labels 'stretch'/'fit width' etc. do NOT exist):
#:   ['fill', 'fithorz', 'fitvert', 'fitbest', 'fitoutside', 'nativeres']
FIT_MODES = ("fill", "fithorz", "fitvert", "fitbest", "fitoutside")

#: Friendlier spellings accepted on the CLI and normalized to TD tokens.
FIT_ALIASES = {
    "stretch": "fill",
    "fitwidth": "fithorz",
    "width": "fithorz",
    "fitheight": "fitvert",
    "height": "fitvert",
    "best": "fitbest",
    "cover": "fitoutside",
    "crop": "fitoutside",
}


def normalize_fit(value: str | None) -> str:
    """Resolve a fit-mode spelling to TD's Fit TOP menu token.

    Raises InputError listing the valid modes for anything unknown —
    a bad token on the toe would silently fall back to menu entry 0.
    """
    v = (value or "fitbest").strip().lower()
    if v in FIT_MODES:
        return v
    if v in FIT_ALIASES:
        return FIT_ALIASES[v]
    raise InputError(
        f"invalid fit mode {value!r} — one of "
        f"{', '.join(FIT_MODES)} (or aliases: "
        f"{', '.join(sorted(FIT_ALIASES))})"
    )


def _default_output_for(input_path: Path, codec: str) -> Path:
    """``video.mov`` + notchlc → ``video.nlc.mov`` (sibling of the input)."""
    stem = input_path.stem
    return input_path.with_name(f"{stem}.{codec}.mov")


@dataclass
class JobSpec:
    """A user request for one output file.

    Exactly one output per JobSpec — multiple outputs means multiple specs
    (the CLI builds one spec per ``-c ... out`` group, like ffmpeg).
    """

    input: Path
    output: Path
    codec: str = "notchlc"
    subtype: str | None = None
    quality: str | None = None  # None → codec default (notchlc: optimal)
    fps: str = "auto"  # "auto" = follow source
    alpha: bool | None = None  # None = follow source; False forces off
    #: "auto" keeps the source resolution; "1920x1080" sets a custom one.
    #: Applied by the toe via a Fit TOP between moviein and movieout.
    resolution: str = "auto"
    #: How a custom resolution rescales — TD's Fit TOP menu tokens
    #: (LIVE-VERIFIED by the builder, not the docs' labels):
    #: fill | fithorz | fitvert | fitbest | fitoutside. Default fitbest is
    #: the non-destructive choice (aspect preserved, letterboxed); aliases
    #: like stretch/cover/best are normalized by normalize_fit().
    fit: str = "fitbest"
    extra: dict[str, Any] = field(default_factory=dict)  # per-codec baggage

    def resolved_quality(self, default_quality: str | None) -> str:
        return self.quality or default_quality or "optimal"

    def validate_paths(self) -> None:
        """Filesystem checks the CLI performs before queueing.

        Codec-level checks (registry) happen in :class:`vcon.queue_manager.QueueManager`;
        these are the cheap early exits.
        """
        if not self.input.exists():
            raise InputError(f"input file not found: {self.input}")
        if not self.input.is_file():
            raise InputError(f"input is not a file: {self.input}")
        if not os.access(self.input, os.R_OK):
            raise InputError(f"input not readable: {self.input}")
        parent = self.output.parent
        if not parent.exists():
            raise OutputError(f"output directory does not exist: {parent}")
        if not os.access(parent, os.W_OK):
            raise OutputError(f"output directory not writable: {parent}")

    def validate_resolution(self) -> None:
        """Resolution grammar: "auto" or "WxH" with positive integers."""
        r = self.resolution
        if r == "auto":
            return
        if "x" not in r:
            raise InputError(
                f"invalid resolution {r!r} — expected 'auto' or WxH "
                f"like 1280x720"
            )
        w, _, h = r.partition("x")
        if not (w.isdigit() and h.isdigit()) or int(w) < 1 or int(h) < 1:
            raise InputError(
                f"invalid resolution {r!r} — width and height must be "
                f"positive integers (e.g. 1280x720)"
            )
        # Normalizes aliases (stretch→fill, cover→fitoutside) and rejects
        # junk with the full valid list — never let an unknown token reach
        # the toe, where it would silently fall back to menu entry 0.
        self.fit = normalize_fit(self.fit)

    def as_dict(self) -> dict[str, Any]:
        return {
            "input": str(self.input),
            "output": str(self.output),
            "codec": self.codec,
            "subtype": self.subtype,
            "quality": self.quality,
            "fps": self.fps,
            "alpha": self.alpha,
            "resolution": self.resolution,
            "fit": self.fit,
            "extra": dict(self.extra),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> JobSpec:
        return cls(
            input=Path(d["input"]),
            output=Path(d["output"]),
            codec=d.get("codec", "notchlc"),
            subtype=d.get("subtype"),
            quality=d.get("quality"),
            fps=d.get("fps", "auto"),
            alpha=d.get("alpha"),
            resolution=d.get("resolution", "auto"),
            fit=d.get("fit", "fitbest"),
            extra=dict(d.get("extra") or {}),
        )


@dataclass
class Job:
    """A queued JobSpec with lifecycle state."""

    spec: JobSpec
    id: str
    status: str = JobStatus.QUEUED
    total_frames: int | None = None
    progress_frame: int = 0
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    #: Output codec was checked to match the request.
    verified: bool | None = None
    verify_note: str = ""
    #: Frames the controller reports writing (``done.frames_written``);
    #: the output file's own frame count is checked against it.
    frames_written: int | None = None
    #: Problems that did not fail the job but left the output short of the
    #: request (``done.warnings``, e.g. the audio mux failed → video-only).
    warnings: list[str] = field(default_factory=list)

    @property
    def is_terminal(self) -> bool:
        return self.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED)

    @property
    def percent(self) -> float | None:
        if self.total_frames:
            return min(100.0, self.progress_frame / self.total_frames * 100.0)
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "spec": self.spec.as_dict(),
            "total_frames": self.total_frames,
            "progress_frame": self.progress_frame,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "verified": self.verified,
            "verify_note": self.verify_note,
            "frames_written": self.frames_written,
            "warnings": list(self.warnings),
        }