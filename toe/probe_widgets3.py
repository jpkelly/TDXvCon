"""Widget probe 3 — the INNER widget's parameter surface + copy pattern.

Paste in the TD textport:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_widgets3.py',
              encoding='utf-8').read())

Probe 2 established: each loaded tox is a WRAPPER COMP (no widget pages)
containing an INNER COMP with the same name (the actual widget). This probe
dumps the inner widget's full parameter surface — the names build_panel.py
must configure: label par, menu par, value par, callback par.

Also verifies the multi-instance pattern the builder will use:
loadTox ONCE, then copy() with unique names (no renames — the no-op rename
is what crashed build_panel.py).

Scratch COMP destroyed at the end.
"""

import os

_TOX_DIR = ("/Applications/TouchDesigner.app/Contents/Resources/tfs/"
            "Samples/Palette/UI/Basic Widgets")
_NAMES = ["fieldFileBrowser", "fieldFolderBrowser", "dropDownMenu",
          "sliderHorz", "label", "buttonMomentary"]

_BUILTIN = {"Common", "Xform", "Transform", "Layout", "Panel", "Look",
            "Children", "Drag/Drop", "Extensions", "Internal OP",
            "Node View"}


def say(msg):
    print(f"[probe3] {msg}")


def dump_inner(inner):
    """Full page/par dump of the actual widget COMP."""
    for pg in inner.pages:
        if pg.name in _BUILTIN:
            continue
        try:
            pars = []
            for p in pg.pars:
                tag = p.name
                menus = getattr(p, "menuNames", None)
                if menus:
                    tag = f"{p.name}[{'|'.join(list(menus)[:6])}]"
                pars.append(tag)
            say(f"    [{pg.name}] {', '.join(pars)}")
        except Exception as exc:
            say(f"    [{pg.name}] (dump failed: {exc})")


scratch = op('/project1/vcon').create(containerCOMP, 'probe3')
try:
    for name in _NAMES:
        say(f"=== {name}.tox")
        ret = scratch.loadTox(os.path.join(_TOX_DIR, f"{name}.tox"))
        outer = ret if ret is not None else scratch.op(name)
        inner = outer.op(name)          # same-named child = the widget
        say(f"  outer: {outer.name} ({len(outer.pages)} pages)"
            f"  inner exists: {inner is not None}")
        if inner is None:
            continue
        dump_inner(inner)
        # try the par names we intend to use in the builder
        for probe_par in ("label", "menunames", "menulabels", "value0",
                          "callback", "button", "field"):
            p = getattr(inner.par, probe_par, None)
            if p is not None:
                say(f"    CONFIRMED par: {probe_par} -> {p.name}")
finally:
    scratch.destroy()
    say("scratch destroyed")

# ---- the copy pattern the builder will use -----------------------------
say("=== copy pattern: load dropDownMenu once, copy 3x unique names")
scratch2 = op('/project1/vcon').create(containerCOMP, 'probe3b')
try:
    ret = scratch2.loadTox(os.path.join(_TOX_DIR, "dropDownMenu.tox"))
    outer = ret if ret is not None else scratch2.op("dropDownMenu")
    say(f"  loaded outer: {outer.name}")
    for uniq in ("codec_dd", "subtype_dd", "format_dd"):
        c = scratch2.copy(outer, name=uniq)
        if c is None:
            say(f"  copy {uniq}: returned None!")
        else:
            inner = c.op("dropDownMenu")
            say(f"  copy {uniq}: OK  inner present: {inner is not None}")
    # and setting a menu on the inner of the first copy — the real config op
    c0 = scratch2.op("codec_dd")
    inner = c0.op("dropDownMenu")
    if inner is not None:
        for p in inner.customPars:
            if getattr(p, "menuNames", None) or "menu" in p.name.lower():
                say(f"  menu-ish par: {p.name} menus={list(getattr(p, 'menuNames', []) or [])[:8]}")
        mn = getattr(inner.par, "menunames", None)
        if mn is not None:
            inner.par.menunames = "notchlc hap prores"
            say(f"  set menunames OK -> {inner.par.menunames.eval()}")
        else:
            say("  no 'menunames' par — see menu-ish pars above")
finally:
    scratch2.destroy()
    say("scratch2 destroyed")