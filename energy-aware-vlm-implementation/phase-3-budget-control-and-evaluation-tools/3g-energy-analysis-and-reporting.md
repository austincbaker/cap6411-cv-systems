# 3g — Energy analysis, comparison tables and figures

**Live issue:** [#19](https://github.com/austincbaker/cap6411-cv-systems/issues/19)
**Priority:** P1 (`priority:P1`)
**GitHub blocked by:** [2d (#10)](https://github.com/austincbaker/cap6411-cv-systems/issues/10), [2f (#12)](https://github.com/austincbaker/cap6411-cv-systems/issues/12), [3e (#17)](https://github.com/austincbaker/cap6411-cv-systems/issues/17), [3f (#18)](https://github.com/austincbaker/cap6411-cv-systems/issues/18)

**Phase**: 3 — Integrate budget control and owned evaluation tools
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-3--integrate-budget-control-and-owned-evaluation-tools-week-3); D02, D06, D07, D08; R02, R03, R08
**Depends on**: [2d](../phase-2-gated-application-and-contracts/2d-evaluation-contracts-and-fixtures.md), [2f](../phase-2-gated-application-and-contracts/2f-benchmark-configurations.md), [3e](../phase-3-budget-control-and-evaluation-tools/3e-event-scoring-cli.md), [3f](../phase-3-budget-control-and-evaluation-tools/3f-benchmark-runner.md)
**Blocks**: [3h](../phase-3-budget-control-and-evaluation-tools/3h-pilot-and-evaluation-freeze.md)

## Scope

Owner: Shawn, with Austin checking energy calculations and James supplying quality metrics. Convert saved trials into comparable energy, latency and quality tables and figures. Keep measured energy domains and unavailable data explicit.

## Tasks

- [ ] Integrate valid power/counter samples and report measured duration, coverage, total and incremental energy.
- [ ] Join trial/latency data and James's metrics using run identifiers.
- [ ] Implement report generation with repeat variability and standalone exportable figures.

## Files to be touched

- `experiments/analyze_results.py` — Proposed analysis/report command.
- `tests/test_energy_analysis.py` — Power integration, units, rollover and missing-data checks.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

None newly surfaced. Apply the parent plan and resolve measured settings in the prerequisite items.

## Acceptance criteria

- [ ] The analyzer distinguishes whole-system and package energy and shows unavailable measurements.
- [ ] Exported comparison artifacts preserve run provenance and incorporate James's event scores.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Integrate valid power/counter samples and report measured duration, coverage, total and incremental energy. | [Tasks](#tasks) | Known traces reproduce manual calculations including irregular intervals and gaps. | — | ⬜ |
| 2 | Join trial/latency data and James's metrics using run identifiers. | [Tasks](#tasks) | Plots and tables cannot silently combine different models, domains or incomplete trials. | — | ⬜ |
| 3 | Implement report generation with repeat variability and standalone exportable figures. | [Tasks](#tasks) | One command regenerates final artifacts from saved logs without manual transcription. | — | ⬜ |
| 4 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

<!-- impl-notes-anchor -->
