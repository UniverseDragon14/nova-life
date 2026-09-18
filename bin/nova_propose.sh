#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
P=proposals
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
    mv "$P/pending/$2.json" "$P/approved/$2.json"
    echo "APPROVED: $2 (moved to approved/, no action taken automatically)"
    ;;
  reject)
    [ -n "${2:-}" ] || { echo "usage: $0 reject <id>"; exit 1; }
    mv "$P/pending/$2.json" "$P/rejected/$2.json"
    echo "REJECTED: $2"
    ;;
  *) echo "usage: $0 {list|approve <id>|reject <id>}" ;;
esac
