import json
import subprocess

import pytest

from energy.windows import WindowsBatteryReader, parse_report
from scripts.qualify_battery import summarize


def report(**changes):
    return {
        "observed_utc": "2026-10-28T02:00:00Z",
        "remaining_mwh": 30_000,
        "full_mwh": 38_646,
        "charge_rate_mw": -40_000,
        "status": "Discharging",
        "power_supply_status": "NotPresent",
        **changes,
    }


def test_native_units_state_and_raw_sign_are_preserved():
    reading = parse_report(report(), 10.0, 10.5)
    assert reading.remaining_mwh == 30_000
    assert reading.energy_j == 108_000
    assert reading.charge_rate_mw == -40_000 and reading.discharge_power_w == 40.0
    assert reading.on_battery and reading.ac_online is False
    assert reading.started_s == 10.0 and reading.available_s == 10.5


@pytest.mark.parametrize(
    "changes",
    [
        {"remaining_mwh": None},
        {"remaining_mwh": True},
        {"remaining_mwh": "90%"},
        {"remaining_mwh": -1},
        {"remaining_mwh": 0xFFFFFFFF},
        {"full_mwh": None},
        {"full_mwh": 0},
        {"remaining_mwh": 40_000},
    ],
)
def test_missing_or_invalid_capacity_cannot_qualify(changes):
    reading = parse_report(report(**changes), 0, 1)
    assert not reading.valid and not reading.on_battery
    assert reading.error
    if reading.remaining_mwh is None:
        assert reading.energy_j is None


@pytest.mark.parametrize("rate", [None, True, "unknown", -0x80000000, 0xFFFFFFFF])
def test_unknown_rate_stays_missing_without_losing_capacity(rate):
    reading = parse_report(report(charge_rate_mw=rate), 0, 1)
    assert reading.valid
    assert reading.discharge_power_w is None and reading.charge_rate_mw is None


@pytest.mark.parametrize(
    "supply,status",
    [
        ("Adequate", "Charging"),
        ("Inadequate", "Discharging"),
        ("unknown", "Discharging"),
        ("NotPresent", "Idle"),
        (["NotPresent"], "Discharging"),
    ],
)
def test_discharge_alone_does_not_establish_unplugged_state(supply, status):
    reading = parse_report(report(power_supply_status=supply, status=status), 0, 1)
    assert not reading.on_battery


def test_reader_reports_errors_without_retries_or_zero_values(monkeypatch):
    calls = []

    def failed(*args, **kwargs):
        calls.append(args)
        raise subprocess.TimeoutExpired("powershell.exe", 1)

    monkeypatch.setattr("energy.windows.subprocess.run", failed)
    reading = WindowsBatteryReader(executable="fake-powershell").read()
    assert len(calls) == 1 and not reading.valid
    assert reading.remaining_mwh is None and reading.energy_j is None
    assert reading.error == "TimeoutExpired"


def test_reader_parses_one_native_report_and_records_query_window(monkeypatch):
    ticks = iter([1.0, 1.7])

    def run(command, **kwargs):
        assert "-NoProfile" in command and "-NonInteractive" in command
        assert "-ExecutionPolicy" not in command
        assert kwargs["timeout"] == 15
        return subprocess.CompletedProcess(command, 0, json.dumps(report()), "")

    monkeypatch.setattr("energy.windows.subprocess.run", run)
    reading = WindowsBatteryReader(executable="fake-powershell", clock=lambda: next(ticks)).read()
    assert reading.on_battery and reading.available_s - reading.started_s == pytest.approx(0.7)


def test_qualification_requires_updating_energy_and_unplugged_samples():
    rows = [
        {
            "phase": phase,
            "windows": parse_report(
                report(remaining_mwh=30_000 - index * 100),
                index * 10,
                index * 10 + 0.5,
            ).to_dict(),
        }
        for index, phase in enumerate(["idle", "idle", "cpu_load", "recovery"])
    ]
    result = summarize(rows)
    assert result["decision"] == "go"
    assert result["energy_drop_wh"] == 0.3
    assert result["raw_energy_unit"] == "mWh"
    rows[2]["windows"]["ac_online"] = True
    result = summarize(rows)
    assert result["decision"] == "no_go" and result["qualified_source"] is None
    for row in rows:
        row["windows"] = parse_report(report(), 0, 1).to_dict()
    assert "insufficient_observed_capacity_updates" in summarize(rows)["reasons"]


def test_empty_qualification_is_unavailable():
    result = summarize([])
    assert result["decision"] == "no_go" and result["energy_drop_wh"] is None
