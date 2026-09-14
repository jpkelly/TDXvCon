"""build_network.py — constructs transcoder.toe's network inside TouchDesigner.

RUN THIS ONCE inside TouchDesigner's TEXTPORT (Window > Textport and DATs):

    exec(open('/Users/jp/Documents/GitHub/vCon/toe/build_network.py', encoding='utf-8').read())

IMPORTANT — do NOT `import` this file as a disk module: TouchDesigner does
not inject its builtins (op, project, op-type constants like moviefileinTOP)
into imported .py modules — that's the NameError: op you hit. exec-ing the
source runs it in the textport's namespace where all TD names exist.
ALWAYS pass encoding='utf-8' — TD's Python defaults to ASCII for open()
and this file contains UTF-8 (em-dashes in prose).
The script auto-runs build() when __name__ == '__main__'; if your textport's
__name__ differs, just type `build()` on the next line.

The script saves the project as src/vcon/data/transcoder.toe automatically.

Resulting network (/project1/vcon):

    vcon (Base COMP)
    ├── moviein   (Movie File In TOP)
    ├── movieout  (Movie File Out TOP ← moviein)
    ├── info      (Info CHOP ← moviein)         'length' channel = frame count
    ├── tcpip     (TCPIP DAT, server mode :7999)
    ├── callbacks (Text DAT, TCPIP callbacks)
    └── vcon_controller (Text DAT — module, holds VconExt)

    execute1 (Perform Execute DAT at /project1 level) → per-frame tick
"""

import os

# Repo location. Do NOT rely on __file__: under exec() in the textport it is
# inherited from TD's own namespace and points into the app bundle
# (…/TouchDesigner.app/Contents/Resources/tfs/…), which is not our script.
REPO_TOE_DIR = "/Users/jp/Documents/GitHub/vCon/toe"


def _resolve_controller_src():
    """Find vcon_controller.py, checking the known repo path first."""
    candidates = [os.path.join(REPO_TOE_DIR, "vcon_controller.py")]
    try:
        cand_file = __file__  # noqa: F821 — may be TD's, hence the filter
        cand_dir = os.path.dirname(os.path.abspath(cand_file))
        if "TouchDesigner.app" not in cand_dir and "Resources" not in cand_dir:
            candidates.append(os.path.join(cand_dir, "vcon_controller.py"))
    except NameError:
        pass
    for c in candidates:
        if os.path.isfile(c):
            return c
    raise RuntimeError(
        "vcon_controller.py not found. Checked:\n  "
        + "\n  ".join(candidates)
        + f"\nSet REPO_TOE_DIR at the top of this file if the repo moved."
    )


CONTROLLER_SRC = _resolve_controller_src()


def _read_version():
    """Version for the toe's custom parameter.

    Read from the controller source so the toe, the package and the reported
    controller_version all agree. Falls back rather than failing: a version
    label is not worth aborting a build over.
    """
    try:
        with open(CONTROLLER_SRC, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("CONTROLLER_VERSION"):
                    return line.split("=", 1)[1].strip().strip('"\'')
    except Exception as exc:
        debug(f"could not read version: {exc}")
    return "unknown"


BUILD_VERSION = _read_version()


def say(msg):
    """Print to the textport (single line — no duplicate debug echo)."""
    print(f"[vcon] {msg}")


#: Non-fatal problems collected during the build (menu mismatches, wiring
#: failures). Reported together at the end so one run reveals everything.
ISSUES = []


def connect_ops(src, dst, index=0, label=None):
    """Wire src -> dst, trying every TD API variant that exists across builds.

    The connector API has differed between TouchDesigner versions, so rather
    than guess we try each known strategy and report which one worked. If
    none work the build continues and the failure is listed at the end.
    """
    label = label or f"{src.name} -> {dst.name}"

    def _c1():
        dst.inputConnectors[index].connect(src)

    def _c2():
        dst.inputConnectors[index].connect(src.outputConnectors[0])

    def _c3():
        src.outputConnectors[0].connect(dst)

    attempts = (
        ("dst.inputConnectors[i].connect(src)", _c1),
        ("dst.inputConnectors[i].connect(src.outputConnectors[0])", _c2),
        ("src.outputConnectors[0].connect(dst)", _c3),
    )
    for name, fn in attempts:
        try:
            fn()
            say(f"  wired {label} via {name}")
            return name
        except Exception as exc:
            last = exc
    ISSUES.append({
        "kind": "wiring", "par": label, "owner": getattr(dst, "path", "?"),
        "tried": [n for n, _ in attempts], "valid": [str(last)],
    })
    say(f"  !! could not wire {label}: {last}")
    return None


def set_op_par(holder, name, target):
    """Set an OP-type parameter (e.g. Info CHOP's 'op'), trying object then
    path string — some builds want one, some the other."""
    for value in (target, target.path):
        try:
            setattr(holder.par, name, value)
            return True
        except Exception:
            continue
    ISSUES.append({
        "kind": "param", "par": f"{holder.name}.{name}",
        "owner": holder.path, "tried": ["op object", "path string"],
        "valid": ["neither accepted"],
    })
    say(f"  !! could not set {holder.name}.{name}")
    return False


def menu_set(par, candidates, label=None):
    """Set a menu parameter using the first candidate present in its menu.

    Soft-fails: on mismatch it records the REAL menu names and continues, so
    a single build run reports every menu discrepancy instead of stopping at
    the first one. Verified names can then be filled in.
    """
    names = list(par.menuNames or [])
    for cand in candidates:
        if cand in names:
            par.val = cand
            say(f"  {label or par.name} = {cand}")
            return cand
    ISSUES.append({
        "kind": "menu", "par": label or par.name,
        "owner": par.owner.path if getattr(par, "owner", None) else "?",
        "tried": list(candidates), "valid": names,
    })
    say(f"  !! menu mismatch: {label or par.name} — tried {candidates}, "
        f"valid = {names}")
    return None

def safe_set(par_collection, name, value):
    """Set an OPTIONAL parameter if it exists; never raise.

    Used for cosmetic/knob parameters whose absence must not break the
    build (e.g. 'color' exists on Container COMPs but not Base COMPs).
    Parameters the encoder actually depends on use the strict helpers
    above so a mismatch fails loudly.
    """
    try:
        setattr(par_collection, name, value)
    except (AttributeError, TypeError):
        pass


def find_type(*names):
    """First TD op-type that exists.

    Op-type constants (baseCOMP, moviefileinTOP, ...) are NOT textport
    globals — they are attributes of the td module, which is importable in
    every TouchDesigner Python context. Check td first, then globals as a
    fallback for DAT-script contexts.
    """
    try:
        import td as _td
    except ImportError:
        _td = None
    for n in names:
        if _td is not None and hasattr(_td, n):
            return getattr(_td, n)
        if n in globals():
            return globals()[n]
    raise RuntimeError(
        f"none of {names} available via the td module or globals — "
        f"run this file via exec() in the TouchDesigner textport"
    )


def build():
    """Build the entire network. Idempotent: destroys /project1/vcon first."""
    ISSUES.clear()
    say("=" * 56)
    say("building vCon transcoder network")
    say("=" * 56)

    # ---- clean slate --------------------------------------------------
    # Where the component is created. This is the ONLY place a location is
    # assumed; set TOE_PARENT_PATH / TOE_COMP_NAME before running to build it
    # elsewhere. Everything downstream derives from `vcon.path`, so the
    # component can also be moved after building.
    parent_path = globals().get("TOE_PARENT_PATH", "/project1")
    comp_name = globals().get("TOE_COMP_NAME", "vcon")
    target_path = f"{parent_path.rstrip('/')}/{comp_name}"

    if op(target_path) is not None:
        say(f"removing existing {target_path}")
        op(target_path).destroy()
    # Never leave two controllers alive: they would both bind TCP 7999.
    default_path = "/project1/vcon"
    if target_path != default_path and op(default_path) is not None:
        say(f"removing stale build at {default_path} (would clash on the port)")
        op(default_path).destroy()
    if op("/project1/execute1") is not None:
        op("/project1/execute1").destroy()

    proj = op(parent_path)
    if proj is None:
        raise RuntimeError(
            f"TOE_PARENT_PATH does not exist: {parent_path!r} — "
            f"create that component first, or unset TOE_PARENT_PATH"
        )

    # ---- container ----------------------------------------------------
    say(f"creating container {target_path}")
    # Base COMP has no h/w/color params (those are Container COMP features);
    # sizing is cosmetic, so it is applied defensively.
    vcon = proj.create(find_type("baseCOMP"), comp_name)
    safe_set(vcon.par, "color", (0.12, 0.35, 0.55))
    safe_set(vcon.par, "h", 400)
    safe_set(vcon.par, "w", 600)
    say(f"  component path: {vcon.path}")
    safe_set(vcon.par, "color", (0.12, 0.35, 0.55))
    safe_set(vcon.par, "h", 400)
    safe_set(vcon.par, "w", 600)

    # ---- moviein ------------------------------------------------------
    say("creating moviein (Movie File In TOP)")
    moviein = vcon.create(find_type("moviefileinTOP"), "moviein")
    moviein.nodeX = -300
    moviein.nodeY = 0
    # Menu literals resolved against the LIVE menu names; 'specify' is TD's
    # internal name for the "Specify Index" menu entry (verified live:
    # playmode menu = ['locked', 'specify', 'sequential', 'timecodeop']).
    menu_set(moviein.par.playmode, ["specify", "specifyindex", "index"],
             "moviein.playmode")
    menu_set(moviein.par.indexunit, ["index", "idx", "frames"],
             "moviein.indexunit")
    moviein.par.index = 0
    safe_set(moviein.par, "prereadframes", 2)    # cap VRAM pre-read buffer to 2 frames
    safe_set(moviein.par, "alwaysloadinitial", 1)  # never encode black frame 0

    # ---- info chop (stream length) ------------------------------------
    say("creating info CHOP (stream length source)")
    info = vcon.create(find_type("infoCHOP"), "info")
    info.nodeX = -300
    info.nodeY = -120
    # An Info CHOP references its target via the 'op' parameter — no input
    # connector exists on this operator family. (Verified live: attempting
    # inputConnectors/inputs wiring raises on this build.)
    set_op_par(info, "op", moviein)

    # ---- movieout ------------------------------------------------------
    say("creating movieout (Movie File Out TOP, NotchLC)")
    movieout = vcon.create(find_type("moviefileoutTOP"), "movieout")
    movieout.nodeX = 0
    movieout.nodeY = 0
    connect_ops(moviein, movieout, label="moviein -> movieout")
    menu_set(movieout.par.videocodec, ["NotchLC", "notchlc"], "movieout.videocodec")
    menu_set(movieout.par.moviecontainer, [".mov", "mov"], "movieout.container")
    movieout.par.pause = 1              # addframe requires pause ON
    safe_set(movieout.par, "stallforopen", 1)   # ensure frame 0 is recorded
    # quality menu is set per job by the controller

    # ---- tcp server ----------------------------------------------------
    say("creating tcpip DAT (server :7999)")
    tcpip = vcon.create(find_type("tcpipDAT"), "tcpip")
    tcpip.nodeX = 150
    tcpip.nodeY = -120
    menu_set(tcpip.par.mode, ["server", "servertcp"], "tcpip.mode")
    tcpip.par.port = 7999
    # Active ENABLES the connection — without it the DAT never binds the
    # port (docs: Connect page, "Active - This check box enables the
    # connection"). Observed live as ConnectionRefused on 7999.
    tcpip.par.active = 1
    safe_set(tcpip.par, "maxclients", 1)    # single front-end connection
    safe_set(tcpip.par, "shared", 0)        # exclusive use of the port

    # ---- callbacks DAT for the TCPIP server ---------------------------
    callbacks = vcon.create(find_type("textDAT"), "callbacks")
    callbacks.nodeX = 300
    callbacks.nodeY = -120
    callbacks.text = TCP_CALLBACKS_SRC
    try:
        tcpip.par.callbacks = callbacks.path  # wire callbacks DAT
    except AttributeError:
        debug(f"no callbacks par on {tcpip.path}")

    # ---- controller module ---------------------------------------------
    # The DAT is LINKED to the file on disk rather than holding a copy.
    # Per the Text DAT docs, `syncfile` means "the file is monitored so that
    # any changes made to the file will update the DAT, and any changes made
    # to the DAT will be written to the file right away" — so editing
    # toe/vcon_controller.py in the repo updates the running toe live, and
    # editing it in TouchDesigner writes back to the repo.
    say("creating controller DAT (linked to toe/vcon_controller.py)")
    controller = vcon.create(find_type("textDAT"), "vcon_controller")
    controller.nodeX = 150
    controller.nodeY = 150
    safe_set(controller.par, "language", "python")
    linked = False
    try:
        controller.par.file = CONTROLLER_SRC
        controller.par.syncfile = 1      # live two-way sync
        controller.par.loadonstart = 1   # reload from disk on project start
        linked = True
        say(f"  linked: {CONTROLLER_SRC}")
    except Exception as exc:
        # Fall back to embedding the text so the build still succeeds.
        say(f"  !! file link failed ({exc}); embedding text instead")
        with open(CONTROLLER_SRC, "r", encoding="utf-8") as f:
            controller.text = f.read()
    if not linked:
        safe_set(controller.par, "loadonstart", 1)

    # ---- per-frame tick (Execute DAT) ----------------------------------
    # The controller's state machine (loading -> encoding -> finishing) is
    # driven from here. This replaces an earlier run(delayFrames=1) scheme
    # that silently stopped firing and left jobs stuck with no error.
    say("creating Execute DAT (per-frame tick)")
    ex = vcon.create(find_type("executeDAT"), "tick")
    ex.nodeX = -150
    ex.nodeY = 150
    ex.text = EXECUTE_TICK_SRC
    safe_set(ex.par, "framestart", 1)   # run onFrame each frame
    safe_set(ex.par, "frameend", 1)
    safe_set(ex.par, "active", 1)
    # ---- attach the controller as a PROPER extension --------------------
    # Documented (docs.derivative.ca/Extensions): the Extension Object
    # parameter holds "a bit of Python code that must return a Python object",
    # most commonly a class instantiated with the Component: `ExampleExt(me)`.
    #
    # We construct VconExt(me) rather than fetching a module singleton. That
    # is the documented pattern, and it is what makes the component
    # EMBEDDABLE: a drop-in COMP at any path gets its OWN controller bound to
    # its own operators, and capitalization-promotion exposes the public API
    # to the surrounding network.
    #
    # The path must be ABSOLUTE in this code string — a relative
    # op('vcon_controller') inside extension code resolves against the wrong
    # scope and returns None. It is built from the component's actual path so
    # the same builder works wherever the COMP lives.
    say("attaching controller extension...")
    ext_ok = False
    ext_errors = []
    obj_code = f"op('{vcon.path}/vcon_controller').module.VconExt(me)"
    for slot in (0, 1, 2, 3):
        try:
            setattr(vcon.par, f"ext{slot}object", obj_code)
            setattr(vcon.par, f"ext{slot}name", "Vcon")
            say(f"  par.ext{slot}object = {obj_code!r}")
            say(f"  par.ext{slot}name = 'Vcon'")
            ext_ok = True
            break
        except Exception as exc:
            ext_errors.append(f"ext{slot}object: {exc}")

    # Have TD build the extension at startup too, and force a re-init now so
    # the row we just created takes effect in this session.
    safe_set(vcon.par, "initextonstart", 1)
    try:
        vcon.par.reinitextensions.pulse()
        say("  pulsed reinitextensions")
    except Exception:
        safe_set(vcon.par, "reinitextensions", 1)

    if not ext_ok:
        say("  !! could not create extension row:")
        for e in ext_errors:
            say(f"     {e}")

    # ---- custom "Settings" parameter page ------------------------------
    # NAMING RULE (docs: Custom Parameters): the first character must be
    # uppercase and every remaining character must be lowercase letters or
    # digits — "sequence parameters cannot end with digits" either. So
    # 'TcpPort' is ILLEGAL (two capitals); 'Tcpport' is fine. Getting this
    # wrong raises, which is why each parameter is added independently below:
    # one bad name must not blank out the whole page.
    #
    # Cleanup destroys EVERY existing custom page — not just "vCon" — so
    # pages from earlier layouts ("Settings") can never survive a rebuild
    # and stack up.
    say("resetting custom parameter pages")
    try:
        for existing_page in list(vcon.customPages):
            existing_page.destroy()
    except Exception as exc:
        debug(f"could not clear old custom pages: {exc}")

    # ---- ONE custom page: vCon -----------------------------------------
    # A single tab holds everything (JP directive: one vCon page, not
    # Settings + vCon). Order: the user-editable port first, then the
    # read-only diagnostics, then Status which the controller writes.
    try:
        ui_page = vcon.appendCustomPage("vCon")
    except Exception as exc:
        say(f"  !! could not create vCon page: {exc}")
        ISSUES.append({
            "kind": "param", "par": "vCon", "owner": vcon.path,
            "tried": ["appendCustomPage"], "valid": [str(exc)],
        })
        ui_page = None

    # Tcpport is the one EDITABLE parameter — two vCon components can
    # coexist in a project by using different ports.
    if ui_page is not None:
        try:
            port_par = ui_page.appendInt("Tcpport", label="TCP port")[0]
            port_par.default = 7999
            try:
                port_par.min = 1024
                port_par.max = 65535
                port_par.clampMin = True
                port_par.clampMax = True
            except Exception:
                pass
            port_par.val = 7999
        except Exception as exc:
            say(f"  !! could not add Tcpport: {exc}")
            ISSUES.append({
                "kind": "param", "par": "vCon/Tcpport", "owner": vcon.path,
                "tried": ["appendInt"], "valid": [str(exc)],
            })

    def add_readonly_str(par_name, label, value):
        """Add one read-only string parameter, independent of the others.

        appendStr returns a TUPLET (a list), not a single Par, so index [0].
        Each parameter is added in its own try/except and the value is both
        defaulted AND seeded — .default alone does not set the current value.
        """
        if ui_page is None:
            return
        try:
            par = ui_page.appendStr(par_name, label=label)[0]
        except Exception as exc:
            say(f"  !! parameter '{par_name}' rejected: {exc}")
            ISSUES.append({
                "kind": "param", "par": f"vCon/{par_name}",
                "owner": vcon.path, "tried": ["appendStr"], "valid": [str(exc)],
            })
            return
        par.default = value
        try:
            par.readOnly = True
        except Exception as exc:
            debug(f"{par_name}: could not set readOnly: {exc}")
        try:
            par.val = value
        except Exception as exc:
            debug(f"{par_name}: could not seed value: {exc}")

    add_readonly_str("Version", "vCon version", BUILD_VERSION)
    add_readonly_str("Controller", "Controller file",
                     CONTROLLER_SRC if linked else "(embedded)")
    add_readonly_str("Linked", "Linked to file", "yes" if linked else "no")
    # Progress: a 0..1 float a panel slider binds to DIRECTLY (normMin/Max
    # are 0..1). Single value — an earlier size=2 (frame, total) tuple
    # rendered as two numbers and confused everyone. The controller writes
    # it every ~10 frames and resets it on completion.
    try:
        prog = ui_page.appendFloat("Progress", label="Progress")[0]
        prog.default = 0.0
        prog.readOnly = True
        try:
            prog.normMin = 0.0
            prog.normMax = 1.0
        except Exception:
            pass
        prog.val = 0.0
    except Exception as exc:
        say(f"  !! could not add Progress: {exc}")
        ISSUES.append({
            "kind": "param", "par": "vCon/Progress", "owner": vcon.path,
            "tried": ["appendFloat"], "valid": [str(exc)],
        })
    # Status: the controller writes it at every state change (loading /
    # encoding N/M / errors / idle + last output). A label or Parameter CHOP
    # can bind it without any Python.
    add_readonly_str("Status", "Status", "idle")
    say("  vCon page parameters requested")

    # NOTE: there is deliberately NO quit-on-idle parameter. Whether this
    # process may terminate itself is answered by PROCESS PROVENANCE (the
    # front-end sets VCON_LAUNCHED=1 when it spawns TD; the controller arms
    # orphan cleanup from that). A user-facing toggle put the decision in
    # the wrong place, and a user-opened session must never be quit by us.

    # Verify the parameters actually EXIST and carry a value. Creating a page
    # is not the same as populating it: an earlier build produced a page whose
    # parameters were blank because a later one raised partway through and
    # skipped the seeding step.
    expected = {
        "Version": True, "Controller": True, "Linked": True,
        "Tcpport": False,          # int: 0 is a valid value, don't flag blank
        "Progress": False,         # float: 0.0 is a valid value
        "Status": True,
    }
    for name, needs_value in expected.items():
        if not hasattr(vcon.par, name):
            ISSUES.append({
                "kind": "param", "par": f"vCon/{name}", "owner": vcon.path,
                "tried": ["appendStr/appendInt", "hasattr"],
                "valid": ["parameter missing after appendCustomPage"],
            })
            say(f"  !! parameter '{name}' was NOT created")
            continue
        if not needs_value:
            continue
        try:
            val = vcon.par[name].eval()
            if val in (None, ""):
                say(f"  !! parameter '{name}' is EMPTY")
        except Exception as exc:
            say(f"  !! could not read '{name}': {exc}")

    # ---- global OP shortcut (nice-to-have) -----------------------------
    safe_set(vcon.par, "shortcut", "vcon")   # op.vcon resolves to this COMP

    # ---- verify ---------------------------------------------------------
    say("verifying...")
    mod_ok = False
    ext_live = False
    try:
        mod = op(f"{vcon.path}/vcon_controller").module
        mod_ok = mod.VconExt is not None
        say(f"  controller module loaded (VconExt present)")
    except Exception as e:
        say(f"  !! controller module failed: {e}")
        ISSUES.append({
            "kind": "module", "par": "vcon_controller.module",
            "owner": f"{vcon.path}/vcon_controller",
            "tried": ["module.VconExt"], "valid": [str(e)],
        })
    try:
        ctrl = vcon.ext.Vcon
        ext_live = ctrl is not None
        if ext_live:
            say(f"  ext.Vcon: live ({type(ctrl).__name__})")
            # Prove it is bound to THIS component, not some other one.
            try:
                same = ctrl.ownerComp.path == vcon.path
                say(f"  bound to this COMP: {same} ({ctrl.ownerComp.path})")
                # and that relative child resolution works
                _ = ctrl.moviein
                _ = ctrl.movieout
                say("  child operators resolve relatively: ok")
            except Exception as exc:
                say(f"  !! extension binding problem: {exc}")
        else:
            say("  ext.Vcon: returned None")
    except Exception as e:
        say(f"  ext.Vcon: not available ({e})")

    # ---- save -----------------------------------------------------------
    toe_dir = os.path.abspath(
        os.path.join(REPO_TOE_DIR, "..", "src", "vcon", "data")
    )
    if not os.path.isdir(toe_dir):
        os.makedirs(toe_dir)
    toe_path = os.path.join(toe_dir, "transcoder.toe")
    say(f"saving project → {toe_path}")
    try:
        project.save(toe_path)
    except Exception as e:
        say(f"WARNING: project.save failed ({e}) — save manually:")
        say(f"  File > Save As... → {toe_path}")
        toe_path = "(not saved)"

    say("=" * 56)
    say(f"network built.  toe: {toe_path}")
    say(f"vcon version: {BUILD_VERSION}")
    say(f"controller: "
        f"{'LINKED to ' + CONTROLLER_SRC if linked else 'EMBEDDED (no file link)'}")
    say(f"extension row set: {ext_ok}   ext.Vcon live: {ext_live}   "
        f"module: {mod_ok}")
    say(f"tcp port: 7999   operators: "
        f"{', '.join(c.name for c in vcon.children)}")
    if ISSUES:
        say("-" * 56)
        say(f"{len(ISSUES)} issue(s) found — details below:")
        for issue in ISSUES:
            say(f"  [{issue['kind']}] {issue['par']}: tried {issue['tried']}"
                f" → {issue['valid']}")
        say("Send these so the script can be corrected.")
    else:
        say("all parameters and connections applied cleanly.")
    say("-" * 56)
    say("MENU REFERENCE (for future codec registry entries):")
    for pname in ("videocodec", "videocodectype", "moviepixelformat",
                  "moviecontainer", "quality"):
        p = getattr(movieout.par, pname, None)
        if p is not None and hasattr(p, "menuNames"):
            say(f"  movieout.{pname} = {list(p.menuNames or [])}")
    say("=" * 56)


TCP_CALLBACKS_SRC = '''\
# TCPIP DAT callbacks.
#
# Documented signatures (docs.derivative.ca/TcpipDAT_Class):
#   onConnect(dat, peer)
#   onReceive(dat, rowIndex, message, bytes, peer)
#   onClose(dat, peer)
#   onDetach(dat, peer)
# Note the receive callback takes (rowIndex, message, bytes, peer) — there
# is no colIndex, and the message is the 3rd argument.
#
# Reaching the controller WITHOUT a hardcoded path: the docs state the `ext`
# member "exists on all Operators and will search up the network hierarchy
# for the named extension", so `parent().ext.Vcon` finds the enclosing
# component's extension wherever that component lives — including when this
# COMP is embedded inside someone else's project.


def _ctrl():
    ctrl = parent().ext.Vcon
    if ctrl is None:
        raise RuntimeError("vCon: no Vcon extension found on the parent COMP")
    return ctrl


def onConnect(dat, peer):
    try:
        _ctrl().onConnect()
    except Exception as e:
        debug(f"vcon onConnect failed: {e}")
    return 1  # accept


def onReceive(dat, rowIndex, message, bytes, peer):
    try:
        _ctrl().onReceive(message)
    except Exception as e:
        debug(f"vcon onReceive failed: {e}")


def onClose(dat, peer):
    pass


def onDetach(dat, peer):
    pass
'''

EXECUTE_TICK_SRC = '''\
# Execute DAT: drives the vCon controller's per-frame state machine.
#
# Using an Execute DAT (TouchDesigner's standard per-frame mechanism) rather
# than run(..., delayFrames=N) scheduling, which silently stopped firing.
#
# The controller is reached via the `ext` member's documented upward search,
# so no operator path is hardcoded and the COMP can live anywhere.


def _ctrl():
    ctrl = parent().ext.Vcon
    if ctrl is None:
        raise RuntimeError("vCon: no Vcon extension found on the parent COMP")
    return ctrl


def onFrameStart(frame):
    try:
        _ctrl().onFrame()
    except Exception as e:
        debug(f"vcon onFrame failed: {e}")


def onFrameEnd(frame):
    pass


def onCreate():
    pass


def onStart():
    pass


def onExit():
    pass
'''

if __name__ == "__main__":
    build()