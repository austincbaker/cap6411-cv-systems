# 2e — Annotated dataset, grouped splits and scoring examples

**Live issue:** [#11](https://github.com/austincbaker/cap6411-cv-systems/issues/11)
**Priority:** P1 (`priority:P1`)
**GitHub blocked by:** [1e (#5)](https://github.com/austincbaker/cap6411-cv-systems/issues/5), [2d (#10)](https://github.com/austincbaker/cap6411-cv-systems/issues/10)

**Phase**: 2 — Deliver a gated application and evaluation contracts
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-2--deliver-a-gated-application-and-evaluation-contracts-week-2); D01, D07; R07
**Depends on**: [1e](../phase-1-live-inference-and-measurement/1e-event-definitions-and-pilot-data.md), [2d](../phase-2-gated-application-and-contracts/2d-evaluation-contracts-and-fixtures.md)
**Blocks**: [3d](../phase-3-budget-control-and-evaluation-tools/3d-event-matching.md)

## Scope

Owner: James. Finish the custom dataset and grouped splits, adding a public subset only where event labels can be mapped honestly. Provide manual expected event outcomes that will become reference cases for the scoring implementation.

## Tasks

- [ ] Complete roughly 30–36 short clips and at least 100 events where feasible, plus longer idle/mixed recordings.
- [ ] Annotate observable intervals and group development/validation/test by session or environment.
- [ ] Double-check a subset with another member and create hand-scored matching examples.

## Files to be touched

- `data/README.md` — Dataset provenance and split methodology.
- `data/annotations/` — Event intervals and split inventory.
- `tests/fixtures/` — Hand-scored event cases coordinated with contract owners.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

None newly surfaced. Apply the parent plan and resolve measured settings in the prerequisite items.

## Acceptance criteria

- [ ] Held-out data is reserved and labels follow the agreed task rules.
- [ ] A second annotator reviews a recorded subset and hand-scored examples are available.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Complete roughly 30–36 short clips and at least 100 events where feasible, plus longer idle/mixed recordings. | [Tasks](#tasks) | The inventory records actual clip/event counts and difficulty coverage. | — | ⬜ |
| 2 | Annotate observable intervals and group development/validation/test by session or environment. | [Tasks](#tasks) | Adjacent frames or near-duplicate sessions do not leak across splits. | — | ⬜ |
| 3 | Double-check a subset with another member and create hand-scored matching examples. | [Tasks](#tasks) | Disagreements are resolved and reference outcomes are recorded before implementation. | — | ⬜ |
| 4 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

<!-- impl-notes-anchor -->
