"""vcon panel callbacks — the panel's logic, run inside TouchDesigner.

Loaded as a file-linked module DAT inside the vCon COMP. Widgets fire
into here via Offtoonscript0 (buttons) and Onvaluechangescript0 (fields).

LIVE-VERIFIED widget facts: config pars are on the INNER COMP (children
scan; op(name) self-matches the wrapper) and are First-uppercase: Value0
is the widget's value; Onvaluechangescript0 fires on any value change;
buttons fire Offtoonscript0 on press. The extension's busy property is
is_busy (lowercase) — the panel must NOT call a promoted-style Isbusy.
"""

import os

#: Codec table — distilled from src/vcon/codec_meta.py (TD menu tokens).
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

#: Movie extensions TD imports (docs.derivative.ca File_Types, verified).
MOVIE_EXTS = {".m4v", ".mkv", ".mov", ".mp4", ".hsp", ".notchlc", ".mpeg",
              ".mpg", ".avi", ".flv", ".m2ts", ".wmv", ".h265", ".vp8",
              ".vp9", ".3gp", ".mxf", ".ts", ".r3d"}

#: Batch queue: list of dicts {input, output, status, rel}
_queue = []


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
    if p is None:
        return None
    outer = p.op(name)
    if outer is None:
        return None
    for c in outer.children:
        if c.name == outer.name or c.isPanel:
            return c
    return outer


def _val(name):
    """Read a widget's Value0."""
    w = widget(name)
    if w is None:
        return None
    try:
        return w.par.Value0.eval()
    except Exception:
        return None


def _output_name(input_path, codec, subtype=None):
    """clip.mov + prores 422hq -> clip.prores422hq.mov (same folder)."""
    folder = os.path.dirname(input_path)
    stem = os.path.splitext(os.path.basename(input_path))[0]
    tag = subtype if subtype and subtype != "none" else codec
    ext = CONTAINERS.get(codec, ".mov")
    return os.path.join(folder, f"{stem}.{tag}{ext}")


def _unique_output(path):
    """Never overwrite: clip.notchlc.mov exists -> 'clip.notchlc (2).mov'."""
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


def _derive_output(src, dst, codec, subtype):
    """The output path a job would get, given current widget state."""
    derived = _output_name(src, codec, subtype)
    if dst and os.path.isdir(dst):
        return os.path.join(dst, os.path.basename(derived))
    return derived


def _is_movie(path):
    return os.path.splitext(path)[1].lower() in MOVIE_EXTS


# ---------------------------------------------------------------------
# Live preview of the output filename
# ---------------------------------------------------------------------

def PreviewOutput():
    """Update the read-only OUTPUT label from current widget state.

    Called on any relevant widget change. Shows the auto-named output the
    next START would create — including ' (2)' collision numbering.
    """
    try:
        src = _val("source")
        out_l = widget("output_l")
        if out_l is None:
            return
        if not src or not os.path.isfile(src):
            out_l.par.Label.val = ""
            return
        dst = _val("destination")
        codec = _val("codec_dd") or "notchlc"
        subtype = _val("subtype_dd")
        if subtype == "none":
            subtype = None
        out = _unique_output(_derive_output(src, dst, codec, subtype))
        out_l.par.Label.val = os.path.basename(out)
    except Exception:
        pass


def UpdateSubtypes():
    """Re-populate SUBTYPE (and FORMAT) for the selected codec.

    The subtype menu must only offer subtypes VALID for the chosen codec
    (Hap's menu has no ProRes entries; ProRes has no 'hapq') — the same
    per-codec filtering the CLI's registry enforces. FORMAT follows the
    same rule: ProRes menus differ PER SUBTYPE (verified live), and only
    NotchLC/Hap/CineForm expose rgb/rgba.

    Wired to the codec dropdown's Onvaluechangescript0 by the builder.
    """
    try:
        codec = _val("codec_dd") or "notchlc"
        meta = CODECS.get(codec, {})
        sub_w = widget("subtype_dd")
        fmt_w = widget("format_dd")
        if sub_w is not None:
            subs = ["none"] + list(meta.get("subtypes", []))
            ok = setp_par(sub_w, "Menunames", " ".join(subs))
            ok &= setp_par(sub_w, "Menulabels", " ".join(subs))
            if ok:
                sub_w.par.Value0.val = "none"
        if fmt_w is not None:
            if codec == "prores":
                # subtype not chosen yet: 422 defaults (the common case)
                fmts = PRORES_PIXEL_FORMATS.get("prores422",
                                                ["yuv4228bit"])
            else:
                fmts = ["none"] + list(meta.get("pixel_formats", []))
            ok = setp_par(fmt_w, "Menunames", " ".join(fmts))
            ok &= setp_par(fmt_w, "Menulabels", " ".join(fmts))
            if ok:
                fmt_w.par.Value0.val = "none"
        # QUALITY is NotchLC-only: grey it out (label + value) for others
        q_w = widget("quality_dd")
        if q_w is not None:
            has_q = bool(meta.get("qualities"))
            try:
                q_w.par.enable = 1 if has_q else 0
            except Exception:
                pass
        # RESOLUTION switch: show custom fields only for 'custom'
        _update_res_fields()
        # refresh the OUTPUT preview for the new codec context
        PreviewOutput()
    except Exception as exc:
        note(f"subtype update failed: {exc}")


def _update_res_fields():
    """Show the SCALE dropdown only when RES is set to 'scaled'.

    Uses the OUTER wrapper's Layout par (display=0 collapses the widget's
    width/height to nothing in the parent panel — verified: widget config
    pars live on the INNER, layout on the outer). If display is missing,
    x-placement is the fallback.
    """
    mode = str(_val("resmode_dd") or "unscaled").strip().lower()
    show = 1 if mode == "scaled" else 0
    outer = panel().op("scale_dd") if panel() is not None else None
    if outer is not None:
        try:
            outer.par.display = show
            return
        except Exception:
            pass
        try:
            outer.par.x = 320 if show else 1200   # off-panel when hidden
        except Exception as exc:
            note(f"display toggle failed: {exc}")


def _res_value():
    """Resolution args for Transcode(): ('auto', scale) from the panel.

    RES widget: 'unscaled' sends nothing (source size preserved);
    'scaled' sends the chosen factor — the CONTROLLER computes the final
    WxH from the movie's real dimensions after load (the panel cannot
    know them pre-load). Returns (resolution, scale)."""
    mode = str(_val("resmode_dd") or "unscaled").strip().lower()
    if mode != "scaled":
        return "auto", None
    factor = str(_val("scale_dd") or "1").strip()
    try:
        return "auto", float(factor)
    except (TypeError, ValueError):
        return "auto", None


def setp_par(inner, par_name, value):
    """setp without the noisy miss-print (used for menu re-population)."""
    try:
        getattr(inner.par, par_name).val = value
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------

def Start():
    """Submit one job (file source) or a batch (folder source)."""
    src = _val("source")
    dst = _val("destination")
    codec = _val("codec_dd") or "notchlc"
    subtype = _val("subtype_dd")
    quality = _val("quality_dd")
    fmt = _val("format_dd")
    fps = str(_val("fps_f") or "auto").strip().lower()
    fitmode = _val("fit_dd")
    res, scale = _res_value()

    if fps in ("", "keep", "auto"):
        fps = "auto"
    if fmt == "none":
        fmt = None
    if subtype == "none":
        subtype = None
    if quality and not CODECS.get(codec, {}).get("qualities"):
        quality = None

    if not src:
        note("pick a source file or folder first")
        return

    # ---- folder source: enqueue every movie in the tree -----------------
    if os.path.isdir(src):
        items = _scan_movies(src)
        if not items:
            note("no movie files found in that folder")
            return
        for inp, rel in items:
            out = _unique_output(_derive_output(inp, dst, codec, subtype))
            _queue.append({"input": inp, "output": out, "status": "queued",
                           "rel": rel})
        note(f"queued {len(items)} file(s) — press START again to run")
        _refresh_queue()
        return

    if not os.path.isfile(src):
        note("source not found")
        return

    out = _unique_output(_derive_output(src, dst, codec, subtype))
    ok = ext().Transcode(
        input_path=src,
        output_path=out,
        codec=codec,
        subtype=subtype,
        quality=quality,
        fps=fps,
        pixel_format=fmt,
        resolution=res,
        scale=scale,
        fit=fitmode,
    )
    if not ok:
        note("busy — job refused")
    else:
        _mark_running(out)
        note(f"encoding {os.path.basename(out)}")


def _run_next():
    """Dequeue the next batch job and submit it (called when idle)."""
    e = ext()
    if e.is_busy:
        return
    nxt = None
    for item in _queue:
        if item["status"] == "queued":
            nxt = item
            break
    if nxt is None:
        return
    src = nxt["input"]
    base = os.path.basename(src)
    dst = _val("destination")
    codec = _val("codec_dd") or "notchlc"
    subtype = _val("subtype_dd")
    if subtype == "none":
        subtype = None
    quality = _val("quality_dd")
    fmt = _val("format_dd")
    fps = str(_val("fps_f") or "auto").strip().lower()
    fitmode = _val("fit_dd")
    res, scale = _res_value()
    if fps in ("", "keep", "auto"):
        fps = "auto"
    if fmt == "none":
        fmt = None
    if quality and not CODECS.get(codec, {}).get("qualities"):
        quality = None
    ok = e.Transcode(
        input_path=src,
        output_path=nxt["output"],
        codec=codec,
        subtype=subtype,
        quality=quality,
        fps=fps,
        pixel_format=fmt,
        resolution=res,
        scale=scale,
        fit=fitmode,
    )
    if ok:
        nxt["status"] = "running"
        _refresh_queue()
    else:
        # busy: try again next time the panel pings
        pass


def PauseResume():
    """Toggle pause/resume on the active job."""
    e = ext()
    if not e.is_busy:
        note("nothing running")
        return
    if getattr(e, "_paused", False):
        e.Resume()
    else:
        e.Pause()


def Stop():
    """Cancel the active job and clear the batch queue."""
    ext().Cancel()
    for item in _queue:
        if item["status"] in ("queued", "running"):
            item["status"] = "cancelled"
    _refresh_queue()
    note("cancelled")


# ---------------------------------------------------------------------
# Batch queue
# ---------------------------------------------------------------------

def _scan_movies(folder, recursive=True):
    """[(path, rel)] for every movie file under folder (sorted)."""
    import glob
    out = []
    if recursive:
        for path in sorted(glob.glob(os.path.join(folder, "**", "*"),
                                     recursive=True)):
            if os.path.isfile(path) and _is_movie(path):
                out.append((path, os.path.relpath(path, folder)))
    else:
        for path in sorted(glob.glob(os.path.join(folder, "*"))):
            if os.path.isfile(path) and _ismovie(path):
                out.append((path, os.path.relpath(path, folder)))
    return out


def _refresh_queue():
    """Redraw the batch queue table (the lister widget's source DAT)."""
    t = panel().op("queue_table")
    if t is None:
        return
    t.clear()
    t.appendRow(["#", "file", "status"])
    for i, item in enumerate(_queue, 1):
        t.appendRow([str(i), os.path.basename(item["input"]),
                     item["status"]])


def _mark_running(output_path):
    for item in _queue:
        if item["output"] == output_path and item["status"] == "queued":
            item["status"] = "running"
            break
    _refresh_queue()


def _mark_done(output_path):
    """Mark the queue row whose output matches; enqueue the next job."""
    done = False
    for item in _queue:
        if item["output"] == output_path:
            item["status"] = "done"
            done = True
    if done:
        _refresh_queue()
        _run_next()


def _on_job_done(output_path):
    """Poll-based completion hook for the panel: refresh + run next."""
    _mark_done(output_path)


def onFrame():
    """Panel-level Execute DAT tick: feed the batch loop + auto-refresh.

    When the controller goes idle and queue rows remain queued, submit the
    next job. When a running row's output file exists and the controller
    is idle, the job finished — mark done, then next.
    """
    try:
        e = ext()
    except Exception:
        return
    if e.is_busy:
        return
    # finished detection: a running row whose output now exists
    for item in list(_queue):
        if item["status"] == "running" and os.path.exists(item["output"]):
            item["status"] = "done"
    _run_next()
    _refresh_queue()


# ---------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------

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


def NormalizeDestination():
    """Show only the selected FOLDER in the destination widget."""
    w = widget("destination")
    if w is None:
        return
    v = w.par.Value0.eval()
    if v and os.path.isfile(v):
        w.par.Value0.val = os.path.dirname(v)


def note(text):
    """Panel-local feedback line — printed to the textport."""
    print(f"[panel] {text}")


def pixel_formats_for(codec, subtype=None):
    """Per-subtype pixel formats (ProRes menus differ per subtype)."""
    if codec == "prores":
        return PRORES_PIXEL_FORMATS.get(subtype, ["yuv4228bit"])
    return CODECS.get(codec, {}).get("pixel_formats", ["rgb"])
