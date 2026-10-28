# 4b — Repeated energy trials and final plots

**Live issue:** [#22](https://github.com/austincbaker/cap6411-cv-systems/issues/22)
**Priority:** P1 (`priority:P1`)
**GitHub blocked by:** [3h (#20)](https://github.com/austincbaker/cap6411-cv-systems/issues/20)

**Phase**: 4 — Complete experiments, report and demonstration
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-4--complete-experiments-report-and-demonstration-week-4); D08, D11; R03, R06, R08
**Depends on**: [3h](../phase-3-budget-control-and-evaluation-tools/3h-pilot-and-evaluation-freeze.md)
**Blocks**: [4d](../phase-4-experiments-report-and-demonstration/4d-budget-and-energy-findings.md), [4e](../phase-4-experiments-report-and-demonstration/4e-research-report.md), [4f](../phase-4-experiments-report-and-demonstration/4f-demo-and-reproducibility.md)

## Scope

Owner: Shawn. Execute the final repeated energy comparison and generate exportable results. Preserve controls, randomized order and trial provenance, including failed or incomplete runs.

## Tasks

- [ ] Run three repeated measurements per main configuration using the frozen protocol.
- [ ] Review coverage, failures and environmental changes before aggregation.
- [ ] Generate final energy-quality tables, latency distributions and uncertainty summaries.

## Files to be touched

- `results/` — Generated final energy and comparison artifacts.
- `docs/final_report.md` — Experiment counts and results references.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

None newly surfaced. Apply the parent plan and resolve measured settings in the prerequisite items.

## Acceptance criteria

- [ ] Each main configuration has three valid repeated measurements or a documented unresolved limitation.
- [ ] Artifacts report sensor domains and variability instead of unsupported exact savings.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Run three repeated measurements per main configuration using the frozen protocol. | [Tasks](#tasks) | Completed trials have distinct manifests and declared measurement durations. | — | ⬜ |
| 2 | Review coverage, failures and environmental changes before aggregation. | [Tasks](#tasks) | Excluded/incomplete runs retain explicit reasons and raw evidence. | — | ⬜ |
| 3 | Generate final energy-quality tables, latency distributions and uncertainty summaries. | [Tasks](#tasks) | Each plotted point or table row links back to its constituent trials. | — | ⬜ |
| 4 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

<!-- impl-notes-anchor -->
