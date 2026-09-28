#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import concurrent.futures, http.client, json
targets=[("connectivitycheck.gstatic.com","/generate_204"),("clients3.google.com","/generate_204")]
def check(item):
    host,path=item; status=None; error=None
    try:
        conn=http.client.HTTPConnection(host,80,timeout=2.5); conn.request("GET",path,headers={"User-Agent":"NOVA-Network-Probe/0.1"}); resp=conn.getresponse(); status=int(resp.status); resp.read(256); conn.close()
    except Exception as exc: error=type(exc).__name__
    return host,{"status":status,"ok_204":status==204,"error":error}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex: rows=dict(ex.map(check,targets))
print(json.dumps({"state":"known","targets":rows,"http_204_ok":any(row["ok_204"] for row in rows.values())},sort_keys=True))
PY
