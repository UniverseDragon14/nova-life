#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import concurrent.futures, json, re, subprocess
names=["example.com","google.com"]; ipv4=re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
def check(name):
    try:
        p=subprocess.run(["timeout","2.8s","dig","+time=2","+tries=1","+short","@1.1.1.1",name,"A"],capture_output=True,text=True,timeout=2.8); answers=[x.strip() for x in p.stdout.splitlines() if x.strip()]; ok=p.returncode==0 and any(ipv4.fullmatch(x) for x in answers)
    except subprocess.TimeoutExpired: ok=False
    return name,ok
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex: rows=dict(ex.map(check,names))
vals=list(rows.values()); state="known" if all(vals) or not any(vals) else "unknown"; aggregate=True if all(vals) else False if not any(vals) else None
print(json.dumps({"state":state,"names":rows,"direct_dns_ok":aggregate},sort_keys=True))
PY
