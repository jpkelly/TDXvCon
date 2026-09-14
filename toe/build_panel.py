"""build_panel.py — generate the vCon panel inside the vCon COMP. (v4)

Run in the TouchDesigner TEXTPORT (never import):

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/build_panel.py',
              encoding='utf-8').read())

Creates /project1/vcon/panel — Basic Widgets from the app-bundle palette
.tox files, configured ENTIRELY through external widget parameters
(never their internals). LIVE-VERIFIED: config pars live on the INNER
COMP (children scan); First-uppercase names (Value0, Widgetlabel,
Menunames, Menulabels, Offtoonscript0, Onvaluechangescript0); label
par for fields/buttons is Widgetlabel (NOT Label — that's the widget's
own name label); button face text is Buttonofflabel/Buttononlabel.

Layout (y measured up from the panel bottom):
    row 6  SOURCE file browser           row 5  DESTINATION folder browser
    row 4  CODEC | SUBTYPE               row 3  FORMAT | QUALITY
    row 2  FPS | RESOLUTION | FIT
    row 1  START PAUSE STOP   OUTPUT: <auto-named file>
    row 0  progress slider | STATUS line
    queue  batch table (lister) below, fed by queue_table DAT
"""

import os

#: td-module op types (find_type resolves td first, globals second —
#: same pattern as build_network.py).
def find_type(*names):
    try:
        import td as _td
    except ImportError:
        _td = None
    for n in names:
        if _td is not None and hasattr(_td, n):
            return getattr(_td, n)
        if n in globals():
            return globals()[n]
    raise RuntimeError(f"op type {names} unavailable — run in the textport")


#: Widget tox roots: most Basic Widgets live in the Basic Widgets folder,
#: but the lister (batch queue) sits at the UI palette ROOT (live-checked).
_TOX_DIR = ("/Applications/TouchDesigner.app/Contents/Resources/tfs/"
            "Samples/Palette/UI/Basic Widgets")
_UI_TOX_DIR = ("/Applications/TouchDesigner.app/Contents/Resources/tfs/"
               "Samples/Palette/UI")
_TOX_PATHS = {
    "lister": os.path.join(_UI_TOX_DIR, "lister.tox"),
}
COMP_PARENT = "/project1/vcon"
COMP_NAME = "panel"
REPO = "/Users/jp/Documents/GitHub/vCon"

#: GRID GEOMETRY — computed rows, uniform 30px heights, narrow columns.
#: Panel is 660x640; STATUS sits at the very bottom (plenty of room).
#: Row pitch 45; y from panel bottom.
_ROW = 30
_TOP = 600


def _r(n):
    return _TOP - n * 45


_WIDGETS = {
    # browsers, full width
    "source":       ("fieldFileBrowser",   20, 600, 620, _ROW),
    "destination":  ("fieldFolderBrowser", 20, 555, 620, _ROW),
    # settings, two narrow columns (half-width each — no spillover)
    # FORMAT and SUBTYPE swapped per JP — SUBTYPE now reads top-left.
    "codec_dd":     ("dropDownMenu",       20, 510, 230, _ROW),
    "format_dd":    ("dropDownMenu",      260, 510, 230, _ROW),
    "subtype_dd":   ("dropDownMenu",       20, 465, 230, _ROW),
    "quality_s":    ("sliderHorz",        260, 465, 230, _ROW),
    # row: FPS | SCALING | SCALE(hidden) | FIT — readable sizes
    "fps_f":        ("fieldString",        20, 420, 140, _ROW),
    "scaled_t":     ("buttonToggle",      170, 420, 130, _ROW),
    "scale_dd":     ("dropDownMenu",      310, 420, 160, _ROW),
    "fit_dd":       ("dropDownMenu",      480, 420, 160, _ROW),
    # buttons (label disabled)
    "start_b":      ("buttonMomentary",    20, 375, 110, _ROW),
    "pause_b":      ("buttonMomentary",   140, 375, 110, _ROW),
    "stop_b":       ("buttonMomentary",   260, 375, 110, _ROW),
    # OUTPUT: full-width read-only field BELOW the buttons (JP: the
    # derived filename is too long for a side slot — give it the row)
    "output_l":     ("label",              20, 330, 620, _ROW),
    # PROGRESS slider, full width
    # PROGRESS: custom bar (no palette widget exists, and sliderHorz's
    # numeric field CANNOT be hidden — probe-verified: 'off' writes
    # succeed but the field persists). A Container track + a fill
    # Container whose width EXPRESSION drives from the Progress par:
    # pure geometry, no number by construction.
    "prog_track":  ("__bar__",            20, 285, 620, 16),
    "prog_fill":   ("__bar__",            20, 285, 620, 16),
    # queue, then STATUS at the very bottom
    "queue":        ("lister",             20,  90, 620, 200),
    "status_l":     ("label",              20,  40, 620, _ROW),
}

#: Field titles via Widgetlabel (LIVE-DUMPED: the widget's title par).
_TITLES = {
    "source": "SOURCE",
    "destination": "DESTINATION",
    "codec_dd": "CODEC",
    "subtype_dd": "SUBTYPE",
    "format_dd": "FORMAT",
    "quality_s": "QUALITY",
    "fps_f": "FPS",
    "scaled_t": "SCALING",
    "scale_dd": "SCALE",
    "fit_dd": "FIT",
    "output_l": "OUTPUT",
    "status_l": "STATUS",
}

_BUTTON_SCRIPT_PAR = "Offtoonscript0"


def say(msg):
    print(f"[panel] {msg}")


def inner_of(wrapper):
    """The actual widget COMP inside a loadTox wrapper (children scan)."""
    for c in wrapper.children:
        if c.name == wrapper.name or c.isPanel:
            return c
    say(f"!! no inner widget inside {wrapper.path}")
    return None


def place(outer, x, y, w, h, row=0):
    """Place a widget: panel-view coords AND network coords.

    - par.x/y/w/h  = where it sits in the PANEL viewer (the UI).
    - nodeX/nodeY  = where the node sits in the NETWORK editor. Without
      these every widget lands at the same spot (a card pile). We mirror
      the panel grid: x maps to nodeX, rows map top-down to nodeY, so the
      network view roughly sketches the panel's layout.
    """
    try:
        outer.par.x = x
        outer.par.y = y
        outer.par.w = w
        outer.par.h = h
    except Exception as exc:
        say(f"  (place {outer.name}: {exc})")
    try:
        # Network scale: COMP nodes render ~200px wide / ~130px tall in the
        # network editor. Panel pitch is 45 — 1:1 mirroring overlaps badly
        # (screenshot-verified). Scale x2 horizontally, x4 vertically so
        # every node clears its neighbors with margin.
        outer.nodeX = (x - 20) * 2
        outer.nodeY = -y * 4 - 120
    except Exception:
        pass


def setp(inner, par_name, value):
    """Set one inner-widget custom par; print the full surface on a miss."""
    try:
        getattr(inner.par, par_name).val = value
        return True
    except Exception:
        names = [p.name for p in inner.customPars]
        say(f"  !! {inner.path}: no par {par_name}. customPars: "
            f"{', '.join(names)}")
        return False


def set_menu(inner, names, labels, default):
    """Populate a dropDownMenu (labels quote-once when containing spaces)."""
    ok = True
    ok &= setp(inner, "Menunames", " ".join(names))
    quoted = " ".join(f"'{l}'" if " " in l else l for l in labels)
    ok &= setp(inner, "Menulabels", quoted)
    if default in names:
        ok &= setp(inner, "Value0", default)
    return ok


def _grey_out_b(inner, grey=True):
    """Builder-side grey-out — STRING MENU tokens ('off'/'on'), not
    booleans (integer writes select menu INDEX 0, which can be 'on')."""
    for cand in ("enable", "Enable"):
        par = getattr(inner.par, cand, None)
        if par is None:
            continue
        try:
            menus = list(getattr(par, "menuNames", None) or [])
            if menus:
                getattr(inner.par, cand).val = "off" if grey else "on"
            else:
                getattr(inner.par, cand).val = 0 if grey else 1
            return True
        except Exception:
            continue
    return False


def build():
    say("=" * 52)
    say("building vCon panel (v4)")
    say("=" * 52)

    vcon = op(COMP_PARENT)
    if vcon is None:
        raise RuntimeError(f"{COMP_PARENT} not found — run build_network.py "
                           f"first, then this script")

    try:
        vcon.par.opshortcut = "vcon"
    except Exception as exc:
        say(f"(opshortcut: {exc})")

    for stale in (COMP_NAME, "panel_callbacks", "queue_table",
                  "panel_tick"):
        if vcon.op(stale) is not None:
            say(f"removing existing {stale}")
            vcon.op(stale).destroy()

    # ---- callbacks DAT (file-linked, like the controller DAT) -----------
    say("creating panel_callbacks DAT (file-linked)")
    cb = vcon.create(textDAT, "panel_callbacks")
    cb.nodeX = 300
    cb.nodeY = 150
    cb.par.file = f"{REPO}/toe/vcon_panel_callbacks.py"
    cb.par.syncfile = 1

    # ---- queue table DAT (lister source) ---------------------------------
    say("creating queue_table DAT (batch list)")
    qt = vcon.create(tableDAT, "queue_table")
    qt.nodeX = 300
    qt.nodeY = 90
    qt.appendRow(["#", "file", "status"])

    # ---- panel container -------------------------------------------------
    panelcomp = vcon.create(containerCOMP, COMP_NAME)
    panelcomp.nodeX = 300
    panelcomp.nodeY = 260
    place(panelcomp, 0, 0, 660, 640)

    # ---- load widgets -----------------------------------------------------
    # FLAT WIDGETS AT PANEL ROOT (JP, twice): load the tox into a scratch,
    # copy ONLY the inner widget COMP up to the panel root, destroy the
    # scratch. The panel's children are the actual widgets — no wrapper
    # containers. Configuration still targets TOP-LEVEL parameters of the
    # widget we keep (the inner widget IS the top level of the flat copy);
    # the top-level-only rule is about never reaching INTO the widget's
    # internals, which we never do.
    say("loading widgets")
    widgets = {}
    for outer_name, (tox, x, y, w, h) in _WIDGETS.items():
        if tox == "__bar__":
            # Custom progress bar (no palette widget exists; sliderHorz's
            # numeric field cannot be hidden — probe-verified). A plain
            # Container; the fill gets its width bind below.
            wcomp = panelcomp.create(containerCOMP, outer_name)
            place(wcomp, x, y, w, h)
            widgets[outer_name] = wcomp
            continue
        path = _TOX_PATHS.get(tox,
                              os.path.join(_TOX_DIR, f"{tox}.tox"))
        scratch = panelcomp.create(containerCOMP, "_scratch")
        ret = scratch.loadTox(path)
        wrapper = ret if ret is not None else scratch.op(tox)
        if wrapper is None:
            say(f"!! loadTox({tox}) failed in scratch")
            scratch.destroy()
            continue
        # Find the inner widget (the tox drops a same-named container
        # holding the real widget).
        inner = None
        for c in wrapper.children:
            if c.name == wrapper.name or c.isPanel:
                inner = c
                break
        src_comp = inner if inner is not None else wrapper
        try:
            wcomp = panelcomp.copy(src_comp, name=outer_name)
        except Exception as exc:
            say(f"!! copy {tox} -> {outer_name}: {exc}")
            scratch.destroy()
            continue
        if wcomp is None:
            say(f"!! copy {tox} returned None")
            scratch.destroy()
            continue
        scratch.destroy()
        place(wcomp, x, y, w, h)
        widgets[outer_name] = wcomp
    say(f"loaded {len(widgets)}/{len(_WIDGETS)} widgets (flat at panel root)")

    # ---- progress bar: track + fill, painted with Constant TOPs ----
    # A bare containerCOMP has NO Look page — panels paint via a
    # Background TOP (Look page 'top' on widget COMPs). PROVEN pattern
    # from build_network's set_op_par: OP-type pars accept the object OR
    # the path string, depending on build — try both. Every write in its
    # OWN try so one miss can't skip the rest (the old block lost the
    # width expression when par.top raised — probe 7 found both dead).
    def _link_op(holder, par_name, target):
        for value in (target, target.path):
            try:
                setattr(holder.par, par_name, value)
                return True
            except Exception:
                continue
        say(f"  !! {holder.name}.{par_name}: neither object nor path "
            f"accepted")
        return False

    if "prog_track" in widgets and "prog_fill" in widgets:
        track = widgets["prog_track"]
        fill = widgets["prog_fill"]
        # track: gray paint
        try:
            ttop = track.create(find_type("constantTOP"), "paint")
            ttop.par.colorr = 0.5
            ttop.par.colorg = 0.5
            ttop.par.colorb = 0.5
            ttop.par.alpha = 1.0
            if _link_op(track, "top", ttop):
                say("  track painted gray (Background TOP linked)")
        except Exception as exc:
            say(f"  (track paint: {exc})")
        # fill: green paint + width expression — separate try blocks
        try:
            ftop = fill.create(find_type("constantTOP"), "paint")
            ftop.par.colorr = 0.2
            ftop.par.colorg = 0.8
            ftop.par.colorb = 0.2
            ftop.par.alpha = 1.0
            if _link_op(fill, "top", ftop):
                say("  fill painted green (Background TOP linked)")
        except Exception as exc:
            say(f"  (fill paint: {exc})")
        try:
            # width EXPRESSION drives the fill: Progress 0..1 -> 0..620
            fill.par.w.expr = "op.vcon.par.Progress * 620"
            say("  progress bar: fill width <- Progress par expression")
        except Exception as exc:
            say(f"  (fill width expr: {exc})")

    mod = cb.module

    # ---- titles (Widgetlabel — the live-dumped title par) ----------------
    say("setting widget titles (Widgetlabel)")
    for name, title in _TITLES.items():
        if name in widgets:
            setp(widgets[name], "Widgetlabel", title)
    # Labelwidth per row type; buttons get NO label area (their titles were
    # doubled-up with face text — label disabled per JP's note).
    _LABEL_W = {"source": 110, "destination": 110, "codec_dd": 90,
                "subtype_dd": 90, "format_dd": 90, "quality_s": 90,
                "fps_f": 45, "scaled_t": 60, "scale_dd": 60,
                "fit_dd": 45, "output_l": 110, "status_l": 110,
                "start_b": 0, "pause_b": 0, "stop_b": 0}
    for name, lw in _LABEL_W.items():
        if name in widgets:
            if lw == 0:
                # Buttons get title suppression in the buttons block
                # (Labeldisplay off + width 1 + Widgetlabel text) — skip
                # here to avoid racing that config.
                pass
            else:
                setp(widgets[name], "Labelwidth", lw)
    # PROGRESS bar title via the status-style label — a plain Container
    # has no Widgetlabel, so skip the title loop entry below.
    _LOCAL_TITLES = {}
    for name, title in _LOCAL_TITLES.items():
        if name in widgets:
            setp(widgets[name], "Widgetlabel", title)
    # Buttons: face text only. THE TITLE LABELS ARE THE PROBLEM (JP, twice:
    # "Momentary Button" keeps coming back). Kill them at BOTH levels:
    # 1) the widget's own Labeldisplay 'off' (top-level par, token form)
    # 2) AND Buttonofflabel/Buttononlabel drive the FACE — we keep those.
    #    The title strip is the widget's Label area: width 0 AND display off
    #    AND its text blanked — belt, suspenders, and a third belt.
    for name, text in [("start_b", "START"), ("pause_b", "PAUSE"),
                       ("stop_b", "STOP")]:
        if name in widgets:
            w_ = widgets[name]
            setp(w_, "Buttonofflabel", text)
            setp(w_, "Buttononlabel", text)
            setp(w_, "Labeldisplay", "off")
            setp(w_, "Labelwidth", 1)
            setp(w_, "Labeltop", 1)          # pin remaining sliver to top
            setp(w_, "Widgetlabel", text)    # if title still shows, it IS the label text
            say(f"  {name}: title suppressed (Labeldisplay off + width 1)")

    # ---- defaults ----------------------------------------------------------
    say("configuring widgets (external pars only)")
    if "fps_f" in widgets:
        setp(widgets["fps_f"], "Value0", "auto")
    # output field: READ-ONLY display of the full output path
    # (destination folder + auto-derived file name). Renders via
    # Widgetlabel (probe 4) — PreviewOutput writes it live.
    # Labelhorizontalmode='fill' is the fix for the early-wrap JP saw:
    # in 'fixed' mode the text area was clamped to Labelwidth (110px),
    # wrapping at 1/6 of the field. 'fill' spans the whole widget width.
    if "output_l" in widgets:
        setp(widgets["output_l"], "Widgetlabel", "(pick a source)")
        setp(widgets["output_l"], "Labelhorizontalmode", "fill")
        setp(widgets["output_l"], "Labelverticalmode", "fill")
        try:
            setp(widgets["output_l"], "Labelwordwrap", 1)
        except Exception:
            pass

    # ---- menus -------------------------------------------------------------
    codec_names = list(mod.CODECS.keys())
    codec_labels = [mod.CODECS[k]["label"] for k in codec_names]
    if "codec_dd" in widgets:
        set_menu(widgets["codec_dd"], codec_names, codec_labels, "notchlc")
    # SUBTYPE / FORMAT seed with NotchLC's REAL values (no 'none' — JP
    # spec: none is never an option). UpdateSubtypes() re-populates them
    # per codec on every change AND once at build end, so the panel opens
    # in a fully valid state: NotchLC selected -> SUBTYPE greyed (no
    # subtypes), FORMAT rgb + rgba with rgb selected.
    notch = mod.CODECS["notchlc"]
    if "subtype_dd" in widgets:
        _grey = True     # NotchLC has no subtypes: greyed from the start
        setp(widgets["subtype_dd"], "Menunames", "")
        _grey_out_b(widgets["subtype_dd"])
    if "format_dd" in widgets:
        notch_fmts = list(notch["pixel_formats"])
        set_menu(widgets["format_dd"], notch_fmts,
                 [mod.FORMAT_LABELS.get(f, f) for f in notch_fmts], "rgb")
    # QUALITY is a SLIDER — the same presentation MvO itself uses for
    # NotchLC (a 0-1 float). The named levels from Derivative's guide
    # (good=0.0 very-good=0.285 excellent=0.575 optimal=0.862 best=1.0)
    # mark the track via Sliderlabelnames (live-dumped par). Greys out
    # for codecs with no ladder.
    if "quality_s" in widgets:
        setp(widgets["quality_s"], "Value0", 0.862)      # optimal
        # String-menu tokens, not booleans (see prog_s note above)
        setp(widgets["quality_s"], "Numericfielddisplay", "on")
        setp(widgets["quality_s"], "Sliderlabelnames",
             "'0.0 Good' '0.285 Very Good' '0.575 Excellent' "
             "'0.862 Optimal' '1.0 Best'")
    if "fit_dd" in widgets:
        set_menu(widgets["fit_dd"],
                 ["fitbest", "fill", "fithorz", "fitvert", "fitoutside"],
                 ["Fit Best", "Stretch", "Fit Width", "Fit Height",
                  "Cover/Crop"],
                 "fitbest")
    # RESOLUTION: a TOGGLE (JP request) — off = Unscaled (fit TOP bypassed,
    # source size preserved), on = Scaled (reveals the SCALE dropdown; the
    # factor is applied by the CONTROLLER against the movie's real
    # dimensions after load, even-dimension clamped). The toggle ALSO
    # rewires the fit path LIVE via the extension's Setfitpath().
    if "scaled_t" in widgets:
        setp(widgets["scaled_t"], "Widgetlabel", "SCALING")
        setp(widgets["scaled_t"], "Buttonofflabel", "OFF")
        setp(widgets["scaled_t"], "Buttononlabel", "ON")
        setp(widgets["scaled_t"], "Value0", 0)
    if "scale_dd" in widgets:
        set_menu(widgets["scale_dd"],
                 ["0.25", "0.5", "1", "2", "3"],
                 ["Quarter (1/4x)", "Half (1/2x)", "Full (1x)",
                  "Two times (2x)", "Three times (3x)"],
                 "1")
    # SCALE dropdown hidden while Unscaled — _update_res_fields toggles it.
    if "scale_dd" in widgets:
        outer = panelcomp.op("scale_dd")
        if outer is not None:
            try:
                outer.par.display = 0
            except Exception as exc:
                say(f"  (display scale_dd: {exc})")

    # ---- buttons -----------------------------------------------------------
    say("wiring buttons")
    for name, fn in [("start_b", "Start"), ("pause_b", "PauseResume"),
                     ("stop_b", "Stop")]:
        if name not in widgets:
            continue
        cmd = f"op.vcon.op('panel_callbacks').module.{fn}()"
        if setp(widgets[name], _BUTTON_SCRIPT_PAR, cmd):
            say(f"  {name}: script via '{_BUTTON_SCRIPT_PAR}' -> {fn}")

    # ---- binds + preview hooks --------------------------------------------
    say("binding progress + status")
    if "status_l" in widgets:
        try:
            # LIVE-VERIFIED (probe 4): label widgets render their
            # WIDGETLABEL, not the 'Label' config par. An expression on
            # Widgetlabel makes the displayed status track the par live.
            widgets["status_l"].par.Widgetlabel.expr = "op.vcon.par.Status"
            say("  status label bound to Status par (Widgetlabel expr)")
        except Exception as exc:
            say(f"  (status bind: {exc})")

    say("wiring live output-name preview")
    preview = "op.vcon.op('panel_callbacks').module.PreviewOutput()"
    for name in ("source", "destination"):
        if name in widgets:
            if setp(widgets[name], "Onvaluechangescript0", preview):
                say(f"  {name}: preview wired")
    # QUALITY slider: every drag tick sets MvO's quality slider LIVE
    # (Setquality promoted hook — same pattern as Setfitpath).
    if "quality_s" in widgets:
        setp(widgets["quality_s"], "Onvaluechangescript0",
             "op.vcon.op('panel_callbacks').module.OnQualityChanged()")
        say("  quality_s: live MvO sync wired")
    # CODEC: repopulates subtype/format menus, previews, AND applies the
    # codec to MvO LIVE (JP: dropdown changes must show in MvO now).
    # The combined hook chain fires: UpdateSubtypes re-filters menus,
    # OnSelectionChanged pushes the choice into MvO via Setparams().
    selchange = ("op.vcon.op('panel_callbacks').module."
                 "OnSelectionChanged()")
    if "codec_dd" in widgets:
        setp(widgets["codec_dd"], "Onvaluechangescript0",
             "op.vcon.op('panel_callbacks').module.UpdateSubtypes(); "
             + selchange)
        say("  codec_dd: menus + live MvO sync wired")
    # SUBTYPE: re-filters the FORMAT menu per subtype (ProRes 422 vs
    # 4444 sets differ — JP: format options must follow the subtype)
    # and applies the subtype live.
    if "subtype_dd" in widgets:
        setp(widgets["subtype_dd"], "Onvaluechangescript0",
             "op.vcon.op('panel_callbacks').module.UpdateSubtypes(); "
             + selchange)
        say("  subtype_dd: format filter + live MvO sync wired")
    # FORMAT: previously wired to NOTHING — the live-apply gap JP found
    # (MvO's parameters didn't move on format change).
    if "format_dd" in widgets:
        setp(widgets["format_dd"], "Onvaluechangescript0", selchange)
        say("  format_dd: live MvO sync wired")
    # SCALED toggle: rewire fit path LIVE + toggle SCALE dropdown visibility
    if "scaled_t" in widgets:
        setp(widgets["scaled_t"], "Onvaluechangescript0",
             "op.vcon.op('panel_callbacks').module._update_res_fields()")
        say("  scaled_t: live fit rewire wired")
    if "destination" in widgets:
        setp(widgets["destination"], "Valueparexec",
             "op.vcon.op('panel_callbacks').module.NormalizeDestination()")

    # ---- queue lister points at queue_table --------------------------------
    # Widgets are now FLAT children: the lister COMP IS the panel child
    # (no wrapper to descend). Its source par wasn't found under 'source'
    # before — dump candidates and try each (docsHelper error showed the
    # old path resolved inside the lister, where par names differ).
    say("wiring batch queue lister")
    q = panelcomp.op("queue")
    if q is not None:
        wired = False
        for cand in ("sourcedat", "Sourcedat", "source", "Source",
                     "dat", "Dat"):
            par = getattr(q.par, cand, None)
            if par is not None:
                try:
                    par.val = qt
                    say(f"  lister source via '{cand}' -> queue_table")
                    wired = True
                    break
                except Exception:
                    continue
        if not wired:
            names = [p.name for p in q.customPars if "ourc" in p.name
                     or p.name.lower().startswith("dat")]
            say(f"  !! lister source par not found. Candidates: "
                f"{', '.join(names) or 'none'}")

    # ---- panel Execute DAT: batch tick --------------------------------------
    # VERIFIED pattern from build_network.py's controller tick: the Execute
    # DAT requires the COMPLETE function set (onFrameStart, onFrameEnd,
    # onCreate, onStart, onExit) — a missing onFrameEnd raised 'Cannot find
    # function named: onFrameEnd' live. Callback goes in the DAT's text;
    # pars are framestart/frameend/active.
    say("creating panel Execute DAT (batch tick)")
    ex = vcon.create(executeDAT, "panel_tick")
    ex.nodeX = 300
    ex.nodeY = 30
    ex.text = (
        "# Panel tick: feed the batch queue when the encoder is idle.\n"
        "\n"
        "\n"
        "def onFrameStart(frame):\n"
        "    try:\n"
        "        op.vcon.op('panel_callbacks').module.onFrame()\n"
        "    except Exception:\n"
        "        pass\n"
        "\n"
        "\n"
        "def onFrameEnd(frame):\n"
        "    pass\n"
        "\n"
        "\n"
        "def onCreate():\n"
        "    pass\n"
        "\n"
        "\n"
        "def onStart():\n"
        "    pass\n"
        "\n"
        "\n"
        "def onExit():\n"
        "    pass\n"
    )
    for p in ("framestart", "frameend", "active"):
        try:
            getattr(ex.par, p).val = 1
        except Exception as exc:
            say(f"  (exec {p}: {exc})")

    say("=" * 52)
    say(f"panel built: {panelcomp.path}")
    # Fire the per-codec hook ONCE so every dropdown starts valid for the
    # seeded codec (NotchLC): SUBTYPE greyed, FORMAT rgb+rgba (rgb on),
    # QUALITY slider live. No 'none' anywhere from the very first frame.
    try:
        mod.UpdateSubtypes()
        say("initial codec state applied (NotchLC defaults)")
    except Exception as exc:
        say(f"  (initial UpdateSubtypes: {exc})")
    say("START with a FOLDER in SOURCE enqueues its movies; the panel")
    say("tick feeds them to the encoder one at a time.")
    say("=" * 52)


build()
