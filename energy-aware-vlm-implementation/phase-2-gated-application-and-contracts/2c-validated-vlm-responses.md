# 2c — Validated prompts, responses and inference logs

**Live issue:** [#9](https://github.com/austincbaker/cap6411-cv-systems/issues/9)
**Priority:** P1 (`priority:P1`)
**GitHub blocked by:** [1a (#1)](https://github.com/austincbaker/cap6411-cv-systems/issues/1), [1e (#5)](https://github.com/austincbaker/cap6411-cv-systems/issues/5)

**Phase**: 2 — Deliver a gated application and evaluation contracts
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-2--deliver-a-gated-application-and-evaluation-contracts-week-2); D01, D03, D06, D07; R05
**Depends on**: [1a](../phase-1-live-inference-and-measurement/1a-local-vlm-inference.md), [1e](../phase-1-live-inference-and-measurement/1e-event-definitions-and-pilot-data.md)
**Blocks**: [2d](../phase-2-gated-application-and-contracts/2d-evaluation-contracts-and-fixtures.md), [3b](../phase-3-budget-control-and-evaluation-tools/3b-inference-cost-ablations.md)

## Scope

Owner: Austin. Constrain prompts and validate model responses against the selected event/observation vocabulary. Record request status, time and available token statistics without confusing model text with confirmed temporal events.

## Tasks

- [ ] Define bounded prompts and a response shape aligned with James's event definitions.
- [ ] Validate parsed output, preserve original request status and distinguish observations from inferred state changes.
- [ ] Emit source-frame and response-available timestamps plus supported token/cache statistics.

## Files to be touched

- `src/vlm/prompts.py` — Proposed prompts and response validation.
- `src/vlm/client.py` — Inference status, timing and available statistics.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

None newly surfaced. Apply the parent plan and resolve measured settings in the prerequisite items.

## Acceptance criteria

- [ ] Valid output maps to the task's declared fields and malformed responses are explicit failures.
- [ ] Each prediction can be traced to its input frame and completion time.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Define bounded prompts and a response shape aligned with James's event definitions. | [Tasks](#tasks) | The prompt/schema uses the selected task vocabulary. | — | ⬜ |
| 2 | Validate parsed output, preserve original request status and distinguish observations from inferred state changes. | [Tasks](#tasks) | Malformed text does not silently become a correct event. | — | ⬜ |
| 3 | Emit source-frame and response-available timestamps plus supported token/cache statistics. | [Tasks](#tasks) | Unavailable counts remain missing and successful responses carry both timestamps. | — | ⬜ |
| 4 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

<!-- impl-notes-anchor -->
