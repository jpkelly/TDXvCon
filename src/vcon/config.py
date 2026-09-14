"""Configuration and TouchDesigner discovery.

Resolution order (ffmpeg-style precedence):

1. ``--td-path`` flag (caller passes Path directly)
2. ``VCON_TDPATH`` environment variable
3. config file (``~/.config/vcon/config.json``, XDG-ish)
4. well-known install locations
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from vcon.errors import ConfigError

#: Well-known install locations per platform (searched in order).
_TD_CANDIDATES: dict[str, tuple[str, ...]] = {
    "mac": (
        "/Applications/TouchDesigner.app/Contents/MacOS/TouchDesigner",
        "/Applications/TouchDesigner.app/Contents/MacOS/TouchPlayer",
    ),
    "windows": (
        r"C:\Program Files\Derivative\TouchDesigner\bin\TouchDesigner.exe",
        r"C:\Program Files\Derivative\TouchDesigner\bin\TouchPlayer.exe",
    ),
}

APP_DIR_NAME = "vcon"


def config_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(
            os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        )
    return base / APP_DIR_NAME


def config_path() -> Path:
    return config_dir() / "config.json"


@dataclass
class Config:
    """Persisted user preferences (td_path is the only knob that matters)."""

    td_path: str | None = None
    port: int = 7999
    extras: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "td_path": self.td_path,
            "port": self.port,
            "extras": self.extras,
        }


def load_config(path: Path | None = None) -> Config:
    p = path or config_path()
    if not p.exists():
        return Config()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ConfigError(f"unreadable config at {p}: {exc}") from None
    return Config(
        td_path=data.get("td_path"),
        port=int(data.get("port", 7999)),
        extras=dict(data.get("extras") or {}),
    )


def save_config(cfg: Config, path: Path | None = None) -> Path:
    p = path or config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
    return p


def find_touchdesigner(
    flag_path: Path | None = None,
    *,
    env: dict[str, str] | None = None,
    config: Config | None = None,
) -> Path | None:
    """Resolve the TouchDesigner binary path; None if not found anywhere."""
    env = env if env is not None else dict(os.environ)

    # 1. explicit flag
    if flag_path is not None:
        if not flag_path.exists():
            raise ConfigError(f"--td-path does not exist: {flag_path}")
        return flag_path

    # 2. environment
    env_path = env.get("VCON_TDPATH")
    if env_path:
        p = Path(env_path)
        if not p.exists():
            raise ConfigError(f"VCON_TDPATH does not exist: {env_path}")
        return p

    # 3. config file
    cfg = config if config is not None else load_config()
    if cfg.td_path:
        p = Path(cfg.td_path)
        if not p.exists():
            raise ConfigError(f"configured td_path does not exist: {cfg.td_path}")
        return p

    # 4. well-known locations
    machine = "mac" if sys.platform.startswith("darwin") else (
        "windows" if sys.platform.startswith("win") else None
    )
    if machine in _TD_CANDIDATES:
        for cand in _TD_CANDIDATES[machine]:
            if Path(cand).exists():
                return Path(cand)

    return None


def resolve_toe_path(flag_toe: Path | None = None) -> Path:
    """Locate the transcoder toe.

    Resolution order:
      1. explicit -toe-path flag
      2. VCON_TOE environment variable  (development override)
      3. installed package data         (pipx / pip install)
      4. dev checkout: toe/ beside src/ (running from a git clone)

    Step 2 matters when vcon is installed with pipx but you are actively
    rebuilding the toe: set VCON_TOE to the repo copy so the installed
    command picks up your latest build instead of a stale packaged one.
    """
    if flag_toe is not None:
        if not flag_toe.exists():
            raise ConfigError(f"-toe-path does not exist: {flag_toe}")
        return flag_toe

    env_toe = os.environ.get("VCON_TOE")
    if env_toe:
        p = Path(env_toe)
        if not p.exists():
            raise ConfigError(f"VCON_TOE does not exist: {env_toe}")
        return p

    # 1. installed package data (pipx / pip install)
    pkg_dir = Path(__file__).parent
    candidate = pkg_dir / "data" / "transcoder.toe"
    if candidate.exists():
        return candidate
    # 2. dev checkout: toe/ sits next to src/
    dev_toe = pkg_dir.parent.parent / "toe" / "transcoder.toe"
    if dev_toe.exists():
        return dev_toe
    raise ConfigError(
        "transcoder.toe not found — build it once in TouchDesigner "
        "(run toe/build_network.py inside TD), or reinstall vcon"
    )