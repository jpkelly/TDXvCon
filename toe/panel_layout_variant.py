#: SCALE-OFF layout capture of the FPS/SCALE row (JP hand-tuned).
#: DELTAS vs the canonical capture (panel_layout_captured.py) —
#: any widget/key not listed keeps its canonical placement.
#: Baked into vcon_panel_callbacks._ROW_LAYOUTS['off'] (the runtime
#: switcher); ['on'] comes from the canonical capture. Re-capture
#: after any hand re-arrangement with SCALE OFF:
#:   exec(op.vcon.op('panel_capture_run').text)
CAPTURED_VARIANT = {
    'scaled_off': {
        'fps_t': {'w': 154},
        'fps_f': {'x': 162},
        'scaled_t': {'x': 250, 'w': 101},
    },
}
