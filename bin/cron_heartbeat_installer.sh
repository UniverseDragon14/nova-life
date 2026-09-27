#!/usr/bin/env bash
set -euo pipefail
NOVA_HOME="${NOVA_HOME:-/home/aslam/nova_home}"
CRON_ENTRY="*/5 * * * * NOVA_HOME=$NOVA_HOME /home/aslam/nova-life/bin/nova_heartbeat.sh >> $NOVA_HOME/journal/cron.log 2>&1"
CRON_BACKUP="$NOVA_HOME/cron.bak.$(date +%s)"
(crontab -l 2>/dev/null || true) > "$CRON_BACKUP"
{ { crontab -l 2>/dev/null || true; } | { grep -v nova_heartbeat || true; }; echo "$CRON_ENTRY"; } | crontab -
echo "NOVA heartbeat scheduled: every 5 minutes"
crontab -l | grep nova
