#!/usr/bin/env bash
CRON_ENTRY="*/5 * * * * /home/aslam/nova-life/bin/nova_heartbeat.sh >> /mnt/extra_sd/nova_home/journal/cron.log 2>&1"
(crontab -l 2>/dev/null || true) | grep -v "nova_heartbeat" | crontab -
echo "$CRON_ENTRY" | crontab -
echo "NOVA heartbeat scheduled: every 5 minutes"
crontab -l | grep nova
