#!/usr/bin/env python3
"""Replay the annotated pilot clips through the app, one run at a time, under one policy.

Each clip is replayed in real time with ``python -m app.main --source replay`` against the
llama-server that is already running (start it with ``scripts/llama_runtime.py serve``). Run
directories are written as OUT/<clip>-<policy>, logs as OUT/logs/<clip>-<policy>.log. A run
directory that already has a manifest is skipped, so an interrupted pass can be resumed and no
earlier result is overwritten. Score the runs with ``scripts/score_pilot_eval.py``.

``--interval-s`` has no default on purpose: the gate's defaults are tuned for 0.5 s checks,
while the app's own default interval is 2 s. The reported comparison is fixed at 2 s against
gated at 0.5 s.

The full default set replays about 1.5 hours of video per policy.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The pilot clips in data/annotations/pilot.csv plus the control clip. thumbs_mov_6 is left out:
# the copy on the team Drive is byte-identical to thumbs_mov_3.
DEFAULT_CLIPS = (
    "recording_1_thumbs",
    "recording_2_thumbs",
    "recording_3_peace",
    "recording_4_peace",
    "control",
    "thumbs_mov_1",
    "thumbs_mov_2",
    "thumbs_mov_3",
    "thumbs_mov_4",
    "thumbs_mov_5",
)
POLICY_ARGS = {"fixed": ["--policy", "fixed_interval"], "gated": ["--policy", "gated"]}
SLOW_CALL_S = 5.0


def server_healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url.rstrip('/')}/health", timeout=5) as response:
            return response.status == 200
    except OSError:
        return False


def median_call_s(run_dir: Path) -> float | None:
    path = run_dir / "requests.jsonl"
    if not path.exists():
        return None
    with path.open() as handle:
        records = [json.loads(line) for line in handle if line.strip()]
    elapsed = [r["elapsed_s"] for r in records if r.get("status") == "ok" and r.get("elapsed_s")]
    return statistics.median(elapsed) if elapsed else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--policy", choices=tuple(POLICY_ARGS), required=True)
    parser.add_argument(
        "--interval-s",
        type=float,
        required=True,
        help="seconds between ticks (reported numbers: fixed 2, gated 0.5)",
    )
    parser.add_argument("--out", type=Path, required=True, help="folder for this pass's runs")
    parser.add_argument("--videos", type=Path, default=ROOT / "data/videos")
    parser.add_argument("--clips", nargs="+", default=list(DEFAULT_CLIPS), metavar="VIDEO_ID")
    parser.add_argument("--duration-s", type=float, help="stop each replay early (smoke checks)")
    parser.add_argument(
        "--profile", type=Path, default=ROOT / "configs/inference.json", help="inference profile"
    )
    args = parser.parse_args(argv)
    if args.interval_s <= 0:
        parser.error("--interval-s must be positive")

    missing = [c for c in args.clips if not (args.videos / f"{c}.mov").exists()]
    if missing:
        print(f"missing videos in {args.videos}: {', '.join(missing)}", file=sys.stderr)
        return 2
    profile = json.loads(args.profile.read_text())
    server_url = f"http://{profile['host']}:{profile['port']}"
    (args.out / "logs").mkdir(parents=True, exist_ok=True)

    failures = 0
    for clip in args.clips:
        name = f"{clip}-{args.policy}"
        run_dir = args.out / name
        if (run_dir / "manifest.json").exists():
            print(f"skip {name}: {run_dir} already has a manifest")
            continue
        if not server_healthy(server_url):
            print(f"llama-server at {server_url} is not healthy; stopping", file=sys.stderr)
            return 3
        command = [
            sys.executable,
            "-m",
            "app.main",
            "--source",
            "replay",
            "--video",
            str(args.videos / f"{clip}.mov"),
            *POLICY_ARGS[args.policy],
            "--interval-s",
            str(args.interval_s),
            "--profile",
            str(args.profile),
            "--no-display",
            "--run-dir",
            str(run_dir),
        ]
        if args.duration_s:
            command += ["--duration-s", str(args.duration_s)]
        print(f"start {name}", flush=True)
        with (args.out / "logs" / f"{name}.log").open("w") as log:
            code = subprocess.call(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        median = median_call_s(run_dir)
        note = ""
        if median is not None and median > SLOW_CALL_S:
            note = f" (slow: median call {median:.1f} s; check machine load and rerun)"
        median_text = "-" if median is None else f"{median:.2f} s"
        print(f"end {name} exit={code} median_call={median_text}{note}", flush=True)
        failures += code != 0
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
