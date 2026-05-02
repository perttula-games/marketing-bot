#!/usr/bin/env bash
set -euo pipefail

SANDBOX="${SANDBOX_NAME:-marketingbox}"
TARGET="${1:-show}"

usage() {
  cat <<'USAGE'
Usage:
  scripts/openclaw-model.sh show
  scripts/openclaw-model.sh pro
  scripts/openclaw-model.sh flash
  scripts/openclaw-model.sh custom <provider/model-id>

Environment:
  SANDBOX_NAME   Sandbox name (default: marketingbox)
USAGE
}

if [[ "$TARGET" == "-h" || "$TARGET" == "--help" ]]; then
  usage
  exit 0
fi

case "$TARGET" in
  show)
    openshell sandbox exec -n "$SANDBOX" -- sh -lc \
      'openclaw config get agents.defaults.model.primary'
    ;;
  pro)
    MODEL="deepseek/deepseek-v4-pro"
    ;;
  flash)
    MODEL="deepseek/deepseek-v4-flash"
    ;;
  custom)
    if [[ $# -lt 2 ]]; then
      echo "error: custom requires model id, e.g. deepseek/deepseek-v4-pro" >&2
      usage
      exit 2
    fi
    MODEL="$2"
    ;;
  *)
    echo "error: unknown target '$TARGET'" >&2
    usage
    exit 2
    ;;
esac

if [[ "$TARGET" != "show" ]]; then
  openshell sandbox exec -n "$SANDBOX" -- sh -lc \
    "openclaw config set agents.defaults.model.primary $MODEL"
  openshell sandbox exec -n "$SANDBOX" -- sh -lc \
    'openclaw config get agents.defaults.model.primary'
fi
