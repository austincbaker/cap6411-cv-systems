"""Power telemetry for the MacBook (item 1b).

``EnergyMonitor`` matches the app's ``TelemetryMonitor`` shape:
``metadata()``, ``sample() -> list[dict]``, ``close()``. Each reading is

    {sensor_id, domain, quantity, raw_value, raw_unit, value, unit,
     host_time_s, device_time_s, valid, error}

``host_time_s`` is ``time.monotonic()`` when the reading was taken;
``device_time_s`` is the sensor's own update time (Unix seconds) when it has
one. An unavailable or invalid reading has ``valid: False`` and
``value: None`` with the reason in ``error``; it is never reported as 0.

Battery (no admin rights): the battery controller (``ioreg``
AppleSmartBattery) updates about once a minute, so it is polled every
``battery_poll_s`` and a reading is emitted only when the controller's
``UpdateTime`` changes. Readings are valid only while running on battery.

- ``battery_power``: Voltage x InstantAmperage, discharge positive, in W.
- ``system_load``: ``PowerTelemetryData.SystemLoad`` (mW) in W. Undocumented
  by Apple; it matched voltage x current when both were read together.
- ``system_load_accumulator``: ``AccumulatedSystemLoad``, a running counter
  whose unit is undocumented (consistent with mJ); kept raw, ``value: None``.
"""

from __future__ import annotations

import plistlib
import subprocess
import sys
import time
from typing import Callable, Optional

IOREG_COMMAND = ["ioreg", "-a", "-r", "-n", "AppleSmartBattery"]


def run_ioreg() -> bytes:
    return subprocess.run(IOREG_COMMAND, capture_output=True, check=True, timeout=5).stdout


def reading(sensor_id: str, domain: str, quantity: str, *, raw_value=None, raw_unit=None, value=None,
            unit=None, host_time_s: float, device_time_s=None, error: Optional[str] = None) -> dict:
    return {
        "sensor_id": sensor_id, "domain": domain, "quantity": quantity,
        "raw_value": raw_value, "raw_unit": raw_unit,
        "value": value if error is None else None, "unit": unit,
        "host_time_s": host_time_s, "device_time_s": device_time_s,
        "valid": error is None, "error": error,
    }


class BatterySensor:
    DOMAIN_BATTERY = "battery_discharge"
    DOMAIN_SYSTEM = "system_load"

    def __init__(self, *, poll_s: float = 5.0, run: Callable[[], bytes] = run_ioreg,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.poll_s = poll_s
        self._run = run
        self._clock = clock
        self._last_poll: Optional[float] = None
        self._last_update_time = None
        self._last_error: Optional[str] = None

    def metadata(self) -> dict:
        return {
            "source": " ".join(IOREG_COMMAND),
            "poll_s": self.poll_s,
            "update_cadence": "about 60 s (battery controller); readings emitted only on change",
            "valid_when": "running on battery (ExternalConnected = No)",
            "sensors": [
                {"sensor_id": "battery_power", "domain": self.DOMAIN_BATTERY, "quantity": "power", "unit": "W",
                 "derived_from": "Voltage (mV) x InstantAmperage (mA), discharge positive"},
                {"sensor_id": "system_load", "domain": self.DOMAIN_SYSTEM, "quantity": "power", "unit": "W",
                 "derived_from": "PowerTelemetryData.SystemLoad (mW, undocumented)"},
                {"sensor_id": "system_load_accumulator", "domain": self.DOMAIN_SYSTEM,
                 "quantity": "energy_counter_raw", "unit": None,
                 "derived_from": "PowerTelemetryData.AccumulatedSystemLoad (unit undocumented, consistent with mJ)"},
            ],
        }

    def poll(self) -> list[dict]:
        now = self._clock()
        if self._last_poll is not None and now - self._last_poll < self.poll_s:
            return []
        self._last_poll = now
        try:
            battery = plistlib.loads(self._run())[0]
            update_time = battery["UpdateTime"]
            on_ac = bool(battery["ExternalConnected"])
            voltage_mv = battery["Voltage"]
            current_ma = battery["InstantAmperage"]
            telemetry = battery["PowerTelemetryData"]
            system_load_mw = telemetry["SystemLoad"]
            accumulator = telemetry["AccumulatedSystemLoad"]
        except FileNotFoundError:
            return self._failure(now, "ioreg_not_found")
        except subprocess.CalledProcessError as exc:
            return self._failure(now, f"ioreg_failed: exit {exc.returncode}")
        except subprocess.TimeoutExpired:
            return self._failure(now, "ioreg_timeout")
        except (plistlib.InvalidFileException, ValueError, IndexError, KeyError, TypeError) as exc:
            return self._failure(now, f"unexpected_ioreg_output: {type(exc).__name__}: {exc}")

        if update_time == self._last_update_time:
            return []  # the controller has not produced a new reading yet
        self._last_update_time = update_time
        self._last_error = None
        error = "external_power_connected" if on_ac else None
        if current_ma >= 2**63:  # some ioreg output formats print the signed value as unsigned 64-bit
            current_ma -= 2**64
        common = dict(host_time_s=now, device_time_s=update_time, error=error)
        return [
            reading("battery_power", self.DOMAIN_BATTERY, "power",
                    raw_value={"voltage_mV": voltage_mv, "current_mA": current_ma}, raw_unit="mV,mA",
                    value=voltage_mv * -current_ma / 1e6, unit="W", **common),
            reading("system_load", self.DOMAIN_SYSTEM, "power", raw_value=system_load_mw, raw_unit="mW",
                    value=system_load_mw / 1000.0, unit="W", **common),
            reading("system_load_accumulator", self.DOMAIN_SYSTEM, "energy_counter_raw",
                    raw_value=accumulator, raw_unit="undocumented", value=None, unit=None, **common),
        ]

    def _failure(self, now: float, error: str) -> list[dict]:
        if error == self._last_error:
            return []  # report a persisting failure once, not every poll
        self._last_error = error
        return [reading("battery", self.DOMAIN_BATTERY, "power", host_time_s=now, error=error)]


class EnergyMonitor:
    def __init__(self, sensors: Optional[list] = None) -> None:
        if sensors is None:
            sensors = [BatterySensor()] if sys.platform == "darwin" else []
        self.sensors = sensors
        self._reported_none = False

    def metadata(self) -> dict:
        return {
            "kind": "energy_monitor",
            "platform": sys.platform,
            "status": "available" if self.sensors else "unavailable",
            "sensors": [type(s).__name__ for s in self.sensors],
            "details": [s.metadata() for s in self.sensors],
        }

    def sample(self) -> list[dict]:
        if not self.sensors:
            if self._reported_none:
                return []
            self._reported_none = True
            return [reading("none", "none", "power", host_time_s=time.monotonic(),
                            error=f"no supported power sensor on {sys.platform}")]
        out: list[dict] = []
        for sensor in self.sensors:
            out.extend(sensor.poll())
        return out

    def close(self) -> None:
        for sensor in self.sensors:
            close = getattr(sensor, "close", None)
            if close:
                close()
