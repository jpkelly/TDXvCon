"""build_panel.py — generate the vCon panel inside the vCon COMP.

Run in the TouchDesigner TEXTPORT (never import):

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/build_panel.py',
              encoding='utf-8').read())

Creates /project1/vcon/panel — a Container COMP of Basic Widgets (loaded
from the app bundle's palette .tox files), laid out in the reference
transcoder's shape: source/destination row, codec settings rows, buttons,
progress + status, and a batch queue list.

SEPARATE from build_network.py on purpose: network rebuilds destroy the
whole vCon COMP (including the panel), so the panel has its own generator.
Re-running THIS script overwrites any manual layout tweaks — an explicit
choice, not an accident. Adjust layout visually in TD afterwards; this
script only needs to run again to regenerate from scratch.

Widget sources: TD app bundle, tfs/Samples/Palette/UI/Basic Widgets —
discovered live 2026-09-13 (no palette global exists on this build).
"""

#: Absolute paths — this script runs inside TD, which may not share the
#: repo's CWD. Override by setting PANEL_TOX_DIR before exec().
_TOX_DIR = ("/Applications/TouchDesigner.app/Contents/Resources/tfs/"
            "Samples/Palette/UI/Basic Widgets")

COMP_PARENT = "/project1/vcon"      # where the panel COMP is created
COMP_NAME = "panel"


def say(msg):
    print(f"[panel] {msg}")


def load_widget(parent, name, x, y, w=240, h=28):
    """Load one Basic Widget .tox into parent; returns the COMP or None."""
    import os
    path = os.path.join(_TOX_DIR, f"{name}.tox")
    if not os.path.isfile(path):
        say(f"!! widget tox not found: {path}")
        return None
    before = [c.name for c in parent.children]
    wcomp = parent.loadTox(path)
    if wcomp is None:
        # loadTox may return None even on success; adopt the new child.
        after = [c.name for c in parent.children]
        new = [n for n in after if n not in before]
        if not new:
            say(f"!! loadTox returned None and no new child appeared ({name})")
            return None
        wcomp = parent.op(new[0])
        say(f"  (loadTox returned None; adopted child {new[0]})")
    wcomp.name = name
    wcomp.nodeX = x
    wcomp.nodeY = y
    try:
        wcomp.par.w = w
        wcomp.par.h = h
    except Exception as exc:
        say(f"  (w/h for {name}: {exc})")
    return wcomp


def set_label(wcomp, text):
    """Set the label parameter on a label/button widget."""
    try:
        wcomp.par.label = text
        return True
    except Exception as exc:
        say(f"  (label on {wcomp.name}: {exc})")
        return False


def set_menu(wcomp, names, labels=None, default=None):
    """Populate a dropDownMenu widget's items. names = menu tokens."""
    try:
        wcomp.par.menunames = " ".join(names)
        if labels:
            wcomp.par.menulabels = " ".join(labels)
        if default and default in names:
            wcomp.par.value0 = default
        return True
    except Exception as exc:
        say(f"  (menu on {wcomp.name}: {exc})")
        return False


def wire_button(button, callback):
    """Point a buttonMomentary's callback at a panel-callbacks function."""
    try:
        button.par.callback = f"parent().op('panel_callbacks').module.{callback}()"
        return True
    except Exception as exc:
        say(f"  (callback on {button.name}: {exc})")
        return False


def build():
    say("=" * 52)
    say("building vCon panel")
    say("=" * 52)

    vcon = op(COMP_PARENT)
    if vcon is None:
        raise RuntimeError(f"{COMP_PARENT} not found — run build_network.py "
                           f"first, then this script")

    old = vcon.op(COMP_NAME)
    if old is not None:
        say(f"removing existing {COMP_PARENT}/{COMP_NAME}")
        old.destroy()
    oldcb = vcon.op("panel_callbacks")
    if oldcb is not None:
        oldcb.destroy()

    # ---- callbacks module DAT (file-linked to the repo, like the
    # controller DAT: edits in the repo live-apply, edits in TD flow back) --
    say("creating panel_callbacks DAT (file-linked)")
    cb = vcon.create(textDAT, "panel_callbacks")
    cb.nodeX = 300
    cb.nodeY = 120
    cb.par.file = ("/Users/jp/Documents/GitHub/vCon/toe/"
                   "vcon_panel_callbacks.py")
    cb.par.syncfile = 1

    # ---- panel container -------------------------------------------------
    say("creating panel Container COMP")
    panelcomp = vcon.create(containerCOMP, COMP_NAME)
    panelcomp.nodeX = 300
    panelcomp.nodeY = 240
    # Base/Widget COMPs may not expose Container Look pars (bgcolor raised
    # tdAttributeError live). Width/height only; the panel's look comes
    # from the widgets' theme anyway.
    try:
        panelcomp.par.w = 560
        panelcomp.par.h = 500
    except Exception as exc:
        say(f"  (w/h: {exc})")

    # ---- widget rows (reference-transcoder layout) -----------------------
    # Row 1: source + destination browsers
    say("widgets: source / destination file+folder browsers")
    src = load_widget(panelcomp, "fieldFileBrowser", x=-260, y=0, w=520)
    dst = load_widget(panelcomp, "fieldFolderBrowser", x=-260, y=-60, w=520)
    if src:
        set_label(src, "SOURCE")
    if dst:
        set_label(dst, "DESTINATION")

    # Row 2: codec / subtype / pixel format / quality
    say("widgets: codec / subtype / pixel format / quality menus")
    codec = load_widget(panelcomp, "dropDownMenu", x=-260, y=-120, w=250)
    subtype = load_widget(panelcomp, "dropDownMenu", x=10, y=-120, w=250)
    fmt = load_widget(panelcomp, "dropDownMenu", x=-260, y=-180, w=250)
    quality = load_widget(panelcomp, "dropDownMenu", x=10, y=-180, w=250)

    # Row 3: fps / resolution / fit mode
    say("widgets: fps / resolution / fit fields")
    fps = load_widget(panelcomp, "fieldString", x=-260, y=-240, w=120)
    res = load_widget(panelcomp, "fieldString", x=-140, y=-240, w=120)
    fitmode = load_widget(panelcomp, "dropDownMenu", x=10, y=-240, w=250)
    if fps:
        set_label(fps, "FPS (keep/number)")
    if res:
        set_label(res, "RES (keep/WxH)")

    # Row 4: buttons
    say("widgets: start / pause / stop buttons")
    start = load_widget(panelcomp, "buttonMomentary", x=-260, y=-300, w=120)
    pauser = load_widget(panelcomp, "buttonMomentary", x=-130, y=-300, w=120)
    stopper = load_widget(panelcomp, "buttonMomentary", x=0, y=-300, w=120)
    if start:
        set_label(start, "START")
        wire_button(start, "Start")
    if pauser:
        set_label(pauser, "PAUSE")
        wire_button(pauser, "PauseResume")
    if stopper:
        set_label(stopper, "STOP")
        wire_button(stopper, "Stop")

    # Row 5: progress + status
    say("widgets: progress slider + status labels")
    prog = load_widget(panelcomp, "sliderHorz", x=-260, y=-360, w=380)
    statusline = load_widget(panelcomp, "label", x=-260, y=-420, w=520)
    statlabel = load_widget(panelcomp, "label", x=130, y=-360, w=120)

    # ---- populate the codec menus from the callbacks module --------------
    say("populating codec menus")
    mod = cb.module
    codec_names = list(mod.CODECS.keys())
    codec_labels = [mod.CODECS[k]["label"] for k in codec_names]
    if codec:
        set_menu(codec, codec_names, codec_labels, default="notchlc")
    if subtype:
        set_menu(subtype, [""], ["(none)"])   # populated on codec change (v1.1)
    if fmt:
        set_menu(fmt, ["rgb", "rgba"], ["RGB", "RGB + Alpha"], default="rgb")
    if quality:
        set_menu(quality, mod.CODECS["notchlc"]["qualities"],
                 default="optimal")
    if fitmode:
        set_menu(fitmode,
                 ["fitbest", "fill", "fithorz", "fitvert", "fitoutside"],
                 ["Fit Best", "Stretch", "Fit Width", "Fit Height",
                  "Cover/Crop"],
                 default="fitbest")

    # ---- bindings --------------------------------------------------------
    say("binding progress/status to the COMP parameters")
    if prog:
        try:
            # Read-only display slider bound 1-way to the Progress par —
            # a bidirectional bindExpr would let a user DRAG progress.
            prog.par.value0.bindExpr = "op('../..').par.Progress"
        except Exception as exc:
            say(f"  (progress bind: {exc})")
    if statusline:
        try:
            statusline.par.label.expr = "op('../..').par.Status"
        except Exception as exc:
            say(f"  (status bind: {exc})")
    if statlabel:
        try:
            statlabel.par.label = "frames 0 / 0"
        except Exception as exc:
            say(f"  (statlabel: {exc})")

    # ---- drag & drop -----------------------------------------------------
    say("enabling drag-and-drop on the panel")
    try:
        panelcomp.par.dropscript = (
            "op('panel_callbacks').module.onDragDrop(args[0])"
        )
    except Exception as exc:
        say(f"  (dropscript: {exc})")

    say("=" * 52)
    say(f"panel built: {panelcomp.path}")
    say("adjust layout/labels visually in TD; re-run this script only to")
    say("regenerate (overwrites tweaks). Open the panel viewer to use it.")
    say("=" * 52)


build()