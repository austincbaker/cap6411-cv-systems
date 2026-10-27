"""Client for a persistent local llama-server running a SmolVLM model (item 1a).

The server is started once and stays loaded (see README); this client sends
one JPEG frame per request to its OpenAI-compatible endpoint
``POST /v1/chat/completions`` with the image as a base64 data URL.

Every call returns an ``InferenceResult``; transport problems never raise:

    ok                text present
    timeout           no response within ``timeout_s``
    connection_error  server not reachable / connection dropped
    http_error        non-200 response
    malformed         200 response that isn't the expected JSON shape
    empty             200 response with no text

Invalid caller input (empty image, max_tokens < 1) raises ``ValueError``
before anything is sent. There are no automatic retries.

The server's prompt cache is disabled per request (``cache_prompt: false``)
so an identical frame is processed again rather than answered from cache.

Standard library only (``http.client``). Each request uses a fresh localhost
connection (no stale keep-alive sockets); ``close()`` from another thread
aborts a request that is still waiting.
"""

from __future__ import annotations

import base64
import http.client
import json
import socket
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit


@dataclass
class InferenceResult:
    status: str
    text: Optional[str] = None
    error_type: Optional[str] = None
    error_detail: Optional[str] = None
    usage: Optional[dict] = None  # server token counts and timings; None when not reported
    finish_reason: Optional[str] = None  # "length" means the max_tokens bound cut the answer
    request_id: Optional[str] = None
    frame_id: Optional[int] = None
    request_start_s: Optional[float] = None  # time.monotonic()
    response_available_s: Optional[float] = None  # time.monotonic()


class LlamaServerClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080",
        *,
        timeout_s: float = 30.0,
        temperature: float = 0.0,
    ) -> None:
        url = urlsplit(base_url)
        if url.scheme != "http" or not url.hostname:
            raise ValueError(f"base_url must look like http://host:port, got {base_url!r}")
        if not timeout_s > 0:
            raise ValueError("timeout_s must be > 0")
        self.host = url.hostname
        self.port = url.port or 80
        self.timeout_s = timeout_s
        self.temperature = temperature
        self._conn: Optional[http.client.HTTPConnection] = None  # the request in progress, if any

    def metadata(self) -> dict:
        return {"kind": "llama-server", "url": f"http://{self.host}:{self.port}", "timeout_s": self.timeout_s,
                "temperature": self.temperature, "cache_prompt": False}

    def health(self) -> bool:
        """True when the server reports it is loaded and ready."""
        try:
            status, _ = self._request("GET", "/health", None)
        except (OSError, http.client.HTTPException):
            return False
        return status == 200

    def describe(
        self, *, image_jpeg: bytes, prompt: str, max_tokens: int, frame_id: int, request_id: str
    ) -> InferenceResult:
        if not image_jpeg:
            raise ValueError("image_jpeg is empty")
        if max_tokens < 1:
            raise ValueError("max_tokens must be >= 1")

        body = json.dumps({
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {
                    "url": "data:image/jpeg;base64," + base64.b64encode(image_jpeg).decode("ascii")}},
            ]}],
            "max_tokens": max_tokens,
            "temperature": self.temperature,
            "cache_prompt": False,
        }).encode("utf-8")

        result = InferenceResult(status="", request_id=request_id, frame_id=frame_id)
        result.request_start_s = time.monotonic()
        try:
            status, raw = self._request("POST", "/v1/chat/completions", body)
        except socket.timeout as exc:
            # The connection is closed on timeout; whether the server then stops generating is in the README.
            return self._finish(result, "timeout", "timeout", f"no response within {self.timeout_s}s ({exc})")
        except (OSError, http.client.HTTPException) as exc:
            return self._finish(result, "connection_error", type(exc).__name__, str(exc))

        if status != 200:
            return self._finish(result, "http_error", f"http_{status}", raw[:300].decode("utf-8", "replace"))
        try:
            payload = json.loads(raw)
            choice = payload["choices"][0]
            text = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            return self._finish(result, "malformed", type(exc).__name__, raw[:300].decode("utf-8", "replace"))
        if text is not None and not isinstance(text, str):
            return self._finish(result, "malformed", "non_string_content", repr(text)[:300])

        result.finish_reason = choice.get("finish_reason")
        usage = {**(payload.get("usage") or {}), **(payload.get("timings") or {})}
        result.usage = usage or None
        if not text or not text.strip():
            return self._finish(result, "empty", "empty_text", "server returned no text")
        result.text = text.strip()
        return self._finish(result, "ok")

    def close(self) -> None:
        """Abort a request in progress (safe from another thread); the client stays usable."""
        conn = self._conn
        if conn is not None and conn.sock is not None:
            try:
                conn.sock.shutdown(socket.SHUT_RDWR)  # wakes a thread blocked in recv()
            except OSError:
                pass

    # -- internals ------------------------------------------------------------
    def _request(self, method: str, path: str, body: Optional[bytes]) -> tuple[int, bytes]:
        conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout_s)
        self._conn = conn
        try:
            headers = {"Content-Type": "application/json"} if body is not None else {}
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            self._conn = None
            conn.close()

    @staticmethod
    def _finish(result: InferenceResult, status: str, error_type: Optional[str] = None,
                error_detail: Optional[str] = None) -> InferenceResult:
        result.status = status
        result.error_type = error_type
        result.error_detail = error_detail
        result.response_available_s = time.monotonic()
        return result
