"""Rigol DS8000-R Python instrument control library.

Creator: Jeff Michaelis
"""
from .driver import RigolDS8000R, Waveform, WaveformPreamble, Channel
from .exceptions import (RigolError, ConnectionError, CommandError,
                         NotConnectedError, ProtocolError, ValidationError)
from . import catalog

__version__ = "1.0.0"
__creator__ = "Jeff Michaelis"
__all__ = ["RigolDS8000R", "Waveform", "WaveformPreamble", "Channel",
           "RigolError", "ConnectionError", "CommandError", "NotConnectedError",
           "ProtocolError", "ValidationError", "catalog"]
