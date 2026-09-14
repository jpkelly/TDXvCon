"""vcon panel callbacks — the panel's logic, run inside TouchDesigner.

Loaded as a module DAT inside the panel COMP; the Execute DAT at the panel
level pulses updates, and panel widgets reach this code via callbacks that
resolve the extension through the upward parent() chain (the panel COMP is
a child of the vCon base COMP, so parent() lands on it wherever the whole
component is dropped).

Public surface (called by widgets' callbacks):
    Start(), PauseResume(), Stop(), onDragDrop(...)
"""

import os

#: Codec table for the panel's dropdowns — the same knowledge the CLI's
#: registry encodes (src/vcon/codec_meta.py), distilled to what the toe
#: needs: TD menu tokens, per-subtype pixel formats, quality ladder.
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
        # pixel formats vary BY SUBTYPE (verified live):
        #   422*  → yuv422 8/10/12bit   4444* → yuv44410 + yuva444412
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

#: Extension (.mov/.mp4) per codec — from the catalog's container data.
CONTAINERS = {
    "notchlc": ".mov", "hap": ".mov", "cineform": ".mov", "prores": ".mov",
    "h264": ".mp4", "h265": ".mp4", "av1": ".mp4",
}


def ctrl():
    """The vCon extension, found by walking up from this panel.

    parent() from a panel child resolves to the vCon base COMP wherever the
    component was dropped or renamed (documented in the extension docs).
    """
    return parent().ext.Vcon


def panel():
    """This panel COMP (the DAT this module lives in sits inside it)."""
    return parent().op("..") if parent().name == "panel_callbacks" else parent()


def _output_name(input_path, codec, subtype=None):
    """``clip.mov`` + prores 422hq → ``clip.prores422hq.mov`` (same folder)."""
    folder = os.path.dirname(input_path)
    stem = os.path.splitext(os.path.basename(input_path))[0]
    tag = subtype or codec
    ext = CONTAINERS.get(codec, ".mov")
    return os.path.join(folder, f"{stem}.{tag}{ext}")


def Start():
    """Read the panel widgets and submit one job through the extension."""
    ext = ctrl()
    p = panel()
    src = p.op("source").par.value0.eval()
    dst = p.op("destination").par.value0.eval()
    codec = p.op("codec").par.value0.eval()
    subtype = p.op("subtype").par.value0.eval() if p.op("subtype") else None
    quality = None
    qw = p.op("quality")
    if qw is not None and ext_codec_has_quality(codec):
        quality = qw.par.value0.eval()
    fmt = p.op("pixelformat").par.value0.eval() if p.op("pixelformat") else None
    fps_w = p.op("fps")
    fps = fps_w.par.value0.eval() if fps_w else "auto"
    if str(fps).strip().lower() in ("", "keep", "auto"):
        fps = "auto"
    res_w = p.op("resolution")
    res = res_w.par.value0.eval() if res_w else "auto"
    if str(res).strip().lower() in ("", "keep", "auto"):
        res = "auto"
    fit_w = p.op("fitmode")
    fit = fit_w.par.value0.eval() if fit_w else None

    if not src or not os.path.isfile(src):
        _status("pick a source file first")
        return
    out = dst if dst and os.path.isdir(dst) else _output_name(src, codec,
                                                             subtype)
    if res != "auto":
        out = out  # output path is folder-join; resolution only affects encode

    ok = ext.Transcode(
        input_path=src,
        output_path=out,
        codec=codec,
        subtype=subtype if subtype else None,
        quality=quality,
        fps=fps,
        pixel_format=fmt if fmt else None,
        resolution=res,
        fit=fit,
    )
    _status("job submitted" if ok else "busy — job refused")


def PauseResume():
    """Toggle pause/resume on the active job."""
    ext = ctrl()
    if ext.Isbusy:
        # paused check: the extension exposes _paused via Ispaused below
        if getattr(ext, "_paused", False):
            ext.Resume()
            _status("resumed")
        else:
            ext.Pause()
            _status("paused")


def Stop():
    """Cancel the active job."""
    ctrl().Cancel()
    _status("cancelled")


def ext_codec_has_quality(codec):
    return bool(CODECS.get(codec, {}).get("qualities"))


def pixel_formats_for(codec, subtype=None):
    """Per-subtype pixel formats (ProRes menus differ per subtype)."""
    if codec == "prores":
        return PRORES_PIXEL_FORMATS.get(subtype, ["yuv4228bit"])
    return CODECS.get(codec, {}).get("pixel_formats", ["rgb"])


def onDragDrop(info):
    """Container Drop Script entry: files/folders dropped onto the panel."""
    dropItems = info["dropItems"]
    first = dropItems[0] if dropItems else None
    if not first:
        return
    p = panel()
    if os.path.isdir(first):
        # a folder dropped: put it in the SOURCE (folder batch later uses it)
        p.op("source").par.value0.val = first
    else:
        p.op("source").par.value0.val = first


def _status(text):
    """Small helper: write to the panel's own status label (not the COMP's)."""
    p = panel()
    lab = p.op("statusline")
    if lab is not None:
        try:
            lab.par.label.eval()
            lab.par.label.val = text
        except Exception:
            pass