# 3d — Deterministic one-to-one event matching

**Live issue:** [#16](https://github.com/austincbaker/cap6411-cv-systems/issues/16)
**Priority:** P1 (`priority:P1`)
**GitHub blocked by:** [2d (#10)](https://github.com/austincbaker/cap6411-cv-systems/issues/10), [2e (#11)](https://github.com/austincbaker/cap6411-cv-systems/issues/11)

**Phase**: 3 — Integrate budget control and owned evaluation tools
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-3--integrate-budget-control-and-owned-evaluation-tools-week-3); D06, D07; R01
**Depends on**: [2d](../phase-2-gated-application-and-contracts/2d-evaluation-contracts-and-fixtures.md), [2e](../phase-2-gated-application-and-contracts/2e-annotated-dataset-and-splits.md)
**Blocks**: [3e](../phase-3-budget-control-and-evaluation-tools/3e-event-scoring-cli.md)

## Scope

Owner: James, with Alejandro reviewing reference cases. Implement deterministic one-to-one matching between predictions and labeled events. Apply frozen label and timing rules so delays, duplicates and wrong events are counted consistently.

## Tasks

- [ ] Validate and normalize annotation/prediction inputs using the documented contract.
- [ ] Implement deterministic one-to-one matching under frozen evidence and availability rules.
- [ ] Classify unmatched predictions/events and duplicate detections with provenance.

## Files to be touched

- `src/evaluation/matching.py` — Proposed matching implementation.
- `tests/test_event_matching.py` — Hand-scored temporal and label cases.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

None newly surfaced. Apply the parent plan and resolve measured settings in the prerequisite items.

## Acceptance criteria

- [ ] Each event and prediction participates in at most one match.
- [ ] Late responses are evaluated using declared timing rules and duplicate predictions remain false positives.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Validate and normalize annotation/prediction inputs using the documented contract. | [Tasks](#tasks) | Malformed records and incompatible schema versions produce useful errors. | — | ⬜ |
| 2 | Implement deterministic one-to-one matching under frozen evidence and availability rules. | [Tasks](#tasks) | Manually scored overlaps, wrong labels and tolerance cases match expected pairings. | — | ⬜ |
| 3 | Classify unmatched predictions/events and duplicate detections with provenance. | [Tasks](#tasks) | Every error row points to event/prediction IDs or an explicit unmatched record. | — | ⬜ |
| 4 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

<!-- impl-notes-anchor -->
