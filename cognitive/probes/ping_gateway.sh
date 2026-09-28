#!/usr/bin/env bash
set -euo pipefail
IFACE="${1:-}"
GW="${2:-}"
python3 - "$IFACE" "$GW" <<'PY'
import json, os, re, socket, subprocess, sys
iface, gw = sys.argv[1:3]
restricted = {"tun_srsue", "ogstun"}
def emit(**kw): print(json.dumps(kw, sort_keys=True))
if not iface or iface in restricted or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,32}", iface):
    emit(state="unknown", reachable=None, method="none", reason="invalid_or_restricted_interface"); raise SystemExit(0)
if not re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", gw or ""):
    emit(state="unknown", reachable=None, method="none", reason="invalid_gateway"); raise SystemExit(0)
try:
    lo, hi = map(int, open("/proc/sys/net/ipv4/ping_group_range").read().split()[:2]); gid = os.getegid(); ping_allowed = lo <= gid <= hi
except Exception: ping_allowed = False
if ping_allowed:
    try:
        p = subprocess.run(["timeout","2.8s","ping","-I",iface,"-c","1","-W","2",gw], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2.8)
        emit(state="known", reachable=(p.returncode==0), method="icmp", reason="icmp_reply" if p.returncode==0 else "icmp_no_reply"); raise SystemExit(0)
    except subprocess.TimeoutExpired:
        emit(state="known", reachable=False, method="icmp", reason="icmp_timeout"); raise SystemExit(0)
neighbor=""
try:
    p=subprocess.run(["ip","neigh","show","to",gw,"dev",iface],capture_output=True,text=True,timeout=1); neighbor=p.stdout.strip()
except Exception: pass
good_neighbor=bool(neighbor) and not any(state in neighbor.split() for state in ("FAILED","INCOMPLETE"))
tcp_ok=False
for port in (53,80):
    try:
        with socket.create_connection((gw,port),timeout=0.8): tcp_ok=True; break
    except OSError: pass
if good_neighbor or tcp_ok: emit(state="known", reachable=True, method="neighbor+tcp", reason="neighbor_or_tcp_evidence")
else: emit(state="unknown", reachable=None, method="neighbor+tcp", reason="insufficient_gateway_evidence")
PY
