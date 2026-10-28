# AGENTS.md

> Living instructions for this repository. Keep repository-wide facts here;
> put package-specific differences in a nested AGENTS.md. Do not treat a TODO
> as an established project convention.

## Keep this file current

- **Fill missing guidance:** Before substantive work, review every TODO below.
  Replace any placeholder whose answer you can verify from the README, code,
  manifests, scripts, or CI. If a section does not apply, say so and explain
  why; if a fact cannot be verified, leave its TODO and report the gap rather
  than guessing. Do not make unrelated code changes just to fill this file.
- **Update changed guidance:** When your work changes the project's purpose,
  stack, layout, contracts, setup, commands, or required checks, update the
  corresponding section in the same change. Do this even if the section has
  already been filled in; an outdated instruction is as misleading as a TODO.
- **Keep instructions usable:** Record exact commands with their working
  directories and any prerequisites. Remove or revise guidance that no longer
  applies, and keep nested AGENTS.md files aligned where their scope overlaps.

## Project overview

- **Purpose:** CAP6411 four-week team research project: an always-on local
  webcam assistant that uses a cheap change gate and an energy-budget
  controller to decide when a compact vision-language model (VLM) analyzes a
  frame, compared against fixed-interval sampling on measured energy, event
  quality and response delay.
- **Stack:** Python application and evaluation tools; a persistent local
  `llama-server` (llama.cpp) running a compact SmolVLM-family model, CPU-first.
  The primary experiment platform is Ubuntu 22.04.5 LTS on the designated
  laptop.
- **Structure:** Planning documents live in `TODO_Plan/` and
  `energy-aware-vlm-implementation/` (see "Planning documents" below). The
  proposed code layout is `app/` (entry point, scene state), `src/capture/`,
  `src/vlm/`, `src/gates/`, `src/energy/`, `src/evaluation/`, `experiments/`
  (scoring, benchmark and analysis commands), `configs/`, `tests/` and
  `tests/fixtures/`, `data/` and `docs/`. Treat a proposed path as real only
  once it exists in the repository.
- **Key contracts:** `docs/data-contracts.md` (planned in item `2d`) is the
  authoritative file contract: versioned JSONL prediction and request logs, CSV
  annotations and power samples, and a JSON run manifest. Evaluation tools
  consume these files, not application internals. Keep source-frame time,
  response-available time and the shared monotonic timeline distinct.
- **External code:** `.cache/llama.cpp/` is a gitignored upstream llama.cpp
  checkout. Do not edit it, and its own `AGENTS.md` does not apply to this
  project.

## Setup and commands

Run commands from the repository root unless stated otherwise. `README.md` is
the single source for install and run steps; keep this section pointing at it
rather than duplicating it once those steps exist.

- **Prerequisites and installation:** TODO: no dependency manifest or install
  procedure is committed yet; item `1a` adds and documents it. Pinned model,
  runtime and dependency versions belong in that committed setup, not here.
- **Run locally:** TODO: no application entry point exists yet; item `1d` adds
  `app/main.py`, and the `llama-server` startup command comes from item `1a`.
- **Build or package:** No build or packaging step is configured.
- **Run a focused test:** TODO: no test setup exists yet. The planned form is
  `python -m pytest tests/<file>.py`.
- **Run the relevant test suite:** TODO: planned as `python -m pytest tests/`
  once the test setup exists.
- **Lint, format, and type-check:** No formatter, linter or type checker is
  configured. Run `git diff --check` for whitespace errors.
- **Required CI checks:** No CI configuration is present in this checkout.

## Planning documents

- `TODO_Plan/build-energy-aware-vlm-assistant.md` is the canonical master plan.
  `energy-aware-vlm-implementation/plan.md` is its synchronized reading copy;
  only the relative item links differ. Change both in the same commit and add
  a revision-log entry for any decision change. Do not create a separate
  decisions file.
- Each work item `1a`–`4g` has one plan file under
  `energy-aware-vlm-implementation/phase-*/` and one GitHub issue (#1–#27)
  with owners, a `priority:P*` label and native blocked-by links. When an
  item's tasks, acceptance criteria or dependencies change, update the issue
  body as well.
- Status markers are `⬜`, `🟡`, `🟢` and `🔴`. Mark a Definition-of-Done row
  `🟢` only with a repository-relative code or artifact reference in its
  `Implemented at` cell. A lean item ends with `<!-- impl-notes-anchor -->`;
  only planning expansion replaces that sentinel.
- Respect item ownership: Austin owns inference and energy (`src/vlm/`,
  `src/energy/`), Alejandro owns capture, gating and the application (`app/`,
  `src/capture/`, `src/gates/`), James owns data and event scoring (`data/`,
  `src/evaluation/`, `experiments/score_events.py`), and Shawn owns methods,
  benchmarks and analysis (`docs/methodology.md`, `experiments/run_benchmarks.py`,
  `experiments/analyze_results.py`). Coordinate edits to shared documents.

## Data and measurement integrity

- Webcam recordings of participants are personal data. Keep raw video and
  permitted public-dataset media local and uncommitted unless sharing
  permission is documented in `data/README.md`. Test fixtures stay small and
  synthetic.
- Record unavailable power, token or timing values as missing, never as zero,
  and keep failed requests and trials visible instead of retrying silently.
- Keep sensor domains separate (CPU/package versus battery/whole laptop) and
  total versus incremental energy separate. Do not label package energy as
  whole-system energy.
- Measured energy, latency and model-compatibility results count only when
  produced on the designated Ubuntu laptop. Do not report measurements from a
  development host such as WSL2 as experiment results.
- Write each run to a new output directory and never overwrite prior results.
  After the item `3h` evaluation freeze, a behavior change requires rerunning
  the affected experiments, and held-out data must not be used for tuning.

## Working approach

- **Read before changing:** Check this file, any instructions closer to the
  files being edited, the README, relevant code, tests, and current git changes.
  Do not overwrite another contributor's work.
- **Make the goal verifiable:** For multi-step work, state a short plan and how
  each step will be checked. Clarify uncertainty when it could change the
  design, security boundary, or requested outcome.
- **Keep changes focused:** Implement the smallest solution that meets the
  request. Match nearby patterns; do not refactor unrelated code or add
  speculative features, configuration, or CI jobs.
- **Reuse existing contracts:** Use established types, schemas, helpers, and
  ownership boundaries instead of creating competing versions. Follow a
  change through its callers, documentation, and tests when its contract changes.
- **Respect generated and external files:** Identify generated outputs,
  vendored code, submodules, and user-provided inputs before editing them.
  Change the authoritative source rather than hand-editing a generated copy.

## Code and documentation

- Follow the repository's configured formatter, linter, naming conventions,
  and language settings. Where no rule exists, match the surrounding code.
- Keep errors actionable and handle expected failures without hiding them.
  Use the project's logging convention; avoid noisy debug output.
- Update documentation, examples and configuration templates when behavior or
  public interfaces change. This repository keeps no changelog; record plan
  decision changes in the master plan's revision log.

## Testing and verification

- Add or update focused tests for changed behavior; for a bug, cover the
  failure that exposed it when practical. Keep fixtures isolated and synthetic.
- Run relevant tests and required lint, format, build, or type checks before
  declaring work complete. Start with focused checks; broaden only as needed
  or as required by the repository's CI contract.
- Distinguish failures introduced by the change from existing failures.
  Report the commands run, their results, and anything not verified.
- Do not run live integration tests, production operations, or costly external
  jobs merely to gain extra confidence. Follow the repository's approval and
  environment rules for those operations.
- Live model, camera and sensor smoke checks are required acceptance evidence
  for items such as `1a`–`1c`, but they run only on the designated laptop and
  are performed or approved by the item owner. Automated tests use fake
  services, sensors and clocks, and must not download models or need a webcam.

## Security and data

- Never commit or print secrets, tokens, private keys, or real personal data.
  Use the approved secret store or ignored local configuration, with a
  sanitized example file where appropriate.
- Treat external input and service responses as untrusted. Preserve
  authentication, authorization, validation, and transport-security boundaries;
  do not weaken them as a shortcut.
- Keep test data synthetic and avoid sending repository, customer, or private
  data to external services unless the project permits it.
- Stop and surface potentially destructive, production-affecting, or
  irreversible actions before taking them.

## Git and review

- Inspect the diff before committing. Keep commits limited to the requested
  change and preserve existing authorship settings; never claim another
  contributor's work as your own.
- Follow the repository's commit convention. If it uses Conventional Commits,
  use a concise subject such as `fix(scope): explain the change`. Describe
  the change and its reason, not the tool used to produce it; do not add
  agent-attribution or co-author trailers unless repository policy requires them.
- Do not force-push, discard unrelated changes, create releases, or deploy
  without an explicit request and the repository's required approvals.
- In a pull request, summarize the change, link relevant work, list checks
  performed and remaining risks, and include visual evidence for UI changes
  when useful.

## Communication and maintenance

- Write in clear, direct language for a technical audience. Lead with the
  result, then briefly explain important decisions, trade-offs, and limits.
- If a recurring pitfall or durable convention emerges, update the appropriate
  AGENTS.md so the next contributor can avoid the same mistake. Keep
  machine-specific workarounds and transient task notes out of this template.
