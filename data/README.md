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
`gesture` in `requests.jsonl`); event rearming behavior remains 2b implementation
work, and all policies must use the same rules before scored trials.

## Running the app on a video

From the repo root, after `uv sync --extra dev` and
`uv run python scripts/llama_runtime.py prepare` (first time only).

1. Start the model server in its own terminal and leave it running:

   ```bash
   uv run python scripts/llama_runtime.py serve
   ```

   Check it with `curl -s http://127.0.0.1:8080/health` (expect `{"status":"ok"}`).
   If it fails with "couldn't bind ... port 8080", a server is already running;
   use it, or stop it with `pkill -f llama-server`.

2. In a second terminal, run a video. **Each `--run-dir` must be a new folder name**,
   otherwise the app exits without running.

   ```bash
   # fixed: ask the VLM every tick
   uv run python -m app.main --source replay --video data/videos/recording_1_thumbs.mov \
       --interval-s 2 --no-display --run-dir results/rec1_fixed

   # gated: ask only when the change gate fires
   uv run python -m app.main --source replay --video data/videos/recording_1_thumbs.mov \
       --policy gated --interval-s 1 --no-display --run-dir results/rec1_gated
   ```

   Replay runs in real time: a 20-minute video takes 20 minutes. Use `tmux` for long
   videos, or `--duration-s 300` to stop early. The last line ends in `exit=0` on success.

3. See what the VLM said and when (`gesture` is the checked answer; it is empty when
   the answer did not validate, and `answer_error` says why):

   ```bash
   python3 -c "import json;[print(round(r['source_time_s'],1), r['status'], r['gesture'], r['answer_error']) for r in map(json.loads, open('results/rec1_fixed/requests.jsonl'))]"
   ```

4. Check whether the VLM looked during each gesture and named it. There is no event
   scorer yet (item 3d); `scripts/gate_check.py` checks requests against one video's
   windows at a time:

   ```bash
   grep ',recording_1_thumbs,' data/annotations/pilot.csv \
     | awk -F, 'BEGIN{print "label,onset_s,end_s"}{print $4","$5","$6}' > /tmp/rec1_windows.csv
   uv run python scripts/gate_check.py results/rec1_fixed results/rec1_gated \
       --windows /tmp/rec1_windows.csv --tolerance-s 1 \
       --name thumbs_up=thumb --name peace_sign="peace|v-sign|victory"
   ```

   "windows caught" means a frame inside the gesture was sent; "named" means the
   checked answer was that gesture.

### Notes from the pilot runs

- One VLM answer takes about 3.7-5 s on the CPU server, so `--interval-s 2` actually
  looks every 4-6 s. Skipped ticks are logged as `tick_skipped_busy` in `drops.jsonl`.
- Every request asks the gesture question, and the answer is constrained to
  `{"hands": "<a few words>", "gesture": "thumbs_up" | "peace_sign" | "none"}` (item 2c).
- Hold gestures 5+ s and start them at least 5 s into a recording, or the sampler may miss them.
  Example: on one fixed 2 s run of `recording_1_thumbs` the VLM looked at 4 s and 10 s and
  never saw the 5-8 s thumbs up.
