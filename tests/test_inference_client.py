import base64
import json

import httpx
import pytest

from vlm.client import VLMClient, VLMConfig


def completion(text="A cup is visible.", **extra):
    return {"choices": [{"message": {"content": text}, "finish_reason": "stop"}], **extra}


def test_repeated_images_keep_one_transport_and_fresh_evidence():
    requests = []

    def handler(request):
        assert request.url.path == "/v1/chat/completions"
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=completion(
                usage={
                    "prompt_tokens": 20,
                    "completion_tokens": 7,
                    "prompt_tokens_details": {"cached_tokens": 0},
                }
            ),
        )

    transport = httpx.MockTransport(handler)
    ticks = iter([100.0, 102.0, 103.0, 104.5])
    with VLMClient(transport=transport, clock=lambda: next(ticks)) as client:
        first = client.infer(b"first image", frame_id="0", source_time_s=1.25, max_tokens=16)
        second = client.infer(b"second image", frame_id="1", max_tokens=16, mime_type="image/png")
    assert first.ok and second.ok
    assert first.elapsed_s == 2.0
    assert first.source_time_s == 1.25
    assert first.response_available_s == 102.0
    assert first.output_tokens == 7 and first.cached_tokens == 0
    assert first.request_id != second.request_id
    assert len(requests) == 2
    for payload, image in zip(requests, [b"first image", b"second image"]):
        assert payload["max_tokens"] == 16
        assert payload["stream"] is False
        assert payload["cache_prompt"] is False
        assert len(payload["messages"]) == 1
        url = payload["messages"][0]["content"][1]["image_url"]["url"]
        assert base64.b64decode(url.split(",")[1]) == image
    assert client._http.is_closed


@pytest.mark.parametrize(
    "response,status",
    [
        (httpx.Response(503, json={"error": "busy"}), "http_error"),
        (httpx.Response(200, text="not JSON"), "invalid_response"),
        (httpx.Response(200, json=[]), "invalid_response"),
        (httpx.Response(200, json={"choices": []}), "invalid_response"),
        (httpx.Response(200, json=completion(None)), "invalid_response"),
        (httpx.Response(200, json=completion("  ")), "empty_response"),
    ],
)
def test_failed_responses_are_records_and_never_retried(response, status):
    calls = []

    def handler(request):
        calls.append(request)
        return response

    with VLMClient(transport=httpx.MockTransport(handler)) as client:
        result = client.infer(b"image", frame_id="a")
    assert result.status == status
    assert result.text is None and result.error
    assert result.to_dict()["record_version"] == 1
    assert len(calls) == 1


@pytest.mark.parametrize(
    "error,status,uncertain",
    [
        (httpx.ConnectError, "connection_error", False),
        (httpx.ConnectTimeout, "timeout", False),
        (httpx.PoolTimeout, "timeout", False),
        (httpx.ReadTimeout, "timeout", True),
        (httpx.WriteTimeout, "timeout", True),
        (httpx.ReadError, "transport_error", True),
    ],
)
def test_transport_failures_preserve_server_uncertainty(error, status, uncertain):
    calls = []

    def handler(request):
        calls.append(request)
        raise error("failure", request=request)

    with VLMClient(transport=httpx.MockTransport(handler)) as client:
        result = client.infer(b"image", frame_id="a")
    assert result.status == status
    assert result.server_state_unknown is uncertain
    assert len(calls) == 1


@pytest.mark.parametrize(
    "arguments",
    [
        {"image": b""},
        {"image": "not bytes"},
        {"frame_id": ""},
        {"prompt": ""},
        {"max_tokens": 0},
        {"max_tokens": 65},
        {"max_tokens": True},
        {"mime_type": "text/plain"},
        {"source_time_s": -1},
        {"source_time_s": float("nan")},
        {"source_time_s": "not a timestamp"},
    ],
)
def test_invalid_inputs_fail_before_network_io(arguments):
    def unexpected(request):
        pytest.fail("invalid input reached the server")

    values = {"image": b"image", "frame_id": "a", **arguments}
    with VLMClient(transport=httpx.MockTransport(unexpected)) as client:
        with pytest.raises(ValueError):
            client.infer(**values)


@pytest.mark.parametrize(
    "usage",
    [
        None,
        [],
        {"completion_tokens": True},
        {
            "prompt_tokens": -1,
            "completion_tokens": "7",
            "prompt_tokens_details": [],
        },
    ],
)
def test_unavailable_or_invalid_usage_is_missing(usage):
    with VLMClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=completion(usage=usage)),
        )
    ) as client:
        result = client.infer(b"image", frame_id="a")
    assert result.ok
    assert result.prompt_tokens is None
    assert result.output_tokens is None
    assert result.cached_tokens is None


@pytest.mark.parametrize(
    "config",
    [
        {"base_url": "file:///tmp/server"},
        {"model": ""},
        {"max_output_tokens": -1},
        {"read_timeout_s": float("inf")},
        {"connect_timeout_s": 0},
        {"read_timeout_s": None},
        {"base_url": "http://user:secret@localhost"},
    ],
)
def test_invalid_configuration(config):
    with pytest.raises(ValueError):
        VLMConfig(**config)


def test_properties_and_closed_client():
    with VLMClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"build_info": "test"}),
        )
    ) as client:
        assert client.server_properties()["build_info"] == "test"
    with pytest.raises(RuntimeError, match="closed"):
        client.infer(b"image", frame_id="a")
