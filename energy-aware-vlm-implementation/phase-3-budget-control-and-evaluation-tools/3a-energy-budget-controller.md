# 3a — Calibrated energy-budget admission

**Live issue:** [#13](https://github.com/austincbaker/cap6411-cv-systems/issues/13)
**Priority:** P1 (`priority:P1`)
**GitHub blocked by:** [1b (#2)](https://github.com/austincbaker/cap6411-cv-systems/issues/2), [2d (#10)](https://github.com/austincbaker/cap6411-cv-systems/issues/10), [2f (#12)](https://github.com/austincbaker/cap6411-cv-systems/issues/12)

**Phase**: 3 — Integrate budget control and owned evaluation tools
**Status**: 🟡 Controller and calibration procedure built (PR #48: token bucket in `src/budget/`, `energy_suite.py calibrate`); tested on fixture costs, live costs await the MacBook energy suite; no priority overrides
**Plan refs**: [Master plan](../plan.md#phase-3--integrate-budget-control-and-owned-evaluation-tools-week-3); D08, D11; R03, R08
**Depends on**: [1b](../phase-1-live-inference-and-measurement/1b-power-telemetry.md), [2d](../phase-2-gated-application-and-contracts/2d-evaluation-contracts-and-fixtures.md), [2f](../phase-2-gated-application-and-contracts/2f-benchmark-configurations.md)
**Blocks**: [3c](../phase-3-budget-control-and-evaluation-tools/3c-budget-aware-application.md), [3h](../phase-3-budget-control-and-evaluation-tools/3h-pilot-and-evaluation-freeze.md)

## Scope

Owner: Austin, with Shawn validating the accounting. Build the calibration procedure and enforce a feasible incremental energy allowance above measured idle. Controller logic is developed and tested against fixture costs; live per-mode and gate-overhead calibration runs in `3c` once the gate and application exist (rev. 6). Account for continuous gate overhead and make priority exceptions visible.

## Tasks

- [x] Implement the calibration procedure and cost inputs for per-mode calls and continuous gate overhead, validated against fixture costs.
- [x] Implement allowance accumulation, cost admission and actual-cost reconciliation.
- [ ] Record infeasible budgets, priority overrides and resulting budget deviation.

## Files to be touched

- `src/energy/budget.py` — Proposed admission and energy accounting.
- `src/energy/monitor.py` — Measured-cost input integration as needed.
- `tests/test_budget.py` — Known-cost, refill and overspend cases.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

None newly surfaced. Apply the parent plan and resolve measured settings in the prerequisite items.

## Acceptance criteria

- [x] Changing a feasible allowance changes admissions and is visible in logs.
- [ ] The measured idle floor, gate overhead and override costs are explicitly accounted for.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Implement the calibration procedure and cost inputs for per-mode calls and continuous gate overhead, validated against fixture costs. | [Tasks](#tasks) | The procedure accepts measured or fixture costs with their sensor domain; live values come from `3c`. | src/budget/controller.py:100, scripts/analyze_energy_suite.py:291, configs/budget_costs.json (placeholder), tests/test_budget.py:150, tests/test_budget.py:357 (the gate runs in the idle pipeline, so its overhead is in the idle floor, not a separate cost) | 🟢 |
| 2 | Implement allowance accumulation, cost admission and actual-cost reconciliation. | [Tasks](#tasks) | Known costs and time increments produce predictable admit/skip decisions. | src/budget/controller.py:231, src/budget/controller.py:271, tests/test_budget.py:43, tests/test_budget.py:55, tests/test_budget.py:113, tests/test_budget.py:130 | 🟢 |
| 3 | Record infeasible budgets, priority overrides and resulting budget deviation. | [Tasks](#tasks) | Overspend and unavailable accounting cannot masquerade as adherence. | src/budget/controller.py:309, tests/test_budget.py:402 (estimated and measured spend are reported against each budget; no priority overrides exist) | 🟡 |
| 4 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

<!-- impl-notes-anchor -->
