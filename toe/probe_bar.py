"""Probe 7: verify the progress bar's existence, placement, and paint.

Paste in the TD textport:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_bar.py',
              encoding='utf-8').read())

Checks every link in the bar chain on the LIVE panel:
  1. prog_track / prog_fill exist and their x/y/w/h
  2. each has a 'paint' Constant TOP inside, and par.top references it
  3. the fill's w expression and its evaluated width
  4. the Progress par value itself
  5. whether the panel's children even include the bars (name drift?)
"""

p = op('/project1/vcon/panel')
if p is None:
    raise RuntimeError('panel not found')

print('[probe] panel children:', [c.name for c in p.children])

for name in ('prog_track', 'prog_fill'):
    w = p.op(name)
    if w is None:
        print(f'[probe] {name}: MISSING')
        continue
    try:
        geom = (w.par.x.eval(), w.par.y.eval(),
                w.par.w.eval(), w.par.h.eval())
        print(f'[probe] {name}: x,y,w,h = {geom}')
    except Exception as exc:
        print(f'[probe] {name}: geometry read failed: {exc}')
        geom = None
    # paint TOP inside?
    pt = w.op('paint')
    print(f'[probe] {name}/paint: {"exists" if pt is not None else "MISSING"}')
    if pt is not None:
        try:
            print(f'[probe]   paint res: {pt.width}x{pt.height} '
                  f'pixel={pt.par.colorr.eval():.2f},{pt.par.colorg.eval():.2f},'
                  f'{pt.par.colorb.eval():.2f}')
        except Exception as exc:
            print(f'[probe]   paint read: {exc}')
    # par.top reference
    try:
        t = w.par.top
        print(f'[probe] {name}.par.top = {t.eval()!r}')
    except Exception as exc:
        print(f'[probe] {name}.par.top read failed: {exc}')

# fill width expression + value
f = p.op('prog_fill')
if f is not None:
    try:
        print(f'[probe] fill w expr: {f.par.w.expr!r}  eval={f.par.w.eval()!r}')
    except Exception as exc:
        print(f'[probe] fill w read: {exc}')

# the Progress par itself
try:
    v = op.vcon.par.Progress.eval()
    print(f'[probe] Progress par = {v!r}')
except Exception as exc:
    print(f'[probe] Progress par read failed: {exc}')