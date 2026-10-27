"""Live smoke check for a running llama-server (item 1a).

    python -m src.vlm.smoke [--url http://127.0.0.1:8080] [--image photo.jpg ...]

Checks that the server is ready, that repeated requests to the one loaded
model succeed, that two different images get different answers, and that a
server that isn't running is reported as connection_error. Exits 0 when all
checks pass.
"""

from __future__ import annotations

import argparse
import socket
import sys

import cv2
import numpy as np

from src.vlm.client import LlamaServerClient

PROMPT = "Describe the scene in one short sentence."


def drawn_image(kind: str) -> bytes:
    image = np.full((480, 640, 3), 255, np.uint8)
    if kind == "red circle":
        cv2.circle(image, (320, 240), 120, (0, 0, 255), -1)
    else:
        cv2.rectangle(image, (200, 120), (440, 360), (255, 0, 0), -1)
    return cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.vlm.smoke", allow_abbrev=False)
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--image", action="append", default=[], help="extra JPEG/PNG to describe (repeatable)")
    parser.add_argument("--max-tokens", type=int, default=64)
    args = parser.parse_args(argv)

    client = LlamaServerClient(args.url, timeout_s=60)
    if not client.health():
        print(f"FAIL  no ready llama-server at {args.url}")
        return 1
    print(f"server  {client.server_props}")

    images = [("red circle", drawn_image("red circle")), ("blue square", drawn_image("blue square"))]
    for path in args.image:
        image = cv2.imread(path)
        if image is None:
            print(f"FAIL  cannot read {path}")
            return 1
        images.append((path, cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()))

    answers: dict[str, set] = {}
    failures = 0
    for repeat in range(2):
        for i, (name, jpeg) in enumerate(images):
            r = client.describe(image_jpeg=jpeg, prompt=PROMPT, max_tokens=args.max_tokens,
                                frame_id=i, request_id=f"smoke-{repeat}-{i}")
            seconds = r.response_available_s - r.request_start_s
            print(f"{r.status:16s} {seconds:5.2f}s  {name:12s} {r.text or r.error_type!r}"
                  f"{'  (cut by max_tokens)' if r.finish_reason == 'length' else ''}")
            failures += r.status != "ok"
            answers.setdefault(name, set()).add(r.text)

    if answers["red circle"] & answers["blue square"]:
        print("FAIL  different images got the same answer")
        failures += 1
    else:
        print("ok    different images got different answers")

    with socket.socket() as s:  # a port with nothing listening stands in for a stopped server
        s.bind(("127.0.0.1", 0))
        dead = f"http://127.0.0.1:{s.getsockname()[1]}"
    r = LlamaServerClient(dead, timeout_s=2).describe(image_jpeg=images[0][1], prompt=PROMPT, max_tokens=8,
                                                      frame_id=0, request_id="smoke-dead")
    if r.status == "connection_error":
        print(f"ok    stopped server reported as connection_error ({r.error_type})")
    else:
        print(f"FAIL  stopped server reported as {r.status}")
        failures += 1

    print("PASS" if failures == 0 else f"FAIL  {failures} check(s) failed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
