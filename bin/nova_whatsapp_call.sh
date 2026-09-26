#!/usr/bin/env bash
set -euo pipefail

TEXT="${1:-Hi machi, NOVA here. Un kitta konjam pesa vandhen. Free-aa irundha voice note la sollu.}"
ROOT="/mnt/extra_sd/nova_home/whatsapp_outbox"
PENDING="$ROOT/pending"
STAMP="$(date +%Y%m%dT%H%M%S)"
ID="call-${STAMP}-$$"
TMP="$PENDING/.${ID}.tmp"
OUT="$PENDING/${ID}.json"

mkdir -p "$PENDING" "$ROOT/sent" "$ROOT/failed"

jq -n   --arg id "$ID"   --arg text "$TEXT"   --arg created "$(date -Is)"   '{
    id:$id,
    type:"call_start",
    text:$text,
    created:$created,
    status:"pending",
    channel:"whatsapp_voice"
  }' > "$TMP"

mv "$TMP" "$OUT"

python3 "$HOME/nova-life/bin/nova_self.py" remember   "NOVA Life queued WhatsApp voice-call request for owner" 7 >/dev/null 2>&1 || true

echo "queued: $ID"
