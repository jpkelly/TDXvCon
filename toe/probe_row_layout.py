"""probe_row_layout.py — dump the LIVE FPS/SCALE row state.

Run in the textport with SCALE in whichever state looks wrong:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_row_layout.py',
              encoding='utf-8').read())

The variant capture records GEOMETRY ONLY (x/y/w/h + display). If a
hand-tune also changed widget pars (Buttonwidth/Labelwidth) or sizing
modes (hmode/vmode/align), those are NOT in the layout switcher and the
row will not reproduce. This prints everything that can move a widget,
plus the _ROW_LAYOUTS entry it SHOULD be at, so the mismatch is visible.
"""

PANEL = '/project1/vcon/panel'
ROW = ("fps_t", "fps_f", "scaled_t", "scale_dd", "fit_dd",
       "resw_f", "resh_f")

#: pars that affect placement/size but are NOT captured by the variant
_EXTRA = ("hmode", "vmode", "align", "alignorder",
          "Labelwidth", "Labeldisplay", "Buttonwidth", "Labelhorizontalmode")

p = op(PANEL)
if p is None:
    raise RuntimeError('panel not found')

st = p.op('scaled_t')
scaled = bool(st.par.Value0.eval()) if st is not None else None
print('=' * 60)
print(f'[row] SCALE is {"ON" if scaled else "OFF"}')

# what the switcher THINKS the row should be
try:
    lay = op.vcon.op('panel_callbacks').module._ROW_LAYOUTS
    expect = lay.get('on' if scaled else 'off') or {}
except Exception as exc:
    expect = {}
    print(f'[row] cannot read _ROW_LAYOUTS: {exc}')

try:
    print(f'[row] panel align={p.par.align.eval()!r} '
          f'w={p.par.w.eval()} h={p.par.h.eval()}')
except Exception:
    pass

for name in ROW:
    w = p.op(name)
    if w is None:
        print(f'[row] {name}: MISSING')
        continue
    try:
        geo = tuple(w.par[k].eval() for k in ('x', 'y', 'w', 'h'))
        disp = bool(w.par.display.eval())
    except Exception as exc:
        print(f'[row] {name}: geometry read failed: {exc}')
        continue
    e = expect.get(name) or {}
    want = tuple(e.get(k) for k in ('x', 'y', 'w', 'h'))
    flag = '' if (None in want or
                  tuple(float(v) for v in geo) ==
                  tuple(float(v) for v in want)) else '   <<< MISMATCH'
    print(f'[row] {name}: live xywh={geo} display={disp} '
          f'expect={want}{flag}')
    extras = {}
    for k in _EXTRA:
        try:
            v = w.par[k].eval()
        except Exception:
            continue
        mark = '' if (k not in e or e[k] == v) else ' <<<'
        extras[k] = f'{v}{mark}'
    if extras:
        print(f'[row]     pars {extras}')

print('[row] done — geometry MISMATCH means the writes are being '
      'overridden; matching geometry with a wrong LOOK means the '
      'hand-tune changed pars the variant capture does not record')
