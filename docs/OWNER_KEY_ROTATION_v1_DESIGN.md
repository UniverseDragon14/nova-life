# NOVA Owner Key Rotation v1 — Design

**Status:** design only. No trust file, key, verifier, core law, service, or SSH-login change is authorized by this document.
**Scope:** nova-life lane.
**Goal:** move routine Black approvals from the current owner key to a new iPhone owner key while keeping a separate recovery key that cannot authorize routine approvals.

## 0. Current state

Current routine owner trust fingerprint:

`SHA256:z9l+iWVR4ZN/44uCquOs6x1laalskDPaLDlbiS8okG0`

Current main:
`2006f008d7e17012a3495af166f2e3a176d673af`

Current hardened-verifier branch:
`dff5e6f9481a4434e5ad58cd2a56a343e7e13c94`

The expected inbox `~/nova-life-inbox/` is not currently present on the Pi5. New public keys must be transferred before any rotation execution.

Private keys never enter the Pi5.
## 1. Sequencing

Do not rotate the owner trust key while the hardened verifier is still pending deployment.

Required order:

1. finish the already-reviewed dragon_verify v2 deployment;
2. hand-run verifier => DRAGON_OK;
3. observe normal NOVA/heartbeat verifier health;
4. push that verified state;
5. only then begin owner-key rotation from the resulting main commit.

Reason: the trust anchor should remain stable while the verifier that enforces it is being replaced.

## 2. Roles

### Primary owner key

Expected public key:
`~/nova-life-inbox/udnos_owner_ios.pub`

Purpose:
routine Black owner approvals.

Principal:
`owner`

Namespace:
`udnos-core`

### Recovery key

Expected public key:
`~/nova-life-inbox/udnos_recovery.pub`

Purpose:
manual recovery of owner trust only.

Principal:
`owner-recovery`

Namespace:
`udnos-recovery`

The recovery key is **not** listed in routine `core/allowed_signers` and cannot approve normal Black actions.
## 3. Proposed trust files

Routine trust:

`core/allowed_signers`

contains only the new primary owner public key with principal `owner` and namespace `udnos-core`.

Recovery trust:

`core/recovery_allowed_signers`

contains only the recovery public key with principal `owner-recovery` and namespace `udnos-recovery`.

Both public trust files are ordinary public material but are part of the Black trust boundary and therefore require signed owner authorization before modification.

## 4. Rotation authorization document

Create:

`core/ATTESTATION_KEY_ROTATION_v1.txt`

Plain ASCII, LF, <2KB.

Fields:

```text
purpose=owner-key-rotation-v1
base_commit=<verified post-dragon-v2 main commit>
old_owner_fingerprint=<current trusted fingerprint>
new_owner_ios_fingerprint=<fingerprint of udnos_owner_ios.pub>
recovery_fingerprint=<fingerprint of udnos_recovery.pub>
new_allowed_signers_sha256=<sha256 of proposed routine trust file>
new_recovery_allowed_signers_sha256=<sha256 of proposed recovery trust file>
routine_principal=owner
routine_namespace=udnos-core
recovery_principal=owner-recovery
recovery_namespace=udnos-recovery
statement=replace routine owner key only; recovery key is not valid for routine approvals
date=<ISO date>
approved_by=owner
```
## 5. Authorization signature

The rotation attestation is signed by the **currently trusted old owner key** before that key is retired.

Verification uses the current trust file:

```text
ssh-keygen -Y verify
  -f core/allowed_signers
  -I owner
  -n udnos-core
  -s core/ATTESTATION_KEY_ROTATION_v1.txt.sig
  < core/ATTESTATION_KEY_ROTATION_v1.txt
```

Only `Good "udnos-core" signature for owner` with exit code 0 authorizes the trust handoff.

The attestation must also bind:
- the exact old trusted fingerprint;
- exact new public-key fingerprints;
- exact SHA256 of both proposed trust files;
- exact base commit.

Any mismatch => STOP.

## 6. Apply rules

Only after valid old-key authorization:

1. verify both inbox files parse as public ED25519 keys;
2. reject any private-key-looking file/content;
3. verify fingerprints equal the signed attestation;
4. construct proposed trust files from the exact transferred public keys;
5. verify their SHA256 values equal the signed attestation;
6. under system lock, install the two trust files with non-writable trusted permissions;
7. do not alter core law content or seal;
8. do not delete the old attestation/history.
## 7. New-key proof before retirement

After installing proposed trust files, prove the new primary key works before considering the old device disposable.

Create a short nonce/challenge file on Pi5 containing:
- purpose=new-owner-key-enrollment-proof
- current commit
- random nonce
- timestamp

Copy it to iPhone, sign with `udnos_owner_ios` under namespace `udnos-core`, return only the signature, and verify against the new routine trust file.

Required:
`Good "udnos-core" signature for owner`.

Recovery enrollment is separate:
sign a recovery challenge with `udnos_recovery` under namespace `udnos-recovery` and verify against `core/recovery_allowed_signers`.

Only after both proofs pass and dragon_verify remains DRAGON_OK is the old Huawei owner key considered retired.

## 8. Replay resistance

The rotation attestation names:
- the old fingerprint;
- the new fingerprints;
- the base commit;
- exact replacement trust-file hashes.

Execution additionally requires the currently installed routine trust fingerprint to equal `old_owner_fingerprint`.

After successful rotation, the old key is no longer in `core/allowed_signers`. Replaying the old rotation attestation therefore cannot satisfy the current-trust precondition.

The signed attestation remains archived as audit evidence.
## 9. Recovery semantics

The recovery key cannot sign ordinary `udnos-core` approvals.

A future recovery procedure must use:
- principal `owner-recovery`;
- namespace `udnos-recovery`;
- `core/recovery_allowed_signers`;
- an explicit recovery attestation that names the replacement owner key.

Physical access to the Pi5 remains the final authority if all owner/recovery keys are lost.

## 10. Important device note

If both `udnos_owner_ios` and `udnos_recovery` private keys live only on the same iPhone, they protect against key-file loss but not against loss/destruction of that phone.

For stronger recovery, keep an encrypted/passphrase-protected recovery-key backup on a separate offline device or medium. The private key still never belongs on the Pi5 or in chat.

## 11. Not part of this design

This design does not:
- transfer public keys;
- modify allowed_signers;
- rotate any key;
- erase the Huawei phone;
- modify dragon_verify;
- enable camera-watch;
- change SSH login/password policy;
- create passwordless SSH login keys;
- disable SSH password authentication;
- commit or push anything.

## 12. Approved apply additions (2026-09-28)

### 12.1 Lock identity

Any live cutover/system action uses:

`AGENT_NAME=nova`

with the shared system lock.

### 12.2 Rotation-signature pin

The verifier pins both:
- rotation attestation SHA256: `d5d014e49172323cf54c023e301fa1df71644ea21f52b5b8cb9afe2c3622512c`;
- rotation signature SHA256: `d91fe5f559bf5576e60bbe093ed9908134001caabf9d95a3f4328c4df1b23ed6`.

A different rotation signature file alerts before signature verification.

### 12.3 Historical verification after retirement

The retired Huawei key remains only in `core/historical_allowed_signers` under principal `retired-owner-v1`, namespace `udnos-core`.

Only the exact allowlisted historical attestation/signature hash pairs in `core/historical_attestations_v1.txt`, plus the exact signed rotation attestation pair, are accepted.
A new or renamed post-rotation attestation carrying a valid retired-key signature is rejected with `retired_key_not_allowlisted`.

### 12.4 Consumed challenge audit evidence

The four consumed challenge artifacts are copied to:

`docs/evidence/rotation_v1/`

with `SHA256SUMS`, mode 0644.

They are public audit evidence only. `bin/dragon_verify.sh` does not use them as trust inputs.

### 12.5 Pre-push proof stop

After live cutover and before push, show:
- old 17 test matrix;
- rotation test matrix;
- direct `bin/dragon_verify.sh` output;
- next live journal line with `core=ok`;
- `git log -3 --show-signature`.

Push requires a separate owner OK.

### 12.6 Deferred mode-hardening design

A durable fix for Git checkout recreating trusted core files under umask 002 is explicitly deferred. No umask, hook, or service change is part of rotation v1.
