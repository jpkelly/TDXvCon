"""Probe 9: the lister widget's source-DAT parameter name.

Paste in the TD textport:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_lister.py',
              encoding='utf-8').read())

Dumps every custom par on the queue lister whose name/label mentions
source, dat, table, or callback — with type, menus, and current value —
so the queue_table DAT can be wired with the real par name. The earlier
'!! lister source par not found' printed only 'Sourceindexinoutput'
as a candidate, so this widens the net: ALL pars, top-level, printed.
"""

q = op('/project1/vcon/panel/queue')
if q is None:
    raise RuntimeError('queue lister not found — build the panel first')

print('[probe] ALL top-level custom pars on queue (lister):')
hits = []
for pg in q.customPages:
    print(f'--- page [{pg.name}]')
    for par in pg.pars:
        n = par.name
        ln = n.lower()
        try:
            cur = par.eval()
        except Exception:
            cur = '(eval failed)'
        style = getattr(par, 'style', '?')
        menus = list(getattr(par, 'menuNames', None) or [])
        print(f'  {n} = {cur!r}  style={style}  menus={menus}')
        if any(k in ln for k in ('source', 'dat', 'table', 'callback',
                                 'data')):
            hits.append(n)

print()
print(f'[probe] data-source candidates: {hits}')
print('[probe] Also: does the lister have internal DATs that hold a')
print('[probe] hardcoded table? Children:',
      [c.name for c in q.children])
