"""vcon panel callbacks — the panel's logic, run inside TouchDesigner.

Loaded as a file-linked module DAT inside the vCon COMP. Widget callbacks
call into here via Global OP Shortcut: op.vcon.op('panel_callbacks').module.<fn>().

LIVE-VERIFIED (probes 2026-09-13): widget config pars are on the INNER
COMP (child of the loadTox wrapper, same name as the wrapper) and are
First-uppercase: Value0 holds the widget's value, Label its label text.
Everything here uses external widget parameters only — internals are
never touched (they're clone-managed and wiped on update).
"""

import os

#: Codec table for the panel's dropdowns — the same knowledge the CLI's
#: registry encodes (src/vcon/codec_meta.py), distilled to TD menu tokens.
#: KEEP IN STEP with codec_meta.py — regenerate via toe/gen_codec_table.py.
CODECS = {
    "notchlc": {
        "label": "NotchLC",
        "subtypes": [],
        "pixel_formats": ["rgb", "rgba"],
        "alpha_format": "rgba",
        "qualities": ["good", "very-good", "excellent", "optimal", "best"],
    },
    "hap": {
        "label": "Hap",
        "subtypes": ["hap", "hapq", "hapr", "haphdr"],
        "pixel_formats": ["rgb", "rgba"],
        "alpha_format": "rgba",
        "qualities": [],
    },
    "cineform": {
        "label": "GoPro CineForm",
        "subtypes": [],
        "pixel_formats": ["rgba"],
        "alpha_format": "rgba",
        "qualities": [],
    },
    "prores": {
        "label": "Apple ProRes",
        "subtypes": ["prores422proxy", "prores422lt", "prores422",
                     "prores422hq", "prores4444", "prores4444xq"],
        "pixel_formats": [],
        "qualities": [],
    },
    "h264": {"label": "H.264", "subtypes": [], "qualities": [],
              "pixel_formats": ["yuv420", "yuv444p8bit"], "alpha_format": None},
    "h265": {"label": "H.265", "subtypes": [], "qualities": [],
              "pixel_formats": ["yuv420", "yuv420p10bit", "yuv444p8bit",
                                "yuv444p10bit"],
              "alpha_format": None},
    "av1": {"label": "AV1", "subtypes": [], "qualities": [],
             "pixel_formats": ["yuv420", "yuv420p10bit"], "alpha_format": None},
}

PRORES_PIXEL_FORMATS = {
    "prores422proxy": ["yuv4228bit", "yuv42210bit", "yuv42212bit"],
    "prores422lt": ["yuv4228bit", "yuv42210bit", "yuv42212bit"],
    "prores422": ["yuv4228bit", "yuv42210bit", "yuv42212bit"],
    "prores422hq": ["yuv4228bit", "yuv42210bit", "yuv42212bit"],
    "prores4444": ["yuv44410bit", "yuva444412bit"],
    "prores4444xq": ["yuv44410bit", "yuva444412bit"],
}

CONTAINERS = {
    "notchlc": ".mov", "hap": ".mov", "cineform": ".mov", "prores": ".mov",
    "h264": ".mp4", "h265": ".mp4", "av1": ".mp4",
}


def ext():
    """The vCon extension (Global OP Shortcut 'vcon' — set by the builder)."""
    return op.vcon.ext.Vcon


def panel():
    """The panel COMP: a child of vcon named 'panel'."""
    return op.vcon.op('panel')


def widget(name):
    """The INNER widget COMP of a named panel child (children scan —
    op(name) self-matches the wrapper, verified live)."""
    p = panel()
    outer = p.op(name)
    if outer is None:
        return None
    for c in outer.children:
        if c.name == outer.name or c.isPanel:
            return c
    return None


def _val(name):
    """Read a widget's Value0."""
    w = widget(name)
    return w.par.Value0.eval() if w is not None else None


def _output_name(input_path, codec, subtype=None):
    """clip.mov + prores 422hq -> clip.prores422hq.mov (same folder)."""
    folder = os.path.dirname(input_path)
    stem = os.path.splitext(os.path.basename(input_path))[0]
    tag = subtype if subtype and subtype != "none" else codec
    ext = CONTAINERS.get(codec, ".mov")
    return os.path.join(folder, f"{stem}.{tag}{ext}")


def _unique_output(path):
    """Never overwrite: clip.notchlc.mov exists -> 'clip.notchlc (2).mov'.

    The same auto-naming the reference transcoders use (their screenshots
    show 'GlowingNights_05 (2).mov'). The panel path bypasses the CLI's
    -y/-n overwrite prompts, so non-clobbering names are the safe default.
    """
    if not os.path.exists(path):
        return path
    folder = os.path.dirname(path)
    stem, ext = os.path.splitext(os.path.basename(path))
    n = 2
    while True:
        cand = os.path.join(folder, f"{stem} ({n}){ext}")
        if not os.path.exists(cand):
            return cand
        n += 1


def Start():
    """Read the panel widgets and submit one job through the extension."""
    src = _val("source")
    dst = _val("destination")
    codec = _val("codec_dd") or "notchlc"
    subtype = _val("subtype_dd")
    quality = _val("quality_dd")
    fmt = _val("format_dd")
    fps = str(_val("fps_f") or "auto").strip().lower()
    res = str(_val("res_f") or "auto").strip().lower()
    fitmode = _val("fit_dd")

    if not src or not os.path.isfile(src):
        note("pick a source file first")
        return

    if fps in ("", "keep", "auto"):
        fps = "auto"
    if res in ("", "keep", "auto"):
        res = "auto"

    derived = _output_name(src, codec, subtype)
    if dst and os.path.isdir(dst):
        # Destination is a FOLDER: the derived FILENAME joins into it.
        # (Passing the folder itself as the output file made movieout
        # error 'Filename missing extension' every frame — caught live.)
        out = os.path.join(dst, os.path.basename(derived))
    else:
        out = derived
    # Auto-name: never clobber — ' (2)', ' (3)', ... on collisions.
    out = _unique_output(out)

    # pixel format 'none' = let the codec/registry decide (auto)
    if fmt == "none":
        fmt = None
    if quality and not CODECS.get(codec, {}).get("qualities"):
        quality = None          # this codec has no quality ladder
    if subtype == "none":
        subtype = None

    ok = ext().Transcode(
        input_path=src,
        output_path=out,
        codec=codec,
        subtype=subtype,
        quality=quality,
        fps=fps,
        pixel_format=fmt,
        resolution=res,
        fit=fitmode,
    )
    note("job submitted" if ok else "busy — job refused")


def PauseResume():
    """Toggle pause/resume on the active job."""
    e = ext()
    if not e.Isbusy:
        note("nothing running")
        return
    if getattr(e, "_paused", False):
        e.Resume()
    else:
        e.Pause()


def Stop():
    """Cancel the active job."""
    ext().Cancel()
    note("cancelled")


def onDragDrop(info):
    """Drop Script entry: file/folder dropped onto the panel."""
    items = info.get("dropItems") if isinstance(info, dict) else None
    if not items:
        items = info["dropItems"] if hasattr(info, "__getitem__") else None
    if not items:
        return
    first = items[0]
    path = first if isinstance(first, str) else first.get("path", str(first))
    w = widget("source")
    if w is not None and path:
        w.par.Value0.val = path
        note("source set from drop")


def note(text):
    """Panel-local feedback line — printed to the textport.

    Deliberately NOT written to the Status par: the controller owns that
    (encode progress, errors, idle). The panel printing its own messages
    means they coexist instead of racing each other's writes.
    """
    print(f"[panel] {text}")


def pixel_formats_for(codec, subtype=None):
    """Per-subtype pixel formats (ProRes menus differ per subtype)."""
    if codec == "prores":
        return PRORES_PIXEL_FORMATS.get(subtype, ["yuv4228bit"])
    return CODECS.get(codec, {}).get("pixel_formats", ["rgb"])
