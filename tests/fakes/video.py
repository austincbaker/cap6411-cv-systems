"""Generate small test videos with cv2.VideoWriter (nothing is committed to the repo)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def write_test_video(path: Path, *, frames: int = 20, fps: float = 10.0, width: int = 64, height: int = 48) -> Path:
    """Write an MJPG .avi whose frame i has mean brightness ~ (i * 10) % 256 and a moving box."""
    path = Path(path)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError("cv2.VideoWriter could not open an MJPG writer")
    try:
        for i in range(frames):
            image = np.full((height, width, 3), (i * 10) % 256, dtype=np.uint8)
            x = (i * 3) % max(1, width - 8)
            cv2.rectangle(image, (x, 4), (x + 8, 12), (0, 0, 255), -1)
            writer.write(image)
    finally:
        writer.release()
    return path
