"""Scriptable stand-in for ``cv2.VideoCapture``.

``frames`` is a list of entries, one per grab/read:
- a numpy image: a good frame
- ``None``: the frame grabs but decodes to nothing (empty frame)
- ``FAIL``: grab/read returns False at this position (stream error or camera glitch)
After the last entry, grab/read return False (end of stream).
"""

from __future__ import annotations

import time
from typing import Any, Optional, Sequence

import cv2
import numpy as np

FAIL = object()


def solid_frame(value: int, width: int = 32, height: int = 24) -> np.ndarray:
    return np.full((height, width, 3), value % 256, dtype=np.uint8)


class FakeVideoCapture:
    def __init__(
        self,
        frames: Sequence[Any],
        *,
        fps: float = 10.0,
        frame_count: Optional[float] = None,
        timestamps_ms: Optional[Sequence[float]] = None,
        opened: bool = True,
        backend: str = "FAKE",
        width: Optional[int] = None,
        height: Optional[int] = None,
        accept_settings: bool = False,
        close_after: Optional[int] = None,
        read_delay_s: float = 0.0,
    ) -> None:
        self.frames = list(frames)
        self.fps = fps
        self.frame_count = float(len(self.frames)) if frame_count is None else frame_count
        if timestamps_ms is None:
            period_ms = 1000.0 / fps if fps and fps > 0 and fps != float("inf") else 0.0
            timestamps_ms = [i * period_ms for i in range(len(self.frames))]
        self.timestamps_ms = list(timestamps_ms)
        self.opened = opened
        self.backend = backend
        self.width = width
        self.height = height
        self.accept_settings = accept_settings
        self.close_after = close_after
        self.read_delay_s = read_delay_s  # real sleep per read(), to mimic a camera's frame interval
        self.released = False
        self.set_calls: list[tuple[int, float]] = []
        self.grabs = 0
        self.retrieves = 0
        self._index = -1  # index of the frame last grabbed

    def isOpened(self) -> bool:
        if self.close_after is not None and self._index + 1 >= self.close_after:
            return False
        return self.opened and not self.released

    def getBackendName(self) -> str:
        return self.backend

    def get(self, prop: int) -> float:
        if prop == cv2.CAP_PROP_FPS:
            return self.fps
        if prop == cv2.CAP_PROP_FRAME_COUNT:
            return self.frame_count
        if prop == cv2.CAP_PROP_POS_MSEC:
            if 0 <= self._index < len(self.timestamps_ms):
                return self.timestamps_ms[self._index]
            return 0.0
        if prop == cv2.CAP_PROP_FRAME_WIDTH:
            return float(self.width or 0)
        if prop == cv2.CAP_PROP_FRAME_HEIGHT:
            return float(self.height or 0)
        return 0.0

    def set(self, prop: int, value: float) -> bool:
        self.set_calls.append((prop, value))
        return self.accept_settings

    def grab(self) -> bool:
        if self.released or not self.opened:
            return False
        self.grabs += 1
        self._index += 1
        if self._index >= len(self.frames):
            return False
        return self.frames[self._index] is not FAIL

    def retrieve(self):
        self.retrieves += 1
        if not (0 <= self._index < len(self.frames)):
            return False, None
        entry = self.frames[self._index]
        if entry is FAIL or entry is None:
            return False, None
        image = entry
        if self.width and self.height:
            image = cv2.resize(entry, (self.width, self.height))
        return True, image.copy()

    def read(self):
        if self.read_delay_s:
            time.sleep(self.read_delay_s)
        if not self.grab():
            return False, None
        return self.retrieve()

    def release(self) -> None:
        self.released = True


class CaptureFactory:
    """Callable used as ``capture_factory``; records every capture it hands out."""

    def __init__(self, make) -> None:
        self._make = make
        self.created: list[Any] = []
        self.calls: list[tuple] = []

    def __call__(self, *args):
        self.calls.append(args)
        capture = self._make()
        self.created.append(capture)
        return capture
