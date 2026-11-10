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


def raw(**overrides):
    """The bare mechanism (no persistence or cooldown) unless a test sets them."""
    return GateConfig(
        **{"threshold": 0.05, "persist_checks": 1, "min_interval_s": 0.0, **overrides}
    )


def decide(gate, image, t):
    d = gate.decide(image, t)
    if d.trigger:
        gate.acknowledge(d, t)
    return d.reason


def test_first_frame_triggers_then_unchanged_frames_skip():
    gate = ChangeGate(raw())
    assert decide(gate, desk(), 0.0) == "gate_initial"
    assert [decide(gate, desk(), t) for t in (0.5, 1.0, 1.5)] == ["gate_no_change"] * 3


def test_change_triggers_and_becomes_the_new_reference():
    gate = ChangeGate(raw())
    decide(gate, desk(), 0.0)
    placed = desk(box=(60, 40, 30, 30))
    assert decide(gate, placed, 1.0) == "gate_change"
    assert decide(gate, placed, 1.5) == "gate_no_change"  # acknowledged: no repeat
    assert decide(gate, desk(), 2.0) == "gate_change"  # removal is a change too


def test_cooldown_skips_a_change_until_the_minimum_interval_passes():
    gate = ChangeGate(raw(min_interval_s=3.0))
    decide(gate, desk(), 0.0)
    placed = desk(box=(60, 40, 30, 30))
    assert decide(gate, placed, 1.0) == "gate_cooldown"
    assert decide(gate, placed, 3.0) == "gate_change"  # still differs from the reference


def test_refresh_forces_a_call_without_change():
    gate = ChangeGate(raw(refresh_s=10.0))
    decide(gate, desk(), 0.0)
    assert decide(gate, desk(), 9.9) == "gate_no_change"
    assert decide(gate, desk(), 10.0) == "gate_refresh"
    assert decide(gate, desk(), 15.0) == "gate_no_change"


def test_a_trigger_that_was_not_sent_keeps_the_old_reference():
    gate = ChangeGate(raw())
    decide(gate, desk(), 0.0)
    placed = desk(box=(60, 40, 30, 30))
    assert gate.decide(placed, 1.0).reason == "gate_change"  # not acknowledged (VLM busy)
    assert gate.decide(placed, 1.5).reason == "gate_change"


def test_gradual_change_accumulates_against_the_acknowledged_reference():
    gate = ChangeGate(raw(threshold=0.3))
    decide(gate, desk(), 0.0)
    reasons = [decide(gate, desk(box=(60, 40, 6 * k, 30)), float(k)) for k in range(1, 8)]
    assert reasons[0] == "gate_no_change"  # each step alone is too small...
    assert "gate_change" in reasons  # ...but the total against the reference is not


def test_persistence_skips_a_change_that_comes_and_goes():
    gate = ChangeGate(raw(persist_checks=3))
    decide(gate, desk(), 0.0)
    moved = desk(box=(60, 40, 30, 30))
    # Two checks of change, then back to the reference: never sent.
    assert [decide(gate, img, t) for img, t in ((moved, 0.5), (moved, 1.0), (desk(), 1.5))] == [
        "gate_persisting",
        "gate_persisting",
        "gate_no_change",
    ]
    # A change that stays is sent on its third check, then ends.
    reasons = [decide(gate, moved, t) for t in (2.0, 2.5, 3.0, 3.5)]
    assert reasons == ["gate_persisting", "gate_persisting", "gate_change", "gate_no_change"]


def test_hysteresis_keeps_a_started_change_alive_below_the_threshold():
    big, faint = desk(box=(60, 40, 30, 30)), desk(box=(60, 40, 30, 12))
    start, _ = scores(desk(), big)
    weak, _ = scores(desk(), faint)
    assert weak < start  # the faint frame alone would not start a change
    threshold = (weak + start) / 2
    plain = ChangeGate(raw(threshold=threshold, persist_checks=2))
    held = ChangeGate(raw(threshold=threshold, persist_checks=2, release_threshold=weak))
    for gate in (plain, held):
        decide(gate, desk(), 0.0)
        assert decide(gate, big, 0.5) == "gate_persisting"
    assert decide(plain, faint, 1.0) == "gate_no_change"  # change broken off
    assert decide(held, faint, 1.0) == "gate_change"  # still alive above the release level


def test_cooldown_applies_after_persistence():
    gate = ChangeGate(raw(persist_checks=2, min_interval_s=3.0))
    decide(gate, desk(), 0.0)
    moved = desk(box=(60, 40, 30, 30))
    reasons = [decide(gate, moved, t) for t in (0.5, 1.0, 2.0, 3.0)]
    assert reasons == ["gate_persisting", "gate_cooldown", "gate_cooldown", "gate_change"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"threshold": 0},
        {"threshold": 1.5},
        {"pixel_delta": 255},
        {"refresh_s": 0},
        {"grid": 0},
        {"persist_checks": 0},
        {"threshold": 0.1, "release_threshold": 0.2},
        {"release_threshold": 0},
    ],
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
    assert gated.manifest["gate"]["persist_checks"] == GateConfig.persist_checks
    requests = read_jsonl(gated.run_dir / "requests.jsonl")
    drops = read_jsonl(gated.run_dir / "drops.jsonl")
    gate_drops = [d for d in drops if d["origin"] == "gate"]

    # One call for the first frame and one for the placed box (at 1.0 s), sent once the change
    # has lasted persist_checks checks and the 2 s minimum interval has passed; the rest are skips.
    assert [r["gate_reason"] for r in requests] == ["gate_initial", "gate_change"]
    assert 1.7 <= requests[1]["source_time_s"] <= 2.5
    assert len(requests) < len(read_jsonl(fixed.run_dir / "requests.jsonl"))
    reasons = {d["reason"] for d in gate_drops}
    assert "gate_persisting" in reasons and reasons <= {
        "gate_no_change",
        "gate_persisting",
        "gate_cooldown",
    }
    assert all(d["gate_score"] is not None and d["gate_compute_s"] >= 0 for d in gate_drops)

    # Every tick is accounted for exactly once: a request or a logged skip.
    ticks = sorted(
        [r["tick_index"] for r in requests]
        + [d["tick_index"] for d in drops if d["origin"] != "source"]
    )
    assert ticks == list(range(len(ticks)))
    counts = gated.manifest["counts"]
    for reason in reasons:
        assert counts[reason] == sum(d["reason"] == reason for d in gate_drops)
    assert counts["gate_change"] == 1
    json.dumps(gated.manifest)  # serializable without the GateConfig object


def test_fixed_interval_records_no_gate_fields(tmp_path):
    clip = write_event_clip(tmp_path / "desk.avi", seconds=1.0)
    _, result = run_baseline(config_for(tmp_path, "--interval-s", "0.25", video=clip))
    assert result.manifest["policy"] == "fixed_interval" and result.manifest["gate"] is None
    assert all("gate_reason" not in r for r in read_jsonl(result.run_dir / "requests.jsonl"))
