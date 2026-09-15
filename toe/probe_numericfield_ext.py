"""Find how the widget's numeric field applies 'customfstring'.

par.text is BIND-driven, so writes are ignored. The supported hook is
Numericfieldformatting='customfstring' + Numericfieldcustom. This
prints the widget's NumericFieldExt source around the formatting code
so we learn the exact variable name the f-string is evaluated with.

Run in TD textport:
  exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_numericfield_ext.py', encoding='utf-8').read())
"""
w = op('/project1/vcon/panel').op('quality_s')
nv = w.op('numericValue0')

for dat_name in ('NumericFieldExt', 'SubWidgetExt', 'text1_callbacks'):
    d = nv.op(dat_name)
    if d is None:
        print(f"--- {dat_name}: NOT FOUND ---")
        continue
    src = d.text
    print(f"=== {dat_name} ({len(src)} chars) ===")
    lines = src.splitlines()
    hits = [i for i, ln in enumerate(lines)
            if 'fstring' in ln.lower() or 'customfmt' in ln.lower()
            or 'formatting' in ln.lower() or 'Numericfieldcustom' in ln]
    if not hits:
        print("  (no formatting code found)")
        print()
        continue
    shown = set()
    for i in hits:
        lo, hi = max(0, i - 6), min(len(lines), i + 10)
        for j in range(lo, hi):
            if j in shown:
                continue
            shown.add(j)
            print(f"  {j+1:4}| {lines[j]}")
        print("  " + "-" * 60)
    print()
