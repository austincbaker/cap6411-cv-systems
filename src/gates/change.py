"""Frame-difference change gate (item 2a).

Each candidate frame is compared with the *acknowledged reference*: the last
frame actually sent to the VLM. A change that builds up slowly therefore keeps
growing against that reference until it triggers, instead of being hidden by
frame-to-frame comparisons.

Score: frames are converted to grayscale, shrunk to ``size`` and blurred, and
each frame's mean brightness is subtracted so a uniform lighting shift does
not count as change. A pixel is *changed* when its brightness moved by more
than ``pixel_delta`` (0-255). The frame is split into a ``grid`` x ``grid``
set of cells, and the score is the changed fraction of the most-changed cell,
so a small object placed in one corner is not diluted by the whole frame.
``grid=1`` gives a single global score.

Persistence and hysteresis: each :meth:`ChangeGate.decide` call is one check.
A change starts when the score reaches ``threshold`` and stays alive while it
is at least ``release_threshold`` (hysteresis; defaults to ``threshold``); it
must stay alive for ``persist_checks`` checks in a row before it triggers, so
a movement that comes and goes (a head turn, someone shifting in a chair) is
skipped while a change that stays (a gesture held, an object placed) is sent,
from a frame where it has settled.

Decision for a candidate frame at host time ``now_s``:

1. no reference yet                      -> trigger ``gate_initial``
2. ``refresh_s`` since the last trigger  -> trigger ``gate_refresh``
3. score below the threshold (``release_threshold`` once a change has
   started)                              -> skip ``gate_no_change``
4. changed for fewer than ``persist_checks`` checks -> skip ``gate_persisting``
5. within ``min_interval_s`` of the last trigger -> skip ``gate_cooldown``
6. otherwise                             -> trigger ``gate_change``

The caller calls :meth:`ChangeGate.acknowledge` with the decision once the
frame is really sent, which moves the reference and the cooldown clock and
ends the change. A trigger that could not be sent (the VLM was busy) changes
nothing, so the next candidate is judged against the same reference.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Optional

import cv2
import numpy as np

TRIGGER_REASONS = ("gate_initial", "gate_refresh", "gate_change")
SKIP_REASONS = ("gate_no_change", "gate_persisting", "gate_cooldown")


@dataclass(frozen=True)
class GateConfig:
    # threshold, persist_checks and min_interval_s were chosen on development clips (README,
    # "Choosing the gate settings") for 0.5 s gate checks; retune for another check interval.
    threshold: float = 0.3  # changed fraction of the most-changed cell that starts a change
    pixel_delta: int = 25  # brightness change (0-255) that marks a pixel as changed
    min_interval_s: float = 2.0  # cooldown between triggers
    refresh_s: Optional[float] = None  # forced call after this long without one; None = never
    grid: int = 4  # cells per side for the regional score
    persist_checks: int = 3  # checks in a row a change must last before it triggers
    release_threshold: Optional[float] = None  # keeps a started change alive; None = threshold
    width: int = 160
    height: int = 120

    def __post_init__(self) -> None:
        if not 0 < self.threshold <= 1:
            raise ValueError("threshold must be in (0, 1]")
        if self.persist_checks < 1:
            raise ValueError("persist_checks must be >= 1")
        if self.release_threshold is not None and not 0 < self.release_threshold <= self.threshold:
            raise ValueError("release_threshold must be in (0, threshold]")
        if not 0 <= self.pixel_delta < 255:
            raise ValueError("pixel_delta must be in [0, 255)")
        if self.min_interval_s < 0:
            raise ValueError("min_interval_s must be >= 0")
        if self.refresh_s is not None and not self.refresh_s > 0:
            raise ValueError("refresh_s must be > 0 or None")
        if self.grid < 1 or self.grid > min(self.width, self.height):
            raise ValueError("grid must be between 1 and the downsampled size")

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GateDecision:
    trigger: bool
    reason: str
    score: Optional[float]  # most-changed cell; None when there is no reference
    global_score: Optional[float]
    compute_s: float  # time spent scoring, for gate-overhead accounting
    processed: np.ndarray  # the preprocessed frame, kept so acknowledge() need not redo it

    def log_fields(self) -> dict:
        return {
            "gate_reason": self.reason,
            "gate_score": self.score,
            "gate_global_score": self.global_score,
            "gate_compute_s": self.compute_s,
        }


def preprocess(image: np.ndarray, width: int, height: int) -> np.ndarray:
    """BGR or gray frame -> small blurred float32 gray image with its mean removed."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    small = cv2.resize(gray, (width, height), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (5, 5), 0).astype(np.float32)
    return small - float(small.mean())


def change_score(a: np.ndarray, b: np.ndarray, pixel_delta: int, grid: int) -> tuple[float, float]:
    """(most-changed cell fraction, global fraction) between two preprocessed frames."""
    changed = np.abs(a - b) > pixel_delta
    h, w = changed.shape
    rows = np.array_split(np.arange(h), grid)
    cols = np.array_split(np.arange(w), grid)
    cell = max(
        float(changed[r[0] : r[-1] + 1, c[0] : c[-1] + 1].mean()) for r in rows for c in cols
    )
    return cell, float(changed.mean())


class ChangeGate:
    def __init__(self, config: GateConfig = GateConfig(), clock=time.perf_counter) -> None:
        self.config = config
        self._clock = clock  # for compute_s only; decisions use the caller's now_s
        self.reference: Optional[np.ndarray] = None
        self.last_trigger_s: Optional[float] = None
        self.streak = 0  # checks in a row the current change has lasted

    def decide(self, image: np.ndarray, now_s: float) -> GateDecision:
        cfg = self.config
        started = self._clock()
        processed = preprocess(image, cfg.width, cfg.height)
        score = global_score = None
        if self.reference is not None:
            score, global_score = change_score(processed, self.reference, cfg.pixel_delta, cfg.grid)
        compute_s = self._clock() - started

        since = None if self.last_trigger_s is None else now_s - self.last_trigger_s
        if self.reference is None:
            reason = "gate_initial"
        elif cfg.refresh_s is not None and since is not None and since >= cfg.refresh_s:
            reason = "gate_refresh"
        else:
            release = cfg.threshold if cfg.release_threshold is None else cfg.release_threshold
            if score < (cfg.threshold if self.streak == 0 else release):
                self.streak = 0
                reason = "gate_no_change"
            else:
                self.streak += 1
                if self.streak < cfg.persist_checks:
                    reason = "gate_persisting"
                elif since is not None and since < cfg.min_interval_s:
                    reason = "gate_cooldown"
                else:
                    reason = "gate_change"
        return GateDecision(
            trigger=reason in TRIGGER_REASONS,
            reason=reason,
            score=score,
            global_score=global_score,
            compute_s=compute_s,
            processed=processed,
        )

    def acknowledge(self, decision: GateDecision, now_s: float) -> None:
        """The frame behind ``decision`` was sent: it becomes the reference."""
        self.reference = decision.processed
        self.last_trigger_s = now_s
        self.streak = 0
