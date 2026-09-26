#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
J=/mnt/extra_sd/nova_home/journal
TS=$(date -Is)
if ./bin/dragon_verify.sh >/dev/null 2>&1; then CORE=ok; else CORE=ALERT; fi
V=$(./bin/nova_vitals.sh)
echo "$TS core=$CORE $V" >> "$J/$(date +%Y-%m).log"
tail -1 "$J/$(date +%Y-%m).log"
python3 "$HOME/nova-life/bin/nova_self.py" update
