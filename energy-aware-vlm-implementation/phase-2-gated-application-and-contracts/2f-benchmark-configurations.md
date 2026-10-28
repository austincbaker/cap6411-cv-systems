# 2f — Benchmark protocol and configuration templates

**Live issue:** [#12](https://github.com/austincbaker/cap6411-cv-systems/issues/12)
**Priority:** P1 (`priority:P1`)
**GitHub blocked by:** [1f (#6)](https://github.com/austincbaker/cap6411-cv-systems/issues/6), [2d (#10)](https://github.com/austincbaker/cap6411-cv-systems/issues/10)

**Phase**: 2 — Deliver a gated application and evaluation contracts
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-2--deliver-a-gated-application-and-evaluation-contracts-week-2); D03, D08, D11; R06, R08
**Depends on**: [1f](../phase-1-live-inference-and-measurement/1f-measurement-protocol-and-research.md), [2d](../phase-2-gated-application-and-contracts/2d-evaluation-contracts-and-fixtures.md)
**Blocks**: [3a](../phase-3-budget-control-and-evaluation-tools/3a-energy-budget-controller.md), [3b](../phase-3-budget-control-and-evaluation-tools/3b-inference-cost-ablations.md), [3f](../phase-3-budget-control-and-evaluation-tools/3f-benchmark-runner.md), [3g](../phase-3-budget-control-and-evaluation-tools/3g-energy-analysis-and-reporting.md)

## Scope

Owner: Shawn. Turn pilot observations into a version-1 benchmark matrix, controls and configuration templates; item `3h` performs the only evaluation freeze (rev. 6). Define rules, not values, for settings that need the integrated application, such as deriving the matched-invocation rate from the cascade's mean rate on development data. Keep a small set of main long-run comparisons while retaining shorter ablations and a matched-invocation baseline.

## Tasks

- [ ] Specify policies, repeats, randomized order, warm-up and measurement windows from pilot results.
- [ ] Prepare configuration templates and define failure, overload and missing-sensor treatment.
- [ ] Document which trials receive long energy measurements and which are shorter ablations.
- [ ] Compute total laptop-hours for the final matrix, including unplugged-battery run limits and a rerun reserve, and cap configurations or durations to finish by 2026-11-22.

## Files to be touched

- `configs/` — Proposed baseline, gate and budget experiment configurations.
- `docs/methodology.md` — Frozen pilot-informed experimental protocol.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

None newly surfaced. Apply the parent plan and resolve measured settings in the prerequisite items.

## Acceptance criteria

- [ ] Main comparisons include idle, fixed, matched invocation, gate and budget-aware modes.
- [ ] Configuration differences are explicit and long-run repeat requirements are feasible.
- [ ] Templates state the rules `3h` uses to fix the remaining values; nothing is labeled frozen before `3h`.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Specify policies, repeats, randomized order, warm-up and measurement windows from pilot results. | [Tasks](#tasks) | The trial checklist identifies the same model/hardware/settings across primary comparisons. | — | ⬜ |
| 2 | Prepare configuration templates and define failure, overload and missing-sensor treatment. | [Tasks](#tasks) | Each planned run has explicit input, policy, duration and output expectations. | — | ⬜ |
| 3 | Document which trials receive long energy measurements and which are shorter ablations. | [Tasks](#tasks) | Three repeats are planned for each main energy configuration without overloading the schedule. | — | ⬜ |
| 4 | Compute total laptop-hours for the final matrix, including unplugged-battery run limits and a rerun reserve, and cap configurations or durations to finish by 2026-11-22. | [Tasks](#tasks) | The schedule fits the Week 4 window with a stated rerun reserve, and controls cover AC/battery state, start charge, Windows power plan and background activity. | — | ⬜ |
| 5 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

<!-- impl-notes-anchor -->
