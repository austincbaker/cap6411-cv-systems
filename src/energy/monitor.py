"""Read-only sysfs telemetry; raw readings are never substituted with estimates."""

from __future__ import annotations

import argparse
import csv
import json
import math
import platform
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event
from typing import Any, Callable, Iterator


def _text(path: Path) -> str:
    return path.read_text().strip()


def _optional_text(path: Path) -> str | None:
    try:
        return _text(path)
    except OSError:
        return None


@dataclass(frozen=True)
class Sensor:
    sensor_id: str
    path: str
    name: str
    domain: str
    quantity: str
    raw_unit: str
    unit: str
    scale: float
    max_energy_range_j: float | None = None
    parent_sensor_id: str | None = None
    battery_path: str | None = None
    readable_at_discovery: bool = True
    discovery_error: str | None = None


@dataclass(frozen=True)
class Reading:
    run_id: str
    sensor_id: str
    elapsed_s: float
    domain: str
    quantity: str
    raw_value: int | None
    raw_unit: str
    value: float | None
    unit: str
    valid: bool
    error: str | None
    max_energy_range_j: float | None
    battery_status: str | None
    ac_online: bool | None
    quality_flags: str


def _read_value(sensor: Sensor) -> tuple[int, float]:
    raw = int(_text(Path(sensor.path)))
    value = raw * sensor.scale
    if not math.isfinite(value):
        raise ValueError("nonfinite sensor reading")
    if sensor.quantity != "power" and raw < 0:
        raise ValueError("negative energy reading")
    if sensor.max_energy_range_j is not None and value > sensor.max_energy_range_j:
        raise ValueError("energy reading exceeds counter range")
    return raw, value


def discover_sensors(sysfs_root: Path = Path("/sys")) -> tuple[list[Sensor], list[str]]:
    """Discover available quantities, following powercap aliases without duplicates.

    A battery's charge_now is deliberately not converted to energy using its
    instantaneous voltage: that would turn a raw measurement into an estimate.
    """
    sensors: list[Sensor] = []
    warnings: list[str] = []
    pending = [sysfs_root / "class/powercap"]
    visited: set[Path] = set()
    zones: dict[Path, str] = {}
    while pending:
        path = pending.pop()
        try:
            real = path.resolve()
            if real in visited:
                continue
            visited.add(real)
            children = sorted(path.iterdir())
            pending.extend(
                child
                for child in children
                if child.is_dir()
                and child.name
                not in {
                    "device",
                    "subsystem",
                    "power",
                    "driver",
                    "firmware_node",
                }
            )
        except (OSError, RuntimeError) as exc:
            warnings.append(f"powercap discovery: {type(exc).__name__}: {path}")
            continue
        counter = real / "energy_uj"
        if not counter.is_file():
            continue
        sensor_id = f"powercap:{real.name}"
        name = _optional_text(real / "name") or real.name
        limit_text = _optional_text(real / "max_energy_range_uj")
        limit = None
        if limit_text is not None:
            try:
                limit = int(limit_text) * 1e-6
                if not math.isfinite(limit) or limit <= 0:
                    raise ValueError("invalid range")
            except (ValueError, OverflowError):
                warnings.append(f"invalid counter range: {real}")
                limit = None
        domain = "cpu_package" if name.startswith("package") else "powercap_zone"
        sensors.append(
            Sensor(sensor_id, str(counter), name, domain, "energy_counter", "uJ", "J", 1e-6, limit)
        )
        zones[real] = sensor_id

    supply_root = sysfs_root / "class/power_supply"
    try:
        supplies = sorted(supply_root.iterdir())
    except OSError as exc:
        warnings.append(f"power-supply discovery: {type(exc).__name__}: {supply_root}")
        supplies = []
    for supply in supplies:
        if _optional_text(supply / "type") != "Battery":
            continue
        if _optional_text(supply / "present") == "0":
            continue
        for attribute, quantity, raw_unit, unit, scale in (
            ("energy_now", "stored_energy", "uWh", "J", 0.0036),
            ("power_now", "power", "uW", "W", 1e-6),
        ):
            path = supply / attribute
            if path.is_file():
                sensors.append(
                    Sensor(
                        f"battery:{supply.name}:{attribute}",
                        str(path),
                        supply.name,
                        "battery_stored_energy" if quantity == "stored_energy" else "battery_flow",
                        quantity,
                        raw_unit,
                        unit,
                        scale,
                        battery_path=str(supply),
                    )
                )
        if not any(s.battery_path == str(supply) for s in sensors):
            warnings.append(f"no measured energy/power attributes for battery {supply.name}")

    checked: list[Sensor] = []
    for sensor in sensors:
        fields = asdict(sensor)
        if sensor.quantity == "energy_counter":
            zone = Path(sensor.path).parent
            fields["parent_sensor_id"] = next(
                (zones[p] for p in zone.parents if p in zones),
                None,
            )
        try:
            _read_value(sensor)
        except (OSError, ValueError, OverflowError) as exc:
            fields.update(readable_at_discovery=False, discovery_error=type(exc).__name__)
        checked.append(Sensor(**fields))
    if not any(sensor.quantity == "energy_counter" for sensor in checked):
        warnings.append("no powercap energy counters found; CPU/package energy is unavailable")
    if not checked:
        warnings.append("no energy or power sensors found; do not report zero consumption")
    return sorted(checked, key=lambda s: s.sensor_id), warnings


class EnergyMonitor:
    """Collect independent sensor rows on a shared host monotonic time base."""

    def __init__(
        self,
        *,
        sysfs_root: Path = Path("/sys"),
        sensors: list[Sensor] | None = None,
        run_id: str | None = None,
        origin_s: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.sysfs_root = Path(sysfs_root)
        self.sensors, self.warnings = (
            discover_sensors(self.sysfs_root)
            if sensors is None
            else (
                list(sensors),
                [],
            )
        )
        self.run_id = run_id or uuid.uuid4().hex
        self._clock = clock
        self._sleep = sleep
        self.origin_s = clock() if origin_s is None else origin_s
        self.virtualized = "microsoft" in platform.release().lower()
        if self.virtualized:
            self.warnings.append(
                "WSL telemetry requires physical-host validation before energy claims"
            )

    def inventory(self) -> dict[str, Any]:
        return {
            "record_version": 1,
            "run_id": self.run_id,
            "origin_monotonic_s": self.origin_s,
            "platform": platform.platform(),
            "wsl": self.virtualized,
            "sysfs_root": str(self.sysfs_root),
            "sensors": [asdict(sensor) for sensor in self.sensors],
            "warnings": self.warnings,
        }

    def _ac_online(self) -> bool | None:
        root = self.sysfs_root / "class/power_supply"
        try:
            values = [
                _optional_text(p / "online")
                for p in root.iterdir()
                if _optional_text(p / "type") != "Battery"
            ]
        except OSError:
            return None
        known = [value == "1" for value in values if value in {"0", "1"}]
        return any(known) if known else None

    def sample(self) -> list[Reading]:
        elapsed = self._clock() - self.origin_s
        ac_online = self._ac_online()
        rows: list[Reading] = []
        for sensor in self.sensors:
            raw = value = error = None
            try:
                raw, value = _read_value(sensor)
            except (OSError, ValueError, OverflowError) as exc:
                error = type(exc).__name__
            battery_status = (
                _optional_text(Path(sensor.battery_path) / "status")
                if sensor.battery_path
                else None
            )
            flags = []
            if self.virtualized:
                flags.append("wsl_host_validation_required")
            if sensor.battery_path and (battery_status != "Discharging" or ac_online is not False):
                flags.append("not_verified_discharging")
            rows.append(
                Reading(
                    self.run_id,
                    sensor.sensor_id,
                    elapsed,
                    sensor.domain,
                    sensor.quantity,
                    raw,
                    sensor.raw_unit,
                    value,
                    sensor.unit,
                    error is None,
                    error,
                    sensor.max_energy_range_j,
                    battery_status,
                    ac_online,
                    ";".join(flags),
                )
            )
        return rows

    def iter_samples(
        self,
        duration_s: float,
        interval_s: float,
        *,
        stop_event: Event | None = None,
    ) -> Iterator[list[Reading]]:
        for value, name in ((duration_s, "duration_s"), (interval_s, "interval_s")):
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        start = self._clock()
        end = start + duration_s
        next_tick = start
        while stop_event is None or not stop_event.is_set():
            delay = max(0.0, next_tick - self._clock())
            if stop_event is not None:
                if stop_event.wait(delay):
                    break
            else:
                self._sleep(delay)
            yield self.sample()
            now = self._clock()
            if now >= end:
                break
            # Skip missed ticks rather than emitting a burst of artificial samples.
            next_tick = min(end, start + (math.floor((now - start) / interval_s) + 1) * interval_s)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", action="store_true", help="Report sensors without a run")
    parser.add_argument("--sysfs-root", type=Path, default=Path("/sys"))
    parser.add_argument("--output", type=Path, help="New run directory (never overwritten)")
    parser.add_argument("--duration", type=float, default=30.0, help="Measured seconds")
    parser.add_argument("--interval", type=float, default=1.0, help="Requested sample spacing")
    parser.add_argument("--run-id", help="Shared run ID when integrating with the application")
    args = parser.parse_args(argv)
    monitor = EnergyMonitor(sysfs_root=args.sysfs_root, run_id=args.run_id)
    if args.inventory:
        print(json.dumps(monitor.inventory(), indent=2))
        return 0
    if args.output is None:
        parser.error("--output is required unless --inventory is selected")
    for value in (args.duration, args.interval):
        if not math.isfinite(value) or value <= 0:
            parser.error("duration and interval must be finite and positive")
    try:
        args.output.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        parser.error(f"cannot create run directory: {exc}")
    metadata = {
        **monitor.inventory(),
        "requested_duration_s": args.duration,
        "requested_interval_s": args.interval,
        "completed": False,
        "valid_rows": 0,
        "invalid_rows": 0,
    }
    exit_code = 0
    started = time.monotonic()
    try:
        with (args.output / "samples.csv").open("x", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=list(Reading.__dataclass_fields__))
            writer.writeheader()
            if not monitor.sensors:
                metadata["error"] = "no_sensors"
                exit_code = 2
            else:
                for batch in monitor.iter_samples(args.duration, args.interval):
                    for row in batch:
                        writer.writerow(asdict(row))
                        metadata["valid_rows" if row.valid else "invalid_rows"] += 1
                    output.flush()
                metadata["completed"] = metadata["valid_rows"] > 0
                if not metadata["completed"]:
                    metadata["error"] = "no_valid_samples"
                    exit_code = 2
    except KeyboardInterrupt:
        metadata["error"] = "interrupted"
        metadata["completed"] = False
        exit_code = 130
    except OSError as exc:
        metadata["error"] = type(exc).__name__
        metadata["completed"] = False
        exit_code = 2
    finally:
        metadata["measured_duration_s"] = time.monotonic() - started
        (args.output / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "completed": metadata["completed"],
                "valid_rows": metadata["valid_rows"],
                "error": metadata.get("error"),
                "warnings": monitor.warnings,
            }
        )
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
