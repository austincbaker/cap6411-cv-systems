"""Live webcam source.

- Opening fails loudly (``SourceOpenError``) when the device cannot be opened
  or opens but never yields a frame (e.g. camera permission denied on macOS).
- After a successful open, a failed or empty read is recorded as a drop
  (reason ``read_failed``); ``max_consecutive_failures`` in a row ends the
  source with ``EndReason.DISCONNECTED``. A disconnect never looks like EOF.
- Requested width/height/fps are recorded next to what the backend actually
  reports after open, plus the backend name OpenCV picked.
- ``source_time_s`` is ``None`` for every webcam frame: there is no media
  timeline, so consumers use ``host_capture_s`` (monotonic, taken right after
  ``read()`` returns).

No platform-specific backend is forced; ``api_preference`` defaults to
``cv2.CAP_ANY`` and the chosen backend is recorded in ``info.backend``.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional, Union

import cv2

from .frame import (
    DropCallback,
    EndReason,
    Frame,
    SourceBase,
    SourceOpenError,
    frame_is_empty,
    release_quietly,
    valid_fps,
)


def parse_device(device: Union[int, str]) -> Union[int, str]:
    """Accept a non-negative camera index (int or digit string) or a device path such as /dev/video0."""
    if isinstance(device, bool):
        raise SourceOpenError(f"invalid camera device {device!r}")
    if isinstance(device, int):
        if device < 0:
            raise SourceOpenError(f"camera index must be >= 0, got {device}")
        return device
    if isinstance(device, str):
        text = device.strip()
        if text.isdigit():
            return int(text)
        if text:
            return text
    raise SourceOpenError(f"invalid camera device {device!r}")


class WebcamSource(SourceBase):
    kind = "webcam"

    def __init__(
        self,
        device: Union[int, str] = 0,
        *,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[float] = None,
        api_preference: int = cv2.CAP_ANY,
        max_consecutive_failures: int = 10,
        clock: Callable[[], float] = time.monotonic,
        on_drop: Optional[DropCallback] = None,
        capture_factory: Callable[..., Any] = cv2.VideoCapture,
    ) -> None:
        self.device = parse_device(device)
        super().__init__(str(self.device), clock=clock, on_drop=on_drop, capture_factory=capture_factory)
        if max_consecutive_failures < 1:
            raise ValueError("max_consecutive_failures must be >= 1")
        self.requested_width = width
        self.requested_height = height
        self.requested_fps = fps
        self.api_preference = api_preference
        self.max_consecutive_failures = max_consecutive_failures
        self._consecutive_failures = 0
        self._pending_first: Optional[Any] = None

    def _open(self) -> None:
        info = self.info
        info.opencv_version = cv2.__version__
        info.time_method = "none_host_capture_only"
        info.requested_width = self.requested_width
        info.requested_height = self.requested_height
        info.requested_fps = self.requested_fps

        capture = self._capture_factory(self.device, self.api_preference)
        if capture is None or not capture.isOpened():
            release_quietly(capture)
            raise SourceOpenError(f"could not open camera {self.device!r} (missing device or no permission)")
        self._capture = capture

        if self.requested_width:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, float(self.requested_width))
        if self.requested_height:
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, float(self.requested_height))
        if self.requested_fps:
            capture.set(cv2.CAP_PROP_FPS, float(self.requested_fps))
        # Keep the driver from handing us stale frames; not every backend honors this.
        info.buffer_size_requested = 1
        info.buffer_size_accepted = bool(capture.set(cv2.CAP_PROP_BUFFERSIZE, 1.0))

        info.backend = _backend_name(capture)
        reported_fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        info.observed_fps = reported_fps if valid_fps(reported_fps) else None
        if info.observed_fps is None:
            info.notes.append(f"backend reported unusable fps {reported_fps!r}; see measured_fps")

        # The first frame proves the device really delivers images and gives the true dimensions.
        ok, image = capture.read()
        if not ok or frame_is_empty(image):
            raise SourceOpenError(f"camera {self.device!r} opened but returned no frame")
        info.observed_height, info.observed_width = int(image.shape[0]), int(image.shape[1])
        if self.requested_width and info.observed_width != self.requested_width:
            info.notes.append(f"requested width {self.requested_width}, got {info.observed_width}")
        if self.requested_height and info.observed_height != self.requested_height:
            info.notes.append(f"requested height {self.requested_height}, got {info.observed_height}")
        self._pending_first = image
        self._consecutive_failures = 0

    def _read(self) -> Optional[Frame]:
        if self._pending_first is not None:
            image, self._pending_first = self._pending_first, None
            return self._deliver(self._take_frame_id(), image, None)

        while True:
            if self._stop_event.is_set():
                return self._finish(self._stop_reason, "stop requested")
            capture = self._capture
            if not capture.isOpened():
                return self._finish(EndReason.DISCONNECTED, "capture reports closed")
            ok, image = capture.read()
            frame_id = self._take_frame_id()
            if ok and not frame_is_empty(image):
                self._consecutive_failures = 0
                return self._deliver(frame_id, image, None)
            self._consecutive_failures += 1
            self._record_drop(frame_id, "read_failed", "empty frame" if ok else "read() returned False")
            if self._consecutive_failures >= self.max_consecutive_failures:
                return self._finish(
                    EndReason.DISCONNECTED,
                    f"{self._consecutive_failures} consecutive failed reads",
                )


def _backend_name(capture: Any) -> Optional[str]:
    try:
        return str(capture.getBackendName())
    except Exception:
        return None
