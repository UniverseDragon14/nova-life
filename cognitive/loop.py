#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, subprocess, time
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REGISTRY=ROOT/'action_registry.json'
WORLD_MODEL=ROOT/'world_model.json'
NOVA_HOME=Path(os.environ.get('NOVA_HOME','/home/aslam/nova_home'))
JOURNAL_DIR=NOVA_HOME/'journal'
RESTRICTED_IFACES={'tun_srsue','ogstun'}
PROBE_TIMEOUT=3.0
WHOLE_RUN_TIMEOUT=20.0

def now_iso(): return datetime.now().astimezone().isoformat(timespec='seconds')
def make_run_id(): return 'netdiag-'+datetime.now().astimezone().strftime('%Y%m%dT%H%M%S%z')+f'-{os.getpid()}'
def journal_path(): return JOURNAL_DIR/f'network_diagnosis-{datetime.now().astimezone():%Y-%m}.jsonl'
def append_event(event, enabled):
    if not enabled: return
    JOURNAL_DIR.mkdir(parents=True,exist_ok=True)
    with journal_path().open('a',encoding='utf-8') as f: f.write(json.dumps(event,sort_keys=True)+'\n')

def parse_main_default_routes(text):
    rows=[]
    for raw in text.splitlines():
        line=raw.strip()
        if not line.startswith('default'): continue
        toks=line.split()
        def after(k,default=None):
            try:return toks[toks.index(k)+1]
            except (ValueError,IndexError):return default
        iface=after('dev'); gateway=after('via'); metric_raw=after('metric','0')
        try:metric=int(metric_raw)
        except (TypeError,ValueError):metric=0
        rows.append({'iface':iface,'gateway':gateway,'metric':metric,'excluded':iface in RESTRICTED_IFACES})
    return rows

def read_main_default_routes():
    p=subprocess.run(['ip','-4','route','show','table','main','default'],capture_output=True,text=True,timeout=1.5)
    return parse_main_default_routes(p.stdout)

def choose_route(routes):
    eligible=[r for r in routes if r.get('iface') and r.get('gateway') and not r.get('excluded')]
    return sorted(eligible,key=lambda r:(int(r.get('metric',0)),str(r.get('iface'))))[0] if eligible else None

def load_registry():
    st=REGISTRY.stat()
    if st.st_uid!=0 or (st.st_mode & 0o022): raise RuntimeError('action registry must be root-owned and not group/world writable')
    data=json.loads(REGISTRY.read_text(encoding='utf-8'))
    for name,row in data.get('actions',{}).items():
        if name.startswith('probe_'):
            if row.get('zone')!='Green': raise RuntimeError(f'{name}: non-Green probe')
            if not row.get('verifier'): raise RuntimeError(f'{name}: verifier missing')
            if float(row.get('timeout_seconds',99))>PROBE_TIMEOUT: raise RuntimeError(f'{name}: timeout exceeds 3s')
    return data

def run_json_script(rel,args,deadline):
    remaining=deadline-time.monotonic()
    if remaining<=0:return {'state':'unknown','reason':'whole_run_deadline_exceeded'}
    try:p=subprocess.run([str(ROOT/rel),*args],capture_output=True,text=True,timeout=min(PROBE_TIMEOUT,remaining))
    except subprocess.TimeoutExpired:return {'state':'unknown','reason':'probe_timeout'}
    try:return json.loads(p.stdout.strip())
    except Exception:return {'state':'unknown','reason':'invalid_probe_output'}

def aggregate_gateway(primary,verifier):
    if primary.get('state')=='known' and verifier.get('state')=='known' and primary.get('reachable')==verifier.get('reachable'):
        return bool(primary.get('reachable')),'known'
    return None,'unknown'

def aggregate_tcp(row):
    vals=list((row.get('targets') or {}).values())
    if len(vals)!=2 or not all(isinstance(v,bool) for v in vals):return None,'unknown'
    return any(vals),'known'

def aggregate_http(row):
    targets=row.get('targets') or {}
    if len(targets)!=2:return None,'unknown'
    oks=[bool(v.get('ok_204')) for v in targets.values() if isinstance(v,dict)]
    if len(oks)!=2:return None,'unknown'
    return any(oks),'known'

def aggregate_dns(row,key):
    val=row.get(key)
    if row.get('state')=='known' and isinstance(val,bool):return val,'known'
    return None,'unknown'

def derive_diagnosis(gateway,tcp,http204,dns_system,dns_direct):
    if gateway is False:return 'local_gateway_problem_suspected'
    if gateway is not True:return 'insufficient_evidence'
    if tcp is False:return 'upstream_problem_suspected'
    if tcp is not True:return 'insufficient_evidence'
    if http204 is False:return 'captive_portal_or_filtered_suspected'
    if http204 is not True:return 'insufficient_evidence'
    if dns_system is False and dns_direct is True:return 'local_resolver_suspected'
    if dns_system is False and dns_direct is False:return 'dns_blocked_or_upstream_suspected'
    if dns_system is True and dns_direct is True:return 'network_appears_healthy'
    return 'insufficient_evidence'

def fact(value,state,evidence,ts,ttl='PT5M'):
    return {'value':value,'state':state,'evidence':evidence,'observed_at':ts,'ttl':ttl}

def fixture_inputs(data):
    return data.get('routes',[]),data.get('gateway',{}),data.get('tcp',{}),data.get('http',{}),data.get('dns_system',{}),data.get('dns_direct',{})

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--fixture'); ap.add_argument('--no-write',action='store_true'); args=ap.parse_args()
    started=time.monotonic(); deadline=started+WHOLE_RUN_TIMEOUT; run_id=make_run_id(); ts=now_iso(); write_enabled=not args.no_write and not args.fixture
    if args.fixture:
        data=json.loads(Path(args.fixture).read_text(encoding='utf-8'))
        routes,gateway_primary,tcp_row,http_row,dns_system_row,dns_direct_row=fixture_inputs(data)
        gateway_verify=data.get('gateway_verify',gateway_primary)
    else:
        registry=load_registry(); routes=read_main_default_routes(); route=choose_route(routes); iface=route.get('iface') if route else 'none'; problem_key=f'network_diagnosis+diagnose+{iface}'; seq=0
        def ev(stage,action,target,state,result,evidence_ref=None,verifier_ref=None,note=''):
            nonlocal seq; seq+=1
            append_event({'ts':now_iso(),'event_id':f'{run_id}-{seq}','run_id':run_id,'problem_key':problem_key,'stage':stage,'action_type':action,'target':target,'zone':(registry.get('actions',{}).get(action) or {}).get('zone','Red'),'result_state':state,'result':result,'evidence_ref':evidence_ref,'verifier_ref':verifier_ref,'note':note},write_enabled)
        ev('probe','probe_default_gateway','main-default-routes','known','observed',f'probe:routes:{run_id}',note=json.dumps(routes,sort_keys=True))
        if not route:
            gateway_primary={'state':'known','reachable':False,'reason':'no_eligible_default_gateway'}; gateway_verify=dict(gateway_primary); tcp_row={'state':'unknown'}; http_row={'state':'unknown'}; dns_system_row={'state':'unknown'}; dns_direct_row={'state':'unknown'}
        else:
            iface,gw=route['iface'],route['gateway']
            gateway_primary=run_json_script('probes/ping_gateway.sh',[iface,gw],deadline); ev('probe','probe_default_gateway',f'{iface}:{gw}',gateway_primary.get('state','unknown'),str(gateway_primary.get('reachable')),f'probe:gateway:{run_id}')
            gateway_verify=run_json_script('verifiers/verify_gateway.sh',[iface,gw],deadline); ev('verify','probe_default_gateway',f'{iface}:{gw}',gateway_verify.get('state','unknown'),str(gateway_verify.get('reachable')),f'probe:gateway:{run_id}',f'verify:gateway:{run_id}')
            tcp_row=run_json_script('probes/ping_known_ip.sh',[],deadline); ev('probe','probe_known_ip_tcp','1.1.1.1:443,8.8.8.8:443',tcp_row.get('state','unknown'),str(tcp_row.get('reachable')),f'probe:known-ip:{run_id}')
            http_row=run_json_script('verifiers/verify_http_204.sh',[],deadline); ev('verify','probe_known_ip_tcp','generate_204 endpoints',http_row.get('state','unknown'),str(http_row.get('http_204_ok')),f'probe:known-ip:{run_id}',f'verify:http204:{run_id}')
            dns_system_row=run_json_script('probes/resolve_dns.sh',[],deadline); ev('probe','probe_dns_system','example.com,google.com',dns_system_row.get('state','unknown'),str(dns_system_row.get('system_dns_ok')),f'probe:dns-system:{run_id}')
            dns_direct_row=run_json_script('verifiers/verify_dns.sh',[],deadline); ev('verify','probe_dns_system','@1.1.1.1 example.com,google.com',dns_direct_row.get('state','unknown'),str(dns_direct_row.get('direct_dns_ok')),f'probe:dns-system:{run_id}',f'verify:dns-direct:{run_id}')
    route=choose_route(routes); iface=route.get('iface') if route else 'none'; problem_key=f'network_diagnosis+diagnose+{iface}'
    gateway,gateway_state=aggregate_gateway(gateway_primary,gateway_verify); tcp,tcp_state=aggregate_tcp(tcp_row); http204,http_state=aggregate_http(http_row); dns_system,dns_system_state=aggregate_dns(dns_system_row,'system_dns_ok'); dns_direct,dns_direct_state=aggregate_dns(dns_direct_row,'direct_dns_ok'); diagnosis=derive_diagnosis(gateway,tcp,http204,dns_system,dns_direct)
    if time.monotonic()-started>WHOLE_RUN_TIMEOUT: diagnosis='insufficient_evidence'
    evidence=lambda name:[f'probe:{name}:{run_id}']
    world={'scenario':'network_diagnosis','run_id':run_id,'problem_key':problem_key,'facts':{
        'default_routes':fact(routes,'known',evidence('routes'),ts),'default_gateway_present':fact(bool(route),'known',evidence('routes'),ts),'gateway_interface':fact(iface if route else None,'known' if route else 'unknown',evidence('routes'),ts),'gateway_reachable':fact(gateway,gateway_state,[f'probe:gateway:{run_id}',f'verify:gateway:{run_id}'],ts),
        'tcp_1_1_1_1_443':fact((tcp_row.get('targets') or {}).get('1.1.1.1:443'),tcp_row.get('state','unknown'),evidence('known-ip'),ts),'tcp_8_8_8_8_443':fact((tcp_row.get('targets') or {}).get('8.8.8.8:443'),tcp_row.get('state','unknown'),evidence('known-ip'),ts),'known_ip_reachable':fact(tcp,tcp_state,evidence('known-ip'),ts),
        'http_204_gstatic':fact(((http_row.get('targets') or {}).get('connectivitycheck.gstatic.com') or {}).get('status'),http_row.get('state','unknown'),[f'verify:http204:{run_id}'],ts),'http_204_second_host':fact(((http_row.get('targets') or {}).get('clients3.google.com') or {}).get('status'),http_row.get('state','unknown'),[f'verify:http204:{run_id}'],ts),'http_204_ok':fact(http204,http_state,[f'verify:http204:{run_id}'],ts),
        'dns_system_example_com':fact((dns_system_row.get('names') or {}).get('example.com'),dns_system_row.get('state','unknown'),evidence('dns-system'),ts),'dns_system_google_com':fact((dns_system_row.get('names') or {}).get('google.com'),dns_system_row.get('state','unknown'),evidence('dns-system'),ts),'dns_system_ok':fact(dns_system,dns_system_state,evidence('dns-system'),ts),
        'dns_direct_example_com':fact((dns_direct_row.get('names') or {}).get('example.com'),dns_direct_row.get('state','unknown'),[f'verify:dns-direct:{run_id}'],ts),'dns_direct_google_com':fact((dns_direct_row.get('names') or {}).get('google.com'),dns_direct_row.get('state','unknown'),[f'verify:dns-direct:{run_id}'],ts),'dns_direct_ok':fact(dns_direct,dns_direct_state,[f'verify:dns-direct:{run_id}'],ts),'diagnosis':fact(diagnosis,'known' if diagnosis=='network_appears_healthy' else 'suspected' if diagnosis!='insufficient_evidence' else 'unknown',[f'derive:{run_id}'],ts)}}
    if write_enabled:
        WORLD_MODEL.write_text(json.dumps(world,indent=2,sort_keys=True)+'\n',encoding='utf-8'); append_event({'ts':now_iso(),'event_id':f'{run_id}-derive','run_id':run_id,'problem_key':problem_key,'stage':'derive','action_type':'derive_diagnosis','target':iface,'zone':'Green','result_state':world['facts']['diagnosis']['state'],'result':diagnosis,'evidence_ref':f'derive:{run_id}','verifier_ref':None,'note':'deterministic diagnosis'},True)
    out={'run_id':run_id,'problem_key':problem_key,'elapsed_seconds':round(time.monotonic()-started,3),'routes':routes,'gateway':{'value':gateway,'state':gateway_state},'known_ip':{'value':tcp,'state':tcp_state},'http_204':{'value':http204,'state':http_state},'dns_system':{'value':dns_system,'state':dns_system_state},'dns_direct':{'value':dns_direct,'state':dns_direct_state},'diagnosis':diagnosis}
    print(json.dumps(out,indent=2,sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
