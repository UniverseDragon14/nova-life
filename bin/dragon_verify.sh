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
ATTEST_SIG="$CORE_DIR/ATTESTATION.txt.sig"
META="$CORE_DIR/ATTESTATION_METADATA_v1.txt"
META_SIG="$CORE_DIR/ATTESTATION_METADATA_v1.txt.sig"
ROT="$CORE_DIR/ATTESTATION_KEY_ROTATION_v1.txt"
ROT_SIG="$CORE_DIR/ATTESTATION_KEY_ROTATION_v1.txt.sig"
SIGNERS="$CORE_DIR/allowed_signers"
RECOVERY_SIGNERS="$CORE_DIR/recovery_allowed_signers"
HIST_SIGNERS="$CORE_DIR/historical_allowed_signers"
HIST_MANIFEST="$CORE_DIR/historical_attestations_v1.txt"

EXPECTED_ROT_SHA="d5d014e49172323cf54c023e301fa1df71644ea21f52b5b8cb9afe2c3622512c"
EXPECTED_ROT_SIG_SHA="d91fe5f559bf5576e60bbe093ed9908134001caabf9d95a3f4328c4df1b23ed6"
EXPECTED_SIGNERS_SHA="d9a068053469f5394b9352ff226b5ec0817d86ec535433dcee32d0da24bdef95"
EXPECTED_RECOVERY_SHA="b8255e5d65a56448d22707fc21e9781786b097e5c0eb0debdfce2587240e07d2"
EXPECTED_HIST_SIGNERS_SHA="2252a17f6662dc094dc231d6ed06bce4e1f32379ccbcee89ab8486daf50840d5"
EXPECTED_HIST_MANIFEST_SHA="9e9fce76055d178d3470b878d446958bd51c7f4247bd5113a0ffbaae317fe921"
EXPECTED_ATTEST_SHA="76f11058b6074197a424e4b983926b4fe887e566e8fbb68730e8e8b96b485a6c"
EXPECTED_ATTEST_SIG_SHA="811ce7647985300af171d6fbb99037de1e20931e685e9c259090b456a786b6db"
EXPECTED_META_SHA="d87b2d6b8a8dc643d6732607bea3829c7971f3e5b8d583840f2a472a306f04c0"
EXPECTED_META_SIG_SHA="a3c51d5c1b41a070d5579d03889269070ea7f201d31f7795e34f001a862b8879"
sha_of() {
  local line
  line=$(/usr/bin/sha256sum -- "$1") || alert hash_unavailable
  printf '%s\n' "${line%% *}"
}

check_trusted_file() {
  local f="$1" expected="$2" real mode perm
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
  [ "$mode" = "644" ] || alert trusted_file_mode
}

for f in "$CORE_JSON" "$SEAL" "$ATTEST" "$ATTEST_SIG" "$META" "$META_SIG" \
         "$ROT" "$ROT_SIG" "$SIGNERS" "$RECOVERY_SIGNERS" "$HIST_SIGNERS" "$HIST_MANIFEST"; do
  check_trusted_file "$f" "$f"
done
[ "$(sha_of "$ROT")" = "$EXPECTED_ROT_SHA" ] || alert rotation_attestation_hash_mismatch
[ "$(sha_of "$ROT_SIG")" = "$EXPECTED_ROT_SIG_SHA" ] || alert rotation_signature_hash_mismatch
[ "$(sha_of "$SIGNERS")" = "$EXPECTED_SIGNERS_SHA" ] || alert current_signers_hash_mismatch
[ "$(sha_of "$RECOVERY_SIGNERS")" = "$EXPECTED_RECOVERY_SHA" ] || alert recovery_signers_hash_mismatch
[ "$(sha_of "$HIST_SIGNERS")" = "$EXPECTED_HIST_SIGNERS_SHA" ] || alert historical_signers_hash_mismatch
[ "$(sha_of "$HIST_MANIFEST")" = "$EXPECTED_HIST_MANIFEST_SHA" ] || alert historical_manifest_hash_mismatch
[ "$(sha_of "$ATTEST")" = "$EXPECTED_ATTEST_SHA" ] || alert historical_attestation_hash_mismatch
[ "$(sha_of "$ATTEST_SIG")" = "$EXPECTED_ATTEST_SIG_SHA" ] || alert historical_attestation_signature_hash_mismatch
[ "$(sha_of "$META")" = "$EXPECTED_META_SHA" ] || alert historical_metadata_hash_mismatch
[ "$(sha_of "$META_SIG")" = "$EXPECTED_META_SIG_SHA" ] || alert historical_metadata_signature_hash_mismatch

[ "$(/usr/bin/wc -l < "$SIGNERS")" -eq 1 ] || alert current_signers_format
[ "$(/usr/bin/wc -l < "$RECOVERY_SIGNERS")" -eq 1 ] || alert recovery_signers_format
[ "$(/usr/bin/wc -l < "$HIST_SIGNERS")" -eq 1 ] || alert historical_signers_format
/usr/bin/grep -Eq '^owner namespaces="udnos-core" ssh-ed25519 [A-Za-z0-9+/=]+$' "$SIGNERS" || alert current_signers_format
/usr/bin/grep -Eq '^owner-recovery namespaces="udnos-recovery" ssh-ed25519 [A-Za-z0-9+/=]+$' "$RECOVERY_SIGNERS" || alert recovery_signers_format
/usr/bin/grep -Eq '^retired-owner-v1 namespaces="udnos-core" ssh-ed25519 [A-Za-z0-9+/=]+$' "$HIST_SIGNERS" || alert historical_signers_format
require_line() {
  /usr/bin/grep -Fqx -- "$2" "$1" || alert "$3"
}

require_line "$ROT" "base_commit=dff5e6f9481a4434e5ad58cd2a56a343e7e13c94" rotation_attestation_malformed
require_line "$ROT" "new_allowed_signers_sha256=$EXPECTED_SIGNERS_SHA" rotation_attestation_malformed
require_line "$ROT" "new_recovery_allowed_signers_sha256=$EXPECTED_RECOVERY_SHA" rotation_attestation_malformed
require_line "$ROT" "historical_allowed_signers_sha256=$EXPECTED_HIST_SIGNERS_SHA" rotation_attestation_malformed
require_line "$ROT" "historical_attestations_manifest_sha256=$EXPECTED_HIST_MANIFEST_SHA" rotation_attestation_malformed
require_line "$ROT" "routine_principal=owner" rotation_attestation_malformed
require_line "$ROT" "routine_namespace=udnos-core" rotation_attestation_malformed
require_line "$ROT" "recovery_principal=owner-recovery" rotation_attestation_malformed
require_line "$ROT" "recovery_namespace=udnos-recovery" rotation_attestation_malformed
require_line "$ROT" "approved_by=owner" rotation_attestation_malformed

require_line "$HIST_MANIFEST" "retired_principal=retired-owner-v1" historical_manifest_malformed
require_line "$HIST_MANIFEST" "namespace=udnos-core" historical_manifest_malformed
require_line "$HIST_MANIFEST" "entry=core/ATTESTATION.txt attestation_sha256=$EXPECTED_ATTEST_SHA signature_sha256=$EXPECTED_ATTEST_SIG_SHA source_commit=321a2ad27aa06a01c7885338688e695a06b2cf84" historical_manifest_malformed
require_line "$HIST_MANIFEST" "entry=core/ATTESTATION_METADATA_v1.txt attestation_sha256=$EXPECTED_META_SHA signature_sha256=$EXPECTED_META_SIG_SHA source_commit=dff5e6f9481a4434e5ad58cd2a56a343e7e13c94" historical_manifest_malformed
(
  cd "$ROOT"
  /usr/bin/sha256sum -c core/nova.core.sha256 --status
) || alert core_hash_mismatch

core_commit=$(/usr/bin/awk -F': ' '$1=="core_commit"{print $2}' "$ATTEST")
core_sha=$(/usr/bin/awk -F': ' '$1=="core_sha256"{print $2}' "$ATTEST")
[ "$(/usr/bin/grep -c '^core_commit: ' "$ATTEST")" -eq 1 ] || alert attestation_malformed
[ "$(/usr/bin/grep -c '^core_sha256: ' "$ATTEST")" -eq 1 ] || alert attestation_malformed
[[ "$core_commit" =~ ^[0-9A-Fa-f]{40}$ ]] || alert attestation_malformed
[[ "$core_sha" =~ ^[0-9A-Fa-f]{64}$ ]] || alert attestation_malformed
[ "$(sha_of "$CORE_JSON")" = "${core_sha,,}" ] || alert owner_attestation_core_mismatch

/usr/bin/git -C "$ROOT" cat-file -e "${core_commit}^{commit}" 2>/dev/null || alert history_unavailable
/usr/bin/git -C "$ROOT" cat-file -e "${core_commit}:core/nova.core.json" 2>/dev/null || alert attested_commit_mismatch
blob_sha=$(/usr/bin/git -C "$ROOT" show "${core_commit}:core/nova.core.json" 2>/dev/null | /usr/bin/sha256sum | /usr/bin/awk '{print $1}') || alert history_unavailable
[ "$blob_sha" = "${core_sha,,}" ] || alert attested_commit_mismatch

meta_base=$(/usr/bin/awk -F= '$1=="base_commit"{print $2}' "$META")
[ "$(/usr/bin/grep -c '^base_commit=' "$META")" -eq 1 ] || alert metadata_attestation_malformed
[[ "$meta_base" =~ ^[0-9A-Fa-f]{40}$ ]] || alert metadata_attestation_malformed
require_line "$META" "file=core/nova.core.json mode=0644 sha256=$(sha_of "$CORE_JSON")" metadata_core_hash_mismatch
require_line "$META" "file=core/nova.core.sha256 mode=0644 sha256=$(sha_of "$SEAL")" metadata_seal_hash_mismatch
/usr/bin/git -C "$ROOT" cat-file -e "${meta_base}^{commit}" 2>/dev/null || alert history_unavailable
/usr/bin/git -C "$ROOT" merge-base --is-ancestor "$meta_base" HEAD 2>/dev/null || alert metadata_base_commit_mismatch
/usr/bin/git -C "$ROOT" cat-file -e "dff5e6f9481a4434e5ad58cd2a56a343e7e13c94^{commit}" 2>/dev/null || alert history_unavailable
/usr/bin/git -C "$ROOT" merge-base --is-ancestor dff5e6f9481a4434e5ad58cd2a56a343e7e13c94 HEAD 2>/dev/null || alert rotation_base_commit_mismatch

hist_blob_sha=$(/usr/bin/git -C "$ROOT" show 321a2ad27aa06a01c7885338688e695a06b2cf84:core/ATTESTATION.txt 2>/dev/null | /usr/bin/sha256sum | /usr/bin/awk '{print $1}') || alert history_unavailable
[ "$hist_blob_sha" = "$EXPECTED_ATTEST_SHA" ] || alert historical_source_mismatch
hist_sig_sha=$(/usr/bin/git -C "$ROOT" show 321a2ad27aa06a01c7885338688e695a06b2cf84:core/ATTESTATION.txt.sig 2>/dev/null | /usr/bin/sha256sum | /usr/bin/awk '{print $1}') || alert history_unavailable
[ "$hist_sig_sha" = "$EXPECTED_ATTEST_SIG_SHA" ] || alert historical_source_mismatch
meta_blob_sha=$(/usr/bin/git -C "$ROOT" show dff5e6f9481a4434e5ad58cd2a56a343e7e13c94:core/ATTESTATION_METADATA_v1.txt 2>/dev/null | /usr/bin/sha256sum | /usr/bin/awk '{print $1}') || alert history_unavailable
[ "$meta_blob_sha" = "$EXPECTED_META_SHA" ] || alert historical_source_mismatch
meta_sig_sha=$(/usr/bin/git -C "$ROOT" show dff5e6f9481a4434e5ad58cd2a56a343e7e13c94:core/ATTESTATION_METADATA_v1.txt.sig 2>/dev/null | /usr/bin/sha256sum | /usr/bin/awk '{print $1}') || alert history_unavailable
[ "$meta_sig_sha" = "$EXPECTED_META_SIG_SHA" ] || alert historical_source_mismatch
/usr/bin/ssh-keygen -Y verify   -f "$HIST_SIGNERS" -I retired-owner-v1 -n udnos-core   -s "$ATTEST_SIG" < "$ATTEST" >/dev/null 2>&1   || alert historical_attestation_signature_invalid

/usr/bin/ssh-keygen -Y verify   -f "$HIST_SIGNERS" -I retired-owner-v1 -n udnos-core   -s "$META_SIG" < "$META" >/dev/null 2>&1   || alert historical_metadata_signature_invalid

/usr/bin/ssh-keygen -Y verify   -f "$HIST_SIGNERS" -I retired-owner-v1 -n udnos-core   -s "$ROT_SIG" < "$ROT" >/dev/null 2>&1   || alert rotation_owner_signature_invalid

for candidate in "$CORE_DIR"/ATTESTATION_*.txt; do
  [ -e "$candidate" ] || continue
  case "$candidate" in
    "$META"|"$ROT") continue ;;
  esac
  candidate_sig="$candidate.sig"
  [ -f "$candidate_sig" ] || continue
  if /usr/bin/ssh-keygen -Y verify       -f "$HIST_SIGNERS" -I retired-owner-v1 -n udnos-core       -s "$candidate_sig" < "$candidate" >/dev/null 2>&1; then
    alert retired_key_not_allowlisted
  fi
done

printf 'DRAGON_OK core intact and owner-attested\n'
exit 0
