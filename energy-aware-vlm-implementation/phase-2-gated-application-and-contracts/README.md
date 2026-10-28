# Phase 2 — Deliver a gated application and evaluation contracts

Gated replay produces traceable admit/skip decisions, the dataset has grouped splits, and James/Shawn independently load the versioned sample artifacts by the end of Week 2.

**Master plan:** [Phase 2](../plan.md#phase-2--deliver-a-gated-application-and-evaluation-contracts-week-2). **Schedule:** Week 2. All status fields track implementation, not planning.

## Prerequisites

Respect each item's listed prerequisites. The previous phase's exit criteria establish the full phase baseline; compatible file fixtures can support independent tool development before the complete application is ready. A planning expansion never satisfies an implementation dependency.

## Items

| Item | Owner | Depends on | Scope |
| --- | --- | --- | --- |
| [2a — Change gate and relevance rules](./2a-change-and-relevance-gate.md) | Alejandro | [1c](../phase-1-live-inference-and-measurement/1c-webcam-and-replay.md), [1d](../phase-1-live-inference-and-measurement/1d-fixed-interval-application.md), [1e](../phase-1-live-inference-and-measurement/1e-event-definitions-and-pilot-data.md) | Required |
| [2b — Latest-frame scheduling and scene state](./2b-latest-frame-and-scene-state.md) | Alejandro | [1d](../phase-1-live-inference-and-measurement/1d-fixed-interval-application.md), [2a](../phase-2-gated-application-and-contracts/2a-change-and-relevance-gate.md) | Required |
| [2c — Validated prompts, responses and inference logs](./2c-validated-vlm-responses.md) | Austin | [1a](../phase-1-live-inference-and-measurement/1a-local-vlm-inference.md), [1e](../phase-1-live-inference-and-measurement/1e-event-definitions-and-pilot-data.md) | Required |
| [2d — Versioned evaluation contracts and sample artifacts](./2d-evaluation-contracts-and-fixtures.md) | Austin and Alejandro | [1b](../phase-1-live-inference-and-measurement/1b-power-telemetry.md), [1d](../phase-1-live-inference-and-measurement/1d-fixed-interval-application.md), [1e](../phase-1-live-inference-and-measurement/1e-event-definitions-and-pilot-data.md), [1f](../phase-1-live-inference-and-measurement/1f-measurement-protocol-and-research.md), [2c](../phase-2-gated-application-and-contracts/2c-validated-vlm-responses.md) | Required |
| [2e — Annotated dataset, grouped splits and scoring examples](./2e-annotated-dataset-and-splits.md) | James | [1e](../phase-1-live-inference-and-measurement/1e-event-definitions-and-pilot-data.md), [2d](../phase-2-gated-application-and-contracts/2d-evaluation-contracts-and-fixtures.md) | Required |
| [2f — Frozen benchmark protocol and configurations](./2f-benchmark-configurations.md) | Shawn | [1f](../phase-1-live-inference-and-measurement/1f-measurement-protocol-and-research.md), [2d](../phase-2-gated-application-and-contracts/2d-evaluation-contracts-and-fixtures.md) | Required |

## Exit criteria

- [ ] Gated replay produces traceable admit/skip decisions, the dataset has grouped splits, and James/Shawn independently load the versioned sample artifacts by the end of Week 2.
- [ ] All required item acceptance criteria are verified and their Definition-of-Done rows contain code or artifact references.
- [ ] Shared documents and schema changes are reviewed with their consumers; raw results are preserved.
