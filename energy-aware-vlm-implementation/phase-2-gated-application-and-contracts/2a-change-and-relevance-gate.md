# 2a — Change gate and relevance rules

**Live issue:** [#7](https://github.com/austincbaker/cap6411-cv-systems/issues/7)
**Priority:** P1 (`priority:P1`)
**GitHub blocked by:** [1c (#3)](https://github.com/austincbaker/cap6411-cv-systems/issues/3), [1d (#4)](https://github.com/austincbaker/cap6411-cv-systems/issues/4), [1e (#5)](https://github.com/austincbaker/cap6411-cv-systems/issues/5)

**Phase**: 2 — Deliver a gated application and evaluation contracts
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-2--deliver-a-gated-application-and-evaluation-contracts-week-2); D04, D05, D07; R05
**Depends on**: [1c](../phase-1-live-inference-and-measurement/1c-webcam-and-replay.md), [1d](../phase-1-live-inference-and-measurement/1d-fixed-interval-application.md), [1e](../phase-1-live-inference-and-measurement/1e-event-definitions-and-pilot-data.md)
**Blocks**: [2b](../phase-2-gated-application-and-contracts/2b-latest-frame-and-scene-state.md), [3c](../phase-3-budget-control-and-evaluation-tools/3c-budget-aware-application.md)

## Scope

Owner: Alejandro. Add cheap downsampled and regional change detection, then relevance rules that prioritize meaningful workspace events. Include retained references, persistence, cooldowns and periodic refresh to reduce repeated calls without permanently missing subtle or gradual changes.

## Tasks

- [ ] Implement normalized global/regional change scores against recent and acknowledged references.
- [ ] Add persistence, hysteresis, cooldown and forced refresh with explicit trigger/skip reasons.
- [ ] Tune only on development clips and check small changes and lighting-only changes.

## Files to be touched

- `src/gates/change.py` — Proposed change scores and references.
- `src/gates/scheduler.py` — Proposed relevance/cooldown/refresh decisions.
- `tests/test_scheduler.py` — Observable refresh and cooldown behavior, plus deterministic change-score cases: identical frames, global versus regional changes, threshold boundaries, acknowledged/recent-reference updates, gradual change and lighting-only variation.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

None newly surfaced. Apply the parent plan and resolve measured settings in the prerequisite items.

## Acceptance criteria

- [ ] Mixed-activity clips produce both admitted and skipped frames with recorded reasons.
- [ ] Reference updates do not hide gradual changes or cause notifications on every frame.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Implement normalized global/regional change scores against recent and acknowledged references. | [Tasks](#tasks) | Pilot clips expose change scores and preserve gradual/local change evidence. | — | ⬜ |
| 2 | Add persistence, hysteresis, cooldown and forced refresh with explicit trigger/skip reasons. | [Tasks](#tasks) | Each decision is traceable to its rule and configuration. | — | ⬜ |
| 3 | Tune only on development clips and check small changes and lighting-only changes. | [Tasks](#tasks) | Held-out clips are not used to choose thresholds. | — | ⬜ |
| 4 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

<!-- impl-notes-anchor -->
