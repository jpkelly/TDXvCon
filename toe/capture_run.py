"""capture_run.py — one-liner runner for the panel capture.

Lives inside the vCon COMP as a file-linked DAT (panel_capture_run), so
re-capturing after hand-tuning is one exec:

    exec(op.vcon.op('panel_capture_run').text)

(the textport can read the DAT's text directly — no repo path needed).

It runs the FULL capture script in a namespace where TD's globals are
absent: the script is context-agnostic (it resolves op-type constants
via the td module — same find_type pattern as the builders).

TWO-LAYOUT ROUTING (JP, 2026-09-16): the FPS/SCALE row has a canonical
layout (SCALE ON) and a variant (SCALE OFF). The scaled_t toggle
routes the capture:
  ON  -> toe/capture_panel.py   (canonical, panel_layout_captured.py)
  OFF -> toe/capture_variant.py (variant, panel_layout_variant.py)
One saved one-liner captures whichever layout is on screen.

DO NOT import as a module — exec() it. (This file is exec()'d by the
DAT, and the DAT's text is exec()'d from the textport; TD's rule about
its builtins holds at each layer.)
"""

import os

_CANON = ('/Users/jp/Documents/GitHub/vCon/toe/'
          'capture_panel.py')
_VARIANT = ('/Users/jp/Documents/GitHub/vCon/toe/'
            'capture_variant.py')

# Route by the SCALE toggle (two-layout FPS/SCALE row): ON -> canonical
# capture, OFF -> variant capture. An unreadable toggle falls back to
# the canonical (the pre-two-layout behavior).
_script = _CANON
try:
    _st = op('/project1/vcon/panel/scaled_t')
    if _st is not None and not bool(_st.par.Value0.eval()):
        _script = _VARIANT
        print("[capture] SCALE is OFF -> capturing the SCALED-OFF "
              "variant layout")
except Exception as _exc:
    print(f"[capture] scaled_t state unreadable ({_exc}) — assuming "
          "canonical")

with open(_script, encoding='utf-8') as _f:
    _src = _f.read()

# The capture script runs at exec() time (module-level code) — no
# callable to invoke, just run it in this namespace. print() goes to
# the textport from any TD context.
exec(compile(_src, _script, 'exec'))