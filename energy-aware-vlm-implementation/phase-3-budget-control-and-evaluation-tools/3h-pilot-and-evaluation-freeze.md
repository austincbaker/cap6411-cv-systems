# 3h — Pilot comparison and final evaluation freeze

**Live issue:** [#20](https://github.com/austincbaker/cap6411-cv-systems/issues/20)
**Priority:** P1 (`priority:P1`)
**GitHub blocked by:** [2e (#11)](https://github.com/austincbaker/cap6411-cv-systems/issues/11), [3a (#13)](https://github.com/austincbaker/cap6411-cv-systems/issues/13), [3b (#14)](https://github.com/austincbaker/cap6411-cv-systems/issues/14), [3c (#15)](https://github.com/austincbaker/cap6411-cv-systems/issues/15), [3e (#17)](https://github.com/austincbaker/cap6411-cv-systems/issues/17), [3f (#18)](https://github.com/austincbaker/cap6411-cv-systems/issues/18), [3g (#19)](https://github.com/austincbaker/cap6411-cv-systems/issues/19)

**Phase**: 3 — Integrate budget control and owned evaluation tools
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-3--integrate-budget-control-and-owned-evaluation-tools-week-3); D06, D07, D08, D10; R01, R06
**Depends on**: [2e](../phase-2-gated-application-and-contracts/2e-annotated-dataset-and-splits.md), [3a](../phase-3-budget-control-and-evaluation-tools/3a-energy-budget-controller.md), [3b](../phase-3-budget-control-and-evaluation-tools/3b-inference-cost-ablations.md), [3c](../phase-3-budget-control-and-evaluation-tools/3c-budget-aware-application.md), [3e](../phase-3-budget-control-and-evaluation-tools/3e-event-scoring-cli.md), [3f](../phase-3-budget-control-and-evaluation-tools/3f-benchmark-runner.md), [3g](../phase-3-budget-control-and-evaluation-tools/3g-energy-analysis-and-reporting.md)
**Blocks**: [4a](../phase-4-experiments-report-and-demonstration/4a-held-out-event-evaluation.md), [4b](../phase-4-experiments-report-and-demonstration/4b-repeated-energy-experiments.md), [4c](../phase-4-experiments-report-and-demonstration/4c-stability-and-defect-resolution.md)

## Scope

Owners: All four members. Run a development/validation pilot through the complete application and both evaluation toolchains. Resolve calculation or contract defects and freeze settings before exposing held-out results. This is the only evaluation freeze (rev. 6): it fixes matching tolerance, reporting horizon and label normalization, the matched-invocation rate, budget levels, and the description-review protocol, and it requires the `3c` stability smoke run and the complete `2e` dataset.

## Tasks

- [ ] Execute a pilot comparison and manually inspect one event and one energy calculation.
- [ ] Run relevant tests and resolve contract/calculation defects before the final freeze.
- [ ] Record final policies, labels, matching rules, model/build and analysis settings.

## Files to be touched

- `configs/` — Frozen evaluation settings.
- `docs/methodology.md` — Pilot review and freeze record.
- `docs/data-contracts.md` — Coordinated corrections only when necessary.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

None newly surfaced. Apply the parent plan and resolve measured settings in the prerequisite items.

## Acceptance criteria

- [ ] James's scorer and Shawn's tools process the same complete pilot run.
- [ ] Freeze happens before held-out scoring and later changes require affected reruns.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Execute a pilot comparison and manually inspect one event and one energy calculation. | [Tasks](#tasks) | Application and tool outputs agree on run identity and timelines. | — | ⬜ |
| 2 | Run relevant tests and resolve contract/calculation defects before the final freeze. | [Tasks](#tasks) | Known reference cases pass and defects have documented resolutions. | — | ⬜ |
| 3 | Record final policies, labels, matching rules, model/build and analysis settings. | [Tasks](#tasks) | Held-out evaluation has a dated frozen configuration and split inventory. | — | ⬜ |
| 4 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

<!-- impl-notes-anchor -->
