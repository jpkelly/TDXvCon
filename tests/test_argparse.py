"""FFmpeg-style parser: grammar, binding, error cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from vcon.argparse_ff import ParsedArgs, ParseError, parse_args
from vcon.argparse_ff import _HelpRequested


def test_basic_single_output():
    p = parse_args(["-i", "clip.mov", "clip.nlc.mov"])
    assert [str(x) for x in p.inputs] == ["clip.mov"]
    assert [str(o["output"]) for o in p.outputs] == ["clip.nlc.mov"]
    assert p.outputs[0].get("codec") is None  # default applies later


def test_defaults():
    p = parse_args(["-i", "a.mov", "b.mov"])
    assert p.loglevel == "info"
    assert p.stats is True
    assert p.overwrite == "ask"
    assert p.backend == "touchdesigner"
    assert p.port == 7999


def test_multi_output_option_binding():
    p = parse_args([
        "-i", "in.mov",
        "-c", "notchlc", "-q", "best", "a.nlc.mov",
        "-c", "hapq", "b.hapq.mov",
    ])
    assert len(p.outputs) == 2
    assert p.outputs[0]["codec"] == "notchlc"
    assert p.outputs[0]["quality"] == "best"
    assert p.outputs[1]["codec"] == "hapq"
    assert "quality" not in p.outputs[1]


def test_global_flags_position_independent():
    p = parse_args(["-y", "-i", "a.mov", "-loglevel", "debug", "out.mov", "-nostats"])
    assert p.overwrite == "yes"
    assert p.loglevel == "debug"
    assert p.stats is False


def test_long_aliases():
    p = parse_args(["-i", "a.mov", "-codec", "notchlc", "-quality", "optimal",
                    "-fps", "30", "-no-alpha", "o.mov"])
    o = p.outputs[0]
    assert o["codec"] == "notchlc"
    assert o["quality"] == "optimal"
    assert o["fps"] == "30"
    assert o["no_alpha"] is True


def test_y_n_conflict_last_wins():
    p = parse_args(["-y", "-n", "-i", "a.mov", "o.mov"])
    assert p.overwrite == "no"
    p = parse_args(["-n", "-y", "-i", "a.mov", "o.mov"])
    assert p.overwrite == "yes"


def test_mock_and_td_path_flags():
    p = parse_args(["-mock", "-td-path", "/usr/bin/td", "-toe-path", "/t.toe",
                    "-port", "8000", "-i", "a.mov", "o.mov"])
    assert p.backend == "mock"
    # Compare as paths: str() uses the OS separator, so on Windows
    # str(Path("/usr/bin/td")) is "\\usr\\bin\\td".
    assert p.td_path == Path("/usr/bin/td")
    assert p.toe_path == Path("/t.toe")
    assert p.port == 8000


def test_codecs_and_doctor_shortcircuit_inputs():
    p = parse_args(["-codecs"])
    assert p.list_codecs and not p.doctor
    p = parse_args(["-doctor"])
    assert p.doctor and not p.list_codecs


def test_missing_input_value():
    with pytest.raises(ParseError, match="expects a value"):
        parse_args(["-i"])


def test_missing_output_value_for_codec():
    with pytest.raises(ParseError, match="expects a value"):
        parse_args(["-i", "a.mov", "-c"])


def test_no_input():
    with pytest.raises(ParseError, match="no input"):
        parse_args(["out.mov"])


def test_no_output():
    with pytest.raises(ParseError, match="no output"):
        parse_args(["-i", "a.mov"])


def test_multiple_inputs_rejected_v1():
    with pytest.raises(ParseError, match="multiple -i"):
        parse_args(["-i", "a.mov", "-i", "b.mov", "o.mov"])


def test_trailing_output_options_rejected():
    with pytest.raises(ParseError, match="after the last output"):
        parse_args(["-i", "a.mov", "o.mov", "-c", "hapq"])


def test_unknown_option():
    with pytest.raises(ParseError, match="unknown option"):
        parse_args(["-i", "a.mov", "-frobnicate", "o.mov"])


def test_bad_loglevel():
    with pytest.raises(ParseError, match="loglevel"):
        parse_args(["-loglevel", "loud", "-i", "a.mov", "o.mov"])


def test_bad_port():
    with pytest.raises(ParseError, match="port"):
        parse_args(["-port", "nope", "-i", "a.mov", "o.mov"])
    with pytest.raises(ParseError, match="range"):
        parse_args(["-port", "70000", "-i", "a.mov", "o.mov"])


def test_help_request():
    with pytest.raises(_HelpRequested):
        parse_args(["-h"])
    with pytest.raises(_HelpRequested):
        parse_args(["--help"])


def test_version_flag():
    p = parse_args(["-version"])
    assert p.version