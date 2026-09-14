"""capture_panel.py v3 — full-fidelity snapshot of your hand-tuned panel.

Run in the TD textport AFTER adjusting the panel by hand:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/capture_panel.py',
              encoding='utf-8').read())

Captures the PANEL CONTAINER ITSELF (a 'panel' entry: its Layout/Look/
drop settings, diffed against a fresh containerCOMP) plus EVERY widget
— all 20, including add_b / resw_f / resh_f and the two progress-bar
containers that v2 silently skipped — diffing custom AND builtin pars
against a freshly loaded copy of each widget's tox.

Fidelity details:
  - geometry (panel-view x/y/w/h) per widget, in the 'geometry' section
  - OP-valued pars become PATH STRINGS (v2 wrote TD reprs like
    'type:tableDAT path:...' which are not valid Python); refs pointing
    INSIDE a widget are skipped (internal wiring — baking them would
    reach into the widget's internals), refs to outside ops
    (queue_display, panel_dnd, ...) are kept as paths
  - EXPRESSIONS are recorded separately ('expressions') — baking the
    eval'd values alone would freeze live bindings like the status
    label's Widgetlabel expr
  - pulse pars are skipped (they are actions, not state)
  - the queue entry also carries 'listerconfig': {DAT name: text} —
    the lister's config COMP holds hand-tuned column settings; it is
    found inside the lister or flattened at panel root (both seen
    in the live panel)

Output: printed AND written to toe/panel_layout_captured.py. Say
"captured" and it gets baked into build_panel.py as canonical state.
"""

import os

_TOX_DIR = ("/Applications/TouchDesigner.app/Contents/Resources/tfs/"
            "Samples/Palette/UI/Basic Widgets")
_UI_TOX_DIR = ("/Applications/TouchDesigner.app/Contents/Resources/tfs/"
               "Samples/Palette/UI")

DUMP_PATH = ('/Users/jp/Documents/GitHub/vCon/toe/'
             'panel_layout_captured.py')

p = op('/project1/vcon/panel')
if p is None:
    raise RuntimeError('panel not found — build it first')

#: panel widget name -> tox it came from (mirror of build_panel _WIDGETS)
_TOX_OF = {
    "source": "fieldFileBrowser", "destination": "fieldFolderBrowser",
    "codec_dd": "dropDownMenu", "subtype_dd": "dropDownMenu",
    "format_dd": "dropDownMenu", "quality_s": "sliderHorz",
    "fps_f": "fieldString", "scaled_t": "buttonToggle",
    "scale_dd": "dropDownMenu", "fit_dd": "dropDownMenu",
    "start_b": "buttonMomentary", "pause_b": "buttonMomentary",
    "stop_b": "buttonMomentary", "add_b": "buttonMomentary",
    "resw_f": "fieldString", "resh_f": "fieldString",
    "output_l": "label", "prog_s": "sliderHorz",
    "status_l": "label", "queue": "lister",
}

#: builder-made bare containers (no tox — baseline is a fresh
#: containerCOMP; all their pars are builtin anyway)
_BARE_CONTAINERS = {"prog_track", "prog_fill"}

#: builtin layout pars excluded from the pars diff — geometry lives in
#: the 'geometry' section, which is authoritative
_GEOM_PARS = {"x", "y", "w", "h"}


def _tox_path(name):
    if name == "lister":
        return os.path.join(_UI_TOX_DIR, "lister.tox")
    return os.path.join(_TOX_DIR, f"{name}.tox")


def _safe_geom(c):
    try:
        return (c.par.y.eval(), c.par.x.eval())
    except Exception:
        return (float('inf'), float('inf'))


_SKIP = object()          # sentinel: omit this par from the dump


def _is_op(v):
    """A TD OP value (has .path/.name; strings/numbers don't)."""
    return (not isinstance(v, str)) and hasattr(v, "path")


def _snap_par(comp, par):
    """Dump-safe value for one par.

    OP values become PATH STRINGS (v2's TD reprs — 'type:tableDAT
    path:...' — were not valid Python). OPs pointing INSIDE the comp
    are internal widget wiring: skip them. Outside refs (queue_display,
    panel_dnd, listerConfig) survive as paths the bake can re-link.
    """
    try:
        v = par.eval()
    except Exception:
        return _SKIP
    if _is_op(v):
        return _SKIP if v.path.startswith(comp.path + "/") else v.path
    return v


def _snapshots(comp):
    """(pars, exprs) of every par — custom AND builtin.

    Pulse pars are actions, not state: skipped. Geometry pars are
    skipped (captured separately). Expressions are recorded apart
    from values so the bake can REBIND live wiring (e.g. the status
    label's Widgetlabel expr) instead of freezing the eval'd snapshot.
    """
    vals, exprs = {}, {}
    allpars = []
    try:
        allpars.extend(comp.pars)
    except Exception:
        pass
    try:
        # explicit union — op.pars should already include customs, but
        # don't bet the capture on it
        allpars.extend(comp.customPars)
    except Exception:
        pass
    for par in allpars:
        try:
            if str(par.style) == "Pulse":
                continue
            is_geom = (not par.isCustom) and par.name in _GEOM_PARS
        except Exception:
            continue
        v = _snap_par(comp, par)
        if v is not _SKIP and not is_geom:
            vals[par.name] = v
        try:
            e = par.expr or ""
        except Exception:
            e = ""
        if e:
            exprs[par.name] = e
    return vals, exprs


def _diff(mine, stock):
    """Keep everything that differs from the stock baseline."""
    if stock:
        return {k: v for k, v in mine.items()
                if k not in stock or stock[k] != v}
    return dict(mine)


def _builtin_geom(comp):
    """Layout pars (x/y/w/h) — builtin, not custom, but part of tuning."""
    out = {}
    for name in ('x', 'y', 'w', 'h'):
        try:
            out[name] = comp.par[name].eval()
        except Exception:
            pass
    return out


lines = ["#: Full capture of JP's hand-tuned panel (v3)",
         "#: {name: {'geometry': {...}, 'pars': {...},",
         "#:          'expressions': {par: expr}}} — OP refs are paths,",
         "#: 'panel' holds the panel CONTAINER's own settings;",
         "#: 'listerconfig' (queue only) = {DAT name: text}.",
         "CAPTURED_PANEL = {"]
scratch = p.create(containerCOMP, '_capture_scratch')


def _capture(name, comp, stock):
    """One entry: geometry + pars diffed vs stock + expressions."""
    geom = _builtin_geom(comp)
    mine_v, mine_e = _snapshots(comp)
    if stock is not None:
        stock_v, _ = _snapshots(stock)
        pars = _diff(mine_v, stock_v)
    else:
        pars = mine_v
    entry = {"geometry": geom, "pars": pars}
    if mine_e:
        entry["expressions"] = mine_e
    return entry


def _emit(name, entry):
    lines.append(f'    "{name}": {{')
    lines.append(f'        "geometry": {entry["geometry"]!r},')
    lines.append(f'        "pars": {entry["pars"]!r},')
    if entry.get("expressions"):
        lines.append(f'        "expressions": '
                     f'{entry["expressions"]!r},')
    if entry.get("listerconfig"):
        lines.append(f'        "listerconfig": '
                     f'{entry["listerconfig"]!r},')
    lines.append('    },')
    extra = ''
    if entry.get("expressions"):
        extra += f', {len(entry["expressions"])} exprs'
    if entry.get("listerconfig"):
        extra += ', listerconfig DATs'
    print(f'[capture] {name}: geometry {entry["geometry"]} — '
          f'{len(entry["pars"])} changed pars{extra}')


def _stock_container():
    """Fresh bare containerCOMP — baseline for panel + bar containers."""
    return scratch.create(containerCOMP, '_stock_base')


def _stock_widget(toxname):
    """Stock copy of a widget tox — the INNER widget, not the loadTox
    wrapper (the wrapper is a plain container with no custom pars;
    v2 diffed against it, which made every diff a full snapshot)."""
    path = _tox_path(toxname)
    if not os.path.isfile(path):
        return None
    ret = scratch.loadTox(path)
    wrapper = ret if ret is not None else scratch.op(toxname)
    if wrapper is None:
        return None
    for ch in wrapper.children:
        if ch.name == wrapper.name or ch.isPanel:
            return ch
    return wrapper


def _dat_texts(comp):
    """{DAT name: text} for the DATs directly inside comp (the
    listerConfig config/callbacks DATs — where hand-tuned column
    settings live)."""
    out = {}
    try:
        dats = list(comp.dats)
    except Exception:
        return out
    for d in dats:
        try:
            out[d.name] = d.text
        except Exception:
            pass
    return out


# ---- the panel CONTAINER itself (JP: capture its settings too) --------
_emit("panel", _capture("panel", p, _stock_container()))

# ---- every widget / bare-container child -------------------------------
for c in sorted(p.children, key=_safe_geom):
    name = c.name
    if name.startswith('_') or (name not in _TOX_OF
                                 and name not in _BARE_CONTAINERS):
        continue        # listerConfig, DATs, scratch, ...
    # skip the lister's internal nodes (listerConfig etc.)
    try:
        c.par.x.eval()
    except Exception:
        continue
    if name in _BARE_CONTAINERS:
        stock = _stock_container()
    else:
        stock = _stock_widget(_TOX_OF[name])
    entry = _capture(name, c, stock)
    # queue: the lister's config COMP holds hand-tuned column state in
    # its DATs — capture their text wherever the config lives (inside
    # the lister, or flattened at panel root as seen in the live panel)
    if name == "queue":
        cfg = c.op('listerConfig')
        if cfg is None:
            cfg = p.op('listerConfig')
        if cfg is not None:
            texts = _dat_texts(cfg)
            if texts:
                entry['listerconfig'] = texts
    _emit(name, entry)

# clean the scratch (all stock copies)
scratch.destroy()

lines.append('}')
text = '\n'.join(lines)
print()
print(f'[capture] full dump written to {DUMP_PATH} '
      f'({len(lines)} lines)')
print('[capture] next build_panel.py run applies it automatically '
      '(the capture is canonical)')
try:
    with open(DUMP_PATH, 'w', encoding='utf-8') as f:
        f.write(text + '\n')
except Exception as exc:
    print(f'[capture] could not write file: {exc}')
