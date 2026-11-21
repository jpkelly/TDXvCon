"""FFmpeg-style argument grammar.

``vcon [global options] [-i INPUT]... [output options] OUTPUT [output options] OUTPUT...``

Options bind to the *output that follows them* — exactly ffmpeg's positional
logic. Global options may appear anywhere. Outputs are the bare positional
arguments.

Differences from ffmpeg, by design:

- no ``-map``/filters (v1 is decode → re-encode)
- audio is automatic (no ``-an``/``-c:a``)
- ``-c`` is REQUIRED per output (ffmpeg defaults to a codec; vcon has no
  single sensible default — NotchLC and H.264 are worlds apart)

The codec list is generated from ``vcon.codec_meta``; see that module for how
to add one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vcon.errors import ParseError

LOGLEVELS = ("quiet", "error", "warning", "info", "debug")

DESCRIPTION = (
    "vcon — GPU video transcoder front-end driving TouchDesigner "
    "(NotchLC, and as the registry grows: Hap, ProRes, H.264, ...)"
)


@dataclass
class ParsedArgs:
    """The result of one successful parse."""

    inputs: list[Path] = field(default_factory=list)
    #: One dict per output: {output: Path, codec, subtype, quality, fps, alpha}
    outputs: list[dict[str, Any]] = field(default_factory=list)

    # globals
    loglevel: str = "info"
    overwrite: str = "ask"  # "ask" | "yes" | "no"
    stats: bool = True
    backend: str = "touchdesigner"
    td_path: Path | None = None
    toe_path: Path | None = None
    port: int = 7999
    list_codecs: bool = False
    doctor: bool = False
    version: bool = False


_GLOBAL_FLAGS = {
    "-y",
    "-n",
    "-loglevel",
    "-nostats",
    "-mock",
    "-td-path",
    "-toe-path",
    "-port",
    "-codecs",
    "-doctor",
    "-version",
    "-h",
    "--help",
}

_OUTPUT_FLAGS = {
    "-c": "codec",
    "-codec": "codec",
    "-t": "subtype",
    "-subtype": "subtype",
    "-q": "quality",
    "-quality": "quality",
    "-f": "fps",
    "-fps": "fps",
    "-s": "resolution",
    "-resolution": "resolution",
    "-fit": "fit",
    "-no-alpha": "no_alpha",
}


def _flag_needs_value(flag: str) -> bool:
    """Flags that consume the following token as their value."""
    return flag in {
        "-i",
        "-loglevel",
        "-td-path",
        "-toe-path",
        "-port",
        "-c", "-codec",
        "-t", "-subtype",
        "-q", "-quality",
        "-f", "-fps",
        "-s", "-resolution",
        "-fit",
    }


def _parse_port(raw: str) -> int:
    try:
        port = int(raw)
    except ValueError:
        raise ParseError(f"-port expects an integer, got {raw!r}") from None
    if not 1 <= port <= 65535:
        raise ParseError(f"-port out of range: {port}")
    return port


def parse_args(argv: list[str]) -> ParsedArgs:
    """Tokenize argv ffmpeg-style. Raises ParseError with usage hints."""
    p = ParsedArgs()

    i = 0
    n = len(argv)
    pending_output_opts: dict[str, Any] = {}

    def need_value(flag: str) -> str:
        nonlocal i
        if i + 1 >= n:
            raise ParseError(f"{flag} expects a value")
        i += 1
        return argv[i]

    while i < n:
        tok = argv[i]

        if tok in ("-h", "--help"):
            raise _HelpRequested()

        if tok == "-version":
            p.version = True
            i += 1
            continue

        if tok in ("-codecs", "-doctor"):
            p.list_codecs = p.list_codecs or tok == "-codecs"
            p.doctor = p.doctor or tok == "-doctor"
            i += 1
            continue

        if tok == "-y":
            p.overwrite = "yes"
            i += 1
            continue
        if tok == "-n":
            p.overwrite = "no"
            i += 1
            continue

        if tok == "-nostats":
            p.stats = False
            i += 1
            continue

        if tok == "-mock":
            p.backend = "mock"
            i += 1
            continue

        if tok == "-loglevel":
            val = need_value(tok)
            if val not in LOGLEVELS:
                raise ParseError(f"invalid loglevel {val!r} (use: {'/'.join(LOGLEVELS)})")
            p.loglevel = val
            i += 1
            continue

        if tok in ("-td-path", "-toe-path"):
            val = need_value(tok)
            setattr(p, "td_path" if tok == "-td-path" else "toe_path", Path(val))
            i += 1
            continue

        if tok == "-port":
            p.port = _parse_port(need_value(tok))
            i += 1
            continue

        if tok == "-i":
            p.inputs.append(Path(need_value(tok)))
            i += 1
            continue

        if tok in _OUTPUT_FLAGS:
            key = _OUTPUT_FLAGS[tok]
            if tok == "-no-alpha":
                pending_output_opts[key] = True
                i += 1
                continue
            val = need_value(tok)
            pending_output_opts[key] = val
            i += 1
            continue

        # Bare token: an output file — pending opts bind to it (ffmpeg logic)
        if tok.startswith("-"):
            raise ParseError(f"unknown option: {tok} (see vcon -h)")
        out = {"output": Path(tok)}
        out.update(pending_output_opts)
        pending_output_opts = {}
        p.outputs.append(out)
        i += 1

    # Post-parse sanity ------------------------------------------------
    if not p.version and not p.list_codecs and not p.doctor:
        if not p.inputs:
            raise ParseError("no input given (use -i INPUT)")
        if not p.outputs:
            raise ParseError("no output file given")
        if len(p.inputs) > 1:
            raise ParseError(
                "multiple -i inputs are not supported in v1 "
                "(one input; multiple outputs)"
            )
        # Any trailing opts with no following output are dropped silently? No —
        # be strict like ffmpeg would be confused; fail loudly.
        if pending_output_opts:
            raise ParseError("output options given after the last output file")

    return p


class _HelpRequested(Exception):
    """Internal signal so cli.py can print usage and exit 0."""


def _codec_help_lines() -> list[str]:
    """Build the codec section from the registry.

    Generated rather than hand-written so the help can never advertise a codec
    or subtype that does not exist. (The earlier static help listed no codecs
    at all, which left users guessing at -t values.)
    """
    try:
        from vcon.codec_meta import all_metas
        from vcon.registry import Registry

        metas = sorted(all_metas(), key=lambda m: m.cli_name)
        registry = Registry()
    except Exception:  # help must never crash
        return ["  (codec list unavailable)"]

    lines = []
    for m in metas:
        if not m.recommend:
            continue
        lines.append(f"  {m.cli_name:<9} {m.label}")
        if m.subtypes:
            # Show the PRIMARY alias per TD token, in declaration order. The
            # map is {alias: token} and I list the preferred alias first, so
            # taking the first occurrence per token drops shorthands (hq, q,
            # xq) while keeping the descriptive names users actually type.
            seen: set[str] = set()
            primary: list[str] = []
            for alias, token in m.subtypes.items():
                if token not in seen:
                    seen.add(token)
                    primary.append(alias)
            default = m.default_subtype
            marks = [
                f"{a}{' (default)' if a == default else ''}" for a in primary
            ]
            lines.append(f"{'':<11}-t {' | '.join(marks)}")
    return lines


def usage_text() -> str:
    """The full help text (codec list generated from the registry)."""
    codec_lines = "\n".join(_codec_help_lines())
    return f"""\
usage: vcon [global options] [-i INPUT] [output options] OUTPUT [output options] OUTPUT...

vCon — encode video with TouchDesigner's GPU encoders.
A codec must be given per output.

output options (apply to the output that follows — like ffmpeg):
  -c,  -codec CODEC        codec — REQUIRED
  -t,  -subtype SUBTYPE    codec variant (see the list below)
  -q,  -quality QUALITY    quality level (notchlc: good|very-good|excellent|optimal|best)
  -f,  -fps FPS            output frame rate ("auto" follows the source)
  -s,  -resolution WxH     output resolution ("auto" keeps the source size)
  -fit MODE                rescale mode (default fitbest): fill|fithorz|fitvert|fitbest|fitoutside
                            (aliases: stretch, fitwidth, fitheight, best, cover)
  -no-alpha                force alpha off even if the source has it

global options:
  -i INPUT                 input file (one per run)
  -y                       overwrite outputs without asking
  -n                       never overwrite existing outputs
  -loglevel LEVEL          quiet|error|warning|info|debug
  -nostats                 suppress the progress line
  -mock                    use the mock backend (no TouchDesigner needed)
  -td-path PATH            TouchDesigner binary override
  -toe-path PATH           transcoder.toe override
  -port N                  controller TCP port (default 7999)
  -codecs                  full codec list with variants, formats and speed
  -doctor                  diagnose the TouchDesigner setup
  -version                 print version
  -h, --help               this message

recommended codecs:
{codec_lines}

  Run 'vcon -codecs' for every codec (including legacy ones), their quality
  levels, pixel formats, and speed.

examples:
  # NotchLC mezzanine at high quality
  vcon -i clip.mov -c notchlc -q best clip.nlc.mov

  # ProRes 4444 XQ for an edit suite (alpha-capable)
  vcon -i clip.mov -c prores -t 4444xq clip_prores.mov

  # Hap Q for a media server
  vcon -i clip.mov -c hap -t hapq clip_hap.mov

  # H.264 delivery file
  vcon -i clip.mov -c h264 clip.mp4

  # Two codecs from one pass through TouchDesigner
  vcon -i clip.mov -c notchlc a.nlc.mov -c hap -t hapq b.hapq.mov

  # Overwrite without asking, quiet
  vcon -y -loglevel error -i clip.mov -c notchlc out.mov

notes:
  - Output path is positional; options bind to the output that follows them.
  - Outputs are typically several times the source size: NotchLC and ProRes
    are mezzanine codecs (~5:1 against RAW, not against H.264).
  - A codec's available subtypes and pixel formats vary; alpha requires a
    format that carries it (e.g. ProRes needs -t 4444, Hap HDR has none).
  - Every output is verified: vCon reads the codec and frame count back out
    of the finished file and fails the job if they are not what was written.

exit status:
  0  every job encoded       1  a job failed       2  TouchDesigner failed
  3  every job encoded, but a warning was printed (e.g. the audio mux
     failed and the output is video-only)
"""


#: Kept for backwards compatibility with tests/imports that expect USAGE.
USAGE = usage_text()


# NOTE: there is deliberately no argparse.ArgumentParser here. The grammar is
# ffmpeg-style (options bind to the following output), which argparse cannot
# express, and an earlier argparse "stand-in" for -h duplicated the help text
# and drifted out of sync. One source of truth: usage_text().