"""apply_panel_capture.py — bake JP's captured hand-tuning into the panel.

NEVER run alone: build_panel.py exec()s this AFTER build(), so the
capture (the canonical hand-tuned state) wins over builder defaults.

Order matters:
  1. geometry (panel-view x/y/w/h) per widget
  2. pars — OP-valued strings re-LINKED (object first, path fallback —
     the set_op_par pattern); the capture already skipped refs pointing
     INSIDE a widget (internal wiring stays untouched)
  3. expressions AND binds REBOUND after values (the status label's
     live Widgetlabel expr and any par bindings survive; baking only
     the eval'd value would freeze them)
  4. queue listerconfig DAT texts (hand-tuned column settings)
  5. ONE explicit lister Refresh pulse on the settled state (the
     established pattern — refresh-on-input-change throws on
     mid-write tables)
A pre-v3 dump contains TD reprs ('type:tableDAT path:...') that are not
valid Python — the compile guard catches it and says re-capture.
"""

DUMP = ('/Users/jp/Documents/GitHub/vCon/toe/'
        'panel_layout_captured.py')
PANEL_PATH = '/project1/vcon/panel'

try:
    with open(DUMP, encoding='utf-8') as f:
        _src = f.read()
    _ns = {}
    exec(compile(_src, DUMP, 'exec'), _ns)
    CAPTURED = _ns['CAPTURED_PANEL']
except Exception as _exc:
    print(f"[capture] !! cannot load {DUMP}")
    print(f"[capture]    {_exc}")
    print("[capture] A pre-v3 dump contains TD reprs that are not valid")
    print("[capture] Python — re-run capture_panel.py (v3) in the textport")
    CAPTURED = None


def _is_op(v):
    return (not isinstance(v, str)) and hasattr(v, 'path')


def _panel():
    return op(PANEL_PATH)


def _target(name):
    """The comp for a capture entry: the panel itself, or its child."""
    if name == 'panel':
        return _panel()
    p = _panel()
    return p.op(name) if p is not None else None


def _set_value(w, par, value):
    """Set one par; OP-ref strings re-link, everything else plain.

    The capture stored OP refs as path strings. A string that resolves
    to a live op AND whose current eval is an op → set object-first
    (path fallback, set_op_par pattern). Everything else is a plain
    value (a string like 'C:/' never resolves via op(), so plain
    string pars can never be mistaken for refs).
    """
    if isinstance(value, str) and value.startswith('/'):
        try:
            cur = par.eval()
        except Exception:
            cur = None
        ref = None
        try:
            ref = op(value)
        except Exception:
            ref = None
        if _is_op(cur) and ref is not None:
            for candidate in (ref, value):
                try:
                    setattr(w.par, par.name, candidate)
                    return True
                except Exception:
                    continue
            print(f"[capture] !! {w.name}.{par.name}: op relink failed")
            return False
    try:
        setattr(w.par, par.name, value)
        return True
    except Exception as exc:
        print(f"[capture] ( {w.name}.{par.name} = {value!r}: {exc} )")
        return False


def _apply_entry(name, entry):
    """Geometry, pars, expressions for one captured widget."""
    w = _target(name)
    if w is None:
        print(f"[capture] !! {name} not found in the built panel — skipped")
        return
    geom = entry.get('geometry') or {}
    for pname in ('x', 'y', 'w', 'h'):
        if pname in geom:
            try:
                w.par[pname].val = geom[pname]
            except Exception as exc:
                print(f"[capture] ( {name}.{pname}: {exc} )")
    missed = 0
    for pname, value in (entry.get('pars') or {}).items():
        try:
            par = w.par[pname]
        except Exception:
            par = None
        if par is None:
            # name absent on this build's widget — report, don't stall
            print(f"[capture] ( {name}: no par {pname} )")
            missed += 1
            continue
        if str(par.style) == 'Pulse':
            continue
        if not _set_value(w, par, value):
            missed += 1
    # expressions AND binds AFTER values: rebinding wins (live wiring
    # restored — the 'None' string was filtered at capture time)
    for pname, expr in (entry.get('expressions') or {}).items():
        try:
            w.par[pname].expr = expr
        except Exception as exc:
            print(f"[capture] ( {name}.{pname} expr: {exc} )")
    for pname, bindexpr in (entry.get('binds') or {}).items():
        try:
            w.par[pname].bindExpr = bindexpr
        except Exception as exc:
            print(f"[capture] ( {name}.{pname} bind: {exc} )")
    print(f"[capture] {name}: geometry + "
          f"{len(entry.get('pars') or {})} pars applied"
          + (f", {len(entry.get('expressions') or {})} exprs rebound"
             if entry.get('expressions') else '')
          + (f", {len(entry.get('binds') or {})} binds rebound"
             if entry.get('binds') else ''))


def _restore_listerconfig(entry):
    """Write the captured listerConfig DAT texts back."""
    texts = entry.get('listerconfig')
    if not texts:
        return
    q = _target('queue')
    if q is None:
        return
    cfg = q.op('listerConfig')
    if cfg is None:
        cfg = _panel().op('listerConfig')
    if cfg is None:
        print("[capture] !! listerConfig not found — column tuning skipped")
        return
    for dname, text in texts.items():
        d = cfg.op(dname)
        if d is None:
            print(f"[capture] ( listerConfig DAT {dname} missing )")
            continue
        try:
            d.text = text
        except Exception as exc:
            print(f"[capture] ( listerConfig {dname}: {exc} )")
    print(f"[capture] listerConfig: {len(texts)} DATs restored")


if CAPTURED:
    _panel_comp = _panel()
    if _panel_comp is None:
        print("[capture] !! panel missing — run build_panel.py fully")
    else:
        print("=" * 52)
        print(f"[capture] applying captured hand-tuning "
              f"({len(CAPTURED)} entries)")
        print("=" * 52)
        # widgets first, panel container LAST (its settings sit above
        # the children and can affect layout passes)
        for _name, _entry in CAPTURED.items():
            if _name == 'panel':
                continue
            if not isinstance(_entry, dict):
                continue
            _apply_entry(_name, _entry)
            if _name == 'queue':
                _restore_listerconfig(_entry)
        if 'panel' in CAPTURED and isinstance(CAPTURED['panel'], dict):
            _apply_entry('panel', CAPTURED['panel'])
        # one clean refresh on the settled state
        _q = _panel_comp.op('queue')
        if _q is not None:
            try:
                _q.par.Refresh.pulse()
                print("[capture] lister refresh pulsed")
            except Exception:
                pass
        print("=" * 52)
        print("[capture] hand-tuned state restored — capture is canonical")
        print("=" * 52)