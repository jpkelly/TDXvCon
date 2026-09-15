"""Probe the quality_s slider's inner structure to find where the
numeric field text renders — the child op that shows '0.0' / '0.862'.

Run in TD textport:
  exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_quality_slider.py', encoding='utf-8').read())
"""
p = op('/project1/vcon/panel').op('quality_s')
print(f"=== quality_s ({p.path}) ===")
print(f"  type: {type(p).__name__}")
print()

def dump(op_, depth=0):
    indent = "  " * depth
    name = op_.name
    otype = type(op_).__name__
    # Show any Widgetlabel / text-like pars
    extras = []
    try:
        for pg in op_.customPages:
            for par in pg.pars:
                if par.name in ('Widgetlabel', 'Stringfield0', 'Text',
                                'Numericfielddisplay', 'Numericfieldtype',
                                'Numericfieldformatting',
                                'Numericfieldcustom',
                                'Numericfielddecimalplaces',
                                'Sliderlabelnames', 'Sliderlabeldisplay',
                                'Valname0'):
                    extras.append(f"{par.name}={par.eval()!r}")
    except Exception:
        pass
    extra_str = f"  [{', '.join(extras)}]" if extras else ""
    print(f"{indent}- {name} [{otype}]{extra_str}")
    try:
        for c in op_.children:
            dump(c, depth + 1)
    except Exception:
        pass

dump(p)