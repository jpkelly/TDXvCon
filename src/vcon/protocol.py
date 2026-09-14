"""Wire protocol: JSON lines over TCP between the front-end and the
TouchDesigner controller (or any future backend process).

Design:

- One JSON object per line, UTF-8, newline-terminated.
- Front-end → controller: ``submit`` and ``cancel`` requests.
- Controller → front-end: ``accepted``, ``progress``, ``done``, ``error``,
  plus a ``hello`` handshake so the driver knows the toe is ready for jobs.
- Every message has ``type`` and a ``id`` of the job it refers to (except
  ``hello``, which carries the protocol version).

The protocol is intentionally boring — a future daemon or GUI reuses these
exact messages as its event vocabulary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

#: Default TCP port the transcoder.toe listens on (localhost).
PROTOCOL_PORT = 7999

#: Bumped on breaking wire changes; the toe refuses mismatched versions.
PROTOCOL_VERSION = 1

MAX_LINE = 1 << 20  # 1 MiB guard


class ProtocolError(Exception):
    """Malformed wire data. Driver wraps this into DriverError."""


@dataclass(frozen=True)
class Submit:
    """Request: encode one output file from one input.

    ``params`` carries the *resolved* Movie File Out TOP settings built by the
    registry (codec, subtype, pixel format, container, quality, fps) — the toe
    applies them without knowing any codec semantics.
    """

    job_id: str
    input: str
    output: str
    params: dict[str, Any]

    @property
    def type(self) -> str:
        return "submit"


@dataclass(frozen=True)
class Cancel:
    """Request: stop a running/queued job."""

    job_id: str

    @property
    def type(self) -> str:
        return "cancel"


#: Union-ish alias for documentation only.
ProtocolMessage = Submit | Cancel


def encode_msg(obj: dict[str, Any] | Submit | Cancel) -> bytes:
    """Serialize one message to a newline-terminated wire line."""
    if isinstance(obj, Submit):
        obj = {
            "type": "submit",
            "id": obj.job_id,
            "input": obj.input,
            "output": obj.output,
            "params": obj.params,
        }
    elif isinstance(obj, Cancel):
        obj = {"type": "cancel", "id": obj.job_id}
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


def decode_msg(line: bytes | str) -> dict[str, Any]:
    """Parse one wire line into a dict; raises ProtocolError on junk."""
    if isinstance(line, bytes):
        if len(line) > MAX_LINE:
            raise ProtocolError(f"line exceeds {MAX_LINE} bytes")
        try:
            line = line.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProtocolError(f"invalid UTF-8: {exc}") from None
    obj = json.loads(line)
    if not isinstance(obj, dict) or "type" not in obj:
        raise ProtocolError(f"not a protocol message: {line[:120]!r}")
    return obj


# Controller → front-end messages -------------------------------------------------


def is_hello(msg: dict[str, Any]) -> bool:
    return msg.get("type") == "hello"


def hello_version(msg: dict[str, Any]) -> int:
    return int(msg.get("version", 0))


def make_hello(version: int = PROTOCOL_VERSION) -> dict[str, Any]:
    return {"type": "hello", "version": version}