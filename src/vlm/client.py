"""Persistent, bounded image requests to a local llama.cpp server.

This transport does not infer scene changes or maintain conversation history.
Every call supplies its image again, and failures are returned as explicit records.
"""

from __future__ import annotations

import base64
import math
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Callable

import httpx


def _positive_seconds(value: float, name: str) -> None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{name} must be finite and positive")


@dataclass(frozen=True)
class VLMConfig:
    base_url: str = "http://127.0.0.1:8080"
    model: str = "smolvlm2-500m-q8"
    max_output_tokens: int = 64
    connect_timeout_s: float = 5.0
    read_timeout_s: float = 120.0
    write_timeout_s: float = 30.0
    pool_timeout_s: float = 5.0

    def __post_init__(self) -> None:
        url = httpx.URL(self.base_url)
        if url.scheme not in {"http", "https"} or not url.host:
            raise ValueError("base_url must be an HTTP(S) server URL")
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("base_url must not contain credentials, a query or a fragment")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("model must be a nonempty server model alias")
        if type(self.max_output_tokens) is not int or self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be a positive integer")
        for field in ("connect_timeout_s", "read_timeout_s", "write_timeout_s", "pool_timeout_s"):
            _positive_seconds(getattr(self, field), field)


@dataclass(frozen=True)
class InferenceResult:
    request_id: str
    frame_id: str
    source_id: str | None
    source_time_s: float | None
    model: str
    status: str
    text: str | None
    request_started_s: float
    response_available_s: float
    elapsed_s: float
    max_output_tokens: int
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None
    finish_reason: str | None = None
    http_status: int | None = None
    error: str | None = None
    server_state_unknown: bool = False

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict[str, Any]:
        return {"record_version": 1, **asdict(self)}


def _token_count(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


class VLMClient:
    """Own one reusable HTTP session; callers must serialize inference requests.

    There are no retries. A read/write timeout can leave server-side work active;
    stop admitting requests until the application verifies that the server is idle.
    The client does not start/stop the service or silently reset its state.
    """

    def __init__(
        self,
        config: VLMConfig | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config or VLMConfig()
        self._clock = clock
        self._closed = False
        self._http = httpx.Client(
            base_url=self.config.base_url.rstrip("/") + "/",
            timeout=httpx.Timeout(
                connect=self.config.connect_timeout_s,
                read=self.config.read_timeout_s,
                write=self.config.write_timeout_s,
                pool=self.config.pool_timeout_s,
            ),
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
            transport=transport,
            trust_env=False,
        )

    def __enter__(self) -> VLMClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()
        self._closed = True

    def server_properties(self) -> dict[str, Any]:
        """Read observed service metadata; transport/HTTP errors remain visible."""
        response = self._http.get("props")
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("server properties must be a JSON object")
        return data

    def infer(
        self,
        image: bytes,
        *,
        frame_id: str,
        prompt: str = "Describe the visible objects in one short sentence.",
        mime_type: str = "image/jpeg",
        source_id: str | None = None,
        source_time_s: float | None = None,
        max_tokens: int | None = None,
    ) -> InferenceResult:
        """Submit fresh image evidence; invalid local inputs raise ValueError.

        Times use the host monotonic clock. source_time_s is independent media
        time, not inferred from request completion or elapsed inference time.
        """
        if self._closed:
            raise RuntimeError("VLMClient is closed")
        if not isinstance(image, bytes) or not image:
            raise ValueError("image must contain encoded image bytes")
        if mime_type not in {"image/jpeg", "image/png"}:
            raise ValueError("mime_type must be image/jpeg or image/png")
        if not isinstance(frame_id, str) or not frame_id.strip():
            raise ValueError("frame_id must be a nonempty string")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a nonempty string")
        if source_time_s is not None and (
            not isinstance(source_time_s, (int, float))
            or isinstance(source_time_s, bool)
            or not math.isfinite(source_time_s)
            or source_time_s < 0
        ):
            raise ValueError("source_time_s must be finite and nonnegative")
        bound = self.config.max_output_tokens if max_tokens is None else max_tokens
        if type(bound) is not int or not 0 < bound <= self.config.max_output_tokens:
            raise ValueError("max_tokens must be positive and within the configured output bound")

        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{base64.b64encode(image).decode('ascii')}"
                            },
                        },
                    ],
                }
            ],
            "max_tokens": bound,
            "temperature": 0,
            "seed": 0,
            "stream": False,
            "cache_prompt": False,
        }
        started = self._clock()
        common = dict(
            request_id=uuid.uuid4().hex,
            frame_id=frame_id,
            source_id=source_id,
            source_time_s=source_time_s,
            model=self.config.model,
            request_started_s=started,
            max_output_tokens=bound,
        )

        def result(status: str, text: str | None = None, **fields: Any) -> InferenceResult:
            ended = self._clock()
            return InferenceResult(
                **common,
                status=status,
                text=text,
                response_available_s=ended,
                elapsed_s=ended - started,
                **fields,
            )

        try:
            response = self._http.post("v1/chat/completions", json=payload)
        except httpx.TimeoutException as exc:
            uncertain = not isinstance(exc, (httpx.ConnectTimeout, httpx.PoolTimeout))
            return result("timeout", error=type(exc).__name__, server_state_unknown=uncertain)
        except httpx.ConnectError as exc:
            return result("connection_error", error=type(exc).__name__)
        except httpx.RequestError as exc:
            return result("transport_error", error=type(exc).__name__, server_state_unknown=True)
        if not response.is_success:
            return result(
                "http_error", http_status=response.status_code, error="HTTP request failed"
            )
        try:
            data = response.json()
            choice = data["choices"][0]
            text = choice["message"]["content"]
            if not isinstance(text, str):
                raise ValueError("completion content must be text")
        except (ValueError, KeyError, IndexError, TypeError):
            return result(
                "invalid_response",
                http_status=response.status_code,
                error="Response is not a supported chat completion",
            )
        if not text.strip():
            return result(
                "empty_response",
                http_status=response.status_code,
                error="Server returned an empty completion",
            )
        usage = data.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        detail = usage.get("prompt_tokens_details")
        detail = detail if isinstance(detail, dict) else {}
        finish = choice.get("finish_reason")
        return result(
            "ok",
            text=text.strip(),
            http_status=response.status_code,
            prompt_tokens=_token_count(usage.get("prompt_tokens")),
            output_tokens=_token_count(usage.get("completion_tokens")),
            cached_tokens=_token_count(detail.get("cached_tokens")),
            finish_reason=finish if isinstance(finish, str) else None,
        )
