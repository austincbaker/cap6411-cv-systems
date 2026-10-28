#!/usr/bin/env python3
"""Run the owner-approved, unplugged 1b battery-source qualification on the team laptop."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from energy.monitor import EnergyMonitor
from energy.windows import WindowsBatteryReader


def summarize(rows: list[dict]) -> dict:
    native = [row["windows"] for row in rows]
    good = [row for row in native if row["valid"]]
    reasons = []
    if len(good) != len(rows) or len(rows) < 3:
        reasons.append("missing_or_invalid_native_samples")
    if any(
        row["ac_online"] is not False or row["battery_status"] != "Discharging" for row in native
    ):
        reasons.append("battery_power_not_verified_for_entire_run")
    capacities = [row["remaining_mwh"] for row in good]
    if not {"idle", "cpu_load", "recovery"}.issubset({row["phase"] for row in rows}):
        reasons.append("missing_phase_samples")
    if len(set(capacities)) < 3:
        reasons.append("insufficient_observed_capacity_updates")
    if not capacities or capacities[-1] >= capacities[0]:
        reasons.append("no_observed_net_battery_energy_drop")
    phases = {}
    for phase in ["idle", "cpu_load", "recovery"]:
        selected = [row for row in rows if row["phase"] == phase and row["windows"]["valid"]]
        powers = [
            row["windows"]["discharge_power_w"]
            for row in selected
            if row["windows"]["discharge_power_w"] is not None
        ]
        phases[phase] = {
            "samples": len(selected),
            "reported_discharge_power_median_w": statistics.median(powers) if powers else None,
        }
    full = [row["full_mwh"] for row in good]
    changes = [
        (
            later["available_s"] - earlier["available_s"],
            earlier["remaining_mwh"] - later["remaining_mwh"],
        )
        for earlier, later in zip(good, good[1:])
        if earlier["remaining_mwh"] != later["remaining_mwh"]
    ]
    positive_steps = [step / 1000 for _, step in changes if step > 0]
    update_times = [
        later["available_s"]
        for earlier, later in zip(good, good[1:])
        if earlier["remaining_mwh"] != later["remaining_mwh"]
    ]
    update_intervals = [b - a for a, b in zip(update_times, update_times[1:])]
    return {
        "decision": "go" if not reasons else "no_go",
        "reasons": reasons,
        "qualified_source": "Windows.Devices.Power.BatteryReport" if not reasons else None,
        "scope": "whole-laptop reported battery energy; includes Windows and background work",
        "raw_energy_unit": "mWh",
        "joules_per_raw_unit": 3.6,
        "samples": len(rows),
        "valid_native_samples": len(good),
        "distinct_remaining_capacity_values": len(set(capacities)),
        "first_remaining_mwh": capacities[0] if capacities else None,
        "last_remaining_mwh": capacities[-1] if capacities else None,
        "energy_drop_wh": (capacities[0] - capacities[-1]) / 1000 if len(capacities) >= 2 else None,
        "native_full_capacity_mwh": full[0] if full else None,
        "observed_capacity_step_median_wh": statistics.median(positive_steps)
        if positive_steps
        else None,
        "observed_update_interval_median_s": statistics.median(update_intervals)
        if update_intervals
        else None,
        "observed_update_interval_max_s": max(update_intervals) if update_intervals else None,
        "phases": phases,
        "limitations": [
            "Battery-controller estimates, not an external meter",
            "Sampling includes PowerShell query overhead",
            "Short qualification run, not a VLM-policy energy comparison",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--idle-seconds", type=float, default=120)
    parser.add_argument("--load-seconds", type=float, default=120)
    parser.add_argument("--recovery-seconds", type=float, default=30)
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    args = parser.parse_args()
    durations = (args.idle_seconds, args.load_seconds, args.recovery_seconds, args.interval)
    if any(not math.isfinite(value) or value <= 0 for value in durations):
        parser.error("phase durations and interval must be finite and positive")
    if not 1 <= args.workers <= (os.cpu_count() or 1):
        parser.error("workers must be positive and no greater than available logical CPUs")
    args.output.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    wsl = EnergyMonitor(origin_s=start)
    windows = WindowsBatteryReader()
    manifest = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "origin_monotonic_s": start,
        "run_id": wsl.run_id,
        "parameters": {
            key: str(value) if isinstance(value, Path) else value
            for key, value in vars(args).items()
        },
        "wsl_inventory": wsl.inventory(),
        "completed": False,
        "events": [],
    }
    manifest["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    workers = []
    rows = []
    total = args.idle_seconds + args.load_seconds + args.recovery_seconds
    load_end = start + args.idle_seconds + args.load_seconds
    next_tick = start
    exit_code = 0
    try:
        with (args.output / "samples.jsonl").open("x") as output:
            while True:
                time.sleep(max(0, next_tick - time.monotonic()))
                elapsed = time.monotonic() - start
                phase = (
                    "idle"
                    if elapsed < args.idle_seconds
                    else (
                        "cpu_load"
                        if elapsed < args.idle_seconds + args.load_seconds
                        else "recovery"
                    )
                )
                if phase == "cpu_load" and not workers:
                    code = (
                        "import hashlib,time,sys; data=b'x'*1048576; "
                        "deadline=float(sys.argv[1]);\n"
                        "while time.monotonic()<deadline: hashlib.sha256(data).digest()"
                    )
                    workers = [
                        subprocess.Popen([sys.executable, "-c", code, str(load_end)])
                        for _ in range(args.workers)
                    ]
                    manifest["events"].append({"event": "cpu_load_started", "elapsed_s": elapsed})
                native = windows.read()
                row = {
                    "run_id": wsl.run_id,
                    "elapsed_s": elapsed,
                    "phase": phase,
                    "windows": native.to_dict(),
                    "wsl": [asdict(sample) for sample in wsl.sample()],
                }
                rows.append(row)
                output.write(json.dumps(row) + "\n")
                output.flush()
                print(
                    json.dumps(
                        {
                            "phase": phase,
                            "elapsed_s": round(elapsed, 1),
                            "remaining_mwh": native.remaining_mwh,
                            "reported_discharge_w": native.discharge_power_w,
                            "ac_online": native.ac_online,
                            "valid": native.valid,
                        }
                    ),
                    flush=True,
                )
                if not native.on_battery:
                    manifest["error"] = "battery_source_invalid_or_ac_connected"
                    exit_code = 2
                    break
                if native.remaining_mwh / native.full_mwh < 0.20:
                    manifest["error"] = "battery_below_20_percent"
                    exit_code = 2
                    break
                if elapsed >= total:
                    manifest["completed"] = True
                    break
                next_tick = min(start + total, next_tick + args.interval)
                if next_tick < time.monotonic():
                    next_tick = min(start + total, time.monotonic() + args.interval)
    except KeyboardInterrupt:
        manifest["error"] = "interrupted"
        exit_code = 130
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.terminate()
            worker.wait()
        manifest["ended_utc"] = datetime.now(timezone.utc).isoformat()
        manifest["duration_s"] = time.monotonic() - start
        (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        report = summarize(rows)
        if not manifest["completed"]:
            report.update(decision="no_go", qualified_source=None)
            report["reasons"].append(manifest.get("error", "incomplete_run"))
        (args.output / "qualification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)
    return exit_code if exit_code else (0 if report["decision"] == "go" else 2)


if __name__ == "__main__":
    sys.exit(main())
