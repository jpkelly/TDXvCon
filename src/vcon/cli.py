"""CLI renderer — subscribes to core events, draws them ffmpeg-style.

Everything user-visible lives here: stats lines, log lines, error reports,
codecs table, doctor. The core stays silent; this module never touches the
queue directly except for pre-flight prompts.

Output follows ffmpeg conventions:

- stats and progress → stderr, in-place via ``\\r``
- errors → stderr, prefixed like ``[vCon] ...``
- normal informational output → stderr too (ffmpeg keeps stdout clean
  for data); stdout only for machine-readable dumps (-codecs json mode later)
"""

from __future__ import annotations

import sys
import textwrap
from typing import IO

from vcon.errors import VconError
from vcon.events import Event
from vcon.models import JobStatus


class Renderer:
    """Draws an event stream onto a terminal (or test capture)."""

    def __init__(
        self,
        stream: IO[str],
        *,
        loglevel: str = "info",
        stats: bool = True,
        tty: bool = True,
    ) -> None:
        self.stream = stream
        self.loglevel = loglevel
        self.stats_enabled = stats
        self.tty = tty  # False in tests: never use \r tricks
        self._order = {"quiet": 99, "error": 3, "warning": 2, "info": 1, "debug": 0}

    # ------------------------------------------------------------------
    # Levels
    # ------------------------------------------------------------------

    def _visible(self, level: str) -> bool:
        return self._order.get(level, 1) >= self._order.get(self.loglevel, 1)

    def _write(self, text: str, *, carriage: bool = False) -> None:
        end = "\r" if (carriage and self.tty) else "\n"
        self.stream.write(text + end)
        self.stream.flush()

    # ------------------------------------------------------------------
    # Static sections
    # ------------------------------------------------------------------

    def banner(self, input_name: str, outputs: list[dict[str, object]]) -> None:
        """ffmpeg's opening lines: input, then one line per output."""
        if not self._visible("info"):
            return
        self._write(f"Input #0: {input_name}")
        for idx, out in enumerate(outputs):
            self._write(
                f"Output #{idx}: {out['output']} "
                f"(codec={out.get('codec', 'notchlc')}"
                + (f", subtype={out['subtype']}" if out.get("subtype") else "")
                + ")"
            )

    def log(self, level: str, message: str) -> None:
        if not self._visible(level):
            return
        prefix = {"error": "[error] ", "warning": "[warning] "}.get(level, "")
        self._write(f"[vCon] {prefix}{message}")

    def error(self, message: str) -> None:
        self.log("error", message)

    # ------------------------------------------------------------------
    # Stats line (the ffmpeg progress line)
    # ------------------------------------------------------------------

    def stats(self, frame: int, total: int | None, fps: float, speed: float) -> None:
        if not self.stats_enabled or not self._visible("info"):
            return
        total_s = f"/{total}" if total else ""
        self._write(
            f"frame= {frame:>7}{total_s} fps= {fps:5.1f} "
            f"speed={speed:.2f}x",
            carriage=True,
        )

    def finish_stats(self) -> None:
        """Terminate the last stats line so logs don't overwrite it."""
        if self.stats_enabled:
            self._write("")

    # ------------------------------------------------------------------
    # Event binding
    # ------------------------------------------------------------------

    def bind(self, bus) -> None:
        """Subscribe this renderer to an EventBus."""
        bus.subscribe_jobs(self._on_job_event)
        bus.subscribe("log", self._on_log)
        bus.subscribe("queue_idle", self._on_idle)

    def _on_log(self, event: Event) -> None:
        self.log(event.data.get("level", "info"), event.data.get("message", ""))

    def _on_idle(self, event: Event) -> None:
        self.finish_stats()

    def _on_job_event(self, event: Event) -> None:
        if event.type == "job_started":
            if self._visible("info"):
                self._write(f"[job {event.job_id}] started: {event.data.get('input', '')}")
        elif event.type == "job_progress":
            d = event.data
            frame = int(d.get("frame", 0))
            total = d.get("total_frames") or None
            total = int(total) if total else None
            # fps/speed derived later from event timestamps; placeholder = 0.0
            self.stats(frame, total, fps=0.0, speed=0.0)
        elif event.type == "job_done":
            self.finish_stats()
            if self._visible("info"):
                secs = d = event.data.get("seconds")
                self._write(f"[job {event.job_id}] done → {event.data.get('output', '')}"
                             + (f" ({secs:.1f}s)" if secs else ""))
        elif event.type == "job_error":
            self.finish_stats()
            self.error(f"job {event.job_id}: {event.data.get('message', 'unknown')}")


# ----------------------------------------------------------------------
# Static text sections (help, codecs, doctor)
# ----------------------------------------------------------------------


def print_help(stream: IO[str]) -> None:
    # Generated at call time so the codec list always matches the registry.
    from vcon.argparse_ff import usage_text

    stream.write(usage_text() + "\n")


def print_version(stream: IO[str]) -> None:
    from vcon import __version__

    stream.write(f"vCon {__version__}\n")


_SPEED_LABEL = {
    "gpu-fast": "GPU, very fast",
    "gpu": "GPU",
    "cpu": "CPU",
    "cpu-slow": "CPU, slow",
}


def print_codecs(registry, stream: IO[str]) -> None:
    """List every codec, split into recommended and legacy/niche."""
    rows = registry.listing()
    recommended = [r for r in rows if _recommended(r)]
    others = [r for r in rows if not _recommended(r)]

    stream.write("Codecs available via TouchDesigner "
                 "(specify with -c CODEC):\n\n")

    def show(row, indent="  "):
        mark = "" if row["available_here"] else "   [unavailable here]"
        stream.write(f"{indent}{row['name']:<10} {row['label']}{mark}\n")
        pad = f"{indent}{'':<10}"
        details = []
        if row["qualities"]:
            details.append(f"quality: {', '.join(row['qualities'])}")
        if row["subtypes"]:
            details.append(f"subtypes: {', '.join(row['subtypes'])}")
        speed = _speed_of(row)
        if speed:
            details.append(f"speed: {speed}")
        if details:
            for i, detail in enumerate(details):
                stream.write(f"{pad}{detail}\n")
        if row["caveat"]:
            wrapped = textwrap.fill(
                row["caveat"], width=72,
                initial_indent=pad, subsequent_indent=pad,
            )
            stream.write(f"{wrapped}\n")

    stream.write("RECOMMENDED\n")
    for row in recommended:
        show(row)

    if others:
        stream.write("\nLEGACY / NICHE (selectable, but rarely what you want)\n")
        for row in others:
            show(row)

    stream.write("\nExamples:\n")
    stream.write("  vcon -i in.mov -c notchlc -q optimal out.mov\n")
    stream.write("  vcon -i in.mov -c prores -t 4444xq out.mov\n")
    stream.write("  vcon -i in.mov -c hap -t hapq out.mov\n")


def _recommended(row) -> bool:
    opts = row.get("options") or {}
    val = opts.get("recommend")
    return bool(val[0]) if val else True


def _speed_of(row) -> str | None:
    opts = row.get("options") or {}
    val = opts.get("speed")
    if not val:
        return None
    return _SPEED_LABEL.get(val[0], val[0])


def print_doctor(findings: list[tuple[str, bool, str]], stream: IO[str]) -> int:
    """Render doctor results; returns exit code."""
    ok = True
    for name, good, detail in findings:
        mark = "✔" if good else "✘"
        if not good:
            ok = False
        stream.write(f"{mark} {name}: {detail}\n")
    stream.write("\n" + ("All good — ready to encode.\n" if ok else "Fix the issues above and re-run vcon -doctor.\n"))
    return 0 if ok else 1


def report_exception(exc: BaseException, stream: IO[str]) -> int:
    """Map an exception to a user-facing message + exit code."""
    if isinstance(exc, VconError):
        stream.write(f"[vCon] error: {exc}\n")
        return 1
    stream.write(f"[vCon] internal error: {exc!r}\n")
    return 2