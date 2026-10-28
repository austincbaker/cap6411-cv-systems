# 4d — Budget adherence and energy findings

**Live issue:** [#24](https://github.com/austincbaker/cap6411-cv-systems/issues/24)
**Priority:** P1 (`priority:P1`)
**GitHub blocked by:** [4b (#22)](https://github.com/austincbaker/cap6411-cv-systems/issues/22), [4c (#23)](https://github.com/austincbaker/cap6411-cv-systems/issues/23)

**Phase**: 4 — Complete experiments, report and demonstration
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-4--complete-experiments-report-and-demonstration-week-4); D08, D11; R03, R08
**Depends on**: [4b](../phase-4-experiments-report-and-demonstration/4b-repeated-energy-experiments.md), [4c](../phase-4-experiments-report-and-demonstration/4c-stability-and-defect-resolution.md)
**Blocks**: [4e](../phase-4-experiments-report-and-demonstration/4e-research-report.md)

## Scope

Owners: Austin and Shawn. Interpret the energy controller's observed behavior and the system's measured energy costs. Report adherence, exceptions, domain limits and the fixed idle floor rather than implying all energy is controllable.

## Tasks

- [ ] Compare target allowances with measured consumption using the declared accounting domain.
- [ ] Separate idle/gate/inference costs where measurements support attribution.
- [ ] Document overspend, infeasible budgets and telemetry uncertainty.

## Files to be touched

- `docs/final_report.md` — Budget adherence and limitations.
- `results/` — Generated budget/accounting summaries.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

None newly surfaced. Apply the parent plan and resolve measured settings in the prerequisite items.

## Acceptance criteria

- [ ] Budget claims account for override decisions and continuous overhead.
- [ ] The report separates processor savings, laptop savings and normalized hourly estimates.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Compare target allowances with measured consumption using the declared accounting domain. | [Tasks](#tasks) | Deviation calculations use compatible units, domains and windows. | — | ⬜ |
| 2 | Separate idle/gate/inference costs where measurements support attribution. | [Tasks](#tasks) | Unsupported attribution is marked unavailable rather than inferred as fact. | — | ⬜ |
| 3 | Document overspend, infeasible budgets and telemetry uncertainty. | [Tasks](#tasks) | The findings explain when the controller respects or exceeds the configured target. | — | ⬜ |
| 4 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

<!-- impl-notes-anchor -->
