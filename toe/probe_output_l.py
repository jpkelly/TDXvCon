"""probe_output_l.py — ground truth for the output_l label widget.

Run in the TD textport (NOT imported):

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_output_l.py',
              encoding='utf-8').read())

Answers, with EVIDENCE instead of guesses (this par has been guessed
wrong twice — Widgetlabel vs Label):
  1. every candidate text par: name, style, current value, expression
  2. WHICH par actually changes the rendered text — the probe writes a
     marker to each candidate in turn and reports what took
  3. the widget's inner structure (what the 'Label' OP-ref points at)
  4. whether output_l even resolves (the flat-widget lookup)
"""

MARKER = "PROBE-OUTPUT-L"

p = op('/project1/vcon/panel')
if p is None:
    raise RuntimeError('panel not found')

w = p.op('output_l')
print('=' * 60)
print('output_l widget:', w.path if w is not None else 'NOT FOUND')
if w is None:
    print('children of panel:')
    for c in p.children:
        print('   ', c.name, c.type)
    raise SystemExit()

print('type:', w.type)
print()
print('--- candidate TEXT pars ---')
candidates = []
for name in ('Widgetlabel', 'Label', 'Labeltext', 'Text', 'Value0',
             'Stringfield0'):
    par = getattr(w.par, name, None)
    if par is None:
        print(f'  {name:16} — absent')
        continue
    try:
        style = str(par.style)
    except Exception as exc:
        style = f'(style unreadable: {exc})'
    try:
        val = par.eval()
    except Exception as exc:
        val = f'(eval failed: {exc})'
    try:
        expr = par.expr or ''
    except Exception:
        expr = ''
    print(f'  {name:16} style={style:12} value={val!r}'
          + (f' expr={expr!r}' if expr else ''))
    if style in ('Str', 'String', 'Menu') or 'label' in name.lower():
        candidates.append(name)

print()
print('--- inner structure (what an OP-ref par points at) ---')
for ch in w.children:
    print(f'  child: {ch.name} ({ch.type})')
    for name in ('Widgetlabel', 'Label', 'Labeltext', 'Text'):
        par = getattr(ch.par, name, None)
        if par is None:
            continue
        try:
            print(f'     inner.{name} style={par.style} '
                  f'value={par.eval()!r}')
        except Exception as exc:
            print(f'     inner.{name}: {exc}')

print()
print('--- WHO RENDERS? writing the marker to each candidate ---')
for name in candidates:
    par = getattr(w.par, name, None)
    if par is None:
        continue
    try:
        par.val = f'{MARKER}-{name}'
    except Exception as exc:
        print(f'  {name}: WRITE FAILED ({type(exc).__name__}: {exc})')
        continue
    try:
        readback = par.eval()
    except Exception as exc:
        readback = f'(eval failed: {exc})'
    ok = (readback == f'{MARKER}-{name}')
    print(f'  {name}: write {"TOOK" if ok else "DID NOT TAKE"} '
          f'(readback={readback!r})')
    print(f'     >> LOOK AT THE PANEL NOW: does output_l show '
          f'{MARKER}-{name}?')

print()
print('=' * 60)
print('the par whose marker APPEARS in the panel is the renderable one')
print('(tell me which, and it goes in as the verified fact)')
print('=' * 60)
