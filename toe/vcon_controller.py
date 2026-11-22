"""vcon controller — the brain inside transcoder.toe.

Runs as a module DAT inside TouchDesigner. Owns the JSON-lines TCP server,
receives submit jobs, and drives Movie File In → Movie File Out frame-stepped
non-realtime encoding. The front-end (vcon) never sets codec parameters
directly — it sends resolved values; this controller applies them.

Operator layout expected (created by build_network.py):

    /project1/vcon            (Base COMP, the whole app)
    ├── moviein               (Movie File In TOP)
    ├── movieout              (Movie File Out TOP, input wired to moviein)
    ├── tcpip                 (TCPIP DAT, server mode, port 7999)
    ├── msgs                  (Text DAT — received lines land here)
    └── vcon_controller       (Text DAT — this module)

Callbacks used:
    tcpip onReceive  → routed by the DAT's callback via ext.Vcon.onReceive
    execute DAT      → per-frame tick via ext.Vcon.onFrame

Protocol (v1, matching vcon.protocol):
    ← {"type": "hello", "version": 1}              (sent on startup)
    → {"type": "submit", "id", "input", "output", "params"}
    ← {"type": "accepted", "id", "total_frames"}
    ← {"type": "progress", "id", "frame", "total_frames"}
    ← {"type": "done", "id", "path", "total_frames", "seconds"}
    ← {"type": "error", "id", "message", "code"}

    → {"type": "cancel", "id"}
    ← {"type": "error", "id", "message": "cancelled", "code": "cancelled"}

    → {"type": "pause", "id"}   (id "*" = whatever is running)
    ← {"type": "paused", "id", "frame", "total_frames"}
    → {"type": "resume", "id"}
    ← {"type": "resumed", "id", "frame", "total_frames"}

    submit params may carry "resolution" ("WxH") and "fit"
    (stretch|fitwidth|fitheight|cover) — the toe inserts a Fit TOP when
    resolution != "auto".
"""

import json
import os
import sys
import time

#: Controller build identifier. The toe's custom "Version" parameter
#: references this value so the UI follows the embedded controller.
#: Keep in step with vcon.__version__ (tests assert this).
CONTROLLER_VERSION = "1.0.0"

PROTOCOL_VERSION = 1
#: Default TCP port. Overridable per-instance via the COMP's Tcpport custom
#: parameter, so two vCon components can coexist in one project.
PORT = 7999
IDLE_QUIT_SECONDS = 300  # safety net: exit TD when idle this long

#: Share of the progress bar given to the encode; the audio mux fills
#: the remainder, so a job's bar rises monotonically across both phases.
_ENCODE_SHARE = 0.92


class VconExt:
    """The transcoder controller.

    A COMP extension (docs: Extensions — the Extension Object parameter holds
    code that returns the object, most commonly `MyExt(me)`).

    NOTHING here may hardcode an absolute operator path: the component is
    meant to be dropped into someone else's project at any location, and
    renamed to suit. All child operators are resolved relative to
    `self.ownerComp`, so `/project1/vcon`, `/myProj/tools/vCon` and a renamed
    `vcon1` all work.
    """

    def __init__(self, ownerComp):
        self.ownerComp = ownerComp
        self.job = None          # active job dict
        self.frame = 0
        self.total = 0
        self.t0 = 0.0
        self.state = "idle"      # idle | loading | encoding | finishing | muxing | extracting
        self.last_activity = time.time()
        #: frame counters for the state machine driven by onFrame()
        self._loading_ticks = 0
        self._finishing_ticks = 0
        self._ticks = 0
        self.seconds_taken = 0.0
        self.last_error = None
        #: Set by onDestroyTD so a re-inited (replaced) extension stops
        #: driving the network. See the docs' re-init gotcha.
        self._destroyed = False
        #: Latched once the idle backstop has asked TD to quit. Without this
        #: the per-frame tick re-asks ~60x/second and buries the user in
        #: modal dialogs.
        self._quit_requested = False
        #: Paused mid-encode (protocol "pause"). While True, _encode_tick
        #: skips writing frames but keeps cooking so "resume" continues
        #: from the exact next frame. "*" targets whatever is running.
        self._paused = False
        #: Live background audio-mux state (see _mux_start), or None.
        self._mux = None
        #: fps resampling (see _plan_frame_rate): source frames available
        #: and how far the source advances per written output frame.
        self._src_total = 0
        self._src_step = 1.0
        #: ORPHAN-CLEANUP ARMING. True only when this TouchDesigner process
        #: was LAUNCHED BY vCon (the front-end sets VCON_LAUNCHED=1 in the
        #: subprocess environment). A session the user opened themselves
        #: never has the variable and can therefore never be quit by us —
        #: process provenance, not a preference. This replaces an earlier
        #: user-facing toggle, which put the decision in the wrong place.
        self._orphan_cleanup_armed = (
            os.environ.get("VCON_LAUNCHED") == "1"
        )

    # ------------------------------------------------------------------
    # Child operator resolution (relative — never absolute)
    # ------------------------------------------------------------------

    def child(self, name):
        """A child operator of this component, by name.

        Uses the COMP's op() member, which searches relative to the
        component's inside — so it is location-independent by construction.
        """
        op_ = self.ownerComp.op(name)
        if op_ is None:
            raise RuntimeError(
                f"vCon: child operator '{name}' not found inside "
                f"{self.ownerComp.path} — the component looks incomplete"
            )
        return op_

    @property
    def moviein(self):
        return self.child("moviein")

    @property
    def fit(self):
        """Fit TOP — present when the toe was built with resolution support.
        Absent in older toes; resolution params are then ignored (logged)."""
        return self.ownerComp.op("fit")

    @property
    def movieout(self):
        return self.child("movieout")

    @property
    def info(self):
        return self.child("info")

    @property
    def tcpip(self):
        return self.child("tcpip")

    # ------------------------------------------------------------------
    # Settings (custom parameters, with safe fallbacks)
    # ------------------------------------------------------------------

    @property
    def port(self):
        """TCP port, from the component's Tcpport custom parameter if present."""
        try:
            return int(self.ownerComp.par.Tcpport.eval())
        except Exception:
            return PORT

    def _set_status(self, text):
        """Reflect state into the COMP's Status parameter, if it exists."""
        try:
            self.ownerComp.par.Status.val = text
        except Exception:
            debug(f"vCon status: {text}")

    def _set_progress(self, frac):
        """Progress par: 0..1 for a panel slider. Encode fills 0..0.92,
        the audio mux fills the rest, so the bar never runs backwards."""
        try:
            self.ownerComp.par.Progress.val = min(1.0, max(0.0, float(frac)))
        except Exception:
            pass  # par absent (older toe) — status text still shows

    # ------------------------------------------------------------------
    # Scheduling helper
    # ------------------------------------------------------------------

    def onFrame(self):
        """Per-frame tick, called by the Execute DAT every frame.

        Deliberately frame-driven rather than self-scheduling: relying on
        run(..., delayFrames=N) silently stopped firing entirely, leaving
        jobs stuck with no error. An Execute DAT is TouchDesigner's standard
        mechanism for per-frame work and has no such ambiguity.

        Errors are REPORTED, never swallowed: an invisible exception here
        leaves a job stuck in 'loading' forever with no feedback at all.
        """
        self._ticks += 1
        try:
            self._tick()
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            debug(f"vcon onFrame error in {self.state}: {detail}")
            if self.state != "idle":
                self._fail(f"controller error ({self.state}): {detail}",
                           "controller-error")

    def _tick(self):
        """The state machine proper (invoked by onFrame)."""
        if self._destroyed:
            return   # a re-inited extension must stop driving the network
        if self.state == "idle":
            self._maybe_quit_idle()
            return
        self.last_activity = time.time()

        if self.state == "loading":
            # Give the Movie File In a few frames to open the file.
            self._loading_ticks += 1
            if self._loading_ticks >= 3:
                self._input_ready()
        elif self.state == "encoding":
            self._encode_tick()
        elif self.state == "finishing":
            self._finishing_ticks += 1
            if self._finishing_ticks >= 3:
                self._closed()
        elif self.state == "muxing":
            self._mux_tick()
        elif self.state == "extracting":
            self._extract_tick()

    # ------------------------------------------------------------------
    # Lifecycle (documented extension gotchas)
    # ------------------------------------------------------------------

    def onInitTD(self):
        """Called by TD at the end of the frame the extension initialised.

        Safe place to touch other operators — at __init__ time the network
        may not be ready (docs: "Cannot use an extension during its
        initialization").
        """
        self._set_status("idle — listening on port {}".format(self.port))

    def onDestroyTD(self):
        """Called when this extension is REPLACED by a re-init.

        The docs warn that a re-init can happen unexpectedly, and that the
        old instance may linger if anything still references it. Without
        this, a stale controller would keep advancing the network state
        machine while a fresh one sits idle — two minds on one body. Here we
        stop cleanly and release any recording.
        """
        self._destroyed = True
        debug(f"vCon: extension destroyed at {self.ownerComp.path}")
        try:
            if self.state != "idle":
                self.movieout.par.record = 0
        except Exception:
            pass
        self._kill_mux()
        self._kill_extract()
        self.job = None
        self.state = "idle"

    def _kill_extract(self):
        """Stop a background audio extraction (cancel/reset/destroy)."""
        s = getattr(self, "_sep", None)
        if not s:
            return
        try:
            s["proc"].kill()
        except Exception:
            pass
        try:
            s["log"].close()
        except Exception:
            pass
        try:
            if os.path.exists(s["log_path"]):
                os.remove(s["log_path"])
        except Exception:
            pass
        self._sep = None

    def _kill_mux(self):
        """Stop a background mux and bin its temp files (cancel/reset/destroy)."""
        m = getattr(self, "_mux", None)
        if not m:
            return
        try:
            m["proc"].kill()
        except Exception:
            pass
        try:
            m["log"].close()
        except Exception:
            pass
        for path in (m["tmp"], m["prog"], m["log_path"]):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        self._mux = None
        debug("vCon: audio mux stopped — output stays video-only")

    # ------------------------------------------------------------------
    # Public API — what an embedder calls
    # ------------------------------------------------------------------

    @property
    def is_busy(self):
        """True while a job is loading or encoding."""
        return self.state != "idle"

    @property
    def progress(self):
        """(frame, total) for the active job, or (0, 0) when idle."""
        return (self.frame, self.total)

    def Transcode(self, input_path, output_path, codec="notchlc",
                  subtype=None, quality=None, fps="auto",
                  pixel_format=None, container=None,
                  resolution="auto", fit=None, scale=None,
                  audio="auto", audio_sep=None):
        """Encode one file. The embedder/panel-facing entry point.

        Promoted (capitalised) so it reads as a method of the component::

            op('vcon').Transcode('/in.mov', '/out.mov', 'notchlc')

        All codec arguments are TD MENU TOKENS (the values the registry
        resolves; e.g. subtype 'prores422hq', not '422hq'). The panel
        resolves aliases against its embedded codec table before calling.
        ``scale`` is either a fit TOP Output Resolution token (eighth/
        quarter/half/twotimes/fourtimes/eighttimes — the panel SCALE menu
        mirrors that menu; the fit TOP applies it natively, no source
        dimensions needed) or a legacy float factor, for which the
        controller computes WxH from the movie's real dimensions after
        load.

        Returns True if the job was accepted, False if the component is busy.
        Completion is asynchronous — poll `Isbusy` / watch the Status
        parameter, or use the TCP protocol for progress events.
        """
        if self.state != "idle":
            debug(f"vCon: Transcode refused, busy ({self.state})")
            return False
        params = {
            "videocodec": codec,
            "videocodectype": subtype,
            "quality": quality,
            "fps": fps or "auto",
        }
        if pixel_format:
            params["moviepixelformat"] = pixel_format
        if container:
            params["moviecontainer"] = container
        if audio and audio != "auto":
            params["audio"] = audio
        if audio_sep:
            params["audio_sep"] = audio_sep
        if scale is not None:
            params["scale"] = scale
            # The fit mode travels with the token too — _apply_fitres
            # re-asserts it per-job, so the panel stays authoritative
            # even if the live par was left elsewhere.
            params["fit"] = fit or "fitbest"
        elif resolution and resolution != "auto":
            params["resolution"] = resolution
            params["fit"] = fit or "fitbest"
        self.onReceive(json.dumps({
            "type": "submit",
            "id": f"embed-{int(time.time() * 1000)}",
            "input": str(input_path),
            "output": str(output_path),
            "params": params,
            "origin": "panel",
        }))
        return True

    def Cancel(self):
        """Abort the active job, if any. Promoted for embedders."""
        if self.job:
            self._cancel(self.job.get("id"))

    def Pause(self):
        """Pause the active encode. Promoted for embedders and the panel."""
        self._pause("*")

    def Resume(self):
        """Resume a paused encode. Promoted for embedders and the panel."""
        self._resume("*")

    def Setfitpath(self, scaled):
        """Promoted panel hook: wire the fit TOP in/out LIVE.

        The SCALED toggle calls this so the wiring visibly changes at the
        SWITCH (JP: rewiring belongs to the toggle, not job start). Idle
        only — never touches the wiring mid-encode; the per-job
        _apply_resolution()/bypass remains the authority during jobs.
        """
        if self.state != "idle":
            debug("vCon: Setfitpath skipped — encoder busy (wiring "
                  "changes at job boundaries only)")
            return False
        try:
            if scaled:
                self._switch_mvo_input(self.fit)
            else:
                self._bypass_fit()
            return True
        except Exception as exc:
            debug(f"vCon: Setfitpath failed: {exc}")
            return False

    def Setfitparams(self, scale=None, fit=None, w=None, h=None):
        """Promoted panel hook: SCALE / FIT / W-H widgets drive the fit
        TOP LIVE (JP: the panel IS the parameter editor — a dropdown
        change must show in the network immediately, like Setquality).

        - ``scale``: a fit TOP Output Resolution token (the panel SCALE
          menu mirrors that menu) or the sentinel 'custom' (WxH)
        - ``fit``: a fit TOP Fit menu token (fill|fithorz|fitvert|
          fitbest|fitoutside — the panel FIT dropdown holds exactly these)
        - ``w``/``h``: with scale='custom', the absolute output resolution

        Idle-guarded: an encode in flight keeps its settings; per-job
        _apply_fitres/_apply_resolution re-assert at every START, so
        the panel stays authoritative between jobs.
        """
        if self.state != "idle":
            debug("vCon: Setfitparams skipped — encoder busy")
            return False
        f = self.fit
        if f is None:
            debug("vCon: Setfitparams skipped — no fit TOP (rebuild toe)")
            return False
        try:
            if scale is not None and str(scale) != "":
                token = str(scale)
                if token == "custom":
                    if w and h:
                        self._set_fit_menu(f.par.outputresolution,
                                           "custom", "customresolution")
                        self._set_fit_custom_res(f, int(w), int(h))
                        debug(f"vCon: fit custom {int(w)}x{int(h)}")
                else:
                    self._set_fit_menu(f.par.outputresolution, token)
                    debug(f"vCon: fit outputresolution <- {token}")
            if fit:
                mode = str(fit).lower()
                menu = list(getattr(f.par.fit, "menuNames", None) or [])
                if menu and mode not in menu:
                    raise ValueError(
                        f"fit mode {mode!r} not in Fit TOP menu {menu}")
                f.par.fit = mode
                debug(f"vCon: fit mode <- {mode}")
            return True
        except Exception as exc:
            debug(f"vCon: Setfitparams failed: {exc}")
            return False

    def Setquality(self, value):
        """Promoted panel hook: the panel's QUALITY slider drives MvO's
        quality slider LIVE — for ANY codec (JP: MvO's quality par is a
        general parameter; whatever codec is selected, the slider
        follows). Fires per drag tick; mid-encode changes affect frames
        written after the change. Each job re-applies the panel value at
        start, so the panel stays authoritative.
        """
        try:
            q = float(value)
        except (TypeError, ValueError):
            return False
        try:
            self.movieout.par.quality.val = q
            debug(f"vCon: MvO quality <- {q}")
            return True
        except Exception as exc:
            debug(f"vCon: Setquality failed: {exc}")
            return False

    def Setfps(self, value):
        """Promoted panel hook: the panel's FPS field drives MvO's fps
        par LIVE (JP: the field both READS the par — seeded at build —
        and CHANGES it, the same live-editor pattern as Setquality).

        'auto' (or blank/keep) = follow the source: the par is set
        from the loaded movie's sample rate when one is available
        (the same resolution _apply_codec_params applies per job); with
        nothing loaded the par is left as-is and job-time auto still
        applies. Any positive number sets the par directly. Idle-
        guarded like the other live hooks: an encode in flight keeps
        its settings, and each job re-applies the panel value at start.
        """
        if self.state != "idle":
            debug("vCon: Setfps skipped — encoder busy")
            return False
        v = str(value or "").strip().lower()
        try:
            if v in ("", "auto", "keep"):
                try:
                    sr = self.info["sample_rate"][0]
                except Exception:
                    sr = 0.0
                if sr and sr > 0:
                    self.movieout.par.fps = sr
                    debug(f"vCon: MvO fps <- {sr} (source rate)")
                    return True
                debug("vCon: Setfps auto — no source rate available, "
                      "par left as-is")
                return False
            f = float(v)
            if f <= 0:
                raise ValueError(f"fps must be positive (got {v!r})")
            self.movieout.par.fps = f
            debug(f"vCon: MvO fps <- {f}")
            return True
        except Exception as exc:
            debug(f"vCon: Setfps failed: {exc}")
            return False

    def Setparams(self, codec=None, subtype=None, pixel_format=None,
                  container=None):
        """Promoted panel hook: apply the CODEC/SUBTYPE/FORMAT dropdown
        choices to MvO LIVE (JP: the panel IS the parameter editor —
        changing a dropdown should show in MvO immediately, like
        Setquality/Setfitpath).

        Reuses _apply_codec_params so every assignment passes the same
        menu read-back verification — an invalid token fails loudly,
        never silently falls back to entry 0. Idle-guarded: an encode in
        flight keeps its settings (codec changes mid-encode would corrupt
        the file; per-job application re-asserts at every START).
        """
        if self.state != "idle":
            debug("vCon: Setparams skipped — encoder busy")
            return False
        params = {}
        if codec:
            params["videocodec"] = codec
        if subtype:
            params["videocodectype"] = subtype
        if pixel_format:
            params["moviepixelformat"] = pixel_format
        if container:
            params["moviecontainer"] = container
        try:
            self._apply_codec_params(params)
            return True
        except Exception as exc:
            debug(f"vCon: Setparams failed: {exc}")
            return False

    # ------------------------------------------------------------------
    # Connection handshake
    # ------------------------------------------------------------------

    def onConnect(self):
        """Front-end connected — recover from any stale TCP-owned state.

        A NEW TCP connection means the previous FRONT-END is gone (it
        crashed, was Ctrl-C'd, or the socket dropped), so a job it owns is
        dead. But PANEL jobs (submitted via the extension, no TCP client)
        must survive: any TCP connect — even a harmless `vcon -doctor`
        probe — must NOT kill an in-flight panel encode. (Caught live: a
        doctor probe aborted a panel job mid-encode.)
        """
        if self.state != "idle" and (self.job or {}).get("origin") == "tcp":
            self._abort_active_job("client reconnected")
        self.last_activity = time.time()
        self._send({
            "type": "hello",
            "version": PROTOCOL_VERSION,
            "controller_version": CONTROLLER_VERSION,
        })

    def _abort_active_job(self, reason):
        """Drop the active job and return to idle, stopping any recording."""
        try:
            movieout = self.movieout
            if movieout is not None:
                movieout.par.record = 0
        except Exception as exc:
            debug(f"abort: could not stop recording: {exc}")
        job_id = (self.job or {}).get("id", "?")
        debug(f"vcon: aborting job {job_id} ({reason})")
        self._kill_mux()
        self._kill_extract()
        self.job = None
        self.frame = 0
        self.total = 0
        self._src_total = 0
        self._src_step = 1.0
        self._loading_ticks = 0
        self._finishing_ticks = 0
        # Reset the Progress par — the success (_closed) and failure
        # (_fail) paths both reset it; the CANCEL path was the one that
        # left the bar stuck at its last value (JP: "progress stops but
        # does not reset when we stop").
        try:
            self.ownerComp.par.Progress.val = 0.0
        except Exception:
            pass
        self.state = "idle"

    # ------------------------------------------------------------------
    # Message intake (called from tcpip DAT callbacks)
    # ------------------------------------------------------------------

    def onReceive(self, message):
        """One protocol line arrived from the front-end.

        The TCPIP DAT's onReceive callback is (dat, rowIndex, message, bytes,
        peer); the callbacks DAT forwards just the message text here.
        """
        self.last_activity = time.time()
        try:
            msg = json.loads(message)
        except ValueError:
            self._send({"type": "error", "id": "?", "message": "bad json",
                        "code": "protocol"})
            return

        mtype = msg.get("type")
        if mtype == "submit":
            self._start_job(msg)
        elif mtype == "cancel":
            self._cancel(msg.get("id"))
        elif mtype == "pause":
            self._pause(msg.get("id"))
        elif mtype == "resume":
            self._resume(msg.get("id"))
        elif mtype == "ping":
            self._send({"type": "pong"})
        elif mtype == "status":
            # Diagnostic: report internal state. Silence from the controller
            # is otherwise indistinguishable from a wedged process.
            self._send({
                "type": "status",
                "id": msg.get("id", "?"),
                "state": self.state,
                "frame": self.frame,
                "total": self.total,
                "job": (self.job or {}).get("id"),
                "ticks": self._ticks,
                "last_error": self.last_error,
                "controller_version": CONTROLLER_VERSION,
                "protocol_version": PROTOCOL_VERSION,
            })
        else:
            self._send({"type": "error", "id": msg.get("id", "?"),
                        "message": f"unknown type {mtype!r}", "code": "protocol"})

    # ------------------------------------------------------------------
    # Job lifecycle
    # ------------------------------------------------------------------

    def _start_job(self, msg):
        if self.state != "idle":
            # Should not normally happen: a fresh connection resets state in
            # onConnect. If it does, say so clearly instead of a bare 'busy'.
            self._send({"type": "error", "id": msg.get("id"),
                        "message": f"controller is busy ({self.state}) — "
                                   f"reconnect to reset, or cancel the job",
                        "code": "busy"})
            return

        job = {
            "id": msg.get("id", ""),
            "input": msg.get("input", ""),
            "output": msg.get("output", ""),
            "params": msg.get("params", {}) or {},
            #: Who submitted this: "tcp" (CLI front-end over the wire) or
            #: "panel" (embedded extension call). Only tcp jobs are aborted
            #: when a new TCP client connects — panel jobs outlive probes.
            "origin": msg.get("origin", "tcp"),
        }
        if not os.path.isfile(job["input"]):
            self._send({"type": "error", "id": job["id"],
                        "message": f"input not found: {job['input']}",
                        "code": "input-missing"})
            return
        out_dir = os.path.dirname(job["output"]) or "."
        if not os.path.isdir(out_dir):
            self._send({"type": "error", "id": job["id"],
                        "message": f"output folder not found: {out_dir}",
                        "code": "output-error"})
            return
        if not os.path.splitext(job["output"])[1]:
            self._send({"type": "error", "id": job["id"],
                        "message": f"output has no file extension: "
                                   f"{job['output']!r} (a folder was given "
                                   f"as the output path?)",
                        "code": "output-error"})
            return
        self.job = job
        self._loading_ticks = 0
        self._paused = False   # a fresh job always starts unpaused
        self.state = "loading"
        self._set_progress(0.0)
        self._set_status(f"loading {os.path.basename(job['input'])}")
        try:
            self._load_input(job)
        except Exception as exc:
            # Never leave the job parked in 'loading' on a setup error.
            self._fail(f"could not set up input ({type(exc).__name__}: "
                       f"{exc})", "input-error")

    def _load_input(self, job):
        moviein = self.moviein
        moviein.par.file = job["input"]
        # VERIFIED LIVE (JP's TD, 2026-09-13; again on 2025.33230/33407):
        #   playmode menu = ['locked','specify','sequential','timecodeop']
        #   indexunit menu = ['indices','frames','seconds','fraction']
        #   (older builds used 'index' instead of 'indices'; both accepted)
        # An unknown token silently falls back to menu entry 0, so both
        # writes are menu-verified rather than plain assignments.
        self._menu_verified_write(moviein.par.playmode, "playmode",
                                  "specify")   # "Specify Index"
        # 'indices'/'index' = the movie's OWN frame number. 'frames' counts
        # TIMELINE frames and rescales by the project rate, so a 24fps movie
        # in a 60fps project advanced 0.4 frames per step — every source
        # frame written ~2.5x and the whole encode time-stretched (measured
        # 2.500 by toe/probe_timing.py). Verify against the live menu so a
        # token that falls back to entry 0 can never silently pick 'frames'.
        self._set_indexunit_menu(moviein.par.indexunit)
        moviein.par.index = 0
        # Throttle pre-read buffer to 2 frames: default 30 frames at 15.3K
        # resolution allocates ~8 GB of VRAM and can cause Metal memory stalls.
        try:
            moviein.par.prereadframes = 2
        except Exception:
            pass
        # _input_ready() is called from onFrame() after a few ticks.

    def _input_ready(self):
        """After the load settles, read stream info and begin encoding."""
        if self.state != "loading" or self.job is None:
            return
        moviein = self.moviein
        # Documented: Movie File In TOP exposes numImages (frame count).
        # (The Info CHOP's 'length' channel is a CHOP channel length, NOT
        # the movie's frame count — earlier assumption was wrong.)
        try:
            self.total = int(moviein.numImages)
        except Exception:
            self.total = 0
        if self.total <= 0:
            # Fallback: the movie's own stream object, if exposed.
            try:
                self.total = int(moviein.stream.numframes)
            except Exception:
                self.total = 0
        if self.total <= 0:
            self._fail(f"could not determine frame count for {self.job['input']}",
                       "input-error")
            return

        try:
            self._apply_codec_params(self.job["params"])
        except ValueError as exc:
            self._fail(f"codec parameters rejected: {exc}", "codec-error")
            return
        except Exception as exc:
            # Never let an unexpected failure leave the job in 'loading'.
            self._fail(
                f"could not apply codec settings ({type(exc).__name__}: {exc})",
                "codec-error",
            )
            return

        # Resolution: params may carry an explicit "resolution" (WxH, from
        # the CLI's -s flag), a "scale" FLOAT factor (legacy panel path —
        # needs the movie's ACTUAL dimensions, known only now after the
        # load settles), or a "scale" STRING token (the panel SCALE menu
        # mirrors the fit TOP's Output Resolution menu: eighth/quarter/
        # half/twotimes/fourtimes/eighttimes) which the fit TOP applies
        # NATIVELY relative to its input — no dimension math at all.
        # Scale wins if several arrive.
        params = self.job["params"]
        resolution = params.get("resolution")
        scale = params.get("scale")
        consumed = False
        if isinstance(scale, str) and scale not in ("", "auto"):
            # Native fit TOP token: _apply_fitres menu-verifies it and
            # fails LOUDLY on drift (never index-0 silent fallback).
            try:
                self._apply_fitres(scale, params.get("fit"))
            except Exception as exc:
                self._fail(f"fit resolution rejected: {exc}", "fit-error")
                return
            consumed = True
        elif scale is not None:
            # NATIVE movie dimensions: fileWidth/fileHeight (MoviefileinTOP
            # class, docs). .width/.height are the TOP's output TEXTURE size
            # — wrong source for scale math.
            try:
                mw = int(moviein.fileWidth)
                mh = int(moviein.fileHeight)
            except Exception:
                mw = mh = 0
            try:
                factor = float(scale)
            except (TypeError, ValueError):
                factor = 0.0
            if mw > 0 and mh > 0 and factor > 0:
                # Even dimensions: most movie codecs require even W/H.
                resolution = (f"{max(2, int(mw * factor) // 2 * 2)}x"
                              f"{max(2, int(mh * factor) // 2 * 2)}")
            else:
                # FAIL LOUDLY: the user asked for a scale; silently encoding
                # unscaled would be the exact wrong-output failure mode this
                # project exists to prevent.
                self._fail(
                    f"could not read source dimensions for scale {scale} "
                    f"(moviein.fileWidth/fileHeight unavailable)",
                    "scale-error",
                )
                return
        if not consumed:
            try:
                self._apply_resolution(resolution, params.get("fit"))
            except Exception as exc:
                self._fail(f"resolution rejected: {exc}", "fit-error")
                return

        movieout = self.movieout
        debug(f"vCon: MvO file <- {self.job['output']!r}")
        movieout.par.file = self.job["output"]
        self._plan_frame_rate(moviein)
        # Stop-frame recording, per the documented sequence:
        #   record = 1  (start recording)
        #   pause  = 1  (stop realtime advancement)
        #   addframe.pulse() per written frame
        # Finalize by setting record = 0 (equivalent of pressing Stop —
        # this closes/flushes the file).
        movieout.par.record = 1
        movieout.par.pause = 1
        debug(f"vCon: encode starting — {self.total} frames, "
              f"record=1 pause=1")

        self.frame = 0
        self.t0 = time.time()
        self.state = "encoding"
        self._set_status(f"encoding 0/{self.total}")
        self._send({"type": "accepted", "id": self.job["id"],
                    "total_frames": self.total})
        # onFrame() drives the loop from here — no scheduling needed.
        # (An earlier run(..., delayFrames=1) approach stopped firing
        #  entirely, leaving jobs stuck in silence.)

    # ------------------------------------------------------------------
    # Per-frame encode loop (driven by onFrame / Execute DAT)
    # ------------------------------------------------------------------

    def _plan_frame_rate(self, moviein):
        """Decide how many frames to write, and which source frame each one
        samples, so the OUTPUT DURATION MATCHES THE SOURCE.

        Writing one output frame per source frame and merely tagging the
        file with a different fps changes the DURATION — a 24fps source
        written at 60fps played 2.5x fast and ended long before its own
        audio. Instead, output frame i samples source frame i*step, where
        step = source_fps/output_fps: frames are held when speeding the
        rate up and dropped when slowing it down.

        Nearest source frame only — no blending or optical flow, so no
        pixels are invented that were not in the source.
        """
        self._src_total = self.total          # frames available to sample
        self._src_step = 1.0                  # 1.0 = one-for-one
        try:
            src_fps = float(self.info["sample_rate"][0])
        except Exception:
            src_fps = 0.0
        try:
            out_fps = float(self.movieout.par.fps.eval())
        except Exception:
            out_fps = 0.0
        if src_fps <= 0 or out_fps <= 0:
            debug("vCon: fps resample skipped — source rate unknown, "
                  "writing one output frame per source frame")
            return
        # Treat near-equal rates as identical: 23.976 vs 23.98 must not
        # trigger a resample and its rounding drift.
        if abs(src_fps - out_fps) < 0.01:
            return
        duration = self._src_total / src_fps
        out_frames = int(round(duration * out_fps))
        if out_frames <= 0:
            debug("vCon: fps resample skipped — computed 0 output frames")
            return
        self._src_step = src_fps / out_fps
        self.total = out_frames
        debug(f"vCon: resampling {src_fps:g} -> {out_fps:g} fps: "
              f"{self._src_total} source frames -> {out_frames} output "
              f"frames ({duration:.1f}s preserved)")

    def _encode_tick(self):
        """Write one frame. Called once per TD frame while encoding."""
        if self.state != "encoding":
            return
        if self._paused:
            # Paused: keep the session alive, write nothing. Progress and
            # status stay at the paused frame so resume continues exactly.
            self.last_activity = time.time()
            return
        moviein = self.moviein
        movieout = self.movieout

        if self.frame >= self.total:
            self._finish()
            return

        # Seek input to the SOURCE frame this output frame samples
        # (playmode=specify drives via 'index'), then pulse addframe to
        # write exactly one frame. step is 1.0 unless the output fps
        # differs from the source — see _plan_frame_rate.
        # Video-only: audio is muxed in by ffmpeg after the encode
        # finishes (TD's stop-frame mode can't feed audio samples —
        # the Audio Movie CHOP produces empty slices with pause=1).
        step = getattr(self, "_src_step", 1.0)
        src_total = getattr(self, "_src_total", self.total)
        src_index = (self.frame if step == 1.0
                     else min(src_total - 1, int(round(self.frame * step))))
        try:
            moviein.par.index = src_index
            movieout.par.addframe.pulse()
        except Exception as exc:
            self._fail(f"frame {self.frame} write failed: {exc}", "encode-error")
            return

        self.frame += 1
        if self.frame == 1:
            debug(f"vCon: first frame written (addframe pulsed)")
        if self.frame % 10 == 0 or self.frame == self.total:
            self._set_status(f"encoding {self.frame}/{self.total}")
            frac = self.frame / float(self.total) if self.total else 0.0
            self._set_progress(frac * _ENCODE_SHARE)
            self._send({"type": "progress", "id": self.job["id"],
                        "frame": self.frame, "total_frames": self.total})

    def _finish(self):
        """Stop recording; record = 0 is the documented "press Stop" that
        closes and finalizes the movie file."""
        self.state = "finishing"
        self._finishing_ticks = 0
        self.seconds_taken = round(time.time() - self.t0, 3)
        debug(f"vCon: finishing — record=0, {self.frame}/{self.total} "
              f"frames written, output={self.job['output']!r}")
        try:
            self.movieout.par.record = 0
        except Exception as exc:
            debug(f"finish: could not stop record: {exc}")
        # onFrame() calls _closed() after a few flush frames.

    def _closed(self):
        # Guard against being called twice (e.g. a cancel racing the finish).
        if self.job is None:
            self.state = "idle"
            return
        out = self.job["output"]
        # Movie File Out finalizes on its own schedule — a large file can
        # still be flushing several frames after record=0. Reporting
        # "size=0" here (and skipping the mux) meant the file simply
        # hadn't landed yet, not that the encode failed.
        if not os.path.isfile(out) and self._finishing_ticks < 300:
            self._set_status("finalizing file…")
            return   # stay in "finishing"; _tick calls back next frame
        movieout = self.movieout
        seconds = getattr(self, "seconds_taken", 0.0) or round(
            time.time() - self.t0, 3)
        frames = self.total
        try:
            frames = int(movieout["total_frames_written"][0]) or self.total
        except Exception:
            pass  # info channel unavailable; report the expected count
        self._done_frames = frames
        self._done_seconds = seconds
        debug(f"vCon: closed — output={out!r}, exists={os.path.exists(out)}, "
              f"size={os.path.getsize(out) if os.path.exists(out) else 0}, "
              f"waited={self._finishing_ticks} ticks")
        # Mux audio from the source file into the TD-encoded video.
        # TD's stop-frame mode writes video-only; ffmpeg copies the
        # audio stream from the original source (no re-encode of video).
        src = self.job.get("input", "")
        if src and os.path.isfile(src) and os.path.isfile(out):
            if self._mux_start(src, out):
                return   # _mux_tick() completes the job when ffmpeg exits
        else:
            debug("vCon: mux SKIPPED (source or output missing)")
        self._maybe_extract_audio(out)

    def _extract_tick(self):
        """Poll the background audio extraction; complete when done."""
        s = getattr(self, "_sep", None)
        if not s:
            self.state = "idle"
            return
        rc = s["proc"].poll()
        if rc is None:
            if time.time() - s["t0"] > 600:
                debug("vCon: audio extraction timed out (10m)")
                try:
                    s["proc"].kill()
                except Exception:
                    pass
                self._extract_done(s, ok=False)
            return
        self._extract_done(s, ok=(rc == 0), rc=rc)

    def _extract_done(self, s, ok, rc=0):
        """Finish audio extraction and complete the job."""
        try:
            s["log"].close()
        except Exception:
            pass
        if ok:
            size = os.path.getsize(s["out"]) if os.path.exists(s["out"]) else 0
            debug(f"vCon: audio extracted — {s['out']}, size={size}")
            note = s["note"] + f", sep audio: {os.path.basename(s['out'])}"
        else:
            debug(f"vCon: audio extraction failed (rc={rc})")
            note = s["note"] + ", sep audio failed"
        try:
            if os.path.exists(s["log_path"]):
                os.remove(s["log_path"])
        except Exception:
            pass
        self._sep = None
        self._job_complete(s["video_out"], note)

    def _job_complete(self, out, note=""):
        """Finalize: tell the client, clear the job, return to idle.

        Deferred until after any audio mux so the panel keeps the row
        'running' (and its bar alive) for the whole pipeline.
        """
        frames = getattr(self, "_done_frames", self.total)
        seconds = getattr(self, "_done_seconds", 0.0)
        if self.job is not None:
            self._send({"type": "done", "id": self.job["id"],
                        "path": out, "total_frames": frames,
                        "seconds": seconds})
        self._set_progress(1.0)
        self._set_status(f"idle — last: {os.path.basename(out)} "
                         f"({frames} frames, {seconds}s{note})")
        self.job = None
        self.state = "idle"
        self.last_activity = time.time()

    # ------------------------------------------------------------------
    # Audio mux (post-encode, via ffmpeg subprocess)
    # ------------------------------------------------------------------

    #: Cached ffmpeg path (None = not yet searched, "" = searched, absent)
    _ffmpeg_cache = None

    def _find_ffmpeg(self):
        """Locate an ffmpeg binary across install layouts.

        TD's embedded Python can't see pip packages installed elsewhere,
        so the search widens from "importable" to "findable on disk":
          1. import imageio_ffmpeg  (TD's Python has it)
          2. pipx venvs and user site-packages (normal user installs)
          3. system ffmpeg on PATH
        Result is cached — this runs once per session, not per job.
        """
        cls = type(self)
        if cls._ffmpeg_cache is not None:
            return cls._ffmpeg_cache or None

        found = ""
        try:
            import imageio_ffmpeg
            found = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass

        if not found:
            import glob
            home = os.path.expanduser("~")
            # vCon's own package folder, written by the panel's
            # "INSTALL AUDIO" button (no admin rights required).
            if sys.platform == "darwin":
                vcon_libs = os.path.expanduser(
                    "~/Library/Application Support/vCon/pylibs")
            elif os.name == "nt":
                vcon_libs = os.path.join(
                    os.environ.get("LOCALAPPDATA") or home,
                    "vCon", "pylibs")
            else:
                vcon_libs = os.path.expanduser("~/.local/share/vCon/pylibs")
            patterns = [
                f"{vcon_libs}/imageio_ffmpeg/binaries/ffmpeg-*",
                f"{home}/.local/pipx/venvs/*/lib/python*/site-packages/"
                "imageio_ffmpeg/binaries/ffmpeg-*",
                f"{home}/Library/Python/*/lib/python/site-packages/"
                "imageio_ffmpeg/binaries/ffmpeg-*",
                f"{home}/.local/lib/python*/site-packages/"
                "imageio_ffmpeg/binaries/ffmpeg-*",
            ]
            for pat in patterns:
                for cand in sorted(glob.glob(pat), reverse=True):
                    if os.path.isfile(cand) and os.access(cand, os.X_OK):
                        found = cand
                        break
                if found:
                    break

        if not found:
            import shutil
            found = shutil.which("ffmpeg") or ""

        cls._ffmpeg_cache = found
        debug(f"vCon: ffmpeg {'found at ' + found if found else 'NOT FOUND'}")
        return found or None

    def _mux_start(self, source, video_output):
        """Launch the audio mux as a BACKGROUND ffmpeg process.

        Never blocks: subprocess.run() froze TD's whole UI for the length
        of the copy (minutes on a multi-GB file). ffmpeg writes machine
        progress to a file that _mux_tick() polls each frame; stderr goes
        to a file too, so a full pipe buffer can't deadlock it.

        Returns True if the process launched (state -> "muxing").
        """
        ffmpeg = self._find_ffmpeg()
        if ffmpeg is None:
            debug("vCon: no ffmpeg found — output is video-only "
                  "(install imageio-ffmpeg or ffmpeg for audio)")
            return False
        # Audio codec from the job params (panel's audio_dd selection).
        # Falls back to container-based defaults for CLI jobs without it.
        audio = (self.job.get("params") or {}).get("audio", "auto")
        if audio == "none":
            debug("vCon: audio=none — skipping mux (video only)")
            return False
        if audio == "auto" or not audio:
            ext = os.path.splitext(video_output)[1].lower()
            if ext == ".mp4":
                audio = "aac"
            else:
                audio = "pcm_s16le"
        # Build ffmpeg args from the audio codec selection
        if audio == "copy":
            aargs = ["-c:a", "copy"]
        elif audio == "pcm_s16le":
            aargs = ["-c:a", "pcm_s16le"]
        elif audio == "pcm_s24le":
            aargs = ["-c:a", "pcm_s24le"]
        elif audio == "aac":
            aargs = ["-c:a", "aac", "-b:a", "256k"]
        elif audio == "alac":
            aargs = ["-c:a", "alac"]
        elif audio == "mp3":
            aargs = ["-c:a", "libmp3lame", "-b:a", "320k"]
        else:
            aargs = ["-c:a", "pcm_s16le"]
        ext = os.path.splitext(video_output)[1].lower()
        # Temp name keeps the real extension — ffmpeg infers the
        # muxer from it, and ".tmp" matches nothing.
        stem = os.path.splitext(video_output)[0]
        tmp = stem + ".muxing" + ext
        prog_path = stem + ".muxing.progress"
        log_path = stem + ".muxing.log"
        cmd = [ffmpeg, "-y", "-nostdin", "-nostats",
               "-progress", prog_path,
               "-i", video_output,
               "-i", source,
               "-map", "0:v:0", "-map", "1:a:0",
               "-c:v", "copy"] + aargs + [tmp]
        try:
            import subprocess
            log = open(log_path, "wb")
            proc = subprocess.Popen(cmd, stdout=log, stderr=log,
                                    stdin=subprocess.DEVNULL)
        except Exception as exc:
            debug(f"vCon: could not launch ffmpeg: {exc}")
            return False
        # Registration must not be able to fail separately from the
        # launch: an exception between Popen and _mux being set orphans
        # a running ffmpeg (it finishes, but nothing swaps or cleans up).
        try:
            self._mux = {
                "proc": proc, "log": log, "tmp": tmp, "out": video_output,
                "prog": prog_path, "log_path": log_path, "acodec": audio,
                "t0": time.time(), "frac": 0.0,
                # expected duration in microseconds, for the progress fraction
                "total_us": self._expected_duration_us(),
            }
            self.state = "muxing"
            size_mb = os.path.getsize(video_output) / 1e6
            debug(f"vCon: muxing audio — {audio}, {size_mb:.0f}MB, "
                  f"source={os.path.basename(source)}")
            self._set_status(
                f"muxing audio 0% — {os.path.basename(video_output)}")
        except Exception as exc:
            debug(f"vCon: mux bookkeeping failed ({exc}) — aborting ffmpeg")
            try:
                proc.kill()
            except Exception:
                pass
            try:
                log.close()
            except Exception:
                pass
            for path in (tmp, prog_path, log_path):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass
            self._mux = None
            return False
        return True

    def _expected_duration_us(self):
        """Output duration in microseconds, for the mux progress fraction."""
        try:
            fps = float(self.movieout.par.fps.eval())
            if fps > 0 and self.total:
                return (self.total / fps) * 1e6
        except Exception:
            pass
        return 0.0

    def _mux_tick(self):
        """Poll the background mux: update progress, finish when it exits."""
        m = getattr(self, "_mux", None)
        if not m:
            self.state = "idle"
            return
        # progress fraction from ffmpeg's -progress file (out_time_us)
        if m["total_us"]:
            try:
                with open(m["prog"], "r") as fh:
                    tail = fh.read()[-2000:]
                done_us = 0.0
                for line in reversed(tail.splitlines()):
                    if line.startswith("out_time_us="):
                        done_us = float(line.split("=", 1)[1] or 0)
                        break
                frac = min(1.0, done_us / m["total_us"])
                if frac > m["frac"]:
                    m["frac"] = frac
            except Exception:
                pass  # file not written yet — keep the last fraction
        self._set_progress(_ENCODE_SHARE + m["frac"] * (1.0 - _ENCODE_SHARE))
        self._set_status(f"muxing audio {int(m['frac'] * 100)}% — "
                         f"{os.path.basename(m['out'])}")
        rc = m["proc"].poll()
        if rc is None:
            if time.time() - m["t0"] > 3600:
                debug("vCon: ffmpeg mux timed out (1h) — output is video-only")
                try:
                    m["proc"].kill()
                except Exception:
                    pass
                self._mux_done(m, ok=False, note=" — mux timed out")
            return
        self._mux_done(m, ok=(rc == 0), rc=rc)

    def _mux_done(self, m, ok, rc=0, note=""):
        """Swap in the muxed file (or clean up) and complete the job."""
        try:
            m["log"].close()
        except Exception:
            pass
        if ok:
            try:
                os.replace(m["tmp"], m["out"])
                size = os.path.getsize(m["out"])
                took = round(time.time() - m["t0"], 1)
                debug(f"vCon: audio muxed — {m['acodec']}, size={size}, "
                      f"{took}s")
                note = f", audio {m['acodec']}"
            except Exception as exc:
                debug(f"vCon: could not replace output after mux: {exc}")
                note = " — mux swap failed"
        elif rc:
            err = ""
            try:
                with open(m["log_path"], "r", errors="replace") as fh:
                    err = fh.read()[-500:]
            except Exception:
                pass
            if "matches no streams" in err:
                debug("vCon: source has no audio track — video only")
                note = ", no audio in source"
            else:
                debug(f"vCon: ffmpeg mux failed (rc={rc}): {err}")
                note = " — audio mux failed"
        for path in (m["tmp"], m["prog"], m["log_path"]):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
        out = m["out"]
        self._mux = None
        self._maybe_extract_audio(out, note)

    def _maybe_extract_audio(self, video_output, note=""):
        """Run separate audio extraction if audio_sep was requested."""
        sep = (self.job.get("params") or {}).get("audio_sep")
        if not sep:
            self._job_complete(video_output, note)
            return
        ffmpeg = self._find_ffmpeg()
        if ffmpeg is None:
            debug("vCon: no ffmpeg for audio extraction — skipping")
            self._job_complete(video_output, note + ", no sep audio")
            return
        src = self.job.get("input", "")
        if not src or not os.path.isfile(src):
            self._job_complete(video_output, note + ", no sep audio")
            return
        # ffmpeg picks the muxer from the EXTENSION, so every entry must
        # be a real audio container. 'copy' keeps the source stream
        # whatever it is, so it needs a container that accepts anything:
        # Matroska audio (.mka) does, where .wav/.m4a would reject half
        # the possible codecs.
        ext = {"wav16": ".wav", "wav24": ".wav", "aiff16": ".aiff",
               "aiff24": ".aiff", "aac": ".m4a", "mp3": ".mp3",
               "copy": ".mka"}.get(sep, ".wav")
        # Sidecar name = video name with the audio extension. The
        # extension already says it is audio; a ".audio." infix would
        # only repeat that. A future naming-string control overrides
        # this via params["audio_sep_name"].
        stem = os.path.splitext(video_output)[0]
        out = (self.job.get("params") or {}).get("audio_sep_name") or (
            stem + ext)
        args = {"wav16": ["-c:a", "pcm_s16le"],
                "wav24": ["-c:a", "pcm_s24le"],
                "aiff16": ["-c:a", "pcm_s16be"],
                "aiff24": ["-c:a", "pcm_s24be"],
                "aac": ["-c:a", "aac", "-b:a", "256k"],
                "mp3": ["-c:a", "libmp3lame", "-b:a", "320k"],
                "copy": ["-c:a", "copy"]}.get(sep, ["-c:a", "pcm_s16le"])
        cmd = [ffmpeg, "-y", "-nostdin", "-nostats",
               "-i", src, "-vn"] + args + [out]
        try:
            import subprocess
            log_path = stem + ".audio_sep.log"
            log = open(log_path, "wb")
            proc = subprocess.Popen(cmd, stdout=log, stderr=log,
                                    stdin=subprocess.DEVNULL)
        except Exception as exc:
            debug(f"vCon: could not launch audio extraction: {exc}")
            self._job_complete(video_output, note + ", sep audio failed")
            return
        try:
            self._sep = {"proc": proc, "log": log, "out": out,
                         "log_path": log_path, "video_out": video_output,
                         "note": note, "t0": time.time()}
            self.state = "extracting"
            self._set_status(f"extracting audio — {os.path.basename(out)}")
            debug(f"vCon: extracting audio — {sep} → {out}")
        except Exception as exc:
            debug(f"vCon: extraction bookkeeping failed ({exc}) — aborting")
            try:
                proc.kill()
            except Exception:
                pass
            try:
                log.close()
            except Exception:
                pass
            self._sep = None
            self._job_complete(video_output, note + ", sep audio failed")

    def _cancel(self, job_id):
        if self.job and self.job["id"] == job_id and self.state in (
                "loading", "encoding", "muxing", "extracting"):
            self._abort_active_job("cancelled by client")
            self._send({"type": "error", "id": job_id, "message": "cancelled",
                        "code": "cancelled"})
        elif self.job is None:
            # nothing running; ack so the front-end can clean up
            self._send({"type": "error", "id": job_id, "message": "cancelled",
                        "code": "cancelled"})

    def _pause(self, job_id):
        """Pause the active encode. id "*" (or a match) pauses; else noop."""
        if self.state == "encoding" and (job_id == "*" or
                (self.job and self.job.get("id") == job_id)):
            self._paused = True
            self._set_status(f"paused at frame {self.frame}/{self.total}")
            self._send({"type": "paused", "id": (self.job or {}).get("id", "?"),
                        "frame": self.frame, "total_frames": self.total})
        elif self.state == "loading":
            # not yet encoding — nothing meaningful to pause; acknowledge
            self._send({"type": "error", "id": job_id,
                        "message": "cannot pause while loading", "code": "noop"})

    def _resume(self, job_id):
        """Resume a paused encode; also clears the pause on a fresh job."""
        if self._paused and (job_id == "*" or
                (self.job and self.job.get("id") == job_id)):
            self._paused = False
            self._set_status(f"encoding {self.frame}/{self.total}")
            self._send({"type": "resumed", "id": (self.job or {}).get("id", "?"),
                        "frame": self.frame, "total_frames": self.total})

    # ------------------------------------------------------------------
    # Codec parameters (registry-resolved values from the front-end)
    # ------------------------------------------------------------------

    def _apply_codec_params(self, p):
        """Apply resolved Movie File Out parameters, verifying menu values.

        Menu parameters SILENTLY fall back to index 0 when given a value that
        is not in the menu — for video codec that means 'rle', producing a
        perfectly valid file in the WRONG codec. So every menu assignment is
        read back and compared; a mismatch is a hard job failure rather than
        a bad output file.
        """
        movieout = self.movieout
        problems = []

        def set_menu(par_name, value):
            """Assign a menu parameter, tolerating par/entry absence.

            Some menu parameters are EMPTY for a given codec (e.g. 'quality'
            reports menuNames == [] for notchlc). Assigning to such a par
            raises, which previously aborted the job with no visible error.
            """
            if value is None:
                return
            par = getattr(movieout.par, par_name, None)
            if par is None:
                return  # parameter not present on this build: not fatal
            valid = list(getattr(par, "menuNames", None) or [])
            if valid:
                if value not in valid:
                    problems.append(
                        f"{par_name}={value!r} not in menu {valid}"
                    )
                    return
            elif par_name != "quality":
                # Empty menu on a value parameter that matters means we
                # cannot apply it — report rather than fail silently later.
                problems.append(
                    f"{par_name} has no menu entries; cannot set {value!r}"
                )
                return
            else:
                debug(f"{par_name}: no menu for this codec; skipping")
                return
            try:
                par.val = value
            except Exception as exc:
                problems.append(f"{par_name} assignment failed: {exc}")

        set_menu("videocodec", p.get("videocodec"))
        set_menu("videocodectype", p.get("videocodectype"))
        set_menu("moviepixelformat", p.get("moviepixelformat"))
        set_menu("moviecontainer", p.get("moviecontainer"))
        # QUALITY is NOT a menu: for NotchLC MvO exposes a FLOAT slider
        # (0-1). Sending a name ('optimal') to a non-menu par raises or
        # no-ops; the registry resolves names to VALUES before they ever
        # reach here (Derivative's NotchLC guide: best=1.0, optimal=0.862,
        # excellent=0.575, very-good=0.285, good=0.0).
        q = p.get("quality")
        if q is not None:
            try:
                movieout.par.quality.val = float(q)
            except (TypeError, ValueError):
                problems.append(f"quality={q!r} is not a number")
            except Exception as exc:
                problems.append(f"quality assignment failed: {exc}")

        if problems:
            raise ValueError("; ".join(problems))

        if p.get("fps"):
            if p["fps"] == "auto":
                # Movie File In has no 'fps' parameter — the source rate
                # comes from the Info CHOP's sample_rate channel.
                try:
                    movieout.par.fps = self.info["sample_rate"][0]
                except Exception as exc:
                    debug(f"could not set fps from sample_rate: {exc}")
            else:
                try:
                    movieout.par.fps = float(p["fps"])
                except (TypeError, ValueError) as exc:
                    debug(f"could not set fps={p['fps']!r}: {exc}")

    #: How a custom resolution rescales — TD's Fit TOP menu tokens
    #: (live-verified: fill|fithorz|fitvert|fitbest|fitoutside).
    #: Kept as a module constant so a future panel can list the modes.
    FIT_MODES = ("fill", "fithorz", "fitvert", "fitbest", "fitoutside")

    def _set_fit_menu(self, par, token, *aliases):
        """Menu-verified write for a fit TOP menu par.

        TD silently falls back to menu index 0 on an unknown token —
        the wrong-output failure mode this project exists to prevent.
        Only a token the LIVE menu holds is written; aliases cover
        build-to-build token drift ('custom' vs 'customresolution').
        Returns the token actually written.
        """
        return self._menu_verified_write(par, "fit TOP", token, *aliases)

    def _menu_verified_write(self, par, label, token, *aliases):
        """Write a menu token only if the LIVE menu agrees.

        TD silently substitutes menu entry 0 for an unknown token. An empty
        menu means the operator has not populated it yet (e.g. Movie File In
        before a file is loaded), so the preferred token is written as a
        best-effort default; a non-empty menu missing every candidate is a
        real mismatch and raises instead of silently picking the wrong unit.
        Returns the token actually written.
        """
        try:
            menu = list(getattr(par, "menuNames", None) or [])
        except Exception:
            menu = []
        for cand in (token,) + aliases:
            if not menu or cand in menu:
                par.val = cand
                return cand
        raise ValueError(f"{token!r} not in live {label} menu {menu}")

    def _set_indexunit_menu(self, par):
        """Menu-verified write for Movie File In's Index Unit menu.

        Live TD builds (2025.33230/33407) expose 'indices'; older builds used
        'index'. Accept either so a menu reorder can never silently switch to
        'frames' and time-stretch the encode.
        """
        return self._menu_verified_write(par, "indexunit", "indices", "index")

    def _apply_fitres(self, token, fit_mode=None):
        """Configure the fit TOP with a NATIVE Output Resolution token.

        The panel's SCALE dropdown mirrors the fit TOP's Output
        Resolution menu (eighth/quarter/half/twotimes/fourtimes/
        eighttimes) — the fit TOP scales relative to its input itself,
        so no source-dimension math happens here. Menu-verified writes
        only: an unknown token raises instead of silently falling back
        to menu index 0.
        """
        f = self.fit
        if f is None:
            raise ValueError(
                "this toe has no fit TOP; rebuild the toe "
                "(exec build_network.py in the textport)"
            )
        self._set_fit_menu(f.par.outputresolution, str(token))
        if fit_mode:
            mode = str(fit_mode).lower()
            menu = list(getattr(f.par.fit, "menuNames", None) or [])
            if menu and mode not in menu:
                raise ValueError(
                    f"fit mode {mode!r} not in Fit TOP menu {menu}"
                )
            f.par.fit = mode
        # Switch the data path: moviein -> fit -> movieout
        self._switch_mvo_input(f)
        self._set_status(f"encoding at fit resolution {token}")

    def _apply_resolution(self, resolution, fit_mode):
        """Configure the Fit TOP for a custom resolution (or bypass it).

        With resolution="auto" the fit TOP is bypassed: moviein is wired
        straight into movieout, so legacy toes (no fit TOP) and legacy jobs
        (no -s flag) behave exactly as before. With a custom WxH the fit TOP
        is inserted and set: outputresolution='custom', resolution='W H',
        and the `fit` menu token (stretch/fitwidth/fitheight/cover —
        lowercase, verified against Fit TOP docs).
        """
        movieout = self.movieout
        if not resolution or resolution == "auto":
            self._bypass_fit()
            return
        f = self.fit
        if f is None:
            # Older toe without a fit TOP: cannot honor resolution. Fail
            # LOUDLY rather than encode at the wrong size silently — the
            # same principle as the codec-menu verification.
            raise ValueError(
                f"this toe has no fit TOP; cannot encode at {resolution}. "
                f"Rebuild the toe (exec build_network.py in the textport)."
            )
        try:
            w, _, h = resolution.partition("x")
            w = int(w)
            h = int(h)
        except (TypeError, ValueError):
            raise ValueError(f"bad resolution {resolution!r} (expected WxH)")
        if w < 1 or h < 1:
            raise ValueError(f"bad resolution {resolution!r} (W and H >= 1)")

        menu = list(getattr(f.par.fit, "menuNames", None) or [])
        # TD's LIVE Fit TOP menu (builder-verified): fill|fithorz|fitvert|
        # fitbest|fitoutside|nativeres. The front-end normalizes aliases
        # (stretch→fill, cover→fitoutside) BEFORE anything reaches here —
        # a raw unknown token would silently fall back to menu index 0.
        mode = (fit_mode or "fitbest").lower()
        if menu and mode not in menu:
            raise ValueError(
                f"fit mode {mode!r} not in Fit TOP menu {menu}"
            )
        f.par.fit = mode
        # Common page: Custom Resolution + explicit W H. LIVE-GOTCHA: this
        # build's fit TOP has NO par named 'resolution' (raised
        # tdAttributeError, killing scaled jobs at load). resx/resy are
        # the Common-page fields; try 'resolution' first (tuple form) and
        # fall back to resx/resy — whichever this build exposes.
        # custom token drifts between TD builds ('custom' vs
        # 'customresolution') — menu-verified write with alias
        self._set_fit_menu(f.par.outputresolution, "custom",
                           "customresolution")
        self._set_fit_custom_res(f, w, h)
        # Switch the data path: moviein -> fit -> movieout. moviein feeds
        # fit permanently (builder); only MvO's input source changes here.
        self._switch_mvo_input(f)
        self._set_status(f"encoding at {w}x{h} ({mode})")

    def _set_fit_custom_res(self, f, w, h):
        """Write the fit TOP's custom resolution — par names drift across
        TD builds (LIVE-EVIDENCE, three rounds):
          - 2026-09-13 probe: f.par.resolution exists? NO — resx/resy were
            the Common-page fields on that build
          - 2026-09-14 build log: 'td.ParCollection has no resx' — resx/
            resy GONE on this build
          - JP reports the par names are resolutionw / resolutionh
        So: try resolutionw/resolutionh FIRST (JP's live report), then
        resolution (tuple form), then resx/resy — first pair that
        exists wins, everything soft-fails and reports. A raise here
        would kill the fit-mode write too (same try in Setfitparams —
        the bug that un-wired FIT with custom W/H).
        """
        w, h = int(w), int(h)
        try:
            f.par.resolutionw = w
            f.par.resolutionh = h
            return
        except Exception:
            pass
        try:
            f.par.resolution = (w, h)
            return
        except Exception:
            pass
        try:
            f.par.resx = w
            f.par.resy = h
            return
        except Exception:
            pass
        raise ValueError(
            f"cannot set fit TOP resolution to {w}x{h} "
            f"(no resolutionw/resolution/resx par on this build)"
        )

    def _switch_mvo_input(self, src):
        """Point movieout's first input at ``src`` (moviein or fit).

        Uses the verified connector API (dst.inputConnectors[0].connect —
        the same mechanism the builder wires with). Whether connect()
        replaces an existing input or raises is verified by the rewire
        probe; the disconnect() fallback covers builds where it raises.
        """
        movieout = self.movieout
        try:
            current = movieout.inputs[0] if movieout.inputs else None
            if current is src:
                return                    # already wired here — nothing to do
        except Exception:
            pass
        conn = movieout.inputConnectors[0]
        try:
            conn.connect(src)
        except Exception:
            try:
                conn.disconnect()
            except Exception as exc:
                debug(f"MvO input switch: disconnect failed: {exc}")
                return
            conn.connect(src)
        debug(f"vCon: MvO input -> {src.name}")

    def _bypass_fit(self):
        """Wire moviein straight to movieout, dropping the fit TOP."""
        try:
            self._switch_mvo_input(self.moviein)
        except Exception as exc:
            debug(f"bypass_fit: {exc}")

    # ------------------------------------------------------------------
    # Plumbing
    # ------------------------------------------------------------------

    def _send(self, payload):
        """Send one protocol line to the connected front-end.

        Documented TCPIP DAT API is send(*messages, terminator=...).
        (sendText() is WebSocket-only; there is no force= argument.)
        """
        tcp = self.tcpip
        if tcp is None:
            return
        try:
            tcp.send(json.dumps(payload), terminator="\n")
        except Exception as e:
            debug(f"send failed: {e}")

    def _maybe_quit_idle(self):
        """Orphan cleanup for TouchDesigner processes that vCon LAUNCHED.

        The front-end normally terminates the TD it spawned (the driver's
        shutdown path). This backstop covers the case where the front-end
        dies first (SIGKILL, crash, power loss): without it the spawned TD
        would linger forever holding port 7999.

        ARMING is by process provenance — the front-end sets VCON_LAUNCHED=1
        in the environment of the TouchDesigner it starts. A session the
        user opened themselves lacks the variable and is therefore NEVER
        quit by this code, however long it idles. An earlier version used a
        user-facing toggle (wrong: the system knows this fact, users should
        not have to configure it) and worse, fired from the per-frame tick
        without a latch — calling project.quit() ~60 times per second and
        stacking modal dialogs the user had to dismiss by hand.
        """
        if not self._orphan_cleanup_armed:
            return                    # user-owned session: hands off, always
        if self._quit_requested:
            return                    # already asked; never ask again

        if time.time() - self.last_activity > IDLE_QUIT_SECONDS:
            self._quit_requested = True     # latch BEFORE quitting
            debug("vCon: front-end vanished — orphan cleanup quitting TD")
            try:
                project.quit()
            except Exception as exc:
                debug(f"vCon: project.quit() failed: {exc}")

    def _fail(self, message, code):
        """Report failure for the active job and return to idle."""
        self.last_error = f"[{code}] {message}"
        self._set_status(f"error: {message}")
        self._send({"type": "error", "id": (self.job or {}).get("id", "?"),
                    "message": message, "code": code})
        # Reset the Progress par so a failed job doesn't leave it stuck
        # mid-way. (Success path resets it in _finish.)
        try:
            self.ownerComp.par.Progress.val = 0.0
        except Exception:
            pass
        self._paused = False
        self.job = None
        self.state = "idle"


# The extension class above is instantiated by TD when the module is listed
# in the vcon COMP's extension parameter; the TCPIP callbacks DAT calls
# ext.Vcon.<method> — no module-level wrappers needed.