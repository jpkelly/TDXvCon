"""Probe 4: label widget — which par drives the DISPLAYED text?

Paste in the TD textport:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_label.py',
              encoding='utf-8').read())

Writes test strings to the candidate pars (Label, Text, Widgetlabel,
Value0) of the panel's output_l widget, one at a time, so we can SEE
which one changes the rendered text. Prints each par's current value
before and after. Restores nothing — the preview callback overwrites
the winner on the next settings change.
"""

v = op('/project1/vcon/panel')
target = None
for c in v.children:
    if c.name == 'output_l':
        target = c
        break
if target is None:
    print('[probe] output_l NOT FOUND in panel children:',
          [c.name for c in v.children])
else:
    print(f'[probe] output_l found: {target.path} ({len(target.customPages)} custom pages)')
    for pg in target.customPages:
        pars = ', '.join(p.name for p in pg.pars)
        print(f'  [{pg.name}] {pars}')
    # try each candidate
    for par_name in ('Label', 'Text', 'Widgetlabel', 'Value0'):
        try:
            par = getattr(target.par, par_name)
        except Exception:
            print(f'[probe] no par {par_name}')
            continue
        try:
            old = par.eval()
        except Exception:
            old = '(eval failed)'
        print(f'[probe] {par_name} current: {old!r}')
        try:
            par.val = f'<<{par_name}>>'
            print(f'[probe]   wrote test string to {par_name} — LOOK AT THE PANEL NOW')
        except Exception as exc:
            print(f'[probe]   write to {par_name} failed: {exc}')
    print('[probe] whichever string is visible in the panel names the right par')