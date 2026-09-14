"""Probe 14: definitive button-label diagnosis on the LIVE start_b.

Paste in the TD textport:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_button.py',
              encoding='utf-8').read())

The screenshot shows 'START | START' — title strip AND face both render.
This reads every label-related par on start_b with its EXACT live value,
mode, and menu list, then:
  1. blanks the title (Widgetlabel='') and re-reads
  2. tries every known display-off spelling on every display par
  3. measures which write changed what
So the final fix is written against observed behavior, not theory.
"""

w = op('/project1/vcon/panel/start_b')
if w is None:
    raise RuntimeError('start_b not found')

print('[probe] label-related pars on start_b (live):')
cands = []
for pg in w.customPages:
    for par in pg.pars:
        n = par.name
        if n.lower().startswith('label') or n.lower().startswith('widget'):
            try:
                cur = par.eval()
            except Exception:
                cur = '(eval failed)'
            style = getattr(par, 'style', '?')
            menus = list(getattr(par, 'menuNames', None) or [])
            print(f'  {n} = {cur!r}  style={style}  menus={menus}')
            if n in ('Labeldisplay', 'Labelwidth', 'Labeltop',
                     'Widgetlabel', 'Label'):
                cands.append((n, par, cur))

print()
print('[probe] WRITE TESTS (watch the button after each):')
for n, orig in cands:
    par = getattr(w.par, n, None)
    if par is None:
        continue
    style = getattr(par, 'style', '?')
    if style == 'Toggle':
        for v in ('off', 0, False):
            try:
                par.val = v
                print(f'  SET {n} = {v!r}  <-- look')
                break
            except Exception as exc:
                print(f'  {n}={v!r} failed: {exc}')
    elif style == 'Int':
        try:
            par.val = 0
            print(f'  SET {n} = 0  <-- look')
        except Exception as exc:
            print(f'  {n}=0 failed: {exc}')
    elif style in ('Str', 'Header'):
        try:
            par.val = ''
            print(f'  SET {n} = ""  <-- look')
        except Exception as exc:
            print(f'  {n}="" failed: {exc}')
print()
print('[probe] RESTORE (title was):', end=' ')
try:
    print(repr(w.par.Widgetlabel.eval()))
except Exception:
    print('(n/a)')