# Phase 3 — Integrate budget control and owned evaluation tools

The complete budget-aware application and both evaluation toolchains process a pilot run; known-answer tests pass and settings are frozen before held-out evaluation.

**Master plan:** [Phase 3](../plan.md#phase-3--integrate-budget-control-and-owned-evaluation-tools-week-3). **Schedule:** Week 3. All status fields track implementation, not planning.

## Prerequisites

Respect each item's listed prerequisites. The previous phase's exit criteria establish the full phase baseline; compatible file fixtures can support independent tool development before the complete application is ready. A planning expansion never satisfies an implementation dependency.

## Items

| Item | Owner | Depends on | Scope |
| --- | --- | --- | --- |
| [3a — Calibrated energy-budget admission](./3a-energy-budget-controller.md) | Austin | [1b](../phase-1-live-inference-and-measurement/1b-power-telemetry.md), [2d](../phase-2-gated-application-and-contracts/2d-evaluation-contracts-and-fixtures.md), [2f](../phase-2-gated-application-and-contracts/2f-benchmark-configurations.md) | Required |
| [3b — Measured image, output and cache ablations](./3b-inference-cost-ablations.md) | Austin | [2c](../phase-2-gated-application-and-contracts/2c-validated-vlm-responses.md), [2d](../phase-2-gated-application-and-contracts/2d-evaluation-contracts-and-fixtures.md), [2f](../phase-2-gated-application-and-contracts/2f-benchmark-configurations.md) | Required |
| [3c — Integrated budget-aware application](./3c-budget-aware-application.md) | Alejandro | [2a](../phase-2-gated-application-and-contracts/2a-change-and-relevance-gate.md), [2b](../phase-2-gated-application-and-contracts/2b-latest-frame-and-scene-state.md), [3a](../phase-3-budget-control-and-evaluation-tools/3a-energy-budget-controller.md) | Required |
| [3d — Deterministic one-to-one event matching](./3d-event-matching.md) | James | [2d](../phase-2-gated-application-and-contracts/2d-evaluation-contracts-and-fixtures.md) | Required |
| [3e — Event metrics and scoring command](./3e-event-scoring-cli.md) | James | [3d](../phase-3-budget-control-and-evaluation-tools/3d-event-matching.md) | Required |
| [3f — Repeated-trial benchmark runner](./3f-benchmark-runner.md) | Shawn | [1d](../phase-1-live-inference-and-measurement/1d-fixed-interval-application.md), [2d](../phase-2-gated-application-and-contracts/2d-evaluation-contracts-and-fixtures.md), [2f](../phase-2-gated-application-and-contracts/2f-benchmark-configurations.md) | Required |
| [3g — Energy analysis, comparison tables and figures](./3g-energy-analysis-and-reporting.md) | Shawn | [2d](../phase-2-gated-application-and-contracts/2d-evaluation-contracts-and-fixtures.md), [2f](../phase-2-gated-application-and-contracts/2f-benchmark-configurations.md), [3e](../phase-3-budget-control-and-evaluation-tools/3e-event-scoring-cli.md), [3f](../phase-3-budget-control-and-evaluation-tools/3f-benchmark-runner.md) | Required |
| [3h — Pilot comparison and final evaluation freeze](./3h-pilot-and-evaluation-freeze.md) | All | [2e](../phase-2-gated-application-and-contracts/2e-annotated-dataset-and-splits.md), [3a](../phase-3-budget-control-and-evaluation-tools/3a-energy-budget-controller.md), [3b](../phase-3-budget-control-and-evaluation-tools/3b-inference-cost-ablations.md), [3c](../phase-3-budget-control-and-evaluation-tools/3c-budget-aware-application.md), [3e](../phase-3-budget-control-and-evaluation-tools/3e-event-scoring-cli.md), [3f](../phase-3-budget-control-and-evaluation-tools/3f-benchmark-runner.md), [3g](../phase-3-budget-control-and-evaluation-tools/3g-energy-analysis-and-reporting.md) | Required |

## Exit criteria

- [ ] The complete budget-aware application and both evaluation toolchains process a pilot run; known-answer tests pass and settings are frozen before held-out evaluation.
- [ ] All required item acceptance criteria are verified and their Definition-of-Done rows contain code or artifact references.
- [ ] Shared documents and schema changes are reviewed with their consumers; raw results are preserved.
