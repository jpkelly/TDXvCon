"""vcon entry point.

Composition root: parse → build JobSpecs → run Transcoder → render events.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from vcon import __version__
from vcon.argparse_ff import ParsedArgs, ParseError, _HelpRequested, parse_args
from vcon.cli import (
    Renderer,
    print_codecs,
    print_doctor,
    print_help,
    print_version,
    report_exception,
)
from vcon.config import find_touchdesigner, resolve_toe_path
from vcon.errors import CodecError, ConfigError, VconError
from vcon.models import JobSpec, _default_output_for
from vcon.registry import Registry
from vcon.transcoder import Transcoder, TranscoderOptions


def _toe_or_none():
    """Resolve the packaged toe, or None if it hasn't been built yet."""
    try:
        return resolve_toe_path()
    except VconError:
        return None


def _build_specs(p: ParsedArgs) -> list[JobSpec]:
    """One JobSpec per output; registry resolves defaults (e.g. output name)."""
    registry = Registry()
    input_path = p.inputs[0]
    specs: list[JobSpec] = []

    for out in p.outputs:
        codec_name = out.get("codec")
        if not codec_name:
            raise CodecError(
                f"no codec given for output '{out['output']}' — specify one "
                f"with -c (e.g. -c notchlc). Run 'vcon -codecs' for the list."
            )
        codec = registry.get(codec_name)
        subtype = out.get("subtype")
        quality = out.get("quality")
        fps = out.get("fps", "auto")
        alpha = None
        if out.get("no_alpha"):
            alpha = False

        output = Path(out["output"])

        specs.append(
            JobSpec(
                input=input_path,
                output=output,
                codec=codec_name,
                subtype=subtype,
                quality=quality,
                fps=fps,
                alpha=alpha,
            )
        )
    return specs


def _overwrite_ok(specs: list[JobSpec], mode: str, renderer: Renderer) -> bool:
    """ffmpeg -y/-n semantics; interactive ask when TTY and unspecified."""
    existing = [s.output for s in specs if s.output.exists()]
    if not existing:
        return True
    if mode == "no":
        for out in existing:
            renderer.error(f"output exists (aborting, -n): {out}")
        return False
    if mode == "yes":
        return True
    if not sys.stdin.isatty():
        for out in existing:
            renderer.error(f"output exists and stdin is not a tty: {out}")
        return False
    for out in existing:
        reply = input(f"Overwrite '{out}'? [y/N] ").strip().lower()
        if reply not in ("y", "yes"):
            renderer.error(f"aborted: {out}")
            return False
    return True


async def _run_transcode(p: ParsedArgs, specs: list[JobSpec], renderer: Renderer) -> int:
    from vcon.queue_manager import QueueOptions
    from vcon.transcoder import Transcoder

    opts = TranscoderOptions(
        backend=p.backend,
        td_path=p.td_path,
        toe_path=p.toe_path or _toe_or_none(),
        port=p.port,
    )
    # ffmpeg-style overwrite semantics → queue behavior
    from vcon.queue_manager import QueueOptions

    t = Transcoder(opts)
    t.queue.options = QueueOptions(
        no_overwrite=p.overwrite == "no",
        yes=p.overwrite == "yes",
        state_path=t.queue.options.state_path,
    )
    t.bus  # core bus — renderer subscribes
    renderer.bind(t.bus)
    renderer.banner(
        str(p.inputs[0]),
        [
            {"output": str(s.output), "codec": s.codec, "subtype": s.subtype}
            for s in specs
        ],
    )
    for spec in specs:
        t.add(spec)
    return await t.run()


def _doctor(renderer: Renderer, port: int = 7999) -> int:
    """Diagnose setup: TD binary, toe, and a live controller if one is up."""
    findings: list[tuple[str, bool, str]] = []
    try:
        td = find_touchdesigner()
        if td is None:
            findings.append(
                ("TouchDesigner binary", False,
                 "not found — install TouchDesigner or pass -td-path")
            )
        else:
            findings.append(("TouchDesigner binary", True, str(td)))
    except ConfigError as exc:
        findings.append(("TouchDesigner binary", False, str(exc)))
    try:
        toe = resolve_toe_path()
        findings.append(("transcoder toe", True, str(toe)))
    except ConfigError as exc:
        findings.append(("transcoder toe", False, str(exc)))

    findings.append(("mock backend", True, "available (use -mock to test without TD)"))
    try:
        toe = resolve_toe_path()
        findings.append(("toe freshness", *_toe_freshness(toe)))
    except ConfigError:
        pass  # already reported above
    findings.append(("controller probe", *_probe_controller(port)))
    return print_doctor(findings, renderer.stream)


def _toe_freshness(toe_path) -> tuple[bool, str]:
    """Report whether the built toe is newer than the controller source.

    A stale toe silently ignores fixes made in toe/*.py — the failure mode is
    baffling ("I fixed that!") because nothing warns you. Timestamps are the
    only reliable signal: .toe files are compressed binary, so you cannot
    grep them for expected code.

    Walks up looking for a ``toe/vcon_controller.py`` sibling; when the toe
    comes from an installed package there is no checkout, so we say so rather
    than guess.
    """
    import datetime

    candidates = []
    here = toe_path.resolve()
    for parent in list(here.parents)[:5]:
        candidates.append(parent / "toe" / "vcon_controller.py")
    # Also check relative to the package (covers `pip install -e .`)
    pkg = Path(__file__).resolve().parent
    for parent in list(pkg.parents)[:5]:
        candidates.append(parent / "toe" / "vcon_controller.py")

    src = next((c for c in candidates if c.exists()), None)
    if src is None:
        return True, "installed package (no sources to compare)"

    toe_m = toe_path.stat().st_mtime
    src_m = src.stat().st_mtime
    fmt = "%Y-%m-%d %H:%M:%S"
    if toe_m < src_m:
        return False, (
            f"STALE — toe built "
            f"{datetime.datetime.fromtimestamp(toe_m):{fmt}}, but "
            f"{src.name} changed "
            f"{datetime.datetime.fromtimestamp(src_m):{fmt}}. Rebuild in the "
            f"TD textport: exec(open('{src.parent}/build_network.py', "
            f"encoding='utf-8').read())"
        )
    return True, (
        f"up to date (toe built {datetime.datetime.fromtimestamp(toe_m):{fmt}})")


def _probe_controller(port: int) -> tuple[bool, str]:
    """Connect to the toe's TCP server and read its hello handshake."""
    import json
    import socket

    from vcon import __version__

    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2.0) as s:
            s.settimeout(3.0)
            data = s.recv(4096)
    except OSError as exc:
        return (False, f"no controller on port {port} ({exc.strerror}) — "
                       f"vCon will launch TouchDesigner for you")
    if b'"hello"' not in data:
        return (False, f"port {port} answered but not with a vcon hello: "
                       f"{data[:80]!r}")
    detail = data.decode(errors="replace").strip()
    try:
        hello = json.loads(detail.splitlines()[0])
    except Exception:
        return (True, f"controller live on port {port} ({detail})")

    ctrl_ver = hello.get("controller_version")
    if ctrl_ver is None:
        return (True, f"controller live on port {port} (older build, no "
                      f"version reported — rebuild the toe to update)")
    if ctrl_ver != __version__:
        return (False, f"controller is v{ctrl_ver} but vcon is v{__version__} "
                       f"— the toe is out of date; rebuild it "
                       f"(exec build_network.py in the TD textport)")
    return (True, f"controller live on port {port}, v{ctrl_ver} (matches)")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        p = parse_args(argv)
    except _HelpRequested:
        print_help(sys.stderr)
        return 0
    except ParseError as exc:
        sys.stderr.write(f"vcon: error: {exc}\n\n")
        print_help(sys.stderr)
        return 1

    if p.version:
        print_version(sys.stderr)
        return 0

    renderer = Renderer(
        sys.stderr, loglevel=p.loglevel, stats=p.stats, tty=sys.stderr.isatty()
    )

    if p.list_codecs:
        print_codecs(Registry(), renderer.stream)
        return 0

    if p.doctor:
        return _doctor(renderer, p.port)

    # Transcode path -----------------------------------------------------
    try:
        specs = _build_specs(p)
        if not _overwrite_ok(specs, p.overwrite, renderer):
            return 1
    except VconError as exc:
        return report_exception(exc, renderer.stream)

    try:
        return asyncio.run(_run_transcode(p, specs, renderer))
    except KeyboardInterrupt:
        renderer.finish_stats()
        renderer.error("interrupted")
        return 130
    except (VconError, RuntimeError) as exc:
        return report_exception(exc, renderer.stream)


if __name__ == "__main__":
    sys.exit(main())