"""PyVISA instrument driver for Rigol DS8104-R / DS8204-R / DS8034-R.

Creator: Jeff Michaelis

The driver has two control layers:
    * A small, checked set of convenience functions for everyday test code.
    * `write()`, `query()`, `query_block()`, and `commands` for EVERY other SCPI
      command and optional instrument feature in the reference guide.

The driver never silently resets an instrument during construction. It uses
locks around VISA transactions so concurrent Python callers cannot interleave
writes and reads in one SCPI exchange.
"""
import math
import re
import threading
from dataclasses import dataclass
from typing import Optional, Tuple, List

from .exceptions import (ConnectionError, CommandError, NotConnectedError,
                         ProtocolError, ValidationError)
from . import catalog


def _channel(number):
    """Ensure a valid analog input index before writing any SCPI command."""
    if isinstance(number, bool) or not isinstance(number, int) or number not in (1, 2, 3, 4):
        raise ValidationError("Channel must be an integer from 1 to 4")
    return number


def _numeric(value, min_value=None, max_value=None):
    """Serialize finite numeric arguments without adding physical-unit suffixes."""
    if isinstance(value, bool):
        raise ValidationError("A numerical value was expected, not bool")
    try:
        v = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValidationError("A finite numeric value is required")
    if not math.isfinite(v) or (min_value is not None and v < min_value) or (
            max_value is not None and v > max_value):
        raise ValidationError("Value {} outside permitted range [{}, {}]".format(
            value, min_value, max_value))
    return "{:.12g}".format(v)


def _choice(value, choices):
    v = str(value).strip().upper()
    if v not in choices:
        raise ValidationError("Expected one of {}; got {!r}".format(", ".join(choices), value))
    return v


def _on_off(value):
    """SCPI accepts ON/OFF or 1/0; reject ambiguous other strings."""
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    return _choice(value, ("ON", "OFF", "1", "0"))


def _scpi_value(value):
    """Serialize a scalar supplied to raw catalog-based commands."""
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    if isinstance(value, float):
        return _numeric(value)
    if isinstance(value, (int, str)):
        val = str(value).strip()
        # Avoid accidentally changing the SCPI command into multiple messages.
        if not val or '\n' in val or '\r' in val or ';' in val:
            raise ValidationError("SCPI value contains a newline, separator, or is empty")
        return val
    raise ValidationError("Unsupported SCPI value type: {}".format(type(value).__name__))


@dataclass(frozen=True)
class WaveformPreamble:
    """Ten parameters returned by :WAVeform:PREamble?."""
    format_code: int
    acquisition_type: int
    points: int
    count: int
    x_increment: float
    x_origin: float
    x_reference: float
    y_increment: float
    y_origin: float
    y_reference: float

    @classmethod
    def parse(cls, response):
        parts = [p.strip() for p in response.split(",")]
        if len(parts) != 10:
            raise ProtocolError("Expected 10 waveform preamble fields, got {}".format(len(parts)))
        try:
            return cls(int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]),
                       *(float(p) for p in parts[4:]))
        except (ValueError, TypeError) as exc:
            raise ProtocolError("Malformed waveform preamble: {}".format(response)) from exc


@dataclass
class Waveform:
    """Time/voltage data and its acquisition metadata.

    `voltages` may contain many samples; fetch smaller point batches when
    memory usage matters. `times()` generates the corresponding time vector.
    """
    channel: int
    preamble: WaveformPreamble
    voltages: List[float]

    def times(self):
        p = self.preamble
        return [(i - p.x_reference) * p.x_increment + p.x_origin
                for i in range(len(self.voltages))]

    def csv(self, filename):
        """Write the capture to an ordinary two-column CSV on the PC."""
        import csv
        with open(filename, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(("Time (s)", "Voltage (V)"))
            for time, voltage in zip(self.times(), self.voltages):
                writer.writerow(("{:.12g}".format(time), "{:.12g}".format(voltage)))


class ManualCommands:
    """Full programming-guide SCPI interface.

    Example:
        scope.commands.set(':CHANnel<n>:SCALe', 0.2, n=1)
        scale = scope.commands.get(':CHANnel<n>:SCALe', n=1)
        scope.commands.query(':MEASure:ITEM', 'VPP,CHANnel1')

    Optional SCPI elements in square brackets are expanded when specifying a
    name as it appears in the guide. For ambiguous optional source/output
    indices, prefer a fully specified literal command in scope.write/query.
    """
    def __init__(self, instrument):
        self.instrument = instrument

    @staticmethod
    def render(command, **indices):
        """Expand <n> placeholders and optional SCPI keyword brackets."""
        name = str(command).strip().rstrip("?")
        # Some manual paths have two <n>s. A literal command can disambiguate.
        for key, val in indices.items():
            if key != "n":
                raise ValidationError("Only named SCPI index 'n' is supported")
            _channel(val)
            name = name.replace("<" + key + ">", str(val))
        if "<n>" in name:
            raise ValidationError("The manual command requires n=1..4")
        # Square brackets mark optional SCPI keywords, NOT literal characters.
        name = name.replace("[", "").replace("]", "")
        if "<" in name or ">" in name:
            raise ValidationError("Unsupported unresolved SCPI placeholder in {}".format(name))
        if not name or '\n' in name or '\r' in name or ';' in name:
            raise ValidationError("Invalid SCPI command path")
        return name

    def list(self, pattern="*"):
        return catalog.entries(pattern)

    def describe(self, name):
        return catalog.find(name)

    def set(self, name, value, **indices):
        """Send a single-argument set form from the manual SCPI vocabulary."""
        path = self.render(name, **indices)
        return self.instrument.write(path + " " + _scpi_value(value))

    def get(self, name, *args, **indices):
        """Execute a query form, passing any documented query parameters."""
        path = self.render(name, **indices)
        suffix = " " + ",".join(_scpi_value(a) for a in args) if args else ""
        return self.instrument.query(path + "?" + suffix)

    def query(self, name, parameters="", **indices):
        """Query including complex, comma-separated manual parameter expressions."""
        path = self.render(name, **indices)
        p = str(parameters).strip()
        if '\n' in p or '\r' in p or ';' in p:
            raise ValidationError("Invalid SCPI query parameters")
        return self.instrument.query(path + "?" + (" " + p if p else ""))

    def action(self, name, **indices):
        return self.instrument.write(self.render(name, **indices))


class Channel:
    """Analog channel facade. All analog channels are numbered 1 through 4."""
    def __init__(self, scope, number):
        self.scope = scope
        self.number = _channel(number)

    def _cmd(self, setting):
        return ":CHANnel{}:{}".format(self.number, setting)

    def _set(self, setting, value):
        self.scope.write("{} {}".format(self._cmd(setting), value))

    def _get(self, setting):
        return self.scope.query(self._cmd(setting) + "?")

    def enable(self, state=True):
        self._set("DISPlay", _on_off(state))

    def is_enabled(self):
        return self._get("DISPlay") == "1"

    def coupling(self, value=None):
        if value is None: return self._get("COUPling")
        self._set("COUPling", _choice(value, ("AC", "DC", "GND")))

    def impedance(self, ohms=None):
        """Return 'OMEG' or 'FIFT'; set 1e6/50 or equivalent SCPI token."""
        if ohms is None: return self._get("IMPedance")
        v = str(ohms).upper()
        if v in ("50", "FIFT", "FIFTY"): self._set("IMPedance", "FIFTy")
        elif v in ("1000000", "1000000.0", "1E6", "OMEG"): self._set("IMPedance", "OMEG")
        else: raise ValidationError("Impedance must be 50 or 1000000 ohms")

    def scale(self, volts_per_div=None):
        if volts_per_div is None: return float(self._get("SCALe"))
        self._set("SCALe", _numeric(volts_per_div, 0.001))

    def offset(self, volts=None):
        if volts is None: return float(self._get("OFFSet"))
        self._set("OFFSet", _numeric(volts))

    def probe(self, ratio=None):
        """Configure ratio with the discrete 1/2/5 decade list in the manual."""
        if ratio is None: return float(self._get("PROBe"))
        permitted = [base * 10.0 ** exponent for exponent in range(-4, 5)
                     for base in (1, 2, 5) if base * 10.0 ** exponent <= 50000]
        if float(ratio) not in permitted:
            raise ValidationError("Probe ratio is not one of the documented 1/2/5 steps")
        self._set("PROBe", _numeric(ratio))

    def bandwidth_limit(self, setting=None):
        """DS8034-R accepts 20M, 250M, OFF (no 500M setting)."""
        if setting is None: return self._get("BWLimit")
        options = ("20M", "250M", "OFF") if "DS8034" in self.scope.model else (
            "20M", "250M", "500M", "OFF")
        self._set("BWLimit", _choice(setting, options))

    def invert(self, state=None):
        if state is None: return self._get("INVert") == "1"
        self._set("INVert", _on_off(state))

    def vernier(self, state=None):
        if state is None: return self._get("VERNier") == "1"
        self._set("VERNier", _on_off(state))

    def units(self, value=None):
        if value is None: return self._get("UNITs")
        self._set("UNITs", _choice(value, ("VOLTage", "WATT", "AMPere", "UNKNown",
                                          "VOLT", "AMP", "UNKN")))

    def raw_set(self, keyword, value):
        self._set(keyword, _scpi_value(value))

    def raw_get(self, keyword):
        return self._get(keyword)


class RigolDS8000R:
    """Reusable connection and SCPI operations for Rigol DS8000-R instruments.

    Parameters
    ----------
    resource: str
        VISA resource e.g. 'TCPIP0::192.168.1.50::INSTR',
        'TCPIP0::192.168.1.50::5555::SOCKET', 'USB0::...::INSTR'.
    timeout: int
        Timeout for a VISA operation in milliseconds (default 10000).
    backend: str or None
        Optional PyVISA backend string such as '@py'. Default uses installed VISA.
    instrument: object or None
        Inject a PyVISA-compatible session (for tests or custom transport).
    check_errors: bool
        After each ordinary write, drain :SYSTem:ERRor? and raise on errors.
        Off by default for speed and compatibility during state transitions.
    """
    def __init__(self, resource=None, timeout=10000, backend=None,
                 instrument=None, check_errors=False):
        self.resource = resource
        self.timeout = int(timeout)
        self.backend = backend
        self.check_errors = bool(check_errors)
        self._session = instrument
        self._manager = None
        self._owns_session = instrument is None
        self._lock = threading.RLock()
        self._idn = None
        self.commands = ManualCommands(self)
        if instrument is not None:
            self._configure_session()

    def _configure_session(self):
        """Apply timeouts and terminations where supported by the transport."""
        try:
            self._session.timeout = self.timeout
            self._session.write_termination = "\n"
            self._session.read_termination = "\n"
        except (AttributeError, ValueError):
            # Some injectable backends expose neither of these properties.
            pass

    def connect(self):
        """Open a VISA session, identify the instrument, and keep it reusable."""
        with self._lock:
            if self._session is None:
                if not self.resource:
                    raise ConnectionError("A VISA resource string is required")
                try:
                    import pyvisa
                    self._manager = pyvisa.ResourceManager(self.backend) if self.backend else pyvisa.ResourceManager()
                    self._session = self._manager.open_resource(self.resource)
                    self._configure_session()
                except Exception as exc:
                    self._session = None
                    raise ConnectionError("Cannot connect to {}: {}".format(self.resource, exc)) from exc
            try:
                self._idn = self.query("*IDN?")
            except Exception as exc:
                if self._owns_session: self.close()
                raise ConnectionError("Connected, but *IDN? failed: {}".format(exc)) from exc
            return self

    def close(self):
        """Close only sessions owned by this driver; never close an injected session."""
        with self._lock:
            if self._session is not None and self._owns_session:
                try: self._session.close()
                finally: self._session = None
            if self._manager is not None:
                try: self._manager.close()
                finally: self._manager = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    @property
    def idn(self):
        return self._idn or self.query("*IDN?")

    @property
    def model(self):
        parts = self.idn.split(",")
        return parts[1].strip().upper() if len(parts)>1 else "UNKNOWN"

    def _require_session(self):
        if self._session is None:
            raise NotConnectedError("Call connect() first or use a with RigolDS8000R(...) block")
        return self._session

    @staticmethod
    def _validate_command(text):
        if not isinstance(text, str) or not text.strip():
            raise ValidationError("SCPI command must be a nonempty string")
        if any(c in text for c in ("\n", "\r", ";")):
            raise ValidationError("Multi-line / chained SCPI commands are disabled; send separately")
        return text.strip()

    def write(self, command):
        """Issue one SCPI command, with optional post-write error checking."""
        command = self._validate_command(command)
        with self._lock:
            self._require_session().write(command)
            if self.check_errors and not command.upper().startswith(":SYST:ERR") and not command.upper().startswith(":SYSTEM:ERROR"):
                err = self.errors()
                if err:
                    raise CommandError(command, err)

    def query(self, command):
        """Issue a single text query and strip outer whitespace/newlines."""
        command = self._validate_command(command)
        with self._lock:
            response = self._require_session().query(command)
            return str(response).strip()

    def query_float(self, command):
        try:
            return float(self.query(command))
        except ValueError as exc:
            raise ProtocolError("Expected numeric response from {}".format(command)) from exc

    def query_int(self, command):
        try:
            return int(float(self.query(command)))
        except ValueError as exc:
            raise ProtocolError("Expected integer response from {}".format(command)) from exc

    def query_block(self, command, word=False, is_big_endian=False):
        """Read an IEEE 488.2 definite-length binary response via PyVISA.

        PyVISA's block reader consumes the ASCII #Nlength header, checks the
        byte count, and handles the expected termination. `word=True` chooses
        16-bit samples (Rigol documents high 8 bits as zero for waveform WORD).
        This also supports image and bus export data blocks. Use the
        is_big_endian argument for 16-bit data if your firmware requires it.
        """
        command = self._validate_command(command)
        with self._lock:
            try:
                session = self._require_session()
                data = session.query_binary_values(command, datatype="H" if word else "B",
                                                    is_big_endian=is_big_endian, container=list,
                                                    header_fmt="ieee", expect_termination=True)
                return bytes([v & 255 for v in data]) if not word else list(data)
            except Exception as exc:
                raise ProtocolError("Binary block transfer failed for {}: {}".format(command, exc)) from exc

    def errors(self, max_errors=32):
        """Drain the SCPI error queue until zero is returned or a cap is reached."""
        found = []
        with self._lock:
            for _ in range(max_errors):
                msg = self.query(":SYSTem:ERRor?")
                # Different firmware versions return 0,"No error" or +0,...
                if re.match(r'^\s*\+?0(?:\s*(?:,|$))', msg):
                    break
                found.append(msg)
        return found

    def clear_status(self):
        """Clear SCPI status/error registers (not the acquisition display)."""
        self.write("*CLS")

    def reset(self):
        """Factory reset is deliberately an explicit method, never automatic."""
        self.write("*RST")

    def operation_complete(self):
        return self.query("*OPC?") == "1"

    def channel(self, number):
        return Channel(self, number)

    def run(self):
        self.write(":RUN")

    def stop(self):
        self.write(":STOP")

    def single(self):
        self.write(":SINGle")

    def force_trigger(self):
        self.write(":TFORce")

    def autoscale(self):
        self.write(":AUToscale")

    def clear_display(self):
        self.write(":CLEar")

    def sample_rate(self):
        return self.query_float(":ACQuire:SRATe?")

    def acquisition_type(self, mode=None):
        if mode is None: return self.query(":ACQuire:TYPE?")
        self.write(":ACQuire:TYPE " + _choice(mode, ("NORMal", "AVERages", "PEAK", "HRESolution",
                                                         "NORM", "AVER", "HRES")))

    def acquisition_averages(self, count=None):
        if count is None: return self.query_int(":ACQuire:AVERages?")
        if not isinstance(count, int) or isinstance(count,bool) or count < 2 or count > 65536 or count & (count - 1):
            raise ValidationError("Average count must be 2,4,8,...,65536")
        self.write(":ACQuire:AVERages {}".format(count))

    def memory_depth(self, value=None):
        if value is None: return self.query(":ACQuire:MDEPth?")
        self.write(":ACQuire:MDEPth " + _choice(value, (
            "AUTO", "1K", "10K", "100K", "1M", "10M", "25M", "50M", "100M", "125M", "250M", "500M")))

    def time_scale(self, seconds_per_div=None):
        if seconds_per_div is None: return self.query_float(":TIMebase:MAIN:SCALe?")
        self.write(":TIMebase:MAIN:SCALe " + _numeric(seconds_per_div, 2e-10, 1000.0))

    def time_offset(self, seconds=None):
        if seconds is None: return self.query_float(":TIMebase:MAIN:OFFSet?")
        self.write(":TIMebase:MAIN:OFFSet " + _numeric(seconds))

    def edge_trigger(self, channel=1, level=None, slope="POS"):
        """Select edge trigger mode, source, polarity and optional threshold."""
        _channel(channel)
        self.write(":TRIGger:MODE EDGE")
        self.write(":TRIGger:EDGE:SOURce CHANnel{}".format(channel))
        self.write(":TRIGger:EDGE:SLOPe " + _choice(slope, ("POS", "NEG", "RFAL", "POSITIVE", "NEGATIVE", "RFALL")))
        if level is not None:
            self.write(":TRIGger:EDGE:LEVel " + _numeric(level))

    def trigger_state(self):
        return self.query(":TRIGger:STATus?")

    def measure(self, measurement="VPP", channel=1, second_channel=None):
        """Return one automatic measurement; supported types in README/catalog.

        Example: `scope.measure('VRMS', 1)` reads AC+DC RMS of CH1.
        """
        _channel(channel)
        args = "{},CHANnel{}".format(_choice(measurement, _MEASUREMENTS), channel)
        if second_channel is not None:
            args += ",CHANnel{}".format(_channel(second_channel))
        return self.query_float(":MEASure:ITEM? " + args)

    def waveform(self, channel=1, points=1000, mode="NORM", binary=True,
                 start=1):
        """Capture samples and convert instrument counts into physical volts.

        For RAW mode, stop the instrument before calling this method. The guide
        disallows reading internal-memory waveform data while acquisition runs.
        The method preserves the existing waveform source/mode/format/start/stop
        settings where those settings can be queried, even if the read fails.
        """
        _channel(channel)
        mode = _choice(mode, ("NORM", "NORMAL", "RAW", "MAX", "MAXIMUM"))
        mode = {"NORMAL": "NORM", "MAXIMUM": "MAX"}.get(mode, mode)
        if not isinstance(points,int) or isinstance(points,bool) or points<1:
            raise ValidationError("points must be a positive integer")
        if mode=="NORM" and (start < 1 or start+points-1>1000):
            raise ValidationError("NORM waveform window must remain within 1..1000")
        if not isinstance(start,int) or start<1:
            raise ValidationError("start must be a positive integer")
        # All waveform setup and transfer steps must remain atomic.
        with self._lock:
            preserve = {}
            for keyword in ("SOURce", "MODE", "FORMat", "STARt", "STOP", "POINts"):
                try: preserve[keyword] = self.query(":WAVeform:{}?".format(keyword))
                except Exception: pass
            try:
                self.write(":WAVeform:SOURce CHANnel{}".format(channel))
                self.write(":WAVeform:MODE " + mode)
                self.write(":WAVeform:FORMat " + ("BYTE" if binary else "ASCii"))
                self.write(":WAVeform:POINts {}".format(points))
                self.write(":WAVeform:STARt {}".format(start))
                self.write(":WAVeform:STOP {}".format(start+points-1))
                pre = WaveformPreamble.parse(self.query(":WAVeform:PREamble?"))
                if binary:
                    codes = self.query_block(":WAVeform:DATA?")
                    # The manual specifies (code - YORigin - YREFerence)*YINCrement.
                    voltages = [(int(v)-pre.y_origin-pre.y_reference)*pre.y_increment for v in codes]
                else:
                    text = self.query(":WAVeform:DATA?")
                    voltages = [float(t) for t in text.split(",") if t.strip()]
                return Waveform(channel,pre,voltages)
            finally:
                # Preserve even if a timeout or short-block transfer occurs.
                for keyword in ("SOURce", "MODE", "FORMat", "POINts", "STARt", "STOP"):
                    if keyword in preserve:
                        try: self.write(":WAVeform:{} {}".format(keyword,preserve[keyword]))
                        except Exception: pass


# Supported items from :MEASure:ITEM in the supplied programming guide.
_MEASUREMENTS = ("VMAX", "VMIN", "VPP", "VTOP", "VBASE", "VAMP", "VAVG", "VRMS",
                 "OVERSHOOT", "PRESHOOT", "MAREA", "MPAREA", "PERIOD", "FREQUENCY",
                 "RTIME", "FTIME", "PWIDTH", "NWIDTH", "PDUTY", "NDUTY", "TVMAX",
                 "TVMIN", "PSLEWRATE", "NSLEWRATE", "VUPPER", "VMID", "VLOWER",
                 "VARIANCE", "PVRMS", "PPULSES", "NPULSES", "PEDGES", "NEDGES",
                 "RRDELAY", "RFDELAY", "FRDELAY", "FFDELAY", "RRPHASE", "RFPHASE",
                 "FRPHASE", "FFPHASE")
