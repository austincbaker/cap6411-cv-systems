"""Observation, gesture scene and display state for the app (items 1d, 2c and 2b).

The *confirmed* observation changes only on a successful response whose answer
validates (item 2c), so a timeout or a malformed answer never replaces the last
good one. The latest request status is tracked separately so the display can
show "timeout on frame 412" next to the still-current confirmed gesture.

``GestureScene`` (item 2b) turns the validated answers into gesture events.
Every policy feeds it the same way, so fixed-interval and gated runs share one
event derivation.

Updated only from the app's main thread; no locking needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

# ============================================================================ gesture scene (2b)
#
# The scene holds one confirmed gesture: thumbs_up, peace_sign or none (neither). It starts at
# none, so a gesture already up in the first answer is an onset. Rules, per validated answer:
#
# - the confirmed gesture again: nothing (a held gesture is reported once);
# - a different gesture, seen in ``confirm`` valid answers in a row: the change is confirmed.
#   An offset ends the gesture that was up, and an onset starts the new one; a direct switch
#   from one gesture to the other gives both, from the same answer. Back to none after a
#   gesture is an offset, and the same gesture after that is a new onset (rearming);
# - an unknown answer (a failed request, or an answer that did not validate): nothing. It is
#   neither a negative nor a confirmation, so the confirmed gesture stays, and a change waiting
#   for confirmation neither advances nor resets.

TRANSITIONS = ("onset", "offset")


@dataclass(frozen=True)
class Evidence:
    """The request whose validated answer a change came from, with its frame and times."""

    request_id: str
    frame_id: int
    source_time_s: Optional[float]
    host_capture_s: float
    response_available_s: float

    @property
    def available_source_time_s(self) -> Optional[float]:
        """When the answer was available, on the source timeline (item 2d)."""
        if self.source_time_s is None:
            return None
        return self.source_time_s + (self.response_available_s - self.host_capture_s)


@dataclass(frozen=True)
class GestureEvent:
    transition: str  # onset | offset
    gesture: str  # thumbs_up | peace_sign: the gesture that starts or ends
    answer: str  # the validated answer behind it (none for a plain offset)
    evidence: Evidence


@dataclass
class GestureScene:
    confirm: int = 1  # valid answers in a row a change needs before it counts
    gesture: str = "none"  # the confirmed gesture
    changed: Optional[Evidence] = None  # the answer that last changed it (None: initial state)
    last_valid: Optional[Evidence] = None
    unknown_since_valid: int = 0  # unknown answers since the last valid one (staleness)
    candidate: Optional[str] = None  # a change waiting for confirmation
    candidate_count: int = 0

    def __post_init__(self) -> None:
        if self.confirm < 1:
            raise ValueError("confirm must be >= 1")

    def update(self, answer: Optional[str], evidence: Optional[Evidence]) -> list[GestureEvent]:
        """Events for one request: ``answer`` is its validated gesture, None when unknown."""
        if answer is None:
            self.unknown_since_valid += 1
            return []
        self.last_valid, self.unknown_since_valid = evidence, 0
        if answer == self.gesture:
            self.candidate, self.candidate_count = None, 0
            return []
        if answer == self.candidate:
            self.candidate_count += 1
        else:
            self.candidate, self.candidate_count = answer, 1
        if self.candidate_count < self.confirm:
            return []
        events = []
        if self.gesture != "none":
            events.append(GestureEvent("offset", self.gesture, answer, evidence))
        if answer != "none":
            events.append(GestureEvent("onset", answer, answer, evidence))
        self.gesture, self.changed = answer, evidence
        self.candidate, self.candidate_count = None, 0
        return events

    def as_dict(self) -> dict:
        """The scene for the manifest: confirmed gesture, its last change and staleness."""
        return {
            "gesture": self.gesture,
            "confirm": self.confirm,
            "changed": None if self.changed is None else _evidence_dict(self.changed),
            "last_valid": None if self.last_valid is None else _evidence_dict(self.last_valid),
            "unknown_since_valid": self.unknown_since_valid,
        }

    def overlay_line(self) -> str:
        since = "start" if self.changed is None else f"frame {self.changed.frame_id}"
        stale = f", {self.unknown_since_valid} unknown since" if self.unknown_since_valid else ""
        return f"scene: {self.gesture} since {since}{stale}"


def _evidence_dict(evidence: Evidence) -> dict:
    return {
        "request_id": evidence.request_id,
        "frame_id": evidence.frame_id,
        "source_time_s": evidence.source_time_s,
        "response_available_s": evidence.response_available_s,
        "available_source_time_s": evidence.available_source_time_s,
    }


# ============================================================================ display state


@dataclass(frozen=True)
class Observation:
    gesture: str
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
        gesture: Optional[str],
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
        if status == "ok" and gesture is not None:
            self.confirmed = Observation(
                gesture=gesture,
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
            lines.append(
                f"[frame {self.confirmed.frame_id}, {age:.1f}s old] {self.confirmed.gesture}"
            )
        if self.last_status is not None:
            detail = f" ({self.last_error_type})" if self.last_error_type else ""
            lines.append(f"last: {self.last_status}{detail} on frame {self.last_frame_id}")
        if self.in_flight_frame_id is not None:
            lines.append(f"in flight: frame {self.in_flight_frame_id}")
        skipped = self.counts.get("tick_skipped_busy", 0)
        gated = sum(
            self.counts.get(k, 0) for k in ("gate_no_change", "gate_persisting", "gate_cooldown")
        )
        lines.append(
            f"requests {self.counts.get('requests', 0)}  skipped(busy) {skipped}  skipped(gate) {gated}"
        )
        return lines


def render_overlay(image: np.ndarray, lines: list[str], max_chars: int = 90) -> np.ndarray:
    """Draw status lines on a copy of a BGR frame."""
    canvas = image.copy()
    y = 22
    for line in lines:
        for chunk in _wrap(line, max_chars):
            cv2.putText(
                canvas, chunk, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA
            )
            cv2.putText(
                canvas,
                chunk,
                (8, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )
            y += 20
    return canvas


def _wrap(text: str, width: int) -> list[str]:
    return [text[i : i + width] for i in range(0, len(text), width)] or [""]
