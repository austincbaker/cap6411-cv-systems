"""LlamaServerClient against a fake HTTP server (no model or llama.cpp needed)."""

from __future__ import annotations

import base64
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from src.vlm.client import LlamaServerClient

JPEG = b"\xff\xd8fake-jpeg-bytes\xff\xd9"


def reply(text="A desk with a laptop.", finish="stop", usage=True, timings=True):
    body = {"choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": finish}]}
    if usage:
        body["usage"] = {"prompt_tokens": 150, "completion_tokens": 8}
    if timings:
        body["timings"] = {"prompt_ms": 2800.0, "predicted_ms": 120.0}
    return 200, json.dumps(body).encode()


class FakeServer:
    """Serves whatever ``self.respond(path, body) -> (status, bytes)`` returns, after ``self.delay_s``."""

    def __init__(self):
        self.requests = []
        self.respond = lambda path, body: reply()
        self.delay_s = 0.0
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _serve(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                fake.requests.append((self.command, self.path, body))
                time.sleep(fake.delay_s)
                status, payload = fake.respond(self.path, body)
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except OSError:
                    pass  # client gave up (timeout / close); nothing to report

            do_GET = do_POST = _serve

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self.thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(2)


@pytest.fixture
def server():
    fake = FakeServer()
    yield fake
    fake.stop()


def describe(client, **kw):
    args = dict(image_jpeg=JPEG, prompt="Describe the scene.", max_tokens=64, frame_id=7, request_id="r1")
    args.update(kw)
    return client.describe(**args)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# --------------------------------------------------------------------------- success


def test_request_carries_image_prompt_and_bounds(server):
    result = describe(LlamaServerClient(server.url), max_tokens=32)
    method, path, raw = server.requests[0]
    body = json.loads(raw)
    assert (method, path) == ("POST", "/v1/chat/completions")
    text_part, image_part = body["messages"][0]["content"]
    assert text_part == {"type": "text", "text": "Describe the scene."}
    url = image_part["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == JPEG
    assert body["max_tokens"] == 32
    assert body["temperature"] == 0.0
    assert body["cache_prompt"] is False
    assert result.status == "ok"


def test_ok_result_has_text_identity_timing_and_usage(server):
    server.respond = lambda p, b: reply(text="  A desk with a laptop.\n")
    result = describe(LlamaServerClient(server.url), frame_id=42, request_id="abc")
    assert result.status == "ok" and result.text == "A desk with a laptop."
    assert (result.request_id, result.frame_id) == ("abc", 42)
    assert result.error_type is None and result.finish_reason == "stop"
    assert result.usage == {"prompt_tokens": 150, "completion_tokens": 8, "prompt_ms": 2800.0, "predicted_ms": 120.0}
    assert result.request_start_s <= result.response_available_s


def test_missing_usage_stays_missing(server):
    server.respond = lambda p, b: reply(usage=False, timings=False)
    result = describe(LlamaServerClient(server.url))
    assert result.status == "ok" and result.usage is None


def test_truncation_by_max_tokens_is_visible(server):
    server.respond = lambda p, b: reply(text="A desk with a", finish="length")
    result = describe(LlamaServerClient(server.url))
    assert result.status == "ok" and result.finish_reason == "length"


def test_repeated_requests_use_the_same_client(server):
    client = LlamaServerClient(server.url)
    assert [describe(client, request_id=f"r{i}").status for i in range(3)] == ["ok"] * 3
    assert len(server.requests) == 3


# --------------------------------------------------------------------------- failures


def test_timeout_is_reported_not_raised(server):
    server.delay_s = 1.0
    started = time.monotonic()
    result = describe(LlamaServerClient(server.url, timeout_s=0.2))
    assert result.status == "timeout" and result.error_type == "timeout" and result.text is None
    assert time.monotonic() - started < 0.8


def test_connection_refused_is_a_connection_error():
    result = describe(LlamaServerClient(f"http://127.0.0.1:{free_port()}", timeout_s=1))
    assert result.status == "connection_error" and result.text is None
    assert result.error_type == "ConnectionRefusedError"


def test_non_200_is_an_http_error(server):
    server.respond = lambda p, b: (500, b'{"error": "model crashed"}')
    result = describe(LlamaServerClient(server.url))
    assert result.status == "http_error" and result.error_type == "http_500"
    assert "model crashed" in result.error_detail


@pytest.mark.parametrize("payload", [b"not json", b"{}", b'{"choices": []}', b'{"choices": [{"message": {}}]}',
                                     b'{"choices": [{"message": {"content": 5}}]}'])
def test_unexpected_body_is_malformed(server, payload):
    server.respond = lambda p, b: (200, payload)
    result = describe(LlamaServerClient(server.url))
    assert result.status == "malformed" and result.text is None


@pytest.mark.parametrize("text", ["", "   \n", None])
def test_no_text_is_empty(server, text):
    server.respond = lambda p, b: reply(text=text)
    result = describe(LlamaServerClient(server.url))
    assert result.status == "empty" and result.error_type == "empty_text" and result.text is None


def test_close_aborts_a_waiting_request(server):
    server.delay_s = 5.0
    client = LlamaServerClient(server.url, timeout_s=10)
    timer = threading.Timer(0.2, client.close)
    started = time.monotonic()
    timer.start()
    result = describe(client)
    timer.join()
    assert result.status == "connection_error"
    assert time.monotonic() - started < 1.5
    server.delay_s = 0.0
    assert describe(client).status == "ok"  # still usable afterwards


# --------------------------------------------------------------------------- validation and health


@pytest.mark.parametrize("kw", [{"image_jpeg": b""}, {"max_tokens": 0}])
def test_invalid_input_fails_before_sending(server, kw):
    with pytest.raises(ValueError):
        describe(LlamaServerClient(server.url), **kw)
    assert server.requests == []


@pytest.mark.parametrize("url", ["127.0.0.1:8080", "https://127.0.0.1:8080", "http://"])
def test_bad_base_url_is_rejected(url):
    with pytest.raises(ValueError):
        LlamaServerClient(url)


def test_health(server):
    assert LlamaServerClient(server.url).health() is True
    server.respond = lambda p, b: (503, b'{"error": "loading model"}')
    assert LlamaServerClient(server.url).health() is False
    assert LlamaServerClient(f"http://127.0.0.1:{free_port()}", timeout_s=1).health() is False
