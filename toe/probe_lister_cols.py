"""Probe 12: the live colDefine — column widths after auto-define.

Paste in the TD textport:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_lister_cols.py',
              encoding='utf-8').read())

The auto-generated columns gave '#' a huge width (JP: the number column
eats the lister). Dumps the LIVE colDefine table (in the lister's
Configcomp, whose path probe 9 showed as listerConfig) so widths and
the 'progress' column can be corrected by editing the real config.
"""

q = op('/project1/vcon/panel/queue')
if q is None:
    raise RuntimeError('queue lister not found')

print('[probe] Configcomp par:', end=' ')
try:
    print(q.par.Configcomp.eval())
except Exception as exc:
    print(f'(read failed: {exc})')

# the config COMP the lister created (probe 9: /project1/vcon/panel/listerConfig)
cfg = op('/project1/vcon/panel/listerConfig')
if cfg is None:
    print('[probe] listerConfig MISSING at panel level')
    cfg = q.op('listerConfig')
if cfg is None:
    print('[probe] no config COMP found')
else:
    print(f'[probe] config COMP: {cfg.path}')
    for c in cfg.children:
        info = ''
        try:
            info = f' ({c.numRows}x{c.numCols})'
        except Exception:
            pass
        print(f'  {c.name}{info}')
    t = cfg.op('colDefine')
    if t is not None:
        print(f'[probe] colDefine ({t.numCols} cols x {t.numRows} rows):')
        for c in range(t.numCols):
            col = []
            for r in range(t.numRows):
                col.append(f'{t[r, c].val!r}')
            print(f'  col {c}: {col}')
    # also the define table
    d = cfg.op('define')
    if d is not None:
        print(f'[probe] define ({d.numRows}x{d.numCols}):')
        for r in range(d.numRows):
            print(f'  {d[r, 0].val!r}: {d[r, 1].val!r}')
