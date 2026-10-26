"""Static and simulated instrument tests."""
# Creator: Jeff Michaelis
import csv
import json
from pathlib import Path

import pytest

from rigol_ds8000r import RigolDS8000R, ValidationError, catalog
from rigol_ds8000r.driver import WaveformPreamble
from rigol_ds8000r.simulator import SimulatedDS8000R
from rigol_ds8000r.verification import TestLog, run_smoke, run_error_tests, main, classification


def test_full_manual_inventory():
    # A coarse guard against shipping a truncated guide inventory.
    rows = catalog.entries()
    assert len(rows) >= 1000
    assert any(x["syntax"] == ":WAVeform:PREamble?" for x in rows)
    assert any(x["syntax"] == ":BUS<n>:SPI:SCLK:SLOPe?" for x in rows)
    assert any(x["syntax"] == ":CHANnel<n>:BWLimit <type>" for x in rows)
    assert all("page" in row and "description" in row for row in rows)
    assert catalog.find(":CHANnel<n>:SCALe")


def test_scpi_connection_and_validation():
    fake = SimulatedDS8000R()
    scope = RigolDS8000R(instrument=fake).connect()
    assert "DS8034-R" in scope.idn
    assert scope.channel(1).scale() == pytest.approx(.5)
    scope.channel(1).scale(.2)
    assert scope.channel(1).scale() == pytest.approx(.2)
    assert scope.channel(1).coupling() == "DC"
    scope.channel(1).enable(True)
    assert scope.channel(1).is_enabled()
    assert scope.sample_rate() == pytest.approx(2.5e9)
    with pytest.raises(ValidationError): scope.channel(5)
    with pytest.raises(ValidationError): scope.channel(True)
    with pytest.raises(ValidationError): scope.channel(1).scale(float("nan"))
    with pytest.raises(ValidationError): scope.channel(1).probe(3)
    with pytest.raises(ValidationError): scope.acquisition_averages(3)
    with pytest.raises(ValidationError): scope.write("*IDN?\n*RST")
    with pytest.raises(ValidationError): scope.channel(1).bandwidth_limit("500M")
    assert scope.errors() == []
    scope.close()
    # Closing borrowed resources must not dispose of the injected object.
    assert not fake.closed


def test_waveform_binary_and_csv(tmp_path):
    with RigolDS8000R(instrument=SimulatedDS8000R()) as scope:
        waveform = scope.waveform(channel=1, points=1000)
        assert len(waveform.voltages) == 1000
        assert waveform.voltages[0] == pytest.approx(0)
        assert waveform.voltages[10] == pytest.approx(.28)
        assert waveform.times()[1] - waveform.times()[0] == pytest.approx(1e-6)
        out = tmp_path / "wave.csv"
        waveform.csv(str(out))
        rows = list(csv.reader(out.open(encoding="utf-8")))
        assert rows[0] == ["Time (s)", "Voltage (V)"]
        assert len(rows) == 1001
        assert scope.query(":WAVeform:FORMat?") == "BYTE"
        with pytest.raises(ValidationError): scope.waveform(points=2000)


def test_template_commands():
    with RigolDS8000R(instrument=SimulatedDS8000R()) as scope:
        assert scope.commands.render(":CHANnel<n>:SCALe", n=3) == ":CHANnel3:SCALe"
        assert scope.commands.render("[:SOURce[<n>]]:FUNCtion[:SHAPe]", n=1) == ":SOURce1:FUNCtion:SHAPe"
        assert float(scope.commands.get(":CHANnel<n>:SCALe", n=1)) == pytest.approx(.5)
        with pytest.raises(ValidationError): scope.commands.get(":CHANnel<n>:SCALe")
        with pytest.raises(ValidationError): scope.commands.render(":CHANnel<n>:SCALe", n=5)


def test_preamble_parse():
    p = WaveformPreamble.parse("0,0,1000,1,1e-6,-.0005,0,.01,0,128")
    assert p.points==1000 and p.y_reference == 128
    with pytest.raises(Exception): WaveformPreamble.parse("invalid")


def test_offline_smoke_and_scpi_error_reporting(tmp_path):
    scope=RigolDS8000R(instrument=SimulatedDS8000R()).connect()
    log=TestLog()
    run_smoke(scope,log)
    run_error_tests(scope,log)
    assert log.summary()["FAIL"] == 0
    assert log.summary()["PASS"] >= 9
    name=tmp_path/"report.json"
    log.export(name)
    data=json.loads(name.read_text())
    assert data["package"]=="Rigol-DS8000-R"
    assert len(data["results"]) >= 9


def test_cli_modes(tmp_path):
    filename=tmp_path/"out.csv"
    assert main(["--mode","inventory","--report",str(filename)]) == 0
    assert sum(1 for _ in filename.open()) > 1000
    assert main(["--simulate","--mode","smoke","--error-tests",
                 "--report",str(tmp_path/"smoke.json")]) == 0


def test_risk_flags():
    assert classification(":LAN:IPADdress?")[1]
    assert classification(":SYSTem:OPTion:INSTall")[1]
    assert classification(":TRIGger:SPI:SOURce")[0]
    assert classification(":BUS1:SPI:MODE")[0]
    assert classification(":WAVeform:DATA?")[2]
