# 3b — Measured image, output and cache ablations

**Live issue:** [#14](https://github.com/austincbaker/cap6411-cv-systems/issues/14)
**Priority:** P2 (`priority:P2`)
**GitHub blocked by:** [2c (#9)](https://github.com/austincbaker/cap6411-cv-systems/issues/9), [2d (#10)](https://github.com/austincbaker/cap6411-cv-systems/issues/10), [2f (#12)](https://github.com/austincbaker/cap6411-cv-systems/issues/12)

**Phase**: 3 — Integrate budget control and owned evaluation tools
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-3--integrate-budget-control-and-owned-evaluation-tools-week-3); D03, D09; R04, R05
**Depends on**: [2c](../phase-2-gated-application-and-contracts/2c-validated-vlm-responses.md), [2d](../phase-2-gated-application-and-contracts/2d-evaluation-contracts-and-fixtures.md), [2f](../phase-2-gated-application-and-contracts/2f-benchmark-configurations.md)
**Blocks**: [3c](../phase-3-budget-control-and-evaluation-tools/3c-budget-aware-application.md), [3h](../phase-3-budget-control-and-evaluation-tools/3h-pilot-and-evaluation-freeze.md)

## Scope

Owner: Austin. Measure the benefit and correctness of output limits, image/crop modes and static-prefix caching. Keep only supported optimizations and preserve negative findings as part of the ablation results.

## Tasks

- [ ] Compare bounded output settings and report actual generated lengths, latency and energy.
- [ ] Measure resolution/crop modes and observable visual-token behavior.
- [ ] Compare valid prefix caching on/off while changing image content.

## Files to be touched

- `src/vlm/preprocessing.py` — Proposed image/crop mode selection.
- `src/vlm/client.py` — Supported cache and generation options.
- `src/vlm/prompts.py` — Short consistent output modes.
- `configs/` — Ablation settings.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

None newly surfaced. Apply the parent plan and resolve measured settings in the prerequisite items.

## Acceptance criteria

- [ ] Ablation artifacts distinguish model-supported controls from unsupported or unavailable statistics.
- [ ] Changed-image correctness is verified with caching enabled.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Compare bounded output settings and report actual generated lengths, latency and energy. | [Tasks](#tasks) | Output-budget effects are measured with the inference schedule held fixed. | — | ⬜ |
| 2 | Measure resolution/crop modes and observable visual-token behavior. | [Tasks](#tasks) | Image-token savings are claimed only when token work is demonstrably reduced. | — | ⬜ |
| 3 | Compare valid prefix caching on/off while changing image content. | [Tasks](#tasks) | New image evidence is processed correctly and cache benefit is measured rather than assumed. | — | ⬜ |
| 4 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

<!-- impl-notes-anchor -->
