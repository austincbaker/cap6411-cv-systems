# 1d — Fixed-interval baseline application

**Live issue:** [#4](https://github.com/austincbaker/cap6411-cv-systems/issues/4)
**Priority:** P0 (`priority:P0`)
**GitHub blocked by:** [1a (#1)](https://github.com/austincbaker/cap6411-cv-systems/issues/1), [1b (#2)](https://github.com/austincbaker/cap6411-cv-systems/issues/2), [1c (#3)](https://github.com/austincbaker/cap6411-cv-systems/issues/3)

**Phase**: 1 — Establish live inference and measurement
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-1--establish-live-inference-and-measurement-week-1); D03, D05, D06, D08; R06
**Depends on**: [1a](../phase-1-live-inference-and-measurement/1a-local-vlm-inference.md), [1b](../phase-1-live-inference-and-measurement/1b-power-telemetry.md), [1c](../phase-1-live-inference-and-measurement/1c-webcam-and-replay.md)
**Blocks**: [2a](../phase-2-gated-application-and-contracts/2a-change-and-relevance-gate.md), [2b](../phase-2-gated-application-and-contracts/2b-latest-frame-and-scene-state.md), [2d](../phase-2-gated-application-and-contracts/2d-evaluation-contracts-and-fixtures.md), [3f](../phase-3-budget-control-and-evaluation-tools/3f-benchmark-runner.md)

## Scope

Owner: Alejandro, integrating Austin's inference and telemetry. Build the first complete application using a fixed inference interval. Produce a minimal display and logs that establish the comparison baseline before adaptive policies are added.

## Tasks

- [ ] Connect webcam/replay, persistent inference and telemetry in the application entry point.
- [ ] Implement configurable fixed-interval invocation and minimal scene display.
- [ ] Record failures, measured duration and overload rather than building an unbounded work queue.

## Files to be touched

- `app/main.py` — Proposed baseline orchestration.
- `app/state.py` — Proposed latest observation and display state.
- `README.md` — Baseline run instructions.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

None newly surfaced. Apply the parent plan and resolve measured settings in the prerequisite items.

## Acceptance criteria

- [ ] The same entry point runs camera or replay with a configurable fixed interval.
- [ ] A short end-to-end run produces response and telemetry artifacts with declared timing.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Connect webcam/replay, persistent inference and telemetry in the application entry point. | [Tasks](#tasks) | One source can drive a recorded baseline run with response and sensor observations. | — | ⬜ |
| 2 | Implement configurable fixed-interval invocation and minimal scene display. | [Tasks](#tasks) | Changing the interval changes invocation timing and visible results. | — | ⬜ |
| 3 | Record failures, measured duration and overload rather than building an unbounded work queue. | [Tasks](#tasks) | A slow request produces documented dropped/skipped work and the application shuts down cleanly. | — | ⬜ |
| 4 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

<!-- impl-notes-anchor -->
