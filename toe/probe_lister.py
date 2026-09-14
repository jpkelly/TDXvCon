"""Probe 11: why is the lister invisible in the panel?

Paste in the TD textport:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_lister.py',
              encoding='utf-8').read())

Checks the queue widget's existence, panel placement, and the
lister-specific visibility question: widget COMPs that render TABLES
have a different look than containers — the lister's own internal
rendering handles the background. Prints geometry, children count (a
live lister has ~30 internals; a dead copy has few), and the
Inputtabledat link, plus a quick cell dump of queue_table.
"""

p = op('/project1/vcon/panel')
q = p.op('queue')
if q is None:
    print('[probe] queue NOT FOUND. panel children:',
          [c.name for c in p.children])
    raise SystemExit

try:
    print(f'[probe] queue: x={q.par.x.eval()} y={q.par.y.eval()} '
          f'w={q.par.w.eval()} h={q.par.h.eval()}')
except Exception as exc:
    print(f'[probe] geometry read failed: {exc}')

kids = [c.name for c in q.children]
print(f'[probe] queue internal children ({len(kids)}): '
      f'{kids[:12]}{"..." if len(kids) > 12 else ""}')
print('[probe] (a LIVE lister has ~30 internals — parExec, select2,')
print('[probe]  ListerExt, out_table, etc. Few = dead wrapper copy.)')

try:
    print(f'[probe] Inputtabledat = {q.par.Inputtabledat.eval()!r}')
except Exception as exc:
    print(f'[probe] Inputtabledat read failed: {exc}')

t = op.vcon.op('queue_table')
print(f'[probe] queue_table at vcon level: {"FOUND" if t else "MISSING"}')
if t is not None:
    try:
        print(f'[probe]   rows={t.numRows} cols={t.numCols} '
              f'row0={[t[0, c].val for c in range(t.numCols)]!r}')
    except Exception as exc:
        print(f'[probe]   table read failed: {exc}')
