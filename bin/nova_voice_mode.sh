#!/usr/bin/env bash
set -euo pipefail
MODE_FILE="${NOVA_VOICE_MODE_FILE:-/mnt/extra_sd/nova_home/config/voice_mode}"
MODE="${1:-status}"

case "$MODE" in
  status)
    if [[ -r "$MODE_FILE" ]]; then
      echo "NOVA_VOICE_MODE=$(tr -d '[:space:]' < "$MODE_FILE")"
    else
      echo "NOVA_VOICE_MODE=human"
    fi
    exit 0
    ;;
  baby|human|robot_man)
    ;;
  robot)
    MODE="robot_man"
    ;;
  *)
    echo "usage: $0 [status|baby|human|robot_man]" >&2
    exit 2
    ;;
esac

mkdir -p "$(dirname "$MODE_FILE")"
tmp="$MODE_FILE.tmp.$$"
printf '%s\n' "$MODE" > "$tmp"
chmod 600 "$tmp"
mv "$tmp" "$MODE_FILE"
echo "NOVA_VOICE_MODE=$MODE"
