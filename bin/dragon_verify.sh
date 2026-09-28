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
META="$CORE_DIR/ATTESTATION_METADATA_v1.txt"
META_SIG="$CORE_DIR/ATTESTATION_METADATA_v1.txt.sig"

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

META_PRESENT=0
if [ -e "$META" ] || [ -e "$META_SIG" ]; then
  [ -e "$META" ] && [ -e "$META_SIG" ] || alert required_material_missing
  check_trusted_file "$META" "$CORE_DIR/ATTESTATION_METADATA_v1.txt"
  check_trusted_file "$META_SIG" "$CORE_DIR/ATTESTATION_METADATA_v1.txt.sig"
  META_PRESENT=1
fi

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

if [ "$META_PRESENT" -eq 1 ]; then
  meta_purpose=''
  meta_base_commit=''
  meta_core_json_mode=''
  meta_core_json_sha=''
  meta_seal_mode=''
  meta_seal_sha=''
  meta_date=''
  meta_approved_by=''
  meta_count_purpose=0
  meta_count_base=0
  meta_count_json=0
  meta_count_seal=0
  meta_count_date=0
  meta_count_owner=0

  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      'purpose=metadata-only hardening, no content change')
        meta_count_purpose=$((meta_count_purpose + 1))
        meta_purpose=${line#purpose=}
        ;;
      'base_commit='*)
        meta_count_base=$((meta_count_base + 1))
        meta_base_commit=${line#base_commit=}
        ;;
      'file=core/nova.core.json mode='*)
        meta_count_json=$((meta_count_json + 1))
        rest=${line#file=core/nova.core.json mode=}
        meta_core_json_mode=${rest%% sha256=*}
        meta_core_json_sha=${rest#* sha256=}
        ;;
      'file=core/nova.core.sha256 mode='*)
        meta_count_seal=$((meta_count_seal + 1))
        rest=${line#file=core/nova.core.sha256 mode=}
        meta_seal_mode=${rest%% sha256=*}
        meta_seal_sha=${rest#* sha256=}
        ;;
      'date='*)
        meta_count_date=$((meta_count_date + 1))
        meta_date=${line#date=}
        ;;
      'approved_by='*)
        meta_count_owner=$((meta_count_owner + 1))
        meta_approved_by=${line#approved_by=}
        ;;
      *) alert metadata_attestation_malformed ;;
    esac
  done < "$META"

  [ "$meta_count_purpose" -eq 1 ] || alert metadata_attestation_malformed
  [ "$meta_count_base" -eq 1 ] || alert metadata_attestation_malformed
  [ "$meta_count_json" -eq 1 ] || alert metadata_attestation_malformed
  [ "$meta_count_seal" -eq 1 ] || alert metadata_attestation_malformed
  [ "$meta_count_date" -eq 1 ] || alert metadata_attestation_malformed
  [ "$meta_count_owner" -eq 1 ] || alert metadata_attestation_malformed

  [ "$meta_purpose" = "metadata-only hardening, no content change" ] || alert metadata_attestation_malformed
  [[ "$meta_base_commit" =~ ^[0-9A-Fa-f]{40}$ ]] || alert metadata_attestation_malformed
  [ "$meta_core_json_mode" = "0644" ] || alert metadata_attestation_malformed
  [ "$meta_seal_mode" = "0644" ] || alert metadata_attestation_malformed
  [[ "$meta_core_json_sha" =~ ^[0-9A-Fa-f]{64}$ ]] || alert metadata_attestation_malformed
  [[ "$meta_seal_sha" =~ ^[0-9A-Fa-f]{64}$ ]] || alert metadata_attestation_malformed
  [ -n "$meta_date" ] || alert metadata_attestation_malformed
  [ "$meta_approved_by" = "owner" ] || alert metadata_attestation_malformed

  /usr/bin/git -C "$ROOT" cat-file -e "${meta_base_commit}^{commit}" 2>/dev/null \
    || alert history_unavailable
  /usr/bin/git -C "$ROOT" merge-base --is-ancestor "$meta_base_commit" HEAD 2>/dev/null \
    || alert metadata_base_commit_mismatch

  meta_current_core_line=$(/usr/bin/sha256sum -- "$CORE_JSON") || alert core_hash_unavailable
  meta_current_core_sha=${meta_current_core_line%% *}
  meta_current_seal_line=$(/usr/bin/sha256sum -- "$SEAL") || alert core_hash_unavailable
  meta_current_seal_sha=${meta_current_seal_line%% *}

  [ "${meta_current_core_sha,,}" = "${meta_core_json_sha,,}" ] \
    || alert metadata_core_hash_mismatch
  [ "${meta_current_seal_sha,,}" = "${meta_seal_sha,,}" ] \
    || alert metadata_seal_hash_mismatch

  core_mode=$(/usr/bin/stat -c '%a' -- "$CORE_JSON") || alert trusted_permission_unavailable
  seal_mode=$(/usr/bin/stat -c '%a' -- "$SEAL") || alert trusted_permission_unavailable
  [ "$core_mode" = "644" ] || alert metadata_mode_mismatch
  [ "$seal_mode" = "644" ] || alert metadata_mode_mismatch

  /usr/bin/ssh-keygen -Y verify \
    -f "$SIGNERS" \
    -I owner \
    -n udnos-core \
    -s "$META_SIG" \
    < "$META" >/dev/null 2>&1 \
    || alert metadata_owner_signature_invalid
fi

printf 'DRAGON_OK core intact and owner-attested\n'
exit 0
