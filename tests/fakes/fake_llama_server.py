"""Fake llama-server: a local HTTP server that serves scripted chat-completion replies."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def reply(text="A desk with a laptop.", finish="stop", usage=True, timings=True):
    body = {"choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": finish}]}
    if usage:
        body["usage"] = {"prompt_tokens": 150, "completion_tokens": 8}
    if timings:
        body["timings"] = {"prompt_ms": 2800.0, "predicted_ms": 120.0}
    return 200, json.dumps(body).encode()


DROP = None  # respond() returning this closes the connection without a reply


def scripted(*replies):
    """respond() that cycles through the given replies, one per completion request."""
    state = {"i": 0}

    def respond(path, body):
        out = replies[state["i"] % len(replies)]
        state["i"] += 1
        return out

    return respond


class FakeServer:
    """Stand-in for llama-server.

    ``GET /health`` answers 200 (503 when ``healthy`` is False). Every other
    request gets ``respond(path, body)``: ``(status, bytes)``, ``(status, bytes,
    delay_s)`` or ``DROP``, sent after ``delay_s`` (default ``self.delay_s``).
    ``max_active`` records the most completion requests handled at once.
    """

    def __init__(self, respond=None, delay_s: float = 0.0):
        self.requests = []
        self.respond = respond or (lambda path, body: reply())
        self.delay_s = delay_s
        self.healthy = True
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, status, payload):
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                except OSError:
                    pass  # client gave up (timeout / close); nothing to report

            def do_GET(self):
                if self.path == "/health":
                    self._send(200 if fake.healthy else 503, b'{"status": "ok"}' if fake.healthy else b'{"error": "loading"}')
                else:
                    self._send(404, b"{}")

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                with fake._lock:
                    fake.requests.append((self.command, self.path, body))
                    fake.active += 1
                    fake.max_active = max(fake.max_active, fake.active)
                try:
                    out = fake.respond(self.path, body)
                    delay = out[2] if out is not DROP and len(out) > 2 else fake.delay_s
                    time.sleep(delay)
                    if out is DROP:
                        self.close_connection = True
                        return
                    self._send(out[0], out[1])
                finally:
                    with fake._lock:
                        fake.active -= 1

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
