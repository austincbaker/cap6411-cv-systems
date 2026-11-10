"""Observation, scene and display state for the app (items 1d and 2b).

The *confirmed* observation changes only on a successful, non-empty response,
so a timeout or malformed reply never replaces the last good description.
The latest request status is tracked separately so the display can show
"timeout on frame 412" next to the still-current confirmed text.

Updated only from the app's main thread; no locking needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

# ============================================================================ scene state (2b)
#
# Shared event derivation: every policy (fixed_interval, gated, later budget)
# turns a successful response into a SceneObservation, differences it against
# the confirmed scene and emits predicted events. Invalid or failed responses
# leave the confirmed scene untouched, and an unchanged scene emits nothing.
#
# parse_observation is a stand-in until item 2c (#9) fixes the prompt and the
# validated observation format: it reads a comma-separated object list such as
# "The objects are a gray mug, a phone and a man." and keeps each item's last
# word (its head noun) so wording like "red mug" vs "mug" does not churn.

SCENE_PROMPT = "Name the objects you see, separated by commas."
PERSON_WORDS = frozenset(
    {"person", "people", "man", "men", "woman", "women", "boy", "girl", "someone", "human", "child"}
)
_LEAD_IN = re.compile(
    r"^\s*(?:in the (?:image|picture|frame)[, ]*)?(?:the |i see |there (?:is|are) )?"
    r"(?:objects? (?:that )?(?:i see |visible |in the (?:image|picture) )?(?:are|is|include)\s*:?)?",
    re.IGNORECASE,
)
_ARTICLES = re.compile(r"^(?:a|an|the|some|two|three|several|one)\s+", re.IGNORECASE)


@dataclass(frozen=True)
class SceneObservation:
    person: bool
    objects: frozenset[str]

    def as_dict(self) -> dict:
        return {"person": self.person, "objects": sorted(self.objects)}


def parse_observation(text: Optional[str]) -> Optional[SceneObservation]:
    """Comma-separated object list -> observation, or None when nothing usable is listed."""
    if not text or not text.strip():
        return None
    body = _LEAD_IN.sub("", text.strip(), count=1).strip().rstrip(".!")
    items = [part.strip() for part in re.split(r",|\band\b|;|\n", body)]
    nouns = set()
    for item in items:
        item = _ARTICLES.sub("", re.sub(r"[^a-z\s-]", "", item.lower())).strip()
        if item and item not in ("none", "nothing"):
            nouns.add(item.split()[-1])
    if not nouns and "none" not in body.lower() and "nothing" not in body.lower():
        return None
    person = bool(nouns & PERSON_WORDS)
    return SceneObservation(person=person, objects=frozenset(nouns - PERSON_WORDS))


def derive_events(
    before: Optional[SceneObservation], after: SceneObservation
) -> list[tuple[str, Optional[str]]]:
    """(label, object) pairs for what changed; the first observation only sets the scene."""
    if before is None:
        return []
    events: list[tuple[str, Optional[str]]] = []
    if after.person and not before.person:
        events.append(("person_enters", None))
    if before.person and not after.person:
        events.append(("person_leaves", None))
    events += [("object_placed", o) for o in sorted(after.objects - before.objects)]
    events += [("object_removed", o) for o in sorted(before.objects - after.objects)]
    return events


@dataclass
class SceneState:
    confirmed: Optional[SceneObservation] = None

    def update(self, text: Optional[str]) -> Optional[list[tuple[str, Optional[str]]]]:
        """Events for a successful response's text; None when the text is not a valid observation."""
        observation = parse_observation(text)
        if observation is None:
            return None
        events = derive_events(self.confirmed, observation)
        self.confirmed = observation
        return events


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
