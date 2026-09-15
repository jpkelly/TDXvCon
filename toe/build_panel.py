"""build_panel.py — generate the vCon panel inside the vCon COMP. (v4)

Run in the TouchDesigner TEXTPORT (never import):

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/build_panel.py',
              encoding='utf-8').read())

Creates /project1/vcon/panel — Basic Widgets from the app-bundle palette
.tox files, configured ENTIRELY through external widget parameters
(never their internals). LIVE-VERIFIED: config pars live on the INNER
COMP (children scan); First-uppercase names (Value0, Widgetlabel,
Menunames, Menulabels, Offtoonscript0, Onvaluechangescript0); label
par for fields/buttons is Widgetlabel (NOT Label — that's the widget's
own name label); button face text is Buttonofflabel/Buttononlabel.

Layout (y measured up from the panel bottom):
    row 6  SOURCE file browser           row 5  DESTINATION folder browser
    row 4  CODEC | SUBTYPE               row 3  FORMAT | QUALITY
    row 2  FPS | RESOLUTION | FIT
    row 1  START PAUSE STOP   OUTPUT: <auto-named file>
    row 0  progress slider | STATUS line
    queue  batch table (lister) below, fed by queue_table DAT
"""

import os

#: td-module op types (find_type resolves td first, globals second —
#: same pattern as build_network.py).
def find_type(*names):
    try:
        import td as _td
    except ImportError:
        _td = None
    for n in names:
        if _td is not None and hasattr(_td, n):
            return getattr(_td, n)
        if n in globals():
            return globals()[n]
    raise RuntimeError(f"op type {names} unavailable — run in the textport")


#: Widget tox roots: most Basic Widgets live in the Basic Widgets folder,
#: but the lister (batch queue) sits at the UI palette ROOT (live-checked).
_TOX_DIR = ("/Applications/TouchDesigner.app/Contents/Resources/tfs/"
            "Samples/Palette/UI/Basic Widgets")
_UI_TOX_DIR = ("/Applications/TouchDesigner.app/Contents/Resources/tfs/"
               "Samples/Palette/UI")
_TOX_PATHS = {
    "lister": os.path.join(_UI_TOX_DIR, "lister.tox"),
}
COMP_PARENT = "/project1/vcon"
COMP_NAME = "panel"
REPO = "/Users/jp/Documents/GitHub/vCon"

#: op-type constants — resolved via the td module first, textport
#: globals second (find_type pattern). Makes the script runnable from
#: the panel_build_run DAT, not just the textport.
def _td_type(name):
    try:
        import td
        return getattr(td, name)
    except Exception:
        return globals()[name]

_TEXTDAT = lambda: _td_type("textDAT")
_TABLEDAT = lambda: _td_type("tableDAT")
_CONTAINERCOMP = lambda: _td_type("containerCOMP")
_EXECUTEDAT = lambda: _td_type("executeDAT")

#: JP's hand-tuned capture — the CANONICAL panel state (capture-first
#: workflow). Read at build START so membership is honored during
#: creation: 'removed' widgets are skipped, 'added' widgets are
#: recreated from their palette tox. Soft-fails (pre-v4 dumps without
#: membership lists simply build everything, as before).
_CAP_DUMP = f"{REPO}/toe/panel_layout_captured.py"
_CAPTURE = {}
if os.path.isfile(_CAP_DUMP):
    try:
        _ns = {}
        exec(compile(open(_CAP_DUMP, encoding='utf-8').read(),
                     _CAP_DUMP, 'exec'), _ns)
        _CAPTURE = _ns.get('CAPTURED_PANEL', {})
    except Exception as _exc:
        say(f"(capture unreadable: {_exc} — building all widgets)")
        _CAPTURE = {}
_REMOVED = set(_CAPTURE.get("removed") or [])
_ADDED = {k: v for k, v in _CAPTURE.items()
          if isinstance(v, dict) and v.get("widgettox")}

#: GRID GEOMETRY — computed rows, uniform 30px heights, narrow columns.
#: Panel is 660x640; STATUS sits at the very bottom (plenty of room).
#: Row pitch 45; y from panel bottom.
_ROW = 30
_TOP = 600


def _r(n):
    return _TOP - n * 45


_WIDGETS = {
    # destination browser, full width (SOURCE field removed — JP:
    # drops / +ADD into the queue are the way files get added)
    "destination":  ("fieldFolderBrowser", 20, 600, 620, _ROW),
    # settings, two narrow columns (half-width each — no spillover)
    "container_dd": ("dropDownMenu",       20, 555, 230, _ROW),
    "codec_dd":     ("dropDownMenu",      260, 555, 230, _ROW),
    "audio_dd":     ("dropDownMenu",       20, 510, 230, _ROW),
    "format_dd":    ("dropDownMenu",      250, 510, 230, _ROW),
    "quality_dd":   ("dropDownMenu",      440, 510, 190, _ROW),
    "subtype_dd":   ("dropDownMenu",      440, 540, 200, _ROW),
    # row: FPS | SCALING | SCALE(hidden) | W | H(hidden) | FIT —
    # tightened per JP: the row overflowed and FIT fell off-panel.
    "fps_f":        ("fieldString",        20, 465, 110, _ROW),
    "scaled_t":     ("buttonToggle",      150, 465, 110, _ROW),
    "scale_dd":     ("dropDownMenu",      270, 465, 115, _ROW),
    "resw_f":       ("fieldString",       395, 465,  70, _ROW),
    "resh_f":       ("fieldString",       465, 465,  70, _ROW),
    "fit_dd":       ("dropDownMenu",      545, 465,  95, _ROW),
    # buttons (label disabled) — evenly spaced, faces centered
    "start_b":      ("buttonMomentary",    20, 420, 145, _ROW),
    "pause_b":      ("buttonMomentary",   175, 420, 145, _ROW),
    "stop_b":       ("buttonMomentary",   330, 420, 145, _ROW),
    "add_b":        ("buttonMomentary",   485, 420, 155, _ROW),
    # OUTPUT: full-width read-only field BELOW the buttons (JP: the
    # derived filename is too long for a side slot — give it the row)
    "output_l":     ("label",              20, 375, 620, _ROW),
    # PROGRESS slider, full width
    # PROGRESS: custom bar (no palette widget exists, and sliderHorz's
    # numeric field CANNOT be hidden — probe-verified: 'off' writes
    # succeed but the field persists). A Container track + a fill
    # Container whose width EXPRESSION drives from the Progress par:
    # pure geometry, no number by construction.
    "prog_track":  ("__bar__",            20, 330, 620, 16),
    "prog_fill":   ("__bar__",            20, 330, 620, 16),
    # queue, then STATUS at the very bottom
    "queue":        ("lister",             20,  90, 620, 200),
    "status_l":     ("label",              20,  40, 620, _ROW),
}

#: Field titles via Widgetlabel (LIVE-DUMPED: the widget's title par).
_TITLES = {
    "destination": "DESTINATION",
    "container_dd": "CONTAINER",
    "audio_dd": "AUDIO",
    "codec_dd": "CODEC",
    "subtype_dd": "SUBTYPE",
    "format_dd": "FORMAT",
    "quality_dd": "QUALITY",
    "fps_f": "FPS",
    "scaled_t": "SCALING",
    "scale_dd": "SCALE",
    "fit_dd": "FIT",
    "resw_f": "W",
    "resh_f": "H",
    "output_l": "OUTPUT",
    "status_l": "STATUS",
}

_BUTTON_SCRIPT_PAR = "Offtoonscript0"


def say(msg):
    print(f"[panel] {msg}")


def inner_of(wrapper):
    """The actual widget COMP inside a loadTox wrapper (children scan)."""
    for c in wrapper.children:
        if c.name == wrapper.name or c.isPanel:
            return c
    say(f"!! no inner widget inside {wrapper.path}")
    return None


def place(outer, x, y, w, h, row=0):
    """Place a widget: panel-view coords AND network coords.

    - par.x/y/w/h  = where it sits in the PANEL viewer (the UI).
    - nodeX/nodeY  = where the node sits in the NETWORK editor. Without
      these every widget lands at the same spot (a card pile). We mirror
      the panel grid: x maps to nodeX, rows map top-down to nodeY, so the
      network view roughly sketches the panel's layout.
    """
    try:
        outer.par.x = x
        outer.par.y = y
        outer.par.w = w
        outer.par.h = h
    except Exception as exc:
        say(f"  (place {outer.name}: {exc})")
    try:
        # Network scale: COMP nodes render ~200px wide / ~130px tall in the
        # network editor. Panel pitch is 45 — 1:1 mirroring overlaps badly
        # (screenshot-verified). Scale x2 horizontally, x4 vertically so
        # every node clears its neighbors with margin.
        outer.nodeX = (x - 20) * 2
        outer.nodeY = -y * 4 - 120
    except Exception:
        pass


def setp(inner, par_name, value):
    """Set one inner-widget custom par; print the full surface on a miss."""
    try:
        getattr(inner.par, par_name).val = value
        return True
    except Exception:
        names = [p.name for p in inner.customPars]
        say(f"  !! {inner.path}: no par {par_name}. customPars: "
            f"{', '.join(names)}")
        return False


def set_menu(inner, names, labels, default):
    """Populate a dropDownMenu (labels quote-once when containing spaces)."""
    ok = True
    ok &= setp(inner, "Menunames", " ".join(names))
    quoted = " ".join(f"'{l}'" if " " in l else l for l in labels)
    ok &= setp(inner, "Menulabels", quoted)
    if default in names:
        ok &= setp(inner, "Value0", default)
    return ok


def _grey_out_b(inner, grey=True):
    """Builder-side grey-out — STRING MENU tokens ('off'/'on'), not
    booleans (integer writes select menu INDEX 0, which can be 'on')."""
    for cand in ("enable", "Enable"):
        par = getattr(inner.par, cand, None)
        if par is None:
            continue
        try:
            menus = list(getattr(par, "menuNames", None) or [])
            if menus:
                getattr(inner.par, cand).val = "off" if grey else "on"
            else:
                getattr(inner.par, cand).val = 0 if grey else 1
            return True
        except Exception:
            continue
    return False


def build():
    say("=" * 52)
    say("building vCon panel (v4)")
    say("=" * 52)

    vcon = op(COMP_PARENT)
    if vcon is None:
        raise RuntimeError(f"{COMP_PARENT} not found — run build_network.py "
                           f"first, then this script")

    try:
        vcon.par.opshortcut = "vcon"
    except Exception as exc:
        say(f"(opshortcut: {exc})")

    for stale in (COMP_NAME, "panel_callbacks", "queue_table",
                  "queue_display", "panel_tick", "panel_capture_run"):
        if vcon.op(stale) is not None:
            say(f"removing existing {stale}")
            vcon.op(stale).destroy()
    # panel_dnd DATs ACCUMULATE across rebuilds (create-with-existing-
    # name auto-renames: the live toe had panel_dnd11) — sweep them ALL
    # so every rebuild names the fresh callbacks DAT plainly 'panel_dnd'.
    # Same for the RUNNER DATs (panel_build_run / panel_capture_run):
    # create-with-existing-name auto-renames, and a duplicate
    # panel_build_run would make op('panel_build_run') ambiguous —
    # sweep by PREFIX so every rebuild leaves exactly one of each.
    for _pref in ("panel_dnd", "panel_build_run", "panel_capture_run"):
        for ch in list(vcon.children):
            suffix = ch.name[len(_pref):] if ch.name.startswith(_pref) else None
            if suffix == "" or (suffix is not None and suffix.isdigit()):
                say(f"removing existing {ch.name}")
                ch.destroy()

    # ---- callbacks DAT (file-linked, like the controller DAT) -----------
    say("creating panel_callbacks DAT (file-linked)")
    cb = vcon.create(_TEXTDAT(), "panel_callbacks")
    cb.nodeX = 300
    cb.nodeY = 150
    cb.par.file = f"{REPO}/toe/vcon_panel_callbacks.py"
    cb.par.syncfile = 1

    # ---- drag/drop callbacks DAT (panel drop target) ----------------------
    say("creating panel_dnd callbacks DAT")
    dnd_cb = vcon.create(find_type("textDAT"), "panel_dnd")
    dnd_cb.nodeX = 360
    dnd_cb.nodeY = 150
    dnd_cb.text = (
        "# Panel drag/drop callbacks (docs: Drag-and-Drop page).\n"
        "# onHoverStartGetAccept MUST return True or the drop is\n"
        "# silently rejected.\n"
        "\n"
        "\n"
        "def onHoverStartGetAccept(comp, info):\n"
        "    for item in info.get('dragItems', []):\n"
        "        p = getattr(item, 'path', None)\n"
        "        if p is None and isinstance(item, str):\n"
        "            p = item\n"
        "        if p and (os.path.isfile(p) or os.path.isdir(p)):\n"
        "            return True\n"
        "    return False\n"
        "\n"
        "\n"
        "def onDropGetResults(comp, info):\n"
        "    try:\n"
        "        op('panel_callbacks').module.onDragDrop(\n"
        "            {'dropItems': list(info.get('dragItems', []))})\n"
        "        return {'accepted': True}\n"
        "    except Exception as exc:\n"
        "        debug(f'vCon drop failed: {exc}')\n"
        "        return {'accepted': False}\n"
        "\n"
        "\n"
        "import os\n"
    )
    # file-linked? no — this DAT is generated; the callbacks module holds
    # the real logic (onDragDrop).

    # ---- capture runner DAT (JP: re-capture with one exec, no repo
    # path) — file-linked to toe/capture_run.py, swept on every rebuild
    # like the other DATs so it can never go stale -----------------------
    say("creating panel_capture_run DAT (file-linked)")
    crun = vcon.create(_TEXTDAT(), "panel_capture_run")
    crun.nodeX = 360
    crun.nodeY = 90
    crun.par.file = f"{REPO}/toe/capture_run.py"
    crun.par.syncfile = 1

    # ---- build runner DAT (JP: same convenience for REBUILDING the
    # panel — exec(op.vcon.op('panel_build_run').text)) -------------
    say("creating panel_build_run DAT (file-linked)")
    brun = vcon.create(_TEXTDAT(), "panel_build_run")
    brun.nodeX = 360
    brun.nodeY = 150
    brun.par.file = f"{REPO}/toe/build_run.py"
    brun.par.syncfile = 1

    # ---- queue table DAT (lister source) ---------------------------------
    say("creating queue_table DAT (batch list)")
    qt = vcon.create(_TABLEDAT(), "queue_table")
    qt.nodeX = 300
    qt.nodeY = 90
    qt.appendRow(["file", "status", "progress", "path"])
    # DISPLAY table: ONLY file + status — the lister reads THIS one, so
    # auto-define generates exactly two columns (JP: no number column,
    # no progress column). queue_table keeps progress as the bar-TOP
    # driver (read by index, never displayed).
    qd = vcon.create(find_type("tableDAT"), "queue_display")
    qd.nodeX = 430
    qd.nodeY = 90
    qd.appendRow(["file", "status"])

    # ---- panel container -------------------------------------------------
    panelcomp = vcon.create(_CONTAINERCOMP(), COMP_NAME)
    panelcomp.nodeX = 300
    panelcomp.nodeY = 260
    place(panelcomp, 0, 0, 660, 640)

    # ---- load widgets -----------------------------------------------------
    # FLAT WIDGETS AT PANEL ROOT (JP, twice): load the tox into a scratch,
    # copy ONLY the inner widget COMP up to the panel root, destroy the
    # scratch. The panel's children are the actual widgets — no wrapper
    # containers. Configuration still targets TOP-LEVEL parameters of the
    # widget we keep (the inner widget IS the top level of the flat copy);
    # the top-level-only rule is about never reaching INTO the widget's
    # internals, which we never do.
    say("loading widgets")
    widgets = {}
    for outer_name, (tox, x, y, w, h) in _WIDGETS.items():
        if outer_name in _REMOVED:
            say(f"  {outer_name}: skipped — removed in the capture "
                f"(JP deleted it by hand)")
            continue
        if tox == "__bar__":
            # Custom progress bar (no palette widget exists; sliderHorz's
            # numeric field cannot be hidden — probe-verified). A plain
            # Container; the fill gets its width bind below.
            wcomp = panelcomp.create(_CONTAINERCOMP(), outer_name)
            place(wcomp, x, y, w, h)
            widgets[outer_name] = wcomp
            continue
        path = _TOX_PATHS.get(tox,
                              os.path.join(_TOX_DIR, f"{tox}.tox"))
        scratch = panelcomp.create(_CONTAINERCOMP(), "_scratch")
        ret = scratch.loadTox(path)
        wrapper = ret if ret is not None else scratch.op(tox)
        if wrapper is None:
            say(f"!! loadTox({tox}) failed in scratch")
            scratch.destroy()
            continue
        # Find the inner widget (the tox drops a same-named container
        # holding the real widget).
        inner = None
        for c in wrapper.children:
            if c.name == wrapper.name or c.isPanel:
                inner = c
                break
        src_comp = inner if inner is not None else wrapper
        try:
            wcomp = panelcomp.copy(src_comp, name=outer_name)
        except Exception as exc:
            say(f"!! copy {tox} -> {outer_name}: {exc}")
            scratch.destroy()
            continue
        if wcomp is None:
            say(f"!! copy {tox} returned None")
            scratch.destroy()
            continue
        scratch.destroy()
        place(wcomp, x, y, w, h)
        widgets[outer_name] = wcomp
    # HAND-ADDED widgets (capture v4): JP added a palette widget by
    # hand; the capture records its palette tox origin — recreate it
    # the same flat way, then the bake restores its geometry/pars.
    for add_name, add_entry in _ADDED.items():
        if add_name == "panel" or add_name in widgets:
            continue
        tox = add_entry["widgettox"]
        if tox == "lister":
            path = os.path.join(_UI_TOX_DIR, "lister.tox")
        else:
            path = os.path.join(_TOX_DIR, f"{tox}.tox")
        if not os.path.isfile(path):
            say(f"  !! added {add_name}: palette tox {tox!r} missing — "
                f"cannot recreate")
            continue
        scratch = panelcomp.create(_CONTAINERCOMP(), "_scratch")
        ret = scratch.loadTox(path)
        wrapper = ret if ret is not None else scratch.op(tox)
        inner = None
        if wrapper is not None:
            for c in wrapper.children:
                if c.name == wrapper.name or c.isPanel:
                    inner = c
                    break
        src_comp = inner if inner is not None else wrapper
        wcomp = None
        if src_comp is not None:
            try:
                wcomp = panelcomp.copy(src_comp, name=add_name)
            except Exception as exc:
                say(f"  !! added {add_name}: copy failed — {exc}")
        scratch.destroy()
        if wcomp is None:
            continue
        geom = add_entry.get("geometry") or {}
        place(wcomp, geom.get("x", 20), geom.get("y", 40),
              geom.get("w", 100), geom.get("h", 30))
        widgets[add_name] = wcomp
        say(f"  added {add_name}: recreated from palette {tox!r}")
    say(f"loaded {len(widgets)} widgets "
        f"({len(_REMOVED)} removed, {len(_ADDED)} added per capture)")

    # ---- row-click INSPECTOR (JP 2026-09-14; DAT per JP's suggestion) --
    # Media File Info DAT: NATIVE TD metadata reader — codec (vcodec/
    # vcodecDesc), resolution (width/height), fps, duration all from
    # ONE op. Replaces the earlier inspectin moviein + Info CHOP + mdls
    # approach (mdls was a workaround for 'TD exposes no source codec' —
    # wrong; this DAT does it natively).
    say("creating row inspector (Media File Info DAT)")
    insdat = panelcomp.create(find_type("mediafileinfoDAT"), "inspector")
    try:
        insdat.par.display = 0
    except Exception:
        pass

    # ---- panel-root NON-WIDGET ops (listerConfig, inspector, DATs) ----
    # CAPTURE-TRACKED (JP 2026-09-14): these nodes' network positions are
    # hand-arranged too, but they aren't panel VIEW widgets — they get
    # no _WIDGETS entry and were never captured. The capture records
    # them as 'panelnodelayout'; apply positions AFTER the bake too so
    # the capture always wins over the builder's hard-coded spots.
    for ch in list(panelcomp.children):
        nm = ch.name
        if nm in widgets or nm.startswith("_"):
            continue        # view widgets get nodelayout from the bake
        _pos = (_CAPTURE.get("panelnodelayout") or {}).get(nm)
        if _pos:
            try:
                ch.nodeX, ch.nodeY = _pos
            except Exception:
                pass

    # ---- queue lister: force geometry + visibility ------------------------
    # The lister's copy historically resisted place() (missing Layout
    # pars on its wrapper). Write each geometry par individually and
    # report misses, so the queue is VISIBLE at a known spot, plus an
    # explicit gray background paint so it reads against the panel.
    if "queue" in widgets:
        qx, qy, qw, qh = 20, 90, 620, 200
        q_ = widgets["queue"]
        for pname, val in (("x", qx), ("y", qy), ("w", qw), ("h", qh)):
            try:
                q_.par[pname].val = val
            except Exception as exc:
                say(f"  (queue {pname}: {exc})")
        for pname in ("display", "enable"):
            try:
                q_.par[pname].val = True
            except Exception:
                pass
        try:
            q_.par.layer = 0          # above nothing, below the bars
        except Exception:
            pass
        try:
            q_.par.bgcolorr = 0.25
            q_.par.bgcolorg = 0.25
            q_.par.bgcolorb = 0.25
            q_.par.bgalpha = 1.0
        except Exception:
            pass          # widget COMPs may have these; bare ones may not
        say("  queue: geometry forced 20,90 620x200")

    # ---- progress bar: track + fill, painted with Constant TOPs ----
    # A bare containerCOMP has NO Look page — panels paint via a
    # Background TOP (Look page 'top' on widget COMPs). PROVEN pattern
    # from build_network's set_op_par: OP-type pars accept the object OR
    # the path string, depending on build — try both. Every write in its
    # OWN try so one miss can't skip the rest (the old block lost the
    # width expression when par.top raised — probe 7 found both dead).
    def _link_op(holder, par_name, target):
        for value in (target, target.path):
            try:
                setattr(holder.par, par_name, value)
                return True
            except Exception:
                continue
        say(f"  !! {holder.name}.{par_name}: neither object nor path "
            f"accepted")
        return False

    if "prog_track" in widgets and "prog_fill" in widgets:
        track = widgets["prog_track"]
        fill = widgets["prog_fill"]
        # track: gray paint
        try:
            ttop = track.create(find_type("constantTOP"), "paint")
            ttop.par.colorr = 0.5
            ttop.par.colorg = 0.5
            ttop.par.colorb = 0.5
            ttop.par.alpha = 1.0
            if _link_op(track, "top", ttop):
                say("  track painted gray (Background TOP linked)")
        except Exception as exc:
            say(f"  (track paint: {exc})")
        # fill: green paint + width expression — separate try blocks
        try:
            ftop = fill.create(find_type("constantTOP"), "paint")
            ftop.par.colorr = 0.2
            ftop.par.colorg = 0.8
            ftop.par.colorb = 0.2
            ftop.par.alpha = 1.0
            if _link_op(fill, "top", ftop):
                say("  fill painted green (Background TOP linked)")
        except Exception as exc:
            say(f"  (fill paint: {exc})")
        try:
            # No width expression: the panel tick (onFrame) drives this
            # width directly with BATCH progress (item N of M) — the
            # expression form would only track the current file's 0-1.
            # Seeded at 0.
            fill.par.w.val = 0
            # Z-ORDER (probe 8): same x/y and equal layer=0 means TD draws
            # same-layer siblings by NAME — 'prog_fill' before
            # 'prog_track' — so the gray track covered the green fill.
            # Depth Layer: higher draws over lower.
            fill.par.layer = 1
            track.par.layer = 0
            say("  progress bar: fill width <- Progress par, fill layer 1 (draws over track)")
        except Exception as exc:
            say(f"  (fill width expr: {exc})")

    mod = cb.module

    # ---- titles (Widgetlabel — the live-dumped title par) ----------------
    say("setting widget titles (Widgetlabel)")
    for name, title in _TITLES.items():
        if name in widgets:
            setp(widgets[name], "Widgetlabel", title)
    # Labelwidth per row type; buttons get NO label area (their titles were
    # doubled-up with face text — label disabled per JP's note).
    _LABEL_W = {"destination": 110, "container_dd": 90,
                "audio_dd": 90,
                "codec_dd": 90,
                "subtype_dd": 90, "format_dd": 90, "quality_dd": 90,
                "fps_f": 45, "scaled_t": 60, "scale_dd": 60,
                "fit_dd": 45, "output_l": 110, "status_l": 110,
                "start_b": 0, "pause_b": 0, "stop_b": 0}
    for name, lw in _LABEL_W.items():
        if name in widgets:
            if lw == 0:
                # Buttons get title suppression in the buttons block
                # (Labeldisplay off + width 1 + Widgetlabel text) — skip
                # here to avoid racing that config.
                pass
            else:
                setp(widgets[name], "Labelwidth", lw)
    # PROGRESS bar title via the status-style label — a plain Container
    # has no Widgetlabel, so skip the title loop entry below.
    _LOCAL_TITLES = {}
    for name, title in _LOCAL_TITLES.items():
        if name in widgets:
            setp(widgets[name], "Widgetlabel", title)
    # ADD button: opens a native file dialog, appends to the queue
    # (JP: no dialog existed to add files to the lister). Face/center
    # config now handled in the buttons block below (same as the rest).
    if "add_b" in widgets:
        setp(widgets["add_b"], "Offtoonscript0",
             "op.vcon.op('panel_callbacks').module.AddFiles()")
        say("  add_b: file dialog -> queue wired")
    # remove_b (JP's hand-added button, capture-recreated): removes the
    # SELECTED queue row (click a row first — RemoveSelected guards:
    # no selection / running rows refuse, queue rebuilds from the table
    # if the module recompiled)
    if "remove_b" in widgets:
        setp(widgets["remove_b"], "Offtoonscript0",
             "op.vcon.op('panel_callbacks').module.RemoveSelected()")
        say("  remove_b: selected-row removal wired")

    # Buttons: PROBE 14 VERDICT — the strip renders WIDGETLABEL, and an
    # earlier fix WROTE 'START' there, doubling with the face ('START |
    # START' in JP's screenshot). The strip must be BLANKED; the face is
    # the button's only text, centered via Buttonalignx/y.
    for name, text in [("start_b", "START"), ("pause_b", "PAUSE"),
                       ("stop_b", "STOP"), ("add_b", "+ ADD"),
                       ("remove_b", "REMOVE")]:
        if name in widgets:
            w_ = widgets[name]
            setp(w_, "Widgetlabel", "")          # strip: BLANK (was the dup)
            setp(w_, "Buttonofflabel", text)     # face: the only text
            setp(w_, "Buttononlabel", text)
            setp(w_, "Labeldisplay", "off")      # strip display off too
            setp(w_, "Labelwidth", 1)
            try:
                w_.par.Buttonalignx = "center"
                w_.par.Buttonaligny = "center"
            except Exception:
                pass
            say(f"  {name}: strip blanked, face = {text}")

    # ---- defaults ----------------------------------------------------------
    say("configuring widgets (external pars only)")
    if "fps_f" in widgets:
        setp(widgets["fps_f"], "Value0", "auto")
    # output field: READ-ONLY display of the full output path
    # (destination folder + auto-derived file name). Renders via
    # Widgetlabel (probe 4) — PreviewOutput writes it live.
    # Labelhorizontalmode='fill' is the fix for the early-wrap JP saw:
    # in 'fixed' mode the text area was clamped to Labelwidth (110px),
    # wrapping at 1/6 of the field. 'fill' spans the whole widget width.
    if "output_l" in widgets:
        setp(widgets["output_l"], "Widgetlabel", "(pick a source)")
        setp(widgets["output_l"], "Labelhorizontalmode", "fill")
        setp(widgets["output_l"], "Labelverticalmode", "fill")
        try:
            setp(widgets["output_l"], "Labelwordwrap", 1)
        except Exception:
            pass

    # ---- menus -------------------------------------------------------------
    # CONTAINER filters the codec list (JP: only compatible codecs appear).
    if "container_dd" in widgets:
        _cnames = ["notchlc", "hap", "cineform", "prores", "h264", "h265",
                   "rle", "mjpa", "mpeg4"]
    else:
        _cnames = list(mod.CODECS.keys())
    codec_names = [c for c in _cnames if c in mod.CODECS]
    codec_labels = [mod.CODECS[k]["label"] for k in codec_names]
    if "codec_dd" in widgets:
        set_menu(widgets["codec_dd"], codec_names, codec_labels, "notchlc")
    # SUBTYPE / FORMAT seed with NotchLC's REAL values (no 'none' — JP
    # spec: none is never an option). UpdateSubtypes() re-populates them
    # per codec on every change AND once at build end, so the panel opens
    # in a fully valid state: NotchLC selected -> SUBTYPE greyed (no
    # subtypes), FORMAT rgb + rgba with rgb selected.
    notch = mod.CODECS["notchlc"]
    if "subtype_dd" in widgets:
        _grey = True     # NotchLC has no subtypes: greyed from the start
        setp(widgets["subtype_dd"], "Menunames", "")
        _grey_out_b(widgets["subtype_dd"])
    if "format_dd" in widgets:
        notch_fmts = list(notch["pixel_formats"])
        set_menu(widgets["format_dd"], notch_fmts,
                 [mod.FORMAT_LABELS.get(f, f) for f in notch_fmts], "rgb")
    # CONTAINER dropdown (JP hand-added). The codec dropdown's contents
    # are FILTERED by this selection — see OnContainerChanged().
    if "container_dd" in widgets:
        set_menu(widgets["container_dd"],
                 ["mov", "mp4", "mkv", "webm"],
                 ["QuickTime (.mov)", "MP4 (.mp4)", "Matroska (.mkv)",
                  "WebM (.webm)"],
                 "mov")
        setp(widgets["container_dd"], "Onvaluechangescript0",
             "op.vcon.op('panel_callbacks').module.OnContainerChanged()")
        say("  container_dd: codec-filter wiring hooked")
    # AUDIO dropdown (JP hand-added). Repopulated by container selection
    # (OnContainerChanged). Default 'copy' — mux source audio as-is.
    if "audio_dd" in widgets:
        set_menu(widgets["audio_dd"],
                 ["copy", "pcm_s16le", "pcm_s24le", "aac", "alac",
                  "mp3", "none"],
                 ["Copy (source)", "PCM 16-bit", "PCM 24-bit", "AAC",
                  "ALAC", "MP3", "None (video only)"],
                 "copy")
        setp(widgets["audio_dd"], "Onvaluechangescript0",
             "op.vcon.op('panel_callbacks').module.OnAudioChanged()")
        say("  audio_dd: mux codec wiring hooked")
    # QUALITY is a DROPDOWN of the five named NotchLC levels (JP). The
    # ladder is discrete, and sliderHorz's numeric field cannot be
    # hidden or relabelled (its text par is BIND-driven), so a slider
    # could only ever show a raw float next to the name.
    if "quality_dd" in widgets:
        set_menu(widgets["quality_dd"],
                 ["0.0", "0.285", "0.575", "0.862", "1.0"],
                 ["Good", "Very Good", "Excellent", "Optimal", "Best"],
                 "0.862")
    if "fit_dd" in widgets:
        set_menu(widgets["fit_dd"],
                 ["fitbest", "fill", "fithorz", "fitvert", "fitoutside"],
                 ["Fit Best", "Stretch", "Fit Width", "Fit Height",
                  "Cover/Crop"],
                 "fitbest")
    # RESOLUTION: a TOGGLE (JP request) — off = Unscaled (fit TOP bypassed,
    # source size preserved), on = Scaled (reveals the SCALE dropdown; the
    # factor is applied by the CONTROLLER against the movie's real
    # dimensions after load, even-dimension clamped). The toggle ALSO
    # rewires the fit path LIVE via the extension's Setfitpath().
    if "scaled_t" in widgets:
        setp(widgets["scaled_t"], "Widgetlabel", "SCALING")
        setp(widgets["scaled_t"], "Buttonofflabel", "OFF")
        setp(widgets["scaled_t"], "Buttononlabel", "ON")
        setp(widgets["scaled_t"], "Value0", 0)
    if "scale_dd" in widgets:
        # JP: the SCALE menu MIRRORS the fit TOP's Output Resolution menu
        # (eighth/quarter/half/two times/four times/eight times). Tokens
        # and labels come from the LIVE fit TOP — never hardcoded (the
        # verified-tokens rule). 'custom' is ours (the W/H fields) and
        # maps to the fit TOP's Custom Resolution via Setfitparams.
        names, labels = [], []
        fitop = vcon.op("fit")
        if fitop is None:
            say("  !! no fit TOP in vcon — SCALE menu needs build_network "
                "first")
        else:
            try:
                names = [str(n) for n in
                         fitop.par.outputresolution.menuNames]
                labels = [str(l) for l in
                         fitop.par.outputresolution.menuLabels]
            except Exception as exc:
                say(f"  (fit TOP menu read: {exc})")
        # JP (2026-09-14): the SCALE menu holds EXACTLY the six scale
        # entries + Custom. The fit TOP's live menu carries more
        # (useinput/fit/limit/parpanel/...) which are NOT scales. Match
        # the six by ALIAS SETS against the live menu's tokens AND
        # labels (JP's build shows tokens eighth/quarter/half/2x/4x/8x
        # with labels Eighth/Quarter/Half/Two Times/Four Times/Eight
        # Times); anything unmatched is left OUT.
        _SCALE_ALIASES = [
            (("eighth",), ("Eighth",)),
            (("quarter",), ("Quarter",)),
            (("half",), ("Half",)),
            (("2x", "twotimes", "2X"), ("Two Times", "2x")),
            (("4x", "fourtimes", "4X"), ("Four Times", "4x")),
            (("8x", "eighttimes", "8X"), ("Eight Times", "8x")),
        ]
        keep = []
        for token_al, label_al in _SCALE_ALIASES:
            hit = None
            for tok in token_al:
                if tok in names:
                    hit = names.index(tok)
                    break
            if hit is None:
                for lab in label_al:
                    if lab in labels:
                        hit = labels.index(lab)
                        break
            if hit is not None:
                keep.append((names[hit], labels[hit]))
        if len(keep) < 6:
            say(f"  !! SCALE mirror incomplete: found {len(keep)}/6 "
                f"scale entries in live fit TOP menu {names}")
        else:
            say(f"  fit TOP scale entries mirrored: {[n for n, _ in keep]}")
        menu_names = [n for n, _ in keep] + ["custom"]
        menu_labels = [l for _, l in keep] + ["Custom"]
        set_menu(widgets["scale_dd"], menu_names, menu_labels,
                menu_names[0] if menu_names else "custom")
    # W/H fields: defaults + hidden (only CUSTOM reveals them)
    for name, val in (("resw_f", "1920"), ("resh_f", "1080")):
        if name in widgets:
            setp(widgets[name], "Value0", val)
            outer = panelcomp.op(name)
            if outer is not None:
                try:
                    outer.par.display = 0
                except Exception as exc:
                    say(f"  (display {name}: {exc})")
    # SCALE, FIT, and the W/H fields hidden while Unscaled — scaling
    # OFF means nothing to configure (fit TOP bypassed), so all vanish
    # (_update_res_fields toggles them with the SCALED switch).
    for name in ("scale_dd", "fit_dd"):
        outer = panelcomp.op(name)
        if outer is not None:
            try:
                outer.par.display = 0
            except Exception as exc:
                say(f"  (display {name}: {exc})")

    # ---- buttons -----------------------------------------------------------
    # ---- per-widget config blocks guard on `in widgets`, so a removed
    # widget silently skips its wiring. The queue is KEEP-ALWAYS but its
    # guards stay for safety on pre-v4 captures.

    say("wiring buttons")
    for name, fn in [("start_b", "Start"), ("pause_b", "PauseResume"),
                     ("stop_b", "Stop")]:
        if name not in widgets:
            continue
        cmd = f"op.vcon.op('panel_callbacks').module.{fn}()"
        if setp(widgets[name], _BUTTON_SCRIPT_PAR, cmd):
            say(f"  {name}: script via '{_BUTTON_SCRIPT_PAR}' -> {fn}")

    # ---- binds + preview hooks --------------------------------------------
    say("binding progress + status")
    if "status_l" in widgets:
        try:
            # Widgetlabel is the STRING par (evidence: the stale path JP
            # saw rendered in output_l lived there; the par NAMED 'Label'
            # is an OP-reference to the widget's inner label child).
            # status_l is a REMOVABLE widget (JP 2026-09-14): absent from
            # the capture, this block simply skips.
            widgets["status_l"].par.Widgetlabel.expr = "op.vcon.par.Status"
            say("  status label bound to Status par (Widgetlabel expr)")
        except Exception as exc:
            say(f"  (status bind: {exc})")

    say("wiring live output-name preview")
    preview = "op.vcon.op('panel_callbacks').module.PreviewOutput()"
    for name in ("destination",):
        if name in widgets:
            if setp(widgets[name], "Onvaluechangescript0", preview):
                say(f"  {name}: preview wired")
    # QUALITY dropdown: every selection sets MvO's quality par LIVE
    # (Setquality promoted hook — same pattern as Setfitpath).
    if "quality_dd" in widgets:
        setp(widgets["quality_dd"], "Onvaluechangescript0",
             "op.vcon.op('panel_callbacks').module.OnQualityChanged()")
        say("  quality_dd: live MvO sync wired")
    # FPS field -> MvO fps par LIVE (JP 2026-09-14: the field both READS
    # the par — seeded from it at build end — and CHANGES it, the same
    # live-editor pattern as the QUALITY slider)
    if "fps_f" in widgets:
        setp(widgets["fps_f"], "Onvaluechangescript0",
             "op.vcon.op('panel_callbacks').module.OnFpsChanged()")
        say("  fps_f: live MvO fps sync wired")
    # FPS MODE toggle (JP's hand-added fps_t, capture-recreated): OFF =
    # SOURCE (field disabled, displays the loaded file's rate, MvO
    # follows it, jobs encode at each file's own rate); ON = CUSTOM
    # (field enabled, two-way with MvO's fps par). Wired ONLY when the
    # capture recreated the toggle — absent toggle = legacy behavior.
    if "fps_t" in widgets:
        setp(widgets["fps_t"], "Onvaluechangescript0",
             "op.vcon.op('panel_callbacks').module.OnFpsModeChanged()")
        say("  fps_t: FPS mode hook wired (off=source, on=custom)")
    # CODEC: repopulates subtype/format menus, previews, AND applies the
    # codec to MvO LIVE (JP: dropdown changes must show in MvO now).
    # The combined hook chain fires: UpdateSubtypes re-filters menus,
    # OnSelectionChanged pushes the choice into MvO via Setparams().
    selchange = ("op.vcon.op('panel_callbacks').module."
                 "OnSelectionChanged()")
    if "codec_dd" in widgets:
        setp(widgets["codec_dd"], "Onvaluechangescript0",
             "op.vcon.op('panel_callbacks').module.UpdateSubtypes(); "
             + selchange)
        say("  codec_dd: menus + live MvO sync wired")
    # SUBTYPE: re-filters the FORMAT menu per subtype (ProRes 422 vs
    # 4444 sets differ — JP: format options must follow the subtype)
    # and applies the subtype live.
    if "subtype_dd" in widgets:
        setp(widgets["subtype_dd"], "Onvaluechangescript0",
             "op.vcon.op('panel_callbacks').module.UpdateSubtypes(); "
             + selchange)
        say("  subtype_dd: format filter + live MvO sync wired")
    # FORMAT: previously wired to NOTHING — the live-apply gap JP found
    # (MvO's parameters didn't move on format change).
    if "format_dd" in widgets:
        setp(widgets["format_dd"], "Onvaluechangescript0", selchange)
        say("  format_dd: live MvO sync wired")
    # SCALED toggle: rewire fit path LIVE + toggle SCALE/FIT/W-H visibility
    if "scaled_t" in widgets:
        setp(widgets["scaled_t"], "Onvaluechangescript0",
             "op.vcon.op('panel_callbacks').module._update_res_fields()")
        say("  scaled_t: live fit rewire wired")
    # SCALE menu choice drives W/H visibility (Custom reveals them)
    # AND pushes the token into the fit TOP's Output Resolution LIVE
    if "scale_dd" in widgets:
        setp(widgets["scale_dd"], "Onvaluechangescript0",
             "op.vcon.op('panel_callbacks').module._update_res_fields(); "
             "op.vcon.op('panel_callbacks').module.OnFitChanged()")
        say("  scale_dd: visibility + live fit push wired")
    # FIT dropdown -> fit TOP's Fit parameter, LIVE
    if "fit_dd" in widgets:
        setp(widgets["fit_dd"], "Onvaluechangescript0",
             "op.vcon.op('panel_callbacks').module.OnFitChanged()")
        say("  fit_dd: live fit push wired")
    # W/H fields -> fit TOP Custom Resolution, LIVE (custom scale only)
    for _wname in ("resw_f", "resh_f"):
        if _wname in widgets:
            setp(widgets[_wname], "Onvaluechangescript0",
                 "op.vcon.op('panel_callbacks').module.OnFitChanged()")
            say(f"  {_wname}: live fit push wired")
    if "destination" in widgets:
        setp(widgets["destination"], "Valueparexec",
             "op.vcon.op('panel_callbacks').module.NormalizeDestination()")

    # ---- persistent settings: append PersistSettings() to every
    # persistent widget's change hook so runtime selections are saved
    # to panel_settings.json on every change (survives TD quit/relaunch).
    _PERSIST_HOOK = ("; op.vcon.op('panel_callbacks').module."
                     "PersistSettings()")
    for _pname in ("codec_dd", "subtype_dd", "format_dd", "quality_dd",
                   "container_dd", "audio_dd",
                   "fps_f", "fps_t", "scaled_t", "scale_dd", "fit_dd",
                   "resw_f", "resh_f", "destination"):
        if _pname in widgets:
            try:
                cur = str(widgets[_pname].par.Onvaluechangescript0.eval()
                          or "")
                if "PersistSettings" not in cur:
                    widgets[_pname].par.Onvaluechangescript0.val = (
                        cur + _PERSIST_HOOK)
            except Exception:
                pass
    say("  persistent settings hooks wired (12 widgets)")

    # ---- queue lister points at queue_table --------------------------------
    # LIVE-VERIFIED (probe 9): source par is INPUTTABLEDAT (style=DAT).
    # ORDER IS CRITICAL: set Refreshoninputchange=off BEFORE linking —
    # the link's internal switch produces one transient empty cook, and
    # the change-hook called Refresh on it -> 'Blank header in col 0'
    # (live traceback, twice). Config first, link LAST, then ONE
    # explicit Refresh pulse on the settled table.
    say("wiring batch queue lister")
    q = panelcomp.op("queue")
    if q is not None:
        try:
            q.par.Refreshoninputchange = "off"
        except Exception:
            pass
        try:
            q.par.Inputtablehasheaders = True
        except Exception:
            pass
        try:
            q.par.Savecolresizes = True
        except Exception as exc:
            say(f"  (Savecolresizes: {exc})")
        if _link_op(q, "Inputtabledat", qd):
            say("  lister Inputtabledat -> queue_display (file, status only)")
        try:
            q.par.Refresh.pulse()      # one clean refresh, settled state
        except Exception:
            pass

    # ---- drag/drop: files/folders straight into the queue (MODERN system) --
    # DOCS-VERIFIED (Drag-and-Drop page): the dropscript par takes a DAT
    # PATH (inline python never worked), and the MODERN panel system is
    # Drag/Drop Callbacks: On Dropping Into = Use Drag/Drop Callbacks, a
    # callbacks DAT with onHoverStartGetAccept (MUST return True or the
    # drop is silently rejected — the "drop did nothing" cause) and
    # onDropGetResults(comp, info). dragItems arrive as tdu.FileInfo-like
    # items with .path for file drops.
    say("wiring drag/drop callbacks (files/folders -> queue)")
    # PAR NAMES (TDParameterHelp, containerCOMP): the mode par is 'drop'
    # (Menu — values checked against the LIVE menu before writing), the
    # callbacks DAT par is 'dragdropcallbacks' (DAT) — my earlier
    # 'dropcallback' did not exist (silently missed).
    drop_menu = []
    try:
        drop_menu = list(panelcomp.par.drop.menuNames or [])
    except Exception:
        pass
    if drop_menu:
        say(f"  drop menu: {drop_menu}")
        # pick the callbacks-style entry by substring, not a guessed token
        target = next((m for m in drop_menu
                       if "callback" in m.lower()), None)
        if target is None:
            target = next((m for m in drop_menu
                           if "drop" in m.lower() and "allow" in m.lower()),
                          None)
        if target is not None:
            panelcomp.par.drop = target
            say(f"  drop mode -> {target!r}")
        else:
            say(f"  !! no callbacks entry in drop menu {drop_menu}")
    else:
        say("  (drop menu unreadable — leaving default)")
    if _link_op(panelcomp, "dragdropcallbacks", dnd_cb):
        say("  dragdropcallbacks DAT linked")
    # builtindrop OFF: our callbacks are the only drop handler
    try:
        panelcomp.par.builtindrop = "off"
    except Exception:
        pass

    # ---- the LISTER as its own drop target (JP: drop onto the queue) -----
    q_ = widgets.get("queue")
    if q_ is not None:
        try:
            qdrop_menu = list(q_.par.drop.menuNames or [])
        except Exception:
            qdrop_menu = []
        if qdrop_menu:
            inherit = next((m for m in qdrop_menu
                            if "inherit" in m.lower() or "parent" in m.lower()),
                           None)
            if inherit is not None:
                q_.par.drop = inherit
                say(f"  lister drop mode -> {inherit!r} (inherit panel)")
        if _link_op(q_, "dragdropcallbacks", dnd_cb):
            say("  lister dragdropcallbacks linked (drops -> queue)")
        try:
            # row highlight while a file hovers (docs: Drophighlight)
            q_.par.Drophighlight = "Row"
        except Exception:
            pass

    # ---- lister ROW-CLICK forwarder (JP 2026-09-14) --------------------
    # The listerConfig callbacks DAT ships with a commented-out
    # onSelectRow template — its OWN select handling must stay intact,
    # only OUR forwarder appends. Builder-OWNED text (code, like menus)
    # — the bake no longer restores the callbacks DAT (the capture keeps
    # owning the column tuning in the OTHER config DATs).
    say("injecting onSelectRow forwarder into listerConfig callbacks")
    if q is not None:
        # MASTER GATE (live-discovered 2026-09-14): the lister's
        # Advancedcallbacks toggle is OFF by stock default — when off,
        # the lister NEVER calls its Callbackdat (onSelectRow included)
        # and every custom row callback silently does nothing. Turn it
        # ON here, every build (builder-owned wiring, capture can't
        # turn it off: Advancedcallbacks isn't in the builder-owned
        # skip list, but we re-assert after the bake too for safety).
        try:
            q.par.Advancedcallbacks.val = True
            say("  lister Advancedcallbacks ON (custom callbacks gate)")
        except Exception as exc:
            say(f"  !! Advancedcallbacks: {exc} — row clicks will not "
                f"fire onSelectRow; the onFrame poll still detects them")
        try:
            cbdat = q.par.Configcomp.eval().op("callbacks")
            txt = cbdat.text or ""
            fwd = (
                "\n\n\n# --- vCon queue row-click inspector (builder-injected) ---\n"
                "def onSelectRow(info):\n"
                "    op.vcon.op('panel_callbacks').module."
                "OnQueueRowSelected(info)\n")
            marker = "vCon queue row-click inspector"
            if marker in txt:
                say("  forwarder already present")
            else:
                cbdat.text = txt + fwd
                say("  onSelectRow -> OnQueueRowSelected wired")
        except Exception as exc:
            say(f"  !! row-click forwarder: {exc}")

    # ---- per-row progress bar BEHIND the file name (JP) ------------------
    # colDefaults vocabulary (probe 11b) + LIVE colDefine format (probe 12:
    # 19 rows per column, key rows: column/columnLabel/sourceData/width/
    # stretch/topPath). We REPLACE the auto-defined columns with an
    # explicit colDefine: '#' narrow (30), 'file' wide (stretch), 'status'
    # fixed — NO progress column (the bar TOPs read queue_table's 4th
    # column directly; the lister doesn't display it).
    say("lister columns: auto-define over queue_display (file, status)")
    # Auto-define stays ON: it generates columns from the input table
    # (queue_display has file + status — exactly what JP wants). The
    # colDefine approach requires matching column names AND auto-define
    # off — turning it off broke the display (colDefine columns didn't
    # match queue_display's). Column WIDTHS under auto-define are
    # content-sized; JP can drag the column divider to widen status,
    # and the capture will record that if Savecolresizes is on.

    # ---- per-row progress bars: PARKED (probe 11b/12 — the colDefine
    # topPath per-row mechanism was never proven). The row-bars code that
    # lived here errored on every build since inception (constant TOPs
    # have no .resx par attribute on this build) and the TOPs it did
    # create were invisible (never referenced by any colDefine). When
    # row bars are wanted: wire a topPath per-row in the listerConfig
    # colDefine first, THEN create the bar TOPs it references.

    # ---- panel Execute DAT: batch tick --------------------------------------
    # VERIFIED pattern from build_network.py's controller tick: the Execute
    # DAT requires the COMPLETE function set (onFrameStart, onFrameEnd,
    # onCreate, onStart, onExit) — a missing onFrameEnd raised 'Cannot find
    # function named: onFrameEnd' live. Callback goes in the DAT's text;
    # pars are framestart/frameend/active.
    say("creating panel Execute DAT (batch tick)")
    ex = vcon.create(_EXECUTEDAT(), "panel_tick")
    ex.nodeX = 300
    ex.nodeY = 30
    ex.text = (
        "# Panel tick: feed the batch queue when the encoder is idle.\n"
        "\n"
        "\n"
        "def onFrameStart(frame):\n"
        "    try:\n"
        "        op.vcon.op('panel_callbacks').module.onFrame()\n"
        "    except Exception as exc:\n"
        "        # never silent: a swallowed tick error hid a dead\n"
        "        # inspector for several rounds. Rate-limited to once\n"
        "        # per ~5s so a persistent fault can't flood.\n"
        "        global _last_err\n"
        "        try:\n"
        "            _last_err\n"
        "        except NameError:\n"
        "            _last_err = 0\n"
        "        if absTime.frame - _last_err > 300:\n"
        "            _last_err = absTime.frame\n"
        "            debug(f'vcon panel tick error: {exc}')\n"
        "\n"
        "\n"
        "def onFrameEnd(frame):\n"
        "    pass\n"
        "\n"
        "\n"
        "def onCreate():\n"
        "    pass\n"
        "\n"
        "\n"
        "def onStart():\n"
        "    pass\n"
        "\n"
        "\n"
        "def onExit():\n"
        "    pass\n"
    )
    for p in ("framestart", "frameend", "active"):
        try:
            getattr(ex.par, p).val = 1
        except Exception as exc:
            say(f"  (exec {p}: {exc})")

    say("=" * 52)
    say(f"panel built: {panelcomp.path}")
    # Fire the per-codec hook ONCE so every dropdown starts valid for the
    # seeded codec (NotchLC): SUBTYPE greyed, FORMAT rgb+rgba (rgb on),
    # QUALITY slider live. No 'none' anywhere from the very first frame.
    try:
        mod.UpdateSubtypes()
        say("initial codec state applied (NotchLC defaults)")
    except Exception as exc:
        say(f"  (initial UpdateSubtypes: {exc})")
    say("START with a FOLDER in SOURCE enqueues its movies; the panel")
    say("tick feeds them to the encoder one at a time.")
    say("=" * 52)


build()

# ---- bake JP's captured hand-tuning (capture-first workflow) ----------
# If toe/panel_layout_captured.py exists (capture_panel.py v3), apply
# it AFTER the build: the capture — JP's hand-tuned canonical state —
# wins over the defaults above. A stale pre-v3 dump fails the compile
# guard inside with a clear "re-capture with v3" message.
_CAP_DUMP = f"{REPO}/toe/panel_layout_captured.py"
if os.path.isfile(_CAP_DUMP):
    exec(open(f"{REPO}/toe/apply_panel_capture.py",
              encoding='utf-8').read())
else:
    print("[panel] no capture file — defaults only "
          "(run capture_panel.py after hand-tuning)")

# Seed the FPS field per MODE (JP: SOURCE mode displays the source's
# rate; CUSTOM mode the MvO par). Runs AFTER the bake so the read wins
# over any captured field text. Both paths (capture / no capture) land
# here. The write fires OnFpsChanged -> Setfps with the same value —
# idempotent, no loop.
try:
    op.vcon.op('panel_callbacks').module.SyncFpsField()
    print("[panel] fps field seeded per mode")
except Exception as exc:
    print(f"[panel] (fps seed: {exc})")
# Re-run the OUTPUT preview AFTER the bake: the capture's output_l
# Widgetlabel is a STALE runtime value (a path from whenever JP last
# captured — the bake faithfully restores it over the seed). The queue
# is always empty at build time (queue_table is recreated fresh), so
# this recomputes the honest '(queue is empty — add files)' message.
# (This is why the empty-queue text 'stopped working a while ago' —
# it broke the day the capture bake landed.)
try:
    op.vcon.op('panel_callbacks').module.PreviewOutput()
    print("[panel] output preview re-seeded (queue state)")
except Exception as exc:
    print(f"[panel] (preview re-seed: {exc})")
# If the FPS MODE toggle is present (capture-recreated), fire its hook
# once so the field's enable state + display match the mode from the
# captured Value0 (grey-out is a live par write, not captured state).
try:
    op.vcon.op('panel').op('fps_t') is not None
    op.vcon.op('panel_callbacks').module.OnFpsModeChanged()
    print("[panel] fps mode applied (grey-out + display)")
except Exception as exc:
    print(f"[panel] (fps mode apply: {exc})")
# Fire OnContainerChanged once so the codec menu is filtered to the
# current container from the start.
try:
    op.vcon.op('panel_callbacks').module.OnContainerChanged()
    print("[panel] container filter applied")
except Exception as exc:
    print(f"[panel] (container filter: {exc})")

# ---- restore persistent runtime settings (survives TD quit/relaunch) -
# Runs AFTER the bake + the seeds so the user's last selections win
# over builder defaults and captured state. The capture owns LAYOUT;
# this owns RUNTIME SELECTIONS (destination, codec, fps mode, scale,
# quality, format, etc.). Written on every widget change via
# _save_settings() in the callbacks module.
try:
    op.vcon.op('panel_callbacks').module._load_settings()
    print("[panel] persistent settings restored")
except Exception as exc:
    print(f"[panel] (settings restore: {exc})")
