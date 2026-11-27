#!/usr/bin/env python3
"""Unattended energy and quality suite on an Apple silicon MacBook.

    uv run python scripts/energy_suite.py prepare          # once: Metal llama.cpp + models
    uv run python scripts/energy_suite.py run --dry-run    # print the plan and runtime
    uv run python scripts/energy_suite.py run              # the whole matrix, unattended
    uv run python scripts/energy_suite.py calibrate runs/suite-...  # budget cost table only

``run`` replays one clip in real time through ``python -m app.main`` for every condition in
``configs/energy_suite.json`` (reps interleaved, one llama-server at a time, restarted and
warmed up for each run, with a cooldown between runs) while ``energy.macos`` records
powermetrics, battery/SMC telemetry and the server's memory. Each run is written to
``runs/<suite>/<condition>_<rep>/``:

- ``app/``            the app's own run files (item 2d contract: manifest, requests, ...)
- ``powermetrics.csv`` (+ raw ``powermetrics.plist``), ``battery.csv``, ``server_rss.csv``
- ``llama-server.log``, ``app.log``, ``profile.json`` (the inference profile the app used)
- ``suite_run.json``  condition, server command, system state before/after, energy summary,
                      latency and the gate_check scores at the configured tolerance

powermetrics needs root: ``run`` asks for the sudo password once in the terminal
(``sudo -v``), keeps the sudo timestamp fresh while it runs, and never stores the password.
``caffeinate`` keeps the laptop and display awake for the whole suite. A run directory that
already has a complete ``suite_run.json`` is skipped by ``--resume``; nothing is overwritten.
Turn the results into a table and figures with ``scripts/analyze_energy_suite.py``.

The optional ``budget`` block runs the energy-budget controller (``--policy budget``, items
3a/3c). Before each budget run the suite calibrates: from the completed fixed-interval runs
and the idle runs of the same suite it derives joules per call above idle for each image size
and writes ``<suite>/budget_costs.json``, the table the controller reads (``calibrate`` does
the same on its own). Budgets given as ``fractions_of_fixed`` are that fraction of the
calibrated fixed-interval spend (full-size joules per call over ``reference_interval_s``).
Without the runs to calibrate from, the repository's placeholder table is used and the run
record says so.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import itertools
import json
import os
import signal
import statistics
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Optional

import cv2

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))
from energy import macos  # noqa: E402
from scripts import analyze_energy_suite as analysis  # noqa: E402
from scripts.gate_check import check_run  # noqa: E402
from scripts.llama_runtime import CPU_FLAGS, digest  # noqa: E402

RUN_RECORD = "suite_run.json"
SUITE_MANIFEST = "suite_manifest.json"
APP_DIR = "app"
METAL_FLAGS = {**CPU_FLAGS, "GGML_METAL": "ON"}  # the pinned profile's build, with Metal
# Pinned f16 weights of the same model revision, quantized locally to Q4_K_M by llama-quantize
# (the model repository publishes Q8_0 and f16 only).
F16 = {
    "filename": "SmolVLM2-500M-Video-Instruct-f16.gguf",
    "sha256": "80f7e3f04bc2d3324ac1a9f52f5776fe13a69912adf74f8e7edacf773d140d77",
}
LOCAL_QUANTS = ("Q4_K_M",)
BUDGET_COSTS = "budget_costs.json"
PLACEHOLDER_COSTS = ROOT / "configs/budget_costs.json"
SERVER_START_S = 20.0  # runtime estimate per run: server start + warm-up


# ============================================================================ plan


def condition_name(prefix: str, **parts) -> str:
    return prefix + "".join(
        f"_{k}{v:g}" if isinstance(v, float) else f"_{k}{v}" for k, v in parts.items()
    )


def expand(config: dict) -> list[dict]:
    """Every run of the suite in execution order: main matrix (reps interleaved, order rotated
    each rep so no condition always runs first), then each enabled block."""
    base = {c["name"]: c for c in config["conditions"]}
    runs = []

    def add(conditions: list[dict], reps: int, block: str) -> None:
        if not conditions:
            return
        for rep in range(1, reps + 1):
            shift = (rep - 1) % len(conditions)
            for condition in conditions[shift:] + conditions[:shift]:
                runs.append({"block": block, "rep": rep, "condition": condition})

    add(list(config["conditions"]), config["reps"], "main")
    blocks = config.get("blocks", {})

    sweep = blocks.get("gate_sweep", {})
    if sweep.get("enabled"):
        conditions = [
            {
                "name": condition_name("gate", i=float(i), t=float(t), p=int(p)),
                "policy": "gated",
                "interval_s": float(i),
                "app_args": {"gate_threshold": t, "gate_persist_checks": p},
            }
            for i, t, p in itertools.product(
                sweep["interval_s"], sweep["threshold"], sweep["persist_checks"]
            )
        ]
        add(conditions, sweep.get("reps", 1), "gate_sweep")

    image = blocks.get("image", {})
    if image.get("enabled"):
        conditions = []
        for side, tokens in itertools.product(image["image_max_side"], image["max_tokens"]):
            args = {"max_tokens": tokens}
            if side:
                args["image_max_side"] = side
            conditions.append(
                {
                    "name": condition_name("image", px=side or "full", tok=tokens),
                    "policy": image.get("policy", "fixed_interval"),
                    "interval_s": float(image.get("interval_s", 2.0)),
                    "app_args": args,
                }
            )
        add(conditions, image.get("reps", 1), "image")

    quant = blocks.get("quantization", {})
    if quant.get("enabled"):
        conditions = []
        for q, name in itertools.product(quant["quants"], quant["conditions"]):
            condition = copy.deepcopy(base[name])
            condition["name"] = f"{name}_{q}"
            condition["server"] = {**condition.get("server", {}), "quant": q}
            conditions.append(condition)
        add(conditions, quant.get("reps", 1), "quantization")

    budget = blocks.get("budget", {})
    if budget.get("enabled"):
        # Cost of each reduced size: a fixed-interval run at that size, unless the image block
        # already has one at the default output bound.
        covered = set()
        if image.get("enabled") and image.get("policy", "fixed_interval") == "fixed_interval":
            covered = {
                side
                for side, tokens in itertools.product(image["image_max_side"], image["max_tokens"])
                if side and tokens >= max(image["max_tokens"])
            }
        calibration = [
            {
                "name": f"budget_calib_px{side}",
                "policy": "fixed_interval",
                "interval_s": float(budget.get("reference_interval_s", 2.0)),
                "app_args": {"image_max_side": side},
            }
            for side in budget.get("calibrate_sizes", [])
            if side not in covered
        ]
        add(calibration, 1, "budget")
        conditions = [
            {
                "name": f"budget_f{fraction:g}",
                "policy": "budget",
                "interval_s": float(budget.get("interval_s", 0.5)),
                "budget": {"fraction_of_fixed": float(fraction)},
            }
            for fraction in budget.get("fractions_of_fixed", [])
        ] + [
            {
                "name": f"budget_wh{wh:g}",
                "policy": "budget",
                "interval_s": float(budget.get("interval_s", 0.5)),
                "budget": {"wh_per_hour": float(wh)},
            }
            for wh in budget.get("budget_wh_per_hour", [])
        ]
        add(conditions, budget.get("reps", 1), "budget")

    for run in runs:
        run["name"] = f"{run['condition']['name']}_{run['rep']}"
    return runs


def clip_duration(path: Path, fallback: float) -> tuple[float, str]:
    capture = cv2.VideoCapture(str(path))
    try:
        frames = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        fps = capture.get(cv2.CAP_PROP_FPS)
    finally:
        capture.release()
    if frames > 0 and fps > 0:
        return frames / fps, "measured"
    return float(fallback), "estimate"


def estimate(runs: list[dict], run_s: float, cooldown_s: float) -> dict:
    per_run = run_s + SERVER_START_S + cooldown_s
    by_block: dict[str, dict] = {}
    for run in runs:
        block = by_block.setdefault(run["block"], {"runs": 0, "seconds": 0.0})
        block["runs"] += 1
        block["seconds"] += per_run
    total = sum(b["seconds"] for b in by_block.values())
    return {"per_run_s": per_run, "blocks": by_block, "total_s": total}


def hms(seconds: float) -> str:
    minutes = round(seconds / 60)
    return f"{minutes // 60} h {minutes % 60:02d} min" if minutes >= 60 else f"{minutes} min"


def print_plan(runs: list[dict], plan: dict, video: Path, duration: tuple[float, str]) -> None:
    print(f"clip {video} ({duration[0]:.0f} s, {duration[1]})")
    for block, info in plan["blocks"].items():
        print(f"  {block:13s} {info['runs']:3d} runs  ~{hms(info['seconds'])}")
    print(f"  {'total':13s} {len(runs):3d} runs  ~{hms(plan['total_s'])}")
    for run in runs:
        c = run["condition"]
        extra = {**c.get("app_args", {}), **c.get("server", {})}
        print(
            f"    {run['block']:12s} {run['name']:32s} {c['policy']:14s} {c['interval_s']:g} s {extra or ''}"
        )


# ============================================================================ server


def cache_paths(cache: Path, models: Path, profile: dict) -> dict:
    model_dir = models / profile["model_alias"]
    return {
        "source": cache / "llama.cpp",
        "server": cache / "llama.cpp/build/bin/llama-server",
        "quantize": cache / "llama.cpp/build/bin/llama-quantize",
        "manifest": cache / "build-manifest.json",
        "model_dir": model_dir,
    }


def model_file(profile: dict, quant: str) -> str:
    return profile["model"]["filename"].replace(profile["quantization"], quant)


def download(url: str, target: Path, sha256: str) -> None:
    if target.exists():
        if digest(target) != sha256:
            raise ValueError(f"checksum mismatch: {target}")
        return
    temporary = target.with_suffix(target.suffix + ".part")
    print(f"downloading {target.name}", flush=True)
    with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)
    if digest(temporary) != sha256:
        raise ValueError(f"downloaded checksum mismatch: {temporary}")
    temporary.replace(target)


def prepare(profile: dict, cache: Path, models: Path, jobs: int, quants: list[str]) -> None:
    paths = cache_paths(cache, models, profile)
    cache.mkdir(parents=True, exist_ok=True)
    if not paths["source"].exists():
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                profile["llama_cpp_release"],
                profile["llama_cpp_repository"],
                str(paths["source"]),
            ],
            check=True,
        )
    revision = subprocess.check_output(
        ["git", "-C", str(paths["source"]), "rev-parse", "HEAD"], text=True
    ).strip()
    if revision != profile["llama_cpp_revision"]:
        raise ValueError(
            "cached llama.cpp revision differs from the profile; use a fresh --cache-dir"
        )
    build = paths["source"] / "build"
    subprocess.run(
        [
            "cmake",
            "-S",
            str(paths["source"]),
            "-B",
            str(build),
            *(f"-D{k}={v}" for k, v in METAL_FLAGS.items()),
        ],
        check=True,
    )
    subprocess.run(
        [
            "cmake",
            "--build",
            str(build),
            "--target",
            "llama-server",
            "llama-quantize",
            "--parallel",
            str(jobs),
        ],
        check=True,
    )
    model_dir = paths["model_dir"]
    model_dir.mkdir(parents=True, exist_ok=True)
    base = f"https://huggingface.co/{profile['hf_repository']}/resolve/{profile['hf_revision']}"
    for artifact in (profile["model"], profile["projector"]):
        download(
            f"{base}/{artifact['filename']}", model_dir / artifact["filename"], artifact["sha256"]
        )
    produced = {}
    for quant in quants:
        target = model_dir / model_file(profile, quant)
        if not target.exists():
            source = model_dir / F16["filename"]
            download(f"{base}/{F16['filename']}", source, F16["sha256"])
            subprocess.run([str(paths["quantize"]), str(source), str(target), quant], check=True)
        produced[quant] = {"path": str(target), "sha256": digest(target)}
    manifest = {
        "profile": profile,
        "observed_llama_cpp_revision": revision,
        "cmake_flags": METAL_FLAGS,
        "server": str(paths["server"]),
        "quantized": produced,
        "f16": F16,
    }
    paths["manifest"].write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"prepared Metal runtime: {paths['manifest']}")


def server_command(paths: dict, profile: dict, server: dict) -> list[str]:
    quant = server.get("quant", profile["quantization"])
    command = [
        str(paths["server"]),
        "--model",
        str(paths["model_dir"] / model_file(profile, quant)),
        "--mmproj",
        str(paths["model_dir"] / profile["projector"]["filename"]),
        "--alias",
        run_alias(profile, quant),
        "--host",
        profile["host"],
        "--port",
        str(profile["port"]),
        "--threads",
        str(server.get("threads", profile["threads"])),
        "--threads-batch",
        str(server.get("threads", profile["threads"])),
        "--ctx-size",
        str(profile["context_size"]),
        "--parallel",
        "1",
        "--n-predict",
        str(profile["max_output_tokens"]),
        "--no-cache-prompt",
    ]
    if server.get("backend", "metal") == "cpu":
        command += ["--device", "none", "--gpu-layers", "0", "--no-mmproj-offload"]
    else:
        command += ["--gpu-layers", str(server.get("gpu_layers", 99))]
    return command


def run_alias(profile: dict, quant: str) -> str:
    if quant == profile["quantization"]:
        return profile["model_alias"]
    return profile["model_alias"].replace(
        profile["quantization"].split("_")[0].lower(), quant.lower()
    )


def port_in_use(host: str, port: int) -> bool:
    import socket

    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def wait_healthy(url: str, process: subprocess.Popen, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"llama-server exited with {process.returncode} before it was ready")
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"llama-server not healthy after {timeout_s:g} s")


def stop_process(process: Optional[subprocess.Popen], timeout: float = 15.0) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)


def warm_up(profile_path: Path, video: Path, requests: int) -> list[Optional[float]]:
    """Send ``requests`` gesture requests with the clip's first frame (shader compile, caches)."""
    from app.main import encode_jpeg, load_vlm_config
    from vlm.client import VLMClient
    from vlm.prompts import GESTURE_PROMPT, GESTURE_RESPONSE_FORMAT

    capture = cv2.VideoCapture(str(video))
    ok, frame = capture.read()
    capture.release()
    if not ok:
        raise RuntimeError(f"cannot read a frame from {video}")
    jpeg = encode_jpeg(frame, 85)
    config = load_vlm_config(
        argparse.Namespace(profile=str(profile_path), request_timeout_s=None, max_tokens=None)
    )
    times = []
    with VLMClient(config) as client:
        for i in range(requests):
            result = client.infer(
                jpeg,
                frame_id=f"warmup-{i}",
                prompt=GESTURE_PROMPT,
                response_format=GESTURE_RESPONSE_FORMAT,
            )
            times.append(result.elapsed_s if result.ok else None)
    return times


# ============================================================================ run


class SudoKeeper:
    """Refreshes the sudo timestamp every minute so ``sudo -n powermetrics`` keeps working."""

    def __init__(self) -> None:
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, name="sudo-keeper", daemon=True)

    def _loop(self) -> None:
        while not self.stop.wait(60):
            subprocess.run(["sudo", "-n", "-v"], capture_output=True)

    def __enter__(self) -> "SudoKeeper":
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop.set()


def powermetrics_preflight(samplers: str) -> tuple[Optional[str], Optional[str]]:
    """The sampler list powermetrics accepts here (falls back to CPU+GPU), or the error."""
    errors = []
    for candidate in dict.fromkeys([samplers, macos.FALLBACK_SAMPLERS]):
        done = subprocess.run(
            [
                "sudo",
                "-n",
                "powermetrics",
                "--samplers",
                candidate,
                "-i",
                "500",
                "-n",
                "1",
                "-f",
                "plist",
            ],
            capture_output=True,
            timeout=30,
        )
        documents, _ = macos.split_plists(done.stdout + b"\x00")
        if done.returncode == 0 and documents:
            row = macos.parse_powermetrics_sample(documents[0], 0.0)
            if row["cpu_mw"] is not None:
                return candidate, None
        errors.append(
            f"{candidate}: exit {done.returncode} {done.stderr.decode(errors='replace')[-300:]}"
        )
    return None, "; ".join(errors)


def latency_stats(requests: list[dict]) -> dict:
    elapsed = sorted(
        r["elapsed_s"]
        for r in requests
        if r.get("status") == "ok" and r.get("elapsed_s") is not None
    )
    if not elapsed:
        return {"latency_median_s": None, "latency_p90_s": None, "latency_max_s": None}
    p90 = elapsed[min(len(elapsed) - 1, max(0, round(0.9 * (len(elapsed) - 1))))]
    return {
        "latency_median_s": statistics.median(elapsed),
        "latency_p90_s": p90,
        "latency_max_s": elapsed[-1],
    }


def read_windows(annotations: Path, video_id: str) -> list[dict]:
    import csv

    with annotations.open(newline="") as handle:
        return [
            {"label": r["label"], "onset_s": float(r["onset_s"]), "end_s": float(r["end_s"])}
            for r in csv.DictReader(handle)
            if r["video_id"] == video_id
        ]


def score_patterns():
    import re

    return {label: re.compile(rf"^{label}$") for label in ("thumbs_up", "peace_sign")}


def app_command(run: dict, video: Path, profile_path: Path, app_dir: Path, duration_s) -> list[str]:
    condition = run["condition"]
    command = [
        sys.executable,
        "-m",
        "app.main",
        "--source",
        "replay",
        "--video",
        str(video),
        "--policy",
        condition["policy"],
        "--interval-s",
        str(condition["interval_s"]),
        "--profile",
        str(profile_path),
        "--telemetry",
        "off",
        "--no-display",
        "--run-dir",
        str(app_dir),
    ]
    for key, value in condition.get("app_args", {}).items():
        command += [f"--{key.replace('_', '-')}", str(value)]
    if duration_s:
        command += ["--duration-s", str(duration_s)]
    return command


def write_cost_table(suite_dir: Path) -> dict:
    """Calibrate from the suite's completed runs into ``<suite>/budget_costs.json``.

    Returns ``{"path", "table", "error"}``; on failure (no idle or full-size fixed runs yet)
    the path is the repository's placeholder table and ``error`` says why.
    """
    records = analysis.load_runs(suite_dir)
    try:
        table = analysis.calibrate(records, suite_dir.name)
    except ValueError as exc:
        return {
            "path": PLACEHOLDER_COSTS,
            "table": json.loads(PLACEHOLDER_COSTS.read_text()),
            "error": str(exc),
        }
    path = suite_dir / BUDGET_COSTS
    path.write_text(json.dumps(table, indent=2) + "\n")
    return {"path": path, "table": table, "error": None}


def resolve_budget(run: dict, suite_dir: Path, config: dict) -> tuple[dict, dict]:
    """A budget run's condition with ``--budget-wh-per-hour`` and ``--budget-costs`` filled in
    from a fresh calibration, plus the record of how they were chosen."""
    block = config.get("blocks", {}).get("budget", {})
    reference_s = float(block.get("reference_interval_s", 2.0))
    costs = write_cost_table(suite_dir)
    full = next(e for e in costs["table"]["entries"] if e["image_max_side"] is None)
    reference_w = full["j_per_call"] / reference_s  # fixed-interval VLM spend above idle
    spec = run["condition"]["budget"]
    if "wh_per_hour" in spec:
        wh = spec["wh_per_hour"]
    else:
        wh = spec["fraction_of_fixed"] * reference_w
    condition = copy.deepcopy(run["condition"])
    condition["app_args"] = {
        **condition.get("app_args", {}),
        "budget_wh_per_hour": round(wh, 6),
        "budget_costs": str(costs["path"]),
    }
    info = {
        "wh_per_hour": wh,
        "fraction_of_fixed": spec.get("fraction_of_fixed"),
        "reference_interval_s": reference_s,
        "reference_fixed_wh_per_hour": reference_w,
        "costs_path": str(costs["path"]),
        "costs_placeholder": bool(costs["table"].get("placeholder")),
        "calibration_error": costs["error"],
        "cost_table": costs["table"],
    }
    return {**run, "condition": condition}, info


def execute_run(run: dict, ctx: dict) -> dict:
    """One run: server up and warm, samplers on, app replay, samplers off, server down, scores."""
    config, profile = ctx["config"], ctx["profile"]
    run_dir: Path = ctx["suite_dir"] / run["name"]
    budget_info = None
    if run["condition"]["policy"] == "budget":
        run, budget_info = resolve_budget(run, ctx["suite_dir"], config)
    run_dir.mkdir(parents=True)
    server_cfg = {**config["server"], **run["condition"].get("server", {})}
    quant = server_cfg.get("quant", profile["quantization"])
    run_profile = {
        **profile,
        "model_alias": run_alias(profile, quant),
        "quantization": quant,
        "model": {"filename": model_file(profile, quant), "sha256": None},
        "suite_backend": server_cfg.get("backend", "metal"),
    }
    profile_path = run_dir / "profile.json"
    profile_path.write_text(json.dumps(run_profile, indent=2) + "\n")
    record: dict = {
        "suite": ctx["suite_dir"].name,
        "name": run["name"],
        "block": run["block"],
        "rep": run["rep"],
        "condition": run["condition"],
        "server_config": server_cfg,
        "started_wall_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "state_before": macos.system_state(),
        "complete": False,
    }
    if budget_info is not None:
        record["budget"] = budget_info
    url = f"http://{profile['host']}:{profile['port']}"
    if port_in_use(profile["host"], profile["port"]):
        raise RuntimeError(f"port {profile['port']} is busy: another llama-server is running")
    server = sampler_rss = sampler_battery = recorder = None
    try:
        command = ctx["server_command"](ctx["paths"], profile, server_cfg)
        record["server_command"] = command
        with (run_dir / "llama-server.log").open("wb") as log:
            server = subprocess.Popen(
                command, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL
            )
        wait_healthy(url, server, server_cfg.get("start_timeout_s", 180))
        record["warmup_s"] = warm_up(
            profile_path, ctx["video"], server_cfg.get("warmup_requests", 2)
        )

        power = config["power"]
        if ctx["powermetrics"] is not False:
            recorder = macos.PowermetricsRecorder(
                run_dir,
                interval_ms=power["powermetrics_interval_ms"],
                samplers=ctx["samplers"],
                command=ctx["powermetrics"] or None,
            )
            recorder.start()
        sampler_battery = macos.PeriodicSampler(
            run_dir / macos.BATTERY_FILE,
            macos.BATTERY_COLUMNS,
            macos.read_battery,
            power["battery_interval_s"],
            "battery",
        )
        sampler_rss = macos.PeriodicSampler(
            run_dir / macos.RSS_FILE,
            macos.RSS_COLUMNS,
            macos.rss_reader(server.pid),
            power["rss_interval_s"],
            "server-rss",
        )
        sampler_battery.start()
        sampler_rss.start()

        app_dir = run_dir / APP_DIR
        command = app_command(run, ctx["video"], profile_path, app_dir, ctx["duration_s"])
        record["app_command"] = command
        spawn = time.monotonic()
        with (run_dir / "app.log").open("wb") as log:
            app = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        exited = time.monotonic()
        record["app_exit_code"] = app.returncode
        record["host_app_spawn_s"], record["host_app_exit_s"] = spawn, exited
    finally:
        record["samplers"] = {
            "powermetrics": recorder.stop() if recorder else {"skipped": True},
            "battery": sampler_battery.stop() if sampler_battery else None,
            "server_rss": sampler_rss.stop() if sampler_rss else None,
        }
        stop_process(server)

    manifest_path = app_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    times = manifest.get("times", {})
    start = times.get("host_tick_origin_s") or spawn
    end = times.get("host_run_end_s") or exited
    record["window"] = {"host_start_s": start, "host_end_s": end, "seconds": end - start}
    record["energy"] = macos.summarize_run(run_dir, start, end)
    requests = []
    if (app_dir / "requests.jsonl").exists():
        requests = [
            json.loads(line)
            for line in (app_dir / "requests.jsonl").read_text().splitlines()
            if line.strip()
        ]
    if budget_info is not None:
        record["budget_summary"] = manifest.get("budget")
    record["calls"] = {
        "requests": len(requests),
        "ok": sum(r.get("status") == "ok" for r in requests),
        "counts": manifest.get("counts", {}),
        **latency_stats(requests),
    }
    if manifest and ctx["windows"]:
        report = check_run(app_dir, ctx["windows"], config["tolerance_s"], score_patterns())
        record["scores"] = {
            "tolerance_s": config["tolerance_s"],
            "windows": len(ctx["windows"]),
            "windows_caught": report["windows_caught"],
            "windows_named": report["windows_named"],
            "outside_calls": report["outside_calls"],
            "per_window": report["windows"],
        }
    record["state_after"] = macos.system_state()
    record["ended_wall_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    record["complete"] = record["app_exit_code"] == 0
    (run_dir / RUN_RECORD).write_text(json.dumps(record, indent=2, default=str) + "\n")
    return record


def git_commit() -> Optional[str]:
    try:
        return subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def battery_check(config: dict) -> tuple[bool, str]:
    battery = macos.read_battery()
    if not battery.get("valid"):
        return (not config["require_battery"]), f"no battery reading ({battery.get('error')})"
    if battery.get("external_connected"):
        return (not config["require_battery"]), "on AC power"
    percent = battery.get("percent")
    if percent is not None and percent < config["battery_floor_percent"]:
        return (
            False,
            f"battery at {percent:.0f}%, below the {config['battery_floor_percent']}% floor",
        )
    return True, f"on battery at {percent}%"


def run_suite(args: argparse.Namespace, config: dict) -> int:
    profile = json.loads(args.profile.read_text())
    video = (
        (ROOT / config["clip"]["path"])
        if not Path(config["clip"]["path"]).is_absolute()
        else Path(config["clip"]["path"])
    )
    if args.video:
        video = args.video
    if args.require_battery is not None:
        config["require_battery"] = args.require_battery
    runs = expand(config)
    if args.only:
        runs = [r for r in runs if r["condition"]["name"] in args.only or r["block"] in args.only]
    duration = (
        clip_duration(video, config["clip"]["duration_s_estimate"])
        if video.exists()
        else (float(config["clip"]["duration_s_estimate"]), "estimate")
    )
    run_s = min(duration[0], args.duration_s) if args.duration_s else duration[0]
    cooldown = config["cooldown_s"] if args.cooldown_s is None else args.cooldown_s
    plan = estimate(runs, run_s, cooldown)
    print_plan(runs, plan, video, duration)
    if args.dry_run:
        return 0
    if not video.exists():
        print(f"error: clip not found: {video} (see docs/energy_runbook.md)", file=sys.stderr)
        return 2
    paths = cache_paths(args.cache_dir.resolve(), args.models_dir.resolve(), profile)
    if not paths["server"].exists():
        print(
            f"error: no llama-server at {paths['server']}; run `energy_suite.py prepare` first",
            file=sys.stderr,
        )
        return 2

    if args.resume:
        suite_dir = args.resume
    else:
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
        suite_dir = args.out / f"{args.name or 'suite'}-{stamp}"
        if suite_dir.exists():
            print(f"error: {suite_dir} already exists", file=sys.stderr)
            return 2
    suite_dir.mkdir(parents=True, exist_ok=True)

    samplers = config["power"]["powermetrics_samplers"]
    powermetrics: object = None
    if args.no_powermetrics:
        powermetrics = False
    elif args.powermetrics_command:
        powermetrics = args.powermetrics_command.split()
    else:
        print("powermetrics needs administrator rights; enter your password once:")
        if subprocess.run(["sudo", "-v"]).returncode != 0:
            print("error: sudo failed; nothing was run", file=sys.stderr)
            return 2
        samplers, error = powermetrics_preflight(samplers)
        if samplers is None:
            print(f"error: powermetrics does not work here: {error}", file=sys.stderr)
            return 2

    ctx = {
        "config": config,
        "profile": profile,
        "paths": paths,
        "suite_dir": suite_dir,
        "video": video,
        "duration_s": args.duration_s,
        "powermetrics": powermetrics,
        "samplers": samplers,
        "server_command": server_command,
        "windows": read_windows(ROOT / config["annotations"], config["clip"]["video_id"]),
    }
    manifest_path = suite_dir / SUITE_MANIFEST
    suite_manifest = {
        "started_wall_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "argv": sys.argv,
        "config": config,
        "git_commit": git_commit(),
        "video": str(video),
        "clip_duration_s": duration,
        "duration_s_override": args.duration_s,
        "cooldown_s": cooldown,
        "powermetrics": "skipped"
        if powermetrics is False
        else (powermetrics or f"sudo -n powermetrics --samplers {samplers}"),
        "build_manifest": json.loads(paths["manifest"].read_text())
        if paths["manifest"].exists()
        else None,
        "estimate": plan,
        "runs": [r["name"] for r in runs],
        "system_state": macos.system_state(),
    }
    if manifest_path.exists():
        suite_manifest = {
            **json.loads(manifest_path.read_text()),
            "resumed_wall_utc": suite_manifest["started_wall_utc"],
        }
    manifest_path.write_text(json.dumps(suite_manifest, indent=2, default=str) + "\n")

    caffeinate = subprocess.Popen(["caffeinate", "-dims", "-w", str(os.getpid())])
    failures, done = 0, 0
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    try:
        with SudoKeeper() if powermetrics is None else _null():
            for index, run in enumerate(runs):
                run_dir = suite_dir / run["name"]
                record_path = run_dir / RUN_RECORD
                if record_path.exists() and json.loads(record_path.read_text()).get("complete"):
                    print(f"[{index + 1}/{len(runs)}] skip {run['name']}: already complete")
                    continue
                if run_dir.exists():  # an interrupted attempt: keep it under another name
                    n = 1
                    while (failed := run_dir.with_name(f"{run_dir.name}.failed-{n}")).exists():
                        n += 1
                    run_dir.rename(failed)
                ok, reason = battery_check(config)
                if not ok:
                    print(
                        f"stopping before {run['name']}: {reason}. Fix it, then rerun with --resume {suite_dir}"
                    )
                    return 4
                print(f"[{index + 1}/{len(runs)}] {run['name']} ({reason}) ...", flush=True)
                try:
                    record = execute_run(run, ctx)
                except Exception as exc:  # keep going: one bad run must not end the suite
                    failures += 1
                    print(f"  failed: {type(exc).__name__}: {exc}", flush=True)
                    (run_dir / "error.txt").write_text(f"{type(exc).__name__}: {exc}\n")
                else:
                    done += 1
                    e, c = record["energy"], record["calls"]
                    print(
                        f"  exit {record['app_exit_code']}, {c['requests']} calls, "
                        f"median {fmt(c['latency_median_s'])} s, package {fmt(e['package_combined_mean_w'])} W, "
                        f"system {fmt(e['system_load_mean_w'])} W, battery {fmt(e['battery_mean_w'])} W, "
                        f"peak RSS {fmt(e['server_peak_rss_mb'])} MB",
                        flush=True,
                    )
                    failures += 0 if record["complete"] else 1
                if stop["flag"]:
                    print("stopped by SIGTERM")
                    return 130
                if index < len(runs) - 1 and cooldown:
                    time.sleep(cooldown)
    except KeyboardInterrupt:
        print(f"\ninterrupted; resume with --resume {suite_dir}")
        return 130
    finally:
        stop_process(caffeinate, 5)
    print(f"done: {done} runs, {failures} failed. Suite: {suite_dir}")
    print(f"next: uv run python scripts/analyze_energy_suite.py {suite_dir}")
    return 0 if failures == 0 else 1


class _null:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None


def fmt(value) -> str:
    return "-" if value is None else f"{value:.2f}"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="action", required=True)
    cal = sub.add_parser("calibrate", help="write <suite>/budget_costs.json from its runs")
    cal.add_argument("suite", type=Path)
    cal.add_argument("--config", type=Path, default=ROOT / "configs/energy_suite.json")
    for name in ("prepare", "run"):
        p = sub.add_parser(name)
        p.add_argument("--profile", type=Path, default=ROOT / "configs/inference.json")
        p.add_argument("--cache-dir", type=Path, default=ROOT / ".cache/energy-suite")
        p.add_argument("--models-dir", type=Path, default=ROOT / "models")
        p.add_argument("--config", type=Path, default=ROOT / "configs/energy_suite.json")
    prep = sub.choices["prepare"]
    prep.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    run = sub.choices["run"]
    run.add_argument("--dry-run", action="store_true", help="print the plan and runtime only")
    run.add_argument("--out", type=Path, default=ROOT / "runs")
    run.add_argument("--name", help="suite folder prefix (default 'suite')")
    run.add_argument("--resume", type=Path, help="continue an earlier suite folder")
    run.add_argument("--only", nargs="+", metavar="NAME", help="only these conditions or blocks")
    run.add_argument("--video", type=Path, help="override the clip (smoke checks)")
    run.add_argument("--duration-s", type=float, help="stop each replay early (smoke checks)")
    run.add_argument("--cooldown-s", type=float, help="override the config's cooldown")
    run.add_argument("--no-powermetrics", action="store_true", help="skip powermetrics (no sudo)")
    run.add_argument("--powermetrics-command", help="replace the powermetrics command (tests)")
    battery = run.add_mutually_exclusive_group()
    battery.add_argument(
        "--allow-ac",
        dest="require_battery",
        action="store_false",
        default=None,
        help="run even when plugged in (no battery energy)",
    )
    battery.add_argument("--require-battery", dest="require_battery", action="store_true")
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text())
    if args.action == "calibrate":
        costs = write_cost_table(args.suite)
        if costs["error"]:
            print(f"calibration failed: {costs['error']}", file=sys.stderr)
            return 2
        for entry in costs["table"]["entries"]:
            side = entry["image_max_side"] or "source"
            print(
                f"  image_max_side {side}: {entry['j_per_call']:.2f} J per call above idle, "
                f"median latency {entry['latency_s']:.2f} s ({len(entry['runs'])} runs)"
            )
        print(f"wrote {costs['path']} ({costs['table']['domain']})")
        return 0
    if args.action == "prepare":
        profile = json.loads(args.profile.read_text())
        quants = sorted(
            {
                q
                for q in config["blocks"].get("quantization", {}).get("quants", [])
                if q in LOCAL_QUANTS
            }
        )
        try:
            prepare(profile, args.cache_dir.resolve(), args.models_dir.resolve(), args.jobs, quants)
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            print(f"prepare failed: {exc}", file=sys.stderr)
            return 1
        return 0
    return run_suite(args, config)


if __name__ == "__main__":
    sys.exit(main())
