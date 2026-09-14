"""capture_run.py — one-liner runner for the panel capture.

Lives inside the vCon COMP as a file-linked DAT (panel_capture_run), so
re-capturing after hand-tuning is one exec:

    exec(op.vcon.op('panel_capture_run').text)

(the textport can read the DAT's text directly — no repo path needed).

It runs the FULL capture script (toe/capture_panel.py) in a namespace
where TD's globals are absent: the script is context-agnostic (it
resolves op-type constants via the td module — same find_type pattern
as the builders). Output goes to the textport plus
toe/panel_layout_captured.py, exactly as the textport route.

DO NOT import as a module — exec() it. (This file is exec()'d by the
DAT, and the DAT's text is exec()'d from the textport; TD's rule about
its builtins holds at each layer.)
"""

import os

_CAPTURE_SCRIPT = ('/Users/jp/Documents/GitHub/vCon/toe/'
                  'capture_panel.py')

with open(_CAPTURE_SCRIPT, encoding='utf-8') as _f:
    _src = _f.read()

# The capture script runs at exec() time (module-level code) — no
# callable to invoke, just run it in this namespace. print() goes to
# the textport from any TD context.
exec(compile(_src, _CAPTURE_SCRIPT, 'exec'))