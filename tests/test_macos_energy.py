"""energy.macos parsing, sampling and per-run totals with synthetic powermetrics/ioreg data."""

from __future__ import annotations

import csv
import plistlib
import sys
import time
from pathlib import Path

import pytest

from energy import macos
from tests.fakes.fake_powermetrics import sample

FAKE = Path(__file__).parent / "fakes" / "fake_powermetrics.py"


def test_parses_a_powermetrics_sample():
    row = macos.parse_powermetrics_sample(sample(1.0, 1500.0, 300.0), 12.0)
    assert row["host_time_s"] == 12.0
    assert row["elapsed_s"] == pytest.approx(1.0)
    assert (row["cpu_mw"], row["gpu_mw"], row["ane_mw"], row["combined_mw"]) == (
        1500.0,
        300.0,
        0.0,
        1800.0,
    )
    assert row["thermal_pressure"] == "Nominal"


def test_falls_back_to_energy_over_elapsed_and_gpu_section():
    document = plistlib.dumps(
        {
            "elapsed_ns": 500_000_000,
            "processor": {"cpu_energy": 1000},  # mJ over 0.5 s = 2000 mW
            "gpu": {"gpu_energy": 100},
        }
    )
    row = macos.parse_powermetrics_sample(document, 0.0)
    assert row["cpu_mw"] == pytest.approx(2000.0)
    assert row["gpu_mw"] == pytest.approx(200.0)
    assert row["ane_mw"] is None
    assert row["combined_mw"] == pytest.approx(2200.0)


def test_split_plists_keeps_the_unfinished_tail():
    a, b = sample(1, 1, 1), sample(1, 2, 2)
    documents, rest = macos.split_plists(a + b"\x00" + b[:20])
    assert documents == [a]
    assert rest == b[:20]


def battery_plist(**fields) -> bytes:
    entry = {
        "BatteryInstalled": True,
        "ExternalConnected": False,
        "IsCharging": False,
        "CurrentCapacity": 80,
        "MaxCapacity": 100,
        "AppleRawCurrentCapacity": 4000,
        "AppleRawMaxCapacity": 5000,
        "Voltage": 12000,
        "InstantAmperage": (1 << 64) - 1000,  # -1000 mA, as ioreg prints it
        "Temperature": 3050,
        "CycleCount": 42,
        "UpdateTime": 1,
        "PowerTelemetryData": {
            "SystemLoad": 9000,
            "SystemPowerIn": 0,
            "AccumulatedSystemLoad": 1_000_000,
            "SystemLoadAccumulatorCount": 100,
        },
    }
    entry.update(fields)
    return plistlib.dumps([entry])


def test_parses_a_discharging_battery():
    row = macos.parse_ioreg_battery(battery_plist(), 5.0)
    assert row["valid"] is True and row["error"] is None
    assert row["amperage_ma"] == -1000
    assert row["power_w"] == pytest.approx(-12.0)
    assert row["percent"] == 80
    assert row["temperature_c"] == pytest.approx(30.5)
    assert row["external_connected"] is False
    assert row["system_load_mw"] == 9000
    assert row["accumulated_system_load"] == 1_000_000


def test_no_battery_is_invalid_but_keeps_system_telemetry():
    row = macos.parse_ioreg_battery(battery_plist(BatteryInstalled=False, Voltage=0), 0.0)
    assert row["valid"] is False and row["error"] == "no battery installed"
    assert row["power_w"] is None
    assert row["system_load_mw"] == 9000


def test_empty_ioreg_output_is_invalid():
    row = macos.parse_ioreg_battery(b"", 0.0)
    assert row["valid"] is False and "no AppleSmartBattery" in row["error"]


def test_pmset_parsers():
    assert macos.parse_pmset_batt("Now drawing from 'Battery Power'\n -InternalBattery-0") == (
        "Battery Power"
    )
    assert macos.parse_low_power_mode(" sleep 1\n lowpowermode         1\n") is True
    assert macos.parse_low_power_mode(" lowpowermode 0") is False
    assert macos.parse_low_power_mode("nothing") is None


def test_recorder_logs_samples_from_a_fake_powermetrics(tmp_path):
    recorder = macos.PowermetricsRecorder(
        tmp_path, command=[sys.executable, str(FAKE), "0.05", "1000", "250"]
    )
    recorder.start()
    time.sleep(0.6)
    info = recorder.stop()
    assert info["samples"] >= 3
    rows = list(csv.DictReader((tmp_path / macos.POWERMETRICS_FILE).open()))
    assert float(rows[0]["combined_mw"]) == 1250.0
    assert (tmp_path / macos.POWERMETRICS_RAW_FILE).stat().st_size > 0


def write_rows(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in columns})


def test_summarize_run_integrates_each_domain(tmp_path):
    write_rows(
        tmp_path / macos.POWERMETRICS_FILE,
        macos.POWERMETRICS_COLUMNS,
        [
            {
                "host_time_s": t,
                "elapsed_s": 1.0,
                "cpu_mw": 2000,
                "gpu_mw": 1000,
                "combined_mw": 3000,
            }
            for t in range(0, 12)
        ],
    )
    battery = []
    for i, t in enumerate((1.0, 10.0, 20.0)):
        battery.append(
            {
                "host_time_s": t,
                "valid": True,
                "external_connected": False,
                "percent": 80 - i,
                "raw_current_capacity_mah": 4000 - 10 * i,
                "voltage_mv": 12000,
                "power_w": -10.0,
                "accumulated_system_load": 1_000_000 + 60_000 * min(i, 1),
                "system_load_count": 100 + 10 * min(i, 1),
            }
        )
    write_rows(tmp_path / macos.BATTERY_FILE, macos.BATTERY_COLUMNS, battery)
    write_rows(
        tmp_path / macos.RSS_FILE,
        macos.RSS_COLUMNS,
        [{"host_time_s": t, "pid": 1, "rss_kb": 1024 * (100 + t)} for t in range(0, 11)],
    )
    summary = macos.summarize_run(tmp_path, 1.0, 10.0)
    assert summary["powermetrics_samples"] == 10  # samples at 1..10 s
    assert summary["package_combined_j"] == pytest.approx(30.0)
    assert summary["package_combined_mean_w"] == pytest.approx(3.0)
    assert summary["on_battery"] is True
    assert summary["battery_mean_w"] == pytest.approx(10.0)
    assert summary["battery_capacity_wh"] == pytest.approx(20 * 12 / 1000)
    assert summary["system_load_mean_w"] == pytest.approx(6.0)  # 60000 mW*ticks / 10 ticks
    assert summary["system_load_j"] == pytest.approx(54.0)
    assert summary["server_peak_rss_mb"] == pytest.approx(110.0)


def test_summarize_run_leaves_missing_domains_empty(tmp_path):
    summary = macos.summarize_run(tmp_path, 0.0, 10.0)
    assert summary["package_combined_j"] is None
    assert summary["battery_j"] is None and summary["on_battery"] is None
    assert summary["system_load_j"] is None
    assert summary["server_peak_rss_mb"] is None


def test_battery_energy_needs_every_sample_on_battery(tmp_path):
    rows = [
        {"host_time_s": t, "valid": True, "external_connected": ac, "power_w": -10.0}
        for t, ac in ((0.0, False), (10.0, True))
    ]
    write_rows(tmp_path / macos.BATTERY_FILE, macos.BATTERY_COLUMNS, rows)
    summary = macos.summarize_run(tmp_path, 0.0, 10.0)
    assert summary["on_battery"] is False
    assert summary["battery_j"] is None
