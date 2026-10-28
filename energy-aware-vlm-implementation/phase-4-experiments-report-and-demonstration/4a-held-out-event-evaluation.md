# 4a — Held-out event and description evaluation

**Live issue:** [#21](https://github.com/austincbaker/cap6411-cv-systems/issues/21)
**Priority:** P1 (`priority:P1`)
**GitHub blocked by:** [3h (#20)](https://github.com/austincbaker/cap6411-cv-systems/issues/20), [4b (#22)](https://github.com/austincbaker/cap6411-cv-systems/issues/22)

**Phase**: 4 — Complete experiments, report and demonstration
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-4--complete-experiments-report-and-demonstration-week-4); D07; R05, R07
**Depends on**: [3h](../phase-3-budget-control-and-evaluation-tools/3h-pilot-and-evaluation-freeze.md), [4b](../phase-4-experiments-report-and-demonstration/4b-repeated-energy-experiments.md)
**Blocks**: [4d](../phase-4-experiments-report-and-demonstration/4d-budget-and-energy-findings.md), [4e](../phase-4-experiments-report-and-demonstration/4e-research-report.md), [4f](../phase-4-experiments-report-and-demonstration/4f-demo-and-reproducibility.md)

## Scope

Owner: James. Apply the frozen evaluator to the held-out prediction logs produced by `4b`'s trials, so quality and energy come from the same runs (rev. 6), and inspect the quality of generated descriptions. Separate gate misses, VLM mistakes and delayed/duplicate notifications in the findings.

## Tasks

- [ ] Score held-out videos without tuning thresholds or labels from their results.
- [ ] Review missed/false/duplicate events and a blinded subset of descriptions.
- [ ] Summarize event quality, delays and representative failure cases.

## Files to be touched

- `docs/final_report.md` — Quality results and failures.
- `results/` — Proposed generated scoring artifacts; commit policy follows data terms.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

None newly surfaced. Apply the parent plan and resolve measured settings in the prerequisite items.

## Acceptance criteria

- [ ] Held-out outputs use frozen settings and retained error reports.
- [ ] Description review records its sample selection and evaluation rubric.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Score held-out videos without tuning thresholds or labels from their results. | [Tasks](#tasks) | The test manifest identifies frozen settings and reserved sessions. | — | ⬜ |
| 2 | Review missed/false/duplicate events and a blinded subset of descriptions. | [Tasks](#tasks) | Accuracy and unsupported claims are assessed with a documented rubric. | — | ⬜ |
| 3 | Summarize event quality, delays and representative failure cases. | [Tasks](#tasks) | The report can trace quality claims to saved metrics and reviewed examples. | — | ⬜ |
| 4 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

<!-- impl-notes-anchor -->
