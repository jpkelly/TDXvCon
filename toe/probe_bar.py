"""Probe 8: why is the green fill missing from the progress bar?

Paste in the TD textport:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_bar.py',
              encoding='utf-8').read())

The gray track paints (Background TOP link works). Checks the fill:
  1. its par.top link state and mode (expression vs constant)
  2. its paint TOP's color
  3. its w expression + evaluated width at the CURRENT Progress value
  4. z-order: children draw in network X order — fill's nodeX vs track's
"""

p = op('/project1/vcon/panel')
f = p.op('prog_fill')
t = p.op('prog_track')
if f is None or t is None:
    raise RuntimeError('bars missing')

print('[probe] FILL:')
for label, par in [('par.top', f.par.top), ]:
    try:
        print(f'  {label} eval = {par.eval()!r}')
        print(f'  {label} mode = {par.mode!r}  expr = {par.expr!r}')
    except Exception as exc:
        print(f'  {label} read failed: {exc}')
pt = f.op('paint')
print(f'  paint TOP: {"exists" if pt is not None else "MISSING"}')
if pt is not None:
    print(f'  paint color: {pt.par.colorr.eval():.2f},{pt.par.colorg.eval():.2f},{pt.par.colorb.eval():.2f} alpha={pt.par.alpha.eval()}')
try:
    print(f'  w expr = {f.par.w.expr!r}   w eval = {f.par.w.eval()!r}')
except Exception as exc:
    print(f'  w read failed: {exc}')
try:
    prog = op.vcon.par.Progress.eval()
    print(f'  Progress par = {prog!r}  (expected fill w = {prog * 620:.1f})')
except Exception as exc:
    print(f'  Progress read failed: {exc}')

print('[probe] Z-ORDER (children draw in network-X order; LOWER nodeX = drawn later/on top in TD panels... actually depth layer):')
for c in (t, f):
    try:
        print(f'  {c.name}: nodeX={c.nodeX} nodeY={c.nodeY} layer={c.par.layer.eval()}')
    except Exception as exc:
        print(f'  {c.name}: layer read failed: {exc}')

print('[probe] If fill w eval tracks Progress, the geometry works and the issue is paint/z-order.')
print('[probe] If w eval stays 620/None, the expression did not take.')
