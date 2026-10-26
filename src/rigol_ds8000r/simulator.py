"""Offline simulation of core DS8000-R SCPI behavior for software CI.

Creator: Jeff Michaelis

This is a deliberately minimal test double, NOT a physics simulation and NOT
proof that a connected instrument accepts every command in the catalogue.
"""
import math
import re
import struct


class SimulatedDS8000R:
    """PyVISA-like object implementing enough SCPI to run automated smoke tests."""
    def __init__(self):
        self.timeout = 10000
        self.read_termination = "\n"
        self.write_termination = "\n"
        self.closed = False
        self._errors = []
        self.settings = {
            ":ACQUIRE:TYPE": "NORM", ":ACQUIRE:SRATE": "2.5E9",
            ":TIMEBASE:MAIN:SCALE": "1E-3", ":TRIGGER:MODE": "EDGE",
            ":TRIGGER:STATUS": "RUN", ":WAVEFORM:SOURCE": "CHAN1",
            ":WAVEFORM:MODE": "NORM", ":WAVEFORM:FORMAT": "BYTE",
            ":WAVEFORM:POINTS": "1000", ":WAVEFORM:START": "1",
            ":WAVEFORM:STOP": "1000", ":CHANNEL1:DISPLAY": "1",
            ":CHANNEL2:DISPLAY": "0", ":CHANNEL3:DISPLAY": "0",
            ":CHANNEL4:DISPLAY": "0", ":CHANNEL1:SCALE": "0.5",
            ":CHANNEL1:COUPLING": "DC", ":CHANNEL1:IMPEDANCE": "OMEG",
        }

    def _path(self, text):
        text = text.strip()
        token, sep, val = text.partition(" ")
        token = token.upper().lstrip(":")
        # Match abbreviated SCPI tokens by comparing significant letters.
        aliases = {"ACQ":"ACQUIRE", "SRAT":"SRATE", "TIM":"TIMEBASE",
                   "MAIN":"MAIN", "SCAL":"SCALE", "CHAN":"CHANNEL",
                   "DISP":"DISPLAY", "TRIG":"TRIGGER", "STAT":"STATUS",
                   "SOUR":"SOURCE", "WAV":"WAVEFORM", "FORM":"FORMAT",
                   "POIN":"POINTS", "STAR":"START", "STOP":"STOP",
                   "PRE":"PREAMBLE", "AVER":"AVERAGES", "RUN":"RUN",
                   "MEAS":"MEASURE", "ITEM":"ITEM", "ERR":"ERROR",
                   "SYST":"SYSTEM", "DATA":"DATA", "MODE":"MODE"}
        if not token.startswith("*"):
            token = ":" + ":".join(aliases.get(t, t) for t in token.split(":"))
        return token, val.strip()

    def write(self, command):
        key, value = self._path(command)
        if key == "*CLS":
            self._errors.clear();return
        if key == ":JEFF:INVALID:COMMAND":
            self._errors.append('-113,"Undefined header"');return
        if key in (":RUN", ":STOP", ":SINGLE", ":TFORCE"):
            self.settings[":TRIGGER:STATUS"] = "RUN" if key==":RUN" else "STOP"
            return
        if key == "*RST":
            self._errors.append('-221,"Reset blocked in simulator"');return
        if key in self.settings:
            self.settings[key] = {"ON":"1", "OFF":"0"}.get(value.upper(),value.upper())
        else:
            self._errors.append('-113,"Undefined header"')

    def query(self, command):
        key, value = self._path(command)
        if key == "*IDN?": return "RIGOL TECHNOLOGIES,DS8034-R,SIM000000,00.01.01.00\n"
        if key == "*OPC?": return "1\n"
        if key == ":SYSTEM:ERROR?":
            return (self._errors.pop(0) if self._errors else '0,"No error"') + "\n"
        if key == ":WAVEFORM:PREAMBLE?":
            return "0,0,1000,1,1e-6,-0.0005,0,0.01,0,128\n"
        if key == ":MEASURE:ITEM?": return "1.25\n"
        if key.endswith("?"):
            base=key[:-1]
            if base in self.settings:return self.settings[base] + "\n"
        self._errors.append('-113,"Undefined header"')
        return "\n"

    def query_binary_values(self, command, datatype='B', is_big_endian=False,
                            container=list, header_fmt='ieee', expect_termination=True):
        key, val = self._path(command)
        if key != ":WAVEFORM:DATA?":
            self._errors.append('-113,"Undefined header"')
            raise RuntimeError("Unavailable binary command")
        return container([128 + round(40*math.sin(i*math.pi/40)) for i in range(1000)])

    def close(self):
        self.closed = True
