"""Fake telemetry matching app.main.TelemetryMonitor. Values are synthetic and labeled as such."""

from __future__ import annotations

import time
from typing import Callable


class FakeTelemetry:
    def __init__(self, power_w: float = 5.0, available: bool = True, clock: Callable[[], float] = time.monotonic) -> None:
        self.power_w = power_w
        self.available = available
        self.clock = clock
        self.samples_taken = 0
        self.closed = False

    def metadata(self) -> dict:
        return {
            "kind": "fake",
            "synthetic": True,
            "status": "available" if self.available else "unavailable",
            "sensors": [{"sensor_id": "fake_power", "domain": "synthetic", "quantity": "power", "unit": "W"}],
        }

    def sample(self) -> list[dict]:
        self.samples_taken += 1
        base = {"sensor_id": "fake_power", "domain": "synthetic", "quantity": "power", "host_time_s": self.clock()}
        if not self.available:
            return [{**base, "raw_value": None, "raw_unit": None, "value": None, "unit": "W", "valid": False, "error": "sensor_unavailable"}]
        return [{**base, "raw_value": self.power_w, "raw_unit": "W", "value": self.power_w, "unit": "W", "valid": True, "error": None}]

    def close(self) -> None:
        self.closed = True
