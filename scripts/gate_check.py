#!/usr/bin/env python3
"""Check where a run's VLM calls landed against annotated event windows (item 2a tuning aid).

For each run directory: how many calls the policy made, which annotated windows got a call on a
frame inside them (and how late after onset), whether that answer names the event, and how many
calls landed outside every window. This is a gate development check on development clips, not
the item 3d event scorer: it looks at requests, not predictions.

The windows CSV has columns label, onset_s, end_s in source seconds; a window is
[onset_s - tolerance, end_s + tolerance).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

DEFAULT_NAMES = {"thumb_up": r"thumb", "peace": r"peace|v[- ]sign|victory"}


def read_windows(path: Path) -> list[dict]:
    with path.open(newline="") as handle:
        return [
            {"label": row["label"], "onset_s": float(row["onset_s"]), "end_s": float(row["end_s"])}
            for row in csv.DictReader(handle)
        ]


def check_run(
    run_dir: Path, windows: list[dict], tolerance_s: float, names: dict[str, re.Pattern]
) -> dict:
    manifest = json.loads((run_dir / "manifest.json").read_text())
    counts = manifest.get("counts", {})
    requests = []
    with (run_dir / "requests.jsonl").open() as handle:
        requests = [json.loads(line) for line in handle if line.strip()]
    ok = [r for r in requests if r.get("status") == "ok" and r.get("source_time_s") is not None]
    inside: set[str] = set()
    results = []
    for window in windows:
        lo, hi = window["onset_s"] - tolerance_s, window["end_s"] + tolerance_s
        hits = [r for r in ok if lo <= r["source_time_s"] < hi]
        inside.update(r["request_id"] for r in hits)
        pattern = names.get(window["label"])
        named = [r for r in hits if pattern and pattern.search(r.get("text") or "")]
        results.append(
            {
                **window,
                "calls": len(hits),
                "first_latency_s": hits[0]["source_time_s"] - window["onset_s"] if hits else None,
                "named": len(named) if pattern else None,
                "first_named_latency_s": (
                    named[0]["source_time_s"] - window["onset_s"] if named else None
                ),
            }
        )
    outside = [r for r in ok if r["request_id"] not in inside]
    return {
        "run_dir": str(run_dir),
        "policy": manifest.get("policy"),
        "calls": len(requests),
        "ok": len(ok),
        "tick_skipped_busy": counts.get("tick_skipped_busy", 0),
        "gate": {k: v for k, v in counts.items() if k.startswith("gate_")},
        "windows": results,
        "windows_caught": sum(1 for w in results if w["calls"]),
        "windows_named": sum(1 for w in results if w["named"]),
        "outside_calls": len(outside),
        "outside_times_s": [round(r["source_time_s"], 2) for r in outside],
    }


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:+.2f}s"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("run_dirs", nargs="+", type=Path)
    parser.add_argument("--windows", type=Path, required=True, help="CSV: label,onset_s,end_s")
    parser.add_argument("--tolerance-s", type=float, default=0.0)
    parser.add_argument(
        "--name",
        action="append",
        default=[],
        metavar="LABEL=REGEX",
        help="answer text that names LABEL (defaults: thumb_up=thumb, peace=peace|v-sign|victory)",
    )
    parser.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = parser.parse_args(argv)
    names = dict(DEFAULT_NAMES)
    for item in args.name:
        label, _, regex = item.partition("=")
        names[label] = regex
    patterns = {label: re.compile(regex, re.IGNORECASE) for label, regex in names.items()}
    windows = read_windows(args.windows)
    reports = [check_run(d, windows, args.tolerance_s, patterns) for d in args.run_dirs]
    if args.json:
        print(json.dumps(reports, indent=2))
        return 0
    for report in reports:
        print(
            f"{report['run_dir']}: {report['policy']}, {report['calls']} calls, "
            f"{report['windows_caught']}/{len(windows)} windows caught, "
            f"{report['windows_named']} named, {report['outside_calls']} outside"
        )
        for w in report["windows"]:
            named = "" if w["named"] is None else f", named {w['named']}"
            print(
                f"  {w['label']} {w['onset_s']:.2f}-{w['end_s']:.2f}s: {w['calls']} calls, "
                f"first {_fmt(w['first_latency_s'])}{named}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
