#!/usr/bin/env python3
"""Turn an energy suite folder into one CSV per run, one per condition, and the report figures.

    uv run python scripts/analyze_energy_suite.py runs/suite-YYYYMMDD-HHMM [--out DIR]

Reads every ``<run>/suite_run.json`` written by ``scripts/energy_suite.py`` (incomplete runs
are listed with ``complete=False`` and left out of the condition means) and writes, into
``--out`` (default ``<suite>/analysis``):

- ``runs.csv``        one row per run: energy per hour in each sensor domain, calls per hour,
                      median and p90 latency, peak server memory, gate_check quality
- ``conditions.csv``  per condition: mean and standard deviation across reps
- ``quality_vs_energy.png``, ``energy_per_hour.png``, ``calls_latency.png``

Energy domains stay separate (AGENTS.md): ``package`` is powermetrics CPU+GPU+ANE,
``system`` the SMC system-load telemetry and ``battery`` voltage x current while unplugged,
both whole laptop. The figures use one headline domain for the whole suite: battery when every
run has it, else system, else package; ``headline_domain`` in the CSVs says which.
Incremental energy is a run's mean power minus the mean idle-pipeline power of the same domain.
Unavailable values stay empty, never zero.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Optional

DOMAINS = ("battery", "system", "package")
DOMAIN_LABEL = {
    "battery": "whole laptop, battery V x I",
    "system": "whole laptop, SMC system load",
    "package": "SoC package, powermetrics",
}
DOMAIN_POWER = {
    "battery": "battery_mean_w",
    "system": "system_load_mean_w",
    "package": "package_combined_mean_w",
}
BLOCK_COLOR = {  # categorical slots in fixed order
    "main": "#257de0",
    "gate_sweep": "#f47230",
    "image": "#00b894",
    "quantization": "#f2a600",
}
TEXT = "#333333"
MUTED = "#8a8a8a"
GRID = "#e6e6e6"
RUN_COLUMNS = [
    "suite",
    "run",
    "condition",
    "block",
    "rep",
    "complete",
    "policy",
    "interval_s",
    "gate_threshold",
    "gate_persist_checks",
    "image_max_side",
    "max_tokens",
    "quant",
    "backend",
    "duration_s",
    "calls",
    "ok_calls",
    "calls_per_hour",
    "tick_skipped_busy",
    "latency_median_s",
    "latency_p90_s",
    "server_peak_rss_mb",
    "package_mean_w",
    "package_wh_per_hour",
    "package_cpu_j",
    "package_gpu_j",
    "package_ane_j",
    "package_j",
    "system_mean_w",
    "system_wh_per_hour",
    "system_j",
    "battery_mean_w",
    "battery_wh_per_hour",
    "battery_j",
    "battery_capacity_wh",
    "on_battery",
    "battery_percent_start",
    "battery_percent_end",
    "headline_domain",
    "energy_wh_per_hour",
    "incremental_w",
    "incremental_j_per_call",
    "windows",
    "windows_caught",
    "windows_named",
    "named_fraction",
    "outside_calls",
    "thermal_pressure",
    "power_source",
    "low_power_mode",
    "display_brightness",
]
SUMMARY_METRICS = [
    "calls_per_hour",
    "latency_median_s",
    "latency_p90_s",
    "server_peak_rss_mb",
    "package_wh_per_hour",
    "system_wh_per_hour",
    "battery_wh_per_hour",
    "energy_wh_per_hour",
    "incremental_w",
    "incremental_j_per_call",
    "windows_named",
    "named_fraction",
    "outside_calls",
]


def load_runs(suite: Path) -> list[dict]:
    records = []
    for path in sorted(suite.glob("*/suite_run.json")):
        records.append(json.loads(path.read_text()))
    return records


def per_hour(joules: Optional[float], seconds: float) -> Optional[float]:
    if joules is None or not seconds:
        return None
    return joules / 3600.0 / (seconds / 3600.0)  # Wh per hour of run time


def run_row(record: dict) -> dict:
    condition = record["condition"]
    args = condition.get("app_args", {})
    server = record.get("server_config", {})
    energy = record.get("energy", {})
    calls = record.get("calls", {})
    scores = record.get("scores") or {}
    seconds = record.get("window", {}).get("seconds") or 0.0
    state = record.get("state_before", {})
    row = {
        "suite": record["suite"],
        "run": record["name"],
        "condition": condition["name"],
        "block": record["block"],
        "rep": record["rep"],
        "complete": record.get("complete", False),
        "policy": condition["policy"],
        "interval_s": condition["interval_s"],
        "gate_threshold": args.get("gate_threshold"),
        "gate_persist_checks": args.get("gate_persist_checks"),
        "image_max_side": args.get("image_max_side"),
        "max_tokens": args.get("max_tokens"),
        "quant": server.get("quant"),
        "backend": server.get("backend"),
        "duration_s": seconds,
        "calls": calls.get("requests"),
        "ok_calls": calls.get("ok"),
        "calls_per_hour": calls.get("requests", 0) / seconds * 3600 if seconds else None,
        "tick_skipped_busy": calls.get("counts", {}).get("tick_skipped_busy", 0),
        "latency_median_s": calls.get("latency_median_s"),
        "latency_p90_s": calls.get("latency_p90_s"),
        "server_peak_rss_mb": energy.get("server_peak_rss_mb"),
        "package_mean_w": energy.get("package_combined_mean_w"),
        "package_wh_per_hour": energy.get("package_combined_mean_w"),
        "package_cpu_j": energy.get("package_cpu_j"),
        "package_gpu_j": energy.get("package_gpu_j"),
        "package_ane_j": energy.get("package_ane_j"),
        "package_j": energy.get("package_combined_j"),
        "system_mean_w": energy.get("system_load_mean_w"),
        "system_wh_per_hour": energy.get("system_load_mean_w"),
        "system_j": energy.get("system_load_j"),
        "battery_mean_w": energy.get("battery_mean_w"),
        "battery_wh_per_hour": per_hour(energy.get("battery_j"), seconds)
        if energy.get("battery_j") is not None
        else None,
        "battery_j": energy.get("battery_j"),
        "battery_capacity_wh": energy.get("battery_capacity_wh"),
        "on_battery": energy.get("on_battery"),
        "battery_percent_start": energy.get("battery_percent_start"),
        "battery_percent_end": energy.get("battery_percent_end"),
        "windows": scores.get("windows"),
        "windows_caught": scores.get("windows_caught"),
        "windows_named": scores.get("windows_named"),
        "named_fraction": scores["windows_named"] / scores["windows"]
        if scores.get("windows")
        else None,
        "outside_calls": scores.get("outside_calls"),
        "thermal_pressure": "|".join(energy.get("thermal_pressure") or []) or None,
        "power_source": state.get("power_source"),
        "low_power_mode": state.get("low_power_mode"),
        "display_brightness": (state.get("display_brightness") or {}).get("value"),
    }
    # Mean power in W equals Wh per hour; battery uses its own sample span, so prefer its mean.
    if row["battery_mean_w"] is not None:
        row["battery_wh_per_hour"] = row["battery_mean_w"]
    return row


def headline_domain(rows: list[dict]) -> Optional[str]:
    done = [r for r in rows if r["complete"]]
    for domain in DOMAINS:
        if done and all(r[f"{domain}_mean_w"] is not None for r in done):
            return domain
    return None


def add_derived(rows: list[dict]) -> Optional[str]:
    domain = headline_domain(rows)
    idle = [
        r[f"{domain}_mean_w"]
        for r in rows
        if domain and r["complete"] and r["policy"] == "idle" and r[f"{domain}_mean_w"] is not None
    ]
    idle_w = statistics.mean(idle) if idle else None
    for row in rows:
        row["headline_domain"] = domain
        value = row.get(f"{domain}_mean_w") if domain else None
        row["energy_wh_per_hour"] = value
        if value is not None and idle_w is not None and row["policy"] != "idle":
            row["incremental_w"] = value - idle_w
            row["incremental_j_per_call"] = (
                row["incremental_w"] * row["duration_s"] / row["calls"] if row["calls"] else None
            )
        else:
            row["incremental_w"] = row["incremental_j_per_call"] = None
    return domain


def summarize(rows: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        if row["complete"]:
            groups.setdefault(row["condition"], []).append(row)
    out = []
    for name, members in groups.items():
        first = members[0]
        summary = {
            "condition": name,
            "block": first["block"],
            "policy": first["policy"],
            "interval_s": first["interval_s"],
            "reps": len(members),
            "headline_domain": first["headline_domain"],
        }
        for metric in SUMMARY_METRICS:
            values = [r[metric] for r in members if r[metric] is not None]
            summary[f"{metric}_mean"] = statistics.mean(values) if values else None
            summary[f"{metric}_sd"] = statistics.stdev(values) if len(values) > 1 else None
            summary[f"{metric}_min"] = min(values) if values else None
            summary[f"{metric}_max"] = max(values) if values else None
        out.append(summary)
    return out


def write_csv(path: Path, rows: list[dict], columns: Optional[list[str]] = None) -> None:
    columns = columns or (list(rows[0]) if rows else [])
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "" if row.get(k) is None else row[k] for k in columns})


# ============================================================================ figures


def _axes_style(ax) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=TEXT, labelsize=8)
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def figures(summary: list[dict], domain: Optional[str], out: Path, title: str) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    written = []
    order = sorted(summary, key=lambda s: (list(BLOCK_COLOR).index(s["block"]), s["condition"]))
    names = [s["condition"] for s in order]
    colors = [BLOCK_COLOR.get(s["block"], MUTED) for s in order]
    unit = f"Wh per hour ({DOMAIN_LABEL[domain]})" if domain else "energy unavailable"
    blocks = [b for b in BLOCK_COLOR if any(s["block"] == b for s in order)]

    def legend(ax) -> None:
        if len(blocks) > 1:
            handles = [
                plt.Line2D([], [], marker="s", linestyle="", color=BLOCK_COLOR[b], label=b)
                for b in blocks
            ]
            ax.legend(
                handles=handles,
                frameon=False,
                fontsize=8,
                labelcolor=TEXT,
                loc="upper left",
                bbox_to_anchor=(1.02, 1.0),
            )

    # Quality vs energy: one point per non-idle condition, whiskers = min..max across reps.
    fig, ax = plt.subplots(figsize=(6.0, 4.0), dpi=200)
    _axes_style(ax)
    idle = [s for s in order if s["policy"] == "idle"]
    plotted = sorted(
        (s for s in order if s["energy_wh_per_hour_mean"] is not None),
        key=lambda s: s["energy_wh_per_hour_mean"],
    )
    x_max = max((s["energy_wh_per_hour_mean"] for s in plotted), default=0.0)
    for rank, s in enumerate(plotted):
        if (
            s["policy"] == "idle"
            or s["energy_wh_per_hour_mean"] is None
            or s["named_fraction_mean"] is None
        ):
            continue
        x, y = s["energy_wh_per_hour_mean"], s["named_fraction_mean"]
        xerr = [[x - s["energy_wh_per_hour_min"]], [s["energy_wh_per_hour_max"] - x]]
        yerr = [[y - s["named_fraction_min"]], [s["named_fraction_max"] - y]]
        color = BLOCK_COLOR.get(s["block"], MUTED)
        ax.errorbar(
            x,
            y,
            xerr=xerr,
            yerr=yerr,
            fmt="o",
            markersize=7,
            color=color,
            ecolor=color,
            elinewidth=1.2,
            capsize=0,
            markeredgecolor="white",
            markeredgewidth=1.5,
        )
        right = x > 0.75 * x_max  # label points near the right edge on their left
        ax.annotate(
            s["condition"],
            (x, y),
            xytext=(-6 if right else 6, 6 if rank % 2 else -12),  # alternate above/below
            textcoords="offset points",
            ha="right" if right else "left",
            fontsize=7,
            color=TEXT,
        )
    if idle and idle[0]["energy_wh_per_hour_mean"] is not None:
        ax.axvline(idle[0]["energy_wh_per_hour_mean"], color=MUTED, linestyle="--", linewidth=1)
        ax.annotate(
            "idle pipeline",
            (idle[0]["energy_wh_per_hour_mean"], 0.02),
            xytext=(4, 0),
            textcoords="offset points",
            fontsize=7,
            color=MUTED,
        )
    ax.set_xlabel(unit, fontsize=8, color=TEXT)
    ax.set_ylabel("annotated gestures named (fraction)", fontsize=8, color=TEXT)
    ax.set_ylim(0, 1.05)
    ax.set_title(f"Quality vs energy, {title}", fontsize=9, color=TEXT, loc="left")
    legend(ax)
    fig.tight_layout()
    path = out / "quality_vs_energy.png"
    fig.savefig(path)
    plt.close(fig)
    written.append(path)

    # Energy per hour: whole laptop (headline) and package, side by side, one bar per condition.
    panels = [d for d in ("system" if domain == "package" else domain, "package") if d]
    panels = list(dict.fromkeys(panels))
    fig, axes = plt.subplots(
        1, len(panels), figsize=(3.4 * len(panels), 0.35 * len(order) + 1.2), dpi=200, squeeze=False
    )
    for ax, panel in zip(axes[0], panels):
        _axes_style(ax)
        ax.grid(axis="y", visible=False)
        key = f"{panel}_wh_per_hour"
        values = [s[f"{key}_mean"] for s in order]
        ax.barh(
            names,
            [v or 0 for v in values],
            color=colors,
            height=0.6,
            edgecolor="white",
            linewidth=2,
        )
        for i, (s, v) in enumerate(zip(order, values)):
            if v is None:
                ax.annotate(
                    "n/a",
                    (0, i),
                    xytext=(3, -3),
                    textcoords="offset points",
                    fontsize=7,
                    color=MUTED,
                )
                continue
            lo, hi = s[f"{key}_min"], s[f"{key}_max"]
            ax.plot([lo, hi], [i, i], color=TEXT, linewidth=1)
            ax.annotate(
                f"{v:.2f}",
                (hi, i),
                xytext=(4, -3),
                textcoords="offset points",
                fontsize=7,
                color=TEXT,
            )
        ax.invert_yaxis()
        ax.margins(x=0.18)
        ax.set_xlabel(f"Wh per hour ({DOMAIN_LABEL[panel]})", fontsize=8, color=TEXT)
    axes[0][0].set_title(f"Energy per hour, {title}", fontsize=9, color=TEXT, loc="left")
    legend(axes[0][-1])
    fig.tight_layout()
    path = out / "energy_per_hour.png"
    fig.savefig(path)
    plt.close(fig)
    written.append(path)

    # Calls per hour and latency (median bar, p90 tick), non-idle conditions.
    active = [s for s in order if s["policy"] != "idle"]
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 0.35 * max(1, len(active)) + 1.2), dpi=200)
    labels = [s["condition"] for s in active]
    for ax in axes:
        _axes_style(ax)
        ax.grid(axis="y", visible=False)
    calls = [s["calls_per_hour_mean"] or 0 for s in active]
    axes[0].barh(
        labels,
        calls,
        color=[BLOCK_COLOR.get(s["block"], MUTED) for s in active],
        height=0.6,
        edgecolor="white",
        linewidth=2,
    )
    for i, v in enumerate(calls):
        axes[0].annotate(
            f"{v:.0f}", (v, i), xytext=(4, -3), textcoords="offset points", fontsize=7, color=TEXT
        )
    axes[0].set_xlabel("VLM calls per hour", fontsize=8, color=TEXT)
    median = [s["latency_median_s_mean"] or 0 for s in active]
    p90 = [s["latency_p90_s_mean"] for s in active]
    axes[1].barh(
        labels,
        median,
        color=[BLOCK_COLOR.get(s["block"], MUTED) for s in active],
        height=0.6,
        edgecolor="white",
        linewidth=2,
    )
    for i, (m, p) in enumerate(zip(median, p90)):
        if p is not None:
            axes[1].plot([p, p], [i - 0.3, i + 0.3], color=TEXT, linewidth=2)
        axes[1].annotate(
            f"{m:.2f}" + (f" / p90 {p:.2f}" if p is not None else ""),
            (max(m, p or 0), i),
            xytext=(4, -3),
            textcoords="offset points",
            fontsize=7,
            color=TEXT,
        )
    axes[1].set_yticklabels([])
    axes[1].set_xlabel("call latency, s (bar median, tick p90)", fontsize=8, color=TEXT)
    for ax in axes:
        ax.invert_yaxis()
        ax.margins(x=0.3)
    axes[0].set_title(f"Calls and latency, {title}", fontsize=9, color=TEXT, loc="left")
    fig.tight_layout()
    path = out / "calls_latency.png"
    fig.savefig(path)
    plt.close(fig)
    written.append(path)
    return written


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("suite", type=Path)
    parser.add_argument("--out", type=Path, help="output folder (default <suite>/analysis)")
    parser.add_argument("--no-figures", action="store_true")
    args = parser.parse_args(argv)
    records = load_runs(args.suite)
    if not records:
        print(f"no suite_run.json under {args.suite}", file=sys.stderr)
        return 2
    rows = [run_row(r) for r in records]
    domain = add_derived(rows)
    summary = summarize(rows)
    out = args.out or args.suite / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "runs.csv", rows, RUN_COLUMNS)
    write_csv(out / "conditions.csv", summary)
    print(
        f"{len(rows)} runs ({sum(r['complete'] for r in rows)} complete), headline energy: "
        f"{DOMAIN_LABEL.get(domain, 'unavailable')}"
    )
    for s in summary:
        e = s["energy_wh_per_hour_mean"]
        print(
            f"  {s['condition']:28s} n={s['reps']}  calls/h {s['calls_per_hour_mean'] or 0:7.0f}  "
            f"energy {'-' if e is None else f'{e:.2f}'} Wh/h  named {s['windows_named_mean']}"
        )
    if not args.no_figures:
        for path in figures(summary, domain, out, args.suite.name):
            print(f"  wrote {path}")
    print(f"  wrote {out / 'runs.csv'}, {out / 'conditions.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
