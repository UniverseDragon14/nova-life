#!/usr/bin/env bash
set -euo pipefail
PATH=/usr/bin:/bin
export PATH

alert() {
  printf 'DRAGON_ALERT %s\n' "$1"
  exit 1
}

SELF=$(/usr/bin/readlink -f -- "$0") || alert verifier_path_invalid
BIN_DIR=${SELF%/*}
ROOT=$(/usr/bin/readlink -f -- "$BIN_DIR/..") || alert verifier_path_invalid
CORE_DIR="$ROOT/core"

[ -d "$CORE_DIR" ] || alert required_material_missing
[ ! -L "$CORE_DIR" ] || alert trusted_path_invalid
CORE_REAL=$(/usr/bin/readlink -f -- "$CORE_DIR") || alert trusted_path_invalid
[ "$CORE_REAL" = "$CORE_DIR" ] || alert trusted_path_invalid

CORE_JSON="$CORE_DIR/nova.core.json"
SEAL="$CORE_DIR/nova.core.sha256"
ATTEST="$CORE_DIR/ATTESTATION.txt"
SIG="$CORE_DIR/ATTESTATION.txt.sig"
SIGNERS="$CORE_DIR/allowed_signers"

check_trusted_file() {
  local f="$1"
  local expected="$2"
  local real mode perm

  [ -e "$f" ] || alert required_material_missing
  [ -f "$f" ] || alert trusted_file_invalid
  [ ! -L "$f" ] || alert trusted_path_invalid
  [ -r "$f" ] || alert trusted_file_unreadable

  real=$(/usr/bin/readlink -f -- "$f") || alert trusted_path_invalid
  [ "$real" = "$expected" ] || alert trusted_path_invalid

  mode=$(/usr/bin/stat -c '%a' -- "$f") || alert trusted_permission_unavailable
  [[ "$mode" =~ ^[0-7]{3,4}$ ]] || alert trusted_permission_invalid
  perm=$((8#$mode))
  (( (perm & 0022) == 0 )) || alert trusted_file_writable
}

check_trusted_file "$CORE_JSON" "$CORE_DIR/nova.core.json"
check_trusted_file "$SEAL" "$CORE_DIR/nova.core.sha256"
check_trusted_file "$ATTEST" "$CORE_DIR/ATTESTATION.txt"
check_trusted_file "$SIG" "$CORE_DIR/ATTESTATION.txt.sig"
check_trusted_file "$SIGNERS" "$CORE_DIR/allowed_signers"

(
  cd "$ROOT"
  /usr/bin/sha256sum -c core/nova.core.sha256 --status
) || alert core_hash_mismatch

core_commit=''
core_sha256=''
statement=''
attest_date=''
count_commit=0
count_sha=0
count_statement=0
count_date=0

while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    'NOVA core attestation'|'') ;;
    'core_commit: '*)
      count_commit=$((count_commit + 1))
      core_commit=${line#core_commit: }
      ;;
    'core_sha256: '*)
      count_sha=$((count_sha + 1))
      core_sha256=${line#core_sha256: }
      ;;
    'statement: '*)
      count_statement=$((count_statement + 1))
      statement=${line#statement: }
      ;;
    'date: '*)
      count_date=$((count_date + 1))
      attest_date=${line#date: }
      ;;
    *) alert attestation_malformed ;;
  esac
done < "$ATTEST"

[ "$count_commit" -eq 1 ] || alert attestation_malformed
[ "$count_sha" -eq 1 ] || alert attestation_malformed
[ "$count_statement" -eq 1 ] || alert attestation_malformed
[ "$count_date" -eq 1 ] || alert attestation_malformed

[[ "$core_commit" =~ ^[0-9A-Fa-f]{40}$ ]] || alert attestation_malformed
[[ "$core_sha256" =~ ^[0-9A-Fa-f]{64}$ ]] || alert attestation_malformed
[ -n "$statement" ] || alert attestation_malformed
[ -n "$attest_date" ] || alert attestation_malformed

current_line=$(/usr/bin/sha256sum -- "$CORE_JSON") || alert core_hash_unavailable
current_sha=${current_line%% *}
[ "${current_sha,,}" = "${core_sha256,,}" ] || alert owner_attestation_core_mismatch

/usr/bin/git -C "$ROOT" cat-file -e "${core_commit}^{commit}" 2>/dev/null \
  || alert history_unavailable

/usr/bin/git -C "$ROOT" cat-file -e "${core_commit}:core/nova.core.json" 2>/dev/null \
  || alert attested_commit_mismatch

set +e
blob_line=$(
  /usr/bin/git -C "$ROOT" show "${core_commit}:core/nova.core.json" 2>/dev/null \
    | /usr/bin/sha256sum
)
blob_rc=$?
set -e
[ "$blob_rc" -eq 0 ] || alert history_unavailable
blob_sha=${blob_line%% *}
[ "${blob_sha,,}" = "${core_sha256,,}" ] || alert attested_commit_mismatch

/usr/bin/ssh-keygen -Y verify \
  -f "$SIGNERS" \
  -I owner \
  -n udnos-core \
  -s "$SIG" \
  < "$ATTEST" >/dev/null 2>&1 \
  || alert owner_signature_invalid

printf 'DRAGON_OK core intact and owner-attested\n'
exit 0
