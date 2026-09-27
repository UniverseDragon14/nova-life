#!/usr/bin/env bash
set -euo pipefail

NOVA_HOME="${NOVA_HOME:-/home/aslam/nova_home}"
TEXT="${1:-}"
REQUESTED="${2:-auto}"
INTENSITY="${3:-0.65}"
VOICE_URL="${NOVA_VOICE_URL:-http://127.0.0.1:8124/v2/speak}"
MODE_FILE="${NOVA_VOICE_MODE_FILE:-$NOVA_HOME/config/voice_mode}"
WORK=$(mktemp -d /tmp/nova-speak.XXXXXX)
trap 'rm -rf -- "$WORK"' EXIT
WAV="$WORK/speech.wav"

if [[ -z "$TEXT" ]]; then
  echo "usage: $0 <text> [auto|baby|human|robot_man|profile] [intensity]" >&2
  exit 2
fi

if [[ "$REQUESTED" == "auto" || -z "$REQUESTED" ]]; then
  if [[ -r "$MODE_FILE" ]]; then
    REQUESTED="$(tr -d '[:space:]' < "$MODE_FILE")"
  else
    REQUESTED="human"
  fi
fi

VOICE_MODE="custom"
case "$REQUESTED" in
  baby|little_baby|little-baby)
    VOICE_MODE="baby"
    PROFILE="dragon_playful"
    ;;
  human|natural)
    VOICE_MODE="human"
    PROFILE="whatsapp_natural"
    ;;
  robot|robot_man|robot-man)
    VOICE_MODE="robot_man"
    PROFILE="dragon_deep"
    ;;
  *)
    PROFILE="$REQUESTED"
    ;;
esac

apply_fx() {
  local input="$1"
  local output="$2"
  case "$VOICE_MODE" in
    baby)
      ffmpeg -y -loglevel error -i "$input" -af "rubberband=pitch=1.16" "$output"
      ;;
    robot_man)
      ffmpeg -y -loglevel error -i "$input" -af "rubberband=pitch=0.90,tremolo=f=22:d=0.10,aecho=0.8:0.72:24:0.10" "$output"
      ;;
    *)
      cp "$input" "$output"
      ;;
  esac
}

play_wav() {
  local file="$1"
  if [[ "${NOVA_NO_PLAY:-0}" == "1" ]]; then
    echo "NOVA_NO_PLAY=1 mode=$VOICE_MODE profile=$PROFILE" >&2
    return 0
  fi
  timeout 90 aplay -q -D pulse "$file"
}

# Tamil speech uses the existing Tamil neural path, now with mode-aware delivery.
if python3 -c 'import sys; sys.exit(0 if any("\u0b80" <= c <= "\u0bff" for c in sys.argv[1]) else 1)' "$TEXT"; then
  TAMIL_VOICE="ta-LK-SaranyaNeural"
  TAMIL_RATE="+0%"
  TAMIL_PITCH="+0Hz"
  case "$VOICE_MODE" in
    baby)
      TAMIL_VOICE="ta-LK-SaranyaNeural"
      TAMIL_RATE="+9%"
      TAMIL_PITCH="+32Hz"
      ;;
    human)
      TAMIL_VOICE="ta-LK-SaranyaNeural"
      TAMIL_RATE="+0%"
      TAMIL_PITCH="+0Hz"
      ;;
    robot_man)
      TAMIL_VOICE="ta-LK-KumarNeural"
      TAMIL_RATE="-8%"
      TAMIL_PITCH="-22Hz"
      ;;
  esac

  if timeout 20 "$HOME/.local/bin/edge-tts"        --voice "$TAMIL_VOICE" --rate "$TAMIL_RATE" --pitch "$TAMIL_PITCH"        --text "$TEXT" --write-media "$WORK/speech.mp3" &&
     timeout 10 ffmpeg -y -loglevel error -i "$WORK/speech.mp3" -ar 24000 -ac 1 "$WORK/tamil-base.wav"; then
    apply_fx "$WORK/tamil-base.wav" "$WAV"
    echo "TTS engine=edge_tamil mode=$VOICE_MODE profile=$PROFILE" >&2
  else
    ESPEAK_PITCH=50
    ESPEAK_SPEED=145
    case "$VOICE_MODE" in
      baby) ESPEAK_PITCH=76; ESPEAK_SPEED=168 ;;
      human) ESPEAK_PITCH=52; ESPEAK_SPEED=148 ;;
      robot_man) ESPEAK_PITCH=34; ESPEAK_SPEED=128 ;;
    esac
    timeout 10 espeak-ng -v ta -p "$ESPEAK_PITCH" -s "$ESPEAK_SPEED" -w "$WORK/tamil-base.wav" "$TEXT"
    apply_fx "$WORK/tamil-base.wav" "$WAV"
    echo "TTS engine=local_tamil_fallback mode=$VOICE_MODE profile=$PROFILE" >&2
  fi
  play_wav "$WAV"
  exit $?
fi

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
  exit 1
fi

PAYLOAD="$(jq -cn --arg text "$TEXT" --arg profile "$PROFILE" --argjson intensity "$INTENSITY"   '{text:$text,profile:$profile,intensity:$intensity,context:"chat",engine:"auto"}')"

if curl --connect-timeout 3 --max-time 25 -fsS "$VOICE_URL"   -H "Authorization: Bearer $TOKEN"   -H "Content-Type: application/json"   --data-binary "$PAYLOAD"   -o "$WORK/base.wav" && [[ "$(head -c 4 "$WORK/base.wav" 2>/dev/null)" == "RIFF" ]]; then
  apply_fx "$WORK/base.wav" "$WAV"
  echo "TTS engine=local_voice mode=$VOICE_MODE profile=$PROFILE" >&2
  play_wav "$WAV"
  exit $?
fi

echo "local voice unavailable; using local English fallback" >&2
ESPEAK_PITCH=50
ESPEAK_SPEED=150
case "$VOICE_MODE" in
  baby) ESPEAK_PITCH=76; ESPEAK_SPEED=172 ;;
  human) ESPEAK_PITCH=52; ESPEAK_SPEED=150 ;;
  robot_man) ESPEAK_PITCH=34; ESPEAK_SPEED=128 ;;
esac
timeout 15 espeak-ng -v en -p "$ESPEAK_PITCH" -s "$ESPEAK_SPEED" -w "$WORK/base.wav" "$TEXT"
apply_fx "$WORK/base.wav" "$WAV"
play_wav "$WAV"
