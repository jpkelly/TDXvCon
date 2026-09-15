"""CLI end-to-end: main() with mock backend, renderer output, exit codes."""

from __future__ import annotations

import io
import sys

import pytest

from vcon import __main__ as cli_main
from vcon.cli import Renderer, print_codecs, print_doctor, print_version
from vcon.registry import Registry


class TtyStream(io.StringIO):
    """A stream that claims to be a tty (to exercise \r stats lines)."""

    def isatty(self) -> bool:
        return True


def run_vcon(argv: list[str], monkeypatch=None, tty: bool = False) -> tuple[int, str]:
    """Run main() with argv; capture stderr (where vcon writes everything).

    stdin is forced non-TTY so the overwrite prompt can never block tests —
    "ask" mode refuses non-interactively, which is the tested behavior.
    """
    err = TtyStream() if tty else io.StringIO()
    old_stderr, old_stdin = sys.stderr, sys.stdin
    sys.stderr = err
    sys.stdin = io.StringIO()  # StringIO.isatty() → False
    try:
        code = cli_main.main(argv)
    finally:
        sys.stderr, sys.stdin = old_stderr, old_stdin
    return code, err.getvalue()


def test_transcode_mock_success(tmp_path, monkeypatch):
    src = tmp_path / "clip.mov"
    src.write_bytes(b"data" * 40)
    out = tmp_path / "clip.nlc.mov"
    code, text = run_vcon(["-mock", "-y", "-i", str(src), "-c", "notchlc", str(out)])
    assert code == 0
    assert out.exists()
    assert "Input #0" in text
    assert "done" in text


def test_transcode_missing_input_fails(tmp_path):
    code, text = run_vcon(["-mock", "-i", str(tmp_path / "ghost.mov"),
                          "-c", "notchlc", "o.mov"])
    assert code == 1
    assert "not found" in text


def test_transcode_unknown_codec_fails(tmp_path):
    src = tmp_path / "a.mov"
    src.write_bytes(b"x")
    code, text = run_vcon(["-mock", "-y", "-i", str(src), "-c", "nope", "o.mov"])
    assert code == 1
    assert "unknown codec" in text


def test_overwrite_guard_noninteractive(tmp_path):
    src = tmp_path / "a.mov"
    src.write_bytes(b"x")
    existing = tmp_path / "o.mov"
    existing.write_bytes(b"existing")
    # no -y, stdin not a tty → refuse
    code, text = run_vcon(["-mock", "-i", str(src), "-c", "notchlc", str(existing)])
    assert code == 1
    assert "exists" in text


def test_overwrite_yes_flag(tmp_path):
    src = tmp_path / "a.mov"
    src.write_bytes(b"x" * 80)
    existing = tmp_path / "o.mov"
    existing.write_bytes(b"existing")
    code, text = run_vcon(["-mock", "-y", "-i", str(src), "-c", "notchlc", str(existing)])
    assert code == 0


def test_overwrite_no_flag(tmp_path):
    src = tmp_path / "a.mov"
    src.write_bytes(b"x" * 80)
    existing = tmp_path / "o.mov"
    existing.write_bytes(b"existing")
    code, text = run_vcon(["-mock", "-n", "-i", str(src), "-c", "notchlc", str(existing)])
    assert code == 1
    assert "-n" in text


def test_multi_output_one_pass(tmp_path):
    src = tmp_path / "a.mov"
    src.write_bytes(b"x" * 80)
    a = tmp_path / "a.nlc.mov"
    b = tmp_path / "b.nlc.mov"
    # Two outputs in one TD pass — both notchlc in v1; -c hapq lands with the
    # registry growth, but the *binding* logic is what's under test here.
    code, text = run_vcon([
        "-mock", "-y", "-i", str(src),
        "-c", "notchlc", "-q", "optimal", str(a),
        "-c", "notchlc", "-q", "best", str(b),
    ])
    assert code == 0
    assert a.exists() and b.exists()


def test_multi_output_unknown_second_codec_fails_fast(tmp_path):
    src = tmp_path / "a.mov"
    src.write_bytes(b"x" * 80)
    code, text = run_vcon([
        "-mock", "-y", "-i", str(src),
        "-c", "notchlc", str(tmp_path / "a.nlc.mov"),
        "-c", "zzz", str(tmp_path / "b.mov"),
    ])
    assert code == 1
    assert "unknown codec" in text
    # nothing ran
    assert not (tmp_path / "a.nlc.mov").exists()


def test_codecs_listing():
    code, text = run_vcon(["-codecs"])
    assert code == 0
    assert "notchlc" in text
    assert "prores" in text
    assert "RECOMMENDED" in text


def test_missing_codec_is_an_error():
    """-c is required, like ffmpeg's -c:v. No silent default."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "a.mov"
        src.write_bytes(b"x" * 40)
        code, text = run_vcon(["-mock", "-y", "-i", str(src), str(Path(d) / "o.mov")])
    assert code == 1
    assert "no codec given" in text
    assert "-c" in text


# ----------------------------------------------------------------------
# Help must stay in sync with the registry
# ----------------------------------------------------------------------


def test_help_lists_every_recommended_codec():
    """The help is the front door; it must not omit usable codecs."""
    from vcon.argparse_ff import usage_text
    from vcon.codec_meta import recommended

    text = usage_text()
    for meta in recommended():
        assert meta.cli_name in text, f"help omits codec {meta.cli_name!r}"


def test_help_shows_subtype_choices():
    """Users cannot guess -t values, so the variants must be listed."""
    from vcon.argparse_ff import usage_text

    text = usage_text()
    for token in ("4444", "hapq"):
        assert token in text, f"help omits subtype {token!r}"


def test_help_documents_every_flag():
    from vcon.argparse_ff import usage_text

    text = usage_text()
    for flag in ("-c", "-t", "-q", "-f", "-i", "-y", "-n", "-loglevel",
                 "-nostats", "-codecs", "-doctor", "-version"):
        assert flag in text, f"help omits flag {flag!r}"


def test_help_examples_never_overwrite_the_input():
    """An earlier example was 'vcon -i clip.mov ... clip.mov', which would
    have destroyed the source file."""
    import re
    from vcon.argparse_ff import usage_text

    for line in usage_text().splitlines():
        line = line.strip()
        if not line.startswith("vcon "):
            continue
        if " -i " not in line:
            continue
        inp = re.search(r"-i\s+(\S+)", line)
        assert inp, line
        source = inp.group(1)
        # any bare positional after the input must not share its name
        rest = line[inp.end():]
        for tok in rest.split():
            if tok.startswith("-"):
                continue
            assert tok != source, f"example overwrites its input: {line}"


def test_help_output_does_not_crash_even_if_registry_fails(monkeypatch):
    import vcon.argparse_ff as aa

    monkeypatch.setattr(aa, "_codec_help_lines", lambda: ["  (unavailable)"])
    text = aa.usage_text()
    assert "usage: vcon" in text


def test_help_flag_prints_to_stderr_and_exits_zero():
    code, text = run_vcon(["-h"])
    assert code == 0
    assert "usage: vcon" in text
    assert "-c,  -codec" in text


def test_doctor_reports(tmp_path):
    code, text = run_vcon(["-doctor"])
    # doctor exits 0 only if TD + toe are found; on CI they aren't —
    # assert it ran and reported something actionable either way.
    assert ("TouchDesigner binary" in text) or ("transcoder toe" in text)


def test_version():
    from vcon import __version__

    code, text = run_vcon(["-version"])
    assert code == 0
    assert f"vCon {__version__}" in text


def test_stats_line_renders_with_tty(tmp_path):
    src = tmp_path / "a.mov"
    src.write_bytes(b"x" * 80)
    code, text = run_vcon(["-mock", "-y", "-i", str(src), "-c", "notchlc",
                          str(tmp_path / "o.mov")],
                          tty=True)
    assert code == 0
    assert "frame=" in text
    assert "\r" in text


def test_nostats_suppresses_progress(tmp_path):
    src = tmp_path / "a.mov"
    src.write_bytes(b"x" * 80)
    code, text = run_vcon(
        ["-mock", "-y", "-nostats", "-i", str(src), "-c", "notchlc",
         str(tmp_path / "o.mov")], tty=True
    )
    assert code == 0
    assert "frame=" not in text


def test_quiet_loglevel(tmp_path):
    src = tmp_path / "a.mov"
    src.write_bytes(b"x" * 80)
    code, text = run_vcon(
        ["-mock", "-y", "-loglevel", "quiet", "-i", str(src), "-c", "notchlc",
         str(tmp_path / "o.mov")],
        tty=True,
    )
    assert code == 0
    assert "Input #0" not in text
    assert "done" not in text


# ----------------------------------------------------------------------
# Renderer unit bits
# ----------------------------------------------------------------------


def test_renderer_stats_line_format():
    stream = io.StringIO()
    r = Renderer(stream, tty=True)
    r.stats(frame=130, total=240, fps=47.0, speed=1.93)
    assert "frame=     130/240" in stream.getvalue()
    assert "fps=  47.0" in stream.getvalue()
    assert "speed=1.93x" in stream.getvalue()


def test_renderer_error_line():
    stream = io.StringIO()
    r = Renderer(stream)
    r.error("boom")
    assert "[vCon] [error] boom" in stream.getvalue()


def test_loglevel_gating():
    stream = io.StringIO()
    r = Renderer(stream, loglevel="error")
    r.log("info", "hidden")
    r.log("error", "shown")
    assert "hidden" not in stream.getvalue()
    assert "shown" in stream.getvalue()


def test_print_codecs_table():
    stream = io.StringIO()
    print_codecs(Registry(), stream)
    out = stream.getvalue()
    assert "notchlc" in out
    assert "optimal" in out


def test_print_doctor_rendering():
    stream = io.StringIO()
    code = print_doctor(
        [("TouchDesigner binary", True, "/opt/td"), ("transcoder toe", False, "missing")],
        stream,
    )
    assert code == 1
    assert "✔" in stream.getvalue() and "✘" in stream.getvalue()


def test_print_version():
    from vcon import __version__

    stream = io.StringIO()
    print_version(stream)
    assert __version__ in stream.getvalue()