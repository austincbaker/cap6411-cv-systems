"""Gesture scene state and the shared event derivation (item 2b). No camera or model needed."""

from __future__ import annotations

import json

import pytest

from app.state import Evidence, GestureScene
from tests.fakes.fake_llama import FakeLlama
from tests.test_app_baseline import config_for, read_jsonl, run_baseline
from tests.test_gate import write_event_clip


def evidence(n: int) -> Evidence:
    return Evidence(
        f"r{n}", n, source_time_s=float(n), host_capture_s=100.0 + n, response_available_s=102.5 + n
    )


def feed(scene: GestureScene, answers) -> list[tuple[int, str, str]]:
    """(answer index, transition, gesture) for each event; None in ``answers`` is unknown."""
    out = []
    for n, answer in enumerate(answers):
        for event in scene.update(answer, None if answer is None else evidence(n)):
            assert event.evidence.request_id == f"r{n}"
            out.append((n, event.transition, event.gesture))
    return out


def test_scene_starts_at_none_so_a_gesture_in_the_first_answer_is_an_onset():
    assert feed(GestureScene(), ["none", "none"]) == []
    assert feed(GestureScene(), ["thumbs_up"]) == [(0, "onset", "thumbs_up")]


def test_a_held_gesture_is_reported_once():
    scene = GestureScene()
    assert feed(scene, ["thumbs_up"] * 5) == [(0, "onset", "thumbs_up")]
    assert scene.gesture == "thumbs_up" and scene.changed.request_id == "r0"


def test_the_same_gesture_after_the_hand_drops_rearms():
    events = feed(GestureScene(), ["thumbs_up", "none", "none", "thumbs_up"])
    assert events == [
        (0, "onset", "thumbs_up"),
        (1, "offset", "thumbs_up"),
        (3, "onset", "thumbs_up"),
    ]


def test_switching_gestures_ends_one_and_starts_the_other_from_the_same_answer():
    events = feed(GestureScene(), ["peace_sign", "thumbs_up", "none"])
    assert events == [
        (0, "onset", "peace_sign"),
        (1, "offset", "peace_sign"),
        (1, "onset", "thumbs_up"),
        (2, "offset", "thumbs_up"),
    ]


def test_unknown_answers_keep_the_confirmed_gesture_and_track_staleness():
    scene = GestureScene()
    assert feed(scene, ["thumbs_up", None, None, "thumbs_up", None]) == [(0, "onset", "thumbs_up")]
    assert scene.gesture == "thumbs_up"  # unknown is never a negative
    assert scene.unknown_since_valid == 1 and scene.last_valid.request_id == "r3"
    assert scene.changed.request_id == "r0"  # last change time is the onset's answer
    assert scene.overlay_line() == "scene: thumbs_up since frame 0, 1 unknown since"


def test_confirm_needs_that_many_valid_answers_in_a_row():
    scene = GestureScene(confirm=2)
    # A one-answer blip is ignored; unknown answers neither confirm nor reset a pending change.
    answers = ["thumbs_up", "none", "thumbs_up", None, "thumbs_up", "thumbs_up", "none", "none"]
    assert feed(scene, answers) == [(4, "onset", "thumbs_up"), (7, "offset", "thumbs_up")]
    with pytest.raises(ValueError):
        GestureScene(confirm=0)


def test_scene_summary_for_the_manifest():
    scene = GestureScene()
    assert scene.as_dict()["changed"] is None and scene.overlay_line() == "scene: none since start"
    feed(scene, ["none", "peace_sign"])
    summary = scene.as_dict()
    assert summary["gesture"] == "peace_sign" and summary["confirm"] == 1
    assert summary["changed"]["request_id"] == "r1"
    assert summary["changed"]["available_source_time_s"] == pytest.approx(1.0 + 2.5)
    json.dumps(summary)


def answer(gesture: str) -> str:
    return json.dumps({"gesture": gesture})


def test_app_writes_onsets_and_offsets_through_the_shared_derivation(tmp_path):
    clip = write_event_clip(tmp_path / "desk.avi", seconds=2.0)
    texts = [
        answer("none"),
        answer("thumbs_up"),
        answer("thumbs_up"),  # held: no new event
        "The person is giving a thumbs up.",  # invalid: unknown, state kept
        answer("peace_sign"),  # switch: offset and onset
        answer("none"),
    ]
    llama = FakeLlama(texts=texts)
    config = config_for(tmp_path, "--interval-s", "0.25", "--duration-s", "1.6", video=clip)
    _, result = run_baseline(config, llama)  # run_baseline also runs contracts-check
    requests = read_jsonl(result.run_dir / "requests.jsonl")
    predictions = read_jsonl(result.run_dir / "predictions.jsonl")
    assert [r["gesture"] for r in requests[:6]] == [
        "none",
        "thumbs_up",
        "thumbs_up",
        None,
        "peace_sign",
        "none",
    ]

    assert [(p["transition"], p["label"], p["observation"]["gesture"]) for p in predictions] == [
        ("onset", "thumbs_up", "thumbs_up"),
        ("offset", "thumbs_up", "peace_sign"),
        ("onset", "peace_sign", "peace_sign"),
        ("offset", "peace_sign", "none"),
    ]
    assert predictions[1]["onset_prediction_id"] == predictions[0]["prediction_id"]
    assert predictions[3]["onset_prediction_id"] == predictions[2]["prediction_id"]
    assert "onset_prediction_id" not in predictions[0]
    by_request = {r["request_id"]: r for r in requests}
    assert [by_request[p["request_id"]]["tick_index"] for p in predictions] == [1, 4, 4, 5]
    for p in predictions:
        r = by_request[p["request_id"]]
        assert (p["frame_id"], p["source_time_s"]) == (r["frame_id"], r["source_time_s"])
        assert p["response_available_s"] == r["response_available_s"]
        assert p["available_source_time_s"] == pytest.approx(
            r["source_time_s"] + r["response_available_s"] - r["host_capture_s"]
        )
    counts = result.manifest["counts"]
    assert counts["prediction:onset:thumbs_up"] == counts["prediction:offset:peace_sign"] == 1
    scene = result.manifest["scene"]
    assert (
        scene["gesture"] == "none" and scene["changed"]["request_id"] == requests[5]["request_id"]
    )


def test_failed_requests_leave_the_gesture_up(tmp_path):
    clip = write_event_clip(tmp_path / "desk.avi", seconds=1.5)
    outcomes = ["ok", "timeout", "http_error"] + ["empty"] * 20  # one valid answer, then none
    llama = FakeLlama(outcomes=outcomes, texts=[answer("thumbs_up")])
    config = config_for(tmp_path, "--interval-s", "0.2", "--duration-s", "0.9", video=clip)
    _, result = run_baseline(config, llama)
    requests = read_jsonl(result.run_dir / "requests.jsonl")
    statuses = [r["status"] for r in requests]
    assert statuses[:4] == ["ok", "timeout", "http_error", "empty_response"]
    predictions = read_jsonl(result.run_dir / "predictions.jsonl")
    assert [(p["transition"], p["label"]) for p in predictions] == [("onset", "thumbs_up")]
    assert result.manifest["scene"]["gesture"] == "thumbs_up"
    assert result.manifest["scene"]["unknown_since_valid"] == len(requests) - 1 >= 3


def test_gated_and_fixed_runs_share_the_derivation(tmp_path):
    clip = write_event_clip(tmp_path / "desk.avi", seconds=3.0)
    gate = ("--gate-threshold", "0.05", "--gate-persist-checks", "1", "--gate-min-interval-s", "0")
    runs = {}
    for policy in ("fixed_interval", "gated"):
        llama = FakeLlama(texts=[answer("none"), answer("thumbs_up")])
        extra = ("--policy", "gated", *gate) if policy == "gated" else ()
        config = config_for(tmp_path, "--interval-s", "0.25", *extra, video=clip, name=policy)
        _, runs[policy] = run_baseline(config, llama)
    for policy, result in runs.items():
        predictions = read_jsonl(result.run_dir / "predictions.jsonl")
        assert [(p["transition"], p["label"]) for p in predictions] == [("onset", "thumbs_up")], (
            policy
        )
        assert result.manifest["policy"] == policy
    gated = read_jsonl(runs["gated"].run_dir / "predictions.jsonl")[0]
    assert 0.9 <= gated["source_time_s"] <= 1.5  # sent when the gate saw the change
