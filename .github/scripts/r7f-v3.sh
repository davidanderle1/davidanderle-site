#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

ROOT="$(pwd)"
SCRIPTS="$ROOT/.github/scripts"
EVIDENCE="$ROOT/evidence"
ARTIFACT="$ROOT/artifact"
BUILDER_DOWNLOAD="$ROOT/builder-download"
BUILDER="$ROOT/builder"
CANDIDATE="$ROOT/candidate"
SOURCE_TAR="$ROOT/source-tar"
RUN1="$ROOT/verifier-run1"
RUN2="$ROOT/verifier-run2"
BUILDER_STRESS="$ROOT/builder-stress-no-marker"
VERIFIER_STRESS="$ROOT/verifier-stress-staged"
SUCCESS=0

required_env=(
  GITHUB_REPOSITORY GITHUB_SHA GITHUB_RUN_ID GITHUB_RUN_ATTEMPT
  BUILDER_RUN_ID BUILDER_COMMIT BUILDER_ARTIFACT_ID BUILDER_ARTIFACT_NAME
  BUILDER_ARTIFACT_DIGEST BUILDER_SOURCE_ARCHIVE_SHA256
)
for name in "${required_env[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required environment variable: $name" >&2
    exit 2
  fi
done

sha256_file() {
  sha256sum "$1" | awk '{print $1}'
}

stage_diagnostic() {
  local exit_status="$1"
  set +e
  rm -rf "$ARTIFACT"
  mkdir -p "$ARTIFACT/R7F_EVIDENCE"
  cp -a "$EVIDENCE/." "$ARTIFACT/R7F_EVIDENCE/" 2>/dev/null || true
  if [[ -d "$CANDIDATE" ]]; then
    mkdir -p "$ARTIFACT/VERIFIER_PRODUCTION_SOURCE"
    cp -a "$CANDIDATE/." "$ARTIFACT/VERIFIER_PRODUCTION_SOURCE/" 2>/dev/null || true
  fi
  if [[ -d "$RUN1/dist" ]]; then
    mkdir -p "$ARTIFACT/VERIFIER_PARTIAL_DIST"
    cp -a "$RUN1/dist/." "$ARTIFACT/VERIFIER_PARTIAL_DIST/" 2>/dev/null || true
  fi
  if [[ -d "$RUN1/.r7e-tmp" ]]; then
    cp -a "$RUN1/.r7e-tmp" "$ARTIFACT/R7F_RUN1_TMP" 2>/dev/null || true
  fi
  printf 'R7F INDEPENDENT VERIFICATION INCOMPLETE — R7 MUST REMAIN OPEN\n' > "$ARTIFACT/R7F_GATE_DECISION.txt"
  printf '{"passed":false,"exitStatus":%s}\n' "$exit_status" > "$ARTIFACT/R7F_PACKAGE_VALIDATION.json"
  (
    cd "$ARTIFACT" || exit 0
    find . -type f ! -name 'R7F_ARTIFACT_SHA256SUMS.txt' -print0 | sort -z | xargs -0 sha256sum > R7F_ARTIFACT_SHA256SUMS.txt
    sha256sum --check --strict R7F_ARTIFACT_SHA256SUMS.txt
  ) >/dev/null 2>&1 || true
}

on_exit() {
  local status=$?
  if [[ "$SUCCESS" -ne 1 ]]; then
    stage_diagnostic "$status"
  fi
  exit "$status"
}
trap on_exit EXIT

rm -rf "$EVIDENCE" "$ARTIFACT" "$BUILDER_DOWNLOAD" "$BUILDER" "$CANDIDATE" "$SOURCE_TAR" "$RUN1" "$RUN2" "$BUILDER_STRESS" "$VERIFIER_STRESS"
mkdir -p "$EVIDENCE" "$ARTIFACT" "$BUILDER_DOWNLOAD"

{
  echo "repository=$GITHUB_REPOSITORY"
  echo "verifier_commit=$GITHUB_SHA"
  echo "verifier_run_id=$GITHUB_RUN_ID"
  echo "verifier_run_attempt=$GITHUB_RUN_ATTEMPT"
  echo "builder_run_id=$BUILDER_RUN_ID"
  echo "builder_commit=$BUILDER_COMMIT"
  echo "builder_artifact_id=$BUILDER_ARTIFACT_ID"
  echo "builder_artifact_name=$BUILDER_ARTIFACT_NAME"
  echo "builder_artifact_digest=$BUILDER_ARTIFACT_DIGEST"
  echo "builder_source_archive_sha256=$BUILDER_SOURCE_ARCHIVE_SHA256"
  echo "node=$(node --version)"
  echo "npm=$(npm --version)"
  echo "runner_os=${RUNNER_OS:-unknown}"
  echo "runner_arch=${RUNNER_ARCH:-unknown}"
  uname -a
} | tee "$EVIDENCE/environment.txt"
test "$(node --version)" = 'v24.20.0'
test "$(npm --version)" = '11.19.0'
python3 -m py_compile \
  "$SCRIPTS/r7f-v3-tree-guard.py" \
  "$SCRIPTS/r7f-independent-link-audit.py" \
  "$SCRIPTS/r7f-independent-dist-audit.py" \
  "$SCRIPTS/r7f-independent-source-audit.py" \
  "$SCRIPTS/r7f-evidence-gates.py"
bash -n "$SCRIPTS/r7f-v3.sh"
sha256sum \
  "$SCRIPTS/r7f-v3-tree-guard.py" \
  "$SCRIPTS/r7f-independent-link-audit.py" \
  "$SCRIPTS/r7f-independent-dist-audit.py" \
  "$SCRIPTS/r7f-independent-source-audit.py" \
  "$SCRIPTS/r7f-evidence-gates.py" \
  "$SCRIPTS/r7f-v3.sh" > "$EVIDENCE/verifier-infrastructure.sha256"

# Authenticate artifact metadata before downloading any candidate bytes.
gh api "repos/${GITHUB_REPOSITORY}/actions/artifacts/${BUILDER_ARTIFACT_ID}" > "$EVIDENCE/builder-artifact-metadata.json"
python3 - <<'PY'
import json, os
from pathlib import Path
m=json.loads(Path('evidence/builder-artifact-metadata.json').read_text())
checks={
  'artifactId':str(m.get('id'))==os.environ['BUILDER_ARTIFACT_ID'],
  'artifactName':m.get('name')==os.environ['BUILDER_ARTIFACT_NAME'],
  'artifactDigest':m.get('digest')==os.environ['BUILDER_ARTIFACT_DIGEST'],
  'artifactActive':m.get('expired') is False,
  'builderRun':str((m.get('workflow_run') or {}).get('id'))==os.environ['BUILDER_RUN_ID'],
  'builderCommit':(m.get('workflow_run') or {}).get('head_sha')==os.environ['BUILDER_COMMIT'],
}
r={'passed':all(checks.values()),'checks':checks,'metadata':m}
Path('evidence/builder-artifact-metadata-gate.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r,indent=2))
if not r['passed']: raise SystemExit(1)
PY

gh run download "$BUILDER_RUN_ID" --repo "$GITHUB_REPOSITORY" --name "$BUILDER_ARTIFACT_NAME" --dir "$BUILDER_DOWNLOAD"
if [[ -f "$BUILDER_DOWNLOAD/R7E_GATE_DECISION.txt" ]]; then
  mv "$BUILDER_DOWNLOAD" "$BUILDER"
elif [[ -d "$BUILDER_DOWNLOAD/$BUILDER_ARTIFACT_NAME" && -f "$BUILDER_DOWNLOAD/$BUILDER_ARTIFACT_NAME/R7E_GATE_DECISION.txt" ]]; then
  mv "$BUILDER_DOWNLOAD/$BUILDER_ARTIFACT_NAME" "$BUILDER"
  rm -rf "$BUILDER_DOWNLOAD"
else
  echo "Downloaded artifact has an unexpected layout" >&2
  find "$BUILDER_DOWNLOAD" -maxdepth 3 -print >&2 || true
  exit 1
fi
(
  cd "$BUILDER"
  sha256sum --check --strict R7E_ARTIFACT_SHA256SUMS.txt
) | tee "$EVIDENCE/builder-internal-manifest-check.txt"
test "$(<"$BUILDER/R7E_GATE_DECISION.txt")" = 'R7E FINGERPRINT-BOUND BUILD EVIDENCE COMPLETE — READY FOR INDEPENDENT R7F V6 AUDIT'

mkdir -p "$CANDIDATE" "$SOURCE_TAR" "$BUILDER_STRESS"
cp -a "$BUILDER/BEARING_PRODUCTION_SOURCE/." "$CANDIDATE/"
tar -xf "$BUILDER/BEARING_FROZEN_SOURCE.tar" -C "$SOURCE_TAR"
cp -a "$BUILDER/BEARING_SCALE_SITE_500/." "$BUILDER_STRESS/"
rm "$BUILDER_STRESS/TEST_ONLY_DO_NOT_DEPLOY.txt"

python3 "$SCRIPTS/r7f-v3-tree-guard.py" compare "$CANDIDATE" "$SOURCE_TAR" "$EVIDENCE/source-tar-directory-parity.json" --source
python3 "$SCRIPTS/r7f-v3-tree-guard.py" manifest "$CANDIDATE" "$EVIDENCE/verifier-input-source-tree.json" --source
python3 "$SCRIPTS/r7f-v3-tree-guard.py" manifest "$BUILDER/BEARING_VERIFIED_DIST" "$EVIDENCE/builder-dist-tree.json"
python3 "$SCRIPTS/r7f-v3-tree-guard.py" manifest "$BUILDER_STRESS" "$EVIDENCE/builder-stress-tree.json"
python3 "$SCRIPTS/r7f-independent-source-audit.py" "$CANDIDATE" "$EVIDENCE/independent-source-audit.json"
python3 "$SCRIPTS/r7f-independent-link-audit.py" "$BUILDER/BEARING_VERIFIED_DIST" "$EVIDENCE/independent-builder-production-links.json"
python3 "$SCRIPTS/r7f-independent-link-audit.py" "$BUILDER/BEARING_SCALE_SITE_500" "$EVIDENCE/independent-builder-stress-links.json"
python3 "$SCRIPTS/r7f-independent-dist-audit.py" "$BUILDER/BEARING_VERIFIED_DIST" "$EVIDENCE/independent-builder-production-dist.json"
python3 "$SCRIPTS/r7f-independent-dist-audit.py" --stress "$BUILDER/BEARING_SCALE_SITE_500" "$EVIDENCE/independent-builder-stress-dist.json"
python3 "$SCRIPTS/r7f-evidence-gates.py" builder \
  --builder-root "$BUILDER" \
  --source-tree "$EVIDENCE/verifier-input-source-tree.json" \
  --dist-tree "$EVIDENCE/builder-dist-tree.json" \
  --stress-tree "$EVIDENCE/builder-stress-tree.json" \
  --repository "$GITHUB_REPOSITORY" \
  --expected-run "$BUILDER_RUN_ID" \
  --expected-commit "$BUILDER_COMMIT" \
  --expected-artifact-name "$BUILDER_ARTIFACT_NAME" \
  --expected-artifact-digest "$BUILDER_ARTIFACT_DIGEST" \
  --expected-source-archive "$BUILDER_SOURCE_ARCHIVE_SHA256" \
  --output "$EVIDENCE/builder-authenticity.json"

# Prove the verifier infrastructure itself is non-vacuous using negative controls.
mkdir -p "$ROOT/negative-link" "$ROOT/negative-dist" "$ROOT/negative-tree"
cp -a "$BUILDER/BEARING_VERIFIED_DIST/." "$ROOT/negative-link/"
python3 - <<'PY'
from pathlib import Path
p=Path('negative-link/index.html')
s=p.read_text()
p.write_text(s.replace('</body>', '<a href="/__r7f_deliberately_missing__/">negative control</a></body>'))
PY
set +e
python3 "$SCRIPTS/r7f-independent-link-audit.py" "$ROOT/negative-link" "$EVIDENCE/negative-control-link.json" > "$EVIDENCE/negative-control-link.stdout.txt" 2> "$EVIDENCE/negative-control-link.stderr.txt"
negative_link_status=$?
set -e
test "$negative_link_status" -ne 0
python3 - <<'PY'
import json
from pathlib import Path
x=json.loads(Path('evidence/negative-control-link.json').read_text())
if x.get('passed') is not False or not any(e.get('code')=='MISSING_TARGET' for e in x.get('errors',[])): raise SystemExit(1)
PY

cp -a "$BUILDER/BEARING_VERIFIED_DIST/." "$ROOT/negative-dist/"
python3 - <<'PY'
from pathlib import Path
p=Path('negative-dist/about/index.html')
s=p.read_text()
p.write_text(s.replace('</body>', '<script>globalThis.__r7f_negative__=true</script></body>'))
PY
set +e
python3 "$SCRIPTS/r7f-independent-dist-audit.py" "$ROOT/negative-dist" "$EVIDENCE/negative-control-dist.json" > "$EVIDENCE/negative-control-dist.stdout.txt" 2> "$EVIDENCE/negative-control-dist.stderr.txt"
negative_dist_status=$?
set -e
test "$negative_dist_status" -ne 0
python3 - <<'PY'
import json
from pathlib import Path
x=json.loads(Path('evidence/negative-control-dist.json').read_text())
if x.get('passed') is not False or not any(e.get('code')=='EXECUTABLE_SCRIPT_SCOPE' for e in x.get('findings',[])): raise SystemExit(1)
PY

cp -a "$CANDIDATE/." "$ROOT/negative-tree/"
printf '\nR7F negative control\n' >> "$ROOT/negative-tree/README.md"
set +e
python3 "$SCRIPTS/r7f-v3-tree-guard.py" compare "$CANDIDATE" "$ROOT/negative-tree" "$EVIDENCE/negative-control-tree.json" --source > "$EVIDENCE/negative-control-tree.stdout.txt" 2> "$EVIDENCE/negative-control-tree.stderr.txt"
negative_tree_status=$?
set -e
test "$negative_tree_status" -ne 0
python3 - <<'PY'
import json
from pathlib import Path
x=json.loads(Path('evidence/negative-control-tree.json').read_text())
if x.get('passed') is not False or 'README.md' not in x.get('changed',[]): raise SystemExit(1)
PY
rm -rf "$ROOT/negative-link" "$ROOT/negative-dist" "$ROOT/negative-tree"

# Independent clean build 1.
mkdir "$RUN1"
cp -a "$CANDIDATE/." "$RUN1/"
python3 "$SCRIPTS/r7f-v3-tree-guard.py" compare "$CANDIDATE" "$RUN1" "$EVIDENCE/run1-source-before.json" --source
(
  cd "$RUN1"
  npm run preflight:source > "$EVIDENCE/run1-preflight.stdout.txt" 2> "$EVIDENCE/run1-preflight.stderr.txt"
  /usr/bin/time -v -o "$EVIDENCE/run1-npm-ci.time.txt" npm ci --audit=false --fund=false > "$EVIDENCE/run1-npm-ci.stdout.txt" 2> "$EVIDENCE/run1-npm-ci.stderr.txt"
  /usr/bin/time -v -o "$EVIDENCE/run1-check.time.txt" npm run check > "$EVIDENCE/run1-check.stdout.txt" 2> "$EVIDENCE/run1-check.stderr.txt"
  /usr/bin/time -v -o "$EVIDENCE/run1-build.time.txt" npm run build > "$EVIDENCE/run1-build.stdout.txt" 2> "$EVIDENCE/run1-build.stderr.txt"
  npm run html:validate > "$EVIDENCE/run1-html.stdout.txt" 2> "$EVIDENCE/run1-html.stderr.txt"
  npm run links:validate > "$EVIDENCE/run1-candidate-links.stdout.txt" 2> "$EVIDENCE/run1-candidate-links.stderr.txt"
)
python3 "$SCRIPTS/r7f-v3-tree-guard.py" compare "$CANDIDATE" "$RUN1" "$EVIDENCE/run1-source-after-build.json" --source
python3 "$SCRIPTS/r7f-v3-tree-guard.py" manifest "$RUN1/dist" "$EVIDENCE/run1-dist-tree.json"
python3 "$SCRIPTS/r7f-independent-link-audit.py" "$RUN1/dist" "$EVIDENCE/independent-run1-production-links.json"
python3 "$SCRIPTS/r7f-independent-dist-audit.py" "$RUN1/dist" "$EVIDENCE/independent-run1-production-dist.json"

# Independent clean build 2.
mkdir "$RUN2"
cp -a "$CANDIDATE/." "$RUN2/"
python3 "$SCRIPTS/r7f-v3-tree-guard.py" compare "$CANDIDATE" "$RUN2" "$EVIDENCE/run2-source-before.json" --source
(
  cd "$RUN2"
  npm run preflight:source > "$EVIDENCE/run2-preflight.stdout.txt" 2> "$EVIDENCE/run2-preflight.stderr.txt"
  /usr/bin/time -v -o "$EVIDENCE/run2-npm-ci.time.txt" npm ci --audit=false --fund=false > "$EVIDENCE/run2-npm-ci.stdout.txt" 2> "$EVIDENCE/run2-npm-ci.stderr.txt"
  /usr/bin/time -v -o "$EVIDENCE/run2-check.time.txt" npm run check > "$EVIDENCE/run2-check.stdout.txt" 2> "$EVIDENCE/run2-check.stderr.txt"
  /usr/bin/time -v -o "$EVIDENCE/run2-build.time.txt" npm run build > "$EVIDENCE/run2-build.stdout.txt" 2> "$EVIDENCE/run2-build.stderr.txt"
  npm run html:validate > "$EVIDENCE/run2-html.stdout.txt" 2> "$EVIDENCE/run2-html.stderr.txt"
  npm run links:validate > "$EVIDENCE/run2-candidate-links.stdout.txt" 2> "$EVIDENCE/run2-candidate-links.stderr.txt"
)
python3 "$SCRIPTS/r7f-v3-tree-guard.py" compare "$CANDIDATE" "$RUN2" "$EVIDENCE/run2-source-after-build.json" --source
python3 "$SCRIPTS/r7f-v3-tree-guard.py" manifest "$RUN2/dist" "$EVIDENCE/run2-dist-tree.json"
python3 "$SCRIPTS/r7f-independent-link-audit.py" "$RUN2/dist" "$EVIDENCE/independent-run2-production-links.json"
python3 "$SCRIPTS/r7f-independent-dist-audit.py" "$RUN2/dist" "$EVIDENCE/independent-run2-production-dist.json"

python3 "$SCRIPTS/r7f-v3-tree-guard.py" compare "$RUN1/dist" "$RUN2/dist" "$EVIDENCE/run1-run2-reproducibility.json"
python3 "$SCRIPTS/r7f-v3-tree-guard.py" compare "$RUN1/dist" "$BUILDER/BEARING_VERIFIED_DIST" "$EVIDENCE/run1-builder-dist-parity.json"
python3 - <<'PY'
import json
from pathlib import Path
paths=[
 'evidence/independent-builder-production-links.json',
 'evidence/independent-run1-production-links.json',
 'evidence/independent-run2-production-links.json',
]
rows=[json.loads(Path(p).read_text()) for p in paths]
r={'passed':len({x['inventorySha256'] for x in rows})==1,'reports':[{k:x[k] for k in ('root','referenceCount','internalReferenceCount','documentReferenceCount','assetReferenceCount','inventorySha256','passed')} for x in rows]}
Path('evidence/independent-production-link-parity.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r,indent=2))
if not r['passed']: raise SystemExit(1)
PY

# Invalid fixture rejection and 500-record verifier build.
(
  cd "$RUN1"
  npm run validate:fixtures > "$EVIDENCE/invalid-fixtures.stdout.txt" 2> "$EVIDENCE/invalid-fixtures.stderr.txt"
  /usr/bin/time -v -o "$EVIDENCE/stress.time.txt" npm run test:stress > "$EVIDENCE/stress.stdout.txt" 2> "$EVIDENCE/stress.stderr.txt"
)
python3 "$SCRIPTS/r7f-v3-tree-guard.py" manifest "$RUN1/.r7e-tmp/stress/dist" "$EVIDENCE/verifier-stress-tree.json"
python3 "$SCRIPTS/r7f-v3-tree-guard.py" compare "$RUN1/.r7e-tmp/stress/dist" "$BUILDER_STRESS" "$EVIDENCE/verifier-builder-stress-parity.json"
mkdir "$VERIFIER_STRESS"
cp -a "$RUN1/.r7e-tmp/stress/dist/." "$VERIFIER_STRESS/"
printf 'TEST_ONLY — DO NOT DEPLOY\n' > "$VERIFIER_STRESS/TEST_ONLY_DO_NOT_DEPLOY.txt"
python3 "$SCRIPTS/r7f-independent-link-audit.py" "$VERIFIER_STRESS" "$EVIDENCE/independent-verifier-stress-links.json"
python3 "$SCRIPTS/r7f-independent-dist-audit.py" --stress "$VERIFIER_STRESS" "$EVIDENCE/independent-verifier-stress-dist.json"
cp "$RUN1/.r7e-tmp/stress/input-manifest.json" "$EVIDENCE/stress-input-manifest.json"
cp "$RUN1/.r7e-tmp/stress/lineage.json" "$EVIDENCE/stress-lineage.json"
python3 - <<'PY'
import json
from pathlib import Path
paths=['evidence/independent-builder-stress-links.json','evidence/independent-verifier-stress-links.json']
rows=[json.loads(Path(p).read_text()) for p in paths]
r={'passed':len({x['inventorySha256'] for x in rows})==1,'reports':[{k:x[k] for k in ('root','htmlFileCount','referenceCount','internalReferenceCount','documentReferenceCount','assetReferenceCount','inventorySha256','passed')} for x in rows]}
Path('evidence/independent-stress-link-parity.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r,indent=2))
if not r['passed']: raise SystemExit(1)
PY

# Browser, accessibility, Lighthouse, runtime network and deployment gates over verifier Run 1.
(
  cd "$RUN1"
  npx playwright install --with-deps chromium > "$EVIDENCE/playwright-install.stdout.txt" 2> "$EVIDENCE/playwright-install.stderr.txt"
  R7E_PLAYWRIGHT_SUITE=browser npm run test:browser > "$EVIDENCE/browser.stdout.txt" 2> "$EVIDENCE/browser.stderr.txt"
  R7E_PLAYWRIGHT_SUITE=axe npm run test:axe > "$EVIDENCE/axe.stdout.txt" 2> "$EVIDENCE/axe.stderr.txt"
  npm run test:lighthouse > "$EVIDENCE/lighthouse.stdout.txt" 2> "$EVIDENCE/lighthouse.stderr.txt"
  npm run network:audit > "$EVIDENCE/network.stdout.txt" 2> "$EVIDENCE/network.stderr.txt"
  npm run wrangler:validate > "$EVIDENCE/wrangler.stdout.txt" 2> "$EVIDENCE/wrangler.stderr.txt"
)
python3 "$SCRIPTS/r7f-evidence-gates.py" runtime --tmp-root "$RUN1/.r7e-tmp" --output "$EVIDENCE/runtime-evidence-gate.json"
cp "$RUN1/.r7e-tmp/playwright/browser-results.json" "$EVIDENCE/browser-playwright-results.json"
cp "$RUN1/.r7e-tmp/playwright/axe-results.json" "$EVIDENCE/axe-playwright-results.json"
cp -a "$RUN1/.r7e-tmp/axe" "$EVIDENCE/axe-raw"
cp "$RUN1/.r7e-tmp/lighthouse/summary.json" "$EVIDENCE/lighthouse-summary.json"
cp "$RUN1/.r7e-tmp/network/audit.json" "$EVIDENCE/network-audit.json"
find "$RUN1/.r7e-tmp/wrangler" -type f -print | sort > "$EVIDENCE/wrangler-files.txt"

# Final immutability and parity checks after every runtime gate.
python3 "$SCRIPTS/r7f-v3-tree-guard.py" compare "$CANDIDATE" "$RUN1" "$EVIDENCE/run1-source-final.json" --source
python3 "$SCRIPTS/r7f-v3-tree-guard.py" compare "$CANDIDATE" "$RUN2" "$EVIDENCE/run2-source-final.json" --source
python3 "$SCRIPTS/r7f-v3-tree-guard.py" compare "$RUN1/dist" "$BUILDER/BEARING_VERIFIED_DIST" "$EVIDENCE/final-builder-dist-parity.json"
python3 "$SCRIPTS/r7f-v3-tree-guard.py" compare "$RUN1/.r7e-tmp/stress/dist" "$BUILDER_STRESS" "$EVIDENCE/final-builder-stress-parity.json"
python3 "$SCRIPTS/r7f-independent-link-audit.py" "$RUN1/dist" "$EVIDENCE/independent-run1-production-links-final.json"
python3 "$SCRIPTS/r7f-independent-dist-audit.py" "$RUN1/dist" "$EVIDENCE/independent-run1-production-dist-final.json"

# Assemble the immutable success package.
rm -rf "$ARTIFACT"
mkdir -p "$ARTIFACT/VERIFIER_PRODUCTION_SOURCE" "$ARTIFACT/VERIFIER_DIST" "$ARTIFACT/VERIFIER_SCALE_SITE_500" "$ARTIFACT/R7F_EVIDENCE"
cp -a "$CANDIDATE/." "$ARTIFACT/VERIFIER_PRODUCTION_SOURCE/"
cp -a "$RUN1/dist/." "$ARTIFACT/VERIFIER_DIST/"
cp -a "$VERIFIER_STRESS/." "$ARTIFACT/VERIFIER_SCALE_SITE_500/"
cp -a "$EVIDENCE/." "$ARTIFACT/R7F_EVIDENCE/"
cp -a "$RUN1/.r7e-tmp" "$ARTIFACT/R7F_RUN1_TMP"
printf 'R7F HARDENED INDEPENDENT VERIFICATION COMPLETE — R7 TECHNICAL ARCHITECTURE MAY CLOSE\n' > "$ARTIFACT/R7F_GATE_DECISION.txt"

python3 "$SCRIPTS/r7f-v3-tree-guard.py" compare "$CANDIDATE" "$ARTIFACT/VERIFIER_PRODUCTION_SOURCE" "$ARTIFACT/R7F_EVIDENCE/staged-source-parity.json" --source
python3 "$SCRIPTS/r7f-v3-tree-guard.py" compare "$RUN1/dist" "$ARTIFACT/VERIFIER_DIST" "$ARTIFACT/R7F_EVIDENCE/staged-dist-parity.json"
rm "$ARTIFACT/VERIFIER_SCALE_SITE_500/TEST_ONLY_DO_NOT_DEPLOY.txt"
python3 "$SCRIPTS/r7f-v3-tree-guard.py" compare "$RUN1/.r7e-tmp/stress/dist" "$ARTIFACT/VERIFIER_SCALE_SITE_500" "$ARTIFACT/R7F_EVIDENCE/staged-stress-parity.json"
printf 'TEST_ONLY — DO NOT DEPLOY\n' > "$ARTIFACT/VERIFIER_SCALE_SITE_500/TEST_ONLY_DO_NOT_DEPLOY.txt"

python3 - <<'PY'
import json, os
from pathlib import Path
root=Path('artifact')
required={
 'gate':root/'R7F_GATE_DECISION.txt',
 'source':root/'VERIFIER_PRODUCTION_SOURCE/package.json',
 'dist':root/'VERIFIER_DIST/index.html',
 'stress':root/'VERIFIER_SCALE_SITE_500/index.html',
 'stressMarker':root/'VERIFIER_SCALE_SITE_500/TEST_ONLY_DO_NOT_DEPLOY.txt',
 'builderAuthenticity':root/'R7F_EVIDENCE/builder-authenticity.json',
 'sourceAudit':root/'R7F_EVIDENCE/independent-source-audit.json',
 'builderProductionLinks':root/'R7F_EVIDENCE/independent-builder-production-links.json',
 'builderStressLinks':root/'R7F_EVIDENCE/independent-builder-stress-links.json',
 'run1Links':root/'R7F_EVIDENCE/independent-run1-production-links-final.json',
 'run1DistAudit':root/'R7F_EVIDENCE/independent-run1-production-dist-final.json',
 'runtime':root/'R7F_EVIDENCE/runtime-evidence-gate.json',
 'reproducibility':root/'R7F_EVIDENCE/run1-run2-reproducibility.json',
 'builderParity':root/'R7F_EVIDENCE/final-builder-dist-parity.json',
 'stressParity':root/'R7F_EVIDENCE/final-builder-stress-parity.json',
 'negativeLink':root/'R7F_EVIDENCE/negative-control-link.json',
 'negativeDist':root/'R7F_EVIDENCE/negative-control-dist.json',
 'negativeTree':root/'R7F_EVIDENCE/negative-control-tree.json',
}
checks={f'present:{name}':path.exists() for name,path in required.items()}
checks.update({
 'gate-ready':(root/'R7F_GATE_DECISION.txt').read_text().strip()=='R7F HARDENED INDEPENDENT VERIFICATION COMPLETE — R7 TECHNICAL ARCHITECTURE MAY CLOSE',
 'builder-authenticity':json.loads((root/'R7F_EVIDENCE/builder-authenticity.json').read_text())['passed'] is True,
 'source-audit':json.loads((root/'R7F_EVIDENCE/independent-source-audit.json').read_text())['passed'] is True,
 'production-links':json.loads((root/'R7F_EVIDENCE/independent-run1-production-links-final.json').read_text())['passed'] is True,
 'production-dist':json.loads((root/'R7F_EVIDENCE/independent-run1-production-dist-final.json').read_text())['passed'] is True,
 'stress-links':json.loads((root/'R7F_EVIDENCE/independent-verifier-stress-links.json').read_text())['passed'] is True,
 'stress-dist':json.loads((root/'R7F_EVIDENCE/independent-verifier-stress-dist.json').read_text())['passed'] is True,
 'runtime':json.loads((root/'R7F_EVIDENCE/runtime-evidence-gate.json').read_text())['passed'] is True,
 'reproducibility':json.loads((root/'R7F_EVIDENCE/run1-run2-reproducibility.json').read_text())['passed'] is True,
 'builder-parity':json.loads((root/'R7F_EVIDENCE/final-builder-dist-parity.json').read_text())['passed'] is True,
 'stress-parity':json.loads((root/'R7F_EVIDENCE/final-builder-stress-parity.json').read_text())['passed'] is True,
 'negative-link-detected':json.loads((root/'R7F_EVIDENCE/negative-control-link.json').read_text())['passed'] is False,
 'negative-dist-detected':json.loads((root/'R7F_EVIDENCE/negative-control-dist.json').read_text())['passed'] is False,
 'negative-tree-detected':json.loads((root/'R7F_EVIDENCE/negative-control-tree.json').read_text())['passed'] is False,
 'no-node-modules':not any(p.name=='node_modules' for p in root.rglob('node_modules')),
 'production-no-synthetic':not any((root/'VERIFIER_DIST/work').glob('synthetic-test-record-*')),
 'stress-500':len(list((root/'VERIFIER_SCALE_SITE_500/work').glob('synthetic-test-record-*/index.html')))==500,
 'screenshots-at-least-40':len(list((root/'R7F_RUN1_TMP/screenshots').glob('*.png')))>=40,
})
result={
 'passed':all(checks.values()),
 'repository':os.environ['GITHUB_REPOSITORY'],
 'verifierCommit':os.environ['GITHUB_SHA'],
 'verifierRunId':os.environ['GITHUB_RUN_ID'],
 'builderRunId':os.environ['BUILDER_RUN_ID'],
 'builderCommit':os.environ['BUILDER_COMMIT'],
 'builderArtifactId':os.environ['BUILDER_ARTIFACT_ID'],
 'builderArtifactName':os.environ['BUILDER_ARTIFACT_NAME'],
 'builderArtifactDigest':os.environ['BUILDER_ARTIFACT_DIGEST'],
 'builderSourceArchiveSha256':os.environ['BUILDER_SOURCE_ARCHIVE_SHA256'],
 'checks':checks,
 'failedChecks':[name for name,passed in checks.items() if not passed],
}
(root/'R7F_PACKAGE_VALIDATION.json').write_text(json.dumps(result,indent=2)+'\n')
(root/'R7F_EVIDENCE_INDEX.json').write_text(json.dumps({name:str(path.relative_to(root)) for name,path in required.items()},indent=2)+'\n')
print(json.dumps(result,indent=2))
if not result['passed']: raise SystemExit(1)
PY

(
  cd "$ARTIFACT"
  find . -type f ! -name 'R7F_ARTIFACT_SHA256SUMS.txt' -print0 | sort -z | xargs -0 sha256sum > R7F_ARTIFACT_SHA256SUMS.txt
  sha256sum --check --strict R7F_ARTIFACT_SHA256SUMS.txt
)
SUCCESS=1
trap - EXIT
printf 'R7F v3 completed successfully.\n'
