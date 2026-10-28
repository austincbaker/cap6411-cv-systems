# 1f — Measurement protocol and research review

**Live issue:** [#6](https://github.com/austincbaker/cap6411-cv-systems/issues/6)
**Priority:** P1 (`priority:P1`)
**GitHub blocked by:** None

**Phase**: 1 — Establish live inference and measurement
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-1--establish-live-inference-and-measurement-week-1); D03, D08, D10, D11; R03, R06, R08
**Depends on**: None; independent Phase 1 discovery/build item
**Blocks**: [2d](../phase-2-gated-application-and-contracts/2d-evaluation-contracts-and-fixtures.md), [2f](../phase-2-gated-application-and-contracts/2f-benchmark-configurations.md)

## Scope

Owner: Shawn. Establish measurement controls and research framing before benchmark implementation. Define fair comparisons and distinguish whole-system battery draw from processor-domain energy.

## Tasks

- [ ] Review primary research and identify the runtime-scheduling contribution without repeating unverified claims.
- [ ] Draft sensor-domain, warm-up, replay-speed and environmental controls.
- [ ] Specify initial fixed, idle and matched-invocation comparisons and a trial checklist.

## Files to be touched

- `docs/methodology.md` — Proposed measurement protocol and research references.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

- [ ] Select feasible fixed intervals and trial durations after Week 1 latency and telemetry measurements; do not treat initial guesses as frozen settings.

## Acceptance criteria

- [ ] Protocol distinguishes total/incremental energy and battery/processor domains.
- [ ] The baseline plan includes matched invocation counts, real-time replay and recorded failures.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Review primary research and identify the runtime-scheduling contribution without repeating unverified claims. | [Tasks](#tasks) | Related-work notes cite sources and separate architectural efficiency from always-on energy scheduling. | — | ⬜ |
| 2 | Draft sensor-domain, warm-up, replay-speed and environmental controls. | [Tasks](#tasks) | The protocol names what is measured, held fixed and reported as unavailable. | — | ⬜ |
| 3 | Specify initial fixed, idle and matched-invocation comparisons and a trial checklist. | [Tasks](#tasks) | The team can execute a pilot comparison without guessing experimental controls. | — | ⬜ |
| 4 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

## Implementation notes

### Context and boundaries

Shawn owns research framing and the measurement protocol. Apply D03 (same primary model/backend), D08 (fair energy comparisons), D10 (four-week delivery) and D11 (Ubuntu). R03, R06 and R08 cover sensor availability, comparison bias and measurement noise.

There is no existing protocol in the repository. Create `docs/methodology.md`, coordinating its sensor section with Austin's item 1b. This item produces usable pilot instructions; item 2f freezes configurations and items 3f/3g are Shawn's coding deliverables. Keep the pilot independent of unfinished automation.

### Ordered implementation breakdown

1. State the research questions in observable terms: energy saved, event quality retained, response delay and adherence to a feasible allowance. Treat savings as an experimental outcome and preserve negative results.
2. Read the three supplied starting papers and relevant primary work on conditional/streaming perception and edge energy. Record each paper's actual task/hardware and how it relates to runtime scheduling; verify claims before repeating the earlier conversation's numbers or publication details.
3. Define the standard test configuration: Ubuntu release, actual laptop/CPU, primary model/quantization, llama.cpp build, CPU backend, power mode, display state, source video and generation settings. Record unknown fields as pending checks.
4. Define separate measurement conditions for webcam and replay. For policy comparisons, use the same real-time recording on the same device; document that decoding overhead and webcam overhead differ.
5. Agree the sensor-domain description with Austin: package energy and battery/whole-laptop draw must be separate outputs. Document supported units, counter ranges, collection cadence, update granularity and data gaps without assuming the laptop exposes every metric.
6. Define an idle condition with camera/replay and model residency aligned to the comparison workload. A no-VLM-call run should still include acquisition, ordinary logging/display work and the loaded model; describe gate-only overhead separately where measured.
7. List the initial policies: idle/no calls, several feasible fixed intervals, random or fixed sampling at a cascade's average invocation count, change/relevance gating and the full budget-aware cascade. Freeze the primary model and output bound while testing temporal selection.
8. Specify warm-up and measured-window boundaries, including treatment of in-flight calls at the end. Record setup and shutdown outside the primary interval; do not credit responses that become available after the declared scoring horizon as timely detections.
9. Draft a repeat/randomization checklist for the main configurations, retaining three repeated final measurements per main comparison. Record trial order and environmental conditions so later variability is interpretable.
10. Use pilot latency and sensor update behavior to choose feasible sampling intervals and long-run durations in item 2f. Record overload/skipped calls for infeasible fixed intervals; do not quietly turn them into a different baseline.
11. Define failure and exclusion handling before final tests: incomplete inputs, sensor gaps, interrupted trials, model failures and changed power states remain visible. Track successful inference count separately from attempted count, while retaining energy spent by failed attempts.
12. Write down energy calculations and dimensions. For an observed interval T seconds and E joules, mean power is E/T watts, total energy is E/3600 Wh, and the hourly normalized rate is E/T Wh/hour. Subtract idle only with compatible domains and conditions; retain a negative noisy estimate rather than silently clipping it.
13. Define the link to James's event outputs: match by run/video identity, use response availability for delay, preserve failed predictions and report false/missed/duplicate events. Add a plan for blinded description review without making text-similarity scores the sole quality measure.
14. Walk through one pilot run with Austin/Alejandro using the written checklist. Record the actual timings, incomplete checks and changes needed before item 2f freezes the protocol.

### Pilot checklist and artifact handoff

Each pilot trial should leave a configuration summary, source/video identity, runtime/model/backend identity, start/end timing, sensor metadata and raw trace, request/response records, completion status and notes about deviations. The exact manifest and log fields are finalized in item 2d; the checklist should not invent a competing permanent schema.

Keep recording IDs and source-video timestamps compatible with James's annotations. Matched-invocation comparisons must use counts derived from development/calibration runs or a prespecified selection rule; do not tune the final baseline using held-out quality results.

Shawn's later runner will execute this procedure sequentially with unique run directories. His analyzer will integrate samples, join James's metrics and regenerate report artifacts. Describe those inputs/outputs here, while leaving implementation to items 3f/3g.

### Verification and acceptance interpretation

A second team member should be able to execute a short trial from the checklist and identify the relevant raw artifacts. Hand-check a constant-power arithmetic example and one idle subtraction using the same units. Verify that package energy is never labeled whole-system energy, and that reporting a short trace normalized to an hour is not presented as a measured one-hour battery run.

The original open question about exact intervals/durations is intentionally resolved by pilot evidence in item 2f. This item is complete with a coherent draft protocol and known pending measurements; it does not require the benchmark runner to exist.

### Files and evidence recap

- `docs/methodology.md` — proposed research notes, controls, baselines, timing/energy definitions, pilot checklist and explicit limitations.
- Austin contributes the sensor subsection from item 1b; Shawn maintains the complete protocol and coordinates any changes before freezing it.

No additional software framework, operating-system backend or measurement infrastructure is introduced by this expansion. Keep the report reproducible with the available laptop and preserve unsupported measurements as unavailable.
