#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
P=proposals

stamp_decision() {
  local file="$1" decision="$2"
  local via="${NOVA_APPROVAL_VIA:-cli}"
  local msg_id="${NOVA_APPROVAL_MSGID:-}"

  case "$via" in
    whatsapp|cli) ;;
    *) echo "invalid NOVA_APPROVAL_VIA: $via" >&2; exit 2 ;;
  esac

  if [ "$via" = "whatsapp" ] && [ -z "$msg_id" ]; then
    echo "NOVA_APPROVAL_MSGID required for whatsapp approval" >&2
    exit 2
  fi

  python3 - "$file" "$decision" "$via" "$msg_id" "${USER:-unknown}" <<'PYJSON'
import json
import sys
from datetime import datetime, timezone

path, decision, via, msg_id, actor = sys.argv[1:6]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

data["status"] = decision
data["decided_by"] = "owner_jid_verified" if via == "whatsapp" else actor
data["via"] = via
if via == "whatsapp":
    data["msg_id"] = msg_id
else:
    data.pop("msg_id", None)
data["decided_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")
PYJSON
}

case "${1:-list}" in
  list)
    echo "=== PENDING ==="
    ls -1 "$P/pending"/*.json 2>/dev/null | while read -r f; do
      echo "--- $(basename "$f" .json)"
      grep -E '"(observation|suggestion|risk)"' "$f"
    done || echo "(none)"
    ;;
  approve)
    [ -n "${2:-}" ] || { echo "usage: $0 approve <id>"; exit 1; }
    stamp_decision "$P/pending/$2.json" approved
    mkdir -p "$P/approved"
    mv "$P/pending/$2.json" "$P/approved/$2.json"
    echo "APPROVED: $2 (moved to approved/, no action taken automatically)"
    ;;
  reject)
    [ -n "${2:-}" ] || { echo "usage: $0 reject <id>"; exit 1; }
    stamp_decision "$P/pending/$2.json" rejected
    mkdir -p "$P/rejected"
    mv "$P/pending/$2.json" "$P/rejected/$2.json"
    echo "REJECTED: $2"
    ;;
  *) echo "usage: $0 {list|approve <id>|reject <id>}" ;;
esac
