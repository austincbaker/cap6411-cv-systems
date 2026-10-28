# 3f — Repeated-trial benchmark runner

**Live issue:** [#18](https://github.com/austincbaker/cap6411-cv-systems/issues/18)
**Priority:** P1 (`priority:P1`)
**GitHub blocked by:** [1d (#4)](https://github.com/austincbaker/cap6411-cv-systems/issues/4), [2d (#10)](https://github.com/austincbaker/cap6411-cv-systems/issues/10), [2f (#12)](https://github.com/austincbaker/cap6411-cv-systems/issues/12)

**Phase**: 3 — Integrate budget control and owned evaluation tools
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-3--integrate-budget-control-and-owned-evaluation-tools-week-3); D02, D06, D08; R02, R06
**Depends on**: [1d](../phase-1-live-inference-and-measurement/1d-fixed-interval-application.md), [2d](../phase-2-gated-application-and-contracts/2d-evaluation-contracts-and-fixtures.md), [2f](../phase-2-gated-application-and-contracts/2f-benchmark-configurations.md)
**Blocks**: [3g](../phase-3-budget-control-and-evaluation-tools/3g-energy-analysis-and-reporting.md), [3h](../phase-3-budget-control-and-evaluation-tools/3h-pilot-and-evaluation-freeze.md)

## Scope

Owner: Shawn, with Austin/Alejandro supplying the runnable application interface. Automate sequential benchmark trials from saved configurations. Preserve unique outputs and provenance so repeated runs can be audited and resumed deliberately.

## Tasks

- [ ] Load validated experiment configurations and generate a repeatable randomized trial order.
- [ ] Execute trials sequentially and store unique manifests and log locations.
- [ ] Handle failed or interrupted trials and verify behavior with a fake application.

## Files to be touched

- `experiments/run_benchmarks.py` — Proposed repeated-run command.
- `tests/test_benchmark_runner.py` — Fake-application repeat/failure/output tests.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

None newly surfaced. Apply the parent plan and resolve measured settings in the prerequisite items.

## Acceptance criteria

- [ ] One command runs a selected policy/video matrix with the configured repeat count.
- [ ] Outputs remain isolated and failures lead to a non-success result with preserved evidence.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Load validated experiment configurations and generate a repeatable randomized trial order. | [Tasks](#tasks) | The order/repeat plan is saved with its seed and configuration. | — | ⬜ |
| 2 | Execute trials sequentially and store unique manifests and log locations. | [Tasks](#tasks) | Each trial records start/end, input/policy/build and success/failure without overwriting prior runs. | — | ⬜ |
| 3 | Handle failed or interrupted trials and verify behavior with a fake application. | [Tasks](#tasks) | Failed trials are marked incomplete and do not silently enter successful aggregates. | — | ⬜ |
| 4 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

<!-- impl-notes-anchor -->
