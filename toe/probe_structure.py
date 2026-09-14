"""Probe 6: definitively map the slider widget's internal structure.

Paste in the TD textport:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_structure.py',
              encoding='utf-8').read())

Dumps the COMPLETE tree of prog_s — every node, its type, its custom
pages, and every custom par on each — so we know exactly which node
owns 'Numericfielddisplay' and where the builder must write. Also does
the same for output_l (to confirm the label structure we fixed).

Read-only: prints, changes nothing.
"""

def dump_tree(op_, depth=0, max_depth=3):
    pad = '  ' * depth
    try:
        ctype = type(op_).__name__
    except Exception:
        ctype = '?'
    pages = []
    try:
        pages = [pg.name for pg in op_.customPages]
    except Exception:
        pass
    print(f"{'  '*depth}- {op_.name} [{ctype}] pages={pages}")
    if depth >= max_depth:
        return
    try:
        for c in op_.children:
            dump_tree(c, depth + 1, max_depth)
    except Exception:
        pass


print('=== panel children (full tree, prog_s + output_l deep) ===')
p = op('/project1/vcon/panel')
for c in p.children:
    if c.name in ('prog_s', 'output_l', 'status_l', 'quality_s'):
        dump_tree(c, 0, 3)
    else:
        print(f"- {c.name} [{type(c).__name__}]")

print()
print('=== prog_s: every node\'s Numeric* and Slider* pars ===')


def find_pars(op_, path=''):
    try:
        for pg in op_.customPages:
            for par in pg.pars:
                if par.name.startswith('Numericfielddisplay') or \
                   par.name in ('Sliderlabelnames', 'Sliderlabeldisplay'):
                    print(f"  {op_.path}  {par.name} = {par.eval()!r}")
    except Exception as exc:
        print(f"  ({op_.path}: {exc})")
    try:
        for c in op_.children:
            find_pars(c, depth)
    except Exception:
        pass


find_pars(p.op('prog_s'))
print()
print('=== quality_s for comparison (its Numericfielddisplay WORKS) ===')
find_pars(p.op('quality_s'))