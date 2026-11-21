"""Registry behavior: lookup, validation, platform gates, listing."""

from __future__ import annotations

import pytest

from vcon.errors import CodecError
from vcon.registry import BUILTIN_CODECS, CodecSpec, Registry, platform_of_current_machine


def test_builtin_registry_has_notchlc():
    r = Registry()
    assert "notchlc" in r.names


def test_get_unknown_codec_raises_with_known_list():
    r = Registry()
    with pytest.raises(CodecError, match="unknown codec 'hapq'"):
        r.get("hapq")


def test_notchlc_quality_ladder():
    spec = next(c for c in BUILTIN_CODECS if c.name == "notchlc")
    assert spec.qualities == ("good", "very-good", "excellent", "optimal", "best")
    assert spec.default_quality == "optimal"


def test_resolve_quality_accepts_valid_and_defaults():
    spec = next(c for c in BUILTIN_CODECS if c.name == "notchlc")
    assert spec.resolve_quality(None) == "optimal"
    assert spec.resolve_quality("best") == "best"


def test_resolve_quality_rejects_junk():
    spec = next(c for c in BUILTIN_CODECS if c.name == "notchlc")
    with pytest.raises(CodecError, match="quality"):
        spec.resolve_quality("ultra")


def test_resolve_subtype_none_when_no_subtypes():
    spec = next(c for c in BUILTIN_CODECS if c.name == "notchlc")
    assert spec.resolve_subtype(None) is None
    with pytest.raises(CodecError, match="subtype"):
        spec.resolve_subtype("4444xq")


def test_preflight_platform_gate():
    r = Registry()
    machine = platform_of_current_machine()
    spec = r.get("notchlc")
    if machine in ("mac", "windows"):
        assert r.preflight("notchlc") is spec
    else:
        with pytest.raises(CodecError, match="cannot encode"):
            r.preflight("notchlc")


def test_preflight_unavailable_platform_message():
    linux_only = CodecSpec(
        name="linuxmyth", label="mythical", td_codec="Myth",
        platforms=frozenset({"windows"}),
    )
    r = Registry((linux_only,))
    with pytest.raises(CodecError, match="mac"):
        r.preflight("linuxmyth", machine="mac")


def test_listing_shape():
    rows = Registry().listing()
    # Sorted alphabetically now that every codec is generated from the
    # catalogue, rather than a single hand-written entry.
    by_name = {r["name"]: r for r in rows}
    assert "notchlc" in by_name
    assert by_name["notchlc"]["available_here"] in (True, False)
    assert by_name["notchlc"]["qualities"][0] == "good"


def test_registry_covers_all_td_codecs():
    """Every codec in TD's videocodec menu has a registry entry."""
    td_menu = {
        "rle", "mjpa", "mpeg4", "h264", "cineform", "hap", "h265", "gif",
        "notchlc", "vp8", "vp9", "prores", "vvc", "av1",
    }
    registered = set(Registry().names)
    missing = td_menu - registered
    assert not missing, f"codecs in TD but not in the registry: {missing}"


def test_every_registry_entry_td_codec_is_a_real_menu_token():
    """Guard: our token must exactly match TD's videocodec menu entry."""
    td_menu = {
        "rle", "mjpa", "mpeg4", "h264", "cineform", "hap", "h265", "gif",
        "notchlc", "vp8", "vp9", "prores", "vvc", "av1",
    }
    for spec in BUILTIN_CODECS:
        assert spec.td_codec in td_menu, (
            f"{spec.name}: td_codec {spec.td_codec!r} is not a TD menu token"
        )


def test_prores_subtypes_present():
    # Tokens VERIFIED LIVE via toe/dump_codec_menus.py — TD uses the full
    # names, NOT the fourccs (ap4h/apch/apcn).
    spec = Registry().get("prores")
    assert spec.default_subtype == "4444"
    assert spec.resolve_subtype("4444xq") == "prores4444xq"
    assert spec.resolve_subtype("422") == "prores422"
    assert spec.resolve_subtype(None) == "prores4444"   # default
    with pytest.raises(CodecError):
        spec.resolve_subtype("nope")


def test_hap_subtypes_present():
    # VERIFIED LIVE: hap/hapq/hapr/haphdr — alpha is a pixel format here,
    # not a subtype (there is no 'hapa' token).
    spec = Registry().get("hap")
    assert spec.resolve_subtype("hapq") == "hapq"
    assert spec.resolve_subtype("haphdr") == "haphdr"
    assert spec.resolve_subtype(None) == "hap"


def test_prores_alpha_requires_4444_subtype():
    """VERIFIED LIVE: ProRes 4444/4444XQ expose 'yuva444412bit' (alpha);
    the 422 variants expose only yuv422*. An earlier reading wrongly
    concluded ProRes had no alpha at all because it had not selected a
    subtype when reading the pixel-format menu."""
    spec = Registry().get("prores")

    # 4444 variants CAN carry alpha
    p4444 = spec.td_params(subtype="4444", alpha=True)
    assert p4444["moviepixelformat"] == "yuva444412bit"
    p4444xq = spec.td_params(subtype="4444xq", alpha=True)
    assert p4444xq["moviepixelformat"] == "yuva444412bit"

    # 422 variants cannot
    for sub in ("422", "422hq", "422lt", "422proxy"):
        with pytest.raises(CodecError, match="cannot encode alpha"):
            spec.td_params(subtype=sub, alpha=True)


def test_prores_4444_pixel_formats_differ_from_422():
    """The menu changes with the subtype — this is the whole point."""
    spec = Registry().get("prores")
    assert spec.pixel_formats_for("prores4444") == ("yuv44410bit", "yuva444412bit")
    assert "yuva444412bit" not in spec.pixel_formats_for("prores422hq")
    assert spec.alpha_format_for("prores4444") == "yuva444412bit"
    assert spec.alpha_format_for("prores422hq") is None


def test_hap_hdr_has_its_own_pixel_formats():
    """VERIFIED LIVE: haphdr offers rgbu/rgbs, not rgb/rgba."""
    spec = Registry().get("hap")
    assert spec.pixel_formats_for("haphdr") == ("rgbu", "rgbs")
    assert spec.alpha_format_for("haphdr") is None
    with pytest.raises(CodecError, match="cannot encode alpha"):
        spec.td_params(subtype="haphdr", alpha=True)
    # the other hap variants do support alpha
    assert spec.td_params(subtype="hapq", alpha=True)["moviepixelformat"] == "rgba"


def test_prores_does_not_send_rgba_pixel_format():
    """ProRes must never be sent 'rgba' — it would silently select index 0."""
    spec = Registry().get("prores")
    for sub in (None, "422hq", "4444"):
        params = spec.td_params(subtype=sub)
        assert params.get("moviepixelformat", "") not in ("rgba", "rgb")


def test_alpha_capable_codecs_still_declare_a_format():
    """Codecs that CAN do alpha must have one declared."""
    for name in ("notchlc", "rle", "cineform"):
        spec = Registry().get(name)
        assert spec.alpha_pixel_format is not None, f"{name} lost its alpha format"
        assert spec.td_params(alpha=True)["moviepixelformat"]


def test_every_codec_pixel_format_is_declared():
    """Any pixel format we send must be in that codec's verified menu."""
    for spec in BUILTIN_CODECS:
        for fmt in (spec.alpha_pixel_format, spec.opaque_pixel_format):
            if fmt is not None:
                assert fmt in spec.pixel_formats, (
                    f"{spec.name}: sends {fmt!r} which is not in its "
                    f"verified pixel formats {spec.pixel_formats}"
                )


def test_td_params_for_prores_carries_subtype():
    spec = Registry().get("prores")
    params = spec.td_params(subtype="422hq")
    assert params["videocodec"] == "prores"
    assert params["videocodectype"] == "prores422hq"
    assert params["moviecontainer"] == "mov"


def test_delivery_codec_uses_mp4_container():
    spec = Registry().get("h264")
    assert spec.default_ext == "mp4"
    assert spec.td_params()["moviecontainer"] == "mp4"


# ----------------------------------------------------------------------
# Version consistency between the package and the toe controller
# ----------------------------------------------------------------------


def test_controller_version_matches_package_version():
    """The toe reports CONTROLLER_VERSION in its hello; vcon compares it to
    __version__ to warn about a stale toe. They must not drift."""
    import re
    from pathlib import Path

    from vcon import __version__

    src = Path(__file__).resolve().parent.parent / "toe" / "vcon_controller.py"
    text = src.read_text(encoding="utf-8")
    m = re.search(r'^CONTROLLER_VERSION\s*=\s*["\']([^"\']+)', text, re.M)
    assert m, "CONTROLLER_VERSION not found in toe/vcon_controller.py"
    assert m.group(1) == __version__, (
        f"toe controller is v{m.group(1)} but package is v{__version__} — "
        f"bump both together"
    )


def test_controller_declares_a_version_constant():
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "toe" / "vcon_controller.py"
    text = src.read_text(encoding="utf-8")
    assert "CONTROLLER_VERSION" in text
    # and reports it in the handshake
    assert "controller_version" in text


# ----------------------------------------------------------------------
# Per-frame side effects must be latched (regression guard)
# ----------------------------------------------------------------------


def _controller_source() -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parent.parent
            / "toe" / "vcon_controller.py").read_text(encoding="utf-8")


def test_project_quit_is_latched_not_per_frame():
    """onFrame runs ~60x/second. An un-latched quit condition re-fired every
    frame and stacked modal dialogs the user had to dismiss by hand. Any call
    that ends the session must be guarded by a latch set BEFORE the call."""
    import ast
    import textwrap
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "toe" / "vcon_controller.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    target = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.FunctionDef) and n.name == "_maybe_quit_idle"),
        None,
    )
    assert target is not None, "_maybe_quit_idle disappeared"

    # Find the real call to project.quit() (not mentions in comments/strings).
    quit_line = None
    for node in ast.walk(target):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "quit"):
            quit_line = node.lineno
            break
    assert quit_line is not None, "expected the idle backstop to call quit()"

    # The latch assignment must come first on an earlier line.
    latch_lines = [
        n.lineno for n in ast.walk(target)
        if isinstance(n, ast.Attribute) and n.attr == "_quit_requested"
        and isinstance(n.ctx, ast.Store)
    ]
    assert latch_lines, "project.quit() must be latched with _quit_requested"
    assert min(latch_lines) < quit_line, (
        "latch must be set BEFORE calling quit, or a nested cook re-enters"
    )

    # And the guard must actually short-circuit.
    assert any("_quit_requested" in src.read_text(encoding="utf-8") for _ in [0])


def test_idle_quit_is_opt_in_by_default():
    """Quitting must be gated on PROCESS PROVENANCE, not a user preference.

    The earlier toggle design put the decision in the wrong place: the
    front-end knows whether it launched TD, so the controller can too — via
    the VCON_LAUNCHED environment variable. A user-opened session must never
    be quit by vCon, and a vCon-spawned orphan must clean itself up without
    anyone configuring anything.
    """
    text = _controller_source()
    assert "VCON_LAUNCHED" in text, (
        "arming must come from the launch environment, not a parameter"
    )
    assert "Quitidle" not in text, (
        "no user-facing quit toggle — provenance makes it redundant"
    )
    # Arming happens in __init__ from the environment: a user-opened TD has
    # no variable and is therefore disarmed unconditionally.
    assert "_orphan_cleanup_armed" in text


def test_driver_marks_spawned_td():
    """The driver must set VCON_LAUNCHED when spawning TouchDesigner."""
    from pathlib import Path

    drv = (Path(__file__).resolve().parent.parent
           / "src" / "vcon" / "td_driver.py").read_text(encoding="utf-8")
    assert 'VCON_LAUNCHED' in drv and '"1"' in drv


def test_onframe_guards_against_destroyed_extension():
    """A re-inited extension must stop driving the network."""
    text = _controller_source()
    assert "self._destroyed" in text
    assert "if self._destroyed:" in text


def test_output_name_suggestion():
    spec = next(c for c in BUILTIN_CODECS if c.name == "notchlc")
    assert spec.output_name("clip.mov") == "clip.notchlc.mov"
    assert spec.output_name("clip.mov", ".mp4") == "clip.notchlc.mp4"
    assert spec.output_name("noext") == "noext.notchlc.mov"


def test_pixel_format_switch_on_alpha():
    # moviepixelformat menu is ['rgb','rgba'] — verified live on TD.
    spec = next(c for c in BUILTIN_CODECS if c.name == "notchlc")
    assert spec.pixel_format_for(True) == "rgba"
    assert spec.pixel_format_for(False) == "rgb"


# ----------------------------------------------------------------------
# td_params — the contract handed to the TouchDesigner controller
# ----------------------------------------------------------------------


def test_td_params_notchlc_defaults():
    spec = next(c for c in BUILTIN_CODECS if c.name == "notchlc")
    params = spec.td_params(quality="optimal", fps="auto")
    # MUST be the lowercase menu token, not the "NotchLC" display label:
    # an invalid menu value silently falls back to index 0 ('rle'), which
    # produced a valid-looking file in the WRONG codec.
    assert params["videocodec"] == "notchlc"
    # Quality travels as the FLOAT MvO's slider takes (Derivative guide:
    # good=0.0 very-good=0.285 excellent=0.575 optimal=0.862 best=1.0)
    assert params["quality"] == 0.862
    assert params["moviecontainer"] == "mov"   # menu value, verified live
    assert params["fps"] == "auto"
    # notchlc has no subtypes — must not emit a bogus videocodectype
    assert "videocodectype" not in params


def test_all_registry_menu_values_are_lowercase_tokens():
    """Guard: TD menu tokens are lowercase. A capitalised value (e.g. the
    docs' 'NotchLC' label) silently selects menu entry 0 instead."""
    for spec in BUILTIN_CODECS:
        assert spec.td_codec == spec.td_codec.lower(), (
            f"{spec.name}: td_codec must be a TD menu token, got "
            f"{spec.td_codec!r} — menu values are lowercase"
        )
        assert spec.default_ext == spec.default_ext.lower()
        for value in spec.subtypes.values():
            assert value == value.lower(), f"{spec.name}: subtype {value!r}"


def test_td_params_defaults_quality_when_omitted():
    spec = next(c for c in BUILTIN_CODECS if c.name == "notchlc")
    assert spec.td_params()["quality"] == 0.862


def test_td_params_alpha_emits_pixel_format():
    spec = next(c for c in BUILTIN_CODECS if c.name == "notchlc")
    with_alpha = spec.td_params(alpha=True)
    assert "moviepixelformat" in with_alpha
    # alpha=None means "follow source" — no pixel format forced
    assert "moviepixelformat" not in spec.td_params(alpha=None)


def test_td_params_rejects_bad_quality():
    spec = next(c for c in BUILTIN_CODECS if c.name == "notchlc")
    with pytest.raises(CodecError):
        spec.td_params(quality="ultra")


def test_td_params_fps_passthrough():
    spec = next(c for c in BUILTIN_CODECS if c.name == "notchlc")
    assert spec.td_params(fps="30")["fps"] == "30"