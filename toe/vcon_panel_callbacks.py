"""vcon panel callbacks — the panel's logic, run inside TouchDesigner.

Loaded as a file-linked module DAT inside the vCon COMP. Widgets fire
into here via Offtoonscript0 (buttons) and Onvaluechangescript0 (fields).

LIVE-VERIFIED widget facts: config pars are on the INNER COMP (children
scan; op(name) self-matches the wrapper) and are First-uppercase: Value0
is the widget's value; Onvaluechangescript0 fires on any value change;
buttons fire Offtoonscript0 on press. The extension's busy property is
is_busy (lowercase) — the panel must NOT call a promoted-style Isbusy.
"""

import os
import sys
import time

#: Codec table — distilled from src/vcon/codec_meta.py (TD menu tokens).
#: KEEP IN STEP with codec_meta.py — regenerate via toe/gen_codec_table.py.
CODECS = {
    "notchlc": {
        "label": "NotchLC",
        "subtypes": [],
        "pixel_formats": ["rgb", "rgba"],
        "alpha_format": "rgba",
        "qualities": ["good", "very-good", "excellent", "optimal", "best"],
    },
    "hap": {
        "label": "Hap",
        "subtypes": ["hap", "hapq", "hapr", "haphdr"],
        "pixel_formats": ["rgb", "rgba"],
        # VERIFIED LIVE (codec_meta): haphdr offers rgbu/rgbs — NOT rgb/rgba
        # — and exposes NO alpha format. Per-subtype menus mirror TD.
        "pixel_formats_by_subtype": {
            "hap": ["rgb", "rgba"],
            "hapq": ["rgb", "rgba"],
            "hapr": ["rgb", "rgba"],
            "haphdr": ["rgbu", "rgbs"],
        },
        "alpha_format": "rgba",
        "alpha_format_by_subtype": {"haphdr": None},
        "qualities": [],
    },
    "cineform": {
        "label": "GoPro CineForm",
        "subtypes": [],
        "pixel_formats": ["rgba"],
        "alpha_format": "rgba",
        "qualities": [],
    },
    "prores": {
        "label": "Apple ProRes",
        "subtypes": ["prores422proxy", "prores422lt", "prores422",
                     "prores422hq", "prores4444", "prores4444xq"],
        "pixel_formats": [],
        "default_subtype": "prores4444",   # JP spec
        "qualities": [],
    },
    "h264": {"label": "H.264", "subtypes": [], "qualities": [],
              "pixel_formats": ["yuv420", "yuv444p8bit"], "alpha_format": None},
    "h265": {"label": "H.265", "subtypes": [], "qualities": [],
              "pixel_formats": ["yuv420", "yuv420p10bit", "yuv444p8bit",
                                "yuv444p10bit"],
              "alpha_format": None},
    "av1": {"label": "AV1", "subtypes": [], "qualities": [],
             "pixel_formats": ["yuv420", "yuv420p10bit"], "alpha_format": None},
}

PRORES_PIXEL_FORMATS = {
    "prores422proxy": ["yuv4228bit", "yuv42210bit", "yuv42212bit"],
    "prores422lt": ["yuv4228bit", "yuv42210bit", "yuv42212bit"],
    "prores422": ["yuv4228bit", "yuv42210bit", "yuv42212bit"],
    "prores422hq": ["yuv4228bit", "yuv42210bit", "yuv42212bit"],
    "prores4444": ["yuv44410bit", "yuva444412bit"],
    "prores4444xq": ["yuv44410bit", "yuva444412bit"],
}

CONTAINERS = {
    "notchlc": ".mov", "hap": ".mov", "cineform": ".mov", "prores": ".mov",
    "h264": ".mp4", "h265": ".mp4", "av1": ".mp4",
}

#: Human-readable labels for the FORMAT dropdown — Menunames keep TD's
#: exact menu tokens (what the encoder needs); Menulabels carry the
#: description (what the user needs). The 'a' in yuva = ALPHA — the entry
#: ProRes 4444 users are looking for (JP: "alpha not apparent").
FORMAT_LABELS = {
    "rgb": "RGB",
    "rgba": "RGB + Alpha",
    "rgbu": "RGB (HDR)",
    "rgbs": "RGB (HDR scRGB)",
    "yuv4228bit": "YUV 4:2:2 8-bit",
    "yuv42210bit": "YUV 4:2:2 10-bit",
    "yuv42212bit": "YUV 4:2:2 12-bit",
    "yuv44410bit": "YUV 4:4:4 10-bit",
    "yuva444412bit": "YUVA 4:4:4 12-bit + Alpha",
    "yuv420": "YUV 4:2:0 8-bit",
    "yuv420p10bit": "YUV 4:2:0 10-bit",
    "yuv444p8bit": "YUV 4:4:4 8-bit",
    "yuv444p10bit": "YUV 4:4:4 10-bit",
}

#: Movie extensions TD imports (docs.derivative.ca File_Types, verified).
MOVIE_EXTS = {".m4v", ".mkv", ".mov", ".mp4", ".hsp", ".notchlc", ".mpeg",
              ".mpg", ".avi", ".flv", ".m2ts", ".wmv", ".h265", ".vp8",
              ".vp9", ".3gp", ".mxf", ".ts", ".r3d"}

#: Batch queue: list of dicts {input, output, status, rel}
_queue = []

#: last source-rate seen by the onFrame FPS display (SOURCE mode)
_last_src_fps = None
#: (source fps, selected path, queue length) — SOURCE mode re-reads the
#: displayed rate whenever any of these change, not just the fps
_last_fps_key = None

#: row-click inspector state: the clicked item + load ticks (the
#: Media File Info DAT provides the metadata; JP 2026-09-14: click a
#: queue row -> name / resolution / frame rate / codec in output_l)
_noted_table = False   # one-shot raw-table dump for label verification
_tick_alive = False    # one-shot proof the panel tick is running
_tick_errs = {}        # {label: last frame reported} — rate-limits tick noise
_showing_activity = False  # OUTPUT field is showing live job status
_install = None            # background audio-support install, or None
_health_check_frame = -999 # last frame we ran the ffmpeg check
_health_ok = True          # cached ffmpeg status for the help button
_ROW_H = 22                # lister row height in px (measured, JP)
_BLANK = "---"             # FPS/OUTPUT placeholder: nothing to show
_lister_errs_cleared = False  # one-shot: stale init error on the lister


def _tick_err(label, exc):
    """Report a per-frame tick failure once every ~5s — silent tick
    blocks hid a dead inspector for several rounds."""
    try:
        now = absTime.frame
    except Exception:
        now = 0
    if now - _tick_errs.get(label, -9999) > 300:
        _tick_errs[label] = now
        note(f"tick error [{label}]: {type(exc).__name__}: {exc}")
_selected_path = None  # input path of the last clicked row (remove_b target)

#: --- persistent panel state (survives TD quit/relaunch) -------------
#: A JSON file written on every relevant widget change and restored
#: at build end (after the bake, before the preview/fps seeds). The
#: capture owns LAYOUT; this owns RUNTIME SELECTIONS.
import json as _json


def _vcon_data_dir():
    """Per-user vCon data folder (settings, downloaded packages).

    Must NOT be inside the repo or the .toe: those paths do not exist
    on anyone else's machine, and the .toe is read-only package data
    once installed.
    """
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/vCon")
    elif os.name == "nt":
        base = os.path.join(
            os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
            "vCon")
    else:
        base = os.path.expanduser("~/.local/share/vCon")
    return base


_SETTINGS_PATH = os.path.join(_vcon_data_dir(), "panel_settings.json")

#: which widget Value0 pars are persisted (string values stored as-is)
_PERSIST_WIDGETS = (
    "destination", "codec_dd", "subtype_dd", "format_dd",
    "quality_dd", "container_dd",
    "audio_dd", "audio_sep_t", "audio_sep_dd",
    "fps_f", "fps_t", "scaled_t", "scale_dd",
    "fit_dd", "resw_f", "resh_f",
)


def _save_settings():
    """Write the panel's runtime selections to JSON (called on every
    relevant widget change via Onvaluechangescript0 hooks)."""
    out = {}
    for name in _PERSIST_WIDGETS:
        w = widget(name)
        if w is None:
            continue
        try:
            out[name] = w.par.Value0.eval()
        except Exception:
            pass
    try:
        os.makedirs(os.path.dirname(_SETTINGS_PATH), exist_ok=True)
        with open(_SETTINGS_PATH, 'w', encoding='utf-8') as f:
            _json.dump(out, f, indent=2)
    except Exception as exc:
        debug(f"panel settings save failed: {exc}")


def _load_settings():
    """Restore the panel's runtime selections from JSON (called at build
    end, after the bake). Returns silently if no file exists yet."""
    if not os.path.isfile(_SETTINGS_PATH):
        return
    try:
        with open(_SETTINGS_PATH, 'r', encoding='utf-8') as f:
            data = _json.load(f)
    except Exception as exc:
        debug(f"panel settings load failed: {exc}")
        return
    for name, val in data.items():
        w = widget(name)
        if w is None:
            continue
        try:
            w.par.Value0.val = val
        except Exception:
            pass
    note(f"panel settings restored from {os.path.basename(_SETTINGS_PATH)}")


def PersistSettings():
    """Call from any widget's Onvaluechangescript0 to save the panel's
    runtime state. Appended to existing hooks by the builder."""
    _save_settings()


#: Shipped selection defaults (JP 2026-09-16). Applied at build end
#: BEFORE _load_settings(), so a saved settings file always wins and
#: these only surface on a first run. Code-owned rather than captured:
#: the canonical capture must be taken with SCALE ON, so it can never
#: record scaled_t OFF as the default, and a captured destination would
#: ship one machine's home folder. A leading '~' is expanded per-user;
#: the folder is NOT created (JP: just seed the path, the user picks).
_DEFAULT_SELECTIONS = {
    "destination": "~/Desktop/converted",
    "container_dd": "mov",
    "codec_dd": "notchlc",
    "format_dd": "rgb",
    "quality_dd": "1.0",
    "fps_t": False,
    "scaled_t": False,
    "audio_dd": "none",
    "audio_sep_t": False,
    "audio_sep_dd": "wav16",
}


def _apply_defaults():
    """Seed the shipped selection defaults (a saved settings file, loaded
    right after, overrides any of them)."""
    for name, val in _DEFAULT_SELECTIONS.items():
        w = widget(name)
        if w is None:
            continue
        if isinstance(val, str) and val.startswith("~"):
            val = os.path.expanduser(val)
        try:
            w.par.Value0.val = val
        except Exception as exc:
            note(f"default ({name}) failed: {exc}")
    note(f"shipped defaults applied ({len(_DEFAULT_SELECTIONS)} widgets)")


def ext():
    """The vCon extension (Global OP Shortcut 'vcon' — set by the builder)."""
    return op.vcon.ext.Vcon


def panel():
    """The panel COMP: a child of vcon named 'panel'."""
    return op.vcon.op('panel')


def widget(name):
    """A named panel child — TOP-LEVEL only (JP rule: configure top-level
    parameters; the builder now places widget COMPs directly in the
    panel). No inner-child searching: if the name resolves, that COMP
    is the widget we configure. Kept as a function so call sites stay
    stable and any future structural change has one choke point."""
    p = panel()
    if p is None:
        return None
    return p.op(name)


def _val(name):
    """Read a widget's Value0."""
    w = widget(name)
    if w is None:
        return None
    try:
        return w.par.Value0.eval()
    except Exception:
        return None


def _td_container(codec):
    """The container token for MvO's moviecontainer par — from the
    dropdown, falling back to the codec's default in CONTAINERS."""
    c = _val("container_dd")
    if c:
        return c
    ext = CONTAINERS.get(codec)
    return ext.lstrip(".") if ext else None


def _output_name(input_path, codec, subtype=None):
    """clip.mov + prores 422hq -> clip.prores422hq.mov (same folder).
    Extension follows the container dropdown, not the codec default."""
    folder = os.path.dirname(input_path)
    stem = os.path.splitext(os.path.basename(input_path))[0]
    tag = subtype if subtype and subtype != "none" else codec
    container = _val("container_dd") or "mov"
    ext = _container_ext(container)
    return os.path.join(folder, f"{stem}.{tag}{ext}")


def _unique_output(path):
    """Never overwrite: clip.notchlc.mov exists -> 'clip.notchlc (2).mov'."""
    if not os.path.exists(path):
        return path
    folder = os.path.dirname(path)
    stem, ext = os.path.splitext(os.path.basename(path))
    n = 2
    while True:
        cand = os.path.join(folder, f"{stem} ({n}){ext}")
        if not os.path.exists(cand):
            return cand
        n += 1


def _derive_output(src, dst, codec, subtype):
    """The output path a job would get, given current widget state."""
    derived = _output_name(src, codec, subtype)
    if dst and os.path.isdir(dst):
        return os.path.join(dst, os.path.basename(derived))
    return derived


def _derived_output_for(src):
    """The full output path `src` would get under the CURRENT settings,
    collision numbering included."""
    codec = _val("codec_dd") or "notchlc"
    subtype = _validate_choice(codec, "subtype", _val("subtype_dd"))
    return _unique_output(_derive_output(src, _dst_dir(), codec, subtype))


def _is_movie(path):
    return os.path.splitext(path)[1].lower() in MOVIE_EXTS


# ---------------------------------------------------------------------
# Live preview: OUTPUT field describes the SOURCE the user is looking at
# ---------------------------------------------------------------------

def PreviewOutput(override_src=None):
    """Refresh the read-only OUTPUT field: 'source name | WxH | fps |
    length | codec' for the selected row.

    `override_src` names the file to describe regardless of selection —
    drops pass the file just added (JP 2026-09-15: without it the field
    kept showing the FIRST drop, since it read _queue[0]).

    LIVE-VERIFIED (2026-09-13 dump): the label widget renders the LABEL
    par, NOT Widgetlabel — writes to Widgetlabel silently don't render
    on this build ('Output field shows nothing', the SECOND occurrence).
    """
    try:
        # An empty queue has nothing to describe, whatever was last
        # clicked: a stale _selected_path from a finished/removed row
        # kept showing a filename after the queue drained.
        global _selected_path
        if not _queue:
            _selected_path = None
            _set_output_text("(queue is empty — add files)")
            return
        # The SELECTED row, or the file a drop just added. NOT the first
        # queued one: after a deselect that described a row the user was
        # no longer pointing at (JP 2026-09-15).
        src = override_src or _selected_path
        if not src or not os.path.isfile(src):
            _set_output_text(_BLANK)
            return
        src = _full_path_for(os.path.basename(src)) or src
        _inspect_now(src, attempt=0)
    except Exception as exc:
        note(f"preview failed: {exc}")


#: Phases worth naming in the status label. 'encoding' also shows the
#: frame counter; the rest have no frames to count.
_PHASE_LABELS = ("loading", "encoding", "finishing", "muxing",
                 "extracting")
_STATUS_PREFIX = "Encoded file name: "
_EMPTY_QUEUE_HINT = "Drag files into the queue area below or click ADD button"


def _controller_phase():
    """The controller's state name, or '' when unreadable. Falls back to
    the first word of the Status par, which carries the same phase."""
    try:
        s = str(ext().state or "").strip().lower()
        if s:
            return s
    except Exception:
        pass
    try:
        return str(op.vcon.par.Status.eval()).strip().split(" ")[0].lower()
    except Exception:
        return ""


def SyncStatusField():
    """The STATUS label (overlaid on the progress bar) names the file
    being WRITTEN, and what is happening to it:
      encoding — output name + 'encoding' + frame counter
      loading/finishing/muxing/extracting — output name + the phase
      idle, row selected — that row's output name under current settings
      idle, nothing selected — '---'
      empty queue — how to add files
    """
    try:
        try:
            busy = bool(ext().is_busy)
        except Exception:
            busy = False
        if busy:
            run = next((it for it in _queue
                        if it["status"] == "running"), None)
            out = (run or {}).get("output") or ""
            text = (_STATUS_PREFIX + os.path.basename(out)) if out else ""
            phase = _controller_phase()
            if phase == "encoding":
                try:
                    frame, total = ext().progress
                except Exception:
                    frame, total = 0, 0
                text = f"{text}  encoding".strip()
                if total:
                    text = f"{text}  {frame}/{total}"
            elif phase in _PHASE_LABELS:
                text = f"{text}  {phase}".strip()
            _set_status_text(text)
            return
        if _selected_path and os.path.isfile(_selected_path):
            src = _full_path_for(
                os.path.basename(_selected_path)) or _selected_path
            _set_status_text(
                _STATUS_PREFIX
                + os.path.basename(_derived_output_for(src)))
            return
        _set_status_text(_BLANK if _queue else _EMPTY_QUEUE_HINT)
    except Exception as exc:
        note(f"status sync failed: {exc}")


def UpdateSubtypes():
    """Re-populate SUBTYPE and FORMAT for the selected codec — no 'none'.

    JP spec: 'none' is never offered. Every codec with subtypes defaults
    to its FIRST real subtype (Hap -> hap, ProRes -> prores422proxy);
    codecs without subtypes (NotchLC, CineForm, delivery codecs) HIDE the
    dropdown entirely (JP 2026-09-16 — an empty greyed control still ate
    a slot in the row). FORMAT offers the codec's real pixel formats with
    the first as default (Hap: rgb + rgba, rgb selected; NotchLC: rgb +
    rgba; CineForm: rgba; ProRes: per-SUBTYPE menus, 422 set while no
    subtype is finer).
    """
    try:
        codec = _val("codec_dd") or "notchlc"
        meta = CODECS.get(codec, {})
        sub_w = widget("subtype_dd")
        fmt_w = widget("format_dd")
        # ---- SUBTYPE: real options only; CLEAR + grey out when none.
        # JP bug report: after selecting Hap (subtypes appear), choosing
        # h264/h265/av1/cineform left 'hap' selectable — the grey-out
        # never landed and the stale menu/value survived. Fix: when a
        # codec has NO subtypes, CLEAR the menu (empty), reset Value0,
        # and grey out — a disabled, visibly-empty control can't offer
        # or keep a stale option.
        if sub_w is not None:
            subs = list(meta.get("subtypes", []))
            try:
                sub_w.par.display.val = 1 if subs else 0
            except Exception as exc:
                note(f"subtype visibility failed: {exc}")
            if subs:
                setp_par(sub_w, "Menunames", " ".join(subs))
                setp_par(sub_w, "Menulabels", " ".join(subs))
                try:
                    default = meta.get("default_subtype", subs[0])
                    if sub_w.par.Value0.val not in subs:
                        sub_w.par.Value0.val = default
                except Exception:
                    pass
                _grey_out(sub_w, False)
            else:
                setp_par(sub_w, "Menunames", "")
                setp_par(sub_w, "Menulabels", "")
                try:
                    sub_w.par.Value0.val = ""
                except Exception:
                    pass
                _grey_out(sub_w, True)
        # ---- FORMAT: per-subtype when the codec defines them (Hap's
        # haphdr offers rgbu/rgbs — verified live), else the codec's
        # list. First entry is the default. Grey out only if empty.
        if fmt_w is not None:
            by_sub = meta.get("pixel_formats_by_subtype", {})
            cur_sub = _val("subtype_dd")
            if by_sub and cur_sub in by_sub:
                fmts = list(by_sub[cur_sub])
                grey = False
            elif codec == "prores":
                fmts = list(PRORES_PIXEL_FORMATS.get(
                    cur_sub, PRORES_PIXEL_FORMATS.get("prores422", [])))
                grey = False
            else:
                fmts = list(meta.get("pixel_formats", []))
                grey = not fmts
            if fmts:
                setp_par(fmt_w, "Menunames", " ".join(fmts))
                setp_par(fmt_w, "Menulabels",
                         " ".join(f"'{FORMAT_LABELS.get(f, f)}'" for f in fmts))
                try:
                    if fmt_w.par.Value0.val not in fmts:
                        fmt_w.par.Value0.val = fmts[0]
                except Exception:
                    pass
            _grey_out(fmt_w, grey)
        # QUALITY: NEVER greyed (JP) — the slider always affects MvO's
        # quality par for whatever codec is selected; the per-codec
        # 'ladder' note is documentation, not a UI state.
        _update_res_fields()
        PreviewOutput()
    except Exception as exc:
        note(f"subtype update failed: {exc}")


def _grey_out(inner, grey):
    """Disable a widget's interaction (greyed like MvO's empty menus).

    Display/enable pars on these widgets are STRING MENUS
    (['off','on']) — integer writes select menu INDEX 0, which can be
    'on'. Write tokens; fall back to ints only if no menu exists.
    Tries BOTH the builtin Panel 'enable' and the widget 'Enable'
    custom par; if neither exists, say so (a silent return here is how
    stale subtypes stayed clickable — JP bug report).
    """
    hit = False
    for cand in ("enable", "Enable"):
        par = getattr(inner.par, cand, None)
        if par is None:
            continue
        try:
            menus = list(getattr(par, "menuNames", None) or [])
            if menus:
                par.val = "off" if grey else "on"
            else:
                par.val = 0 if grey else 1
            hit = True
        except Exception:
            continue
    if not hit:
        note(f"grey-out failed on {inner.name}: no enable par")


# Container → codec compatibility matrix. The codec dropdown is
# repopulated from this on every container change — incompatible
# codecs simply don't appear in the menu.
_CONTAINER_CODECS = {
    "mov":  ["notchlc", "hap", "cineform", "prores", "h264", "h265",
             "rle", "mjpa", "mpeg4"],
    "mp4":  ["h264", "h265", "av1", "mpeg4", "vvc"],
    "mkv":  ["h264", "h265", "av1", "vp8", "vp9", "prores", "vvc",
             "mjpa", "mpeg4"],
    "webm": ["vp8", "vp9", "av1"],
}

#: Container → audio codec compatibility for the ffmpeg mux.
_CONTAINER_AUDIO = {
    "mov":  ["copy", "pcm_s16le", "pcm_s24le", "aac", "alac", "none"],
    "mp4":  ["copy", "aac", "none"],
    "mkv":  ["copy", "pcm_s16le", "pcm_s24le", "aac", "alac", "mp3",
             "none"],
    "webm": ["none"],
}

#: Audio codec → menu label. The ffmpeg argument mapping lives in the
#: controller, which is what actually runs the mux.
_AUDIO_LABELS = {
    "copy": "Copy (source)", "pcm_s16le": "PCM 16-bit",
    "pcm_s24le": "PCM 24-bit", "aac": "AAC", "alac": "ALAC",
    "mp3": "MP3", "none": "None (video only)",
}


def _container_codecs(container):
    """Compatible codecs for a container, or all if unknown."""
    return _CONTAINER_CODECS.get(container, list(CODECS.keys()))


def _container_ext(container):
    """File extension for a container token."""
    return {"mov": ".mov", "mp4": ".mp4", "mkv": ".mkv",
            "webm": ".webm"}.get(container, ".mov")


def _set_menu(w, names, labels, default):
    """Populate a dropDownMenu at runtime (mirrors build_panel.set_menu)."""
    try:
        w.par.Menunames.val = " ".join(names)
        w.par.Menulabels.val = " ".join(
            f"'{l}'" if " " in l else l for l in labels)
        if default in names:
            w.par.Value0.val = default
    except Exception as exc:
        note(f"menu set failed on {w.name}: {exc}")


def _container_audio(container):
    """Compatible mux audio codecs for a container."""
    return _CONTAINER_AUDIO.get(container, ["copy"])


def _audio_value():
    """Current audio_dd selection, default 'copy'."""
    return _val("audio_dd") or "copy"


def OnAudioChanged():
    """AUDIO dropdown changed → persisted. The mux reads this at job time."""
    PersistSettings()


def OnAudioSepChanged():
    """AUDIO SEP toggle changed → show/hide the format dropdown + persist."""
    on = bool(_val("audio_sep_t"))
    w = widget("audio_sep_dd")
    if w is not None:
        try:
            w.par.display.val = on
        except Exception:
            pass
    PersistSettings()


def OnContainerChanged():
    """CONTAINER dropdown changed → repopulate codec_dd AND audio_dd with
    only compatible entries, preserving current selections if still valid.
    Then fire the selection chain so subtype/format/MvO all follow."""
    try:
        container = _val("container_dd") or "mov"
        # Codec menu
        w = widget("codec_dd")
        if w is not None:
            cur = _val("codec_dd")
            valid = _container_codecs(container)
            names = [c for c in valid if c in CODECS]
            labels = [CODECS[c]["label"] for c in names]
            _set_menu(w, names, labels,
                      cur if cur in names else names[0])
        # Audio menu
        aw = widget("audio_dd")
        if aw is not None:
            acur = _val("audio_dd")
            anames = _container_audio(container)
            alabels = [_AUDIO_LABELS.get(a, a) for a in anames]
            _set_menu(aw, anames, alabels,
                      acur if acur in anames else anames[0])
        # Re-fire the codec/subtype/format chain for the new selection
        UpdateSubtypes()
        OnSelectionChanged()
        PersistSettings()
    except Exception as exc:
        note(f"container change failed: {exc}")


# NotchLC quality ladder (Derivative's guide) — the dropdown's menu
# tokens are these values as strings, so the label IS the name.
_QUALITY_LEVELS = [
    (0.0,   "Good"),
    (0.285, "Very Good"),
    (0.575, "Excellent"),
    (0.862, "Optimal"),
    (1.0,   "Best"),
]


def _quality_value():
    """The QUALITY dropdown's 0-1 float, defaulting to Optimal."""
    try:
        return float(_val("quality_dd"))
    except (TypeError, ValueError):
        return 0.862


def OnQualityChanged():
    """QUALITY dropdown changed -> set MvO's quality par LIVE."""
    try:
        ext().Setquality(_quality_value())
    except Exception as exc:
        note(f"quality sync failed: {exc}")


def OnSelectionChanged():
    """CODEC/SUBTYPE/FORMAT dropdown changed -> apply to MvO LIVE.

    JP: changing a dropdown must show in MvO's parameters immediately —
    the panel IS the parameter editor. Fires from all three dropdowns'
    Onvaluechangescript0; routes through the extension's Setparams(),
    which reuses the menu read-back verification (invalid tokens fail
    loudly, never silently fall back to entry 0). Idle-guarded on the
    controller side: an encode in flight keeps its settings.
    """
    try:
        codec = _val("codec_dd") or "notchlc"
        meta = CODECS.get(codec, {})
        subtype = _validate_choice(codec, "subtype", _val("subtype_dd"))
        fmt = _validate_choice(codec, "format", _val("format_dd"))
        ext().Setparams(
            codec=codec,
            subtype=subtype if subtype else None,
            pixel_format=fmt if fmt else None,
            container=_val("container_dd") or None,
        )
    except Exception as exc:
        note(f"selection sync failed: {exc}")


#: FPS/SCALE row layouts — TWO hand-tuned arrangements (JP): SCALE ON
#: keeps the full row; SCALE OFF repositions the FPS group (NOT
#: hard-left) with the scale controls hidden.
#: Entries are {par: value} — geometry (x/y/w/h/display) AND the label/
#: button widths, which are per-layout too: a wider fps_t in OFF needs
#: Labelwidth 90, and leaving that set broke the ON row (JP 2026-09-16).
#: Baked from the captures: 'on' from toe/panel_layout_captured.py,
#: 'off' from toe/panel_layout_variant.py (capture_variant prints
#: paste-ready blocks after each capture).
_ROW_LAYOUTS = {
    'on': {
        'fps_t': {'x': 12, 'y': 510, 'w': 85, 'h': 30, 'display': True,
                  'Labelwidth': 29, 'Buttonwidth': 51},
        'fps_f': {'x': 94, 'y': 510, 'w': 55, 'h': 30, 'display': True,
                  'Labelwidth': 29, 'Labeldisplay': False},
        'scaled_t': {'x': 154, 'y': 510, 'w': 82, 'h': 30, 'display': True,
                     'Labelwidth': 42, 'Buttonwidth': 33},
        'scale_dd': {'x': 231, 'y': 510, 'w': 108, 'h': 30,
                     'Labelwidth': 32},
        'fit_dd': {'x': 336, 'y': 510, 'w': 121, 'h': 30,
                   'Labelwidth': 26},
        'resw_f': {'x': 449, 'y': 510, 'w': 100, 'h': 30,
                   'Labelwidth': 20},
        'resh_f': {'x': 540, 'y': 510, 'w': 100, 'h': 30,
                   'Labelwidth': 20},
    },
    'off': {
        'fps_t': {'x': 12, 'y': 510, 'w': 154, 'h': 30, 'display': True,
                  'Labelwidth': 90, 'Buttonwidth': 58},
        'fps_f': {'x': 162, 'y': 510, 'w': 55, 'h': 30, 'display': True,
                  'Labelwidth': 29, 'Labeldisplay': False},
        'scaled_t': {'x': 250, 'y': 510, 'w': 101, 'h': 30, 'display': True,
                     'Labelwidth': 60, 'Buttonwidth': 33},
        'scale_dd': {'x': 231, 'y': 510, 'w': 108, 'h': 30,
                     'Labelwidth': 32},
        'fit_dd': {'x': 336, 'y': 510, 'w': 121, 'h': 30,
                   'Labelwidth': 26},
        'resw_f': {'x': 449, 'y': 510, 'w': 100, 'h': 30,
                   'Labelwidth': 20},
        'resh_f': {'x': 540, 'y': 510, 'w': 100, 'h': 30,
                   'Labelwidth': 20},
    },
}


def _apply_row_layout(scaled):
    """Place + size the FPS/SCALE row per the SCALE ON/OFF layout.

    Runs from _update_res_fields on every toggle flip and once at build
    end — idempotent writes. Every key is written as a par, so geometry
    and the label/button widths switch together; the scale group's
    display flags are re-derived right after.
    """
    lay = _ROW_LAYOUTS.get('on' if scaled else 'off') or {}
    for name, entry in lay.items():
        w = panel().op(name)
        if w is None:
            continue
        for key, val in entry.items():
            try:
                w.par[key].val = val
            except Exception as exc:
                note(f"row layout ({name}.{key}) failed: {exc}")


def _update_res_fields():
    """Live-fit wiring + SCALE visibility, driven by the SCALED toggle.

    Two effects when the toggle flips (JP: wiring should visibly change
    AT THE SWITCH, not at job time):
      - SCALED  -> controller wires moviein -> fit -> movieout NOW
                   (fit configured with the chosen mode; a later job only
                   sets the exact WxH once the movie's size is known)
      - UNSCALED-> controller rewires moviein -> movieout NOW
    Plus: the SCALE dropdown shows/hides with the toggle. The SCALE/FIT/
    W-H choices also push LIVE into the fit TOP (OnFitChanged below —
    the panel IS the parameter editor), and the visibility state
    re-derives from the actual widget values.
    """
    mode = _val("scaled_t")
    # buttonToggle's Value0 is a BOOLEAN (0/1), not a string — comparing
    # to 'scaled' never matched, so the toggle silently did nothing.
    scaled = bool(mode)
    # 0) ROW LAYOUT: place the row per SCALE ON/OFF (JP's two-layout
    #    row) BEFORE the visibility pass — the OFF arrangement moves the
    #    FPS group out of the hard-left margin position.
    _apply_row_layout(scaled)
    # 1) rewire NOW through the extension (toggle state is advisory; the
    #    controller re-applies per job, so a busy encoder is unaffected).
    try:
        ext().Setfitpath(scaled)
    except Exception as exc:
        note(f"fit rewire failed: {exc}")
    # 2) SCALE + FIT + W/H fields show/hide. When SCALING is OFF there
    #    is nothing to configure (fit TOP bypassed) — all hidden. When
    #    ON: SCALE + FIT show; the W/H fields show ONLY for Custom
    #    (an absolute output resolution — JP).
    scaled_on = 1 if scaled else 0
    for name, show in (("scale_dd", scaled_on), ("fit_dd", scaled_on)):
        outer = panel().op(name) if panel() is not None else None
        if outer is None:
            continue
        try:
            outer.par.display.val = show
        except Exception:
            try:
                outer.par.x = 270 if show else 1200
            except Exception as exc:
                note(f"display toggle failed ({name}): {exc}")
    custom = (scaled and str(_val("scale_dd") or "") == "custom")
    for name in ("resw_f", "resh_f"):
        outer = panel().op(name) if panel() is not None else None
        if outer is None:
            continue
        try:
            outer.par.display.val = 1 if custom else 0
        except Exception:
            try:
                outer.par.x = 440 if custom else 1200
            except Exception as exc:
                note(f"display toggle failed ({name}): {exc}")
    # 3) LIVE push: the current SCALE/FIT/W-H choice into the fit TOP
    #    (the panel IS the parameter editor — the network updates at
    #    the SWITCH, not just at job time).
    if scaled:
        try:
            OnFitChanged()
        except Exception as exc:
            note(f"live fit push failed: {exc}")


def OnFitChanged():
    """SCALE / FIT / W-H widget hook → fit TOP, LIVE.

    Called by Onvaluechangescript0 on scale_dd / fit_dd / resw_f /
    resh_f (wired by the builder). Pushes the current choice through
    Setfitparams so the fit TOP's Output Resolution / Fit / custom
    WxH pars move immediately — JP: the panel IS the parameter editor.
    """
    scaled = bool(_val("scaled_t"))
    scaled = scaled and not ext().is_busy
    if not scaled:
        return          # fit TOP bypassed (or mid-encode) — nothing to push
    choice = str(_val("scale_dd") or "").strip()
    fitmode = str(_val("fit_dd") or "").strip() or None
    w = str(_val("resw_f") or "").strip()
    h = str(_val("resh_f") or "").strip()
    if choice == "custom":
        if w.isdigit() and h.isdigit() and int(w) > 0 and int(h) > 0:
            ext().Setfitparams(scale=choice, fit=fitmode, w=w, h=h)
        else:
            note("custom resolution needs valid W and H in the fields")
    elif choice:
        ext().Setfitparams(scale=choice, fit=fitmode)


def OnFpsChanged():
    """FPS field hook -> MvO's fps par, LIVE (JP: the field changes the
    par — same live-editor pattern as the QUALITY slider). 'auto'
    resolves to the loaded source's rate when one is available.
    """
    v = str(_val("fps_f") or "").strip()
    # The field also carries placeholder text ('---' when there is no
    # rate to show); pushing that to the controller raised a float
    # conversion error on every write (JP 2026-09-15).
    if not v or v == _BLANK:
        return
    try:
        ext().Setfps(v)
    except Exception as exc:
        note(f"fps set failed: {exc}")


def _fps_source_mode():
    """True when the FPS mode toggle is OFF: use the SOURCE's own rate.

    fps_t (JP's hand-added toggle): ON = CUSTOM (the field drives MvO's
    fps par), OFF = SOURCE. No toggle in this build (pre-capture):
    False — the field stays a free custom editor, exactly as before.
    """
    v = _val("fps_t")
    if v is None:
        return False
    return not bool(v)


def _source_fps():
    """The loaded source's frame rate — the Info CHOP's sample_rate
    channel (the verified source: Movie File In has no fps par).
    None when nothing is loaded / the channel is unreadable.

    PROBE-VERIFIED (JP 2026-09-15): with no movie loaded the Info CHOP
    still reports a rate — the PROJECT's (60), not a source's. So the
    Movie In's file par gates the read; without that, 'no source' is
    indistinguishable from 'a real 60fps source'.
    """
    try:
        if not str(ext().moviein.par.file.eval() or "").strip():
            return None
    except Exception:
        return None
    try:
        sr = float(ext().info["sample_rate"][0])
        if sr > 0:
            return sr
    except Exception:
        pass
    return None


def OnFpsModeChanged():
    """fps_t toggle hook (JP 2026-09-14):
      OFF = SOURCE: the FPS field is DISABLED and displays the loaded
             source's rate (Info CHOP sample_rate); MvO's fps par
             follows it; every job encodes at its own file's rate.
      ON  = CUSTOM: the FPS field is ENABLED and two-way with MvO's
             fps par (the live-editor pattern).
    """
    source = _fps_source_mode()
    w = widget("fps_f")
    if w is None:
        return
    # LIVE-VERIFIED (JP 2026-09-14): the FPS field is a fieldString —
    # its interaction disable is STRINGFIELDREADONLY (a Boolean: writes
    # are ints 0/1, NEVER the string 'off', which coerces True on
    # Toggles). The generic enable par does NOT stop typing in a
    # string field (first attempt: field stayed editable).
    try:
        w.par.Stringfieldreadonly.val = 1 if source else 0
    except Exception as exc:
        note(f"fps field readonly failed: {exc}")
        _grey_out(w, source)      # legacy fallback (enable par)
    if source:
        # MvO follows the source's rate; the field displays it
        # (readonly — display-only until the mode flips back)
        SyncFpsField()
    else:
        # CUSTOM: the field is the authority — push it to MvO now
        OnFpsChanged()


def _queued_fps():
    """Frame rate of the SELECTED queue row, or None.

    Selection only — no falling back to the next queued item (JP
    2026-09-15: nothing selected must show nothing, or the field
    describes a file the user never pointed at).
    """
    src = _selected_path
    if src:
        src = _full_path_for(os.path.basename(src)) or src
    if not src or not os.path.isfile(src):
        note(f"  queued fps: no selected file ({src!r})")
        return None
    p = panel()
    d = p.op("inspector") if p is not None else None
    if d is None:
        note("  queued fps: NO 'inspector' DAT — rebuild needed")
        return None
    try:
        if str(d.par.file.eval() or "") != src:
            d.par.file = src
            d.par.reloadpulse.pulse()
        d.cook(force=True)
    except Exception as exc:
        note(f"  queued fps: inspector cook failed: {exc}")
        return None
    vals = _inspector_values()
    raw = None
    for n in ("fps", "frame rate", "framerate"):
        if n in vals:
            raw = vals[n]
            break
    if raw is None:
        note(f"  queued fps: no fps row in inspector {sorted(vals)!r}")
        return None
    try:
        return float(raw) or None
    except (TypeError, ValueError):
        return None


def SyncFpsField():
    """Seed the FPS field per MODE (runs at build end, AFTER the capture
    bake, and whenever the mode/source rate/selection changes):
      SOURCE mode — the running job's rate while encoding; otherwise the
        SELECTED queue row's rate; '---' when nothing is selected, so a
        stale value is never shown as if it were the source's.
      CUSTOM mode — display MvO's fps par (the field IS the par's editor).
    The field write fires OnFpsChanged -> Setfps with the same value —
    idempotent, no loop.
    """
    w = widget("fps_f")
    if w is None:
        return
    if _fps_source_mode():
        # The controller leaves the finished job's movie loaded in Movie
        # In, so a file being present does NOT mean it is what the user
        # is looking at — only a running job does (JP 2026-09-15: the
        # field pinned to the last encode's rate and ignored clicks).
        try:
            busy = bool(ext().is_busy)
        except Exception:
            busy = False
        v = _source_fps() if busy else None
        label = "source rate"
        if v is None:
            v = _queued_fps()
            label = "selected row"
        if v is None:
            # Nothing loaded and nothing queued: show no number rather
            # than the last CUSTOM value, which reads as the source's.
            try:
                w.par.Value0.val = _BLANK
                note(f"FPS field <- {_BLANK} (no source)")
            except Exception as exc:
                note(f"fps field write failed: {exc}")
            return
        try:
            # MvO follows the source rate (JP spec for SOURCE mode)
            ext().Setfps(str(v))
        except Exception as exc:
            note(f"fps source push failed: {exc}")
    else:
        try:
            v = float(ext().movieout.par.fps.eval())
        except Exception as exc:
            note(f"fps read failed: {exc}")
            return
        label = "MvO par"
    text = str(int(v)) if v == int(v) else ('%g' % v)
    try:
        w.par.Value0.val = text
        note(f"FPS field <- {text} ({label})")
    except Exception as exc:
        note(f"fps field write failed: {exc}")


def _set_output_text(text):
    """Write text to the OUTPUT label (the renderable string par).

    EVIDENCE (JP's capture): Widgetlabel is the STRING that renders —
    the stale '/Users/jp/Desktop/toConvert/...mov' path JP saw in the
    field lived in Widgetlabel. The par named 'Label' is an OP-REFERENCE
    par (type:containerCOMP path:.../label) — writing a string to it
    silently fails (my regression, reverted).

    The write is READ-BACK VERIFIED: if the par doesn't take the text,
    that is reported instead of failing silently (the failure mode that
    cost two rounds here).
    """
    w = widget("output_l")
    if w is None:
        note("output text: output_l widget not found")
        return
    try:
        w.par.Widgetlabel.val = text
    except Exception as exc:
        note(f"output text failed (Widgetlabel): {exc}")
        return
    try:
        got = str(w.par.Widgetlabel.eval())
        if got != text:
            note(f"output text: par took {got!r}, expected {text!r}")
    except Exception:
        pass


def _set_status_text(text):
    """Write text to the STATUS label (same Widgetlabel rule as the
    output field). Silent when the widget is absent — status_l has been
    deleted from the panel before."""
    w = widget("status_l")
    if w is None:
        return
    try:
        w.par.Widgetlabel.val = text
    except Exception as exc:
        note(f"status text failed (Widgetlabel): {exc}")


def _queue_rebuild_from_table():
    """Reconstruct the in-memory _queue from queue_table (the durable
    copy) when the module was recompiled.

    GOTCHA (live-diagnosed 2026-09-14): TD recompiles file-linked DAT
    modules on EVERY file change — module-level state (_queue) resets,
    while the lister keeps showing rows from the table DAT. Without
    this, clicks say 'no matching queue item' and START silently
    encodes NOTHING though rows are right there. The table is the
    source of truth; the list is the cache.

    Col 3 holds the FULL input path (the lister never sees it — it
    reads queue_display, cols 0-1). Outputs are re-derived (the cached
    paths were lost with the list). Old tables without col 3 fall back
    to the basename (best effort — the inspector may then fail to load
    the file, and it says so).
    """
    global _queue
    t = op.vcon.op("queue_table")
    if t is None:
        return 0
    rows = []
    try:
        ncols = t.numCols
        for r in range(1, t.numRows):          # row 0 = header
            base = str(t[r, 0] or "").strip()
            s = str(t[r, 1] or "").strip()
            full = (str(t[r, 3] or "").strip()
                    if ncols > 3 else "")
            if not base:
                continue
            if not full:
                full = base                   # legacy table: basename only
            # a running row's status is a block bar — treat as queued
            # (the controller is the authority on what's actually
            # encoding; re-submitting after a recompile is safe because
            # _run_next's is_busy gate serializes it)
            if s.startswith(chr(0x2588)):
                s = "queued"
            rows.append({"input": full, "output": "", "status": s,
                         "rel": base})
    except Exception:
        pass
    if not rows:
        return 0
    # re-derive outputs (the cached ones died with the old list)
    codec = _val("codec_dd") or "notchlc"
    sub = _validate_choice(codec, "subtype", _val("subtype_dd"))
    for it in rows:
        try:
            it["output"] = _unique_output(_derive_output(
                it["input"], _dst_dir(), codec, sub))
        except Exception:
            it["output"] = it["input"]      # _run_next will fail loudly
    _queue = rows
    note(f"queue rebuilt from table: {len(rows)} item(s)")
    return len(rows)


def _queue_item_from_info(info):
    """Map a lister selection to its _queue item.

    LIVE-VERIFIED (JP's first-click dump 2026-09-14): the onSelectRow
    info carries rowData with the FILE NAME DIRECTLY:
      {'row': 5, 'rowData': {'file': 'OK_Go_TTSP.mp4', ...},
       'sourceIndex': 5, 'callbackName': 'onSelectRow'}
    So: rowData.file first (exact, no row-numbering guesses), then
    basename match at the row index, then direct index as a last
    resort. The old table-scanning heuristic is gone (it could grab
    the WRONG internal DAT — the lister's license-text callbacks DAT
    passes a 'not a header' check).
    """
    # 1) direct: rowData carries the file name
    rd = info.get("rowData") or {}
    nm = str(rd.get("file") or "").strip()
    if nm:
        for it in _queue:
            if os.path.basename(it["input"]) == nm:
                return it
    # 2) row index: try both conventions against queue_display
    r = info.get("row")
    try:
        r = int(r)
    except (TypeError, ValueError):
        return None
    try:
        d = op.vcon.op("queue_display")
        if d is not None:
            for idx in (r + 1, r):
                if 0 <= idx < d.numRows:
                    cell = str(d[idx, 0] or "").strip()
                    if cell and cell != "file":
                        for it in _queue:
                            if os.path.basename(it["input"]) == cell:
                                return it
    except Exception:
        pass
    # 3) last resort: direct index (0-based assumption)
    if 0 <= r < len(_queue):
        return _queue[r]
    return None


def _inspector_values():
    """The Media File Info DAT's 2-column table as {label: value}.

    The DAT (JP's suggestion — replaces the inspectin/mdls approach)
    emits one row per field: filename/filepath/vcodec/vcodecDesc/
    width/height/fps/frames/seconds (+ audio rows, + 'valid' on newer
    builds). Labels are normalized lowercase; the docs note DISPLAY
    labels may differ from API names ('Video Codec' vs 'vcodec'), so
    lookups go through label VARIANTS (see _inspect_tick).
    """
    p = panel()
    d = p.op("inspector") if p is not None else None
    if d is None:
        return {}
    out = {}
    try:
        for r in range(d.numRows):
            k = str(d[r, 0] or "").strip().lower()
            v = str(d[r, 1] or "").strip()
            if k and v:
                out[k] = v
    except Exception:
        pass
    return out


def _full_path_for(basename):
    """The FULL input path for a queue row's basename — resolved via
    queue_table col 3 (the durable full-path column), then any _queue
    item that has a real path (not a bare basename)."""
    t = op.vcon.op("queue_table")
    if t is not None:
        try:
            for r in range(1, t.numRows):
                if str(t[r, 0] or "").strip() == basename:
                    full = (str(t[r, 3] or "").strip()
                            if t.numCols > 3 else "")
                    if full:
                        return full
        except Exception:
            pass
    for it in _queue:
        if os.path.basename(it["input"]) == basename:
            cand = it["input"]
            if os.path.sep in cand:
                return cand
    return None


def OnQueueRowSelected(info=None):
    """Lister onSelectRow hook: show the clicked file's metadata in
    output_l (name | WxH | fps | length | codec).

    SYNCHRONOUS by design. The previous version handed off to the
    onFrame tick, which never ran — the display silently depended on a
    per-frame state machine. Now the click sets the file, FORCE-COOKS
    the Media File Info DAT, reads it, and writes the label in one go;
    a delayed retry covers builds where the cook lands a frame later.
    """
    global _selected_path
    info = info or {}
    note(f"lister onSelectRow: {info.get('callbackName')} "
         f"row={info.get('row')} "
         f"file={(info.get('rowData') or {}).get('file')}")
    if not _queue:
        _queue_rebuild_from_table()
    item = _queue_item_from_info(info)
    if item is None:
        note("  no matching queue item — inspect skipped")
        return
    _selected_path = item["input"]
    full = _full_path_for(os.path.basename(item["input"])) or item["input"]
    _inspect_now(full, attempt=0)
    # SOURCE mode shows the selected file's rate, so the field follows
    # the selection. CUSTOM mode leaves the field alone — it is the
    # user's editor.
    if _fps_source_mode():
        SyncFpsField()
    else:
        note("  fps_t is CUSTOM — FPS field left alone")
    SyncStatusField()


def OnQueueRowDeselected(info=None):
    """Lister onDeselectRow hook: clicking empty space clears the
    highlight, so the fields that describe the selection must clear too.

    Without this the lister's highlight vanished while _selected_path
    stayed set, freezing the FPS and OUTPUT fields on a row that no
    longer looked selected (JP 2026-09-15).
    """
    global _selected_path
    info = info or {}
    note(f"lister onDeselectRow: row={info.get('row')}")
    _selected_path = None
    if _fps_source_mode():
        SyncFpsField()
    PreviewOutput()
    SyncStatusField()


def _inspect_now(path, attempt=0):
    """Load `path` into the inspector DAT, cook it, display the result.

    Retries via the global run() scheduler (not the panel tick) so the
    display never depends on onFrame being alive.
    """
    p = panel()
    d = p.op("inspector") if p is not None else None
    if d is None:
        note("  NO 'inspector' DAT in the panel — rebuild needed")
        return
    if attempt == 0:
        note(f"  inspector loading: {path!r}")
        try:
            d.par.file = path
            d.par.reloadpulse.pulse()
        except Exception as exc:
            note(f"  inspect load failed: {exc}")
            return
    try:
        d.cook(force=True)
    except Exception:
        pass
    vals = _inspector_values()
    if not vals and attempt < 6:
        run("args[0](args[1], args[2])", _inspect_now, path, attempt + 1,
            delayFrames=10, fromOP=me if 'me' in globals() else None)
        return
    if not vals:
        note(f"  inspector: DAT returned no rows after {attempt} retries")
        _set_output_text(os.path.basename(path) + "  |  metadata unavailable")
        return
    if attempt == 0 or not _noted_table:
        _note_table_once(d, vals)
    _set_output_text(_format_media_info(path, vals))


def _note_table_once(d, vals):
    global _noted_table
    if not _noted_table:
        _noted_table = True
        note(f"  inspector DAT table ({d.numRows} rows): {vals!r}")


def _format_media_info(path, vals):
    """'source name | WxH | fps | length | codec' — what the user is
    looking AT. The file the encode will WRITE is the status field's
    job (JP 2026-09-15: one subject per field)."""
    def pick(*names):
        for n in names:
            if n in vals:
                return vals[n]
        return None

    parts = [os.path.basename(path)]
    width = pick("width", "video width")
    height = pick("height", "video height")
    if width and height:
        parts.append(f"{width}x{height}")
    fps = pick("fps", "frame rate", "framerate")
    if fps:
        try:
            parts.append(f"{float(fps):g} fps")
        except (TypeError, ValueError):
            parts.append(f"{fps} fps")
    dur = pick("duration", "length")
    if not dur:
        secs = pick("seconds", "numseconds")
        if secs:
            try:
                s = float(secs)
                dur = f"{int(s // 60)}:{s % 60:04.1f}"
            except (TypeError, ValueError):
                dur = f"{secs} s"
    if not dur:
        frames = pick("frames")
        dur = f"{frames} frames" if frames else None
    if dur:
        parts.append(dur)
    codec = pick("vcodecdesc", "vcodedesc", "video codec description",
                 "vcodec", "video codec", "codec")
    parts.append(codec if codec else "(codec unavailable)")
    text = "  |  ".join(parts)
    note(f"  inspector: {text}")
    return text


def _res_value():
    """Resolution args for Transcode(): (resolution, scale).

    SCALING off -> ('auto', None). ON: the SCALE dropdown holds a fit
    TOP Output Resolution token (the panel menu MIRRORS that menu —
    eighth/quarter/half/twotimes/fourtimes/eighttimes) which the fit
    TOP applies natively; 'custom' sends an ABSOLUTE WxH from the W/H
    fields (the controller applies it directly).
    """
    mode = _val("scaled_t")
    if not bool(mode):
        return "auto", None
    choice = str(_val("scale_dd") or "").strip()
    if not choice:
        # EMPTY SCALE with scaling on: no token to send — auto, not a
        # guessed default (a garbage token would fail the job loudly)
        note("no SCALE chosen — falling back unscaled")
        return "auto", None
    if choice == "custom":
        W = str(_val("resw_f") or "").strip()
        H = str(_val("resh_f") or "").strip()
        if W.isdigit() and H.isdigit() and int(W) > 0 and int(H) > 0:
            return f"{int(W)}x{int(H)}", None
        note("custom resolution needs valid W and H — falling back unscaled")
        return "auto", None
    # A fit TOP Output Resolution token (eighth/quarter/half/twotimes/
    # fourtimes/eighttimes) — the controller menu-verifies it against
    # the live fit TOP menu and fails LOUDLY on drift, never silent
    # index-0 fallback.
    return "auto", choice


def setp_par(inner, par_name, value):
    """setp without the noisy miss-print (used for menu re-population)."""
    try:
        getattr(inner.par, par_name).val = value
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------

def _validate_choice(codec, kind, value, allow_empty=True):
    """Widget values must be VALID for the current codec before submit.

    A greyed widget keeps whatever Value0 it last held — a stale subtype
    from a previous codec selection. Filter it here so junk can never
    reach the encoder: return the value if legal for this codec, else
    None (or the codec default when allow_empty=False).
    """
    meta = CODECS.get(codec, {})
    if kind == "subtype":
        legal = list(meta.get("subtypes", []))
    else:
        by_sub = meta.get("pixel_formats_by_subtype", {})
        if by_sub:
            cur = _val("subtype_dd")
            legal = list(by_sub.get(cur,
                                    list(meta.get("pixel_formats", []))))
        elif codec == "prores":
            cur = _val("subtype_dd")
            legal = list(PRORES_PIXEL_FORMATS.get(
                cur, PRORES_PIXEL_FORMATS.get("prores422", [])))
        else:
            legal = list(meta.get("pixel_formats", []))
    if value in legal:
        return value
    return legal[0] if (not allow_empty and legal) else None


def Start():
    """Run the queue: open the batch gate and let the tick feed items.

    SOURCE field removed (JP): the queue IS the input — files arrive via
    +ADD, drag/drop, or a folder drop. Encoding begins only on START.
    """
    global _batch_started
    if not _queue:
        note("queue is empty — add files first")
        return
    _batch_started = True
    _refresh_queue()
    n = sum(1 for it in _queue if it["status"] == "queued")
    note(f"batch started — {n} file(s) queued")


#: Batch gate: items enqueue freely (via +ADD / drops / folder browse),
#: but the tick only submits them once START has been pressed (JP:
#: adding a movie must NOT begin the encode). Set True by Start(),
#: False by Stop() and when the queue empties.
_batch_started = False


def _run_next():
    """Dequeue the next batch job and submit it (called when idle).

    GATED on _batch_started: queued items sit until START.
    """
    e = ext()
    if e.is_busy:
        return
    if not _batch_started:
        return                      # queue loaded, awaiting START (JP)
    # DURABLE QUEUE: a module recompile (file-linked DATs recompile on
    # every file change) resets the in-memory _queue — rebuild from the
    # table BEFORE iterating, or START silently encodes nothing.
    if not _queue:
        if _queue_rebuild_from_table() == 0:
            return
    nxt = None
    for item in _queue:
        if item["status"] == "queued":
            nxt = item
            break
    if nxt is None:
        return
    src = nxt["input"]
    base = os.path.basename(src)
    codec = _val("codec_dd") or "notchlc"
    subtype = _validate_choice(codec, "subtype", _val("subtype_dd"))
    # Re-derive the output HERE: the path stored at drop time carries
    # whatever codec was selected then (a file dropped under NotchLC
    # then encoded as ProRes came out named '.notchlc.mov').
    nxt["output"] = _unique_output(
        _derive_output(src, _dst_dir(), codec, subtype))
    note(f"  submitting: src={src!r}")
    note(f"  output: {nxt['output']!r}")
    note(f"  exists already: {os.path.exists(nxt['output'])}")
    quality = _quality_value()   # 0-1 float straight to MvO
    fmt = _validate_choice(codec, "format", _val("format_dd"))
    # FPS per MODE: SOURCE -> 'auto' (the controller re-resolves from
    # each loaded movie's sample_rate, so batch files with different
    # rates each encode at their own); CUSTOM -> the field's value
    if _fps_source_mode():
        fps = "auto"
    else:
        fps = str(_val("fps_f") or "auto").strip().lower()
    fitmode = _val("fit_dd")
    res, scale = _res_value()
    if fps in ("", "keep", "auto"):
        fps = "auto"
    if codec != "notchlc":
        quality = None          # only NotchLC has a quality slider in MvO
    container = _td_container(codec)
    audio = _audio_value()
    audio_sep = bool(_val("audio_sep_t"))
    audio_sep_fmt = _val("audio_sep_dd") or "wav16" if audio_sep else None
    note(f"  codec={codec} sub={subtype} fmt={fmt} fps={fps} "
         f"res={res} scale={scale} fit={fitmode} "
         f"container={container} audio={audio}"
         f"{' audio_sep=' + audio_sep_fmt if audio_sep_fmt else ''}")
    ok = e.Transcode(
        input_path=src,
        output_path=nxt["output"],
        codec=codec,
        subtype=subtype,
        quality=quality,
        fps=fps,
        pixel_format=fmt,
        resolution=res,
        scale=scale,
        fit=fitmode,
        container=container,
        audio=audio,
        audio_sep=audio_sep_fmt,
    )
    if ok:
        nxt["status"] = "running"
        _refresh_queue()
    else:
        # busy: try again next time the panel pings
        pass


def PauseResume():
    """Toggle pause/resume on the active job."""
    e = ext()
    if not e.is_busy:
        note("nothing running")
        return
    if getattr(e, "_paused", False):
        e.Resume()
    else:
        e.Pause()


def Stop():
    """Cancel the active job, stop the batch, clear the queue."""
    global _batch_started
    _batch_started = False      # re-close the gate (JP: adds must wait)
    ext().Cancel()
    for item in _queue:
        if item["status"] in ("queued", "running"):
            item["status"] = "cancelled"
    _refresh_queue()
    PreviewOutput()      # the preview follows queue state (JP 2026-09-14)
    note("cancelled")


# ---------------------------------------------------------------------
# Batch queue
# ---------------------------------------------------------------------

def _scan_movies(folder, recursive=True):
    """[(path, rel)] for every movie file under folder (sorted)."""
    import glob
    out = []
    if recursive:
        for path in sorted(glob.glob(os.path.join(folder, "**", "*"),
                                     recursive=True)):
            if os.path.isfile(path) and _is_movie(path):
                out.append((path, os.path.relpath(path, folder)))
    else:
        for path in sorted(glob.glob(os.path.join(folder, "*"))):
            if os.path.isfile(path) and _ismovie(path):
                out.append((path, os.path.relpath(path, folder)))
    return out


#: Half-block chars for the in-cell row bar: 8 sub-steps per char cell.
_BAR_FULL = "\u2588"
_BAR_EMPTY = "\u2591"


def _bar_text(frac, width=10):
    """A block-character progress bar for a queue row's status cell."""
    frac = 0.0 if frac is None else min(1.0, max(0.0, float(frac)))
    full = int(frac * width)
    return _BAR_FULL * full + _BAR_EMPTY * (width - full)


def _batch_progress():
    """(done_count, total_count) across the queue — the PANEL bar shows
    this for the whole batch (JP), not the current file's 0-1."""
    if not _queue:
        return 0.0
    done = sum(1 for it in _queue if it["status"] == "done")
    running = next((it for it in _queue if it["status"] == "running"),
                   None)
    if running is not None:
        try:
            frac = float(op.vcon.par.Progress.eval())
        except Exception:
            frac = 0.0
        return (done + frac) / len(_queue)
    return done / len(_queue)


def _refresh_queue():
    """Redraw the batch queue table (the lister widget's source DAT).

    STRATEGY (two rounds of live tracebacks): the lister refreshes on
    EVERY table write and throws 'Blank header in col 0' on any
    mid-write state (clear+append OR setSize leaves one). So the
    builder sets Refreshoninputchange=OFF — writes never trigger it —
    and this function finishes with ONE explicit Refresh pulse, so the
    lister only ever redraws on a complete, valid table.

    The RUNNING row's status is a block-character bar that fills as
    the encode progresses. A 4th 'progress' column (0-1) drives the
    per-row background TOP (bar behind the file name — JP).
    """
    t = panel().op("queue_table")
    if t is None:
        # The builder creates queue_table at the VCON level (next to the
        # panel), not inside the panel — a path-lookup here silently
        # returned None, which is why the queue table never redrew.
        t = op.vcon.op("queue_table")
    if t is None:
        return
    # current encode progress, if a job is running
    try:
        prog = float(op.vcon.par.Progress.eval())
    except Exception:
        prog = 0.0
    rows = [["file", "status", "progress", "path"]]
    for i, item in enumerate(_queue, 1):
        status = item["status"]
        row_prog = 0.0
        if status == "running":
            status = _bar_text(prog)
            row_prog = prog
        elif status == "done":
            row_prog = 1.0
        rows.append([os.path.basename(item["input"]),
                     status, f"{row_prog:.4f}",
                     item["input"]])
    # DRIVER table (3 cols: file, status, progress — progress is the
    # bar-TOP driver read by INDEX from col 2; the lister reads the
    # DISPLAY table below, so progress never shows. Col 3 = FULL PATH
    # — the durable copy the module rebuilds _queue from after a
    # recompile; the lister never sees it.)
    try:
        cur_r, cur_c = t.numRows, t.numCols
    except Exception:
        cur_r, cur_c = 0, 3
    big = max(cur_r, len(rows))
    try:
        t.setSize(big, 4)
    except Exception:
        pass
    for r in range(big):
        row = rows[r] if r < len(rows) else ["", "", "", ""]
        for c in range(4):
            try:
                t[r, c] = row[c]
            except Exception:
                pass
    if big > len(rows):
        try:
            t.setSize(len(rows), 4)
        except Exception:
            pass

    # DISPLAY table (2 cols: file, status — what the lister reads, so
    # auto-define makes exactly those two columns; NO number column,
    # NO progress column, per JP).
    d = op.vcon.op("queue_display")
    if d is not None:
        drows = [[r[0], r[1]] for r in rows]
        try:
            dcur = d.numRows
        except Exception:
            dcur = 0
        dbig = max(dcur, len(drows))
        try:
            d.setSize(dbig, 2)
        except Exception:
            pass
        for r in range(dbig):
            row = drows[r] if r < len(drows) else ["", ""]
            for c in range(2):
                try:
                    d[r, c] = row[c]
                except Exception:
                    pass
        if dbig > len(drows):
            try:
                d.setSize(len(drows), 2)
            except Exception:
                pass
    # ONE refresh, on our schedule, on a complete table.
    q = panel().op("queue")
    if q is not None:
        try:
            q.par.Refresh.pulse()
        except Exception:
            pass
    _update_scrollbar()
    _update_start_button()


def _update_scrollbar():
    """Show the lister's vertical scrollbar only when rows overflow.

    The lister has no 'auto' scrollbar mode (vscrollbar is off/on) and
    exposes no row height anywhere, so overflow is computed from a
    measured row height (22px, JP) — adjust _ROW_H if the bar appears
    a row early or late.
    """
    q = panel().op("queue")
    if q is None:
        return
    try:
        # +1 for the header row, which occupies list space too
        needed = (len(_queue) + 1) * _ROW_H
        q.par.vscrollbar.val = needed > float(q.par.h.eval())
    except Exception as exc:
        _tick_err("scrollbar", exc)


def _update_start_button():
    """START button: green when the queue has items, gray when empty."""
    w = widget("start_b")
    if w is None:
        return
    has_items = len(_queue) > 0
    try:
        if has_items:
            w.par.Buttonofffacecolorr.val = 0.0
            w.par.Buttonofffacecolorg.val = 0.395
            w.par.Buttonofffacecolorb.val = 0.07
        else:
            w.par.Buttonofffacecolorr.val = 0.25
            w.par.Buttonofffacecolorg.val = 0.25
            w.par.Buttonofffacecolorb.val = 0.25
    except Exception:
        pass


def _mark_running(output_path):
    for item in _queue:
        if item["output"] == output_path and item["status"] == "queued":
            item["status"] = "running"
            break
    _refresh_queue()


def RemoveSelected():
    """remove_b (JP 2026-09-14): remove the SELECTED queue row.

    The selection is tracked by input PATH, set on every row click; a
    module recompile wipes the module globals, so the queue list
    rebuilds from the table first when it is empty. Guards:
      - a RUNNING row is never removed (the controller owns it; the
        job would finish writing to an output the queue no longer
        tracks) — STOP cancels instead
      - no selection: said so in the textport, nothing happens
    """
    global _queue, _selected_path
    if not _queue:
        _queue_rebuild_from_table()
    if not _queue:
        note("nothing to remove — the queue is empty")
        return
    if not _selected_path:
        note("no row selected — click a file first")
        return
    tgt = None
    for it in _queue:
        if it["input"] == _selected_path:
            tgt = it
            break
    if tgt is None:
        note(f"selected item no longer in the queue: "
             f"{os.path.basename(_selected_path)}")
        _selected_path = None
        return
    if tgt["status"] == "running":
        note(f"{os.path.basename(_selected_path)} is encoding — "
             "STOP cancels it; removing mid-encode is refused")
        return
    idx = _queue.index(tgt)
    _queue.remove(tgt)
    # The lister keeps its highlight on the same ROW INDEX, which now
    # holds the next item, but moving it itself fires no onSelectRow —
    # so clearing here left a highlighted row that delete refused to
    # touch (JP 2026-09-15). Track what the user can see.
    if _queue:
        _selected_path = _queue[min(idx, len(_queue) - 1)]["input"]
    else:
        _selected_path = None
    _refresh_queue()
    _sync_lister_selection()
    PreviewOutput()          # the preview follows queue state
    SyncStatusField()
    note(f"removed {os.path.basename(tgt['input'])} — selection now "
         f"{os.path.basename(_selected_path) if _selected_path else 'none'}")


def _sync_lister_selection():
    """Push _selected_path to the lister's own highlight so the visible
    selection and the tracked one cannot disagree.

    SelectRow/SelectedRows are PROBE-VERIFIED on this build (JP
    2026-09-15); a failure is still non-fatal because the lister's own
    highlight already sits on the right row index after a remove.
    """
    q = panel().op("queue") if panel() is not None else None
    if q is None:
        return
    row = None
    if _selected_path:
        for i, it in enumerate(_queue):
            if it["input"] == _selected_path:
                row = i
                break
    try:
        e = q.ext.ListerExt
    except Exception:
        return
    try:
        if row is None:
            e.SelectedRows = []
        else:
            e.SelectRow(row)
    except Exception as exc:
        note(f"  lister selection sync skipped: {exc}")


def _mark_done(output_path):
    """Mark the queue row whose output matches; enqueue the next job."""
    done = False
    for item in _queue:
        if item["output"] == output_path:
            item["status"] = "done"
            done = True
    if done:
        _refresh_queue()
        _run_next()
        # Preview refresh (JP 2026-09-14): when this was the LAST job,
        # the queue is all-done — the preview must fall back to the
        # empty-queue message, not keep showing the finished file's
        # derived output.
        try:
            PreviewOutput()
        except Exception:
            pass


def _on_job_done(output_path):
    """Poll-based completion hook for the panel: refresh + run next."""
    _mark_done(output_path)


def onFrame():
    """Panel-level Execute DAT tick: feed the batch loop + auto-refresh.

    When the controller goes idle and queue rows remain queued, submit the
    next job. When a running row's output file exists and the controller
    is idle, the job finished — mark done, then next.

    The PANEL bar shows BATCH progress (item N of M — JP), not the
    current file's 0-1; the tick computes it and writes the fill width
    directly (no expression needed). The LISTER row shows the current
    file's own progress as a block bar.
    """
    global _last_src_fps, _tick_alive, _last_fps_key
    try:
        e = ext()
    except Exception:
        return

    if not _tick_alive:
        _tick_alive = True
        note("panel tick alive (batch feeding + progress active)")

    # 0) one-shot: clear the lister's stale init error — and ONLY that one.
    # ListerExt.Refresh runs while the operator is being CREATED (during
    # loadTox/copy, and again on every .toe open), so it always sees a
    # blank table and stores "Blank header in col 0". Nothing can link a
    # table early enough to prevent it. Blanket-clearing would also hide
    # real faults, so the stored text is checked first: anything that
    # is NOT this known error is REPORTED and left on the node.
    global _lister_errs_cleared
    if not _lister_errs_cleared:
        _lister_errs_cleared = True
        try:
            q_ = panel().op("queue")
            if q_ is not None:
                # scriptErrors() is the counterpart to clearScriptErrors();
                # errors() is a different channel and comes back empty for
                # this, which is why gating on it alone stopped the clear.
                txt = ""
                for meth in ("scriptErrors", "errors"):
                    fn = getattr(q_, meth, None)
                    if callable(fn):
                        try:
                            txt = fn() or ""
                        except Exception:
                            txt = ""
                        if txt:
                            break
                if txt and "Blank header in col 0" not in txt:
                    note(f"lister error left in place (not the known "
                         f"init error): {txt.strip()[:200]}")
                else:
                    q_.clearScriptErrors()
        except Exception as exc:
            _tick_err("clear lister errors", exc)

    # 1) drive the panel bar with batch progress, every frame
    try:
        fill = panel().op("prog_fill")
        if fill is not None:
            fill.par.w.val = _batch_progress() * 620
    except Exception as exc:
        _tick_err("progress bar", exc)

    # 1b) SOURCE-mode FPS display follows the running job's rate, and
    # — when idle — the selected/queued file, so it also has to react
    # to the queue emptying or filling and to jobs starting/ending.
    try:
        if _fps_source_mode():
            try:
                busy = bool(ext().is_busy)
            except Exception:
                busy = False
            key = (_source_fps(), _selected_path, len(_queue), busy)
            if key != _last_fps_key:
                _last_fps_key = key
                _last_src_fps = key[0]
                SyncFpsField()
    except Exception as exc:
        _tick_err("fps display", exc)

    # 1c) STATUS label (over the progress bar) names the file being
    # written and counts its frames; the OUTPUT field keeps describing
    # the source and is only re-read when a job ends.
    global _showing_activity
    try:
        SyncStatusField()
        if e.is_busy:
            _showing_activity = True
        elif _showing_activity:
            _showing_activity = False
            PreviewOutput()
    except Exception as exc:
        _tick_err("activity text", exc)

    # 1d) preview refresh for the just-emptied moment (mutation points
    # call PreviewOutput directly; this catches paths that don't)
    try:
        if not _queue:
            d_ = op.vcon.op("queue_display")
            if d_ is not None and d_.numRows > 1:
                PreviewOutput()
    except Exception as exc:
        _tick_err("preview refresh", exc)

    # 1e) background audio-support install, if one is running
    try:
        if _install is not None:
            _install_tick()
    except Exception as exc:
        _tick_err("audio install", exc)

    # 1f) help button health indicator: blue when ready, pulsing red
    # when audio support is missing. Checked every ~60 frames (cached).
    try:
        _update_health_button()
    except Exception as exc:
        _tick_err("health button", exc)

    # 2) feed the loop when idle
    if e.is_busy:
        _refresh_queue()     # keeps the running row's bar moving
        return
    # finished detection: a running row whose output now exists
    for item in list(_queue):
        if item["status"] == "running" and os.path.exists(item["output"]):
            item["status"] = "done"
    # JP: finished items are REMOVED from the list (the bar + the row
    # both clear — no stale 'done' rows)
    global _batch_started
    remaining = [it for it in _queue if it["status"] != "done"]
    if len(remaining) < len(_queue):
        _queue[:] = remaining
    # close the batch gate + reset the bar when the queue empties
    if not _queue:
        _batch_started = False
        try:
            op.vcon.par.Progress.val = 0.0
        except Exception:
            pass
        # Re-run the preview HERE: the activity block above already fired
        # its one PreviewOutput() while the finished row was still in the
        # queue, so it rendered that row's path. This is the first moment
        # the queue is actually empty.
        PreviewOutput()
    _run_next()
    _refresh_queue()


# ---------------------------------------------------------------------
# Audio support setup (ffmpeg via imageio-ffmpeg)
# ---------------------------------------------------------------------
#
# TD's embedded Python cannot see pip packages installed elsewhere, and
# we do not ship a 60MB ffmpeg binary inside the toe. So audio muxing
# needs imageio-ffmpeg fetched ONCE. InstallAudioSupport() does that
# without a terminal: it runs pip into a vCon-owned folder in the user's
# data directory — no admin rights, no writing inside the TD app bundle
# (which needs admin on Windows and breaks code signing on macOS), and
# it survives TouchDesigner updates.

def _vcon_libs_dir():
    """Where vCon keeps downloaded Python packages."""
    return os.path.join(_vcon_data_dir(), "pylibs")


def _ffmpeg_binary():
    """The ffmpeg binary vCon can currently use, or None."""
    import glob
    import shutil
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    home = os.path.expanduser("~")
    for pat in (
            f"{_vcon_libs_dir()}/imageio_ffmpeg/binaries/ffmpeg-*",
            f"{home}/.local/pipx/venvs/*/lib/python*/site-packages/"
            "imageio_ffmpeg/binaries/ffmpeg-*",
            f"{home}/Library/Python/*/lib/python/site-packages/"
            "imageio_ffmpeg/binaries/ffmpeg-*"):
        for cand in sorted(glob.glob(pat), reverse=True):
            if os.path.isfile(cand):
                return cand
    return shutil.which("ffmpeg")


def _python_for_pip():
    """An interpreter that can run pip, preferring TouchDesigner's own.

    sys.executable inside TD is the TouchDesigner BINARY, not python —
    running `sys.executable -m pip` would launch a second TD. So the
    interpreter is located explicitly.
    """
    import subprocess
    cands = []
    for prefix in (sys.prefix, getattr(sys, "base_prefix", "")):
        if not prefix:
            continue
        if os.name == "nt":
            cands += [os.path.join(prefix, "python.exe")]
        else:
            cands += [os.path.join(prefix, "bin", "python3.11"),
                      os.path.join(prefix, "bin", "python3")]
    import shutil
    for name in (("py", "python", "python3") if os.name == "nt"
                 else ("python3", "python")):
        found = shutil.which(name)
        if found:
            cands.append(found)
    for cand in cands:
        if not cand or not os.path.isfile(cand):
            continue
        try:
            rc = subprocess.run([cand, "-m", "pip", "--version"],
                                capture_output=True, timeout=30).returncode
            if rc == 0:
                return cand
        except Exception:
            continue
    return None


def _toe_version():
    """Version baked into this .toe (the controller's CONTROLLER_VERSION)."""
    try:
        return op.vcon.op('vcon_controller').module.CONTROLLER_VERSION
    except Exception:
        return "unknown"


def _cli_version():
    """Version of the installed tdxvcon command-line tool, if any.

    TD's Python cannot import it, so the version is read off the
    dist-info directory name in the pipx venv instead.
    """
    import glob
    import re
    try:
        from importlib.metadata import version
        return version("tdxvcon")
    except Exception:
        pass
    home = os.path.expanduser("~")
    pats = [
        f"{home}/.local/pipx/venvs/tdxvcon/lib/python*/site-packages/"
        "tdxvcon-*.dist-info",
        # older pipx on Windows keeps venvs under LOCALAPPDATA
        os.path.join(os.environ.get("LOCALAPPDATA") or home, "pipx", "pipx",
                     "venvs", "tdxvcon", "Lib", "site-packages",
                     "tdxvcon-*.dist-info"),
        f"{home}/.local/pipx/venvs/tdxvcon/Lib/site-packages/"
        "tdxvcon-*.dist-info",
    ]
    for pat in pats:
        for hit in glob.glob(pat):
            m = re.search(r"tdxvcon-([^-/\\]+)\.dist-info", hit)
            if m:
                return m.group(1)
    return None


def _version_tuple(v):
    """'0.1.10' -> (0, 1, 10) for ordering; non-numeric parts sort last."""
    out = []
    for part in str(v).split("."):
        try:
            out.append(int(part))
        except ValueError:
            out.append(-1)
    return tuple(out)


def _latest_release(timeout=2.0):
    """Newest tdxvcon version on PyPI, or None if the check fails.

    Called ONLY when the setup dialog opens — never on a timer and never
    at startup. Short timeout so a slow or absent network cannot stall
    TouchDesigner's UI, and failure is silent by design: someone working
    offline should not be shown an error they cannot act on.
    """
    try:
        import json as _j
        import urllib.request
        url = "https://pypi.org/pypi/tdxvcon/json"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return _j.loads(resp.read().decode("utf-8"))["info"]["version"]
    except Exception:
        return None


def _ffmpeg_version():
    """Version string of the ffmpeg vCon would use, or None."""
    exe = _ffmpeg_binary()
    if not exe:
        return None
    try:
        import subprocess
        out = subprocess.run([exe, "-version"], capture_output=True,
                             timeout=10).stdout.decode("utf-8", "replace")
        first = out.splitlines()[0] if out else ""
        # "ffmpeg version 7.1 Copyright ..." -> "7.1"
        parts = first.split()
        if len(parts) >= 3 and parts[0] == "ffmpeg":
            return parts[2]
        return first[:40] or None
    except Exception:
        return None


def ShowSetupDialog():
    """SETUP button: a modal dialog with live status + actions.

    Uses TD's native ui.messageBox so the information reaches the user
    where they are looking, instead of the textport they may never open.
    Falls back to textport output if messageBox is unavailable.
    """
    exe = _ffmpeg_binary()
    dest = _vcon_libs_dir()
    py = _python_for_pip() or ("py" if os.name == "nt" else "python3")
    ready = exe is not None
    cli_ver = _cli_version()
    ff_ver = _ffmpeg_version()
    toe_ver = _toe_version()
    latest = _latest_release()
    lines = []
    # An available update stays at the TOP — it is the one thing here
    # that is time-sensitive. The version list itself goes last.
    if latest is not None and _version_tuple(latest) > _version_tuple(toe_ver):
        lines += [
            f"UPDATE AVAILABLE: {latest}  (this .toe is {toe_ver})",
            "  pipx install:  pipx upgrade tdxvcon, then reopen the .toe",
            "  given a .toe:  ask for an updated copy",
            "",
        ]
    lines += [
        "AUDIO SUPPORT:  " + ("READY" if ready else "NOT INSTALLED"),
        "",
    ]
    if ready:
        lines += [f"ffmpeg: {exe}"]
    else:
        lines += [
            "Encodes will be VIDEO ONLY until this is installed.",
            "",
            "TouchDesigner's frame-by-frame recording cannot write",
            "audio, so vCon muxes the source audio in afterwards with",
            "ffmpeg. ffmpeg comes from the imageio-ffmpeg package",
            "(~30MB), which is not bundled in the .toe.",
            "",
            "Press INSTALL NOW to fetch it automatically. It installs to",
            "vCon's own folder in your user Library — no admin rights",
            "needed, no files are written into the TouchDesigner",
            "application folder, and it survives TouchDesigner updates.",
        ]
    lines += [
        "",
        "Install folder:",
        f"  {dest}",
        "",
        "Manual install (Terminal on macOS, cmd/PowerShell on Windows):",
        f'  "{py}" -m pip install --upgrade --target "{dest}" imageio-ffmpeg',
        "",
        "vCon also finds ffmpeg from:",
        "  - pipx install tdxvcon   (the vCon command-line tool)",
        "  - any system ffmpeg on PATH",
        "",
        "--- Command-line usage ---",
        "Install the CLI:  pipx install tdxvcon",
        "Transcode:  vcon -i input.mov -c notchlc output.mov",
        "List codecs:  vcon -codecs",
        "Diagnostics:  vcon -doctor",
        "",
        "--- Versions ---",
        f"  vCon (this .toe) : {toe_ver}",
        f"  vcon CLI tool    : {cli_ver or 'not installed'}",
        f"  ffmpeg           : {ff_ver or 'not installed'}",
    ]
    if latest is not None:
        lines += [f"  latest on PyPI   : {latest}"]
    msg = "\n".join(lines)
    manual_cmd = (f'"{py}" -m pip install --upgrade '
                  f'--target "{dest}" imageio-ffmpeg')
    buttons = (["Re-check", "Copy Command", "Close"] if ready
               else ["Install Now", "Copy Command", "Close"])
    try:
        choice = ui.messageBox("vCon — Setup & Help", msg, buttons=buttons)
    except TypeError:
        # Older builds: messageBox without a buttons argument.
        try:
            ui.messageBox("vCon — Setup & Help", msg)
        except Exception:
            note(msg)
        return
    except Exception:
        # No messageBox at all (headless): textport is the fallback.
        note(msg)
        return
    if choice == 0:
        if ready:
            AudioSupportStatus()
        else:
            InstallAudioSupport()
    elif choice == 1:
        try:
            ui.clipboard = manual_cmd
            note("manual install command copied to the clipboard:")
            note(f"  {manual_cmd}")
            ui.messageBox(
                "vCon — Command Copied",
                "The manual install command is on your clipboard.\n\n"
                "Paste it into Terminal (macOS) or cmd/PowerShell\n"
                "(Windows) and press Enter:\n\n"
                f"{manual_cmd}")
        except Exception:
            note("clipboard unavailable — manual install command:")
            note(f"  {manual_cmd}")


def AudioSupportStatus():
    """Report whether audio muxing is ready, and how to fix it if not."""
    exe = _ffmpeg_binary()
    if exe:
        note(f"audio support: READY — ffmpeg at {exe}")
        return True
    note("audio support: NOT INSTALLED — encodes will be video-only.")
    note("  Press the SETUP button on the panel for instructions.")
    return False


def ShowAudioSetupHelp():
    """Print the manual install steps for this platform (savvy users)."""
    dest = _vcon_libs_dir()
    py = _python_for_pip() or ("py" if os.name == "nt" else "python3")
    note("-" * 64)
    note("MANUAL AUDIO SETUP — vCon muxes audio with ffmpeg, supplied")
    note("by the imageio-ffmpeg package. Install it into vCon's own")
    note("folder (no admin rights, nothing written inside TouchDesigner):")
    note("")
    note(f'  "{py}" -m pip install --upgrade --target "{dest}" imageio-ffmpeg')
    note("")
    note("Run that in Terminal (macOS) or cmd/PowerShell (Windows).")
    note("Alternatives that vCon also detects automatically:")
    note("  • pipx install tdxvcon      (the vCon command-line tool)")
    note("  • a system ffmpeg on PATH   (brew install ffmpeg, etc.)")
    note("Then click CHECK AUDIO, or restart TouchDesigner.")
    note("-" * 64)


def InstallAudioSupport():
    """One-click audio support: pip-install imageio-ffmpeg in the background.

    Non-blocking — pip downloads ~30MB and would freeze TD's UI if run
    synchronously. Progress is polled by the panel tick and narrated to
    the textport so the user can see exactly what is happening.
    """
    global _install
    if _install is not None:
        note("audio install: already running — watch the OUTPUT field")
        return
    exe = _ffmpeg_binary()
    if exe:
        note(f"audio support already installed — ffmpeg at {exe}")
        return
    py = _python_for_pip()
    if py is None:
        note("audio install: no Python with pip was found.")
        note("  TouchDesigner normally ships one; if this persists, use")
        note("  the manual steps below.")
        ShowAudioSetupHelp()
        return
    dest = _vcon_libs_dir()
    try:
        os.makedirs(dest, exist_ok=True)
    except Exception as exc:
        note(f"audio install: cannot create {dest}: {exc}")
        return
    log_path = os.path.join(dest, "install.log")
    cmd = [py, "-m", "pip", "install", "--upgrade",
           "--target", dest, "imageio-ffmpeg"]
    note("-" * 64)
    note("INSTALLING AUDIO SUPPORT")
    note(f"  interpreter : {py}")
    note(f"  installing  : imageio-ffmpeg (ffmpeg binary, ~30MB download)")
    note(f"  destination : {dest}")
    note("  This runs in the background — TouchDesigner stays responsive.")
    note("-" * 64)
    try:
        import subprocess
        log = open(log_path, "wb")
        proc = subprocess.Popen(cmd, stdout=log, stderr=log,
                                stdin=subprocess.DEVNULL)
    except Exception as exc:
        note(f"audio install: could not start pip: {exc}")
        ShowAudioSetupHelp()
        return
    _install = {"proc": proc, "log": log, "log_path": log_path,
                "dest": dest, "t0": time.time()}
    _set_output_text("Installing audio support — downloading ffmpeg…")


def _update_health_button():
    """Drive the help button color: blue when ready, pulsing red when not.

    Caches the ffmpeg check so we don't glob every frame — re-checks
    every 60 frames. The pulse uses absTime.frame so it runs without
    any extra CHOP or timer.
    """
    global _health_check_frame, _health_ok
    w = widget("help_b")
    if w is None:
        return
    frame = absTime.frame
    if frame - _health_check_frame >= 60 or _health_check_frame < 0:
        _health_check_frame = frame
        _health_ok = _ffmpeg_binary() is not None
    if _health_ok:
        w.par.Buttonofffacecolorr.val = 0.0
        w.par.Buttonofffacecolorg.val = 0.3666667
        w.par.Buttonofffacecolorb.val = 0.5
    else:
        # sine pulse at ~2Hz (60fps / 15 ≈ 4Hz, halved by abs)
        import math
        pulse = 0.5 + 0.5 * math.sin(frame * 6.28 / 60)
        r = 0.4 + 0.4 * pulse
        w.par.Buttonofffacecolorr.val = r
        w.par.Buttonofffacecolorg.val = 0.0
        w.par.Buttonofffacecolorb.val = 0.0


def _install_tick():
    """Poll the background pip install; narrate the result."""
    global _install
    inst = _install
    if inst is None:
        return
    rc = inst["proc"].poll()
    if rc is None:
        if time.time() - inst["t0"] > 600:
            try:
                inst["proc"].kill()
            except Exception:
                pass
            note("audio install: timed out after 10 minutes.")
            ShowAudioSetupHelp()
            _install = None
        else:
            secs = int(time.time() - inst["t0"])
            _set_output_text(f"Installing audio support — {secs}s elapsed…")
        return
    try:
        inst["log"].close()
    except Exception:
        pass
    _install = None
    if rc == 0:
        exe = _ffmpeg_binary()
        if exe:
            note("-" * 64)
            note("AUDIO SUPPORT INSTALLED")
            note(f"  ffmpeg: {exe}")
            note("  Encodes will now carry audio. Nothing else to do.")
            note("-" * 64)
            _set_output_text("Audio support installed — ready to encode")
            try:
                ui.messageBox(
                    "vCon — Audio Support Installed",
                    "ffmpeg is now available:\n\n"
                    f"{exe}\n\n"
                    "Encodes will carry the source audio from now on.")
            except Exception:
                pass
        else:
            note("audio install: pip succeeded but no ffmpeg binary was "
                 "found afterwards.")
            ShowAudioSetupHelp()
        PreviewOutput()
        return
    tail = ""
    try:
        with open(inst["log_path"], "r", errors="replace") as fh:
            tail = fh.read()[-800:]
    except Exception:
        pass
    note(f"audio install FAILED (pip exit code {rc}):")
    if tail:
        note(tail)
    ShowAudioSetupHelp()
    _set_output_text("Audio install failed — see textport for details")
    try:
        ui.messageBox(
            "vCon — Audio Install Failed",
            f"pip exited with code {rc}.\n\n"
            f"{tail[-400:] if tail else '(no output captured)'}\n\n"
            "The manual command has been printed to the textport.")
    except Exception:
        pass


# ---------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------

def onDragDrop(info):
    """Drop Script entry: files/folders dropped anywhere on the panel.

    DESIRED WORKFLOW (JP): drops enqueue DIRECTLY into the batch queue —
    a file adds one row; a folder adds every movie under it (recursive,
    same scan as folder-in-SOURCE + START). Also mirrors the drop into
    the SOURCE widget so the OUTPUT preview derives. The tick then feeds
    rows to the encoder one at a time; no START needed unless queued
    items should re-run.
    """
    items = info.get("dropItems") if isinstance(info, dict) else None
    if not items:
        try:
            items = info["dropItems"]
        except Exception:
            return
    if not items:
        return

    paths = []
    for it in items:
        p = it if isinstance(it, str) else it.get("path", str(it))
        if p:
            paths.append(p)
    if not paths:
        return

    added = 0
    last_added = None
    for path in paths:
        if os.path.isdir(path):
            for inp, rel in _scan_movies(path):
                out = _unique_output(_derive_output(
                    inp, _dst_dir(), _val("codec_dd") or "notchlc",
                    _val("subtype_dd")))
                _queue.append({"input": inp, "output": out,
                               "status": "queued", "rel": rel})
                added += 1
                last_added = inp
        elif os.path.isfile(path):
            out = _unique_output(_derive_output(
                path, _dst_dir(), _val("codec_dd") or "notchlc",
                _val("subtype_dd")))
            _queue.append({"input": path, "output": out,
                           "status": "queued",
                           "rel": os.path.basename(path)})
            added += 1
            last_added = path

    if added:
        _refresh_queue()
        PreviewOutput(last_added)   # the newest drop, not _queue[0]
        SyncStatusField()
        note(f"dropped {added} file(s) — press START to encode")
    else:
        note("no movie files in the drop")


def _dst_dir():
    """The destination folder from the DESTINATION widget.

    The widget is a FOLDER browser — its Value0 is a folder path, not a
    file path. os.path.dirname would strip the last component (the actual
    target folder) and write to its PARENT — the file appears in the
    wrong place. If the path is a directory, use it directly; if not
    (e.g. a stale captured file path), fall back to dirname.
    """
    dst = _val("destination")
    if not dst:
        return None
    if os.path.isdir(dst):
        return dst
    d = os.path.dirname(dst)
    return d if d else None


def AddFiles():
    """The + button: open a file dialog and APPEND to the queue.

    JP: there was no way to add files to the lister via a dialog — the
    SOURCE browser only ever holds ONE path. ui.chooseFile is the
    documented native dialog (start=None opens at last location;
    fileTypes filters). Multi-select isn't available in one call on
    all builds, so the button can be pressed repeatedly; folder adds
    come through drag/drop or SOURCE-browse + START.
    """
    try:
        path = ui.chooseFile(start=None, fileTypes=list(MOVIE_EXTS),
                             title="Add movie to the queue")
    except Exception as exc:
        note(f"file dialog failed: {exc}")
        return
    if not path:
        return
    if os.path.isfile(path):
        codec = _val("codec_dd") or "notchlc"
        out = _unique_output(_derive_output(path, _dst_dir(), codec,
                                            _val("subtype_dd")))
        _queue.append({"input": path, "output": out,
                       "status": "queued",
                       "rel": os.path.basename(path)})
        _refresh_queue()
        PreviewOutput()   # the preview follows queue state (JP 2026-09-14)
        note(f"added {os.path.basename(path)} — press START to encode")
    elif os.path.isdir(path):
        n = 0
        for inp, rel in _scan_movies(path):
            out = _unique_output(_derive_output(
                inp, _dst_dir(), _val("codec_dd") or "notchlc",
                _val("subtype_dd")))
            _queue.append({"input": inp, "output": out, "status": "queued",
                           "rel": rel})
            n += 1
        _refresh_queue()
        PreviewOutput()   # the preview follows queue state (JP 2026-09-14)
        note(f"added {n} file(s) from folder — press START to encode")


def NormalizeDestination():
    """DESTINATION stays a FOLDER path (its browser widget requires it).

    JP: the derived FILE name should not be crammed into the folder
    field (the folder browser re-normalizes full paths away — that's
    why the filename never showed). The filename lives in the
    read-only OUTPUT field (output_l), updated by PreviewOutput().
    """
    try:
        dst_w = widget("destination")
        if dst_w is None:
            return
        v = dst_w.par.Value0.eval()
        if v and os.path.isfile(v):
            dst_w.par.Value0.val = os.path.dirname(v)
    except Exception as exc:
        note(f"destination display: {exc}")


def note(text):
    """Panel-local feedback line — printed to the textport."""
    print(f"[panel] {text}")


def pixel_formats_for(codec, subtype=None):
    """Per-subtype pixel formats (ProRes menus differ per subtype)."""
    if codec == "prores":
        return PRORES_PIXEL_FORMATS.get(subtype, ["yuv4228bit"])
    return CODECS.get(codec, {}).get("pixel_formats", ["rgb"])
