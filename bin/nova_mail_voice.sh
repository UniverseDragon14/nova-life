#!/usr/bin/env bash
set -euo pipefail

TEXT="${1:-}"
SUBJECT="${2:-NOVA voice message}"
PROFILE="${3:-nova_warm}"
INTENSITY="${4:-0.70}"
NOVA_HOME="${NOVA_HOME:-/home/aslam/nova_home}"
OUTBOX="$NOVA_HOME/outbox"
VOICE_URL="${NOVA_VOICE_URL:-http://127.0.0.1:8124/v2/speak}"

if [[ -z "$TEXT" ]]; then
  echo "usage: $0 <text> [subject] [profile] [intensity]" >&2
  exit 2
fi

mkdir -p "$OUTBOX"
STAMP="$(date +%Y%m%dT%H%M%S)"
WAV="$OUTBOX/nova-voice-$STAMP.wav"
META="$OUTBOX/nova-voice-$STAMP.json"

TOKEN=""
for f in "$HOME/dragon-local-voice-v1/.env" "$HOME/dragon-local-voice-v2/runtime.env"; do
  [[ -r "$f" ]] || continue
  line="$(grep -m1 '^DRAGON_VOICE_TOKEN=' "$f" 2>/dev/null || true)"
  [[ -n "$line" ]] || continue
  TOKEN="${line#*=}"
  TOKEN="${TOKEN%\"}"; TOKEN="${TOKEN#\"}"
done

if [[ -z "$TOKEN" ]]; then
  echo "voice auth token unavailable" >&2
  exit 3
fi

PAYLOAD="$(jq -cn --arg text "$TEXT" --arg profile "$PROFILE" --argjson intensity "$INTENSITY" \
  '{text:$text,profile:$profile,intensity:$intensity,context:"chat",engine:"auto"}')"

curl -fsS "$VOICE_URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary "$PAYLOAD" \
  -o "$WAV"

[[ "$(head -c 4 "$WAV")" == "RIFF" ]] || { echo "invalid WAV response" >&2; exit 4; }

jq -n   --arg to "univercialdragon@gmail.com"   --arg subject "$SUBJECT"   --arg wav "$WAV"   --arg created "$(date -Is)"   '{to:$to,subject:$subject,wav:$wav,created:$created,status:"queued",transport:"gmail-not-configured"}'   > "$META"

echo "queued voice message: $WAV"
echo "gmail transport not configured on Pi; nothing sent"
