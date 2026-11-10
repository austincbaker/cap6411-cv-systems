# Always-on VLM assistant — CAP6411

Local image inference and read-only Linux energy telemetry for the always-on VLM project.
The software for Austin's first two items is implemented here and smoke-checked on the WSL2
experiment platform; owner review and the unplugged energy go/no-go remain. Webcam capture, event gating, scene-state
logic, energy-budget admission and final evaluation remain separate team tasks.

## Setup

Use Ubuntu 22.04.5 LTS, Python 3.10 or newer, Git, CMake, a C/C++ toolchain and
[uv](https://docs.astral.sh/uv/). The checked-in `uv.lock` records Python dependencies.
The WSL development check used Python 3.11.9, CMake 3.22.1 and GCC 11.4.0.

```bash
uv sync --extra dev
uv run python scripts/llama_runtime.py prepare
```

`prepare` clones the pinned llama.cpp release into `.cache/llama.cpp`, builds a CPU-only
server, downloads about 520 MiB of model/projector weights, checks their SHA-256 digests,
and writes `.cache/build-manifest.json`. It reuses verified weights on subsequent runs.
It does not install system packages. A fresh Ubuntu installation may need
`sudo apt-get install build-essential cmake git` first.

The selected profile is [configs/inference.json](configs/inference.json):

- llama.cpp `v0.7.0`, commit `620d2225cc436ab0b001e3200e590e3b286ef9ab`.
- SmolVLM2-500M-Video-Instruct Q8_0, with its matching Q8_0 vision projector, both
  from revision `ccd7aae53bcb1997355c2f094959e72b3642ce17`.
- Four CPU threads, one server slot, a 4,096-token context and a 64-token output ceiling.
- GPU backends are disabled at build time; language-model and projector offload are
  disabled again at startup. Prompt caching is disabled for this initial baseline.

See the [pinned runtime source](https://github.com/ggml-org/llama.cpp/tree/620d2225cc436ab0b001e3200e590e3b286ef9ab)
and [model artifacts](https://huggingface.co/ggml-org/SmolVLM2-500M-Video-Instruct-GGUF/tree/ccd7aae53bcb1997355c2f094959e72b3642ce17).
The 256M SmolVLM family remains a fallback candidate; it has not been downloaded or
validated in this implementation, and requires a separately pinned profile before use.

## Run local inference

Start the persistent service in its own terminal:

```bash
uv run python scripts/llama_runtime.py serve
```

The service listens on `http://127.0.0.1:8080`. Stop it with Ctrl+C. Startup records its
PID and exact command in `.cache/server-start.json`. The client connects to this existing
service and does not load weights or restart it for each image.

Use two contrasting JPEG/PNG files. These public COCO examples reproduce the live check:

```bash
mkdir -p .cache/smoke-images
curl -fL https://s3.amazonaws.com/images.cocodataset.org/val2017/000000039769.jpg -o .cache/smoke-images/cats.jpg
curl -fL https://s3.amazonaws.com/images.cocodataset.org/val2017/000000000139.jpg -o .cache/smoke-images/room.jpg
uv run vlm-smoke --image .cache/smoke-images/cats.jpg --image .cache/smoke-images/room.jpg --repeat 2 --max-tokens 32 --output results/inference-smoke
```

Each run directory must be new. The smoke command writes `requests.jsonl` and
`manifest.json`, preserving image hashes, request/frame IDs, source and host timestamps,
observed server properties, available usage counts and explicit failures. It stops on
the first failed inference instead of retrying uncertain server-side work.

Alejandro can call the transport directly:

```python
from pathlib import Path
from vlm.client import VLMClient, VLMConfig

with VLMClient(VLMConfig()) as client:
    result = client.infer(
        Path("frame.jpg").read_bytes(),
        frame_id="camera:12",
        source_id="camera:0",
        source_time_s=4.0,
        max_tokens=32,
    )
    print(result.to_dict())
```

Every call submits fresh image data and an independent prompt. Callers serialize requests
and own frame dropping/queue policy. Local input mistakes raise `ValueError`; attempted
requests return an `InferenceResult` whose status distinguishes success, connection
failure, timeout, HTTP error, malformed output and empty completion. A read/write timeout
does not prove server-side cancellation: when `server_state_unknown` is true, stop
admitting requests until the application verifies that the service is idle.

## Collect telemetry

```bash
uv run energy-monitor --inventory
uv run energy-monitor --duration 30 --interval 1 --output results/telemetry
```

The collector reads exposed sysfs sensors without modifying power limits or hardware
settings. It produces `samples.csv` and `manifest.json` with raw values, declared units,
normalized joules/watts, sensor domains, counter ranges, actual sampling times and error
or quality flags. Missing values are blank CSV cells, never fabricated zeros.

**This workspace is WSL2.** No powercap/RAPL counters are exposed. The default
`energy-monitor` sysfs output is diagnostic: the unplugged check found an unqualified
absolute battery scale. Use Windows host battery reporting for energy experiments.
The [dated 1b qualification](docs/1b-battery-qualification.md) records the GO decision,
raw evidence, coarse 30–40 second updates and experiment limitations.

The native reader needs Windows PowerShell interop (`powershell.exe` on PATH), without
admin access. One read preserves raw mWh, normalized joules, timing and AC/battery state:

```python
from energy.windows import WindowsBatteryReader
reading = WindowsBatteryReader().read()
# Accept energy only when reading.on_battery and the complete run is valid.
print(reading.to_dict())
```

To repeat the owner-authorized unplugged qualification, which includes a bounded CPU load:

```bash
uv run python scripts/qualify_battery.py --output results/battery-qualification-new \
  --idle-seconds 120 --load-seconds 120 --recovery-seconds 30 --interval 10 --workers 4
```

This creates `samples.jsonl`, `manifest.json` and `qualification.json`. It records native
battery readings alongside WSL diagnostics and aborts on invalid readings, AC connection
or battery below 20%. Application-wide run integration remains item 2d.

`completed` means recording completed; `valid` means a reading parsed successfully.
Neither overrides a measurement's domain or quality flags. In particular, battery flow
while plugged in is not whole-laptop draw. No sensor produces a nonzero command exit and
an explicit manifest error rather than a successful empty measurement.

For integration, `EnergyMonitor` accepts a shared `run_id` and `origin_s` from the
application's monotonic clock. `iter_samples(duration_s, interval_s, stop_event=...)`
yields batches without starting background threads. See [sensor methodology](docs/methodology.md)
for units, time alignment and limits. Component record formats remain provisional until
the team's item 2d contract handoff.

## Verification and handoff

```bash
uv run python -m pytest -q
uv run ruff check src scripts tests
uv run ruff format --check src scripts tests
```

Tests use fake HTTP services, sysfs trees and clocks; no GPU, model download or privileged
sensor access is required. Live validation and its limitations are recorded in
[docs/validation-1a-1b.md](docs/validation-1a-1b.md), with small real traces under
`docs/examples/`. Model weights, builds and full run artifacts remain ignored locally.

The [implementation index](energy-aware-vlm-implementation/README.md) links the team
tasks and their GitHub issues. No webcam/event-detection implementation is included yet.

## Capture and baseline

Webcam / real-time replay sources (`src/capture/`, issue #3) and the
fixed-interval baseline app (`app/`, issue #4).

Setup and tests use the same `uv sync --extra dev` environment as the rest of
the repository (OpenCV and NumPy are declared in `pyproject.toml`). The tests in
`tests/test_capture_sources.py` and `tests/test_app_baseline.py` need no webcam,
model or server.

### Running the baseline

Start the server first (see "Run local inference"), then:

```bash
# replay a recording in real time, one VLM request every 2 s, headless
uv run python -m app.main --source replay --video clip.mp4 --interval-s 2 --no-display

# webcam for 60 s with the overlay window (press q to stop)
uv run python -m app.main --source webcam --device 0 --interval-s 2 --duration-s 60
```

The app reads the server address, model alias, output bound and timeouts from
`--profile` (default `configs/inference.json`) and exits with code 2 before
creating a run directory if the server does not answer. Run
`uv run python -m app.main -h` for the full flag list. The flags are a stable interface for the benchmark
runner (#18); change them only with a note to its owner.

| Flag | Default | Meaning |
|---|---|---|
| `--source webcam\|replay` | required | input type |
| `--video PATH` | | file for `replay` |
| `--device ID` | `0` | camera index or device path for `webcam` |
| `--width/--height/--camera-fps` | | requested camera settings (observed values are recorded) |
| `--interval-s N` | `2.0` | seconds between VLM invocations |
| `--duration-s N` | until EOF / q / Ctrl-C | stop after N seconds |
| `--profile PATH` | `configs/inference.json` | inference profile: server address, model, bounds |
| `--prompt`, `--max-tokens`, `--request-timeout-s` | profile values | request settings; `--max-tokens` cannot exceed the profile bound |
| `--jpeg-quality` | `85` | JPEG quality of the frame sent to the VLM |
| `--server-idle-timeout-s` | `60` | after an uncertain timeout, end the run if the server stays busy this long |
| `--telemetry on\|off` | `on` | sysfs and Windows battery telemetry |
| `--telemetry-interval-s`, `--battery-interval-s` | `1`, `10` | sample intervals for sysfs and the Windows battery report |
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

A read timeout can leave the server still working (`server_state_unknown` in
the request record). After one, the app sends nothing until llama-server's
`/slots` reports no busy slot; those ticks are logged as
`tick_skipped_server_unknown`. If the server stays busy longer than
`--server-idle-timeout-s`, the run ends with `server_not_idle` (exit 2).

### Change gate (`--policy gated`, item 2a)

`--policy gated` keeps the same tick grid but sends a tick's frame only when
the change gate in `src/gates/change.py` triggers, so a gated run and a
fixed-interval run over the same clip and `--interval-s` see the same
candidate frames. With the gate, `--interval-s` is how often the gate looks
(for example 0.5), not how often the VLM is called.

```bash
uv run python -m app.main --source replay --video clip.mp4 --policy gated \
    --interval-s 0.5 --gate-threshold 0.05 --gate-min-interval-s 2 --no-display
```

Each frame is compared with the last frame sent to the VLM (the acknowledged
reference), so a slow change keeps growing until it triggers. Frames are
shrunk to 160x120 gray, blurred and mean-subtracted (a uniform lighting shift
is not change). A pixel counts as changed when it moved more than
`--gate-pixel-delta` (default 25 of 255); the score is the changed fraction of
the most-changed cell in a `--gate-grid` x `--gate-grid` grid (default 4;
1 is a global score). Per tick, in order:

| Reason | Logged in | When |
|---|---|---|
| `tick_skipped_busy`, `tick_skipped_server_unknown` | `drops.jsonl`, origin `app` | as in fixed-interval runs; checked first |
| `gate_initial` | `requests.jsonl` | first frame, no reference yet |
| `gate_refresh` | `requests.jsonl` | `--gate-refresh-s` passed since the last call (off by default) |
| `gate_no_change` | `drops.jsonl`, origin `gate` | score below `--gate-threshold` |
| `gate_cooldown` | `drops.jsonl`, origin `gate` | changed, but within `--gate-min-interval-s` of the last call |
| `gate_change` | `requests.jsonl` | otherwise |

Gate skips carry `gate_score`, `gate_global_score` and `gate_compute_s` (time
spent scoring, for gate-overhead accounting); sent requests carry the same
fields plus `gate_reason`. The manifest records `policy` and the `gate`
settings, and `counts` has one entry per reason. The default thresholds are
starting points: tune them on development clips only.

### Run directory

File formats follow the item 2d contract in
[`docs/data-contracts.md`](docs/data-contracts.md) (`schema_version: "1-draft"`).
Check a run directory with `uv run contracts-check runs/<run>`.

- `requests.jsonl`: the client's `InferenceResult` record (`request_id`, `status`,
  `text`, `request_started_s`, `response_available_s`, `elapsed_s`, token counts,
  `finish_reason`, `error`, `server_state_unknown`, ...) plus the app's `run_id`,
  `tick_index`, integer `frame_id`, `source_kind`, `source_time_s`,
  `host_capture_s`, `host_tick_s`, `encode_s`, `image_bytes`. The app adds the
  statuses `client_exception` and `abandoned_at_shutdown`.
- `drops.jsonl`: `origin` (`app`, `source` or `gate`), `reason`
  (`tick_skipped_busy`, `tick_skipped_server_unknown`, `replay_late`,
  `empty_frame`, `read_failed`, `gate_no_change`, `gate_cooldown`), `frame_id`, host times
- `power.csv`: one row per sensor value on the shared host clock, with
  `source` = `windows_battery` (stored energy and discharge power, the
  qualified whole-laptop source) or `sysfs`. Unavailable readings are
  `valid=false` with an empty `value`, never `0`
- `manifest.json`: policy, config, source metadata (backend, requested vs
  observed size/fps, time method), AC/battery state at start and end, source
  end reason, run end reason, counts, platform

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
from capture import ReplaySource, WebcamSource

with ReplaySource("clip.mp4") as source:          # or WebcamSource(0)
    for frame in source:                          # frame.image is HxWx3 uint8 BGR
        print(frame.frame_id, frame.source_time_s, frame.host_capture_s)
print(source.end.reason)       # eof | incomplete_source | decode_failures | disconnected | stopped | ...
print(source.info.as_dict())   # backend, requested vs observed settings, drop counts
```

Opening fails with `SourceOpenError` (missing file, undecodable video, no
camera / permission). The capture is released on every exit path, including
Ctrl-C, and can be reopened.
