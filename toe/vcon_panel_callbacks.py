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

#: last source-rate seen by the onFrame FPS display (SOURCE mode)
_last_src_fps = None

#: row-click inspector state: the clicked item + load ticks (the
#: Media File Info DAT provides the metadata; JP 2026-09-14: click a
#: queue row -> name / resolution / frame rate / codec in output_l)
_inspect_item = None
_inspect_ticks = 0
_noted_table = False   # one-shot raw-table dump for label verification
_last_sel = ""         # last lister Selectedrows seen (poll fallback)
_selected_path = None  # input path of the last clicked row (remove_b target)


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
        out_l = widget("output_l")
        if out_l is None:
            return
        # SOURCE field removed (JP: drops/+ADD are the way in). Derive
        # from the first QUEUED item — that's what the next encode makes.
        src = _queue[0]["input"] if _queue else None
        if not src or not os.path.isfile(src):
            out_l.par.Widgetlabel.val = "(queue is empty — add files)"
            return
        dst = _val("destination")
        dst_dir = dst if dst and os.path.isdir(dst) else (
            os.path.dirname(dst) if dst else None)
        codec = _val("codec_dd") or "notchlc"
        subtype = _validate_choice(codec, "subtype", _val("subtype_dd"))
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
        # ---- SUBTYPE: real options only; CLEAR + grey out when none.
        # JP bug report: after selecting Hap (subtypes appear), choosing
        # h264/h265/av1/cineform left 'hap' selectable — the grey-out
        # never landed and the stale menu/value survived. Fix: when a
        # codec has NO subtypes, CLEAR the menu (empty), reset Value0,
        # and grey out — a disabled, visibly-empty control can't offer
        # or keep a stale option.
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
                setp_par(sub_w, "Menunames", "")
                setp_par(sub_w, "Menulabels", "")
                try:
                    sub_w.par.Value0.val = ""
                except Exception:
                    pass
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
    Tries BOTH the builtin Panel 'enable' and the widget 'Enable'
    custom par; if neither exists, say so (a silent return here is how
    stale subtypes stayed clickable — JP bug report).
    """
    hit = False
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
            hit = True
        except Exception:
            continue
    if not hit:
        note(f"grey-out failed on {inner.name}: no enable par")


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
    Plus: the SCALE dropdown shows/hides with the toggle. The SCALE/FIT/
    W-H choices also push LIVE into the fit TOP (OnFitChanged below —
    the panel IS the parameter editor), and the visibility state
    re-derives from the actual widget values.
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
    # 2) SCALE + FIT + W/H fields show/hide. When SCALING is OFF there
    #    is nothing to configure (fit TOP bypassed) — all hidden. When
    #    ON: SCALE + FIT show; the W/H fields show ONLY for Custom
    #    (an absolute output resolution — JP).
    scaled_on = 1 if scaled else 0
    for name, show in (("scale_dd", scaled_on), ("fit_dd", scaled_on)):
        outer = panel().op(name) if panel() is not None else None
        if outer is None:
            continue
        try:
            outer.par.display.val = show
        except Exception:
            try:
                outer.par.x = 270 if show else 1200
            except Exception as exc:
                note(f"display toggle failed ({name}): {exc}")
    custom = (scaled and str(_val("scale_dd") or "") == "custom")
    for name in ("resw_f", "resh_f"):
        outer = panel().op(name) if panel() is not None else None
        if outer is None:
            continue
        try:
            outer.par.display.val = 1 if custom else 0
        except Exception:
            try:
                outer.par.x = 440 if custom else 1200
            except Exception as exc:
                note(f"display toggle failed ({name}): {exc}")
    # 3) LIVE push: the current SCALE/FIT/W-H choice into the fit TOP
    #    (the panel IS the parameter editor — the network updates at
    #    the SWITCH, not just at job time).
    if scaled:
        try:
            OnFitChanged()
        except Exception as exc:
            note(f"live fit push failed: {exc}")


def OnFitChanged():
    """SCALE / FIT / W-H widget hook → fit TOP, LIVE.

    Called by Onvaluechangescript0 on scale_dd / fit_dd / resw_f /
    resh_f (wired by the builder). Pushes the current choice through
    Setfitparams so the fit TOP's Output Resolution / Fit / custom
    WxH pars move immediately — JP: the panel IS the parameter editor.
    """
    scaled = bool(_val("scaled_t"))
    scaled = scaled and not ext().is_busy
    if not scaled:
        return          # fit TOP bypassed (or mid-encode) — nothing to push
    choice = str(_val("scale_dd") or "").strip()
    fitmode = str(_val("fit_dd") or "").strip() or None
    w = str(_val("resw_f") or "").strip()
    h = str(_val("resh_f") or "").strip()
    if choice == "custom":
        if w.isdigit() and h.isdigit() and int(w) > 0 and int(h) > 0:
            ext().Setfitparams(scale=choice, fit=fitmode, w=w, h=h)
        else:
            note("custom resolution needs valid W and H in the fields")
    elif choice:
        ext().Setfitparams(scale=choice, fit=fitmode)


def OnFpsChanged():
    """FPS field hook -> MvO's fps par, LIVE (JP: the field changes the
    par — same live-editor pattern as the QUALITY slider). 'auto'
    resolves to the loaded source's rate when one is available.
    """
    v = str(_val("fps_f") or "").strip()
    try:
        ext().Setfps(v)
    except Exception as exc:
        note(f"fps set failed: {exc}")


def _fps_source_mode():
    """True when the FPS mode toggle is OFF: use the SOURCE's own rate.

    fps_t (JP's hand-added toggle): ON = CUSTOM (the field drives MvO's
    fps par), OFF = SOURCE. No toggle in this build (pre-capture):
    False — the field stays a free custom editor, exactly as before.
    """
    v = _val("fps_t")
    if v is None:
        return False
    return not bool(v)


def _source_fps():
    """The loaded source's frame rate — the Info CHOP's sample_rate
    channel (the verified source: Movie File In has no fps par).
    None when nothing is loaded / the channel is unreadable."""
    try:
        sr = float(ext().info["sample_rate"][0])
        if sr > 0:
            return sr
    except Exception:
        pass
    return None


def OnFpsModeChanged():
    """fps_t toggle hook (JP 2026-09-14):
      OFF = SOURCE: the FPS field is DISABLED and displays the loaded
             source's rate (Info CHOP sample_rate); MvO's fps par
             follows it; every job encodes at its own file's rate.
      ON  = CUSTOM: the FPS field is ENABLED and two-way with MvO's
             fps par (the live-editor pattern).
    """
    source = _fps_source_mode()
    w = widget("fps_f")
    if w is None:
        return
    # LIVE-VERIFIED (JP 2026-09-14): the FPS field is a fieldString —
    # its interaction disable is STRINGFIELDREADONLY (a Boolean: writes
    # are ints 0/1, NEVER the string 'off', which coerces True on
    # Toggles). The generic enable par does NOT stop typing in a
    # string field (first attempt: field stayed editable).
    try:
        w.par.Stringfieldreadonly.val = 1 if source else 0
    except Exception as exc:
        note(f"fps field readonly failed: {exc}")
        _grey_out(w, source)      # legacy fallback (enable par)
    if source:
        # MvO follows the source's rate; the field displays it
        # (readonly — display-only until the mode flips back)
        SyncFpsField()
    else:
        # CUSTOM: the field is the authority — push it to MvO now
        OnFpsChanged()


def SyncFpsField():
    """Seed the FPS field per MODE (runs at build end, AFTER the capture
    bake, and whenever the mode/source rate changes):
      SOURCE mode — display the loaded source's rate (sample_rate) and
        push MvO's par to follow it (JP: 'move out parameter with the
        FPS of the source'). Best available when nothing is loaded:
        MvO's current par.
      CUSTOM mode — display MvO's fps par (the field IS the par's editor).
    The field write fires OnFpsChanged -> Setfps with the same value —
    idempotent, no loop.
    """
    w = widget("fps_f")
    if w is None:
        return
    if _fps_source_mode():
        v = _source_fps()
        if v is None:
            try:
                v = float(ext().movieout.par.fps.eval())
            except Exception as exc:
                note(f"fps read failed: {exc}")
                return
        try:
            # MvO follows the source rate (JP spec for SOURCE mode)
            ext().Setfps(str(v))
        except Exception as exc:
            note(f"fps source push failed: {exc}")
        label = "source rate"
    else:
        try:
            v = float(ext().movieout.par.fps.eval())
        except Exception as exc:
            note(f"fps read failed: {exc}")
            return
        label = "MvO par"
    text = str(int(v)) if v == int(v) else ('%g' % v)
    try:
        w.par.Value0.val = text
        note(f"FPS field <- {text} ({label})")
    except Exception as exc:
        note(f"fps field write failed: {exc}")


def _set_output_text(text):
    """Write text to the OUTPUT label (renders Widgetlabel — verified)."""
    w = widget("output_l")
    if w is None:
        return
    try:
        w.par.Widgetlabel.val = text
    except Exception as exc:
        note(f"output text failed: {exc}")


def _queue_rebuild_from_table():
    """Reconstruct the in-memory _queue from queue_table (the durable
    copy) when the module was recompiled.

    GOTCHA (live-diagnosed 2026-09-14): TD recompiles file-linked DAT
    modules on EVERY file change — module-level state (_queue) resets,
    while the lister keeps showing rows from the table DAT. Without
    this, clicks say 'no matching queue item' and START silently
    encodes NOTHING though rows are right there. The table is the
    source of truth; the list is the cache.

    Col 3 holds the FULL input path (the lister never sees it — it
    reads queue_display, cols 0-1). Outputs are re-derived (the cached
    paths were lost with the list). Old tables without col 3 fall back
    to the basename (best effort — the inspector may then fail to load
    the file, and it says so).
    """
    global _queue
    t = op.vcon.op("queue_table")
    if t is None:
        return 0
    rows = []
    try:
        ncols = t.numCols
        for r in range(1, t.numRows):          # row 0 = header
            base = str(t[r, 0] or "").strip()
            s = str(t[r, 1] or "").strip()
            full = (str(t[r, 3] or "").strip()
                    if ncols > 3 else "")
            if not base:
                continue
            if not full:
                full = base                   # legacy table: basename only
            # a running row's status is a block bar — treat as queued
            # (the controller is the authority on what's actually
            # encoding; re-submitting after a recompile is safe because
            # _run_next's is_busy gate serializes it)
            if s.startswith(chr(0x2588)):
                s = "queued"
            rows.append({"input": full, "output": "", "status": s,
                         "rel": base})
    except Exception:
        pass
    if not rows:
        return 0
    # re-derive outputs (the cached ones died with the old list)
    codec = _val("codec_dd") or "notchlc"
    sub = _validate_choice(codec, "subtype", _val("subtype_dd"))
    for it in rows:
        try:
            it["output"] = _unique_output(_derive_output(
                it["input"], _dst_dir(), codec, sub))
        except Exception:
            it["output"] = it["input"]      # _run_next will fail loudly
    _queue = rows
    note(f"queue rebuilt from table: {len(rows)} item(s)")
    return len(rows)


def _queue_item_from_info(info):
    """Map a lister selection to its _queue item.

    LIVE-VERIFIED (JP's first-click dump 2026-09-14): the onSelectRow
    info carries rowData with the FILE NAME DIRECTLY:
      {'row': 5, 'rowData': {'file': 'OK_Go_TTSP.mp4', ...},
       'sourceIndex': 5, 'callbackName': 'onSelectRow'}
    So: rowData.file first (exact, no row-numbering guesses), then
    basename match at the row index, then direct index as a last
    resort. The old table-scanning heuristic is gone (it could grab
    the WRONG internal DAT — the lister's license-text callbacks DAT
    passes a 'not a header' check).
    """
    # 1) direct: rowData carries the file name
    rd = info.get("rowData") or {}
    nm = str(rd.get("file") or "").strip()
    if nm:
        for it in _queue:
            if os.path.basename(it["input"]) == nm:
                return it
    # 2) row index: try both conventions against queue_display
    r = info.get("row")
    try:
        r = int(r)
    except (TypeError, ValueError):
        return None
    try:
        d = op.vcon.op("queue_display")
        if d is not None:
            for idx in (r + 1, r):
                if 0 <= idx < d.numRows:
                    cell = str(d[idx, 0] or "").strip()
                    if cell and cell != "file":
                        for it in _queue:
                            if os.path.basename(it["input"]) == cell:
                                return it
    except Exception:
        pass
    # 3) last resort: direct index (0-based assumption)
    if 0 <= r < len(_queue):
        return _queue[r]
    return None


def _inspector_values():
    """The Media File Info DAT's 2-column table as {label: value}.

    The DAT (JP's suggestion — replaces the inspectin/mdls approach)
    emits one row per field: filename/filepath/vcodec/vcodecDesc/
    width/height/fps/frames/seconds (+ audio rows, + 'valid' on newer
    builds). Labels are normalized lowercase; the docs note DISPLAY
    labels may differ from API names ('Video Codec' vs 'vcodec'), so
    lookups go through label VARIANTS (see _inspect_tick).
    """
    p = panel()
    d = p.op("inspector") if p is not None else None
    if d is None:
        return {}
    out = {}
    try:
        for r in range(d.numRows):
            k = str(d[r, 0] or "").strip().lower()
            v = str(d[r, 1] or "").strip()
            if k and v:
                out[k] = v
    except Exception:
        pass
    return out


def _full_path_for(basename):
    """The FULL input path for a queue row's basename — resolved via
    queue_table col 3 (the durable full-path column), then any _queue
    item that has a real path (not a bare basename)."""
    t = op.vcon.op("queue_table")
    if t is not None:
        try:
            for r in range(1, t.numRows):
                if str(t[r, 0] or "").strip() == basename:
                    full = (str(t[r, 3] or "").strip()
                            if t.numCols > 3 else "")
                    if full:
                        return full
        except Exception:
            pass
    for it in _queue:
        if os.path.basename(it["input"]) == basename:
            cand = it["input"]
            if os.path.sep in cand:
                return cand
    return None


def OnQueueRowSelected(info=None):
    """Lister onSelectRow hook (JP 2026-09-14): clicking a queue row
    shows that FILE's info in the OUTPUT label — name, resolution,
    frame rate, codec — via the Media File Info DAT (JP's suggestion:
    native TD metadata, one op). The onFrame tick finishes the display
    once the DAT cooks; the next preview/queue event overwrites the
    label back, as before.
    """
    global _inspect_item, _inspect_ticks
    info = info or {}
    # LIVE-VERIFIED shape (first-click dump): row / rowData.file /
    # sourceIndex / callbackName. EVERY click reports its outcome now
    # (the one-shot dump hid failures on clicks 2+).
    note(f"lister onSelectRow: {info.get('callbackName')} "
         f"row={info.get('row')} "
         f"file={(info.get('rowData') or {}).get('file')}")
    if not _queue:
        # module recompiled (TD recompiles file-linked DATs on every
        # file change — the queue list reset; the lister still shows
        # the table's rows). Rebuild from the durable table copy.
        _queue_rebuild_from_table()
    item = _queue_item_from_info(info)
    if item is None:
        note("  no matching queue item — inspect skipped")
        return
    if item is _inspect_item and _inspect_ticks > 0:
        note("  re-click on the inspecting item — ignored")
        return
    _inspect_item = item
    _inspect_ticks = 0
    # REMOVAL TRACKING (JP's remove_b 2026-09-14): the selected item is
    # stored BY PATH — dict identity dies with every module recompile
    # (the queue list rebuilds from the table), a path survives.
    global _selected_path
    _selected_path = item["input"]
    # no intermediate 'inspecting …' text (JP: not needed) — output_l
    # keeps its current content until the metadata lands
    p = panel()
    d = p.op("inspector") if p is not None else None
    if d is None:
        note("  NO 'inspector' DAT in the panel — rebuild needed "
             "(exec panel_build_run)")
        _inspect_item = None
        return
    full = _full_path_for(os.path.basename(item["input"])) or item["input"]
    note(f"  inspector loading: {full!r}")
    try:
        d.par.file = full
        d.par.reloadpulse.pulse()
    except Exception as exc:
        note(f"inspect load failed: {exc}")


def _inspect_tick():
    """onFrame: finish the row inspector once the Media File Info DAT
    has cooked the clicked file. Field lookup by label VARIANTS (the
    docs' API names vs possible display labels); the 'valid' row (newer
    builds) gates readiness. ~2s timeout falls back to whatever is
    present."""
    global _inspect_item, _inspect_ticks
    if _inspect_item is None:
        return
    vals = _inspector_values()
    # PER-CLICK diagnostics (probe-first): the DAT's real labels dump
    # to the textport — if the pick() variants ever miss, that dump
    # shows the true row names. A missing DAT says so plainly (builder
    # creates it — file-linked module changes go live WITHOUT a
    # rebuild, the DAT does not). A cook with the FILE PAR UNSET means
    # the write fell over (par name, pulse, or the file path itself).
    global _noted_table
    p_ = panel()
    d_ = p_.op("inspector") if p_ is not None else None
    if d_ is not None:
        try:
            cur_file = str(d_.par.file.eval() or "")
            if vals and cur_file.lower() in ("", "none"):
                note("  inspector: DAT has rows but FILE PAR is EMPTY "
                     "— the file write/pulse didn't land")
        except Exception:
            pass
    if not _noted_table:
        p_ = panel()
        d_ = p_.op("inspector") if p_ is not None else None
        if d_ is None:
            note("row inspector: no 'inspector' DAT in the panel — "
                "rebuild (exec panel_build_run)")
            _noted_table = True
        elif vals:
            note(f"inspector DAT table ({d_.numRows} rows): {vals!r}")
            _noted_table = True
    if not vals:
        _inspect_ticks += 1
        if _inspect_ticks > 120:
            _set_output_text(
                os.path.basename(_inspect_item["input"])
                + "  |  metadata unavailable")
            _inspect_item = None
        return

    def pick(*names):
        for n in names:
            if n in vals:
                return vals[n]
        return None

    vcodec = pick("vcodec", "video codec", "videocodec", "codec")
    vdesc = pick("vcodedesc", "vcodecdesc", "video codec description",
                 "codec description")
    width = pick("width", "video width")
    height = pick("height", "video height")
    fps = pick("fps", "frame rate", "framerate")
    valid = pick("valid")
    ready = ((vcodec or width or fps) and
             (valid is None or valid.lower() in ("1", "true", "yes")))
    _inspect_ticks += 1
    if ready or _inspect_ticks > 120:
        parts = [os.path.basename(_inspect_item["input"])]
        if width and height:
            parts.append(f"{width}x{height}")
        if fps:
            parts.append(f"{fps} fps")
        # LENGTH (JP 2026-09-14): the DAT emits 'duration' (formatted),
        # 'seconds' (float) and 'frames' — prefer the formatted one
        dur = pick("duration", "length")
        if not dur:
            secs = pick("seconds")
            dur = f"{secs} s" if secs else None
        if not dur:
            frames = pick("frames")
            dur = f"{frames} frames" if frames else None
        if dur:
            parts.append(dur)
        codec = vdesc or vcodec
        parts.append(codec if codec else "(codec unavailable)")
        _set_output_text("  |  ".join(parts))
        note(f"  inspector: {', '.join(parts)}")
        _inspect_item = None


def _res_value():
    """Resolution args for Transcode(): (resolution, scale).

    SCALING off -> ('auto', None). ON: the SCALE dropdown holds a fit
    TOP Output Resolution token (the panel menu MIRRORS that menu —
    eighth/quarter/half/twotimes/fourtimes/eighttimes) which the fit
    TOP applies natively; 'custom' sends an ABSOLUTE WxH from the W/H
    fields (the controller applies it directly).
    """
    mode = _val("scaled_t")
    if not bool(mode):
        return "auto", None
    choice = str(_val("scale_dd") or "").strip()
    if not choice:
        # EMPTY SCALE with scaling on: no token to send — auto, not a
        # guessed default (a garbage token would fail the job loudly)
        note("no SCALE chosen — falling back unscaled")
        return "auto", None
    if choice == "custom":
        W = str(_val("resw_f") or "").strip()
        H = str(_val("resh_f") or "").strip()
        if W.isdigit() and H.isdigit() and int(W) > 0 and int(H) > 0:
            return f"{int(W)}x{int(H)}", None
        note("custom resolution needs valid W and H — falling back unscaled")
        return "auto", None
    # A fit TOP Output Resolution token (eighth/quarter/half/twotimes/
    # fourtimes/eighttimes) — the controller menu-verifies it against
    # the live fit TOP menu and fails LOUDLY on drift, never silent
    # index-0 fallback.
    return "auto", choice


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
    """Run the queue: open the batch gate and let the tick feed items.

    SOURCE field removed (JP): the queue IS the input — files arrive via
    +ADD, drag/drop, or a folder drop. Encoding begins only on START.
    """
    global _batch_started
    if not _queue:
        note("queue is empty — add files first")
        return
    _batch_started = True
    _refresh_queue()
    n = sum(1 for it in _queue if it["status"] == "queued")
    note(f"batch started — {n} file(s) queued")


#: Batch gate: items enqueue freely (via +ADD / drops / folder browse),
#: but the tick only submits them once START has been pressed (JP:
#: adding a movie must NOT begin the encode). Set True by Start(),
#: False by Stop() and when the queue empties.
_batch_started = False


def _run_next():
    """Dequeue the next batch job and submit it (called when idle).

    GATED on _batch_started: queued items sit until START.
    """
    e = ext()
    if e.is_busy:
        return
    if not _batch_started:
        return                      # queue loaded, awaiting START (JP)
    # DURABLE QUEUE: a module recompile (file-linked DATs recompile on
    # every file change) resets the in-memory _queue — rebuild from the
    # table BEFORE iterating, or START silently encodes nothing.
    if not _queue:
        if _queue_rebuild_from_table() == 0:
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
    # FPS per MODE: SOURCE -> 'auto' (the controller re-resolves from
    # each loaded movie's sample_rate, so batch files with different
    # rates each encode at their own); CUSTOM -> the field's value
    if _fps_source_mode():
        fps = "auto"
    else:
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
    """Cancel the active job, stop the batch, clear the queue."""
    global _batch_started
    _batch_started = False      # re-close the gate (JP: adds must wait)
    ext().Cancel()
    for item in _queue:
        if item["status"] in ("queued", "running"):
            item["status"] = "cancelled"
    _refresh_queue()
    PreviewOutput()      # the preview follows queue state (JP 2026-09-14)
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


#: Half-block chars for the in-cell row bar: 8 sub-steps per char cell.
_BAR_FULL = "\u2588"
_BAR_EMPTY = "\u2591"


def _bar_text(frac, width=10):
    """A block-character progress bar for a queue row's status cell."""
    frac = 0.0 if frac is None else min(1.0, max(0.0, float(frac)))
    full = int(frac * width)
    return _BAR_FULL * full + _BAR_EMPTY * (width - full)


def _batch_progress():
    """(done_count, total_count) across the queue — the PANEL bar shows
    this for the whole batch (JP), not the current file's 0-1."""
    if not _queue:
        return 0.0
    done = sum(1 for it in _queue if it["status"] == "done")
    running = next((it for it in _queue if it["status"] == "running"),
                   None)
    if running is not None:
        try:
            frac = float(op.vcon.par.Progress.eval())
        except Exception:
            frac = 0.0
        return (done + frac) / len(_queue)
    return done / len(_queue)


def _refresh_queue():
    """Redraw the batch queue table (the lister widget's source DAT).

    STRATEGY (two rounds of live tracebacks): the lister refreshes on
    EVERY table write and throws 'Blank header in col 0' on any
    mid-write state (clear+append OR setSize leaves one). So the
    builder sets Refreshoninputchange=OFF — writes never trigger it —
    and this function finishes with ONE explicit Refresh pulse, so the
    lister only ever redraws on a complete, valid table.

    The RUNNING row's status is a block-character bar that fills as
    the encode progresses. A 4th 'progress' column (0-1) drives the
    per-row background TOP (bar behind the file name — JP).
    """
    t = panel().op("queue_table")
    if t is None:
        # The builder creates queue_table at the VCON level (next to the
        # panel), not inside the panel — a path-lookup here silently
        # returned None, which is why the queue table never redrew.
        t = op.vcon.op("queue_table")
    if t is None:
        return
    # current encode progress, if a job is running
    try:
        prog = float(op.vcon.par.Progress.eval())
    except Exception:
        prog = 0.0
    rows = [["file", "status", "progress", "path"]]
    for i, item in enumerate(_queue, 1):
        status = item["status"]
        row_prog = 0.0
        if status == "running":
            status = _bar_text(prog)
            row_prog = prog
        elif status == "done":
            row_prog = 1.0
        rows.append([os.path.basename(item["input"]),
                     status, f"{row_prog:.4f}",
                     item["input"]])
    # DRIVER table (3 cols: file, status, progress — progress is the
    # bar-TOP driver read by INDEX from col 2; the lister reads the
    # DISPLAY table below, so progress never shows. Col 3 = FULL PATH
    # — the durable copy the module rebuilds _queue from after a
    # recompile; the lister never sees it.)
    try:
        cur_r, cur_c = t.numRows, t.numCols
    except Exception:
        cur_r, cur_c = 0, 3
    big = max(cur_r, len(rows))
    try:
        t.setSize(big, 4)
    except Exception:
        pass
    for r in range(big):
        row = rows[r] if r < len(rows) else ["", "", "", ""]
        for c in range(4):
            try:
                t[r, c] = row[c]
            except Exception:
                pass
    if big > len(rows):
        try:
            t.setSize(len(rows), 4)
        except Exception:
            pass

    # DISPLAY table (2 cols: file, status — what the lister reads, so
    # auto-define makes exactly those two columns; NO number column,
    # NO progress column, per JP).
    d = op.vcon.op("queue_display")
    if d is not None:
        drows = [[r[0], r[1]] for r in rows]
        try:
            dcur = d.numRows
        except Exception:
            dcur = 0
        dbig = max(dcur, len(drows))
        try:
            d.setSize(dbig, 2)
        except Exception:
            pass
        for r in range(dbig):
            row = drows[r] if r < len(drows) else ["", ""]
            for c in range(2):
                try:
                    d[r, c] = row[c]
                except Exception:
                    pass
        if dbig > len(drows):
            try:
                d.setSize(len(drows), 2)
            except Exception:
                pass
    # ONE refresh, on our schedule, on a complete table.
    q = panel().op("queue")
    if q is not None:
        try:
            q.par.Refresh.pulse()
        except Exception:
            pass


def _mark_running(output_path):
    for item in _queue:
        if item["output"] == output_path and item["status"] == "queued":
            item["status"] = "running"
            break
    _refresh_queue()


def RemoveSelected():
    """remove_b (JP 2026-09-14): remove the SELECTED queue row.

    The selection is tracked by input PATH (set on every row click —
    and by the onFrame poll fallback; a module recompile wipes the
    module globals, so the path also rebuilds from the table first if
    the queue list is empty). Guards:
      - a RUNNING row is never removed (the controller owns it; the
        job would finish writing to an output the queue no longer
        tracks) — STOP cancels instead
      - no selection: said so in the textport, nothing happens
    """
    global _queue, _selected_path
    if not _queue:
        _queue_rebuild_from_table()
    if not _queue:
        note("nothing to remove — the queue is empty")
        return
    if not _selected_path:
        note("no row selected — click a file first")
        return
    tgt = None
    for it in _queue:
        if it["input"] == _selected_path:
            tgt = it
            break
    if tgt is None:
        note(f"selected item no longer in the queue: "
             f"{os.path.basename(_selected_path)}")
        _selected_path = None
        return
    if tgt["status"] == "running":
        note(f"{os.path.basename(_selected_path)} is encoding — "
             "STOP cancels it; removing mid-encode is refused")
        return
    _queue.remove(tgt)
    _selected_path = None
    _refresh_queue()
    PreviewOutput()          # the preview follows queue state
    note(f"removed {os.path.basename(tgt['input'])}")


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
        # Preview refresh (JP 2026-09-14): when this was the LAST job,
        # the queue is all-done — the preview must fall back to the
        # empty-queue message, not keep showing the finished file's
        # derived output.
        try:
            PreviewOutput()
        except Exception:
            pass


def _on_job_done(output_path):
    """Poll-based completion hook for the panel: refresh + run next."""
    _mark_done(output_path)


def onFrame():
    """Panel-level Execute DAT tick: feed the batch loop + auto-refresh.

    When the controller goes idle and queue rows remain queued, submit the
    next job. When a running row's output file exists and the controller
    is idle, the job finished — mark done, then next.

    The PANEL bar shows BATCH progress (item N of M — JP), not the
    current file's 0-1; the tick computes it and writes the fill width
    directly (no expression needed). The LISTER row shows the current
    file's own progress as a block bar.
    """
    try:
        e = ext()
    except Exception:
        return

    # 1) drive the panel bar with batch progress, every frame
    try:
        fill = panel().op("prog_fill")
        if fill is not None:
            fill.par.w.val = _batch_progress() * 620
    except Exception:
        pass

    # 1b) SOURCE-mode FPS display: follow the loaded movie's rate. When
    # a new file loads (job start), sample_rate changes — refresh the
    # (disabled) field so it displays the current source's rate. Cheap
    # per-frame float compare, only in source mode.
    try:
        if _fps_source_mode() and _source_fps() != _last_src_fps:
            _last_src_fps = _source_fps()
            if _last_src_fps is not None:
                SyncFpsField()
    except Exception:
        pass

    # 1c) row-click inspector: a clicked queue file loads in the
    # Media File Info DAT; finish its display in output_l once cooked.
    # FALLBACK POLL: if the lister's Advancedcallbacks gate is ever off
    # (stock default — the builder turns it on, but a stale capture
    # could revert it), onSelectRow never fires; the Selectedrows par
    # still tracks the selection, so detect changes here too.
    try:
        if _inspect_item is not None:
            _inspect_tick()
    except Exception:
        pass
    try:
        q_ = widget("queue")
        sel = str(q_.par.Selectedrows.eval() or "") if q_ is not None else ""
        if sel and sel != _last_sel:
            _last_sel = sel
            # map the lister's selection to a queue item: try both the
            # info shape (row int) and the raw string
            for cand in (sel.strip(), int(sel.strip())):
                try:
                    item = _queue_item_from_info({"row": cand})
                    if item is not None and item is not _inspect_item:
                        OnQueueRowSelected({"row": cand})
                        break
                except (TypeError, ValueError):
                    continue
    except Exception:
        pass

    # 1d) OUTPUT preview refresh when the queue EMPTIES: drops/adds call
    # PreviewOutput directly, but paths that empty the lister (Stop, the
    # last job finishing via tick detection) left the label stale. Cheap
    # per-frame check: only acts when the queue is empty AND rows remain
    # in the display table (the just-emptied moment); the refresh itself
    # clears those rows.
    try:
        if not _queue:
            d_ = op.vcon.op("queue_display")
            if d_ is not None and d_.numRows > 1:
                PreviewOutput()
    except Exception:
        pass

    # 2) feed the loop when idle
    if e.is_busy:
        _refresh_queue()     # keeps the running row's bar moving
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
    """Drop Script entry: files/folders dropped anywhere on the panel.

    DESIRED WORKFLOW (JP): drops enqueue DIRECTLY into the batch queue —
    a file adds one row; a folder adds every movie under it (recursive,
    same scan as folder-in-SOURCE + START). Also mirrors the drop into
    the SOURCE widget so the OUTPUT preview derives. The tick then feeds
    rows to the encoder one at a time; no START needed unless queued
    items should re-run.
    """
    items = info.get("dropItems") if isinstance(info, dict) else None
    if not items:
        try:
            items = info["dropItems"]
        except Exception:
            return
    if not items:
        return

    paths = []
    for it in items:
        p = it if isinstance(it, str) else it.get("path", str(it))
        if p:
            paths.append(p)
    if not paths:
        return

    added = 0
    for path in paths:
        if os.path.isdir(path):
            for inp, rel in _scan_movies(path):
                out = _unique_output(_derive_output(
                    inp, _dst_dir(), _val("codec_dd") or "notchlc",
                    _val("subtype_dd")))
                _queue.append({"input": inp, "output": out,
                               "status": "queued", "rel": rel})
                added += 1
        elif os.path.isfile(path):
            out = _unique_output(_derive_output(
                path, _dst_dir(), _val("codec_dd") or "notchlc",
                _val("subtype_dd")))
            _queue.append({"input": path, "output": out,
                           "status": "queued",
                           "rel": os.path.basename(path)})
            added += 1
            PreviewOutput()      # refresh from the first queued item

    if added:
        _refresh_queue()
        note(f"dropped {added} file(s) — press START to encode")
    else:
        note("no movie files in the drop")


def _dst_dir():
    """The destination folder (or None) from the DESTINATION widget."""
    dst = _val("destination")
    return os.path.dirname(dst) if dst else None


def AddFiles():
    """The + button: open a file dialog and APPEND to the queue.

    JP: there was no way to add files to the lister via a dialog — the
    SOURCE browser only ever holds ONE path. ui.chooseFile is the
    documented native dialog (start=None opens at last location;
    fileTypes filters). Multi-select isn't available in one call on
    all builds, so the button can be pressed repeatedly; folder adds
    come through drag/drop or SOURCE-browse + START.
    """
    try:
        path = ui.chooseFile(start=None, fileTypes=list(MOVIE_EXTS),
                             title="Add movie to the queue")
    except Exception as exc:
        note(f"file dialog failed: {exc}")
        return
    if not path:
        return
    if os.path.isfile(path):
        codec = _val("codec_dd") or "notchlc"
        out = _unique_output(_derive_output(path, _dst_dir(), codec,
                                            _val("subtype_dd")))
        _queue.append({"input": path, "output": out,
                       "status": "queued",
                       "rel": os.path.basename(path)})
        _refresh_queue()
        PreviewOutput()   # the preview follows queue state (JP 2026-09-14)
        note(f"added {os.path.basename(path)} — press START to encode")
    elif os.path.isdir(path):
        n = 0
        for inp, rel in _scan_movies(path):
            out = _unique_output(_derive_output(
                inp, _dst_dir(), _val("codec_dd") or "notchlc",
                _val("subtype_dd")))
            _queue.append({"input": inp, "output": out, "status": "queued",
                           "rel": rel})
            n += 1
        _refresh_queue()
        PreviewOutput()   # the preview follows queue state (JP 2026-09-14)
        note(f"added {n} file(s) from folder — press START to encode")


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
