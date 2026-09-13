#!/usr/bin/env bash
set -euo pipefail
TEMP=$(awk '{printf "%.1f", $1/1000}' /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo "NA")
UP=$(awk '{printf "%.1f", $1/3600}' /proc/uptime)
LOAD=$(awk '{print $1}' /proc/loadavg)
DISK=$(df -h / | awk 'NR==2{print $5}')
MEM=$(free -m | awk 'NR==2{printf "%d%%", $3*100/$2}')
echo "temp=${TEMP}C uptime=${UP}h load=${LOAD} disk=${DISK} mem=${MEM}"
