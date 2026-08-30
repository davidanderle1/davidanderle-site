#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

ROOT="$(pwd)"
SCRIPTS="$ROOT/.github/scripts"
EVIDENCE="$ROOT/evidence"
ARTIFACT="$ROOT/artifact"
RUN1="$ROOT/verifier-run1"
BUILDER_V6="$ROOT/r7f-v6-builder"
V6_SUCCESS=0

stage_v6_failure() {
  local status="$1"
  set +e
  mkdir -p "$ARTIFACT/R7F_EVIDENCE"
  [[ -d "$EVIDENCE" ]] && cp -a "$EVIDENCE/." "$ARTIFACT/R7F_EVIDENCE/" 2>/dev/null || true
  printf 'R7F V6 FINGERPRINT-BOUND VERIFICATION INCOMPLETE — R7 MUST REMAIN OPEN\n' > "$ARTIFACT/R7F_GATE_DECISION.txt"
  python3 - "$status" <<'PY' 2>/dev/null || true
import json, sys
from pathlib import Path
path=Path('artifact/R7F_PACKAGE_VALIDATION.json')
try: data=json.loads(path.read_text()) if path.exists() else {}
except Exception: data={}
data.update({'passed':False,'verificationVersion':'R7F-v6-fingerprint-bound','v6ExitStatus':int(sys.argv[1]),'v6Failure':'Exact Axe node fingerprint verification did not complete.'})
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

python3 -m py_compile "$SCRIPTS/r7f-independent-axe-fingerprint-audit.py"
bash -n "$SCRIPTS/r7f-v6.sh"
sha256sum \
  "$SCRIPTS/r7f-v3.sh" \
  "$SCRIPTS/r7f-v4.sh" \
  "$SCRIPTS/r7f-v5.sh" \
  "$SCRIPTS/r7f-independent-axe-audit.py" \
  "$SCRIPTS/r7f-independent-axe-fingerprint-audit.py" \
  "$SCRIPTS/r7f-v6.sh" \
  > /tmp/r7f-v6-verifier-infrastructure.sha256

# Preserve every v3-v5 authenticity, reproducibility, scale, browser, runtime,
# compensation and non-vacuity gate before adding exact node fingerprints.
bash "$SCRIPTS/r7f-v5.sh"

rm -rf "$BUILDER_V6" "$ROOT/negative-fingerprint-desktop" "$ROOT/negative-fingerprint-mobile" "$ROOT/negative-fingerprint-proof"
mkdir -p "$BUILDER_V6"
curl --fail --silent --show-error --location \
  -H "Authorization: Bearer ${GH_TOKEN}" \
  -H 'Accept: application/vnd.github+json' \
  "https://api.github.com/repos/${GITHUB_REPOSITORY}/actions/artifacts/${BUILDER_ARTIFACT_ID}/zip" \
  --output /tmp/r7f-v6-builder.zip
actual_builder_digest="sha256:$(sha256sum /tmp/r7f-v6-builder.zip | awk '{print $1}')"
test "$actual_builder_digest" = "$BUILDER_ARTIFACT_DIGEST"
unzip -q /tmp/r7f-v6-builder.zip -d "$BUILDER_V6"
test "$(cat "$BUILDER_V6/R7E_FINGERPRINT_BOUND_GATE_DECISION.txt")" = 'R7E FINGERPRINT-BOUND EVIDENCE VERIFIED — READY FOR R7F V6'
test "$(jq -r '.passed' "$BUILDER_V6/R7E_FINGERPRINT_PACKAGE_VALIDATION.json")" = true
BUILDER_INVENTORY="$BUILDER_V6/R7E_EVIDENCE/axe-node-fingerprint-inventory-v1.json"
test -f "$BUILDER_INVENTORY"
test "$(jq -r '.passed' "$BUILDER_INVENTORY")" = true
test "$(jq -r '.metrics.nodeCount' "$BUILDER_INVENTORY")" -eq 438

# Recompute the complete fingerprint multiset from both the exact builder raw
# reports and an independently rebuilt verifier browser run.
python3 "$SCRIPTS/r7f-independent-axe-fingerprint-audit.py" \
  "$BUILDER_V6/R7E_RUN1_TMP" "$BUILDER_INVENTORY" \
  "$EVIDENCE/independent-builder-axe-fingerprint-audit.json" \
  --label builder
python3 "$SCRIPTS/r7f-independent-axe-fingerprint-audit.py" \
  "$RUN1/.r7e-tmp" "$BUILDER_INVENTORY" \
  "$EVIDENCE/independent-verifier-axe-fingerprint-audit.json" \
  --label verifier

# Negative control 1: preserve counts/message keys/HTML, but alter the exact
# desktop affected target. The full fingerprint comparison must reject it.
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
        key=((rows[0].get('data') or {}).get('messageKey') if len(rows)==1 else None)
        if key=='elmPartiallyObscuring':
            node['target']=['#r7f-v6-mutated-desktop-target']
            changed=True
            break
    if changed: break
if not changed: raise SystemExit('desktop mutation target not found')
p.write_text(json.dumps(x,indent=2)+'\n')
PY
set +e
python3 "$SCRIPTS/r7f-independent-axe-fingerprint-audit.py" \
  "$ROOT/negative-fingerprint-desktop" "$BUILDER_INVENTORY" \
  "$EVIDENCE/negative-control-desktop-target.json" --label negative-desktop \
  > "$EVIDENCE/negative-control-desktop-target.stdout.txt" \
  2> "$EVIDENCE/negative-control-desktop-target.stderr.txt"
desktop_status=$?
set -e
test "$desktop_status" -ne 0
jq -e '.passed == false and ((.failedChecks | index("exact-payload-multiset")) != null) and ((.failedChecks | index("exact-fingerprint-multiset")) != null)' \
  "$EVIDENCE/negative-control-desktop-target.json" >/dev/null

# Negative control 2: alter only the related list-item index on a mobile
# pseudo-content node. Generic-selector checking used to miss this mutation.
cp -a "$RUN1/.r7e-tmp" "$ROOT/negative-fingerprint-mobile"
python3 - <<'PY'
import json,re
from pathlib import Path
p=Path('negative-fingerprint-mobile/axe/home-390.json')
x=json.loads(p.read_text())
changed=False
for result in x.get('incomplete',[]):
    for node in result.get('nodes',[]):
        rows=node.get('any') or []
        if len(rows)!=1 or ((rows[0].get('data') or {}).get('messageKey'))!='pseudoContent':
            continue
        for related in rows[0].get('relatedNodes') or []:
            target=related.get('target') or []
            for i,value in enumerate(target):
                m=re.search(r'li:nth-child\((\d+)\)',value)
                if m:
                    old=int(m.group(1)); new=2 if old==1 else 1
                    target[i]=value[:m.start(1)]+str(new)+value[m.end(1):]
                    related['target']=target
                    changed=True
                    break
            if changed: break
        if changed: break
    if changed: break
if not changed: raise SystemExit('mobile related-index mutation target not found')
p.write_text(json.dumps(x,indent=2)+'\n')
PY
set +e
python3 "$SCRIPTS/r7f-independent-axe-fingerprint-audit.py" \
  "$ROOT/negative-fingerprint-mobile" "$BUILDER_INVENTORY" \
  "$EVIDENCE/negative-control-mobile-related-index.json" --label negative-mobile \
  > "$EVIDENCE/negative-control-mobile-related-index.stdout.txt" \
  2> "$EVIDENCE/negative-control-mobile-related-index.stderr.txt"
mobile_status=$?
set -e
test "$mobile_status" -ne 0
jq -e '.passed == false and ((.failedChecks | index("exact-payload-multiset")) != null) and ((.failedChecks | index("exact-fingerprint-multiset")) != null)' \
  "$EVIDENCE/negative-control-mobile-related-index.json" >/dev/null

# Negative control 3: invalidate the opaque-backplate proof while preserving
# all raw Axe nodes and their exact fingerprints.
cp -a "$RUN1/.r7e-tmp" "$ROOT/negative-fingerprint-proof"
python3 - <<'PY'
import json
from pathlib import Path
p=Path('negative-fingerprint-proof/axe-compensation/home-route-backplates-1280.json')
x=json.loads(p.read_text())
x['passed']=False
p.write_text(json.dumps(x,indent=2)+'\n')
PY
set +e
python3 "$SCRIPTS/r7f-independent-axe-fingerprint-audit.py" \
  "$ROOT/negative-fingerprint-proof" "$BUILDER_INVENTORY" \
  "$EVIDENCE/negative-control-compensation-proof.json" --label negative-proof \
  > "$EVIDENCE/negative-control-compensation-proof.stdout.txt" \
  2> "$EVIDENCE/negative-control-compensation-proof.stderr.txt"
proof_status=$?
set -e
test "$proof_status" -ne 0
jq -e '.passed == false and ((.failedChecks | index("proof-1280")) != null) and ((.failedChecks | index("all-independently-adjudicated")) != null)' \
  "$EVIDENCE/negative-control-compensation-proof.json" >/dev/null

rm -rf "$ROOT/negative-fingerprint-desktop" "$ROOT/negative-fingerprint-mobile" "$ROOT/negative-fingerprint-proof" "$BUILDER_V6"
python3 "$SCRIPTS/r7f-v3-tree-guard.py" compare \
  "$ROOT/candidate" "$RUN1" "$EVIDENCE/run1-source-after-fingerprint-audit.json" --source
cp /tmp/r7f-v6-verifier-infrastructure.sha256 "$EVIDENCE/verifier-v6-infrastructure.sha256"
cp -a "$EVIDENCE/." "$ARTIFACT/R7F_EVIDENCE/"
printf 'R7F V6 FINGERPRINT-BOUND INDEPENDENT VERIFICATION COMPLETE — R7 MAY CLOSE AFTER FINAL AUDIT\n' \
  > "$ARTIFACT/R7F_GATE_DECISION.txt"
rm -f "$ARTIFACT/R7F_ARTIFACT_SHA256SUMS.txt"

python3 - <<'PY'
import json
from pathlib import Path
root=Path('artifact')
p=root/'R7F_PACKAGE_VALIDATION.json'
data=json.loads(p.read_text())
checks=dict(data.get('checks') or {})
builder=json.loads((root/'R7F_EVIDENCE/independent-builder-axe-fingerprint-audit.json').read_text())
verifier=json.loads((root/'R7F_EVIDENCE/independent-verifier-axe-fingerprint-audit.json').read_text())
desktop=json.loads((root/'R7F_EVIDENCE/negative-control-desktop-target.json').read_text())
mobile=json.loads((root/'R7F_EVIDENCE/negative-control-mobile-related-index.json').read_text())
proof=json.loads((root/'R7F_EVIDENCE/negative-control-compensation-proof.json').read_text())
source=json.loads((root/'R7F_EVIDENCE/run1-source-after-fingerprint-audit.json').read_text())
checks.update({
  'gate-ready-v6':(root/'R7F_GATE_DECISION.txt').read_text().strip()=='R7F V6 FINGERPRINT-BOUND INDEPENDENT VERIFICATION COMPLETE — R7 MAY CLOSE AFTER FINAL AUDIT',
  'builder-exact-fingerprints':builder.get('passed') is True,
  'verifier-exact-fingerprints':verifier.get('passed') is True,
  'builder-verifier-fingerprint-parity':(builder.get('metrics') or {}).get('fingerprintMultisetSha256')==(verifier.get('metrics') or {}).get('fingerprintMultisetSha256'),
  'fingerprint-node-count-438':(verifier.get('metrics') or {}).get('nodeCount')==438,
  'desktop-target-negative-rejected':desktop.get('passed') is False,
  'mobile-related-index-negative-rejected':mobile.get('passed') is False,
  'compensation-proof-negative-rejected':proof.get('passed') is False,
  'source-immutable-after-fingerprint-audit':source.get('passed') is True,
  'v6-infrastructure-manifest':(root/'R7F_EVIDENCE/verifier-v6-infrastructure.sha256').is_file(),
})
data.update({
  'passed':all(checks.values()),
  'verificationVersion':'R7F-v6-fingerprint-bound',
  'checks':checks,
  'failedChecks':[name for name,passed in checks.items() if not passed],
  'axeFingerprintEvidence':{
    'builderAudit':'R7F_EVIDENCE/independent-builder-axe-fingerprint-audit.json',
    'verifierAudit':'R7F_EVIDENCE/independent-verifier-axe-fingerprint-audit.json',
    'desktopTargetNegative':'R7F_EVIDENCE/negative-control-desktop-target.json',
    'mobileRelatedIndexNegative':'R7F_EVIDENCE/negative-control-mobile-related-index.json',
    'proofNegative':'R7F_EVIDENCE/negative-control-compensation-proof.json',
    'fingerprintMultisetSha256':(verifier.get('metrics') or {}).get('fingerprintMultisetSha256'),
    'nodeCount':(verifier.get('metrics') or {}).get('nodeCount'),
  },
})
p.write_text(json.dumps(data,indent=2)+'\n')
index_path=root/'R7F_EVIDENCE_INDEX.json'
index=json.loads(index_path.read_text()) if index_path.exists() else {}
index.update({
  'builderAxeFingerprintAudit':'R7F_EVIDENCE/independent-builder-axe-fingerprint-audit.json',
  'verifierAxeFingerprintAudit':'R7F_EVIDENCE/independent-verifier-axe-fingerprint-audit.json',
  'desktopTargetNegative':'R7F_EVIDENCE/negative-control-desktop-target.json',
  'mobileRelatedIndexNegative':'R7F_EVIDENCE/negative-control-mobile-related-index.json',
  'compensationProofNegative':'R7F_EVIDENCE/negative-control-compensation-proof.json',
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
printf 'R7F v6 fingerprint-bound verification completed successfully.\n'
