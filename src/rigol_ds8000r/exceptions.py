"""Exceptions for the Rigol DS8000-R Python driver.

"""
# Creator: Jeff Michaelis


class RigolError(Exception):
    """Base class for failures involving a DS8000-R oscilloscope."""


class ConnectionError(RigolError):
    """The configured instrument could not be opened or contacted."""


class CommandError(RigolError):
    """The oscilloscope reported an SCPI error."""

    def __init__(self, command, messages):
        self.command = command
        self.messages = list(messages)
        super(CommandError, self).__init__(
            "{}: {}".format(command, "; ".join(self.messages))
        )


class ProtocolError(RigolError):
    """A response did not have the expected SCPI/TMC representation."""


class ValidationError(RigolError, ValueError):
    """A Python argument is invalid or outside a known instrument limit."""


class NotConnectedError(ConnectionError):
    """The driver has not established an active session."""
