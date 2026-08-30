#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

ROOT="$(pwd)"
SCRIPTS="$ROOT/.github/scripts"
EVIDENCE="$ROOT/evidence"
ARTIFACT="$ROOT/artifact"
RUN1="$ROOT/verifier-run1"
CANDIDATE="$ROOT/candidate"
NEGATIVE_AXE="$ROOT/negative-axe"
V5_SUCCESS=0

stage_v5_failure() {
  local status="$1"
  set +e
  mkdir -p "$ARTIFACT/R7F_EVIDENCE"
  if [[ -d "$EVIDENCE" ]]; then
    cp -a "$EVIDENCE/." "$ARTIFACT/R7F_EVIDENCE/" 2>/dev/null || true
  fi
  printf 'R7F V5 INDEPENDENT VERIFICATION INCOMPLETE — R7 MUST REMAIN OPEN\n' > "$ARTIFACT/R7F_GATE_DECISION.txt"
  python3 - "$status" <<'PY' 2>/dev/null || true
import json, sys
from pathlib import Path
root=Path('artifact')
path=root/'R7F_PACKAGE_VALIDATION.json'
try:
    data=json.loads(path.read_text()) if path.exists() else {}
except Exception:
    data={}
data.update({
    'passed':False,
    'verificationVersion':'R7F-v5',
    'v5ExitStatus':int(sys.argv[1]),
    'v5Failure':'Independent non-vacuous Axe compensation verification did not complete.',
})
path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps(data,indent=2)+'\n')
PY
  rm -f "$ARTIFACT/R7F_ARTIFACT_SHA256SUMS.txt"
  if [[ -d "$ARTIFACT" ]]; then
    (
      cd "$ARTIFACT" || exit 0
      find . -type f ! -name 'R7F_ARTIFACT_SHA256SUMS.txt' -print0 | sort -z | xargs -0 sha256sum > R7F_ARTIFACT_SHA256SUMS.txt
      sha256sum --check --strict R7F_ARTIFACT_SHA256SUMS.txt
    ) >/dev/null 2>&1 || true
  fi
}

on_exit() {
  local status=$?
  if [[ "$V5_SUCCESS" -ne 1 ]]; then
    stage_v5_failure "$status"
  fi
  exit "$status"
}
trap on_exit EXIT

python3 -m py_compile "$SCRIPTS/r7f-independent-axe-audit.py"
bash -n "$SCRIPTS/r7f-v5.sh"
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
  "$SCRIPTS/r7f-independent-axe-audit.py" \
  "$SCRIPTS/r7f-v5.sh" > /tmp/r7f-v5-verifier-infrastructure.sha256

# First execute all v3 authenticity/reproducibility/scale/runtime gates and the
# v4 route-specific browser audit. Then independently classify every raw Axe
# incomplete node against exact immutable evidence rather than trusting the
# candidate test's exit status.
bash "$SCRIPTS/r7f-v4.sh"

cp /tmp/r7f-v5-verifier-infrastructure.sha256 "$EVIDENCE/verifier-v5-infrastructure.sha256"
python3 "$SCRIPTS/r7f-independent-axe-audit.py" \
  "$RUN1/.r7e-tmp" \
  "$EVIDENCE/independent-axe-compensation-audit.json"

# Non-vacuity control: a proof marked false must invalidate the same raw Axe
# data. The independent auditor must write a readable failure report and exit
# non-zero.
rm -rf "$NEGATIVE_AXE"
mkdir -p "$NEGATIVE_AXE/playwright"
cp -a "$RUN1/.r7e-tmp/axe" "$NEGATIVE_AXE/"
cp -a "$RUN1/.r7e-tmp/axe-compensation" "$NEGATIVE_AXE/"
cp "$RUN1/.r7e-tmp/contrast-bounds.json" "$NEGATIVE_AXE/"
cp "$RUN1/.r7e-tmp/playwright/axe-results.json" "$NEGATIVE_AXE/playwright/"
python3 - <<'PY'
import json
from pathlib import Path
p=Path('negative-axe/axe-compensation/home-route-backplates-1280.json')
x=json.loads(p.read_text())
x['passed']=False
p.write_text(json.dumps(x,indent=2)+'\n')
PY
set +e
python3 "$SCRIPTS/r7f-independent-axe-audit.py" \
  "$NEGATIVE_AXE" "$EVIDENCE/negative-control-axe-report.json" \
  > "$EVIDENCE/negative-control-axe.stdout.txt" \
  2> "$EVIDENCE/negative-control-axe.stderr.txt"
negative_axe_status=$?
set -e
test "$negative_axe_status" -ne 0
python3 - <<'PY'
import json
from pathlib import Path
r=json.loads(Path('evidence/negative-control-axe-report.json').read_text())
checks={
  'rejected':r.get('passed') is False,
  'proofFailureDetected':'proof:1280:passed' in (r.get('failedChecks') or []),
  'semanticFailureDetected':'axe:no-uncompensated-nodes' in (r.get('failedChecks') or []),
}
result={'passed':all(checks.values()),'exitStatusWasNonzero':True,'checks':checks,'failedChecks':r.get('failedChecks')}
Path('evidence/negative-control-axe-gate.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
if not result['passed']: raise SystemExit(1)
PY
rm -rf "$NEGATIVE_AXE"

# The verifier's extra browser and Axe audits are read-only with respect to the
# submitted canonical production source.
python3 "$SCRIPTS/r7f-v3-tree-guard.py" compare \
  "$CANDIDATE" "$RUN1" "$EVIDENCE/run1-source-after-independent-axe.json" --source

cp -a "$EVIDENCE/." "$ARTIFACT/R7F_EVIDENCE/"
printf 'R7F HARDENED INDEPENDENT VERIFICATION V5 COMPLETE — R7 TECHNICAL ARCHITECTURE MAY CLOSE\n' > "$ARTIFACT/R7F_GATE_DECISION.txt"
rm -f "$ARTIFACT/R7F_ARTIFACT_SHA256SUMS.txt"

python3 - <<'PY'
import json
from pathlib import Path
root=Path('artifact')
validation_path=root/'R7F_PACKAGE_VALIDATION.json'
data=json.loads(validation_path.read_text())
checks=dict(data.get('checks') or {})
axe=json.loads((root/'R7F_EVIDENCE/independent-axe-compensation-audit.json').read_text())
negative=json.loads((root/'R7F_EVIDENCE/negative-control-axe-gate.json').read_text())
source=json.loads((root/'R7F_EVIDENCE/run1-source-after-independent-axe.json').read_text())
checks.update({
  'gate-ready-v5':(root/'R7F_GATE_DECISION.txt').read_text().strip()=='R7F HARDENED INDEPENDENT VERIFICATION V5 COMPLETE — R7 TECHNICAL ARCHITECTURE MAY CLOSE',
  'independent-axe-compensation-audit':axe.get('passed') is True,
  'axe-raw-file-count-10':(axe.get('metrics') or {}).get('rawFileCount')==10,
  'axe-zero-violations':(axe.get('metrics') or {}).get('totalViolations')==0,
  'axe-exact-incomplete-node-count':(axe.get('metrics') or {}).get('totalIncompleteNodes')==438,
  'axe-exact-message-key-inventory':(axe.get('metrics') or {}).get('messageKeys')=={'bgGradient':430,'elmPartiallyObscuring':2,'pseudoContent':6},
  'axe-static-contrast-floor':float((axe.get('metrics') or {}).get('staticContrastMinimumObservedRatio',0))>=4.5,
  'negative-axe-control-detected':negative.get('passed') is True,
  'source-immutable-after-independent-axe':source.get('passed') is True,
  'v5-infrastructure-manifest':(root/'R7F_EVIDENCE/verifier-v5-infrastructure.sha256').is_file(),
})
data.update({
  'passed':all(checks.values()),
  'verificationVersion':'R7F-v5',
  'checks':checks,
  'failedChecks':[name for name,passed in checks.items() if not passed],
  'axeEvidence':{
    'audit':'R7F_EVIDENCE/independent-axe-compensation-audit.json',
    'negativeControl':'R7F_EVIDENCE/negative-control-axe-gate.json',
    'rawFileCount':(axe.get('metrics') or {}).get('rawFileCount'),
    'totalViolations':(axe.get('metrics') or {}).get('totalViolations'),
    'totalIncompleteNodes':(axe.get('metrics') or {}).get('totalIncompleteNodes'),
    'messageKeys':(axe.get('metrics') or {}).get('messageKeys'),
    'staticContrastMinimumObservedRatio':(axe.get('metrics') or {}).get('staticContrastMinimumObservedRatio'),
  },
})
validation_path.write_text(json.dumps(data,indent=2)+'\n')
index_path=root/'R7F_EVIDENCE_INDEX.json'
index=json.loads(index_path.read_text()) if index_path.exists() else {}
index.update({
  'independentAxeCompensationAudit':'R7F_EVIDENCE/independent-axe-compensation-audit.json',
  'negativeAxeControl':'R7F_EVIDENCE/negative-control-axe-gate.json',
  'postAxeSourceImmutability':'R7F_EVIDENCE/run1-source-after-independent-axe.json',
  'v5InfrastructureManifest':'R7F_EVIDENCE/verifier-v5-infrastructure.sha256',
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

V5_SUCCESS=1
trap - EXIT
printf 'R7F v5 completed successfully.\n'
