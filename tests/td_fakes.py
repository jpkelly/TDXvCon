"""Minimal TouchDesigner stand-ins for exercising toe/vcon_controller.py.

The controller is plain Python that only touches TD through a small surface:
operator ``par`` collections, a few TOP/CHOP attributes, the TCPIP DAT's
``send`` and the ``debug`` builtin. These fakes model exactly that surface,
including the two TD behaviours the controller's correctness depends on:

- a menu parameter given an unknown token silently falls back to entry 0;
- Movie File Out starts a NEW file only on a record off→on edge, and an
  ``addframe`` pulse captures whatever frame its input currently shows.

Menus are the live values read from TouchDesigner 2025.33230 / 2025.33407.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

CONTROLLER_PATH = (Path(__file__).resolve().parent.parent
                   / "toe" / "vcon_controller.py")

PLAYMODE_MENU = ["locked", "specify", "sequential", "timecodeop"]
INDEXUNIT_MENU = ["indices", "frames", "seconds", "fraction"]
VIDEOCODEC_MENU = ["rle", "notchlc", "hap", "prores", "cineform", "h264",
                   "h265"]
CONTAINER_MENU = ["mov", "mp4", "avi", "mkv"]
FIT_MENU = ["fill", "fithorz", "fitvert", "fitbest", "fitoutside",
            "nativeres"]
FIT_RES_MENU = ["useinput", "eighth", "quarter", "half", "twotimes",
                "fourtimes", "eighttimes", "custom"]


class Par:
    """One parameter. Menu pars emulate TD's silent fallback to entry 0."""

    def __init__(self, val=None, menu=None, on_set=None, on_pulse=None):
        self._val = val
        self.menuNames = list(menu) if menu else []
        self.writes = []          # every value actually stored, in order
        self._on_set = on_set
        self._on_pulse = on_pulse
        self.owner = None
        self.name = ""

    @property
    def val(self):
        return self._val

    @val.setter
    def val(self, value):
        if self.menuNames and value not in self.menuNames:
            value = self.menuNames[0]          # TD: unknown token -> entry 0
        old = self._val
        self._val = value
        self.writes.append(value)
        if self._on_set:
            self._on_set(old, value)

    def eval(self):
        return self._val

    def pulse(self):
        if self._on_pulse:
            self._on_pulse()


class Pars:
    """An operator's ``par`` collection: attribute reads give the Par,
    attribute writes set its value, unknown names raise like TD."""

    def __init__(self, owner, pars):
        object.__setattr__(self, "_p", dict(pars))
        for name, par in pars.items():
            par.owner, par.name = owner, name

    def __getattr__(self, name):
        try:
            return self._p[name]
        except KeyError:
            raise AttributeError(f"td.ParCollection has no '{name}'") from None

    def __setattr__(self, name, value):
        getattr(self, name).val = value


class FakeOp:
    def __init__(self, name, **pars):
        self.name = name
        self.path = f"/project1/vcon/{name}"
        self.par = Pars(self, pars)


class FakeMovieIn(FakeOp):
    """Movie File In: shows source frame ``par.index`` immediately.

    ``opens = False`` models a file TD cannot open: as measured live, the
    TOP then shows a 256x256 placeholder (numImages 1, sample_rate 1),
    warns "Failed to open file" and the Info CHOP's true_length is 0."""

    def __init__(self, frames=10, rate=24.0, width=1920, height=1080,
                 has_audio=False):
        super().__init__(
            "moviein",
            file=Par(""),
            playmode=Par("locked", PLAYMODE_MENU),
            indexunit=Par("frames", INDEXUNIT_MENU),
            index=Par(0),
            prereadframes=Par(30),
        )
        self.frames = frames
        self._rate = rate
        self._size = (width, height)
        self.has_audio = has_audio
        self.opens = True

    @property
    def numImages(self):
        return self.frames if self.opens else 1

    @property
    def rate(self):
        return self._rate if self.opens else 1.0

    @property
    def fileWidth(self):
        return self._size[0] if self.opens else 256

    @property
    def fileHeight(self):
        return self._size[1] if self.opens else 256

    def warnings(self):
        return "" if self.opens else \
            "Warning: Failed to open file. (/project1/vcon/moviein)"

    @property
    def shown_index(self):
        return self.par.index.eval()


class FakeInfo(FakeOp):
    """Info CHOP on moviein: ``info['sample_rate'][0]`` etc."""

    def __init__(self, moviein):
        super().__init__("info")
        self._moviein = moviein

    def __getitem__(self, chan):
        if chan == "sample_rate":
            return [self._moviein.rate]
        if chan == "mv_has_audio":
            return [1.0 if self._moviein.has_audio else 0.0]
        if chan == "true_length":
            return [float(self._moviein.frames if self._moviein.opens else 0)]
        raise KeyError(chan)


class Connector:
    def __init__(self, owner):
        self.owner = owner

    def connect(self, src):
        self.owner.inputs = [src]

    def disconnect(self):
        self.owner.inputs = []


class FakeMovieOut(FakeOp):
    """Movie File Out. ``files`` maps each file started to the source
    frame indices captured into it. A file starts only on a record off→on
    edge; it is created on disk at that moment, as TD does."""

    def __init__(self, moviein):
        self._moviein = moviein
        self.files = {}
        self.current = None
        self.fail_addframe = False
        #: False simulates a file that never lands on disk.
        self.create_files = True
        #: True models a codec this OS cannot encode (TD 2025.33230, macOS):
        #: record=1 opens no recording, writes nothing, sets ``error_text``.
        self.fail_open = False
        self.error_text = ""
        super().__init__(
            "movieout",
            file=Par(""),
            record=Par(0, on_set=self._on_record),
            pause=Par(0),
            addframe=Par(None, on_pulse=self._on_addframe),
            fps=Par(60.0),
            quality=Par(0.5),
            videocodec=Par("rle", VIDEOCODEC_MENU),
            videocodectype=Par(None),
            moviepixelformat=Par(None),
            moviecontainer=Par("mov", CONTAINER_MENU),
        )
        self.inputs = [moviein]
        self.inputConnectors = [Connector(self)]

    def errors(self, recurse=False):
        return self.error_text

    def cook(self, force=False):
        pass

    def _on_record(self, old, new):
        if not old and new and self.fail_open:
            return
        if not old and new:
            path = self.par.file.eval()
            self.current = path
            self.files[path] = []
            if self.create_files:
                Path(path).write_bytes(b"")
        elif old and not new:
            self.current = None

    def _on_addframe(self):
        if self.fail_addframe:
            raise RuntimeError("simulated MvO write failure")
        if self.current is not None and self.par.record.eval():
            self.files[self.current].append(self._moviein.shown_index)


class FakeFit(FakeOp):
    """Fit TOP fed by Movie File In: its output size follows
    ``outputresolution`` (a scale token, 'custom', or the input size)."""

    SCALES = {"eighth": 1 / 8, "quarter": 1 / 4, "half": 1 / 2,
              "twotimes": 2, "fourtimes": 4, "eighttimes": 8}

    def __init__(self, moviein=None):
        super().__init__(
            "fit",
            fit=Par("fitbest", FIT_MENU),
            outputresolution=Par("useinput", FIT_RES_MENU),
            resolutionw=Par(1280),
            resolutionh=Par(720),
        )
        self._moviein = moviein
        self.cooks = 0

    def cook(self, force=False):
        self.cooks += 1

    def _size(self):
        res = self.par.outputresolution.eval()
        if res == "custom":
            return self.par.resolutionw.eval(), self.par.resolutionh.eval()
        w, h = self._moviein.fileWidth, self._moviein.fileHeight
        k = self.SCALES.get(res, 1)
        return int(w * k), int(h * k)

    @property
    def width(self):
        return self._size()[0]

    @property
    def height(self):
        return self._size()[1]


class FakeMvoInfo(FakeOp):
    """Info CHOP on Movie File Out. ``active_records`` stays 1 for
    ``flush_cooks`` cooks after record goes 0, as VP9/VVC did live while
    the file was still being written (None = forever)."""

    def __init__(self, movieout, flush_cooks=0):
        super().__init__("mvo_info")
        self._movieout = movieout
        self.flush_left = flush_cooks

    def cook(self, force=False):
        if not self._movieout.par.record.eval() and self.flush_left:
            self.flush_left -= 1

    def __getitem__(self, chan):
        mvo = self._movieout
        if chan == "active_records":
            if mvo.fail_open:
                return [0.0]
            busy = mvo.par.record.eval() or self.flush_left != 0
            return [1.0 if busy else 0.0]
        if chan == "total_frames_written":
            return [float(len(mvo.files.get(mvo.current, [])))
                    if mvo.current else 0.0]
        raise KeyError(chan)


class FakeTcp(FakeOp):
    def __init__(self, localaddress=""):
        super().__init__("tcpip", localaddress=Par(localaddress))
        self.sent = []

    def send(self, text, terminator="\n"):
        self.sent.append(json.loads(text))


class FakeComp(FakeOp):
    """The vCon Base COMP: children by name plus Status/Progress pars."""

    def __init__(self, children):
        super().__init__("vcon", Status=Par(""), Progress=Par(0.0))
        self.path = "/project1/vcon"
        self._children = {c.name: c for c in children}
        self.storage = {}

    def op(self, name):
        return self._children.get(name)

    # COMP storage, as TD documents it: store / fetch / unstore.
    def store(self, key, value):
        self.storage[key] = value
        return value

    def fetch(self, key, default=None, search=True, storeDefault=False):
        return self.storage.get(key, default)

    def unstore(self, keys1, *morekeys):
        for key in (keys1, *morekeys):
            self.storage.pop(key, None)


class FakeProject:
    """TD's ``project`` global: only the FPS (cookRate) is modelled.
    ``rates`` lists every value written, in order."""

    def __init__(self, cook_rate=60.0):
        self._rate = float(cook_rate)
        self.rates = []

    @property
    def cookRate(self):
        return self._rate

    @cookRate.setter
    def cookRate(self, value):
        self._rate = float(value)
        self.rates.append(self._rate)


def ffmpeg_report(path=None):
    """A validated fake, or a completed search with nothing installed."""
    return {
        "state": "ready" if path else "missing", "path": path,
        "version": "test" if path else None,
        "error": "" if path else "ffmpeg not found", "failures": (),
        "muxers": frozenset(("mov", "mp4", "matroska", "webm", "avi",
                             "wav", "aiff", "ipod", "mp3")),
        "encoders": frozenset(("pcm_s16le", "pcm_s24le", "pcm_s16be",
                               "pcm_s24be", "aac", "alac", "libmp3lame", "libopus")),
    }


def load_controller_module():
    """Import toe/vcon_controller.py with TD's ``debug`` builtin stubbed."""
    spec = importlib.util.spec_from_file_location(
        "vcon_controller_under_test", CONTROLLER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.debug = lambda *args, **kwargs: None
    # Never start real discovery/probes from simulated encode tests.
    mod.VconExt.FFmpegStatus = lambda self, **kwargs: ffmpeg_report()
    return mod


class Rig:
    """A controller wired to fakes, plus helpers to drive it."""

    def __init__(self, frames=10, rate=24.0, has_audio=False,
                 width=1920, height=1080, flush_cooks=None,
                 cook_rate=60.0):
        self.mod = load_controller_module()
        self.project = FakeProject(cook_rate)
        self.mod.project = self.project
        self.moviein = FakeMovieIn(frames=frames, rate=rate,
                                   width=width, height=height,
                                   has_audio=has_audio)
        self.info = FakeInfo(self.moviein)
        self.movieout = FakeMovieOut(self.moviein)
        self.fit = FakeFit(self.moviein)
        self.tcp = FakeTcp()
        children = [self.moviein, self.info, self.movieout, self.fit,
                    self.tcp]
        # mvo_info only when asked for: toes built before it have none.
        if flush_cooks is not None:
            self.mvo_info = FakeMvoInfo(self.movieout, flush_cooks)
            children.append(self.mvo_info)
        self.comp = FakeComp(children)
        self.ext = self.mod.VconExt(self.comp)

    def submit(self, src, dst, **params):
        self.ext.onReceive(json.dumps({
            "type": "submit", "id": f"job-{Path(dst).name}",
            "input": str(src), "output": str(dst),
            "params": {"videocodec": "notchlc", "fps": "auto", **params},
        }))

    def run(self, max_ticks=1000):
        """Tick until the controller returns to idle."""
        for _ in range(max_ticks):
            if self.ext.state == "idle":
                return
            self.ext.onFrame()
        raise AssertionError(f"still {self.ext.state} after {max_ticks} ticks")

    def tick_until(self, state, max_ticks=100):
        for _ in range(max_ticks):
            if self.ext.state == state:
                return
            self.ext.onFrame()
        raise AssertionError(f"never reached {state}; at {self.ext.state}")

    def events(self, etype):
        return [m for m in self.tcp.sent if m.get("type") == etype]
