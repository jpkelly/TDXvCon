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

#: outer-name -> (tox, x, y, w, h)
_WIDGETS = {
    "source":       ("fieldFileBrowser",   10, 596, 540, 30),
    "destination":  ("fieldFolderBrowser", 10, 556, 540, 30),
    "codec_dd":     ("dropDownMenu",       10, 506, 260, 30),
    "subtype_dd":   ("dropDownMenu",      290, 506, 260, 30),
    "format_dd":    ("dropDownMenu",       10, 456, 260, 30),
    "quality_dd":   ("dropDownMenu",      290, 456, 260, 30),
    "fps_f":        ("fieldString",        10, 406, 160, 30),
    "res_f":        ("fieldString",       180, 406, 160, 30),
    "fit_dd":       ("dropDownMenu",      350, 406, 200, 30),
    "start_b":      ("buttonMomentary",    10, 346, 120, 36),
    "pause_b":      ("buttonMomentary",   140, 346, 120, 36),
    "stop_b":       ("buttonMomentary",   270, 346, 120, 36),
    "output_l":     ("label",             400, 346, 150, 36),
    "prog_s":       ("sliderHorz",         10, 296, 380, 30),
    "status_l":     ("label",             400, 296, 150, 30),
    "queue":        ("lister",             10,  10, 540, 270),
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
    "res_f": "RES",
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
    place(panelcomp, 0, 0, 560, 640)

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
    # Buttons' face text (off/on labels, live-dumped) — the title is separate
    for name, text in [("start_b", "START"), ("pause_b", "PAUSE"),
                       ("stop_b", "STOP")]:
        if name in widgets:
            setp(widgets[name], "Buttonofflabel", text)
            setp(widgets[name], "Buttononlabel", text)

    # ---- defaults ----------------------------------------------------------
    say("configuring widgets (external pars only)")
    for name, val in [("fps_f", "auto"), ("res_f", "auto")]:
        if name in widgets:
            setp(widgets[name], "Value0", val)
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
    for name in ("source", "destination", "codec_dd", "subtype_dd",
                 "format_dd", "quality_dd"):
        if name in widgets:
            if setp(widgets[name], "Onvaluechangescript0", preview):
                say(f"  {name}: preview wired")
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
