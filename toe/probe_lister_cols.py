"""Probe 11: the lister's colDefine / row-draw internals.

Paste in the TD textport:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_lister_cols.py',
              encoding='utf-8').read())

JP wants a progress bar BEHIND the file name in each row (colored row
background driven by per-item progress). The lister's colDefine system
governs per-cell/row rendering (backgrounds, editable, etc). This probe
dumps:
  1. the colDefine table (the lister's column configuration)
  2. the callbacks DAT's callback signatures (esp. row/cell draw hooks)
  3. the raw column default table (colDefaults)
so the per-row background can be written against the REAL format.
"""

q = op('/project1/vcon/panel/queue')
if q is None:
    raise RuntimeError('queue lister not found')

print('[probe] lister internals (colDefine + callbacks):')

# 1. the config COMP's children (colDefine etc.)
cfg = q.op('listerConfig')
print('[probe] listerConfig children:',
      [c.name for c in cfg.children] if cfg is not None else 'MISSING')

# 2. any table named like colDefine — dump its contents
for name in ('colDefine', 'colDefaults', 'configDefault'):
    t = (cfg.op(name) if cfg is not None else None) or q.op(name)
    if t is None:
        print(f'[probe] {name}: MISSING')
        continue
    print(f'[probe] {name} ({t.numRows}x{t.numCols}):')
    for r in range(min(t.numRows, 8)):
        print(f'  row {r}: {[t[r, c].val for c in range(t.numCols)]!r}')

# 3. the callbacks DAT — dump its function signatures
cb = (cfg.op('callbacks') if cfg is not None else None) or q.op('callbacks')
if cb is None:
    print('[probe] callbacks DAT: MISSING')
else:
    text = cb.text
    import re as _re
    sigs = _re.findall(r'def (\w+\([^)]*\))', text)
    print(f'[probe] callbacks DAT ({len(sigs)} functions):')
    for s in sigs:
        print(f'  def {s}')

# 4. look for row-draw-related lines in the callbacks text
if cb is not None:
    for kw in ('draw', 'Draw', 'bg', 'Bg', 'color', 'Color', 'progress'):
        lines = [ln for ln in cb.text.splitlines() if kw in ln]
        if lines:
            print(f'[probe] callback lines mentioning {kw!r}:')
            for ln in lines[:6]:
                print(f'    {ln.strip()[:100]}')