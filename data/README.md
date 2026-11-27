# Data

Selected application: fixed-camera `thumbs_up` and `peace_sign` recognition.
This supersedes the original workspace object-change scope (master-plan revision 9).
Pilot dataset for items 1e and 2e. Owner: James.

## Events

| Label | Starts | Ends |
|---|---|---|
| `thumbs_up` | thumb is fully up, other fingers curled | hand starts to drop or the shape breaks |
| `peace_sign` | index and middle fingers fully up in a V, others curled | hand starts to drop or the shape breaks |

- A gesture must be held at least 0.5 s to count.
- The same gesture again after the hand drops is a new event.
- Waving, scratching, reaching and other hand motion are not events.

## Videos

Raw videos are **not in git** (they are personal data and too large). They are in the
team Google Drive folder: [Link](https://drive.google.com/file/d/1VaOD0aY6IQ65kxMTBN8p248hxRu-Z1na/view?usp=drive_link). Download them into `data/videos/`
(git-ignored). File names must match `video_id` in the annotations exactly
(`thumbs_mov_1.mov` -> `thumbs_mov_1`).

| Videos | Session | Recorded by | Contents |
|---|---|---|---|
| `control.mov` | S1 | James | idle, no events |
| `recording_1..4_*.mov` | S1 | James | ~10 s clips, one gesture each |
| `thumbs_mov_1..6.mov` | S1 | James | 10-30 min, mostly idle, two thumbs ups each |

## Annotations

`data/annotations/pilot.csv`, format in `docs/data-contracts.md` (`annotations.csv`).
Times are seconds from the start of the video. Check it with:

```bash
uv run contracts-check --kind annotation data/annotations/pilot.csv
```

## Dataset status and remaining handoff

The CSV contains 16 events (14 thumbs-up, 2 peace-sign) in 10 videos. All rows
belong to S1 and all split fields are blank. The control clip is listed above
and has no positive annotation rows. These are pilot data; no grouped held-out
split or completion of the planned roughly 30–36 clips/100-event target is claimed.

Item 2e must record the final inventory, session/environment groups, reserved
splits, second-annotator review, hand-scored cases and description-review rubric.
Record a public gesture candidate's access, terms and label fit, or a documented
reason to omit it. Listing candidates in issue #5 or replaying Jester frames does
not by itself establish that assessment. Existing gate-tuning clips have already
been inspected; record that history before assigning any final split.

The 0.5-second rule defines ground truth. The advice below to hold staged gestures
for 5+ seconds helps pilot sampling and does not redefine the event vocabulary.
Occlusion or an uncertain model answer must not be silently treated as a confirmed
negative. Answers are validated against `thumbs_up`, `peace_sign` and `none` (2c,
`gesture` in `requests.jsonl`), and every policy derives gesture onsets and offsets
from them with the same rules (2b, README "Gesture scene state"): a failed or
invalid answer keeps the confirmed gesture, and a gesture after an answer of `none`
is a new onset.

## Running the app on a video

The main README's "Reproduce the main numbers" section has the commands: start the
model server, replay the annotated clips with `scripts/run_pilot_eval.py` under each
policy (fixed every 2 s, gated checked every 0.5 s; always pass `--interval-s`), and score
them with `scripts/score_pilot_eval.py`. `scripts/gate_check.py` checks one clip's runs
against its windows from `annotations/pilot.csv`.

When recording new clips, hold gestures 5+ s and start them at least 5 s into the
recording, or a fixed 2 s sampler may miss them.
