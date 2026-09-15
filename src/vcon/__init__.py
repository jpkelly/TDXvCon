"""vcon — GPU video transcoding, FFmpeg-style, powered by TouchDesigner.

Public API lives at the package root; submodules may be imported directly::

    from vcon import CodecSpec, JobSpec, Registry, Transcoder
"""

from vcon.errors import (
    VconError,
    ConfigError,
    CodecError,
    DriverError,
    InputError,
    OutputError,
    ParseError,
)
from vcon.events import Event, EventBus, log_to_stderr
from vcon.models import JobSpec, Job, JobStatus
from vcon.registry import CodecSpec, Registry, platform_of_current_machine
from vcon.protocol import (
    PROTOCOL_PORT,
    encode_msg,
    decode_msg,
    Submit,
    Cancel,
    ProtocolMessage,
)
from vcon.queue_manager import QueueManager, QueueOptions
from vcon.driver import Driver, DriverContext
from vcon.mock_driver import MockDriver
from vcon.td_driver import TouchDesignerDriver
from vcon.transcoder import Transcoder, TranscoderOptions
from vcon.config import load_config, save_config, Config, find_touchdesigner

__version__ = "0.1.4"

__all__ = [
    "VconError",
    "ConfigError",
    "CodecError",
    "DriverError",
    "InputError",
    "OutputError",
    "ParseError",
    "Event",
    "EventBus",
    "log_to_stderr",
    "JobSpec",
    "Job",
    "JobStatus",
    "CodecSpec",
    "Registry",
    "platform_of_current_machine",
    "PROTOCOL_PORT",
    "encode_msg",
    "decode_msg",
    "Submit",
    "Cancel",
    "ProtocolMessage",
    "QueueManager",
    "QueueOptions",
    "Driver",
    "DriverContext",
    "MockDriver",
    "TouchDesignerDriver",
    "Transcoder",
    "TranscoderOptions",
    "load_config",
    "save_config",
    "Config",
    "find_touchdesigner",
    "__version__",
]