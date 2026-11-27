# Always-on VLM assistant — CAP6411

An always-on webcam assistant that sends frames to a compact local vision-language model
(SmolVLM2 on a CPU llama.cpp server) and uses a cheap change gate to decide which frames are
worth asking about. Implemented here: local inference, read-only energy telemetry, webcam and
replay capture, the fixed-interval and gated application, validated gesture answers, gesture
scene state, the run-file contract and the pilot evaluation scripts. Energy-budget admission
(3a/3c), the event scorer (3d/3e) and the team-laptop energy trials are not implemented.
To rerun the pilot comparison, see "Reproduce the main numbers" below.

## Selected task and evaluation readiness

The primary application recognizes **thumbs-up (`thumbs_up`) and peace-sign
(`peace_sign`) hand gestures** from a fixed camera. Other motion and neither
gesture are negatives. This supersedes the original object-change default;
see master-plan revision 9 and [the data protocol](data/README.md).

PR #41 supplies a pilot with 16 events in 10 annotated videos, one session group
and no assigned splits, plus a documented control clip. Pilot replay and gate
checks can run now. Complete scored comparisons still require:

- **3d / #16 and 3e / #17 (James):** one-to-one matching and scoring CLI.
- **2e / #11 (James):** full dataset, grouped splits and annotation review before
  the 3h evaluation freeze and held-out trials.

The app asks every frame the gesture question, validates each answer and derives
gesture onsets and offsets from the validated answers with one rule set for every
policy (2b), written to `predictions.jsonl`. Gate-window coverage measures whether a frame was sampled; it does not establish
precision, recall, F1 or response-available delay.

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

## Reproduce the main numbers

The main comparison replays the annotated pilot clips through the app twice: fixed
sampling every 2 s, and the change gate checked every 0.5 s. Both runs ask the same
question of each frame sent and score answers against the same 14 gesture windows
(`data/annotations/pilot.csv`: 10 videos, 12 thumbs-ups and 2 peace signs, plus the
`control` clip with no events). These numbers come from a Mac mini (Apple silicon, CPU
llama-server, median call about 2.5 s). They are a functional check of quality and call
counts, and they carry no energy claim:

| Policy | Check interval | VLM calls | Windows named (±1 s) | Windows with a call | False mentions |
|---|---|---|---|---|---|
| Fixed | 2 s | 1,348 | 10/14 | 14/14 | 245 |
| Gated | 0.5 s | 303 | 14/14 | 14/14 | 112 |

"Named" means a call on a frame inside the window (widened by 1 s each side, since the
labels run about a second off) returned that window's gesture. A false mention is a
`thumbs_up` or `peace_sign` answer outside every window. Most false mentions come from
`thumbs_mov_3` and `thumbs_mov_5`, where the model reports gestures that are not there.

1. **Set up** as in [Setup](#setup): `uv sync --extra dev`, then
   `uv run python scripts/llama_runtime.py prepare`.
2. **Get the clips.** The videos are personal data and are not in git. Download them from
   the team Drive folder linked in [data/README.md](data/README.md) into `data/videos/`
   (git-ignored), named by `video_id`: `recording_1_thumbs.mov` to `recording_4_peace.mov`,
   `control.mov` and `thumbs_mov_1.mov` to `thumbs_mov_5.mov`. `thumbs_mov_6` is left out:
   the Drive copy is the same file as `thumbs_mov_3`.
3. **Start one model server** in its own terminal and leave it running:

   ```bash
   uv run python scripts/llama_runtime.py serve
   ```

4. **Replay the clips**, one policy after the other (each pass replays about 1.5 hours of
   video in real time):

   ```bash
   uv run python scripts/run_pilot_eval.py --policy fixed --interval-s 2 --out runs/pilot
   uv run python scripts/run_pilot_eval.py --policy gated --interval-s 0.5 --out runs/pilot
   ```

   Each clip becomes `runs/pilot/<video_id>-<policy>/`, with its log in `runs/pilot/logs/`.
   A run that already has a manifest is skipped, so an interrupted pass resumes where it
   stopped. `--interval-s` is required: the gate's defaults are tuned for 0.5 s checks,
   while the app's own default is 2 s. Use `--clips recording_1_thumbs --duration-s 15`
   for a quick check.

5. **Score** every run against the annotations:

   ```bash
   uv run python scripts/score_pilot_eval.py runs/pilot
   ```

   This writes `runs/pilot/quality.csv` (one row per run) and prints the totals per
   policy, which should match the table above. To draw the report's three figures from
   the pass (the defaults read and overwrite the committed files under `docs/report/`):

   ```bash
   uv run python scripts/report_figures.py --scores runs/pilot/quality.csv \
       --export-timeline runs/pilot --timeline runs/pilot/timeline.csv --out runs/pilot/figures
   ```

   Scoring builds on `scripts/gate_check.py`, which also checks one clip's runs at a time:

   ```bash
   grep ',thumbs_mov_1,' data/annotations/pilot.csv \
     | awk -F, 'BEGIN{print "label,onset_s,end_s"}{print $4","$5","$6}' > thumbs_mov_1.windows.csv
   uv run python scripts/gate_check.py runs/pilot/thumbs_mov_1-fixed runs/pilot/thumbs_mov_1-gated \
       --windows thumbs_mov_1.windows.csv --tolerance-s 1 \
       --name thumbs_up=thumb --name peace_sign="peace|v-sign|victory"
   ```

Calls are serialized and a tick that arrives while a call is running is skipped, so call
counts depend on how fast the machine answers: with calls of about 2.5 s, fixed 2 s
sampling sends every other tick. Run one server and one pass at a time, and check the
median call time each run prints; a run slowed by other load (median above 5 s is
flagged) should be deleted and rerun. Scoring needs runs that log validated answers
(`gesture` in `requests.jsonl`, item 2c).

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

`response_format=` passes a structured-output request through unchanged, such as the
gesture schema below; the answer text comes back unparsed.

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
tasks and their GitHub issues.

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
| `--image-max-side N` | source size | shrink each sent frame to at most N pixels on its longer side (the gate still sees the full frame) |
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
    --interval-s 0.5 --no-display
```

Each frame is compared with the last frame sent to the VLM (the acknowledged
reference), so a slow change keeps growing until it triggers. Frames are
shrunk to 160x120 gray, blurred and mean-subtracted (a uniform lighting shift
is not change). A pixel counts as changed when it moved more than
`--gate-pixel-delta` (default 25 of 255); the score is the changed fraction of
the most-changed cell in a `--gate-grid` x `--gate-grid` grid (default 4;
1 is a global score). A change starts when the score reaches `--gate-threshold`
(default 0.3) and must last `--gate-persist-checks` checks in a row (default 3,
so 1 s at 0.5 s checks) before it is sent, so a movement that comes and goes,
like a head turn, is skipped and the frame sent shows the change once it has
settled. `--gate-release-threshold` (off by default) adds hysteresis: a started
change stays alive while the score is at least that value. Per tick, in order:

| Reason | Logged in | When |
|---|---|---|
| `tick_skipped_busy`, `tick_skipped_server_unknown` | `drops.jsonl`, origin `app` | as in fixed-interval runs; checked first |
| `gate_initial` | `requests.jsonl` | first frame, no reference yet |
| `gate_refresh` | `requests.jsonl` | `--gate-refresh-s` passed since the last call (off by default) |
| `gate_no_change` | `drops.jsonl`, origin `gate` | score below `--gate-threshold` (below `--gate-release-threshold` once a change has started) |
| `gate_persisting` | `drops.jsonl`, origin `gate` | changed for fewer than `--gate-persist-checks` checks in a row |
| `gate_cooldown` | `drops.jsonl`, origin `gate` | changed long enough, but within `--gate-min-interval-s` (default 2) of the last call |
| `gate_change` | `requests.jsonl` | otherwise |

Gate skips carry `gate_score`, `gate_global_score` and `gate_compute_s` (time
spent scoring, for gate-overhead accounting); sent requests carry the same
fields plus `gate_reason`. The manifest records `policy` and the `gate`
settings, and `counts` has one entry per reason.

`--policy idle` runs the same gate on every tick but never sends a request: each tick is
logged as `idle_no_call` with the gate's verdict in `detail`. It measures the pipeline's
base cost (capture, gate and an idle server) for energy comparisons; see
`docs/energy_runbook.md`.

`--policy budget --budget-wh-per-hour X --interval-s 0.5` keeps the VLM's energy above that
base cost within X Wh per hour. The gate still decides when something changed; a token-bucket
controller (`src/budget/`) decides whether to call, and at what image size, using the cost
table in `--budget-costs` (default `configs/budget_costs.json`, a placeholder until the energy
suite writes a measured one). A change it cannot afford yet is kept and sent once the bucket
refills. Every tick's decision, bucket level and estimated spend go to `budget.jsonl`; see
`docs/energy_runbook.md` for calibration and the suite's budget block.

#### Choosing the gate settings

The defaults were chosen on development clips only: James's `real_thumbs_1`
(9.7 min, two thumbs-ups; `thumbs_mov_1` in `data/annotations/pilot.csv`) and his
four short gesture clips plus a control. `real_thumbs_2` (8.8 min, `thumbs_mov_2`;
one thumbs-up was annotated when it was checked) was held out and checked
once with the chosen setting. On `real_thumbs_1`, ordinary movement scores
0.02 (median) to 0.40 (99th percentile) and a thumbs-up peaks at 0.68 to
0.75. The old default (threshold 0.05, no persistence) fired on head movement
and made more calls than fixed 2 s sampling. Threshold 0.3 with 3 checks
caught every gesture with 82% fewer calls than fixed sampling on
`real_thumbs_1`; 0.4 cut calls further but leaves less margin under the
gestures' scores. Hysteresis only added calls on these clips, so it is off.
These settings were developed for gesture clips. Object events are outside the
primary study; these checks do not establish object-event performance.

| Clip (role) | Fixed 2 s calls | Gated calls | Gestures caught (fixed, gated) |
|---|---|---|---|
| `real_thumbs_1` (development) | 147 | 27 | 2/2, 2/2 |
| `real_thumbs_2` (held out) | 133 | 28 | 1/1, 1/1 |
| Jester thumbs-up replay, 60 s | 15 | 8 | 3/4, 4/4 |

These come from `scripts/gate_sweep.py`, which decodes a clip once, samples the
newest frame at every 0.5 s tick, runs the real gate for each setting and
models inference as a fixed 2.5 s busy time (the Mac mini measured 2.5 to
2.7 s per call):

```bash
uv run python scripts/gate_sweep.py clip.mov --windows clip.windows.csv \
    --tolerance-s 0.5 --thresholds 0.1,0.2,0.3,0.4 --persist 1,2,3,4
```

Retune on development clips if the check interval, camera or scenes change,
and record the clips used here.

#### Checking the gate on gesture clips

`scripts/gate_check.py` compares runs over the same clip against annotated
windows (a CSV of `label,onset_s,end_s` in source seconds): how many calls each
run made, which windows got a call on a frame inside them and how long after
onset, whether that answer names the gesture, and how many calls landed outside
every window. It reads requests, not predictions, so it is a gate tuning aid,
not the item 3d event scorer.

```bash
uv run python scripts/gate_check.py runs/<fixed-run> runs/<gated-run> \
    --windows clip.windows.csv --tolerance-s 0.5
```

A Jester clip is 3 s of one gesture with nothing for a gate to skip.
`uv run python scripts/jester_replay.py FRAMES_ROOT replay.avi` builds a replay
(default 4 clips in 15 s segments at 12 fps) that holds each clip's first frame,
then plays the clip, and writes `replay.windows.csv` next to it; `--clip-ids`
rebuilds a given replay. The held stretch is a frozen frame and the cut into
each clip is a scene change the gate should catch, so treat it as a functional
check. Keep the frames, recordings and outputs local.

### Gesture answers (item 2c)

Every request asks one question about the frame (`--prompt`, default "Describe
what the person's hands are doing in a few words, then say whether the person is
making a thumbs up, a peace sign, or neither (none).") and sends the JSON schema
in `src/vlm/prompts.py` as `response_format`. llama-server turns the schema into
a grammar, so the model can only answer an object with a short `hands`
description (at most 80 characters) followed by `gesture`, which is exactly
`thumbs_up`, `peace_sign` or `none`:

```json
{"hands": "thumb up", "gesture": "thumbs_up"}
```

`none` is a valid negative. Only `gesture` is the observation; `hands` is there
because the model writes it before it picks: asked for `gesture` alone,
SmolVLM2 answers `thumbs_up` for every frame. On the Mac mini an answer is
about 24 output tokens and a call takes about 2.5 s.

The app validates every `ok` answer exactly (`vlm.prompts.parse_gesture_answer`,
no normalizing) and writes the result next to the raw `text` in
`requests.jsonl`: `gesture`, or `answer_error` (`truncated`, `not_json`,
`not_object`, `missing_field`, `unexpected_fields`, `hands_not_text`,
`out_of_vocabulary`) when the answer is not a valid observation, for example
from a server that ignores `response_format`. The request `status` stays `ok`: the server did answer. An
invalid answer is unknown, never a negative: the confirmed observation keeps
the last valid answer. The manifest counts `answer:<gesture>` and
`answer_invalid:<reason>`, and records the prompt and schema under `vlm`.

`scripts/gate_check.py` matches its `--name` patterns against the validated
`gesture` for runs that log one, so an invalid answer names nothing.

### Gesture scene state (item 2b)

Every policy feeds each request's validated answer to the same `GestureScene` in
`app/state.py`, which holds the confirmed gesture (`thumbs_up`, `peace_sign` or
`none`, starting at `none`) and the answer that last changed it:

- a different valid answer changes it (after `confirm` answers in a row; the app
  uses 1). A change to a gesture writes an `onset` to `predictions.jsonl`; a
  change away from one writes an `offset` naming its onset
  (`onset_prediction_id`), and a direct switch writes both, from one answer;
- the same gesture again writes nothing, so a held gesture is one onset; after an
  answer of `none` the same gesture is a new onset;
- an unknown answer (failed request, or `answer_error`) changes nothing, so a
  gesture stays up through timeouts and bad answers; the scene counts them as
  `unknown_since_valid`.

Each prediction carries the request, frame and times it came from, and the
validated answer as `observation`. The manifest's `scene` holds the final state,
`counts` has `prediction:<transition>:<label>`, and the display shows the
confirmed gesture and the frame it changed on.

Pending work stays bounded: at most one request is in flight, the capture
thread keeps only the newest frame, and a busy tick is skipped rather than
queued, so slow inference never replays a backlog.

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
  `empty_frame`, `read_failed`, `gate_no_change`, `gate_persisting`, `gate_cooldown`), `frame_id`, host times
- `power.csv`: one row per sensor value on the shared host clock, with
  `source` = `windows_battery` (stored energy and discharge power, the
  qualified whole-laptop source) or `sysfs`. Unavailable readings are
  `valid=false` with an empty `value`, never `0`
- `requests.jsonl` also carries the validated `gesture` and `answer_error` (item 2c,
  "Gesture answers" above)
- `predictions.jsonl`: gesture onsets and offsets (item 2b) with the request, frame
  and times they came from, including `available_source_time_s`
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
