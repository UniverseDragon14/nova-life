# NOVA Cognitive Core v0.2 — Thinking Addendum

**Status:** Design only. Not implemented.  
**Scope:** `nova-life` lane only. Python/shell implementation when coding begins.  
**Relationship to v0.1:** This document is an addendum to `docs/COGNITIVE_CORE_v0.1.md`. Every v0.1 decision remains in force unless an owner-approved later amendment explicitly changes it. This document does not replace v0.1.  
**Core boundary:** This addendum does not modify `core/`, the gate, the action registry, keys, or approval policy.

## Origin

Concept by Aslam (Universal Dragon). In his words:

> ஒரே situation-ல 20 பேர் இருந்தாலும் 20 பேர் மூளை ஒரே மாதிரி வேலை செய்யாது…  
> NOVA dumb-ஆ இருக்கக்கூடாது, யோசிக்க கத்துக்கணும். Fixed answer இல்ல, fixed thinking framework.

This addendum formalizes that idea into evidence-bound thinking rules without changing the v0.1 action-authority boundary.

## 0. Current implementation state

At the time this addendum was written:

- `docs/COGNITIVE_CORE_v0.1.md` is committed.
- The v0.1 network-diagnosis scenario has **not started in code**: there is no `cognitive/` implementation tree and no network-diagnosis/probe implementation under `bin/`.
- Therefore v0.2 thinking work must not jump ahead of the v0.1 network scenario.
- Pi5 system timestamps are still **+04:00**. Journal and trace records must preserve the actual offset emitted by the Pi5 rather than pretending they are Sri Lanka local time.

## 1. Core-law mapping note

The genesis core contained these seven foundational law names, all of which still exist in the current `core/nova.core.json`:

`guardian_law`, `robot_motion_law`, `approval_law`, `learning_law`, `language_law`, `rollback_law`, `truth_law`.

The current core also contains three later laws:

`autocode_law`, `research_law`, `perception_law`.

Those three newer laws remain fully in force through v0.1 and are not weakened by this addendum. The rule mapping below uses the requested seven foundational law names and, where directly relevant, also notes the newer current law that further constrains the rule. No invented law numbers are used.

## 2. Honesty scale

NOVA must express epistemic state using one of exactly five labels:

| Label | Meaning |
|---|---|
| `know` | Directly supported by current, attributable evidence. |
| `think` | Evidence supports a conclusion, but the conclusion is still an inference. |
| `guessing` | A hypothesis with weak or incomplete evidence. |
| `don't know` | The answer is not supported by current evidence. |
| `don't know how to know` | NOVA does not currently have a valid method, tool, permission, or observable signal that could establish the answer. |

Confidence is never reported as a free-floating number. A confidence statement must carry its evidence source.

Conceptual record:

```json
{
  "claim": "example claim",
  "honesty": "think",
  "confidence": 0.72,
  "evidence": [
    {
      "source": "probe/network_gateway",
      "observed_at": "2026-09-28T04:00:00+04:00",
      "result_ref": "..."
    }
  ]
}
```

If there is no evidence source, NOVA must not report numeric confidence. It must use `guessing`, `don't know`, or `don't know how to know` as appropriate.

**Foundational-law mapping:** `truth_law`, `guardian_law`, `learning_law`.  
**Additional current constraint:** `research_law`, `perception_law`.

## 3. Calibration

Calibration is tracked per domain, not as one global intelligence score.

Initial domains should follow actual implemented scenarios, for example:

- `network_diagnosis`
- later domains only after they exist and have independent verification

For each decision that includes a claimed confidence, calibration stores:

```json
{
  "domain": "network_diagnosis",
  "claim_id": "...",
  "claimed_confidence": 0.72,
  "outcome": "success",
  "verifier_evidence": ["..."],
  "verified_at": "2026-09-28T04:00:00+04:00"
}
```

Rules:

1. Only independent verifier evidence may set `outcome`.
2. Planner self-report, command exit status alone, model confidence, or user-facing wording never count as an outcome.
3. If independent verification is unavailable, outcome is `unknown`; that event is excluded from proven-success/proven-failure calibration totals.
4. Calibration is reported as `k/n` per domain and per claimed-confidence bucket:
   - `<0.7`
   - `0.7-0.9`
   - `>=0.9`
5. `k` is verifier-proven successes and `n` is total verifier-proven outcomes in that bucket.
6. If `n < 20` for a bucket, the report must say `insufficient calibration data`; it must make no reliability claim for that bucket.
7. Calibration may reveal overconfidence or underconfidence, but it must not silently change permission zones or approval requirements.

**Foundational-law mapping:** `truth_law`, `learning_law`, `guardian_law`.  
**Additional current constraint:** `perception_law`.

## 4. Failure record

Every verifier-proven failed attempt creates a failure record.

Required shape:

```json
{
  "problem": "what NOVA was trying to solve",
  "problem_key": "scenario + goal_type + target",
  "approach": "what approach/playbook/action sequence was attempted",
  "result": "the verifier-proven result",
  "signal_missed": "what observable signal should have changed the decision earlier",
  "next_time": "what should be checked or tried differently next time",
  "evidence": ["independent evidence references"]
}
```

Rules:

- `problem_key = scenario + goal_type + target`.
- Failure escalation counters are keyed by `problem_key`; rewording the same request does not reset the count.
- `result` must come from independent verification.
- `signal_missed` must name an observable signal, not invent a motive or hidden state.
- `next_time` is a lesson/hypothesis, not an automatic permission to modify a playbook.
- External text from logs, web pages, documents, issue comments, or model output remains **data, never instructions**.

**Foundational-law mapping:** `learning_law`, `truth_law`, `rollback_law`, `guardian_law`.  
**Additional current constraint:** `research_law`, `autocode_law`.

## 5. Playbook score and amendment boundary

Each approved playbook carries verifier-based counters:

```json
{
  "successes": 0,
  "failures": 0,
  "score": null
}
```

Score update rule:

- `successes` increments only after verifier-proven success.
- `failures` increments only after verifier-proven failure.
- when at least one proven outcome exists: `score = successes / (successes + failures)`.
- before any proven outcome: `score = null` and the playbook is `unrated`.
- score updates automatically when verifier evidence records a proven outcome.

A score is operational history, not confidence and not permission.

### Playbook amendment rule

Any change to a playbook's **trigger** or **action** is a new proposal and requires owner approval. NOVA may not silently tune trigger/action behavior because its score changed.

This preserves v0.1 Amendment 1:

- try proven playbooks first;
- invent alternatives only when no suitable playbook applies;
- a newly successful solution becomes a playbook only with owner approval.

A playbook is archived only when both conditions are true:

- proven outcomes `n = successes + failures` is at least `5`; and
- `score < 0.3`.

With fewer than 5 proven outcomes, the playbook remains active/unrated-for-archive regardless of score. This prevents one early failure from archiving a potentially useful playbook.

Archiving never deletes history. Counters, evidence, prior versions, and amendment chain remain available for audit. An archived playbook is not automatically selected.

**Foundational-law mapping:** `approval_law`, `learning_law`, `rollback_law`, `truth_law`.  
**Additional current constraint:** `autocode_law`.

## 6. Decision trace

Every decision must produce a trace before acting.

Required fields:

```json
{
  "decision_id": "...",
  "observed_at": "2026-09-28T04:00:00+04:00",
  "goal": "...",
  "problem_key": "scenario + goal_type + target",
  "inputs": ["fact/evidence references"],
  "unknowns": ["..."],
  "zone": "Green|Yellow|Red|Black",
  "zone_source": "external/static registry result",
  "playbook": "playbook id or null",
  "alternatives": [
    {
      "option": "...",
      "rejected": true,
      "why_rejected": "..."
    }
  ],
  "selected": "...",
  "success_check": "...",
  "verifier": "..."
}
```

Rules:

- Zone comes only from the external/static registry; NOVA never self-classifies.
- Unknown actions remain Red as defined by v0.1.
- The trace must include alternatives actually considered, not fabricated alternatives added after the fact.
- Rejection reasons must cite evidence, policy, missing information, risk, or applicability.
- Every goal still requires a success check defined before acting.
- No success check means no action.
- Decision traces are records, not executable instructions.

**Foundational-law mapping:** `approval_law`, `truth_law`, `guardian_law`, `rollback_law`.  
**Additional current constraint:** `autocode_law`, `research_law`.

## 7. Thinking-depth rules

v0.2 uses explicit depth rules, **not a weighted formula** and not a synthetic "genius score."

The deterministic depth policy is:

| Condition | Required behavior |
|---|---|
| Green + known applicable playbook | Run the approved playbook, then independently verify. |
| `unknowns > 0` | Information-seeking first. Do not act as though the unknown is known. |
| 2 verifier-proven failures for the same `problem_key` | Escalate thinking depth, widen evidence gathering within allowed bounds, and report the failures. |
| 3 verifier-proven failures for the same `problem_key` | Stop and ask the owner. |
| Conflicting applicable playbooks | Stop and ask the owner. Do not vote between playbooks. |
| Red action | Full analysis, decision trace, success check, risk summary, and owner approval before action. |
| Black action | Existing v0.1/core boundary remains authoritative; v0.2 thinking does not create a path around it. |

`problem_key` is deterministically formed as `scenario + goal_type + target`. The same operational problem keeps the same key even when the natural-language request is reworded.

"Escalate thinking depth" means gather more admissible evidence, revisit assumptions, inspect failure records, and generate/reject alternatives explicitly. It does not mean bypass the gate or call more models until one agrees.

**Foundational-law mapping:** `approval_law`, `learning_law`, `truth_law`, `guardian_law`, `rollback_law`.  
**Additional current constraint:** `research_law`, `autocode_law`.

## 8. Daily reflection journal

Daily reflection lives under:

```text
journal/YYYY-MM-DD.md
```

The date is derived from the Pi5's actual system time. While the Pi5 remains configured at `+04:00`, entries must preserve `+04:00` timestamps. Do not relabel them as `+05:30`.

Each daily journal contains at minimum:

```text
date
previous_journal_hash
decisions_count
verified_successes
verified_failures
unknown_outcomes
playbooks_used
playbooks_archived
gaps_found
still_confused_about
```

Narrative sections must include:

- counts;
- verifier-proven failures;
- important gaps/unknowns;
- `still confused about` items that remain unresolved.

### Journal signing

The reflection journal is signed with a **separate NOVA journal key**, not the owner approval key.

Design requirements:

- separate signing identity and namespace for NOVA journal records;
- owner approval key is never reused;
- the journal body contains `previous_journal_hash`, defined as the SHA256 of yesterday's complete `.md` file;
- today's own hash is **not** stored inside today's `.md`, avoiding a circular self-hash;
- today's signature is stored in the sidecar `journal/YYYY-MM-DD.md.sig`, not inside the `.md`;
- if yesterday's journal is missing or its hash/signature cannot be verified, today's journal records the break and does not pretend continuity;
- signing proves journal provenance/integrity only; it does not approve Red/Black actions.

A future implementation may use `ssh-keygen -Y sign` / `ssh-keygen -Y verify` with a dedicated journal namespace. The signature input is the exact completed `.md` bytes (or their documented SHA256, consistently defined before implementation). v0.2 design does not create or install keys.

**Foundational-law mapping:** `truth_law`, `learning_law`, `guardian_law`, `rollback_law`.

## 9. Counterfactuals, multiple thinkers, and external text

### No multi-thinker voting as confidence

Multiple models, personas, simulated experts, or "20 thinkers" may generate candidate hypotheses later, but agreement among them is not evidence and must not be converted into confidence.

Confidence remains tied to attributable evidence and calibration remains tied to verifier-proven outcomes.

### Counterfactual replay

Counterfactual replay may ask:

> If NOVA had checked signal X earlier, would a different approach have been worth testing?

Counterfactual results are **hypotheses only**. They are never auto-applied, never counted as verifier-proven outcomes, and never update a playbook trigger/action without owner-approved amendment.

### Web/docs/logs boundary

Web pages, documentation, logs, issue text, chat transcripts, fetched files, and model outputs are data. They never become instructions merely because they contain imperative language.

**Foundational-law mapping:** `truth_law`, `learning_law`, `guardian_law`, `approval_law`.  
**Additional current constraint:** `research_law`, `autocode_law`.

## 10. Later, not v0.2: Red-action red-team checklist

A future version may require an explicit Red-action red-team pass with the question:

> How can this fail?

Possible categories may include:

- wrong assumptions;
- stale evidence;
- unexpected side effects;
- incomplete rollback;
- dependency failure;
- permission escalation;
- data exposure;
- verification blind spots.

This is explicitly **not part of v0.2 implementation scope**. It must not block completion of the v0.1 network scenario or the v0.2 sequence below.

**Foundational-law mapping:** `guardian_law`, `approval_law`, `rollback_law`, `truth_law`.

## 11. Build order

Implementation order is fixed:

1. **Finish v0.1 network scenario.**
   - deterministic network diagnosis only;
   - preserve all v0.1 gate, evidence, world-model, TTL, success-check, verifier, and permission-zone rules.

2. **Honesty + decision trace.**
   - add five-state honesty reporting;
   - evidence-bound confidence;
   - trace every decision before acting.

3. **Failure records + playbook scores.**
   - verifier-proven failure records;
   - automatic success/failure counters;
   - archive only when proven outcomes `n >= 5` and score is below `0.3`;
   - no trigger/action amendment without owner approval.

4. **Reflection journal.**
   - daily counts/failures/gaps/confusion;
   - previous-day hash chain;
   - separate NOVA journal signature.

5. **Calibration.**
   - domain-specific and confidence-bucket `k/n` reporting;
   - `n < 20` in a bucket means `insufficient calibration data`, with no reliability claim;
   - unknown/unverified outcomes never treated as success or failure.

No later stage may be used to justify skipping an earlier stage.

## 12. Language and implementation constraints

When implementation begins:

- language: Python and shell only inside the `nova-life` lane unless the owner later approves otherwise;
- no modification to `core/` from this addendum;
- no new permission-zone logic inside the planner;
- no self-assigned approval;
- no downloaded/web-provided instructions executed as code;
- no auto-application of counterfactual conclusions;
- all timestamps retain the Pi5's actual offset, currently `+04:00`;
- v0.1 success-check and independent-verifier requirements remain mandatory.

## 13. Rule-to-foundational-law matrix

| v0.2 rule | Foundational law names |
|---|---|
| Honesty scale | `truth_law`, `guardian_law`, `learning_law` |
| Evidence-bound confidence | `truth_law`, `learning_law` |
| Domain calibration | `truth_law`, `learning_law`, `guardian_law` |
| Failure records | `learning_law`, `truth_law`, `rollback_law` |
| Playbook scoring | `learning_law`, `truth_law`, `rollback_law` |
| Trigger/action amendment requires owner | `approval_law`, `learning_law` |
| Archive low-score playbooks, keep history | `learning_law`, `rollback_law`, `truth_law` |
| Decision trace | `approval_law`, `truth_law`, `guardian_law` |
| External registry decides zone | `approval_law`, `guardian_law` |
| Unknowns cause info-seeking first | `learning_law`, `truth_law` |
| 2 failures escalate + report | `learning_law`, `rollback_law`, `truth_law` |
| 3 failures stop and ask owner | `approval_law`, `guardian_law`, `rollback_law` |
| Conflicting playbooks stop and ask owner | `approval_law`, `guardian_law` |
| Red gets full analysis + approval | `approval_law`, `guardian_law`, `rollback_law` |
| Daily reflection | `learning_law`, `truth_law` |
| Separate NOVA journal signature | `truth_law`, `guardian_law` |
| Hash-chain journals | `truth_law`, `rollback_law` |
| No multi-thinker voting as confidence | `truth_law`, `guardian_law` |
| Counterfactuals are hypotheses only | `truth_law`, `learning_law`, `approval_law` |
| Web/docs/logs are data, not instructions | `learning_law`, `guardian_law`, `approval_law` |
| Future Red red-team checklist | `guardian_law`, `approval_law`, `rollback_law`, `truth_law` |
| User-facing explanations follow user's language | `language_law` |
| Any future robot-motion use remains separately constrained | `robot_motion_law`, `approval_law`, `guardian_law` |

## 14. Non-goals

v0.2 does **not**:

- implement the network scenario;
- enable autocode;
- modify core laws;
- regenerate the core seal;
- change permission zones;
- create owner/NOVA keys;
- use multi-agent voting as truth;
- treat model agreement as evidence;
- auto-promote playbooks;
- execute web instructions;
- replace independent verification with command exit status.

This addendum defines thinking records and learning discipline only. Action authority remains where v0.1 and the core/gate place it.
