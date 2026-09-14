"""Probe 11b: colDefaults complete + topPath/topFill semantics.

Paste in the TD textport:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_lister_cols.py',
              encoding='utf-8').read())

colDefaults (already seen, 19 rows) defines per-column rendering and
includes topPath/topFill — a TOP drawn behind the cell (JP's bar-behind-
the-filename). This finishes the dump:
  1. ALL 19 colDefaults rows
  2. the ListerExt's col define API
  3. the configDefault COMP children (the colDefine lives here)
"""

q = op('/project1/vcon/panel/queue')
if q is None:
    raise RuntimeError('queue lister not found')

print('[probe] colDefaults — ALL rows:')
t = q.op('colDefaults')
if t is None:
    print('  MISSING')
else:
    for r in range(t.numRows):
        print(f'  {t[r, 0].val!r}: {t[r, 1].val!r}')

print()
print('[probe] ListerExt public methods (col/define/row/draw API):')
ext_ = q.op('ListerExt')
if ext_ is None:
    print('  MISSING')
else:
    names = [m for m in dir(ext_) if not m.startswith('_')
             and any(k in m.lower() for k in ('col', 'define', 'row',
                                              'draw', 'top'))]
    print(f'  {names}')

print()
print('[probe] configDefault COMP children (colDefine lives here):')
cfg = q.op('configDefault')
if cfg is None:
    print('  MISSING')
else:
    for c in cfg.children:
        info = ''
        try:
            info = f' ({c.numRows}x{c.numCols})'
        except Exception:
            pass
        print(f'  {c.name}{info}')
        if hasattr(c, 'numRows') and c.numRows:
            for r in range(min(c.numRows, 20)):
                try:
                    print(f'    {c[r, 0].val!r}: {c[r, 1].val!r}')
                except Exception:
                    pass
