"""probe_mvo_audio.py — dump MvO's audio-related pars.

Run in the TD textport:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_mvo_audio.py',
              encoding='utf-8').read())
"""

mvo = op('/project1/vcon/movieout')
if mvo is None:
    print('movieout not found')
    raise SystemExit()

print('=' * 60)
print('MvO AUDIO PARS')
print('=' * 60)
for pg in mvo.pages:
    for par in pg.pars:
        name = par.name.lower()
        if 'audio' in name or 'acodec' in name or 'audiostream' in name:
            try:
                val = par.eval()
            except Exception:
                val = '(eval failed)'
            try:
                menus = list(par.menuNames or [])
            except Exception:
                menus = []
            try:
                labels = list(par.menuLabels or [])
            except Exception:
                labels = []
            print(f'\n  {par.name} (style={par.style})')
            print(f'    value: {val!r}')
            if menus:
                print(f'    menuNames: {menus}')
            if labels:
                print(f'    menuLabels: {labels}')

print()
print('=' * 60)
print('ALL MvO pars with "codec" or "audio" in the name:')
for pg in mvo.pages:
    for par in pg.pars:
        if 'codec' in par.name.lower() or 'audio' in par.name.lower():
            print(f'  {par.name} = {par.eval()!r}  (page={pg.name})')
print('=' * 60)