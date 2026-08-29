#!/usr/bin/env bash
set -euo pipefail

ROOT="$PWD"
SOURCE="$ROOT/BEARING_PRODUCTION_SOURCE"
BOOTSTRAP="$ROOT/R7E_BOOTSTRAP_EVIDENCE"
RUNNER=(python3 "$ROOT/r7e/run_command.py")

rm -rf "$SOURCE" "$BOOTSTRAP" "$ROOT/R7E_OUTPUT" \
  "$ROOT/r7e-negative-schema" "$ROOT/r7e-negative-crossref" \
  "$ROOT/r7e-negative-duplicate" "$ROOT/r7e-negative-photo" "$ROOT/r7e-negative-js"
mkdir -p "$BOOTSTRAP"

"${RUNNER[@]}" --evidence "$BOOTSTRAP" --id 000-node-version --artifact . -- node --version
"${RUNNER[@]}" --evidence "$BOOTSTRAP" --id 001-npm-upgrade -- npm install --global npm@11.19.0
"${RUNNER[@]}" --evidence "$BOOTSTRAP" --id 002-reference-builder --artifact "$SOURCE" -- python3 r7e/reference_builder_v2.py --output "$SOURCE" --workspace "$ROOT"
mkdir -p "$SOURCE/evidence/bootstrap-host"
cp -a "$BOOTSTRAP/." "$SOURCE/evidence/bootstrap-host/"

cd "$SOURCE"
R=(python3 scripts/run_evidence.py --evidence evidence)

"${R[@]}" --id 010-lockfile --artifact package-lock.json -- npm install --package-lock-only --ignore-scripts
"${R[@]}" --id 020-npm-ci --artifact node_modules/.package-lock.json -- npm ci
"${R[@]}" --id 030-toolchain-environment --artifact evidence/reports/toolchain-environment.json -- node scripts/capture-toolchain.mjs
"${R[@]}" --id 040-official-sources --artifact evidence/reports/official-source-verification.json -- node scripts/verify-official-sources.mjs
"${R[@]}" --id 050-source-verification --artifact evidence/reports/source-verification.json -- node scripts/verify-source.mjs
"${R[@]}" --id 060-astro-check -- npx astro check
"${R[@]}" --id 070-content-validation --artifact evidence/reports/content-validation-canonical.json -- node scripts/validate-content.mjs
"${R[@]}" --id 080-portrait-selection --soft --artifact evidence/reports/portrait-source-selection.json -- node scripts/select-portrait-source.mjs ..
"${R[@]}" --id 090-image-processing --artifact public/media/portrait-manifest.json --artifact evidence/reports/image-processing.json -- node scripts/process-images.mjs
"${R[@]}" --id 100-base-build --artifact dist -- bash -lc '/usr/bin/time -v npm run build'
"${R[@]}" --id 110-dist-verification --artifact evidence/reports/dist-verification.json -- node scripts/verify-dist.mjs dist
"${R[@]}" --id 120-playwright-install --soft -- npx playwright install --with-deps chromium
"${R[@]}" --id 130-browser-tests --soft --artifact evidence/browser -- npx playwright test
"${R[@]}" --id 140-lighthouse --soft --artifact evidence/lighthouse -- node scripts/run-lighthouse.mjs
"${R[@]}" --id 150-wrangler-dry-run --soft --artifact evidence/wrangler-dry-run -- npx wrangler deploy --dry-run --outdir evidence/wrangler-dry-run
"${R[@]}" --id 160-wrangler-preview --soft --artifact evidence/wrangler-preview -- node scripts/test-wrangler-preview.mjs
"${R[@]}" --id 170-scale-generate --artifact evidence/scale/generated-records-manifest.json -- node scripts/generate-scale-fixtures.mjs 500
"${R[@]}" --id 180-scale-content-validation --env R7E_SCALE=1 --artifact evidence/reports/content-validation-scale.json -- node scripts/validate-content.mjs
"${R[@]}" --id 190-scale-build --env R7E_SCALE=1 --env R7E_OUT_DIR=dist-scale --artifact dist-scale -- bash -lc '/usr/bin/time -v npx astro build'
"${R[@]}" --id 200-scale-verification --artifact evidence/reports/scale-verification.json -- node scripts/verify-scale.mjs
"${R[@]}" --id 210-scale-clean -- node scripts/clear-scale-fixtures.mjs

"${R[@]}" --id 220-neg-schema-prepare -- node scripts/prepare-negative-fixture.mjs schema ../r7e-negative-schema
cd "$ROOT/r7e-negative-schema"
python3 "$SOURCE/scripts/run_evidence.py" --evidence "$SOURCE/evidence" --id 221-neg-schema-astro --expect nonzero -- npx astro build
cd "$SOURCE"

"${R[@]}" --id 230-neg-crossref-prepare -- node scripts/prepare-negative-fixture.mjs crossref ../r7e-negative-crossref
cd "$ROOT/r7e-negative-crossref"
python3 "$SOURCE/scripts/run_evidence.py" --evidence "$SOURCE/evidence" --id 231-neg-crossref-validation --expect nonzero -- node scripts/validate-content.mjs
cd "$SOURCE"

"${R[@]}" --id 240-neg-duplicate-prepare -- node scripts/prepare-negative-fixture.mjs duplicate ../r7e-negative-duplicate
cd "$ROOT/r7e-negative-duplicate"
python3 "$SOURCE/scripts/run_evidence.py" --evidence "$SOURCE/evidence" --id 241-neg-duplicate-validation --expect nonzero -- node scripts/validate-content.mjs
cd "$SOURCE"

"${R[@]}" --id 250-neg-photo-prepare -- node scripts/prepare-negative-fixture.mjs photo-upscale ../r7e-negative-photo
cd "$ROOT/r7e-negative-photo"
python3 "$SOURCE/scripts/run_evidence.py" --evidence "$SOURCE/evidence" --id 251-neg-photo-process --expect nonzero -- node scripts/process-images.mjs
cd "$SOURCE"

"${R[@]}" --id 260-neg-js-prepare -- node scripts/prepare-negative-fixture.mjs ordinary-js ../r7e-negative-js
cd "$ROOT/r7e-negative-js"
python3 "$SOURCE/scripts/run_evidence.py" --evidence "$SOURCE/evidence" --id 261-neg-js-dist --expect nonzero -- node scripts/verify-dist.mjs dist
cd "$SOURCE"

"${R[@]}" --id 270-reproducibility --artifact evidence/reproducibility/report.json -- node scripts/verify-reproducibility.mjs
"${R[@]}" --id 280-npm-audit --soft --expect any -- npm audit --json
mkdir -p evidence/supply-chain
"${R[@]}" --id 290-sbom --soft -- bash -lc 'npm sbom --sbom-format=cyclonedx > evidence/supply-chain/sbom.cdx.json'
"${R[@]}" --id 300-npm-ls --soft -- npm ls --all --json

rm -rf "$ROOT/r7e-negative-schema" "$ROOT/r7e-negative-crossref" "$ROOT/r7e-negative-duplicate" "$ROOT/r7e-negative-photo" "$ROOT/r7e-negative-js"
node scripts/finalize-evidence.mjs
"${R[@]}" --id 310-final-gate --artifact R7E_FINAL_GATE.json --artifact evidence/reports/R7E_FINAL_GATE.json -- node scripts/verify-final-gate.mjs
python3 scripts/package_r7e.py
