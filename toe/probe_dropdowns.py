"""List every panel dropdown: op name, label, menu tokens, value.

Run in TD textport:
  exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_dropdowns.py', encoding='utf-8').read())
"""
p = op('/project1/vcon/panel')
print(f"{'op name':<16} {'y':>5}  {'Widgetlabel':<16} {'Value0':<14} Menunames")
print("-" * 100)
rows = []
for c in p.children:
    try:
        menus = c.par.Menunames.eval()
    except Exception:
        continue          # not a dropdown
    try:
        label = c.par.Widgetlabel.eval()
    except Exception:
        label = "?"
    try:
        val = c.par.Value0.eval()
    except Exception:
        val = "?"
    rows.append((c.par.y.eval(), c.name, label, val, menus))
for y, name, label, val, menus in sorted(rows, reverse=True):
    print(f"{name:<16} {y:>5}  {str(label):<16} {str(val):<14} {menus}")
