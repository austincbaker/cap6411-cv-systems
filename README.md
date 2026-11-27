# Always-on VLM assistant — CAP6411

An always-on webcam assistant that sends frames to a compact local vision-language model
(SmolVLM2-500M on a llama.cpp server) and uses a cheap change gate to decide which frames
are worth asking about. The task is recognizing two hand gestures from a fixed camera,
thumbs-up (`thumbs_up`) and peace sign (`peace_sign`); other motion is a negative. The
question is how many model calls, and how much battery, the gate saves against asking every
2 s, and what that costs in missed or late gestures.

What is built:

- **Inference and telemetry:** a persistent local llama-server and client, and read-only
  energy telemetry (Windows battery on the WSL2 team laptop; powermetrics and battery in the
  MacBook energy suite).
- **The app** (`app/main.py`): webcam or real-time video replay, one VLM call in flight at a
  time, and four policies: fixed interval, change gate, idle (gate only) and an energy-budget
  controller that keeps VLM energy within a set number of Wh per hour.
- **Answers and scene state:** every call asks the same gesture question under a JSON schema;
  answers are validated, and gesture onsets and offsets are derived from them the same way for
  every policy.
- **Run files and evaluation:** a versioned run-file contract with a checker, the pilot
  replay and scoring scripts, and the MacBook energy suite.

Not built before submission: a one-to-one event scorer with precision and recall, a
full dataset with held-out splits, and repeated energy trials on the team laptop. The
[implementation plans](energy-aware-vlm-implementation/README.md) track each piece as a
numbered work item (`1a` to `4g`) with its GitHub issue.

| Path | What |
|---|---|
| `app/` | the application and gesture scene state |
| `src/` | `vlm` (client, prompts), `energy` (telemetry), `capture` (webcam, replay), `gates` (change gate), `budget` (energy-budget controller), `contracts` (run-file checker) |
| `scripts/` | model server setup, pilot replay and scoring, gate tuning tools, energy suite and analysis |
| `configs/` | pinned inference profile, energy suite matrix, budget cost table |
| `data/` | annotations and the data protocol (videos stay local) |
| `docs/` | [app and components](docs/app.md), [run-file contract](docs/data-contracts.md), [energy runbook](docs/energy_runbook.md), [measurement method](docs/methodology.md) |
| `tests/` | unit tests with fake servers, sensors and clocks |

## Setup

Use Ubuntu 22.04.5 LTS (WSL2 on the team laptop) or macOS on Apple silicon, Python 3.10 or
newer, Git, CMake, a C/C++ toolchain and
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

### Pilot comparison (quality and call counts)

The main comparison replays the annotated pilot clips through the app twice: fixed
sampling every 2 s, and the change gate checked every 0.5 s. Both runs ask the same
question of each frame sent and score answers against the same 14 gesture windows
(`data/annotations/pilot.csv`: 10 videos, 12 thumbs-ups and 2 peace signs, plus the
`control` clip with no events). The numbers are in [Results](#results).

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
   policy, which should match the table in [Results](#results). It builds on `scripts/gate_check.py`,
   which also checks one clip's runs at a time:

   ```bash
   grep ',thumbs_mov_1,' data/annotations/pilot.csv \
     | awk -F, 'BEGIN{print "label,onset_s,end_s"}{print $4","$5","$6}' > thumbs_mov_1.windows.csv
   uv run python scripts/gate_check.py runs/pilot/thumbs_mov_1-fixed runs/pilot/thumbs_mov_1-gated \
       --windows thumbs_mov_1.windows.csv --tolerance-s 1
   ```

Calls are serialized and a tick that arrives while a call is running is skipped, so call
counts depend on how fast the machine answers: with calls of about 2.5 s, fixed 2 s
sampling sends every other tick. Run one server and one pass at a time, and check the
median call time each run prints; a run slowed by other load (median above 5 s is
flagged) should be deleted and rerun. Scoring needs runs that log validated answers
(`gesture` in `requests.jsonl`).

### Energy comparison (MacBook energy suite)

Energy is measured with a separate one-command suite on an Apple M2 MacBook Pro, unplugged:
it replays `thumbs_mov_1` under idle (gate only, no VLM calls), fixed 2 s and gated 0.5 s,
three reps each, plus the energy-budget controller at 50%, 25% and 10% of the fixed-interval
spend (13 runs, about 2.5 hours), and records powermetrics and battery power for each run.
[docs/energy_runbook.md](docs/energy_runbook.md) has the setup, options and hand-back steps;
in short:

```bash
uv run python scripts/energy_suite.py prepare
uv run python scripts/energy_suite.py run
uv run python scripts/analyze_energy_suite.py runs/suite-YYYYMMDD-HHMM
```

## Results

Pilot comparison from a Mac mini (Apple silicon, CPU llama-server, median call about 2.5 s).
It is a functional check of quality and call counts and carries no energy claim:

| Policy | Check interval | VLM calls | Windows named (±1 s) | Windows with a call | False mentions |
|---|---|---|---|---|---|
| Fixed | 2 s | 1,348 | 9/14 | 14/14 | 246 |
| Gated | 0.5 s | 303 | 13/14 | 13/14 | 113 |

"Named" means a call on a frame inside the window (widened by 1 s each side, since the
labels run about a second off) returned that window's gesture. A false mention is a
`thumbs_up` or `peace_sign` answer outside every window. Most false mentions come from
`thumbs_mov_3` and `thumbs_mov_5`, where the model reports gestures that are not there.

Energy results come only from the MacBook energy suite above, every policy on the same
machine and settings; they go in the project report, never mixed with the Mac mini
numbers. Energy sensors stay separate: SoC package power (powermetrics) is
not whole-laptop energy.

## Tests and checks

```bash
uv run python -m pytest -q
uv run ruff check src scripts tests
uv run ruff format --check src scripts tests
```

Tests use fake HTTP services, sensors and clocks; no GPU, webcam, model download or
privileged sensor access is required. CI runs the same checks on Ubuntu 22.04 with Python
3.10. Live validation of the model and battery sensor on the team laptop is recorded in
[docs/validation-1a-1b.md](docs/validation-1a-1b.md) and
[docs/1b-battery-qualification.md](docs/1b-battery-qualification.md).

## More detail

- [docs/app.md](docs/app.md): the model server and client, telemetry, every app flag and
  policy, how the gate and its settings were chosen, the answer format, scene state, run
  files and time bases.
- [docs/data-contracts.md](docs/data-contracts.md): the run-file formats; check a run with
  `uv run contracts-check runs/<run>`.
- [data/README.md](data/README.md): gesture definitions, the clips and annotations.
- [docs/energy_runbook.md](docs/energy_runbook.md): the MacBook energy suite.
