"""Probe 13: live state AFTER the explicit colDefine write.

Paste in the TD textport:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_lister_cols.py',
              encoding='utf-8').read())

The build log SAID colDefine was written, but the lister still shows a
wide '#' and a progress column. Determine which layer ignored the
write: dump (1) Autodefinecols state, (2) the colDefine as LIVE-read,
(3) what ListerExt actually derives from the input table.
"""

q = op('/project1/vcon/panel/queue')
if q is None:
    raise RuntimeError('queue lister not found')

print('[probe] par states:')
for pn in ('Autodefinecols', 'Inputtablehasheaders',
           'Refreshoninputchange', 'Lockconfigs'):
    try:
        print(f'  {pn} = {getattr(q.par, pn).eval()!r}')
    except Exception as exc:
        print(f'  {pn}: {exc}')

print('[probe] Configcomp:')
try:
    cfg = q.par.Configcomp.eval()
    print(f'  {cfg}')
except Exception as exc:
    print(f'  read failed: {exc}')
    cfg = None

if cfg is not None:
    cd = cfg.op('colDefine')
    if cd is None:
        print('  colDefine MISSING')
    else:
        print(f'  colDefine LIVE ({cd.numRows}x{cd.numCols}):')
        # print transposed: one line per column
        names = [cd[r, 0].val for r in range(cd.numRows)]
        for c in range(cd.numCols):
            vals = {names[r]: cd[r, c].val for r in range(cd.numRows)}
            print(f'  col {c}: column={vals.get("column")!r} '
                  f'sourceData={vals.get("sourceData")!r} '
                  f'width={vals.get("width")!r} stretch={vals.get("stretch")!r}')

print('[probe] ListerExt derived columns:')
try:
    ext_ = q.op('ListerExt')
    # try common accessors
    for attr in ('cols', 'colDefine', 'columnDefinitions'):
        try:
            v = getattr(ext_, attr)
            print(f'  {attr}: {v}')
        except Exception:
            pass
except Exception as exc:
    print(f'  {exc}')

print('[probe] the RAW input table the lister reads:')
try:
    t = q.par.Inputtabledat.eval()
    print(f'  {t} ({t.numRows}x{t.numCols})')
    for r in range(min(t.numRows, 3)):
        print(f'  row {r}: {[t[r, c].val for c in range(t.numCols)]!r}')
except Exception as exc:
    print(f'  {exc}')
