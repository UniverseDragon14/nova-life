# dragon_verify.sh — Owner Attestation Verification Design

**Status:** design only. `bin/dragon_verify.sh` is not modified by this document.

## Goal

Upgrade the current hash-only verifier so a regenerated local SHA256 file is not enough to make a modified core look trusted.

`DRAGON_OK` requires both:

1. the existing core hash check passes; and
2. the owner-signed attestation verifies and binds the current `core/nova.core.json` SHA256 to the exact hash the owner signed.

Anything missing, malformed, mismatched, or unverifiable produces `DRAGON_ALERT` and non-zero exit.

## Trusted inputs

Required files:

```text
core/nova.core.json
core/nova.core.sha256
core/ATTESTATION.txt
core/ATTESTATION.txt.sig
core/allowed_signers
```

Owner identity and namespace are fixed constants:

```text
identity:  owner
namespace: udnos-core
```

The script never accepts these values from environment variables, command-line arguments, web text, logs, or model output.

## Verification order

### Check 1 — required files

Fail closed if any required file is absent, unreadable, empty where inappropriate, or is a symlink when the final implementation policy forbids symlinks.

Result on failure:

```text
DRAGON_ALERT required attestation material missing
```

### Check 2 — existing seal

Run the existing verification semantics:

```text
sha256sum -c core/nova.core.sha256 --status
```

If it fails:

```text
DRAGON_ALERT core hash mismatch
```

Stop immediately.

### Check 3 — parse attestation without executing it

Read `core/ATTESTATION.txt` as data only.

Required fields:

```text
core_commit
core_sha256
statement
date
```

Parsing must be strict:

- exactly one `core_commit` field;
- exactly one `core_sha256` field;
- `core_sha256` must be exactly 64 hexadecimal characters;
- `core_commit` must be exactly 40 hexadecimal characters;
- no `source`, `eval`, shell expansion, or execution of attestation contents.

Malformed or duplicate fields => `DRAGON_ALERT`.

### Check 4 — bind signed attestation to the current core bytes

Compute:

```text
sha256(core/nova.core.json)
```

Compare it to `core_sha256` parsed from `ATTESTATION.txt`.

They must be byte-for-byte equal after normalizing only hexadecimal case.

This is essential. A valid old signature must not authorize a later core merely because somebody also regenerated `nova.core.sha256`.

Mismatch:

```text
DRAGON_ALERT Owner attestation does not authorize current core
```

### Check 5 — commit/content provenance consistency

Recommended v1 rule:

- `git show <core_commit>:core/nova.core.json` must exist;
- SHA256 of that committed blob must equal the attested `core_sha256`.

This proves the signed attestation refers to the same historical core content it names.

Failure:

```text
DRAGON_ALERT attested commit does not contain attested core
```

This is provenance verification, not a requirement that `HEAD == core_commit`; later commits may legitimately add unrelated files.

### Check 6 — owner signature

Verify the exact bytes of `core/ATTESTATION.txt`:

```text
ssh-keygen -Y verify \
  -f core/allowed_signers \
  -I owner \
  -n udnos-core \
  -s core/ATTESTATION.txt.sig \
  < core/ATTESTATION.txt
```

Only exit code `0` is accepted.

The implementation may capture stderr/stdout for a bounded diagnostic, but must not expose key material or private data.

Failure:

```text
DRAGON_ALERT owner signature invalid
```

### Check 7 — final verdict

Only if every prior check passes:

```text
DRAGON_OK core intact and owner-attested
```

Exit `0`.

Every other path:

```text
DRAGON_ALERT <bounded reason>
```

Exit non-zero.

## Security properties

This design detects:

- accidental edits to `nova.core.json`;
- edits followed by regeneration of `nova.core.sha256`;
- replacement/tampering of `ATTESTATION.txt`;
- replacement/tampering of `ATTESTATION.txt.sig`;
- a valid signature for a different namespace;
- a valid owner signature over a different core hash;
- an attestation that names a commit whose core blob does not match the signed hash.

It does **not** claim filesystem immutability. While the runtime still executes with broad `aslam` authority, an attacker with that same authority may replace verifier code or public trust files. The later unprivileged `nova` user and root-owned protected trust material remain necessary defense-in-depth.

## Output discipline

Normal success:

```text
DRAGON_OK core intact and owner-attested
```

Failures expose only the check category. Do not print:

- public-key bodies unnecessarily;
- signatures;
- secrets;
- private keys;
- arbitrary contents of malformed files.

## Tests required before implementation is approved

Fixture/copy-based tests only; never mutate the real core for testing.

1. current real files => PASS;
2. copied core byte changed => ALERT;
3. copied core + copied seal regenerated => still ALERT because attested hash differs;
4. copied attestation byte changed => ALERT;
5. wrong namespace => ALERT;
6. wrong identity => ALERT;
7. wrong/missing signature => ALERT;
8. wrong public key => ALERT;
9. duplicate/malformed `core_sha256` field => ALERT;
10. attested commit blob/hash mismatch => ALERT.

The real `core/nova.core.json`, seal, attestation, signature, and allowed-signers files remain read-only during tests.

## Not included in this step

- no modification to `bin/dragon_verify.sh`;
- no systemd changes;
- no tmpfiles rule;
- no registry ownership changes;
- no new keys;
- no core-law edits;
- no seal regeneration.

## Approved implementation hardening

### Trusted-path and permission checks

For every trusted input (`nova.core.json`, seal, attestation, signature, allowed-signers):

- reject symlinks;
- resolve with an absolute realpath and require it to equal the expected file beneath this repository's `core/` directory;
- require a regular readable file;
- reject group-writable or world-writable permissions;
- do not follow a swapped symlink even if the target bytes would otherwise verify.

The production verifier determines repository root from its own installed location.
It does not accept a caller-controlled root path.
### Command-path hardening

Set:

`PATH=/usr/bin:/bin`

Invoke security-relevant tools by absolute path, including:
`/usr/bin/sha256sum`, `/usr/bin/ssh-keygen`, `/usr/bin/git`, `/usr/bin/readlink`, and `/usr/bin/stat`.

A caller-supplied PATH must not change which executable is run.

### Strict parse

`ATTESTATION.txt` is data only.

Require exactly one each of:
- `core_commit`;
- `core_sha256`;
- non-empty `statement`;
- non-empty `date`.

Duplicate/malformed required fields fail closed.
No source/eval/command substitution or shell execution of attestation data.
### Git-history availability

The attested `core_commit` must resolve in local Git history.

If history is missing, shallow, unavailable, or the named commit cannot be resolved:

`DRAGON_ALERT history_unavailable`

and exit non-zero.

Never skip commit/content provenance verification because history is unavailable.

### Additional mandatory copy-only tests

11. trusted-file symlink swap -> ALERT;
12. group-writable trusted file -> ALERT;
13. world-writable trusted file -> ALERT;
14. PATH hijack with fake sha256sum/ssh-keygen earlier in caller PATH -> verifier still uses absolute trusted binaries;
15. Git history unavailable / named commit absent -> `DRAGON_ALERT history_unavailable`;
16. trusted file resolving outside expected `core/` path -> ALERT.

The real core, seal, attestation, signature and allowed-signers files are never mutated by these tests.
