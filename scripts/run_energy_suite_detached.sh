#!/bin/bash
# Run the energy report suite unattended on battery, with the machine prepared in code.
#
#   scripts/run_energy_suite_detached.sh [SUITE_DIR]      # default runs/report-YYYYMMDD-HHMM
#
# Start it detached so it survives the network (and this terminal) going away, e.g.
#   python3 -c 'import os,sys; os.setsid(); os.execvp("bash", ["bash"] + sys.argv[1:])' \
#     scripts/run_energy_suite_detached.sh runs/report-... </dev/null >/dev/null 2>&1 &
#
# At the start it records the battery level and the current Wi-Fi, Bluetooth and brightness,
# turns Wi-Fi and Bluetooth off, switches auto-brightness off and holds the display at
# $BRIGHTNESS, and writes all of it to SUITE_DIR/test_conditions.json (copied into every
# run's suite_run.json). True Tone is not touched. On exit, error or signal a trap turns Wi-Fi
# and Bluetooth back on and puts the brightness back. With the network back it analyses
# $PREV_SUITES and this suite, writes docs/report/5.2-energy-results.md and, unless
# OPEN_PR=0, commits it and opens a draft pull request (never merges).
# Logs: SUITE_DIR/wrapper.log (this script) and SUITE_DIR/suite.log (energy_suite.py).
# Resume a stopped suite by running this script again with the same SUITE_DIR.

set -u
cd "$(dirname "$0")/.." || exit 2
export PATH="/opt/homebrew/bin:$HOME/.local/bin:/usr/sbin:/usr/bin:/bin:/sbin:$PATH"

SUITE="${1:-runs/report-$(date +%Y%m%d-%H%M)}"
CONFIG="${CONFIG:-configs/energy_suite_report.json}"
DURATION_S="${DURATION_S:-180}"
BRIGHTNESS="${BRIGHTNESS:-0.5}"
PREV_SUITES="${PREV_SUITES:-runs/suite-20261127-2017}"
OPEN_PR="${OPEN_PR:-1}"
NO_NETWORK_CHANGES="${NO_NETWORK_CHANGES:-0}"  # 1: leave Wi-Fi and Bluetooth alone (testing)
mkdir -p "$SUITE"
exec >>"$SUITE/wrapper.log" 2>&1
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }
display() { uv run --quiet python scripts/macos_display.py "$@"; }
json_field() { python3 -c "import json,sys; print(json.load(sys.stdin).get('$1', ''))"; }

log "wrapper start: suite $SUITE, config $CONFIG, ${DURATION_S}s runs, pid $$"
BATTERY_LINE="$(pmset -g batt | tail -1)"
BATTERY_START="$(echo "$BATTERY_LINE" | grep -oE '[0-9]+%' | head -1)"
log "battery at start: $BATTERY_LINE"
WIFI_DEV="$(networksetup -listallhardwareports | awk '/Hardware Port: Wi-Fi/{getline; print $2}')"
WIFI_BEFORE="$(networksetup -getairportpower "$WIFI_DEV" 2>&1 | awk '{print $NF}')"
BT_BEFORE="$(blueutil -p 2>&1)"
BRIGHT_BEFORE="$(display get | json_field brightness)"
log "before: Wi-Fi $WIFI_DEV $WIFI_BEFORE, Bluetooth $BT_BEFORE, brightness $BRIGHT_BEFORE"

RESTORED=0
restore() {
  [ "$RESTORED" = 1 ] && return
  RESTORED=1
  log "restore: Wi-Fi on: $(networksetup -setairportpower "$WIFI_DEV" on 2>&1 && echo ok)"
  log "restore: Bluetooth on: $(blueutil -p 1 2>&1 && echo ok) (now $(blueutil -p 2>&1))"
  if [ -n "$BRIGHT_BEFORE" ]; then
    log "restore: brightness $BRIGHT_BEFORE: $(display set-brightness "$BRIGHT_BEFORE")"
  fi
  # The previous auto-brightness setting cannot be read without root; it was on before
  # (brightness drifted between runs on 2026-11-27), so turn it back on.
  log "restore: auto-brightness on: $(display auto-brightness on)"
}
SUITE_PID=""
on_signal() {
  log "signal received"
  if [ -n "$SUITE_PID" ] && kill -0 "$SUITE_PID" 2>/dev/null; then
    # energy_suite.py finishes the current run on SIGTERM (stops its server), then exits
    log "stopping the suite (pid $SUITE_PID) after its current run"
    kill -TERM "$SUITE_PID"
    wait "$SUITE_PID"
  fi
  restore
  exit 130
}
trap restore EXIT
trap on_signal INT TERM HUP
caffeinate -dims -w $$ &  # keep the laptop and display awake for the wrapper's whole life

# ---- prepare the machine
if [ "$NO_NETWORK_CHANGES" = 1 ]; then
  WIFI_RESULT="left on (NO_NETWORK_CHANGES=1)"
  BT_RESULT="left on (NO_NETWORK_CHANGES=1)"
else
  WIFI_RESULT="$(networksetup -setairportpower "$WIFI_DEV" off 2>&1 && echo ok)"
  BT_RESULT="$(blueutil -p 0 2>&1 && echo ok)"
fi
log "Wi-Fi off ($WIFI_DEV): $WIFI_RESULT -> $(networksetup -getairportpower "$WIFI_DEV" 2>&1)"
log "Bluetooth off: $BT_RESULT -> $(blueutil -p 2>&1)"
AUTO_RESULT="$(display auto-brightness off)"
log "auto-brightness off: $AUTO_RESULT"
BRIGHT_RESULT="$(display set-brightness "$BRIGHTNESS")"
log "brightness $BRIGHTNESS: $BRIGHT_RESULT"

export BATTERY_START BATTERY_LINE WIFI_DEV WIFI_BEFORE WIFI_RESULT BT_BEFORE BT_RESULT \
  AUTO_RESULT BRIGHTNESS BRIGHT_BEFORE BRIGHT_RESULT
python3 - "$SUITE/test_conditions.json" <<'PY' || log "could not write test_conditions.json"
import json, os, sys
e = os.environ
json.dump({
    "prepared_by": "scripts/run_energy_suite_detached.sh",
    "battery_start_percent": e["BATTERY_START"],
    "battery_start_pmset": e["BATTERY_LINE"].strip(),
    "wifi": f"off via networksetup ({e['WIFI_DEV']}, was {e['WIFI_BEFORE']}): {e['WIFI_RESULT']}",
    "bluetooth": f"off via blueutil (was {e['BT_BEFORE']}): {e['BT_RESULT']}",
    "auto_brightness": f"off via CoreDisplay ({e['AUTO_RESULT']}); previous setting not readable",
    "display_brightness": f"fixed at {e['BRIGHTNESS']} (was {e['BRIGHT_BEFORE']}): {e['BRIGHT_RESULT']}",
    "true_tone": "unchanged and not recorded (no unprivileged control)",
}, open(sys.argv[1], "w"), indent=2)
PY

# ---- the suite (energy_suite.py stops itself below the 20% battery floor)
log "suite start"
CONDITIONS_ARG=()
[ -f "$SUITE/test_conditions.json" ] && CONDITIONS_ARG=(--conditions-json "$SUITE/test_conditions.json")
uv sync --quiet --extra dev
.venv/bin/python scripts/energy_suite.py run \
  --config "$CONFIG" --resume "$SUITE" --duration-s "$DURATION_S" \
  --no-sudo-prompt ${CONDITIONS_ARG[@]+"${CONDITIONS_ARG[@]}"} \
  </dev/null >>"$SUITE/suite.log" 2>&1 &
SUITE_PID=$!
log "suite pid $SUITE_PID"
wait "$SUITE_PID"
RC=$?
SUITE_PID=""
case $RC in
  0) STATUS="finished, all runs complete" ;;
  1) STATUS="finished with failed runs (see error.txt in their folders)" ;;
  4) STATUS="stopped at the battery floor; resume with: scripts/run_energy_suite_detached.sh $SUITE" ;;
  130) STATUS="interrupted" ;;
  *) STATUS="exited with code $RC" ;;
esac
log "suite exit $RC: $STATUS; battery now $(pmset -g batt | tail -1)"
restore

# ---- analysis (works offline)
for d in $PREV_SUITES "$SUITE"; do
  uv run python scripts/analyze_energy_suite.py "$d" >>"$SUITE/analysis.log" 2>&1
  for domain in package system; do
    uv run python scripts/analyze_energy_suite.py "$d" --domain "$domain" \
      --out "$d/analysis-$domain" >>"$SUITE/analysis.log" 2>&1 \
      || log "analysis $d --domain $domain failed (see analysis.log)"
  done
done
uv run python scripts/energy_report_section.py $PREV_SUITES "$SUITE" >>"$SUITE/analysis.log" 2>&1 \
  || log "report section failed (see analysis.log)"
log "analysis done"

[ "$OPEN_PR" = 1 ] || { log "OPEN_PR=0: not opening a pull request"; exit 0; }

# ---- draft pull request once the network is back (up to 15 min)
for _ in $(seq 60); do
  curl -sfI --max-time 5 https://api.github.com >/dev/null && break
  sleep 15
done
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git add docs/report
git commit -q -m "docs(report): energy results section 5.2 from $(basename "$SUITE")

Suite status: $STATUS

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01CYMdHtb9GeTxd24nEnks4R" || log "nothing new to commit"
git push -q -u origin "$BRANCH" || { log "git push failed"; exit 1; }
BODY="$SUITE/pr_body.md"
{
  echo "Draft for report section 5.2 (energy results on the M2 MacBook Pro). **Do not merge** until the numbers have been reviewed."
  echo
  echo "Suite \`$(basename "$SUITE")\`: $STATUS. Battery at start $BATTERY_START. Prepared in code: Wi-Fi and Bluetooth off, auto-brightness off, brightness $BRIGHTNESS; True Tone unchanged."
  echo
  sed -n '/^## Key numbers/,/^## /p' docs/report/5.2-energy-results.md | sed '$d'
  echo
  [ -f "$SUITE/pr_notes.md" ] && cat "$SUITE/pr_notes.md"
  echo
  echo "🤖 Generated with [Claude Code](https://claude.com/claude-code)"
  echo
  echo "https://claude.ai/code/session_01CYMdHtb9GeTxd24nEnks4R"
} >"$BODY"
if gh pr view "$BRANCH" >/dev/null 2>&1; then
  gh pr edit "$BRANCH" --body-file "$BODY" && log "updated PR: $(gh pr view "$BRANCH" --json url -q .url)"
else
  gh pr create --draft --base main --head "$BRANCH" \
    --title "Energy results for report section 5.2 (M2 suite, ablations)" \
    --body-file "$BODY" && log "opened draft PR: $(gh pr view "$BRANCH" --json url -q .url)"
fi
log "wrapper done"
