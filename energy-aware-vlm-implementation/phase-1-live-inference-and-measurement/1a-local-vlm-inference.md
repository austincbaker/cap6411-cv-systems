# 1a — Persistent local VLM inference

**Live issue:** [#1](https://github.com/austincbaker/cap6411-cv-systems/issues/1)
**Priority:** P0 (`priority:P0`)
**GitHub blocked by:** None

**Phase**: 1 — Establish live inference and measurement
**Status**: 🟡 In progress
**Plan refs**: [Master plan](../plan.md#phase-1--establish-live-inference-and-measurement-week-1); D03, D09, D11; R05, R09
**Depends on**: None; independent Phase 1 discovery/build item
**Blocks**: [1d](../phase-1-live-inference-and-measurement/1d-fixed-interval-application.md), [2c](../phase-2-gated-application-and-contracts/2c-validated-vlm-responses.md)

## Scope

Owner: Austin. Establish persistent local multimodal inference using a supported compact model and a recorded llama.cpp build. Keep the primary backend CPU-first and return bounded responses with explicit request failures.

## Tasks

- [x] Configure a repeatable local development and llama.cpp setup and record model/build/backend provenance.
- [x] Implement the persistent inference interface and record latency, output bounds and request failures.
- [x] Document a small live smoke check and the supported fallback model if the initial candidate is impractical.

## Files to be touched

- `src/vlm/client.py` — Proposed persistent inference interface.
- `README.md` — Repeatable setup and smoke-check instructions.
- `AGENTS.md` — Replace the setup and test-command TODOs with pointers to the committed route (rev. 4).

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

- [ ] Which model/build/quantization combination passes the WSL2 platform compatibility and latency check? **Result:** The pinned SmolVLM2-500M Q8_0 model/projector passes on the WSL2 experiment platform (D11); the owner confirms and closes this question. See `docs/validation-1a-1b.md`.

## Acceptance criteria

- [ ] A supported local model answers repeated image requests with a configured generation bound on the WSL2 experiment platform (owner-performed or owner-approved).
- [x] Timeouts or unavailable service errors are distinguishable from valid descriptions.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Configure a repeatable local development and llama.cpp setup and record model/build/backend provenance. | [Tasks](#tasks) | A second member can follow the setup and identify the exact model and runtime used. | scripts/llama_runtime.py:46, configs/inference.json:1, README.md:7 | 🟡 |
| 2 | Implement the persistent inference interface and record latency, output bounds and request failures. | [Tasks](#tasks) | Repeated image requests use one loaded service and return successful responses or explicit failure records. | src/vlm/client.py:86, tests/test_inference_client.py:14 | 🟢 |
| 3 | Document a small live smoke check and the supported fallback model if the initial candidate is impractical. | [Tasks](#tasks) | The chosen candidate passes the smoke check without dedicated-GPU use. | src/vlm/smoke.py:18, docs/validation-1a-1b.md:9 | 🟡 |
| 4 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | tests/test_inference_client.py:64, docs/validation-1a-1b.md:9 | 🟡 |

## Implementation notes

### Context and boundaries

Austin owns this item. Apply D03 (one primary model and CPU-first inference), D09 (measure optimizations rather than assume them) and D11 (Ubuntu 22.04.5 LTS). R05 and R09 cover model limitations and the absence of established setup conventions. The existing repository has only the project heading in `README.md:1` and a Python-oriented `.gitignore`; there is no inference implementation to extend. All project symbols and file responsibilities below are proposed.

This item prepares a persistent inference service and its client. Gate logic, energy admission, final event schemas and cache optimization remain in their assigned later items. The unresolved model question requires a hardware smoke check during implementation, not a guessed model selection during planning.

### Ordered implementation breakdown

1. Inspect the implementation environment on the actual Ubuntu laptop and record Python, compiler/build prerequisites, available RAM, CPU and intended backend. Do not treat the current agent environment as the test laptop.
2. Establish one documented Python installation/dependency route for this repository, following any conventions introduced before implementation begins. Capture the chosen dependency versions and make the proposed module/test commands work from the repository root.
3. Select a small supported SmolVLM-family candidate, verifying its current llama.cpp support and matching language-model/projector artifacts. Record model repository/revision, quantization, filenames and llama.cpp commit.
4. Build or obtain the selected llama.cpp revision using its own documented Ubuntu instructions. Verify CPU placement for the language model and vision projector from build options and runtime logs; an integrated-GPU run gets a separate recorded configuration.
5. Start one local `llama-server` process and retain it across requests. Document its startup command and readiness condition in `README.md`; the Python client should connect to an existing service rather than reload weights for every frame.
6. In `src/vlm/client.py`, define a small proposed client interface that accepts encoded image data, prompt text, a generation bound and caller-provided frame identity. Keep image encoding/policy decisions outside the transport boundary.
7. Use the selected server revision's documented multimodal request format. The current upstream server documents image content through `POST /v1/chat/completions` with base64 image data; verify the pinned build before finalizing request construction. [Upstream server reference](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).
8. Make each request carry an explicit finite generation bound and finite connection/response timeouts. Validate the image and required inputs locally so an empty image or invalid bound fails before submitting expensive work.
9. Return the response text together with request ID, source-frame identity, request start and response-available times, elapsed duration, completion status and supported usage/timing fields. Keep unavailable statistics missing rather than manufacturing token counts.
10. Represent connection failure, timeout, non-success HTTP response, malformed transport output and an empty completion separately from successful text. Keep failed requests visible; avoid unlogged automatic retries that distort invocation counts and energy measurements.
11. Reuse the client/session for repeated calls and release its resources cleanly on interruption. Document whether a timed-out server request has actually stopped; the application must not assume that a client timeout cancels inference or immediately launch overlapping work.
12. Run a short smoke sequence using at least two visibly different images and repeated requests. Record actual latency, memory behavior and output lengths; if the candidate is impractical, try a smaller supported candidate and retain the reason for switching before the primary model is frozen.

### Inputs, outputs and handoff

- **Input:** Locally encoded frame, source/frame identifier, prompt, generation bound and runtime connection settings.
- **Output:** Successful text or an explicit request failure with timing and provenance. Suggested names such as `frame_id` and `response_available_s` are provisional; item 2d owns final field names and units.
- **To Alejandro:** A documented import/call example and lifecycle behavior for item 1d. One request consumes one frame; this interface does not own the capture loop or queue.
- **To James/Shawn:** Example successful and failed request records, actual model/build/backend identity and available latency/token observations. Full fixture/schema freeze still belongs to item 2d.

Use monotonic timing for durations and retain caller-provided source-video time separately. A fresh frame is new evidence; cache behavior must not cause an earlier image's answer to be presented as current.

### Verification and acceptance interpretation

Add focused transport-behavior checks in proposed `tests/test_inference_client.py` using a fake server/session: image request construction, output bound, valid response, missing usage statistics, timeout, malformed body and connection failure. These checks should not download models or require a webcam. Run them through the repository's adopted test setup.

The live smoke check establishes model compatibility that a fake transport cannot prove. Demonstrate that one running server handles repeated images, a changed image changes the evidence being processed, and a stopped service yields a recognizable failure. Do not require exact generated wording across requests or claim full event accuracy from this check.

### Files and evidence recap

- `src/vlm/client.py` — proposed reusable transport, input checks, response/timing extraction and resource cleanup.
- `README.md` — existing setup entry point; document the selected Ubuntu/Python/model/build configuration, startup and smoke procedure.
- `tests/test_inference_client.py` — proposed targeted checks of successful and failed transport behavior.
- The chosen dependency manifest may need to be added during setup; record that choice once, with versions, rather than introducing competing installation paths.

Close the original matrix only when setup is reproducible, the selected model really runs, and request outcomes are reviewable. Model/build/quantization selection remains the original implementation-time verification item; no additional user decision is needed to begin.


## Execution record — 2026-10-27

Software implemented locally with a pinned CPU runtime, persistent HTTP client, smoke CLI and focused tests. Under D11 the WSL2 smoke check is platform evidence; owner review closes the item. Four alternating images passed on one server process; all output lengths were below the 32-token bound. A stopped-service check recorded one connection failure without retrying. The test service was stopped after verification. Evidence is in `docs/validation-1a-1b.md` and `docs/examples/`. GitHub issue #1 remains open for review; source changes are on branch `feat/1a-1b-inference-telemetry`.
