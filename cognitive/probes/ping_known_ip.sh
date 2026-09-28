#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import concurrent.futures, json, socket
targets=[("1.1.1.1",443),("8.8.8.8",443)]
def check(target):
    host,port=target
    try:
        with socket.create_connection((host,port),timeout=2.5): return f"{host}:{port}",True
    except OSError: return f"{host}:{port}",False
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex: rows=dict(ex.map(check,targets))
print(json.dumps({"state":"known","targets":rows,"reachable":any(rows.values())},sort_keys=True))
PY
