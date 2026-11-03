"""In-process stand-in for llama-server, used through httpx.MockTransport by vlm.client.VLMClient."""

from __future__ import annotations

import itertools
import json
import threading

import httpx

from vlm.client import VLMClient, VLMConfig

PROPS = {
    "build_info": "b0-fake",
    "model_path": "/models/fake.gguf",
    "model_alias": "fake",
    "total_slots": 1,
}


def completion(text: str) -> dict:
    return {
        "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 150, "completion_tokens": 8},
        "timings": {"prompt_ms": 2800.0, "predicted_ms": 120.0},
    }


class FakeLlama:
    """Answers /props and /v1/chat/completions after ``latency_s``, cycling through ``outcomes``:
    ok, timeout (read timeout), connect_error, http_error, invalid, empty.
    ``release`` cuts a pending wait short; ``max_active`` records concurrent completions."""

    def __init__(self, latency_s: float = 0.01, outcomes=("ok",)) -> None:
        self.latency_s = latency_s
        self._outcomes = itertools.cycle(outcomes)
        self._lock = threading.Lock()
        self.release = threading.Event()
        self.completions: list[dict] = []
        self.active = 0
        self.max_active = 0

    def client(self, *, read_timeout_s: float = 120.0, max_output_tokens: int = 64) -> VLMClient:
        config = VLMConfig(
            base_url="http://fake-llama:8080",
            model="fake",
            max_output_tokens=max_output_tokens,
            read_timeout_s=read_timeout_s,
        )
        return VLMClient(config, transport=httpx.MockTransport(self))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/props":
            return httpx.Response(200, json=PROPS)
        with self._lock:
            outcome = next(self._outcomes)
            self.completions.append(json.loads(request.content))
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            self.release.wait(self.latency_s)
            if outcome == "timeout":
                raise httpx.ReadTimeout("fake read timeout", request=request)
            if outcome == "connect_error":
                raise httpx.ConnectError("fake connection refused", request=request)
            if outcome == "http_error":
                return httpx.Response(500, json={"error": "boom"})
            if outcome == "invalid":
                return httpx.Response(200, content=b"not json")
            if outcome == "empty":
                return httpx.Response(200, json=completion(""))
            return httpx.Response(200, json=completion(f"fake description {len(self.completions)}"))
        finally:
            with self._lock:
                self.active -= 1
