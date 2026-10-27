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

The defaults are `--vlm fake` and `--telemetry fake` (test doubles in
`tests/fakes/`, synthetic values). `--vlm real` uses a running llama-server
at `--vlm-url` and exits with an error if none is ready. `--telemetry real`
exits with a "pending #2" error until #2 lands. Run `python -m app.main -h`
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
| `--vlm fake\|real`, `--vlm-url` | `fake`, `http://127.0.0.1:8080` | VLM backend and llama-server address |
| `--telemetry fake\|real\|off`, `--telemetry-interval-s` | `fake`, `0.5` | telemetry backend |
| `--fake-vlm-latency-s`, `--fake-vlm-outcomes` | `0.5`, `ok` | fake client behavior, e.g. `ok,timeout,malformed,empty` |
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
