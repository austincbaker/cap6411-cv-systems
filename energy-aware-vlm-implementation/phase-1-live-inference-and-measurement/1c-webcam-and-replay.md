# 1c — Webcam and real-time replay sources

**Live issue:** [#3](https://github.com/austincbaker/cap6411-cv-systems/issues/3)
**Priority:** P0 (`priority:P0`)
**GitHub blocked by:** None

**Phase**: 1 — Establish live inference and measurement
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-1--establish-live-inference-and-measurement-week-1); D05, D06, D11; R06, R08
**Depends on**: None; independent Phase 1 discovery/build item
**Blocks**: [1d](../phase-1-live-inference-and-measurement/1d-fixed-interval-application.md), [2a](../phase-2-gated-application-and-contracts/2a-change-and-relevance-gate.md)

## Scope

Owner: Alejandro. Provide interchangeable webcam and recorded-video input with explicit frame timestamps. Replay at real-time speed so fixed and adaptive policies can be compared on the same content.

## Tasks

- [ ] Implement webcam capture with timestamped frames and explicit device errors.
- [ ] Implement real-time replay with source-video timing and deterministic frame identity.
- [ ] Release camera/file resources on completion or interruption and document source metadata.

## Files to be touched

- `src/capture/webcam.py` — Proposed camera source.
- `src/capture/replay.py` — Proposed paced recorded source.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

None newly surfaced. Apply the parent plan and resolve measured settings in the prerequisite items.

## Acceptance criteria

- [ ] Both input types deliver identifiable frames on a documented time base.
- [ ] Replay finishes cleanly at EOF and input failures do not look like successful idle periods.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Implement webcam capture with timestamped frames and explicit device errors. | [Tasks](#tasks) | Available camera frames are delivered and inaccessible devices fail visibly. | — | ⬜ |
| 2 | Implement real-time replay with source-video timing and deterministic frame identity. | [Tasks](#tasks) | Replays preserve video-relative timing without running as fast as decoding allows. | — | ⬜ |
| 3 | Release camera/file resources on completion or interruption and document source metadata. | [Tasks](#tasks) | Both source types close cleanly and can be opened again. | — | ⬜ |
| 4 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

## Implementation notes

### Context and boundaries

Alejandro owns both input sources. Apply D05 (bounded downstream work), D06 (distinct time bases), D11 (Ubuntu), R06 (fair sampling) and R08 (capture versus replay overhead). Neither capture file exists yet, so the interfaces described here are proposed rather than existing symbols.

Provide frames and timing, not event decisions or VLM calls. Item 1d supplies the first consumer; later items 2a/2b own the gate and one-active/one-pending inference lifecycle.

### Ordered implementation breakdown

1. Confirm the camera device can be opened on the primary Ubuntu laptop and select a small local recording for replay checks. Record the actual input backend, dimensions and reported frame rate.
2. Implement a common minimal source behavior across `src/capture/webcam.py` and `src/capture/replay.py`: open, deliver timestamped frames, signal end/error and close. Share record definitions only if needed; avoid introducing a large capture framework.
3. Keep a frame record containing source identity, sequential frame ID, image pixels, observed dimensions, source-relative time and host monotonic delivery/capture time. The exact record class/field names will be agreed with Austin and finalized in item 2d.
4. For webcam input, validate the device identifier, distinguish failed initialization from a later read failure, and use a documented host-side timestamp if a trustworthy device timestamp is unavailable.
5. Observe actual device settings after requesting dimensions or frame rate. Camera/backend behavior can differ from requested settings; preserve observed metadata rather than asserting the request was honored.
6. For recorded input, verify file readability and decode initialization before starting the run clock. Use media presentation timestamps when reliable; if using frame index divided by a fixed frame rate, require a valid rate and record that constant-frame-rate assumption.
7. Pace replay with monotonic deadlines relative to the source timestamps. A 60-second recording should represent approximately 60 seconds of observation, excluding separately recorded setup/teardown; decoding speed must not define simulated event time.
8. Keep source acquisition timing independent of model completion when integrating with item 1d. A slow VLM must not turn real-time replay into serial decode-after-inference playback. Define how late frames are skipped or surfaced, and record their identities/reasons.
9. Keep source ordering and IDs stable for repeated replay. When runtime timing causes drops, preserve those drops as observations in the run record; do not claim bit-for-bit identical delivered frame sets under different load.
10. Normalize the image layout/color convention at the source/consumer boundary and document it. The existing OpenCV API provides `VideoCapture` with open/read/close behavior; verify the installed version before use. [OpenCV capture reference](https://docs.opencv.org/4.x/d8/dfe/classcv_1_1VideoCapture.html).
11. Treat normal EOF, unreadable/corrupt media, empty decoded frames and camera disconnection as distinct outcomes where the backend supports that distinction. If an early decode failure cannot be distinguished from EOF, record an incomplete-source condition rather than claiming full video coverage.
12. Release the device/file in every exit path, including interruption and a downstream exception. Confirm the camera can be reopened after stopping, and ensure source loops do not leave background readers running.
13. Give Austin a short consumer example using frame IDs and separate source/host times. Give James the source-time convention and Shawn the replay pacing/overhead information for their protocols.

### Contract and ownership handoff

The frame's media-relative time locates its visual evidence; host monotonic time aligns acquisition with inference and power traces. A response's availability time is added by the inference/application layer and must never replace source time.

The source should allow the consumer to keep one newest frame without accumulating an inference backlog. Queue policy itself remains item 2b. Any shared frame type or configuration helper is a small implementation detail to agree with Austin, not a reason to couple capture to VLM transport.

Item 2d freezes final field names. Record source kind, video/device identity, actual dimensions/rate/backend, timing method and decode/drop outcomes so later comparisons use the same input interpretation.

### Verification and acceptance interpretation

In proposed `tests/test_capture_sources.py`, use a controlled clock and fake capture to check monotonic pacing, increasing frame IDs, invalid frame-rate metadata, EOF/error distinction and resource release after interruption. A slow fake consumer must not convert the intended real-time source into accelerated or paused playback.

Perform one actual webcam open/read/close/reopen check and one replay whose known duration and event timestamps can be checked against elapsed wall time. Specify a practical pacing tolerance from observed timing before final experiments; do not impose a guessed precision requirement here.

### Files and evidence recap

- `src/capture/webcam.py` — proposed webcam lifecycle and timestamped frames.
- `src/capture/replay.py` — proposed media-time extraction, pacing and completion/error reporting.
- `tests/test_capture_sources.py` — proposed deterministic source/lifecycle checks.

Document camera access and replay timing findings for the baseline owner. No new material planning question was found; measured frame-rate/timestamp reliability is an implementation check within this item's scope.
