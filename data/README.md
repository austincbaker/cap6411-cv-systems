# Data

Pilot gesture dataset for the always-on VLM project (items 1e and 2e). Owner: James.

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

3. See what the VLM said and when:

   ```bash
   python3 -c "import json;[print(round(r['source_time_s'],1), r['status'], r['text']) for r in map(json.loads, open('results/rec1_fixed/requests.jsonl'))]"
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
   answer mentioned it.

### Notes from the pilot runs

- One VLM answer takes about 3.7-5 s on the CPU server, so `--interval-s 2` actually
  looks every 4-6 s. Skipped ticks are logged as `tick_skipped_busy` in `drops.jsonl`.
- The default prompt asks for an object list, so the VLM never mentions gestures.
  To test gestures, add:
  `--prompt "Is the person making a thumbs up, a peace sign, or neither? Answer with one word: thumbs_up, peace_sign, or none."`
  With that prompt, ignore `predictions.jsonl` (the parser still expects an object list).
- Hold gestures 5+ s and start them at least 5 s into a recording, or the sampler may miss them.
  Example: on one fixed 2 s run of `recording_1_thumbs` the VLM looked at 4 s and 10 s and
  never saw the 5-8 s thumbs up.
