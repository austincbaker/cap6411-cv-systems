#!/usr/bin/env python3
"""Draw the report's pilot figures (Mac mini functional check) as PDF and PNG.

Reads only committed files: the per-run scores ``docs/report/data/pilot-2026-11-18.csv``
(``scripts/score_pilot_eval.py`` output), the call timeline
``docs/report/data/timeline-thumbs_mov_1.csv`` and ``data/annotations/pilot.csv``.
``--export-timeline RUNS_DIR`` rewrites the timeline file from a pass's
``thumbs_mov_1-fixed`` and ``thumbs_mov_1-gated`` runs first.

Writes calls_per_clip, named_per_clip and timeline_thumbs_mov_1 (.pdf and .png) to
``docs/report/figures``. No energy is drawn: these runs measured none.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/report"
SCORES = REPORT / "data/pilot-2026-11-18.csv"
TIMELINE_CLIP = "thumbs_mov_1"
TIMELINE = REPORT / f"data/timeline-{TIMELINE_CLIP}.csv"
ANNOTATIONS = ROOT / "data/annotations/pilot.csv"
OUT = REPORT / "figures"

POLICIES = ("fixed", "gated")
NAMES = {"fixed": "Fixed, every 2 s", "gated": "Gated, checks every 0.5 s"}
COLORS = {"fixed": "#f47230", "gated": "#257de0"}
INK, INK_2, GRID, WINDOW = "#191919", "#666666", "#e6e6e6", "#e9e9e9"
TAG = "Mac mini, functional check"
TOLERANCE_S = 1.0


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def export_timeline(runs_dir: Path, out: Path = TIMELINE) -> None:
    rows = []
    for policy in POLICIES:
        with (runs_dir / f"{TIMELINE_CLIP}-{policy}" / "requests.jsonl").open() as handle:
            for line in handle:
                r = json.loads(line)
                if r.get("source_time_s") is None:
                    continue
                rows.append(
                    {
                        "policy": policy,
                        "source_time_s": f"{r['source_time_s']:.3f}",
                        "status": r.get("status"),
                        "gesture": r.get("gesture") or "",
                        "gate_reason": r.get("gate_reason") or "",
                    }
                )
    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _style(plt) -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 7.5,
            "axes.edgecolor": INK_2,
            "axes.labelcolor": INK,
            "axes.linewidth": 0.6,
            "xtick.color": INK_2,
            "ytick.color": INK,
            "xtick.major.width": 0.6,
            "ytick.major.size": 0,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "pdf.fonttype": 42,
            "savefig.dpi": 200,
        }
    )


def _save(fig, name: str, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        meta = {"CreationDate": None} if ext == "pdf" else {"Software": None}
        fig.savefig(out / f"{name}.{ext}", bbox_inches="tight", pad_inches=0.03, metadata=meta)


def _by_clip(scores: list[dict]) -> tuple[list[str], dict]:
    table: dict[str, dict[str, dict]] = {}
    for row in scores:
        table.setdefault(row["clip"], {})[row["policy"]] = row
    # Shortest clips at the top, by the fixed policy's call count.
    clips = sorted(table, key=lambda c: (int(table[c]["fixed"]["calls"]), c), reverse=True)
    return clips, table


def _legend(ax, loc="lower right") -> None:
    ax.legend(loc=loc, frameon=False, handlelength=1.0, borderaxespad=0.2)


def calls_per_clip(plt, scores: list[dict], out: Path) -> None:
    clips, table = _by_clip(scores)
    fig, ax = plt.subplots(figsize=(3.3, 2.7))
    height = 0.38
    for i, policy in enumerate(POLICIES):
        offset = (0.5 - i) * height
        values = [int(table[c][policy]["calls"]) for c in clips]
        ys = [k + offset for k in range(len(clips))]
        ax.barh(ys, values, height=height - 0.04, color=COLORS[policy], label=NAMES[policy])
        for y, v in zip(ys, values):
            ax.text(v + 4, y, f"{v:,}", va="center", ha="left", fontsize=6.5, color=INK)
    totals = {p: sum(int(table[c][p]["calls"]) for c in clips) for p in POLICIES}
    ax.set_yticks(range(len(clips)), clips, fontsize=7)
    ax.set_xlabel("VLM calls per clip")
    ax.set_xlim(0, max(int(r["calls"]) for r in scores) * 1.15)
    ax.xaxis.grid(True, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.set_title(
        f"VLM calls: fixed {totals['fixed']:,}, gated {totals['gated']:,}\n{TAG}",
        fontsize=7.5,
        loc="left",
        color=INK,
    )
    _legend(ax, "upper right")
    _save(fig, "calls_per_clip", out)
    plt.close(fig)


def named_per_clip(plt, scores: list[dict], out: Path) -> None:
    clips, table = _by_clip(scores)
    clips = [c for c in clips if int(table[c]["fixed"]["windows"]) > 0]
    fig, ax = plt.subplots(figsize=(3.3, 2.5))
    height = 0.38
    for k, clip in enumerate(clips):
        windows = int(table[clip]["fixed"]["windows"])
        ax.barh(k, windows, height=0.86, color=WINDOW, zorder=0)
    for i, policy in enumerate(POLICIES):
        offset = (0.5 - i) * height
        values = [int(table[c][policy]["windows_named"]) for c in clips]
        ys = [k + offset for k in range(len(clips))]
        ax.barh(ys, values, height=height - 0.04, color=COLORS[policy], label=NAMES[policy])
    totals = {p: sum(int(table[c][p]["windows_named"]) for c in clips) for p in POLICIES}
    windows = sum(int(table[c]["fixed"]["windows"]) for c in clips)
    ax.set_yticks(range(len(clips)), clips, fontsize=7)
    ax.set_xticks([0, 1, 2])
    ax.set_xlim(0, 2.15)
    ax.set_xlabel("Gestures named (of annotated, ±1 s)")
    ax.set_title(
        f"Gestures named: fixed {totals['fixed']}/{windows}, gated {totals['gated']}/{windows}\n"
        f"{TAG}",
        fontsize=7.5,
        loc="left",
        color=INK,
    )
    from matplotlib.patches import Patch

    handles, _ = ax.get_legend_handles_labels()
    handles.append(Patch(color=WINDOW, label="Annotated gestures"))
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.4, -0.2),
        ncol=2,
        frameon=False,
        handlelength=1.0,
    )
    _save(fig, "named_per_clip", out)
    plt.close(fig)


def timeline(plt, rows: list[dict], windows: list[dict], out: Path) -> None:
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    end = max(float(r["source_time_s"]) for r in rows) + 4
    zooms = [(w["onset_s"] - 25, w["end_s"] + 25) for w in windows]
    fig = plt.figure(figsize=(7.0, 2.6))
    grid = fig.add_gridspec(2, len(zooms), height_ratios=[1, 1.15], hspace=0.75, wspace=0.12)
    axes = [fig.add_subplot(grid[0, :])] + [fig.add_subplot(grid[1, i]) for i in range(len(zooms))]
    lanes = {"gated": 1, "fixed": 0}
    for n, ax in enumerate(axes):
        lo, hi = (0, end) if n == 0 else zooms[n - 1]
        for w in windows:
            ax.axvspan(w["onset_s"], w["end_s"], color=WINDOW, zorder=0, linewidth=0)
            if n:
                for edge in (w["onset_s"] - TOLERANCE_S, w["end_s"] + TOLERANCE_S):
                    ax.axvline(edge, color=INK_2, linewidth=0.5, linestyle=":", zorder=0)
        for policy, lane in lanes.items():
            calls = [r for r in rows if r["policy"] == policy and r["status"] == "ok"]
            ts = [float(r["source_time_s"]) for r in calls if lo <= float(r["source_time_s"]) <= hi]
            ax.vlines(ts, lane - 0.32, lane + 0.32, color=COLORS[policy], linewidth=0.8)
            hits = [
                float(r["source_time_s"])
                for r in calls
                if r["gesture"] == "thumbs_up" and lo <= float(r["source_time_s"]) <= hi
            ]
            ax.plot(
                hits,
                [lane + 0.48] * len(hits),
                linestyle="none",
                marker="v",
                markersize=3.6 if n == 0 else 4.5,
                color=INK,
            )
        ax.set_ylim(-0.6, 1.75)
        ax.set_yticks([0, 1], ["Fixed", "Gated"])
        ax.set_xlim(lo, hi)
        ax.spines["left"].set_visible(False)
        if n == 0:
            ticks = range(0, int(end) + 1, 60)
            ax.set_xticks(list(ticks), [f"{t // 60}:00" for t in ticks])
            ax.set_xlabel("Video time (min:s)", labelpad=1)
            counts = {p: sum(r["policy"] == p and r["status"] == "ok" for r in rows) for p in lanes}
            ax.set_title(
                f"{TIMELINE_CLIP}: every VLM call (fixed {counts['fixed']}, gated "
                f"{counts['gated']}) against the annotated thumbs-ups\n{TAG}; fixed every 2 s, "
                "gated checks every 0.5 s",
                fontsize=7.5,
                loc="left",
                color=INK,
            )
        else:
            w = windows[n - 1]
            ax.set_xlabel("Video time (s)", labelpad=1)
            ax.set_title(
                f"Thumbs-up {n}: {w['onset_s']:.0f} to {w['end_s']:.0f} s",
                fontsize=7,
                loc="left",
                color=INK,
            )
            if n > 1:
                ax.set_yticklabels([])
    handles = [
        Line2D([], [], color=COLORS["fixed"], linewidth=1.2, label="Fixed call"),
        Line2D([], [], color=COLORS["gated"], linewidth=1.2, label="Gated call"),
        Line2D(
            [], [], color=INK, marker="v", linestyle="none", markersize=4, label="Answer: thumbs_up"
        ),
        Patch(color=WINDOW, label="Annotated thumbs-up"),
        Line2D([], [], color=INK_2, linestyle=":", linewidth=0.8, label="±1 s scoring tolerance"),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncol=5,
        frameon=False,
        bbox_to_anchor=(0.5, -0.1),
        handlelength=1.4,
    )
    _save(fig, f"timeline_{TIMELINE_CLIP}", out)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--scores", type=Path, default=SCORES)
    parser.add_argument("--timeline", type=Path, default=TIMELINE)
    parser.add_argument("--annotations", type=Path, default=ANNOTATIONS)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument(
        "--export-timeline",
        type=Path,
        metavar="RUNS_DIR",
        help=f"first rewrite --timeline from RUNS_DIR/{TIMELINE_CLIP}-{{fixed,gated}}",
    )
    args = parser.parse_args(argv)

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if args.export_timeline:
        export_timeline(args.export_timeline, args.timeline)
    _style(plt)
    scores = read_csv(args.scores)
    windows = [
        {"onset_s": float(r["onset_s"]), "end_s": float(r["end_s"])}
        for r in read_csv(args.annotations)
        if r["video_id"] == TIMELINE_CLIP
    ]
    calls_per_clip(plt, scores, args.out)
    named_per_clip(plt, scores, args.out)
    timeline(plt, read_csv(args.timeline), windows, args.out)
    print(f"wrote figures to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
