#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

ROOT="$(pwd)"
LOCK="$ROOT/.github/r7f-v6-builder-input.json"
EXTERNAL_AUDIT="$ROOT/.github/r7f-v6-r7e-external-audit.json"
EVIDENCE="$ROOT/evidence"
ARTIFACT="$ROOT/artifact"
LOCKED_SUCCESS=0

stage_locked_failure() {
  local status="$1"
  set +e
  mkdir -p "$ARTIFACT/R7F_EVIDENCE"
  [[ -f "$LOCK" ]] && cp "$LOCK" "$ARTIFACT/R7F_EVIDENCE/builder-input-lock-v6.json" 2>/dev/null || true
  [[ -f "$EXTERNAL_AUDIT" ]] && cp "$EXTERNAL_AUDIT" "$ARTIFACT/R7F_EVIDENCE/r7e-external-fingerprint-audit.json" 2>/dev/null || true
  [[ -f /tmp/r7f-v6-lock-preflight.json ]] && cp /tmp/r7f-v6-lock-preflight.json "$ARTIFACT/R7F_EVIDENCE/builder-input-lock-v6-gate.json" 2>/dev/null || true
  printf 'R7F V6 LOCKED EXACT FINGERPRINT VERIFICATION INCOMPLETE — R7 MUST REMAIN OPEN\n' > "$ARTIFACT/R7F_GATE_DECISION.txt"
  python3 - "$status" <<'PY' 2>/dev/null || true
import json,sys
from pathlib import Path
p=Path('artifact/R7F_PACKAGE_VALIDATION.json')
try: data=json.loads(p.read_text()) if p.exists() else {}
except Exception: data={}
data.update({'passed':False,'verificationVersion':'R7F-v6-exact-fingerprint-bound-locked','lockedExitStatus':int(sys.argv[1])})
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(json.dumps(data,indent=2)+'\n')
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

required_env=(
  GITHUB_REPOSITORY GITHUB_SHA GITHUB_RUN_ID GITHUB_RUN_ATTEMPT GH_TOKEN
  BUILDER_BRANCH BUILDER_WORKFLOW_PATH BUILDER_RUN_ID BUILDER_COMMIT
  BUILDER_ARTIFACT_ID BUILDER_ARTIFACT_NAME BUILDER_ARTIFACT_DIGEST
  BUILDER_SOURCE_ARCHIVE_SHA256 BUILDER_FROZEN_SOURCE_TREE_SHA256
  BUILDER_FROZEN_SOURCE_TAR_SHA256 BUILDER_VERIFIED_DIST_TREE_SHA256
  BUILDER_STRESS_DIST_TREE_SHA256 BUILDER_AXE_ADJUDICATION_FILE_SHA256
  BUILDER_AXE_SEMANTIC_INVENTORY_SHA256 BUILDER_AXE_NODE_SET_SHA256
  BUILDER_AXE_BINDING_SET_SHA256 R7E_EXTERNAL_AUDIT_SHA256
)
for name in "${required_env[@]}"; do
  [[ -n "${!name:-}" ]] || { echo "Missing required environment variable: $name" >&2; exit 2; }
done

test -f "$LOCK"
test -f "$EXTERNAL_AUDIT"
bash -n "$ROOT/.github/scripts/r7f-v6-final.sh"
bash -n "$ROOT/.github/scripts/r7f-v6-final-locked.sh"
python3 -m py_compile "$ROOT/.github/scripts/r7f-independent-axe-fingerprint-audit-v2.py"

python3 - <<'PY'
import hashlib,json,os
from pathlib import Path
lock_path=Path('.github/r7f-v6-builder-input.json')
audit_path=Path('.github/r7f-v6-r7e-external-audit.json')
lock=json.loads(lock_path.read_text())
audit=json.loads(audit_path.read_text())
audit_sha=hashlib.sha256(audit_path.read_bytes()).hexdigest()
checks={
 'schema':lock.get('schema')=='R7F_BUILDER_INPUT_V4_EXACT_FINGERPRINT_BOUND',
 'repository':lock.get('repository')==os.environ['GITHUB_REPOSITORY'],
 'builderBranch':lock.get('builderBranch')==os.environ['BUILDER_BRANCH'],
 'builderWorkflowPath':lock.get('builderWorkflowPath')==os.environ['BUILDER_WORKFLOW_PATH'],
 'builderRunId':str(lock.get('builderRunId'))==os.environ['BUILDER_RUN_ID'],
 'builderHeadSha':lock.get('builderHeadSha')==os.environ['BUILDER_COMMIT'],
 'builderArtifactId':str(lock.get('builderArtifactId'))==os.environ['BUILDER_ARTIFACT_ID'],
 'builderArtifactName':lock.get('builderArtifactName')==os.environ['BUILDER_ARTIFACT_NAME'],
 'builderArtifactDigest':lock.get('builderArtifactDigest')==os.environ['BUILDER_ARTIFACT_DIGEST'],
 'sourceArchive':lock.get('builderSourceArchiveSha256')==os.environ['BUILDER_SOURCE_ARCHIVE_SHA256'],
 'sourceTree':lock.get('builderFrozenSourceTreeSha256')==os.environ['BUILDER_FROZEN_SOURCE_TREE_SHA256'],
 'sourceTar':lock.get('builderFrozenSourceTarSha256')==os.environ['BUILDER_FROZEN_SOURCE_TAR_SHA256'],
 'distTree':lock.get('builderVerifiedDistTreeSha256')==os.environ['BUILDER_VERIFIED_DIST_TREE_SHA256'],
 'stressTree':lock.get('builderStressDistTreeSha256')==os.environ['BUILDER_STRESS_DIST_TREE_SHA256'],
 'inventoryFile':lock.get('builderAxeAdjudicationFileSha256')==os.environ['BUILDER_AXE_ADJUDICATION_FILE_SHA256'],
 'semanticInventory':lock.get('builderAxeSemanticInventorySha256')==os.environ['BUILDER_AXE_SEMANTIC_INVENTORY_SHA256'],
 'nodeSet':lock.get('builderAxeNodeFingerprintSetSha256')==os.environ['BUILDER_AXE_NODE_SET_SHA256'],
 'bindingSet':lock.get('builderAxeBindingFingerprintSetSha256')==os.environ['BUILDER_AXE_BINDING_SET_SHA256'],
 'externalAuditSha':lock.get('r7eExternalAuditSha256')==os.environ['R7E_EXTERNAL_AUDIT_SHA256']==audit_sha,
 'externalAuditPassed':audit.get('passed') is True and audit.get('decision')=='R7E_EXTERNAL_FINGERPRINT_AUDIT_PASS' and audit.get('blockers')==[],
 'externalAuditTuple':str((audit.get('builder') or {}).get('runId'))==os.environ['BUILDER_RUN_ID'] and str((audit.get('builder') or {}).get('artifactId'))==os.environ['BUILDER_ARTIFACT_ID'] and (audit.get('builder') or {}).get('headSha')==os.environ['BUILDER_COMMIT'] and (audit.get('builder') or {}).get('artifactDigest')==os.environ['BUILDER_ARTIFACT_DIGEST'],
 'hashShapes':all(isinstance(lock.get(name),str) and len(lock[name])==64 for name in (
   'builderSourceArchiveSha256','builderFrozenSourceTreeSha256','builderFrozenSourceTarSha256',
   'builderVerifiedDistTreeSha256','builderStressDistTreeSha256','builderAxeAdjudicationFileSha256',
   'builderAxeSemanticInventorySha256','builderAxeNodeFingerprintSetSha256',
   'builderAxeBindingFingerprintSetSha256','r7eExternalAuditSha256')),
}
result={'gate':'R7F_V6_IMMUTABLE_EXACT_FINGERPRINT_INPUT_LOCK','passed':all(checks.values()),'checks':checks,'failedChecks':[k for k,v in checks.items() if not v],'lock':lock,'externalAuditSha256':audit_sha}
Path('/tmp/r7f-v6-lock-preflight.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
if not result['passed']: raise SystemExit(1)
PY

# Authenticate the current branch head, workflow run, artifact metadata and
# transferred ZIP before the broader verifier downloads candidate bytes.
test "$(gh api "repos/${GITHUB_REPOSITORY}/branches/${BUILDER_BRANCH}" --jq '.commit.sha')" = "$BUILDER_COMMIT"
gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${BUILDER_RUN_ID}" > /tmp/r7f-v6-builder-run.json
jq -e --arg head "$BUILDER_COMMIT" --arg branch "$BUILDER_BRANCH" --arg path "$BUILDER_WORKFLOW_PATH" \
  '.head_sha==$head and .head_branch==$branch and .path==$path and .status=="completed" and .conclusion=="success"' \
  /tmp/r7f-v6-builder-run.json >/dev/null
gh api "repos/${GITHUB_REPOSITORY}/actions/artifacts/${BUILDER_ARTIFACT_ID}" > /tmp/r7f-v6-builder-artifact.json
jq -e --argjson id "$BUILDER_ARTIFACT_ID" --arg name "$BUILDER_ARTIFACT_NAME" --arg digest "$BUILDER_ARTIFACT_DIGEST" --argjson run "$BUILDER_RUN_ID" \
  '.id==$id and .name==$name and .digest==$digest and .expired==false and .workflow_run.id==$run' \
  /tmp/r7f-v6-builder-artifact.json >/dev/null
curl --fail --silent --show-error --location \
  -H "Authorization: Bearer ${GH_TOKEN}" \
  -H 'Accept: application/vnd.github+json' \
  "https://api.github.com/repos/${GITHUB_REPOSITORY}/actions/artifacts/${BUILDER_ARTIFACT_ID}/zip" \
  --output /tmp/r7f-v6-builder-transfer.zip
test "sha256:$(sha256sum /tmp/r7f-v6-builder-transfer.zip | awk '{print $1}')" = "$BUILDER_ARTIFACT_DIGEST"

sha256sum \
  "$LOCK" \
  "$EXTERNAL_AUDIT" \
  "$ROOT/.github/scripts/r7f-v6-final.sh" \
  "$ROOT/.github/scripts/r7f-v6-final-locked.sh" \
  "$ROOT/.github/scripts/r7f-independent-axe-fingerprint-audit-v2.py" \
  > /tmp/r7f-v6-lock-infrastructure.sha256

bash "$ROOT/.github/scripts/r7f-v6-final.sh"

cp "$LOCK" "$EVIDENCE/builder-input-lock-v6.json"
cp "$EXTERNAL_AUDIT" "$EVIDENCE/r7e-external-fingerprint-audit.json"
cp /tmp/r7f-v6-lock-preflight.json "$EVIDENCE/builder-input-lock-v6-gate.json"
cp /tmp/r7f-v6-builder-run.json "$EVIDENCE/builder-run-metadata-lock.json"
cp /tmp/r7f-v6-builder-artifact.json "$EVIDENCE/builder-artifact-metadata-lock.json"
cp /tmp/r7f-v6-lock-infrastructure.sha256 "$EVIDENCE/verifier-v6-lock-infrastructure.sha256"
cp "$EVIDENCE/builder-input-lock-v6.json" "$ARTIFACT/R7F_EVIDENCE/"
cp "$EVIDENCE/r7e-external-fingerprint-audit.json" "$ARTIFACT/R7F_EVIDENCE/"
cp "$EVIDENCE/builder-input-lock-v6-gate.json" "$ARTIFACT/R7F_EVIDENCE/"
cp "$EVIDENCE/builder-run-metadata-lock.json" "$ARTIFACT/R7F_EVIDENCE/"
cp "$EVIDENCE/builder-artifact-metadata-lock.json" "$ARTIFACT/R7F_EVIDENCE/"
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
audit=json.loads((root/'R7F_EVIDENCE/r7e-external-fingerprint-audit.json').read_text())
identity=json.loads((root/'R7F_EVIDENCE/builder-exact-fingerprint-identity.json').read_text())
builder=json.loads((root/'R7F_EVIDENCE/independent-builder-axe-fingerprint-v2.json').read_text())
metrics=builder.get('metrics') or {}
checks=dict(data.get('checks') or {})
checks.update({
 'immutable-exact-fingerprint-input-lock':gate.get('passed') is True,
 'locked-builder-run':str(lock.get('builderRunId'))==str(data.get('builderRunId')),
 'locked-builder-commit':lock.get('builderHeadSha')==data.get('builderCommit'),
 'locked-builder-artifact-id':str(lock.get('builderArtifactId'))==str(data.get('builderArtifactId')),
 'locked-builder-artifact-name':lock.get('builderArtifactName')==data.get('builderArtifactName'),
 'locked-builder-artifact-digest':lock.get('builderArtifactDigest')==data.get('builderArtifactDigest'),
 'locked-source-archive':lock.get('builderSourceArchiveSha256')==data.get('builderSourceArchiveSha256'),
 'locked-source-tree':lock.get('builderFrozenSourceTreeSha256')==(identity.get('identity') or {}).get('frozenSourceTreeSha256'),
 'locked-source-tar':lock.get('builderFrozenSourceTarSha256')==(identity.get('identity') or {}).get('frozenSourceTarSha256'),
 'locked-dist-tree':lock.get('builderVerifiedDistTreeSha256')==(identity.get('identity') or {}).get('verifiedDistTreeSha256'),
 'locked-stress-tree':lock.get('builderStressDistTreeSha256')==(identity.get('identity') or {}).get('stressDistTreeSha256'),
 'locked-inventory-file':lock.get('builderAxeAdjudicationFileSha256')==(builder.get('builderInventory') or {}).get('fileSha256'),
 'locked-semantic-inventory':lock.get('builderAxeSemanticInventorySha256')==metrics.get('inventorySha256'),
 'locked-node-set':lock.get('builderAxeNodeFingerprintSetSha256')==metrics.get('nodeFingerprintSetSha256'),
 'locked-binding-set':lock.get('builderAxeBindingFingerprintSetSha256')==metrics.get('bindingFingerprintSetSha256'),
 'external-r7e-audit-pass':audit.get('passed') is True and audit.get('blockers')==[],
 'v6-lock-infrastructure':(root/'R7F_EVIDENCE/verifier-v6-lock-infrastructure.sha256').is_file(),
})
data.update({
 'passed':all(checks.values()),
 'verificationVersion':'R7F-v6-exact-fingerprint-bound-locked',
 'checks':checks,
 'failedChecks':[name for name,passed in checks.items() if not passed],
 'builderInputLock':lock,
})
p.write_text(json.dumps(data,indent=2)+'\n')
index_path=root/'R7F_EVIDENCE_INDEX.json'
index=json.loads(index_path.read_text()) if index_path.exists() else {}
index.update({
 'builderInputLockV6':'R7F_EVIDENCE/builder-input-lock-v6.json',
 'builderInputLockV6Gate':'R7F_EVIDENCE/builder-input-lock-v6-gate.json',
 'r7eExternalFingerprintAudit':'R7F_EVIDENCE/r7e-external-fingerprint-audit.json',
 'builderRunMetadataLock':'R7F_EVIDENCE/builder-run-metadata-lock.json',
 'builderArtifactMetadataLock':'R7F_EVIDENCE/builder-artifact-metadata-lock.json',
 'v6LockInfrastructure':'R7F_EVIDENCE/verifier-v6-lock-infrastructure.sha256',
})
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
printf 'R7F v6 locked exact fingerprint-bound verification completed successfully.\n'
