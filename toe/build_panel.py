"""build_panel.py — generate the vCon panel inside the vCon COMP. (v2)

Run in the TouchDesigner TEXTPORT (never import):

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/build_panel.py',
              encoding='utf-8').read())

Creates /project1/vcon/panel — Basic Widgets loaded from the app bundle's
palette .tox files, configured ENTIRELY through their external (custom)
parameters. Widgets are never entered or modified internally.

LIVE-VERIFIED FACTS this version is built on (probes 1-3, 2026-09-13):
  - loadTox(path) returns a WRAPPER COMP whose single child of the same
    name is the actual widget; config pars live on the inner COMP's
    custom pages (the wrapper has only builtin pages).
  - op(name) from a COMP SELF-MATCHES — use a children scan, not op().
  - Widget custom pars are First-uppercase (TD naming rule): Menunames,
    Menulabels, Value0, Label. Value0 on a dropDownMenu IS a menu par;
    names/labels are space-delimited, quoted when containing spaces.
  - Renaming to a name that already exists inside raises 'duplicate
    operator name'; copy(widget, name=unique) works for multi-instance.
  - The vcon COMP gets a Global OP Shortcut ('vcon') so widget commands
    and binds are location-independent (op.vcon from anywhere).
"""

import os

_TOX_DIR = ("/Applications/TouchDesigner.app/Contents/Resources/tfs/"
            "Samples/Palette/UI/Basic Widgets")
COMP_PARENT = "/project1/vcon"
COMP_NAME = "panel"
REPO = "/Users/jp/Documents/GitHub/vCon"

#: panel children: outer-name -> (tox name, x, y, w, h)  [y up from bottom]
_WIDGETS = {
    "source":       ("fieldFileBrowser",   10, 470, 540, 30),
    "destination":  ("fieldFolderBrowser", 10, 410, 540, 30),
    "codec_dd":     ("dropDownMenu",       10, 350, 250, 30),
    "subtype_dd":   ("dropDownMenu",      280, 350, 270, 30),
    "format_dd":    ("dropDownMenu",       10, 290, 250, 30),
    "quality_dd":   ("dropDownMenu",      280, 290, 270, 30),
    "fps_f":        ("fieldString",        10, 230, 120, 30),
    "res_f":        ("fieldString",        140, 230, 130, 30),
    "fit_dd":       ("dropDownMenu",      280, 230, 270, 30),
    "start_b":      ("buttonMomentary",    10, 170, 120, 34),
    "pause_b":      ("buttonMomentary",   140, 170, 120, 34),
    "stop_b":       ("buttonMomentary",   270, 170, 120, 34),
    "prog_s":       ("sliderHorz",         10, 110, 400, 30),
    "status_l":     ("label",              10,  60, 540, 26),
}

#: Button custom pars (LIVE-DUMPED from buttonMomentary):
#:   Offtoonscript0 — script fired on press (momentary off->on)
#:   Buttonofflabel / Buttononlabel — the visible text
_BUTTON_SCRIPT_PAR = "Offtoonscript0"


def say(msg):
    print(f"[panel] {msg}")


def inner_of(wrapper):
    """The actual widget COMP inside a loadTox wrapper.

    children scan — op(name) from the wrapper would SELF-MATCH the
    wrapper (verified), so a lookup by name is useless here.
    """
    for c in wrapper.children:
        if c.name == wrapper.name or c.isPanel:
            return c
    say(f"!! no inner widget inside {wrapper.path}")
    return None


def place(outer, x, y, w, h):
    """Panel layout of the wrapper (Layout pars are lowercase x/y/w/h)."""
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
    """Populate a dropDownMenu: Menunames/Menulabels then Value0.

    Menulabels is space-delimited with quotes around entries containing
    spaces — the caller passes RAW label text; quoting happens here ONCE
    (a previous version double-quoted and TD reported 'Invalid menu items').
    """
    ok = True
    ok &= setp(inner, "Menunames", " ".join(names))
    quoted = " ".join(f"'{l}'" if " " in l else l for l in labels)
    ok &= setp(inner, "Menulabels", quoted)
    if default in names:
        ok &= setp(inner, "Value0", default)
    return ok


def build():
    say("=" * 52)
    say("building vCon panel (v2)")
    say("=" * 52)

    vcon = op(COMP_PARENT)
    if vcon is None:
        raise RuntimeError(f"{COMP_PARENT} not found — run build_network.py "
                           f"first, then this script")

    # Global OP Shortcut: widgets reach the COMP from anywhere via op.vcon
    try:
        vcon.par.opshortcut = "vcon"
    except Exception as exc:
        say(f"(opshortcut: {exc})")

    old = vcon.op(COMP_NAME)
    if old is not None:
        say(f"removing existing {COMP_NAME}")
        old.destroy()
    oldcb = vcon.op("panel_callbacks")
    if oldcb is not None:
        oldcb.destroy()

    # ---- callbacks DAT (file-linked, like the controller DAT) -----------
    say("creating panel_callbacks DAT (file-linked)")
    cb = vcon.create(textDAT, "panel_callbacks")
    cb.nodeX = 300
    cb.nodeY = 150
    cb.par.file = f"{REPO}/toe/vcon_panel_callbacks.py"
    cb.par.syncfile = 1

    # ---- panel container -------------------------------------------------
    panelcomp = vcon.create(containerCOMP, COMP_NAME)
    panelcomp.nodeX = 300
    panelcomp.nodeY = 260
    place(panelcomp, 0, 0, 560, 500)

    # ---- load widgets (one loadTox per type; copy() for repeats) ---------
    say("loading widgets")
    loaded = {}          # tox name -> outer wrapper
    widgets = {}         # outer name -> inner widget COMP
    for outer_name, (tox, x, y, w, h) in _WIDGETS.items():
        if tox in loaded:
            outer = panelcomp.copy(loaded[tox], name=outer_name)
            if outer is None:
                say(f"!! copy for {outer_name} returned None")
                continue
        else:
            path = os.path.join(_TOX_DIR, f"{tox}.tox")
            outer = panelcomp.loadTox(path)
            if outer is None:
                say(f"!! loadTox({tox}) returned None")
                continue
            outer.name = outer_name      # unique name per widget
            loaded[tox] = outer
        place(outer, x, y, w, h)
        inner = inner_of(outer)
        if inner is not None:
            widgets[outer_name] = inner
    say(f"loaded {len(widgets)}/{len(_WIDGETS)} widgets")

    mod = cb.module

    # ---- labels / defaults ------------------------------------------------
    say("configuring widgets (external pars only)")
    for name, text in [("source", "SOURCE"), ("destination", "DESTINATION"),
                       ("fps_f", "FPS"), ("res_f", "RES")]:
        if name in widgets:
            setp(widgets[name], "Label", text)
    for name, val in [("fps_f", "auto"), ("res_f", "auto")]:
        if name in widgets:
            setp(widgets[name], "Value0", val)

    # ---- menus ------------------------------------------------------------
    codec_names = list(mod.CODECS.keys())
    codec_labels = [mod.CODECS[k]["label"] for k in codec_names]
    if "codec_dd" in widgets:
        set_menu(widgets["codec_dd"], codec_names, codec_labels, "notchlc")

    # v1: union of subtype tokens with 'none' first. Per-codec filtering is
    # a v2 hook — a mismatched pair fails loudly in the controller.
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

    # ---- buttons ----------------------------------------------------------
    say("wiring buttons")
    for name, fn, text in [("start_b", "Start", "START"),
                           ("pause_b", "PauseResume", "PAUSE"),
                           ("stop_b", "Stop", "STOP")]:
        if name not in widgets:
            continue
        inner = widgets[name]
        # Label text on a button lives in Buttonofflabel/Buttononlabel
        # (the plain Label par is the widget's own name label, not the
        # button face text — live dump shows both).
        setp(inner, "Buttonofflabel", text)
        setp(inner, "Buttononlabel", text)
        cmd = f"op.vcon.op('panel_callbacks').module.{fn}()"
        if setp(inner, _BUTTON_SCRIPT_PAR, cmd):
            say(f"  {name}: script via '{_BUTTON_SCRIPT_PAR}' -> {fn}")
        else:
            names = [p.name for p in inner.customPars]
            say(f"  !! {name}: no command par. customPars: {', '.join(names)}")

    # ---- progress bind + status label ------------------------------------
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

    # ---- live 'will create:' preview -------------------------------------
    # Onvaluechangescript0 fires whenever the widget's value changes; the
    # callbacks module recomputes the auto-named output and shows it.
    say("wiring live output-name preview")
    preview = ("op.vcon.op('panel_callbacks').module.PreviewOutput()")
    for name in ("source", "destination", "codec_dd", "subtype_dd",
                 "format_dd", "quality_dd"):
        if name in widgets:
            if setp(widgets[name], "Onvaluechangescript0", preview):
                say(f"  {name}: preview wired")
    # Destination shows only the selected FOLDER (strip an appended file).
    if "destination" in widgets:
        setp(widgets["destination"], "Onvaluesetcompletedscript0",
             "op.vcon.op('panel_callbacks').module.NormalizeDestination()")

    say("=" * 52)
    say(f"panel built: {panelcomp.path}")
    say("open the panel viewer (RMB -> View...) to use it. Adjust the")
    say("layout visually; re-run this script only to regenerate.")
    say("=" * 52)


build()
