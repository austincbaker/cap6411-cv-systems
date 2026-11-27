"""Energy suite planning, commands and analysis, plus the app's idle policy and image shrinking.
No model, camera, sudo or powermetrics needed."""

from __future__ import annotations

import copy
import csv
import json
from pathlib import Path

import numpy as np
import pytest

from app.main import BaselineRun, parse_args, shrink_to
from scripts import analyze_energy_suite as analyze
from scripts import energy_suite as suite
from tests.fakes.fake_llama import FakeLlama
from tests.fakes.video import write_test_video

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "configs/energy_suite.json").read_text())
PROFILE = json.loads((ROOT / "configs/inference.json").read_text())


def all_blocks() -> dict:
    config = copy.deepcopy(CONFIG)
    for block in config["blocks"].values():
        block["enabled"] = True
    return config


def test_default_matrix_interleaves_and_rotates_reps():
    runs = suite.expand(CONFIG)
    assert [r["name"] for r in runs] == [
        "idle_1",
        "fixed_2s_1",
        "gated_0.5s_1",
        "fixed_2s_2",
        "gated_0.5s_2",
        "idle_2",
        "gated_0.5s_3",
        "idle_3",
        "fixed_2s_3",
    ]
    assert {r["block"] for r in runs} == {"main"}


def test_optional_blocks_expand_to_their_grids():
    runs = suite.expand(all_blocks())
    by_block: dict[str, list] = {}
    for run in runs:
        by_block.setdefault(run["block"], []).append(run)
    assert len(by_block["gate_sweep"]) == 6
    assert len(by_block["image"]) == 4
    assert len(by_block["quantization"]) == 2
    sweep = by_block["gate_sweep"][0]["condition"]
    assert sweep["policy"] == "gated" and sweep["app_args"]["gate_persist_checks"] == 3
    quant = by_block["quantization"][0]["condition"]
    assert quant["server"]["quant"] == "Q4_K_M" and quant["name"] == "fixed_2s_Q4_K_M"
    assert len({r["name"] for r in runs}) == len(runs)


def test_runtime_estimate_counts_server_start_and_cooldown():
    runs = suite.expand(CONFIG)
    plan = suite.estimate(runs, 585.0, 90.0)
    assert plan["per_run_s"] == 585.0 + suite.SERVER_START_S + 90.0
    assert plan["total_s"] == pytest.approx(9 * plan["per_run_s"])
    assert suite.hms(plan["total_s"]) == "1 h 44 min"


def test_app_command_passes_interval_and_condition_args(tmp_path):
    run = next(r for r in suite.expand(all_blocks()) if r["block"] == "image")
    command = suite.app_command(run, Path("clip.mov"), Path("p.json"), tmp_path / "app", 30.0)
    assert command[command.index("--interval-s") + 1] == "2.0"
    assert command[command.index("--policy") + 1] == "fixed_interval"
    assert "--max-tokens" in command and "--image-max-side" in command
    assert command[command.index("--telemetry") + 1] == "off"
    assert command[-2:] == ["--duration-s", "30.0"]


def test_server_command_backends_and_quant_files(tmp_path):
    paths = suite.cache_paths(tmp_path, tmp_path / "models", PROFILE)
    metal = suite.server_command(paths, PROFILE, {"backend": "metal", "quant": "Q8_0"})
    assert metal[metal.index("--gpu-layers") + 1] == "99"
    assert "--device" not in metal
    assert metal[metal.index("--alias") + 1] == PROFILE["model_alias"]
    cpu = suite.server_command(paths, PROFILE, {"backend": "cpu", "quant": "Q4_K_M"})
    assert cpu[cpu.index("--device") + 1] == "none"
    assert cpu[cpu.index("--model") + 1].endswith("SmolVLM2-500M-Video-Instruct-Q4_K_M.gguf")
    assert cpu[cpu.index("--alias") + 1] == "smolvlm2-500m-q4_k_m"


def test_latency_stats_ignore_failed_calls():
    requests = [{"status": "ok", "elapsed_s": float(v)} for v in range(1, 11)]
    requests.append({"status": "timeout", "elapsed_s": 120.0})
    stats = suite.latency_stats(requests)
    assert stats["latency_median_s"] == 5.5
    assert stats["latency_p90_s"] == 9.0
    assert stats["latency_max_s"] == 10.0
    assert suite.latency_stats([])["latency_median_s"] is None


def test_shrink_to_keeps_aspect_and_never_enlarges():
    image = np.zeros((720, 1280, 3), np.uint8)
    assert shrink_to(image, 640).shape == (360, 640, 3)
    assert shrink_to(image, 2000) is image
    assert shrink_to(image, None) is image


def _run(tmp_path, *extra):
    tmp_path.mkdir(parents=True, exist_ok=True)
    clip = write_test_video(tmp_path / "clip.avi", frames=30, fps=20.0)
    config = parse_args(
        [
            "--source", "replay", "--video", str(clip), "--no-display",
            "--run-dir", str(tmp_path / "run"), "--telemetry", "off", *extra,
        ]
    )  # fmt: skip
    llama = FakeLlama()
    result = BaselineRun(config, client=llama.client(), server_idle=lambda: True).run()
    return result, llama


def test_idle_policy_runs_the_gate_but_never_sends(tmp_path):
    result, llama = _run(tmp_path, "--policy", "idle", "--interval-s", "0.25")
    assert result.exit_code == 0
    assert llama.completions == []
    assert (result.run_dir / "requests.jsonl").read_text() == ""
    drops = [json.loads(line) for line in (result.run_dir / "drops.jsonl").read_text().splitlines()]
    idle = [d for d in drops if d["reason"] == "idle_no_call"]
    assert idle and idle[0]["detail"] == "gate_initial"
    assert all("gate_score" in d for d in idle)
    assert result.manifest["policy"] == "idle" and result.manifest["gate"] is not None


def test_image_max_side_shrinks_the_sent_frame(tmp_path):
    full, _ = _run(tmp_path / "a", "--interval-s", "0.5")
    small, _ = _run(tmp_path / "b", "--interval-s", "0.5", "--image-max-side", "16")

    def mean_bytes(result):
        records = (result.run_dir / "requests.jsonl").read_text().splitlines()
        sizes = [json.loads(line)["image_bytes"] for line in records]
        return sum(sizes) / len(sizes)

    assert mean_bytes(small) < mean_bytes(full)


# ============================================================================ analysis


def fake_record(
    name, condition, rep, *, package_w, system_w, battery_w, calls, named, seconds=600.0
):
    return {
        "suite": "suite-test",
        "name": f"{name}_{rep}",
        "block": "main",
        "rep": rep,
        "complete": True,
        "condition": condition,
        "server_config": {"backend": "metal", "quant": "Q8_0"},
        "window": {"seconds": seconds},
        "energy": {
            "package_combined_mean_w": package_w,
            "package_combined_j": package_w * seconds,
            "system_load_mean_w": system_w,
            "system_load_j": system_w * seconds,
            "battery_mean_w": battery_w,
            "battery_j": None if battery_w is None else battery_w * seconds,
            "on_battery": battery_w is not None,
            "server_peak_rss_mb": 900.0,
            "thermal_pressure": ["Nominal"],
        },
        "calls": {
            "requests": calls,
            "ok": calls,
            "counts": {},
            "latency_median_s": 0.5 if calls else None,
            "latency_p90_s": 0.8 if calls else None,
        },
        "scores": {
            "windows": 2,
            "windows_caught": named,
            "windows_named": named,
            "outside_calls": 3,
        },
        "state_before": {"power_source": "Battery Power", "low_power_mode": False},
    }


def write_suite(tmp_path, battery=True) -> Path:
    suite_dir = tmp_path / "suite-test"
    conditions = {c["name"]: c for c in CONFIG["conditions"]}
    specs = {
        "idle": dict(package_w=1.0, system_w=5.0, calls=0, named=0),
        "fixed_2s": dict(package_w=4.0, system_w=9.0, calls=290, named=2),
        "gated_0.5s": dict(package_w=1.5, system_w=6.0, calls=30, named=2),
    }
    for name, spec in specs.items():
        for rep in (1, 2):
            battery_w = (spec["system_w"] + 0.5) if battery else None
            record = fake_record(name, conditions[name], rep, battery_w=battery_w, **spec)
            (suite_dir / record["name"]).mkdir(parents=True)
            (suite_dir / record["name"] / "suite_run.json").write_text(json.dumps(record))
    return suite_dir


def test_analysis_writes_csvs_with_incremental_energy(tmp_path):
    suite_dir = write_suite(tmp_path)
    assert analyze.main([str(suite_dir), "--no-figures"]) == 0
    rows = list(csv.DictReader((suite_dir / "analysis/runs.csv").open()))
    assert len(rows) == 6 and {r["headline_domain"] for r in rows} == {"battery"}
    fixed = next(r for r in rows if r["condition"] == "fixed_2s")
    assert float(fixed["energy_wh_per_hour"]) == pytest.approx(9.5)
    assert float(fixed["incremental_w"]) == pytest.approx(4.0)
    assert float(fixed["incremental_j_per_call"]) == pytest.approx(4.0 * 600 / 290)
    assert float(fixed["calls_per_hour"]) == pytest.approx(290 * 6)
    idle = next(r for r in rows if r["condition"] == "idle")
    assert idle["incremental_w"] == "" and idle["latency_median_s"] == ""
    summary = list(csv.DictReader((suite_dir / "analysis/conditions.csv").open()))
    gated = next(s for s in summary if s["condition"] == "gated_0.5s")
    assert gated["reps"] == "2" and float(gated["named_fraction_mean"]) == 1.0


def test_analysis_falls_back_to_system_load_and_draws_figures(tmp_path):
    suite_dir = write_suite(tmp_path, battery=False)
    assert analyze.main([str(suite_dir), "--out", str(tmp_path / "out")]) == 0
    rows = list(csv.DictReader((tmp_path / "out/runs.csv").open()))
    assert {r["headline_domain"] for r in rows} == {"system"}
    for name in ("quality_vs_energy.png", "energy_per_hour.png", "calls_latency.png"):
        assert (tmp_path / "out" / name).stat().st_size > 1000
