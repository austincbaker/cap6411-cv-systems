"""Fixed-interval baseline app checks: real VLM client against a fake llama-server,
fake telemetry, generated clips. No camera or model needed.

These run in real time on short clips, so timing assertions use tolerances.
"""

from __future__ import annotations

import _thread
import json
import socket
import threading
import time

import numpy as np
import pytest

from app.main import BaselineRun, main, parse_args
from app.state import ObservationState, render_overlay
from src.capture import EndReason, ReplaySource, WebcamSource
from tests.fakes.fake_capture import FAIL, CaptureFactory, FakeVideoCapture, solid_frame
from tests.fakes.fake_llama_server import DROP, FakeServer, reply, scripted
from tests.fakes.fake_telemetry import FakeTelemetry
from tests.fakes.video import write_test_video


@pytest.fixture
def clip(tmp_path):
    return write_test_video(tmp_path / "clip.avi", frames=40, fps=20.0)  # 2.0 s


@pytest.fixture
def llama():
    server = FakeServer(delay_s=0.01)
    yield server
    server.stop()


def config_for(tmp_path, llama, *extra, video=None, name="run"):
    argv = ["--source", "replay", "--video", str(video), "--no-display", "--run-dir", str(tmp_path / name),
            "--vlm-url", llama.url, *extra]
    return parse_args(argv)


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def baseline_threads_alive():
    return [t.name for t in threading.enumerate() if t.name.startswith("baseline-") and t.is_alive()]


def run_baseline(config, **kwargs):
    run = BaselineRun(config, **kwargs)
    result = run.run()
    return run, result


# --------------------------------------------------------------------------- interval


def test_changing_interval_changes_invocation_timing(tmp_path, llama, clip):
    counts = {}
    for interval in (0.25, 0.5):
        config = config_for(tmp_path, llama, "--interval-s", str(interval),
                            video=clip, name=f"run_{interval}")
        run, result = run_baseline(config)
        assert result.exit_code == 0 and result.manifest["run_end_reason"] == "eof"
        requests = read_jsonl(result.run_dir / "requests.jsonl")
        counts[interval] = len(requests)
        ticks = [r["host_tick_s"] for r in requests]
        gaps = np.diff(ticks)
        assert np.allclose(gaps, interval, atol=1e-6), gaps  # ticks sit on the fixed grid
        for r in requests:
            assert 0 <= r["host_request_start_s"] - r["host_tick_s"] < 0.1
            assert r["status"] == "ok"
        # Each request used the newest frame at its tick: source time tracks tick time.
        origin = result.manifest["times"]["host_tick_origin_s"]
        for r in requests:
            assert abs(r["source_time_s"] - (r["host_tick_s"] - origin)) < 0.1
    assert 7 <= counts[0.25] <= 9
    assert 3 <= counts[0.5] <= 5


# --------------------------------------------------------------------------- overload


def test_slow_request_records_busy_skips_instead_of_a_backlog(tmp_path, llama, clip):
    llama.delay_s = 0.6
    config = config_for(tmp_path, llama, "--interval-s", "0.2", video=clip)
    run, result = run_baseline(config)
    manifest = result.manifest
    requests = read_jsonl(result.run_dir / "requests.jsonl")
    drops = read_jsonl(result.run_dir / "drops.jsonl")
    busy = [d for d in drops if d["reason"] == "tick_skipped_busy"]

    assert llama.max_active == 1
    assert 3 <= len(requests) <= 4  # ~2 s / 0.6 s, not one per 0.2 s tick
    assert len(busy) >= 5
    for d in busy:
        assert isinstance(d["frame_id"], int)
        assert d["in_flight_request_id"] in {r["request_id"] for r in requests}
    # Every tick is accounted for exactly once: dispatched or skipped.
    tick_ids = sorted([r["tick_index"] for r in requests] + [d["tick_index"] for d in drops if d["origin"] == "app"])
    assert tick_ids == list(range(len(tick_ids)))
    # No backlog after EOF: nothing starts after the source ended, so the run
    # ends at most one request latency after the 2 s clip.
    assert manifest["source"]["info"]["frames_delivered"] == 40  # replay not slowed by inference
    assert 2.0 <= manifest["times"]["observed_duration_s"] <= 2.0 + 0.6 + 0.3
    starts = sorted(r["host_request_start_s"] for r in requests)
    assert all(b - a >= 0.6 - 0.05 for a, b in zip(starts, starts[1:]))  # strictly serial
    assert manifest["counts"]["tick_skipped_busy"] == len(busy)


# --------------------------------------------------------------------------- failures


def test_failures_are_logged_and_do_not_replace_confirmed_state(tmp_path, llama, clip):
    llama.respond = scripted(
        reply(),                     # ok
        (200, reply()[1], 0.3),      # answers after the 0.1 s client timeout
        (200, b"not json"),          # malformed
        reply(text=""),              # empty
        DROP,                        # connection dropped
        (500, b'{"error": "boom"}'),  # http error
        reply(text="   "),           # blank text
    )
    config = config_for(tmp_path, llama, "--interval-s", "0.15", "--request-timeout-s", "0.1", video=clip)
    run, result = run_baseline(config)
    requests = read_jsonl(result.run_dir / "requests.jsonl")
    assert len(requests) >= 7

    first = requests[:7]
    assert [r["status"] for r in first] == ["ok", "timeout", "malformed", "empty", "connection_error", "http_error", "empty"]
    assert first[0]["text"] and first[0]["error_type"] is None
    for r in first[1:]:
        assert r["text"] is None and r["error_type"]
    assert [first[i]["error_type"] for i in (1, 3, 5, 6)] == ["timeout", "empty_text", "http_500", "empty_text"]

    oks = [r for r in requests if r["status"] == "ok"]
    assert run.state.confirmed.frame_id == oks[-1]["frame_id"]
    assert run.state.confirmed.text == oks[-1]["text"]
    assert run.state.last_status == requests[-1]["status"]
    assert result.exit_code == 0  # request failures are recorded, not fatal


def test_client_exception_is_logged_not_fatal(tmp_path, llama, clip):
    class Exploding:
        def describe(self, **kwargs):
            raise RuntimeError("client blew up")

        def close(self):
            pass

    config = config_for(tmp_path, llama, "--interval-s", "0.5", "--duration-s", "0.6", video=clip)
    run, result = run_baseline(config, client=Exploding())
    requests = read_jsonl(result.run_dir / "requests.jsonl")
    assert requests and all(r["status"] == "client_exception" and r["error_type"] == "RuntimeError" for r in requests)
    assert result.exit_code == 0


def test_observation_state_keeps_confirmed_text_through_failures():
    state = ObservationState()
    common = dict(source_time_s=0.0, host_capture_s=1.0, host_response_available_s=2.0)
    state.record_result(status="ok", text="a cat", error_type=None, request_id="r1", frame_id=1, **common)
    state.record_result(status="timeout", text=None, error_type="timeout", request_id="r2", frame_id=2, **common)
    assert state.confirmed.text == "a cat" and state.confirmed.frame_id == 1
    lines = state.overlay_lines(now_s=3.0)
    assert "a cat" in lines[0] and "timeout" in lines[1] and "frame 2" in lines[1]
    image = np.zeros((48, 64, 3), np.uint8)
    out = render_overlay(image, lines)
    assert out.shape == image.shape and out.any() and not image.any()


# --------------------------------------------------------------------------- shutdown


def test_interrupt_shuts_down_cleanly_with_request_in_flight(tmp_path, llama, clip):
    llama.delay_s = 10.0
    telemetry = FakeTelemetry()
    config = config_for(tmp_path, llama, "--interval-s", "0.2", "--shutdown-timeout-s", "2", video=clip)
    timer = threading.Timer(0.5, _thread.interrupt_main)
    started = time.monotonic()
    timer.start()
    run, result = run_baseline(config, telemetry=telemetry)
    elapsed = time.monotonic() - started
    timer.join()

    assert result.exit_code == 130
    manifest = result.manifest
    assert manifest["run_end_reason"] == "interrupted"
    assert manifest["source"]["end"]["reason"] == EndReason.INTERRUPTED.value
    assert manifest["threads_not_joined"] == [] and baseline_threads_alive() == []
    assert not run.source.is_open
    assert run.client_closed and telemetry.closed
    assert elapsed < 2.0  # the 10 s request was abandoned, not waited out
    requests = read_jsonl(result.run_dir / "requests.jsonl")
    assert len(requests) == 1 and requests[0]["status"] in ("connection_error", "abandoned_at_shutdown")
    assert (result.run_dir / "manifest.json").exists()

    # The same source path can be opened again right away.
    with ReplaySource(clip) as again:
        assert again.read().frame_id == 0


def test_duration_limit_stops_a_run_and_exits_zero(tmp_path, llama):
    long_clip = write_test_video(tmp_path / "long.avi", frames=100, fps=20.0)  # 5 s
    config = config_for(tmp_path, llama, "--interval-s", "0.2", "--duration-s", "0.6", video=long_clip)
    run, result = run_baseline(config)
    assert result.exit_code == 0
    assert result.manifest["run_end_reason"] == "duration_limit"
    assert 0.6 <= result.manifest["times"]["observed_duration_s"] < 1.0
    assert baseline_threads_alive() == []


def test_webcam_source_runs_through_the_same_entry_point(tmp_path, llama):
    capture = FakeVideoCapture([solid_frame(i) for i in range(200)], read_delay_s=0.02)
    factory = CaptureFactory(lambda: capture)
    config = parse_args(["--source", "webcam", "--interval-s", "0.2", "--duration-s", "0.7",
                         "--no-display", "--run-dir", str(tmp_path / "cam"), "--vlm-url", llama.url])
    run, result = run_baseline(
        config, source_factory=lambda on_drop: WebcamSource(0, capture_factory=factory, on_drop=on_drop)
    )
    assert result.exit_code == 0 and result.manifest["run_end_reason"] == "duration_limit"
    requests = read_jsonl(result.run_dir / "requests.jsonl")
    assert 3 <= len(requests) <= 5
    assert all(r["source_kind"] == "webcam" and r["source_time_s"] is None for r in requests)
    assert result.manifest["source"]["info"]["backend"] == "FAKE"
    assert capture.released


def test_source_errors_are_not_reported_as_success(tmp_path, llama):
    placeholder = tmp_path / "fake.avi"
    placeholder.write_bytes(b"")
    truncated = FakeVideoCapture([solid_frame(i) for i in range(6)] + [FAIL], frame_count=100, fps=20.0)
    config = config_for(tmp_path, llama, "--interval-s", "0.1", video=placeholder)
    run, result = run_baseline(
        config,
        source_factory=lambda on_drop: ReplaySource(placeholder, capture_factory=lambda *_: truncated, on_drop=on_drop),
    )
    assert result.exit_code == 2
    assert result.manifest["run_end_reason"] == "incomplete_source"
    assert result.manifest["source"]["end"]["complete"] is False


def test_source_open_failure_still_writes_a_manifest(tmp_path, llama):
    config = config_for(tmp_path, llama, video=tmp_path / "missing.avi")
    run, result = run_baseline(config)
    assert result.exit_code == 2
    manifest = json.loads((result.run_dir / "manifest.json").read_text())
    assert manifest["run_end_reason"] == "source_open_failed"
    assert "not found" in manifest["error_detail"]


def test_source_drops_reach_the_drop_log(tmp_path, llama):
    placeholder = tmp_path / "fake.avi"
    placeholder.write_bytes(b"")
    entries = [solid_frame(0), solid_frame(1), None, solid_frame(3), solid_frame(4)]
    capture = FakeVideoCapture(entries, fps=10.0)
    config = config_for(tmp_path, llama, "--interval-s", "0.1", video=placeholder)
    run, result = run_baseline(
        config, source_factory=lambda on_drop: ReplaySource(placeholder, capture_factory=lambda *_: capture, on_drop=on_drop)
    )
    drops = [d for d in read_jsonl(result.run_dir / "drops.jsonl") if d["origin"] == "source"]
    assert [(d["frame_id"], d["reason"]) for d in drops] == [(2, "empty_frame")]
    assert result.manifest["counts"]["source_drops"] == {"empty_frame": 1}


# --------------------------------------------------------------------------- telemetry


def test_telemetry_is_written_and_unavailable_sensors_are_never_zero(tmp_path, llama, clip):
    config = config_for(tmp_path, llama, "--interval-s", "0.5", "--duration-s", "0.5", "--telemetry-interval-s", "0.1",
                        video=clip, name="ok")
    _, result = run_baseline(config)
    samples = read_jsonl(result.run_dir / "telemetry.jsonl")
    assert len(samples) >= 4 and all(s["valid"] and s["unit"] == "W" for s in samples)
    assert result.manifest["telemetry"]["metadata"]["synthetic"] is True

    config = config_for(tmp_path, llama, "--interval-s", "0.5", "--duration-s", "0.3", "--telemetry-interval-s", "0.1",
                        video=clip, name="unavailable")
    _, result = run_baseline(config, telemetry=FakeTelemetry(available=False))
    samples = read_jsonl(result.run_dir / "telemetry.jsonl")
    assert samples and all(s["valid"] is False and s["value"] is None and s["error"] for s in samples)

    config = config_for(tmp_path, llama, "--telemetry", "off", "--duration-s", "0.2",
                        video=clip, name="off")
    _, result = run_baseline(config)
    assert (result.run_dir / "telemetry.jsonl").read_text() == ""
    assert result.manifest["telemetry"] == {"kind": "off"}


# --------------------------------------------------------------------------- CLI


@pytest.mark.parametrize(
    "argv",
    [
        ["--source", "replay"],
        ["--source", "webcam", "--video", "x.avi"],
        ["--source", "replay", "--video", "x.avi", "--interval-s", "0"],
        ["--source", "replay", "--video", "x.avi", "--interval-s", "-1"],
        ["--source", "replay", "--video", "x.avi", "--vlm", "fake"],
        ["--source", "camera"],
    ],
)
def test_invalid_cli_arguments_exit_2(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        parse_args(argv)
    assert exc.value.code == 2


def test_pending_real_telemetry_fails_clearly_without_creating_a_run(tmp_path, llama, clip, capsys):
    run_dir = tmp_path / "never"
    code = main(["--source", "replay", "--video", str(clip), "--no-display", "--run-dir", str(run_dir),
                 "--vlm-url", llama.url, "--telemetry", "real"])
    assert code == 2
    assert "pending #2" in capsys.readouterr().err
    assert not run_dir.exists()


def test_missing_llama_server_fails_before_the_run(tmp_path, clip, capsys):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{s.getsockname()[1]}"
    run_dir = tmp_path / "never"
    code = main(["--source", "replay", "--video", str(clip), "--no-display", "--run-dir", str(run_dir),
                 "--vlm-url", url])
    assert code == 2
    assert "no ready llama-server" in capsys.readouterr().err
    assert not run_dir.exists()


def test_requests_reach_llama_server_and_log_its_reply(tmp_path, llama, clip):
    llama.respond = lambda path, body: reply(text="A moving red box.")
    config = config_for(tmp_path, llama, "--interval-s", "0.5", "--duration-s", "1.2", video=clip)
    run, result = run_baseline(config)
    assert result.exit_code == 0
    requests = read_jsonl(result.run_dir / "requests.jsonl")
    assert len(requests) == 3
    assert all(r["status"] == "ok" and r["text"] == "A moving red box." and r["finish_reason"] == "stop" for r in requests)
    assert requests[0]["usage"]["prompt_tokens"] == 150
    assert result.manifest["vlm"]["kind"] == "llama-server"
    posted = [json.loads(body) for method, path, body in llama.requests]
    assert [p["max_tokens"] for p in posted] == [64] * 3


def test_refuses_to_overwrite_a_non_empty_run_dir(tmp_path, llama, clip, capsys):
    run_dir = tmp_path / "used"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text("{}")
    code = main(["--source", "replay", "--video", str(clip), "--no-display", "--run-dir", str(run_dir),
                 "--vlm-url", llama.url])
    assert code == 2
    assert (run_dir / "manifest.json").read_text() == "{}"
