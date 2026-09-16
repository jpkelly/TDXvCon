"""Find the lister's row height / content height so vscrollbar can be
toggled on real overflow instead of a guessed constant.

Run in TD textport:
  exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_lister_rows.py', encoding='utf-8').read())
"""
q = op('/project1/vcon/panel/queue')
print(f"=== lister {q.path} ===")
print(f"  panel h = {q.par.h.eval()}")

print()
print("--- children (looking for the rows container) ---")
for c in q.children:
    try:
        h = c.par.h.eval()
        y = c.par.y.eval()
        print(f"  {c.name:<20} {type(c).__name__:<16} y={y:<8} h={h}")
    except Exception:
        print(f"  {c.name:<20} {type(c).__name__:<16} (no geometry)")

print()
print("--- any par mentioning row/height/item on the lister ---")
for pg in q.pages:
    for par in pg.pars:
        n = par.name.lower()
        if 'row' in n or 'height' in n or 'item' in n:
            try:
                print(f"  page={pg.name:<12} {par.name:<22} = {par.eval()!r}")
            except Exception:
                pass

print()
print("--- lister extension: anything exposing row geometry ---")
for dname in ('ListerExt', 'listerExt'):
    d = q.op(dname)
    if d is not None:
        txt = d.text
        import re
        for m in re.finditer(r'def (\w*[Rr]ow\w*)\(', txt):
            print(f"  {dname}.{m.group(1)}()")
        break
