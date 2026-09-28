#!/usr/bin/env bash
set -euo pipefail
IFACE="${1:-}"
GW="${2:-}"
python3 - "$IFACE" "$GW" <<'PY'
import json, re, subprocess, sys
iface, gw = sys.argv[1:3]
restricted={"tun_srsue","ogstun"}
def emit(**kw): print(json.dumps(kw, sort_keys=True))
if not iface or iface in restricted: emit(state="unknown",reachable=None,reason="invalid_or_restricted_interface"); raise SystemExit(0)
if not re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}",gw or ""): emit(state="unknown",reachable=None,reason="invalid_gateway"); raise SystemExit(0)
try:
    p=subprocess.run(["ip","neigh","show","to",gw,"dev",iface],capture_output=True,text=True,timeout=1); line=p.stdout.strip()
except Exception: line=""
tokens=set(line.split())
if line and tokens.intersection({"REACHABLE","STALE","DELAY","PROBE","PERMANENT","NOARP"}): emit(state="known",reachable=True,reason="kernel_neighbor_state")
elif "FAILED" in tokens: emit(state="known",reachable=False,reason="kernel_neighbor_failed")
else: emit(state="unknown",reachable=None,reason="no_independent_neighbor_evidence")
PY
