"""Find the scrollbar parameter on the queue lister.

Run in TD textport:
  exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_lister_scroll.py', encoding='utf-8').read())
"""
q = op('/project1/vcon/panel/queue')
if q is None:
    print('queue lister not found')
    raise SystemExit()

print(f"=== queue lister ({q.path}) ===")
print()
# Scan every page for anything scroll-related
for pg in q.pages:
    for par in pg.pars:
        name = par.name
        if any(k in name.lower() for k in ('scroll', 'bar', 'hbar', 'vbar')):
            try:
                menus = list(par.menuNames or [])
            except Exception:
                menus = []
            try:
                val = par.eval()
            except Exception:
                val = '?'
            print(f"  page={pg.name:<12} {name}  = {val!r}  menu={menus}")
print()
# Also check customPars
try:
    for par in q.customPars:
        if 'scroll' in par.name.lower() or 'bar' in par.name.lower():
            print(f"  custom         {par.name} = {par.eval()!r}")
except Exception:
    pass