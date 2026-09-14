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
import time

#: Controller build identifier. Written into the toe's custom "Version"
#: parameter at build time so a stale toe is identifiable in the UI.
#: Keep in step with vcon.__version__ (tests assert this).
CONTROLLER_VERSION = "0.1.1"

PROTOCOL_VERSION = 1
#: Default TCP port. Overridable per-instance via the COMP's Tcpport custom
#: parameter, so two vCon components can coexist in one project.
PORT = 7999
IDLE_QUIT_SECONDS = 300  # safety net: exit TD when idle this long


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
        self.state = "idle"      # idle | loading | encoding | finishing
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
        self.job = None
        self.state = "idle"

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
                  resolution="auto", fit=None, scale=None):
        """Encode one file. The embedder/panel-facing entry point.

        Promoted (capitalised) so it reads as a method of the component::

            op('vcon').Transcode('/in.mov', '/out.mov', 'notchlc')

        All codec arguments are TD MENU TOKENS (the values the registry
        resolves; e.g. subtype 'prores422hq', not '422hq'). The panel
        resolves aliases against its embedded codec table before calling.
        ``scale`` (0.25/0.5/1/2/3) defers resolution math to the controller,
        which computes WxH from the movie's real dimensions after load.

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
        if scale is not None:
            params["scale"] = scale
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
        self.job = None
        self.frame = 0
        self.total = 0
        self._loading_ticks = 0
        self._finishing_ticks = 0
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
        self._set_status(f"loading {os.path.basename(job['input'])}")
        self._load_input(job)

    def _load_input(self, job):
        moviein = self.moviein
        moviein.par.file = job["input"]
        # VERIFIED LIVE (JP's TD, 2026-09-13):
        #   playmode menu = ['locked','specify','sequential','timecodeop']
        #   indexunit menu = ['index','frames','seconds','fraction']
        moviein.par.playmode = "specify"   # "Specify Index"
        moviein.par.indexunit = "frames"
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

        # Resolution: params may carry either an explicit "resolution"
        # (WxH, from the CLI's -s flag) or a "scale" factor (panel: quarter/
        # half/1x/2x/3x) which needs the movie's ACTUAL dimensions — known
        # only now, after the load settles. Scale wins if both arrive.
        params = self.job["params"]
        resolution = params.get("resolution")
        scale = params.get("scale")
        if scale is not None:
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
        self._apply_resolution(resolution, params.get("fit"))

        movieout = self.movieout
        movieout.par.file = self.job["output"]
        # Stop-frame recording, per the documented sequence:
        #   record = 1  (start recording)
        #   pause  = 1  (stop realtime advancement)
        #   addframe.pulse() per written frame
        # Finalize by setting record = 0 (equivalent of pressing Stop —
        # this closes/flushes the file).
        movieout.par.record = 1
        movieout.par.pause = 1

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

        # Seek input to this frame (playmode=specify drives via 'index'
        # param), then pulse addframe to write exactly one frame.
        try:
            moviein.par.index = self.frame
            movieout.par.addframe.pulse()
        except Exception as exc:
            self._fail(f"frame {self.frame} write failed: {exc}", "encode-error")
            return

        self.frame += 1
        if self.frame % 10 == 0 or self.frame == self.total:
            self._set_status(f"encoding {self.frame}/{self.total}")
            # Progress par: 0..1 fraction, for a panel slider. Seeded at 0
            # by the builder; a slider binds directly with normMin/Max 0..1.
            try:
                self.ownerComp.par.Progress.val = (
                    self.frame / float(self.total) if self.total else 0.0
                )
            except Exception:
                pass  # par absent (older toe) — status text still shows
            self._send({"type": "progress", "id": self.job["id"],
                        "frame": self.frame, "total_frames": self.total})

    def _finish(self):
        """Stop recording; record = 0 is the documented "press Stop" that
        closes and finalizes the movie file."""
        self.state = "finishing"
        self._finishing_ticks = 0
        self.seconds_taken = round(time.time() - self.t0, 3)
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
        movieout = self.movieout
        seconds = getattr(self, "seconds_taken", 0.0) or round(
            time.time() - self.t0, 3)
        frames = self.total
        try:
            frames = int(movieout["total_frames_written"][0]) or self.total
        except Exception:
            pass  # info channel unavailable; report the expected count
        self._send({"type": "done", "id": self.job["id"],
                    "path": self.job["output"],
                    "total_frames": frames, "seconds": seconds})
        out = self.job["output"]
        self._set_status(f"idle — last: {os.path.basename(out)} "
                         f"({frames} frames, {seconds}s)")
        # Reset the slider-bound Progress par so the next job starts at 0.
        try:
            self.ownerComp.par.Progress.val = 0.0
        except Exception:
            pass
        self.job = None
        self.state = "idle"
        self.last_activity = time.time()

    def _cancel(self, job_id):
        if self.job and self.job["id"] == job_id and self.state in ("loading",
                                                                    "encoding"):
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
        f.par.outputresolution = "custom"
        try:
            f.par.resolution = (w, h)
        except Exception:
            try:
                f.par.resx = w
                f.par.resy = h
            except Exception as exc:
                raise ValueError(
                    f"cannot set fit TOP resolution to {w}x{h}: {exc}"
                )
        # Switch the data path: moviein -> fit -> movieout. moviein feeds
        # fit permanently (builder); only MvO's input source changes here.
        self._switch_mvo_input(f)
        self._set_status(f"encoding at {w}x{h} ({mode})")

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