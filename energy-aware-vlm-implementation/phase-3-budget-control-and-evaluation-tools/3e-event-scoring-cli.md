# 3e — Event metrics and scoring command

**Live issue:** [#17](https://github.com/austincbaker/cap6411-cv-systems/issues/17)
**Priority:** P1 (`priority:P1`)
**GitHub blocked by:** [3d (#16)](https://github.com/austincbaker/cap6411-cv-systems/issues/16)

**Phase**: 3 — Integrate budget control and owned evaluation tools
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-3--integrate-budget-control-and-owned-evaluation-tools-week-3); D02, D06, D07; R02
**Depends on**: [3d](../phase-3-budget-control-and-evaluation-tools/3d-event-matching.md)
**Blocks**: [3g](../phase-3-budget-control-and-evaluation-tools/3g-energy-analysis-and-reporting.md), [3h](../phase-3-budget-control-and-evaluation-tools/3h-pilot-and-evaluation-freeze.md), [4g](../phase-4-experiments-report-and-demonstration/4g-failure-review-viewer.md)

## Scope

Owner: James. Build the command-line evaluator that produces the final quality results. Export aggregate scores and an event-level error report that others can review without reading the inference implementation.

## Tasks

- [ ] Compute precision, recall, F1, delays and counts from the matching output.
- [ ] Implement the scoring command with clear input errors and separate output artifacts.
- [ ] Export correct, missed, false and duplicate event records for review.

## Files to be touched

- `src/evaluation/metrics.py` — Proposed task metrics.
- `experiments/score_events.py` — Proposed scoring command.
- `tests/test_event_metrics.py` — Metric and empty-data checks.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

None newly surfaced. Apply the parent plan and resolve measured settings in the prerequisite items.

## Acceptance criteria

- [ ] The planned scoring command produces aggregate metrics and traceable errors.
- [ ] Repeated scoring of unchanged inputs produces identical results.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Compute precision, recall, F1, delays and counts from the matching output. | [Tasks](#tasks) | Known fixtures reproduce manually calculated metrics including empty-set behavior. | — | ⬜ |
| 2 | Implement the scoring command with clear input errors and separate output artifacts. | [Tasks](#tasks) | One command scores annotations and prediction logs without a live VLM. | — | ⬜ |
| 3 | Export correct, missed, false and duplicate event records for review. | [Tasks](#tasks) | The final report and Shawn's tools can consume stable metric/error files. | — | ⬜ |
| 4 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

<!-- impl-notes-anchor -->
