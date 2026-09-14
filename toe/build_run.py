"""build_run.py — one-liner runner for the panel build.

Lives inside the vCon COMP as a file-linked DAT (panel_build_run), so
rebuilding the panel after a capture is one exec:

    exec(op.vcon.op('panel_build_run').text)

Runs the FULL build (toe/build_panel.py) in this namespace — the
build script is context-agnostic (op-type constants resolve via the
td module). The capture bake runs automatically at the end when
toe/panel_layout_captured.py exists (the capture is canonical).

DO NOT import as a module — exec() it.
"""

_BUILD_SCRIPT = '/Users/jp/Documents/GitHub/vCon/toe/build_panel.py'

with open(_BUILD_SCRIPT, encoding='utf-8') as _f:
    _src = _f.read()

exec(compile(_src, _BUILD_SCRIPT, 'exec'))