# Methodology

This document currently covers Austin's item 1b collector and its hardware checks.
Shawn owns the later experiment protocol, controls, repeat strategy and analysis in items
1f, 2f, 3f and 3g; their completion is not implied by this sensor documentation.

## Research questions

### Primary research question

Can runtime scheduling reduce the energy consumption of an always-on, on-device VLM assistant while maintaining useful event quality and acceptable response delay?

### Supplementary research questions

  1. How does event-driven VLM invocation affect energy consumption compared with fixed-interval invocation?
  2. How much event quality is retained, and how is response delay affected, when VLM calls are selectively scheduled?
  3. Can a budget-aware scheduling policy operate within a defined energy allowance while retaining useful assistant behavior?
The research questions use the same event-quality and response-delay definitions as the final evaluation contract. Energy savings are treated as an experimental outcome rather than an assumed benefit; negative or inconclusive results are retained.

## Related work and research framing

### Efficient VLM architectures
#### SmolVLM

SmolVLM addresses the computational and memory requirements that limit the deployment of vision language models on resource constrained mobile and edge devices. The authors argue that smaller VLMs can remain inefficient when they inherit design choices from larger models, including extensive image tokenization. SmolVLM therefore investigates architectural configurations, tokenization strategies, and training data curation designed specifically for resource efficient multimodal inference. [1]
Its architecture encodes images or sampled video frames into visual features, rearranges those features using a pixel shuffle operation, and projects them into the language model's input space as visual tokens. These visual tokens are combined with text embeddings before being processed by the language model. The paper evaluates compact models at several scales and reports that its smallest 256M parameter model requires less than 1 GB of GPU memory during inference. SmolVLM also evaluates both image and video understanding, making it relevant to resource constrained systems that process continuous visual inputs [1].
For this project, SmolVLM provides the architectural foundation for efficient VLM inference. Its results motivate using a compact multimodal model rather than a substantially larger VLM when targeting constrained hardware. However, SmolVLM primarily addresses the efficiency and capability of the model when inference occurs. Our project investigates a complementary runtime question: whether additional energy savings can be achieved by controlling when the VLM is invoked. Therefore, event driven invocation, fixed interval invocation, and budget aware scheduling are treated as experimental runtime policies rather than benefits established by the SmolVLM paper.

#### MobileVLM

MobileVLM targets multimodal vision language inference on mobile devices. The model combines mobile oriented architectural choices with language models at the 1.4B- and 2.7B-parameter scales, a vision model pretrained in a CLIP style approach, and an efficient cross modality projector. The work therefore approaches efficiency as an architectural problem spanning both the language and visual components of a VLM. [2]
The authors evaluate MobileVLM on standard vision language benchmarks and also measure inference speed on resource constrained hardware, including a Qualcomm Snapdragon 888 CPU and NVIDIA Jetson Orin GPU. This hardware evaluation makes MobileVLM particularly relevant to our project because it demonstrates VLM inference in environments closer to mobile and edge deployment rather than evaluating performance exclusively on large server class systems. [2]
For this project, MobileVLM provides evidence that the cost of each multimodal inference can be reduced through mobile oriented model and projection design. Our project investigates a complementary runtime problem. Rather than modifying MobileVLM's architecture, we study whether an efficient on device VLM system can further control resource use by selecting when expensive VLM inference occurs. Fixed interval, event driven, and budget aware invocation are therefore runtime policies evaluated by our project rather than benefits established by MobileVLM.

#### FastVLM

FastVLM investigates the efficiency of the visual processing stage of vision language models, particularly when processing high resolution images. The authors identify two important sources of VLM latency: the time required by the vision encoder and the number of visual tokens subsequently passed to the language model. The paper analyzes the interaction among image resolution, vision encoder latency, visual token count, language model size, accuracy, and overall latency. [3]
FastVLM introduces FastViTHD, a hybrid vision encoder designed to produce fewer visual tokens while reducing the encoding time required for high resolution images. The approach seeks a better tradeoff among image resolution, latency, model size, and accuracy without requiring an additional visual token pruning stage. In the paper's LLaVA-1.5 evaluation setup, FastVLM reports a 3.2× improvement in time-to-first token while maintaining similar benchmark performance relative to prior approaches. [3]
FastVLM is relevant to this project because it demonstrates that the cost of VLM inference depends on more than the size of the language model. Visual encoding, image resolution, and the number of visual tokens passed to the language model can also substantially affect inference latency. These factors help establish why efficient visual processing matters for an on device VLM system.
Our project examines a complementary runtime dimension. FastVLM seeks to make an individual inference more efficient, whereas our runtime scheduler investigates whether an inference needs to occur at each candidate time. We therefore treat architectural efficiency and temporal scheduling as separate but complementary approaches to reducing the resource requirements of an always on VLM assistant.

### Conditional and streaming perception

Video and continuously captured visual inputs contain more frames than a resource constrained model may be able or need to process. VideoBrain studies this problem in long form video understanding, contrasting uniform frame sampling with an adaptive approach in which a VLM acquires additional visual information according to learned sampling policies [4]. The approach combines semantic retrieval across a video with dense temporal sampling within selected intervals and learns when additional frame acquisition is useful. The authors report improved performance on four long video benchmarks while processing fewer frames than the comparison baseline [4].
This work is relevant to our always on setting because it establishes that visual information does not necessarily need to be sampled uniformly over time. Visual information can instead be acquired selectively over time based on the information needed by the VLM. Our system investigates a related but distinct runtime decision. Rather than training the VLM itself to adaptively retrieve frames for video question answering, our application uses lightweight event/change detection to determine when the primary VLM should be invoked. Fixed interval sampling therefore provides a useful comparison against event driven scheduling.

### Edge energy-aware inference

Energy consumption is an important systems constraint when neural network inference is performed on resource constrained edge hardware. PolyThrottle studies energy efficient neural network inference on edge devices by examining how hardware configurations, including CPU, GPU and memory frequencies, as well as batch size, affect inference energy consumption and latency [5]. The system uses constrained Bayesian optimization to identify energy efficient hardware configurations while satisfying an inference latency constraint, and the authors evaluate the approach on NVIDIA Jetson TX2 and Orin devices [5].
PolyThrottle is relevant to our project because it demonstrates that inference latency and measured energy consumption can exhibit a nontrivial tradeoff and can be considered jointly when optimizing an edge inference system [5]. Our project evaluates a different control variable: the timing and frequency of VLM invocation. We therefore measure the energy behavior of the scheduling policies directly rather than if a change in invocation behavior produces a particular amount of energy savings. Following our measurement protocol, whole system battery measurements and processor domain measurements are reported separately when those measurement domains are available.

### Runtime-scheduling contribution

The related work separates two complementary sources of efficiency. The SmolVLM, MobileVLM, and FastVLM work reviewed above demonstrate approaches to improving the architectural and computational characteristics of multimodal inference, including compact model design, visual processing, visual-token processing, and inference latency [1][2][3]. Adaptive video sampling research demonstrates that visual computation can also be allocated selectively over time instead of relying exclusively on uniform frame sampling [4]. Energy-aware edge inference research further demonstrates that energy and performance can be treated jointly when operating under resource constraints [5].
Our project combines these motivations around a system level evaluation of an always on VLM assistant. The primary VLM and backend are held fixed when evaluating temporal scheduling so that improvements caused by changing the model are not confused with improvements caused by changing when the model is invoked. The runtime comparison considers idle/no invocation behavior, fixed interval invocation, matched invocation sampling, event driven invocation, and the full budget aware policy.
The contribution being evaluated is not the claim that event driven scheduling necessarily saves energy. Instead, the project asks whether controlling the timing and frequency of expensive VLM inference produces a better energy quality tradeoff than fixed scheduling under the same replay content and measurement controls. The evaluation therefore considers measured energy consumption together with VLM invocation behavior, retained event quality, response delay, and adherence to the available energy allowance. Negative or inconclusive energy results are retained rather than interpreted as successful scheduling.

The project distinguishes architectural efficiency from runtime scheduling.

Architectural efficiency reduces the cost of an individual VLM inference through techniques such as compact models, more efficient visual processing, and reductions in visual token processing.

This project investigates a complementary system level question: whether an always on VLM assistant can reduce energy consumption by controlling when expensive VLM inference occurs. The evaluation compares fixed-interval, event-driven, and budget-aware VLM invocation while holding the primary model/backend and experimental controls fixed.

The effectiveness of runtime scheduling is treated as an experimental question. Energy savings, event quality, response delay, and adherence to the energy allowance are measured rather than assumed.

The report will frame the work against compact VLMs (including SmolVLM, MobileVLM and
FastVLM), conditional and streaming perception, and edge energy aware inference. Its
contribution is runtime scheduling: comparing fixed interval, event driven and
budget aware VLM invocation under the same replay content and measurement controls.

## Measurement protocol

### Measurement domains

Energy results are reported according to the domain measured by the available sensor.
Package energy and whole system battery energy are treated as separate quantities and are not combined or substituted for one another.
Whole system battery energy is determined only from a qualified battery energy source
under a valid discharge condition. Package energy is reported only when an
appropriate package energy counter is available and qualified.
Idle and workload energy may be compared or subtracted only when they use compatible
measurement domains and experimental conditions. Measurements unavailable on the test
hardware are reported as unavailable rather than estimated from another sensor domain.

### Standard test configuration

Each comparison records and, where applicable, holds fixed:

- Test machine and hardware configuration
- Operating system environment
- Power mode
- AC/battery state
- Display state
- Primary VLM
- Model quantization
- Inference backend and build
- Generation parameters and output bound
- Input video
- Replay speed
- Energy measurement source and polling configuration
- Application logging/display behavior

Unknown configuration values are recorded as pending until measured or finalized.
Temporal policy comparisons use the same primary model and inference backend so that
differences between scheduling policies are not confounded with changes to the model.

### recorded video replay controls

Primary scheduling policy comparisons use the same recorded source video on the same
test machine. Recorded video is replayed in real time so that scheduling behavior,
response availability and energy measurements correspond to a common wall clock
duration.
Each run records both host monotonic time and source video time. Source video identity
and timestamps are preserved so that runtime outputs can later be aligned with the
event annotations used for quality evaluation.
Replay overhead is part of the measured workload and is kept consistent between policy
comparisons.

### webcam controls

Live webcam measurements are treated separately from recorded video replay measurements.
Camera acquisition and recorded video decoding can introduce different system overheads,
so results from the two input modes are not directly substituted for one another.
When webcam trials are performed, camera configuration, acquisition behavior and relevant
application settings are recorded and kept consistent across the policies being compared.

### warm-up and measurement window

Model loading and initialization occur before the primary measured interval. A defined
warm-up procedure will be applied consistently before comparable trials so that startup
behavior is not unintentionally included in only some configurations.
Each trial records explicit measurement window start and end times. Setup and shutdown
occur outside the primary measured interval. Requests initiated during the interval are
tracked separately if their responses become available after the declared scoring
horizon.
Final warm-up duration and measured window duration will be selected using pilot latency
and telemetry observations rather than assumed in advance.

Shawn's protocol will specify the trial controls, baseline configurations, repeat strategy,
randomized order, warm-up, missing-data handling and energy normalization before the final
evaluation freeze.

### Environmental controls

Comparable trials are performed on the same machine under documented operating
conditions. The following conditions are recorded and held fixed where feasible:

- Power mode
- AC/battery state
- Display state
- Background application state
- Model and backend configuration
- Input source and replay configuration
- Energy sensor configuration

Trial order and observed environmental deviations are recorded. A changed power state,
unexpected interruption or other material deviation is retained in the trial record
rather than silently ignored.

### Unavailable measurements and limitations

A metric is reported only when the corresponding measurement source is available and
qualified for the experimental condition. Missing processor/package energy, invalid
sensor samples or unsupported measurement domains are reported as unavailable rather
than inferred from another measurement.

Whole system battery measurements must not be labeled as processor energy, and
processor/package measurements must not be labeled as whole system energy.

The qualified battery source has limited update granularity and therefore is not used
to attribute battery energy consumption to an individual VLM inference. Longer measured
windows and repeated trials are used for whole system energy comparisons.

### Initial comparison policies

The initial pilot evaluates scheduling policies using the same primary VLM, inference
backend, source video, generation settings and measurement conditions. Exact fixed
intervals and final trial durations are not frozen in this phase; they will be selected
using pilot latency and telemetry observations.

#### Idle / no invocation condition

The idle condition measures the application without VLM inference requests while keeping
the comparison workload otherwise aligned. The model remains loaded, and normal video
acquisition or replay, logging and other ordinary application activity continue.

This condition estimates the energy associated with the surrounding application workload
without VLM invocation. Idle energy is subtracted from another measurement only when the
measurement domain and experimental conditions are compatible.

#### Fixed interval condition

The fixed interval condition invokes the VLM according to a predetermined temporal
interval without using event or relevance information to select invocation times.

Several feasible intervals will be considered after pilot measurements establish VLM
latency and measurement behavior. If a requested interval cannot be sustained, skipped
or overloaded calls are recorded rather than silently changing the effective policy.

#### Matched invocation condition

The matched invocation condition uses a prespecified sampling rule to make approximately
the same number of VLM invocations as the event driven policy without using the
event driven policy's event decisions to select invocation times.

Invocation counts used for matching are derived from development or calibration runs or
another prespecified rule. Held out evaluation results are not used to tune the
matched invocation baseline.

This comparison helps separate the effect of reducing the number of VLM calls from the
effect of selecting useful invocation times.

#### Event driven condition

The event driven condition uses the application's event/change detection mechanism to
determine when the primary VLM is invoked.

The event detector and its configuration are recorded for each trial. VLM attempts,
successful responses, failures, source video timestamps and response availability times
are retained so that scheduling behavior can later be aligned with event quality
evaluation.

#### Budget aware condition

The budget aware condition evaluates the full scheduling policy in which VLM invocation
behavior is additionally constrained by the project's energy budget mechanism.

The energy allowance and final policy configuration are not frozen during this phase.
Those settings are finalized only after pilot measurements establish feasible runtime
and measurement behavior.

### Failure and exclusion handling

Failures and deviations remain visible in the experimental record rather than being
silently removed. These include:

- Incomplete or invalid input
- Missing or invalid energy samples
- Interrupted trials
- Model or inference failures
- Changed power states
- Overloaded or skipped VLM calls
- Incomplete responses at the scoring horizon
- Material deviations from the recorded test configuration

Attempted and successful VLM invocations are reported separately. Energy consumed by a
failed inference attempt remains part of the measured workload.

A trial may be excluded from a primary comparison only for a documented reason defined
by the protocol. Excluded trials and the reasons for exclusion remain recorded.

### Energy calculations

For a measured interval of duration T seconds with observed energy E joules:

- Mean power (W) = E / T
- Total energy (Wh) = E / 3600
- Hourly normalized energy rate (Wh/hour) = E / T


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

## References 

[1] A. Marafioti et al., "SmolVLM: Redefining Small and Efficient Multimodal Models," arXiv:2504.05299, 2025.

[2] X. Chu et al., "MobileVLM: A Fast, Strong and Open Vision Language Assistant for Mobile Devices," arXiv:2312.16886.

[3] P. K. A. Vasu et al., "FastVLM: Efficient Vision Encoding for Vision Language Models," arXiv:2412.13303.

[4] J. Zou, Z. Huang, S. Zhang, L. Zhang, and W. Shen, "VideoBrain: Learning Adaptive Frame Sampling for Long Video Understanding," ICML, 2026.

[5] M. Yan, H. Wang, and S. Venkataraman, "PolyThrottle: Energy-efficient Neural Network Inference on Edge Devices," arXiv:2310.19991, 2024.
