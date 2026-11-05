"""Fixed-interval baseline app checks: vlm.client.VLMClient against an in-process fake
llama-server, energy readers with fake inputs, generated clips. No camera or model needed.

These run in real time on short clips, so timing assertions use tolerances.
"""

from __future__ import annotations

import _thread
import csv
import json
import socket
import threading
import time

import numpy as np
import pytest

from app.main import BaselineRun, ConfigError, main, parse_args
from app.state import ObservationState, render_overlay
from capture import EndReason, ReplaySource, WebcamSource
from contracts import read_artifact, validate_run_dir
from energy.monitor import EnergyMonitor, Sensor
from energy.windows import WindowsBatteryReader, parse_report
from tests.fakes.fake_capture import FAIL, CaptureFactory, FakeVideoCapture, solid_frame
from tests.fakes.fake_llama import FakeLlama
from tests.fakes.video import write_test_video


@pytest.fixture
def clip(tmp_path):
    return write_test_video(tmp_path / "clip.avi", frames=40, fps=20.0)  # 2.0 s


def config_for(tmp_path, *extra, video=None, name="run"):
    argv = [
        "--source",
        "replay",
        "--video",
        str(video),
        "--no-display",
        "--run-dir",
        str(tmp_path / name),
        "--telemetry",
        "off",
        *extra,
    ]
    return parse_args(argv)


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def baseline_threads_alive():
    return [
        t.name for t in threading.enumerate() if t.name.startswith("baseline-") and t.is_alive()
    ]


def run_baseline(config, llama=None, *, read_timeout_s=120.0, server_idle=lambda: True, **kwargs):
    llama = llama or FakeLlama()
    run = BaselineRun(
        config,
        client=llama.client(read_timeout_s=read_timeout_s),
        server_idle=server_idle,
        **kwargs,
    )
    result = run.run()
    # Every run directory the app writes must meet the item 2d contract.
    assert [str(i) for i in validate_run_dir(result.run_dir)] == []
    return run, result


def read_power(run_dir):
    records, issues = read_artifact("power", run_dir / "power.csv")
    assert issues == []
    return records


# --------------------------------------------------------------------------- interval


def test_changing_interval_changes_invocation_timing(tmp_path, clip):
    counts = {}
    for interval in (0.25, 0.5):
        config = config_for(
            tmp_path, "--interval-s", str(interval), video=clip, name=f"run_{interval}"
        )
        run, result = run_baseline(config)
        assert result.exit_code == 0 and result.manifest["run_end_reason"] == "eof"
        requests = read_jsonl(result.run_dir / "requests.jsonl")
        counts[interval] = len(requests)
        gaps = np.diff([r["host_tick_s"] for r in requests])
        assert np.allclose(gaps, interval, atol=1e-6), gaps  # ticks sit on the fixed grid
        origin = result.manifest["times"]["host_tick_origin_s"]
        for r in requests:
            assert r["status"] == "ok" and r["text"].startswith("fake description")
            assert 0 <= r["request_started_s"] - r["host_tick_s"] < 0.1
            # Each request used the newest frame at its tick: source time tracks tick time.
            assert abs(r["source_time_s"] - (r["host_tick_s"] - origin)) < 0.1
    assert 7 <= counts[0.25] <= 9
    assert 3 <= counts[0.5] <= 5


def test_requests_carry_the_frame_prompt_and_output_bound(tmp_path, clip):
    llama = FakeLlama()
    config = config_for(
        tmp_path, "--interval-s", "0.5", "--duration-s", "1.2", "--max-tokens", "32", video=clip
    )
    run, result = run_baseline(config, llama)
    requests = read_jsonl(result.run_dir / "requests.jsonl")
    assert len(requests) == 3 and len(llama.completions) == 3
    assert all(
        body["max_tokens"] == 32 and body["cache_prompt"] is False for body in llama.completions
    )
    assert llama.completions[0]["messages"][0]["content"][0]["text"] == config.prompt
    first = requests[0]
    assert (
        first["frame_id"] == 0
        and first["prompt_tokens"] == 150
        and first["finish_reason"] == "stop"
    )
    assert first["source_id"] == str(clip) and first["run_id"] == result.manifest["run_id"]
    assert result.manifest["vlm"]["server_properties"]["build_info"] == "b0-fake"
    assert result.manifest["vlm"]["max_tokens"] == 32


# --------------------------------------------------------------------------- overload


def test_slow_request_records_busy_skips_instead_of_a_backlog(tmp_path, clip):
    llama = FakeLlama(latency_s=0.6)
    config = config_for(tmp_path, "--interval-s", "0.2", video=clip)
    run, result = run_baseline(config, llama)
    manifest = result.manifest
    requests = read_jsonl(result.run_dir / "requests.jsonl")
    drops = read_jsonl(result.run_dir / "drops.jsonl")
    busy = [d for d in drops if d["reason"] == "tick_skipped_busy"]

    assert llama.max_active == 1
    assert 3 <= len(requests) <= 4  # ~2 s / 0.6 s, not one per 0.2 s tick
    assert len(busy) >= 5
    assert all(d["in_flight_frame_id"] in {r["frame_id"] for r in requests} for d in busy)
    # Every tick is accounted for exactly once: dispatched or skipped.
    tick_ids = sorted(
        [r["tick_index"] for r in requests]
        + [d["tick_index"] for d in drops if d["origin"] == "app"]
    )
    assert tick_ids == list(range(len(tick_ids)))
    assert manifest["source"]["info"]["frames_delivered"] == 40  # replay not slowed by inference
    assert 2.0 <= manifest["times"]["observed_duration_s"] <= 2.0 + 0.6 + 0.3
    starts = sorted(r["request_started_s"] for r in requests)
    assert all(b - a >= 0.6 - 0.05 for a, b in zip(starts, starts[1:]))  # strictly serial
    assert manifest["counts"]["tick_skipped_busy"] == len(busy)


# --------------------------------------------------------------------------- failures


def test_failures_are_logged_and_do_not_replace_confirmed_state(tmp_path, clip):
    outcomes = ["ok", "timeout", "invalid", "empty", "connect_error", "http_error"]
    llama = FakeLlama(outcomes=outcomes)
    config = config_for(tmp_path, "--interval-s", "0.15", video=clip)
    run, result = run_baseline(config, llama)
    requests = read_jsonl(result.run_dir / "requests.jsonl")
    assert len(requests) >= len(outcomes)

    first = requests[: len(outcomes)]
    assert [r["status"] for r in first] == [
        "ok",
        "timeout",
        "invalid_response",
        "empty_response",
        "connection_error",
        "http_error",
    ]
    assert first[0]["text"] and first[0]["error"] is None
    assert all(r["text"] is None and r["error"] for r in first[1:])
    assert first[1]["server_state_unknown"] is True and first[5]["http_status"] == 500

    oks = [r for r in requests if r["status"] == "ok"]
    assert run.state.confirmed.frame_id == oks[-1]["frame_id"]
    assert run.state.confirmed.text == oks[-1]["text"]
    assert result.exit_code == 0  # request failures are recorded, not fatal


def test_unknown_server_state_pauses_requests_until_the_server_is_idle(tmp_path, clip):
    idle_answers = iter([False, False, False])
    llama = FakeLlama(outcomes=["timeout", "ok"])
    config = config_for(tmp_path, "--interval-s", "0.1", "--duration-s", "1.0", video=clip)
    run, result = run_baseline(config, llama, server_idle=lambda: next(idle_answers, True))
    requests = read_jsonl(result.run_dir / "requests.jsonl")
    paused = [
        d
        for d in read_jsonl(result.run_dir / "drops.jsonl")
        if d["reason"] == "tick_skipped_server_unknown"
    ]
    assert requests[0]["status"] == "timeout" and requests[0]["server_state_unknown"]
    assert len(paused) == 3
    assert paused[0]["tick_index"] == requests[0]["tick_index"] + 1
    assert requests[1]["tick_index"] == paused[-1]["tick_index"] + 1  # resumes once idle
    assert result.exit_code == 0


def test_a_server_that_never_becomes_idle_ends_the_run_with_an_error(tmp_path, clip):
    llama = FakeLlama(outcomes=["timeout"])
    config = config_for(
        tmp_path, "--interval-s", "0.1", "--server-idle-timeout-s", "0.3", video=clip
    )
    run, result = run_baseline(config, llama, server_idle=lambda: False)
    assert result.exit_code == 2
    assert result.manifest["run_end_reason"] == "server_not_idle"
    assert len(read_jsonl(result.run_dir / "requests.jsonl")) == 1


def test_client_exception_is_logged_not_fatal(tmp_path, clip):
    client = FakeLlama().client()

    def explode(*args, **kwargs):
        raise RuntimeError("client blew up")

    client.infer = explode
    config = config_for(tmp_path, "--interval-s", "0.5", "--duration-s", "0.6", video=clip)
    result = BaselineRun(config, client=client, server_idle=lambda: True).run()
    requests = read_jsonl(result.run_dir / "requests.jsonl")
    assert requests and all(
        r["status"] == "client_exception" and "RuntimeError" in r["error"] for r in requests
    )
    assert result.exit_code == 0


def test_observation_state_keeps_confirmed_text_through_failures():
    state = ObservationState()
    common = dict(source_time_s=0.0, host_capture_s=1.0, host_response_available_s=2.0)
    state.record_result(
        status="ok", text="a cat", error_type=None, request_id="r1", frame_id=1, **common
    )
    state.record_result(
        status="timeout", text=None, error_type="ReadTimeout", request_id="r2", frame_id=2, **common
    )
    assert state.confirmed.text == "a cat" and state.confirmed.frame_id == 1
    lines = state.overlay_lines(now_s=3.0)
    assert "a cat" in lines[0] and "timeout" in lines[1] and "frame 2" in lines[1]
    image = np.zeros((48, 64, 3), np.uint8)
    out = render_overlay(image, lines)
    assert out.shape == image.shape and out.any() and not image.any()


# --------------------------------------------------------------------------- shutdown


def test_interrupt_shuts_down_and_records_the_abandoned_request(tmp_path, clip):
    llama = FakeLlama(latency_s=10.0)
    config = config_for(tmp_path, "--interval-s", "0.2", "--shutdown-timeout-s", "0.5", video=clip)
    timer = threading.Timer(0.5, _thread.interrupt_main)
    started = time.monotonic()
    timer.start()
    try:
        run, result = run_baseline(config, llama)
        elapsed = time.monotonic() - started
    finally:
        timer.join()
        llama.release.set()  # let the fake finish the request the app gave up on

    assert result.exit_code == 130
    manifest = result.manifest
    assert manifest["run_end_reason"] == "interrupted"
    assert manifest["source"]["end"]["reason"] == EndReason.INTERRUPTED.value
    assert not run.source.is_open and run.client_closed
    assert elapsed < 3.0  # the 10 s request was abandoned, not waited out
    requests = read_jsonl(result.run_dir / "requests.jsonl")
    assert len(requests) == 1 and requests[0]["status"] == "abandoned_at_shutdown"
    # httpx cannot cancel a blocked request, so only the inference thread may outlive shutdown.
    assert set(manifest["threads_not_joined"]) <= {"baseline-inference"}

    with ReplaySource(clip) as again:  # the source can be reopened right away
        assert again.read().frame_id == 0


def test_duration_limit_stops_a_run_and_exits_zero(tmp_path):
    long_clip = write_test_video(tmp_path / "long.avi", frames=100, fps=20.0)  # 5 s
    config = config_for(tmp_path, "--interval-s", "0.2", "--duration-s", "0.6", video=long_clip)
    run, result = run_baseline(config)
    assert result.exit_code == 0
    assert result.manifest["run_end_reason"] == "duration_limit"
    assert 0.6 <= result.manifest["times"]["observed_duration_s"] < 1.0
    requests = read_jsonl(result.run_dir / "requests.jsonl")
    assert all(
        r["host_tick_s"] < result.manifest["times"]["host_tick_origin_s"] + 0.6 for r in requests
    )
    assert baseline_threads_alive() == []


def test_webcam_source_runs_through_the_same_entry_point(tmp_path):
    capture = FakeVideoCapture([solid_frame(i) for i in range(200)], read_delay_s=0.02)
    factory = CaptureFactory(lambda: capture)
    config = parse_args(
        [
            "--source",
            "webcam",
            "--interval-s",
            "0.2",
            "--duration-s",
            "0.7",
            "--no-display",
            "--telemetry",
            "off",
            "--run-dir",
            str(tmp_path / "cam"),
        ]
    )
    run, result = run_baseline(
        config,
        source_factory=lambda on_drop: WebcamSource(0, capture_factory=factory, on_drop=on_drop),
    )
    assert result.exit_code == 0 and result.manifest["run_end_reason"] == "duration_limit"
    requests = read_jsonl(result.run_dir / "requests.jsonl")
    assert 3 <= len(requests) <= 5
    assert all(r["source_kind"] == "webcam" and r["source_time_s"] is None for r in requests)
    assert result.manifest["source"]["info"]["backend"] == "FAKE"
    assert capture.released


def test_source_errors_are_not_reported_as_success(tmp_path):
    placeholder = tmp_path / "fake.avi"
    placeholder.write_bytes(b"")
    truncated = FakeVideoCapture(
        [solid_frame(i) for i in range(6)] + [FAIL], frame_count=100, fps=20.0
    )
    config = config_for(tmp_path, "--interval-s", "0.1", video=placeholder)
    run, result = run_baseline(
        config,
        source_factory=lambda on_drop: ReplaySource(
            placeholder, capture_factory=lambda *_: truncated, on_drop=on_drop
        ),
    )
    assert result.exit_code == 2
    assert result.manifest["run_end_reason"] == "incomplete_source"
    assert result.manifest["source"]["end"]["complete"] is False


def test_source_open_failure_still_writes_a_manifest(tmp_path):
    config = config_for(tmp_path, video=tmp_path / "missing.avi")
    run, result = run_baseline(config)
    assert result.exit_code == 2
    manifest = json.loads((result.run_dir / "manifest.json").read_text())
    assert manifest["run_end_reason"] == "source_open_failed"
    assert "not found" in manifest["error_detail"]


def test_source_drops_reach_the_drop_log(tmp_path):
    placeholder = tmp_path / "fake.avi"
    placeholder.write_bytes(b"")
    entries = [solid_frame(0), solid_frame(1), None, solid_frame(3), solid_frame(4)]
    capture = FakeVideoCapture(entries, fps=10.0)
    config = config_for(tmp_path, "--interval-s", "0.1", video=placeholder)
    run, result = run_baseline(
        config,
        source_factory=lambda on_drop: ReplaySource(
            placeholder, capture_factory=lambda *_: capture, on_drop=on_drop
        ),
    )
    drops = [d for d in read_jsonl(result.run_dir / "drops.jsonl") if d["origin"] == "source"]
    assert [(d["frame_id"], d["reason"]) for d in drops] == [(2, "empty_frame")]
    assert result.manifest["counts"]["source_drops"] == {"empty_frame": 1}


# --------------------------------------------------------------------------- telemetry


class FakeBatteryReader:
    executable = "powershell.exe (fake)"

    def __init__(self):
        self.reads = 0

    def read(self):
        self.reads += 1
        report = {
            "remaining_mwh": 30000 - self.reads,
            "full_mwh": 38646,
            "charge_rate_mw": -11500,
            "status": "Discharging",
            "power_supply_status": "NotPresent",
            "observed_utc": "2026-11-03T12:00:00Z",
        }
        now = time.monotonic()
        return parse_report(report, now, now)


def test_telemetry_logs_sysfs_and_battery_rows_with_their_sources(tmp_path, clip):
    counter = tmp_path / "energy_uj"
    counter.write_text("123456789\n")
    sensor = Sensor(
        "powercap:fake", str(counter), "package-0", "cpu_package", "energy_counter", "uJ", "J", 1e-6
    )
    config = config_for(
        tmp_path,
        "--telemetry",
        "on",
        "--interval-s",
        "0.5",
        "--duration-s",
        "0.6",
        "--telemetry-interval-s",
        "0.1",
        "--battery-interval-s",
        "0.2",
        video=clip,
    )
    run, result = run_baseline(
        config, energy_monitor=EnergyMonitor(sensors=[sensor]), battery_reader=FakeBatteryReader()
    )
    rows = read_power(result.run_dir)
    sysfs = [r for r in rows if r["source"] == "sysfs"]
    windows = [r for r in rows if r["source"] == "windows_battery"]
    assert len(sysfs) >= 4 and all(
        r["valid"] and r["value"] == pytest.approx(123.456789) for r in sysfs
    )
    # sysfs rows sit on the same host clock as requests, inside the run.
    times = result.manifest["times"]
    assert all(
        times["host_run_start_s"] - 1 <= r["host_time_s"] <= times["host_run_end_s"] for r in sysfs
    )
    power = [r for r in windows if r["quantity"] == "discharge_power"]
    energy = [r for r in windows if r["quantity"] == "stored_energy"]
    assert len(power) >= 2 and all(r["valid"] and r["value"] == 11.5 for r in power)
    assert len(energy) == len(power) and all(
        r["domain"] == "whole_laptop_battery" and r["raw_unit"] == "mWh" and r["unit"] == "J"
        for r in energy
    )
    assert all(r["run_id"] == result.manifest["run_id"] for r in rows)
    state = result.manifest["power_state"]
    assert state["at_start"]["ac_online"] is False
    assert state["at_end"]["battery_status"] == "Discharging"
    telemetry = result.manifest["telemetry"]
    assert (
        telemetry["enabled"]
        and telemetry["battery_source"] == "Windows.Devices.Power.BatteryReport"
    )
    assert telemetry["sysfs_inventory"]["sensors"][0]["sensor_id"] == "powercap:fake"


def test_unavailable_battery_report_is_logged_invalid_not_zero(tmp_path, clip):
    config = config_for(
        tmp_path,
        "--telemetry",
        "on",
        "--interval-s",
        "0.5",
        "--duration-s",
        "0.3",
        "--battery-interval-s",
        "0.1",
        video=clip,
    )
    reader = WindowsBatteryReader(executable=str(tmp_path / "no-powershell.exe"))
    run, result = run_baseline(
        config, energy_monitor=EnergyMonitor(sensors=[]), battery_reader=reader
    )
    rows = [r for r in read_power(result.run_dir) if r["source"] == "windows_battery"]
    assert rows and all(r["valid"] is False and r["value"] is None and r["error"] for r in rows)
    with open(result.run_dir / "power.csv", newline="") as f:
        cells = [row["value"] for row in csv.DictReader(f)]
    assert set(cells) == {""}  # missing, never 0
    assert result.manifest["power_state"] == {"at_start": None, "at_end": None}


def test_telemetry_off_writes_no_samples(tmp_path, clip):
    config = config_for(tmp_path, "--duration-s", "0.2", video=clip)
    run, result = run_baseline(config)
    assert read_power(result.run_dir) == []
    assert result.manifest["telemetry"] == {"enabled": False}


# --------------------------------------------------------------------------- CLI and setup


@pytest.mark.parametrize(
    "argv",
    [
        ["--source", "replay"],
        ["--source", "webcam", "--video", "x.avi"],
        ["--source", "replay", "--video", "x.avi", "--interval-s", "0"],
        ["--source", "replay", "--video", "x.avi", "--interval-s", "-1"],
        ["--source", "replay", "--video", "x.avi", "--vlm", "fake"],
        ["--source", "replay", "--video", "x.avi", "--telemetry", "fake"],
        ["--source", "camera"],
    ],
)
def test_invalid_cli_arguments_exit_2(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        parse_args(argv)
    assert exc.value.code == 2


def test_missing_llama_server_fails_before_the_run(tmp_path, clip, capsys):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    profile = tmp_path / "inference.json"
    profile.write_text(
        json.dumps(
            {
                "host": "127.0.0.1",
                "port": port,
                "model_alias": "m",
                "max_output_tokens": 64,
                "connect_timeout_s": 1,
                "read_timeout_s": 5,
            }
        )
    )
    run_dir = tmp_path / "never"
    code = main(
        [
            "--source",
            "replay",
            "--video",
            str(clip),
            "--no-display",
            "--run-dir",
            str(run_dir),
            "--profile",
            str(profile),
            "--telemetry",
            "off",
        ]
    )
    assert code == 2
    assert "no ready llama-server" in capsys.readouterr().err
    assert not run_dir.exists()


def test_max_tokens_above_the_profile_bound_is_rejected(tmp_path, clip):
    config = config_for(tmp_path, "--max-tokens", "65", video=clip)
    with pytest.raises(ConfigError, match="exceeds"):
        BaselineRun(config, client=FakeLlama().client(max_output_tokens=64))


def test_refuses_to_overwrite_a_non_empty_run_dir(tmp_path, clip):
    run_dir = tmp_path / "used"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text("{}")
    config = config_for(tmp_path, video=clip, name="used")
    with pytest.raises(ConfigError, match="refusing to overwrite"):
        BaselineRun(config, client=FakeLlama().client())
    assert (run_dir / "manifest.json").read_text() == "{}"
