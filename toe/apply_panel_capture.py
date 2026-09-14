"""apply_panel_capture.py — bake JP's captured hand-tuning into the panel.

NEVER run alone: build_panel.py exec()s this AFTER build(), so the
capture (the canonical hand-tuned state) wins over builder defaults.

Order matters:
  1. geometry (panel-view x/y/w/h) per widget
  2. pars — OP-valued strings re-LINKED (object first, path fallback —
     the set_op_par pattern), with a RENAME fallback: a captured path
     that no longer resolves (the live toe's panel_dnd11 vs a fresh
     build's panel_dnd) retries with trailing digits stripped; the
     capture already skipped refs pointing INSIDE a widget (internal
     wiring stays untouched). A par the capture holds as a CONSTANT
     gets its live expression CLEARED first — stock exprs (e.g.
     buttonMomentary's chr(0xF070E) icon on Buttonofflabel) would
     otherwise re-evaluate and swallow the write. Widget metadata pars
     (Version/Toxsavebuild/Help) are skipped.
  3. expressions AND binds REBOUND after values (the status label's
     live Widgetlabel expr and any par bindings survive; baking only
     the eval'd value would freeze them). BROKEN expressions are
     compile-guarded and skipped with a warning — the first capture
     carried a hand typo ('2o') that would otherwise bake an error par.
  4. queue listerconfig DAT texts (hand-tuned column settings)
  5. res-field visibility re-run once (scale/fit/W-H show state can
     arrive via captured Value0 writes without firing widget hooks),
     then ONE explicit lister Refresh pulse on the settled state (the
     established pattern — refresh-on-input-change throws on
     mid-write tables)
A pre-v3 dump contains TD reprs ('type:tableDAT path:...') that are not
valid Python — the compile guard catches it and says re-capture.
"""

DUMP = ('/Users/jp/Documents/GitHub/vCon/toe/'
        'panel_layout_captured.py')
PANEL_PATH = '/project1/vcon/panel'

#: widget metadata pars — not bakeable state, silently skipped
_META_SKIP = {'Version', 'Toxsavebuild', 'Help'}

#: BUILDER-OWNED pars — the bake never applies these from a capture.
#: Menus are GENERATED (codec registry, live fit-TOP mirror); script
#: pars are WIRED by the builder. A stale capture re-applying them
#: would un-wire future features — exactly the regression this rule
#: prevents (the first capture held the old SCALE factor menu + old
#: hook strings, which would have reverted the fit-TOP wiring).
#: The capture owns LOOK + LAYOUT + STATE (Value0 selections);
#: the builder owns WIRING + MENUS.
_BUILDER_OWNED = {'Menunames', 'Menulabels', 'Onvaluechangescript0',
                  'Offtoonscript0', 'Ontooffscript0', 'Valueparexec'}

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

    The capture stored OP refs as path strings. A path that doesn't
    resolve gets ONE fallback — trailing digits stripped (fresh-build
    renames: the live toe's panel_dnd11 becomes plain panel_dnd) —
    and if that also fails the par is LEFT AS BUILT rather than
    written broken. A string that never resolves via op() (like a
    destination path 'C:/') never enters the ref branch, so plain
    string pars can't be mistaken for refs.
    """
    if isinstance(value, str) and value.startswith('/'):
        try:
            cur = par.eval()
        except Exception:
            cur = None
        if _is_op(cur):
            # fresh-build RENAME fallback: the live toe's panel_dnd11 vs
            # a fresh build's panel_dnd — retry with trailing digits
            # stripped before giving up
            ref = None
            for cand in (value, value.rstrip('0123456789')):
                try:
                    ref = op(cand)
                except Exception:
                    ref = None
                if ref is not None:
                    break
            if ref is None:
                print(f"[capture] !! {w.name}.{par.name}: no live op "
                      f"for {value!r} — left as built")
                return False
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
    # NODE LAYOUT (v4): where the COMP sits in the network editor —
    # JP's hand-arranged node arrangement persists across rebuilds
    nl = entry.get('nodelayout')
    if nl and len(nl) == 2:
        try:
            w.nodeX, w.nodeY = nl
        except Exception as exc:
            print(f"[capture] ( {name} nodelayout: {exc} )")
    missed = 0
    exprs = entry.get('expressions') or {}
    binds = entry.get('binds') or {}
    for pname, value in (entry.get('pars') or {}).items():
        if pname in _META_SKIP:
            continue          # widget metadata — not bakeable state
        if pname in _BUILDER_OWNED:
            continue          # builder-owned wiring/menus — never from capture
        try:
            par = w.par[pname]
        except Exception:
            par = None
        if par is None:
            # name absent on this build's widget — report, don't stall
            print(f"[capture] ( {name}: no par {pname} )")
            missed += 1
            continue
        try:
            if str(par.style) == 'Pulse':
                continue
        except Exception:
            pass
        # CONSTANT over expression: a live expression re-evaluates and
        # swallows the write (stock buttonMomentary drives Buttonofflabel
        # with a chr(0xF070E) icon expr — JP's captured text must replace
        # it). Clear expression mode first; captured exprs are re-set
        # right after, so the captured state always wins.
        if pname not in exprs:
            try:
                if par.expr:
                    par.expr = ''
            except Exception:
                pass
        if pname not in binds:
            try:
                if par.bindExpr:
                    par.bindExpr = ''
            except Exception:
                pass
        if not _set_value(w, par, value):
            missed += 1
    # expressions AND binds AFTER values: rebinding wins (live wiring
    # restored — the 'None' string was filtered at capture time).
    # BROKEN expressions are compile-guarded: the first capture carried
    # a hand typo ('2o' on resh_f.Labelwidth) that would otherwise bake
    # an error par into every rebuild.
    for pname, expr in exprs.items():
        try:
            compile(expr, f'{name}.{pname}', 'eval')
        except Exception as exc:
            print(f"[capture] !! {name}.{pname}: broken expression "
                  f"{expr!r} skipped ({exc})")
            continue
        try:
            w.par[pname].expr = expr
        except Exception as exc:
            print(f"[capture] ( {name}.{pname} expr: {exc} )")
    for pname, bindexpr in binds.items():
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
        _removed = CAPTURED.get('removed') or []
        _added = [k for k, v in CAPTURED.items()
                  if isinstance(v, dict) and v.get('widgettox')]
        print(f"[capture] applying captured hand-tuning "
              f"({len(CAPTURED)} entries"
              + (f", {len(_removed)} removed" if _removed else '')
              + (f", {len(_added)} added" if _added else '') + ")")
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
        # res-field visibility: captured Value0 writes (scaled=on,
        # scale=custom) may land without firing the widget hooks — re-run
        # the visibility logic once so SCALE/FIT/W/H match the state
        try:
            op.vcon.op('panel_callbacks').module._update_res_fields()
            print("[capture] res-field visibility refreshed")
        except Exception:
            pass
        # VCON-LEVEL NODE LAYOUT: also restored by build_network.py at
        # its save step, but the PANEL build doesn't run that — apply
        # here too so either runner honors JP's vcon arrangement
        _vlay = CAPTURED.get('vconnodelayout')
        if _vlay:
            _applied = 0
            for _name, (_nx, _ny) in _vlay:
                _op_ = _panel_comp.parent().op(_name)
                if _op_ is not None:
                    try:
                        _op_.nodeX = _nx
                        _op_.nodeY = _ny
                        _applied += 1
                    except Exception:
                        pass
            print(f"[capture] vcon node layout applied to "
                  f"{_applied}/{len(_vlay)} ops")
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