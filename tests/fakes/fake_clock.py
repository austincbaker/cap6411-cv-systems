"""A manually advanced monotonic clock. ``sleep`` advances time instead of blocking."""

from __future__ import annotations


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(0.0, float(seconds))

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)
