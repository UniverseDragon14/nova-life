#!/usr/bin/env bash
set -euo pipefail
PATH=/usr/bin:/bin
export PATH

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SRC_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
TMP=$(/usr/bin/mktemp -d)
trap '/usr/bin/rm -rf "$TMP"' EXIT

BASE="$TMP/base"
/usr/bin/git clone -q --no-hardlinks "$SRC_ROOT" "$BASE"
/usr/bin/git -C "$BASE" checkout -q dff5e6f9481a4434e5ad58cd2a56a343e7e13c94

for f in   bin/dragon_verify.sh   core/ATTESTATION_KEY_ROTATION_v1.txt   core/ATTESTATION_KEY_ROTATION_v1.txt.sig   core/allowed_signers   core/recovery_allowed_signers   core/historical_allowed_signers   core/historical_attestations_v1.txt; do
  /usr/bin/cp "$SRC_ROOT/$f" "$BASE/$f"
done

/usr/bin/mkdir -p "$BASE/docs/evidence/rotation_v1"
/usr/bin/cp "$SRC_ROOT/docs/evidence/rotation_v1/"* "$BASE/docs/evidence/rotation_v1/"
/usr/bin/chmod 0755 "$BASE/bin/dragon_verify.sh"
/usr/bin/chmod 0644   "$BASE/core/nova.core.json"   "$BASE/core/nova.core.sha256"   "$BASE/core/ATTESTATION.txt"   "$BASE/core/ATTESTATION.txt.sig"   "$BASE/core/ATTESTATION_METADATA_v1.txt"   "$BASE/core/ATTESTATION_METADATA_v1.txt.sig"   "$BASE/core/ATTESTATION_KEY_ROTATION_v1.txt"   "$BASE/core/ATTESTATION_KEY_ROTATION_v1.txt.sig"   "$BASE/core/allowed_signers"   "$BASE/core/recovery_allowed_signers"   "$BASE/core/historical_allowed_signers"   "$BASE/core/historical_attestations_v1.txt"   "$BASE/docs/evidence/rotation_v1/"*

pass=0
fail=0

ok() {
  printf 'PASS %-38s %s\n' "$1" "$2"
  pass=$((pass+1))
}
bad() {
  printf 'FAIL %-38s %s\n' "$1" "$2"
  fail=$((fail+1))
}
new_case() {
  local name="$1"
  local dir="$TMP/$name"
  /usr/bin/cp -a "$BASE" "$dir"
  printf '%s\n' "$dir"
}
expect_alert() {
  local name="$1" repo="$2" expected="$3" out rc
  set +e
  out=$("$repo/bin/dragon_verify.sh" 2>&1)
  rc=$?
  set -e
  if [ "$rc" -ne 0 ] && [[ "$out" == *"$expected"* ]]; then
    ok "$name" "$expected"
  else
    bad "$name" "rc=$rc out=$out"
  fi
}

expect_ok() {
  local name="$1" repo="$2" out rc
  set +e
  out=$("$repo/bin/dragon_verify.sh" 2>&1)
  rc=$?
  set -e
  if [ "$rc" -eq 0 ] && [ "$out" = "DRAGON_OK core intact and owner-attested" ]; then
    ok "$name" "$out"
  else
    bad "$name" "rc=$rc out=$out"
  fi
}

if /usr/bin/ssh-keygen -Y verify   -f "$BASE/core/historical_allowed_signers" -I retired-owner-v1 -n udnos-core   -s "$BASE/core/ATTESTATION.txt.sig" < "$BASE/core/ATTESTATION.txt" >/dev/null 2>&1; then
  ok historical_core_signature "old proof verifies"
else
  bad historical_core_signature "verify failed"
fi
if /usr/bin/ssh-keygen -Y verify   -f "$BASE/core/historical_allowed_signers" -I retired-owner-v1 -n udnos-core   -s "$BASE/core/ATTESTATION_METADATA_v1.txt.sig" < "$BASE/core/ATTESTATION_METADATA_v1.txt" >/dev/null 2>&1; then
  ok historical_metadata_signature "old metadata proof verifies"
else
  bad historical_metadata_signature "verify failed"
fi

if /usr/bin/ssh-keygen -Y verify   -f "$BASE/core/historical_allowed_signers" -I retired-owner-v1 -n udnos-core   -s "$BASE/core/ATTESTATION_KEY_ROTATION_v1.txt.sig" < "$BASE/core/ATTESTATION_KEY_ROTATION_v1.txt" >/dev/null 2>&1; then
  ok rotation_old_owner_signature "exact rotation proof verifies"
else
  bad rotation_old_owner_signature "verify failed"
fi

r=$(new_case new_old_key_attestation)
/usr/bin/cp "$r/core/ATTESTATION_KEY_ROTATION_v1.txt" "$r/core/ATTESTATION_POST_ROTATION_OLD.txt"
/usr/bin/cp "$r/core/ATTESTATION_KEY_ROTATION_v1.txt.sig" "$r/core/ATTESTATION_POST_ROTATION_OLD.txt.sig"
/usr/bin/chmod 0644 "$r/core/ATTESTATION_POST_ROTATION_OLD.txt" "$r/core/ATTESTATION_POST_ROTATION_OLD.txt.sig"
expect_alert new_old_key_attestation "$r" "DRAGON_ALERT retired_key_not_allowlisted"

r=$(new_case historical_attestation_tamper)
/usr/bin/printf '\n' >> "$r/core/ATTESTATION.txt"
expect_alert historical_attestation_tamper "$r" "DRAGON_ALERT historical_attestation_hash_mismatch"
r=$(new_case historical_signature_tamper)
/usr/bin/printf '\n' >> "$r/core/ATTESTATION.txt.sig"
expect_alert historical_signature_tamper "$r" "DRAGON_ALERT historical_attestation_signature_hash_mismatch"

r=$(new_case historical_manifest_tamper)
/usr/bin/printf '\n' >> "$r/core/historical_attestations_v1.txt"
expect_alert historical_manifest_tamper "$r" "DRAGON_ALERT historical_manifest_hash_mismatch"

r=$(new_case old_key_as_routine)
/usr/bin/cp "$r/core/historical_allowed_signers" "$r/core/allowed_signers"
expect_alert old_key_as_routine "$r" "DRAGON_ALERT current_signers_hash_mismatch"

r=$(new_case recovery_key_as_routine)
/usr/bin/python3 - "$r/core/recovery_allowed_signers" "$r/core/allowed_signers" <<'PY'
from pathlib import Path
import sys
src=Path(sys.argv[1]).read_text().split()
keytype=next(x for x in src if x.startswith("ssh-"))
i=src.index(keytype)
keydata=src[i+1]
Path(sys.argv[2]).write_text(f'owner namespaces="udnos-core" {keytype} {keydata}\n')
PY
expect_alert recovery_key_as_routine "$r" "DRAGON_ALERT current_signers_hash_mismatch"

r=$(new_case rotation_signature_tamper)
/usr/bin/printf '\n' >> "$r/core/ATTESTATION_KEY_ROTATION_v1.txt.sig"
expect_alert rotation_signature_tamper "$r" "DRAGON_ALERT rotation_signature_hash_mismatch"
r=$(new_case rotation_attestation_tamper)
/usr/bin/printf '\n' >> "$r/core/ATTESTATION_KEY_ROTATION_v1.txt"
expect_alert rotation_attestation_tamper "$r" "DRAGON_ALERT rotation_attestation_hash_mismatch"

r=$(new_case recovery_trust_tamper)
/usr/bin/printf '\n' >> "$r/core/recovery_allowed_signers"
expect_alert recovery_trust_tamper "$r" "DRAGON_ALERT recovery_signers_hash_mismatch"

OWNER_CH="$BASE/docs/evidence/rotation_v1/owner-ios-20260928T160632Z.challenge"
OWNER_SIG="$OWNER_CH.sig"
if /usr/bin/ssh-keygen -Y verify   -f "$BASE/core/allowed_signers" -I owner -n udnos-core   -s "$OWNER_SIG" < "$OWNER_CH" >/dev/null 2>&1; then
  ok owner_ios_challenge_proof "new routine key verifies"
else
  bad owner_ios_challenge_proof "verify failed"
fi

REC_CH="$BASE/docs/evidence/rotation_v1/owner-recovery-20260928T160632Z.challenge"
REC_SIG="$REC_CH.sig"
if /usr/bin/ssh-keygen -Y verify   -f "$BASE/core/recovery_allowed_signers" -I owner-recovery -n udnos-recovery   -s "$REC_SIG" < "$REC_CH" >/dev/null 2>&1; then
  ok recovery_challenge_proof "recovery key verifies only recovery namespace"
else
  bad recovery_challenge_proof "verify failed"
fi
if ( cd "$BASE/docs/evidence/rotation_v1" && /usr/bin/sha256sum -c SHA256SUMS >/dev/null ); then
  ok audit_evidence_sha256 "all 4 consumed challenge artifacts match"
else
  bad audit_evidence_sha256 "sha256 list failed"
fi

r=$(new_case evidence_not_trust_input)
/usr/bin/printf '\nAUDIT_ONLY_TAMPER\n' >> "$r/docs/evidence/rotation_v1/owner-ios-20260928T160632Z.challenge"
expect_ok evidence_not_trust_input "$r"

r=$(new_case baseline_rotation)
expect_ok baseline_rotation "$r"

printf 'ROTATION_TOTAL_PASS=%s\nROTATION_TOTAL_FAIL=%s\n' "$pass" "$fail"
[ "$pass" -eq 17 ] && [ "$fail" -eq 0 ]
