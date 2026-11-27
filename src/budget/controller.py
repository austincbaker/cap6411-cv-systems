"""Token-bucket admission controller for VLM calls under an energy budget (item 3a).

The user sets a budget ``B`` in Wh per hour for the VLM's energy *above the idle pipeline*
(capture, gate and a loaded but idle llama-server). One Wh per hour is one watt, so the
bucket refills at ``B`` joules per second, continuously, up to its capacity. Each call has a
cost in joules for the size of the image it sends, from a calibration table measured by the
energy suite (``scripts/energy_suite.py calibrate``); the repository ships a placeholder
table until the MacBook runs exist.

The change gate (item 2a) still decides *when* something changed; the controller decides
*whether* and *at what size* to look. On every check (``step``):

1. A gate trigger becomes the single **pending change** (a newer trigger replaces it, so the
   freshest frame of an ongoing change is what gets sent).
2. With nothing pending, the decision is ``no_change``. While a request is in flight it is
   ``busy`` (the pending change waits).
3. A pending change older than ``pending_max_age_s`` without a newer trigger is ``drop``-ped:
   by then its answer would be too late to count (the event matcher's horizon is 10 s).
4. Otherwise the largest image size whose cost fits in the bucket is admitted
   (``admit_full`` at the run's own size, ``admit_reduced`` at a smaller table size, which
   sends fewer image tokens), and its estimated cost is debited.
5. If no size fits, the decision is ``defer``: the change stays pending and is sent on the
   first check where the bucket has refilled enough.

Settlement (optional, on by default): when a response arrives, the estimate is replaced by
``j_per_call x elapsed / latency_s`` of the table entry, so a call that ran slower than
calibrated (other load, a long answer) is charged for the extra time the server was busy.
The bucket may go negative after settlement; nothing is admitted until it refills.

Guarantee: estimated spend over any window of ``t`` seconds is at most
``capacity + B x t`` plus the settlement overrun of the last call. Measured energy follows
only as far as the cost table is right, which is why the suite measures it per run.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

DECISIONS = ("no_change", "busy", "admit_full", "admit_reduced", "defer", "drop", "settle")
ADMIT_DECISIONS = ("admit_full", "admit_reduced")
TABLE_VERSION = 1


@dataclass(frozen=True)
class CostEntry:
    image_max_side: Optional[int]  # None = the source resolution, unshrunk
    j_per_call: float  # energy above the idle pipeline per call, joules
    latency_s: Optional[float] = None  # median call latency at calibration, for settlement

    def __post_init__(self) -> None:
        if not self.j_per_call > 0:
            raise ValueError(f"j_per_call must be > 0, got {self.j_per_call}")
        if self.latency_s is not None and not self.latency_s > 0:
            raise ValueError(f"latency_s must be > 0 or null, got {self.latency_s}")
        if self.image_max_side is not None and self.image_max_side <= 0:
            raise ValueError("image_max_side must be a positive integer or null")


@dataclass(frozen=True)
class CostTable:
    entries: tuple[CostEntry, ...]
    placeholder: bool = True
    source: Optional[str] = None  # where the numbers came from
    meta: dict = field(default_factory=dict)

    def entry(self, image_max_side: Optional[int]) -> Optional[CostEntry]:
        for e in self.entries:
            if e.image_max_side == image_max_side:
                return e
        return None

    def options(self, full_side: Optional[int]) -> list[CostEntry]:
        """The run's own size first, then each smaller table size, most expensive first."""
        full = self.entry(full_side)
        if full is None:
            label = "null (source resolution)" if full_side is None else str(full_side)
            raise ValueError(f"cost table has no entry for image_max_side {label}")
        smaller = [
            e
            for e in self.entries
            if e.image_max_side is not None
            and (full_side is None or e.image_max_side < full_side)
            and e.j_per_call < full.j_per_call
        ]
        return [full] + sorted(smaller, key=lambda e: -e.j_per_call)

    def as_dict(self) -> dict:
        return {
            "table_version": TABLE_VERSION,
            "placeholder": self.placeholder,
            "source": self.source,
            **self.meta,
            "entries": [asdict(e) for e in self.entries],
        }


def load_cost_table(path: Path | str) -> CostTable:
    data = json.loads(Path(path).read_text())
    if data.get("table_version") != TABLE_VERSION:
        raise ValueError(f"{path}: table_version must be {TABLE_VERSION}")
    entries = tuple(
        CostEntry(
            image_max_side=e.get("image_max_side"),
            j_per_call=float(e["j_per_call"]),
            latency_s=None if e.get("latency_s") is None else float(e["latency_s"]),
        )
        for e in data["entries"]
    )
    sides = [e.image_max_side for e in entries]
    if len(set(sides)) != len(sides):
        raise ValueError(f"{path}: duplicate image_max_side entries")
    meta = {
        k: v
        for k, v in data.items()
        if k not in ("table_version", "placeholder", "source", "entries")
    }
    return CostTable(
        entries=entries,
        placeholder=bool(data.get("placeholder", True)),
        source=data.get("source") or str(path),
        meta=meta,
    )


@dataclass(frozen=True)
class BudgetConfig:
    budget_wh_per_hour: float  # = average watts above idle the VLM may use
    capacity_j: Optional[float] = None  # None = burst_calls x the full-size cost
    burst_calls: float = 2.0
    pending_max_age_s: float = 10.0
    settle: bool = True

    def __post_init__(self) -> None:
        if not self.budget_wh_per_hour > 0:
            raise ValueError("budget_wh_per_hour must be > 0")
        if self.capacity_j is not None and not self.capacity_j > 0:
            raise ValueError("capacity_j must be > 0")
        if not self.burst_calls > 0:
            raise ValueError("burst_calls must be > 0")
        if not self.pending_max_age_s > 0:
            raise ValueError("pending_max_age_s must be > 0")

    @property
    def rate_w(self) -> float:
        return self.budget_wh_per_hour  # 1 Wh/h = 3600 J / 3600 s = 1 W

    def as_dict(self) -> dict:
        return {**asdict(self), "rate_j_per_s": self.rate_w}


@dataclass
class Verdict:
    decision: str
    item: Any = None  # the admitted (or dropped) change
    image_max_side: Optional[int] = None
    est_cost_j: Optional[float] = None
    bucket_before_j: float = 0.0
    bucket_after_j: float = 0.0
    spent_j: float = 0.0  # cumulative estimated spend after this step
    allowance_j: float = 0.0  # capacity at start plus everything refilled so far
    pending_age_s: Optional[float] = None
    replaced_pending: bool = False

    def log_fields(self) -> dict:
        return {
            "decision": self.decision,
            "image_max_side": self.image_max_side,
            "est_cost_j": self.est_cost_j,
            "bucket_before_j": self.bucket_before_j,
            "bucket_after_j": self.bucket_after_j,
            "spent_j": self.spent_j,
            "allowance_j": self.allowance_j,
            "pending_age_s": self.pending_age_s,
            "replaced_pending": self.replaced_pending,
        }


class BudgetController:
    def __init__(
        self,
        config: BudgetConfig,
        table: CostTable,
        *,
        full_side: Optional[int] = None,
        start_s: float = 0.0,
    ) -> None:
        self.config = config
        self.table = table
        self.options = table.options(full_side)
        self.full_side = full_side
        self.capacity_j = (
            config.capacity_j
            if config.capacity_j is not None
            else config.burst_calls * self.options[0].j_per_call
        )
        self.level_j = self.capacity_j  # starts full
        self.start_s = self.last_s = start_s
        self.refilled_j = 0.0
        self.spent_j = 0.0
        self.pending: Any = None
        self.pending_since: Optional[float] = None
        self.counts = {d: 0 for d in DECISIONS}

    def start(self, now_s: float) -> None:
        """Restart the clock (the run's first tick): full bucket, nothing spent or pending."""
        self.level_j = self.capacity_j
        self.start_s = self.last_s = now_s
        self.refilled_j = self.spent_j = 0.0
        self._clear()
        self.counts = {d: 0 for d in DECISIONS}

    # -- bucket ------------------------------------------------------------
    def _refill(self, now_s: float) -> None:
        elapsed = max(0.0, now_s - self.last_s)
        self.last_s = max(self.last_s, now_s)
        added = min(self.capacity_j - self.level_j, self.config.rate_w * elapsed)
        if added > 0:
            self.level_j += added
        self.refilled_j += self.config.rate_w * elapsed

    def allowance_j(self, now_s: Optional[float] = None) -> float:
        """Initial capacity plus the budget accrued since the start: the most the controller
        could have spent by ``now_s`` (refill above capacity is lost, so it may spend less)."""
        t = self.last_s if now_s is None else now_s
        return self.capacity_j + self.config.rate_w * max(0.0, t - self.start_s)

    # -- decisions ---------------------------------------------------------
    def step(self, now_s: float, change: Any = None, *, busy: bool = False) -> Verdict:
        """One check. ``change`` is this tick's gate trigger (None if the gate did not fire);
        ``busy`` means a request is in flight, so nothing can be sent now."""
        self._refill(now_s)
        before = self.level_j
        replaced = False
        if change is not None:
            replaced = self.pending is not None
            self.pending, self.pending_since = change, now_s
        verdict = Verdict("no_change", bucket_before_j=before, replaced_pending=replaced)
        if self.pending is not None:
            verdict.pending_age_s = now_s - self.pending_since
            if verdict.pending_age_s > self.config.pending_max_age_s:
                verdict.decision, verdict.item = "drop", self.pending
                self._clear()
            elif busy:
                verdict.decision = "busy"
            else:
                choice = next((o for o in self.options if o.j_per_call <= self.level_j), None)
                if choice is None:
                    verdict.decision = "defer"
                    verdict.est_cost_j = self.options[-1].j_per_call  # cheapest, still too dear
                else:
                    verdict.decision = (
                        "admit_full" if choice is self.options[0] else "admit_reduced"
                    )
                    verdict.item = self.pending
                    verdict.image_max_side = choice.image_max_side
                    verdict.est_cost_j = choice.j_per_call
                    self.level_j -= choice.j_per_call
                    self.spent_j += choice.j_per_call
                    self._clear()
        elif busy:
            verdict.decision = "busy"
        self.counts[verdict.decision] += 1
        verdict.bucket_after_j = self.level_j
        verdict.spent_j = self.spent_j
        verdict.allowance_j = self.allowance_j(now_s)
        return verdict

    def settle(
        self,
        now_s: float,
        image_max_side: Optional[int],
        est_cost_j: float,
        elapsed_s: Optional[float],
    ) -> Verdict:
        """Replace an admitted call's estimate by the latency-scaled cost once it has finished.
        Without settlement, a missing latency, or no calibrated latency the estimate stands."""
        self._refill(now_s)
        before = self.level_j
        entry = self.table.entry(image_max_side)
        actual = est_cost_j
        if (
            self.config.settle
            and entry is not None
            and entry.latency_s
            and elapsed_s is not None
            and elapsed_s >= 0
        ):
            actual = entry.j_per_call * elapsed_s / entry.latency_s
        delta = actual - est_cost_j
        self.level_j -= delta
        self.spent_j += delta
        self.counts["settle"] += 1
        return Verdict(
            "settle",
            image_max_side=image_max_side,
            est_cost_j=actual,
            bucket_before_j=before,
            bucket_after_j=self.level_j,
            spent_j=self.spent_j,
            allowance_j=self.allowance_j(now_s),
        )

    def _clear(self) -> None:
        self.pending = self.pending_since = None

    def summary(self, now_s: Optional[float] = None) -> dict:
        t = self.last_s if now_s is None else now_s
        elapsed = max(0.0, t - self.start_s)
        return {
            "config": self.config.as_dict(),
            "capacity_j": self.capacity_j,
            "full_image_max_side": self.full_side,
            "options": [asdict(o) for o in self.options],
            "cost_table": self.table.as_dict(),
            "elapsed_s": elapsed,
            "estimated_spend_j": self.spent_j,
            "allowance_j": self.allowance_j(t),
            "estimated_spend_wh_per_hour": self.spent_j / elapsed if elapsed > 0 else None,
            "final_bucket_j": self.level_j,
            "pending_at_end": self.pending is not None,
            "decisions": dict(self.counts),
        }
