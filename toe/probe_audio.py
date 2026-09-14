"""probe_audio.py — diagnose the audio chain.

Run in the TD textport:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_audio.py',
              encoding='utf-8').read())
"""

vcon = op('/project1/vcon')
if vcon is None:
    print('vcon not found')
    raise SystemExit()

moviein = vcon.op('moviein')
movieout = vcon.op('movieout')
audio = vcon.op('audio')

print('=' * 60)
print('AUDIO CHAIN DIAGNOSTICS')
print('=' * 60)

print()
print('--- Movie File In TOP ---')
print(f'  file: {moviein.par.file.eval()!r}')
try:
    print(f'  numImages: {moviein.numImages}')
except Exception:
    pass

print()
print('--- Audio Movie CHOP ---')
if audio is None:
    print('  !! audio CHOP NOT FOUND — rebuild network')
else:
    print(f'  path: {audio.path}')
    try:
        mfitop = audio.par.moviefileintop.eval()
        print(f'  moviefileintop: {mfitop!r}')
    except Exception as exc:
        print(f'  moviefileintop: {exc}')
    try:
        print(f'  play: {audio.par.play.eval()}')
    except Exception:
        pass
    try:
        print(f'  prereadlength: {audio.par.prereadlength.eval()} '
              f'{audio.par.prereadlengthunit.eval()}')
    except Exception:
        pass
    try:
        print(f'  timeslice: {audio.par.timeslice.eval()}')
    except Exception:
        pass
    try:
        print(f'  numChannels: {audio.numChannels}')
    except Exception as exc:
        print(f'  numChannels: {exc}')
    try:
        print(f'  numSamples: {audio.numSamples}')
    except Exception as exc:
        print(f'  numSamples: {exc}')
    try:
        print(f'  sampleRate: {audio.sampleRate}')
    except Exception as exc:
        print(f'  sampleRate: {exc}')
    try:
        ch = audio.chanNames
        print(f'  chanNames: {ch}')
    except Exception:
        pass

print()
print('--- Movie File Out TOP audio ---')
if movieout is None:
    print('  !! movieout NOT FOUND')
else:
    try:
        ac = movieout.par.audiochop.eval()
        print(f'  audiochop: {ac!r}')
    except Exception as exc:
        print(f'  audiochop: {exc}')
    try:
        ab = movieout.par.audiobitrate
        print(f'  audiobitrate: {ab.eval()!r}')
        print(f'  audiobitrate menuNames: {list(ab.menuNames or [])}')
        print(f'  audiobitrate menuLabels: {list(ab.menuLabels or [])}')
    except Exception as exc:
        print(f'  audiobitrate: {exc}')
    try:
        print(f'  record: {movieout.par.record.eval()}')
    except Exception:
        pass
    try:
        print(f'  pause: {movieout.par.pause.eval()}')
    except Exception:
        pass

print()
print('=' * 60)