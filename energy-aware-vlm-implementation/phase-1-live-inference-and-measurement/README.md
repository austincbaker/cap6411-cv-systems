# Phase 1 — Establish live inference and measurement

A camera and real-time replay both produce local VLM responses, the sensor domain is documented, pilot events can be labeled, and the fixed-interval baseline has usable logs.

**Master plan:** [Phase 1](../plan.md#phase-1--establish-live-inference-and-measurement-week-1). **Schedule:** Week 1. All status fields track implementation, not planning.

## Prerequisites

Ubuntu 22.04.5 LTS is confirmed. Independent discovery/build items 1a, 1b, 1c, 1e and 1f can begin now; model, device and sensor checks are work to perform, not facts assumed to have passed. Item 1d waits for 1a–1c.

## Items

| Item | Owner | Depends on | Scope |
| --- | --- | --- | --- |
| [1a — Persistent local VLM inference](./1a-local-vlm-inference.md) | Austin | None | Required |
| [1b — Power and energy telemetry](./1b-power-telemetry.md) | Austin | None | Required |
| [1c — Webcam and real-time replay sources](./1c-webcam-and-replay.md) | Alejandro | None | Required |
| [1d — Fixed-interval baseline application](./1d-fixed-interval-application.md) | Alejandro | [1a](../phase-1-live-inference-and-measurement/1a-local-vlm-inference.md), [1b](../phase-1-live-inference-and-measurement/1b-power-telemetry.md), [1c](../phase-1-live-inference-and-measurement/1c-webcam-and-replay.md) | Required |
| [1e — Event definitions and pilot dataset](./1e-event-definitions-and-pilot-data.md) | James | None | Required |
| [1f — Measurement protocol and research review](./1f-measurement-protocol-and-research.md) | Shawn | None | Required |

## Planning readiness

Austin confirmed direct expansion of `1a`, `1b`, `1c`, `1e` and `1f`; their item files now contain detailed implementation notes. All implementation tasks remain not started. Item `1d` stays lean until its runtime dependencies are implemented. A repository `AGENTS.md` now exists; the absence of a committed dependency/test setup remains the master plan's R09 risk.

## Exit criteria

- [ ] A camera and real-time replay both produce local VLM responses, the sensor domain is documented, pilot events can be labeled, and the fixed-interval baseline has usable logs.
- [ ] All required item acceptance criteria are verified and their Definition-of-Done rows contain code or artifact references.
- [ ] Shared documents and schema changes are reviewed with their consumers; raw results are preserved.
