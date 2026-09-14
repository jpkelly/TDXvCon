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

#: GRID GEOMETRY — the layout is COMPUTED, not hand-placed: rows are
#: indexed top-down, all heights uniform, two columns with fixed spans.
#: Column spans guarantee no widget crosses into its neighbor or past
#: the right edge (x + w <= 640 on a 660-wide panel).
_ROW = 30            # every widget, every row
_PITCH = 45          # row spacing
_TOP = 590           # first row's y (panel origin is bottom-left)
_X = 20              # left margin
_W_FULL = 620        # full-width widgets (label 110 + field 510)
_C1X, _C1W = 20, 290     # settings column 1
_C2X, _C2W = 330, 310    # settings column 2


def _r(n):
    """Panel y for row n (counted from the top)."""
    return _TOP - n * _PITCH


_WIDGETS = {
    # rows 0-1: browsers (full width)
    "source":       ("fieldFileBrowser",   _X, _r(0), _W_FULL, _ROW),
    "destination":  ("fieldFolderBrowser", _X, _r(1), _W_FULL, _ROW),
    # rows 2-4: settings, two columns
    "codec_dd":     ("dropDownMenu",      _C1X, _r(2), _C1W, _ROW),
    "subtype_dd":   ("dropDownMenu",      _C2X, _r(2), _C2W, _ROW),
    "format_dd":    ("dropDownMenu",      _C1X, _r(3), _C1W, _ROW),
    "quality_dd":   ("dropDownMenu",      _C2X, _r(3), _C2W, _ROW),
    "fps_f":        ("fieldString",       _C1X, _r(4), _C1W, _ROW),
    "resmode_dd":   ("dropDownMenu",      _C2X, _r(4), _C2W, _ROW),
    # row 5: FIT (left) | SCALE (right, hidden while Unscaled)
    "fit_dd":       ("dropDownMenu",      _C1X, _r(5), _C1W, _ROW),
    "scale_dd":     ("dropDownMenu",      _C2X, _r(5), _C2W, _ROW),
    # row 6: buttons | OUTPUT name
    "start_b":      ("buttonMomentary",    20, _r(6), 100, _ROW),
    "pause_b":      ("buttonMomentary",   130, _r(6), 100, _ROW),
    "stop_b":       ("buttonMomentary",   240, _r(6), 100, _ROW),
    "output_l":     ("label",             350, _r(6), 290, _ROW),
    # row 7: progress | STATUS
    "prog_s":       ("sliderHorz",        20, _r(7), 330, _ROW),
    "status_l":     ("label",             360, _r(7), 290, _ROW),
    # queue at the bottom
    "queue":        ("lister",             20,  20, 620, 200),
}

#: Field titles via Widgetlabel (LIVE-DUMPED: the widget's title par).
_TITLES = {
    "source": "SOURCE",
    "destination": "DESTINATION",
    "codec_dd": "CODEC",
    "subtype_dd": "SUBTYPE",
    "format_dd": "FORMAT",
    "quality_dd": "QUALITY",
    "fps_f": "FPS",
    "resmode_dd": "RES",
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


def place(outer, x, y, w, h):
    try:
        outer.par.x = x
        outer.par.y = y
        outer.par.w = w
        outer.par.h = h
    except Exception as exc:
        say(f"  (place {outer.name}: {exc})")


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
    say("loading widgets")
    loaded = {}
    widgets = {}
    for outer_name, (tox, x, y, w, h) in _WIDGETS.items():
        if tox in loaded:
            outer = panelcomp.copy(loaded[tox], name=outer_name)
            if outer is None:
                say(f"!! copy for {outer_name} returned None")
                continue
        else:
            path = _TOX_PATHS.get(tox,
                                  os.path.join(_TOX_DIR, f"{tox}.tox"))
            outer = panelcomp.loadTox(path)
            if outer is None:
                say(f"!! loadTox({tox}) returned None")
                continue
            outer.name = outer_name
            loaded[tox] = outer
        place(outer, x, y, w, h)
        inner = inner_of(outer)
        if inner is not None:
            widgets[outer_name] = inner
    say(f"loaded {len(widgets)}/{len(_WIDGETS)} widgets")

    mod = cb.module

    # ---- titles (Widgetlabel — the live-dumped title par) ----------------
    say("setting widget titles (Widgetlabel)")
    for name, title in _TITLES.items():
        if name in widgets:
            setp(widgets[name], "Widgetlabel", title)
    # Labelwidth per column: full-width rows get 110; two-column widgets
    # get 90 so the label never eats the field; small buttons none.
    _LABEL_W = {"source": 110, "destination": 110, "codec_dd": 90,
                "subtype_dd": 90, "format_dd": 90, "quality_dd": 90,
                "fps_f": 60, "resmode_dd": 60, "scale_dd": 70,
                "fit_dd": 60, "output_l": 110, "status_l": 110,
                "start_b": 60, "pause_b": 60, "stop_b": 60}
    for name, lw in _LABEL_W.items():
        if name in widgets:
            setp(widgets[name], "Labelwidth", lw)
    # Buttons' titles were never set in earlier versions (default text
    # 'Momentary Button' showed) — Widgetlabel covers every widget.
    for name, text in [("start_b", "START"), ("pause_b", "PAUSE"),
                       ("stop_b", "STOP")]:
        if name in widgets:
            setp(widgets[name], "Widgetlabel", text)
            setp(widgets[name], "Buttonofflabel", text)
            setp(widgets[name], "Buttononlabel", text)

    # ---- defaults ----------------------------------------------------------
    say("configuring widgets (external pars only)")
    if "fps_f" in widgets:
        setp(widgets["fps_f"], "Value0", "auto")
    # output label: read-only-ish — the preview callback writes its text
    if "output_l" in widgets:
        setp(widgets["output_l"], "Label", "(pick a source)")

    # ---- menus -------------------------------------------------------------
    codec_names = list(mod.CODECS.keys())
    codec_labels = [mod.CODECS[k]["label"] for k in codec_names]
    if "codec_dd" in widgets:
        set_menu(widgets["codec_dd"], codec_names, codec_labels, "notchlc")
    subs = ["none"] + sorted({s for c in mod.CODECS.values()
                              for s in c.get("subtypes", [])})
    if "subtype_dd" in widgets:
        set_menu(widgets["subtype_dd"], subs, subs, "none")
    fmts = ["none", "rgb", "rgba", "yuv4228bit", "yuv42210bit",
            "yuv42212bit", "yuv44410bit", "yuva444412bit", "yuv420",
            "yuv420p10bit", "yuv444p8bit", "yuv444p10bit"]
    if "format_dd" in widgets:
        set_menu(widgets["format_dd"], fmts, fmts, "none")
    qual = mod.CODECS["notchlc"]["qualities"]
    if "quality_dd" in widgets:
        set_menu(widgets["quality_dd"], qual, qual, "optimal")
    if "fit_dd" in widgets:
        set_menu(widgets["fit_dd"],
                 ["fitbest", "fill", "fithorz", "fitvert", "fitoutside"],
                 ["Fit Best", "Stretch", "Fit Width", "Fit Height",
                  "Cover/Crop"],
                 "fitbest")
    # RESOLUTION: Unscaled (source size preserved — fit TOP bypassed) or
    # Scaled, which reveals the SCALE dropdown (quarter..3x). The factor is
    # applied by the CONTROLLER against the movie's real dimensions after
    # load (the panel can't know WxH pre-load); even-dimension clamped.
    if "resmode_dd" in widgets:
        set_menu(widgets["resmode_dd"], ["unscaled", "scaled"],
                 ["Unscaled", "Scaled"], "unscaled")
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
    if "prog_s" in widgets:
        try:
            widgets["prog_s"].par.Value0.bindExpr = "op.vcon.par.Progress"
            say("  progress slider bound to Progress par")
        except Exception as exc:
            say(f"  (progress bind: {exc})")
    if "status_l" in widgets:
        try:
            widgets["status_l"].par.Label.expr = "op.vcon.par.Status"
            say("  status label bound to Status par")
        except Exception as exc:
            say(f"  (status bind: {exc})")

    say("wiring live output-name preview")
    preview = "op.vcon.op('panel_callbacks').module.PreviewOutput()"
    for name in ("source", "destination", "quality_dd"):
        if name in widgets:
            if setp(widgets[name], "Onvaluechangescript0", preview):
                say(f"  {name}: preview wired")
    # CODEC drives subtype/format menu repopulation (+ preview refresh)
    if "codec_dd" in widgets:
        setp(widgets["codec_dd"], "Onvaluechangescript0",
             "op.vcon.op('panel_callbacks').module.UpdateSubtypes()")
        say("  codec_dd: subtype/format filter wired")
    # subtype change re-filters format (ProRes menus differ per subtype)
    if "subtype_dd" in widgets:
        setp(widgets["subtype_dd"], "Onvaluechangescript0",
             "op.vcon.op('panel_callbacks').module.UpdateSubtypes()")
        say("  subtype_dd: format filter wired")
    # RESOLUTION switch toggles the SCALE dropdown's visibility
    if "resmode_dd" in widgets:
        setp(widgets["resmode_dd"], "Onvaluechangescript0",
             "op.vcon.op('panel_callbacks').module._update_res_fields()")
        say("  resmode_dd: scale visibility wired")
    if "destination" in widgets:
        setp(widgets["destination"], "Valueparexec",
             "op.vcon.op('panel_callbacks').module.NormalizeDestination()")

    # ---- queue lister points at queue_table --------------------------------
    say("wiring batch queue lister")
    q = panelcomp.op("queue")
    if q is not None:
        for c in q.children:
            if c.name == "lister" or c.isPanel:
                qinner = c
                break
        else:
            qinner = None
        if qinner is not None:
            try:
                qinner.par.source.dat = qt
                say("  lister source -> queue_table")
            except Exception as exc:
                say(f"  (lister source: {exc})")

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
    say("titles are Widgetlabel; batch queue = lister + queue_table;")
    say("START with a FOLDER in SOURCE enqueues its movies; the panel")
    say("tick feeds them to the encoder one at a time.")
    say("=" * 52)


build()
