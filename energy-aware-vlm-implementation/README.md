# Energy-aware VLM implementation plans

This directory breaks the four-week research project into 27 owned work items: 26 required outcomes and one optional failure-review viewer. Ubuntu 22.04.5 LTS is the primary platform, with CPU-first local inference. This directory contains plans, not a working application.

## Reading order and document authority

1. Read [plan.md](./plan.md), the local reading copy of the [canonical master plan](../TODO_Plan/build-energy-aware-vlm-assistant.md).
2. Read the relevant phase README, then the owned item plans listed below.
3. Review dependencies, acceptance criteria and the Definition-of-Done matrix before implementation.

The original TODO is canonical. When decisions change, update it in place with a revision entry and refresh `plan.md`, rebasing only its relative item links. Do not introduce an independent decisions file. Repository source/test paths in plans are repository-relative and proposed until implemented.

## Directory layout

```text
energy-aware-vlm-implementation/
├── README.md
├── plan.md
├── phase-1-live-inference-and-measurement/
│   ├── README.md
│   └── 6 owned item plans
├── phase-2-gated-application-and-contracts/
│   ├── README.md
│   └── 6 owned item plans
├── phase-3-budget-control-and-evaluation-tools/
│   ├── README.md
│   └── 8 owned item plans
└── phase-4-experiments-report-and-demonstration/
    ├── README.md
    └── 7 owned item plans
```

## Phases

| Phase | Week | Items | Outcome |
| --- | --- | --- | --- |
| [1 — Establish live inference and measurement](./phase-1-live-inference-and-measurement/README.md) | 1 | 6 | Local baseline and verified telemetry |
| [2 — Deliver a gated application and evaluation contracts](./phase-2-gated-application-and-contracts/README.md) | 2 | 6 | Gated application, data and stable handoff contracts |
| [3 — Integrate budget control and owned evaluation tools](./phase-3-budget-control-and-evaluation-tools/README.md) | 3 | 8 | Budget-aware system and owned evaluation tools |
| [4 — Complete experiments, report and demonstration](./phase-4-experiments-report-and-demonstration/README.md) | 4 | 7 | Final experiments, report and demonstration |

## Ownership and item index

Austin owns local inference and energy admission. Alejandro owns capture, cascade and the integrated application. James owns the dataset and event-scoring software. Shawn owns measurement methods, benchmark automation and energy/report generation. All members contribute recordings and review findings.

| Item | Owner | Outcome | Depends on | Priority | GitHub issue | Planning detail |
| --- | --- | --- | --- | --- | --- | --- |
| [1a](./phase-1-live-inference-and-measurement/1a-local-vlm-inference.md) | Austin | Persistent local VLM inference | None | P0 | [#1](https://github.com/austincbaker/cap6411-cv-systems/issues/1) | Expanded |
| [1b](./phase-1-live-inference-and-measurement/1b-power-telemetry.md) | Austin | Power and energy telemetry | None | P0 | [#2](https://github.com/austincbaker/cap6411-cv-systems/issues/2) | Expanded |
| [1c](./phase-1-live-inference-and-measurement/1c-webcam-and-replay.md) | Alejandro | Webcam and real-time replay sources | None | P0 | [#3](https://github.com/austincbaker/cap6411-cv-systems/issues/3) | Expanded |
| [1d](./phase-1-live-inference-and-measurement/1d-fixed-interval-application.md) | Alejandro | Fixed-interval baseline application | `1a`, `1b`, `1c` | P0 | [#4](https://github.com/austincbaker/cap6411-cv-systems/issues/4) | Lean |
| [1e](./phase-1-live-inference-and-measurement/1e-event-definitions-and-pilot-data.md) | James | Event definitions and pilot dataset | None | P0 | [#5](https://github.com/austincbaker/cap6411-cv-systems/issues/5) | Expanded |
| [1f](./phase-1-live-inference-and-measurement/1f-measurement-protocol-and-research.md) | Shawn | Measurement protocol and research review | None | P1 | [#6](https://github.com/austincbaker/cap6411-cv-systems/issues/6) | Expanded |
| [2a](./phase-2-gated-application-and-contracts/2a-change-and-relevance-gate.md) | Alejandro | Change gate and relevance rules | `1c`, `1d`, `1e` | P1 | [#7](https://github.com/austincbaker/cap6411-cv-systems/issues/7) | Lean |
| [2b](./phase-2-gated-application-and-contracts/2b-latest-frame-and-scene-state.md) | Alejandro | Latest-frame scheduling and scene state | `1d`, `2a`, `2c` | P1 | [#8](https://github.com/austincbaker/cap6411-cv-systems/issues/8) | Lean |
| [2c](./phase-2-gated-application-and-contracts/2c-validated-vlm-responses.md) | Austin | Validated prompts, responses and inference logs | `1a`, `1e` | P1 | [#9](https://github.com/austincbaker/cap6411-cv-systems/issues/9) | Lean |
| [2d](./phase-2-gated-application-and-contracts/2d-evaluation-contracts-and-fixtures.md) | Austin (lead) and Alejandro | Versioned evaluation contracts and sample artifacts | `1b`, `1d`, `1e`, `1f`, `2c` | P0 | [#10](https://github.com/austincbaker/cap6411-cv-systems/issues/10) | Lean |
| [2e](./phase-2-gated-application-and-contracts/2e-annotated-dataset-and-splits.md) | James | Annotated dataset, grouped splits and scoring examples | `1e`, `2d` | P1 | [#11](https://github.com/austincbaker/cap6411-cv-systems/issues/11) | Lean |
| [2f](./phase-2-gated-application-and-contracts/2f-benchmark-configurations.md) | Shawn | Benchmark protocol and configuration templates | `1f`, `2d` | P1 | [#12](https://github.com/austincbaker/cap6411-cv-systems/issues/12) | Lean |
| [3a](./phase-3-budget-control-and-evaluation-tools/3a-energy-budget-controller.md) | Austin | Calibrated energy-budget admission | `1b`, `2d`, `2f` | P1 | [#13](https://github.com/austincbaker/cap6411-cv-systems/issues/13) | Lean |
| [3b](./phase-3-budget-control-and-evaluation-tools/3b-inference-cost-ablations.md) | Austin | Measured image, output and cache ablations | `2c`, `2d`, `2f` | P2 | [#14](https://github.com/austincbaker/cap6411-cv-systems/issues/14) | Lean |
| [3c](./phase-3-budget-control-and-evaluation-tools/3c-budget-aware-application.md) | Alejandro | Integrated budget-aware application | `2a`, `2b`, `3a` | P1 | [#15](https://github.com/austincbaker/cap6411-cv-systems/issues/15) | Lean |
| [3d](./phase-3-budget-control-and-evaluation-tools/3d-event-matching.md) | James | Deterministic one-to-one event matching | `2d` | P1 | [#16](https://github.com/austincbaker/cap6411-cv-systems/issues/16) | Lean |
| [3e](./phase-3-budget-control-and-evaluation-tools/3e-event-scoring-cli.md) | James | Event metrics and scoring command | `3d` | P1 | [#17](https://github.com/austincbaker/cap6411-cv-systems/issues/17) | Lean |
| [3f](./phase-3-budget-control-and-evaluation-tools/3f-benchmark-runner.md) | Shawn | Repeated-trial benchmark runner | `1d`, `2d`, `2f` | P1 | [#18](https://github.com/austincbaker/cap6411-cv-systems/issues/18) | Lean |
| [3g](./phase-3-budget-control-and-evaluation-tools/3g-energy-analysis-and-reporting.md) | Shawn | Energy analysis, comparison tables and figures | `2d`, `2f`, `3e`, `3f` | P1 | [#19](https://github.com/austincbaker/cap6411-cv-systems/issues/19) | Lean |
| [3h](./phase-3-budget-control-and-evaluation-tools/3h-pilot-and-evaluation-freeze.md) | All | Pilot comparison and final evaluation freeze | `2e`, `3a`, `3b`, `3c`, `3e`, `3f`, `3g` | P1 | [#20](https://github.com/austincbaker/cap6411-cv-systems/issues/20) | Lean |
| [4a](./phase-4-experiments-report-and-demonstration/4a-held-out-event-evaluation.md) | James | Held-out event and description evaluation | `3h`, `4b` | P1 | [#21](https://github.com/austincbaker/cap6411-cv-systems/issues/21) | Lean |
| [4b](./phase-4-experiments-report-and-demonstration/4b-repeated-energy-experiments.md) | Shawn | Repeated energy trials and final plots | `3h` | P1 | [#22](https://github.com/austincbaker/cap6411-cv-systems/issues/22) | Lean |
| [4c](./phase-4-experiments-report-and-demonstration/4c-stability-and-defect-resolution.md) | Austin and Alejandro | Stability run and blocking defect resolution | `3h` | P1 | [#23](https://github.com/austincbaker/cap6411-cv-systems/issues/23) | Lean |
| [4d](./phase-4-experiments-report-and-demonstration/4d-budget-and-energy-findings.md) | Austin and Shawn | Budget adherence and energy findings | `4a`, `4b`, `4c` | P1 | [#24](https://github.com/austincbaker/cap6411-cv-systems/issues/24) | Lean |
| [4e](./phase-4-experiments-report-and-demonstration/4e-research-report.md) | James and Shawn | Final research report with technical contributions | `4a`, `4b`, `4c`, `4d` | P1 | [#25](https://github.com/austincbaker/cap6411-cv-systems/issues/25) | Lean |
| [4f](./phase-4-experiments-report-and-demonstration/4f-demo-and-reproducibility.md) | All | Demonstration and independent reproduction | `4a`, `4b`, `4c`, `4e` | P1 | [#26](https://github.com/austincbaker/cap6411-cv-systems/issues/26) | Lean |
| [4g](./phase-4-experiments-report-and-demonstration/4g-failure-review-viewer.md) | James | Optional failure-review viewer (optional) | `3e` | P3 | [#27](https://github.com/austincbaker/cap6411-cv-systems/issues/27) | Lean |

## Status conventions and how to use these plans

- `⬜ Not started` — implementation has not begun.
- `🟡 In progress` — implementation is underway.
- `🟢 Complete` — all acceptance criteria and evidence rows are verified.
- `🔴 Blocked` — include the concrete reason and unmet prerequisite.

The Definition-of-Done matrix is the canonical implementation completion view. Its `Implemented at` cells start as `—`; implementers fill them with repository-relative code or artifact locations and line references when closing a row. An empty evidence cell means the row is not complete. Planning expansion must leave status, task checkboxes and matrix rows untouched.

A lean stub ends in `<!-- impl-notes-anchor -->`. Direct expansion replaces only that sentinel with one `## Implementation notes` section. A stub containing that heading is already expanded and must be skipped on repeat runs. Do not expand every later phase merely because it exists.

## Current implementation starting points

The five independent items are `1a` (Austin: VLM), `1b` (Austin: telemetry), `1c` (Alejandro: capture), `1e` (James: pilot data) and `1f` (Shawn: methods). Item `1d` becomes ready after `1a`, `1b` and `1c` are implemented. Ubuntu is settled; model and sensor success must still be verified on the actual laptop.

Austin confirmed these five items for direct expansion with `fill-plan-stubs`. They now contain detailed implementation notes; the other 22 remain lean and unchanged. No application code was implemented and every implementation status is still `⬜ Not started`. No new material planning questions surfaced. A repository `AGENTS.md` now exists (Revision 4); setup and test commands remain TODO until `1a`, which is still R09 in the master plan. See Revision 2 for the expansion record.


## Live GitHub tracking

All 27 items are published in [the repository issue tracker](https://github.com/austincbaker/cap6411-cv-systems/issues), assigned to their planned owners and prioritized using `priority:P0` through `priority:P3`. Native blocked-by relationships mirror the 61 prerequisite edges (rev. 6) in the master plan. Five independent starting items have no blockers.

P0 covers critical foundations/handoffs, P1 required delivery, P2 the inference ablation and P3 the optional viewer. Priority is separate from readiness and required scope. Local implementation statuses and completion matrices remain unchanged; publishing an issue does not mean its implementation has started.
