#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
J=/mnt/extra_sd/nova_home/journal
P=proposals/pending
LOG="$J/$(date +%Y-%m).log"

[ -f "$LOG" ] || exit 0

# Pattern: disk usage over 85% in last 20 heartbeats
HIGH=$(tail -20 "$LOG" | grep -o 'disk=[0-9]*%' | tr -d 'disk=%' | awk '$1>85' | wc -l)

if [ "$HIGH" -ge 15 ]; then
  ID="disk-$(date +%Y%m%d)"
  [ -f "$P/$ID.json" ] && exit 0
  [ -f "proposals/approved/$ID.json" ] && { echo "SKIP: already approved"; exit 0; }
  [ -f "proposals/rejected/$ID.json" ] && { echo "SKIP: already rejected"; exit 0; }
  cat > "$P/$ID.json" << JSON
{
  "id": "$ID",
  "created": "$(date -Is)",
  "observation": "disk above 85% in $HIGH of last 20 heartbeats",
  "suggestion": "review large files under /home and /var/log",
  "risk": "read-only analysis, no deletion",
  "status": "pending"
}
JSON
  echo "PROPOSAL_CREATED: $ID"
else
  echo "NO_PROPOSAL: disk high in $HIGH/20"
fi
