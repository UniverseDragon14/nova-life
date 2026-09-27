#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
NOVA_HOME="${NOVA_HOME:-/home/aslam/nova_home}"
J="$NOVA_HOME/journal"
P=proposals/pending
LOG="$J/$(date +%Y-%m).log"

mkdir -p "$P" proposals/approved proposals/rejected
[ -f "$LOG" ] || exit 0

# Pattern: disk usage over 85% in last 20 heartbeats.
DISKS=$(tail -20 "$LOG" | grep -o 'disk=[0-9]*%' | tr -d 'disk=%' || true)
HIGH=$(printf '%s\n' "$DISKS" | awk 'NF && $1>85 {n++} END {print n+0}')
MAX=$(printf '%s\n' "$DISKS" | awk 'NF && $1>m {m=$1} END {print m+0}')

if [ "$HIGH" -ge 15 ]; then
  if [ "$MAX" -ge 95 ]; then
    SEVERITY=urgent
    SEVERITY_RANK=2
  else
    SEVERITY=warning
    SEVERITY_RANK=1
  fi

  GUARD=$(python3 - "$SEVERITY_RANK" <<'PY'
import json
import sys
import time
from datetime import datetime
from pathlib import Path

rank = int(sys.argv[1])
root = Path("proposals")

def read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def condition(data, path):
    if data.get("condition"):
        return str(data["condition"])
    stem = path.stem
    if stem.startswith("disk-") or stem == "agent-disk_high":
        return "disk_high"
    return ""

for path in (root / "pending").glob("*.json"):
    if condition(read(path), path) == "disk_high":
        print("already_pending")
        raise SystemExit
latest = None
for folder in ("approved", "rejected"):
    for path in (root / folder).glob("*.json"):
        data = read(path)
        if condition(data, path) != "disk_high":
            continue
        raw = data.get("decided_at") or data.get("owner_decision_at") or data.get("created")
        if not raw:
            continue
        try:
            ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
        row = (ts, int(data.get("severity_rank", 1) or 1))
        if latest is None or row[0] > latest[0]:
            latest = row

if latest and time.time() - latest[0] < 6 * 3600 and rank <= latest[1]:
    print("decision_cooldown")
else:
    print("allow")
PY
)

  case "$GUARD" in
    already_pending)
      echo "SKIP: disk_high already pending"
      exit 0
      ;;
    decision_cooldown)
      echo "SKIP: disk_high decision cooldown active (6h)"
      exit 0
      ;;
  esac

  ID="disk-$(date +%Y%m%dT%H%M%S)"
  cat > "$P/$ID.json" <<JSON
{
  "id": "$ID",
  "condition": "disk_high",
  "created": "$(date -Is)",
  "observation": "disk above 85% in $HIGH of last 20 heartbeats; max=$MAX%",
  "suggestion": "review large files under /home and /var/log",
  "risk": "read-only analysis, no deletion",
  "severity": "$SEVERITY",
  "severity_rank": $SEVERITY_RANK,
  "status": "pending"
}
JSON
  echo "PROPOSAL_CREATED: $ID"
else
  echo "NO_PROPOSAL: disk high in $HIGH/20"
fi
