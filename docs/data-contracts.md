# Data contracts (item 2d)

**Contract version:** `1-draft`. Fields, units and rules below are a draft for
review by James (event scoring, 3d) and Shawn (benchmarks and analysis, 3f/3g).
The version becomes `1` once both have consumed the fixtures. Any later
change that breaks a consumer bumps the version.

`src/contracts/` is the executable form of this document. The app, the event
scorer and the energy analyzer import it instead of parsing run files
themselves. If this document and the validator disagree, fix one of them in
the same change.

## General rules

- **Missing values:** `null` in JSON, an empty cell in CSV. Never `0`, `""`,
  `NaN` or a guess. A failed reading or request stays in the file, marked
  invalid or failed; it is not dropped or retried silently.
- **CSV:** UTF-8, comma-separated, header row first, `true`/`false` for
  booleans. Columns appear in the order listed below. Consumers look columns
  up by name, so extra trailing columns are allowed.
- **JSONL:** one JSON object per line. Fields not listed here may appear;
  consumers ignore them.
- **Versioning:** every record carries `schema_version`. The validator
  rejects records from another version.
- **IDs:** `run_id` is a 32-character hex UUID, the same in every file of a
  run. `request_id` comes from the VLM client. `frame_id` is the source's
  integer frame index (the decode index for replay, so it is the same on
  every replay of a file).

## Time bases

Three clocks are kept apart and never substituted for one another.

| Time base | Fields | Meaning |
|---|---|---|
| Source time | `source_time_s`, `onset_s`, `end_s`, `available_source_time_s` | Seconds from the start of the video, from the media timestamp. `null` for webcam frames, which have no media timeline. |
| Host time | every `host_*` field, `request_started_s`, `response_available_s` | `time.monotonic()` seconds in the app process. All logs of one run share it, so frames, requests and power samples line up. Not comparable across runs. |
| Wall clock | `started_wall_utc` | ISO 8601 UTC, in the manifest only, for provenance. Never used for durations. |

Frame evidence, response availability and sensor sampling are separate times:

- **Frame evidence:** `source_time_s` (replay) or `host_capture_s` (any
  source) is when the scene looked the way the model saw it.
- **Response availability:** `response_available_s` is when the answer
  existed in the app. For real-time replay the app also gives it on the
  source timeline:
  `available_source_time_s = source_time_s + (response_available_s - host_capture_s)`.
  This is the time the scorer compares with an event's onset.
- **Sensor sampling:** a power row's `host_time_s` is when the value was
  read. `host_read_start_s` is when the read began, for slow readers such as
  the Windows battery report, which runs PowerShell. The battery value itself
  only updates every 30–40 s, so it describes some earlier moment.

## Artifacts

| File | Producer | Consumers | Time base | Kind |
|---|---|---|---|---|
| `manifest.json` | app (1d, later 3c) | runner 3f, analyzer 3g, scorer 3d | host and wall | `manifest` |
| `requests.jsonl` | app | analyzer 3g | host and source | `request` |
| `drops.jsonl` | app | analyzer 3g | host | `schedule` |
| `power.csv` | app | analyzer 3g | host | `power` |
| `predictions.jsonl` | app, from the 2b event derivation | scorer 3d | source and host | `prediction` |
| `annotations.csv` | James (1e, 2e) | scorer 3d | source | `annotation` |
| `metrics.json` | scorer 3d (quality) and analyzer 3g (energy) | analyzer 3g, report | source and host | `metrics` |

The first five files are written to one run directory. `predictions.jsonl`
appears once 2b lands; until then the baseline app writes none. Annotations
live in `data/annotations/`. Metrics are written next to the run or in an
analysis output directory.

## Application run interface

The benchmark runner (3f) launches one trial with:

```bash
uv run python -m app.main --source replay --video PATH --interval-s N \
    --duration-s N --run-dir NEW_DIR --no-display [--profile configs/inference.json]
```

The README's "Capture and baseline" section lists every flag. The contract
part is:

- **Inputs:** `--profile` (inference config), `--source replay --video PATH`
  or `--source webcam --device ID`, `--run-dir` (output directory).
- **Output directory:** `--run-dir` must not exist or must be empty. The app
  never overwrites a previous run.
- **Manifest:** `manifest.json` is written whenever the run directory was
  created, including failed and interrupted runs. Its `exit_code` and
  `run_end_reason` match the process outcome.
- **Exit status:**

  | Code | Meaning | Manifest |
  |---|---|---|
  | `0` | Completed: end of video, `--duration-s` reached, or the user pressed q | yes, `run_end_reason` `eof`, `duration_limit` or `user_quit` |
  | `2` | Configuration error, or llama-server not reachable | **no**, the run directory is not created |
  | `2` | Source failed to open or ended in error, or the server stayed busy after a timeout | yes, for example `source_open_failed`, `disconnected` or `server_not_idle` |
  | `130` | Interrupted (Ctrl-C) | yes, `interrupted` |
  | `1` | Unexpected application error | yes, `app_error` or `capture_error`, with `error_detail` |

- **Success check:** a trial succeeded if and only if the exit code is `0`,
  `manifest.json` exists, and `contracts-check RUN_DIR` reports no issues.
- **stdout:** the last line is `run_dir=... end=... exit=...` for humans.
  Runners read the manifest, not this line.

## Fields

`?` marks an optional field; *null* marks a field that is always present but
may be missing (`null` or an empty cell).

### `manifest.json` (kind `manifest`)

| Field | Type | Notes |
|---|---|---|
| `schema_version`, `run_id` | str | |
| `policy` | str | `fixed_interval` or `gated` now; later `idle`, `matched_invocation`, `budget` |
| `gate` | object, *null* | gate settings (`threshold`, `pixel_delta`, `grid`, `min_interval_s`, `refresh_s`, `width`, `height`) for `gated`; *null* otherwise |
| `run_dir` | str | |
| `argv` | list, *null* | command-line arguments |
| `config` | object | resolved app settings |
| `started_wall_utc` | str | |
| `times` | object | `host_run_start_s`, `host_tick_origin_s` (start of the measured window), `host_run_end_s` (end of the window), `observed_duration_s`; any of them *null* |
| `run_end_reason` | str | see the exit status table |
| `exit_code` | int | |
| `error_detail` | str, *null* | |
| `files` | object | artifact kind → file name in this directory |
| `power_state` | object | `at_start`, `at_end`: first and last valid battery report (`host_time_s`, `ac_online`, `battery_status`, `power_supply_status`, `remaining_mwh`, `full_mwh`), or *null* if there was none |
| `source` | object | `info` (backend, `time_method`, requested and observed size/fps, `drop_counts`), `end` (`reason`, `detail`, `complete`) |
| `vlm` | object | client `config`, `max_tokens`, llama-server `server_properties` |
| `telemetry` | object | `enabled`, plus intervals and the sensor inventory when enabled |
| `counts` | object | `requests`, `status:<status>`, each skip reason, `frames_delivered`, `power_samples` |
| `platform` | object | OS, kernel release (shows WSL2), machine, Python and library versions |

### `requests.jsonl` (kind `request`)

One line per VLM request the app sent, including failed and abandoned ones.

| Field | Type | Notes |
|---|---|---|
| `schema_version`, `run_id` | str | |
| `request_id` | str, *null* | *null* only when the client raised before creating a request, or the request was abandoned |
| `tick_index` | int | scheduling tick that sent it |
| `frame_id` | int | |
| `source_kind` | str | `replay` or `webcam` |
| `source_time_s` | float, *null* | frame evidence (source time) |
| `host_capture_s`, `host_tick_s`, `request_started_s` | float | host time |
| `response_available_s` | float, *null* | host time; *null* only for `abandoned_at_shutdown` |
| `status` | str | `ok`, `timeout`, `connection_error`, `transport_error`, `http_error`, `invalid_response`, `empty_response`, `client_exception`, `abandoned_at_shutdown` |
| `text` | str, *null* | nonempty when `status` is `ok` |
| `error` | str, *null* | required when `status` is not `ok` |
| `server_state_unknown` | bool | true when the server may still be working on it |
| `gate_reason`? `gate_score`? `gate_global_score`? `gate_compute_s`? | | `gated` runs: why the gate sent it (`gate_initial`, `gate_change`, `gate_refresh`) and its score |
| `elapsed_s`? `model`? `max_output_tokens`? `prompt_tokens`? `output_tokens`? `cached_tokens`? `finish_reason`? `http_status`? `encode_s`? `image_bytes`? | | client statistics; *null* when the server did not report them |

### `drops.jsonl` (kind `schedule`)

Every tick that did not send a request and every frame the source dropped.

| Field | Type | Notes |
|---|---|---|
| `schema_version`, `run_id` | str | |
| `origin` | str | `app` (scheduler), `source` (capture) or `gate` (change gate, 2a) |
| `reason` | str | `tick_skipped_busy`, `tick_skipped_server_unknown`, `replay_late`, `empty_frame`, `read_failed`; origin `gate`: `gate_no_change`, `gate_cooldown` |
| `frame_id` | int, *null* | |
| `host_time_s` | float | when it was logged |
| `tick_index`? `host_tick_s`? `source_time_s`? `in_flight_frame_id`? `detail`? | | |
| `gate_score`? `gate_global_score`? `gate_compute_s`? | float, *null* | gate skips: most-changed cell and global changed fractions, scoring time |

### `power.csv` (kind `power`)

One row per sensor value. A Windows battery report produces two rows (stored
energy and discharge power) with the same times.

| Column | Type | Notes |
|---|---|---|
| `schema_version`, `run_id` | str | |
| `source` | str | `windows_battery` (the qualified source), `sysfs`, or `telemetry_error` (a reader crashed) |
| `sensor_id` | str | for example `windows:aggregate:remaining_capacity`, `battery:BAT1:energy_now` |
| `domain` | str | `whole_laptop_battery` (Windows report); sysfs uses `cpu_package`, `powercap_zone`, `battery_stored_energy`, `battery_flow` |
| `quantity` | str | `stored_energy`, `discharge_power`, `energy_counter`, `power` |
| `host_read_start_s` | float, *null* | |
| `host_time_s` | float | |
| `raw_value`, `raw_unit` | *null* | value as the sensor reported it (mWh, mW, uJ, uWh) |
| `value`, `unit` | *null* | converted to J or W; empty when `valid` is false |
| `valid` | bool | |
| `error` | str, *null* | required when `valid` is false |
| `ac_online` | bool, *null* | |
| `battery_status` | str, *null* | for example `Discharging`, `Idle`, `Charging` |
| `quality_flags` | str, *null* | `;`-separated, for example `not_verified_discharging`, `wsl_host_validation_required` |

Domains are never combined. Only `whole_laptop_battery` rows from
`windows_battery` count as measured energy on the WSL2 platform. The sysfs
battery rows are kept for diagnosis; item 1b found their scale unreliable
under WSL2.

### `annotations.csv` (kind `annotation`)

| Column | Type | Notes |
|---|---|---|
| `schema_version` | str | |
| `video_id` | str | stem of the replayed file name (`pilot-desk-01` for `.../pilot-desk-01.mp4`) |
| `event_id` | str | unique within the video |
| `label` | str | from the event vocabulary, **provisional** until 1e: `person_enters`, `person_leaves`, `object_placed`, `object_removed` |
| `onset_s` | float | source time when the event first becomes visible |
| `end_s` | float, *null* | empty for an instantaneous event |
| `group_id` | str | session or environment, for grouped splits (2e) |
| `split` | str, *null* | `dev`, `validation` or `test` |
| `annotator`, `notes` | str, *null* | |

### `predictions.jsonl` (kind `prediction`)

Predicted events from the shared 2b derivation: validated observations (2c)
differenced against the confirmed scene state. Model text alone is never a
prediction.

| Field | Type | Notes |
|---|---|---|
| `schema_version`, `run_id`, `prediction_id` | str | |
| `label` | str | normalized to the vocabulary; out-of-vocabulary labels are kept and scored as errors |
| `request_id`, `frame_id` | str, int | the request whose response produced it; must exist in `requests.jsonl` |
| `source_time_s` | float, *null* | frame evidence |
| `host_capture_s`, `response_available_s` | float | host time |
| `available_source_time_s` | float, *null* | see "Time bases"; *null* exactly when `source_time_s` is |
| `observation`? | any | the validated observation behind it (format set in 2c) |

### `metrics.json` (kind `metrics`)

One report per run and video, so the analyzer can join it with energy by
`run_id`.

| Field | Type | Notes |
|---|---|---|
| `schema_version`, `run_id` | str | |
| `video_id` | str, *null* | |
| `scorer` | object | `name`, `version` |
| `matching` | object | the parameters used (see "Event matching") |
| `counts` | object | `events`, `predictions`, `true_positives`, `false_positives`, `false_negatives` (required); `duplicates`, `late`, `unmatched_predictions`, `out_of_vocabulary` |
| `precision`, `recall`, `f1` | float, *null* | *null* when undefined (no predictions, or no events) |
| `delay_s` | object | `n`, `mean`, `median`, `max` over true positives; *null* when `n` is 0 |
| `matches` | list | one entry per outcome: `event_id`, `prediction_id`, `outcome`, `delay_s` |
| `energy` | list | one entry per domain: `domain`, `source`, `energy_j` **or** `unavailable_reason`, `sample_span_s`, `mean_power_w`, `samples_used`, `samples_invalid`, `measured_window_s` |
| `errors` | list | `{code, count?, detail?}`, for example `failed_requests`, `out_of_vocabulary`, `incomplete_at_horizon` |

## Event matching (draft for 3d)

Parameters are provisional. Item 3h freezes them on validation data.

| Parameter | Draft value |
|---|---|
| `evidence_tolerance_s` | 1.0 |
| `horizon_s` | 10.0 |
| label normalization | lowercase, spaces and hyphens to underscores |

1. Use only annotations whose `video_id` matches the run's replayed file.
2. A prediction is **eligible** for an event when the labels are equal after
   normalization and `onset_s − tol ≤ source_time_s ≤ (end_s or onset_s) + tol`.
3. An eligible prediction is **on time** when
   `available_source_time_s ≤ onset_s + horizon_s`.
4. Take events in onset order. Each event matches the on-time eligible
   prediction with the smallest `available_source_time_s` that is still
   unmatched; ties go to the smaller `prediction_id`. Each event and each
   prediction takes part in at most one match.
5. Outcomes:
   - matched → `true_positive`, with `delay_s = available_source_time_s − onset_s`
   - unmatched event → `false_negative`
   - unmatched prediction that was eligible for an event matched by another
     prediction → `duplicate`
   - unmatched prediction that was eligible but not on time → `late`
   - any other unmatched prediction → `unmatched_prediction`

   All three unmatched-prediction outcomes are false positives.
6. `precision = TP / predictions` and `recall = TP / events`; *null* when
   the denominator is 0.
7. Webcam runs have no source time and are not scored for event quality.

## Energy (draft for 3g)

For the `whole_laptop_battery` domain:

1. The measured window is `[times.host_tick_origin_s, times.host_run_end_s]`.
2. Take the `windows_battery` `stored_energy` rows whose `host_time_s` falls
   inside the window. Invalid rows are counted in `samples_invalid` and
   otherwise ignored.
3. If any valid row has `ac_online` other than `false`, or `battery_status`
   other than `Discharging`, the energy is unavailable: `not_on_battery`.
   With fewer than two valid rows it is `insufficient_samples`.
4. `energy_j` = first valid value − last valid value;
   `sample_span_s` = their `host_time_s` difference;
   `mean_power_w = energy_j / sample_span_s`. A negative difference is
   `energy_increased` (unavailable).
5. The report coarseness (updates every 30–40 s) means a run's energy is
   uncertain by about one update period's worth of drain. Use long windows
   and repeated trials, and do not attribute battery energy to single
   requests.

`cpu_package` is reported as unavailable (`no_package_counter`) on WSL2, which
exposes no RAPL counter. Idle and workload energy are compared or subtracted
only within the same domain and under the same conditions.

## Validator

```bash
uv run contracts-check runs/<run>                         # a run directory
uv run contracts-check --kind annotation data/annotations/pilot.csv
```

It prints one line per issue and exits `1` if there are any. In Python:

```python
from contracts import read_artifact, validate_run_dir

rows, issues = read_artifact("power", run_dir / "power.csv")  # typed rows; CSV missing → None
issues = validate_run_dir(run_dir)  # also checks run_id across files and prediction → request links
```

## Fixtures

`tests/fixtures/contracts/` holds one synthetic replay run with numbers chosen
to be checked by hand. `tests/test_contracts.py` validates every file and
recomputes the expected values.

- `run_valid/`: a 60 s replay of `pilot-desk-01` at 2 s intervals.
  - 30 ticks: 22 requests (21 `ok`, 1 `timeout` with unknown server state),
    7 busy skips, 1 server-unknown skip.
  - 1 late replay frame.
  - 5 predictions.
  - Battery reports every 10 s, one of which failed.
- `annotations.csv`: three events in `pilot-desk-01`, plus one in another
  video that must be ignored.
- `expected_metrics.json`: the hand-scored result.

  | Prediction | Label | Evidence (s) | Available (s) | Outcome |
  |---|---|---|---|---|
  | P1 | person_enters | 10.0 | 11.8 | TP for E1 (onset 10.0), delay 1.8 |
  | P2 | person_enters | 12.0 | 13.7 | duplicate of E1 |
  | P3 | object_placed | 24.0 | 35.5 | late for E2 (35.5 > 25.0 + 10) |
  | P4 | object_removed | 38.0 | 39.7 | unmatched |
  | P5 | person_leaves | 50.0 | 51.6 | TP for E3 (onset 50.0), delay 1.6 |

  This gives TP 2, FP 3, FN 1 (E2), precision 2/5 = 0.4, recall 2/3,
  F1 0.5 and mean delay 1.7 s.

  Battery: 50000 mWh at 1000.2 s and 49740 mWh at 1060.2 s are
  180000.0 J and 179064.0 J, so 936.0 J over 60.0 s, or 15.6 W. Six
  valid samples are used and one is invalid. Package energy is unavailable.
- `power_ac_online.csv` with `expected_metrics_ac_online.json`: the same run
  plugged in, so battery energy is `not_on_battery`.
- `invalid/`: one file per failure kind:
  - wrong version and missing manifest field
  - `ok` with empty text, missing field, failure without an error, wrong type
  - `0` written for a missing power value
  - end before onset, unknown label, unknown split
  - availability before evidence
  - negative count, out-of-range precision, energy given both a value and a reason

## Open items

- **1e (James):** the event vocabulary and the onset/end rules. The labels
  above are placeholders.
- **2c (Austin):** the structured observation format behind `observation`.
- **2b (Alejandro):** the event derivation that writes `predictions.jsonl`.
- **2a (Alejandro):** gate decision reasons in `drops.jsonl` (`origin: gate`).
- **3h:** freeze `evidence_tolerance_s`, `horizon_s` and label
  normalization.
- **Review:** James and Shawn confirm that their tools can read the fixtures.
  The version then becomes `1`.
