#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile

BASE_PATH = Path(__file__).with_name('r7-portable-external-audit-v2.py')
spec = importlib.util.spec_from_file_location('audit_base', BASE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit('cannot load external-audit primitives')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

AuditFailure = base.AuditFailure
require = base.require
load = base.load
unique = base.unique
sha256_file = base.sha256_file
safe_extract = base.safe_extract
verify_manifest = base.verify_manifest
regenerate_manifest = base.regenerate_manifest
schema_audit = base.schema_audit

BUILDER_REPLACEMENTS = [
    ('r7e-portable-json-schema-verification-20260831', 'r7e-portable-authoritative-v3-20260901'),
    ('.github/r7-status/portable-r7e-v2.json', '.github/r7-status/portable-r7e-v3.json'),
    ('R7E_PORTABLE_JSON_SCHEMA_AUTHORITATIVE_TUPLE_V2', 'R7E_PORTABLE_JSON_SCHEMA_AUTHORITATIVE_TUPLE_V3'),
]
PATH_CORRECTIONS = [
    ('../../../r7f-evidence', '$GITHUB_WORKSPACE/r7f-evidence', 'absolute evidence paths'),
    ('cd r7f-input/run1', 'cd "$GITHUB_WORKSPACE/r7f-input/run1"', 'absolute candidate run directory'),
    ("root=Path('r7f-evidence/lighthouse')", "root=Path(__import__('os').environ['GITHUB_WORKSPACE'])/'r7f-evidence/lighthouse'", 'absolute Lighthouse report root'),
    ("Path('r7f-evidence/LIGHTHOUSE_AUDIT.json').write_text", "(Path(__import__('os').environ['GITHUB_WORKSPACE'])/'r7f-evidence/LIGHTHOUSE_AUDIT.json').write_text", 'absolute Lighthouse summary output'),
]


def semantic(root: Path, status: dict, builder_extract: Path | None) -> dict:
    decision_path = unique(root, 'R7F_PORTABLE_V2_DECISION.json')
    tuple_path = unique(root, 'R7E_TUPLE.json')
    preaudit_path = unique(root, 'R7E_PREAUDIT.json')
    execution_path = unique(root, 'R7F_PLAN_EXECUTION.json')
    original_path = unique(root, 'R7F_ORIGINAL_SOURCE_PLAN.yml')
    builder_plan_path = unique(root, 'R7F_BUILDER_V3_SOURCE_PLAN.yml')
    builder_diff_path = unique(root, 'R7F_BUILDER_V3_BINDING.diff')
    builder_binding_path = unique(root, 'R7F_BUILDER_V3_BINDING.json')
    final_plan_path = unique(root, 'R7F_FINAL_CORRECTED_PLAN.yml')
    correction_diff_path = unique(root, 'R7F_PLAN_CORRECTION.diff')
    browser_path = unique(root, 'BROWSER_AUDIT.json')
    lighthouse_path = unique(root, 'LIGHTHOUSE_AUDIT.json')
    reproducibility_path = unique(root, 'REPRODUCIBILITY.json')
    stress_path = unique(root, 'STRESS_DIST_TREE.json')

    decision = load(decision_path)
    builder_tuple = load(tuple_path)
    preaudit = load(preaudit_path)
    execution = load(execution_path)
    binding = load(builder_binding_path)
    browser = load(browser_path)
    lighthouse = load(lighthouse_path)
    reproducibility = load(reproducibility_path)
    stress = load(stress_path)

    original = original_path.read_text(encoding='utf-8')
    expected_builder = original
    expected_builder_counts = {}
    for old, new in BUILDER_REPLACEMENTS:
        count = expected_builder.count(old)
        require(count > 0, f'original plan lacks builder binding anchor: {old}')
        expected_builder_counts[old] = count
        expected_builder = expected_builder.replace(old, new)
    actual_builder = builder_plan_path.read_text(encoding='utf-8')
    expected_final = expected_builder
    expected_corrections = []
    for old, new, label in PATH_CORRECTIONS:
        count = expected_final.count(old)
        require(count > 0, f'builder-bound plan lacks path anchor: {old}')
        expected_final = expected_final.replace(old, new)
        expected_corrections.append({'label': label, 'from': old, 'to': new, 'count': count})

    checks = {
        'status-schema': status.get('schema') == 'R7F_PORTABLE_JSON_SCHEMA_AUTHORITATIVE_TUPLE_V5',
        'status-pass': status.get('passed') is True,
        'status-correction-model': status.get('correctionModel') == 'EXACT_FOUR_CLASS_PATH_REPAIR',
        'decision-pass': decision.get('passed') is True and decision.get('decision') == 'R7F_PORTABLE_INDEPENDENT_PASS',
        'decision-commit': decision.get('verifier', {}).get('commit') == status.get('commit'),
        'decision-run': decision.get('verifier', {}).get('runId') == status.get('runId'),
        'decision-digest': sha256_file(decision_path) == status.get('decisionSha256'),
        'execution-digest': sha256_file(execution_path) == status.get('planExecutionSha256'),
        'binding-digest': sha256_file(builder_binding_path) == status.get('builderBindingSha256'),
        'builder-status-commit': builder_tuple.get('commit') == status.get('builder', {}).get('commit'),
        'builder-status-digest': builder_tuple.get('artifact', {}).get('digest') == status.get('builder', {}).get('artifactDigest'),
        'builder-schema': builder_tuple.get('schema') == 'R7E_PORTABLE_JSON_SCHEMA_AUTHORITATIVE_TUPLE_V3',
        'builder-pass': builder_tuple.get('passed') is True,
        'builder-branch': builder_tuple.get('branch') == 'r7e-portable-authoritative-v3-20260901',
        'builder-source-hash': builder_tuple.get('sourceArchiveSha256') == '764271738ad8578de7d89c522d9cedd1a22ce00d1b8e5d06b271903b52a3923d',
        'preaudit-pass': preaudit.get('passed') is True and preaudit.get('sourceFileCount') == 146,
        'binding-pass': binding.get('passed') is True,
        'binding-counts-exact': binding.get('replacements') == expected_builder_counts,
        'builder-plan-byte-exact': actual_builder == expected_builder,
        'builder-diff-present': builder_diff_path.stat().st_size > 0,
        'correction-diff-present': correction_diff_path.stat().st_size > 0,
        'final-plan-byte-exact': final_plan_path.read_text(encoding='utf-8') == expected_final,
        'execution-schema': execution.get('schema') == 'R7F_CORRECTED_PLAN_EXECUTION_V5',
        'execution-pass': execution.get('passed') is True,
        'execution-corrections-exact': execution.get('corrections') == expected_corrections,
        'execution-total-count': execution.get('totalReplacementCount') == sum(row['count'] for row in expected_corrections),
        'execution-skipped-status-only': execution.get('skippedRunSteps') == ['Persist exact authoritative R7F tuple'],
        'execution-all-run-steps-pass': bool(execution.get('executed')) and all(row.get('exitCode') == 0 for row in execution.get('executed', [])),
        'browser-pass': browser.get('passed') is True,
        'browser-page-checks': browser.get('metrics', {}).get('pageChecks') == 168,
        'axe-zero-violations': browser.get('metrics', {}).get('axeViolationCount') == 0,
        'network-zero-off-origin': browser.get('metrics', {}).get('offOriginRequestCount') == 0,
        'lighthouse-pass': lighthouse.get('passed') is True and lighthouse.get('reportCount') == 4,
        'reproducibility-pass': reproducibility.get('passed') is True and reproducibility.get('fileCount') == 34,
        'stress-output': stress.get('fileCount', 0) >= 534,
    }

    schema_hashes, schema_checks = schema_audit(root)
    checks.update({f'schema:{key}': value for key, value in schema_checks.items()})
    checks['preaudit-schema-hashes-match'] = all(preaudit.get('schemaHashes', {}).get(name) == digest for name, digest in schema_hashes.items())

    if builder_extract is not None:
        builder_manifest = verify_manifest(builder_extract, 'R7E_ARTIFACT_SHA256SUMS.txt')
        builder_source = unique(builder_manifest['root'], 'BEARING_PRODUCTION_SOURCE')
        require(builder_source.is_dir(), 'builder source is not a directory')
        builder_hashes = {path.name: sha256_file(path) for path in (builder_source / 'schemas').glob('*.json')}
        checks.update({
            'builder-manifest-pass': builder_manifest['entryCount'] > 0,
            'builder-schema-byte-parity': builder_hashes == schema_hashes,
            'builder-package-validation': load(unique(builder_manifest['root'], 'R7E_PACKAGE_VALIDATION.json')).get('passed') is True,
        })

    failed = sorted(name for name, passed in checks.items() if not passed)
    require(not failed, f'portable external audit v4 failed: {failed}')
    manifest = verify_manifest(root, 'R7F_ARTIFACT_SHA256SUMS.txt')
    return {
        'checks': checks,
        'failedChecks': [],
        'schemaHashes': schema_hashes,
        'metrics': {
            'r7fManifestEntries': manifest['entryCount'],
            'executedRunSteps': len(execution.get('executed', [])),
            'pathCorrectionClasses': len(expected_corrections),
            'pathReplacementCount': sum(row['count'] for row in expected_corrections),
            'browserPageChecks': browser.get('metrics', {}).get('pageChecks'),
            'independentAxeIncompleteNodes': browser.get('metrics', {}).get('axeIncompleteNodeCount'),
            'lighthouseReports': lighthouse.get('reportCount'),
            'stressDistFiles': stress.get('fileCount'),
        },
    }


def selftests(root: Path, status: dict) -> dict:
    cases = [
        ('decision', 'R7F_PORTABLE_V2_DECISION.json', lambda data: data.__setitem__('passed', False)),
        ('builder-digest', 'R7E_TUPLE.json', lambda data: data['artifact'].__setitem__('digest', 'sha256:' + '0' * 64)),
        ('schema-dialect', 'profile.schema.json', lambda data: data.__setitem__('$schema', 'https://invalid.example/schema')),
        ('browser-count', 'BROWSER_AUDIT.json', lambda data: data['metrics'].__setitem__('pageChecks', 167)),
        ('execution-pass', 'R7F_PLAN_EXECUTION.json', lambda data: data.__setitem__('passed', False)),
        ('binding-pass', 'R7F_BUILDER_V3_BINDING.json', lambda data: data.__setitem__('passed', False)),
        ('correction-model', 'R7F_PLAN_EXECUTION.json', lambda data: data['corrections'][0].__setitem__('to', '/tmp/fake')),
    ]
    results = []
    with tempfile.TemporaryDirectory(prefix='r7-portable-audit-v4-selftest-') as temporary:
        base_dir = Path(temporary)
        for name, filename, mutate in cases:
            target = base_dir / name
            shutil.copytree(root, target)
            path = unique(target, filename)
            data = load(path)
            mutate(data)
            path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
            regenerate_manifest(target, 'R7F_ARTIFACT_SHA256SUMS.txt')
            rejected = False
            error = None
            try:
                semantic(target, status, None)
            except AuditFailure as exc:
                rejected = True
                error = str(exc)
            results.append({'name': name, 'rejected': rejected, 'error': error})
    require(len(results) == 7 and all(row['rejected'] for row in results), f'v4 self-tests failed: {results}')
    return {'schema':'R7_PORTABLE_EXTERNAL_AUDIT_SELFTEST_V4','passed':True,'caseCount':7,'passedCaseCount':7,'cases':results}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--r7f-zip', required=True)
    parser.add_argument('--r7f-status', required=True)
    parser.add_argument('--r7e-zip', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--selftest-output', required=True)
    args = parser.parse_args()
    r7f_zip = Path(args.r7f_zip).resolve()
    r7e_zip = Path(args.r7e_zip).resolve()
    status = load(Path(args.r7f_status).resolve())
    r7f_digest = status.get('artifact', {}).get('digest', '')
    r7e_digest = status.get('builder', {}).get('artifactDigest', '')
    require(r7f_digest.startswith('sha256:') and sha256_file(r7f_zip) == r7f_digest.removeprefix('sha256:'), 'R7F outer digest mismatch')
    require(r7e_digest.startswith('sha256:') and sha256_file(r7e_zip) == r7e_digest.removeprefix('sha256:'), 'R7E outer digest mismatch')
    with tempfile.TemporaryDirectory(prefix='r7-portable-audit-v4-') as temporary:
        base_dir = Path(temporary)
        r7f_metrics = safe_extract(r7f_zip, base_dir / 'r7f')
        r7e_metrics = safe_extract(r7e_zip, base_dir / 'r7e')
        r7f_manifest = verify_manifest(base_dir / 'r7f', 'R7F_ARTIFACT_SHA256SUMS.txt')
        audited = semantic(r7f_manifest['root'], status, base_dir / 'r7e')
        tests = selftests(r7f_manifest['root'], status)
    report = {
        'schema': 'R7_PORTABLE_EXTERNAL_AUDIT_V4',
        'passed': True,
        'decision': 'R7_PORTABLE_EXTERNAL_AUDIT_PASS',
        'r7fStatus': status,
        'r7fDownloadedZipSha256': sha256_file(r7f_zip),
        'r7eDownloadedZipSha256': sha256_file(r7e_zip),
        'r7fZip': r7f_metrics,
        'r7eZip': r7e_metrics,
        **audited,
        'selftest': {'passed': True, 'caseCount': 7},
        'scope': 'External audit of R7 portable architecture evidence only; no whole-site or deployment certification',
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    Path(args.selftest_output).resolve().write_text(json.dumps(tests, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    try:
        main()
    except AuditFailure as exc:
        raise SystemExit(str(exc))
