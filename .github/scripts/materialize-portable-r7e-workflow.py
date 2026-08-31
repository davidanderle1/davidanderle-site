#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

SOURCE = Path('.github/workflows/r7e-full-history-reconciled-verification.yml')
TARGET = Path('.github/workflows/r7e-portable-json-schema-verification.yml')


def replace_exact(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected one anchor, found {count}: {old!r}')
    return text.replace(old, new, 1)


def main() -> None:
    text = SOURCE.read_text(encoding='utf-8')

    replacements = [
        ('name: R7E full-history reconciled native Astro verification', 'name: R7E portable JSON Schema native Astro verification', 'workflow name'),
        ('r7e-full-history-reconciled-verification-20260831', 'r7e-portable-json-schema-verification-20260831', 'branch'),
        ('r7e-full-history-reconciled-${{ github.ref }}', 'r7e-portable-json-schema-${{ github.ref }}', 'concurrency'),
        ('Checkout immutable reconciliation branch', 'Checkout immutable portable-schema branch', 'checkout name'),
        ("if not result['passed'] or len(actual) != 131:", "if not result['passed'] or len(actual) != 146:", 'source file count'),
        ("test \"$(grep -c 'EXPECTED FAILURE (exit 1)' ../evidence/invalid-fixtures.stdout.txt)\" -eq 28", "test \"$(grep -c 'EXPECTED FAILURE (exit 1)' ../evidence/invalid-fixtures.stdout.txt)\" -eq 29", 'fixture count'),
        ('.github/workflows/r7e-full-history-reconciled-verification.yml | tee evidence/builder-infrastructure.sha256', '.github/workflows/r7e-portable-json-schema-verification.yml | tee evidence/builder-infrastructure.sha256', 'infrastructure manifest'),
        ("'schema':'R7E_FULL_HISTORY_RECONCILED_CANDIDATE_IDENTITY_V1'", "'schema':'R7E_PORTABLE_JSON_SCHEMA_CANDIDATE_IDENTITY_V1'", 'candidate schema'),
        ("'workflowSha256':sha('.github/workflows/r7e-full-history-reconciled-verification.yml')", "'workflowSha256':sha('.github/workflows/r7e-portable-json-schema-verification.yml')", 'workflow digest'),
        ("'sourceCorrectionLayer':'NONE — full-history reconciliation folded into canonical packed source'", "'sourceCorrectionLayer':'NONE — full-history reconciliation and portable Draft 2020-12 contract folded into canonical packed source'", 'source layer'),
        ("printf 'R7E FULL-HISTORY RECONCILED BUILD EVIDENCE COMPLETE — READY FOR INDEPENDENT R7F\\n'", "printf 'R7E PORTABLE JSON SCHEMA BUILD EVIDENCE COMPLETE — READY FOR INDEPENDENT R7F\\n'", 'success gate'),
        ("printf 'R7E FULL-HISTORY RECONCILED BUILD EVIDENCE INCOMPLETE — DO NOT START R7F\\n'", "printf 'R7E PORTABLE JSON SCHEMA BUILD EVIDENCE INCOMPLETE — DO NOT START R7F\\n'", 'failure gate'),
        ("=='R7E FULL-HISTORY RECONCILED BUILD EVIDENCE COMPLETE — READY FOR INDEPENDENT R7F'", "=='R7E PORTABLE JSON SCHEMA BUILD EVIDENCE COMPLETE — READY FOR INDEPENDENT R7F'", 'gate validation'),
        ("identity.get('schema')=='R7E_FULL_HISTORY_RECONCILED_CANDIDATE_IDENTITY_V1'", "identity.get('schema')=='R7E_PORTABLE_JSON_SCHEMA_CANDIDATE_IDENTITY_V1'", 'identity validation'),
        ("'schema':'R7E_FULL_HISTORY_RECONCILED_PACKAGE_VALIDATION_V1'", "'schema':'R7E_PORTABLE_JSON_SCHEMA_PACKAGE_VALIDATION_V1'", 'package schema'),
        ('Upload full-history reconciled R7E evidence', 'Upload portable JSON Schema R7E evidence', 'upload name'),
        ('name: r7e-full-history-reconciled-evidence-${{ github.sha }}', 'name: r7e-portable-json-schema-evidence-${{ github.sha }}', 'artifact name'),
    ]
    for old, new, label in replacements:
        text = replace_exact(text, old, new, label)

    quoted_old = "'.github/workflows/r7e-full-history-reconciled-verification.yml'"
    quoted_new = "'.github/workflows/r7e-portable-json-schema-verification.yml'"
    quoted_count = text.count(quoted_old)
    if quoted_count != 2:
        raise SystemExit(f'workflow path anchors: expected two, found {quoted_count}')
    text = text.replace(quoted_old, quoted_new)

    old_required = "for required in package.json package-lock.json .node-version .nvmrc astro.config.mjs src/content.config.ts docs/R7_HISTORY_RECONCILIATION.md src/components/HomepageRecordPreview.astro src/components/WritingRecordPreview.astro src/lib/profile-copy.ts scripts/build-axe-fingerprint-adjudication.mjs; do"
    new_required = "for required in package.json package-lock.json .node-version .nvmrc astro.config.mjs src/content.config.ts src/content-schemas.ts docs/R7_HISTORY_RECONCILIATION.md docs/PORTABLE_JSON_SCHEMA.md schemas/index.json schemas/canonical-content.schema.json src/components/HomepageRecordPreview.astro src/components/WritingRecordPreview.astro src/lib/profile-copy.ts scripts/build-axe-fingerprint-adjudication.mjs scripts/generate-json-schemas.mjs scripts/validate-json-schema.mjs scripts/verify-json-schema-drift.mjs; do"
    text = replace_exact(text, old_required, new_required, 'required paths')

    old_lock = "const ok=p.packageManager==='npm@11.19.0' && p.engines?.node==='24.20.0' && p.engines?.npm==='11.19.0' && l.lockfileVersion===3 && count>=500 && !l.r7eBootstrapStatus && axeScript.includes('build-axe-fingerprint-adjudication.mjs');"
    new_lock = "const ok=p.packageManager==='npm@11.19.0' && p.engines?.node==='24.20.0' && p.engines?.npm==='11.19.0' && l.lockfileVersion===3 && count>=500 && !l.r7eBootstrapStatus && axeScript.includes('build-axe-fingerprint-adjudication.mjs') && p.devDependencies?.ajv==='8.20.0' && l.packages?.['node_modules/ajv']?.version==='8.20.0' && ['schema:generate','schema:check','schema:contract','schema:validate:stress'].every((name)=>typeof p.scripts?.[name]==='string');"
    text = replace_exact(text, old_lock, new_lock, 'toolchain lock')

    portable_step = '''      - name: Verify portable Draft 2020-12 schema contract
        working-directory: candidate
        shell: bash
        run: |
          set -euo pipefail
          npm ci --audit=false --fund=false > ../evidence/portable-schema-npm-ci.stdout.txt 2> ../evidence/portable-schema-npm-ci.stderr.txt
          rm -rf public/assets/portrait public/assets/js public/artifacts src/data/generated dist .astro .r7e-tmp
          npm run schema:check > ../evidence/portable-schema-check.stdout.txt 2> ../evidence/portable-schema-check.stderr.txt
          npm run schema:contract > ../evidence/portable-schema-contract.stdout.txt 2> ../evidence/portable-schema-contract.stderr.txt
          test "$(find schemas -maxdepth 1 -type f -name '*.json' | wc -l)" -eq 9
          jq -e '.contractVersion=="1.0.0" and .dialect=="https://json-schema.org/draft/2020-12/schema" and (.schemas|length)==8' schemas/index.json >/dev/null
          for file in schemas/*.schema.json; do
            jq -e '."$schema"=="https://json-schema.org/draft/2020-12/schema" and ."x-contract-version"=="1.0.0"' "$file" >/dev/null
          done
          cp schemas/index.json ../evidence/portable-schema-index.json
          find schemas -maxdepth 1 -type f -name '*.json' -print0 | sort -z | xargs -0 sha256sum > ../evidence/portable-schema-files.sha256
          rm -rf node_modules public/assets/portrait public/assets/js public/artifacts src/data/generated dist .astro .r7e-tmp

'''
    freeze_anchor = '      - name: Freeze source and deterministic transport\n'
    text = replace_exact(text, freeze_anchor, portable_step + freeze_anchor, 'freeze step')

    run1_anchor = "          /usr/bin/time -v -o ../evidence/run1-check.time.txt npm run check > ../evidence/run1-check.stdout.txt 2> ../evidence/run1-check.stderr.txt\n"
    run1_insert = "          npm run schema:check > ../evidence/run1-schema-check.stdout.txt 2> ../evidence/run1-schema-check.stderr.txt\n          npm run schema:contract > ../evidence/run1-schema-contract.stdout.txt 2> ../evidence/run1-schema-contract.stderr.txt\n"
    text = replace_exact(text, run1_anchor, run1_insert + run1_anchor, 'run1 schema')

    run2_anchor = "          /usr/bin/time -v -o ../evidence/run2-check.time.txt npm run check > ../evidence/run2-check.stdout.txt 2> ../evidence/run2-check.stderr.txt\n"
    run2_insert = "          npm run schema:check > ../evidence/run2-schema-check.stdout.txt 2> ../evidence/run2-schema-check.stderr.txt\n          npm run schema:contract > ../evidence/run2-schema-contract.stdout.txt 2> ../evidence/run2-schema-contract.stderr.txt\n"
    text = replace_exact(text, run2_anchor, run2_insert + run2_anchor, 'run2 schema')

    stress_anchor = "          /usr/bin/time -v -o ../evidence/stress.time.txt npm run test:stress > ../evidence/stress.stdout.txt 2> ../evidence/stress.stderr.txt\n"
    stress_insert = "          npm run schema:validate:stress > ../evidence/stress-schema.stdout.txt 2> ../evidence/stress-schema.stderr.txt\n"
    text = replace_exact(text, stress_anchor, stress_anchor + stress_insert, 'stress schema')

    identity_anchor = "            'axeIncompleteNodeCount':axe['metrics']['totalIncompleteNodes'],\n"
    identity_insert = "            'portableSchemaContractVersion':'1.0.0',\n            'portableSchemaDialect':'https://json-schema.org/draft/2020-12/schema',\n            'portableSchemaIndexSha256':sha('frozen/schemas/index.json'),\n            'portableSchemaSetSha256':sha('evidence/portable-schema-files.sha256'),\n"
    text = replace_exact(text, identity_anchor, identity_anchor + identity_insert, 'identity schema')

    package_anchor = "            'historyReconciliationPresent':(root/'BEARING_PRODUCTION_SOURCE/docs/R7_HISTORY_RECONCILIATION.md').is_file(),\n"
    package_insert = "            'portableSchemaDocumentationPresent':(root/'BEARING_PRODUCTION_SOURCE/docs/PORTABLE_JSON_SCHEMA.md').is_file(),\n            'portableSchemaIndexPresent':(root/'BEARING_PRODUCTION_SOURCE/schemas/index.json').is_file(),\n            'portableSchemaCanonicalPresent':(root/'BEARING_PRODUCTION_SOURCE/schemas/canonical-content.schema.json').is_file(),\n            'portableSchemaEvidencePresent':(root/'R7E_EVIDENCE/portable-schema-index.json').is_file() and (root/'R7E_EVIDENCE/portable-schema-files.sha256').is_file(),\n"
    text = replace_exact(text, package_anchor, package_anchor + package_insert, 'package schema')

    old_index = "'wrangler':'R7E_EVIDENCE/wrangler-files.txt'}"
    new_index = "'wrangler':'R7E_EVIDENCE/wrangler-files.txt','portableSchemaIndex':'R7E_EVIDENCE/portable-schema-index.json','portableSchemaHashes':'R7E_EVIDENCE/portable-schema-files.sha256'}"
    text = replace_exact(text, old_index, new_index, 'evidence index')

    forbidden = ('R7E FULL-HISTORY RECONCILED', 'r7e-full-history-reconciled')
    remaining = [token for token in forbidden if token in text]
    if remaining:
        raise SystemExit(f'legacy workflow identity remains: {remaining}')

    required = (
        'R7E portable JSON Schema native Astro verification',
        'r7e-portable-json-schema-verification-20260831',
        'R7E_PORTABLE_JSON_SCHEMA_CANDIDATE_IDENTITY_V1',
        'R7E PORTABLE JSON SCHEMA BUILD EVIDENCE COMPLETE',
        'portable-schema-index.json',
        'schema:contract',
        'len(actual) != 146',
        '-eq 29',
    )
    missing = [token for token in required if token not in text]
    if missing:
        raise SystemExit(f'generated workflow missing contracts: {missing}')

    TARGET.write_text(text, encoding='utf-8')
    print(f'generated={TARGET} bytes={TARGET.stat().st_size}')


if __name__ == '__main__':
    main()
