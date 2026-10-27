"""Shared frame record, source metadata and end-of-source outcomes.

Time bases (kept separate, never substituted for one another):

- ``source_time_s``: media-relative time of the frame's visual evidence. For
  replay this comes from the media timestamp (or frame_index / fps when the
  constant-frame-rate fallback is in use). For webcam it is ``None``: a live
  camera has no media timeline, so consumers use ``host_capture_s``.
- ``host_capture_s``: ``time.monotonic()`` taken right after the frame was
  read from OpenCV. Aligns frames with inference requests and power samples.

Image convention: ``image`` is an HxWx3 uint8 numpy array in OpenCV's BGR
channel order, exactly as ``cv2.VideoCapture.read`` returns it.

Field names are provisional; item 2d (#10) freezes them.
"""

from __future__ import annotations

import enum
import math
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

import numpy as np

MAX_VALID_FPS = 1000.0


class SourceOpenError(RuntimeError):
    """The source could not be initialized (missing file, no device, no decodable frames)."""


class EndReason(str, enum.Enum):
    """Why a source stopped delivering frames. Only EOF means "completed normally"."""

    EOF = "eof"  # replay reached the end of the media
    INCOMPLETE_SOURCE = "incomplete_source"  # replay stopped well before the reported frame count
    DECODE_FAILURES = "decode_failures"  # too many consecutive empty/undecodable frames
    DISCONNECTED = "disconnected"  # webcam stopped returning frames after a successful open
    STOPPED = "stopped"  # consumer called stop()
    DURATION_LIMIT = "duration_limit"  # consumer stopped the source at its configured run length
    INTERRUPTED = "interrupted"  # KeyboardInterrupt while the source was open
    CONSUMER_ERROR = "consumer_error"  # downstream exception while the source was open

    @property
    def is_error(self) -> bool:
        return self in (
            EndReason.INCOMPLETE_SOURCE,
            EndReason.DECODE_FAILURES,
            EndReason.DISCONNECTED,
            EndReason.CONSUMER_ERROR,
        )


@dataclass(frozen=True)
class SourceEnd:
    reason: EndReason
    detail: str = ""
    # True when replay coverage was verified against the reported frame count,
    # None when it could not be verified (unknown count, webcam, early stop).
    complete: Optional[bool] = None

    def as_dict(self) -> dict[str, Any]:
        return {"reason": self.reason.value, "detail": self.detail, "complete": self.complete}


@dataclass(frozen=True)
class Frame:
    source_kind: str
    frame_id: int
    image: np.ndarray = field(repr=False)
    width: int
    height: int
    source_time_s: Optional[float]
    host_capture_s: float


@dataclass
class SourceInfo:
    """Observed source metadata. Requested values are kept next to what the backend actually reports."""

    source_kind: str
    source_id: str
    backend: Optional[str] = None
    time_method: Optional[str] = None  # "media_pos_msec" | "frame_index_over_fps" | "none_host_capture_only"
    cfr_assumed: bool = False  # True when source time is frame_index / fps
    reported_fps: Optional[float] = None  # CAP_PROP_FPS after open; None if missing or invalid
    reported_frame_count: Optional[int] = None
    requested_width: Optional[int] = None
    requested_height: Optional[int] = None
    requested_fps: Optional[float] = None
    observed_width: Optional[int] = None
    observed_height: Optional[int] = None
    measured_fps: Optional[float] = None  # delivered frames / host elapsed, filled at close
    buffer_size_accepted: Optional[bool] = None  # webcam: whether CAP_PROP_BUFFERSIZE=1 was honored
    frames_delivered: int = 0
    drop_counts: dict[str, int] = field(default_factory=dict)
    nonmonotonic_timestamps: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# on_drop(frame_id, reason, host_time_s, detail)
DropCallback = Callable[[int, str, float, str], None]


def valid_fps(fps: Optional[float]) -> bool:
    return fps is not None and math.isfinite(fps) and 0.0 < fps <= MAX_VALID_FPS


def frame_is_empty(image: Optional[np.ndarray]) -> bool:
    return image is None or not isinstance(image, np.ndarray) or image.size == 0 or image.ndim < 2


def backend_name(capture: Any) -> Optional[str]:
    try:
        return str(capture.getBackendName())
    except Exception:
        return None


def release_quietly(capture: Any) -> None:
    if capture is None:
        return
    try:
        capture.release()
    except Exception:  # release must never mask the original exit path
        pass


class SourceBase:
    """Lifecycle shared by webcam and replay sources: open -> read()* -> close.

    ``read()`` returns a ``Frame`` or ``None``; ``None`` always comes with
    ``self.end`` set to an explicit ``SourceEnd``. Sources start no threads.
    Use as a context manager (or call ``close()`` in a ``finally``) so the
    capture is released on EOF, error, exception and KeyboardInterrupt.
    ``stop()`` is safe to call from another thread.
    """

    kind = "base"

    def __init__(
        self,
        source_id: str,
        *,
        clock: Callable[[], float],
        on_drop: Optional[DropCallback],
        capture_factory: Callable[..., Any],
    ) -> None:
        self.source_id = source_id
        self._clock = clock
        self._on_drop = on_drop
        self._capture_factory = capture_factory
        self._capture: Any = None
        self._stop_event = threading.Event()
        self._stop_reason = EndReason.STOPPED
        self.info = SourceInfo(source_kind=self.kind, source_id=source_id)
        self.end: Optional[SourceEnd] = None
        self._next_frame_id = 0
        self._first_capture_s: Optional[float] = None
        self._last_capture_s: Optional[float] = None

    # -- lifecycle -------------------------------------------------------
    @property
    def is_open(self) -> bool:
        return self._capture is not None

    def open(self) -> SourceInfo:
        if self.is_open:
            raise RuntimeError(f"{self.kind} source is already open")
        self.info = SourceInfo(source_kind=self.kind, source_id=self.source_id)
        self.end = None
        self._stop_event.clear()
        self._stop_reason = EndReason.STOPPED
        self._next_frame_id = 0
        self._first_capture_s = self._last_capture_s = None
        try:
            self._open()
        except BaseException:
            self.close()
            raise
        return self.info

    def close(self) -> None:
        capture, self._capture = self._capture, None
        release_quietly(capture)
        if (
            self._first_capture_s is not None
            and self._last_capture_s is not None
            and self.info.frames_delivered > 1
            and self._last_capture_s > self._first_capture_s
        ):
            self.info.measured_fps = (self.info.frames_delivered - 1) / (
                self._last_capture_s - self._first_capture_s
            )

    def stop(self, reason: EndReason = EndReason.STOPPED) -> None:
        self._stop_reason = reason
        self._stop_event.set()

    def __enter__(self) -> "SourceBase":
        if not self.is_open:
            self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self.end is None:
            if exc_type is not None and issubclass(exc_type, KeyboardInterrupt):
                self._finish(EndReason.INTERRUPTED, "KeyboardInterrupt")
            elif exc_type is not None:
                self._finish(EndReason.CONSUMER_ERROR, f"{exc_type.__name__}: {exc}")
            else:
                self._finish(EndReason.STOPPED, "closed before the source ended")
        self.close()
        return False

    def __iter__(self):
        while True:
            frame = self.read()
            if frame is None:
                return
            yield frame

    def read(self) -> Optional[Frame]:
        if self.end is not None:
            return None
        if not self.is_open:
            raise RuntimeError(f"{self.kind} source is not open")
        if self._stop_event.is_set():
            return self._finish(self._stop_reason, "stop requested")
        try:
            return self._read()
        except KeyboardInterrupt:
            self._finish(EndReason.INTERRUPTED, "KeyboardInterrupt during read")
            raise

    # -- subclass hooks ---------------------------------------------------
    def _open(self) -> None:
        raise NotImplementedError

    def _read(self) -> Optional[Frame]:
        raise NotImplementedError

    # -- helpers ----------------------------------------------------------
    def _take_frame_id(self) -> int:
        frame_id = self._next_frame_id
        self._next_frame_id += 1
        return frame_id

    def _record_drop(self, frame_id: int, reason: str, detail: str = "") -> None:
        self.info.drop_counts[reason] = self.info.drop_counts.get(reason, 0) + 1
        if self._on_drop is not None:
            self._on_drop(frame_id, reason, self._clock(), detail)

    def _deliver(self, frame_id: int, image: np.ndarray, source_time_s: Optional[float]) -> Frame:
        host_capture_s = self._clock()
        if self._first_capture_s is None:
            self._first_capture_s = host_capture_s
        self._last_capture_s = host_capture_s
        self.info.frames_delivered += 1
        return Frame(
            source_kind=self.kind,
            frame_id=frame_id,
            image=image,
            width=int(image.shape[1]),
            height=int(image.shape[0]),
            source_time_s=source_time_s,
            host_capture_s=host_capture_s,
        )

    def _finish(self, reason: EndReason, detail: str = "", complete: Optional[bool] = None) -> None:
        if self.end is None:
            self.end = SourceEnd(reason=reason, detail=detail, complete=complete)
        return None
