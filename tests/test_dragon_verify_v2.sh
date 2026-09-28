#!/usr/bin/env bash
set -euo pipefail
PATH=/usr/bin:/bin
export PATH

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
SRC_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
CANDIDATE="$SRC_ROOT/bin/dragon_verify.sh"
TMP=$(/usr/bin/mktemp -d)
trap '/usr/bin/rm -rf "$TMP"' EXIT

BASE="$TMP/base"
/usr/bin/git clone -q --no-hardlinks "$SRC_ROOT" "$BASE"
/usr/bin/cp "$CANDIDATE" "$BASE/bin/dragon_verify.sh"
/usr/bin/chmod 0755 "$BASE/bin/dragon_verify.sh"
/usr/bin/chmod 0644 \
  "$BASE/core/nova.core.json" \
  "$BASE/core/nova.core.sha256" \
  "$BASE/core/ATTESTATION.txt" \
  "$BASE/core/ATTESTATION.txt.sig" \
  "$BASE/core/allowed_signers"

pass=0
fail=0

new_case() {
  local name="$1"
  local dir="$TMP/$name"
  /usr/bin/cp -a "$BASE" "$dir"
  printf '%s\n' "$dir"
}

expect_case() {
  local name="$1"
  local repo="$2"
  local expected="$3"
  local expected_rc="${4:-nonzero}"
  local out rc
  set +e
  out=$("$repo/bin/dragon_verify.sh" 2>&1)
  rc=$?
  set -e
  if [ "$expected_rc" = "zero" ]; then
    if [ "$rc" -eq 0 ] && [[ "$out" == *"$expected"* ]]; then
      printf 'PASS %-28s rc=%s %s\n' "$name" "$rc" "$expected"
      pass=$((pass+1))
    else
      printf 'FAIL %-28s rc=%s out=%s\n' "$name" "$rc" "$out"
      fail=$((fail+1))
    fi
  else
    if [ "$rc" -ne 0 ] && [[ "$out" == *"$expected"* ]]; then
      printf 'PASS %-28s rc=%s %s\n' "$name" "$rc" "$expected"
      pass=$((pass+1))
    else
      printf 'FAIL %-28s rc=%s out=%s\n' "$name" "$rc" "$out"
      fail=$((fail+1))
    fi
  fi
}

r=$(new_case baseline)
expect_case baseline "$r" "DRAGON_OK core intact and owner-attested" zero

r=$(new_case core_changed)
/usr/bin/printf '\n' >> "$r/core/nova.core.json"
expect_case core_changed "$r" "DRAGON_ALERT core_hash_mismatch"

r=$(new_case core_and_seal_changed)
/usr/bin/printf '\n' >> "$r/core/nova.core.json"
( cd "$r" && /usr/bin/sha256sum core/nova.core.json > core/nova.core.sha256 )
expect_case core_and_seal_changed "$r" "DRAGON_ALERT owner_attestation_core_mismatch"

r=$(new_case attestation_changed)
/usr/bin/python3 - "$r/core/ATTESTATION.txt" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); s=p.read_text()
s=s.replace("statement: I, the owner, reviewed and approve this core.",
            "statement: I, the owner, reviewed and approve this core. altered",1)
p.write_text(s)
PY
expect_case attestation_changed "$r" "DRAGON_ALERT owner_signature_invalid"

r=$(new_case wrong_namespace)
/usr/bin/sed -i 's/namespaces="udnos-core"/namespaces="wrong-core"/' "$r/core/allowed_signers"
expect_case wrong_namespace "$r" "DRAGON_ALERT owner_signature_invalid"

r=$(new_case wrong_identity)
/usr/bin/sed -i 's/^owner /other /' "$r/core/allowed_signers"
expect_case wrong_identity "$r" "DRAGON_ALERT owner_signature_invalid"

r=$(new_case missing_signature)
/usr/bin/rm -f "$r/core/ATTESTATION.txt.sig"
expect_case missing_signature "$r" "DRAGON_ALERT required_material_missing"

r=$(new_case wrong_public_key)
/usr/bin/ssh-keygen -q -t ed25519 -N '' -f "$r/wrong_key" >/dev/null
pub=$(/usr/bin/cat "$r/wrong_key.pub")
/usr/bin/printf 'owner namespaces="udnos-core" %s\n' "$pub" > "$r/core/allowed_signers"
/usr/bin/rm -f "$r/wrong_key" "$r/wrong_key.pub"
expect_case wrong_public_key "$r" "DRAGON_ALERT owner_signature_invalid"

r=$(new_case duplicate_sha)
line=$(/usr/bin/grep '^core_sha256:' "$r/core/ATTESTATION.txt")
/usr/bin/printf '%s\n' "$line" >> "$r/core/ATTESTATION.txt"
expect_case duplicate_sha "$r" "DRAGON_ALERT attestation_malformed"

r=$(new_case commit_blob_mismatch)
other=$(/usr/bin/git -C "$r" rev-parse c0c98ca)
/usr/bin/python3 - "$r/core/ATTESTATION.txt" "$other" <<'PY'
from pathlib import Path
import sys,re
p=Path(sys.argv[1]); other=sys.argv[2]
s=p.read_text()
s=re.sub(r'^core_commit: [0-9a-fA-F]{40}$', 'core_commit: '+other, s, count=1, flags=re.M)
p.write_text(s)
PY
expect_case commit_blob_mismatch "$r" "DRAGON_ALERT attested_commit_mismatch"

r=$(new_case symlink_swap)
/usr/bin/mv "$r/core/ATTESTATION.txt" "$r/attestation.real"
/usr/bin/ln -s ../attestation.real "$r/core/ATTESTATION.txt"
expect_case symlink_swap "$r" "DRAGON_ALERT trusted_path_invalid"

r=$(new_case group_writable)
/usr/bin/chmod 0664 "$r/core/allowed_signers"
expect_case group_writable "$r" "DRAGON_ALERT trusted_file_writable"

r=$(new_case world_writable)
/usr/bin/chmod 0666 "$r/core/ATTESTATION.txt.sig"
expect_case world_writable "$r" "DRAGON_ALERT trusted_file_writable"

r=$(new_case path_hijack)
/usr/bin/mkdir -p "$r/fakebin"
/usr/bin/printf '#!/bin/sh\ntouch "%s"\nexit 99\n' "$r/PATH_HIJACKED" > "$r/fakebin/sha256sum"
/usr/bin/printf '#!/bin/sh\ntouch "%s"\nexit 99\n' "$r/PATH_HIJACKED" > "$r/fakebin/ssh-keygen"
/usr/bin/chmod 0755 "$r/fakebin/sha256sum" "$r/fakebin/ssh-keygen"
set +e
out=$(PATH="$r/fakebin:/usr/bin:/bin" "$r/bin/dragon_verify.sh" 2>&1)
rc=$?
set -e
if [ "$rc" -eq 0 ] && [[ "$out" == *"DRAGON_OK core intact and owner-attested"* ]] && [ ! -e "$r/PATH_HIJACKED" ]; then
  printf 'PASS %-28s rc=%s absolute-tools-used\n' path_hijack "$rc"
  pass=$((pass+1))
else
  printf 'FAIL %-28s rc=%s out=%s marker=%s\n' path_hijack "$rc" "$out" "$([ -e "$r/PATH_HIJACKED" ] && echo yes || echo no)"
  fail=$((fail+1))
fi

r=$(new_case history_unavailable)
/usr/bin/mv "$r/.git" "$r/.git.off"
expect_case history_unavailable "$r" "DRAGON_ALERT history_unavailable"

r=$(new_case core_dir_symlink)
/usr/bin/mv "$r/core" "$r/outside-core"
/usr/bin/ln -s outside-core "$r/core"
expect_case core_dir_symlink "$r" "DRAGON_ALERT trusted_path_invalid"

printf 'TOTAL_PASS=%s\nTOTAL_FAIL=%s\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
