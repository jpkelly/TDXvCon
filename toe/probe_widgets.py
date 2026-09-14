"""Widget discovery probe — dump what the loaded widgets actually expose.

Paste this in the TD textport:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_widgets.py',
              encoding='utf-8').read())

Loads the same three widgets build_panel.py uses, into a throwaway COMP,
then prints: the child name loadTox gives them, their custom parameter
PAGES + parameter names on each page, and the menuNames of any menu par.
Destroys the scratch COMP at the end. No state persists.
"""

_TOX_DIR = ("/Applications/TouchDesigner.app/Contents/Resources/tfs/"
            "Samples/Palette/UI/Basic Widgets")
_NAMES = ["fieldFileBrowser", "dropDownMenu", "buttonMomentary",
          "sliderHorz", "label", "fieldString"]

import os


def say(msg):
    print(f"[probe] {msg}")


def dump_pars(w):
    for page in w.customPages:
        names = [p.name for p in page.pars]
        say(f"    page '{page.name}': {', '.join(names)}")


scratch = op('/project1/vcon').create(containerCOMP, 'probe_scratch')
try:
    for n in _NAMES:
        path = os.path.join(_TOX_DIR, f"{n}.tox")
        say(f"--- {n}")
        before = {c.name for c in scratch.children}
        w = scratch.loadTox(path)
        if w is None:
            after = {c.name for c in scratch.children}
            new = after - before
            if not new:
                say("  !! no child appeared")
                continue
            w = scratch.op(sorted(new)[0])
            say(f"  loadTox returned None; child = {w.name}")
        else:
            say(f"  loadTox returned: {w.name}")
        say(f"  path: {w.path}  type: {type(w)}")
        try:
            say(f"  clone par: {w.par.clone.eval() if w.par.clone else None}")
        except Exception as exc:
            say(f"  clone: {exc}")
        # custom pages / par names
        try:
            dump_pars(w)
        except Exception as exc:
            say(f"  customPages: {exc}")
        # built-in pages that matter for wiring (Label page on buttons etc.)
        try:
            for pn in ("label", "button", "menu", "field", "callback"):
                coll = getattr(w.par, pn, None)
                if coll is not None:
                    say(f"  builtin par '{pn}' exists")
        except Exception as exc:
            say(f"  builtin check: {exc}")
        # menu values if it's a menu widget
        try:
            for p in w.customPars:
                if getattr(p, "menuNames", None):
                    say(f"  menu par {p.name}: {list(p.menuNames)[:12]}")
        except Exception as exc:
            say(f"  menu scan: {exc}")
finally:
    scratch.destroy()
    say("scratch destroyed — run build_panel.py next")