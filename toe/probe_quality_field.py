"""Why the quality slider's field text won't change.

Checks (a) whether numericValue0/text's text par is bind/expression
driven, and (b) whether Numericfieldformatting has a 'custom' mode
that Numericfieldcustom feeds — the widget's own hook for field text.

Run in TD textport:
  exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_quality_field.py', encoding='utf-8').read())
"""
w = op('/project1/vcon/panel').op('quality_s')
print(f"=== quality_s = {w.path} ===")

print()
print("--- Numericfield* pars on the widget (modes + menus) ---")
for pg in w.customPages:
    for par in pg.pars:
        if par.name.startswith('Numericfield'):
            try:
                menu = list(par.menuNames) if par.isMenu else None
            except Exception:
                menu = None
            print(f"  {par.name:32} = {par.eval()!r}"
                  f"  mode={par.mode.name}"
                  + (f"  menu={menu}" if menu else ""))

print()
print("--- numericValue0/text (the textCOMP that renders the number) ---")
nv = w.op('numericValue0')
txt = nv.op('text') if nv is not None else None
if txt is None:
    print("  NOT FOUND")
else:
    print(f"  path: {txt.path}  type: {type(txt).__name__}")
    for pname in ('text', 'Text'):
        try:
            par = getattr(txt.par, pname)
        except Exception:
            continue
        print(f"  par.{pname}: mode={par.mode.name}  val={par.eval()!r}")
        print(f"      expr={par.expr!r}")
        try:
            print(f"      bindExpr={par.bindExpr!r}")
            print(f"      bindMaster={par.bindMaster}")
        except Exception:
            pass

print()
print("--- numericValue0 own Numericfield* pars ---")
if nv is not None:
    for pg in nv.customPages:
        for par in pg.pars:
            if par.name.startswith('Numericfield'):
                try:
                    menu = list(par.menuNames) if par.isMenu else None
                except Exception:
                    menu = None
                print(f"  {par.name:32} = {par.eval()!r}"
                      f"  mode={par.mode.name}"
                      + (f"  menu={menu}" if menu else ""))

print()
print("--- LIVE WRITE TEST: set the textCOMP text to 'PROBE' ---")
if txt is not None:
    try:
        txt.par.text.val = 'PROBE'
        print(f"  after write: {txt.par.text.eval()!r}")
        print("  -> look at the panel NOW; does the slider field say PROBE?")
    except Exception as exc:
        print(f"  write FAILED: {exc}")
