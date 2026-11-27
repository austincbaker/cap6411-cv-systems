# Energy suite runbook (Apple silicon MacBook)

How to run the unattended energy and quality suite on an Apple M2 MacBook Pro (plan
revision 10) and hand the results back. One command runs the whole matrix; it needs the
sudo password once, at the start, for `powermetrics`.

## What it measures

Every run replays one clip in real time through the app (`python -m app.main`) under one
condition, with its own freshly started and warmed-up llama-server, and records:

| File in the run folder | What | Domain |
|---|---|---|
| `powermetrics.csv` | CPU, GPU, ANE and combined power every 1 s | SoC package (not the whole laptop) |
| `battery.csv` | battery charge, voltage, current, AC state every 10 s | whole laptop, only while unplugged |
| `battery.csv` (SMC columns) | system load and its per-second accumulator, published about once a minute | whole laptop, on AC or battery |
| `server_rss.csv` | llama-server resident memory every 1 s | server process |
| `app/` | the app's run files: `requests.jsonl` (per-call latency), `drops.jsonl`, `manifest.json`, ... | |
| `suite_run.json` | condition, server command, power source, Low Power Mode, display brightness, Wi-Fi and machine before and after, energy totals, latency, gate_check scores (±1 s) | |

The default matrix, in `configs/energy_suite.json`, is three conditions × 3 reps on
`thumbs_mov_1` (James's `real_thumbs_1`, 9.7 min, two annotated thumbs-ups). Reps are
interleaved and the order rotates each rep:

| Condition | Policy | Check / call interval |
|---|---|---|
| `idle` | gate runs on every tick, no VLM calls (`--policy idle`) | 0.5 s |
| `fixed_2s` | a VLM call every tick | 2 s |
| `gated_0.5s` | a VLM call only when the change gate triggers (default gate settings) | 0.5 s |

`idle` is the base cost (camera replay, gate and an idle loaded server); the analysis
subtracts it to get incremental energy per call.

## Runtime

Each run takes the clip length (585 s) plus about 20 s for server start and warm-up plus a
90 s cooldown, about 11.6 min. `run --dry-run` prints the same plan for the current config.

| Block | Default | Runs | Time | What it varies |
|---|---|---|---|---|
| main matrix | on | 9 | ~1 h 44 min | idle vs fixed 2 s vs gated 0.5 s, 3 reps |
| `gate_sweep` | off | 6 | ~1 h 09 min | gate threshold 0.1 / 0.2 / 0.3 × check interval 0.5 / 1 s (3 persistence checks), 1 rep |
| `image` | off | 4 | ~46 min | sent frame 384 / 768 px longer side × 64 / 32 max output tokens, fixed 2 s, 1 rep |
| `quantization` | off | 2 | ~23 min | Q4_K_M model for fixed 2 s and gated 0.5 s (the main matrix is the Q8_0 side), 1 rep |
| `budget` | on | 4 | ~46 min | energy-budget controller at 50%, 25% and 10% of the fixed 2 s spend, 0.5 s checks, plus one fixed 2 s run at 384 px to calibrate the reduced size (3 runs, ~35 min, when `image` is on) |
| all blocks | | 24 | ~4 h 38 min | |

The default suite (main matrix plus `budget`) is 13 runs, ~2 h 31 min. Turn a block on or off
by setting its `"enabled"` in `configs/energy_suite.json`. The gate
defaults were tuned for 0.5 s checks, so 1 s rows in the gate sweep are expected to call less
and may miss gestures. The main matrix runs first, then the budget block; if the battery
reaches the 20% floor before the end, charge and `--resume` (see below). Run other optional
blocks on a later charge.

## One-time setup (fresh clone)

1. Command Line Tools, cmake and uv (skip what you have):

   ```bash
   xcode-select --install
   brew install cmake uv
   ```

2. Clone and install:

   ```bash
   git clone https://github.com/austincbaker/cap6411-cv-systems.git
   cd cap6411-cv-systems
   git checkout energy-suite-macos   # until it is merged; then stay on main
   uv sync --extra dev
   ```

3. Build llama.cpp with Metal and get the models (about 5 min plus downloads of about
   1.4 GB). It builds the pinned llama.cpp revision from `configs/inference.json` into
   `.cache/energy-suite/`, downloads the pinned SmolVLM2-500M Q8_0 model and projector and the
   f16 weights into `models/`, checks every SHA-256, and quantizes the f16 weights to Q4_K_M
   for the quantization block:

   ```bash
   uv run python scripts/energy_suite.py prepare
   ```

4. Get the clip. From the team Google Drive folder **CVSystems Project**, download
   `thumbs_mov_1.mov` (773 MB) into `data/videos/` (git-ignored; never commit footage):

   ```bash
   mkdir -p data/videos
   mv ~/Downloads/thumbs_mov_1.mov data/videos/
   ls -l data/videos/thumbs_mov_1.mov   # 773222336 bytes
   ```

5. Smoke test, plugged in (about 5 min; asks for the sudo password):

   ```bash
   uv run python scripts/energy_suite.py run --allow-ac --only fixed_2s \
     --duration-s 60 --cooldown-s 5 --name smoke
   uv run python scripts/analyze_energy_suite.py runs/smoke-*
   ```

   Expect three runs with about 30 calls each, a package power in watts, and the three
   figures under `runs/smoke-*/analysis/`. Battery energy is empty while plugged in; that is
   correct.

## Pre-run checklist

- Charge to 100%, then **unplug**. The suite refuses to start on AC unless `--allow-ac`
  is given, and stops before a run when the battery is below 20%
  (`battery_floor_percent`).
- **Brightness fixed:** System Settings > Displays: turn off "Automatically adjust
  brightness" and True Tone, set a brightness and leave it (for example 50%). The run
  records the value.
- **Low Power Mode off** (System Settings > Battery); the run records it either way.
- **Quit other apps:** browsers, Slack, Discord, Docker/OrbStack, Dropbox; pause iCloud
  sync; turn on Do Not Disturb. Wait for Spotlight indexing to finish after a big download.
- **Wi-Fi and Bluetooth:** after setup the suite needs no network. Turn Wi-Fi and Bluetooth
  off and keep them off for the whole suite (Wi-Fi state is recorded).
- Lid open, on a hard surface, at room temperature; don't use the laptop while it runs.
  The suite runs `caffeinate`, so the laptop and display stay awake.
- No other llama-server running (`pgrep -fl llama-server` prints nothing).

## The one command

```bash
uv run python scripts/energy_suite.py run
```

It prints the plan and estimated time, asks for your password once (`sudo -v`; nothing is
stored and no sudoers file is changed), and then runs unattended. Results go to
`runs/suite-YYYYMMDD-HHMM/<condition>_<rep>/`. Each finished run prints one line with its
call count, median latency, package, system and battery power, and peak memory.

- **Interrupted, or stopped at the battery floor:** charge, unplug, and continue the same
  suite; finished runs are skipped and a half-finished run is kept as `<name>.failed-1`:

  ```bash
  uv run python scripts/energy_suite.py run --resume runs/suite-YYYYMMDD-HHMM
  ```

- **Only some conditions or blocks:** `--only gated_0.5s fixed_2s` or `--only gate_sweep`.

## Budget block and calibration

The `budget` block runs the app with `--policy budget`: the change gate still decides when
something changed, and the energy-budget controller (`src/budget/`) decides whether, and at
what image size, to call the VLM, so that its energy above the idle pipeline stays within a
budget in Wh per hour (one Wh per hour is one watt). It needs the main matrix's idle and
fixed 2 s runs from the same suite folder, so run it after (or together with) the main matrix.

**Calibration.** Before each budget run the suite derives the controller's cost table from the
suite's completed runs and writes `runs/suite-.../budget_costs.json`:

- for each image size, joules per call above idle = (run mean power − mean idle power) ×
  run time ÷ calls, averaged over the fixed-interval runs at that size (default output
  bound, Q8_0), in the suite's headline domain (battery when unplugged);
- the full size comes from the main matrix's `fixed_2s` runs; 384 px from the block's
  `budget_calib_px384` run, or from the `image` block's 384 px / 64-token run when that block
  is on; 768 px is added when the `image` block ran;
- each entry also keeps the median call latency, which the controller uses to rescale a call
  that ran slower than calibrated.

To recompute the table on its own (for example after a resumed suite):

```bash
uv run python scripts/energy_suite.py calibrate runs/suite-YYYYMMDD-HHMM
```

Without the runs to calibrate from (for example `--only budget` in a new folder), the budget
runs use the placeholder table in `configs/budget_costs.json`, and `suite_run.json` records
`costs_placeholder: true` and why. Those runs are functional checks, not results.

**Budgets.** `fractions_of_fixed` (default 0.5, 0.25, 0.1) are fractions of the calibrated
fixed 2 s spend (full-size joules per call ÷ 2 s). They bracket the gated policy, which made
about a fifth of the fixed policy's calls in the Mac mini pilot. For fixed values, list them in
`budget_wh_per_hour` instead (or as well); each becomes a `budget_wh<value>` run.

On a tight budget, a tick where the gate fires but the bucket is short is logged as
`budget_deferred`; the change is kept and sent (at 768 or 384 px if only those fit) as soon as
the bucket refills, and dropped only if it waits more than 10 s with no newer trigger. Every
tick's decision, bucket level and estimated spend are in each run's `app/budget.jsonl`.

## Analysis

```bash
uv run python scripts/analyze_energy_suite.py runs/suite-YYYYMMDD-HHMM
```

Writes into `runs/suite-.../analysis/`:

- `runs.csv`: one row per run: energy per hour in each domain, calls per hour, median and
  p90 latency, peak server memory, incremental power and energy per call over idle,
  annotated gestures caught and named (gate_check at ±1 s), outside calls, power source,
  Low Power Mode, brightness and thermal pressure.
- `conditions.csv`: per condition, mean, standard deviation, min and max across reps.
- `quality_vs_energy.png`, `energy_per_hour.png`, `calls_latency.png`.
- With the budget block: `budget.csv` (per budget run: the budget, measured VLM energy above
  idle and its ratio to the budget, the controller's estimated spend, calls, admit full /
  reduced / defer / drop counts, gestures named at ±1 s), `budget.png` (measured energy vs
  budget with the fixed and gated levels, and quality vs budget) and `budget_spend.png`
  (estimated spend against the allowance over each run).

The figures use one headline energy domain for the whole suite: battery V x I when every
run has it (unplugged), else SMC system load, else powermetrics package; `headline_domain`
in the CSVs names it. Domains are never mixed or relabelled.

## Hand the results back

Zip the suite folder (no video is in it; `requests.jsonl` holds the model's answers, not
images) and upload it to the Drive folder **CVSystems Project**:

```bash
cd runs && zip -r suite-YYYYMMDD-HHMM.zip suite-YYYYMMDD-HHMM && cd ..
```

Do not commit `runs/`.

## Troubleshooting

- `port 8080 is busy`: another llama-server is running. Stop it if it is yours
  (`pkill -f llama-server`), then `--resume`.
- `powermetrics does not work here`: the suite first tries CPU, GPU, ANE and thermal
  samplers and falls back to CPU and GPU only; the error lists both attempts.
- A run that failed has `error.txt`, `llama-server.log` and `app.log` in its folder; the
  suite moves on to the next run.
- `display_brightness` may read as missing on some macOS versions (it uses the private
  DisplayServices framework); write the value you set in the suite notes instead.
- The SMC system-load figure updates about once a minute, so it covers about 8 of the
  9.7 minutes of each run; battery current is read every 10 s. Server memory is resident
  memory from `ps`; Metal buffers in unified memory may not all show there.
