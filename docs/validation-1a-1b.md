# Implementation validation: items 1a and 1b

These are smoke checks on the WSL2 experiment platform (D11), not the final
task-quality/energy benchmark. Austin accepted both items on 2026-11-05 after
review of the existing evidence and explicitly instructed closing issues #1 and #2.
Raw image files and model weights remain local; small output/telemetry examples are
included here so Alejandro, James and Shawn can inspect the interfaces.

## Item 1a: inference and owner acceptance verified

The CPU-only build used llama.cpp commit
`620d2225cc436ab0b001e3200e590e3b286ef9ab`, SmolVLM2-500M-Video-Instruct Q8_0 and the
matching Q8_0 projector from Hugging Face revision
`ccd7aae53bcb1997355c2f094959e72b3642ce17`. Both artifact checksums matched the pinned profile.

One server process remained alive for four image requests in order: cats, room, cats,
room. The model alias and observed server build (`b1-620d222`) matched the configured
runtime. The build disabled GPU backends, startup disabled layer/projector offload, and
the server reported no usable GPU. Its process was verified alive after all four calls.

| Check | Observation |
| --- | --- |
| Generation bound | 32 tokens per request |
| Actual output lengths | 24, 18, 24, 18 tokens |
| Finish reasons | Four successful `stop` completions |
| Cached prompt tokens | 0 for all four requests |
| Mean request latency | 2.4801 seconds on this WSL2/CPU configuration |
| Persistent model/service | One PID used throughout the sequence |
| Stopped service | One `connection_error` record, unsuccessful exit, no retry |

See [inference-smoke.jsonl](examples/inference-smoke.jsonl),
[inference-server-stopped.jsonl](examples/inference-server-stopped.jsonl) and
[validation-summary.json](examples/validation-summary.json). The summary records source
image URLs and hashes. Generated descriptions are not ground-truth event annotations;
these four requests establish compatibility and fresh-image processing, not accuracy.

## Item 1b: collection and unplugged source qualification verified

The collector was exercised against real exposed sysfs attributes during a 10-second
quiet interval and a 30-second interval containing the inference sequence. This machine
is Ubuntu 22.04.5 under WSL2, with no powercap/RAPL energy counters exposed.

| Trace | Rows | Readings |
| --- | --- | --- |
| [Idle](examples/telemetry-wsl-idle.csv) | 22 | Loaded model with no requests; BAT1 stored energy and power sampled over 10 seconds |
| [Inference period](examples/telemetry-wsl-inference.csv) | 62 | Same two quantities, sampled at 0 through 30 seconds |

The battery reported `Not charging`, AC was online, stored energy remained 4.7 Wh
(16,920 J), and reported battery flow was 0 W. Both quality flags are present in the rows:
`wsl_host_validation_required` and `not_verified_discharging`.

**No processor energy, whole-laptop draw, inference energy or savings can be derived
from these traces.** In particular, 0 W battery flow while plugged in is not a measurement
of 0 W laptop consumption. These historical plugged-in traces remain unqualified.
The later unplugged check selected Windows reporting, as described below;
package (RAPL) energy remains unavailable.

The [idle manifest](examples/telemetry-wsl-idle-manifest.json) and
[inference-period manifest](examples/telemetry-wsl-inference-manifest.json) preserve the
sensor inventory, monotonic origin and warnings. These are separate component runs with
their own IDs; align their observations by host monotonic time when inspecting the smoke
check. The integrated application will provide a shared run ID and measurement window.

The software records unavailable sensors and quality limits rather than inventing
measurements. Collection, units, gaps, timestamps and cleanup are implemented; the
unplugged source check is now complete. **GO on 2026-10-27 for native Windows
BatteryReport remaining capacity**: 28 valid discharging/AC-off samples, 3.089 Wh reported
drop over approximately 270 seconds. WSL sysfs absolute energy is unqualified because
its full-capacity scale disagreed with Windows. Native updates were coarse (30–40 seconds),
so later comparisons require long controlled runs. See the
[qualification report](1b-battery-qualification.md) for preserved evidence and limitations,
and [methodology.md](methodology.md) for Shawn's handoff.

## Owner closeout — 2026-11-05

Austin explicitly authorized updating and closing both issues after the evidence audit.
The implementation was merged in [PR #31](https://github.com/austincbaker/cap6411-cv-systems/pull/31).
This is acceptance of the existing runs, with no new live measurement.

For `1a`, the audit checked four successful bounded image requests, two distinct image
hashes, the persistent-server record, CPU provenance and the stopped-service failure.
The pinned setup and run instructions are documented in the README. D11/Revision 6
accepts the tested WSL2 laptop as the experiment platform. The original
`validation-summary.json` retains its capture-time `development-smoke-only` label and
`designated_laptop_validation=false`; these historical acceptance flags are superseded
by the [dated owner-acceptance record](examples/acceptance-1a-1b.json). Raw measurements
and the original summary are unchanged. A second-member setup run is not claimed.

For `1b`, the audit checked all 28 samples for validity, discharging state, AC off,
monotonic query times, mWh-to-joule conversion and nonincreasing remaining capacity.
The first/last capacity difference is 3.089 Wh (11,120.4 J), and the preserved executed
script matches the manifest SHA-256. The original GO decision and all three phases
are present. The source is suitable for longer-window whole-laptop battery comparisons,
subject to its documented coarse updates and background activity. CPU/package and
individual-inference energy remain unavailable; workload effects and savings are unproven.

Austin authorized closure using this evidence review instead of waiting for a separate
Shawn sign-off. No approval or review is attributed to Shawn. His later experimental
protocol and analysis work remain separate. Each laptop still requires its own source
qualification. The machine-readable acceptance record includes evidence-file hashes.

## Automated verification

```bash
uv run python -m pytest -q
uv run ruff check src scripts tests
uv run ruff format --check src scripts tests
```

The 80 tests cover image payloads, bounded output, missing usage counts and server timings, connection/HTTP/JSON
failures, timeout uncertainty, no automatic retry, sample unit conversions, domain
hierarchy, alias deduplication, counter decreases, missing/invalid sensor reads, finite
cadence, interruption and CLI output behavior. Fakes do not substitute for the live model
smoke check or the live battery-source qualification. Added fake-reader checks cover
native unit/sign conversion, AC/battery states, unknown values, bounded errors without
retries and qualification decisions.

The local llama service used for verification was stopped cleanly after the check.
Restart it with `uv run python scripts/llama_runtime.py serve`. Full original run
directories are under ignored `results/`; builds/logs are under ignored `.cache/`.
