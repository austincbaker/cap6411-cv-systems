#!/usr/bin/env python3
"""Write the report's energy results section (5.2) from one or more energy suite folders.

    uv run python scripts/energy_report_section.py runs/suite-A runs/report-B \
        --out docs/report/5.2-energy-results.md --figures docs/report/figures/5.2

Conclusions use the SoC package (powermetrics) and whole-laptop SMC system load domains only.
Battery V x I is listed for completeness but not used: on identical runs it swung between
3.4 and 15.6 W (suite-20261127-2017), far more than the effects measured here. Every table gives
mean ± standard deviation across reps (n per row); incremental values are a condition's mean
power minus the same suite's mean idle power in the same domain. Domains are never mixed.
"""

from __future__ import annotations

import argparse
import copy
import json
import statistics
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
from scripts import analyze_energy_suite as analysis  # noqa: E402

DOMAINS = ("package", "system")
LABEL = {"package": "package W", "system": "system W"}


def load(suite: Path) -> dict:
    records = analysis.load_runs(suite)
    base = [analysis.run_row(r) for r in records]
    by_domain = {}
    for domain in DOMAINS:
        rows = copy.deepcopy(base)
        # A short run can miss the once-a-minute SMC update: leave such a run out of this
        # domain's statistics only, never count its missing value as zero.
        for r in rows:
            r["complete"] = r["complete"] and r[f"{domain}_mean_w"] is not None
        analysis.add_derived(rows, domain)
        by_domain[domain] = rows
    manifest_path = suite / "suite_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    return {"name": suite.name, "path": suite, "rows": by_domain, "manifest": manifest}


def stats(values: list[float]) -> Optional[tuple[float, Optional[float], int]]:
    values = [v for v in values if v is not None]
    if not values:
        return None
    return (
        statistics.mean(values),
        statistics.stdev(values) if len(values) > 1 else None,
        len(values),
    )


def fmt(s, digits: int = 2) -> str:
    if s is None:
        return "–"
    mean, sd, _ = s
    return f"{mean:.{digits}f}" + ("" if sd is None else f" ± {sd:.{digits}f}")


def condition_table(suite: dict) -> dict[str, dict]:
    """Per condition: block, settings and stats for every metric the section uses."""
    out: dict[str, dict] = {}
    for domain in DOMAINS:
        for r in suite["rows"][domain]:
            if not r["complete"]:
                continue
            entry = out.setdefault(
                r["condition"],
                {
                    "condition": r["condition"],
                    "block": r["block"],
                    "policy": r["policy"],
                    "interval_s": r["interval_s"],
                    "image_max_side": r["image_max_side"],
                    "gate_threshold": r["gate_threshold"],
                    "budget_wh_per_hour": [],
                    "duration_s": [],
                    "values": {},
                },
            )
            v = entry["values"]
            v.setdefault(f"{domain}_w", []).append(r[f"{domain}_mean_w"])
            v.setdefault(f"{domain}_inc_w", []).append(r["incremental_w"])
            v.setdefault(f"{domain}_j_call", []).append(r["incremental_j_per_call"])
            if domain == "package":
                v.setdefault("calls_h", []).append(r["calls_per_hour"])
                v.setdefault("latency", []).append(r["latency_median_s"])
                v.setdefault("named", []).append(r["windows_named"])
                v.setdefault("windows", []).append(r["windows"])
                v.setdefault("battery_w", []).append(r["battery_mean_w"])
                v.setdefault("rss", []).append(r["server_peak_rss_mb"])
                entry["budget_wh_per_hour"].append(r["budget_wh_per_hour"])
                entry["duration_s"].append(r["duration_s"])
    for entry in out.values():
        entry["stats"] = {k: stats(v) for k, v in entry["values"].items()}
        entry["n"] = max((s[2] for s in entry["stats"].values() if s), default=0)
    return out


def row(entry: dict, label: Optional[str] = None) -> str:
    s = entry["stats"]
    named = s.get("named")
    windows = s.get("windows")
    quality = "–" if named is None else f"{named[0]:.2f}/{windows[0]:.0f}" if windows else "–"
    return (
        f"| {label or entry['condition']} | {entry['n']} | {fmt(s.get('calls_h'), 0)} | "
        f"{fmt(s.get('package_w'))} | {fmt(s.get('package_inc_w'))} | "
        f"{fmt(s.get('package_j_call'), 1)} | {fmt(s.get('system_w'))} | "
        f"{fmt(s.get('system_inc_w'))} | {fmt(s.get('latency'))} | {quality} |"
    )


HEADER = (
    "| Condition | n | Calls/h | Package W | Package Δ W | Package Δ J/call | System W | "
    "System Δ W | Median latency s | Gestures named |\n"
    "|---|---|---|---|---|---|---|---|---|---|"
)


def table(entries: list[dict]) -> str:
    return "\n".join([HEADER] + [row(e) for e in entries])


def pick(conditions: dict, names: list[str]) -> list[dict]:
    return [conditions[n] for n in names if n in conditions]


def mean_of(entry: Optional[dict], key: str) -> Optional[float]:
    if not entry or not entry["stats"].get(key):
        return None
    return entry["stats"][key][0]


def pct(a: Optional[float], b: Optional[float]) -> str:
    if a is None or b is None or b == 0:
        return "–"
    return f"{(1 - a / b) * 100:.0f}%"


def scatter(suites: list[dict], out: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(10, 4), dpi=150)
    for ax, domain in zip(axes, DOMAINS):
        for suite in suites:
            for entry in condition_table(suite).values():
                s = entry["stats"]
                if not s.get("calls_h") or not s.get(f"{domain}_w"):
                    continue
                color = analysis.BLOCK_COLOR.get(entry["block"], analysis.MUTED)
                x, y = s["calls_h"][0], s[f"{domain}_w"][0]
                ax.errorbar(
                    x,
                    y,
                    yerr=s[f"{domain}_w"][1] or 0,
                    fmt="o",
                    color=color,
                    ms=4,
                    capsize=2,
                    lw=1,
                )
        ax.set_xlabel("VLM calls per hour", fontsize=8)
        ax.set_ylabel(f"mean power, W ({analysis.DOMAIN_LABEL[domain]})", fontsize=8)
        analysis._axes_style(ax)
    blocks = [
        b
        for b in analysis.BLOCK_COLOR
        if any(e["block"] == b for s in suites for e in condition_table(s).values())
    ]
    handles = [
        plt.Line2D([], [], marker="o", ls="", color=analysis.BLOCK_COLOR[b], label=b)
        for b in blocks
    ]
    axes[1].legend(handles=handles, frameon=False, fontsize=7, loc="upper left")
    fig.suptitle("Power against call rate, every condition (mean ± sd over reps)", fontsize=9)
    fig.tight_layout()
    path = out / "power_vs_calls.png"
    fig.savefig(path)
    plt.close(fig)
    return path


def setup_lines(suite: dict) -> list[str]:
    m = suite["manifest"]
    machine = (m.get("system_state") or {}).get("machine") or {}
    rows = [r for r in suite["rows"]["package"]]
    complete = [r for r in rows if r["complete"]]
    starts = [r["battery_percent_start"] for r in rows if r["battery_percent_start"] is not None]
    lines = [
        f"- **{suite['name']}**: {len(complete)} of {len(rows)} runs complete; "
        f"replay length {m.get('duration_s_override') or 'full clip'} s, cooldown "
        f"{m.get('cooldown_s')} s; commit `{(m.get('git_commit') or '?')[:7]}`; "
        f"{machine.get('chip') or '?'} ({machine.get('model') or '?'}, macOS "
        f"{machine.get('macos') or '?'})."
    ]
    if starts:
        lines.append(
            f"  Battery from {max(starts):.0f}% to {min(starts):.0f}% at run starts "
            "(unplugged throughout)."
        )
    tc = m.get("test_conditions")
    if tc:
        lines.append(
            "  Machine prepared by the wrapper: "
            + "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in tc.items() if k != "log")
            + "."
        )
    battery = [r["battery_mean_w"] for r in complete if r["battery_mean_w"] is not None]
    if battery:
        lines.append(
            f"  Battery V x I ranged {min(battery):.1f}–{max(battery):.1f} W across runs and "
            "is not used for conclusions."
        )
    return lines


def write_section(suites: list[dict], out: Path, figures: Path) -> None:
    figures.mkdir(parents=True, exist_ok=True)
    md = ["# 5.2 Energy results (Apple M2 MacBook Pro)", ""]
    md += [
        "Generated by `scripts/energy_report_section.py` from the suite folders below "
        "(not committed; zipped to the team Drive). Package W is powermetrics CPU+GPU+ANE "
        "(SoC package only); system W is the SMC whole-laptop system load (updates about once "
        "a minute, so a 3-minute run has about 3 samples). Δ is above the same suite's idle "
        "pipeline (camera replay, gate, loaded idle server). Values are mean ± sd across reps; "
        "n is the number of complete reps. Battery V x I is excluded: it swung 3.4–15.6 W on "
        "identical runs.",
        "",
        "## Setup",
        "",
    ]
    for suite in suites:
        md += setup_lines(suite)
    md.append("")

    latest = suites[-1]
    c = condition_table(latest)
    fixed, gated, idle = c.get("fixed_2s"), c.get("gated_0.5s"), c.get("idle")
    md += ["## Key numbers", ""]
    if fixed and gated:
        md += [
            f"- Gated 0.5 s against fixed 2 s ({latest['name']}): package power "
            f"{fmt(gated['stats'].get('package_w'))} W vs {fmt(fixed['stats'].get('package_w'))} W "
            f"({pct(mean_of(gated, 'package_w'), mean_of(fixed, 'package_w'))} lower); above idle "
            f"{fmt(gated['stats'].get('package_inc_w'))} W vs "
            f"{fmt(fixed['stats'].get('package_inc_w'))} W "
            f"({pct(mean_of(gated, 'package_inc_w'), mean_of(fixed, 'package_inc_w'))} lower). "
            f"System load {fmt(gated['stats'].get('system_w'))} W vs "
            f"{fmt(fixed['stats'].get('system_w'))} W "
            f"({pct(mean_of(gated, 'system_w'), mean_of(fixed, 'system_w'))} lower).",
            f"- Calls per hour: {fmt(gated['stats'].get('calls_h'), 0)} gated vs "
            f"{fmt(fixed['stats'].get('calls_h'), 0)} fixed; gestures named "
            f"{fmt(gated['stats'].get('named'))} vs {fmt(fixed['stats'].get('named'))} "
            f"of {mean_of(fixed, 'windows') or 0:.0f} annotated in the replayed span.",
        ]
    if idle:
        md.append(
            f"- Idle pipeline: package {fmt(idle['stats'].get('package_w'))} W, system "
            f"{fmt(idle['stats'].get('system_w'))} W."
        )
    if fixed:
        md.append(
            f"- Energy per full-size call above idle (fixed 2 s): package "
            f"{fmt(fixed['stats'].get('package_j_call'), 1)} J, system "
            f"{fmt(fixed['stats'].get('system_j_call'), 1)} J."
        )
    md.append("")

    sections = [
        ("Main matrix", ["idle", "fixed_2s", "gated_0.5s"]),
        ("Fixed-interval sweep", ["fixed_1s", "fixed_2s", "fixed_4s", "fixed_8s"]),
        (
            "Sent image size (longer side, px)",
            [
                "fixed_2s_px256",
                "fixed_2s_px384",
                "fixed_2s_px512",
                "fixed_2s",
                "gated_0.5s_px256",
                "gated_0.5s_px384",
                "gated_0.5s_px512",
                "gated_0.5s",
            ],
        ),
        (
            "Gate settings (check interval, threshold; default threshold 0.3)",
            ["gated_0.25s", "gated_0.5s", "gated_1s", "gated_0.5s_t0.2", "gated_0.5s_t0.1"],
        ),
        ("Full clip (9.7 min)", ["full_gated_0.5s", "full_fixed_2s"]),
    ]
    for suite in suites:
        conditions = condition_table(suite)
        md += [f"## {suite['name']}", ""]
        shown: set[str] = set()
        for title, names in sections:
            entries = pick(conditions, names)
            if not entries or (
                title != "Main matrix" and all(e["block"] == "main" for e in entries)
            ):
                continue
            md += [f"### {title}", "", table(entries), ""]
            shown |= {e["condition"] for e in entries}
        budget = sorted(
            (e for e in conditions.values() if e["policy"] == "budget"),
            key=lambda e: -(stats(e["budget_wh_per_hour"]) or (0,))[0],
        )
        if budget:
            md += [
                "### Energy-budget controller (budget is VLM power above idle)",
                "",
                "| Condition | n | Budget W | Package Δ W | System Δ W | Calls/h | Gestures named |",
                "|---|---|---|---|---|---|---|",
            ]
            for e in budget:
                s = e["stats"]
                md.append(
                    f"| {e['condition']} | {e['n']} | {fmt(stats(e['budget_wh_per_hour']), 3)} | "
                    f"{fmt(s.get('package_inc_w'))} | {fmt(s.get('system_inc_w'))} | "
                    f"{fmt(s.get('calls_h'), 0)} | {fmt(s.get('named'))} |"
                )
            md.append("")
            shown |= {e["condition"] for e in budget}
        rest = [e for n, e in sorted(conditions.items()) if n not in shown]
        if rest:
            md += ["### Other conditions", "", table(rest), ""]

    md += ["## Figures", ""]
    path = scatter(suites, figures)
    md += [f"![Power against call rate]({relative(path, out)})", ""]
    for suite in suites:
        for sub in ("analysis-package", "analysis-system"):
            folder = suite["path"] / sub
            for png in sorted(folder.glob("*.png")):
                target = figures / f"{suite['name']}_{sub.split('-')[1]}_{png.name}"
                target.write_bytes(png.read_bytes())
                md += [f"![{suite['name']} {sub} {png.stem}]({relative(target, out)})", ""]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md).rstrip() + "\n")


def relative(path: Path, out: Path) -> str:
    try:
        return str(path.resolve().relative_to(out.parent.resolve()))
    except ValueError:
        return str(path)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("suites", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "docs/report/5.2-energy-results.md")
    parser.add_argument("--figures", type=Path, default=ROOT / "docs/report/figures/5.2")
    args = parser.parse_args(argv)
    suites = [load(s) for s in args.suites]
    write_section(suites, args.out, args.figures)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
