# Methodology

This document currently covers Austin's item 1b collector and its hardware checks.
Shawn owns the later experiment protocol, controls, repeat strategy and analysis in items
1f, 2f, 3f and 3g; their completion is not implied by this sensor documentation.

## Research questions

# Primary research question

Can runtime scheduling reduce the energy consumption of an always-on, on-device VLM assistant while maintaining useful event quality and acceptable response delay?

# Supplementary research questions

  1. How does event-driven VLM invocation affect energy consumption compared with fixed-interval invocation?
  2. How much event quality is retained, and how is response delay affected, when VLM calls are selectively scheduled?
  3. Can a budget-aware scheduling policy operate within a defined energy allowance while retaining useful assistant behavior?
The research questions use the same event-quality and response-delay definitions as the final evaluation contract. Energy savings are treated as an experimental outcome rather than an assumed benefit; negative or inconclusive results are retained.

## Related work and research framing

# Efficient VLM architectures
# SmolVLM

SmolVLM investigates how vision language models can be made small enough for resource constrained deployment while retaining useful multimodal capabilities. Its approach focuses on compact VLM configurations and reducing the amount of visual information that must be processed by the language model.
In this project, SmolVLM is important as related work and as the basis for the primary VLM. It shows the use of a compact model when compute and memory are limited and shows that efficiency can be improved within the VLM architecture itself.
However, architectural efficiency and runtime scheduling are different problems. SmolVLM primarily addresses the cost and capability of the model when inference is performed. Our project instead investigates whether an always-on system can obtain additional energy savings by deciding when VLM inference should occur. Therefore, SmolVLM provides the efficient inference foundation, while invocation frequency and timing remain system-level variables evaluated by this project.

# MobileVLM

MobileVLM studies vision language modeling for resource constrained mobile and edge environments. A central efficiency idea is reducing the visual information passed into the language model so that multimodal inference requires less computation. Its architecture demonstrates that efficiency must be considered across both visual processing and language model execution when targeting constrained hardware.
It is relevant to our project because an always on assistant cannot treat the cost of visual processing as negligible. Reducing the computational cost associated with each VLM invocation complements the project's goal of reducing unnecessary invocations.
MobileVLM primarily addresses architectural and per-inference efficiency. Our project studies a different but complementary question. It is whether temporal and event driven scheduling can reduce the number and timing of expensive VLM calls while retaining useful event coverage. The primary model and backend will therefore remain fixed when comparing runtime scheduling policies.

# FastVLM

FastVLM examines end-to-end VLM efficiency with particular attention to visual encoding, visual-token processing and inference latency. The work demonstrates the importance of considering the complete multimodal inference path rather than evaluating language model size alone. Its design emphasizes efficient visual processing and reducing the amount of visual information that must subsequently be handled by the language model.
FastVLM is especially relevant to this project because latency and the cost of visual processing affect the feasibility of an always-on assistant. An efficient runtime policy cannot compensate for arbitrarily expensive individual inferences, so architectural and runtime efficiency should be treated as complementary parts of the system.
It focuses on making an inference more efficient, whereas our project asks whether the system needs to perform that inference at every candidate time. Our evaluation therefore focuses on temporal selection. Like comparing fixed interval, event driven and budget aware invocation under controlled conditions.

# Conditional and streaming perception
# Edge energy-aware inference
# Runtime-scheduling contribution

The project distinguishes architectural efficiency from runtime scheduling.

Architectural efficiency reduces the cost of an individual VLM inference through techniques such as compact models, more efficient visual processing, and reductions in visual-token processing.

This project investigates a complementary system-level question: whether an always-on VLM assistant can reduce energy consumption by controlling when expensive VLM inference occurs. The evaluation compares fixed-interval, event-driven, and budget-aware VLM invocation while holding the primary model/backend and experimental controls fixed.

The effectiveness of runtime scheduling is treated as an experimental question. Energy savings, event quality, response delay, and adherence to the energy allowance are measured rather than assumed.

The report will frame the work against compact VLMs (including SmolVLM, MobileVLM and
FastVLM), conditional and streaming perception, and edge energy-aware inference. Its
contribution is runtime scheduling: comparing fixed-interval, event-driven and
budget-aware VLM invocation under the same replay content and measurement controls.

## Measurement protocol

Shawn's protocol will specify the trial controls, baseline configurations, repeat strategy,
randomized order, warm-up, missing-data handling and energy normalization before the final
evaluation freeze.

## Sensor collection methodology

## Quantities and domains

| Source attribute | Raw unit | Normalized value | Interpretation |
| --- | --- | --- | --- |
| Powercap `energy_uj` | Microjoules | Raw × 0.000001 J | Cumulative energy in the named hardware zone |
| Battery `energy_now` | Microwatt-hours | Raw × 0.0036 J | Stored battery energy at that observation |
| Battery `power_now` | Microwatts | Raw × 0.000001 W | Battery power flow; not necessarily total system draw |

The collector preserves every zone separately and records parent relationships. Do not
add a CPU package's energy to the subdomains it already contains. Discover actual zones;
do not assume a particular CPU vendor, path name or permissions from the Ubuntu version.

`charge_now` is not converted to energy using instantaneous voltage. Charge, stored energy,
counter deltas and instantaneous power are different quantities. The collector makes no
per-process attribution and does not infer an inference's energy cost from CPU utilization.

References: [Linux powercap](https://docs.kernel.org/power/powercap/powercap.html) and
[Linux power-supply units](https://docs.kernel.org/power/power_supply_class.html).

## Artifact format

`energy-monitor` creates a new output directory and refuses to overwrite an existing run.

- `manifest.json`: record version, shared run ID, platform/WSL indicator, sensor inventory,
  requested cadence/duration, monotonic origin, actual recording duration, valid/invalid
  row counts, completion and errors.
- `samples.csv`: one row per sensor/sample, with `elapsed_s`, raw and normalized values,
  unit, domain, quantity, parse validity, errors, counter range, AC/battery state and
  measurement quality flags.

CSV nulls are empty cells; booleans use `True`/`False`. Sensor metadata includes the source
path and units. Invalid reads leave raw/normalized numeric fields missing. The collector
does not carry a previous reading forward as a fresh measurement or replace a gap with 0.

The record format is an initial component handoff. Final application schemas, evaluation
matching rules and fixture conventions remain item 2d's responsibility.

## Timing and lifecycle

Use one host monotonic time base for inference and telemetry. A sensor row's absolute host
time is `origin_monotonic_s + elapsed_s`. `VLMClient` records request start and response
availability on that same host clock. Source-video time remains an independent field.

Requested sampling cadence is not a guarantee about sensor refresh. Actual sample times
are retained; missed ticks are skipped instead of emitted in bursts. The iterator samples
the start and end of a finite interval. Each read opens/closes its file, and stopping does
not leave a collector thread running. The CLI flushes completed batches and retains partial
CSV/manifest data after interruption, returning 130.

Counter range metadata is retained for later rollover handling. A decreasing counter may
also indicate reset or suspend/resume; the collector preserves the raw decrease and does
not silently decide it was one wrap. Final analysis must reject ambiguous gaps/ranges.

## Validity and quality flags

`valid=True` means a reading was parsed and normalized in its declared unit. It does not
establish that the reading measures the desired experimental quantity.

- `wsl_host_validation_required`: validate exposed telemetry against the physical host
  before treating it as physical energy evidence.
- `not_verified_discharging`: battery state and AC status do not establish battery-powered
  discharge. This prevents interpreting a plugged-in zero-flow value as zero laptop draw.

No discovered sensors, all-invalid samples, file output errors and interrupted recording
are explicit unsuccessful outcomes. Individual invalid sensors do not suppress valid rows
from other domains; consumers still inspect coverage, flags and completion before analysis.

## Observed hardware check

The implementation ran on Ubuntu 22.04.5 LTS with kernel
`6.6.87.1-microsoft-standard-WSL2`, an exposed Intel i7-13620H CPU, eight logical CPUs and
approximately 12 GiB assigned memory. This identifies the development environment rather
than assuming it is a native Ubuntu boot.

The powercap directory contained no counters. `BAT1` exposed `energy_now=4700000 uWh`
(16,920 J stored energy) and `power_now=0 uW`; `AC1` was online and battery status was
`Not charging`. Stored energy stayed constant across the short idle/inference traces.
Both WSL and discharge-quality flags are therefore significant. These traces cannot
establish processor energy, whole-laptop draw or savings.

The unplugged follow-up completed the `1b` go/no-go on 2026-10-27: **GO for Windows
host `Windows.Devices.Power.BatteryReport` capacity**, read through PowerShell from WSL.
See the [qualification report and raw evidence](1b-battery-qualification.md).
The WSL full-capacity scale was 5 Wh versus native 38.646 Wh, so its absolute energy
and power remain unqualified even while discharging. Package energy remains unavailable.

The native reader in `src/energy/windows.py` retains raw remaining/full mWh and signed
charge-rate mW. Remaining mWh × 3.6 gives stored joules; negative charge rate represents
discharge. A qualified discharge sample requires valid capacity, AC disconnected and
status `Discharging`. Missing values and errors remain explicit. Microsoft's
[BatteryReport documentation](https://learn.microsoft.com/en-us/uwp/api/windows.devices.power.batteryreport?view=winrt-26100)
defines the native units.

`scripts/qualify_battery.py` creates native/WSL `samples.jsonl`, a manifest and a decision
report; the existing `energy-monitor` CSV remains a separate diagnostic path. Native
readings preserve host monotonic query start/availability and observation UTC. Polling
starts a PowerShell process each time, so keep that overhead/cadence matched across
policies. Observations updated only about every 30–40 seconds, with median capacity step
0.387 Wh. Use longer windows spanning many steps and repeat trials; this source cannot
resolve a single inference's energy. Use start/end remaining-capacity differences for
whole-laptop battery energy, keeping reported instantaneous power as a separate quantity.

The 270-second check returned 28 valid unplugged samples and a reported 3.089 Wh drop.
Reported median load-phase power was lower than idle, so no workload effect or savings
is established. Background activity and Windows are part of the measurement domain.
Final trial duration, precision criteria and experimental controls remain Shawn's 2f
protocol. A finer WMI path was only briefly probed and is not qualified by this run.
Do not change power limits or loosen system permissions silently.

Results may vary depending on whose laptop runs the tests. Hardware, battery health,
power settings, background activity and sensor update rates can affect energy and
latency. Record the laptop/configuration for each run and compare policies on the same
machine. Qualify the battery source on each additional laptop and report its results
separately; this laptop's qualification and cost estimates do not transfer automatically.

## Arithmetic check for Shawn

Constant 10 W over 60 s represents 600 J = 0.1667 Wh. Normalized to an hour, it is
10 Wh/hour (numerically the average power in watts). A real observed stored-energy drop
must be measured over its actual interval with matching units and a qualified discharge
condition. It is not appropriate to apply that calculation to the constant WSL readings.

Small raw traces and the live smoke summary are linked in
[validation-1a-1b.md](validation-1a-1b.md). Long-run trials and statistical comparisons remain
the later evaluation tasks.
