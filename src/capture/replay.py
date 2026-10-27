"""Real-time replay of a recorded video.

Timing
------
- Source time comes from the media timestamp (``CAP_PROP_POS_MSEC``, which
  the OpenCV FFmpeg backend reports for the frame just grabbed). It is used
  when the first two frames give ``0 <= t0 < t1``.
- Otherwise source time falls back to ``frame_index / fps``. That requires a
  finite fps in (0, 1000]; the constant-frame-rate assumption is recorded as
  ``info.time_method == "frame_index_over_fps"`` and ``info.cfr_assumed``.
  An unusable timestamp *and* an invalid fps fail at open.
- Pacing: the run clock starts at the first ``read()`` (after open/decoder
  checks). Frame i is due at ``start + (t_i - t_0)`` on the monotonic clock.
  Early frames wait; frames already more than one frame period past their
  deadline are skipped without decoding and reported as ``replay_late``. A slow
  decoder or slow consumer therefore causes recorded drops, never slowed or
  accelerated playback.

Outcomes
--------
``EOF`` (with ``complete=True`` when the reported frame count was reached,
``None`` when the container reports no count), ``INCOMPLETE_SOURCE`` (stream
ended well before the reported count), ``DECODE_FAILURES`` (consecutive
empty/undecodable frames), plus the shared stop/interrupt reasons.

Frame IDs are the 0-based decode index, so they are identical across replays;
skipped frames still consume their ID.
"""

from __future__ import annotations

import math
import os
import time
from typing import Any, Callable, Optional

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

FALLBACK_FRAME_PERIOD_S = 0.1  # only when neither fps nor two timestamps are known


class ReplaySource(SourceBase):
    kind = "replay"

    def __init__(
        self,
        path: str,
        *,
        max_consecutive_decode_failures: int = 5,
        clock: Callable[[], float] = time.monotonic,
        sleep: Optional[Callable[[float], Any]] = None,
        on_drop: Optional[DropCallback] = None,
        capture_factory: Callable[..., Any] = cv2.VideoCapture,
    ) -> None:
        super().__init__(str(path), clock=clock, on_drop=on_drop, capture_factory=capture_factory)
        if max_consecutive_decode_failures < 1:
            raise ValueError("max_consecutive_decode_failures must be >= 1")
        self.path = str(path)
        self.max_consecutive_decode_failures = max_consecutive_decode_failures
        # Default sleep wakes early when stop() is called from another thread.
        self._sleep = sleep if sleep is not None else self._stop_event.wait
        self._reset_run_state()

    def _reset_run_state(self) -> None:
        self._fps: Optional[float] = None
        self._use_media_time = True
        self._buffered: list[tuple[Any, float]] = []
        self._start_host_s: Optional[float] = None
        self._t0_s: Optional[float] = None
        self._prev_t_s: Optional[float] = None
        self._prev_deadline_s: Optional[float] = None
        self._consecutive_decode_failures = 0
        self._frame_period_s = FALLBACK_FRAME_PERIOD_S

    # -- open ---------------------------------------------------------------
    def _open(self) -> None:
        self._reset_run_state()
        info = self.info
        info.opencv_version = cv2.__version__

        if not os.path.isfile(self.path):
            raise SourceOpenError(f"video file not found: {self.path}")
        capture = self._capture_factory(self.path)
        if capture is None or not capture.isOpened():
            release_quietly(capture)
            raise SourceOpenError(f"could not open video for decoding: {self.path}")
        self._capture = capture

        info.backend = _backend_name(capture)
        fps = _finite_or_none(capture.get(cv2.CAP_PROP_FPS))
        info.reported_fps = fps
        count = _finite_or_none(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        info.reported_frame_count = int(count) if count is not None and count > 0 else None
        self._fps = fps if valid_fps(fps) else None
        info.observed_fps = self._fps

        ok, first = capture.read()
        if not ok or frame_is_empty(first):
            raise SourceOpenError(f"video has no decodable frames: {self.path}")
        t0_ms = _finite_or_none(capture.get(cv2.CAP_PROP_POS_MSEC))
        ok, second = capture.read()
        has_second = bool(ok) and not frame_is_empty(second)
        t1_ms = _finite_or_none(capture.get(cv2.CAP_PROP_POS_MSEC)) if has_second else None

        media_ok = t0_ms is not None and t0_ms >= 0 and (
            not has_second or (t1_ms is not None and t1_ms > t0_ms)
        )
        if media_ok:
            self._use_media_time = True
            info.time_method = "media_pos_msec"
            first_t = t0_ms / 1000.0
            second_t = t1_ms / 1000.0 if has_second else None
        elif self._fps is not None:
            self._use_media_time = False
            info.time_method = "frame_index_over_fps"
            info.cfr_assumed = True
            info.notes.append(
                f"media timestamps unusable (t0={t0_ms!r} ms, t1={t1_ms!r} ms); "
                f"assuming constant frame rate {self._fps} fps"
            )
            first_t = 0.0
            second_t = 1.0 / self._fps if has_second else None
        else:
            raise SourceOpenError(
                f"media timestamps unusable (t0={t0_ms!r} ms, t1={t1_ms!r} ms) and "
                f"reported fps {fps!r} is invalid; cannot establish source time for {self.path}"
            )

        info.observed_height, info.observed_width = int(first.shape[0]), int(first.shape[1])
        self._buffered.append((first, first_t))
        if has_second:
            self._buffered.append((second, second_t))
        elif ok:
            # read() succeeded but returned an empty image: report it as an empty_frame drop.
            self._buffered.append((None, first_t))
        # If the second read failed at end of stream, the next grab() fails too and ends the replay.

        if self._fps is not None:
            self._frame_period_s = 1.0 / self._fps
        elif second_t is not None and second_t > first_t:
            self._frame_period_s = second_t - first_t
        else:
            self._frame_period_s = FALLBACK_FRAME_PERIOD_S

    # -- read ---------------------------------------------------------------
    def _read(self) -> Optional[Frame]:
        while True:
            if self._stop_event.is_set():
                return self._finish(self._stop_reason, "stop requested")

            image: Any = None
            decoded = False
            if self._buffered:
                image, t_s = self._buffered.pop(0)
                decoded = True
            elif not self._capture.grab():
                return self._end_of_stream()
            else:
                t_s = self._source_time(self._next_frame_id)

            frame_id = self._take_frame_id()
            deadline = self._deadline(t_s)

            now = self._clock()
            if now > deadline + self._frame_period_s:
                self._record_drop(frame_id, "replay_late", f"{now - deadline:.4f}s past deadline")
                continue

            if not decoded:
                ok, image = self._capture.retrieve()
                decoded = bool(ok)
            if not decoded or frame_is_empty(image):
                self._consecutive_decode_failures += 1
                self._record_drop(frame_id, "empty_frame", "decoder returned no image")
                if self._consecutive_decode_failures >= self.max_consecutive_decode_failures:
                    return self._finish(
                        EndReason.DECODE_FAILURES,
                        f"{self._consecutive_decode_failures} consecutive undecodable frames "
                        f"ending at frame {frame_id}",
                        complete=False,
                    )
                continue
            self._consecutive_decode_failures = 0

            now = self._clock()
            while now < deadline:
                if self._stop_event.is_set():
                    return self._finish(self._stop_reason, "stop requested")
                self._sleep(deadline - now)
                now = self._clock()
            if self._stop_event.is_set():
                return self._finish(self._stop_reason, "stop requested")
            return self._deliver(frame_id, image, t_s)

    def _source_time(self, frame_index: int) -> float:
        if self._use_media_time:
            pos_ms = _finite_or_none(self._capture.get(cv2.CAP_PROP_POS_MSEC))
            if pos_ms is not None:
                return pos_ms / 1000.0
            # A missing timestamp mid-stream: keep the timeline moving, but count it.
            self.info.nonmonotonic_timestamps += 1
            return self._prev_t_s if self._prev_t_s is not None else 0.0
        return frame_index / self._fps

    def _deadline(self, t_s: float) -> float:
        if self._start_host_s is None:
            self._start_host_s = self._clock()
            self._t0_s = t_s
        if self._prev_t_s is not None and t_s <= self._prev_t_s:
            self.info.nonmonotonic_timestamps += 1
        self._prev_t_s = t_s
        deadline = self._start_host_s + (t_s - self._t0_s)
        # Never schedule backwards in host time, even if media timestamps do.
        if self._prev_deadline_s is not None and deadline < self._prev_deadline_s:
            deadline = self._prev_deadline_s
        self._prev_deadline_s = deadline
        return deadline

    def _end_of_stream(self) -> None:
        # The last frame stays "on screen" for one frame period, so a clip of
        # length L takes about L seconds of host time, not L minus one frame.
        if self._prev_deadline_s is not None:
            end_s = self._prev_deadline_s + self._frame_period_s
            now = self._clock()
            while now < end_s and not self._stop_event.is_set():
                self._sleep(end_s - now)
                now = self._clock()
            if self._stop_event.is_set():
                return self._finish(self._stop_reason, "stop requested")
        seen = self._next_frame_id
        expected = self.info.reported_frame_count
        if expected is None:
            return self._finish(
                EndReason.EOF,
                f"end of stream after {seen} frames; container reports no frame count, coverage unverified",
                complete=None,
            )
        tolerance = max(1, int(0.01 * expected))
        if seen < expected - tolerance:
            return self._finish(
                EndReason.INCOMPLETE_SOURCE,
                f"stream ended after {seen} of {expected} reported frames",
                complete=False,
            )
        return self._finish(EndReason.EOF, f"end of stream after {seen} of {expected} frames", complete=True)


def _finite_or_none(value: Any) -> Optional[float]:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _backend_name(capture: Any) -> Optional[str]:
    try:
        return str(capture.getBackendName())
    except Exception:
        return None
