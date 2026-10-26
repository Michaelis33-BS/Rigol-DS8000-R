"""Instrument-wide SCPI acceptance and read-back verification runner.


This is a hardware acceptance tool, not an assertion that all options exist.
It records every form from the bundled command catalogue and explicitly
classifies unsupported, parameterized, optional, and risky operations.
"""
# Creator: Jeff Michaelis
import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import catalog
from .driver import RigolDS8000R, _channel
from .exceptions import ProtocolError


# Subsystems requiring separately purchased/installed options on some models.
OPTIONAL_PREFIXES = (":EYE", ":JITTER", ":SFP", ":POWER", ":BUS1:RS232", ":BUS1:SPI",
                     ":BUS1:IIC", ":BUS1:IIS", ":BUS1:CAN", ":BUS1:FLEX",
                     ":BUS1:M1553", ":BUS1:LIN", ":SOUR", ":TRIGGER:RS232",
                     ":TRIGGER:IIC", ":TRIGGER:SPI", ":TRIGGER:CAN", ":TRIGGER:FLEX",
                     ":TRIGGER:IIS", ":TRIGGER:LIN", ":TRIGGER:M1553")
# Changing network/remote-management, calibration, licensing, file/state storage,
# and active waveform output is not suited to unattended command sweeping.
RISKY_TOKENS = (":LAN:", ":SYSTEM:DATE", ":SYSTEM:TIME", ":SYSTEM:OPTION",
                ":SYSTEM:RCLOCK", ":SYSTEM:PWDCLEAR", ":SYSTEM:RESET", ":SYSTEM:SETUP",
                ":SYSTEM:PON", ":SYSTEM:AUTCLEAR", ":SYSTEM:RAMOUNT", ":SYSTEM:GAMOUNT",
                ":SFP:", ":SOURCE", ":LOAD:", ":SAVE:", ":REFERENCE:RESET",
                ":REFERENCE:SAVE", ":CHANNEL1:CSTART", ":CHANNEL2:CSTART", ":CHANNEL3:CSTART",
                ":CHANNEL4:CSTART", ":TRACE", ":ULTRALAB:", ":QUICK:", ":WAVEFORM:CHANSEND")
BINARY_DATA = (":WAV:DATA", ":DISP:DATA", ":BUS1:DATA", ":BUS2:DATA",
               ":BUS3:DATA", ":BUS4:DATA", ":SYST:SETU")
# A modest selection of API-level checks which will not reset the instrument.
BASE_QUERY_TESTS = ["*IDN?", "*OPC?", ":ACQuire:TYPE?", ":ACQuire:SRATe?",
                    ":TIMebase:MAIN:SCALe?", ":TRIGger:MODE?", ":TRIGger:STATus?"]


def canonical(name):
    """Convert guide-style SCPI keyword abbreviations to a uniform match key."""
    return str(name).upper().replace("[", "").replace("]", "")


def classification(name):
    """Return decision markers for optional or high-impact commands."""
    upper = canonical(name)
    optional = any(upper.startswith(p) for p in OPTIONAL_PREFIXES)
    # Match both long-form and abbreviated spellings, because the source uses
    # full forms while commands on the wire can be abbreviated.
    risky = (any(upper.startswith(p) for p in RISKY_TOKENS) or
             upper.startswith(("*RST", "*RCL", "*SAV", "*ESR", "*STB", "*TST", ":AUTOSCALE", ":CLE", ":SING", ":TFOR")) or
             ("CALIB" in upper) or ("UNINSTALL" in upper) or ("INSTALL" in upper))
    binary = (":DATA" in upper and (upper.startswith(":WAVEFORM") or
              upper.startswith(":DISPLAY") or upper.startswith(":BUS")) or
              upper.startswith(":SYSTEM:SETUP"))
    return optional, risky, binary


def command_wire(syntax, n=1):
    """Produce an actual wire command from a manual syntax form."""
    cmd = syntax.split(" ", 1)[0]
    cmd = cmd.replace("<n>", str(_channel(n))).replace("[", "").replace("]", "")
    # Some patterns include <...> in the path itself, not just parameters.
    if "<" in cmd:
        raise ValueError("Unresolved path index")
    return cmd


class TestLog:
    __test__ = False  # Pytest should not treat this result logger as a test class.
    """Streaming test results; every catalogue command produces a record."""
    def __init__(self):
        self.records = []

    def add(self, name, status, detail="", command="", elapsed=0.0, page=""):
        r = {"name": name, "status": status, "detail": str(detail),
             "command": command, "elapsed_s": round(elapsed, 4), "manual_page": page}
        self.records.append(r)
        print("[{:<4}] {}{}".format(status, name,
              " - " + str(detail)[:150] if detail else ""), flush=True)

    def export(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".csv":
            with path.open("w", newline="", encoding="utf-8") as fp:
                writer = csv.DictWriter(fp, fieldnames=["name", "status", "detail", "command", "elapsed_s", "manual_page"])
                writer.writeheader()
                writer.writerows(self.records)
        else:
            with path.open("w", encoding="utf-8") as fp:
                json.dump({"package": "Rigol-DS8000-R", "created_utc": datetime.now(timezone.utc).isoformat(),
                           "summary": self.summary(), "results": self.records}, fp, indent=2)

    def summary(self):
        return {s: sum(1 for r in self.records if r["status"] == s)
                for s in ("PASS", "FAIL", "SKIP")}


def _drain(scope):
    """Retrieve fresh SCPI errors without converting option absence to a PASS."""
    try:
        return scope.errors(max_errors=12)
    except Exception as exc:
        return ["Cannot read error queue: {}".format(exc)]


def run_smoke(scope, log):
    """Small set of high-value, read-only checks; plus reversible readback."""
    for command in BASE_QUERY_TESTS:
        start = time.monotonic()
        try:
            result = scope.query(command)
            if not result:
                raise ProtocolError("Empty response")
            errors = _drain(scope)
            if errors: raise ProtocolError("; ".join(errors))
            log.add(command, "PASS", result[:100], command, time.monotonic()-start)
        except Exception as exc:
            log.add(command, "FAIL", repr(exc), command, time.monotonic()-start)
    # The following setting is restored inside finally to be safe even after an
    # instrument IO error. It uses a known innocuous channel setting.
    name = ":CHANnel1:DISPlay"
    try:
        old = scope.query(name + "?")
        scope.write(name + " " + old)
        new = scope.query(name + "?")
        err = _drain(scope)
        assert new == old and not err, "readback mismatch {} vs {} errors={}".format(old, new, err)
        log.add(name + " write/readback", "PASS", "same value re-applied")
    except Exception as exc:
        log.add(name + " write/readback", "FAIL", repr(exc))
    finally:
        if "old" in locals():
            try: scope.write(name + " " + old)
            except Exception: pass


def sweep(scope, log, mode, include_optional=False, include_data=False,
          allow_risky=False, all_indices=False, max_queries=None):
    """Visit every documented syntax, safely exercising what is eligible.

    `query`: sends parameterless read commands to the instrument.
    `exercise`: queries each parameterless read and re-applies original setting
                for set/query pairs with ONE single, simple parameter.
    `full`: additionally runs a few stateless actions (never resets, writes
            files, or modifies network interfaces). Complex dependent forms are
            still recorded as SKIP with the reason.
    """
    # Save the initial RUN/STOP state before the full-mode action sweep.
    # Every command still gets a result record even when this query fails.
    initial_running = None
    if mode == "full":
        try:
            initial_running = scope.trigger_state().upper() != "STOP"
        except Exception:
            pass
    docs = catalog.entries()
    pairs = {}
    for e in docs:
        pairs.setdefault(e["name"].upper(), {})["query" if e["query"] else "set"] = e
    count = 0
    for row in docs:
        vals = range(1, 5) if all_indices and "<n>" in row["name"] else (1,)
        for n in vals:
            label = row["syntax"] + (" [n={}]".format(n) if "<n>" in row["name"] else "")
            try:
                cmd = command_wire(row["syntax"], n=n)
            except (ValueError, TypeError) as exc:
                log.add(label, "SKIP", "cannot render path: {}".format(exc), page=row["page"])
                continue
            optional, risky, binary = classification(cmd)
            if optional and not include_optional:
                log.add(label, "SKIP", "optional feature: --include-optional", cmd, page=row["page"])
                continue
            if binary and not include_data:
                log.add(label, "SKIP", "binary/large response: --include-data", cmd, page=row["page"])
                continue
            if risky and not allow_risky:
                log.add(label, "SKIP", "stateful or hazardous operation: --allow-risky", cmd, page=row["page"])
                continue
            if max_queries is not None and count >= max_queries:
                log.add(label, "SKIP", "limit --max-queries reached", cmd, page=row["page"])
                continue
            begin = time.monotonic()
            try:
                if row["query"]:
                    # Queries with query arguments (e.g., :MEAS:ITEM? VPP,CH1)
                    # are not safe to invent; flag them explicitly.
                    after = row["syntax"].split("?", 1)[1].strip()
                    if after:
                        log.add(label, "SKIP", "query requires parameters: {}".format(after), cmd, page=row["page"])
                        continue
                    if binary:
                        answer = scope.query_block(cmd)
                        detail = "{} bytes/samples".format(len(answer))
                    else:
                        answer = scope.query(cmd)
                        if not answer:
                            raise ProtocolError("Empty query response")
                        detail = answer[:90]
                    error = _drain(scope)
                    if error:
                        raise ProtocolError("Instrument SCPI errors: " + "; ".join(error))
                    log.add(label, "PASS", detail, cmd, time.monotonic()-begin, row["page"])
                    count += 1
                else:
                    pair = pairs[row["name"].upper()]
                    query = pair.get("query")
                    # Full mode sends stateless core actions only; resets and
                    # other dangerous commands are never exercised automatically.
                    if "<" not in row["syntax"] and mode == "full" and canonical(cmd) in (":RUN", ":STOP"):
                        scope.write(cmd)
                        error = _drain(scope)
                        if error: raise ProtocolError("; ".join(error))
                        log.add(label, "PASS", "action executed", cmd, time.monotonic()-begin, row["page"])
                        count += 1
                    elif mode in ("exercise", "full") and query and query["syntax"].split("?",1)[-1].strip()=="" and re.match(r'^\S+\s+<[^<>]+>$',row["syntax"]):
                        # Only a one-parameter set/query pair can be verified
                        # generically. Read the CURRENT value, re-apply it,
                        # verify, and restore in finally; never guess setpoints.
                        original = scope.query(cmd+"?")
                        if not original or any(c in original for c in ("\r", "\n", ";")):
                            raise ProtocolError("Cannot safely use returned value for set/readback")
                        try:
                            scope.write(cmd+" "+original)
                            actual = scope.query(cmd+"?")
                            errors = _drain(scope)
                            def norm(s):
                                try: return float(s)
                                except (ValueError, TypeError): return str(s).strip().upper()
                            if errors or norm(original)!=norm(actual):
                                raise ProtocolError("readback original={} actual={} errors={}".format(original,actual,errors))
                            log.add(label, "PASS", "set/current readback {}".format(actual[:80]), cmd,
                                    time.monotonic()-begin, row["page"])
                            count += 1
                        finally:
                            try: scope.write(cmd+" "+original)
                            except Exception: pass
                    else:
                        log.add(label, "SKIP", "action, multi-parameter, or no query for safe readback", cmd,
                                page=row["page"])
            except Exception as exc:
                # Hardware errors are real failures rather than defaulting to a
                # successful command just because VISA returned control.
                error = _drain(scope)
                details = repr(exc) + (" | SCPI: " + "; ".join(error) if error else "")
                log.add(label, "FAIL", details, cmd, time.monotonic()-begin, row["page"])
    if initial_running is not None:
        try:
            # RUN/STOP is not a perfect snapshot of a single-shot acquisition;
            # only attempt to restore the original continuous run state.
            scope.run() if initial_running else scope.stop()
        except Exception as exc:
            log.add("restore RUN/STOP state", "FAIL", repr(exc))


def run_error_tests(scope, log):
    """Test SCPI error reporting with one known-invalid command header.

    Clears stale errors first, injects a deliberately invalid header, then
    verifies that :SYSTem:ERRor? returns a nonzero code and drains the queue.
    """
    try:
        scope.clear_status()
        scope.write(":UNSUPPORTED:INVALID:COMMAND")
        errors = scope.errors()
        if errors and not any(re.match(r'^\+?0,',x) for x in errors):
            log.add("SCPI negative command", "PASS", "; ".join(errors))
        else:
            log.add("SCPI negative command", "FAIL", "No nonzero error for invalid command")
    except Exception as exc:
        log.add("SCPI negative command", "FAIL", repr(exc))
    finally:
        try: scope.clear_status()
        except Exception: pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="Rigol-DS8000-R complete SCPI inventory/test CLI")
    parser.add_argument("--resource", help="VISA resource string, such as TCPIP0::192.168.1.50::INSTR")
    parser.add_argument("--backend", help="VISA backend, e.g. @py")
    parser.add_argument("--simulate", action="store_true", help="Run the included fake instrument offline")
    parser.add_argument("--mode", choices=("inventory", "smoke", "query", "exercise", "full"), default="smoke")
    parser.add_argument("--include-optional", action="store_true", help="Attempt licensed-option commands")
    parser.add_argument("--include-data", action="store_true", help="Attempt binary/large data queries")
    parser.add_argument("--allow-risky", action="store_true", help="Allow sensitive-state queries and reversible setters")
    parser.add_argument("--all-indices", action="store_true", help="Test <n> family for n=1..4, not just n=1")
    parser.add_argument("--error-tests", action="store_true", help="Run a controlled invalid-command/error-queue check")
    parser.add_argument("--max-queries", type=int, help="Optional cap on actual instrument transactions")
    parser.add_argument("--timeout", type=int, default=10000, help="VISA timeout in ms")
    parser.add_argument("--report", default="rigol_test_results.json", help="Output path ending .json or .csv")
    parser.add_argument("--yes", action="store_true", help="Confirm that state-changing sweep is intended")
    a = parser.parse_args(argv)
    log = TestLog()
    if a.mode == "inventory":
        for r in catalog.entries():
            log.add(r["syntax"], "SKIP", "catalog entry; no instrument contacted", page=r["page"])
    else:
        if not a.simulate and not a.resource:
            parser.error("--resource is required unless --simulate or --mode inventory")
        if (a.mode in ("exercise", "full") or a.allow_risky) and not a.yes and not a.simulate:
            parser.error("Settings could change; pass --yes after verifying the DUT is safe")
        if a.simulate:
            from .simulator import SimulatedDS8000R
            scope = RigolDS8000R(instrument=SimulatedDS8000R(),timeout=a.timeout)
        else:
            scope = RigolDS8000R(a.resource, timeout=a.timeout, backend=a.backend)
        try:
            scope.connect()
            print("Instrument:", scope.idn, flush=True)
            if a.mode == "smoke":
                run_smoke(scope, log)
            else:
                sweep(scope,log,a.mode,a.include_optional,a.include_data,a.allow_risky,
                      a.all_indices,a.max_queries)
            if a.error_tests:
                run_error_tests(scope,log)
        finally:
            scope.close()
    log.export(a.report)
    print("\nSummary: {} ({} records)".format(log.summary(), len(log.records)))
    print("Report:", a.report)
    return 1 if log.summary()["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
