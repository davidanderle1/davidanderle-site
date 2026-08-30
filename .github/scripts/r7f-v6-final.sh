#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

ROOT="$(pwd)"
SCRIPTS="$ROOT/.github/scripts"
EVIDENCE="$ROOT/evidence"
ARTIFACT="$ROOT/artifact"
RUN1="$ROOT/verifier-run1"
BUILDER="$ROOT/builder"
CANDIDATE="$ROOT/candidate"
INDEPENDENT_AUDITOR="$SCRIPTS/r7f-independent-axe-fingerprint-audit-v3.py"
V6_SUCCESS=0

stage_v6_failure() {
  local status="$1"
  set +e
  mkdir -p "$ARTIFACT/R7F_EVIDENCE"
  [[ -d "$EVIDENCE" ]] && cp -a "$EVIDENCE/." "$ARTIFACT/R7F_EVIDENCE/" 2>/dev/null || true
  printf 'R7F V6 EXACT FINGERPRINT VERIFICATION INCOMPLETE — R7 MUST REMAIN OPEN\n' > "$ARTIFACT/R7F_GATE_DECISION.txt"
  python3 - "$status" <<'PY' 2>/dev/null || true
import json, sys
from pathlib import Path
path=Path('artifact/R7F_PACKAGE_VALIDATION.json')
try: data=json.loads(path.read_text()) if path.exists() else {}
except Exception: data={}
data.update({
    'passed':False,
    'verificationVersion':'R7F-v6-exact-fingerprint-bound',
    'v6ExitStatus':int(sys.argv[1]),
    'v6Failure':'Independent exact-node Axe fingerprint verification did not complete.',
})
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
  if [[ "$V6_SUCCESS" -ne 1 ]]; then stage_v6_failure "$status"; fi
  exit "$status"
}
trap on_exit EXIT

required_env=(
  GITHUB_REPOSITORY GITHUB_SHA GITHUB_RUN_ID GITHUB_RUN_ATTEMPT GH_TOKEN
  BUILDER_RUN_ID BUILDER_COMMIT BUILDER_ARTIFACT_ID BUILDER_ARTIFACT_NAME
  BUILDER_ARTIFACT_DIGEST BUILDER_SOURCE_ARCHIVE_SHA256
  BUILDER_FROZEN_SOURCE_TREE_SHA256 BUILDER_FROZEN_SOURCE_TAR_SHA256
  BUILDER_VERIFIED_DIST_TREE_SHA256 BUILDER_STRESS_DIST_TREE_SHA256
  BUILDER_AXE_ADJUDICATION_FILE_SHA256 BUILDER_AXE_SEMANTIC_INVENTORY_SHA256
  BUILDER_AXE_NODE_SET_SHA256 BUILDER_AXE_BINDING_SET_SHA256
)
for name in "${required_env[@]}"; do
  [[ -n "${!name:-}" ]] || { echo "Missing required environment variable: $name" >&2; exit 2; }
done

python3 -m py_compile "$INDEPENDENT_AUDITOR"
bash -n "$SCRIPTS/r7f-v3.sh"
bash -n "$SCRIPTS/r7f-v4.sh"
bash -n "$SCRIPTS/r7f-v6-final.sh"
sha256sum \
  "$SCRIPTS/r7f-v3-tree-guard.py" \
  "$SCRIPTS/r7f-independent-link-audit.py" \
  "$SCRIPTS/r7f-independent-dist-audit.py" \
  "$SCRIPTS/r7f-independent-source-audit.py" \
  "$SCRIPTS/r7f-evidence-gates.py" \
  "$SCRIPTS/r7f-v3.sh" \
  "$SCRIPTS/r7f-candidate-browser-evidence-gate.py" \
  "$SCRIPTS/r7f-independent-browser-audit.mjs" \
  "$SCRIPTS/r7f-v4.sh" \
  "$INDEPENDENT_AUDITOR" \
  "$SCRIPTS/r7f-v6-final.sh" \
  > /tmp/r7f-v6-verifier-infrastructure.sha256

# Preserve all v3 architecture, custody, reproducibility, scale, browser,
# accessibility, Lighthouse, network and deployment gates. v4 additionally
# performs an independent route-specific browser audit and negative control.
bash "$SCRIPTS/r7f-v4.sh"

BUILDER_IDENTITY="$BUILDER/R7E_EVIDENCE/R7E_CANDIDATE_IDENTITY.json"
BUILDER_INVENTORY="$BUILDER/R7E_EVIDENCE/axe-adjudication-inventory.json"
test -f "$BUILDER_IDENTITY"
test -f "$BUILDER_INVENTORY"
python3 - <<'PY'
import hashlib,json,os
from pathlib import Path
identity=json.loads(Path('builder/R7E_EVIDENCE/R7E_CANDIDATE_IDENTITY.json').read_text())
inventory_path=Path('builder/R7E_EVIDENCE/axe-adjudication-inventory.json')
inventory=json.loads(inventory_path.read_text())
file_sha=hashlib.sha256(inventory_path.read_bytes()).hexdigest()
checks={
 'repository':identity.get('repository')==os.environ['GITHUB_REPOSITORY'],
 'commit':identity.get('workflowCommit')==os.environ['BUILDER_COMMIT'],
 'run':str(identity.get('runId'))==os.environ['BUILDER_RUN_ID'],
 'sourceArchive':identity.get('sourceArchiveSha256')==os.environ['BUILDER_SOURCE_ARCHIVE_SHA256'],
 'sourceTree':identity.get('frozenSourceTreeSha256')==os.environ['BUILDER_FROZEN_SOURCE_TREE_SHA256'],
 'sourceTar':identity.get('frozenSourceTarSha256')==os.environ['BUILDER_FROZEN_SOURCE_TAR_SHA256'],
 'distTree':identity.get('verifiedDistTreeSha256')==os.environ['BUILDER_VERIFIED_DIST_TREE_SHA256'],
 'stressTree':identity.get('stressDistTreeSha256')==os.environ['BUILDER_STRESS_DIST_TREE_SHA256'],
 'inventoryFile':file_sha==os.environ['BUILDER_AXE_ADJUDICATION_FILE_SHA256']==identity.get('axeAdjudicationInventorySha256'),
 'semanticInventory':inventory.get('inventorySha256')==os.environ['BUILDER_AXE_SEMANTIC_INVENTORY_SHA256']==identity.get('axeSemanticInventorySha256'),
 'nodeSet':inventory.get('nodeFingerprintSetSha256')==os.environ['BUILDER_AXE_NODE_SET_SHA256']==identity.get('axeNodeFingerprintSetSha256'),
 'bindingSet':inventory.get('bindingFingerprintSetSha256')==os.environ['BUILDER_AXE_BINDING_SET_SHA256']==identity.get('axeBindingFingerprintSetSha256'),
 'inventoryPassed':inventory.get('passed') is True and inventory.get('failedChecks')==[] and inventory.get('errors')==[],
}
result={'gate':'R7F_V6_BUILDER_EXACT_FINGERPRINT_IDENTITY','passed':all(checks.values()),'checks':checks,'failedChecks':[k for k,v in checks.items() if not v],'identity':identity,'inventoryFileSha256':file_sha}
Path('evidence/builder-exact-fingerprint-identity.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
if not result['passed']: raise SystemExit(1)
PY

# Independently recompute every canonical node, classification, proof binding,
# node hash and adjudication hash from both builder and verifier raw evidence.
python3 "$INDEPENDENT_AUDITOR" \
  "$BUILDER/R7E_RUN1_TMP" "$BUILDER_INVENTORY" \
  "$EVIDENCE/independent-builder-axe-fingerprint-v2.json" \
  --label authoritative-builder
python3 "$INDEPENDENT_AUDITOR" \
  "$RUN1/.r7e-tmp" "$BUILDER_INVENTORY" \
  "$EVIDENCE/independent-verifier-axe-fingerprint-v2.json" \
  --label independent-verifier \
  --reference-tmp-root "$BUILDER/R7E_RUN1_TMP"

rm -rf \
  "$ROOT/negative-fingerprint-desktop" \
  "$ROOT/negative-fingerprint-mobile" \
  "$ROOT/negative-fingerprint-proof" \
  "$ROOT/negative-fingerprint-inventory"

# Negative control 1: mutate only the exact affected desktop target.
cp -a "$RUN1/.r7e-tmp" "$ROOT/negative-fingerprint-desktop"
python3 - <<'PY'
import json
from pathlib import Path
p=Path('negative-fingerprint-desktop/axe/home-1280.json')
x=json.loads(p.read_text())
changed=False
for result in x.get('incomplete',[]):
    for node in result.get('nodes',[]):
        rows=node.get('any') or []
        if len(rows)==1 and ((rows[0].get('data') or {}).get('messageKey'))=='elmPartiallyObscuring':
            node['target']=['#r7f-v6-mutated-desktop-target']
            changed=True
            break
    if changed: break
if not changed: raise SystemExit('desktop mutation target not found')
p.write_text(json.dumps(x,indent=2)+'\n')
PY
set +e
python3 "$INDEPENDENT_AUDITOR" \
  "$ROOT/negative-fingerprint-desktop" "$BUILDER_INVENTORY" \
  "$EVIDENCE/negative-control-desktop-target-v2.json" --label negative-desktop \
  > "$EVIDENCE/negative-control-desktop-target-v2.stdout.txt" \
  2> "$EVIDENCE/negative-control-desktop-target-v2.stderr.txt"
desktop_status=$?
set -e
test "$desktop_status" -ne 0
jq -e '.passed == false and ((.failedChecks | index("all-nodes-independently-adjudicated")) != null) and ((.failedChecks | index("builder-entries-exact")) != null)' \
  "$EVIDENCE/negative-control-desktop-target-v2.json" >/dev/null

# Negative control 2: mutate only the mobile related owner/list-item identity.
cp -a "$RUN1/.r7e-tmp" "$ROOT/negative-fingerprint-mobile"
python3 - <<'PY'
import json
from pathlib import Path
p=Path('negative-fingerprint-mobile/axe/home-390.json')
x=json.loads(p.read_text())
changed=False
for result in x.get('incomplete',[]):
    for node in result.get('nodes',[]):
        rows=node.get('any') or []
        if len(rows)!=1 or ((rows[0].get('data') or {}).get('messageKey'))!='pseudoContent':
            continue
        related=rows[0].get('relatedNodes') or []
        if related:
            related[0]['target']=['ol > li:nth-child(99)']
            changed=True
            break
    if changed: break
if not changed: raise SystemExit('mobile related-owner mutation target not found')
p.write_text(json.dumps(x,indent=2)+'\n')
PY
set +e
python3 "$INDEPENDENT_AUDITOR" \
  "$ROOT/negative-fingerprint-mobile" "$BUILDER_INVENTORY" \
  "$EVIDENCE/negative-control-mobile-related-owner-v2.json" --label negative-mobile \
  > "$EVIDENCE/negative-control-mobile-related-owner-v2.stdout.txt" \
  2> "$EVIDENCE/negative-control-mobile-related-owner-v2.stderr.txt"
mobile_status=$?
set -e
test "$mobile_status" -ne 0
jq -e '.passed == false and ((.failedChecks | index("all-nodes-independently-adjudicated")) != null) and ((.failedChecks | index("builder-entries-exact")) != null)' \
  "$EVIDENCE/negative-control-mobile-related-owner-v2.json" >/dev/null

# Negative control 3: keep raw Axe bytes fixed but mutate an exact proof owner.
cp -a "$RUN1/.r7e-tmp" "$ROOT/negative-fingerprint-proof"
python3 - <<'PY'
import json
from pathlib import Path
p=Path('negative-fingerprint-proof/axe-compensation/home-route-backplates-1280.json')
x=json.loads(p.read_text())
x['elements'][0]['ownerTarget']=['ol > li:nth-child(99)']
p.write_text(json.dumps(x,indent=2)+'\n')
PY
set +e
python3 "$INDEPENDENT_AUDITOR" \
  "$ROOT/negative-fingerprint-proof" "$BUILDER_INVENTORY" \
  "$EVIDENCE/negative-control-proof-binding-v2.json" --label negative-proof \
  > "$EVIDENCE/negative-control-proof-binding-v2.stdout.txt" \
  2> "$EVIDENCE/negative-control-proof-binding-v2.stderr.txt"
proof_status=$?
set -e
test "$proof_status" -ne 0
jq -e '.passed == false and ((.failedChecks | index("builder-proof-digest-home1280")) != null) and ((.failedChecks | index("builder-entries-exact")) != null)' \
  "$EVIDENCE/negative-control-proof-binding-v2.json" >/dev/null

# Negative control 4: create a self-consistent but raw-evidence-inconsistent
# builder inventory. Recompute all its internal hashes to prevent a trivial
# checksum-only rejection; the independent raw recomputation must still fail.
cp -a "$RUN1/.r7e-tmp" "$ROOT/negative-fingerprint-inventory"
cp "$BUILDER_INVENTORY" "$ROOT/negative-fingerprint-inventory/mutated-inventory.json"
python3 - <<'PY'
import hashlib,json
from pathlib import Path
p=Path('negative-fingerprint-inventory/mutated-inventory.json')
x=json.loads(p.read_text())

def canon(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(v): return hashlib.sha256(canon(v).encode()).hexdigest()
entry=x['entries'][0]
entry['canonical']['target']=['#self-consistent-mutated-builder-inventory']
entry['nodeFingerprint']=sha(entry['canonical'])
adj={
 'schema':'R7_AXE_ADJUDICATION_FINGERPRINT_V1',
 'nodeFingerprint':entry['nodeFingerprint'],
 'classification':entry['classification'],
 'proofBinding':entry['proofBinding'],
 'passed':entry['passed'],
}
entry['adjudicationFingerprint']=sha(adj)
nodes=[row['nodeFingerprint'] for row in x['entries']]
adjs=[row['adjudicationFingerprint'] for row in x['entries']]
x['orderedNodeFingerprintSha256']=sha(nodes)
x['orderedAdjudicationFingerprintSha256']=sha(adjs)
x['nodeFingerprintSetSha256']=sha(sorted(set(nodes)))
x['bindingFingerprintSetSha256']=sha(sorted(set(adjs)))
projection=[{
 'nodeFingerprint':row['nodeFingerprint'],
 'adjudicationFingerprint':row['adjudicationFingerprint'],
 'canonical':row['canonical'],
 'classification':row['classification'],
 'proofBinding':row['proofBinding'],
 'passed':row['passed'],
} for row in x['entries']]
x['inventorySha256']=sha(projection)
p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
PY
set +e
python3 "$INDEPENDENT_AUDITOR" \
  "$ROOT/negative-fingerprint-inventory" "$ROOT/negative-fingerprint-inventory/mutated-inventory.json" \
  "$EVIDENCE/negative-control-self-consistent-inventory-v2.json" --label negative-inventory \
  > "$EVIDENCE/negative-control-self-consistent-inventory-v2.stdout.txt" \
  2> "$EVIDENCE/negative-control-self-consistent-inventory-v2.stderr.txt"
inventory_status=$?
set -e
test "$inventory_status" -ne 0
jq -e '.passed == false and ((.failedChecks | index("builder-entries-exact")) != null)' \
  "$EVIDENCE/negative-control-self-consistent-inventory-v2.json" >/dev/null

rm -rf \
  "$ROOT/negative-fingerprint-desktop" \
  "$ROOT/negative-fingerprint-mobile" \
  "$ROOT/negative-fingerprint-proof" \
  "$ROOT/negative-fingerprint-inventory"

python3 "$SCRIPTS/r7f-v3-tree-guard.py" compare \
  "$CANDIDATE" "$RUN1" "$EVIDENCE/run1-source-after-exact-fingerprint-v2.json" --source
cp /tmp/r7f-v6-verifier-infrastructure.sha256 "$EVIDENCE/verifier-v6-infrastructure.sha256"
cp -a "$EVIDENCE/." "$ARTIFACT/R7F_EVIDENCE/"
printf 'R7F V6 EXACT FINGERPRINT-BOUND INDEPENDENT VERIFICATION COMPLETE — R7 MAY CLOSE AFTER FINAL AUDIT\n' \
  > "$ARTIFACT/R7F_GATE_DECISION.txt"
rm -f "$ARTIFACT/R7F_ARTIFACT_SHA256SUMS.txt"

python3 - <<'PY'
import json
from pathlib import Path
root=Path('artifact')
validation_path=root/'R7F_PACKAGE_VALIDATION.json'
data=json.loads(validation_path.read_text())
checks=dict(data.get('checks') or {})
identity=json.loads((root/'R7F_EVIDENCE/builder-exact-fingerprint-identity.json').read_text())
builder=json.loads((root/'R7F_EVIDENCE/independent-builder-axe-fingerprint-v2.json').read_text())
verifier=json.loads((root/'R7F_EVIDENCE/independent-verifier-axe-fingerprint-v2.json').read_text())
desktop=json.loads((root/'R7F_EVIDENCE/negative-control-desktop-target-v2.json').read_text())
mobile=json.loads((root/'R7F_EVIDENCE/negative-control-mobile-related-owner-v2.json').read_text())
proof=json.loads((root/'R7F_EVIDENCE/negative-control-proof-binding-v2.json').read_text())
inventory=json.loads((root/'R7F_EVIDENCE/negative-control-self-consistent-inventory-v2.json').read_text())
source=json.loads((root/'R7F_EVIDENCE/run1-source-after-exact-fingerprint-v2.json').read_text())
bm=builder.get('metrics') or {}
vm=verifier.get('metrics') or {}
checks.update({
  'gate-ready-v6-exact':(root/'R7F_GATE_DECISION.txt').read_text().strip()=='R7F V6 EXACT FINGERPRINT-BOUND INDEPENDENT VERIFICATION COMPLETE — R7 MAY CLOSE AFTER FINAL AUDIT',
  'builder-exact-fingerprint-identity':identity.get('passed') is True,
  'builder-exact-fingerprint-audit':builder.get('passed') is True,
  'verifier-exact-fingerprint-audit':verifier.get('passed') is True,
  'verifier-normalized-raw-report-parity':(verifier.get('checks') or {}).get('reference-normalized-raw-reports-exact') is True,
  'builder-verifier-semantic-inventory-parity':bm.get('inventorySha256')==vm.get('inventorySha256'),
  'builder-verifier-node-set-parity':bm.get('nodeFingerprintSetSha256')==vm.get('nodeFingerprintSetSha256'),
  'builder-verifier-binding-set-parity':bm.get('bindingFingerprintSetSha256')==vm.get('bindingFingerprintSetSha256'),
  'exact-node-count-438':bm.get('nodeCount')==438 and vm.get('nodeCount')==438,
  'desktop-target-negative-rejected':desktop.get('passed') is False,
  'mobile-related-owner-negative-rejected':mobile.get('passed') is False,
  'proof-binding-negative-rejected':proof.get('passed') is False,
  'self-consistent-inventory-negative-rejected':inventory.get('passed') is False,
  'source-immutable-after-exact-fingerprint':source.get('passed') is True,
  'v6-infrastructure-manifest':(root/'R7F_EVIDENCE/verifier-v6-infrastructure.sha256').is_file(),
})
data.update({
  'passed':all(checks.values()),
  'verificationVersion':'R7F-v6-exact-fingerprint-bound',
  'checks':checks,
  'failedChecks':[name for name,passed in checks.items() if not passed],
  'axeFingerprintEvidence':{
    'builderAudit':'R7F_EVIDENCE/independent-builder-axe-fingerprint-v2.json',
    'verifierAudit':'R7F_EVIDENCE/independent-verifier-axe-fingerprint-v2.json',
    'desktopTargetNegative':'R7F_EVIDENCE/negative-control-desktop-target-v2.json',
    'mobileRelatedOwnerNegative':'R7F_EVIDENCE/negative-control-mobile-related-owner-v2.json',
    'proofBindingNegative':'R7F_EVIDENCE/negative-control-proof-binding-v2.json',
    'selfConsistentInventoryNegative':'R7F_EVIDENCE/negative-control-self-consistent-inventory-v2.json',
    'nodeCount':vm.get('nodeCount'),
    'inventorySha256':vm.get('inventorySha256'),
    'nodeFingerprintSetSha256':vm.get('nodeFingerprintSetSha256'),
    'bindingFingerprintSetSha256':vm.get('bindingFingerprintSetSha256'),
  },
})
validation_path.write_text(json.dumps(data,indent=2)+'\n')
index_path=root/'R7F_EVIDENCE_INDEX.json'
index=json.loads(index_path.read_text()) if index_path.exists() else {}
index.update({
  'builderExactFingerprintIdentity':'R7F_EVIDENCE/builder-exact-fingerprint-identity.json',
  'builderExactFingerprintAudit':'R7F_EVIDENCE/independent-builder-axe-fingerprint-v2.json',
  'verifierExactFingerprintAudit':'R7F_EVIDENCE/independent-verifier-axe-fingerprint-v2.json',
  'desktopTargetNegative':'R7F_EVIDENCE/negative-control-desktop-target-v2.json',
  'mobileRelatedOwnerNegative':'R7F_EVIDENCE/negative-control-mobile-related-owner-v2.json',
  'proofBindingNegative':'R7F_EVIDENCE/negative-control-proof-binding-v2.json',
  'selfConsistentInventoryNegative':'R7F_EVIDENCE/negative-control-self-consistent-inventory-v2.json',
  'postFingerprintSourceImmutability':'R7F_EVIDENCE/run1-source-after-exact-fingerprint-v2.json',
  'v6Infrastructure':'R7F_EVIDENCE/verifier-v6-infrastructure.sha256',
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

V6_SUCCESS=1
trap - EXIT
printf 'R7F v6 exact fingerprint-bound verification completed successfully.\n'
