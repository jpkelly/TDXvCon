"""Two questions in one probe:

1. WHY the header colour will not stick — yellow values in TD mean the
   parameter is in EXPRESSION mode, so a typed constant is recomputed
   away. This prints the mode + expression + bind for the header's
   colour pars, and where they resolve from.
2. WHAT numbers a manual dynamic scrollbar needs — row height, list
   height, row count — so we can toggle vscrollbar ourselves.

Run in TD textport:
  exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_lister_header.py', encoding='utf-8').read())
"""
q = op('/project1/vcon/panel/queue')
if q is None:
    print('queue lister not found')
    raise SystemExit()

cfg = None
try:
    cfg = q.par.Configcomp.eval()
except Exception:
    pass
if cfg is None:
    cfg = q.op('listerConfig') or op('/project1/vcon/panel/listerConfig')

print("=" * 66)
print("1. HEADER COLOUR — what actually drives it")
print("=" * 66)
hdr = cfg.op('header') if cfg is not None else None
print(f"  header op: {hdr.path if hdr else 'NOT FOUND'}")
if hdr is not None:
    for pg in hdr.pages:
        for par in pg.pars:
            if 'bgcolor' in par.name.lower() or 'bgalpha' in par.name.lower():
                try:
                    mode = par.mode.name
                except Exception:
                    mode = '?'
                try:
                    val = par.eval()
                except Exception:
                    val = '?'
                print(f"    {par.name:<14} mode={mode:<10} val={val!r}")
                if mode != 'CONSTANT':
                    print(f"      expr      = {par.expr!r}")
                    try:
                        print(f"      bindExpr  = {par.bindExpr!r}")
                        print(f"      bindMaster= {par.bindMaster}")
                    except Exception:
                        pass

print()
print("  --- lister colour pars that an expression might read from ---")
for pg in q.pages:
    for par in pg.pars:
        n = par.name.lower()
        if 'color' in n and ('header' in n or 'head' in n):
            try:
                print(f"    {par.name:<24} = {par.eval()!r}  "
                      f"mode={par.mode.name}")
            except Exception:
                pass

print()
print("=" * 66)
print("2. DYNAMIC SCROLLBAR — numbers needed to drive vscrollbar")
print("=" * 66)
for pg in q.pages:
    for par in pg.pars:
        n = par.name.lower()
        if any(k in n for k in ('rowheight', 'headerheight', 'rowspacing',
                                'vscrollbar', 'autoheight')):
            try:
                menus = list(par.menuNames or [])
            except Exception:
                menus = []
            print(f"    page={pg.name:<10} {par.name:<18} = {par.eval()!r}"
                  + (f"  menu={menus}" if menus else ""))
print(f"    lister panel height (par.h) = {q.par.h.eval()}")
d = op('/project1/vcon/queue_display')
print(f"    queue_display rows          = {d.numRows if d else '?'} "
      f"(includes header row)")
