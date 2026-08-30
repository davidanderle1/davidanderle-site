#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

ROOT="$(pwd)"
LOCK="$ROOT/.github/r7f-v6-builder-input.json"
EVIDENCE="$ROOT/evidence"
ARTIFACT="$ROOT/artifact"
SUCCESS=0

stage_failure() {
  local status="$1"
  set +e
  mkdir -p "$ARTIFACT/R7F_EVIDENCE"
  [[ -f "$LOCK" ]] && cp "$LOCK" "$ARTIFACT/R7F_EVIDENCE/builder-input-lock-v6.json" 2>/dev/null || true
  [[ -f /tmp/r7f-v6-lock-preflight.json ]] && cp /tmp/r7f-v6-lock-preflight.json "$ARTIFACT/R7F_EVIDENCE/builder-input-lock-v6-gate.json" 2>/dev/null || true
  printf 'R7F V6 LOCKED VERIFICATION INCOMPLETE — R7 MUST REMAIN OPEN\n' > "$ARTIFACT/R7F_GATE_DECISION.txt"
  python3 - "$status" <<'PY' 2>/dev/null || true
import json,sys
from pathlib import Path
p=Path('artifact/R7F_PACKAGE_VALIDATION.json')
try: data=json.loads(p.read_text()) if p.exists() else {}
except Exception: data={}
data.update({'passed':False,'verificationVersion':'R7F-v6-fingerprint-bound-locked-v2','lockedExitStatus':int(sys.argv[1])})
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(json.dumps(data,indent=2)+'\n')
PY
  rm -f "$ARTIFACT/R7F_ARTIFACT_SHA256SUMS.txt"
  if [[ -d "$ARTIFACT" ]]; then
    (cd "$ARTIFACT" && find . -type f ! -name 'R7F_ARTIFACT_SHA256SUMS.txt' -print0 | sort -z | xargs -0 sha256sum > R7F_ARTIFACT_SHA256SUMS.txt && sha256sum --check --strict R7F_ARTIFACT_SHA256SUMS.txt) >/dev/null 2>&1 || true
  fi
}
trap 'status=$?; [[ "$SUCCESS" -eq 1 ]] || stage_failure "$status"; exit "$status"' EXIT

required_env=(GITHUB_REPOSITORY BUILDER_RUN_ID BUILDER_COMMIT BUILDER_ARTIFACT_ID BUILDER_ARTIFACT_NAME BUILDER_ARTIFACT_DIGEST BUILDER_SOURCE_ARCHIVE_SHA256 BUILDER_FINGERPRINT_INVENTORY_SHA256 BUILDER_FINGERPRINT_MULTISET_SHA256)
for name in "${required_env[@]}"; do
  [[ -n "${!name:-}" ]] || { echo "Missing $name" >&2; exit 2; }
done

test -f "$LOCK"
python3 - <<'PY'
import json,os
from pathlib import Path
lock=json.loads(Path('.github/r7f-v6-builder-input.json').read_text())
checks={
 'schema':lock.get('schema')=='R7F_BUILDER_INPUT_V3_FINGERPRINT_BOUND',
 'repository':lock.get('repository')==os.environ['GITHUB_REPOSITORY'],
 'builderRunId':str(lock.get('builderRunId'))==os.environ['BUILDER_RUN_ID'],
 'builderHeadSha':lock.get('builderHeadSha')==os.environ['BUILDER_COMMIT'],
 'builderArtifactId':str(lock.get('builderArtifactId'))==os.environ['BUILDER_ARTIFACT_ID'],
 'builderArtifactName':lock.get('builderArtifactName')==os.environ['BUILDER_ARTIFACT_NAME'],
 'builderArtifactDigest':lock.get('builderArtifactDigest')==os.environ['BUILDER_ARTIFACT_DIGEST'],
 'builderSourceArchiveSha256':lock.get('builderSourceArchiveSha256')==os.environ['BUILDER_SOURCE_ARCHIVE_SHA256'],
 'fingerprintInventory':lock.get('builderFingerprintInventorySha256')==os.environ['BUILDER_FINGERPRINT_INVENTORY_SHA256'],
 'fingerprintMultiset':lock.get('builderFingerprintMultisetSha256')==os.environ['BUILDER_FINGERPRINT_MULTISET_SHA256'],
 'builderFingerprintGate':(lock.get('builderFingerprintGate') or {}).get('passed') is True and (lock.get('builderFingerprintGate') or {}).get('blockers')==[],
 'hash-shape':all(isinstance(lock.get(name),str) and len(lock[name])==64 for name in ('builderSourceArchiveSha256','builderFingerprintInventorySha256','builderFingerprintMultisetSha256')),
}
result={'gate':'R7F_V6_IMMUTABLE_FINGERPRINT_BOUND_INPUT_LOCK_V2','passed':all(checks.values()),'checks':checks,'failedChecks':[k for k,v in checks.items() if not v],'lock':lock}
Path('/tmp/r7f-v6-lock-preflight.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
if not result['passed']: raise SystemExit(1)
PY
sha256sum "$LOCK" "$ROOT/.github/scripts/r7f-v6-locked-v2.sh" > /tmp/r7f-v6-lock-infrastructure.sha256
bash "$ROOT/.github/scripts/r7f-v6.sh"

cp "$LOCK" "$EVIDENCE/builder-input-lock-v6.json"
cp /tmp/r7f-v6-lock-preflight.json "$EVIDENCE/builder-input-lock-v6-gate.json"
cp /tmp/r7f-v6-lock-infrastructure.sha256 "$EVIDENCE/verifier-v6-lock-infrastructure.sha256"
cp "$EVIDENCE/builder-input-lock-v6.json" "$ARTIFACT/R7F_EVIDENCE/"
cp "$EVIDENCE/builder-input-lock-v6-gate.json" "$ARTIFACT/R7F_EVIDENCE/"
cp "$EVIDENCE/verifier-v6-lock-infrastructure.sha256" "$ARTIFACT/R7F_EVIDENCE/"
rm -f "$ARTIFACT/R7F_ARTIFACT_SHA256SUMS.txt"

python3 - <<'PY'
import json
from pathlib import Path
root=Path('artifact')
p=root/'R7F_PACKAGE_VALIDATION.json'
data=json.loads(p.read_text())
lock=json.loads((root/'R7F_EVIDENCE/builder-input-lock-v6.json').read_text())
gate=json.loads((root/'R7F_EVIDENCE/builder-input-lock-v6-gate.json').read_text())
builder_audit=json.loads((root/'R7F_EVIDENCE/independent-builder-axe-fingerprint-audit.json').read_text())
checks=dict(data.get('checks') or {})
checks.update({
 'immutable-fingerprint-bound-input-lock':gate.get('passed') is True,
 'locked-builder-run':str(lock.get('builderRunId'))==str(data.get('builderRunId')),
 'locked-builder-commit':lock.get('builderHeadSha')==data.get('builderCommit'),
 'locked-builder-artifact-id':str(lock.get('builderArtifactId'))==str(data.get('builderArtifactId')),
 'locked-builder-artifact-name':lock.get('builderArtifactName')==data.get('builderArtifactName'),
 'locked-builder-artifact-digest':lock.get('builderArtifactDigest')==data.get('builderArtifactDigest'),
 'locked-source-archive':lock.get('builderSourceArchiveSha256')==data.get('builderSourceArchiveSha256'),
 'locked-fingerprint-inventory':lock.get('builderFingerprintInventorySha256')==(builder_audit.get('builderInventory') or {}).get('inventorySha256'),
 'locked-fingerprint-multiset':lock.get('builderFingerprintMultisetSha256')==(data.get('axeFingerprintEvidence') or {}).get('fingerprintMultisetSha256'),
 'v6-lock-infrastructure':(root/'R7F_EVIDENCE/verifier-v6-lock-infrastructure.sha256').is_file(),
})
data.update({'passed':all(checks.values()),'verificationVersion':'R7F-v6-fingerprint-bound-locked-v2','checks':checks,'failedChecks':[name for name,passed in checks.items() if not passed],'builderInputLock':lock})
p.write_text(json.dumps(data,indent=2)+'\n')
index_path=root/'R7F_EVIDENCE_INDEX.json'
index=json.loads(index_path.read_text()) if index_path.exists() else {}
index.update({'builderInputLockV6':'R7F_EVIDENCE/builder-input-lock-v6.json','builderInputLockV6Gate':'R7F_EVIDENCE/builder-input-lock-v6-gate.json','v6LockInfrastructure':'R7F_EVIDENCE/verifier-v6-lock-infrastructure.sha256'})
index_path.write_text(json.dumps(index,indent=2)+'\n')
print(json.dumps(data,indent=2))
if not data['passed']: raise SystemExit(1)
PY

(
  cd "$ARTIFACT"
  find . -type f ! -name 'R7F_ARTIFACT_SHA256SUMS.txt' -print0 | sort -z | xargs -0 sha256sum > R7F_ARTIFACT_SHA256SUMS.txt
  sha256sum --check --strict R7F_ARTIFACT_SHA256SUMS.txt
)

SUCCESS=1
trap - EXIT
printf 'R7F v6 locked fingerprint-bound verification completed successfully.\n'
