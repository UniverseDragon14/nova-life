# NOVA Cognitive Core v0.1 — Network Diagnosis Phase 0 Plan

**Status:** Design only. No implementation yet.
**Scope:** `nova-life` lane only. No `core/` changes. No Yellow/Red execution.
**Authority:** `docs/COGNITIVE_CORE_v0.1.md` remains authoritative; the v0.2 thinking addendum is later-stage guidance and must not be used to skip v0.1.

## 1. Phase 0 purpose

Phase 0 is NOVA's first deterministic thinking exam: determine whether a connectivity problem is primarily local-gateway, upstream/known-IP, or DNS-related using Green read-only probes and traceable evidence.

Constraints:

- no LLM calls;
- Python/shell only;
- observe-only;
- all probes are Green;
- Yellow/Red results become proposals only, never actions;
- default fact TTL is `PT5M` unless the probe definition explicitly overrides it;
- Pi5 timestamps preserve the actual system offset, currently `+04:00`;
- command/script exit code is never enough to assert a world fact;
- disagreement between primary observation and independent verifier becomes `unknown` or `suspected`, never forced into `true`/`false`.
- scope is the main network namespace only; never enter or probe `ue1`, `tun_srsue`, or `ogstun`.
- every probe timeout is at most `3s`; the whole run is capped at `20s`; no sudo.
- every run shares one `run_id`; `problem_key = network_diagnosis + diagnose + <iface>`.

## 2. Planned file layout under `cognitive/`

```text
cognitive/
  world_model.json              # v0.1 network-diagnosis facts only
  goal_schema.json              # deterministic goal shape
  action_registry.json          # static action type -> zone + required verifier
  loop.py                       # deterministic orchestration only
  probes/
    ping_gateway.sh             # primary default-gateway observation
    ping_known_ip.sh            # TCP 443 primary; ICMP secondary diagnostic
    resolve_dns.sh              # two fixed known-good DNS names
  verifiers/
    verify_gateway.sh           # independent follow-up gateway evidence
    verify_http_204.sh          # independent HTTP generate_204 evidence
    verify_dns.sh               # independent follow-up resolution evidence
  playbooks/                    # reserved for owner-approved playbooks; empty in Phase 0
```

`world_model.json` is intentionally scoped only to the network-diagnosis scenario in v0.1. It must not silently become a global NOVA world model.

`action_registry.json` is planned as `root:root` mode `0644` from day one, matching the v0.1 owner decision. Phase 0 itself does not change permissions or create the file yet.

## 3. Probe list

### 3.1 Default gateway

Primary observation:

1. Read **all** default IPv4 routes from table `main`; record interface + metric for every route.
2. Exclude `tun_srsue` and `ogstun` from probe selection. Never enter network namespace `ue1`.
3. Select the lowest-metric eligible default route as the diagnostic target.
4. If no eligible default route/gateway exists, record `default_gateway_present=false` and do not invent a target.
5. If unprivileged ICMP is permitted by `/proc/sys/net/ipv4/ping_group_range`, run a bounded ICMP gateway probe (`<=3s`).
6. If unprivileged ping is unavailable, use kernel `ip neigh` state and a bounded TCP attempt to the gateway as secondary evidence; absence of an open gateway TCP port is not proof that the gateway is unreachable.

Primary facts:

- `default_gateway_present`
- `gateway_reachable`
- `gateway_interface`
- `default_routes` (every main-table default route: iface + metric + gateway; LTE interfaces may be recorded as excluded metadata but never probed)

Verifier:

- run a separate follow-up gateway probe from the verifier process after the primary probe;
- corroborate with the kernel neighbour entry for the same gateway/interface when available;
- never treat the primary script's exit code alone as proof;
- if primary and verifier disagree, set `gateway_reachable.state=unknown` and journal the conflict.

### 3.2 Known-IP upstream reachability

Targets are fixed for v0.1:

- `1.1.1.1:443`
- `8.8.8.8:443`

Primary observation:

- attempt a bounded TCP connection to **both** targets;
- either target succeeding means primary known-IP reachability evidence exists;
- ICMP ping to the same IPs is secondary diagnostic evidence only and never the sole reachability verdict.

Independent verifier:

- do **not** repeat the same TCP check as the verifier;
- query `http://connectivitycheck.gstatic.com/generate_204` and `http://clients3.google.com/generate_204`, both bounded to `<=3s` and without following redirects;
- expected success status is HTTP `204`; either endpoint returning `204` is enough for `http_204_ok=true`;
- if TCP known-IP reachability is true but neither HTTP endpoint returns `204` (including redirect/non-204), derive `captive_portal_or_filtered_suspected`;
- preserve each HTTP status separately so redirects/non-204 responses remain evidence rather than being collapsed into a generic failure.

### 3.3 DNS resolution

Two fixed known-good names are proposed for Phase 0:

- `example.com`
- `google.com`

Both names are always attempted. One name alone is not enough evidence to classify DNS health.

Primary observation — system resolver:

- resolve both names through the host's normal resolver path using `getent` (or `resolvectl` when explicitly available/selected);
- record each name separately; one-name-only success is insufficient for a healthy verdict.

Independent verifier — direct DNS:

- use bounded `dig @1.1.1.1` for both names;
- system resolver fails + direct DNS succeeds => `local_resolver_suspected`;
- system resolver fails + direct DNS fails => `dns_blocked_or_upstream_suspected`;
- system resolver succeeds + direct DNS fails is conflicting evidence => `insufficient_evidence`;
- mixed one-name-only results on either channel => `unknown` for that channel.

The derived diagnosis never calls DNS the cause merely because one resolver command returned non-zero.

## 4. World-model fact format

Every fact follows the v0.1 evidence/TTL discipline:

```json
{
  "fact_name": {
    "value": true,
    "state": "known",
    "evidence": [
      "probe:<probe_id>:<run_id>",
      "verify:<verifier_id>:<run_id>"
    ],
    "observed_at": "2026-09-28T10:02:11+04:00",
    "ttl": "PT5M"
  }
}
```

Allowed state semantics:

- `known` — primary and verifier evidence support the same directly observed fact;
- `suspected` — derived diagnosis/inference, never a direct observation;
- `unknown` — missing, expired, conflicting, or insufficient evidence.

Phase 0 fact set:

```text
default_gateway_present
gateway_reachable
gateway_interface
tcp_1_1_1_1_443
tcp_8_8_8_8_443
known_ip_reachable
http_204_gstatic
http_204_second_host
http_204_ok
dns_system_example_com
dns_system_google_com
dns_system_ok
dns_direct_example_com
dns_direct_google_com
dns_direct_ok
diagnosis
```

`diagnosis` is always derived. It may be values such as `local_gateway_problem_suspected`, `upstream_problem_suspected`, `captive_portal_or_filtered_suspected`, `local_resolver_suspected`, `dns_blocked_or_upstream_suspected`, `network_appears_healthy`, or `insufficient_evidence`, but its state remains `suspected` unless the value is merely a neutral summary such as `insufficient_evidence`.

## 5. Registry/verifier mapping

Phase 0 registry entries are planned as:

| Action/probe type | Zone | Required verifier | Notes |
|---|---|---|---|
| `probe_default_gateway` | Green | `verify_gateway` | read-only route + ICMP evidence |
| `probe_known_ip_tcp` | Green | `verify_http_204` | both TCP 443 targets attempted; verifier is different protocol/evidence |
| `probe_dns_system` | Green | `verify_dns_direct` | system resolver vs direct `dig @1.1.1.1` |
| unknown action type | Red | none until owner-approved registry entry exists | fail closed |

The planner emits only action type + target. It never assigns the zone or substitutes a verifier.

## 6. Deterministic diagnosis table

| Gateway | Known-IP TCP | HTTP 204 | System DNS | Direct DNS | Result |
|---|---|---|---|---|---|
| false | any | any | any | any | `local_gateway_problem_suspected` |
| true | false | any | any | any | `upstream_problem_suspected` |
| true | true | false | any | any | `captive_portal_or_filtered_suspected` |
| true | true | true | false | true | `local_resolver_suspected` |
| true | true | true | false | false | `dns_blocked_or_upstream_suspected` |
| true | true | true | true | true | `network_appears_healthy` |
| unknown/conflict | any | any | any | any | `insufficient_evidence` |
| true | unknown/conflict | any | any | any | `insufficient_evidence` |
| true | true | unknown/conflict | any | any | `insufficient_evidence` |
| true | true | true | true | false | `insufficient_evidence` |
| true | true | true | unknown/conflict | any | `insufficient_evidence` |
| true | true | true | any | unknown/conflict | `insufficient_evidence` |

No repair action is executed in v0.1. No real fault injection is allowed because NOVA/LTE/bot services are live on this Pi5.

## 7. Journal entries

Phase 0 uses the existing NOVA journal location under `$NOVA_HOME/journal/`; it does not implement the v0.2 daily signed reflection journal yet.

Planned event file:

```text
$NOVA_HOME/journal/network_diagnosis-YYYY-MM.jsonl
```

Each stage appends one structured JSON object:

```json
{
  "ts": "2026-09-28T10:02:11+04:00",
  "event_id": "netdiag-<run_id>-<sequence>",
  "run_id": "<stable run id shared by every probe/verify/derive event>",
  "problem_key": "network_diagnosis+diagnose+<iface>",
  "stage": "probe|verify|derive|gate|proposal",
  "action_type": "probe_known_ip_tcp",
  "target": "1.1.1.1:443",
  "zone": "Green",
  "result_state": "known",
  "result": "success|failure|unknown|suspected",
  "evidence_ref": "probe:<id>:<run_id>",
  "verifier_ref": "verify:<id>:<run_id>",
  "note": "bounded factual summary only"
}
```

Journal rules:

- append-only for Phase 0;
- actual `+04:00` offset preserved;
- every world-model evidence reference resolves to a journal event;
- every gate lookup records action type, registry zone, verifier id, and outcome;
- conflicting primary/verifier results are both retained, not overwritten;
- every default main-table route is journaled with interface + metric; restricted LTE interfaces are metadata only and are never probed;
- each probe has a `<=3s` timeout and the orchestrator enforces a `<=20s` whole-run deadline;
- no secret values, credentials, raw private data, or web instructions are written;
- v0.2 `journal/YYYY-MM-DD.md` reflection/signature work waits for its later build stage.

## 8. Phase 0 success criteria

Phase 0 design is ready for coding only after owner review confirms:

1. exact file layout;
2. fixed TCP/HTTP/DNS targets;
3. main-namespace/LTE exclusion rule;
4. per-probe `<=3s` and whole-run `<=20s` bounds;
5. world-model fact names/states/TTL;
6. action-registry verifier mapping;
7. journal JSONL fields with shared `run_id` and deterministic `problem_key`;
8. deterministic diagnosis table.

Phase 1 test gate: fixture mode must cover every diagnosis row, including conflict -> unknown, captive portal/filtered, and local-resolver cases; then one real healthy run on the Pi5. No real fault injection.
