"""capture_variant.py — capture the SCALED-OFF layout of the FPS/SCALE row.

The FPS/SCALE row has TWO hand-tuned arrangements (JP):
  SCALE ON  -> canonical: fps + scale controls share the row (the
               canonical capture, toe/panel_layout_captured.py)
  SCALE OFF -> variant: the scale controls hide and the FPS group
               re-positions (NOT hard-left) so the row reads cleanly

Normally run via the in-toe runner, which routes by the SCALE toggle
itself — one saved one-liner captures whichever layout is on screen:

    exec(op.vcon.op('panel_capture_run').text)

(SCALE ON -> capture_panel.py / the canonical; SCALE OFF -> this.)

Captures x/y/w/h + display AND the per-layout widget pars (label and
button widths — these differ between the two arrangements; leaving OFF's
wide Labelwidth set is what broke the ON row), DIFFS them against the
canonical capture, and writes toe/panel_layout_variant.py with only the
DELTAS — anything not captured keeps its canonical placement. Refuses to
run with SCALE ON (that state belongs to the canonical capture). The
summary prints ready-to-paste _ROW_LAYOUTS blocks for the bake into
vcon_panel_callbacks.py (the runtime switcher).
"""

PANEL = '/project1/vcon/panel'
ROW_WIDGETS = ("fps_t", "fps_f", "scaled_t",
               "scale_dd", "fit_dd", "resw_f", "resh_f")
#: the FPS trio — display IS captured for these (the scale group's
#: visibility is derived at runtime from the toggle/custom state, so it
#: is never captured)
_FPS_GROUP = ("fps_t", "fps_f", "scaled_t")

#: widget pars that are part of the ARRANGEMENT, not static styling —
#: a wider container needs a wider label/button or the row reads wrong
_LAYOUT_PARS = ("Labelwidth", "Buttonwidth", "Labeldisplay")

CANON_PATH = ('/Users/jp/Documents/GitHub/vCon/toe/'
              'panel_layout_captured.py')
OUT_PATH = ('/Users/jp/Documents/GitHub/vCon/toe/'
            'panel_layout_variant.py')

p = op(PANEL)
if p is None:
    raise RuntimeError('panel not found — build it first')

# --- state gate: this capture is ONLY for SCALE OFF --------------------
st = p.op('scaled_t')
if st is None:
    raise RuntimeError('scaled_t not found — rebuild the panel first')
if bool(st.par.Value0.eval()):
    raise RuntimeError(
        "SCALE is ON — the ON layout is the CANONICAL capture "
        "(capture_panel.py). Flip SCALE OFF, arrange the row, then "
        "re-run: exec(op.vcon.op('panel_capture_run').text)")

# --- canonical baseline -------------------------------------------------
try:
    with open(CANON_PATH, encoding='utf-8') as _f:
        _ns = {}
        exec(compile(_f.read(), CANON_PATH, 'exec'), _ns)
    canonical = _ns['CAPTURED_PANEL']
except Exception as exc:
    raise RuntimeError(
        f'cannot load the canonical capture ({CANON_PATH}): {exc} — '
        'capture the canonical (SCALE ON) layout FIRST')

# --- capture + diff vs canonical ---------------------------------------
issues = []
captured = {}
for name in ROW_WIDGETS:
    w = p.op(name)
    if w is None:
        issues.append(f'{name}: MISSING from panel — skipped')
        continue
    try:
        mine = {k: w.par[k].eval() for k in ('x', 'y', 'w', 'h')}
        mine['display'] = bool(w.par.display.eval())
    except Exception as exc:
        issues.append(f'{name}: par read failed: {exc}')
        continue
    centry = canonical.get(name) or {}
    cgeom = centry.get('geometry') or {}
    cpars = centry.get('pars') or {}
    cdisp = bool(cpars.get('display', True))
    delta = {}
    for k in ('x', 'y', 'w', 'h'):
        if cgeom.get(k) != mine[k]:
            delta[k] = mine[k]
    if name in _FPS_GROUP and cdisp != mine['display']:
        delta['display'] = mine['display']
    for k in _LAYOUT_PARS:
        try:
            v = w.par[k].eval()
        except Exception:
            continue        # par doesn't exist on this widget type
        # canonical 'pars' holds DIFFS vs stock only — a key absent from
        # it has an unknown baseline, so record the live value outright
        if k not in cpars or cpars[k] != v:
            delta[k] = v
    if delta:
        captured[name] = delta
        print(f'[variant] {name}: {delta}')
    else:
        print(f'[variant] {name}: unchanged from canonical — not captured')

# --- write the variant dump (deltas only) -------------------------------
out = [
    "#: SCALE-OFF layout capture of the FPS/SCALE row (JP hand-tuned).",
    "#: DELTAS vs the canonical capture (panel_layout_captured.py) —",
    "#: any widget/key not listed keeps its canonical placement.",
    "#: Baked into vcon_panel_callbacks._ROW_LAYOUTS['off'] (the runtime",
    "#: switcher); ['on'] comes from the canonical capture. Re-capture",
    "#: after any hand re-arrangement with SCALE OFF:",
    "#:   exec(op.vcon.op('panel_capture_run').text)",
    "CAPTURED_VARIANT = {",
    "    'scaled_off': {",
]
for _name in ROW_WIDGETS:
    if _name in captured:
        out.append(f"        {_name!r}: {captured[_name]!r},")
out += ["    },", "}"]
with open(OUT_PATH, 'w', encoding='utf-8') as _f:
    _f.write("\n".join(out) + "\n")
print(f"[variant] wrote {OUT_PATH} ({len(captured)} widget deltas)")


def _fmt(v):
    """Compact numeric repr — ints without .0 (panel pars eval float)."""
    if isinstance(v, bool):
        return repr(v)
    try:
        f = float(v)
    except Exception:
        return repr(v)
    return str(int(f)) if f.is_integer() else repr(round(f, 2))


def _merged(name, use_delta):
    """Canonical placement overlayed with the captured deltas."""
    centry = canonical.get(name) or {}
    cgeom = centry.get('geometry') or {}
    cpars = centry.get('pars') or {}
    out = {k: cgeom[k] for k in ('x', 'y', 'w', 'h') if k in cgeom}
    if name in _FPS_GROUP:
        out['display'] = bool(cpars.get('display', True))
    for k in _LAYOUT_PARS:
        if k in cpars:
            out[k] = cpars[k]
    if use_delta:
        out.update(captured.get(name) or {})
    return out


# --- ready-to-paste bake blocks (both layouts, merged) ------------------
print('[variant] ---- paste into vcon_panel_callbacks._ROW_LAYOUTS ----')
for _key, _use_d in (('on', False), ('off', True)):
    print(f"    {_key!r}: {{")
    for _name in ROW_WIDGETS:
        if p.op(_name) is None:
            continue
        _items = ", ".join(f"{_k!r}: {_fmt(_v)}"
                           for _k, _v in _merged(_name, _use_d).items())
        print(f"        {_name!r}: {{{_items}}},")
    print("    },")

if issues:
    print('[variant] ISSUES:')
    for _i in issues:
        print(f'[variant]   - {_i}')
print('[variant] done — flip SCALE ON and re-run the same exec to '
      'capture/verify the canonical layout')