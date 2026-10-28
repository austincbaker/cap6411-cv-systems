# Build an energy-aware always-on VLM assistant — Four-week team plan

- **Status:** TODO
- **Owners:** Austin (technical lead), Alejandro (application and cascade), James (data and event evaluation), Shawn (energy experiments and reporting)
- **Estimated effort:** XL — four weeks across four team members, with Austin and Alejandro leading core development

## Summary

As a **laptop user**, I want **a local webcam assistant that recognizes meaningful scene changes within an energy budget**, so that **I can receive useful updates while limiting battery consumption**.

Build a persistent llama.cpp application on CPU or integrated graphics, using a cheap change-detection gate to decide when the VLM should analyze a frame. Compare event-driven and budget-aware inference against fixed-interval sampling using measured energy, event quality, and response delay.

Austin and Alejandro own the core runtime. James and Shawn own research and evaluation early, followed by concrete evaluation-software deliverables in Weeks 3–4. Provide stable example logs by the end of Week 2 so their implementation can proceed independently.

---

## Background / Context

**Verified from the conversation:** The team has approximately one month. Austin and Alejandro have the most development availability. James and Shawn have less coding time but should each own a relevant software component used in the final results.

**Verified in the repository:** `README.md` currently contains only the project heading. Application structure, commands, models, and tests described below are proposed; their implementation has not been verified.

The research starting points are [SmolVLM](https://arxiv.org/abs/2504.05299), [FastVLM](https://arxiv.org/abs/2412.13303), and [MobileVLM](https://arxiv.org/abs/2312.16886). These are supplied research references. This plan does not independently verify the performance claims or dataset details in earlier discussion.

**Assumption:** Workspace awareness with object addition/removal is the default application because the events can be staged and annotated using a fixed webcam. Simulated lab-safety monitoring and assistive object tracking remain candidate task definitions; implementing all three applications is outside the four-week scope.

**Platform confirmed by Austin (rev. 1):** Ubuntu 22.04.5 LTS is the primary experiment platform. Keep the settled CPU-first baseline; integrated graphics, if tested, remain a separate configuration. The CPU vendor, exposed energy counters, battery telemetry and sensor permissions still require a hardware check in item `1b`.

**Implementation-time checks retained for Week 1:** Finalize the event vocabulary using the default workspace task, verify a supported and sufficiently responsive model, check the actual laptop/sensors, and confirm public clip access and fit. These are assigned discovery tasks, not assumptions that their outcomes are already known.

**Planning-quality risk (rev. 4):** A repository `AGENTS.md` now records project purpose, planned layout, plan-document and ownership rules, and data/measurement-integrity rules. No committed implementation code, dependency manifest or test setup exists yet; its setup and test commands remain TODO until item `1a` adds them. Follow the explicit plan without inventing existing conventions.

---

## Goals

1. **Week 1:** Run local inference on webcam and recorded input, establish fixed-interval behavior, and verify usable power telemetry.
2. **Week 2:** Deliver an event-driven application, a labeled evaluation subset, and stable schemas with sample logs.
3. **Week 3:** Integrate energy-budget control and measured inference optimizations; deliver initial versions of James's scorer and Shawn's benchmark/report tools.
4. **Week 4:** Produce repeatable energy-versus-quality results, a stable demonstration, and a report with a clear contribution from each member.

## Non-Goals

- Training a new VLM or designing a new visual encoder.
- Dedicated-GPU or cloud inference for the application.
- Supporting every operating system or power-measurement backend in the first release.
- Building all three candidate applications or persistent identity tracking across complex occlusions.
- Requiring a learned gate, a failure-review viewer, or advanced cache management to complete the core study.
- Publishing a live GitHub issue as part of creating this draft.

---

## Acceptance Criteria

- [ ] **Phase 1:** Given the selected laptop and model, webcam and real-time replay both produce bounded VLM responses; the selected telemetry source records power or energy with its measurement domain documented.
- [ ] **Phase 2:** Given a video with meaningful changes, irrelevant motion, and idle periods, the application logs trigger decisions and observations without repeated notifications for an unchanged confirmed state.
- [ ] **Phase 2 handoff:** Given the documented schemas and example files, James and Shawn can start their tools without a running model or webcam.
- [ ] **Phase 3:** Given a feasible energy allowance, the scheduler records estimated costs, admission decisions, actual consumption, and any budget exceptions; changes in budget affect inference behavior.
- [ ] **James's coding contribution:** Given annotations and prediction logs, one command exports event metrics and an event-level report of correct detections, false alarms, duplicates, and missed events.
- [ ] **Shawn's coding contribution:** Given experiment configurations, one command executes repeated trials; given completed logs and James's metrics, another exports comparison tables and energy-versus-quality figures.
- [ ] Given a model timeout, invalid response, or missing power samples, the run records the failure and marks affected results unavailable or incomplete rather than treating them as successful zero-cost work.
- [ ] **Phase 4:** The final application completes a 30-minute stability run and the main comparison configurations have three repeated energy measurements each.
- [ ] Fixed-interval, matched-invocation, event-driven, and budget-aware results use the same primary model and record all relevant configuration differences.
- [ ] The targeted behavioral tests in this plan pass, and another member can reproduce one result using the documented commands.

Energy savings and quality preservation are research outcomes to measure, not guaranteed acceptance thresholds. Report unfavorable or inconclusive findings alongside positive results.

---

## Design

### Decision register (rev. 1)

The original Design choices remain settled. Stable identifiers below let item plans refer to those choices without reopening them. The five-column table records baseline versus revised choices.

| # | Decision | Baseline choice | Rev. 1 choice | Δ |
| --- | --- | --- | --- | --- |
| D01 | Application boundary | One application; workspace object changes by default | Same; finalize narrow event vocabulary in `1e` | — |
| D02 | Ownership | Austin/Alejandro core runtime; James/Shawn evaluation software | Same; each item names its owner | — |
| D03 | Inference | One compact model/quantization; CPU-first | Same; compatibility measured in `1a`; integrated GPU reported separately | — |
| D04 | Cascade | Cheap rule gate, refresh, cooldown and acknowledged reference | Same; learned classifier stays optional | — |
| D05 | Runtime lifecycle | One active inference and at most one pending latest frame | Same; errors preserve confirmed state | — |
| D06 | File contracts | Versioned JSONL logs, CSV annotations/power, JSON manifest | Same; Week 2 fixtures unblock evaluation tooling | — |
| D07 | Evaluation | One-to-one event matches; source and availability times; grouped held-out data | Same; detailed rules frozen before testing | — |
| D08 | Energy comparison | Idle, fixed, matched invocation, gate and budget modes; repeated main trials | Same; keep sensor domains and total/incremental energy separate | — |
| D09 | Optimizations | Measure output/image/cache effects; no assumed visual-token saving | Same; unsupported controls remain unavailable | — |
| D10 | Delivery scope | Four weeks; optional learned gate/viewer; no new VLM training | Same; 26 required items and one optional viewer | — |
| D11 | Primary platform | Laptop/OS open | Ubuntu 22.04.5 LTS, confirmed by Austin; sensor verification remains in `1b` | new decision |

**Document authority:** `TODO_Plan/build-energy-aware-vlm-assistant.md` is the canonical master plan. `energy-aware-vlm-implementation/plan.md` is its synchronized reading copy, with local links adjusted for that directory. Future decisions must update the canonical plan and refresh the reading copy together; no separate decisions file is used.

**Next deliverable (rev. 2):** Implement the five confirmed, expanded Phase 1 starting items: `1a`, `1b`, `1c`, `1e` and `1f`. Their detailed plans are ready; implementation remains not started. The integrated baseline `1d` becomes dependency-ready after `1a`, `1b` and `1c` are implemented, not merely planned. See the [implementation index](../energy-aware-vlm-implementation/README.md) for item links and status.

### GitHub priorities and ownership (rev. 3)

All 27 work items now have corresponding live issues in [austincbaker/cap6411-cv-systems](https://github.com/austincbaker/cap6411-cv-systems/issues). Each issue is assigned to its planned owner or owners, has one priority label, and uses native GitHub blocking relationships for the exact prerequisite list in the work-item register. A blocked relationship tracks readiness; implementation completion still requires the existing acceptance checks.

| Label | Meaning | Work items |
| --- | --- | --- |
| `priority:P0` | Critical foundations or a handoff bottleneck | `1a`, `1b`, `1c`, `1d`, `1e`, `2d` |
| `priority:P1` | Required application, data, evaluation or final delivery | The other 19 required non-optimization items |
| `priority:P2` | Measured inference optimizations/ablations after the foundations | `3b` |
| `priority:P3` | Optional stretch work | `4g` |

Priority does not remove dependencies or change the required scope: `3b` remains required by the plan even though it is ranked P2. P0 describes task impact and coordination needs, not the importance of a team member's contribution. Shared issues keep the existing joint owners; the pilot (`3h`) and demonstration (`4f`) are assigned to all four members.

### Scope and ownership

**Decision:** Deliver one application and one primary hardware configuration. Default to workspace object changes, confirming the final task in Week 1. Keep the development path concentrated with Austin and Alejandro while giving James and Shawn ownership of the tools that produce the final evaluation.

| Member | Early work: Weeks 1–2 | Coding ownership: Weeks 3–4 | Required deliverable |
| --- | --- | --- | --- |
| Austin | Model setup, architecture, telemetry integration, inference benchmarks | Inference client, bounded prompts, cache experiments, energy-budget controller | Persistent local inference and budget control |
| Alejandro | Webcam/replay, baseline policy, change gate, scene state | Relevance rules, scheduler integration, simple UI, runtime reliability | Complete live and replay application |
| James | Dataset selection, recording coordination, event definitions, annotation and quality rubric | Event matching, scoring CLI, event-level error report | Ground truth and reproducible quality metrics |
| Shawn | Related work, measurement controls, trial protocol and initial benchmark execution | Benchmark runner, energy/latency analysis, tables and plots | Repeated experiment execution and reproducible result artifacts |

All members contribute recordings and review the report. James and Shawn begin with file-based tools; their work does not require completing application UI changes. Austin reviews Shawn's energy calculations, and Alejandro reviews James's event matching against manually scored examples.

### Architecture and implementation choices

`FrameSource` → cheap change gate → relevance/cooldown/refresh policy → budget admission → selected image input → persistent llama.cpp inference → confirmed scene state and notifications.

| Option | Description | Verdict |
| --- | --- | --- |
| Rules-based change gate | Downsampled frame differences, regional changes, persistence and cooldown | ✅ **Recommended.** Fast to implement and easy to analyze. |
| Learned relevance classifier | Small classifier after the change gate | 🟡 **Defer.** Add only after the baseline and evaluation pipeline work. |
| Custom dataset plus public subset | Task-specific webcam clips and independently sourced validation clips | ✅ **Recommended.** Supports controlled events and an external check. |
| Full-scale tracking benchmark integration | Broad tracking evaluation with persistent object identities | 🟡 **Defer.** Exceeds the initial event-change task. |
| New VLM training | Retrain an encoder or language model | ❌ **Rejected.** Does not fit the runtime scheduling question or deadline. |

**Decision:** Use one supported compact VLM and quantization for primary comparisons. Try a small SmolVLM-family model first, verifying compatibility, latency, and memory in Week 1. Use CPU as the simplest common baseline; document integrated-GPU runs separately if included.

Keep one inference active and at most one pending latest frame. Compare against the last acknowledged scene as well as recent motion so gradual changes can be detected. Use cooldowns and forced refreshes to balance repeated triggers and stale scene state. Treat disappearance as “no longer visible” unless removal is supported by the task evidence.

Measure resolution/crop effects, output-token limits, and valid static-prefix caching. Changed images must be processed as changed input. Only claim image-token savings when the selected model actually processes fewer visual tokens. A cache result showing little benefit remains a valid ablation.

### Contracts and handoff by the end of Week 2

**Decision:** Use versioned JSONL event/request logs, CSV power samples and annotations, and a JSON run manifest. Define field names and units in `docs/data-contracts.md`. Provide small synthetic examples with known expected results in `tests/fixtures/`.

| Artifact | Required information | Producer → consumer |
| --- | --- | --- |
| Annotation records | Video/session ID, event ID, class, object if relevant, observable event interval, priority | James → evaluator |
| Prediction records | Run/video ID, prediction ID, source-frame time, response-available time, event label, object, description, request status | Austin/Alejandro → James |
| Request/gate records | Trigger or skip reason, frame time, inference mode, latency, output length, available token/cache statistics | Austin/Alejandro → Shawn |
| Power samples | Run ID, monotonic elapsed time, power in W or cumulative energy in J, sensor and domain, sample validity | Austin → Shawn |
| Run manifest | Schema version, configuration, video/session, repeat, model/build revisions, hardware/backend, power mode, measured interval and completion status | Core runtime initially; Shawn's runner later → all tools |
| Metrics/error reports | Matched event/prediction IDs, TP/FP/FN counts, duplicates, event delay, aggregate metrics | James → Shawn and report |

Use video-relative time for event matching and a shared monotonic timeline for energy/inference alignment. Keep source-frame time and response-available time distinct so a delayed response is not credited as an immediate detection. Store unavailable sensor or token values explicitly as missing.

James and Alejandro define the event-label normalization, matching tolerance and eligibility window before the held-out evaluation. Require one-to-one matches; extra predictions for an already matched event count as false positives and are flagged as duplicates. Define empty-set metric behavior in the contract. Support a reporting horizon for sustained state changes when the transition itself has ended, with that horizon frozen before testing.

### Data and experimental method

James coordinates approximately 30–36 short clips, at least 100 labeled events where feasible, and longer quiet/mixed-activity recordings. Include small changes, irrelevant motion, lighting variation, occlusion and no-event scenes. Split by session or environment; retain an unseen environment if practical. Two members independently check a subset of annotations.

Use one accessible public subset if its camera view and labels can be mapped honestly to the selected task. Candidate sources from the discussion include Charades or Watch-n-Patch for workspace activity, R2PPE for PPE monitoring, and TREK-150 or Ego4D Hands & Objects for manipulation. James verifies access, terms and task fit before adoption; these are candidates, not confirmed dependencies. Keep participant recordings and permitted public data local unless sharing permission is established.

Shawn defines these comparisons: camera/model idle; fixed sampling at several feasible intervals; random or fixed sampling at the cascade's average invocation rate; change gate; relevance gate; and the complete budget-aware policy. Specify missed deadlines and dropped frames explicitly when fixed sampling overloads the hardware. Use the same replay content at real-time speed and repeat the main energy trials three times in randomized order.

Report total energy and incremental energy above the camera-and-loaded-model idle condition separately. Label whole-laptop battery energy separately from CPU/package estimates. Integrate power over the actual observed interval, handle supported counter rollover, avoid summing overlapping energy domains, and mark gaps rather than silently interpolating long missing intervals. Distinguish measured duration from hourly normalization.

The energy controller uses measured cost estimates per inference mode and an incremental allowance above measured idle. Account for continuous gate overhead as well as VLM calls. Reject infeasible budget configurations below the measured energy floor or explicitly report their infeasibility. Record high-priority overrides and resulting overspend.

### Proposed tool interfaces

Commands below are planned interfaces, not commands that work in the current repository:

- James: `python -m experiments.score_events --annotations <file> --predictions <file> --output <directory>`.
- Shawn: `python -m experiments.run_benchmarks --config <file> --output <directory>`.
- Shawn: `python -m experiments.analyze_results --runs <directory> --output <directory>`.

Required command-line behavior includes useful errors for malformed input, separate output directories per run, and a non-success status for failed trials. James's failure-review viewer is a stretch deliverable after the scorer works.

---

## Implementation Plan / Sub-Tasks

### Phase 1 — Establish live inference and measurement (Week 1)

- **Outcome:** A reproducible fixed-interval assistant runs on the selected machine and produces preliminary telemetry.
- **Dependencies / entry criteria (rev. 1):** Ubuntu 22.04.5 LTS is selected. Independent model/sensor verification, input-source work, pilot-data work and protocol work may begin now; successful hardware/model checks are required before the integrated baseline is accepted.
- [ ] **Austin:** Configure llama.cpp and implement persistent requests, bounded responses and errors in `src/vlm/client.py`; record build/model revisions.
- [ ] **Austin:** Verify available Ubuntu 22.04.5 LTS energy/battery telemetry, implement the selected adapter in `src/energy/monitor.py`, and confirm its units, coverage and limitations.
- [ ] **Alejandro:** Implement webcam and real-time recorded input in `src/capture/webcam.py` and `src/capture/replay.py`.
- [ ] **Alejandro:** Connect fixed-interval inference and minimal scene display in `app/main.py` and `app/state.py`.
- [ ] **James:** Define event classes and annotation rules in `data/README.md`; verify one public-data candidate and collect pilot clips.
- [ ] **Shawn:** Write initial controls, baselines and measurement protocol in `docs/methodology.md`; review relevant primary research sources.
- **Acceptance criteria:** Both input paths return descriptions, request errors are visible, and a short run produces interpretable energy measurements.
- **Verification / exit criteria:** Austin and Alejandro demonstrate a live request and replay; Shawn checks the sensor trace against runtime duration; James confirms pilot events are visually labelable.

### Phase 2 — Deliver a gated application and evaluation contracts (Week 2)

- **Outcome:** Event-driven inference works, annotation is underway, and sample files unblock the later evaluation tools.
- **Dependencies / entry criteria:** Phase 1 inference and telemetry work; pilot recordings and event definitions exist.
- [ ] **Alejandro:** Add downsampled/regional change scores, persistent references, hysteresis, cooldowns, refreshes and simple relevance rules in `src/gates/change.py` and `src/gates/scheduler.py`.
- [ ] **Alejandro:** Handle a busy VLM with latest-frame replacement and update `app/state.py` to suppress repeated notifications.
- [ ] **Austin:** Add prompt/response validation in `src/vlm/prompts.py` and baseline timing/token observations to request logs.
- [ ] **Austin and Alejandro:** Freeze first-version field names, time bases and units in `docs/data-contracts.md`; provide example annotations, predictions, power samples and manifests in `tests/fixtures/`.
- [ ] **James:** Finish the selected capture set, label observable event intervals, define grouped splits and manually score a small reference example.
- [ ] **Shawn:** Finalize repeat counts, randomized trial order, warm-up, missing-data rules and baseline configuration templates in `configs/` and `docs/methodology.md`.
- **Acceptance criteria:** A mixed-activity replay logs both skipped and admitted frames; all required example files validate and have known expected metrics.
- **Verification / exit criteria:** James and Shawn each load sample artifacts independently; the team checks one full event and its request/power timeline. Neither later tool requires live inference to start development.

### Phase 3 — Integrate budget control and owned evaluation tools (Week 3)

- **Outcome:** The complete cascade and first versions of James's and Shawn's tools work together.
- **Dependencies / entry criteria:** Phase 2 contracts and fixtures are stable; the gated application generates compatible logs.
- [ ] **Austin:** Calibrate per-mode energy estimates and implement allowance accumulation, admission, overhead accounting and explicit overrides in `src/energy/budget.py`.
- [ ] **Austin:** Measure output limits and prompt-cache correctness; add image/crop modes in `src/vlm/preprocessing.py`, retaining optimizations supported by actual measurements.
- [ ] **Alejandro:** Integrate budget admission, priority and input-mode decisions into `src/gates/scheduler.py`; complete a simple live/replay interface.
- [ ] **James:** Implement one-to-one temporal matching and label normalization in `src/evaluation/matching.py`.
- [ ] **James:** Implement aggregate metrics and event-level error exports in `src/evaluation/metrics.py` and `experiments/score_events.py`; compare output against manually scored fixtures.
- [ ] **Shawn:** Implement sequential repeated runs and manifests in `experiments/run_benchmarks.py`, saving unique trial outputs and recording failures.
- [ ] **Shawn:** Implement power/energy integration, latency summaries and initial tables/plots in `experiments/analyze_results.py`; consume James's metrics through documented files.
- [ ] **All:** Run a pilot comparison on development/validation data; correct contract or calculation errors before the final freeze.
- **Acceptance criteria:** James's command scores a pilot run, Shawn's commands execute repeats and produce a comparison artifact, and changing the energy allowance changes admissions with traceable accounting.
- **Verification / exit criteria:** Review the targeted tests below; cross-check an event report and an energy calculation by hand; freeze application settings, labels and evaluation rules for held-out tests.

### Phase 4 — Complete experiments, report and demonstration (Week 4)

- **Outcome:** The team can reproduce the measured energy-quality tradeoff and demonstrate the assistant.
- **Dependencies / entry criteria:** Phase 3 application and tools pass their checks; held-out data and experiment configurations are frozen.
- [ ] **James:** Run the event scorer on held-out data, review failures, and assess a blinded subset of descriptions for accuracy and unsupported claims.
- [ ] **Shawn:** Execute three repeated energy trials per main configuration and generate final tables, latency distributions and energy-quality plots.
- [ ] **Austin and Alejandro:** Complete a 30-minute stability run and fix blocking defects; record any changes that require rerunning affected experiments.
- [ ] **Austin and Shawn:** Report budget adherence, total versus incremental energy, sensor limitations and any infeasible budgets or overrides.
- [ ] **James and Shawn:** Draft dataset, method and results sections in `docs/final_report.md`; Austin and Alejandro supply and review architecture and implementation sections.
- [ ] **All:** Finish the demonstration and reproducibility instructions in `README.md`; have another member rerun one documented example.
- [ ] **Optional — James:** Add a viewer linking error rows to source frames and model responses after required scoring is complete.
- **Acceptance criteria:** Required CLI deliverables, repeated measurements, held-out results, report and demo are complete; limitations and negative findings are preserved.
- **Verification / exit criteria:** Recreate one final table from saved logs and reproduce one run from its manifest; confirm all four members' deliverables are represented in the final presentation.

### Work-item register (rev. 1)

One stub corresponds to each of the 27 existing phase checklist items. Dependencies below are item-level; a calendar week is not permission to bypass an unmet prerequisite. Planning completion does not mean implementation completion. Where tasks share a document, coordinate section ownership or integrate sequentially.

| Item | Phase | Owner | Outcome | Depends on | Priority | GitHub issue |
| --- | --- | --- | --- | --- | --- | --- |
| [1a](../energy-aware-vlm-implementation/phase-1-live-inference-and-measurement/1a-local-vlm-inference.md) | 1 | Austin | Persistent local VLM inference | None; independent discovery/build item | P0 | [#1](https://github.com/austincbaker/cap6411-cv-systems/issues/1) |
| [1b](../energy-aware-vlm-implementation/phase-1-live-inference-and-measurement/1b-power-telemetry.md) | 1 | Austin | Power and energy telemetry | None; independent discovery/build item | P0 | [#2](https://github.com/austincbaker/cap6411-cv-systems/issues/2) |
| [1c](../energy-aware-vlm-implementation/phase-1-live-inference-and-measurement/1c-webcam-and-replay.md) | 1 | Alejandro | Webcam and real-time replay sources | None; independent discovery/build item | P0 | [#3](https://github.com/austincbaker/cap6411-cv-systems/issues/3) |
| [1d](../energy-aware-vlm-implementation/phase-1-live-inference-and-measurement/1d-fixed-interval-application.md) | 1 | Alejandro | Fixed-interval baseline application | `1a`, `1b`, `1c` | P0 | [#4](https://github.com/austincbaker/cap6411-cv-systems/issues/4) |
| [1e](../energy-aware-vlm-implementation/phase-1-live-inference-and-measurement/1e-event-definitions-and-pilot-data.md) | 1 | James | Event definitions and pilot dataset | None; independent discovery/build item | P0 | [#5](https://github.com/austincbaker/cap6411-cv-systems/issues/5) |
| [1f](../energy-aware-vlm-implementation/phase-1-live-inference-and-measurement/1f-measurement-protocol-and-research.md) | 1 | Shawn | Measurement protocol and research review | None; independent discovery/build item | P1 | [#6](https://github.com/austincbaker/cap6411-cv-systems/issues/6) |
| [2a](../energy-aware-vlm-implementation/phase-2-gated-application-and-contracts/2a-change-and-relevance-gate.md) | 2 | Alejandro | Change gate and relevance rules | `1c`, `1d`, `1e` | P1 | [#7](https://github.com/austincbaker/cap6411-cv-systems/issues/7) |
| [2b](../energy-aware-vlm-implementation/phase-2-gated-application-and-contracts/2b-latest-frame-and-scene-state.md) | 2 | Alejandro | Latest-frame scheduling and scene state | `1d`, `2a` | P1 | [#8](https://github.com/austincbaker/cap6411-cv-systems/issues/8) |
| [2c](../energy-aware-vlm-implementation/phase-2-gated-application-and-contracts/2c-validated-vlm-responses.md) | 2 | Austin | Validated prompts, responses and inference logs | `1a`, `1e` | P1 | [#9](https://github.com/austincbaker/cap6411-cv-systems/issues/9) |
| [2d](../energy-aware-vlm-implementation/phase-2-gated-application-and-contracts/2d-evaluation-contracts-and-fixtures.md) | 2 | Austin and Alejandro | Versioned evaluation contracts and sample artifacts | `1b`, `1d`, `1e`, `1f`, `2c` | P0 | [#10](https://github.com/austincbaker/cap6411-cv-systems/issues/10) |
| [2e](../energy-aware-vlm-implementation/phase-2-gated-application-and-contracts/2e-annotated-dataset-and-splits.md) | 2 | James | Annotated dataset, grouped splits and scoring examples | `1e`, `2d` | P1 | [#11](https://github.com/austincbaker/cap6411-cv-systems/issues/11) |
| [2f](../energy-aware-vlm-implementation/phase-2-gated-application-and-contracts/2f-benchmark-configurations.md) | 2 | Shawn | Frozen benchmark protocol and configurations | `1f`, `2d` | P1 | [#12](https://github.com/austincbaker/cap6411-cv-systems/issues/12) |
| [3a](../energy-aware-vlm-implementation/phase-3-budget-control-and-evaluation-tools/3a-energy-budget-controller.md) | 3 | Austin | Calibrated energy-budget admission | `1b`, `2d`, `2f` | P1 | [#13](https://github.com/austincbaker/cap6411-cv-systems/issues/13) |
| [3b](../energy-aware-vlm-implementation/phase-3-budget-control-and-evaluation-tools/3b-inference-cost-ablations.md) | 3 | Austin | Measured image, output and cache ablations | `2c`, `2d`, `2f` | P2 | [#14](https://github.com/austincbaker/cap6411-cv-systems/issues/14) |
| [3c](../energy-aware-vlm-implementation/phase-3-budget-control-and-evaluation-tools/3c-budget-aware-application.md) | 3 | Alejandro | Integrated budget-aware application | `2a`, `2b`, `3a`, `3b` | P1 | [#15](https://github.com/austincbaker/cap6411-cv-systems/issues/15) |
| [3d](../energy-aware-vlm-implementation/phase-3-budget-control-and-evaluation-tools/3d-event-matching.md) | 3 | James | Deterministic one-to-one event matching | `2d`, `2e` | P1 | [#16](https://github.com/austincbaker/cap6411-cv-systems/issues/16) |
| [3e](../energy-aware-vlm-implementation/phase-3-budget-control-and-evaluation-tools/3e-event-scoring-cli.md) | 3 | James | Event metrics and scoring command | `3d` | P1 | [#17](https://github.com/austincbaker/cap6411-cv-systems/issues/17) |
| [3f](../energy-aware-vlm-implementation/phase-3-budget-control-and-evaluation-tools/3f-benchmark-runner.md) | 3 | Shawn | Repeated-trial benchmark runner | `1d`, `2d`, `2f` | P1 | [#18](https://github.com/austincbaker/cap6411-cv-systems/issues/18) |
| [3g](../energy-aware-vlm-implementation/phase-3-budget-control-and-evaluation-tools/3g-energy-analysis-and-reporting.md) | 3 | Shawn | Energy analysis, comparison tables and figures | `2d`, `2f`, `3e`, `3f` | P1 | [#19](https://github.com/austincbaker/cap6411-cv-systems/issues/19) |
| [3h](../energy-aware-vlm-implementation/phase-3-budget-control-and-evaluation-tools/3h-pilot-and-evaluation-freeze.md) | 3 | All | Pilot comparison and final evaluation freeze | `3a`, `3b`, `3c`, `3e`, `3f`, `3g` | P1 | [#20](https://github.com/austincbaker/cap6411-cv-systems/issues/20) |
| [4a](../energy-aware-vlm-implementation/phase-4-experiments-report-and-demonstration/4a-held-out-event-evaluation.md) | 4 | James | Held-out event and description evaluation | `3h` | P1 | [#21](https://github.com/austincbaker/cap6411-cv-systems/issues/21) |
| [4b](../energy-aware-vlm-implementation/phase-4-experiments-report-and-demonstration/4b-repeated-energy-experiments.md) | 4 | Shawn | Repeated energy trials and final plots | `3h` | P1 | [#22](https://github.com/austincbaker/cap6411-cv-systems/issues/22) |
| [4c](../energy-aware-vlm-implementation/phase-4-experiments-report-and-demonstration/4c-stability-and-defect-resolution.md) | 4 | Austin and Alejandro | Stability run and blocking defect resolution | `3h` | P1 | [#23](https://github.com/austincbaker/cap6411-cv-systems/issues/23) |
| [4d](../energy-aware-vlm-implementation/phase-4-experiments-report-and-demonstration/4d-budget-and-energy-findings.md) | 4 | Austin and Shawn | Budget adherence and energy findings | `4b`, `4c` | P1 | [#24](https://github.com/austincbaker/cap6411-cv-systems/issues/24) |
| [4e](../energy-aware-vlm-implementation/phase-4-experiments-report-and-demonstration/4e-research-report.md) | 4 | James and Shawn | Final research report with technical contributions | `4a`, `4b`, `4c`, `4d` | P1 | [#25](https://github.com/austincbaker/cap6411-cv-systems/issues/25) |
| [4f](../energy-aware-vlm-implementation/phase-4-experiments-report-and-demonstration/4f-demo-and-reproducibility.md) | 4 | All | Demonstration and independent reproduction | `4a`, `4b`, `4c`, `4e` | P1 | [#26](https://github.com/austincbaker/cap6411-cv-systems/issues/26) |
| [4g](../energy-aware-vlm-implementation/phase-4-experiments-report-and-demonstration/4g-failure-review-viewer.md) | 4 | James | Optional failure-review viewer (optional) | `3e` | P3 | [#27](https://github.com/austincbaker/cap6411-cv-systems/issues/27) |

### Tests

- [ ] `tests/test_inference_client.py` — Austin verifies bounded image requests and explicit transport failures using a fake service; selected-model compatibility still requires a live smoke check.
- [ ] `tests/test_energy_monitor.py` — Austin verifies timestamped raw/unit handling, missing sensors and collection cleanup using fake readers; actual sensor availability still requires a laptop check.
- [ ] `tests/test_capture_sources.py` — Alejandro verifies source timing, replay pacing and release behavior using controlled capture/clock inputs; actual camera and replay checks remain required.
- [ ] `tests/test_event_matching.py` — James verifies one-to-one matching, duplicates, wrong labels, tolerance boundaries, delayed availability and overlapping events using hand-scored cases.
- [ ] `tests/test_event_metrics.py` — James verifies empty predictions, no-event clips, false alarms and undefined metric handling.
- [ ] `tests/test_energy_analysis.py` — Shawn checks known constant-power traces, irregular sample intervals, supported rollover, gaps, unit conversions and idle subtraction.
- [ ] `tests/test_benchmark_runner.py` — Shawn verifies unique run outputs, repeat counts and failed-trial recording with a lightweight fake application.
- [ ] `tests/test_scheduler.py` — Alejandro verifies cooldown/refresh behavior, latest-frame replacement and no accumulated stale queue.
- [ ] `tests/test_budget.py` — Austin verifies admission under known costs, allowance refill, infeasible budgets and explicit overspend accounting.
- [ ] Establish the test setup during implementation and run `python -m pytest tests/` once these proposed files exist; document any repository-wide checks actually adopted.
- [ ] Manually verify changed-image processing with cache enabled, camera/model failures and long-run application stability.

### Documentation

- [ ] `README.md` — Install/run steps, hardware/backend selection, proposed CLI commands made concrete, and reproducibility example.
- [ ] `docs/data-contracts.md` — Schemas, units, timelines, sample fixtures, matching rules and missing-value behavior.
- [ ] `data/README.md` — Event definitions, recording protocol, grouped splits, provenance and data-sharing terms.
- [ ] `docs/methodology.md` — Controls, baselines, sensor domains, repeat strategy, energy normalization and frozen evaluation choices.
- [ ] `docs/final_report.md` — Research framing, related work, architecture, experiments, failures and practical limitations.

---

## Files to Change

All paths except the existing `README.md` are proposed targets. Check for an established implementation layout before creating them and adapt names without changing ownership or contracts.

| File | Change |
| --- | --- |
| `README.md` | Update the existing placeholder with setup, application and evaluation instructions. |
| `app/main.py`, `app/state.py` | Proposed new application entry point, scene state and notifications; Alejandro. |
| `src/capture/webcam.py`, `src/capture/replay.py` | Proposed new interchangeable video sources; Alejandro. |
| `src/vlm/client.py`, `src/vlm/prompts.py`, `src/vlm/preprocessing.py` | Proposed new inference interface, bounded output and selected image inputs; Austin. |
| `src/gates/change.py`, `src/gates/scheduler.py` | Proposed new gate and policy scheduling; Alejandro. |
| `src/energy/monitor.py`, `src/energy/budget.py` | Proposed new sensor integration and energy admission; Austin. |
| `src/evaluation/matching.py`, `src/evaluation/metrics.py` | Proposed new event matching, metrics and error reporting; James. |
| `experiments/score_events.py` | Proposed new scoring command; James. |
| `experiments/run_benchmarks.py`, `experiments/analyze_results.py` | Proposed new repeated-trial runner and report generator; Shawn. |
| `configs/` | Proposed baseline, gate and budget configurations; Austin/Alejandro define runtime fields, Shawn defines trial combinations. |
| `tests/fixtures/`, `docs/data-contracts.md` | Proposed shared contracts and handoff samples; Austin/Alejandro with James/Shawn review. |
| `tests/test_inference_client.py`, `tests/test_energy_monitor.py`, `tests/test_capture_sources.py` | Proposed targeted Phase 1 verification paths from direct expansion; Austin/Alejandro. |
| `tests/test_event_matching.py`, `tests/test_event_metrics.py` | Proposed evaluator correctness tests; James. |
| `tests/test_energy_analysis.py`, `tests/test_benchmark_runner.py` | Proposed energy math and experiment execution tests; Shawn. |
| `tests/test_scheduler.py`, `tests/test_budget.py` | Proposed scheduler and controller correctness tests; Alejandro/Austin. |
| `data/README.md`, `docs/methodology.md`, `docs/final_report.md` | Proposed data protocol, measurement method and report; James/Shawn coordinate, all contribute. |

---

## Risks / Considerations

- **R01 — Late handoff:** James and Shawn cannot complete tools if schemas arrive in Week 4. Deliver small valid fixtures by the end of Week 2 and coordinate any subsequent format changes.
- **R02 — Limited availability:** Give James the scorer and Shawn the runner/analyzer as bounded deliverables. Keep the viewer and extra visualizations optional; pair briefly on setup and review numerical correctness.
- **R03 — Hardware telemetry (rev. 1):** OS selection is resolved as Ubuntu 22.04.5 LTS; sensor availability remains an implementation-time check in `1b`. Do not assume Intel RAPL or a laptop battery merely from the OS. Keep domains separate and choose feasible budgets from actual measurements.
- **R04 — Scope growth:** Freeze core features at the end of Week 3. Defer learned gating and advanced visual/cache optimizations when required evaluation is at risk.
- **R05 — Small-model accuracy:** Separate gate misses from VLM errors, use a narrow task vocabulary and retain difficult/negative examples in the evaluation.
- **R06 — Unfair comparisons:** Include matched invocation counts and identical primary model settings; document overload, output limits and frame drops.
- **R07 — Data mismatch:** Public action or tracking labels may not describe the selected events. Annotate a small compatible subset rather than treating all existing labels as ground truth for this task.
- **R08 — Measurement noise:** Use long enough windows, repeat key trials, control power settings and include uncertainty. Replay and webcam overhead differ; compare policies within each input mode.

- **R09 — Missing repository conventions (rev. 4):** `AGENTS.md` now exists and records repository-wide conventions, but no committed dependency/test setup exists yet. Item `1a` documents the development setup in `README.md` and replaces the corresponding `AGENTS.md` TODOs; do not claim existing APIs or runnable commands until implemented. Live model/camera/sensor checks count only on the designated Ubuntu laptop.
- **R10 — Shared planning copies and files (rev. 1):** Keep the canonical master and reading copy synchronized. Coordinate edits to shared method/contract documents; later evaluation tools consume agreed files rather than reaching into application internals.

---

## Rollout

1. Demonstrate the fixed-interval baseline and telemetry on the selected laptop.
2. Introduce event gating with replay and inspect logged decisions before enabling budget constraints.
3. Add the budget controller and optimizations only after their behavior is measured and traceable.
4. Freeze configuration, execute held-out/repeated experiments, then demonstrate live operation and reproduce reports from saved logs.

## Rollback

- Keep fixed-interval and gate-only policies selectable through configuration so an unstable optimization can be disabled for diagnosis.
- Preserve raw logs, manifests, annotations and prior results. Write reruns to new directories and label superseded results rather than overwriting them.
- If schemas must change, update their version, fixtures and consumers together before repeating affected trials.

---

## Definition of Done

- [ ] All required phase outcomes and acceptance criteria are met; optional work is clearly identified.
- [ ] Austin's local inference/budget component and Alejandro's complete application work together on the selected laptop.
- [ ] James owns a tested scoring command used to generate final event-quality results.
- [ ] Shawn owns tested benchmark/report commands used to generate final energy/performance results.
- [ ] Relevant automated checks pass, along with the documented live and 30-minute stability checks.
- [ ] Main comparisons have three repeated measurements and use frozen held-out evaluation rules.
- [ ] Dataset provenance, measurement limitations, model/build settings and raw result locations are documented.
- [ ] Another team member reproduces one experiment and one report artifact from the instructions.
- [ ] Final report and presentation explain all four members' technical contributions and the measured energy-quality tradeoff.

---

## High-Level Change Summary

- **Target outcome:** A local webcam assistant detects meaningful changes under a configurable energy allowance, with measured quality and responsiveness.
- **Current state:** The conversation establishes a project concept and team roles; the repository contains a placeholder README and no verified implementation.
- **Major changes:**
  - Week 1 establishes persistent inference, webcam/replay input, a fixed-interval baseline and usable telemetry.
  - Week 2 adds event gating, labeled data and stable contracts that enable independent evaluation development.
  - Week 3 integrates Austin's energy control and Alejandro's application while James builds event scoring and Shawn builds benchmark/report automation.
  - Week 4 produces repeated energy trials, held-out quality results, a live demonstration and reproducible report artifacts.
- **Overall effect:** All four members own essential technical deliverables. The resulting application and evaluation tools establish when adaptive VLM inference saves energy, how it affects useful event detection, and where the approach fails.


---

## Revision log

### Revision 1 — 2026-10-25 — bounded audit and work-item scaffold

**Trigger:** Austin requested `generate-stubs-for-plan`, followed by `fill-plan-stubs`, and confirmed Ubuntu 22.04.5 LTS in response to the audit's platform question.

**Decision changes in dependency order:**

1. **Primary OS:** Open → Ubuntu 22.04.5 LTS (D11). Austin's answer settles the platform while leaving CPU/sensor availability to a measured check in `1b`.
2. **Existing design:** Unnumbered settled choices → D01–D10 references with unchanged scope and ownership. This provides stable context for item plans rather than reopening decisions.
3. **Implementation tracking:** Four coarse phase checklists → 27 linked work items with explicit item dependencies. The 26 required outcomes and optional viewer are unchanged.
4. **Plan authority:** One source document → canonical original plus synchronized implementation-directory reading copy. Adjust only relative links between copies and record future changes here.

**Phase structure:** Preserve all four phases and their weekly outcomes. No Phase 0 or production changes are added. The next dependency-ready planning wave is `1a`, `1b`, `1c`, `1e` and `1f`; `1d` depends on the first three runtime components.

**Risks:** R03 now distinguishes resolved OS selection from unverified sensors. R09 records absent repository conventions; R10 records shared-file/copy coordination. Remaining event/model/data checks stay in their assigned implementation items.

**Principles applied:** Preserve authoritative scope and named ownership, make dependencies explicit, keep stubs lean, verify hardware before energy claims, and avoid inventing existing code or conventions.


### Revision 2 — 2026-10-25 — direct stub-expansion follow-up

**Trigger:** Austin explicitly confirmed expansion of the five independent Phase 1 starting items. Direct expansion added implementation detail without changing the settled design or implementing application code.

**Stubs expanded this run** (5):

- `phase-1-live-inference-and-measurement/1a-local-vlm-inference.md` — Austin: Persistent local VLM inference.
- `phase-1-live-inference-and-measurement/1b-power-telemetry.md` — Austin: Power and energy telemetry.
- `phase-1-live-inference-and-measurement/1c-webcam-and-replay.md` — Alejandro: Webcam and real-time replay sources.
- `phase-1-live-inference-and-measurement/1e-event-definitions-and-pilot-data.md` — James: Event definitions and pilot dataset.
- `phase-1-live-inference-and-measurement/1f-measurement-protocol-and-research.md` — Shawn: Measurement protocol and research review.

**Resolved questions** (0): No new material planning question was surfaced, so the question-resolution phase was skipped. Existing model compatibility, sensor availability, task-vocabulary and interval-selection checks remain assigned implementation work in their original Open questions sections. They have not been marked complete or silently resolved.

**Cross-stub resolutions** (0): None. Existing time-base, energy-domain and file-contract choices are applied consistently; final schema names remain item `2d`'s handoff.

**Blocked or needs-review** (0): None of the selected plans is blocked or requires human-content review. Hardware/model smoke checks may still reveal implementation blockers later.

**Implementation detail added:** Ordered steps, proposed interfaces and file responsibilities, provenance, error/cleanup behavior, focused tests and handoff expectations. Three proposed Phase 1 test filenames are added to the tests/file-impact lists as verification detail; no new product capability is introduced.

**Tracking preserved:** Every original selected-stub byte preceding the expansion sentinel, including its Definition-of-Done matrix, remains unchanged. All implementation statuses remain `⬜ Not started`; all evidence cells remain `—`. The other 22 stubs are unchanged and deferred.

**Next deliverable:** Implement `1a`, `1b`, `1c`, `1e` and `1f` from their expanded plans. Item `1d` follows implemented `1a`–`1c`; later planning expansion should follow actual item readiness. Keep the canonical TODO and the implementation-directory reading copy synchronized.


### Revision 3 — 2026-10-27 — live GitHub tracking

**Trigger:** Austin requested blocked-by relationships, priorities and assignments for all implementation issues.

**Remote state before this change:** The repository had no GitHub issues. The 27 local item plans were published as issues #1–#27 so the requested tracking could be applied. Issue bodies retain the item tasks, acceptance criteria and any expanded implementation notes.

**Tracking added:** 59 native prerequisite relationships, one priority label on each issue, and the named owner assignments. Counts are P0: 6, P1: 19, P2: 1, P3: 1. Dependencies follow the existing graph without adding, removing or reprioritizing its edges.

**Local synchronization:** Each item now records its live URL, priority and live prerequisite links. The work-item register and implementation index expose the same metadata. Native GitHub relationships provide blocked indicators; local implementation statuses, checkboxes and completion-evidence matrices are preserved.

**Scope unchanged:** No application code was implemented. No issue was marked complete, and the P2 ablation retains its existing prerequisite/required-work role. The five independent starting items remain `1a`, `1b`, `1c`, `1e` and `1f`.


### Revision 4 — 2026-10-27 — repository AGENTS.md

**Trigger:** Austin added a repository `AGENTS.md` and requested a review. Its project-specific sections had been copied from an unrelated repository and were rewritten for this project.

**Changes:** The planning-quality note and R09 now record that `AGENTS.md` exists while dependency, run and test commands remain TODO until item `1a`. `AGENTS.md` adds plan-document authority, item/issue tracking conventions, ownership boundaries, the gitignored external `.cache/llama.cpp/` checkout, and data/measurement-integrity rules taken from this plan. It also states that live smoke checks are acceptance evidence produced only on the designated laptop, and that `README.md` remains the single source for setup steps.

**Scope unchanged:** No decision, dependency edge, owner or priority changed. No application code was implemented and all implementation statuses are unchanged.
