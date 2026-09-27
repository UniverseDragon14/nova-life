# NOVA Cognitive Core v0.1 (Design Only)

Status: DESIGN ONLY — no code in this document, nothing here is implemented.
Owner: Aslam
Scope: how NOVA thinks, decides, and asks for permission, across every capability
(voice, vision, repair brain, auto-code, public learning). This document does not
replace `core/nova.core.json`; it describes the reasoning loop that must obey it.

Ground truth this design is bound by:
- `core/nova.core.json` — guardian, approval, autocode, learning, research,
  perception, language, rollback and truth laws. These are constitution, not
  suggestions. Nothing in the cognitive core may reinterpret them.
- `core/nova.core.sha256` — integrity hash checked by `bin/dragon_verify.sh`.
  The cognitive core is a *consumer* of this check, never an editor of it.
- `~/NOVA_REPAIR_BRAIN_DESIGN_v0.1.md` — the repair brain is one capability
  that plugs into this loop; its four action levels map onto the permission
  gate described in section 5.
- Existing `bin/nova_observe.sh` / `bin/nova_propose.sh` proposal pattern —
  the pending/approved/rejected JSON files under `proposals/` are the existing,
  working instance of "write a proposal instead of acting," and the cognitive
  core generalizes that pattern rather than replacing it.

---

## 1. The loop

Every NOVA task, regardless of capability, runs the same cycle:

```
goal
  -> perceive
  -> world model (update)
  -> gap (goal vs world model)
  -> unknowns (what's missing to close the gap)
  -> info-seeking (bounded, read-only, allowlisted)
  -> options (playbook first, invention only if no playbook fits)
  -> consequences (what each option changes, and how it's verified)
  -> permission gate (zone lookup, never decided by the planner)
  -> act (only Green/Yellow auto; Red/Black never auto)
  -> observe (independent evidence, not "command exited 0")
  -> verify (against goal.success_check)
  -> reflect (did it work, why/why not)
  -> update memory (world model facts, and — only with owner approval — playbooks)
```

Notes on the shape of the loop:
- It is not linear-once. `observe -> verify` failing sends the loop back to
  `gap`/`unknowns` with the new evidence folded into the world model, not
  straight back to `act`.
- `info-seeking` and `act` are the only points where anything leaves the
  planner's head and touches the outside world (a probe, a command, a fetch).
  Both are gated — info-seeking by `research_law`, act by the permission gate.
- Every stage's output is journaled (see section 5), so the loop is auditable
  after the fact even if nothing is undone.

---

## 2. Policy is fixed; solutions are not hardcoded

Two things are true at once, and neither erases the other:

- **The policy is fixed.** The constitution, the action-zone registry, and the
  permission gate code do not change based on what the planner "thinks would
  help." A planner cannot loosen its own rules to get a job done.
- **Solutions are not hardcoded.** The planner is allowed to reason about a
  novel problem and propose a novel option. NOVA is not a fixed script.

The reconciliation is procedural, not a value judgment made per-incident:

1. When facing a gap, the planner first checks whether a **proven playbook**
   (a known-good sequence for this class of problem, e.g. repair brain's
   Level 3 allowlist) applies. If one applies, it is preferred over inventing
   anything new — proven beats novel, always, when both are on the table.
2. Only when no playbook applies does the planner invent candidate options.
   Invented options are still subject to the same consequence-prediction and
   permission-gate steps as playbook options — being "new" does not exempt an
   action from the gate; if anything it makes Red the default (see section 5).
3. If an invented option is executed (after Red approval) and it verifiably
   works, it becomes eligible to be *proposed* as a new playbook. It does not
   *become* a playbook automatically. A human owner reviews and approves the
   promotion, the same way `bin/nova_propose.sh approve <id>` promotes a
   proposal from `pending/` to `approved/` today. Until approved, "it worked
   once" stays a memory entry, not a rule.

This is the same shape as `autocode_law`: repair-only, no self-modification of
policy, and "unknown or risky failures become proposals instead of automatic
changes" — generalized from code repair to every domain NOVA reasons about.

---

## 3. World model fact format

The world model is the planner's only source of truth about the environment.
It is a collection of facts, not a raw log. Each fact:

```json
{
  "value": "<the claim, typed to the domain, e.g. \"gateway_reachable\": true>",
  "state": "known | suspected | unknown",
  "evidence": "<probe id / observation id / source reference that produced this>",
  "observed_at": "<ISO-8601 timestamp>",
  "ttl": "<duration after which this fact is no longer trusted>"
}
```

Rules:
- **`state` is honest about confidence.** `known` means directly observed with
  fresh evidence. `suspected` means inferred, not observed (e.g. "probably DNS,
  because gateway ping succeeded but resolution failed" before a DNS probe has
  actually run). `unknown` means no usable evidence exists yet.
- **A stale fact becomes `unknown`, not a stale `known`.** When `now - observed_at
  > ttl`, the fact's state is treated as `unknown` regardless of what its last
  known `value` was, until re-observed. The planner must not act on expired
  facts as if they were current truth.
- **`evidence` is mandatory and traceable.** It points at the probe/observation
  that produced the fact (e.g. a journal line, a proposal id, a probe run id),
  so any fact in the world model can be traced back to what actually happened,
  matching the "evidence references" requirement already used by Repair Brain
  Detect/Diagnose.
- **External content is data, never instructions.** Anything read from the web,
  documentation, camera frames, or any other external source is ingested only
  as the *value* of a fact (with `state` usually `suspected` until corroborated,
  and `evidence` pointing at the source). It is never treated as a command, a
  policy change, or a new goal. This is `research_law` and `perception_law`
  applied structurally: a fetched page can tell the world model "this forum
  post claims X," never "do X."

---

## 4. Goal format

```json
{
  "intent": "<what outcome is wanted, in domain terms>",
  "deadline": "<when this stops being worth pursuing, or null>",
  "constraints": ["<hard limits the plan must respect, e.g. laws, budgets, zones>"],
  "success_check": "<how completion is verified, independent of the actions taken>"
}
```

Rule: **`success_check` is required and must be defined before any `act` step,
not derived afterward to justify what happened.** A goal submitted without a
verifiable `success_check` is rejected at intake — the loop never starts. This
prevents the failure mode where an agent acts first and then narrates
whatever happened as success. It also gives `verify` (loop step 12) a fixed
target that isn't moved after the fact.

"Verifiable" here means the same thing it means in section 7: independent
evidence, not the exit status of the action itself.

---

## 5. Permission gate

The gate is the single choke point between "the planner decided to do X" and
"X actually happens." Its properties:

- **A static action registry maps action type -> zone.** The registry is data,
  not planner output. It is versioned and reviewed like the constitution, not
  generated per-task.
- **Zones:**
  - **Green** — read, diagnose, simulate. No side effects on the world.
  - **Yellow** — limited and reversible. Bounded blast radius, has a rollback,
    rate-limited (this is exactly Repair Brain's Level 3 allowlist: one
    action per incident, cooldown, precondition snapshot, automatic rollback).
  - **Red** — owner approval required before execution (Repair Brain's Level 4,
    and everything `approval_law` names: movement, deployment, credential/auth
    changes, uploads, private-person lookup, arbitrary external network
    actions, system-wide changes, risky commands).
  - **Black** — denied outright. Constitution, gate code, the registry itself,
    and keys are Black to the agent, full stop — not "Red, escalate," but not
    reachable at all.
- **The planner never assigns zones.** The planner emits an action *type* and
  *target*; the gate looks up the zone from the registry. The planner cannot
  argue, self-classify, or override this lookup.
- **Unknown action = Red, fail closed.** If an action type isn't in the
  registry, it is treated as Red (needs approval), never as Green-by-default.
  Absence of a rule is not permission.
- **Every decision is journaled.** Every gate lookup — the action, the zone it
  resolved to, and the outcome (executed / queued for approval / denied) — is
  appended to the journal NOVA already writes via `nova_observe.sh` /
  `nova_heartbeat.sh`, and Red-zone actions additionally produce a proposal
  file in `proposals/pending/`, matching the existing
  `nova_propose.sh {list,approve,reject}` workflow. Approval only ever moves a
  proposal to `approved/`; it never causes automatic execution by itself.

---

## 6. Enforcement outside the agent

The gate only means something if the agent cannot rewrite it, so enforcement
lives partly outside the agent's own writable surface:

**Current reality:** this separation is a target, not a fact about the current
Pi5 deployment. Today the NOVA agent loop, the WhatsApp bot, and Desktop
Commander agents all run as `aslam`, and that account can sudo. Therefore the
current process boundary is not sufficient to protect Yellow actions from the
agent itself. Before any Yellow action is wired in, v0.2 requires a dedicated
unprivileged `nova` user with no sudo path; the protected gate, registry, and
owner-signing material must remain outside that user's writable authority.

- **Target state: the agent runs as an unprivileged user.** It has no path to sudo, no
  ability to edit files it doesn't own, and no ambient authority beyond what
  its own user account grants — consistent with `autocode_law`'s "no sudo, no
  hardware motion, no credential edits."
- **The constitution, gate code, and registry are root-owned and read-only to
  the agent.** The agent can read `core/nova.core.json` and the action
  registry to reason about them, but the filesystem permissions themselves —
  not the agent's good behavior — are what prevent it from writing to them.
- **The seal is signed with the owner's SSH key** (`ssh-keygen -Y sign` /
  `ssh-keygen -Y verify`), and the agent cannot read that key. This is a step
  up from the current `core/nova.core.sha256` check: a hash proves the file
  matches what was hashed, but anyone with write access could rehash after
  editing. A signature proves the owner specifically attested to this exact
  content, and only the owner's private key can produce a new valid signature.
- **Note on the current state:** today, `bin/dragon_verify.sh` does a
  `sha256sum -c core/nova.core.sha256` check. That detects *accidental*
  drift (a bad edit, a corrupted file) but does **not** detect deliberate
  tampering, because whoever can edit `nova.core.json` can also regenerate
  `nova.core.sha256` to match. Moving to owner-signed verification (this
  section) is what closes that gap; it is called out here as a known,
  currently-unaddressed limitation of the sha256-beside-file approach, not
  something this document silently assumes is already fixed.

---

## 7. Verifier

`verify` (loop step 12) must never accept "the command returned 0" as proof of
success. Exit codes prove the process didn't crash; they don't prove the
world changed the way the goal intended. The verifier requires **independent
evidence** — something observed separately from the action's own report of
itself:

- a delivery receipt (e.g. a WhatsApp message actually arrived, not just that
  the send call didn't throw)
- a tunnel/reachability ping succeeding *after* the action, from outside the
  process that took the action
- a service's `ActiveState=active` and stable `NRestarts` observed in a
  follow-up window, not just "systemctl restart exited 0" (this mirrors
  Repair Brain's Level 3 health-check design directly)
- a file's hash/content actually matching the expected post-state, not just
  "the write call didn't error"

If no independent evidence channel exists for a given action, that is itself
a fact the planner must record (`state: unknown` on the outcome) rather than
defaulting to "assume success."

---

## 8. Self-expanding capabilities

NOVA may sometimes need a capability it doesn't have yet (a new probe, a new
integration). Growing that capability is itself gated, on top of the normal
action gate:

- **Sandbox only.** New capabilities are built and tested under a separate,
  unprivileged sandbox user: no network access, no secrets, and enforced time
  and memory limits. This is a stricter environment than the agent's normal
  runtime user, not the same one.
- **First real use is always Red.** Even after a new capability passes every
  sandbox test, the first time it is invoked against anything real requires
  owner approval — sandbox success is evidence, not permission.
- **Never auto-promoted.** A capability does not gain a permanent zone
  assignment, and does not get added to the action registry, by virtue of
  passing tests or by repeated Red approvals. Promotion into the registry (and
  into Green/Yellow territory) is a distinct owner action, matching section 2's
  rule that a working new solution becomes a playbook only with explicit
  approval — same principle, applied to code the agent itself produces.

---

## 9. Repair Brain as a sub-capability

Repair Brain (per `NOVA_REPAIR_BRAIN_DESIGN_v0.1.md`) is not a separate system;
it is what the cognitive core's action-zone mapping looks like for the
"something is broken" domain:

- **Detect/Diagnose = Green.** Read-only checks (service state, restart loops,
  journal patterns, disk/inode pressure, temperature, memory pressure, device
  presence, repo dirty state, filesystem read-only state, stale proposals) and
  read-only evidence gathering both run automatically, with no side effects.
- **Safe allowlist = Yellow.** The Level 3 list (bounded service restart,
  disposable cache cleanup with a size cap, log rotation via the service's own
  mechanism, ephemeral runtime dir recreation, transient probe retry) is
  exactly what "limited and reversible" means in section 5: one action per
  incident, cooldown, precondition snapshot, post-action health check,
  automatic rollback where one exists, and escalate-to-proposal on health
  check failure.
- **Signed approval = Red.** Level 4 (source edits, config/unit/cron changes,
  git commit/push, deletion or moving non-cache data, filesystem repair,
  partition/mount changes, firmware flashing, credentials/auth/keys,
  firewall/network-wide changes, destructive database repair, policy/
  constitution changes, widening repair permissions) always goes through the
  same signed-approval path as any other Red action in section 5-6 — Repair
  Brain does not get its own separate approval mechanism, it reuses this one.

---

## 10. v0.1 build scope (for later — not now)

This section describes what a first implementation would contain. **Nothing
in this section is being built now.** It is scoped tightly on purpose:

- **No LLM.** The v0.1 loop is deterministic Python/bash, not a model call.
- **Observe-only.** No Yellow or Red action ever executes in v0.1 — it only
  ever produces proposals.
- **One scenario: network diagnosis** — gateway vs DNS vs internet, i.e.
  "is the problem the local gateway, name resolution, or upstream
  connectivity."
- **Green probes only:**
  - ping the default gateway
  - test upstream IP reachability primarily with TCP connects to
    `1.1.1.1:443` and `8.8.8.8:443`; both are tried, and either succeeding
    means known-IP reachability is available
  - ICMP ping to those known IPs is a secondary diagnostic only, never the
    sole reachability verdict
  - DNS checks resolve two known-good names; one resolver result is not enough
    evidence to classify DNS health
- **Yellow/Red actions are written as proposals, never executed** — following
  the existing `proposals/pending/*.json` pattern verbatim, not a new format.
- **Code goes in `cognitive/`** (new top-level directory, sibling to `bin/`
  and `core/`), so it's clearly separated from the existing operational
  scripts in `bin/` and from the constitution in `core/`.

Proposed file list (not yet created):

```
cognitive/
  world_model.json          # current facts, per section 3
  goal_schema.json           # goal shape, per section 4
  action_registry.json       # static action-type -> zone map, per section 5
  probes/
    ping_gateway.sh          # Green
    ping_known_ip.sh         # Green: TCP 443 primary, ICMP secondary
    resolve_dns.sh           # Green: resolves two known-good names
  loop.py                    # the deterministic loop for the one scenario
```

Example `cognitive/world_model.json` after a run:

```json
{
  "facts": {
    "gateway_reachable": {
      "value": true,
      "state": "known",
      "evidence": "probe:ping_gateway:2026-09-28T10:02:11+04:00",
      "observed_at": "2026-09-28T10:02:11+04:00",
      "ttl": "PT5M"
    },
    "known_ip_reachable": {
      "value": false,
      "state": "known",
      "evidence": "probe:ping_known_ip:2026-09-28T10:02:13+04:00",
      "observed_at": "2026-09-28T10:02:13+04:00",
      "ttl": "PT5M"
    },
    "dns_resolves": {
      "value": null,
      "state": "unknown",
      "evidence": "probe:resolve_dns:2026-09-28T10:02:14+04:00",
      "observed_at": "2026-09-28T10:02:14+04:00",
      "ttl": "PT5M"
    },
    "diagnosis": {
      "value": "suspected_isp_or_upstream_outage",
      "state": "suspected",
      "evidence": "derived:gateway_reachable=true,known_ip_reachable=false",
      "observed_at": "2026-09-28T10:02:14+04:00",
      "ttl": "PT5M"
    }
  }
}
```

In this example, gateway is up but a known external IP isn't reachable, so
the loop suspects an upstream/ISP issue rather than local DNS — and, per
section 4, would only report this as `suspected`, would write any repair
action as a Red proposal, and would take no Yellow/Red action itself.

---

## 11. Open questions for the owner

1. **TTL values.** Section 3 requires every fact to have a `ttl`, but this
   doc doesn't set one — should TTL be fixed per fact-type (e.g. network
   probes expire in minutes, "is this device physically present" expires in
   hours), or configurable globally?
2. **Playbook storage.** Section 2 says approved solutions become playbooks —
   where do these live (new `cognitive/playbooks/` dir? appended to the
   action registry? a separate approved-playbooks file mirroring
   `proposals/approved/`)?
3. **Signed seal rollout.** Section 6 proposes moving from sha256-beside-file
   to owner-signed verification via `ssh-keygen -Y`. Is this in scope for the
   v0.1 build (section 10), or a later phase once the observe-only loop is
   proven out?
4. **Registry ownership/location.** Should `cognitive/action_registry.json`
   be root-owned like `core/` from day one (per section 6), even during the
   observe-only v0.1 where nothing Yellow/Red executes yet, or is root
   ownership deferred until Yellow actions are actually wired up?
5. **Cross-capability world model.** Is there one shared `world_model.json`
   across all of NOVA's capabilities (voice, vision, repair, network
   diagnosis), or one per scenario/domain? Section 10 assumes one file scoped
   to the network-diagnosis scenario only — confirm that's intentional for
   v0.1 and not meant to generalize yet.
6. **What counts as "independent evidence" per action type.** Section 7 gives
   examples but not a canonical list — should the action registry itself
   carry a `verifier` field per action type, so "how do we know this worked"
   is defined at registry-authoring time rather than improvised per incident?

---

## 12. Decisions v0.1

The owner decisions for the six open questions in section 11 are:

1. **TTL policy:** TTL is defined per fact type in each probe definition.
   The default is `PT5M` unless a probe explicitly defines a different value.
2. **Playbook storage:** approved playbooks live in `cognitive/playbooks/`,
   one owner-approved file per playbook. Playbooks are **not** stored in the
   action registry.
3. **Signed seal rollout:** the SSH-signed seal is not part of the observe-only
   v0.1 implementation, but it is **required before any Yellow action is wired**.
   This is a v0.2 gate, not an optional hardening task.
4. **Registry ownership:** `cognitive/action_registry.json` is
   `root:root` mode `0644` from day one. That catches accidental writes in
   the current deployment; the real privilege barrier is the dedicated
   unprivileged `nova` user required by section 6 before Yellow actions.
5. **World-model scope:** v0.1 uses one world model per scenario. The first
   network-diagnosis world model does not silently become a global shared model.
6. **Verifier requirement:** every action-registry entry has a **required
   `verifier` field**. Verification policy is defined when the registry entry
   is authored, not invented by the planner after execution.
