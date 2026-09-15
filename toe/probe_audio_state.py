"""Live state of the audio widgets, exactly as _run_next() reads them.

Run in TD textport:
  exec(open('/Users/jp/Documents/GitHub/vCon/toe/probe_audio_state.py', encoding='utf-8').read())
"""
p = op('/project1/vcon/panel')
cb = op.vcon.op('panel_callbacks').module

print("=== live widget values ===")
for name in ("audio_dd", "audio_sep_t", "audio_sep_dd"):
    w = p.op(name)
    if w is None:
        print(f"  {name:<14} WIDGET NOT FOUND")
        continue
    try:
        val = w.par.Value0.eval()
    except Exception as exc:
        val = f"(eval failed: {exc})"
    try:
        disp = w.par.display.eval()
    except Exception:
        disp = "?"
    try:
        hook = w.par.Onvaluechangescript0.eval()
    except Exception:
        hook = "?"
    print(f"  {name:<14} Value0={val!r}  display={disp}")
    print(f"  {'':<14} hook={hook!r}")

print()
print("=== what a job submitted RIGHT NOW would send ===")
sep_on = bool(cb._val("audio_sep_t"))
sep_fmt = (cb._val("audio_sep_dd") or "wav16") if sep_on else None
print(f"  audio     = {cb._audio_value()!r}")
print(f"  audio_sep = {sep_fmt!r}   (None means extraction is SKIPPED)")

print()
print("=== persistence ===")
print(f"  _PERSIST_WIDGETS contains audio_dd     : "
      f"{'audio_dd' in cb._PERSIST_WIDGETS}")
print(f"  _PERSIST_WIDGETS contains audio_sep_t  : "
      f"{'audio_sep_t' in cb._PERSIST_WIDGETS}")
print(f"  _PERSIST_WIDGETS contains audio_sep_dd : "
      f"{'audio_sep_dd' in cb._PERSIST_WIDGETS}")

print()
print("=== ffmpeg ===")
print(f"  binary: {cb._ffmpeg_binary()}")
