#!/usr/bin/env bash
# Start the nemo-bot APScheduler as a background service inside the sandbox.
# Invoked by the NemoClaw sandbox entrypoint on boot.

set -euo pipefail

SCHEDULE_CFG="${SCHEDULE_CFG:-/sandbox/schedule.yaml}"
SYSTEM_PROMPT_CFG="${MARKETING_SYSTEM_PROMPT_FILE:-/sandbox/marketing-system-prompt.md}"
LOG_DIR="${LOG_DIR:-/sandbox/.nemo-bot}"
LOG_FILE="${LOG_DIR}/scheduler.log"

mkdir -p "$LOG_DIR"

# If no schedule config in the sandbox yet, seed from the packaged default.
if [[ ! -f "$SCHEDULE_CFG" ]]; then
  cp /usr/local/lib/nemo-marketing-bot/schedule.yaml "$SCHEDULE_CFG"
fi

# If no editable marketing prompt exists yet, seed from the packaged default.
if [[ ! -f "$SYSTEM_PROMPT_CFG" ]]; then
  mkdir -p "$(dirname "$SYSTEM_PROMPT_CFG")"
  cp /usr/local/lib/nemo-marketing-bot/marketing-system-prompt.md "$SYSTEM_PROMPT_CFG"
fi

# Seed workspace files on first boot only.
WS_DIR="/sandbox/.openclaw/workspace"
if [[ -d /opt/nemoclaw-workspace-seed ]] && [[ -z "$(ls -A "$WS_DIR" 2>/dev/null || true)" ]]; then
  mkdir -p "$WS_DIR/memory"
  cp -r /opt/nemoclaw-workspace-seed/. "$WS_DIR/"
fi

# Defensive bootstrap: some sandbox builds miss /sandbox/.openclaw/openclaw.json,
# which prevents gateway token export and breaks `openclaw tui`.
if [[ ! -f /sandbox/.openclaw/openclaw.json ]] && command -v openclaw >/dev/null 2>&1; then
  if ! openclaw setup >> "$LOG_FILE" 2>&1; then
    echo "warning: openclaw setup bootstrap failed; tui may require manual setup" >> "$LOG_FILE"
  fi
fi

# Launch scheduler in the background. The sandbox init reaps it on shutdown.
nohup nemo-bot schedule --config "$SCHEDULE_CFG" \
  >> "$LOG_FILE" 2>&1 &

echo "nemo-bot scheduler started (pid=$!, log=$LOG_FILE)"
