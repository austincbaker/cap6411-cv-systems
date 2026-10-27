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

powermetrics (needs root): ``sudo -n powermetrics`` runs as a child process
for the whole run and streams one sample per ``interval_ms``. Each sample
gives the energy used in that interval by the CPU, GPU and Neural Engine
(``cpu_energy``, ``gpu_energy``, ``ane_energy``, mJ), reported as
``quantity: "energy"`` in J with the measured ``interval_s``. ``sudo -n``
never prompts: without cached credentials or a sudoers rule the sensor
reports ``sudo_password_required`` and the run continues without it.
"""

from __future__ import annotations

import plistlib
import subprocess
import sys
import threading
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
        battery_w = voltage_mv * -current_ma / 1e6
        system_w = system_load_mw / 1000.0

        def power_error(watts: float) -> Optional[str]:
            # Power drawn on battery can't be negative; the controller has reported e.g. SystemLoad = -31.7 W.
            return error or ("implausible_negative_value" if watts < 0 else None)

        common = dict(host_time_s=now, device_time_s=update_time)
        return [
            reading("battery_power", self.DOMAIN_BATTERY, "power",
                    raw_value={"voltage_mV": voltage_mv, "current_mA": current_ma}, raw_unit="mV,mA",
                    value=battery_w, unit="W", error=power_error(battery_w), **common),
            reading("system_load", self.DOMAIN_SYSTEM, "power", raw_value=system_load_mw, raw_unit="mW",
                    value=system_w, unit="W", error=power_error(system_w), **common),
            reading("system_load_accumulator", self.DOMAIN_SYSTEM, "energy_counter_raw",
                    raw_value=accumulator, raw_unit="undocumented", value=None, unit=None, error=error, **common),
        ]

    def _failure(self, now: float, error: str) -> list[dict]:
        if error == self._last_error:
            return []  # report a persisting failure once, not every poll
        self._last_error = error
        return [reading("battery", self.DOMAIN_BATTERY, "power", host_time_s=now, error=error)]


class PowermetricsSensor:
    DOMAINS = ("cpu", "gpu", "ane")

    def __init__(self, *, interval_ms: int = 500, popen: Callable[..., subprocess.Popen] = subprocess.Popen,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.interval_ms = interval_ms
        self.command = ["sudo", "-n", "/usr/bin/powermetrics", "--samplers", "cpu_power,gpu_power,ane_power",
                        "-i", str(interval_ms), "-f", "plist"]
        self._popen = popen
        self._clock = clock
        self._proc: Optional[subprocess.Popen] = None
        self._reader: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._pending: list[dict] = []
        self._started = False
        self._ended_reported = False

    def metadata(self) -> dict:
        return {
            "source": " ".join(self.command),
            "interval_ms": self.interval_ms,
            "sensors": [{"sensor_id": f"{d}_energy", "domain": d, "quantity": "energy", "unit": "J",
                         "derived_from": f"powermetrics processor.{d}_energy (mJ per interval)"} for d in self.DOMAINS],
            "host_time_s": "when the sample arrived, i.e. the end of its interval",
        }

    def poll(self) -> list[dict]:
        if not self._started:
            self._started = True
            self._start()
        with self._lock:
            out, self._pending = self._pending, []
        if self._proc is not None and self._proc.poll() is not None and not self._reader.is_alive() \
                and not self._ended_reported:
            self._ended_reported = True
            err = (self._proc.stderr.read() or b"").decode("utf-8", "replace").strip() if self._proc.stderr else ""
            reason = "sudo_password_required" if "password" in err else f"powermetrics_exited: {self._proc.returncode} {err[:200]}"
            out.append(reading("powermetrics", "cpu", "energy", host_time_s=self._clock(), error=reason))
        return out

    def close(self) -> None:
        proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.terminate()  # sudo relays the signal to powermetrics
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
        if self._reader is not None:
            self._reader.join(timeout=3)

    def _start(self) -> None:
        try:
            self._proc = self._popen(self.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as exc:
            self._ended_reported = True
            with self._lock:
                self._pending.append(reading("powermetrics", "cpu", "energy", host_time_s=self._clock(),
                                             error=f"powermetrics_not_started: {exc}"))
            return
        self._reader = threading.Thread(target=self._read_stream, name="powermetrics-reader", daemon=True)
        self._reader.start()

    def _read_stream(self) -> None:
        buffer = b""
        while True:
            chunk = self._proc.stdout.read1(65536) if hasattr(self._proc.stdout, "read1") else self._proc.stdout.read(65536)
            if not chunk:
                break
            buffer += chunk
            *docs, buffer = buffer.split(b"\0")
            for doc in docs:
                if doc.strip():
                    self._handle(doc)
        if buffer.strip():
            self._handle(buffer)

    def _handle(self, doc: bytes) -> None:
        now = self._clock()
        try:
            sample = plistlib.loads(doc.strip())
            interval_s = sample["elapsed_ns"] / 1e9
            processor = sample["processor"]
            device_time = sample.get("timestamp")
            device_time_s = device_time.timestamp() if hasattr(device_time, "timestamp") else None
            readings = []
            for d in self.DOMAINS:
                mj = processor[f"{d}_energy"]
                r = reading(f"{d}_energy", d, "energy", raw_value=mj, raw_unit="mJ", value=mj / 1000.0, unit="J",
                            host_time_s=now, device_time_s=device_time_s)
                r["interval_s"] = interval_s
                readings.append(r)
        except (plistlib.InvalidFileException, ValueError, KeyError, TypeError) as exc:
            readings = [reading("powermetrics", "cpu", "energy", host_time_s=now,
                                error=f"unexpected_powermetrics_output: {type(exc).__name__}: {exc}")]
        with self._lock:
            self._pending.extend(readings)


class EnergyMonitor:
    def __init__(self, sensors: Optional[list] = None, *, powermetrics_interval_ms: int = 500) -> None:
        if sensors is None:
            sensors = ([BatterySensor(), PowermetricsSensor(interval_ms=powermetrics_interval_ms)]
                       if sys.platform == "darwin" else [])
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
