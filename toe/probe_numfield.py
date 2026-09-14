"""Probe 5: why does the progress slider's number box still show?

Paste in the TD textport:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_numfield.py',
              encoding='utf-8').read())

Reads the live state of every Numeric/Slider display par on prog_s,
then flips the most likely candidates to 0 one at a time — watch the
panel after each step and note which one makes the '0.000' box vanish.
"""

p = op('/project1/vcon/panel')
w = p.op('prog_s')
if w is None:
    raise RuntimeError('prog_s not found')

# TOP-LEVEL only (JP rule) — the widget COMP is the panel child
target = w
print(f'[probe] target: {target.path}')

# 1. current state of every candidate
for name in ('Numericfielddisplay', 'Numericfieldwidth',
             'Numericfieldhorizontalmode', 'Numericfieldverticalmode',
             'Sliderlabeldisplay', 'Sliderlabelnames'):
    par = getattr(target.par, name, None)
    if par is None:
        print(f'[probe] {name}: (no such par)')
    else:
        try:
            print(f'[probe] {name} = {par.eval()!r}  (valid={par.valid})')
        except Exception as exc:
            print(f'[probe] {name} = (eval failed: {exc})')

# 2. flip candidates one at a time — watch the panel after each print
for name, val in [('Numericfielddisplay', 'off'),
                  ('Numericfieldwidth', 0),
                  ('Sliderlabeldisplay', 'off')]:
    par = getattr(target.par, name, None)
    if par is None:
        continue
    try:
        par.val = val
        print(f'[probe] set {name}={val} — did the number box disappear?')
    except Exception as exc:
        print(f'[probe] {name} write failed: {exc}')
print('[probe] done — report which step (if any) hid the box')