#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if sha256sum -c core/nova.core.sha256 --status; then
  echo "DRAGON_OK core intact"
  exit 0
else
  echo "DRAGON_ALERT core changed without approval"
  exit 1
fi
