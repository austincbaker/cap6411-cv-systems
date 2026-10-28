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
