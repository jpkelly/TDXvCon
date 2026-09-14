"""capture_panel.py v3.1 — full-fidelity snapshot of your hand-tuned panel.

Run in the TD textport AFTER adjusting the panel by hand:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/capture_panel.py',
              encoding='utf-8').read())

Captures the PANEL CONTAINER ITSELF (a 'panel' entry: its Layout/Look/
drop settings, diffed against a fresh containerCOMP) plus EVERY widget
— all 20, including add_b / resw_f / resh_f and the two progress-bar
containers that v2 silently skipped — diffing EVERY par (custom AND
builtin: fonts, font choices, sizes, colors, alignment, everything)
against a freshly loaded copy of each widget's tox.

v3.1 fixes found by auditing the first v3 run (2026-09-14):
  - PAR ENUMERATION now goes comp.pages -> page.pars with fallbacks
    (v3's comp.pars alone did NOT deliver builtin pars — the 'panel'
    and 'prog_fill' entries came out with 0 changed pars despite the
    builder-set drop settings and layer=1)
  - EXPRESSIONS are DIFFED AGAINST STOCK too (v3 recorded ~20 exprs
    per button: the widget's own internal exprs plus 'None' strings
    that this TD build returns for unset expressions — baking those
    would break pars)
  - BINDS (par.bindExpr) are captured as well — value + expr + bind
    is the complete parameter state
  - listerconfig lookup goes through the queue's Configcomp PAR first
    (canonical — points at the ACTIVE config wherever it lives), with
    loud diagnostics instead of v3's silent skip

Fidelity details:
  - geometry (panel-view x/y/w/h) per widget, in the 'geometry' section
  - OP-valued pars become PATH STRINGS (v2 wrote TD reprs like
    'type:tableDAT path:...' which are not valid Python); refs pointing
    INSIDE a widget are skipped (internal wiring — baking them would
    reach into the widget's internals), refs to outside ops
    (queue_display, panel_dnd, ...) are kept as paths
  - only DIFFS vs stock are recorded — unchanged pars (fonts, colors,
    sizes matching the stock widget) regenerate from the tox on
    rebuild, so capture + rebuild reproduces the panel exactly
  - pulse pars are skipped (they are actions, not state)
  - the queue entry also carries 'listerconfig': {DAT name: text} —
    the lister's config COMP holds hand-tuned column settings

Output: written to toe/panel_layout_captured.py (summary printed).
The next build_panel.py run applies it automatically — the capture
is canonical. Hand-broken expressions (typos) are recorded faithfully
— check the printed summary.
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
_ENUM_REPORTED = [False]  # one-shot enumeration diagnostic


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
    """(pars, exprs, binds) of EVERY par — builtin AND custom.

    v3.1: enumeration goes comp.pages -> page.pars (the probe-verified
    pattern) with customPars/comp.pars fallbacks — the first v3 run
    proved comp.pars alone did NOT deliver builtin pars ('panel' came
    out with 0 changed pars despite builder-set drop settings, and
    prog_fill lost its layer=1).
    Pulse pars are actions, not state: skipped. Geometry pars are
    skipped as VALUES (captured separately) but their expressions are
    still recorded. 'None' strings — what this TD build returns for
    unset expressions/binds — are filtered; the stock diff below then
    keeps only expressions/binds that genuinely differ.
    """
    vals, exprs, binds = {}, {}, {}
    allpars = []
    n_pages = n_custom = n_bare = 0
    try:
        for page in comp.pages:
            for par in page.pars:
                allpars.append(par)
                n_pages += 1
    except Exception:
        pass
    try:
        allpars.extend(comp.customPars)
        n_custom = len(comp.customPars)
    except Exception:
        pass
    try:
        # whatever comp.pars yields on this build — belt and braces
        allpars.extend(comp.pars)
        n_bare = len(comp.pars)
    except Exception:
        pass
    if not _ENUM_REPORTED[0]:
        _ENUM_REPORTED[0] = True
        print(f'[capture] par enumeration on {comp.name}: {n_pages} '
              f'via pages, {n_custom} via customPars, {n_bare} via pars')
    seen = set()
    for par in allpars:
        try:
            pname = par.name
        except Exception:
            continue
        if pname in seen:
            continue
        seen.add(pname)
        try:
            if str(par.style) == "Pulse":
                continue
            is_geom = (not par.isCustom) and pname in _GEOM_PARS
        except Exception:
            continue
        v = _snap_par(comp, par)
        if v is not _SKIP and not is_geom:
            vals[pname] = v
        try:
            e = par.expr
        except Exception:
            e = None
        if e and str(e) != 'None':
            exprs[pname] = str(e)
        try:
            b = par.bindExpr
        except Exception:
            b = None
        if b and str(b) != 'None':
            binds[pname] = str(b)
    return vals, exprs, binds


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


lines = ["#: Full capture of JP's hand-tuned panel (v3.1)",
         "#: {name: {'geometry': {...}, 'pars': {...},",
         "#:          'expressions': {...}, 'binds': {...}}} —",
         "#: OP refs are paths; 'panel' holds the panel CONTAINER's",
         "#: own settings; 'listerconfig' (queue only) = {DAT: text}.",
         "CAPTURED_PANEL = {"]
scratch = p.create(containerCOMP, '_capture_scratch')


def _capture(name, comp, stock):
    """One entry: geometry + pars/exprs/binds, each diffed vs stock."""
    geom = _builtin_geom(comp)
    mine_v, mine_e, mine_b = _snapshots(comp)
    if stock is not None:
        stock_v, stock_e, stock_b = _snapshots(stock)
        pars = _diff(mine_v, stock_v)
        # expressions/binds that MATCH stock regenerate from the tox —
        # only genuine differences are baked (kills the widget-internal
        # expr flood the first v3 run recorded)
        exprs = {k: v for k, v in mine_e.items() if stock_e.get(k) != v}
        binds = {k: v for k, v in mine_b.items() if stock_b.get(k) != v}
    else:
        pars, exprs, binds = mine_v, mine_e, mine_b
    entry = {"geometry": geom, "pars": pars}
    if exprs:
        entry["expressions"] = exprs
    if binds:
        entry["binds"] = binds
    return entry


def _emit(name, entry):
    lines.append(f'    "{name}": {{')
    lines.append(f'        "geometry": {entry["geometry"]!r},')
    lines.append(f'        "pars": {entry["pars"]!r},')
    if entry.get("expressions"):
        lines.append(f'        "expressions": '
                     f'{entry["expressions"]!r},')
    if entry.get("binds"):
        lines.append(f'        "binds": '
                     f'{entry["binds"]!r},')
    if entry.get("listerconfig"):
        lines.append(f'        "listerconfig": '
                     f'{entry["listerconfig"]!r},')
    lines.append('    },')
    extra = ''
    if entry.get("expressions"):
        extra += f', {len(entry["expressions"])} exprs'
    if entry.get("binds"):
        extra += f', {len(entry["binds"])} binds'
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
    """{DAT name: text} for the DATs inside comp (the listerConfig
    config/callbacks DATs — where hand-tuned column settings live).
    comp.dats first; children-scan fallback in case .dats fails on
    this build (the first v3 run produced NO DATs silently)."""
    out = {}
    dats = []
    try:
        dats = list(comp.dats)
    except Exception:
        dats = []
    if not dats:
        try:
            dats = [ch for ch in comp.children if ch.isDAT]
        except Exception:
            dats = []
    for d in dats:
        try:
            out[d.name] = d.text
        except Exception as exc:
            print(f"[capture] ( DAT {d.name} text read failed: {exc} )")
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
    # its DATs. Find it CANONICALLY via the Configcomp par (it points
    # at the ACTIVE config wherever it lives) — the first v3 run
    # printed no listerconfig at all, so this branch now reports
    # loudly instead of skipping silently.
    if name == "queue":
        cfg = None
        try:
            cfg = c.par.Configcomp.eval()
        except Exception:
            cfg = None
        if not _is_op(cfg):
            cfg = c.op('listerConfig')
        if not _is_op(cfg):
            cfg = p.op('listerConfig')
        if not _is_op(cfg):
            print('[capture] !! queue: listerConfig NOT FOUND '
                  '(Configcomp par, inside queue, panel root — all '
                  'missed); column tuning will not be captured')
        else:
            texts = _dat_texts(cfg)
            print(f"[capture] queue: listerConfig at {cfg.path} — "
                  f"{len(texts)} DATs"
                  + (f" ({', '.join(sorted(texts))})" if texts else ''))
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
