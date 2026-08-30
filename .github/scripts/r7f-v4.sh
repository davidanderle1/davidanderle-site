#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

ROOT="$(pwd)"
SCRIPTS="$ROOT/.github/scripts"
EVIDENCE="$ROOT/evidence"
ARTIFACT="$ROOT/artifact"
RUN1="$ROOT/verifier-run1"
CANDIDATE="$ROOT/candidate"
NEGATIVE_BROWSER="$ROOT/negative-browser"
V4_SUCCESS=0

stage_v4_failure() {
  local status="$1"
  set +e
  mkdir -p "$ARTIFACT/R7F_EVIDENCE"
  if [[ -d "$EVIDENCE" ]]; then
    cp -a "$EVIDENCE/." "$ARTIFACT/R7F_EVIDENCE/" 2>/dev/null || true
  fi
  printf 'R7F V4 INDEPENDENT VERIFICATION INCOMPLETE — R7 MUST REMAIN OPEN\n' > "$ARTIFACT/R7F_GATE_DECISION.txt"
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
    'verificationVersion':'R7F-v4',
    'v4ExitStatus':int(sys.argv[1]),
    'v4Failure':'Independent route-specific browser verification did not complete.',
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
  if [[ "$V4_SUCCESS" -ne 1 ]]; then
    stage_v4_failure "$status"
  fi
  exit "$status"
}
trap on_exit EXIT

python3 -m py_compile "$SCRIPTS/r7f-candidate-browser-evidence-gate.py"
node --check "$SCRIPTS/r7f-independent-browser-audit.mjs"
bash -n "$SCRIPTS/r7f-v4.sh"
sha256sum \
  "$SCRIPTS/r7f-v3-tree-guard.py" \
  "$SCRIPTS/r7f-independent-link-audit.py" \
  "$SCRIPTS/r7f-independent-dist-audit.py" \
  "$SCRIPTS/r7f-independent-source-audit.py" \
  "$SCRIPTS/r7f-evidence-gates.py" \
  "$SCRIPTS/r7f-v3.sh" \
  "$SCRIPTS/r7f-candidate-browser-evidence-gate.py" \
  "$SCRIPTS/r7f-independent-browser-audit.mjs" \
  "$SCRIPTS/r7f-v4.sh" > /tmp/r7f-v4-verifier-infrastructure.sha256

# Reuse the already hardened builder/authenticity/reproducibility/scale/runtime verifier,
# then independently close the browser-evidence gap discovered during external artifact review.
bash "$SCRIPTS/r7f-v3.sh"

cp /tmp/r7f-v4-verifier-infrastructure.sha256 "$EVIDENCE/verifier-v4-infrastructure.sha256"
python3 "$SCRIPTS/r7f-candidate-browser-evidence-gate.py" \
  "$RUN1/.r7e-tmp" \
  "$EVIDENCE/candidate-browser-evidence-gate.json"
cp "$RUN1/.r7e-tmp/no-js-route-evidence.json" "$EVIDENCE/candidate-no-js-route-evidence.json"
cp "$RUN1/.r7e-tmp/vce-enhancement-evidence.json" "$EVIDENCE/candidate-vce-enhancement-evidence.json"
mkdir -p "$EVIDENCE/candidate-browser-screenshots"
cp "$RUN1/.r7e-tmp/screenshots/alternate-no-js-vce-390.png" "$EVIDENCE/candidate-browser-screenshots/"
cp "$RUN1/.r7e-tmp/screenshots/alternate-vce-enhanced-step-390.png" "$EVIDENCE/candidate-browser-screenshots/"

node "$SCRIPTS/r7f-independent-browser-audit.mjs" \
  "$RUN1" "$RUN1/dist" "$EVIDENCE/independent-browser" 4197
python3 - <<'PY'
import json
from pathlib import Path
r=json.loads(Path('evidence/independent-browser/report.json').read_text())
checks={
  'passed':r.get('passed') is True,
  'routeCount':(r.get('noJavaScript') or {}).get('routeCount')==14,
  'noJsFourVisible':((r.get('noJavaScript') or {}).get('vce') or {}).get('visiblePanelCount')==4,
  'enhancementHome':(r.get('enhancement') or {}).get('selectedIndexAfterHome')==0,
  'enhancementOneVisible':(r.get('enhancement') or {}).get('visiblePanelCountAfterHome')==1,
  'ordinaryRouteCount':(r.get('ordinaryRouteIsolation') or {}).get('routeCount')==13,
  'ordinaryScriptsZero':all(x.get('scriptRequestCount')==0 for x in ((r.get('ordinaryRouteIsolation') or {}).get('routes') or [])),
}
result={'passed':all(checks.values()),'checks':checks}
Path('evidence/independent-browser-gate.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
if not result['passed']: raise SystemExit(1)
PY

# Non-vacuity control: the independent audit must reject a semantically wrong route heading.
rm -rf "$NEGATIVE_BROWSER"
mkdir -p "$NEGATIVE_BROWSER/dist"
cp -a "$RUN1/dist/." "$NEGATIVE_BROWSER/dist/"
python3 - <<'PY'
from pathlib import Path
p=Path('negative-browser/dist/work/volatility-cascade-engine/index.html')
s=p.read_text()
needle='<h1>Volatility Cascade Engine</h1>'
replacement='<h1>R7F deliberate browser-evidence failure</h1>'
if needle not in s: raise SystemExit('negative-control H1 needle not found')
p.write_text(s.replace(needle,replacement,1))
PY
set +e
node "$SCRIPTS/r7f-independent-browser-audit.mjs" \
  "$RUN1" "$NEGATIVE_BROWSER/dist" "$EVIDENCE/negative-control-browser" 4198 \
  > "$EVIDENCE/negative-control-browser.stdout.txt" \
  2> "$EVIDENCE/negative-control-browser.stderr.txt"
negative_browser_status=$?
set -e
test "$negative_browser_status" -ne 0
python3 - <<'PY'
import json
from pathlib import Path
p=Path('evidence/negative-control-browser/report.json')
r=json.loads(p.read_text())
checks={
  'rejected':r.get('passed') is False,
  'headingMismatch':(r.get('failure') or {}).get('code')=='HEADING_MISMATCH',
}
result={'passed':all(checks.values()),'exitWasNonzero':True,'checks':checks,'failure':r.get('failure')}
Path('evidence/negative-control-browser-gate.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
if not result['passed']: raise SystemExit(1)
PY
rm -rf "$NEGATIVE_BROWSER"

# Independent browser execution must not mutate the submitted source.
python3 "$SCRIPTS/r7f-v3-tree-guard.py" compare \
  "$CANDIDATE" "$RUN1" "$EVIDENCE/run1-source-after-independent-browser.json" --source

# Replace the provisional v3 closure with a v4 package that explicitly contains and validates
# route-specific no-JavaScript and interactive VCE evidence.
cp -a "$EVIDENCE/." "$ARTIFACT/R7F_EVIDENCE/"
printf 'R7F HARDENED INDEPENDENT VERIFICATION V4 COMPLETE — R7 TECHNICAL ARCHITECTURE MAY CLOSE\n' > "$ARTIFACT/R7F_GATE_DECISION.txt"
rm -f "$ARTIFACT/R7F_ARTIFACT_SHA256SUMS.txt"

python3 - <<'PY'
import hashlib, json
from pathlib import Path
root=Path('artifact')
validation_path=root/'R7F_PACKAGE_VALIDATION.json'
data=json.loads(validation_path.read_text())
checks=dict(data.get('checks') or {})
candidate=json.loads((root/'R7F_EVIDENCE/candidate-browser-evidence-gate.json').read_text())
independent=json.loads((root/'R7F_EVIDENCE/independent-browser/report.json').read_text())
independent_gate=json.loads((root/'R7F_EVIDENCE/independent-browser-gate.json').read_text())
negative=json.loads((root/'R7F_EVIDENCE/negative-control-browser-gate.json').read_text())
no_js=json.loads((root/'R7F_EVIDENCE/candidate-no-js-route-evidence.json').read_text())
enhancement=json.loads((root/'R7F_EVIDENCE/candidate-vce-enhancement-evidence.json').read_text())
screenshots=list((root/'R7F_RUN1_TMP/screenshots').glob('*.png'))
checks.update({
  'gate-ready':(root/'R7F_GATE_DECISION.txt').read_text().strip()=='R7F HARDENED INDEPENDENT VERIFICATION V4 COMPLETE — R7 TECHNICAL ARCHITECTURE MAY CLOSE',
  'candidate-browser-evidence':candidate.get('passed') is True,
  'candidate-no-js-route-count-14':no_js.get('routeCount')==14,
  'candidate-no-js-vce-four-visible':(no_js.get('vce') or {}).get('visiblePanelCount')==4,
  'candidate-vce-enhancement-complete':enhancement.get('passed') is True and enhancement.get('selectedIndexAfterHome')==0 and enhancement.get('visiblePanelCountAfterHome')==1,
  'independent-browser-audit':independent.get('passed') is True,
  'independent-browser-gate':independent_gate.get('passed') is True,
  'independent-ordinary-routes-no-js':all(x.get('scriptRequestCount')==0 for x in ((independent.get('ordinaryRouteIsolation') or {}).get('routes') or [])),
  'negative-browser-control-detected':negative.get('passed') is True,
  'screenshots-at-least-41':len(screenshots)>=41,
  'v4-infrastructure-manifest':(root/'R7F_EVIDENCE/verifier-v4-infrastructure.sha256').is_file(),
  'source-immutable-after-independent-browser':json.loads((root/'R7F_EVIDENCE/run1-source-after-independent-browser.json').read_text()).get('passed') is True,
})
data.update({
  'passed':all(checks.values()),
  'verificationVersion':'R7F-v4',
  'checks':checks,
  'failedChecks':[name for name,passed in checks.items() if not passed],
  'browserEvidence':{
    'candidateRouteCount':no_js.get('routeCount'),
    'candidateScreenshotCount':len(screenshots),
    'independentRouteCount':(independent.get('noJavaScript') or {}).get('routeCount'),
    'independentOrdinaryRouteCount':(independent.get('ordinaryRouteIsolation') or {}).get('routeCount'),
    'candidateNoJsScreenshotSha256':((no_js.get('vce') or {}).get('screenshotSha256')),
    'candidateEnhancedScreenshotSha256':enhancement.get('screenshotSha256'),
    'independentNoJsScreenshotSha256':((independent.get('noJavaScript') or {}).get('vce') or {}).get('screenshotSha256'),
    'independentEnhancedScreenshotSha256':(independent.get('enhancement') or {}).get('screenshotSha256'),
  },
})
validation_path.write_text(json.dumps(data,indent=2)+'\n')
index_path=root/'R7F_EVIDENCE_INDEX.json'
index=json.loads(index_path.read_text()) if index_path.exists() else {}
index.update({
  'candidateBrowserEvidence':'R7F_EVIDENCE/candidate-browser-evidence-gate.json',
  'candidateNoJsEvidence':'R7F_EVIDENCE/candidate-no-js-route-evidence.json',
  'candidateVceEnhancementEvidence':'R7F_EVIDENCE/candidate-vce-enhancement-evidence.json',
  'independentBrowserAudit':'R7F_EVIDENCE/independent-browser/report.json',
  'independentBrowserGate':'R7F_EVIDENCE/independent-browser-gate.json',
  'negativeBrowserControl':'R7F_EVIDENCE/negative-control-browser-gate.json',
  'postBrowserSourceImmutability':'R7F_EVIDENCE/run1-source-after-independent-browser.json',
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

V4_SUCCESS=1
trap - EXIT
printf 'R7F v4 completed successfully.\n'
