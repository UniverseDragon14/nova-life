#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import concurrent.futures, json, subprocess
names=["example.com","google.com"]
def check(name):
    try:
        p=subprocess.run(["timeout","2.8s","getent","ahostsv4",name],capture_output=True,text=True,timeout=2.8); ok=p.returncode==0 and bool(p.stdout.strip())
    except subprocess.TimeoutExpired: ok=False
    return name,ok
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex: rows=dict(ex.map(check,names))
vals=list(rows.values()); state="known" if all(vals) or not any(vals) else "unknown"; aggregate=True if all(vals) else False if not any(vals) else None
print(json.dumps({"state":state,"names":rows,"system_dns_ok":aggregate},sort_keys=True))
PY
