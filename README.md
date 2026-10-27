# cap6411-cv-systems

## Capture and baseline

Webcam / real-time replay sources (`src/capture/`, issue #3) and the
fixed-interval baseline app (`app/`, issue #4).

### Setup and tests

Dependency setup belongs to #1; until it lands, a plain venv is enough:

```bash
python3 -m venv .venv
.venv/bin/pip install opencv-python numpy pytest
.venv/bin/python -m pytest          # run from the repo root; no webcam or model needed
```

### Running the baseline

```bash
# replay a recording in real time, one VLM request every 2 s, headless
python -m app.main --source replay --video clip.mp4 --interval-s 2 --no-display

# webcam for 60 s with the overlay window (press q to stop)
python -m app.main --source webcam --device 0 --interval-s 2 --duration-s 60
```

The app needs a running llama-server at `--vlm-url` (see "Local VLM
server" below) and exits with an error before creating a run directory if
none is ready. Telemetry defaults to `--telemetry fake` (a test double in
`tests/fakes/`, synthetic values); `--telemetry real` exits with a
"pending #2" error until #2 lands. Run `python -m app.main -h`
for the full flag list. The flags are a stable interface for the benchmark
runner (#18); change them only with a note to its owner.

| Flag | Default | Meaning |
|---|---|---|
| `--source webcam\|replay` | required | input type |
| `--video PATH` | | file for `replay` |
| `--device ID` | `0` | camera index or device path for `webcam` |
| `--width/--height/--camera-fps` | | requested camera settings (observed values are recorded) |
| `--interval-s N` | `2.0` | seconds between VLM invocations |
| `--duration-s N` | until EOF / q / Ctrl-C | stop after N seconds |
| `--prompt`, `--max-tokens`, `--request-timeout-s` | | request settings |
| `--jpeg-quality` | `85` | JPEG quality of the frame sent to the VLM |
| `--vlm-url` | `http://127.0.0.1:8080` | llama-server address |
| `--telemetry fake\|real\|off`, `--telemetry-interval-s` | `fake`, `0.5` | telemetry backend |
| `--run-dir PATH` | `runs/<UTC>_<source>/` | output directory (refuses to overwrite) |
| `--no-display` | | headless run |
| `--shutdown-timeout-s` | `5` | max wait for threads / in-flight request on Ctrl-C |

Exit codes: `0` completed (EOF, duration, or q), `2` bad config, source failed
to open, or source ended in error, `130` interrupted, `1` unexpected error.

### Scheduling

Ticks fire at `t0 + k * interval` on the monotonic clock. Each tick sends the
newest frame. At most one request is in flight; a tick that fires while one is
running is skipped and logged as `tick_skipped_busy`. Nothing is queued.
Capture runs on its own thread, so slow inference never slows the source.

### Run directory

All field names are provisional until #10 (`schema_version: "0-provisional"`).

- `requests.jsonl`: `request_id`, `tick_index`, `frame_id`, `source_time_s`,
  `host_capture_s`, `host_tick_s`, `host_request_start_s`,
  `host_response_available_s`, `duration_s`, `status`
  (`ok|timeout|connection_error|http_error|malformed|empty|client_exception|abandoned_at_shutdown`),
  `text` (ok only), `error_type`, `error_detail`, `usage`
- `drops.jsonl`: `origin` (`app` or `source`), `reason`
  (`tick_skipped_busy`, `replay_late`, `empty_frame`, `read_failed`), `frame_id`, host times
- `telemetry.jsonl`: one line per sensor reading; unavailable readings are
  `valid: false, value: null`, never `0`
- `manifest.json`: config, source metadata (backend, requested vs observed
  size/fps, time method), source end reason, run end reason, counts, platform

### Time bases

- `host_*`: `time.monotonic()` seconds in the app process. Used to align frames,
  requests and power samples.
- `source_time_s`: media-relative seconds from the video's timestamps
  (`CAP_PROP_POS_MSEC`). If those are unusable, it is `frame_index / fps`; this
  needs a valid fps and is recorded as `time_method: frame_index_over_fps`,
  `cfr_assumed: true`. Webcam frames have `source_time_s = null`; use `host_capture_s`.

Replay frame *i* is due at `start + (t_i - t_0)`. Frames already later than one
frame period are skipped without decoding and logged as `replay_late`, so a
60 s clip takes about 60 s whether decoding or the consumer is fast or slow.
Frame IDs are the decode index, so they are the same on every replay.

### Using a source directly

```python
from src.capture import ReplaySource, WebcamSource

with ReplaySource("clip.mp4") as source:          # or WebcamSource(0)
    for frame in source:                          # frame.image is HxWx3 uint8 BGR
        print(frame.frame_id, frame.source_time_s, frame.host_capture_s)
print(source.end.reason)       # eof | incomplete_source | decode_failures | disconnected | stopped | ...
print(source.info.as_dict())   # backend, requested vs observed settings, drop counts
```

Opening fails with `SourceOpenError` (missing file, undecodable video, no
camera / permission). The capture is released on every exit path, including
Ctrl-C, and can be reopened.


## Local VLM server

Issue #1. One `llama-server` process keeps SmolVLM loaded; the app and
`src/vlm/client.py` send it one frame per request. CPU only.

### Pinned versions

| What | Version |
|---|---|
| llama.cpp | release `b11936`, commit `27b7a8a009de2f5f75d8111b6171381c920df764`, built with `GGML_METAL=OFF` (no GPU backend) |
| Primary model | [`ggml-org/SmolVLM-500M-Instruct-GGUF`](https://huggingface.co/ggml-org/SmolVLM-500M-Instruct-GGUF) rev `72e986006ef53e37cdd3f6d4241c90b0f01df376`: `SmolVLM-500M-Instruct-Q8_0.gguf` + `mmproj-SmolVLM-500M-Instruct-Q8_0.gguf` |
| Fallback model | [`ggml-org/SmolVLM-256M-Instruct-GGUF`](https://huggingface.co/ggml-org/SmolVLM-256M-Instruct-GGUF) rev `b9e4379657e1450d04d02eec8e345667265b0a00`, same file pattern |

SHA-256 of the files:

```
9d4612de6a42214499e301494a3ecc2be0abdd9de44e663bda63f1152fad1bf4  SmolVLM-500M-Instruct-Q8_0.gguf
d1eb8b6b23979205fdf63703ed10f788131a3f812c7b1f72e0119d5d81295150  mmproj-SmolVLM-500M-Instruct-Q8_0.gguf
2a31195d3769c0b0fd0a4906201666108834848db768af11de1d2cef7cd35e65  SmolVLM-256M-Instruct-Q8_0.gguf
7e943f7c53f0382a6fc41b6ee0c2def63ba4fded9ab8ed039cc9e2ab905e0edd  mmproj-SmolVLM-256M-Instruct-Q8_0.gguf
```

### Build llama.cpp (once)

```bash
git clone https://github.com/ggml-org/llama.cpp ~/src/llama.cpp
cd ~/src/llama.cpp && git checkout b11936
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_METAL=OFF -DGGML_BLAS=OFF
cmake --build build -j 8 --target llama-server llama-mtmd-cli
./build/bin/llama-server --list-devices     # expect "(none)": CPU only
```

Tested on macOS (Apple M2). On Linux the same commands build a CPU-only
server (`GGML_METAL` is ignored there); not yet verified on Ubuntu.

### Download the model (once)

```bash
mkdir -p ~/models/smolvlm && cd ~/models/smolvlm
REV=72e986006ef53e37cdd3f6d4241c90b0f01df376
for f in SmolVLM-500M-Instruct-Q8_0.gguf mmproj-SmolVLM-500M-Instruct-Q8_0.gguf; do
  curl -L --fail -o "$f" "https://huggingface.co/ggml-org/SmolVLM-500M-Instruct-GGUF/resolve/$REV/$f"
done
shasum -a 256 *.gguf    # compare with the table above
```

### Start the server (keep it running)

```bash
~/src/llama.cpp/build/bin/llama-server \
  -m ~/models/smolvlm/SmolVLM-500M-Instruct-Q8_0.gguf \
  --mmproj ~/models/smolvlm/mmproj-SmolVLM-500M-Instruct-Q8_0.gguf \
  --host 127.0.0.1 --port 8080 -ngl 0 --no-mmproj-offload --parallel 1 -c 4096
```

- Ready when `curl http://127.0.0.1:8080/health` returns `{"status":"ok"}` (under a second).
- `--parallel 1`: one request at a time. With the default (4 slots), a new request
  can run alongside one the client already gave up on, which skews timing and energy.
- `-ngl 0 --no-mmproj-offload`: no GPU offload even on a build that has a GPU backend.
- `-c 4096`: a request uses about 300 tokens (image + prompt + answer).

The app records the server's build, model file, slot count and context in each
run's `manifest.json` (`vlm.server`).

### Smoke check

```bash
python -m src.vlm.smoke                      # add --image some.jpg to include a real photo
```

It describes two drawn images twice each, checks that they get different
answers, and checks that a server that isn't running shows up as
`connection_error`. Ends with `PASS` (exit 0) or `FAIL`.

### Behavior worth knowing

- **Latency (M2, CPU, 4 threads):** about 1.5 s for a 640x480 image, about 3 s for a
  1280x720 webcam frame. Almost all of it is image processing, not text generation,
  which is also why the 256M fallback is barely faster (2.9 s vs 3.0 s median).
- **Prompt cache off:** the client sends `cache_prompt: false`, so an identical image is
  processed again instead of answered from cache (a cached repeat took 0.05 s).
- **Timeouts:** when the client gives up, the server notices the closed connection and
  cancels the request about 1 s later. With `--parallel 1` the next request waits for
  that, so the first request after a timeout can take up to ~1 s longer.
- **Output bound:** `max_tokens` caps every answer; a cut-off answer is logged with
  `finish_reason: "length"`.
