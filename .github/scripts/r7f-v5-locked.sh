#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

ROOT="$(pwd)"
LOCK="$ROOT/.github/r7f-v5-builder-input.json"
EVIDENCE="$ROOT/evidence"
ARTIFACT="$ROOT/artifact"
LOCKED_SUCCESS=0

stage_locked_failure() {
  local status="$1"
  set +e
  mkdir -p "$ARTIFACT/R7F_EVIDENCE"
  [[ -f "$LOCK" ]] && cp "$LOCK" "$ARTIFACT/R7F_EVIDENCE/builder-input-lock.json" 2>/dev/null || true
  [[ -f /tmp/r7f-v5-lock-preflight.json ]] && cp /tmp/r7f-v5-lock-preflight.json "$ARTIFACT/R7F_EVIDENCE/builder-input-lock-gate.json" 2>/dev/null || true
  printf 'R7F V5 LOCKED VERIFICATION INCOMPLETE — R7 MUST REMAIN OPEN\n' > "$ARTIFACT/R7F_GATE_DECISION.txt"
  python3 - "$status" <<'PY' 2>/dev/null || true
import json, sys
from pathlib import Path
path=Path('artifact/R7F_PACKAGE_VALIDATION.json')
try: data=json.loads(path.read_text()) if path.exists() else {}
except Exception: data={}
data.update({'passed':False,'verificationVersion':'R7F-v5-locked','lockedExitStatus':int(sys.argv[1]),'lockedFailure':'Immutable builder input lock validation or locked verifier execution did not complete.'})
path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps(data,indent=2)+'\n')
PY
  rm -f "$ARTIFACT/R7F_ARTIFACT_SHA256SUMS.txt"
  if [[ -d "$ARTIFACT" ]]; then
    (cd "$ARTIFACT" && find . -type f ! -name 'R7F_ARTIFACT_SHA256SUMS.txt' -print0 | sort -z | xargs -0 sha256sum > R7F_ARTIFACT_SHA256SUMS.txt && sha256sum --check --strict R7F_ARTIFACT_SHA256SUMS.txt) >/dev/null 2>&1 || true
  fi
}

on_exit() {
  local status=$?
  if [[ "$LOCKED_SUCCESS" -ne 1 ]]; then stage_locked_failure "$status"; fi
  exit "$status"
}
trap on_exit EXIT

required_env=(GITHUB_REPOSITORY BUILDER_RUN_ID BUILDER_COMMIT BUILDER_ARTIFACT_ID BUILDER_ARTIFACT_NAME BUILDER_ARTIFACT_DIGEST BUILDER_SOURCE_ARCHIVE_SHA256)
for name in "${required_env[@]}"; do
  [[ -n "${!name:-}" ]] || { echo "Missing required environment variable: $name" >&2; exit 2; }
done

test -f "$LOCK"
bash -n "$ROOT/.github/scripts/r7f-v5-locked.sh"
sha256sum "$LOCK" "$ROOT/.github/scripts/r7f-v5-locked.sh" > /tmp/r7f-v5-lock-infrastructure.sha256
python3 - <<'PY'
import json, os
from pathlib import Path
lock=json.loads(Path('.github/r7f-v5-builder-input.json').read_text())
checks={
  'schema':lock.get('schema')=='R7F_BUILDER_INPUT_V2',
  'repository':lock.get('repository')==os.environ['GITHUB_REPOSITORY'],
  'builderRunId':str(lock.get('builderRunId'))==os.environ['BUILDER_RUN_ID'],
  'builderHeadSha':lock.get('builderHeadSha')==os.environ['BUILDER_COMMIT'],
  'builderArtifactId':str(lock.get('builderArtifactId'))==os.environ['BUILDER_ARTIFACT_ID'],
  'builderArtifactName':lock.get('builderArtifactName')==os.environ['BUILDER_ARTIFACT_NAME'],
  'builderArtifactDigest':lock.get('builderArtifactDigest')==os.environ['BUILDER_ARTIFACT_DIGEST'],
  'builderSourceArchiveSha256':lock.get('builderSourceArchiveSha256')==os.environ['BUILDER_SOURCE_ARCHIVE_SHA256'],
  'externalAuditPassed':(lock.get('externalR7eAudit') or {}).get('passed') is True and (lock.get('externalR7eAudit') or {}).get('decision')=='R7E_EXTERNAL_AUDIT_PASS' and (lock.get('externalR7eAudit') or {}).get('blockers')==[],
  'externalAuditDigest':(lock.get('externalR7eAudit') or {}).get('auditSha256')=='9ff467f9982f83674b1849e1dcf19052bfb3793dcd113774c72274af9081e6dd',
  'treeHashes':all(isinstance(lock.get(name),str) and len(lock[name])==64 for name in ('builderFrozenSourceTreeSha256','builderVerifiedDistTreeSha256','builderStressDistTreeSha256')),
}
result={'gate':'R7F_V5_IMMUTABLE_BUILDER_INPUT_LOCK','passed':all(checks.values()),'checks':checks,'failedChecks':[k for k,v in checks.items() if not v],'lock':lock}
Path('/tmp/r7f-v5-lock-preflight.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
if not result['passed']: raise SystemExit(1)
PY

bash "$ROOT/.github/scripts/r7f-v5.sh"

cp "$LOCK" "$EVIDENCE/builder-input-lock.json"
cp /tmp/r7f-v5-lock-preflight.json "$EVIDENCE/builder-input-lock-gate.json"
cp /tmp/r7f-v5-lock-infrastructure.sha256 "$EVIDENCE/verifier-v5-lock-infrastructure.sha256"
cp "$EVIDENCE/builder-input-lock.json" "$ARTIFACT/R7F_EVIDENCE/"
cp "$EVIDENCE/builder-input-lock-gate.json" "$ARTIFACT/R7F_EVIDENCE/"
cp "$EVIDENCE/verifier-v5-lock-infrastructure.sha256" "$ARTIFACT/R7F_EVIDENCE/"
rm -f "$ARTIFACT/R7F_ARTIFACT_SHA256SUMS.txt"

python3 - <<'PY'
import json
from pathlib import Path
root=Path('artifact')
validation_path=root/'R7F_PACKAGE_VALIDATION.json'
data=json.loads(validation_path.read_text())
lock=json.loads((root/'R7F_EVIDENCE/builder-input-lock.json').read_text())
gate=json.loads((root/'R7F_EVIDENCE/builder-input-lock-gate.json').read_text())
checks=dict(data.get('checks') or {})
checks.update({
  'immutable-builder-input-lock':gate.get('passed') is True,
  'locked-builder-run':str(lock.get('builderRunId'))==str(data.get('builderRunId')),
  'locked-builder-commit':lock.get('builderHeadSha')==data.get('builderCommit'),
  'locked-builder-artifact-id':str(lock.get('builderArtifactId'))==str(data.get('builderArtifactId')),
  'locked-builder-artifact-name':lock.get('builderArtifactName')==data.get('builderArtifactName'),
  'locked-builder-artifact-digest':lock.get('builderArtifactDigest')==data.get('builderArtifactDigest'),
  'locked-builder-source-archive':lock.get('builderSourceArchiveSha256')==data.get('builderSourceArchiveSha256'),
  'external-r7e-audit-pass':(lock.get('externalR7eAudit') or {}).get('passed') is True and (lock.get('externalR7eAudit') or {}).get('blockers')==[],
  'lock-infrastructure-manifest':(root/'R7F_EVIDENCE/verifier-v5-lock-infrastructure.sha256').is_file(),
})
data.update({'passed':all(checks.values()),'verificationVersion':'R7F-v5-locked','checks':checks,'failedChecks':[name for name,passed in checks.items() if not passed],'builderInputLock':lock})
validation_path.write_text(json.dumps(data,indent=2)+'\n')
index_path=root/'R7F_EVIDENCE_INDEX.json'
index=json.loads(index_path.read_text()) if index_path.exists() else {}
index.update({'builderInputLock':'R7F_EVIDENCE/builder-input-lock.json','builderInputLockGate':'R7F_EVIDENCE/builder-input-lock-gate.json','lockInfrastructureManifest':'R7F_EVIDENCE/verifier-v5-lock-infrastructure.sha256'})
index_path.write_text(json.dumps(index,indent=2)+'\n')
print(json.dumps(data,indent=2))
if not data['passed']: raise SystemExit(1)
PY

(
  cd "$ARTIFACT"
  find . -type f ! -name 'R7F_ARTIFACT_SHA256SUMS.txt' -print0 | sort -z | xargs -0 sha256sum > R7F_ARTIFACT_SHA256SUMS.txt
  sha256sum --check --strict R7F_ARTIFACT_SHA256SUMS.txt
)

LOCKED_SUCCESS=1
trap - EXIT
printf 'R7F v5 locked verification completed successfully.\n'
