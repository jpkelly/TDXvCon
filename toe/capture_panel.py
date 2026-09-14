"""capture_panel.py v4 — full-fidelity snapshot of your hand-tuned panel.

Run in the TD textport AFTER adjusting the panel by hand:

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/capture_panel.py',
              encoding='utf-8').read())

Captures the PANEL CONTAINER ITSELF (a 'panel' entry: its Layout/Look/
drop settings, diffed against a fresh containerCOMP) plus EVERY widget
— diffing EVERY par (custom AND builtin: fonts, font choices, sizes,
colors, alignment, everything) against a freshly loaded copy of each
widget's tox.

v4 (JP 2026-09-14): the capture now owns PANEL MEMBERSHIP —
  - HAND-ADDED widgets are captured with the palette tox they came
    from ('widgettox' field, read from the widget's own Widgettox
    par), so future builds RECREATE them from the palette. Unknown
    widget types (no palette tox) are reported loudly and skipped —
    the builder can only rebuild what it knows how to make.
  - BUILDER widgets MISSING from the panel are recorded as removed
    ('removed' list) — future builds skip creating them. Removing
    the queue removes the batch UI; the encoder itself (queue_table,
    panel_callbacks, movieout...) is BUILDER INFRASTRUCTURE and is
    never treated as removed.
  - NODE LAYOUT: each entry records nodeX/nodeY — where the COMP sits
    in the network editor INSIDE the panel operator — so a hand-
    arranged node layout persists across rebuilds.

Fidelity details:
  - geometry (panel-view x/y/w/h) per widget, in the 'geometry' section
  - nodeX/nodeY per widget, in the 'nodelayout' section
  - OP-valued pars become PATH STRINGS; refs pointing INSIDE a widget
    are skipped (internal wiring), outside refs are kept as paths
  - only DIFFS vs stock are recorded — unchanged pars regenerate from
    the tox on rebuild
  - pulse pars are skipped (they are actions, not state)
  - the queue entry also carries 'listerconfig': {DAT name: text}

Output: written to toe/panel_layout_captured.py (summary printed).
The next build_panel.py run applies it automatically — the capture
is canonical.
"""

import os


def _find_container_comp():
    """The containerCOMP type constant — from the td module first, the
    textport globals second. TD injects op-type constants into contexts
    IT runs (textport) but NOT into imported DAT modules, so a DAT-based
    runner needs this indirection (the find_type pattern from
    build_network.py / build_panel.py)."""
    try:
        import td
        return td.containerCOMP
    except Exception:
        return globals()["containerCOMP"]


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

#: Every palette tox we can recreate a hand-added widget from (Basic
#: Widgets directory — the source of the panel's existing widgets).
_BASIC_WIDGET_TOXES = {
    "buttonMomentary", "buttonToggle", "buttonPush", "checkbox",
    "radioButton", "dropDownMenu", "fieldString", "fieldNumeric",
    "fieldFileBrowser", "fieldFolderBrowser", "sliderHorz",
    "sliderVert", "slider2D", "sliderBank", "label", "lister",
    "masterHeader", "masterButton", "masterLabel", "masterSlider",
    "masterStringField", "masterNumericField", "masterField",
    "masterSliderHorz", "masterCheckbox", "masterCheckbox",
    "masterRadioButton", "masterDropMenu", "masterList",
    "masterFolderTabs", "masterSection", "masterFooter",
}

#: builder-made bare containers (no tox — baseline is a fresh
#: containerCOMP; all their pars are builtin anyway)
_BARE_CONTAINERS = {"prog_track", "prog_fill"}

#: The panel widgets the BUILDER knows how to make (mirror of
#: build_panel._WIDGETS). Used to detect (a) hand-ADDED widgets (in the
#: panel but not here → captured with their palette tox so future
#: builds recreate them) and (b) builder widgets REMOVED by hand (in
#: here but missing from the panel → future builds skip them).
_BUILDER_WIDGETS = {
    "destination", "codec_dd", "format_dd", "subtype_dd", "quality_s",
    "fps_f", "scaled_t", "scale_dd", "fit_dd", "resw_f", "resh_f",
    "start_b", "pause_b", "stop_b", "add_b", "output_l",
    "prog_track", "prog_fill", "queue", "status_l",
}

#: BUILDER INFRASTRUCTURE — never treated as 'removed' even if absent
#: (the panel breaks without them). NOTE (JP, 2026-09-14): status_l is
#: NOT in this set — the status line is a removable UI widget (the
#: Status par + textport notes carry the state; the label is display
#: only). Only the batch queue plumbing + the progress bar are
#: structural.
_KEEP_ALWAYS = {"queue", "prog_track", "prog_fill"}

#: palette tox directory → the tox file names inside it that we know
#: how to recreate. A hand-added widget reports its palette origin via
#: its own 'Widgettox' par (e.g. 'buttonMomentary').
_TOX_DIRS = [
    ("/Applications/TouchDesigner.app/Contents/Resources/tfs/"
     "Samples/Palette/UI/Basic Widgets", _BASIC_WIDGET_TOXES),
    ("/Applications/TouchDesigner.app/Contents/Resources/tfs/"
     "Samples/Palette/UI", {"lister", "sliderBank", "radioButton",
                            "button"}),
]

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


lines = ["#: Full capture of JP's hand-tuned panel (v4)",
         "#: {name: {'geometry': {...}, 'nodelayout': (x, y),",
         "#:          'pars': {...}, 'expressions': {...},",
         "#:          'binds': {...}, 'widgettox': 'palette tox'}}}",
         "#: — OP refs are paths; 'panel' holds the panel CONTAINER's",
         "#: own settings; 'listerconfig' (queue only) = {DAT: text}.",
         "#: 'added' = hand-added widgets (rebuilt from 'widgettox');",
         "#: 'removed' = builder widgets deleted by hand (skipped).",
         "CAPTURED_PANEL = {"]
_containerCOMP = _find_container_comp()
scratch = p.create(_containerCOMP, '_capture_scratch')


def _node_layout(comp):
    """(nodeX, nodeY) — where the COMP sits in the network editor."""
    try:
        return (comp.nodeX, comp.nodeY)
    except Exception:
        return None


def _capture(name, comp, stock):
    """One entry: geometry + node layout + pars/exprs/binds."""
    geom = _builtin_geom(comp)
    mine_v, mine_e, mine_b = _snapshots(comp)
    if stock is not None:
        stock_v, stock_e, stock_b = _snapshots(stock)
        pars = _diff(mine_v, stock_v)
        # expressions/binds that MATCH stock regenerate from the tox —
        # only genuine differences are baked
        exprs = {k: v for k, v in mine_e.items() if stock_e.get(k) != v}
        binds = {k: v for k, v in mine_b.items() if stock_b.get(k) != v}
    else:
        pars, exprs, binds = mine_v, mine_e, mine_b
    entry = {"geometry": geom, "pars": pars}
    nl = _node_layout(comp)
    if nl is not None:
        entry["nodelayout"] = nl
    if exprs:
        entry["expressions"] = exprs
    if binds:
        entry["binds"] = binds
    return entry


def _emit(name, entry):
    lines.append(f'    "{name}": {{')
    lines.append(f'        "geometry": {entry["geometry"]!r},')
    if entry.get("nodelayout"):
        lines.append(f'        "nodelayout": {entry["nodelayout"]!r},')
    if entry.get("widgettox"):
        lines.append(f'        "widgettox": {entry["widgettox"]!r},')
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
    if entry.get("nodelayout"):
        extra += ', node layout'
    if entry.get("widgettox"):
        extra += f', tox={entry["widgettox"]!r}'
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
    return scratch.create(_containerCOMP, '_stock_base')


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

# ---- MEMBERSHIP accumulators (v4) --------------------------------------
# added:   hand-added widgets (in the panel, unknown to the builder map)
# removed: builder widgets deleted by hand (absent from the panel)
added = []
removed = []

# ---- every widget / bare-container child -------------------------------
for c in sorted(p.children, key=_safe_geom):
    name = c.name
    if name.startswith('_'):
        continue
    try:
        c.par.x.eval()
    except Exception:
        continue        # DATs, TOPs, scratch, internal nodes
    known = name in _TOX_OF or name in _BARE_CONTAINERS
    if not known:
        # v4 (JP): a hand-ADDED widget. Capture it IF we can identify
        # its palette tox (its own Widgettox par) — then future builds
        # recreate it from the palette. Unknown widget types are
        # reported loudly and skipped (the builder can only make what
        # it knows). listerConfig (queue's config COMP) is internal
        # plumbing, not a user widget — excluded.
        tox = None
        try:
            tox = str(c.par.Widgettox.eval() or "")
        except Exception:
            tox = ""
        if not tox or tox == "None":
            print(f'[capture] !! {name}: hand-added widget with no '
                  'Widgettox par — cannot recreate; NOT captured '
                  '(add it to build_panel._WIDGETS manually)')
            continue
        # verify the tox exists in our palette dirs
        toxfile = None
        for d, allowed in _TOX_DIRS:
            cand = os.path.join(d, f"{tox}.tox")
            if os.path.isfile(cand) and (allowed is None
                                         or tox in allowed):
                toxfile = cand
                break
        if toxfile is None:
            print(f'[capture] !! {name}: Widgettox={tox!r} not found '
                  'in the palette directories — NOT captured')
            continue
        entry = _capture(name, c, _stock_widget(tox))
        entry['widgettox'] = tox
        _emit(name, entry)
        added.append(name)
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

# builder widgets MISSING from the panel = removed by hand (v4).
# Infrastructure widgets are exempt (the panel breaks without them);
# only UI widgets may be removed. A removed queue means JP wants no
# batch UI — the encoder still works via the CLI/TCP.
_present = set()
for c in p.children:
    try:
        c.par.x.eval()
        _present.add(c.name)
    except Exception:
        continue
for name in sorted(_BUILDER_WIDGETS):
    if name in _KEEP_ALWAYS:
        continue
    if name not in _present:
        removed.append(name)
        print(f'[capture] {name}: builder widget absent — recorded as '
              'REMOVED (future builds skip it)')

# clean the scratch (all stock copies)
scratch.destroy()

if added:
    lines.append(f'    "added": {sorted(added)!r},')
if removed:
    lines.append(f'    "removed": {sorted(removed)!r},')
lines.append('}')
text = '\n'.join(lines)
print()
print(f'[capture] full dump written to {DUMP_PATH} '
      f'({len(lines)} lines)')
if added:
    print(f'[capture] hand-added widgets captured (recreated from '
          f'palette tox): {sorted(added)}')
if removed:
    print(f'[capture] builder widgets recorded REMOVED: {sorted(removed)}')
print('[capture] next build_panel.py run applies it automatically '
      '(the capture is canonical)')
try:
    with open(DUMP_PATH, 'w', encoding='utf-8') as f:
        f.write(text + '\n')
except Exception as exc:
    print(f'[capture] could not write file: {exc}')
