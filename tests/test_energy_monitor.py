"""Battery telemetry from fake ioreg output (no Mac hardware needed)."""

from __future__ import annotations

import datetime
import io
import plistlib
import subprocess

import pytest

from src.energy.monitor import BatterySensor, EnergyMonitor, PowermetricsSensor
from tests.fakes.fake_clock import FakeClock


def ioreg_bytes(update_time=1000, on_ac=False, voltage=11714, current=-548, system_load=6419, accumulator=951318210):
    return plistlib.dumps([{
        "UpdateTime": update_time, "ExternalConnected": on_ac, "Voltage": voltage, "InstantAmperage": current,
        "PowerTelemetryData": {"SystemLoad": system_load, "AccumulatedSystemLoad": accumulator},
    }])


class FakeIoreg:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        out = self.outputs[min(self.calls - 1, len(self.outputs) - 1)]
        if isinstance(out, BaseException):
            raise out
        return out


def by_id(readings):
    return {r["sensor_id"]: r for r in readings}


def test_on_battery_reports_power_in_watts_with_raw_values():
    clock = FakeClock()
    sensor = BatterySensor(run=FakeIoreg(ioreg_bytes()), clock=clock)
    r = by_id(sensor.poll())
    assert r["battery_power"]["value"] == pytest.approx(11.714 * 0.548)
    assert r["battery_power"]["raw_value"] == {"voltage_mV": 11714, "current_mA": -548}
    assert r["system_load"]["value"] == pytest.approx(6.419) and r["system_load"]["raw_unit"] == "mW"
    acc = r["system_load_accumulator"]
    assert acc["raw_value"] == 951318210 and acc["value"] is None and acc["valid"]
    assert all(x["valid"] and x["error"] is None for x in r.values())
    assert all(x["host_time_s"] == clock.now and x["device_time_s"] == 1000 for x in r.values())


def test_unsigned_current_from_ioreg_is_converted_to_negative():
    sensor = BatterySensor(run=FakeIoreg(ioreg_bytes(current=2**64 - 548)), clock=FakeClock())
    assert by_id(sensor.poll())["battery_power"]["value"] == pytest.approx(11.714 * 0.548)


def test_polls_are_rate_limited_and_repeats_are_not_re_emitted():
    clock = FakeClock()
    ioreg = FakeIoreg(ioreg_bytes(update_time=1000), ioreg_bytes(update_time=1000), ioreg_bytes(update_time=1060))
    sensor = BatterySensor(poll_s=5.0, run=ioreg, clock=clock)
    assert len(sensor.poll()) == 3
    clock.advance(1.0)
    assert sensor.poll() == [] and ioreg.calls == 1  # too soon: ioreg not even run
    clock.advance(5.0)
    assert sensor.poll() == [] and ioreg.calls == 2  # same controller reading: nothing new
    clock.advance(5.0)
    assert {r["device_time_s"] for r in sensor.poll()} == {1060}


def test_external_power_makes_readings_invalid_not_zero():
    sensor = BatterySensor(run=FakeIoreg(ioreg_bytes(on_ac=True, current=1500)), clock=FakeClock())
    readings = sensor.poll()
    assert readings and all(r["valid"] is False and r["value"] is None for r in readings)
    assert {r["error"] for r in readings} == {"external_power_connected"}


@pytest.mark.parametrize("failure, error", [
    (FileNotFoundError(), "ioreg_not_found"),
    (subprocess.CalledProcessError(1, "ioreg"), "ioreg_failed: exit 1"),
    (subprocess.TimeoutExpired("ioreg", 5), "ioreg_timeout"),
    (b"not a plist", "unexpected_ioreg_output"),
    (plistlib.dumps([]), "unexpected_ioreg_output"),
    (plistlib.dumps([{"UpdateTime": 1}]), "unexpected_ioreg_output"),
])
def test_read_failures_are_explicit_and_reported_once(failure, error):
    clock = FakeClock()
    sensor = BatterySensor(run=FakeIoreg(failure), clock=clock)
    first = sensor.poll()
    assert len(first) == 1 and first[0]["valid"] is False and first[0]["value"] is None
    assert first[0]["error"].startswith(error)
    clock.advance(10)
    assert sensor.poll() == []  # same failure is not repeated every poll


def test_recovery_after_a_failure_reports_again():
    clock = FakeClock()
    sensor = BatterySensor(run=FakeIoreg(FileNotFoundError(), ioreg_bytes()), clock=clock)
    assert sensor.poll()[0]["valid"] is False
    clock.advance(10)
    assert all(r["valid"] for r in sensor.poll())


def test_monitor_without_sensors_reports_unavailable_once():
    monitor = EnergyMonitor(sensors=[])
    assert monitor.metadata()["status"] == "unavailable"
    first = monitor.sample()
    assert len(first) == 1 and first[0]["valid"] is False and first[0]["value"] is None
    assert monitor.sample() == []


def test_monitor_combines_sensor_metadata_and_readings():
    monitor = EnergyMonitor(sensors=[BatterySensor(run=FakeIoreg(ioreg_bytes()), clock=FakeClock())])
    meta = monitor.metadata()
    assert meta["status"] == "available" and meta["sensors"] == ["BatterySensor"]
    assert {s["sensor_id"] for s in meta["details"][0]["sensors"]} == {"battery_power", "system_load", "system_load_accumulator"}
    assert len(monitor.sample()) == 3


# --------------------------------------------------------------------------- powermetrics


def pm_sample(cpu_mj=452, gpu_mj=102, ane_mj=20, elapsed_ns=503_771_541):
    return plistlib.dumps({
        "is_delta": True, "elapsed_ns": elapsed_ns, "timestamp": datetime.datetime(2026, 10, 27, 19, 57, 39),
        "processor": {"cpu_energy": cpu_mj, "gpu_energy": gpu_mj, "ane_energy": ane_mj, "cpu_power": 897.2},
    })


class FakeProc:
    def __init__(self, stdout=b"", stderr=b"", returncode=None):
        self.stdout = io.BytesIO(stdout)
        self.stderr = io.BytesIO(stderr)
        self.returncode = returncode
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.returncode = -9


def started(proc, **kw):
    calls = []

    def popen(cmd, **kwargs):
        calls.append(cmd)
        return proc

    sensor = PowermetricsSensor(popen=popen, clock=FakeClock(), **kw)
    first = sensor.poll()  # starts the process
    if sensor._reader is not None:
        sensor._reader.join(2)
    return sensor, first, calls


def test_powermetrics_command_never_prompts_for_a_password():
    sensor, _, calls = started(FakeProc(), interval_ms=250)
    assert calls == [["sudo", "-n", "/usr/bin/powermetrics", "--samplers", "cpu_power,gpu_power,ane_power",
                      "-i", "250", "-f", "plist"]]


def test_powermetrics_samples_become_energy_readings_in_joules():
    stream = pm_sample() + b"\0" + pm_sample(cpu_mj=298, gpu_mj=80, ane_mj=18, elapsed_ns=511_249_083) + b"\0"
    sensor, first, _ = started(FakeProc(stdout=stream))
    readings = first + sensor.poll()
    assert [r["sensor_id"] for r in readings] == ["cpu_energy", "gpu_energy", "ane_energy"] * 2
    cpu = readings[0]
    assert cpu["value"] == pytest.approx(0.452) and cpu["raw_value"] == 452 and cpu["raw_unit"] == "mJ"
    assert cpu["unit"] == "J" and cpu["quantity"] == "energy" and cpu["domain"] == "cpu" and cpu["valid"]
    assert cpu["interval_s"] == pytest.approx(0.503771541)
    assert cpu["device_time_s"] is not None
    assert readings[3]["value"] == pytest.approx(0.298)
    assert sensor.poll() == []


def test_missing_sudo_rights_are_reported_once_not_as_zero():
    proc = FakeProc(stderr=b"sudo: a password is required\n", returncode=1)
    sensor, first, _ = started(proc)
    readings = first + sensor.poll()
    assert len(readings) == 1
    assert readings[0]["valid"] is False and readings[0]["value"] is None
    assert readings[0]["error"] == "sudo_password_required"
    assert sensor.poll() == []


def test_bad_powermetrics_output_is_flagged_and_later_samples_still_parse():
    stream = b"garbage\0" + pm_sample() + b"\0"
    sensor, first, _ = started(FakeProc(stdout=stream))
    readings = first + sensor.poll()
    assert readings[0]["valid"] is False and readings[0]["error"].startswith("unexpected_powermetrics_output")
    assert [r["sensor_id"] for r in readings[1:]] == ["cpu_energy", "gpu_energy", "ane_energy"]


def test_powermetrics_that_cannot_start_is_reported():
    def popen(cmd, **kwargs):
        raise FileNotFoundError("sudo")
    sensor = PowermetricsSensor(popen=popen, clock=FakeClock())
    readings = sensor.poll()
    assert len(readings) == 1 and readings[0]["error"].startswith("powermetrics_not_started")
    assert sensor.poll() == []


def test_close_stops_a_running_powermetrics():
    proc = FakeProc(stdout=pm_sample() + b"\0")
    sensor, _, _ = started(proc)
    sensor.close()
    assert proc.terminated
    assert not sensor._reader.is_alive()
