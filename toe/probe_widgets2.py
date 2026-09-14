"""Widget probe 2 — full parameter surface + the rename/copy crash repro.

Paste in the TD textport:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_widgets2.py',
              encoding='utf-8').read())

Answers, with ground truth from the LIVE widgets:
  1. Does loading fieldFolderBrowser then dropDownMenu collide (the exact
     sequence that crashed build_panel.py)?
  2. What pages/pars does each widget REALLY expose (full dump — the
     2022-era docs' "Values page" did not appear in probe 1)?
  3. What children live inside each widget (wrapper vs widget)?
  4. Does renaming to a unique name work? Does parent.copy(widget, name=...)
     work (needed for the 4x dropDownMenu instances)?

Everything loads into a scratch COMP destroyed at the end.
"""

import os

_TOX_DIR = ("/Applications/TouchDesigner.app/Contents/Resources/tfs/"
            "Samples/Palette/UI/Basic Widgets")

#: Builtin COMP pages — shown as one line; everything else dumped fully
#: (custom pages hold the widget's real configuration surface).
_BUILTIN = {"Common", "Xform", "Transform", "Layout", "Panel", "Look",
            "Children", "Drag/Drop", "Extensions", "Internal OP", "Node View"}


def say(msg):
    print(f"[probe2] {msg}")


def dump(w):
    say(f"  '{w.name}' pages:")
    for pg in w.pages:
        if pg.name in _BUILTIN:
            continue
        try:
            pars = ", ".join(p.name for p in pg.pars)
        except Exception as exc:
            pars = f"(par list failed: {exc})"
        say(f"    [{pg.name}] {pars}")
    try:
        kids = [c.name for c in w.children]
        say(f"    children: {kids if kids else '(none)'}")
    except Exception as exc:
        say(f"    children: {exc}")


scratch = op('/project1/vcon').create(containerCOMP, 'probe2')
try:
    # -- 1. the crash sequence: browsers THEN menus ------------------------
    for name in ["fieldFileBrowser", "fieldFolderBrowser", "dropDownMenu",
                 "sliderHorz", "label", "buttonMomentary"]:
        before = {c.name for c in scratch.children}
        say(f"--- loading {name}.tox")
        try:
            ret = scratch.loadTox(os.path.join(_TOX_DIR, f"{name}.tox"))
            after = {c.name for c in scratch.children}
            new = sorted(after - before)
            say(f"  loadTox returned: {ret.name if ret else 'None'}"
                f"   new children: {new}")
        except Exception as exc:
            say(f"  loadTox RAISED: {exc}")
            continue
        if ret is not None:
            dump(ret)

    # -- 2. rename to a UNIQUE name (crashed when same-name in panel) ------
    d = scratch.op("dropDownMenu")
    if d is not None:
        say("--- rename test")
        try:
            d.name = "codecmenu"
            say(f"  rename -> 'codecmenu': OK")
        except Exception as exc:
            say(f"  rename RAISED: {exc}")

        # -- 3. copy() for a second menu instance -------------------------
        say("--- copy test")
        try:
            c2 = scratch.copy(d, name="subtypemenu")
            say(f"  copy -> 'subtypemenu': {'OK' if c2 else 'None returned'}")
            if c2 is not None:
                say(f"    copy path: {c2.path}")
        except Exception as exc:
            say(f"  copy RAISED: {exc}")
finally:
    scratch.destroy()
    say("scratch destroyed")