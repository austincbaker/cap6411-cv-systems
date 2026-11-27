"""Pilot replay runner and scorer, on fake run directories and a stubbed app process."""

import csv
import json

import pytest

from scripts import run_pilot_eval
from scripts.score_pilot_eval import main as score_main

ANNOTATIONS = [
    ["schema_version", "video_id", "event_id", "label", "onset_s", "end_s"],
    ["1-draft", "clip_a", "E1", "thumbs_up", "10.0", "12.0"],
    ["1-draft", "clip_a", "E2", "peace_sign", "30.0", "33.0"],
]


def write_annotations(path):
    with path.open("w", newline="") as handle:
        csv.writer(handle).writerows(ANNOTATIONS)
    return path


def fake_run(run_dir, policy, answers, onsets, interval_s=2.0, counts=None):
    """answers: (source_time_s, gesture) with each answer available 2 s after capture."""
    run_dir.mkdir(parents=True)
    manifest = {
        "policy": policy,
        "config": {"interval_s": interval_s},
        "exit_code": 0,
        "run_end_reason": "eof",
        "counts": counts or {},
    }
    (run_dir / "manifest.json").write_text(json.dumps(manifest))
    with (run_dir / "requests.jsonl").open("w") as handle:
        for index, (t, gesture) in enumerate(answers):
            record = {
                "request_id": f"r{index}",
                "frame_id": index,
                "source_time_s": t,
                "host_capture_s": 100.0 + t,
                "response_available_s": 102.0 + t,
                "status": "ok",
                "gesture": gesture,
                "answer_error": None if gesture else "schema",
                "elapsed_s": 2.0,
                "output_tokens": 20,
            }
            handle.write(json.dumps(record) + "\n")
    with (run_dir / "predictions.jsonl").open("w") as handle:
        for label, t in onsets:
            handle.write(
                json.dumps({"transition": "onset", "label": label, "source_time_s": t}) + "\n"
            )


def test_scores_named_windows_false_mentions_delay_and_onsets(tmp_path, capsys):
    annotations = write_annotations(tmp_path / "pilot.csv")
    runs = tmp_path / "runs"
    # Window 1 named (thumbs at 10.5), window 2 caught but named wrong, one false mention at 50.
    fake_run(
        runs / "clip_a-fixed",
        "fixed_interval",
        [
            (0.0, "none"),
            (10.5, "thumbs_up"),
            (31.0, "thumbs_up"),
            (40.0, "none"),
            (50.0, "peace_sign"),
        ],
        onsets=[("thumbs_up", 10.5), ("peace_sign", 50.0)],
    )
    fake_run(
        runs / "clip_a-gated",
        "gated",
        [(9.5, "thumbs_up"), (30.5, "peace_sign"), (31.5, None)],
        onsets=[("thumbs_up", 9.5), ("peace_sign", 30.5)],
        interval_s=0.5,
        counts={"gate_no_change": 5, "gate_cooldown": 2, "tick_skipped_busy": 3},
    )
    fake_run(runs / "control-gated", "gated", [(5.0, "none")], onsets=[], interval_s=0.5)
    (runs / "notes").mkdir()  # not a run directory: ignored

    assert score_main([str(runs), "--annotations", str(annotations)]) == 0
    rows = {(r["clip"], r["policy"]): r for r in csv.DictReader((runs / "quality.csv").open())}
    assert set(rows) == {("clip_a", "fixed"), ("clip_a", "gated"), ("control", "gated")}

    fixed = rows["clip_a", "fixed"]
    assert (fixed["windows"], fixed["windows_caught"], fixed["windows_named"]) == ("2", "2", "1")
    assert fixed["wrong_gesture_in_window"] == "1"
    assert fixed["false_mentions_outside"] == "1"
    assert fixed["median_delay_to_naming_answer_s"] == "2.5"  # 10.5 + 2 s answer - 10.0 onset
    assert (fixed["onsets"], fixed["onsets_in_window"], fixed["windows_with_onset"]) == (
        "2",
        "1",
        "1",
    )
    assert fixed["gate_skips"] == ""

    gated = rows["clip_a", "gated"]
    assert gated["windows_named"] == "2"  # 9.5 is inside the 1 s tolerance
    assert gated["answers_invalid"] == "1" and gated["invalid_errors"] == "schema"
    assert (gated["gate_skips"], gated["busy_skips"], gated["interval_s"]) == ("7", "3", "0.5")
    assert rows["control", "gated"]["windows"] == "0"

    out = capsys.readouterr().out
    assert "fixed (interval 2.0 s, 1 runs): 5 calls, named 1/2 windows" in out
    assert "gated (interval 0.5 s, 2 runs): 4 calls, named 2/2 windows" in out


def test_scorer_rejects_predictions_that_disagree_with_scene_state(tmp_path):
    annotations = write_annotations(tmp_path / "pilot.csv")
    runs = tmp_path / "runs"
    fake_run(runs / "clip_a-fixed", "fixed_interval", [(10.5, "thumbs_up")], onsets=[])
    with pytest.raises(SystemExit, match="differ from the scene-state derivation"):
        score_main([str(runs), "--annotations", str(annotations)])


def test_runner_replays_each_clip_once_with_the_given_policy_and_interval(
    tmp_path, monkeypatch, capsys
):
    videos = tmp_path / "videos"
    videos.mkdir()
    for clip in ("clip_a", "clip_b"):
        (videos / f"{clip}.mov").write_bytes(b"")
    out = tmp_path / "out"
    (out / "clip_b-gated").mkdir(parents=True)
    (out / "clip_b-gated" / "manifest.json").write_text("{}")  # finished earlier: skipped
    calls = []

    def fake_call(command, cwd, stdout, stderr):
        calls.append(command)
        run_dir = command[command.index("--run-dir") + 1]
        fake_run(tmp_path / run_dir, "gated", [(1.0, "none")], onsets=[])
        return 0

    monkeypatch.setattr(
        run_pilot_eval, "server_healthy", lambda url: url == "http://127.0.0.1:8080"
    )
    monkeypatch.setattr(run_pilot_eval.subprocess, "call", fake_call)
    args = ["--policy", "gated", "--interval-s", "0.5", "--out", str(out), "--videos", str(videos)]
    assert run_pilot_eval.main([*args, "--clips", "clip_a", "clip_b", "--duration-s", "5"]) == 0

    assert len(calls) == 1
    command = calls[0]
    assert command[command.index("--policy") + 1] == "gated"
    assert command[command.index("--interval-s") + 1] == "0.5"
    assert command[command.index("--video") + 1] == str(videos / "clip_a.mov")
    assert command[command.index("--duration-s") + 1] == "5.0"
    assert "--no-display" in command
    text = capsys.readouterr().out
    assert "skip clip_b-gated" in text
    assert "end clip_a-gated exit=0 median_call=2.00 s" in text


def test_runner_stops_on_missing_videos_or_an_unhealthy_server(tmp_path, monkeypatch):
    videos = tmp_path / "videos"
    videos.mkdir()
    args = ["--policy", "fixed", "--interval-s", "2", "--out", str(tmp_path / "out")]
    assert run_pilot_eval.main([*args, "--videos", str(videos), "--clips", "clip_a"]) == 2
    (videos / "clip_a.mov").write_bytes(b"")
    monkeypatch.setattr(run_pilot_eval, "server_healthy", lambda url: False)
    assert run_pilot_eval.main([*args, "--videos", str(videos), "--clips", "clip_a"]) == 3


def test_runner_requires_an_interval():
    with pytest.raises(SystemExit):
        run_pilot_eval.main(["--policy", "gated", "--out", "x"])
