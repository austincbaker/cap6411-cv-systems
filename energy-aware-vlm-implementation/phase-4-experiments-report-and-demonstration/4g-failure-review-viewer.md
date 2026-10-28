# 4g — Optional failure-review viewer

**Live issue:** [#27](https://github.com/austincbaker/cap6411-cv-systems/issues/27)
**Priority:** P3 (`priority:P3`)
**GitHub blocked by:** [3e (#17)](https://github.com/austincbaker/cap6411-cv-systems/issues/17)

**Phase**: 4 — Complete experiments, report and demonstration
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-4--complete-experiments-report-and-demonstration-week-4); D02, D07, D10; R02, R04
**Depends on**: [3e](../phase-3-budget-control-and-evaluation-tools/3e-event-scoring-cli.md)
**Blocks**: None; optional and excluded from required completion

## Scope

Optional owner: James. After required scoring is complete, add a small review interface that connects error rows to source frames and model responses. This is a stretch contribution and does not block the main evaluation or project completion.

## Tasks

- [ ] Load James's saved error reports and locate referenced video frames/predictions.
- [ ] Display ground truth, model response and timing together without changing scoring rules.

## Files to be touched

- `experiments/review_failures.py` — Proposed optional viewer; exact UI approach is an implementation choice.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

None newly surfaced. Apply the parent plan and resolve measured settings in the prerequisite items.

## Acceptance criteria

- [ ] The viewer opens a saved error case and shows the corresponding evidence.
- [ ] The viewer remains optional and does not change the authoritative scoring output.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Load James's saved error reports and locate referenced video frames/predictions. | [Tasks](#tasks) | A reviewer can inspect a selected false/missed/duplicate event. | — | ⬜ |
| 2 | Display ground truth, model response and timing together without changing scoring rules. | [Tasks](#tasks) | Review actions do not mutate the frozen labels or aggregate metrics. | — | ⬜ |
| 3 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

<!-- impl-notes-anchor -->
