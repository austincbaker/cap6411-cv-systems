# 1e — Event definitions and pilot dataset

**Live issue:** [#5](https://github.com/austincbaker/cap6411-cv-systems/issues/5)
**Priority:** P0 (`priority:P0`)
**GitHub blocked by:** None

**Phase**: 1 — Establish live inference and measurement
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-1--establish-live-inference-and-measurement-week-1); D01, D02, D07; R07
**Depends on**: None; independent Phase 1 discovery/build item
**Blocks**: [2a](../phase-2-gated-application-and-contracts/2a-change-and-relevance-gate.md), [2c](../phase-2-gated-application-and-contracts/2c-validated-vlm-responses.md), [2d](../phase-2-gated-application-and-contracts/2d-evaluation-contracts-and-fixtures.md), [2e](../phase-2-gated-application-and-contracts/2e-annotated-dataset-and-splits.md)

## Scope

Owner: James, with recordings contributed by all members. Define a narrow event vocabulary for the selected application and capture pilot clips containing meaningful and irrelevant changes. Check whether a public subset can support an external validation without confusing its original labels with project events.

## Tasks

- [ ] Document the event vocabulary, observable onset/end rules and no-event cases.
- [ ] Collect representative pilot clips and verify one public-data candidate's access, terms and label fit.
- [ ] Create pilot annotations and describe grouping by session/environment.

## Files to be touched

- `data/README.md` — Proposed event/capture/annotation protocol.
- `data/annotations/` — Proposed task-specific annotations; raw videos remain local unless sharing is permitted.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

- [ ] Finalize the task-specific event labels in Week 1 using the parent plan's default workspace scope unless the team explicitly chooses another application.

## Acceptance criteria

- [ ] Pilot labels distinguish meaningful change from irrelevant activity and lighting variation.
- [ ] Public dataset access/fit is verified or the mismatch is documented without claiming unsupported event ground truth.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Document the event vocabulary, observable onset/end rules and no-event cases. | [Tasks](#tasks) | Two team members can label the same pilot events using the written rules. | — | ⬜ |
| 2 | Collect representative pilot clips and verify one public-data candidate's access, terms and label fit. | [Tasks](#tasks) | Pilot recordings cover idle, meaningful change and irrelevant motion; public-data feasibility is recorded. | — | ⬜ |
| 3 | Create pilot annotations and describe grouping by session/environment. | [Tasks](#tasks) | Each pilot event has an ID and observable interval linked to a known clip. | — | ⬜ |
| 4 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

## Implementation notes

### Context and boundaries

James owns the pilot dataset and annotation rules; all members contribute recordings. Apply D01 (one application, workspace changes by default), D02 (James later owns evaluation software), D07 (temporal ground truth and grouped splits) and R07 (public-data mismatch).

The repository has no dataset or annotation tools. `data/README.md` and `data/annotations/` are proposed outputs. This item defines a workable pilot; item 2e completes the dataset/splits and items 3d/3e implement James's matcher/scorer. Do not make a new annotation UI a prerequisite.

### Ordered implementation breakdown

1. Write a short task definition for fixed-camera workspace changes in `data/README.md`. Define what the assistant should report and distinguish observable object state from an inferred action or intent.
2. Draft a small event vocabulary appropriate to that task, including object appearance/no-longer-visible or relocation when visually supported. Treat names as pilot candidates until James and Alejandro agree on the final labels; do not silently reinterpret visibility loss as physical removal.
3. Define annotation boundaries in observable terms: earliest reliable visual evidence, end of the transition or relevant state interval, involved object, region if useful, priority and ambiguity notes.
4. Include explicit negative categories/scenarios such as walking in the background, lighting changes and idle periods. Negative examples are useful for false-trigger analysis, but must not automatically be counted as positive task events.
5. Give each contributor a short recording checklist with camera placement, clip/session identifiers and expected scenarios. Vary background, lighting, object size, event timing and camera angle while retaining the fixed-webcam task.
6. Capture a few pilot clips before requesting the full 30–36-clip target. Include one small meaningful change, one irrelevant disturbance, occlusion and an uneventful stretch; keep raw recordings local unless sharing permission is established.
7. Annotate the pilot in a simple editable tabular form. Retain clip/session ID, event ID, tentative class, object when applicable, start/end times, priority and visibility/ambiguity notes; leave exact column names to the shared contract in item 2d.
8. Have another member independently label selected pilot events using the written instructions. Compare onset/end boundaries and labels, resolve disagreements, and update the instructions with actual ambiguous examples.
9. Review clips at the source frame times used by Alejandro's replay, not at inference completion times. Reserve separate guidance for how long a persistent post-change state remains eligible for scoring; James and Alejandro freeze that with item 2d before held-out testing.
10. Inspect one accessible public candidate from the master plan, starting with indoor-activity videos if the default task is retained. Verify current access, permitted uses, camera viewpoint, temporal coverage and whether project events need new annotations.
11. Record the public dataset's actual provenance, selected clip identifiers and label mapping. If action labels or tracking boxes cannot establish addition/removal events, document the mismatch and annotate a small compatible subset or omit it with the limitation recorded.
12. Describe session/environment grouping now so later development/validation/test allocation avoids near-duplicate leakage. Do not tune thresholds on the held-out environment or repeatedly relabel test clips to fit model outputs.
13. Hand the pilot definitions and annotated examples to Austin/Alejandro for prompt/gate work and to Shawn for scenario balance. Include difficult and ambiguous events so the system's failure analysis does not become an afterthought.

### Artifact contract and later coding contribution

The pilot should be usable in a spreadsheet or plain CSV without model inference. Keep stable event IDs and video-relative timestamps. Record whether an interval denotes a transition or an ongoing visible state; the scorer cannot safely infer that distinction from class names.

James's later coding tasks consume these annotations: one-to-one event matching, aggregate metrics and error reports. Save a few small, hand-scored hypothetical prediction/event examples alongside the protocol for item 2d's shared fixtures. These examples should include a correct event, wrong label, missed event and duplicate, without prematurely selecting a matching algorithm.

The final contract, matching tolerance and reporting horizon are still owned by item 2d. Event vocabulary finalization is the existing Week 1 team deliverable, not a new architecture choice introduced by this expansion.

### Verification and acceptance interpretation

Have a second annotator demonstrate that the pilot instructions are usable and that timestamps fall within the video duration. Check unique IDs, valid ordered intervals, recognized draft labels and traceability to the source clip. This can be a manual review at this stage; no new coding requirement is added to James's early workload.

A successful public-data check records access/fit or a specific mismatch. Availability of a named dataset alone is insufficient. The full clip/event target and final grouped splits belong to item 2e, so pilot acceptance should not depend on completing the entire collection first.

### Files and evidence recap

- `data/README.md` — proposed task vocabulary, capture checklist, temporal-label guidance, ambiguity examples, provenance and split rules.
- `data/annotations/` — proposed pilot records and clip/session inventory; omit unapproved raw participant video from shared artifacts.

Close this item when the task is labelable, pilot evidence is organized and a public candidate has been honestly assessed. Keep the original vocabulary check open until that implementation work is performed.
