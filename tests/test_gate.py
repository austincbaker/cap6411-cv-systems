"""Change gate (item 2a): deterministic scores and decisions on synthetic frames, plus a
gated app run against the fake llama-server. No camera or model needed."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from gates import ChangeGate, GateConfig, change_score, preprocess
from tests.test_app_baseline import config_for, read_jsonl, run_baseline

W, H = 160, 120


def desk(brightness: int = 120, box: tuple[int, int, int, int] | None = None) -> np.ndarray:
    """A textured static scene; ``box`` (x, y, w, h) adds a dark object."""
    rng = np.random.default_rng(0)
    image = np.clip(rng.normal(brightness, 12, (H, W, 3)), 0, 255).astype(np.uint8)
    if box is not None:
        x, y, w, h = box
        image[y : y + h, x : x + w] = 20
    return image


def scores(a, b, grid=4, delta=25):
    return change_score(preprocess(a, W, H), preprocess(b, W, H), delta, grid)


def test_identical_frames_score_zero():
    assert scores(desk(), desk()) == (0.0, 0.0)


def test_uniform_lighting_shift_does_not_count_as_change():
    cell, overall = scores(desk(120), desk(160))
    assert cell < 0.01 and overall < 0.01


def test_small_local_object_shows_in_the_cell_score_not_the_global_one():
    cell, overall = scores(desk(), desk(box=(5, 5, 18, 14)))
    assert cell > 0.2  # a large part of one 40x30 cell
    assert overall < 0.03  # diluted over the whole frame
    global_only, _ = scores(desk(), desk(box=(5, 5, 18, 14)), grid=1)
    assert global_only == pytest.approx(overall)


def decide(gate, image, t):
    d = gate.decide(image, t)
    if d.trigger:
        gate.acknowledge(d, t)
    return d.reason


def test_first_frame_triggers_then_unchanged_frames_skip():
    gate = ChangeGate(GateConfig())
    assert decide(gate, desk(), 0.0) == "gate_initial"
    assert [decide(gate, desk(), t) for t in (0.5, 1.0, 1.5)] == ["gate_no_change"] * 3


def test_change_triggers_and_becomes_the_new_reference():
    gate = ChangeGate(GateConfig())
    decide(gate, desk(), 0.0)
    placed = desk(box=(60, 40, 30, 30))
    assert decide(gate, placed, 1.0) == "gate_change"
    assert decide(gate, placed, 1.5) == "gate_no_change"  # acknowledged: no repeat
    assert decide(gate, desk(), 2.0) == "gate_change"  # removal is a change too


def test_cooldown_skips_a_change_until_the_minimum_interval_passes():
    gate = ChangeGate(GateConfig(min_interval_s=3.0))
    decide(gate, desk(), 0.0)
    placed = desk(box=(60, 40, 30, 30))
    assert decide(gate, placed, 1.0) == "gate_cooldown"
    assert decide(gate, placed, 3.0) == "gate_change"  # still differs from the reference


def test_refresh_forces_a_call_without_change():
    gate = ChangeGate(GateConfig(refresh_s=10.0))
    decide(gate, desk(), 0.0)
    assert decide(gate, desk(), 9.9) == "gate_no_change"
    assert decide(gate, desk(), 10.0) == "gate_refresh"
    assert decide(gate, desk(), 15.0) == "gate_no_change"


def test_a_trigger_that_was_not_sent_keeps_the_old_reference():
    gate = ChangeGate(GateConfig())
    decide(gate, desk(), 0.0)
    placed = desk(box=(60, 40, 30, 30))
    assert gate.decide(placed, 1.0).reason == "gate_change"  # not acknowledged (VLM busy)
    assert gate.decide(placed, 1.5).reason == "gate_change"


def test_gradual_change_accumulates_against_the_acknowledged_reference():
    gate = ChangeGate(GateConfig(threshold=0.3))
    decide(gate, desk(), 0.0)
    reasons = [decide(gate, desk(box=(60, 40, 6 * k, 30)), float(k)) for k in range(1, 8)]
    assert reasons[0] == "gate_no_change"  # each step alone is too small...
    assert "gate_change" in reasons  # ...but the total against the reference is not


@pytest.mark.parametrize(
    "kwargs",
    [{"threshold": 0}, {"threshold": 1.5}, {"pixel_delta": 255}, {"refresh_s": 0}, {"grid": 0}],
)
def test_invalid_config_is_rejected(kwargs):
    with pytest.raises(ValueError):
        GateConfig(**kwargs)


# ---------------------------------------------------------------------------- app


def write_event_clip(path: Path, *, seconds: float = 3.0, fps: float = 20.0) -> Path:
    """Static desk; a box is placed at 1.0 s and stays."""
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (W, H))
    for i in range(int(seconds * fps)):
        writer.write(desk(box=(60, 40, 30, 30)) if i >= fps else desk())
    writer.release()
    return path


def test_gated_run_skips_unchanged_ticks_and_logs_every_decision(tmp_path):
    clip = write_event_clip(tmp_path / "desk.avi")
    _, fixed = run_baseline(config_for(tmp_path, "--interval-s", "0.25", video=clip, name="fixed"))
    run, gated = run_baseline(
        config_for(tmp_path, "--interval-s", "0.25", "--policy", "gated", video=clip, name="gated")
    )
    assert gated.exit_code == 0 and gated.manifest["policy"] == "gated"
    assert gated.manifest["gate"]["threshold"] == GateConfig.threshold
    requests = read_jsonl(gated.run_dir / "requests.jsonl")
    drops = read_jsonl(gated.run_dir / "drops.jsonl")
    gate_drops = [d for d in drops if d["origin"] == "gate"]

    # One call for the first frame and one for the placed box; the rest are gate skips.
    assert [r["gate_reason"] for r in requests] == ["gate_initial", "gate_change"]
    assert 0.9 <= requests[1]["source_time_s"] <= 1.5
    assert len(requests) < len(read_jsonl(fixed.run_dir / "requests.jsonl"))
    assert gate_drops and {d["reason"] for d in gate_drops} == {"gate_no_change"}
    assert all(d["gate_score"] is not None and d["gate_compute_s"] >= 0 for d in gate_drops)

    # Every tick is accounted for exactly once: a request or a logged skip.
    ticks = sorted(
        [r["tick_index"] for r in requests]
        + [d["tick_index"] for d in drops if d["origin"] != "source"]
    )
    assert ticks == list(range(len(ticks)))
    counts = gated.manifest["counts"]
    assert counts["gate_no_change"] == len(gate_drops) and counts["gate_change"] == 1
    json.dumps(gated.manifest)  # serializable without the GateConfig object


def test_fixed_interval_records_no_gate_fields(tmp_path):
    clip = write_event_clip(tmp_path / "desk.avi", seconds=1.0)
    _, result = run_baseline(config_for(tmp_path, "--interval-s", "0.25", video=clip))
    assert result.manifest["policy"] == "fixed_interval" and result.manifest["gate"] is None
    assert all("gate_reason" not in r for r in read_jsonl(result.run_dir / "requests.jsonl"))
