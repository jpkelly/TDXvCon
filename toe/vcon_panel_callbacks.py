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
        # VERIFIED LIVE (codec_meta): haphdr offers rgbu/rgbs — NOT rgb/rgba
        # — and exposes NO alpha format. Per-subtype menus mirror TD.
        "pixel_formats_by_subtype": {
            "hap": ["rgb", "rgba"],
            "hapq": ["rgb", "rgba"],
            "hapr": ["rgb", "rgba"],
            "haphdr": ["rgbu", "rgbs"],
        },
        "alpha_format": "rgba",
        "alpha_format_by_subtype": {"haphdr": None},
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
        "default_subtype": "prores4444",   # JP spec
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

#: Human-readable labels for the FORMAT dropdown — Menunames keep TD's
#: exact menu tokens (what the encoder needs); Menulabels carry the
#: description (what the user needs). The 'a' in yuva = ALPHA — the entry
#: ProRes 4444 users are looking for (JP: "alpha not apparent").
FORMAT_LABELS = {
    "rgb": "RGB",
    "rgba": "RGB + Alpha",
    "rgbu": "RGB (HDR)",
    "rgbs": "RGB (HDR scRGB)",
    "yuv4228bit": "YUV 4:2:2 8-bit",
    "yuv42210bit": "YUV 4:2:2 10-bit",
    "yuv42212bit": "YUV 4:2:2 12-bit",
    "yuv44410bit": "YUV 4:4:4 10-bit",
    "yuva444412bit": "YUVA 4:4:4 12-bit + Alpha",
    "yuv420": "YUV 4:2:0 8-bit",
    "yuv420p10bit": "YUV 4:2:0 10-bit",
    "yuv444p8bit": "YUV 4:4:4 8-bit",
    "yuv444p10bit": "YUV 4:4:4 10-bit",
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
    """A named panel child — TOP-LEVEL only (JP rule: configure top-level
    parameters; the builder now places widget COMPs directly in the
    panel). No inner-child searching: if the name resolves, that COMP
    is the widget we configure. Kept as a function so call sites stay
    stable and any future structural change has one choke point."""
    p = panel()
    if p is None:
        return None
    return p.op(name)


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
    """Update the read-only OUTPUT field from current widget state.

    Called on any relevant widget change. Shows the auto-named output the
    next START would create — including ' (2)' collision numbering.

    LIVE-VERIFIED (probe 4): the label widget renders its WIDGETLABEL
    (title) as the displayed text — writes to the 'Label' config par
    never showed. Full path: destination folder + derived file name.
    """
    try:
        src = _val("source")
        out_l = widget("output_l")
        if out_l is None:
            return
        if not src or not os.path.isfile(src):
            out_l.par.Widgetlabel.val = "(pick a source)"
            return
        dst = _val("destination")
        dst_dir = dst if dst and os.path.isdir(dst) else (
            os.path.dirname(dst) if dst else None)
        codec = _val("codec_dd") or "notchlc"
        subtype = _val("subtype_dd")
        if subtype == "none":
            subtype = None
        out = _unique_output(_derive_output(src, dst_dir, codec, subtype))
        out_l.par.Widgetlabel.val = out
    except Exception as exc:
        note(f"preview failed: {exc}")


def UpdateSubtypes():
    """Re-populate SUBTYPE and FORMAT for the selected codec — no 'none'.

    JP spec: 'none' is never offered. Every codec with subtypes defaults
    to its FIRST real subtype (Hap -> hap, ProRes -> prores422proxy);
    codecs without subtypes (NotchLC, CineForm, delivery codecs) grey the
    dropdown out — the same 'empty menu = grey' rule MvO uses. FORMAT
    offers the codec's real pixel formats with the first as default
    (Hap: rgb + rgba, rgb selected; NotchLC: rgb + rgba; CineForm: rgba;
    ProRes: per-SUBTYPE menus, 422 set while no subtype is finer).
    """
    try:
        codec = _val("codec_dd") or "notchlc"
        meta = CODECS.get(codec, {})
        sub_w = widget("subtype_dd")
        fmt_w = widget("format_dd")
        # ---- SUBTYPE: real options only; grey out when there are none.
        if sub_w is not None:
            subs = list(meta.get("subtypes", []))
            if subs:
                setp_par(sub_w, "Menunames", " ".join(subs))
                setp_par(sub_w, "Menulabels", " ".join(subs))
                try:
                    default = meta.get("default_subtype", subs[0])
                    if sub_w.par.Value0.val not in subs:
                        sub_w.par.Value0.val = default
                except Exception:
                    pass
                _grey_out(sub_w, False)
            else:
                _grey_out(sub_w, True)
        # ---- FORMAT: per-subtype when the codec defines them (Hap's
        # haphdr offers rgbu/rgbs — verified live), else the codec's
        # list. First entry is the default. Grey out only if empty.
        if fmt_w is not None:
            by_sub = meta.get("pixel_formats_by_subtype", {})
            cur_sub = _val("subtype_dd")
            if by_sub and cur_sub in by_sub:
                fmts = list(by_sub[cur_sub])
                grey = False
            elif codec == "prores":
                fmts = list(PRORES_PIXEL_FORMATS.get(
                    cur_sub, PRORES_PIXEL_FORMATS.get("prores422", [])))
                grey = False
            else:
                fmts = list(meta.get("pixel_formats", []))
                grey = not fmts
            if fmts:
                setp_par(fmt_w, "Menunames", " ".join(fmts))
                setp_par(fmt_w, "Menulabels",
                         " ".join(f"'{FORMAT_LABELS.get(f, f)}'" for f in fmts))
                try:
                    if fmt_w.par.Value0.val not in fmts:
                        fmt_w.par.Value0.val = fmts[0]
                except Exception:
                    pass
            _grey_out(fmt_w, grey)
        # QUALITY: NEVER greyed (JP) — the slider always affects MvO's
        # quality par for whatever codec is selected; the per-codec
        # 'ladder' note is documentation, not a UI state.
        _update_res_fields()
        PreviewOutput()
    except Exception as exc:
        note(f"subtype update failed: {exc}")


def _grey_out(inner, grey):
    """Disable a widget's interaction (greyed like MvO's empty menus).

    Display/enable pars on these widgets are STRING MENUS
    (['off','on']) — integer writes select menu INDEX 0, which can be
    'on'. Write tokens; fall back to ints only if no menu exists.
    """
    for cand in ("enable", "Enable"):
        par = getattr(inner.par, cand, None)
        if par is None:
            continue
        try:
            menus = list(getattr(par, "menuNames", None) or [])
            if menus:
                par.val = "off" if grey else "on"
            else:
                par.val = 0 if grey else 1
            return
        except Exception:
            continue


def OnQualityChanged():
    """QUALITY slider dragged -> set MvO's quality slider LIVE.

    Wired to the slider's Onvaluechangescript0 (fires on every drag
    tick). Works for ANY codec, ALWAYS enabled (JP: never greyed —
    MvO's quality par is general).
    """
    try:
        v = _val("quality_s")
        ext().Setquality(v)
    except Exception as exc:
        note(f"quality sync failed: {exc}")


def OnSelectionChanged():
    """CODEC/SUBTYPE/FORMAT dropdown changed -> apply to MvO LIVE.

    JP: changing a dropdown must show in MvO's parameters immediately —
    the panel IS the parameter editor. Fires from all three dropdowns'
    Onvaluechangescript0; routes through the extension's Setparams(),
    which reuses the menu read-back verification (invalid tokens fail
    loudly, never silently fall back to entry 0). Idle-guarded on the
    controller side: an encode in flight keeps its settings.
    """
    try:
        codec = _val("codec_dd") or "notchlc"
        meta = CODECS.get(codec, {})
        subtype = _validate_choice(codec, "subtype", _val("subtype_dd"))
        fmt = _validate_choice(codec, "format", _val("format_dd"))
        ext().Setparams(
            codec=codec,
            subtype=subtype if subtype else None,
            pixel_format=fmt if fmt else None,
            container=CONTAINERS.get(codec),
        )
    except Exception as exc:
        note(f"selection sync failed: {exc}")


def _update_res_fields():
    """Live-fit wiring + SCALE visibility, driven by the SCALED toggle.

    Two effects when the toggle flips (JP: wiring should visibly change
    AT THE SWITCH, not at job time):
      - SCALED  -> controller wires moviein -> fit -> movieout NOW
                   (fit configured with the chosen mode; a later job only
                   sets the exact WxH once the movie's size is known)
      - UNSCALED-> controller rewires moviein -> movieout NOW
    Plus: the SCALE dropdown shows/hides with the toggle.
    """
    mode = _val("scaled_t")
    # buttonToggle's Value0 is a BOOLEAN (0/1), not a string — comparing
    # to 'scaled' never matched, so the toggle silently did nothing.
    scaled = bool(mode)
    # 1) rewire NOW through the extension (toggle state is advisory; the
    #    controller re-applies per job, so a busy encoder is unaffected).
    try:
        ext().Setfitpath(scaled)
    except Exception as exc:
        note(f"fit rewire failed: {exc}")
    # 2) SCALE dropdown visibility
    outer = panel().op("scale_dd") if panel() is not None else None
    if outer is not None:
        try:
            # OUTER-wrapper Layout 'display' is a TOGGLE (TDParameterHelp:
            # containerCOMP.display parType Toggle) — boolean 0/1, NOT a
            # string menu. (The earlier token write did nothing.)
            outer.par.display.val = 1 if scaled else 0
        except Exception:
            try:
                outer.par.x = 270 if scaled else 1200
            except Exception as exc:
                note(f"display toggle failed: {exc}")


def _res_value():
    """Resolution args for Transcode(): ('auto', scale) from the panel.

    The SCALED toggle drives everything: unscaled sends nothing (source
    size preserved); scaled sends the chosen factor — the CONTROLLER
    computes the final WxH from the movie's real dimensions after load.
    Returns (resolution, scale)."""
    mode = _val("scaled_t")
    # buttonToggle Value0 is BOOLEAN (0/1) — not a menu string.
    if not bool(mode):
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

def _validate_choice(codec, kind, value, allow_empty=True):
    """Widget values must be VALID for the current codec before submit.

    A greyed widget keeps whatever Value0 it last held — a stale subtype
    from a previous codec selection. Filter it here so junk can never
    reach the encoder: return the value if legal for this codec, else
    None (or the codec default when allow_empty=False).
    """
    meta = CODECS.get(codec, {})
    if kind == "subtype":
        legal = list(meta.get("subtypes", []))
    else:
        by_sub = meta.get("pixel_formats_by_subtype", {})
        if by_sub:
            cur = _val("subtype_dd")
            legal = list(by_sub.get(cur,
                                    list(meta.get("pixel_formats", []))))
        elif codec == "prores":
            cur = _val("subtype_dd")
            legal = list(PRORES_PIXEL_FORMATS.get(
                cur, PRORES_PIXEL_FORMATS.get("prores422", [])))
        else:
            legal = list(meta.get("pixel_formats", []))
    if value in legal:
        return value
    return legal[0] if (not allow_empty and legal) else None


def Start():
    """Submit one job (file source) or a batch (folder source)."""
    src = _val("source")
    dst = _val("destination")
    codec = _val("codec_dd") or "notchlc"
    subtype = _validate_choice(codec, "subtype", _val("subtype_dd"))
    quality = _val("quality_s")   # 0-1 float straight to MvO
    fmt = _validate_choice(codec, "format", _val("format_dd"))
    fps = str(_val("fps_f") or "auto").strip().lower()
    fitmode = _val("fit_dd")
    res, scale = _res_value()

    if fps in ("", "keep", "auto"):
        fps = "auto"
    if codec != "notchlc":
        quality = None          # only NotchLC documents a quality ladder

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

    # DESTINATION may hold either a folder OR the previous output path
    # (we write the derived file path into it for display). Take its
    # directory as the real destination.
    dst_dir = dst if dst and os.path.isdir(dst) else (
        os.path.dirname(dst) if dst else None)
    out = _unique_output(_derive_output(src, dst_dir, codec, subtype))
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
    # destination widget holds a full output path — its folder is the target
    dst = os.path.dirname(dst) if dst else None
    codec = _val("codec_dd") or "notchlc"
    subtype = _validate_choice(codec, "subtype", _val("subtype_dd"))
    quality = _val("quality_s")   # 0-1 float straight to MvO
    fmt = _validate_choice(codec, "format", _val("format_dd"))
    fps = str(_val("fps_f") or "auto").strip().lower()
    fitmode = _val("fit_dd")
    res, scale = _res_value()
    if fps in ("", "keep", "auto"):
        fps = "auto"
    if codec != "notchlc":
        quality = None          # only NotchLC has a quality slider in MvO
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
    """DESTINATION stays a FOLDER path (its browser widget requires it).

    JP: the derived FILE name should not be crammed into the folder
    field (the folder browser re-normalizes full paths away — that's
    why the filename never showed). The filename lives in the
    read-only OUTPUT field (output_l), updated by PreviewOutput().
    """
    try:
        dst_w = widget("destination")
        if dst_w is None:
            return
        v = dst_w.par.Value0.eval()
        if v and os.path.isfile(v):
            dst_w.par.Value0.val = os.path.dirname(v)
    except Exception as exc:
        note(f"destination display: {exc}")


def note(text):
    """Panel-local feedback line — printed to the textport."""
    print(f"[panel] {text}")


def pixel_formats_for(codec, subtype=None):
    """Per-subtype pixel formats (ProRes menus differ per subtype)."""
    if codec == "prores":
        return PRORES_PIXEL_FORMATS.get(subtype, ["yuv4228bit"])
    return CODECS.get(codec, {}).get("pixel_formats", ["rgb"])
