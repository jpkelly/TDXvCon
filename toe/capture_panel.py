"""capture_panel.py — full-fidelity snapshot of your hand-tuned panel.

Run in the TD textport AFTER adjusting the panel by hand:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/capture_panel.py',
              encoding='utf-8').read())

Captures EVERY top-level custom parameter that differs from the stock
widget (geometry, titles, colors, fonts, display states, menu contents)
by diffing against a freshly loaded copy of each widget's tox — so
anything you changed is captured, not just x/y/w/h.

Output: a Python dict per widget (par name -> value), printed AND
written to toe/panel_layout_captured.py. Paste or say "captured" and
it gets baked into build_panel.py as the canonical state.
"""

import os

_TOX_DIR = ("/Applications/TouchDesigner.app/Contents/Resources/tfs/"
            "Samples/Palette/UI/Basic Widgets")
_UI_TOX_DIR = ("/Applications/TouchDesigner.app/Contents/Resources/tfs/"
               "Samples/Palette/UI")

DUMP_PATH = ('/Users/jp/Documents/GitHub/vCon/toe/'
             'panel_layout_captured.py')

p = op('/project1/vcon/panel')
if p is None:
    raise RuntimeError('panel not found — build it first')

#: panel widget name -> tox it came from (mirror of build_panel _WIDGETS)
_TOX_OF = {
    "source": "fieldFileBrowser", "destination": "fieldFolderBrowser",
    "codec_dd": "dropDownMenu", "subtype_dd": "dropDownMenu",
    "format_dd": "dropDownMenu", "quality_s": "sliderHorz",
    "fps_f": "fieldString", "scaled_t": "buttonToggle",
    "scale_dd": "dropDownMenu", "fit_dd": "dropDownMenu",
    "start_b": "buttonMomentary", "pause_b": "buttonMomentary",
    "stop_b": "buttonMomentary", "output_l": "label",
    "prog_s": "sliderHorz", "status_l": "label", "queue": "lister",
}


def _tox_path(name):
    if name == "lister":
        return os.path.join(_UI_TOX_DIR, "lister.tox")
    return os.path.join(_TOX_DIR, f"{name}.tox")


def _safe_geom(c):
    try:
        return (c.par.y.eval(), c.par.x.eval())
    except Exception:
        return (float('inf'), float('inf'))


def _par_snapshot(comp):
    """{par name: eval'd value} of every TOP-LEVEL custom par."""
    out = {}
    for pg in comp.customPages:
        for par in pg.pars:
            try:
                out[par.name] = par.eval()
            except Exception:
                pass
    return out


def _builtin_geom(comp):
    """Layout pars (x/y/w/h) — builtin, not custom, but part of tuning."""
    out = {}
    for name in ('x', 'y', 'w', 'h'):
        try:
            out[name] = comp.par[name].eval()
        except Exception:
            pass
    return out


lines = ["#: Full capture of JP's hand-tuned panel (diff vs stock tox)",
         "#: Format: {widget: {'geometry': {...}, 'pars': {par: value}}}",
         "CAPTURED_PANEL = {"]
scratch = p.create(containerCOMP, '_capture_scratch')

for c in sorted(p.children, key=_safe_geom):
    name = c.name
    if name.startswith('_') or name not in _TOX_OF:
        continue
    # skip the lister's internal nodes (listerConfig etc.)
    try:
        c.par.x.eval()
    except Exception:
        continue

    # Load a STOCK copy of this widget's tox as the diff baseline
    base = None
    toxname = _TOX_OF[name]
    path = _tox_path(toxname)
    if os.path.isfile(path):
        ret = scratch.loadTox(path)
        if ret is not None:
            base = ret
        else:
            new = [ch for ch in scratch.children
                   if ch.name == toxname]
            base = new[0] if new else None

    geom = _builtin_geom(c)
    mine = _par_snapshot(c)
    stock = _par_snapshot(base) if base is not None else {}

    # keep everything that differs from stock (or all pars when no
    # baseline could load)
    if stock:
        diff = {k: v for k, v in mine.items()
                if k not in stock or stock[k] != v}
    else:
        diff = mine

    lines.append(f'    "{name}": {{')
    lines.append(f'        "geometry": {geom!r},')
    lines.append(f'        "pars": {diff!r},')
    lines.append('    },')
    print(f'[capture] {name}: geometry {geom} — {len(diff)} changed pars')

# clean the scratch (all stock copies)
scratch.destroy()

lines.append('}')
text = '\n'.join(lines)
print()
print(text)
print()
print(f'[capture] full dump written to {DUMP_PATH}')
try:
    with open(DUMP_PATH, 'w', encoding='utf-8') as f:
        f.write(text + '\n')
except Exception as exc:
    print(f'[capture] could not write file: {exc}')
