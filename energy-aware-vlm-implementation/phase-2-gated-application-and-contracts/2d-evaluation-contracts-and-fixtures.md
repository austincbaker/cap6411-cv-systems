# 2d — Versioned evaluation contracts and sample artifacts

**Live issue:** [#10](https://github.com/austincbaker/cap6411-cv-systems/issues/10)
**Priority:** P0 (`priority:P0`)
**GitHub blocked by:** [1b (#2)](https://github.com/austincbaker/cap6411-cv-systems/issues/2), [1d (#4)](https://github.com/austincbaker/cap6411-cv-systems/issues/4), [1e (#5)](https://github.com/austincbaker/cap6411-cv-systems/issues/5), [1f (#6)](https://github.com/austincbaker/cap6411-cv-systems/issues/6), [2c (#9)](https://github.com/austincbaker/cap6411-cv-systems/issues/9)

**Phase**: 2 — Deliver a gated application and evaluation contracts
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-2--deliver-a-gated-application-and-evaluation-contracts-week-2); D02, D06, D07, D08; R01, R10
**Depends on**: [1b](../phase-1-live-inference-and-measurement/1b-power-telemetry.md), [1d](../phase-1-live-inference-and-measurement/1d-fixed-interval-application.md), [1e](../phase-1-live-inference-and-measurement/1e-event-definitions-and-pilot-data.md), [1f](../phase-1-live-inference-and-measurement/1f-measurement-protocol-and-research.md), [2c](../phase-2-gated-application-and-contracts/2c-validated-vlm-responses.md)
**Blocks**: [2e](../phase-2-gated-application-and-contracts/2e-annotated-dataset-and-splits.md), [2f](../phase-2-gated-application-and-contracts/2f-benchmark-configurations.md), [3a](../phase-3-budget-control-and-evaluation-tools/3a-energy-budget-controller.md), [3b](../phase-3-budget-control-and-evaluation-tools/3b-inference-cost-ablations.md), [3d](../phase-3-budget-control-and-evaluation-tools/3d-event-matching.md), [3f](../phase-3-budget-control-and-evaluation-tools/3f-benchmark-runner.md), [3g](../phase-3-budget-control-and-evaluation-tools/3g-energy-analysis-and-reporting.md)

## Scope

Owners: Austin (lead drafter) and Alejandro; James and Shawn review the consumer interfaces. Freeze versioned file contracts and small synthetic examples by the end of Week 2. This is the handoff that lets evaluation software be developed independently of the running VLM. Rev. 6 adds the application run interface, a metrics/error-report schema and fixture, a shared contract validator, the `2b` event-derivation rules in the prediction contract, and AC/battery state in the run manifest.

## Tasks

- [ ] Specify annotation, prediction, request/gate, power and manifest fields, units and schema versions.
- [ ] Agree event matching eligibility/normalization and error/empty-data semantics with James and Shawn.
- [ ] Provide valid and failure-case fixtures with expected event and energy outcomes.
- [ ] Specify the application run interface: config path, live or replay input, output directory, manifest writing and exit status.
- [ ] Add a metrics/error-report schema and fixture, and a shared contract validator used by both the scorer and the analyzer.

## Files to be touched

- `docs/data-contracts.md` — Proposed authoritative file contract.
- `tests/fixtures/` — Proposed small annotations, logs, manifests, metrics/error reports and known expected results.
- `src/contracts.py` — Proposed shared schema-version and field validator.
- `tests/test_contracts.py` — Fixture and malformed-record validation.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

- [ ] Draft matching tolerance, reporting horizon and label normalization with James and Alejandro; item `3h` freezes them on validation data (rev. 6).

## Acceptance criteria

- [ ] Both evaluation owners successfully consume the first-version examples.
- [ ] Timelines distinguish frame evidence, response availability and sensor sampling; missing values are explicit.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Specify annotation, prediction, request/gate, power and manifest fields, units and schema versions. | [Tasks](#tasks) | Every required artifact has a documented producer, consumer, time base and missing-value rule. | — | ⬜ |
| 2 | Agree event matching eligibility/normalization and error/empty-data semantics with James and Shawn. | [Tasks](#tasks) | Scoring and energy calculations have written rules and hand-checkable expected values. | — | ⬜ |
| 3 | Provide valid and failure-case fixtures with expected event and energy outcomes. | [Tasks](#tasks) | James and Shawn can independently parse all samples without starting the model. | — | ⬜ |
| 4 | Specify the application run interface: config path, live or replay input, output directory, manifest writing and exit status. | [Tasks](#tasks) | Shawn's runner can launch one trial and detect success or failure from the documented interface alone. | — | ⬜ |
| 5 | Add a metrics/error-report schema and fixture, and a shared contract validator used by both the scorer and the analyzer. | [Tasks](#tasks) | `tests/test_contracts.py` validates every fixture, and `3d`/`3g` import the shared validator instead of re-parsing files. | — | ⬜ |
| 6 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

<!-- impl-notes-anchor -->
