"""Probe 10: inspect the lister's internal error + our table state.

Paste in the TD textport:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_lister.py',
              encoding='utf-8').read())

Prints:
  1. queue_table's full contents (header + rows) as the lister sees them
  2. the lister's Inputtabledat link and header setting
  3. any errors reported on the lister's operators (error() flags)
  4. ListerExt's colDefine — the lister auto-generates columns from the
     header; if col 0's header isn't a clean string, it chokes.
"""

p = op('/project1/vcon/panel')
t = p.op('queue_table')
q = p.op('queue')

print('[probe] queue_table contents:')
if t is None:
    print('  MISSING')
else:
    try:
        print(f'  rows={t.numRows} cols={t.numCols}')
        for r in range(t.numRows):
            print(f'  row {r}: {[t[r, c].val for c in range(t.numCols)]!r}')
    except Exception as exc:
        print(f'  read failed: {exc}')

print('[probe] lister link state:')
if q is not None:
    try:
        v = q.par.Inputtabledat.eval()
        print(f'  Inputtabledat = {v!r}')
        print(f'  Inputtablehasheaders = {q.par.Inputtablehasheaders.eval()!r}')
    except Exception as exc:
        print(f'  par read failed: {exc}')

print('[probe] errors on the queue subtree:')
try:
    errs = []
    for c in q.ops('*'):
        e = c.error()
        if e:
            errs.append(f'  {c.path}: {e}')
    print('\n'.join(errs) if errs else '  (no operator errors)')
except Exception as exc:
    print(f'  error scan failed: {exc}')

print('[probe] ListerExt colDefine (auto columns from header):')
try:
    ext = q.op('ListerExt')
    raw = ext.GetRawData()
    print(f'  raw rows: {len(raw) if raw else 0}')
except Exception as exc:
    print(f'  GetRawData failed: {exc}')
