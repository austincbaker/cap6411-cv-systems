import json
from dataclasses import replace

import pytest

from vlm import smoke
from vlm.client import InferenceResult


def test_smoke_repeats_images_in_one_client_and_records_provenance(tmp_path, monkeypatch):
    calls = []
    clients = []

    class Client:
        def __init__(self, config):
            clients.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True

        def server_properties(self):
            return {"build_info": "observed-test-build"}

        def infer(self, image, **kwargs):
            calls.append((image, kwargs))
            return InferenceResult(
                request_id=str(len(calls)),
                frame_id=kwargs["frame_id"],
                source_id=kwargs["source_id"],
                source_time_s=None,
                model="test",
                status="ok",
                text="A scene.",
                request_started_s=10,
                response_available_s=11,
                elapsed_s=1,
                max_output_tokens=kwargs["max_tokens"],
            )

    monkeypatch.setattr(smoke, "VLMClient", Client)
    images = [tmp_path / "a.jpg", tmp_path / "b.png"]
    for image, data in zip(images, [b"first", b"second"]):
        image.write_bytes(data)
    output = tmp_path / "run"
    args = [
        "--image",
        str(images[0]),
        "--image",
        str(images[1]),
        "--output",
        str(output),
        "--max-tokens",
        "16",
    ]
    assert smoke.main(args) == 0
    assert len(clients) == 1 and clients[0].closed
    assert [data for data, _ in calls] == [b"first", b"second", b"first", b"second"]
    records = [json.loads(line) for line in (output / "requests.jsonl").read_text().splitlines()]
    assert len(records) == 4
    assert records[0]["image_sha256"] != records[1]["image_sha256"]
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["completed"] and manifest["requests"] == 4
    assert manifest["observed_server_properties"]["build_info"] == "observed-test-build"
    with pytest.raises(SystemExit):
        smoke.main(args)

    # A failed inference may still be executing on the server; stop, do not retry.
    def failure(self, image, **kwargs):
        return replace(
            InferenceResult(
                "failure", kwargs["frame_id"], None, None, "test", "ok", "x", 10, 11, 1, 16
            ),
            status="timeout",
            text=None,
            error="ReadTimeout",
            server_state_unknown=True,
        )

    monkeypatch.setattr(Client, "infer", failure)
    failed = tmp_path / "failed"
    assert smoke.main(["--image", str(images[0]), "--output", str(failed)]) == 1
    manifest = json.loads((failed / "manifest.json").read_text())
    assert not manifest["completed"] and manifest["requests"] == 1


def test_invalid_image_never_creates_a_run(tmp_path):
    image = tmp_path / "empty.png"
    image.write_bytes(b"")
    output = tmp_path / "run"
    with pytest.raises(SystemExit):
        smoke.main(["--image", str(image), "--output", str(output)])
    assert not output.exists()
