"""Gate development tools (item 2a): the Jester replay builder and the window check, on
synthetic frames and fake run directories."""

import csv
import json
import re

import cv2
import numpy as np

from gates import GateConfig
from scripts.gate_check import check_run, main, read_windows
from scripts.gate_sweep import sample_ticks, score, simulate
from scripts.jester_replay import build, choose_clips, still_start


def write_clip(folder, frames):
    folder.mkdir(parents=True)
    for index, frame in enumerate(frames, start=1):
        cv2.imwrite(str(folder / f"{index:05d}.jpg"), frame)


def gesture_clip(n=6, size=(32, 16), moving_from=3):
    frames = []
    for index in range(n):
        frame = np.full((size[1], size[0], 3), 120, np.uint8)
        if index >= moving_from:
            frame[:, : 4 * (index - moving_from + 1)] = 250  # a "hand" sweeping in
        frames.append(frame)
    return frames


def test_still_start_rejects_a_clip_already_moving():
    assert still_start(gesture_clip(moving_from=3))
    assert not still_start(gesture_clip(moving_from=0))


def test_choose_clips_filters_size_length_and_motion(tmp_path):
    write_clip(tmp_path / "1", gesture_clip())
    write_clip(tmp_path / "2", gesture_clip(moving_from=0))  # moving at frame 1
    write_clip(tmp_path / "3", gesture_clip(size=(20, 16)))  # other size
    write_clip(tmp_path / "4", gesture_clip(n=3))  # too short
    chosen = choose_clips(tmp_path, 4, seed=0, size=(32, 16), min_frames=5, max_frames=8)
    assert [clip_id for clip_id, _ in chosen] == ["1"]


def test_build_holds_first_frame_then_plays_and_writes_windows(tmp_path):
    clips = [("a", gesture_clip()), ("b", gesture_clip())]
    out = tmp_path / "replay.avi"
    meta = build(clips, out, fps=4.0, segment_s=5.0, label="thumb_up")
    assert meta["frames"] == 40 and meta["duration_s"] == 10.0
    assert [s["clip_start_s"] for s in meta["segments"]] == [3.5, 8.5]  # 14 held frames each
    capture = cv2.VideoCapture(str(out))
    assert int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) == 40
    capture.release()
    windows = read_windows(out.with_suffix(".windows.csv"))
    assert windows == [
        {"label": "thumb_up", "onset_s": 3.5, "end_s": 5.0},
        {"label": "thumb_up", "onset_s": 8.5, "end_s": 10.0},
    ]
    assert json.loads(out.with_suffix(".json").read_text())["segments"][1]["clip_id"] == "b"


def fake_run(run_dir, policy, requests, counts=None):
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text(json.dumps({"policy": policy, "counts": counts or {}}))
    with (run_dir / "requests.jsonl").open("w") as handle:
        for index, (t, status, text) in enumerate(requests):
            record = {"request_id": f"r{index}", "source_time_s": t, "status": status, "text": text}
            handle.write(json.dumps(record) + "\n")


def windows_csv(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["label", "onset_s", "end_s"])
        writer.writerows(rows)
    return read_windows(path)


def test_check_run_counts_hits_latency_names_and_outside(tmp_path):
    fake_run(
        tmp_path / "run",
        "gated",
        [
            (0.0, "ok", "A person sitting."),
            (5.2, "ok", "A person sitting."),
            (6.0, "ok", "A person giving a thumbs-up."),
            (7.0, "error", None),  # failed requests never count as a catch
            (8.0, "ok", "A person sitting."),  # end is exclusive
            (20.0, "ok", "A person sitting."),
        ],
        counts={"tick_skipped_busy": 3, "gate_change": 4, "requests": 6},
    )
    windows = windows_csv(tmp_path / "w.csv", [["thumb_up", 5, 8], ["peace", 12, 14]])
    report = check_run(tmp_path / "run", windows, 0.0, {"thumb_up": re.compile("thumb")})
    first, second = report["windows"]
    assert (first["calls"], first["named"]) == (2, 1)
    assert round(first["first_latency_s"], 2) == 0.2
    assert round(first["first_named_latency_s"], 2) == 1.0
    assert second["calls"] == 0 and second["named"] is None  # no pattern for peace
    assert report["calls"] == 6 and report["ok"] == 5
    assert (report["windows_caught"], report["windows_named"]) == (1, 1)
    assert report["outside_times_s"] == [0.0, 8.0, 20.0]
    assert report["gate"] == {"gate_change": 4} and report["tick_skipped_busy"] == 3


def test_tolerance_widens_both_edges(tmp_path, capsys):
    fake_run(tmp_path / "run", "fixed_interval", [(3.6, "ok", "thumb"), (8.4, "ok", "thumb")])
    windows_csv(tmp_path / "w.csv", [["thumb_up", 4, 8]])
    assert main([str(tmp_path / "run"), "--windows", str(tmp_path / "w.csv"), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["windows"][0]["calls"] == 0
    args = [str(tmp_path / "run"), "--windows", str(tmp_path / "w.csv"), "--tolerance-s", "0.5"]
    assert main(args + ["--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["windows"][0]["calls"] == 2


def test_gate_sweep_models_busy_time_and_scores_windows(tmp_path):
    clip = tmp_path / "clip.avi"
    writer = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (64, 48))
    for index in range(100):  # 10 s; a bright block from 4 s to 7 s
        frame = np.full((48, 64, 3), 100, np.uint8)
        if 40 <= index < 70:
            frame[10:40, 10:40] = 250
        writer.write(frame)
    writer.release()
    ticks = sample_ticks(clip, 0.5, (32, 24))
    assert len(ticks) == 20 and ticks[0][0] == 0.0
    config = GateConfig(threshold=0.2, persist_checks=2, width=32, height=24, grid=2)
    sent = simulate(ticks, 0.5, 1.0, config)
    assert sent == [0.0, 4.5, 7.5]  # first frame, then the second check of each change
    fixed = simulate(ticks, 0.5, 2.5, None, fixed_interval_s=1.0)
    assert fixed == [0.0, 3.0, 6.0, 9.0]  # busy 2.5 s skips every other 1 s tick
    result = score(sent, [{"label": "x", "onset_s": 4.0, "end_s": 7.0}], 0.0, 10.0)
    assert result["windows_caught"] == 1 and result["outside_calls"] == 2
