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
