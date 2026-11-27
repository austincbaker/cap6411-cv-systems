"""macOS energy recording for the experiment suite (Apple silicon laptops).

Three samplers run alongside one experiment run and write their own files into the run
directory; none of them changes the item 2d ``power.csv`` contract:

- ``powermetrics.csv``: ``powermetrics`` CPU, GPU, ANE and combined power every second
  (``-f plist``). Domain: the SoC package as powermetrics reports it, not the whole laptop.
  powermetrics needs root; the suite runs it as ``sudo -n powermetrics`` after asking for the
  password once in the terminal (``sudo -v``). No password is stored.
- ``battery.csv``: ``ioreg -rn AppleSmartBattery -a`` every 10 s: charge, voltage, current and
  AC state (domain: the whole laptop, meaningful only while it runs on battery), plus the SMC
  power telemetry in the same record (``PowerTelemetryData``: system load in mW and its
  per-second accumulator, published about once a minute; whole laptop, on AC or battery).
- ``server_rss.csv``: resident memory of the llama-server process every second (``ps``).

Readings that cannot be taken are written as missing (empty cells with an error), never as
zero. ``summarize_run`` turns the three files into per-run totals.
"""

from __future__ import annotations

import csv
import ctypes
import ctypes.util
import plistlib
import re
import shlex
import subprocess
import threading
import time
from pathlib import Path
from typing import IO, Callable, Optional, Sequence

POWERMETRICS_FILE = "powermetrics.csv"
POWERMETRICS_RAW_FILE = "powermetrics.plist"
BATTERY_FILE = "battery.csv"
RSS_FILE = "server_rss.csv"

POWERMETRICS_COLUMNS = [
    "host_time_s",
    "elapsed_s",
    "cpu_mw",
    "gpu_mw",
    "ane_mw",
    "combined_mw",
    "thermal_pressure",
]
BATTERY_COLUMNS = [
    "host_time_s",
    "valid",
    "error",
    "external_connected",
    "is_charging",
    "percent",
    "raw_current_capacity_mah",
    "raw_max_capacity_mah",
    "voltage_mv",
    "amperage_ma",
    "power_w",
    "temperature_c",
    "cycle_count",
    "battery_installed",
    "system_load_mw",
    "system_power_in_mw",
    "accumulated_system_load",
    "system_load_count",
    "update_time",
]
RSS_COLUMNS = ["host_time_s", "pid", "rss_kb", "error"]
DEFAULT_SAMPLERS = "cpu_power,gpu_power,ane_power,thermal"
FALLBACK_SAMPLERS = "cpu_power,gpu_power"


# ============================================================================ parsing


def split_plists(data: bytes) -> tuple[list[bytes], bytes]:
    """Complete NUL-separated plist documents in ``data`` and the unfinished remainder."""
    *done, rest = data.split(b"\x00")
    return [chunk for chunk in done if chunk.strip()], rest


def _number(value) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def parse_powermetrics_sample(document: bytes, host_time_s: float) -> dict:
    """One powermetrics plist sample as a POWERMETRICS_COLUMNS row (powers in mW, missing = None).

    Powers come from ``processor.<x>_power`` when present, else from ``<x>_energy`` (mJ) over
    the sample's elapsed time; GPU power may sit under ``gpu`` on some macOS versions.
    """
    sample = plistlib.loads(document.strip())
    elapsed_ns = _number(sample.get("elapsed_ns"))
    elapsed_s = elapsed_ns / 1e9 if elapsed_ns else None
    processor = sample.get("processor") or {}
    gpu = sample.get("gpu") or {}

    def power(name: str, *sections: dict) -> Optional[float]:
        for section in sections:
            value = _number(section.get(f"{name}_power"))
            if value is not None:
                return value
        for section in sections:
            energy = _number(section.get(f"{name}_energy"))
            if energy is not None and elapsed_s:
                return energy / elapsed_s  # mJ / s = mW
        return None

    cpu = power("cpu", processor)
    gpu_mw = power("gpu", processor, gpu)
    ane = power("ane", processor)
    combined = _number(processor.get("combined_power"))
    if combined is None and cpu is not None and gpu_mw is not None:
        combined = cpu + gpu_mw + (ane or 0.0)
    return {
        "host_time_s": host_time_s,
        "elapsed_s": elapsed_s,
        "cpu_mw": cpu,
        "gpu_mw": gpu_mw,
        "ane_mw": ane,
        "combined_mw": combined,
        "thermal_pressure": sample.get("thermal_pressure"),
    }


def _signed(value) -> Optional[int]:
    """ioreg reports negative currents as unsigned 64-bit integers."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value - (1 << 64) if value >= (1 << 63) else value


def parse_ioreg_battery(data: bytes, host_time_s: float) -> dict:
    """A BATTERY_COLUMNS row from ``ioreg -rn AppleSmartBattery -a`` output.

    ``power_w`` is voltage x current: negative while discharging, positive while charging.
    A machine without a battery (a Mac mini) gives an invalid row with an error.
    """
    row = {column: None for column in BATTERY_COLUMNS}
    row["host_time_s"] = host_time_s
    try:
        entries = plistlib.loads(data) if data.strip() else []
    except Exception as exc:
        row.update(valid=False, error=f"unparsable ioreg output: {type(exc).__name__}")
        return row
    if isinstance(entries, dict):
        entries = [entries]
    if not entries:
        row.update(valid=False, error="no AppleSmartBattery (no battery on this machine)")
        return row
    battery = entries[0]
    telemetry = battery.get("PowerTelemetryData") or {}
    row.update(
        battery_installed=battery.get("BatteryInstalled"),
        system_load_mw=_number(telemetry.get("SystemLoad")),
        system_power_in_mw=_number(telemetry.get("SystemPowerIn")),
        accumulated_system_load=_number(telemetry.get("AccumulatedSystemLoad")),
        system_load_count=_number(telemetry.get("SystemLoadAccumulatorCount")),
        update_time=battery.get("UpdateTime"),
    )
    if battery.get("BatteryInstalled") is False:
        row.update(
            valid=False,
            error="no battery installed",
            external_connected=battery.get("ExternalConnected"),
        )
        return row
    voltage = _number(battery.get("Voltage"))
    amperage = _signed(battery.get("InstantAmperage", battery.get("Amperage")))
    if amperage is None:
        amperage = _signed(battery.get("Amperage"))
    max_capacity = _number(battery.get("MaxCapacity"))
    current = _number(battery.get("CurrentCapacity"))
    percent = None
    if current is not None and max_capacity:
        # Apple silicon reports CurrentCapacity/MaxCapacity in percent (MaxCapacity 100).
        percent = current if max_capacity == 100 else 100.0 * current / max_capacity
    temperature = _number(battery.get("Temperature"))
    row.update(
        valid=voltage is not None and amperage is not None,
        error=None if voltage is not None and amperage is not None else "missing voltage/current",
        external_connected=battery.get("ExternalConnected"),
        is_charging=battery.get("IsCharging"),
        percent=percent,
        raw_current_capacity_mah=_number(battery.get("AppleRawCurrentCapacity")),
        raw_max_capacity_mah=_number(battery.get("AppleRawMaxCapacity")),
        voltage_mv=voltage,
        amperage_ma=amperage,
        power_w=(voltage * amperage / 1e6)
        if voltage is not None and amperage is not None
        else None,
        temperature_c=temperature / 100.0 if temperature is not None else None,
        cycle_count=battery.get("CycleCount"),
    )
    return row


# ============================================================================ system state


def _run(command: Sequence[str], timeout: float = 10.0) -> tuple[Optional[str], Optional[str]]:
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if done.returncode != 0:
        return None, (done.stderr or done.stdout).strip() or f"exit {done.returncode}"
    return done.stdout, None


def parse_pmset_batt(text: str) -> Optional[str]:
    match = re.search(r"drawing from '([^']+)'", text)
    return match.group(1) if match else None


def parse_low_power_mode(text: str) -> Optional[bool]:
    match = re.search(r"^\s*lowpowermode\s+(\d)", text, re.MULTILINE)
    return None if match is None else match.group(1) == "1"


def display_brightness() -> dict:
    """Built-in display brightness 0-1 via the DisplayServices framework, or the error."""
    try:
        services = ctypes.CDLL(
            "/System/Library/PrivateFrameworks/DisplayServices.framework/DisplayServices"
        )
        graphics = ctypes.CDLL(ctypes.util.find_library("CoreGraphics"))
        graphics.CGMainDisplayID.restype = ctypes.c_uint32
        display = graphics.CGMainDisplayID()
        value = ctypes.c_float()
        services.DisplayServicesGetBrightness.argtypes = [
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_float),
        ]
        status = services.DisplayServicesGetBrightness(display, ctypes.byref(value))
    except (OSError, AttributeError, TypeError) as exc:
        return {"value": None, "error": f"{type(exc).__name__}: {exc}"}
    if status != 0:
        return {"value": None, "error": f"DisplayServicesGetBrightness returned {status}"}
    return {"value": round(value.value, 4), "error": None}


def system_state() -> dict:
    """Power source, Low Power Mode, brightness, Wi-Fi and machine identity, each with its error."""
    state: dict = {}
    batt, error = _run(["pmset", "-g", "batt"])
    state["power_source"] = parse_pmset_batt(batt) if batt else None
    state["power_source_error"] = error
    settings, error = _run(["pmset", "-g"])
    state["low_power_mode"] = parse_low_power_mode(settings) if settings else None
    state["low_power_mode_error"] = error
    state["display_brightness"] = display_brightness()
    wifi, error = _run(["networksetup", "-getairportpower", "en0"])
    state["wifi"] = wifi.strip() if wifi else None
    state["wifi_error"] = error
    machine = {}
    for key, command in {
        "model": ["sysctl", "-n", "hw.model"],
        "chip": ["sysctl", "-n", "machdep.cpu.brand_string"],
        "memory_bytes": ["sysctl", "-n", "hw.memsize"],
        "macos": ["sw_vers", "-productVersion"],
        "macos_build": ["sw_vers", "-buildVersion"],
    }.items():
        out, _ = _run(command)
        machine[key] = out.strip() if out else None
    state["machine"] = machine
    battery_out, error = _run(["ioreg", "-rn", "AppleSmartBattery", "-a"])
    state["battery"] = (
        parse_ioreg_battery(battery_out.encode(), time.monotonic())
        if battery_out is not None
        else {"valid": False, "error": error}
    )
    return state


# ============================================================================ samplers


class _CsvLog:
    def __init__(self, path: Path, columns: list[str]) -> None:
        self.columns = columns
        self._file = open(path, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=columns)
        self._writer.writeheader()
        self._lock = threading.Lock()
        self.rows = 0

    def write(self, row: dict) -> None:
        with self._lock:
            self._writer.writerow({k: "" if row.get(k) is None else row[k] for k in self.columns})
            self._file.flush()
            self.rows += 1

    def close(self) -> None:
        with self._lock:
            self._file.close()


class PowermetricsRecorder:
    """Runs ``powermetrics`` (through ``sudo -n`` by default) and logs one row per sample.

    ``command`` replaces the whole command line (tests and stubbed runs use a fake emitter).
    The raw plist stream is kept next to the CSV so a parsing problem can be redone later.
    """

    def __init__(
        self,
        run_dir: Path,
        *,
        interval_ms: int = 1000,
        samplers: str = DEFAULT_SAMPLERS,
        command: Optional[Sequence[str]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.command = (
            list(command)
            if command
            else [
                "sudo",
                "-n",
                "powermetrics",
                "--samplers",
                samplers,
                "-i",
                str(interval_ms),
                "-f",
                "plist",
            ]
        )
        self.run_dir = Path(run_dir)
        self.clock = clock
        self.process: Optional[subprocess.Popen] = None
        self.thread: Optional[threading.Thread] = None
        self.errors: list[str] = []
        self.log: Optional[_CsvLog] = None

    def start(self) -> None:
        self.log = _CsvLog(self.run_dir / POWERMETRICS_FILE, POWERMETRICS_COLUMNS)
        raw = open(self.run_dir / POWERMETRICS_RAW_FILE, "wb")
        self.process = subprocess.Popen(
            self.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL
        )
        self.thread = threading.Thread(
            target=self._read, args=(self.process.stdout, raw), name="powermetrics", daemon=True
        )
        self.thread.start()

    def _read(self, stream: IO[bytes], raw: IO[bytes]) -> None:
        pending = b""
        try:
            while chunk := stream.read1(65536):
                raw.write(chunk)
                documents, pending = split_plists(pending + chunk)
                for document in documents:
                    try:
                        self.log.write(parse_powermetrics_sample(document, self.clock()))
                    except Exception as exc:  # keep reading; the raw stream has the sample
                        self.errors.append(f"unparsable sample: {type(exc).__name__}: {exc}")
        finally:
            raw.close()

    def stop(self, timeout: float = 5.0) -> dict:
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()  # sudo relays the signal to powermetrics
                try:
                    self.process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=timeout)
            stderr = self.process.stderr.read().decode(errors="replace").strip()
            if stderr:
                self.errors.append(stderr[-500:])
        if self.thread is not None:
            self.thread.join(timeout=timeout)
        if self.log is not None:
            self.log.close()
        return {
            "command": shlex.join(self.command),
            "samples": self.log.rows if self.log else 0,
            "exit_code": self.process.returncode if self.process else None,
            "errors": self.errors,
        }


class PeriodicSampler:
    """Calls ``read()`` every ``interval_s`` on its own thread and logs each returned row."""

    def __init__(
        self,
        path: Path,
        columns: list[str],
        read: Callable[[], dict],
        interval_s: float,
        name: str,
    ) -> None:
        self.log = _CsvLog(path, columns)
        self.read = read
        self.interval_s = interval_s
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._loop, name=name, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _loop(self) -> None:
        next_t = time.monotonic()
        while not self.stop_event.is_set():
            self.log.write(self.read())
            next_t += self.interval_s
            self.stop_event.wait(max(0.0, next_t - time.monotonic()))

    def stop(self) -> dict:
        self.stop_event.set()
        self.thread.join(timeout=15)
        self.log.close()
        return {"samples": self.log.rows, "interval_s": self.interval_s}


def read_battery() -> dict:
    now = time.monotonic()
    out, error = _run(["ioreg", "-rn", "AppleSmartBattery", "-a"])
    if out is None:
        row = {column: None for column in BATTERY_COLUMNS}
        row.update(host_time_s=now, valid=False, error=error)
        return row
    return parse_ioreg_battery(out.encode(), now)


def rss_reader(pid: int) -> Callable[[], dict]:
    def read() -> dict:
        now = time.monotonic()
        out, error = _run(["ps", "-o", "rss=", "-p", str(pid)], timeout=5)
        try:
            rss = int(out.strip()) if out else None
        except ValueError:
            rss, error = None, f"unparsable ps output: {out!r}"
        return {"host_time_s": now, "pid": pid, "rss_kb": rss, "error": None if rss else error}

    return read


# ============================================================================ summary


def _floats(rows: list[dict], key: str) -> list[float]:
    out = []
    for row in rows:
        try:
            out.append(float(row[key]))
        except (KeyError, TypeError, ValueError):
            pass
    return out


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def summarize_run(run_dir: Path, start_s: float, end_s: float) -> dict:
    """Per-run energy and memory totals over [start_s, end_s] (host monotonic seconds).

    Package energy integrates each powermetrics sample's power over its own elapsed time.
    Battery energy integrates -voltage x current (discharge positive) between battery samples,
    and is reported only when every sample in the window was on battery.
    """
    run_dir = Path(run_dir)
    duration = end_s - start_s
    out: dict = {"window_s": duration}

    samples = [
        r
        for r in _read_csv(run_dir / POWERMETRICS_FILE)
        if start_s <= float(r["host_time_s"]) <= end_s
    ]
    out["powermetrics_samples"] = len(samples)
    for key in ("cpu", "gpu", "ane", "combined"):
        energy, covered = 0.0, 0.0
        for row in samples:
            try:
                power_mw, elapsed = float(row[f"{key}_mw"]), float(row["elapsed_s"])
            except (TypeError, ValueError):
                continue
            energy += power_mw / 1000.0 * elapsed
            covered += elapsed
        valid = covered > 0
        out[f"package_{key}_j"] = energy if valid else None
        out[f"package_{key}_mean_w"] = energy / covered if valid else None
    out["package_coverage_s"] = sum(_floats(samples, "elapsed_s")) if samples else None
    out["thermal_pressure"] = sorted(
        {r["thermal_pressure"] for r in samples if r.get("thermal_pressure")}
    )

    battery = [
        r
        for r in _read_csv(run_dir / BATTERY_FILE)
        if r.get("valid") == "True" and start_s - 15 <= float(r["host_time_s"]) <= end_s + 15
    ]
    on_battery = bool(battery) and all(r.get("external_connected") == "False" for r in battery)
    out["battery_samples"] = len(battery)
    out["on_battery"] = on_battery if battery else None
    if on_battery and len(battery) >= 2:
        energy = 0.0
        for a, b in zip(battery, battery[1:]):
            dt = float(b["host_time_s"]) - float(a["host_time_s"])
            energy += -(float(a["power_w"]) + float(b["power_w"])) / 2.0 * dt
        span = float(battery[-1]["host_time_s"]) - float(battery[0]["host_time_s"])
        out["battery_j"] = energy
        out["battery_mean_w"] = energy / span if span > 0 else None
        first, last = battery[0], battery[-1]
        try:
            used_mah = float(first["raw_current_capacity_mah"]) - float(
                last["raw_current_capacity_mah"]
            )
            volts = (float(first["voltage_mv"]) + float(last["voltage_mv"])) / 2000.0
            out["battery_capacity_wh"] = used_mah * volts / 1000.0
        except (TypeError, ValueError):
            out["battery_capacity_wh"] = None
        out["battery_percent_start"] = (
            _floats([first], "percent")[0] if first.get("percent") else None
        )
        out["battery_percent_end"] = _floats([last], "percent")[0] if last.get("percent") else None
    else:
        out.update(
            battery_j=None,
            battery_mean_w=None,
            battery_capacity_wh=None,
            battery_percent_start=None,
            battery_percent_end=None,
        )

    # SMC telemetry (PowerTelemetryData): the accumulator gains SystemLoad (mW) once per second
    # and is published about once a minute, so the mean load is a ratio of differences.
    telemetry = []
    for r in _read_csv(run_dir / BATTERY_FILE):
        if not start_s <= float(r["host_time_s"]) <= end_s:
            continue
        try:
            telemetry.append((float(r["accumulated_system_load"]), float(r["system_load_count"])))
        except (KeyError, TypeError, ValueError):
            continue
    counts = sorted(set(telemetry), key=lambda t: t[1])
    if len(counts) >= 2 and counts[-1][1] > counts[0][1]:
        mean_mw = (counts[-1][0] - counts[0][0]) / (counts[-1][1] - counts[0][1])
        out["system_load_mean_w"] = mean_mw / 1000.0
        out["system_load_j"] = mean_mw / 1000.0 * duration
        out["system_load_coverage_s"] = counts[-1][1] - counts[0][1]
    else:
        out.update(system_load_mean_w=None, system_load_j=None, system_load_coverage_s=None)

    rss = [r for r in _read_csv(run_dir / RSS_FILE) if start_s <= float(r["host_time_s"]) <= end_s]
    values = _floats(rss, "rss_kb")
    out["server_peak_rss_mb"] = max(values) / 1024.0 if values else None
    out["server_mean_rss_mb"] = sum(values) / len(values) / 1024.0 if values else None
    return out
