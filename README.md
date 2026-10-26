# Rigol DS8000-R / DS8034-R Python Driver and Test Suite

**Creator:** Jeff Michaelis  
**Version:** 1.0.0  
**Programming reference:** *RIGOL DS8000-R Series Digital Oscilloscope Programming Guide*, publication PGA27101-1110, November 2020.  
**Models:** DS8034-R (350 MHz), DS8104-R (1 GHz), DS8204-R (2 GHz). All have four analog channels; an arbitrary waveform generator channel is optional.

## Contents

1. Overview and scope
2. Installation (Python 3.8+)
3. Connecting over LAN, USB, or USB-GPIB
4. Typical Python examples
5. Driver API and error handling
6. Waveform capture and data conversion
7. Hardware test utility, modes, and risk controls
8. SCPI command catalogue: **every syntax form from the guide**
9. Troubleshooting, boundaries, and software tests

## 1. Overview and scope

This pip-installable package provides reusable, programmable access to the Rigol DS8000-R oscilloscopes. The library uses the **SCPI command set documented in the supplied guide** through PyVISA. The package does not require Matplotlib, NumPy, or any graphical environment. Python scripts can import a stable class and use a small, validated convenience API; advanced scripts can address **all commands** with the generic VISA/SCPI layer and a machine-readable catalog.

**Included features:**

- Connection/session management with `with` blocks, adjustable VISA timeout, configurable VISA backend, and thread locking.
- Instrument identification, direct SCPI read/write, text query, numeric query, and IEEE-488.2 binary block transfers.
- Four analog channel objects (`coupling`, `impedance`, `scale`, `offset`, `probe`, `display`, `invert`, `vernier`, `units`, `bandwidth_limit`).
- Acquisition sample rate/type/averaging/memory depth; horizontal scaling; edge trigger; common automatic measurements.
- Capture on-screen waveform data into scaled voltage/time arrays; CSV export to the **PC**.
- Dedicated `commands` interface for all other documented SCPI syntax, including bus decode, cursor, measurements, statistics, math, FFT, jitter, eye, optional AWG, network, storage, and advanced trigger systems.
- Complete embedded JSON command inventory, derived from the November 2020 guide, which contains **1,014 syntax forms for 563 unique command paths**. A syntax form is a set variant or a query variant, not a count of physical subsystems.
- Dedicated hardware test CLI with read-only mode, read-back sweep, optional option coverage, negative SCPI error testing, JSON/CSV results, and an offline fake instrument for PC-side validation.

**Important qualification:** The catalogue describes commands present in the programming guide, **not commands proven functional on every firmware/version**. Some are option-dependent. No physical DS8034-R is connected to the build environment. All actual-device validation remains to be performed on your oscilloscope.

## 2. Installation

Requirements: **Python 3.8 or newer**, Python pip, and a connection to a supported Rigol instrument. Real hardware use needs a VISA implementation: NI-VISA, Keysight VISA, or PyVISA's pure-Python backend (additional USB networking dependencies may vary by platform).

From the extracted package root:

```powershell
python -m pip install --upgrade pip
python -m pip install .
```

Optional pure-Python VISA backend:

```powershell
python -m pip install ".[py]"
```

Offline simulator and tests can run without a physical instrument. The Python distribution depends on `pyvisa>=1.12,<1.15`; the optional `pyvisa-py` backend is available through the `[py]` extra. Do not use `python setup.py install`; the package uses `pyproject.toml`.

If you have multiple Python installations, always use the specific interpreter's `python -m pip` to install and run. Examples:

```powershell
py -3.8 -m pip install .
py -3.8 -m pip show rigol-ds8000r-jeff
```

If `py -3.8` is unavailable, use the correct installed `python.exe` directly. A Python 3.8-compatible virtual environment is optional; it does not need to be created on a NAS or a mapped network drive.

To install a **wheel file** from the included `dist` directory (if one was built):

```powershell
python -m pip install dist/rigol_ds8000r_jeff-1.0.0-py3-none-any.whl
```

To import in another Python file:

```python
from rigol_ds8000r import RigolDS8000R, catalog
```

## 3. Connection setup

Typical resource strings are:

| Transport | PyVISA example | Notes |
|---|---|---|
| LAN, VXI-11 | `TCPIP0::192.168.1.50::INSTR` | Recommended first choice when enabled by the instrument. Replace the IP. |
| LAN, socket | `TCPIP0::192.168.1.50::5555::SOCKET` | **Only** when the oscilloscope advertises that socket service/port; do not assume 5555 is enabled. |
| USB | `USB0::0x1AB1::...::INSTR` | Obtain the precise resource from `pyvisa.ResourceManager().list_resources()`. |
| USB-GPIB adapter | `GPIB0::...::INSTR` | Requires Rigol-supported USB-GPIB converter and proper VISA support. |

Check available VISA connections:

```python
import pyvisa
rm = pyvisa.ResourceManager()             # NI-/Keysight VISA backend
print(rm.list_resources())
rm.close()

# If configured with PyVISA-py:
# rm = pyvisa.ResourceManager('@py')
```

The programming guide explicitly lists USB, LAN, and adapter-based GPIB. It does not guarantee that all instruments respond on arbitrary TCP port numbers. The resource string and any option licenses must match the specific instrument configuration.

A basic session:

```python
from rigol_ds8000r import RigolDS8000R

with RigolDS8000R("TCPIP0::192.168.1.50::INSTR", timeout=10000) as scope:
    print(scope.idn)
    print(scope.model)
    print(scope.query("*IDN?"))
```

For PyVISA-py use `backend="@py"`. `timeout` is in **milliseconds**. The class always sends `*IDN?` when connecting and does not change acquisition settings as part of connection. The same VISA session can be passed as `instrument=...` when a custom transport or simulator is needed.

## 4. Common usage examples

### Configure channels, acquisition, and triggers

```python
with RigolDS8000R("TCPIP0::192.168.1.50::INSTR") as scope:
    scope.channel(1).enable(True)
    scope.channel(1).impedance(1000000)   # 1 MΩ; avoid loading sensitive circuits
    scope.channel(1).coupling("DC")
    scope.channel(1).probe(10)           # 10x attenuation
    scope.channel(1).bandwidth_limit("20M")
    scope.channel(1).scale(0.5)          # volts/division (dependent on probe/impedance)
    scope.channel(1).offset(0.0)         # volts

    scope.acquisition_type("AVER")
    scope.acquisition_averages(16)
    scope.memory_depth("1M")
    scope.time_scale(0.001)              # seconds/division
    scope.edge_trigger(channel=1, level=0.1, slope="POS")
    scope.run()

    print("Vpp:", scope.measure("VPP", channel=1))
    print("Vrms:", scope.measure("VRMS", channel=1))
    print("Sample rate:", scope.sample_rate())
```

`scope.channel(1).bandwidth_limit("500M")` is explicitly rejected for a detected DS8034-R, since its guide lists only `OFF`, `20M`, and `250M`.

### Capture and export a waveform

```python
with RigolDS8000R("TCPIP0::192.168.1.50::INSTR") as scope:
    capture = scope.waveform(channel=1, points=1000, mode="NORM", binary=True)
    print("Sample count:", len(capture.voltages))
    print("First five volts:", capture.voltages[:5])
    print("First five timestamps:", capture.times()[:5])
    capture.csv("ch1_capture.csv")
```

To acquire memory waveforms, call `scope.stop()` first, then `scope.waveform(..., mode="RAW")`, and use a point count that fits your installed memory and current acquisition configuration. This method reads one requested window, not an automatically streamed full 500-million-point acquisition. For very large captures, request consecutive batches with manual SCPI or expand the `waveform` method to stream bounded blocks without allocating all points in memory.

### Control every SCPI feature, not just convenience methods

```python
with RigolDS8000R("TCPIP0::192.168.1.50::INSTR") as scope:
    # Raw SCPI always works when the target firmware supports the command.
    scope.write(":TRIGger:EDGE:SLOPe POSitive")
    print(scope.query(":TRIGger:EDGE:SLOPe?"))

    # Named lookups let scripts use the exact template in the manual.
    scope.commands.set(":CHANnel<n>:SCALe", 0.25, n=1)
    print(scope.commands.get(":CHANnel<n>:SCALe", n=1))

    # Parameterized query: return a waveform measurement.
    print(scope.commands.query(":MEASure:ITEM", "VPP,CHANnel1"))

    # A SCPI command requiring two or more parameters can be sent raw.
    # scope.write(":BUS1:THReshold 2.4,PAL")
    # print(scope.query(":BUS1:THReshold? PAL"))

    # Browse the full command vocabulary offline.
    for cmd in scope.commands.list(":WAVeform:*"):
        print(cmd["syntax"], cmd["page"])
```

The generic commands module accepts *one scalar* in `.set()`; commands involving optional or repeated SCPI parameters, pathnames, binary inputs, or multi-value data should be invoked with `scope.write()` or `scope.query()` using the guide's full syntax. The path-index helper accepts `n=1..4` and includes optional keywords; complicated source/output-number combinations should instead use explicit wire commands.

### Raw exception and SCPI error handling

```python
from rigol_ds8000r import RigolDS8000R, RigolError

try:
    with RigolDS8000R("TCPIP0::192.168.1.50::INSTR", check_errors=True) as scope:
        print(scope.idn)
        print("SCPI error queue:", scope.errors())
except RigolError as exc:
    print("Instrument failure:", exc)
```

The library distinguishes `ConnectionError`, `NotConnectedError`, `CommandError`, `ProtocolError`, and `ValidationError`. Unknown PyVISA transport exceptions can propagate and will be visible in the test report. Most commands use no automatic post-write error query by default (`check_errors=False`), because that can slow time-critical automation and disturb deliberate SCPI negative tests. Set `check_errors=True` when debugging command acceptance; it uses the instrument's `:SYSTem:ERRor?` query.

## 5. Public driver API

| Method/property | Purpose | Return / notes |
|---|---|---|
| `RigolDS8000R(resource, timeout=10000, backend=None, instrument=None, check_errors=False)` | Create a reusable controller | Does not connect/reset until `connect()` or `with` |
| `connect()`, `close()` | Open or close VISA session | Injected sessions remain caller-owned |
| `idn`, `model` | Identity string and model | Based on `*IDN?` |
| `write(command)` | Send an SCPI command | Rejects multiline/chained messages |
| `query(command)` | Read SCPI text response | Returns `str` |
| `query_float`, `query_int` | Parsed numeric queries | Returns float / int |
| `query_block(command, word=False)` | IEEE-488.2 definite-length binary data | Returns `bytes` (`word=False`) or list of 16-bit ints |
| `errors(max_errors=32)` | Drain SCPI error queue | Returns list of messages; empty means no errors |
| `clear_status()` | Clear IEEE-488.2 status registers and SCPI errors | Invokes `*CLS` |
| `reset()` | **Explicitly** restore instrument defaults | Invokes `*RST` |
| `operation_complete()` | Wait/query operation complete | Invokes `*OPC?` |
| `channel(1..4)` | Analog channel object | See detailed table below |
| `run()`, `stop()`, `single()`, `force_trigger()` | Acquisition control | `:RUN`, `:STOP`, `:SINGle`, `:TFORce` |
| `autoscale()`, `clear_display()` | Oscilloscope auto setup, screen clear | Both change display/acquisition |
| `acquisition_type(mode=None)` | `NORM`, `AVER`, `PEAK`, `HRES` | Query or set |
| `acquisition_averages(count=None)` | Powers-of-two from 2 to 65536 | Query or set |
| `memory_depth(value=None)` | `AUTO`, `1K` through `500M` | Subject to channel-count memory limitations |
| `sample_rate()` | Acquisition rate | Samples per second |
| `time_scale(value=None)` | Main timebase setting | Seconds/division |
| `time_offset(value=None)` | Horizontal offset | Seconds |
| `edge_trigger(channel=1, level=None, slope='POS')` | Edge trigger configuration | Configures mode, source, slope and optional level |
| `trigger_state()` | Trigger acquisition state | Instrument string |
| `measure(measurement='VPP', channel=1, second_channel=None)` | On-board automatic waveform result | Float, using `:MEASure:ITEM?` |
| `waveform(channel=1, points=1000, mode='NORM', binary=True, start=1)` | Acquire and scale waveform | `Waveform` object |
| `commands.list(pattern='*')` | Query the manual catalog | Records include SCPI syntax, guide page and description |
| `commands.describe(name)` | Find a documented path | One or more syntax records |
| `commands.set(name,value,n=...)` | Write a scalar by guide template | No implied query/error check unless configured |
| `commands.get(name,*args,n=...)` | Query by guide template | Text result |
| `commands.query(name,parameters='',n=...)` | Parameterized query using complete SCPI comma string | Text result |
| `commands.action(name,n=...)` | Send a command without an argument | Return ignored |

**Channel objects** expose `enable`, `is_enabled`, `coupling`, `impedance`, `scale`, `offset`, `probe`, `bandwidth_limit`, `invert`, `vernier`, `units`, `raw_set`, and `raw_get`. Setters with a `None` default double as getters, except `enable()` and `is_enabled()` which are separate by design.

**Measurement tokens** accepted by `measure()`:

```
VMAX VMIN VPP VTOP VBASE VAMP VAVG VRMS OVERSHOOT PRESHOOT
MAREA MPAREA PERIOD FREQUENCY RTIME FTIME PWIDTH NWIDTH PDUTY NDUTY
TVMAX TVMIN PSLEWRATE NSLEWRATE VUPPER VMID VLOWER VARIANCE PVRMS
PPULSES NPULSES PEDGES NEDGES RRDELAY RFDELAY FRDELAY FFDELAY
RRPHASE RFPHASE FRPHASE FFPHASE
```

These are instrument-defined measurement tokens. A result may require a valid trigger and captured signal; `NaN`/over-range semantics are firmware dependent. Values are not computed by Python.

## 6. Waveform data format and conversion

The oscilloscope's `:WAVeform:PREamble?` returns ten comma-separated parameters:

`format, type, points, count, XINCrement, XORigin, XREFerence, YINCrement, YORigin, YREFerence`.

The driver converts bytes using:

```
voltage_V = (sample_code - YORigin - YREFerence) * YINCrement
time_s    = (sample_index - XREFerence) * XINCrement + XORigin
```

`Waveform` holds `channel`, `preamble`, `voltages` and supports `.times()` / `.csv(file)`. The guide specifies WORD format as 16-bit with only the low 8 bits meaningful. The driver's normal capture uses BYTE, and the raw binary read API has an optional WORD mode. ASCII waveforms return voltage values directly and bypass the byte formula. The capture routine tries to preserve previous waveform readout settings on exit.

Instrument-specific caveats: RAW mode requires STOP, memory depth decreases as more analog channels are enabled, some captures return fewer valid points, and binary transfers can be large. The oscilloscope's input limits and probe derating must always be checked before connecting a circuit to 50 Ω or 1 MΩ inputs.

## 7. Test and verification utility

Install once, then run `rigol-ds8000r-test`, or execute with the module name:

```powershell
python -m rigol_ds8000r.verification --help
```

**Zero-hardware first check**:

```powershell
rigol-ds8000r-test --simulate --mode smoke --error-tests --report offline_smoke.json
```

**Exact full inventory without communicating with any instrument**:

```powershell
rigol-ds8000r-test --mode inventory --report all_commands.csv
```

**Query sweep** (visits every catalogue syntax; sends eligible parameterless queries; certain SCPI status queries inherently clear their status registers and are skipped without `--allow-risky`):

```powershell
rigol-ds8000r-test --resource "TCPIP0::192.168.1.50::INSTR" --mode query --report rigol_query_sweep.json
```

**Settings readback sweep** (explicit opt-in, re-applies current values of simple set/query pairs and tries to restore them):

```powershell
rigol-ds8000r-test --resource "TCPIP0::192.168.1.50::INSTR" --mode exercise --yes --report rigol_readbacks.csv
```

**Broader active SCPI coverage**, still skipping high-impact commands by default:

```powershell
rigol-ds8000r-test --resource "TCPIP0::192.168.1.50::INSTR" --mode full --yes --all-indices --include-optional --include-data --error-tests --report rigol_full_results.json
```

Only if the instrument is isolated and intentionally being reconfigured, adding `--allow-risky --yes` permits additional stateful readback/query attempts. It does **not** blindly run factory reset, network readdressing, output enabling, license operations, or other irreversible/multi-parameter commands; such commands remain `SKIP` where they cannot be safely characterized. Avoid `--allow-risky` during live system testing.

### All test options

| Option | Description |
|---|---|
| `--resource STRING` | VISA resource; required unless simulator/inventory |
| `--backend @py` | PyVISA-py backend |
| `--simulate` | Use included deterministic simulator, no real scope |
| `--mode inventory` | One report entry per manual syntax; no instrument IO |
| `--mode smoke` | ID, acquisition, trigger, sample rate and reversible CH1 check |
| `--mode query` | All eligible no-argument SCPI read commands |
| `--mode exercise` | Query coverage and safe re-application/readback of existing values |
| `--mode full` | Add a small number of core stateful actions such as RUN and STOP |
| `--include-optional` | Allow commands belonging to instrument options; unsupported options can report FAIL |
| `--include-data` | Allow binary/large-data transfers (can be slow) |
| `--allow-risky` | Permit additional stateful queries and reversible setting attempts |
| `--all-indices` | Expand `<n>` families across values 1,2,3,4 |
| `--error-tests` | Send invalid `:JEFF:INVALID:COMMAND`, require nonzero SCPI error, then clear status |
| `--max-queries N` | Limit count of actual sends/queries, with remaining entries SKIP |
| `--timeout 10000` | VISA timeout (ms) |
| `--report name.json` | JSON or CSV result log |
| `--yes` | Explicit confirmation for mode `exercise`/`full` or `--allow-risky` |

**Test result states:** `PASS` = valid response with no SCPI error or readback matched, `FAIL` = timeout, unsupported/invalid command, unexpected response, or SCPI error, `SKIP` = test was catalogued but not sent due to constraints/required parameters, option requirements or safety limits. The runner **records every catalogued syntax form**, even when it does not transmit that command. A skip must never be interpreted as a pass, and the simulator is not a hardware certification.

**Interpreting test results:** All query forms are not equally testable without setup. Example: `:MEASure:ITEM? <item>[,<src>...]` needs a specific measurement selector; bus decode needs option installation and channels configured; file save needs valid paths; network settings could drop the connection; AWG/output controls can produce voltages. The test runner therefore inventories such commands and marks unsupported/unsafe cases. For meaningful acceptance, run a controlled test fixture with known waveforms and append purpose-built test cases for each licensed subsystem.

### Tested offline

The `tests/test_driver.py` suite validates command inventory, argument validation, template expansion, waveform conversion, CSV creation, simulation of SCPI error handling, and both inventory/smoke CLI modes. Install `pytest` and run:

```powershell
python -m pip install ".[test]"
python -m pytest -q
```

## 8. Complete programming-guide SCPI syntax catalogue

The following is the embedded catalogue supplied in `rigol_ds8000r/command_catalog.json`, displayed in groups. It is comprehensive with respect to syntax entries extracted from the supplied November 2020 guide (1,014 SCPI forms, 563 distinct command paths). It includes the complete command spelling, placeholders, optional brackets, and page references for details such as units, accepted enumerations, dynamic ranges, or required operating mode. `Set/action` and `Query` columns refer to the **exact guide syntax**; a dash means that variant is not documented for that command path.

SCPI notation: `<x>` is a required argument/index to substitute, `[...]` is optional, `|` in manual parameter tables means alternatives. Capital letters in SCPI keywords indicate the permitted abbreviation; the actual commands are case-insensitive. Physical values must be given as numbers in the command's stated native units, not with a V/s/Hz suffix. See guide **Chapter 1 (pp. 1-1–1-2)** for the syntax rules.

Optional interfaces may not be installed on your particular DS8034-R. Output voltage and frequency limits, measurement modes, acquisition depth, memory access, threshold boundaries, and network/file path formats should be taken from the specific manual page and confirmed with `:SYSTem:ERRor?` as required.

### IEEE 488.2 common commands

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `*CLS` | `*CLS` | — | Clears all the event registers, and also clears the error queue. | 2-79 |
| `*ESE` | `*ESE <maskargument>` | `*ESE?` | Sets or queries the enable register bit of the standard event register set. | 2-79 |
| `*ESR` | — | `*ESR?` | Queries and clears the event register of the standard event status register. | 2-79 |
| `*IDN` | — | `*IDN?` | Queries the ID string of the instrument. | 2-80 |
| `*OPC` | `*OPC` | `*OPC?` | The *OPC command sets bit 0 (Operation Complete, OPC) in the standard event status register to 1 after the current operation is finished. The OPC? command queries whether the current operation is… | 2-80 |
| `*RCL` | `*RCL` | — | Recalls the instrument state in the specified location. | 2-80 |
| `*RST` | `*RST` | — | Restores the instrument to its factory default settings. | 2-80 |
| `*SAV` | `*SAV <value>` | — | Saves the current instrument state to the selected register. | 2-80 |
| `*SRE` | `*SRE <maskargument>` | `*SRE?` | Sets or queries the enable register of the status byte register set. | 2-81 |
| `*STB` | — | `*STB?` | Queries the event register for the status byte register. After executing the command, the value in the status byte register is cleared. | 2-81 |
| `*TST` | — | `*TST?` | Performs a self-test and queries the self-test result. | 2-81 |
| `*WAI` | `*WAI` | — | Waits for all the pending operations to complete before executing any additional commands. | 2-81 |

### SOURce / arbitrary waveform generator

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `[:SOURce[<n>]]:APPLy` | — | `[:SOURce[<n>]]:APPLy?` | Queries the current output configuration of the specified arbitrary waveform generator channel. | 2-161 |
| `[:SOURce[<n>]]:APPLy:NOISe` | `[:SOURce[<n>]]:APPLy:NOISe [<amp>[,<offset>]]` | — | Configures the specified arbitrary waveform generator channel to output the signal with the specified waveforms and parameters. | 2-161 |
| `[:SOURce[<n>]]:APPLy:PULSe` | `[:SOURce[<n>]]:APPLy:PULSe [<freq>[,<amp>[,<offset>[,<phase>]]]]` | — | Configures the specified arbitrary waveform generator channel to output the signal with the specified waveforms and parameters. | 2-161 |
| `[:SOURce[<n>]]:APPLy:RAMP` | `[:SOURce[<n>]]:APPLy:RAMP [<freq>[,<amp>[,<offset>[,<phase>]]]]` | — | Configures the specified arbitrary waveform generator channel to output the signal with the specified waveforms and parameters. | 2-161 |
| `[:SOURce[<n>]]:APPLy:SINusoid` | `[:SOURce[<n>]]:APPLy:SINusoid [<freq>[,<amp>[,<offset>[,<phase>]]]]` | — | Configures the specified arbitrary waveform generator channel to output the signal with the specified waveforms and parameters. | 2-161 |
| `[:SOURce[<n>]]:APPLy:SQUare` | `[:SOURce[<n>]]:APPLy:SQUare [<freq>[,<amp>[,<offset>[,<phase>]]]]` | — | Configures the specified arbitrary waveform generator channel to output the signal with the specified waveforms and parameters. | 2-161 |
| `[:SOURce[<n>]]:APPLy:USER` | `[:SOURce[<n>]]:APPLy:USER [<freq>[,<amp>[,<offset>[,<phase>]]]]` | — | Configures the specified arbitrary waveform generator channel to output the signal with the specified waveforms and parameters. | 2-161 |
| `[:SOURce[<n>]]:BURSt:CYCLes` | `[:SOURce[<n>]]:BURSt:CYCLes <count>` | `[:SOURce[<n>]]:BURSt:CYCLes?` | Sets or queries the number of burst cycles of the specified signal source channel. | 2-160 |
| `[:SOURce[<n>]]:BURSt:DELay` | `[:SOURce[<n>]]:BURSt:DELay <time>` | `[:SOURce[<n>]]:BURSt:DELay?` | Sets or queries the burst delay time of the specified signal source channel. | 2-160 |
| `[:SOURce[<n>]]:BURSt:TYPE` | `[:SOURce[<n>]]:BURSt:TYPE <type>` | `[:SOURce[<n>]]:BURSt:TYPE?` | Sets or queries the burst type of the specified signal source channel. | 2-160 |
| `[:SOURce[<n>]]:FREQuency[:FIXed]` | `[:SOURce[<n>]]:FREQuency[:FIXed] <frequency>` | `[:SOURce[<n>]]:FREQuency[:FIXed]?` | If modulation is not enabled for the specified arbitrary waveform generator channel, this command is used to set or query the output frequency of the specified arbitrary waveform generator… | 2-152 |
| `[:SOURce[<n>]]:FUNCtion:RAMP:SYMMetry` | `[:SOURce[<n>]]:FUNCtion:RAMP:SYMMetry <val>` | `[:SOURce[<n>]]:FUNCtion:RAMP:SYMMetry?` | Sets or queries the symmetry of the Ramp waveforms output from the specified arbitrary waveform generator channel. | 2-153 |
| `[:SOURce[<n>]]:FUNCtion[:SHAPe]` | `[:SOURce[<n>]]:FUNCtion[:SHAPe] <wave>` | `[:SOURce[<n>]]:FUNCtion[:SHAPe]?` | If modulation is not enabled for the specified arbitrary waveform generator channel, this command is used to select or query the output signal waveform. If modulation is enabled for the specified… | 2-153 |
| `[:SOURce[<n>]]:MOD:AM:INTernal:FREQuency` | `[:SOURce[<n>]]:MOD:AM:INTernal:FREQuency <frequency>` | `[:SOURce[<n>]]:MOD:AM:INTernal:FREQuency?` | Sets or queries the modulating waveform frequency of AM or FM of the specified arbitrary waveform generator channel. The default unit is Hz. | 2-157 |
| `[:SOURce[<n>]]:MOD:AM:INTernal:FUNCtion` | `[:SOURce[<n>]]:MOD:AM:INTernal:FUNCtion <wave>` | `[:SOURce[<n>]]:MOD:AM:INTernal:FUNCtion?` | Sets or queries the modulating waveform of AM or FM of the specified arbitrary waveform generator channel. | 2-157 |
| `[:SOURce[<n>]]:MOD:AM[:DEPTh]` | `[:SOURce[<n>]]:MOD:AM[:DEPTh] <depth>` | `[:SOURce[<n>]]:MOD:AM[:DEPTh]?` | Sets or queries the depth of AM of the specified arbitrary waveform generator channel. The modulation depth refers to the strength of the AM and is expressed in percentage. | 2-156 |
| `[:SOURce[<n>]]:MOD:FM:INTernal:FREQuency` | `[:SOURce[<n>]]:MOD:FM:INTernal:FREQuency <frequency>` | `[:SOURce[<n>]]:MOD:FM:INTernal:FREQuency?` | Sets or queries the modulating waveform frequency of AM or FM of the specified arbitrary waveform generator channel. The default unit is Hz. | 2-157 |
| `[:SOURce[<n>]]:MOD:FM:INTernal:FUNCtion` | `[:SOURce[<n>]]:MOD:FM:INTernal:FUNCtion <wave>` | `[:SOURce[<n>]]:MOD:FM:INTernal:FUNCtion?` | Sets or queries the modulating waveform of AM or FM of the specified arbitrary waveform generator channel. | 2-157 |
| `[:SOURce[<n>]]:MOD:FM[:DEVIation]` | `[:SOURce[<n>]]:MOD:FM[:DEVIation] <dev>` | `[:SOURce[<n>]]:MOD:FM[:DEVIation]?` | Sets or queries the frequency offset of FM of the specified arbitrary waveform generator channel. By default, the unit is Hz. | 2-158 |
| `[:SOURce[<n>]]:MOD:TYPE` | `[:SOURce[<n>]]:MOD:TYPE <type>` | `[:SOURce[<n>]]:MOD:TYPE?` | Sets or queries the modulation type of the specified arbitrary waveform generator channel. | 2-156 |
| `[:SOURce[<n>]]:OUTPut[<n>]:IMPedance` | `[:SOURce[<n>]]:OUTPut[<n>]:IMPedance <impedance>` | `[:SOURce[<n>]]:OUTPut[<n>]:IMPedance?` | Sets or queries the impedance of the specified arbitrary waveform generator channel. | 2-163 |
| `[:SOURce[<n>]]:OUTPut[<n>][:STATe]` | `[:SOURce[<n>]]:OUTPut[<n>][:STATe] <bool>` | `[:SOURce[<n>]]:OUTPut[<n>][:STATe]?` | Enables or disables the output of the specified arbitrary waveform generator channel; or queries the output status of the specified arbitrary waveform generator channel. | 2-162 |
| `[:SOURce[<n>]]:PHASe[:ADJust]` | `[:SOURce[<n>]]:PHASe[:ADJust] <phase>` | `[:SOURce[<n>]]:PHASe[:ADJust]?` | Sets or queries the start phase of the signal of the specified arbitrary waveform generator channel. By default, the unit is °. | 2-152 |
| `[:SOURce[<n>]]:PULSe:DCYCle` | `[:SOURce[<n>]]:PULSe:DCYCle <percent>` | `[:SOURce[<n>]]:PULSe:DCYCle?` | Sets or queries the duty cycle of the pulse output from the specified arbitrary waveform generator channel, i.g. the ratio of high level to a pulse period. | 2-155 |
| `[:SOURce[<n>]]:SWEep:BTIMe` | `[:SOURce[<n>]]:SWEep:BTIMe <time>` | `[:SOURce[<n>]]:SWEep:BTIMe?` | Sets or queries the return time of the specified signal source channel. | 2-159 |
| `[:SOURce[<n>]]:SWEep:STIMe` | `[:SOURce[<n>]]:SWEep:STIMe <time>` | `[:SOURce[<n>]]:SWEep:STIMe?` | Sets or queries the sweep time of the specified signal source channel. | 2-159 |
| `[:SOURce[<n>]]:SWEep:TYPE` | `[:SOURce[<n>]]:SWEep:TYPE <type>` | `[:SOURce[<n>]]:SWEep:TYPE?` | Sets or queries the sweep type of the specified signal source channel. | 2-158 |
| `[:SOURce[<n>]]:TYPE` | `[:SOURce[<n>]]:TYPE <type>` | `[:SOURce[<n>]]:TYPE?` | Sets or queries the signal source type of the specified arbitrary waveform generator channel. | 2-155 |
| `[:SOURce[<n>]]:VOLTage[:LEVel]` | `[:SOURce[<n>]]:VOLTage[:LEVel] [:IMMediate]:OFFSet <offset>` / `[:SOURce[<n>]]:VOLTage[:LEVel] [:IMMediate]:OFFSet?` | — | Sets or queries the DC offset of the signal output from the specified arbitrary waveform generator channel. By default, the unit is VDC. | 2-154 |
| `[:SOURce[<n>]]:VOLTage[:LEVel][:IMMediate][:AMPLitude]` | `[:SOURce[<n>]]:VOLTage[:LEVel][:IMMediate][:AMPLitude] <amplitude>` | `[:SOURce[<n>]]:VOLTage[:LEVel][:IMMediate][:AMPLitude]?` | Sets or queries the amplitude of the signal output from the specified arbitrary waveform generator channel. By default, the unit is Vpp. | 2-154 |

### TRACe / DAC output

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `[:TRACe[<n>]]:DATA:DAC16` | `[:TRACe[<n>]]:DATA:DAC16 volatile,<flag>,<binary_block_data>` | — | Downloads binary data block to the volatile memory of the specified signal source. | 2-177 |

### acquire

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:ACQuire:AALias` | `:ACQuire:AALias <bool>` | `:ACQuire:AALias?` | Enables or disables the anti-aliasing function of the oscilloscope; or queries the on/off status of the anti-aliasing function. | 2-6 |
| `:ACQuire:AVERages` | `:ACQuire:AVERages <count>` | `:ACQuire:AVERages?` | Sets or queries the number of averages in the average acquisition mode. | 2-4 |
| `:ACQuire:MDEPth` | `:ACQuire:MDEPth <mdep>` | `:ACQuire:MDEPth?` | Sets or queries the memory depth of the oscilloscope (i.g. the number of waveform points that can be stored through the sampling in a single trigger). The default unit is pts. | 2-4 |
| `:ACQuire:SRATe` | — | `:ACQuire:SRATe?` | Queries the current sample rate. The default unit is Sa/s. | 2-5 |
| `:ACQuire:TYPE` | `:ACQuire:TYPE <type>` | `:ACQuire:TYPE?` | Sets or queries the acquisition mode of the oscilloscope. | 2-5 |

### autoscale

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:AUToscale` | `:AUToscale` | — | Enables the waveform auto setting function. The oscilloscope will automatically adjust the vertical scale, horizontal time base, and trigger mode according to the input signal to realize optimal… | 2-2 |

### bus

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:BUS<n>:CAN:BAUD` | `:BUS<n>:CAN:BAUD <baud>` | `:BUS<n>:CAN:BAUD?` | Sets or queries the signal rate of CAN decoding. The default unit is bps. | 2-30 |
| `:BUS<n>:CAN:SOURce` | `:BUS<n>:CAN:SOURce <source>` | `:BUS<n>:CAN:SOURce?` | Sets or queries the source channel of CAN decoding. | 2-29 |
| `:BUS<n>:CAN:SPOint` | `:BUS<n>:CAN:SPOint <spoint>` | `:BUS<n>:CAN:SPOint?` | Sets or queries the sample point position of CAN decoding (expressed in %). | 2-30 |
| `:BUS<n>:CAN:STYPe` | `:BUS<n>:CAN:STYPe <stype>` | `:BUS<n>:CAN:STYPe?` | Sets or queries the signal type of CAN decoding. | 2-29 |
| `:BUS<n>:DATA` | — | `:BUS<n>:DATA?` | Reads the data in the decoding event table. | 2-10 |
| `:BUS<n>:DISPlay` | `:BUS<n>:DISPlay <bool>` | `:BUS<n>:DISPlay?` | Enables or disables the specified decoding bus; or queries the on/off display status of the specified decoding bus. | 2-8 |
| `:BUS<n>:EEXPort` | `:BUS<n>:EEXPort <path>` | — | Exports the decoding information in the specified decoding bus event table in CSV form. | 2-10 |
| `:BUS<n>:EVENt` | `:BUS<n>:EVENt <bool>` | `:BUS<n>:EVENt?` | Enables or disables the event table of the specified decoding bus; or queries the on/off status of the specified decoding bus event table. | 2-8 |
| `:BUS<n>:EVENt:FORMat` | `:BUS<n>:EVENt:FORMat <format>` | `:BUS<n>:EVENt:FORMat?` | Sets or queries the display format of the specified decoding bus event table. | 2-9 |
| `:BUS<n>:EVENt:VIEW` | `:BUS<n>:EVENt:VIEW <packet>` | `:BUS<n>:EVENt:VIEW?` | Sets or queries the data page of the specified decoding bus event table. | 2-9 |
| `:BUS<n>:FLEXray:BAUD` | `:BUS<n>:FLEXray:BAUD <baud>` | `:BUS<n>:FLEXray:BAUD?` | Sets or queries the signal rate of FlexRay decoding. The default unit is bps. | 2-31 |
| `:BUS<n>:FLEXray:SOURce` | `:BUS<n>:FLEXray:SOURce <source>` | `:BUS<n>:FLEXray:SOURce?` | Sets or queries the source channel of FlexRay decoding. | 2-31 |
| `:BUS<n>:FLEXray:SPOint` | `:BUS<n>:FLEXray:SPOint <spoint>` | `:BUS<n>:FLEXray:SPOint?` | Sets or queries the sample point position of FlexRay decoding (expressed in %). | 2-32 |
| `:BUS<n>:FLEXray:STYPe` | `:BUS<n>:FLEXray:STYPe <stype>` | `:BUS<n>:FLEXray:STYPe?` | Sets or queries the signal type of FlexRay decoding. | 2-32 |
| `:BUS<n>:FORMat` | `:BUS<n>:FORMat <fmt>` | `:BUS<n>:FORMat?` | Sets or queries the display format of decoding data of the specified decoding bus. | 2-8 |
| `:BUS<n>:IIC:ADDRess` | `:BUS<n>:IIC:ADDRess <addr>` | `:BUS<n>:IIC:ADDRess?` | Sets or queries the address mode of I2C decoding. | 2-21 |
| `:BUS<n>:IIC:SCLK:SOURce` | `:BUS<n>:IIC:SCLK:SOURce <source>` | `:BUS<n>:IIC:SCLK:SOURce?` | Sets or queries the clock source of I2C decoding. | 2-21 |
| `:BUS<n>:IIC:SDA:SOURce` | `:BUS<n>:IIC:SDA:SOURce <source>` | `:BUS<n>:IIC:SDA:SOURce?` | Sets or queries the data channel source of I2C decoding. | 2-21 |
| `:BUS<n>:IIS:ALIGnment` | `:BUS<n>:IIS:ALIGnment <align>` | `:BUS<n>:IIS:ALIGnment?` | Sets or queries the alignment mode of the I2S decoding. | 2-36 |
| `:BUS<n>:IIS:CLOCk:SLOPe` | `:BUS<n>:IIS:CLOCk:SLOPe <slope>` | `:BUS<n>:IIS:CLOCk:SLOPe?` | Sets or queries the clock edge type of I2S decoding. | 2-36 |
| `:BUS<n>:IIS:RWIDth` | `:BUS<n>:IIS:RWIDth <val>` | `:BUS<n>:IIS:RWIDth?` | Sets or queries the word size of the I2S decoding. | 2-37 |
| `:BUS<n>:IIS:SOURce:CLOCk` | `:BUS<n>:IIS:SOURce:CLOCk <source>` | `:BUS<n>:IIS:SOURce:CLOCk?` | Sets or queries the clock source of the I2S decoding. | 2-35 |
| `:BUS<n>:IIS:SOURce:DATA` | — | `:BUS<n>:IIS:SOURce:DATA?` | Sets or queries the data source of the I2S decoding. | 2-35 |
| `:BUS<n>:IIS:SOURce:DATA<source>` | `:BUS<n>:IIS:SOURce:DATA<source>` | — | Sets or queries the data source of the I2S decoding. | 2-35 |
| `:BUS<n>:IIS:SOURce:WSELect` | `:BUS<n>:IIS:SOURce:WSELect <source>` | `:BUS<n>:IIS:SOURce:WSELect?` | Sets or queries the audio channel of the I2S trigger. | 2-36 |
| `:BUS<n>:LABel` | `:BUS<n>:LABel <bool>` | `:BUS<n>:LABel?` | Enables or disables the label of the specified decoding bus; or queries the on/off status of the label of the specified decoding bus. | 2-9 |
| `:BUS<n>:LIN:BAUD` | `:BUS<n>:LIN:BAUD <baud>` | `:BUS<n>:LIN:BAUD?` | Sets or queries the baud rate of LIN decoding. The default unit is bps。 | 2-33 |
| `:BUS<n>:LIN:POLarity` | `:BUS<n>:LIN:POLarity <bool>` | `:BUS<n>:LIN:POLarity?` | Sets or queries the parity bit of LIN decoding. | 2-33 |
| `:BUS<n>:LIN:SOURce` | `:BUS<n>:LIN:SOURce <source>` | `:BUS<n>:LIN:SOURce?` | Sets or queries the source of LIN bus. | 2-34 |
| `:BUS<n>:LIN:STANdard` | `:BUS<n>:LIN:STANdard <value>` | `:BUS<n>:LIN:STANdard?` | Sets or queries the version of LIN bus. | 2-34 |
| `:BUS<n>:M1553:SOURce` | `:BUS<n>:M1553:SOURce <source>` | `:BUS<n>:M1553:SOURce?` | Sets or queries the source of the M1553 decoding. | 2-38 |
| `:BUS<n>:MODE` | `:BUS<n>:MODE <mode>` | `:BUS<n>:MODE?` | Sets or queries the decoding type of the specified decoding bus. | 2-7 |
| `:BUS<n>:PARallel:BITX` | `:BUS<n>:PARallel:BITX <bit>` | `:BUS<n>:PARallel:BITX?` | Sets or queries the data bit that the parallel bus requires to set for the channel source. | 2-13 |
| `:BUS<n>:PARallel:BUS` | `:BUS<n>:PARallel:BUS <source>` | `:BUS<n>:PARallel:BUS?` | Sets or queries the current source of the Parallel decoding bus. | 2-12 |
| `:BUS<n>:PARallel:CLK` | `:BUS<n>:PARallel:CLK <source>` | `:BUS<n>:PARallel:CLK?` | Sets or queries the clock source of the Parallel decoding. | 2-12 |
| `:BUS<n>:PARallel:NREJect` | `:BUS<n>:PARallel:NREJect <bool>` | `:BUS<n>:PARallel:NREJect?` | Enables or disables the noise rejection function of Parallel decoding; or queries the status of the noise rejection function of Parallel decoding. | 2-15 |
| `:BUS<n>:PARallel:NRTime` | `:BUS<n>:PARallel:NRTime <time>` | `:BUS<n>:PARallel:NRTime?` | Sets or queries the noise rejection time of Parallel decoding. The default unit is s. | 2-15 |
| `:BUS<n>:PARallel:POLarity` | `:BUS<n>:PARallel:POLarity <pol>` | `:BUS<n>:PARallel:POLarity?` | Sets or queries the data polarity of Parallel decoding. | 2-14 |
| `:BUS<n>:PARallel:SLOPe` | `:BUS<n>:PARallel:SLOPe <slope>` | `:BUS<n>:PARallel:SLOPe?` | Sets or queries the edge type of the clock channel when being sampled by Parallel decoding on the data channel. | 2-13 |
| `:BUS<n>:PARallel:SOURce` | `:BUS<n>:PARallel:SOURce <src>` | `:BUS<n>:PARallel:SOURce?` | Sets or queries the channel source of the currently selected data bit. | 2-14 |
| `:BUS<n>:PARallel:WIDTh` | `:BUS<n>:PARallel:WIDTh <wid>` | `:BUS<n>:PARallel:WIDTh?` | Sets or queries the data width of the parallel bus, i.g. the number of bits per frame. | 2-13 |
| `:BUS<n>:POSition` | `:BUS<n>:POSition <pos>` | `:BUS<n>:POSition?` | Sets or queries the vertical position of the bus on the screen. | 2-11 |
| `:BUS<n>:RS232:BAUD` | `:BUS<n>:RS232:BAUD <baud>` | `:BUS<n>:RS232:BAUD?` | Sets or queries the baud rate of data transmission in RS232 decoding. The default unit is bps. | 2-17 |
| `:BUS<n>:RS232:DBITs` | `:BUS<n>:RS232:DBITs <bits>` | `:BUS<n>:RS232:DBITs?` | Sets or queries the data width of RS232 decoding. | 2-18 |
| `:BUS<n>:RS232:ENDian` | `:BUS<n>:RS232:ENDian <endian>` | `:BUS<n>:RS232:ENDian?` | Sets or queries the endian of data transmission in RS232 decoding. | 2-17 |
| `:BUS<n>:RS232:PACKet` | `:BUS<n>:RS232:PACKet <bool>` | `:BUS<n>:RS232:PACKet?` | Enables or disables the packet end during data transmission; or queries the status of packet end during data transmission. | 2-19 |
| `:BUS<n>:RS232:PARity` | `:BUS<n>:RS232:PARity <parity>` | `:BUS<n>:RS232:PARity?` | Sets or queries the odd-even check mode of data transmission in RS232 decoding. | 2-18 |
| `:BUS<n>:RS232:PEND` | `:BUS<n>:RS232:PEND <package end>` | `:BUS<n>:RS232:PEND?` | Sets or queries the packet separator type during data transmission. | 2-19 |
| `:BUS<n>:RS232:POLarity` | `:BUS<n>:RS232:POLarity <pol>` | `:BUS<n>:RS232:POLarity?` | Sets or queries the polarity of RS232 decoding. | 2-17 |
| `:BUS<n>:RS232:RX` | `:BUS<n>:RS232:RX <source>` | `:BUS<n>:RS232:RX?` | Sets or queries the RX channel source of RS232 decoding. | 2-16 |
| `:BUS<n>:RS232:SBITs` | `:BUS<n>:RS232:SBITs <stop bits>` | `:BUS<n>:RS232:SBITs?` | Sets or queries the stop bits of each frame of data in RS232 decoding. | 2-18 |
| `:BUS<n>:RS232:TX` | `:BUS<n>:RS232:TX <source>` | `:BUS<n>:RS232:TX?` | Sets or queries the TX channel source of RS232 decoding. | 2-16 |
| `:BUS<n>:SPI:DBITs` | `:BUS<n>:SPI:DBITs <width>` | `:BUS<n>:SPI:DBITs?` | Sets or queries the data width of SPI decoding. | 2-25 |
| `:BUS<n>:SPI:ENDian` | `:BUS<n>:SPI:ENDian <endian>` | `:BUS<n>:SPI:ENDian?` | Sets or queries the endian of data transmission in SPI decoding. | 2-26 |
| `:BUS<n>:SPI:MISO:POLarity` | `:BUS<n>:SPI:MISO:POLarity <polarity>` | `:BUS<n>:SPI:MISO:POLarity?` | Sets or queries the polarity of MISO data line of SPI decoding. | 2-24 |
| `:BUS<n>:SPI:MISO:SOURce` | `:BUS<n>:SPI:MISO:SOURce <source>` | `:BUS<n>:SPI:MISO:SOURce?` | Sets or queries the MISO data source of SPI decoding. | 2-24 |
| `:BUS<n>:SPI:MODE` | `:BUS<n>:SPI:MODE <mode>` | `:BUS<n>:SPI:MODE?` | Sets or queries the decode mode of SPI decoding. | 2-26 |
| `:BUS<n>:SPI:MOSI:POLarity` | `:BUS<n>:SPI:MOSI:POLarity <polarity>` | `:BUS<n>:SPI:MOSI:POLarity?` | Sets or queries the polarity of MOSI data line of SPI decoding. | 2-25 |
| `:BUS<n>:SPI:MOSI:SOURce` | `:BUS<n>:SPI:MOSI:SOURce <source>` | `:BUS<n>:SPI:MOSI:SOURce?` | Sets or queries the MOSI data source of SPI decoding. | 2-25 |
| `:BUS<n>:SPI:SCLK:SLOPe` | `:BUS<n>:SPI:SCLK:SLOPe <slope>` | `:BUS<n>:SPI:SCLK:SLOPe?` | Sets or queries the clock edge type of SPI decoding. | 2-24 |
| `:BUS<n>:SPI:SCLK:SOURce` | `:BUS<n>:SPI:SCLK:SOURce <source>` | `:BUS<n>:SPI:SCLK:SOURce?` | Sets or queries the clock source of SPI decoding. | 2-23 |
| `:BUS<n>:SPI:SS:POLarity` | `:BUS<n>:SPI:SS:POLarity <polarity>` | `:BUS<n>:SPI:SS:POLarity?` | Sets or queries the polarity of the CS line of SPI decoding. | 2-27 |
| `:BUS<n>:SPI:SS:SOURce` | `:BUS<n>:SPI:SS:SOURce <source>` | `:BUS<n>:SPI:SS:SOURce?` | Sets or queries the source channel of the CS line of SPI decoding. | 2-27 |
| `:BUS<n>:SPI:TIMeout:TIME` | `:BUS<n>:SPI:TIMeout:TIME <time>` | `:BUS<n>:SPI:TIMeout:TIME?` | Sets or queries the timeout value of SPI decoding. The default unit is s. | 2-27 |
| `:BUS<n>:THReshold` | `:BUS<n>:THReshold <value>,<type>` | `:BUS<n>:THReshold? <type>` | Sets or queries the threshold of the specified decoding source. | 2-11 |

### channel

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:CHANnel<n>:BWLimit` | `:CHANnel<n>:BWLimit <type>` | `:CHANnel<n>:BWLimit?` | Sets or queries the bandwidth limit of the specified channel. | 2-39 |
| `:CHANnel<n>:COUPling` | `:CHANnel<n>:COUPling <coupling>` | `:CHANnel<n>:COUPling?` | Sets or queries the coupling mode of the specified channel. | 2-40 |
| `:CHANnel<n>:CSTart` | `:CHANnel<n>:CSTart` | — | Starts calibration for the active probe currently connected to the specified analog channel. | 2-43 |
| `:CHANnel<n>:DISPlay` | `:CHANnel<n>:DISPlay <bool>` | `:CHANnel<n>:DISPlay?` | Turns on or off the specified channel; or queries the on/off status of the specified channel. | 2-40 |
| `:CHANnel<n>:IMPedance` | `:CHANnel<n>:IMPedance <impedance>` | `:CHANnel<n>:IMPedance?` | Sets or queries the input impedance of the specified analog channel. The default unit is Ω. | 2-42 |
| `:CHANnel<n>:INVert` | `:CHANnel<n>:INVert <bool>` | `:CHANnel<n>:INVert?` | Turns on or off the waveform invert for the specified channel; or queries the on/off status of the waveform invert for the specified channel. | 2-40 |
| `:CHANnel<n>:OFFSet` | `:CHANnel<n>:OFFSet <offset>` | `:CHANnel<n>:OFFSet?` | Sets or queries the vertical offset of the specified channel. The default unit is V. | 2-41 |
| `:CHANnel<n>:POSition` | `:CHANnel<n>:POSition <offset>` | `:CHANnel<n>:POSition?` | Sets or queries the offset calibration voltage for calibrating the zero point of the specified analog channel. | 2-45 |
| `:CHANnel<n>:PROBe` | `:CHANnel<n>:PROBe <atten>` | `:CHANnel<n>:PROBe?` | Sets or queries the probe ratio of the specified channel. | 2-43 |
| `:CHANnel<n>:PROBe:BIAS` | `:CHANnel<n>:PROBe:BIAS <bias>` | `:CHANnel<n>:PROBe:BIAS?` | Sets or queries the probe bias voltage of the specified channel. | 2-44 |
| `:CHANnel<n>:PROBe:DELay` | `:CHANnel<n>:PROBe:DELay <delay>` | `:CHANnel<n>:PROBe:DELay?` | Sets or queries the probe delay time of the specified channel. | 2-43 |
| `:CHANnel<n>:SCALe` | `:CHANnel<n>:SCALe <scale>` | `:CHANnel<n>:SCALe?` | Sets or queries the vertical scale of the specified channel. The default unit is V. | 2-42 |
| `:CHANnel<n>:TCALibrate` | `:CHANnel<n>:TCALibrate <val>` | `:CHANnel<n>:TCALibrate?` | Sets or queries the delay calibration time (used to calibrate the zero offset of the corresponding channel) of the specified channel. The default unit is s. | 2-41 |
| `:CHANnel<n>:UNITs` | `:CHANnel<n>:UNITs <units>` | `:CHANnel<n>:UNITs?` | Sets or queries the amplitude display unit of the specified analog channel. | 2-44 |
| `:CHANnel<n>:VERNier` | `:CHANnel<n>:VERNier <bool>` | `:CHANnel<n>:VERNier?` | Enables or disables the fine adjustment of the vertical scale of the specified analog channel; or queries the on/off status of the fine adjustment function of the vertical scale of the specified… | 2-44 |

### clear

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:CLEar` | `:CLEar` | — | Clears all the waveforms on the screen. This command functions the same as clicking the Clear key at the right section of the operation interface in the Web Control page. | 2-2 |

### clock

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:CLOCk:EXTChan` | `:CLOCk:EXTChan <ch>` | `:CLOCk:EXTChan?` | Sets or queries the source of the external clock recovery method. | 2-47 |
| `:CLOCk:METHod` | `:CLOCk:METHod <type>` | `:CLOCk:METHod?` | Sets or queries the clock recovery method. | 2-46 |
| `:CLOCk:PLL:BW` | `:CLOCk:PLL:BW <val>` | `:CLOCk:PLL:BW?` | Sets or queries the PLL loop bandwidth. | 2-47 |
| `:CLOCk:PLL:ORDer` | `:CLOCk:PLL:ORDer <ord>` | `:CLOCk:PLL:ORDer?` | Sets or queries the PLL order. | 2-47 |
| `:CLOCk:RATE` | `:CLOCk:RATE <val>` | `:CLOCk:RATE?` | Sets or queries the data rate of the Manual method. | 2-46 |
| `:CLOCk:TYPE` | `:CLOCk:TYPE <type>` | `:CLOCk:TYPE?` | Sets or queries the data rate type of the constant clock recovery method. | 2-46 |

### counter

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:COUNter:ENABle` | `:COUNter:ENABle <bool>` | `:COUNter:ENABle?` | Enables or disables the frequency counter; or queries the on/off status of the frequency counter. | 2-48 |
| `:COUNter:MODE` | `:COUNter:MODE <mode>` | `:COUNter:MODE?` | Sets or queries the mode of the frequency counter. | 2-49 |
| `:COUNter:NDIGits` | `:COUNter:NDIGits <val>` | `:COUNter:NDIGits?` | Sets or queries the resolution of the frequency counter. | 2-49 |
| `:COUNter:SOURce` | `:COUNter:SOURce <source>` | `:COUNter:SOURce?` | Sets or queries the source of the frequency counter. | 2-48 |
| `:COUNter:TOTalize:CLEar` | `:COUNter:TOTalize:CLEar` | — | Clears the total count. Description Available when "Totalize" is selected under "Measure". | 2-50 |
| `:COUNter:TOTalize:ENABle` | `:COUNter:TOTalize:ENABle <bool>` | `:COUNter:TOTalize:ENABle?` | Enables or disables the statistical function of the frequency counter; or queries the on/off status of the statistical function of the frequency counter. | 2-49 |

### cursor

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:CURSor:MANual:AXValue` | — | `:CURSor:MANual:AXValue?` | Queries the X value at Cursor A in the manual mode of cursor measurement. The unit is determined by the currently selected horizontal unit. | 2-55 |
| `:CURSor:MANual:AYValue` | — | `:CURSor:MANual:AYValue?` | Queries the Y value at Cursor A in the manual mode of cursor measurement. The unit is determined by the currently selected vertical unit. | 2-56 |
| `:CURSor:MANual:BXValue` | — | `:CURSor:MANual:BXValue?` | Queries the X value at Cursor B in the manual mode of cursor measurement. The unit is determined by the currently selected horizontal unit. | 2-56 |
| `:CURSor:MANual:BYValue` | — | `:CURSor:MANual:BYValue?` | Queries the Y value at Cursor B in the manual mode of cursor measurement. The unit is determined by the currently selected vertical unit. | 2-56 |
| `:CURSor:MANual:CAX` | `:CURSor:MANual:CAX <ax>` | `:CURSor:MANual:CAX?` | Sets or queries the horizontal position of Cursor A in the manual mode of cursor measurement. | 2-54 |
| `:CURSor:MANual:CAY` | `:CURSor:MANual:CAY <ay>` | `:CURSor:MANual:CAY?` | Sets or queries the vertical position of Cursor A in the manual mode of cursor measurement. | 2-55 |
| `:CURSor:MANual:CBX` | `:CURSor:MANual:CBX <bx>` | `:CURSor:MANual:CBX?` | Sets or queries the horizontal position of Cursor B in the manual mode of cursor measurement. | 2-54 |
| `:CURSor:MANual:CBY` | `:CURSor:MANual:CBY <by>` | `:CURSor:MANual:CBY?` | Sets or queries the vertical position of Cursor B in the manual mode of cursor measurement. | 2-55 |
| `:CURSor:MANual:IXDelta` | — | `:CURSor:MANual:IXDelta?` | Queries the reciprocal (1/△X) of the absolute difference between the X value at Cursor A and the X value at Cursor B in the manual mode of cursor measurement. The unit is determined by the… | 2-56 |
| `:CURSor:MANual:SOURce` | `:CURSor:MANual:SOURce <source>` | `:CURSor:MANual:SOURce?` | Sets or queries the channel source of the manual mode of cursor measurement. | 2-53 |
| `:CURSor:MANual:TUNit` | `:CURSor:MANual:TUNit <unit>` | `:CURSor:MANual:TUNit?` | Sets or queries the horizontal unit in the manual mode of cursor measurement. | 2-53 |
| `:CURSor:MANual:TYPE` | `:CURSor:MANual:TYPE <type>` | `:CURSor:MANual:TYPE?` | Sets or queries the cursor type in the manual mode of cursor measurement. | 2-52 |
| `:CURSor:MANual:VUNit` | `:CURSor:MANual:VUNit <unit>` | `:CURSor:MANual:VUNit?` | Sets or queries the vertical unit in the manual mode of cursor measurement. | 2-53 |
| `:CURSor:MANual:XDELta` | — | `:CURSor:MANual:XDELta?` | Queries the difference (△X) between the X value at Cursor A and the X value at Cursor B in the manual mode of cursor measurement. The unit is determined by the currently selected horizontal unit. | 2-56 |
| `:CURSor:MANual:YDELta` | — | `:CURSor:MANual:YDELta?` | Queries the difference (△Y) between the Y value at Cursor A and the Y value at Cursor B in the manual mode of cursor measurement. The unit is determined by the currently selected vertical unit. | 2-57 |
| `:CURSor:MEASure:INDicator` | `:CURSor:MEASure:INDicator <bool>` | `:CURSor:MEASure:INDicator?` | Sets or queries the on/off status of the measurement auto cursor. | 2-66 |
| `:CURSor:MODE` | `:CURSor:MODE <mode>` | `:CURSor:MODE?` | Sets or queries the mode of the cursor measurement. | 2-51 |
| `:CURSor:TRACk:AXValue` | — | `:CURSor:TRACk:AXValue?` | Queries the X value at Cursor A in the track mode of cursor measurement. The unit is determined by the amplitude unit selected for the currently corresponding channel. | 2-61 |
| `:CURSor:TRACk:AYValue` | — | `:CURSor:TRACk:AYValue?` | Queries the Y value at Cursor A in the track mode of cursor measurement. The unit is the same as that selected for the current channel. | 2-61 |
| `:CURSor:TRACk:BXValue` | — | `:CURSor:TRACk:BXValue?` | Queries the X value at Cursor B in the track mode of cursor measurement. The unit is determined by the amplitude unit selected for the currently corresponding channel. | 2-61 |
| `:CURSor:TRACk:BYValue` | — | `:CURSor:TRACk:BYValue?` | Queries the Y value at Cursor B in the track mode of cursor measurement. The unit is the same as that selected for the current channel. | 2-61 |
| `:CURSor:TRACk:CAX` | `:CURSor:TRACk:CAX <ax>` | `:CURSor:TRACk:CAX?` | Sets or queries the horizontal position of Cursor A in the track mode of cursor measurement. | 2-59 |
| `:CURSor:TRACk:CAY` | — | `:CURSor:TRACk:CAY?` | Queries the vertical position of Cursor A in the track mode of cursor measurement. | 2-60 |
| `:CURSor:TRACk:CBX` | `:CURSor:TRACk:CBX <bx>` | `:CURSor:TRACk:CBX?` | Sets or queries the horizontal position of Cursor B in the track mode of cursor measurement. | 2-60 |
| `:CURSor:TRACk:CBY` | — | `:CURSor:TRACk:CBY?` | Queries the vertical position of Cursor B in the track mode of cursor measurement. | 2-60 |
| `:CURSor:TRACk:IXDelta` | — | `:CURSor:TRACk:IXDelta?` | Queries the reciprocal (1/△X) of the absolute difference between the X value at Cursor A and the X value at Cursor B in the track mode of cursor measurement. The default unit is Hz. | 2-62 |
| `:CURSor:TRACk:SOURce1` | `:CURSor:TRACk:SOURce1 <source>` | `:CURSor:TRACk:SOURce1?` | Sets or queries the channel source of Cursor A in the track mode of cursor measurement. | 2-58 |
| `:CURSor:TRACk:SOURce2` | `:CURSor:TRACk:SOURce2 <source>` | `:CURSor:TRACk:SOURce2?` | Sets or queries the channel source of Cursor B in the track mode of cursor measurement. | 2-59 |
| `:CURSor:TRACk:XDELta` | — | `:CURSor:TRACk:XDELta?` | Queries the difference (△X) between the X value at Cursor A and the X value at Cursor B in the track mode of cursor measurement. The default unit is s. | 2-61 |
| `:CURSor:TRACk:YDELta` | — | `:CURSor:TRACk:YDELta?` | Queries the difference (△Y) between the Y value at Cursor A and the Y value at Cursor B in the track mode of cursor measurement. The unit is the same as that selected for the current channel. | 2-61 |
| `:CURSor:XY:AX` | `:CURSor:XY:AX <x>` | `:CURSor:XY:AX?` | Sets or queries the horizontal position of Cursor A in the XY cursor measurement mode. | 2-63 |
| `:CURSor:XY:AXValue` | — | `:CURSor:XY:AXValue?` | Queries the X value at Cursor A in the XY cursor measurement mode. The unit is determined by the amplitude unit selected for the currently corresponding channel. | 2-65 |
| `:CURSor:XY:AY` | `:CURSor:XY:AY <y>` | `:CURSor:XY:AY?` | Sets or queries the vertical position of Cursor A in the XY cursor measurement mode. | 2-64 |
| `:CURSor:XY:AYValue` | — | `:CURSor:XY:AYValue?` | Queries the X value at Cursor A in the XY cursor measurement mode. The unit is determined by the amplitude unit selected for the currently corresponding channel. | 2-65 |
| `:CURSor:XY:BX` | `:CURSor:XY:BX <x>` | `:CURSor:XY:BX?` | Sets or queries the horizontal position of Cursor B in the XY cursor measurement mode. | 2-64 |
| `:CURSor:XY:BXValue` | — | `:CURSor:XY:BXValue?` | Queries the X value at Cursor B in the XY cursor measurement mode. The unit is determined by the amplitude unit selected for the currently corresponding channel. | 2-65 |
| `:CURSor:XY:BY` | `:CURSor:XY:BY <y>` | `:CURSor:XY:BY?` | Sets or queries the vertical position of Cursor B in the XY cursor measurement mode. | 2-65 |
| `:CURSor:XY:BYValue` | — | `:CURSor:XY:BYValue?` | Queries the Y value at Cursor B in the XY cursor measurement mode. The unit is determined by the amplitude unit selected for the currently corresponding channel. | 2-65 |

### display

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:DISPlay:CLEar` | `:DISPlay:CLEar` | — | Clears all the waveforms on the screen. | 2-67 |
| `:DISPlay:COLor` | `:DISPlay:COLor <val>` | `:DISPlay:COLor?` | Enables or disables the color grade display; or queries the on/off status of the color grade display. | 2-69 |
| `:DISPlay:DATA` | — | `:DISPlay:DATA?` | Queries the bitmap data stream of the currently displayed image. | 2-69 |
| `:DISPlay:GBRightness` | `:DISPlay:GBRightness <brightness>` | `:DISPlay:GBRightness?` | Sets or queries the brightness of the screen grid, expressed in percentage. | 2-69 |
| `:DISPlay:GRADing:TIME` | `:DISPlay:GRADing:TIME <time>` | `:DISPlay:GRADing:TIME?` | Sets or queries the persistence time. The default unit is s. | 2-68 |
| `:DISPlay:GRID` | `:DISPlay:GRID <grid>` | `:DISPlay:GRID?` | Sets or queries the display type of the screen grid. | 2-68 |
| `:DISPlay:RULers` | `:DISPlay:RULers <bool>` | `:DISPlay:RULers?` | Enables or disables the ruler display; or queries the on/off status of the ruler. | 2-69 |
| `:DISPlay:TYPE` | `:DISPlay:TYPE <type>` | `:DISPlay:TYPE?` | Sets or queries the display type of the waveforms on the screen. | 2-67 |
| `:DISPlay:WBRightness` | `:DISPlay:WBRightness <time>` | `:DISPlay:WBRightness?` | Sets or queries the brightness of the waveforms on the screen, expressed in percentage. | 2-68 |

### dvm

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:DVM:CURRent` | — | `:DVM:CURRent?` | Queries the current voltage value under test. | 2-71 |
| `:DVM:ENABle` | `:DVM:ENABle <bool>` | `:DVM:ENABle?` | Enables or disables the digital voltmeter; or queries the on/off status of the digital voltmeter. | 2-71 |
| `:DVM:MODE` | `:DVM:MODE <mode>` | `:DVM:MODE?` | Sets or queries the mode of the digital voltmeter. | 2-72 |
| `:DVM:SOURce` | `:DVM:SOURce <source>` | `:DVM:SOURce?` | Sets or queries the source of the digital voltmeter. | 2-71 |

### eye

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:EYE:ENABle` | `:EYE:ENABle <bool>` | `:EYE:ENABle?` | Enables or disables the eye analysis function; or queries the on/off status of the eye analysis function. | 2-73 |
| `:EYE:MEASure:ENABle` | `:EYE:MEASure:ENABle <bool>` | `:EYE:MEASure:ENABle?` | Enables or disables the eye measurement; or queries the on/off status of the eye measurement. | 2-74 |
| `:EYE:MEASure:ITEM` | — | `:EYE:MEASure:ITEM? <item>` | Queries the measurements of an eye diagram. | 2-74 |
| `:EYE:SOURce` | `:EYE:SOURce <source>` | `:EYE:SOURce?` | Sets or queries the source of the eye diagram. | 2-73 |

### histogram

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:HISTogram:BLIMit` | `:HISTogram:BLIMit <y>` | `:HISTogram:BLIMit?` | Sets or queries the histogram's bottom boundary limit. | 2-77 |
| `:HISTogram:DISPlay` | `:HISTogram:DISPlay <bool>` | `:HISTogram:DISPlay?` | Enables or disables the histogram function; or queries the status of the histogram. | 2-75 |
| `:HISTogram:LLIMit` | `:HISTogram:LLIMit <x>` | `:HISTogram:LLIMit?` | Sets or queries the histogram's left boundary limit. | 2-77 |
| `:HISTogram:RESet` | `:HISTogram:RESet` | — | Resets the statistics. | 2-76 |
| `:HISTogram:RLIMit` | `:HISTogram:RLIMit <x>` | `:HISTogram:RLIMit?` | Sets or queries the histogram's right boundary limit. | 2-77 |
| `:HISTogram:SIZE` | `:HISTogram:SIZE <size>` | `:HISTogram:SIZE?` | Sets or queries the height of the histogram. | 2-76 |
| `:HISTogram:SOURce` | `:HISTogram:SOURce <source>` | `:HISTogram:SOURce?` | Sets or queries the source of the histogram. | 2-76 |
| `:HISTogram:STATic` | `:HISTogram:STATic <bool>` | `:HISTogram:STATic?` | Enables or disables the statistical function; or queries the status of the statistical function. | 2-76 |
| `:HISTogram:TLIMit` | `:HISTogram:TLIMit <y>` | `:HISTogram:TLIMit?` | Sets or queries the histogram's top boundary limit. | 2-78 |
| `:HISTogram:TYPE` | `:HISTogram:TYPE <type>` | `:HISTogram:TYPE?` | Sets or queries the type of the histogram. | 2-75 |

### jitter

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:JITTer:ENABle` | `:JITTer:ENABle <bool>` | `:JITTer:ENABle?` | Enables or disables the jitter analysis function; or queries the on/off status of the jitter analysis function. | 2-82 |
| `:JITTer:HISTogram:APPLy` | `:JITTer:HISTogram:APPLy <bool>` | `:JITTer:HISTogram:APPLy?` | Enables or disables the jitter histogram; or queries the on/off status of the jitter histogram. | 2-83 |
| `:JITTer:MEASure:ENABle` | `:JITTer:MEASure:ENABle <bool>` | `:JITTer:MEASure:ENABle?` | Enables or disables the jitter measurement; or queries the on/off status of the jitter measurement. | 2-84 |
| `:JITTer:MEASure:ITEM` | `:JITTer:MEASure:ITEM <item>[,<source>]` | `:JITTer:MEASure:ITEM? <item>[,<source>]` | Sets or queries the jitter measurement item of the specified channel. | 2-84 |
| `:JITTer:MEASure:STATistic:ITEM` | — | `:JITTer:MEASure:STATistic:ITEM? <type>,<item>[,<source>]` | Sets or queries the statistics value of the jitter measurement item for the specified channel. | 2-84 |
| `:JITTer:MEASure:TYPE` | — | `:JITTer:MEASure:TYPE?` | Sets or queries the measurement item of the jitter. | 2-83 |
| `:JITTer:MEASure:TYPE<item>` | `:JITTer:MEASure:TYPE<item>` | — | Sets or queries the measurement item of the jitter. | 2-83 |
| `:JITTer:SLOPe` | `:JITTer:SLOPe <slope>` | `:JITTer:SLOPe?` | Sets or queries the edge of the jitter measurement item. | 2-85 |
| `:JITTer:SOURce` | `:JITTer:SOURce <source>` | `:JITTer:SOURce?` | Sets or queries the source of the jitter. | 2-82 |
| `:JITTer:TRENd:APPLy` | `:JITTer:TRENd:APPLy <bool>` | `:JITTer:TRENd:APPLy?` | Enables or disables the jitter trend graph; or queries the on/off status of the jitter trend graph. | 2-83 |

### lan

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:LAN:APPLy` | `:LAN:APPLy` | — | Applies the network configuration. | 2-91 |
| `:LAN:AUToip` | `:LAN:AUToip <bool>` | `:LAN:AUToip?` | Turns on or off the Auto IP configuration mode; or queries the on/off status of the current Auto IP configuration mode. | 2-87 |
| `:LAN:DESCription` | `:LAN:DESCription <name>` | `:LAN:DESCription?` | Sets or queries the description. | 2-90 |
| `:LAN:DHCP` | `:LAN:DHCP <bool>` | `:LAN:DHCP?` | Turns on or off the DHCP configuration mode; or queries the on/off status of the current DHCP configuration mode. | 2-86 |
| `:LAN:DNS` | `:LAN:DNS <string>` | `:LAN:DNS?` | Sets or queries the DNS address. | 2-87 |
| `:LAN:DSErver` | — | `:LAN:DSErver?` | Queries the address of the DHCP server. | 2-88 |
| `:LAN:GATeway` | `:LAN:GATeway <string>` | `:LAN:GATeway?` | Sets or queries the default gateway. | 2-87 |
| `:LAN:HOST:NAME` | `:LAN:HOST:NAME <name>` | `:LAN:HOST:NAME?` | Sets or queries the host name. | 2-90 |
| `:LAN:IPADdress` | `:LAN:IPADdress <string>` | `:LAN:IPADdress?` | Sets or queries the IP address of the instrument. | 2-89 |
| `:LAN:MAC` | — | `:LAN:MAC?` | Queries the MAC address of the instrument. | 2-88 |
| `:LAN:MANual` | `:LAN:MANual <bool>` | `:LAN:MANual?` | Turns on or off the static IP configuration mode; or queries the on/off status of the static IP configuration mode. | 2-88 |
| `:LAN:MDNS` | `:LAN:MDNS <bool>` | `:LAN:MDNS?` | Enables or disables MDNS; or queries the MDNS status. | 2-90 |
| `:LAN:SMASk` | `:LAN:SMASk <string>` | `:LAN:SMASk?` | Sets or queries the subnet mask. | 2-89 |
| `:LAN:STATus` | — | `:LAN:STATus?` | Queries the current network configuration status. | 2-89 |
| `:LAN:VISA` | — | `:LAN:VISA?` | Queries the VISA address of the instrument. | 2-90 |

### load

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:LOAD:SETup` | `:LOAD:SETup <path>` | — | Loads the setup file of the oscilloscope from the specified path. | 2-134 |

### mask

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:MASK:CREate` | `:MASK:CREate` | — | Creates the pass/fail test mask with the currently set horizontal and vertical adjustment | 2-94 |
| `:MASK:ENABle` | `:MASK:ENABle <bool>` | `:MASK:ENABle?` | Enables or disables the pass/fail test function; or queries the on/off status of the pass/fail test function. | 2-92 |
| `:MASK:FAILed` | — | `:MASK:FAILed?` | Queries the number of failed frames in the pass/fail test. | 2-94 |
| `:MASK:MDISplay` | `:MASK:MDISplay <bool>` | `:MASK:MDISplay?` | Enables or disables the statistical function; or queries the on/off status of the statistical function when the pass/fail test is enabled. | 2-93 |
| `:MASK:OPERate` | `:MASK:OPERate <oper>` | `:MASK:OPERate?` | Runs or stops the pass/fail test; or queries the operating status of the pass/fail test. | 2-93 |
| `:MASK:PASSed` | — | `:MASK:PASSed?` | Queries the number of passed frames in the pass/fail test. | 2-94 |
| `:MASK:RESet` | `:MASK:RESet` | — | Resets the number of frames that passed and failed the pass/fail test, as well as the total number of frames. | 2-95 |
| `:MASK:SOURce` | `:MASK:SOURce <source>` | `:MASK:SOURce?` | Sets or queries the measurement source of the pass/fail test. | 2-92 |
| `:MASK:TOTal` | — | `:MASK:TOTal?` | Queries the total number of frames in the pass/fail test. | 2-95 |
| `:MASK:X` | `:MASK:X <x>` | `:MASK:X?` | Sets or queries the horizontal adjustment parameter of the pass/fail test mask. The default unit is div. | 2-93 |
| `:MASK:Y` | `:MASK:Y <y>` | `:MASK:Y?` | Sets or queries the vertical adjustment parameter of the pass/fail test mask. The default unit is div. | 2-94 |

### math

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:MATH<n>:DISPlay` | `:MATH<n>:DISPlay <bool>` | `:MATH<n>:DISPlay?` | Enables or disables the math operation function; or queries the status of the math operation function. | 2-97 |
| `:MATH<n>:DISTance` | `:MATH<n>:DISTance <dist>` | `:MATH<n>:DISTance?` | Sets or queries the smoothing window width of differential operation. | 2-108 |
| `:MATH<n>:FFT:FREQuency:END` | `:MATH<n>:FFT:FREQuency:END <value>` | `:MATH<n>:FFT:FREQuency:END?` | Sets or queries the stop frequency of FFT operation results. | 2-104 |
| `:MATH<n>:FFT:FREQuency:STARt` | `:MATH<n>:FFT:FREQuency:STARt <value>` | `:MATH<n>:FFT:FREQuency:STARt?` | Sets or queries the start frequency of FFT operation results. | 2-103 |
| `:MATH<n>:FFT:HCENter` | `:MATH<n>:FFT:HCENter <cent>` | `:MATH<n>:FFT:HCENter?` | Sets or queries the center frequency of FFT operation results, i.g. the frequency relative to the horizontal center of the screen. The default unit is Hz. | 2-103 |
| `:MATH<n>:FFT:HSCale` | `:MATH<n>:FFT:HSCale <hsc>` | `:MATH<n>:FFT:HSCale?` | Sets or queries the frequency range of FFT operation results. The default unit is Hz. | 2-102 |
| `:MATH<n>:FFT:OFFSet` | `:MATH<n>:FFT:OFFSet <offset>` | `:MATH<n>:FFT:OFFSet?` | Sets or queries the vertical offset of FFT operation results. | 2-102 |
| `:MATH<n>:FFT:SCALe` | `:MATH<n>:FFT:SCALe <scale>` | `:MATH<n>:FFT:SCALe?` | Sets or queries the vertical scale of FFT operation results. | 2-102 |
| `:MATH<n>:FFT:SEARch:ENABle` | `:MATH<n>:FFT:SEARch:ENABle <bool>` | `:MATH<n>:FFT:SEARch:ENABle?` | Enables or disables the FFT peak search; or queries the on/off status of the FFT peak search function. | 2-104 |
| `:MATH<n>:FFT:SEARch:EXCursion` | `:MATH<n>:FFT:SEARch:EXCursion <excur>` | `:MATH<n>:FFT:SEARch:EXCursion?` | Sets or queries the excursion of the FFT peak search. | 2-105 |
| `:MATH<n>:FFT:SEARch:NUM` | `:MATH<n>:FFT:SEARch:NUM <num>` | `:MATH<n>:FFT:SEARch:NUM?` | Sets or queries the maximum number of the FFT peak search. | 2-104 |
| `:MATH<n>:FFT:SEARch:ORDer` | `:MATH<n>:FFT:SEARch:ORDer <order>` | `:MATH<n>:FFT:SEARch:ORDer?` | Sets or queries the sequence of the FFT peak search results. | 2-105 |
| `:MATH<n>:FFT:SEARch:THReshold` | `:MATH<n>:FFT:SEARch:THReshold <thres>` | `:MATH<n>:FFT:SEARch:THReshold?` | Sets or queries the threshold of the FFT peak search. | 2-105 |
| `:MATH<n>:FFT:SOURce` | `:MATH<n>:FFT:SOURce <src>` | `:MATH<n>:FFT:SOURce?` | Sets or queries the channel source of FFT operation. | 2-101 |
| `:MATH<n>:FFT:UNIT` | `:MATH<n>:FFT:UNIT <unit>` | `:MATH<n>:FFT:UNIT?` | Sets or queries the vertical unit of FFT operation results. | 2-101 |
| `:MATH<n>:FFT:WINDow` | `:MATH<n>:FFT:WINDow <wnd>` | `:MATH<n>:FFT:WINDow?` | Sets or queries the window function of FFT operation. | 2-101 |
| `:MATH<n>:FILTer:TYPE` | `:MATH<n>:FILTer:TYPE <type>` | `:MATH<n>:FILTer:TYPE?` | Sets or queries the filter type. | 2-106 |
| `:MATH<n>:FILTer:W1` | `:MATH<n>:FILTer:W1 <freq1>` | `:MATH<n>:FILTer:W1?` | Sets or queries the cut-off frequency of Low Pass Filter/High Pass Filter; or the cut-off frequency 1 of Band Pass Filter/Band Stop Filter. The default unit is Hz. | 2-106 |
| `:MATH<n>:FILTer:W2` | `:MATH<n>:FILTer:W2 <freq2>` | `:MATH<n>:FILTer:W2?` | Sets or queries the cut-off frequency 2 of Band Pass Filter/Band Stop Filter. The default unit is Hz. | 2-107 |
| `:MATH<n>:INVert` | `:MATH<n>:INVert <bool>` | `:MATH<n>:INVert?` | Enables or disables the inverted display of the operation results; or queries the status of the inverted display of the operation results. | 2-100 |
| `:MATH<n>:LSOUrce1` | `:MATH<n>:LSOUrce1 <src>` | `:MATH<n>:LSOUrce1?` | Sets or queries Source A of the logic operation. | 2-99 |
| `:MATH<n>:LSOUrce2` | `:MATH<n>:LSOUrce2 <src>` | `:MATH<n>:LSOUrce2?` | Sets or queries Source B of the logic operation. | 2-99 |
| `:MATH<n>:OFFSet` | `:MATH<n>:OFFSet <offset>` | `:MATH<n>:OFFSet?` | Sets or queries the vertical offset of the operation results. The unit is related to the currently selected operator and the unit selected by the source. | 2-100 |
| `:MATH<n>:OPERator` | `:MATH<n>:OPERator <opt>` | `:MATH<n>:OPERator?` | Sets or queries the operator of math operation. | 2-97 |
| `:MATH<n>:RESet` | `:MATH<n>:RESet` | — | After you send this command, the instrument will adjust the vertical scale of the operation results to an optimal value based on the currently selected operator and the horizontal time base of the… | 2-100 |
| `:MATH<n>:SCALe` | `:MATH<n>:SCALe <scale>` | `:MATH<n>:SCALe?` | Sets or queries the vertical scale of the operation results. The unit is related to the currently selected operator and the unit selected by the source. | 2-99 |
| `:MATH<n>:SENSitivity` | `:MATH<n>:SENSitivity <sens>` | `:MATH<n>:SENSitivity?` | Sets or queries the sensitivity of the logic operation. The default unit is div. | 2-107 |
| `:MATH<n>:SOURce1` | `:MATH<n>:SOURce1 <src>` | `:MATH<n>:SOURce1?` | Sets or queries the source or Source A of arithmetic operation, function operation, and filter operation. | 2-98 |
| `:MATH<n>:SOURce2` | `:MATH<n>:SOURce2 <src>` | `:MATH<n>:SOURce2?` | Sets or queries Source B of arithmetic operation. | 2-98 |
| `:MATH<n>:THReshold1` | `:MATH<n>:THReshold1 <thre>` | `:MATH<n>:THReshold1?` | Sets or queries threshold level of Analog Channel 1 in the logic operation. The default unit is V. | 2-108 |
| `:MATH<n>:THReshold2` | `:MATH<n>:THReshold2 <thre>` | `:MATH<n>:THReshold2?` | Sets or queries threshold level of Analog Channel 2 in the logic operation. The default unit is V. | 2-108 |
| `:MATH<n>:THReshold3` | `:MATH<n>:THReshold3 <thre>` | `:MATH<n>:THReshold3?` | Sets or queries threshold level of Analog Channel 3 in the logic operation. The default unit is V. | 2-109 |
| `:MATH<n>:THReshold4` | `:MATH<n>:THReshold4 <thre>` | `:MATH<n>:THReshold4?` | Sets or queries threshold level of Analog Channel 4 in the logic operation. The default unit is V. | 2-109 |

### measure

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:MEASure:AMSource` | `:MEASure:AMSource <chan>` | `:MEASure:AMSource?` | Sets the source and displays all measurement values of the set source; or queries the channel source(s) of the all measurement function. | 2-113 |
| `:MEASure:AREA` | `:MEASure:AREA <area>` | `:MEASure:AREA?` | Sets or queries the type of the measurement range. | 2-118 |
| `:MEASure:CATegory` | `:MEASure:CATegory <val>` | `:MEASure:CATegory?` | Refer to the programming guide for behavior and prerequisites. | 2-119 |
| `:MEASure:CLEar` | `:MEASure:CLEar <item>` | — | Clears any one or all of the 10 measurement items that have been turned on. | 2-112 |
| `:MEASure:CREGion:CAX` | `:MEASure:CREGion:CAX <cax>` | `:MEASure:CREGion:CAX?` | Sets or queries the position of Cursor A when the measurement range is the "cursor region". | 2-119 |
| `:MEASure:CREGion:CBX` | `:MEASure:CREGion:CBX <cbx>` | `:MEASure:CREGion:CBX?` | Sets or queries the position of Cursor B when the measurement range is the "cursor region". | 2-119 |
| `:MEASure:ITEM` | `:MEASure:ITEM <item>[,<src>[,<src>]]` | `:MEASure:ITEM? <item>[,<src>[,<src>]]` | Measures any waveform parameter of the specified source, or queries the statistical results of any waveform parameter of the specified source. | 2-117 |
| `:MEASure:MODE` | `:MEASure:MODE <mode>` | `:MEASure:MODE?` | Sets or queries the measurement mode. | 2-112 |
| `:MEASure:SETup:DSA` | `:MEASure:SETup:DSA <source>` | `:MEASure:SETup:DSA?` | Sets or queries Source A in the phase or delay measurement. | 2-115 |
| `:MEASure:SETup:DSB` | `:MEASure:SETup:DSB <source>` | `:MEASure:SETup:DSB?` | Sets or queries Source B in the phase or delay measurement. | 2-116 |
| `:MEASure:SETup:MAX` | `:MEASure:SETup:MAX <value>` | `:MEASure:SETup:MAX?` | Sets or queries the threshold level upper limit of the analog channel in auto measurement. | 2-113 |
| `:MEASure:SETup:MID` | `:MEASure:SETup:MID <value>` | `:MEASure:SETup:MID?` | Sets or queries the threshold level middle value of the analog channel in auto measurement. | 2-114 |
| `:MEASure:SETup:MIN` | `:MEASure:SETup:MIN <value>` | `:MEASure:SETup:MIN?` | Sets or queries the threshold level lower limit of the analog channel in auto measurement. | 2-114 |
| `:MEASure:SETup:PSA` | `:MEASure:SETup:PSA <source>` | `:MEASure:SETup:PSA?` | Sets or queries Source A in the phase or delay measurement. | 2-114 |
| `:MEASure:SETup:PSB` | `:MEASure:SETup:PSB <source>` | `:MEASure:SETup:PSB?` | Sets or queries Source B in the phase or delay measurement. | 2-115 |
| `:MEASure:SOURce` | `:MEASure:SOURce <sour>` | `:MEASure:SOURce?` | Sets or queries the channel source of the current measurement parameter. | 2-111 |
| `:MEASure:STATistic:DISPlay` | `:MEASure:STATistic:DISPlay <bool>` | `:MEASure:STATistic:DISPlay?` | Enables or disables the statistical function; or queries the status of the statistical function. | 2-116 |
| `:MEASure:STATistic:ITEM` | `:MEASure:STATistic:ITEM <item>[,<src>[,<src>]]` | `:MEASure:STATistic:ITEM? <type>,<item>[,<src>[,<src>]]` | Enables the statistical function of any waveform parameter of the specified source, or queries the statistical results of any waveform parameter of the specified source. | 2-117 |
| `:MEASure:STATistic:RESet` | `:MEASure:STATistic:RESet` | — | Clears the history statistics data and makes statistics again. | 2-116 |
| `:MEASure:THReshold:DEFault` | `:MEASure:THReshold:DEFault` | — | Sets the threshold level of the analog channel in auto measurement to a default value. | 2-112 |
| `:MEASure:THReshold:SOURce` | `:MEASure:THReshold:SOURce <source>` | — | Sets the threshold source. | 2-112 |

### power

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:POWer:CURRentsource` | `:POWer:CURRentsource <source>` | `:POWer:CURRentsource?` | Sets or queries the current source of power quality. | 2-121 |
| `:POWer:QUALity:FREQreference` | `:POWer:QUALity:FREQreference <source>` | `:POWer:QUALity:FREQreference?` | Sets or queries the frequency reference source of power quality. | 2-122 |
| `:POWer:REFLevel:METHod` | `:POWer:REFLevel:METHod <method>` | `:POWer:REFLevel:METHod?` | Sets or queries the reference level type of power quality. | 2-122 |
| `:POWer:REFLevel:PERCent:HIGH` | `:POWer:REFLevel:PERCent:HIGH <value>` | `:POWer:REFLevel:PERCent:HIGH?` | Sets or queries the reference level percentage upper limit of power quality. | 2-123 |
| `:POWer:REFLevel:PERCent:LOW` | `:POWer:REFLevel:PERCent:LOW <value>` | `:POWer:REFLevel:PERCent:LOW?` | Sets or queries the reference level percentage lower limit of power quality. | 2-123 |
| `:POWer:REFLevel:PERCent:MID` | `:POWer:REFLevel:PERCent:MID <value>` | `:POWer:REFLevel:PERCent:MID?` | Sets or queries the reference level percentage median of power quality. | 2-123 |
| `:POWer:TYPE` | `:POWer:TYPE <type>` | `:POWer:TYPE?` | Sets or queries the power analysis type. | 2-121 |
| `:POWer:VOLTagesource` | `:POWer:VOLTagesource <source>` | `:POWer:VOLTagesource?` | Sets or queries the voltage source of power quality. | 2-122 |

### quick

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:QUICk:OPERation` | `:QUICk:OPERation <type>` | `:QUICk:OPERation?` | Sets or queries the type of the shortcut keys. | 2-124 |

### record

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:RECord:CURRent` | `:RECord:CURRent <value>` | `:RECord:CURRent?` | Sets or queries the current frame in waveform playing. | 2-126 |
| `:RECord:ENABle` | `:RECord:ENABle <bool>` | `:RECord:ENABle?` | Enables or disables the waveform recording function; or queries the on/off status of the waveform recording function. | 2-125 |
| `:RECord:FRAMes` | `:RECord:FRAMes <value>` | `:RECord:FRAMes?` | Sets or queries the number of frames for waveform recording. | 2-126 |
| `:RECord:PLAY` | `:RECord:PLAY <bool>` | `:RECord:PLAY?` | Enables or disables the waveform playing function; or queries the on/off status of the waveform playing function. | 2-126 |
| `:RECord:STARt` | `:RECord:STARt <bool>` | `:RECord:STARt?` | Sets to start or stop the waveform recording, or queries whether the waveform recording starts or stops. | 2-125 |

### reference

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:REFerence:COLor` | `:REFerence:COLor <ref>,<color>` | `:REFerence:COLor? <ref>` | Sets or queries the display color of the specified reference channel. | 2-129 |
| `:REFerence:CURRent` | `:REFerence:CURRent <ref>` | — | Selects the specified reference channel. | 2-129 |
| `:REFerence:DISPlay` | `:REFerence:DISPlay <bool>` | `:REFerence:DISPlay?` | Turns on or off the REF function; or queries the on/off status of the REF function. | 2-127 |
| `:REFerence:LABel:CONTent` | `:REFerence:LABel:CONTent <ref>,<str>` | `:REFerence:LABel:CONTent? <ref>` | Sets or queries the label of the specified reference channel. | 2-130 |
| `:REFerence:LABel:ENABle` | `:REFerence:LABel:ENABle <bool>` | `:REFerence:LABel:ENABle?` | Enables or disables the display of all the labels; or queries the on/off display of all the labels. | 2-130 |
| `:REFerence:RESet` | `:REFerence:RESet <ref>` | — | Resets the vertical scale and vertical offset of the specified reference channel to the defaults. | 2-129 |
| `:REFerence:SAVE` | `:REFerence:SAVE <ref>` | — | Saves the waveform of the specified reference channel to the internal memory as the reference waveform. | 2-129 |
| `:REFerence:SOURce` | `:REFerence:SOURce <ref>,<chan>` | `:REFerence:SOURce? <ref>` | Sets or queries the source of the specified reference channel. | 2-127 |
| `:REFerence:VOFFset` | `:REFerence:VOFFset <ref>,<offset>` | `:REFerence:VOFFset? <ref>` | Sets or queries the vertical offset of the specified reference channel. The unit is the same as that of the current source. | 2-128 |
| `:REFerence:VSCale` | `:REFerence:VSCale <ref>,<scale>` | `:REFerence:VSCale? <ref>` | Sets or queries the vertical scale of the specified reference channel. The unit is the same as that of the current source. | 2-128 |

### run

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:RUN` | `:RUN` | — | The :RUN command starts the oscilloscope and the :STOP command stops the oscilloscope. This command functions the same as the RUN/STOP key on the front panel. | 2-2 |

### save

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:SAVE:CSV` | `:SAVE:CSV <path>` | — | Saves the waveform data displayed on the screen to the internal or external memory in "*.csv" format. | 2-131 |
| `:SAVE:CSV:CHANnel` | `:SAVE:CSV:CHANnel <channel>,<bool>` | `:SAVE:CSV:CHANnel? <channel>` | Sets or queries the on/off status of the storage channel. | 2-132 |
| `:SAVE:CSV:LENGth` | `:SAVE:CSV:LENGth <len>` | `:SAVE:CSV:LENGth?` | Sets or queries the data length type in saving the "*.csv" file. | 2-131 |
| `:SAVE:IMAGe` | `:SAVE:IMAGe <path>` | — | Stores the contents displayed on the screen into the internal or external memory in image format. | 2-132 |
| `:SAVE:IMAGe:COLor` | `:SAVE:IMAGe:COLor <bool>` | `:SAVE:IMAGe:COLor?` | Sets the image color for image saving to Color or Gray; or queries image color for image saving. | 2-133 |
| `:SAVE:IMAGe:INVert` | `:SAVE:IMAGe:INVert <bool>` | `:SAVE:IMAGe:INVert?` | Enables or disables the invert function when saving the image; or queries whether the invert function is enabled when saving the image. | 2-133 |
| `:SAVE:IMAGe:TYPE` | `:SAVE:IMAGe:TYPE <type>` | `:SAVE:IMAGe:TYPE?` | Sets or queries in what format is the image saved. | 2-132 |
| `:SAVE:SETup` | `:SAVE:SETup <path>` | — | Saves the current setup parameters of the oscilloscope to the internal or external memory as a file. | 2-133 |
| `:SAVE:STATus` | — | `:SAVE:STATus?` | Queries the saving status of the internal memory or the external USB storage device. | 2-134 |
| `:SAVE:WAVeform` | `:SAVE:WAVeform <path>` | — | Saves the waveform data to the internal or external memory as a file. | 2-134 |

### search

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:SEARch:COUNt` | — | `:SEARch:COUNt?` | Queries the total number of search events. | 2-135 |
| `:SEARch:EDGE:SLOPe` | `:SEARch:EDGE:SLOPe <slope>` | `:SEARch:EDGE:SLOPe?` | Sets or queries the edge for the "Edge" search type. | 2-137 |
| `:SEARch:EDGE:SOURce` | `:SEARch:EDGE:SOURce <source>` | `:SEARch:EDGE:SOURce?` | Sets or queries the source for "Edge" search type. | 2-137 |
| `:SEARch:EDGE:THReshold` | `:SEARch:EDGE:THReshold <thre>` | `:SEARch:EDGE:THReshold?` | Sets or queries the threshold for "Edge" search type. | 2-138 |
| `:SEARch:EVENt` | `:SEARch:EVENt <value>` | `:SEARch:EVENt?` | Sets to navigate a search event. | 2-137 |
| `:SEARch:MODE` | `:SEARch:MODE <value>` | `:SEARch:MODE?` | Sets the search type. | 2-136 |
| `:SEARch:PULSe:LWIDth` | `:SEARch:PULSe:LWIDth <width>` | `:SEARch:PULSe:LWIDth?` | Sets or queries the pulse lower limit for "Pulse" search type. | 2-139 |
| `:SEARch:PULSe:POLarity` | `:SEARch:PULSe:POLarity <polarity>` | `:SEARch:PULSe:POLarity?` | Sets or queries the polarity for "Pulse" search type. | 2-138 |
| `:SEARch:PULSe:QUALifier` | `:SEARch:PULSe:QUALifier <qualifier>` | `:SEARch:PULSe:QUALifier?` | Sets or queries the search condition for "Pulse" search type. | 2-138 |
| `:SEARch:PULSe:SOURce` | `:SEARch:PULSe:SOURce <source>` | `:SEARch:PULSe:SOURce?` | Sets or queries the source for "Pulse" search type. | 2-139 |
| `:SEARch:PULSe:THReshold` | `:SEARch:PULSe:THReshold <thre>` | `:SEARch:PULSe:THReshold?` | Sets or queries the threshold for "Edge" search type. | 2-140 |
| `:SEARch:PULSe:UWIDth` | `:SEARch:PULSe:UWIDth <width>` | `:SEARch:PULSe:UWIDth?` | Sets or queries the pulse upper limit for "Pulse" search type. | 2-139 |
| `:SEARch:RUNT:POLarity` | `:SEARch:RUNT:POLarity <polarity>` | `:SEARch:RUNT:POLarity?` | Sets or queries the polarity for "Runt" search type. | 2-140 |
| `:SEARch:RUNT:QUALifier` | `:SEARch:RUNT:QUALifier <qualifier>` | `:SEARch:RUNT:QUALifier?` | Sets or queries the search condition for "Runt" search type. | 2-140 |
| `:SEARch:RUNT:SOURce` | `:SEARch:RUNT:SOURce <source>` | `:SEARch:RUNT:SOURce?` | Sets or queries the source for "Runt" search type. | 2-141 |
| `:SEARch:RUNT:THReshold1` | `:SEARch:RUNT:THReshold1 <thre>` | `:SEARch:RUNT:THReshold1?` | Sets or queries Threshold A for "Runt" search type. | 2-142 |
| `:SEARch:RUNT:THReshold2` | `:SEARch:RUNT:THReshold2 <thre>` | `:SEARch:RUNT:THReshold2?` | Sets or queries Threshold B for "Runt" search type. | 2-142 |
| `:SEARch:RUNT:WLOWer` | `:SEARch:RUNT:WLOWer <width>` | `:SEARch:RUNT:WLOWer?` | Sets or queries the pulse lower limit for "Runt" search type. | 2-141 |
| `:SEARch:RUNT:WUPPer` | `:SEARch:RUNT:WUPPer <width>` | `:SEARch:RUNT:WUPPer?` | Sets or queries the pulse upper limit for "Runt" search type. | 2-141 |
| `:SEARch:SLOPe:POLarity` | `:SEARch:SLOPe:POLarity <polarity>` | `:SEARch:SLOPe:POLarity?` | Sets or queries the edge type for "Slope" search type. | 2-142 |
| `:SEARch:SLOPe:QUALifier` | `:SEARch:SLOPe:QUALifier <qualifier>` | `:SEARch:SLOPe:QUALifier?` | Sets or queries the search condition for "Slope" search type. | 2-143 |
| `:SEARch:SLOPe:SOURce` | `:SEARch:SLOPe:SOURce <source>` | `:SEARch:SLOPe:SOURce?` | Sets or queries the source for "Slope" search type. | 2-143 |
| `:SEARch:SLOPE:THReshold1` | `:SEARch:SLOPE:THReshold1 <thre>` | `:SEARch:SLOPE:THReshold1?` | Sets or queries Threshold A for "Slope" search type. | 2-144 |
| `:SEARch:SLOPE:THReshold2` | `:SEARch:SLOPE:THReshold2 <thre>` | `:SEARch:SLOPE:THReshold2?` | Sets or queries Threshold B for "Slope" search type. | 2-144 |
| `:SEARch:SLOPE:TLOWer` | `:SEARch:SLOPE:TLOWer <width>` | `:SEARch:SLOPE:TLOWer?` | Sets or queries the time lower limit for "Slope" search type. | 2-144 |
| `:SEARch:SLOPe:TUPPer` | `:SEARch:SLOPe:TUPPer <time>` | `:SEARch:SLOPe:TUPPer?` | Sets or queries the time upper limit for "Slope" search type. | 2-143 |
| `:SEARch:STATe` | `:SEARch:STATe <bool>` | `:SEARch:STATe?` | Enables or disables the search function; or queries the on/off status of the search function. | 2-136 |
| `:SEARch:VALue` | — | `:SEARch:VALue? <x>` | Queries the time that corresponds to the specified event number. | 2-136 |

### sfp

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:SFP:APPLy` | `:SFP:APPLy` | — | Applies the network configuration for the SFP+ interface. | 2-145 |
| `:SFP:CLOSe` | `:SFP:CLOSe` | — | Disables the SFP+ interface. | 2-145 |
| `:SFP:LOCal:CMD:PORT` | `:SFP:LOCal:CMD:PORT <string>` | `:SFP:LOCal:CMD:PORT?` | Sets or queries the local command port number of the SFP+ interface. | 2-147 |
| `:SFP:LOCal:DATa:PORT` | `:SFP:LOCal:DATa:PORT <string>` | `:SFP:LOCal:DATa:PORT?` | Sets or queries the local data port number of the SFP+ interface. | 2-147 |
| `:SFP:LOCal:IPADdress` | `:SFP:LOCal:IPADdress <string>` | `:SFP:LOCal:IPADdress?` | Sets or queries the local IP address of the SFP+ interface. | 2-147 |
| `:SFP:MAC` | — | `:SFP:MAC?` | Queries the local MAC address of the SFP+ interface. | 2-146 |
| `:SFP:OPEN` | `:SFP:OPEN` | — | Enables the SFP+ interface. | 2-145 |
| `:SFP:REMote:CMD:PORT` | `:SFP:REMote:CMD:PORT <string>` | `:SFP:REMote:CMD:PORT?` | Sets or queries the destination command port number of the SFP+ interface. | 2-149 |
| `:SFP:REMote:DATa:PORT` | `:SFP:REMote:DATa:PORT <string>` | `:SFP:REMote:DATa:PORT?` | Sets or queries the destination data port number of the SFP+ interface. | 2-149 |
| `:SFP:REMote:IPADdress` | `:SFP:REMote:IPADdress <string>` | `:SFP:REMote:IPADdress?` | Sets or queries the destination IP address of the SFP+ interface. | 2-149 |
| `:SFP:STATus` | — | `:SFP:STATus?` | Queries the on/off status of the SFP+ interface. | 2-145 |

### single

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:SINGle` | `:SINGle` | — | Sets the trigger mode of the oscilloscope to "Single". This command functions the same as either of the following two operation: click the Single key at the right section of the | 2-2 |

### stop

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:STOP` | `:STOP` | — | The :RUN command starts the oscilloscope and the :STOP command stops the oscilloscope. This command functions the same as the RUN/STOP key on the front panel. | 2-2 |

### system

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:SYSTem:AOUTput` | `:SYSTem:AOUTput <aux output>` | `:SYSTem:AOUTput?` | Sets or queries the type of the signal output from the [TRIG OUT] connector on the rear panel. | 2-165 |
| `:SYSTem:AUTClear` | `:SYSTem:AUTClear` | — | Restores the default password for AUTO lock (the default password is none). | 2-165 |
| `:SYSTem:AUToscale` | `:SYSTem:AUToscale <bool>` | `:SYSTem:AUToscale?` | Enables or disables the Auto function; or queries the on/off status of the Auto function. | 2-165 |
| `:SYSTem:BEEPer` | `:SYSTem:BEEPer <bool>` | `:SYSTem:BEEPer?` | Turns on or off the beeper; or queries the on/off status of the beeper. | 2-166 |
| `:SYSTem:DATE` | `:SYSTem:DATE <year>,<month>,<day>.` | `:SYSTem:DATE?` | Sets or queries the system date. | 2-166 |
| `:SYSTem:ERRor[:NEXT]` | — | `:SYSTem:ERRor[:NEXT]?` | Queries and clears the latest error message. | 2-166 |
| `:SYSTem:EXT:MODEalarm` | `:SYSTem:EXT:MODEalarm <bool>` | `:SYSTem:EXT:MODEalarm?` | Sets or queries the alarm mode. | 2-172 |
| `:SYSTem:EXT:OVERload` | — | `:SYSTem:EXT:OVERload?` | Queries whether the external trigger is overloaded. | 2-171 |
| `:SYSTem:GAMount` | — | `:SYSTem:GAMount?` | Queries the number of grids in the horizontal direction of the screen. | 2-166 |
| `:SYSTem:GPIB` | `:SYSTem:GPIB <adr>` | `:SYSTem:GPIB?` | Sets or queries the GPIB address. | 2-167 |
| `:SYSTem:LANGuage` | `:SYSTem:LANGuage <language>` | `:SYSTem:LANGuage?` | Sets or queries the system language. | 2-167 |
| `:SYSTem:LOCKed` | `:SYSTem:LOCKed <bool>` | `:SYSTem:LOCKed?` | Turns on or off the keyboard lock function; or queries whether the keyboard is locked or unlocked. | 2-171 |
| `:SYSTem:MODules` | — | `:SYSTem:MODules?` | Queries the hardware modules. | 2-171 |
| `:SYSTem:OPTion:INSTall` | `:SYSTem:OPTion:INSTall <license>` | — | Installs an option. | 2-168 |
| `:SYSTem:OPTion:STATus` | — | `:SYSTem:OPTion:STATus? <type>` | Queries the status of the options of the oscilloscope. | 2-169 |
| `:SYSTem:OPTion:UNINstall` | `:SYSTem:OPTion:UNINstall` | — | Uninstalls all the official options. | 2-169 |
| `:SYSTem:PON` | `:SYSTem:PON <power_on>` | `:SYSTem:PON?` | Sets or queries the configuration type recalled by the oscilloscope when it is powered on again after power-off. | 2-168 |
| `:SYSTem:PSTatus` | `:SYSTem:PSTatus <sat>` | `:SYSTem:PSTatus?` | Sets or queries the power status of the oscilloscope. | 2-168 |
| `:SYSTem:PWDClear` | `:SYSTem:PWDClear` | — | Restores the default password for web control (the default password is rigol). | 2-169 |
| `:SYSTem:RAMount` | — | `:SYSTem:RAMount?` | Queries the number of analog channels of the current instrument. | 2-170 |
| `:SYSTem:RCLock` | `:SYSTem:RCLock <clock>` | `:SYSTem:RCLock?` | Sets or queries the type of the reference clock. | 2-167 |
| `:SYSTem:RESet` | `:SYSTem:RESet` | — | Resets the system to power on again. | 2-170 |
| `:SYSTem:SETup` | `:SYSTem:SETup <setup_data>` | `:SYSTem:SETup?` | Sends or reads the data stream of the system setup file. | 2-170 |
| `:SYSTem:SSAVer:TIME` | `:SYSTem:SSAVer:TIME <time>` | `:SYSTem:SSAVer:TIME?` | Sets or queries the screen saver time. The default unit for the value is minute. | 2-170 |
| `:SYSTem:TIME` | `:SYSTem:TIME <hours>,<minutes>,<seconds>` | `:SYSTem:TIME?` | Sets or queries the system time. | 2-171 |

### tforce

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:TFORce` | `:TFORce` | — | Generates a trigger signal forcibly. This command is only applicable to the normal and single trigger modes (refer to the :TRIGger:SWEep command). This command functions the same as the Force key… | 2-3 |

### timebase

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:TIMebase:DELay:ENABle` | `:TIMebase:DELay:ENABle <bool>` | `:TIMebase:DELay:ENABle?` | Turns on or off the delayed sweep; or queries the on/off status of the delayed sweep. | 2-173 |
| `:TIMebase:DELay:OFFSet` | `:TIMebase:DELay:OFFSet <offset>` | `:TIMebase:DELay:OFFSet?` | Sets or queries the offset of the delayed time base. The default unit is s. | 2-173 |
| `:TIMebase:DELay:SCALe` | `:TIMebase:DELay:SCALe <scale>` | `:TIMebase:DELay:SCALe?` | Sets or queries the scale of the delayed time base. The default unit is s/div. | 2-174 |
| `:TIMebase:HREFerence:MODE` | `:TIMebase:HREFerence:MODE <href>` | `:TIMebase:HREFerence:MODE?` | Sets or queries the horizontal reference mode. | 2-175 |
| `:TIMebase:HREFerence:POSition` | `:TIMebase:HREFerence:POSition <pos>` | `:TIMebase:HREFerence:POSition?` | Sets or queries the user-defined reference position when the waveforms are expanded or compressed horizontally. | 2-176 |
| `:TIMebase:MODE` | `:TIMebase:MODE <mode>` | `:TIMebase:MODE?` | Sets or queries the horizontal time base mode. | 2-175 |
| `:TIMebase:VERNier` | `:TIMebase:VERNier <bool>` | `:TIMebase:VERNier?` | Enables or disables the fine adjustment function of the horizontal scale; or queries the on/off status of the fine adjustment function of the horizontal scale. | 2-176 |
| `:TIMebase[:MAIN]:OFFSet` | `:TIMebase[:MAIN]:OFFSet <offset>` | `:TIMebase[:MAIN]:OFFSet?` | Sets or queries the offset of the main time base. The default unit is s. | 2-174 |
| `:TIMebase[:MAIN]:SCALe` | `:TIMebase[:MAIN]:SCALe <scale>` | `:TIMebase[:MAIN]:SCALe?` | Sets or queries the scale of the main time base. | 2-175 |

### trigger

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:TRIGger:CAN:BAUD` | `:TRIGger:CAN:BAUD <baud>` | `:TRIGger:CAN:BAUD?` | Sets or queries the signal rate of CAN trigger. The unit is bps. | 2-223 |
| `:TRIGger:CAN:LEVel` | `:TRIGger:CAN:LEVel <level>` | `:TRIGger:CAN:LEVel?` | Sets or queries the trigger level of CAN trigger. Its unit is the same as that of the current amplitude. | 2-225 |
| `:TRIGger:CAN:SOURce` | `:TRIGger:CAN:SOURce <source>` | `:TRIGger:CAN:SOURce?` | Sets or queries the trigger source of CAN trigger. | 2-223 |
| `:TRIGger:CAN:SPOint` | `:TRIGger:CAN:SPOint <spoint>` | `:TRIGger:CAN:SPOint?` | Sets or queries the sample point position of CAN trigger (expressed in %). | 2-224 |
| `:TRIGger:CAN:STYPe` | `:TRIGger:CAN:STYPe <stype>` | `:TRIGger:CAN:STYPe?` | Sets or queries the signal type of CAN trigger. | 2-223 |
| `:TRIGger:CAN:WHEN` | `:TRIGger:CAN:WHEN <cond>` | `:TRIGger:CAN:WHEN?` | Sets or queries the trigger condition of CAN trigger. | 2-224 |
| `:TRIGger:COUPling` | `:TRIGger:COUPling <couple>` | `:TRIGger:COUPling?` | Selects or queries the trigger coupling type. | 2-179 |
| `:TRIGger:DELay:ALEVel` | `:TRIGger:DELay:ALEVel <level>` | `:TRIGger:DELay:ALEVel?` | Sets or queries the threshold level of source A of Delay trigger. The unit is the same as that of the current amplitude. | 2-208 |
| `:TRIGger:DELay:BLEVel` | `:TRIGger:DELay:BLEVel <level>` | `:TRIGger:DELay:BLEVel?` | Sets or queries the threshold level of source B of Delay trigger. The unit is the same as that of the current amplitude. | 2-209 |
| `:TRIGger:DELay:SA` | `:TRIGger:DELay:SA <Source>` | `:TRIGger:DELay:SA?` | Sets or queries the trigger source of Source A in Delay trigger. | 2-206 |
| `:TRIGger:DELay:SB` | `:TRIGger:DELay:SB <source>` | `:TRIGger:DELay:SB?` | Sets or queries the trigger source of Source B in Delay trigger. | 2-207 |
| `:TRIGger:DELay:SLOPA` | `:TRIGger:DELay:SLOPA <slope>` | `:TRIGger:DELay:SLOPA?` | Sets or queries the edge type of Edge A in Delay trigger. | 2-206 |
| `:TRIGger:DELay:SLOPB` | `:TRIGger:DELay:SLOPB <slope>` | `:TRIGger:DELay:SLOPB?` | Sets or queries the edge type of Edge B in Delay trigger. | 2-207 |
| `:TRIGger:DELay:TLOWer` | `:TRIGger:DELay:TLOWer <time>` | `:TRIGger:DELay:TLOWer?` | Sets or queries the lower limit of delay time of the Delay trigger. The default unit is s. | 2-208 |
| `:TRIGger:DELay:TUPPer` | `:TRIGger:DELay:TUPPer <time>` | `:TRIGger:DELay:TUPPer?` | Sets or queries the upper limit of delay time of the Delay trigger. The default unit is s. | 2-208 |
| `:TRIGger:DELay:TYPE` | `:TRIGger:DELay:TYPE <type>` | `:TRIGger:DELay:TYPE?` | Sets or queries the delay type of Delay trigger. | 2-207 |
| `:TRIGger:DURation:LEVel` | `:TRIGger:DURation:LEVel <source>,<level>` | `:TRIGger:DURation:LEVel? <source>` | Sets or queries the trigger level of the specified channel in Duration trigger. The unit is the same as that of the current amplitude. | 2-197 |
| `:TRIGger:DURation:SOURce` | `:TRIGger:DURation:SOURce <source>` | `:TRIGger:DURation:SOURce?` | Sets or queries the trigger source of Duration trigger. | 2-195 |
| `:TRIGger:DURation:TLOWer` | `:TRIGger:DURation:TLOWer <time>` | `:TRIGger:DURation:TLOWer?` | Sets or queries the lower limit of the duration time of Duration trigger. The default unit is s. | 2-196 |
| `:TRIGger:DURation:TUPPer` | `:TRIGger:DURation:TUPPer <time>` | `:TRIGger:DURation:TUPPer?` | Sets or queries the upper limit of the duration time of Duration trigger. The default unit is s. | 2-196 |
| `:TRIGger:DURation:TYPE` | `:TRIGger:DURation:TYPE` | — | Sets or queries the channel pattern of Duration trigger. | 2-195 |
| `:TRIGger:DURation:WHEN` | `:TRIGger:DURation:WHEN <when>` | `:TRIGger:DURation:WHEN?` | Sets or queries the trigger condition of Duration trigger. | 2-196 |
| `:TRIGger:EDGE:LEVel` | `:TRIGger:EDGE:LEVel <level>` | `:TRIGger:EDGE:LEVel?` | Sets or queries the trigger level of Edge trigger. The unit is the same as that of current amplitude of the selected source. | 2-183 |
| `:TRIGger:EDGE:SLOPe` | `:TRIGger:EDGE:SLOPe <slope>` | `:TRIGger:EDGE:SLOPe?` | Sets or queries the edge type of Edge trigger. | 2-182 |
| `:TRIGger:EDGE:SOURce` | `:TRIGger:EDGE:SOURce <source>` | `:TRIGger:EDGE:SOURce?` | Sets or queries the trigger source of Edge trigger. | 2-182 |
| `:TRIGger:EXTDelay` | `:TRIGger:EXTDelay <value>` | `:TRIGger:EXTDelay?` | Sets or queries the delay of the external trigger. | 2-181 |
| `:TRIGger:FLEXray:BAUD` | `:TRIGger:FLEXray:BAUD <baud>` | `:TRIGger:FLEXray:BAUD?` | Sets or queries the signal rate of FlexRay trigger. The default unit is bps. | 2-231 |
| `:TRIGger:FLEXray:LEVel` | `:TRIGger:FLEXray:LEVel <level>` | `:TRIGger:FLEXray:LEVel?` | Sets or queries the trigger level of FlexRay trigger. Its unit is the same as that of the current amplitude. | 2-231 |
| `:TRIGger:FLEXray:SOURce` | `:TRIGger:FLEXray:SOURce <source>` | `:TRIGger:FLEXray:SOURce?` | Sets or queries the trigger source of FlexRay trigger. | 2-232 |
| `:TRIGger:FLEXray:WHEN` | `:TRIGger:FLEXray:WHEN <cond>` | `:TRIGger:FLEXray:WHEN?` | Sets or queries the trigger condition of FLEXray trigger. | 2-232 |
| `:TRIGger:HOLDoff` | `:TRIGger:HOLDoff <value>` | `:TRIGger:HOLDoff?` | Sets or queries the trigger holdoff time. The default unit is s. | 2-180 |
| `:TRIGger:IIC:ADDRess` | `:TRIGger:IIC:ADDRess <address>` | `:TRIGger:IIC:ADDRess?` | Sets or queries the address of I2C trigger when the trigger condition is "ADDRess" or "ADATa". | 2-221 |
| `:TRIGger:IIC:AWIDth` | `:TRIGger:IIC:AWIDth <bits>` | `:TRIGger:IIC:AWIDth?` | Sets or queries the address width of I2C trigger when the trigger condition is "ADDRess" or "ADATa". | 2-220 |
| `:TRIGger:IIC:CLEVel` | `:TRIGger:IIC:CLEVel <level>` | `:TRIGger:IIC:CLEVel?` | Sets or queries the trigger level of the clock line in I2C trigger. The unit is the same as that of the current amplitude. | 2-222 |
| `:TRIGger:IIC:DATA` | `:TRIGger:IIC:DATA <data>` | `:TRIGger:IIC:DATA?` | Sets or queries the data value of I2C trigger when the trigger condition is "DATA" or "ADATa". | 2-221 |
| `:TRIGger:IIC:DBYTes` | `:TRIGger:IIC:DBYTes <bytes>` | `:TRIGger:IIC:DBYTes?` | Sets or queries the data bytes of I2C trigger when the trigger condition is "Data" or "A&D". | 2-222 |
| `:TRIGger:IIC:DIRection` | `:TRIGger:IIC:DIRection <direction>` | `:TRIGger:IIC:DIRection?` | Sets or queries the data direction of I2C trigger when the trigger condition is "ADDRess" or "ADATa". | 2-221 |
| `:TRIGger:IIC:DLEVel` | `:TRIGger:IIC:DLEVel <level>` | `:TRIGger:IIC:DLEVel?` | Sets or queries the trigger level of the data line in I2C trigger. The unit is the same as that of the current amplitude. | 2-222 |
| `:TRIGger:IIC:SCL` | `:TRIGger:IIC:SCL <source>` | `:TRIGger:IIC:SCL?` | Sets or queries the source channel of the clock line of I2C trigger. | 2-219 |
| `:TRIGger:IIC:SDA` | `:TRIGger:IIC:SDA <source>` | `:TRIGger:IIC:SDA?` | Sets or queries the source channel of the data line of I2C trigger. | 2-219 |
| `:TRIGger:IIC:WHEN` | `:TRIGger:IIC:WHEN <when>` | `:TRIGger:IIC:WHEN?` | Refer to the programming guide for behavior and prerequisites. | 2-219 |
| `:TRIGger:IIS:ALIGnment` | `:TRIGger:IIS:ALIGnment <setting>` | `:TRIGger:IIS:ALIGnment?` | Sets or queries the alignment mode of the I2S trigger. | 2-233 |
| `:TRIGger:IIS:AUDio` | `:TRIGger:IIS:AUDio <audio>` | `:TRIGger:IIS:AUDio?` | Sets or queries the audio state of I2S trigger. | 2-235 |
| `:TRIGger:IIS:CLOCk:SLOPe` | `:TRIGger:IIS:CLOCk:SLOPe <slope>` | `:TRIGger:IIS:CLOCk:SLOPe?` | Sets or queries the type of the clock edge of I2S trigger. | 2-233 |
| `:TRIGger:IIS:DATA` | `:TRIGger:IIS:DATA <data>` | `:TRIGger:IIS:DATA?` | Sets or queries the data value of the I2S trigger. | 2-236 |
| `:TRIGger:IIS:SOURce:CLOCk` | `:TRIGger:IIS:SOURce:CLOCk <source>` | `:TRIGger:IIS:SOURce:CLOCk?` | Sets or queries the clock source of the I2S trigger. | 2-234 |
| `:TRIGger:IIS:SOURce:DATA` | `:TRIGger:IIS:SOURce:DATA <source>` | `:TRIGger:IIS:SOURce:DATA?` | Sets or queries the data source of the I2S trigger. | 2-234 |
| `:TRIGger:IIS:SOURce:WSELect` | `:TRIGger:IIS:SOURce:WSELect <source>` | `:TRIGger:IIS:SOURce:WSELect?` | Sets or queries the audio channel of the I2S trigger. | 2-234 |
| `:TRIGger:IIS:WHEN` | `:TRIGger:IIS:WHEN <operator>` | `:TRIGger:IIS:WHEN?` | Sets or queries the trigger condition of I2S trigger. | 2-235 |
| `:TRIGger:LIN:BAUD` | `:TRIGger:LIN:BAUD <baud>` | `:TRIGger:LIN:BAUD?` | Sets or queries the baud rate of LIN trigger. The default unit is bps. | 2-237 |
| `:TRIGger:LIN:ID` | `:TRIGger:LIN:ID <id>` | `:TRIGger:LIN:ID?` | Sets or queries the ID value of LIN trigger. | 2-237 |
| `:TRIGger:LIN:LEVel` | `:TRIGger:LIN:LEVel <level>` | `:TRIGger:LIN:LEVel?` | Sets or queries the trigger level of LIN trigger. Its unit is the same as that of the current amplitude. | 2-239 |
| `:TRIGger:LIN:SAMPlepoint` | `:TRIGger:LIN:SAMPlepoint <value>` | `:TRIGger:LIN:SAMPlepoint?` | Sets or queries the sample position of LIN trigger. | 2-238 |
| `:TRIGger:LIN:SOURce` | `:TRIGger:LIN:SOURce <source>` | `:TRIGger:LIN:SOURce?` | Sets or queries the trigger source of LIN trigger. | 2-237 |
| `:TRIGger:LIN:STANdard` | `:TRIGger:LIN:STANdard <std>` | `:TRIGger:LIN:STANdard?` | Sets or queries the protocol version of LIN trigger. | 2-238 |
| `:TRIGger:LIN:WHEN` | `:TRIGger:LIN:WHEN <when>` | `:TRIGger:LIN:WHEN?` | Sets or queries the trigger condition of LIN trigger. | 2-238 |
| `:TRIGger:M1553:ALEVel` | `:TRIGger:M1553:ALEVel <level>` | `:TRIGger:M1553:ALEVel?` | Sets or queries the upper limit of the trigger level of M1553 trigger. The unit is the same as that of the current amplitude. | 2-241 |
| `:TRIGger:M1553:BLEVel` | `:TRIGger:M1553:BLEVel <level>` | `:TRIGger:M1553:BLEVel?` | Sets or queries the lower limit of the trigger level of M1553 trigger. The unit is the same as that of the current amplitude. | 2-241 |
| `:TRIGger:M1553:POLarity` | `:TRIGger:M1553:POLarity <polarity>` | `:TRIGger:M1553:POLarity?` | Refer to the programming guide for behavior and prerequisites. | 2-240 |
| `:TRIGger:M1553:SOURce` | `:TRIGger:M1553:SOURce <source>` | `:TRIGger:M1553:SOURce?` | Sets or queries the trigger source of M1553 trigger. | 2-240 |
| `:TRIGger:M1553:WHEN` | `:TRIGger:M1553:WHEN <when>` | `:TRIGger:M1553:WHEN?` | Sets or queries the trigger condition of M1553 trigger. | 2-240 |
| `:TRIGger:MODE` | `:TRIGger:MODE <mode>` | `:TRIGger:MODE?` | Selects or queries the trigger type. | 2-179 |
| `:TRIGger:NEDGe:EDGE` | `:TRIGger:NEDGe:EDGE <edge>` | `:TRIGger:NEDGe:EDGE?` | Sets or queries the number of edges of the Nth Edge trigger. | 2-215 |
| `:TRIGger:NEDGe:IDLE` | `:TRIGger:NEDGe:IDLE <time>` | `:TRIGger:NEDGe:IDLE?` | Sets or queries the idle time of the Nth Edge trigger. The default unit is s. | 2-214 |
| `:TRIGger:NEDGe:LEVel` | `:TRIGger:NEDGe:LEVel <level>` | `:TRIGger:NEDGe:LEVel?` | Sets or queries the trigger level of the Nth Edge trigger. The unit is the same as that of current amplitude. | 2-215 |
| `:TRIGger:NEDGe:SLOPe` | `:TRIGger:NEDGe:SLOPe <slope>` | `:TRIGger:NEDGe:SLOPe?` | Sets or queries the edge type of the Nth Edge trigger. | 2-214 |
| `:TRIGger:NEDGe:SOURce` | `:TRIGger:NEDGe:SOURce <source>` | `:TRIGger:NEDGe:SOURce?` | Sets or queries the trigger source of the Nth Edge trigger. | 2-214 |
| `:TRIGger:NREJect` | `:TRIGger:NREJect <bool>` | `:TRIGger:NREJect?` | Turns on or off noise rejection; or queries the on/off status of noise rejection. | 2-181 |
| `:TRIGger:PATTern:LEVel` | `:TRIGger:PATTern:LEVel <source>,<level>` | `:TRIGger:PATTern:LEVel? <source>` | Sets or queries the trigger level of the specified channel in Pattern trigger. The unit is the same as that of the current amplitude. | 2-193 |
| `:TRIGger:PATTern:PATTern` | `:TRIGger:PATTern:PATTern` | — | Sets or queries the channel pattern of Pattern trigger. | 2-193 |
| `:TRIGger:PATTern:SOURce` | `:TRIGger:PATTern:SOURce <source>` | `:TRIGger:PATTern:SOURce?` | Sets or queries the trigger source of Pattern trigger. | 2-194 |
| `:TRIGger:PULSe:LEVel` | `:TRIGger:PULSe:LEVel <level>` | `:TRIGger:PULSe:LEVel?` | Sets or queries the trigger level of Pulse trigger. The unit is the same as that of the current amplitude. | 2-185 |
| `:TRIGger:PULSe:LWIDth` | `:TRIGger:PULSe:LWIDth <width>` | `:TRIGger:PULSe:LWIDth?` | Sets or queries the pulse lower limit of the Pulse trigger. The default unit is s. | 2-185 |
| `:TRIGger:PULSe:SOURce` | `:TRIGger:PULSe:SOURce <source>` | `:TRIGger:PULSe:SOURce?` | Sets or queries the trigger source of Pulse trigger. | 2-184 |
| `:TRIGger:PULSe:UWIDth` | `:TRIGger:PULSe:UWIDth <width>` | `:TRIGger:PULSe:UWIDth?` | Sets or queries the pulse upper limit of the Pulse trigger. The default unit is s. | 2-185 |
| `:TRIGger:PULSe:WHEN` | `:TRIGger:PULSe:WHEN <when>` | `:TRIGger:PULSe:WHEN?` | Sets or queries the trigger condition of Pulse trigger. | 2-184 |
| `:TRIGger:RS232:BAUD` | `:TRIGger:RS232:BAUD <baud>` | `:TRIGger:RS232:BAUD?` | Sets or queries the baud rate of RS232 trigger. The default unit is bps. | 2-218 |
| `:TRIGger:RS232:DATA` | `:TRIGger:RS232:DATA <data>` | `:TRIGger:RS232:DATA?` | Sets or queries the data value of RS232 trigger when the trigger condition is "Data". | 2-217 |
| `:TRIGger:RS232:LEVel` | `:TRIGger:RS232:LEVel <level>` | `:TRIGger:RS232:LEVel?` | Sets or queries the trigger level of RS232 trigger. The unit is the same as that of the current amplitude. | 2-218 |
| `:TRIGger:RS232:PARity` | `:TRIGger:RS232:PARity <parity>` | `:TRIGger:RS232:PARity?` | Sets or queries the check mode of RS232 trigger. | 2-217 |
| `:TRIGger:RS232:SOURce` | `:TRIGger:RS232:SOURce <source>` | `:TRIGger:RS232:SOURce?` | Sets or queries the trigger source of RS232 trigger. | 2-216 |
| `:TRIGger:RS232:STOP` | `:TRIGger:RS232:STOP <bit>` | `:TRIGger:RS232:STOP?` | Sets or queries the stop bits of RS232 trigger. | 2-217 |
| `:TRIGger:RS232:WHEN` | `:TRIGger:RS232:WHEN <when>` | `:TRIGger:RS232:WHEN?` | Sets or queries the trigger condition of RS232 trigger. | 2-216 |
| `:TRIGger:RS232:WIDTh` | `:TRIGger:RS232:WIDTh <width>` | `:TRIGger:RS232:WIDTh?` | Sets or queries the data width of RS232 trigger when the trigger condition is "Data". | 2-218 |
| `:TRIGger:RUNT:ALEVel` | `:TRIGger:RUNT:ALEVel <level>` | `:TRIGger:RUNT:ALEVel?` | Sets or queries the upper limit of the trigger level of Runt trigger. The unit is the same as that of the current amplitude. | 2-202 |
| `:TRIGger:RUNT:BLEVel` | `:TRIGger:RUNT:BLEVel <level>` | `:TRIGger:RUNT:BLEVel?` | Sets or queries the lower limit of the trigger level of Runt trigger. The unit is the same as that of the current amplitude. | 2-202 |
| `:TRIGger:RUNT:POLarity` | `:TRIGger:RUNT:POLarity <polarity>` | `:TRIGger:RUNT:POLarity?` | Sets or queries the polarity of Runt trigger. | 2-200 |
| `:TRIGger:RUNT:SOURce` | `:TRIGger:RUNT:SOURce <source>` | `:TRIGger:RUNT:SOURce?` | Sets or queries the trigger source of Runt trigger. | 2-200 |
| `:TRIGger:RUNT:WHEN` | `:TRIGger:RUNT:WHEN <when>` | `:TRIGger:RUNT:WHEN?` | Sets or queries the qualifier of Runt trigger. | 2-201 |
| `:TRIGger:RUNT:WLOWer` | `:TRIGger:RUNT:WLOWer <width>` | `:TRIGger:RUNT:WLOWer?` | Sets or queries the lower limit of the pulse width of Runt trigger. The default unit is s. | 2-201 |
| `:TRIGger:RUNT:WUPPer` | `:TRIGger:RUNT:WUPPer <width>` | `:TRIGger:RUNT:WUPPer?` | Sets or queries the upper limit of the pulse width of Runt trigger. The default unit is s. | 2-201 |
| `:TRIGger:SHOLd:CLEVel` | `:TRIGger:SHOLd:CLEVel <level>` | `:TRIGger:SHOLd:CLEVel?` | Sets or queries the trigger level of the clock source. The unit is the same as that of the current amplitude. | 2-213 |
| `:TRIGger:SHOLd:CSRC` | `:TRIGger:SHOLd:CSRC <source>` | `:TRIGger:SHOLd:CSRC?` | Sets or queries the clock source of Setup&Hold trigger. | 2-210 |
| `:TRIGger:SHOLd:DLEVel` | `:TRIGger:SHOLd:DLEVel <level>` | `:TRIGger:SHOLd:DLEVel?` | Sets or queries the trigger level of the data source. The unit is the same as that of the current amplitude. | 2-212 |
| `:TRIGger:SHOLd:DSRC` | `:TRIGger:SHOLd:DSRC <source>` | `:TRIGger:SHOLd:DSRC?` | Sets or queries the data source of Setup&Hold trigger. | 2-210 |
| `:TRIGger:SHOLd:HTIMe` | `:TRIGger:SHOLd:HTIMe <time>` | `:TRIGger:SHOLd:HTIMe?` | Sets or queries the hold time of Setup&Hold trigger. The default unit is s. | 2-212 |
| `:TRIGger:SHOLd:PATTern` | `:TRIGger:SHOLd:PATTern <pattern>` | `:TRIGger:SHOLd:PATTern?` | Sets or queries the data type of Setup&Hold trigger. | 2-211 |
| `:TRIGger:SHOLd:SLOPe` | `:TRIGger:SHOLd:SLOPe <slope>` | `:TRIGger:SHOLd:SLOPe?` | Sets or queries the edge type of Setup&Hold trigger. | 2-210 |
| `:TRIGger:SHOLd:STIMe` | `:TRIGger:SHOLd:STIMe <time>` | `:TRIGger:SHOLd:STIMe?` | Sets or queries the setup time of Setup&Hold trigger. The default unit is s. | 2-212 |
| `:TRIGger:SHOLd:TYPE` | `:TRIGger:SHOLd:TYPE <type>` | `:TRIGger:SHOLd:TYPE?` | Sets or queries the hold type of Setup&Hold trigger. | 2-211 |
| `:TRIGger:SLOPe:ALEVel` | `:TRIGger:SLOPe:ALEVel <level>` | `:TRIGger:SLOPe:ALEVel?` | Sets or queries the upper limit of the trigger level of Slope trigger. The unit is the same as that of the current amplitude. | 2-188 |
| `:TRIGger:SLOPe:BLEVel` | `:TRIGger:SLOPe:BLEVel <level>` | `:TRIGger:SLOPe:BLEVel?` | Sets or queries the lower limit of the trigger level of Slope trigger. The unit is the same as that of the current amplitude. | 2-188 |
| `:TRIGger:SLOPe:SOURce` | `:TRIGger:SLOPe:SOURce <channel>` | `:TRIGger:SLOPe:SOURce?` | Sets or queries the trigger source of Slope trigger. | 2-186 |
| `:TRIGger:SLOPe:TLOWer` | `:TRIGger:SLOPe:TLOWer <time>` | `:TRIGger:SLOPe:TLOWer?` | Sets or queries the lower time limit value of the Slope trigger. The default unit is s. | 2-187 |
| `:TRIGger:SLOPe:TUPPer` | `:TRIGger:SLOPe:TUPPer <time>` | `:TRIGger:SLOPe:TUPPer?` | Sets or queries the upper time limit value of the Slope trigger. The default unit is s. | 2-187 |
| `:TRIGger:SLOPe:WHEN` | `:TRIGger:SLOPe:WHEN <when>` | `:TRIGger:SLOPe:WHEN?` | Sets or queries the trigger condition of Slope trigger. | 2-186 |
| `:TRIGger:SLOPe:WINDow` | `:TRIGger:SLOPe:WINDow <window>` | `:TRIGger:SLOPe:WINDow?` | Sets or queries the vertical window type of Slope trigger. | 2-187 |
| `:TRIGger:SPI:CLEVel` | `:TRIGger:SPI:CLEVel <level>` | `:TRIGger:SPI:CLEVel?` | Sets or queries the trigger level of the clock channel of SPI trigger. The unit is the same as that of the current amplitude. | 2-228 |
| `:TRIGger:SPI:CS` | `:TRIGger:SPI:CS <source>` | `:TRIGger:SPI:CS?` | Sets or queries the source channel of the CS line when the trigger condition of SPI is set to CS. | 2-230 |
| `:TRIGger:SPI:DATA` | `:TRIGger:SPI:DATA <data>` | `:TRIGger:SPI:DATA?` | Sets or queries the data value of SPI trigger. | 2-227 |
| `:TRIGger:SPI:DLEVel` | `:TRIGger:SPI:DLEVel <level>` | `:TRIGger:SPI:DLEVel?` | Sets or queries the trigger level of the data channel of SPI trigger. The unit is the same as that of the current amplitude. | 2-229 |
| `:TRIGger:SPI:MODE` | `:TRIGger:SPI:MODE <mode>` | `:TRIGger:SPI:MODE?` | Sets or queries the CS mode of SPI trigger when the trigger condition is "CS". | 2-229 |
| `:TRIGger:SPI:SCL` | `:TRIGger:SPI:SCL <source>` | `:TRIGger:SPI:SCL?` | Sets or queries the channel source of the clock line of SPI trigger. | 2-226 |
| `:TRIGger:SPI:SDA` | `:TRIGger:SPI:SDA <source>` | `:TRIGger:SPI:SDA?` | Sets or queries the channel source of the data line of SPI trigger. | 2-226 |
| `:TRIGger:SPI:SLEVel` | `:TRIGger:SPI:SLEVel <level>` | `:TRIGger:SPI:SLEVel?` | Sets or queries the trigger level of the CS channel of SPI trigger. The unit is the same as that of the current amplitude. | 2-229 |
| `:TRIGger:SPI:SLOPe` | `:TRIGger:SPI:SLOPe <slope>` | `:TRIGger:SPI:SLOPe?` | Sets or queries the type of the clock edge of SPI trigger. | 2-228 |
| `:TRIGger:SPI:TIMeout` | `:TRIGger:SPI:TIMeout <time>` | `:TRIGger:SPI:TIMeout?` | Sets or queries the timeout value when the trigger condition of SPI trigger is "Timeout". The default unit is s. | 2-228 |
| `:TRIGger:SPI:WHEN` | `:TRIGger:SPI:WHEN <when>` | `:TRIGger:SPI:WHEN?` | Sets or queries the trigger condition of SPI trigger. | 2-227 |
| `:TRIGger:SPI:WIDTh` | `:TRIGger:SPI:WIDTh <width>` | `:TRIGger:SPI:WIDTh?` | Sets or queries the data width of data channel in SPI trigger. | 2-227 |
| `:TRIGger:STATus` | — | `:TRIGger:STATus?` | Queries the current trigger status. | 2-179 |
| `:TRIGger:SWEep` | `:TRIGger:SWEep <sweep>` | `:TRIGger:SWEep?` | Sets or queries the trigger mode. | 2-180 |
| `:TRIGger:TIMeout:LEVel` | `:TRIGger:TIMeout:LEVel <level>` | `:TRIGger:TIMeout:LEVel?` | Sets or queries the trigger level of Timeout trigger. The unit is the same as that of the current amplitude. | 2-199 |
| `:TRIGger:TIMeout:SLOPe` | `:TRIGger:TIMeout:SLOPe <slope>` | `:TRIGger:TIMeout:SLOPe?` | Sets or queries the edge type of Timeout trigger. | 2-198 |
| `:TRIGger:TIMeout:SOURce` | `:TRIGger:TIMeout:SOURce <source>` | `:TRIGger:TIMeout:SOURce?` | Sets or queries the trigger source of Timeout trigger. | 2-198 |
| `:TRIGger:TIMeout:TIME` | `:TRIGger:TIMeout:TIME <time>` | `:TRIGger:TIMeout:TIME?` | Sets or queries the timeout value of Timeout trigger. The default unit is s. | 2-198 |
| `:TRIGger:VIDeo:LEVel` | `:TRIGger:VIDeo:LEVel <level>` | `:TRIGger:VIDeo:LEVel?` | Sets or queries the trigger level of Video trigger. The unit is the same as that of the current amplitude. | 2-191 |
| `:TRIGger:VIDeo:LINE` | `:TRIGger:VIDeo:LINE <line>` | `:TRIGger:VIDeo:LINE?` | Sets or queries the line number when the sync type of Video trigger to Line. | 2-190 |
| `:TRIGger:VIDeo:MODE` | `:TRIGger:VIDeo:MODE <mode>` | `:TRIGger:VIDeo:MODE?` | Sets or queries the sync type of Video trigger. | 2-190 |
| `:TRIGger:VIDeo:POLarity` | `:TRIGger:VIDeo:POLarity <polarity>` | `:TRIGger:VIDeo:POLarity?` | Sets or queries the video polarity of Video trigger. | 2-189 |
| `:TRIGger:VIDeo:SOURce` | `:TRIGger:VIDeo:SOURce <channel>` | `:TRIGger:VIDeo:SOURce?` | Sets or queries the trigger source of Video trigger. | 2-189 |
| `:TRIGger:VIDeo:STANdard` | `:TRIGger:VIDeo:STANdard <standard>` | `:TRIGger:VIDeo:STANdard?` | Sets or queries the video standard of Video trigger. | 2-191 |
| `:TRIGger:WINDows:ALEVel` | `:TRIGger:WINDows:ALEVel <level>` | `:TRIGger:WINDows:ALEVel?` | Sets or queries the upper limit of the trigger level of Window trigger. The unit is the same as that of the current amplitude. | 2-204 |
| `:TRIGger:WINDows:BLEVel` | `:TRIGger:WINDows:BLEVel <level>` | `:TRIGger:WINDows:BLEVel?` | Sets or queries the lower limit of the trigger level of Window trigger. The unit is the same as that of the current amplitude. | 2-205 |
| `:TRIGger:WINDows:POSition` | `:TRIGger:WINDows:POSition <pos>` | `:TRIGger:WINDows:POSition?` | Sets or queries the trigger position of Window trigger. | 2-204 |
| `:TRIGger:WINDows:SLOPe` | `:TRIGger:WINDows:SLOPe <type>` | `:TRIGger:WINDows:SLOPe?` | Sets or queries the window type of Window trigger. | 2-203 |
| `:TRIGger:WINDows:SOURce` | `:TRIGger:WINDows:SOURce <source>` | `:TRIGger:WINDows:SOURce?` | Sets or queries the trigger source of Window trigger. | 2-203 |
| `:TRIGger:WINDows:TIME` | `:TRIGger:WINDows:TIME <time>` | `:TRIGger:WINDows:TIME?` | Sets or queries the window time of Window trigger. | 2-204 |

### ultralab

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:ULTRalab:SERVer` | `:ULTRalab:SERVer <string>` | `:ULTRalab:SERVer?` | Sets or queries the IP address of the server. | 2-242 |

### waveform

| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |
|---|---|---|---|---|
| `:WAVeform:CHANsend` | `:WAVeform:CHANsend <chan>` | `:WAVeform:CHANsend?` | Sets or queries the channel No. to be reported automatically. | 2-250 |
| `:WAVeform:DATA` | — | `:WAVeform:DATA?` | Reads the waveform data. | 2-246 |
| `:WAVeform:FORMat` | `:WAVeform:FORMat <format>` | `:WAVeform:FORMat?` | Sets or queries the return format of the waveform data. | 2-245 |
| `:WAVeform:MODE` | `:WAVeform:MODE <mode>` | `:WAVeform:MODE?` | Sets or queries the mode of the :WAVeform:DATA? command in reading data. | 2-244 |
| `:WAVeform:POINts` | `:WAVeform:POINts <point>` | `:WAVeform:POINts?` | Sets or queries the number of the waveform points to be read. | 2-245 |
| `:WAVeform:PREamble` | — | `:WAVeform:PREamble?` | Queries all the waveform parameters. | 2-249 |
| `:WAVeform:SOURce` | `:WAVeform:SOURce <source>` | `:WAVeform:SOURce?` | Sets or queries the source channel of waveform data reading. | 2-244 |
| `:WAVeform:STARt` | `:WAVeform:STARt <sta>` | `:WAVeform:STARt?` | Sets or queries the start position of waveform data reading. | 2-248 |
| `:WAVeform:STOP` | `:WAVeform:STOP <stop>` | `:WAVeform:STOP?` | Sets or queries the stop position of waveform data reading. | 2-248 |
| `:WAVeform:TIME` | — | `:WAVeform:TIME?` | Queries the time stamp of the current external trigger. | 2-249 |
| `:WAVeform:XINCrement` | — | `:WAVeform:XINCrement?` | Queries the time interval between two neighboring points of the currently selected channel source in the X direction. | 2-246 |
| `:WAVeform:XORigin` | — | `:WAVeform:XORigin?` | Queries the start time of the waveform data of the currently selected channel source in the X direction. | 2-247 |
| `:WAVeform:XREFerence` | — | `:WAVeform:XREFerence?` | Queries the reference time of the waveform points of the currently selected channel source in the X direction. | 2-247 |
| `:WAVeform:YINCrement` | — | `:WAVeform:YINCrement?` | Queries the unit voltage of the current channel in the Y axis. Its unit is the same as that of the current amplitude. | 2-247 |
| `:WAVeform:YORigin` | — | `:WAVeform:YORigin?` | Queries the vertical offset relative to the vertical reference position of the currently selected channel source in the Y direction. | 2-247 |
| `:WAVeform:YREFerence` | — | `:WAVeform:YREFerence?` | Queries the vertical reference position of the currently selected channel source in the Y direction. | 2-248 |

## 9. Troubleshooting and boundaries

**Cannot find the module (`ModuleNotFoundError`):** You may have installed the package into a different Python environment. Run `python -m pip show rigol-ds8000r-jeff` and `python -c "import rigol_ds8000r; print(rigol_ds8000r.__version__)"` with the *same* interpreter that executes your test scripts.

**No VISA resources found:** Confirm Rigol LAN/USB mode, firewall settings, cabling, VISA installation, and the selected resource identifier. A `TCPIP0::address::INSTR` session generally requires the appropriate VXI-11 resource service. A socket resource is not interchangeable and usually requires device-specific termination and port selection.

**VISA timeout on `:WAVeform:DATA?` or `:DISPlay:DATA?`:** Increase `timeout` in milliseconds, first capture only 1000 points, and verify that the scope has completed acquisition. RAW memory capture requires the scope to be stopped. Querying binary data as plain ASCII is incorrect; use `query_block()` or `waveform()`.

**Instrument returns an empty reply or an SCPI error:** Verify whether the command is query-only, requires arguments, is conditional on a selected mode, or is an optional licensed feature. Run `scope.errors()` and check the page shown in the command catalog. Some firmware versions differ from the November 2020 guide.

**Waveform amplitude inaccurate:** Set channel probe ratio and impedance to match the actual physical probe. Confirm offset and volts/div, trigger and sampling mode, and avoid clipping or undersampling. Compare `:WAVeform:PREamble?` against `scope.waveform(...).preamble`.

**A command changes a system under test:** Use the default read-only test sweep. The test runner intentionally doesn't send all 1,014 forms automatically: many commands reset/capture/file-export/change operating modes or depend on absent options. Instrument safety and connected equipment take priority. Restoring readback settings is best-effort, not transactional hardware rollback.

**Exception types:** `ConnectionError`, `NotConnectedError`, `CommandError`, `ProtocolError`, `ValidationError`. They inherit from `RigolError`. Catching `RigolError` handles most driver-side validation/protocol faults; low-level VISA errors can be caught separately if required.

## 10. Package map

```text
rigol_ds8000r_pkg/
├── README.md                      # Installation, examples, all command syntaxes
├── LICENSE                        # MIT, copyright Jeff Michaelis
├── pyproject.toml                 # Python packaging metadata and CLI entrypoint
├── src/rigol_ds8000r/
│   ├── __init__.py
│   ├── driver.py                   # Reusable PyVISA driver and waveform conversion
│   ├── exceptions.py               # Driver and SCPI exceptions
│   ├── catalog.py                  # Catalog lookup helpers
│   ├── command_catalog.json        # Complete manual syntax inventory
│   ├── verification.py             # Command-by-command test CLI
│   └── simulator.py                # Offline SCPI test double
├── tests/test_driver.py            # Automated software tests
├── rigol_ds8000r_test.py         # Standalone command-line launch file
├── examples/quick_start.py
├── examples/raw_catalog.py
├── tools/generate_readme.py        # Regenerate command appendix from JSON
└── tools/extract_catalog.py       # Regenerate catalog from a guide PDF (PyMuPDF)
```

**Author attribution:** Jeff Michaelis is identified as the creator throughout the source files and package metadata.

**License:** MIT for the authored Python package. The Rigol user-supplied programming guide is a separate manufacturer publication and is not included in this distribution.
