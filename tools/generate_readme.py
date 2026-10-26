"""Regenerate the comprehensive README SCPI appendix from command_catalog.json."""
# Creator: Jeff Michaelis
import json
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
records=json.loads((ROOT/'src'/'rigol_ds8000r'/'command_catalog.json').read_text(encoding='utf-8'))
paths=defaultdict(list)
for record in records:paths[record['name']].append(record)
subsystems=defaultdict(list)
for name, variants in paths.items():
    key=name.replace('[','').replace(']','').lstrip(':').split(':',1)[0].replace('<n>','')
    if key.startswith('*'):key='IEEE 488.2 common commands'
    elif key.upper().startswith('SOURCE'):key='SOURce / arbitrary waveform generator'
    elif key.upper().startswith('TRACE'):key='TRACe / DAC output'
    else:key=key.lower()
    subsystems[key].append((name,variants))

manual_intro=r'''# Rigol-DS8000-R Python Driver and Test Suite

**Creator:** __CREATOR_CREDIT__  
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
py -3.8 -m pip show Rigol-DS8000-R
```

If `py -3.8` is unavailable, use the correct installed `python.exe` directly. A Python 3.8-compatible virtual environment is optional; it does not need to be created on a NAS or a mapped network drive.

To install a **wheel file** from the included `dist` directory (if one was built):

```powershell
python -m pip install dist/rigol_ds8000_r-1.0.0-py3-none-any.whl
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
| `--error-tests` | Send invalid `:UNSUPPORTED:INVALID:COMMAND`, require nonzero SCPI error, then clear status |
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

'''
lines=[manual_intro]
for group in sorted(subsystems,key=lambda x:(x!='IEEE 488.2 common commands',x)):
    items=sorted(subsystems[group], key=lambda kv:kv[0].upper())
    lines.append('### '+group+'\n\n')
    lines.append('| SCPI command path | Set / action syntax | Query syntax | Description | Guide page |\n')
    lines.append('|---|---|---|---|---|\n')
    for name,variants in items:
        sets=[r['syntax'] for r in variants if not r['query']]
        gets=[r['syntax'] for r in variants if r['query']]
        desc=next((r['description'] for r in variants if r['description']), '')
        if not desc: desc='Refer to the programming guide for behavior and prerequisites.'
        desc=' '.join(desc.split())
        if len(desc)>200:desc=desc[:197].rsplit(' ',1)[0]+'…'
        desc=desc.replace('|','\\|').replace('`','\\`')
        # Standard Markdown does not support br tags on every renderer; a given
        # path normally has exactly one set and one query form, but when it
        # doesn't, join with line-break symbols inside the cell.
        def cell(arr):
            return ' / '.join('`'+v.replace('|','\\|')+'`' for v in arr) if arr else '—'
        pages=','.join(sorted(set(x['page'] for x in variants)))
        lines.append('| `'+name.replace('|','\\|')+'` | '+cell(sets)+' | '+cell(gets)+' | '+desc+' | '+pages+' |\n')
    lines.append('\n')
lines.append('''## 9. Troubleshooting and boundaries

**Cannot find the module (`ModuleNotFoundError`):** You may have installed the package into a different Python environment. Run `python -m pip show Rigol-DS8000-R` and `python -c "import rigol_ds8000r; print(rigol_ds8000r.__version__)"` with the *same* interpreter that executes your test scripts.

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
├── LICENSE                        # MIT license
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

**Creator:** __CREATOR_CREDIT__. Attribution is retained in source-code comments and this README; installable distribution metadata uses the project name only.

**License:** MIT for the authored Python package. The Rigol user-supplied programming guide is a separate manufacturer publication and is not included in this distribution.
''')
out=ROOT/'README.md'
# Read attribution from this file's source comment. Keeping the creator's
# name out of generated file metadata and runtime strings avoids branding the
# installable Python distribution with a personal name.
creator_comment = next((line for line in Path(__file__).read_text(encoding='utf-8').splitlines()
                        if line.startswith('# Creator: ')), '')
if not creator_comment:
    raise RuntimeError('Missing creator attribution comment')
creator_credit = creator_comment.partition(': ')[2]
out.write_text(''.join(lines).replace('__CREATOR_CREDIT__', creator_credit), encoding='utf-8')
print('Created',out,'bytes',out.stat().st_size,'groups',len(subsystems),'paths',len(paths),'forms',len(records))
