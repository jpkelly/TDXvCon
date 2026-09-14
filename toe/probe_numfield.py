"""Probe 5 final: complete dump of every display-ish par on the slider.

Paste in the TD textport:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_numfield.py',
              encoding='utf-8').read())

Prints EVERY custom par on prog_s whose name mentions display/field/
width/mode, with: live value, TD par style, and the full menu list.
The output names the controlling par and its exact off-value — no
guessing. Then tries the two strongest candidates stepwise (watch the
panel; original values printed for restore).
"""

w = op('/project1/vcon/panel/prog_s')
if w is None:
    raise RuntimeError('prog_s not found — build the panel first')

print('[probe] EVERY display/field-ish par on prog_s (top level):')
saved = []
for pg in w.customPages:
    for par in pg.pars:
        n = par.name
        ln = n.lower()
        if any(k in ln for k in ('display', 'field', 'view', 'readout')):
            try:
                cur = par.eval()
            except Exception:
                cur = '(eval failed)'
            menus = list(getattr(par, 'menuNames', None) or [])
            style = getattr(par, 'style', '?')
            print(f'  {n} = {cur!r}  style={style}  menus={menus}')
            saved.append((n, cur))

print()
print('[probe] stepwise hide attempts (WATCH THE PANEL):')
# strongest candidates, with type-correct values derived from the dump
for n, _ in saved:
    if n.lower().endswith('display') or 'fielddisplay' in n.lower():
        par = getattr(w.par, n, None)
        if par is None:
            continue
        menus = list(getattr(par, 'menuNames', None) or [])
        if menus:
            # pick the token that means hidden: 'off'/'no'/'none' if present
            off = next((m for m in menus
                        if m.lower() in ('off', 'no', 'none', 'hidden',
                                         'false')), menus[0])
        else:
            off = 0
        try:
            par.val = off
            print(f'  SET {n} = {off!r}   <-- LOOK NOW')
        except Exception as exc:
            print(f'  {n}={off!r} failed: {exc}')

print()
print('[probe] ORIGINAL VALUES (to restore if a step hid too much):')
for n, v in saved:
    print(f'  {n} was {v!r}')
print('[probe] Report which SET line hid the 0.000 box (if any).')
