"""Fake VLM client matching app.main.InferenceClient.

Cycles through scripted outcomes so overload and failure paths are testable:
  ok               "fake description of frame N"
  timeout          waits timeout_s, then status "timeout"
  connection_error / http_error / malformed / empty   explicit failure statuses
  ok_blank         status "ok" with whitespace text (the app must reject it)
  raise            describe() raises RuntimeError (the app logs client_exception)
Waiting is interruptible: close() makes an in-flight call return promptly.
"""

from __future__ import annotations

import itertools
import threading
import time
from typing import Callable, Optional, Sequence

from app.main import InferenceResult


class FakeVLMClient:
    def __init__(
        self,
        latency_s: float = 0.5,
        outcomes: Sequence[str] = ("ok",),
        timeout_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.latency_s = float(latency_s)
        self.outcomes = list(outcomes)
        self.timeout_s = float(timeout_s)
        self.clock = clock
        self._cycle = itertools.cycle(self.outcomes)
        self._closed = threading.Event()
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.calls: list[dict] = []
        self.closed = False

    def metadata(self) -> dict:
        return {"kind": "fake", "latency_s": self.latency_s, "outcomes": self.outcomes, "timeout_s": self.timeout_s}

    def describe(self, *, image_jpeg: bytes, prompt: str, max_tokens: int, frame_id: int, request_id: str) -> InferenceResult:
        with self._lock:
            outcome = next(self._cycle)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls.append({
                "request_id": request_id, "frame_id": frame_id, "outcome": outcome,
                "image_bytes": len(image_jpeg), "start_s": self.clock(), "max_tokens": max_tokens, "prompt": prompt,
            })
        try:
            if not image_jpeg:
                return InferenceResult(status="malformed", error_type="empty_image", error_detail="no image bytes")
            wait = min(self.latency_s, self.timeout_s) if outcome != "timeout" else self.timeout_s
            if self._closed.wait(wait):
                return InferenceResult(status="connection_error", error_type="client_closed", error_detail="closed during request")
            if outcome == "ok":
                return InferenceResult(status="ok", text=f"fake description of frame {frame_id}", usage=None)
            if outcome == "ok_blank":
                return InferenceResult(status="ok", text="   ")
            if outcome == "raise":
                raise RuntimeError("fake client blew up")
            if outcome == "timeout":
                return InferenceResult(status="timeout", error_type="timeout", error_detail=f"no response in {self.timeout_s}s")
            return InferenceResult(status=outcome, error_type=outcome, error_detail=f"fake {outcome}")
        finally:
            with self._lock:
                self.active -= 1

    def close(self) -> None:
        self.closed = True
        self._closed.set()
