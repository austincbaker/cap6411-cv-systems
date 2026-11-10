#!/usr/bin/env python3
"""Build a replay clip for gate checks (item 2a) from Jester-style frame folders.

A Jester clip is about 3 s of one gesture with no idle time, so a change gate has nothing to
skip in it. Each segment of the replay holds a clip's first frame (a still scene), then plays the
whole clip, so the gesture has a known window. The cut into the next segment changes the whole
scene and is expected to trigger the gate. The idle stretch is a frozen frame, with no sensor
noise, so it is easier for a gate than real idle video.

Writes an MJPG .avi, a JSON sidecar (clip ids, segment times) and a windows CSV for
scripts/gate_check.py. The frames stay local: never commit them or the output.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np


def load_clip(folder: Path) -> list[np.ndarray]:
    frames = [cv2.imread(str(path)) for path in sorted(folder.glob("*.jpg"))]
    return [frame for frame in frames if frame is not None]


def still_start(frames: list[np.ndarray], max_mean_diff: float = 2.0, count: int = 3) -> bool:
    """True when the first frames barely differ, i.e. the hand is not already moving."""
    gray = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).astype(np.int16) for f in frames[:count]]
    return all(float(np.abs(g - gray[0]).mean()) <= max_mean_diff for g in gray[1:])


def choose_clips(
    root: Path,
    count: int,
    seed: int,
    size: tuple[int, int],
    min_frames: int,
    max_frames: int,
) -> list[tuple[str, list[np.ndarray]]]:
    """Seeded pick of clips with the given (width, height), a usual length and a still start."""
    ids = sorted(path.name for path in root.iterdir() if path.is_dir())
    random.Random(seed).shuffle(ids)
    chosen = []
    for clip_id in ids:
        frames = load_clip(root / clip_id)
        if not frames or (frames[0].shape[1], frames[0].shape[0]) != size:
            continue
        if min_frames <= len(frames) <= max_frames and still_start(frames):
            chosen.append((clip_id, frames))
            if len(chosen) == count:
                break
    return chosen


def build(
    clips: list[tuple[str, list[np.ndarray]]],
    out: Path,
    fps: float,
    segment_s: float,
    label: str,
) -> dict:
    size = (clips[0][1][0].shape[1], clips[0][1][0].shape[0])
    segment_frames = round(segment_s * fps)
    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"MJPG"), fps, size)
    if not writer.isOpened():
        raise SystemExit(f"cannot write {out}")
    segments, written = [], 0
    try:
        for index, (clip_id, frames) in enumerate(clips):
            if (frames[0].shape[1], frames[0].shape[0]) != size:
                raise SystemExit(f"clip {clip_id} is not {size[0]}x{size[1]}")
            hold = segment_frames - len(frames)
            if hold < 1:
                raise SystemExit(f"clip {clip_id} ({len(frames)} frames) is longer than a segment")
            for _ in range(hold):
                writer.write(frames[0])
            for frame in frames:
                writer.write(frame)
            segments.append(
                {
                    "segment": index,
                    "clip_id": clip_id,
                    "clip_frames": len(frames),
                    "segment_start_s": written / fps,
                    "clip_start_s": (written + hold) / fps,
                    "segment_end_s": (written + segment_frames) / fps,
                }
            )
            written += segment_frames
    finally:
        writer.release()
    meta = {
        "fps": fps,
        "size": list(size),
        "frames": written,
        "duration_s": written / fps,
        "segments": segments,
    }
    out.with_suffix(".json").write_text(json.dumps(meta, indent=2) + "\n")
    with out.with_suffix(".windows.csv").open("w", newline="") as handle:
        rows = csv.writer(handle)
        rows.writerow(["label", "onset_s", "end_s"])
        for segment in segments:
            rows.writerow([label, segment["clip_start_s"], segment["segment_end_s"]])
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("frames_root", type=Path, help="folder of clip folders (00001.jpg, ...)")
    parser.add_argument("out", type=Path, help="output .avi (must not exist)")
    parser.add_argument(
        "--clip-ids", help="comma-separated clip folders, in order (skips the pick)"
    )
    parser.add_argument("--clips", type=int, default=4, help="clips to pick (default 4)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--size", default="176x100", help="WxH of clips to pick (default 176x100)")
    parser.add_argument("--min-frames", type=int, default=33)
    parser.add_argument("--max-frames", type=int, default=37)
    parser.add_argument("--fps", type=float, default=12.0, help="Jester frame rate (default 12)")
    parser.add_argument("--segment-s", type=float, default=15.0)
    parser.add_argument("--label", default="thumb_up", help="label in the windows CSV")
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error(f"{args.out} exists; write each replay to a new path")
    if args.clip_ids:
        clips = [(cid, load_clip(args.frames_root / cid)) for cid in args.clip_ids.split(",")]
        missing = [cid for cid, frames in clips if not frames]
        if missing:
            parser.error(f"no frames for clip(s) {', '.join(missing)}")
    else:
        width, height = (int(v) for v in args.size.lower().split("x"))
        clips = choose_clips(
            args.frames_root,
            args.clips,
            args.seed,
            (width, height),
            args.min_frames,
            args.max_frames,
        )
        if len(clips) < args.clips:
            parser.error(f"only {len(clips)} clips match; relax --size or the frame limits")
    meta = build(clips, args.out, args.fps, args.segment_s, args.label)
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
