#!/usr/bin/env python3
"""Score pilot replay runs against the pilot annotations, one row per run, with policy totals.

RUNS_DIR holds run directories named <video_id>-<policy>, as ``scripts/run_pilot_eval.py``
writes them. Each run is matched to its video's windows in the annotations CSV (a clip with no
rows, such as ``control``, has no windows) with a tolerance of ``--tolerance-s`` around each
window (default 1 s; the pilot labels run about a second off). Call coverage comes from
``scripts/gate_check.py``; on top of it, for runs with validated answers (item 2c):

- named: a window with an ok call inside it whose ``gesture`` is the window's label;
- false mention: an ok call outside every window whose gesture is thumbs_up or peace_sign;
- delay: from window onset to when the first naming answer was available, source seconds;
- onsets: gesture onsets derived from the requests with ``app.state.GestureScene``, checked
  against the run's own predictions.jsonl.

This is a pilot functional check over requests, not the item 3d event scorer.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.state import Evidence, GestureScene  # noqa: E402
from scripts.gate_check import check_run  # noqa: E402

GESTURES = ("thumbs_up", "peace_sign")
PATTERNS = {
    "thumbs_up": re.compile("thumb", re.IGNORECASE),
    "peace_sign": re.compile("peace|v[- ]sign|victory", re.IGNORECASE),
}
POLICIES = ("fixed", "gated")
GATE_SKIPS = ("gate_no_change", "gate_persisting", "gate_cooldown")


def read_annotations(path: Path) -> dict[str, list[dict]]:
    windows: dict[str, list[dict]] = {}
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            windows.setdefault(row["video_id"], []).append(
                {
                    "label": row["label"],
                    "onset_s": float(row["onset_s"]),
                    "end_s": float(row["end_s"]),
                }
            )
    return windows


def read_jsonl(path: Path) -> list[dict]:
    with path.open() as handle:
        return [json.loads(line) for line in handle if line.strip()]


def answer_source_s(record: dict) -> float | None:
    """When the answer was available, on the source timeline."""
    if record.get("response_available_s") is None:
        return None
    return record["source_time_s"] + (record["response_available_s"] - record["host_capture_s"])


def derived_onsets(requests: list[dict]) -> list[dict]:
    scene, onsets = GestureScene(), []
    for r in requests:
        evidence = None
        if r.get("gesture") is not None:
            evidence = Evidence(
                r["request_id"],
                r["frame_id"],
                r["source_time_s"],
                r["host_capture_s"],
                r["response_available_s"],
            )
        for event in scene.update(r.get("gesture"), evidence):
            if event.transition == "onset":
                onsets.append({"label": event.gesture, "source_time_s": evidence.source_time_s})
    return onsets


def _median(values: list[float]):
    return round(statistics.median(values), 2) if values else ""


def score_run(run: Path, clip: str, policy: str, windows: list[dict], tol: float) -> dict:
    base = check_run(run, windows, tol, PATTERNS)
    manifest = json.loads((run / "manifest.json").read_text())
    counts = manifest.get("counts", {})
    requests = read_jsonl(run / "requests.jsonl")
    ok = [r for r in requests if r.get("status") == "ok" and r.get("source_time_s") is not None]

    def in_window(w: dict, t: float) -> bool:
        return w["onset_s"] - tol <= t < w["end_s"] + tol

    delays, named_windows, wrong = [], 0, 0
    for w in windows:
        hits = [r for r in ok if in_window(w, r["source_time_s"])]
        named = [r for r in hits if r.get("gesture") == w["label"]]
        wrong += sum(1 for r in hits if r.get("gesture") in GESTURES and r["gesture"] != w["label"])
        if named:
            named_windows += 1
            delays.append(answer_source_s(named[0]) - w["onset_s"])
    outside = [r for r in ok if not any(in_window(w, r["source_time_s"]) for w in windows)]
    false = [r for r in outside if r.get("gesture") in GESTURES]
    invalid = [r for r in ok if r.get("gesture") is None]

    onsets = derived_onsets(requests)
    predictions = read_jsonl(run / "predictions.jsonl")
    app_onsets = [p for p in predictions if p.get("transition") == "onset"]
    app_offsets = [p for p in predictions if p.get("transition") == "offset"]
    if [(p["label"], p["source_time_s"]) for p in app_onsets] != [
        (o["label"], o["source_time_s"]) for o in onsets
    ]:
        raise SystemExit(f"{run}: predictions.jsonl onsets differ from the scene-state derivation")
    windows_with_onset = sum(
        1
        for w in windows
        if any(o["label"] == w["label"] and in_window(w, o["source_time_s"]) for o in onsets)
    )
    return {
        "label": "Mac mini, functional check",
        "clip": clip,
        "policy": policy,
        "interval_s": manifest.get("config", {}).get("interval_s", ""),
        "exit_code": manifest.get("exit_code"),
        "run_end_reason": manifest.get("run_end_reason"),
        "calls": base["calls"],
        "ok": base["ok"],
        "failed": base["calls"] - base["ok"],
        "busy_skips": counts.get("tick_skipped_busy", 0),
        "gate_skips": sum(counts.get(k, 0) for k in GATE_SKIPS) if policy == "gated" else "",
        "windows": len(windows),
        "windows_caught": base["windows_caught"],
        "windows_named": named_windows,
        "windows_named_gate_check": base["windows_named"],
        "wrong_gesture_in_window": wrong,
        "false_mentions_outside": len(false),
        "outside_calls": len(outside),
        "median_delay_to_naming_answer_s": _median(delays),
        "delays_s": " ".join(f"{d:.2f}" for d in delays),
        "answers_thumbs_up": sum(1 for r in ok if r.get("gesture") == "thumbs_up"),
        "answers_peace_sign": sum(1 for r in ok if r.get("gesture") == "peace_sign"),
        "answers_none": sum(1 for r in ok if r.get("gesture") == "none"),
        "answers_invalid": len(invalid),
        "invalid_errors": " ".join(sorted({r.get("answer_error") or "?" for r in invalid})),
        "onsets": len(onsets),
        "onsets_in_window": sum(
            1 for o in onsets if any(in_window(w, o["source_time_s"]) for w in windows)
        ),
        "windows_with_onset": windows_with_onset,
        "app_onsets": len(app_onsets),
        "app_offsets": len(app_offsets),
        "onsets_thumbs_up": sum(o["label"] == "thumbs_up" for o in onsets),
        "onsets_peace_sign": sum(o["label"] == "peace_sign" for o in onsets),
        "median_call_s": _median([r["elapsed_s"] for r in ok if r.get("elapsed_s") is not None]),
        "median_output_tokens": _median(
            [r["output_tokens"] for r in ok if r.get("output_tokens") is not None]
        ),
    }


def find_runs(runs_dir: Path) -> list[tuple[Path, str, str]]:
    found = []
    for run in sorted(runs_dir.iterdir()):
        clip, _, policy = run.name.rpartition("-")
        if policy in POLICIES and (run / "manifest.json").exists():
            found.append((run, clip, policy))
    return found


def totals(rows: list[dict]) -> list[str]:
    lines = []
    for policy in POLICIES:
        rs = [r for r in rows if r["policy"] == policy]
        if not rs:
            continue
        intervals = sorted({str(r["interval_s"]) for r in rs})
        lines.append(
            f"{policy} (interval {', '.join(intervals)} s, {len(rs)} runs): "
            f"{sum(r['calls'] for r in rs)} calls, "
            f"named {sum(r['windows_named'] for r in rs)}/{sum(r['windows'] for r in rs)} windows, "
            f"caught {sum(r['windows_caught'] for r in rs)}, "
            f"false mentions {sum(r['false_mentions_outside'] for r in rs)}, "
            f"onsets {sum(r['onsets'] for r in rs)}"
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("runs_dir", type=Path)
    parser.add_argument("--annotations", type=Path, default=ROOT / "data/annotations/pilot.csv")
    parser.add_argument("--tolerance-s", type=float, default=1.0)
    parser.add_argument("--out", type=Path, help="per-run CSV (default RUNS_DIR/quality.csv)")
    args = parser.parse_args(argv)

    annotations = read_annotations(args.annotations)
    rows = [
        score_run(run, clip, policy, annotations.get(clip, []), args.tolerance_s)
        for run, clip, policy in find_runs(args.runs_dir)
    ]
    if not rows:
        print(f"no <video_id>-<fixed|gated> runs with a manifest in {args.runs_dir}")
        return 1
    out = args.out or args.runs_dir / "quality.csv"
    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for r in rows:
        print(
            f"{r['clip']} {r['policy']}: {r['calls']} calls, named {r['windows_named']}/"
            f"{r['windows']}, false mentions {r['false_mentions_outside']}, "
            f"median call {r['median_call_s']} s"
        )
    print("\n".join(totals(rows)))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
