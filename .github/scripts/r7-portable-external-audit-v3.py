#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile

MODULE_PATH = Path(__file__).with_name('r7-portable-external-audit-v2.py')
spec = importlib.util.spec_from_file_location('audit_v2', MODULE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit('cannot load v2 audit primitives')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

AuditFailure = audit.AuditFailure
require = audit.require
load = audit.load
unique = audit.unique
sha256_file = audit.sha256_file
safe_extract = audit.safe_extract
verify_manifest = audit.verify_manifest
regenerate_manifest = audit.regenerate_manifest
schema_audit = audit.schema_audit


def semantic_v4(root: Path, status: dict, builder_root: Path | None) -> dict:
    decision_path = unique(root, 'R7F_PORTABLE_V2_DECISION.json')
    tuple_path = unique(root, 'R7E_TUPLE.json')
    preaudit_path = unique(root, 'R7E_PREAUDIT.json')
    execution_path = unique(root, 'R7F_PLAN_EXECUTION.json')
    original_path = unique(root, 'R7F_ORIGINAL_SOURCE_PLAN.yml')
    builder_plan_path = unique(root, 'R7F_BUILDER_V3_SOURCE_PLAN.yml')
    builder_diff_path = unique(root, 'R7F_BUILDER_V3_BINDING.diff')
    builder_binding_path = unique(root, 'R7F_BUILDER_V3_BINDING.json')
    final_plan_path = unique(root, 'R7F_FINAL_CORRECTED_PLAN.yml')
    path_diff_path = unique(root, 'R7F_LOG_PATH_CORRECTION.diff')
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
    replacements = [
        ('r7e-portable-json-schema-verification-20260831', 'r7e-portable-authoritative-v3-20260901'),
        ('.github/r7-status/portable-r7e-v2.json', '.github/r7-status/portable-r7e-v3.json'),
        ('R7E_PORTABLE_JSON_SCHEMA_AUTHORITATIVE_TUPLE_V2', 'R7E_PORTABLE_JSON_SCHEMA_AUTHORITATIVE_TUPLE_V3'),
    ]
    expected_counts = {}
    for old, new in replacements:
        expected_counts[old] = expected_builder.count(old)
        require(expected_counts[old] > 0, f'original plan lacks expected builder binding anchor: {old}')
        expected_builder = expected_builder.replace(old, new)
    actual_builder = builder_plan_path.read_text(encoding='utf-8')
    expected_final = expected_builder.replace('../../../r7f-evidence', '$GITHUB_WORKSPACE/r7f-evidence')

    checks = {
        'status-schema': status.get('schema') == 'R7F_PORTABLE_JSON_SCHEMA_AUTHORITATIVE_TUPLE_V4',
        'status-pass': status.get('passed') is True,
        'decision-pass': decision.get('passed') is True and decision.get('decision') == 'R7F_PORTABLE_INDEPENDENT_PASS',
        'decision-commit': decision.get('verifier', {}).get('commit') == status.get('commit'),
        'decision-run': decision.get('verifier', {}).get('runId') == status.get('runId'),
        'decision-digest': sha256_file(decision_path) == status.get('decisionSha256'),
        'execution-digest': sha256_file(execution_path) == status.get('planExecutionSha256'),
        'builder-binding-digest': sha256_file(builder_binding_path) == status.get('builderBindingSha256'),
        'builder-status-commit': builder_tuple.get('commit') == status.get('builder', {}).get('commit'),
        'builder-status-digest': builder_tuple.get('artifact', {}).get('digest') == status.get('builder', {}).get('artifactDigest'),
        'builder-pass': builder_tuple.get('passed') is True,
        'builder-schema': builder_tuple.get('schema') == 'R7E_PORTABLE_JSON_SCHEMA_AUTHORITATIVE_TUPLE_V3',
        'builder-branch': builder_tuple.get('branch') == 'r7e-portable-authoritative-v3-20260901',
        'builder-source-hash': builder_tuple.get('sourceArchiveSha256') == '764271738ad8578de7d89c522d9cedd1a22ce00d1b8e5d06b271903b52a3923d',
        'preaudit-pass': preaudit.get('passed') is True,
        'preaudit-source-files': preaudit.get('sourceFileCount') == 146,
        'binding-pass': binding.get('passed') is True,
        'binding-counts-exact': binding.get('replacements') == expected_counts,
        'builder-plan-byte-exact': actual_builder == expected_builder,
        'builder-diff-present': builder_diff_path.stat().st_size > 0,
        'path-diff-present': path_diff_path.stat().st_size > 0,
        'final-plan-byte-exact': final_plan_path.read_text(encoding='utf-8') == expected_final,
        'execution-pass': execution.get('passed') is True,
        'execution-source-plan': str(execution.get('sourcePlan', '')).endswith('R7F_BUILDER_V3_SOURCE_PLAN.yml'),
        'execution-corrected-plan': str(execution.get('correctedPlan', '')).endswith('R7F_FINAL_CORRECTED_PLAN.yml'),
        'execution-correction-exact': execution.get('correction') == {'from': '../../../r7f-evidence', 'to': '$GITHUB_WORKSPACE/r7f-evidence'},
        'execution-correction-count': execution.get('correctionCount') == expected_builder.count('../../../r7f-evidence') and execution.get('correctionCount', 0) > 0,
        'execution-skipped-status-only': execution.get('skippedRunSteps') == ['Persist exact authoritative R7F tuple'],
        'execution-all-steps-pass': bool(execution.get('executed')) and all(row.get('exitCode') == 0 for row in execution.get('executed', [])),
        'browser-pass': browser.get('passed') is True,
        'browser-page-checks': browser.get('metrics', {}).get('pageChecks') == 168,
        'axe-zero-violations': browser.get('metrics', {}).get('axeViolationCount') == 0,
        'network-zero-off-origin': browser.get('metrics', {}).get('offOriginRequestCount') == 0,
        'lighthouse-pass': lighthouse.get('passed') is True and lighthouse.get('reportCount') == 4,
        'reproducibility-pass': reproducibility.get('passed') is True and reproducibility.get('fileCount') == 34,
        'stress-files': stress.get('fileCount', 0) >= 534,
    }

    schema_hashes, schema_checks = schema_audit(root)
    checks.update({f'schema:{key}': value for key, value in schema_checks.items()})
    checks['preaudit-schema-hashes-match'] = all(preaudit.get('schemaHashes', {}).get(name) == digest for name, digest in schema_hashes.items())

    if builder_root is not None:
        builder_manifest = verify_manifest(builder_root, 'R7E_ARTIFACT_SHA256SUMS.txt')
        builder_source = unique(builder_manifest['root'], 'BEARING_PRODUCTION_SOURCE')
        require(builder_source.is_dir(), 'builder source is not a directory')
        builder_hashes = {path.name: sha256_file(path) for path in (builder_source / 'schemas').glob('*.json')}
        checks.update({
            'builder-artifact-manifest': builder_manifest['entryCount'] > 0,
            'builder-schema-byte-parity': builder_hashes == schema_hashes,
            'builder-package-validation': load(unique(builder_manifest['root'], 'R7E_PACKAGE_VALIDATION.json')).get('passed') is True,
        })

    failed = sorted(name for name, passed in checks.items() if not passed)
    require(not failed, f'v4 semantic checks failed: {failed}')
    manifest = verify_manifest(root, 'R7F_ARTIFACT_SHA256SUMS.txt')
    return {
        'checks': checks,
        'failedChecks': [],
        'schemaHashes': schema_hashes,
        'metrics': {
            'r7fManifestEntries': manifest['entryCount'],
            'executedRunSteps': len(execution.get('executed', [])),
            'browserPageChecks': browser.get('metrics', {}).get('pageChecks'),
            'independentAxeIncompleteNodes': browser.get('metrics', {}).get('axeIncompleteNodeCount'),
            'lighthouseReports': lighthouse.get('reportCount'),
            'stressDistFiles': stress.get('fileCount'),
            'builderBindingReplacementCount': sum(expected_counts.values()),
            'logPathCorrectionCount': execution.get('correctionCount'),
        },
    }


def selftests(root: Path, status: dict) -> dict:
    cases = [
        ('decision', 'R7F_PORTABLE_V2_DECISION.json', lambda d: d.__setitem__('passed', False)),
        ('builder-digest', 'R7E_TUPLE.json', lambda d: d['artifact'].__setitem__('digest', 'sha256:' + '0' * 64)),
        ('schema', 'profile.schema.json', lambda d: d.__setitem__('$schema', 'https://invalid.example/schema')),
        ('browser', 'BROWSER_AUDIT.json', lambda d: d['metrics'].__setitem__('pageChecks', 167)),
        ('execution', 'R7F_PLAN_EXECUTION.json', lambda d: d.__setitem__('passed', False)),
        ('binding', 'R7F_BUILDER_V3_BINDING.json', lambda d: d.__setitem__('passed', False)),
    ]
    results = []
    with tempfile.TemporaryDirectory(prefix='r7-v3-selftest-') as temporary:
        base = Path(temporary)
        for name, filename, mutate in cases:
            target = base / name
            shutil.copytree(root, target)
            path = unique(target, filename)
            data = load(path); mutate(data)
            path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
            regenerate_manifest(target, 'R7F_ARTIFACT_SHA256SUMS.txt')
            rejected = False; error = None
            try:
                semantic_v4(target, status, None)
            except AuditFailure as exc:
                rejected = True; error = str(exc)
            results.append({'name': name, 'rejected': rejected, 'error': error})
    require(len(results) == 6 and all(row['rejected'] for row in results), f'self-tests did not all reject: {results}')
    return {'schema': 'R7_PORTABLE_EXTERNAL_AUDIT_SELFTEST_V3', 'passed': True, 'caseCount': 6, 'passedCaseCount': 6, 'cases': results}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--r7f-zip', required=True)
    parser.add_argument('--r7f-status', required=True)
    parser.add_argument('--r7e-zip', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--selftest-output', required=True)
    args = parser.parse_args()
    r7f_zip = Path(args.r7f_zip).resolve(); r7e_zip = Path(args.r7e_zip).resolve()
    status = load(Path(args.r7f_status).resolve())
    r7f_digest = status.get('artifact', {}).get('digest', '')
    builder_digest = status.get('builder', {}).get('artifactDigest', '')
    require(r7f_digest.startswith('sha256:') and sha256_file(r7f_zip) == r7f_digest.removeprefix('sha256:'), 'R7F outer digest mismatch')
    require(builder_digest.startswith('sha256:') and sha256_file(r7e_zip) == builder_digest.removeprefix('sha256:'), 'R7E outer digest mismatch')
    with tempfile.TemporaryDirectory(prefix='r7-external-v3-') as temporary:
        base = Path(temporary)
        r7f_metrics = safe_extract(r7f_zip, base / 'r7f')
        r7e_metrics = safe_extract(r7e_zip, base / 'r7e')
        r7f_manifest = verify_manifest(base / 'r7f', 'R7F_ARTIFACT_SHA256SUMS.txt')
        semantic = semantic_v4(r7f_manifest['root'], status, base / 'r7e')
        tests = selftests(r7f_manifest['root'], status)
    report = {
        'schema': 'R7_PORTABLE_EXTERNAL_AUDIT_V3',
        'passed': True,
        'decision': 'R7_PORTABLE_EXTERNAL_AUDIT_PASS',
        'r7fStatus': status,
        'r7fDownloadedZipSha256': sha256_file(r7f_zip),
        'r7eDownloadedZipSha256': sha256_file(r7e_zip),
        'r7fZip': r7f_metrics,
        'r7eZip': r7e_metrics,
        **semantic,
        'selftest': {'passed': True, 'caseCount': 6},
        'scope': 'External audit of R7 portable architecture evidence only; no whole-site or deployment certification',
    }
    output = Path(args.output).resolve(); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    Path(args.selftest_output).resolve().write_text(json.dumps(tests, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    try:
        main()
    except AuditFailure as exc:
        raise SystemExit(str(exc))
