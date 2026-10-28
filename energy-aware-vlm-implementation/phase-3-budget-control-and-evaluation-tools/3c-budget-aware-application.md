# 3c — Integrated budget-aware application

**Live issue:** [#15](https://github.com/austincbaker/cap6411-cv-systems/issues/15)
**Priority:** P1 (`priority:P1`)
**GitHub blocked by:** [2a (#7)](https://github.com/austincbaker/cap6411-cv-systems/issues/7), [2b (#8)](https://github.com/austincbaker/cap6411-cv-systems/issues/8), [3a (#13)](https://github.com/austincbaker/cap6411-cv-systems/issues/13)

**Phase**: 3 — Integrate budget control and owned evaluation tools
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-3--integrate-budget-control-and-owned-evaluation-tools-week-3); D04, D05, D08, D09; R04
**Depends on**: [2a](../phase-2-gated-application-and-contracts/2a-change-and-relevance-gate.md), [2b](../phase-2-gated-application-and-contracts/2b-latest-frame-and-scene-state.md), [3a](../phase-3-budget-control-and-evaluation-tools/3a-energy-budget-controller.md)
**Blocks**: [3h](../phase-3-budget-control-and-evaluation-tools/3h-pilot-and-evaluation-freeze.md)

## Scope

Owner: Alejandro. Connect the gate, budget admission and selected inference modes into a usable application. Preserve fixed-interval and gate-only policies for fair comparisons and fallback diagnosis. Image and output modes come from configuration using `2c` defaults; `3b` results inform `3h`, not this item (rev. 6). Keep the display minimal; UI polish does not block integration.

## Tasks

- [ ] Integrate relevance/priority and budget decisions with image/output mode selection.
- [ ] Finish a simple live/replay display showing confirmed observations and status.
- [ ] Verify failure handling and bounded pending work across all policies.
- [ ] Run live per-mode and gate-overhead calibration for the `3a` controller on development data, with Austin measuring.
- [ ] Complete a stability smoke run of the integrated application, with the duration set in `2f`.

## Files to be touched

- `src/gates/scheduler.py` — Full cascade orchestration.
- `app/main.py` — Selectable policies and runtime wiring.
- `app/state.py` — Scene and budget/status display.
- `tests/test_scheduler.py` — Integrated admission and pending-work behavior.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

None newly surfaced. Apply the parent plan and resolve measured settings in the prerequisite items.

## Acceptance criteria

- [ ] Fixed, event-driven and budget-aware policies run through the same application.
- [ ] Budget skips and failures remain visible without corrupting confirmed scene state.
- [ ] A stability smoke run passes before `3h` begins.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Integrate relevance/priority and budget decisions with image/output mode selection. | [Tasks](#tasks) | Every admitted or skipped request records its effective policy and mode. | — | ⬜ |
| 2 | Finish a simple live/replay display showing confirmed observations and status. | [Tasks](#tasks) | The UI distinguishes current successful observations from stale or failed updates. | — | ⬜ |
| 3 | Verify failure handling and bounded pending work across all policies. | [Tasks](#tasks) | Timeouts, exhausted allowance and camera errors do not hang the application. | — | ⬜ |
| 4 | Run live per-mode and gate-overhead calibration for the `3a` controller on development data, with Austin measuring. | [Tasks](#tasks) | Calibrated costs are recorded with sensor domain, AC/battery state and run identity. | — | ⬜ |
| 5 | Complete a stability smoke run of the integrated application, with the duration set in `2f`. | [Tasks](#tasks) | The smoke run finishes with bounded work and clean shutdown; `3h` requires it. | — | ⬜ |
| 6 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

<!-- impl-notes-anchor -->
