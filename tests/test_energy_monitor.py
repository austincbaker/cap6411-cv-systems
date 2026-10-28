import csv
import json
from pathlib import Path
from threading import Event

import pytest

from energy.monitor import EnergyMonitor, discover_sensors, main


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(value))


@pytest.fixture
def sysfs(tmp_path):
    root = tmp_path / "sys"
    (root / "class/powercap").mkdir(parents=True)
    battery = root / "class/power_supply/BAT0"
    for name, value in {
        "type": "Battery",
        "present": 1,
        "status": "Discharging",
        "energy_now": 2_000_000,
        "power_now": 2_500_000,
    }.items():
        write(battery / name, value)
    write(root / "class/power_supply/AC/type", "Mains")
    write(root / "class/power_supply/AC/online", 0)
    return root


def zone(root, name="intel-rapl:0", value=1_000_000, label="package-0"):
    path = root / "class/powercap" / name
    write(path / "energy_uj", value)
    write(path / "name", label)
    write(path / "max_energy_range_uj", 100_000_000)
    return path


def test_discovery_deduplicates_aliases_keeps_hierarchy_and_avoids_backreferences(sysfs, tmp_path):
    package = zone(sysfs)
    core = zone(sysfs, "intel-rapl:0/intel-rapl:0:0", label="core", value=200_000)
    (sysfs / "class/powercap/alias").symlink_to(package, target_is_directory=True)
    unrelated = tmp_path / "unrelated"
    write(unrelated / "energy_uj", 500)
    (core / "device").symlink_to(unrelated, target_is_directory=True)
    sensors, warnings = discover_sensors(sysfs)
    assert not warnings
    assert len(sensors) == 4
    counter = next(s for s in sensors if s.name == "core")
    assert counter.parent_sensor_id == "powercap:intel-rapl:0"
    assert counter.max_energy_range_j == 100.0
    assert len({s.path for s in sensors}) == 4


def test_units_domains_and_shared_time_origin(sysfs, monkeypatch):
    monkeypatch.setattr("energy.monitor.platform.release", lambda: "6.8.0")
    zone(sysfs)
    monitor = EnergyMonitor(sysfs_root=sysfs, run_id="test-run", origin_s=10, clock=lambda: 12)
    rows = {row.sensor_id: row for row in monitor.sample()}
    assert rows["powercap:intel-rapl:0"].value == 1.0
    energy = rows["battery:BAT0:energy_now"]
    assert energy.value == 7200.0 and energy.raw_unit == "uWh" and energy.unit == "J"
    assert energy.domain == "battery_stored_energy"
    power = rows["battery:BAT0:power_now"]
    assert power.value == 2.5 and power.unit == "W" and power.domain == "battery_flow"
    assert all(r.run_id == "test-run" and r.elapsed_s == 2 for r in rows.values())
    assert all(r.valid and not r.quality_flags for r in rows.values())


def test_counter_decreases_are_preserved_not_unwrapped(sysfs):
    path = zone(sysfs)
    monitor = EnergyMonitor(sysfs_root=sysfs)
    first = next(r for r in monitor.sample() if r.quantity == "energy_counter")
    write(path / "energy_uj", 100)
    second = next(r for r in monitor.sample() if r.quantity == "energy_counter")
    assert first.raw_value == 1_000_000 and second.raw_value == 100
    assert first.max_energy_range_j == second.max_energy_range_j == 100.0


@pytest.mark.parametrize("raw", ["invalid", "-1", "100000001"])
def test_invalid_counter_never_becomes_valid_zero(sysfs, raw):
    path = zone(sysfs)
    monitor = EnergyMonitor(sysfs_root=sysfs)
    write(path / "energy_uj", raw)
    row = next(r for r in monitor.sample() if r.quantity == "energy_counter")
    assert not row.valid and row.value is None and row.raw_value is None
    assert row.error == "ValueError"


def test_permission_failure_and_disappearing_sensor(sysfs, monkeypatch):
    path = zone(sysfs)
    original = Path.read_text

    def read(p, *args, **kwargs):
        if p == path / "energy_uj":
            raise PermissionError("test denial")
        return original(p, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    monitor = EnergyMonitor(sysfs_root=sysfs)
    sensor = next(s for s in monitor.sensors if s.quantity == "energy_counter")
    assert sensor.readable_at_discovery is False
    row = next(r for r in monitor.sample() if r.quantity == "energy_counter")
    assert row.error == "PermissionError" and row.value is None
    monkeypatch.setattr(Path, "read_text", original)
    (path / "energy_uj").unlink()
    row = next(r for r in monitor.sample() if r.quantity == "energy_counter")
    assert row.error == "FileNotFoundError" and not row.valid


def test_charge_only_is_not_fabricated_energy(tmp_path):
    root = tmp_path / "sys"
    write(root / "class/power_supply/BAT/type", "Battery")
    write(root / "class/power_supply/BAT/charge_now", 5_000_000)
    write(root / "class/power_supply/BAT/voltage_now", 12_000_000)
    sensors, warnings = discover_sensors(root)
    assert sensors == []
    assert any("no measured energy/power" in w for w in warnings)


def test_virtualized_and_not_discharging_are_quality_flags_not_fake_watts(sysfs, monkeypatch):
    monkeypatch.setattr("energy.monitor.platform.release", lambda: "6.6-microsoft-WSL2")
    write(sysfs / "class/power_supply/AC/online", 1)
    write(sysfs / "class/power_supply/BAT0/status", "Not charging")
    write(sysfs / "class/power_supply/BAT0/power_now", 0)
    row = next(r for r in EnergyMonitor(sysfs_root=sysfs).sample() if r.quantity == "power")
    assert row.valid and row.value == 0.0
    assert row.ac_online is True
    assert "wsl_host_validation_required" in row.quality_flags
    assert "not_verified_discharging" in row.quality_flags


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_finite_sampling_includes_interval_end_and_can_stop(sysfs):
    clock = Clock()
    monitor = EnergyMonitor(sysfs_root=sysfs, clock=clock, sleep=clock.sleep)
    batches = list(monitor.iter_samples(1.0, 0.4))
    assert [batch[0].elapsed_s for batch in batches] == pytest.approx([0, 0.4, 0.8, 1.0])
    stopped = Event()
    stopped.set()
    assert list(monitor.iter_samples(1.0, 0.1, stop_event=stopped)) == []


@pytest.mark.parametrize("duration,interval", [(0, 1), (1, -1), (float("nan"), 1)])
def test_bad_sampling_configuration(sysfs, duration, interval):
    with pytest.raises(ValueError):
        list(EnergyMonitor(sysfs_root=sysfs).iter_samples(duration, interval))


def test_cli_saves_rows_and_missing_sensors_exit_unsuccessfully(sysfs, tmp_path, capsys):
    output = tmp_path / "run"
    assert (
        main(
            [
                "--sysfs-root",
                str(sysfs),
                "--output",
                str(output),
                "--duration",
                "0.01",
                "--interval",
                "0.01",
            ]
        )
        == 0
    )
    console = json.loads(capsys.readouterr().out)
    assert any("CPU/package energy is unavailable" in warning for warning in console["warnings"])
    with (output / "samples.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    manifest = json.loads((output / "manifest.json").read_text())
    assert rows and manifest["completed"]
    assert manifest["valid_rows"] == len(rows)
    assert manifest["measured_duration_s"] >= 0.01
    empty = tmp_path / "no-sensors"
    assert main(["--sysfs-root", str(tmp_path / "empty"), "--output", str(empty)]) == 2
    assert json.loads((empty / "manifest.json").read_text())["error"] == "no_sensors"
    with pytest.raises(SystemExit):
        main(["--sysfs-root", str(sysfs), "--output", str(output)])


def test_cli_preserves_partial_trace_on_interrupt(sysfs, tmp_path, monkeypatch):
    def interrupted(self, *args, **kwargs):
        yield self.sample()
        raise KeyboardInterrupt

    monkeypatch.setattr(EnergyMonitor, "iter_samples", interrupted)
    output = tmp_path / "interrupted"
    assert main(["--sysfs-root", str(sysfs), "--output", str(output)]) == 130
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["error"] == "interrupted" and not manifest["completed"]
    assert manifest["valid_rows"] > 0
    assert len((output / "samples.csv").read_text().splitlines()) > 1
