"""Exception hierarchy for vcon.

Every failure the CLI reports maps to one of these. Codes are stable strings
used by tests and (later) the TD controller so errors survive the wire.
"""

from __future__ import annotations


class VconError(Exception):
    """Base class for all vcon errors."""

    #: Stable machine-readable code (e.g. "input-missing").
    code: str = "vcon-error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class ConfigError(VconError):
    """Bad configuration or missing/broken TouchDesigner install."""

    code = "config-error"


class CodecError(VconError):
    """Unknown codec/subtype/quality, or codec unavailable on this platform."""

    code = "codec-error"


class InputError(VconError):
    """Input file missing, unreadable, or undecodable."""

    code = "input-error"


class OutputError(VconError):
    """Output path invalid, exists without -y, or not writable."""

    code = "output-error"


class DriverError(VconError):
    """The encoding backend (mock or TouchDesigner) failed."""

    code = "driver-error"


class ParseError(VconError):
    """The CLI arguments could not be parsed."""

    code = "parse-error"