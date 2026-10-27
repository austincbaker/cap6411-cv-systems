"""Latest observation and display state for the baseline app (item 1d).

The *confirmed* observation changes only on a successful, non-empty response,
so a timeout or malformed reply never replaces the last good description.
The latest request status is tracked separately so the display can show
"timeout on frame 412" next to the still-current confirmed text.

Updated only from the app's main thread; no locking needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np


@dataclass(frozen=True)
class Observation:
    text: str
    request_id: str
    frame_id: int
    source_time_s: Optional[float]
    host_capture_s: float
    host_response_available_s: float


@dataclass
class ObservationState:
    confirmed: Optional[Observation] = None
    last_status: Optional[str] = None
    last_error_type: Optional[str] = None
    last_frame_id: Optional[int] = None
    last_status_host_s: Optional[float] = None
    in_flight_frame_id: Optional[int] = None
    counts: dict[str, int] = field(default_factory=dict)

    def bump(self, key: str, n: int = 1) -> None:
        self.counts[key] = self.counts.get(key, 0) + n

    def record_dispatch(self, frame_id: int) -> None:
        self.in_flight_frame_id = frame_id
        self.bump("requests")

    def record_result(
        self,
        *,
        status: str,
        text: Optional[str],
        error_type: Optional[str],
        request_id: str,
        frame_id: int,
        source_time_s: Optional[float],
        host_capture_s: float,
        host_response_available_s: float,
    ) -> None:
        self.in_flight_frame_id = None
        self.last_status = status
        self.last_error_type = error_type
        self.last_frame_id = frame_id
        self.last_status_host_s = host_response_available_s
        self.bump(f"status:{status}")
        if status == "ok" and text:
            self.confirmed = Observation(
                text=text,
                request_id=request_id,
                frame_id=frame_id,
                source_time_s=source_time_s,
                host_capture_s=host_capture_s,
                host_response_available_s=host_response_available_s,
            )

    def overlay_lines(self, now_s: float) -> list[str]:
        lines = []
        if self.confirmed is None:
            lines.append("no confirmed observation yet")
        else:
            age = now_s - self.confirmed.host_capture_s
            lines.append(f"[frame {self.confirmed.frame_id}, {age:.1f}s old] {self.confirmed.text}")
        if self.last_status is not None:
            detail = f" ({self.last_error_type})" if self.last_error_type else ""
            lines.append(f"last: {self.last_status}{detail} on frame {self.last_frame_id}")
        if self.in_flight_frame_id is not None:
            lines.append(f"in flight: frame {self.in_flight_frame_id}")
        skipped = self.counts.get("tick_skipped_busy", 0)
        lines.append(f"requests {self.counts.get('requests', 0)}  skipped(busy) {skipped}")
        return lines


def render_overlay(image: np.ndarray, lines: list[str], max_chars: int = 90) -> np.ndarray:
    """Draw status lines on a copy of a BGR frame."""
    canvas = image.copy()
    y = 22
    for line in lines:
        for chunk in _wrap(line, max_chars):
            cv2.putText(canvas, chunk, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(canvas, chunk, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
            y += 20
    return canvas


def _wrap(text: str, width: int) -> list[str]:
    return [text[i : i + width] for i in range(0, len(text), width)] or [""]
