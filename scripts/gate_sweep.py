#!/usr/bin/env python3
"""Sweep change-gate settings offline on a development clip (item 2a tuning aid).

Decodes the clip once and samples the newest frame at every tick, as the app does, then runs
the real ``gates.ChangeGate`` for each setting. Inference is modeled as a fixed busy time after
each call (``--latency-s``): ticks inside it are skipped without a gate check, as in the app.
A fixed-interval row with the same model is printed for comparison. Each setting reports
calls, calls per minute, how many annotated windows got a call on a frame inside them (see
scripts/gate_check.py for the CSV) and how many calls landed outside every window.

Tune on development clips only; keep held-out clips for the final check.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import cv2
import numpy as np

from gates import ChangeGate, GateConfig

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.gate_check import read_windows  # noqa: E402


def sample_ticks(
    video: Path, tick_s: float, size: tuple[int, int]
) -> list[tuple[float, np.ndarray]]:
    """(source time of the frame used, small gray frame) for every tick, newest frame at or before it."""
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise SystemExit(f"cannot open {video}")
    ticks: list[tuple[float, np.ndarray]] = []
    index, previous = 0, None
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            t = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            while previous is not None and index * tick_s < t:
                ticks.append(previous)
                index += 1
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            previous = (t, cv2.resize(gray, size, interpolation=cv2.INTER_AREA))
    finally:
        capture.release()
    while previous is not None and index * tick_s <= previous[0]:
        ticks.append(previous)
        index += 1
    return ticks


def simulate(ticks, tick_s, latency_s, config: GateConfig | None, fixed_interval_s=None):
    """Source times of the frames that would be sent."""
    gate = None if config is None else ChangeGate(config)
    busy_until, sent = -1.0, []
    every = None if fixed_interval_s is None else max(1, round(fixed_interval_s / tick_s))
    for index, (frame_t, image) in enumerate(ticks):
        now = index * tick_s
        if now < busy_until:
            continue
        if gate is None:
            if index % every:
                continue
        else:
            decision = gate.decide(image, now)
            if not decision.trigger:
                continue
            gate.acknowledge(decision, now)
        sent.append(frame_t)
        busy_until = now + latency_s
    return sent


def score(sent: list[float], windows: list[dict], tolerance_s: float, duration_s: float) -> dict:
    inside, latencies = set(), []
    for window in windows:
        lo, hi = window["onset_s"] - tolerance_s, window["end_s"] + tolerance_s
        hits = [i for i, t in enumerate(sent) if lo <= t < hi]
        inside.update(hits)
        latencies.append(round(sent[hits[0]] - window["onset_s"], 2) if hits else None)
    return {
        "calls": len(sent),
        "calls_per_min": round(len(sent) / (duration_s / 60), 2) if duration_s else None,
        "windows_caught": sum(lat is not None for lat in latencies),
        "first_latency_s": latencies,
        "outside_calls": len(sent) - len(inside),
    }


def floats(text: str) -> list[float]:
    return [float(v) for v in text.split(",")]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("video", type=Path)
    parser.add_argument("--windows", type=Path, help="CSV: label,onset_s,end_s (optional)")
    parser.add_argument("--tolerance-s", type=float, default=0.0)
    parser.add_argument("--tick-s", type=float, default=0.5, help="gate check interval")
    parser.add_argument("--latency-s", type=float, default=2.5, help="modeled busy time per call")
    parser.add_argument("--thresholds", type=floats, default=floats("0.05,0.1,0.15,0.2,0.3"))
    parser.add_argument("--persist", default="1,2,3,4", help="persist_checks values")
    parser.add_argument(
        "--release-ratio",
        type=floats,
        default=floats("1.0"),
        help="release threshold as a fraction of the threshold (1.0 = no hysteresis)",
    )
    parser.add_argument("--min-interval-s", type=float, default=2.0)
    parser.add_argument("--fixed-interval-s", type=float, default=2.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    defaults = GateConfig()
    ticks = sample_ticks(args.video, args.tick_s, (defaults.width, defaults.height))
    duration = ticks[-1][0] if ticks else 0.0
    windows = read_windows(args.windows) if args.windows else []
    rows = [
        {
            "policy": f"fixed {args.fixed_interval_s:g}s",
            **score(
                simulate(ticks, args.tick_s, args.latency_s, None, args.fixed_interval_s),
                windows,
                args.tolerance_s,
                duration,
            ),
        }
    ]
    persist = [int(v) for v in args.persist.split(",")]
    for threshold, checks, ratio in itertools.product(args.thresholds, persist, args.release_ratio):
        config = GateConfig(
            threshold=threshold,
            persist_checks=checks,
            release_threshold=None if ratio >= 1 else threshold * ratio,
            min_interval_s=args.min_interval_s,
        )
        sent = simulate(ticks, args.tick_s, args.latency_s, config)
        rows.append(
            {
                "policy": f"gated t={threshold:g} p={checks} r={ratio:g}",
                **score(sent, windows, args.tolerance_s, duration),
            }
        )
    if args.json:
        print(
            json.dumps({"video": str(args.video), "duration_s": duration, "rows": rows}, indent=2)
        )
        return 0
    print(
        f"{args.video.name}: {duration:.0f} s, {len(windows)} windows, latency {args.latency_s} s"
    )
    for row in rows:
        print(
            f"  {row['policy']:26s} calls {row['calls']:4d} ({row['calls_per_min']}/min)  "
            f"caught {row['windows_caught']}/{len(windows)} {row['first_latency_s']}  "
            f"outside {row['outside_calls']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
