# 2b — Latest-frame scheduling and scene state

**Live issue:** [#8](https://github.com/austincbaker/cap6411-cv-systems/issues/8)
**Priority:** P1 (`priority:P1`)
**GitHub blocked by:** [1d (#4)](https://github.com/austincbaker/cap6411-cv-systems/issues/4), [2a (#7)](https://github.com/austincbaker/cap6411-cv-systems/issues/7), [2c (#9)](https://github.com/austincbaker/cap6411-cv-systems/issues/9)

**Phase**: 2 — Deliver a gated application and evaluation contracts
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-2--deliver-a-gated-application-and-evaluation-contracts-week-2); D05, D06; R05
**Depends on**: [1d](../phase-1-live-inference-and-measurement/1d-fixed-interval-application.md), [2a](../phase-2-gated-application-and-contracts/2a-change-and-relevance-gate.md), [2c](../phase-2-gated-application-and-contracts/2c-validated-vlm-responses.md)
**Blocks**: [3c](../phase-3-budget-control-and-evaluation-tools/3c-budget-aware-application.md)

## Scope

Owner: Alejandro. Bound inference work to one active request and one pending latest frame. Maintain confirmed scene state and suppress redundant notifications while preserving failures and stale-observation status. Own the shared event derivation (rev. 6): normalize validated per-frame observations, difference them against confirmed state and emit predicted events; every policy, including fixed-interval, uses this same derivation.

## Tasks

- [ ] Replace pending work with the latest eligible frame while inference is busy.
- [ ] Update confirmed observations only from successful validated inference and suppress repeated unchanged notices.
- [ ] Derive predicted events by normalizing observations and differencing them against confirmed state, shared by all policies.
- [ ] Add clean stop behavior and tests for slow requests, cooldown and refresh interactions.

## Files to be touched

- `src/gates/scheduler.py` — Busy/request lifecycle and latest-frame logic.
- `app/state.py` — Confirmed observations and notification suppression.
- `tests/test_scheduler.py` — Slow-request and state-transition cases.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

None newly surfaced. Apply the parent plan and resolve measured settings in the prerequisite items.

## Acceptance criteria

- [ ] At most one request and one pending frame exist at a time.
- [ ] Repeated unchanged observations do not generate repeated event notifications.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Replace pending work with the latest eligible frame while inference is busy. | [Tasks](#tasks) | The pending queue never exceeds one frame. | — | ⬜ |
| 2 | Update confirmed observations only from successful validated inference and suppress repeated unchanged notices. | [Tasks](#tasks) | Invalid responses leave the previous confirmed state intact. | — | ⬜ |
| 3 | Add clean stop behavior and tests for slow requests, cooldown and refresh interactions. | [Tasks](#tasks) | Slow inference does not replay a stale backlog after it finishes. | — | ⬜ |
| 4 | Derive predicted events by normalizing observations and differencing them against confirmed state, shared by all policies. | [Tasks](#tasks) | Fixed-interval and gated runs emit prediction records through the same derivation, documented in the `2d` prediction contract. | — | ⬜ |
| 5 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

<!-- impl-notes-anchor -->
