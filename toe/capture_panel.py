"""capture_panel.py — snapshot your hand-tuned panel layout for the builder.

Run in the TD textport AFTER adjusting the panel by hand:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/capture_panel.py',
              encoding='utf-8').read())

Reads every widget's LIVE geometry (x/y/w/h), Labelwidth, Widgetlabel,
and visibility from the actual panel, and prints a Python dict in the
builder's _WIDGETS format. Paste the output back to the assistant; it
gets baked into build_panel.py so future re-runs regenerate YOUR
layout instead of the default grid.

Also writes the same dump to toe/panel_layout_captured.py in the repo
so the values survive even if the textport scroll is lost.
"""

p = op('/project1/vcon/panel')
if p is None:
    raise RuntimeError('panel not found — build it first')

DUMP_PATH = ('/Users/jp/Documents/GitHub/vCon/toe/'
             'panel_layout_captured.py')

def _safe_geom(c):
    """(y, x) for sorting; non-panel children (e.g. lister's config DAT)
    have no Layout pars and sort to the end instead of crashing."""
    try:
        return (c.par.y.eval(), c.par.x.eval())
    except Exception:
        return (float('inf'), float('inf'))


rows = []
for c in sorted(p.children, key=_safe_geom):
    name = c.name
    if name.startswith('_'):
        continue
    # Skip anything without panel Layout pars — listerConfig and friends
    # are the lister's internal DATs, not widgets to capture.
    try:
        x = c.par.x.eval()
        y = c.par.y.eval()
        w = c.par.w.eval()
        h = c.par.h.eval()
    except Exception:
        continue
    try:
        lw = c.par.Labelwidth.eval()
    except Exception:
        lw = None
    try:
        title = str(c.par.Widgetlabel.eval())
    except Exception:
        title = None
    try:
        disp = c.par.display.eval()
    except Exception:
        disp = 1
    rows.append((name, x, y, w, h, lw, title, disp))

lines = ["#: Captured from JP's hand-tuned panel — paste into build_panel.py",
         "_WIDGETS = {"]
for name, x, y, w, h, lw, title, disp in rows:
    geom = f'{x}, {y}, {w}, {h}'
    lines.append(f'    "{name}": ("__tox__", {geom}),'
                 f'   # Labelwidth={lw!r} title={title!r} display={disp}')
lines.append("}")
text = "\n".join(lines)
print(text)
print()
print(f"[capture] {len(rows)} widgets captured — paste the block above to")
print(f"[capture] the assistant. Also written to {DUMP_PATH}")

try:
    with open(DUMP_PATH, 'w', encoding='utf-8') as f:
        f.write(text + "\n")
except Exception as exc:
    print(f"[capture] could not write file: {exc}")