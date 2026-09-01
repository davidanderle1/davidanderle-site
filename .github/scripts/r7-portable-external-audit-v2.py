#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile


class AuditFailure(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditFailure(message)


def safe_extract(zip_path: Path, target: Path) -> dict[str, object]:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    names: set[str] = set()
    regular = 0
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            pure = PurePosixPath(info.filename)
            mode = info.external_attr >> 16
            require(not pure.is_absolute() and '..' not in pure.parts, f'unsafe ZIP path: {info.filename}')
            require(info.filename not in names, f'duplicate ZIP entry: {info.filename}')
            require(stat.S_IFMT(mode) != stat.S_IFLNK, f'ZIP symlink rejected: {info.filename}')
            names.add(info.filename)
            if not info.is_dir():
                regular += 1
        archive.extractall(target)
    return {'entryCount': len(names), 'regularFileCount': regular}


def unique(root: Path, pattern: str) -> Path:
    matches = list(root.rglob(pattern))
    require(len(matches) == 1, f'expected one {pattern}, found {len(matches)}')
    return matches[0]


def parse_manifest(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for raw in path.read_text(encoding='utf-8').splitlines():
        if not raw.strip():
            continue
        require('  ' in raw, f'invalid manifest line: {raw!r}')
        digest, relative = raw.split('  ', 1)
        relative = relative.lstrip('*')
        pure = PurePosixPath(relative)
        require(len(digest) == 64 and all(ch in '0123456789abcdef' for ch in digest), 'invalid manifest digest')
        require(not pure.is_absolute() and '..' not in pure.parts and relative not in rows, f'unsafe manifest path: {relative}')
        rows[relative] = digest
    require(bool(rows), 'manifest is empty')
    return rows


def verify_manifest(root: Path, name: str) -> dict[str, object]:
    manifest_path = unique(root, name)
    artifact_root = manifest_path.parent
    rows = parse_manifest(manifest_path)
    actual = {
        path.relative_to(artifact_root).as_posix()
        for path in artifact_root.rglob('*')
        if path.is_file() and path != manifest_path
    }
    require(set(rows) == actual, f'{name} coverage mismatch')
    for relative, expected in rows.items():
        require(sha256_file(artifact_root / relative) == expected, f'{name} checksum mismatch: {relative}')
    return {'path': manifest_path, 'root': artifact_root, 'entryCount': len(rows)}


def regenerate_manifest(root: Path, name: str) -> None:
    manifest = root / name
    rows = []
    for path in sorted((p for p in root.rglob('*') if p.is_file() and p != manifest), key=lambda p: p.relative_to(root).as_posix().encode()):
        rows.append(f'{sha256_file(path)}  {path.relative_to(root).as_posix()}')
    manifest.write_text('\n'.join(rows) + '\n', encoding='utf-8')


def schema_audit(root: Path) -> tuple[dict[str, str], dict[str, bool]]:
    schema_paths = sorted(root.glob('*.json'))
    schema_names = {
        'profile.schema.json', 'work-record.schema.json', 'writing-record.schema.json',
        'milestone.schema.json', 'public-document.schema.json', 'redirect-record.schema.json',
        'tombstone-record.schema.json', 'canonical-content.schema.json', 'index.json',
    }
    found = {path.name for path in schema_paths if path.name in schema_names}
    require(found == schema_names, f'portable schema set mismatch: {sorted(found)}')
    hashes = {path.name: sha256_file(path) for path in schema_paths if path.name in schema_names}
    checks: dict[str, bool] = {}
    index = load(root / 'index.json')
    checks['index-version'] = index.get('contractVersion') == '1.0.0'
    checks['index-dialect'] = index.get('dialect') == 'https://json-schema.org/draft/2020-12/schema'
    checks['index-count'] = len(index.get('schemas', [])) == 8
    for name in sorted(schema_names - {'index.json'}):
        data = load(root / name)
        checks[f'{name}:dialect'] = data.get('$schema') == 'https://json-schema.org/draft/2020-12/schema'
        checks[f'{name}:version'] = data.get('x-contract-version') == '1.0.0'
        checks[f'{name}:id'] = isinstance(data.get('$id'), str) and data['$id'].startswith('https://davidanderle.com/schemas/')
    require(all(checks.values()), f'schema semantic checks failed: {[k for k,v in checks.items() if not v]}')
    return hashes, checks


def semantic_r7f_audit(root: Path, status: dict, builder_root: Path | None) -> dict[str, object]:
    decision_path = unique(root, 'R7F_PORTABLE_V2_DECISION.json')
    tuple_path = unique(root, 'R7E_TUPLE.json')
    preaudit_path = unique(root, 'R7E_PREAUDIT.json')
    execution_path = unique(root, 'R7F_PLAN_EXECUTION.json')
    source_plan_path = unique(root, 'R7F_SOURCE_PLAN.yml')
    corrected_plan_path = unique(root, 'R7F_CORRECTED_PLAN.yml')
    correction_diff_path = unique(root, 'R7F_PLAN_CORRECTION.diff')
    browser_path = unique(root, 'BROWSER_AUDIT.json')
    lighthouse_path = unique(root, 'LIGHTHOUSE_AUDIT.json')
    reproducibility_path = unique(root, 'REPRODUCIBILITY.json')
    stress_path = unique(root, 'STRESS_DIST_TREE.json')

    decision = load(decision_path)
    builder_tuple = load(tuple_path)
    preaudit = load(preaudit_path)
    execution = load(execution_path)
    browser = load(browser_path)
    lighthouse = load(lighthouse_path)
    reproducibility = load(reproducibility_path)
    stress = load(stress_path)

    checks = {
        'status-schema': status.get('schema') == 'R7F_PORTABLE_JSON_SCHEMA_AUTHORITATIVE_TUPLE_V3',
        'status-pass': status.get('passed') is True,
        'decision-pass': decision.get('passed') is True and decision.get('decision') == 'R7F_PORTABLE_INDEPENDENT_PASS',
        'decision-commit': decision.get('verifier', {}).get('commit') == status.get('commit'),
        'decision-run': decision.get('verifier', {}).get('runId') == status.get('runId'),
        'decision-digest': sha256_file(decision_path) == status.get('decisionSha256'),
        'execution-digest': sha256_file(execution_path) == status.get('planExecutionSha256'),
        'builder-status-commit': builder_tuple.get('commit') == status.get('builder', {}).get('commit'),
        'builder-status-digest': builder_tuple.get('artifact', {}).get('digest') == status.get('builder', {}).get('artifactDigest'),
        'builder-pass': builder_tuple.get('passed') is True,
        'builder-schema': builder_tuple.get('schema') == 'R7E_PORTABLE_JSON_SCHEMA_AUTHORITATIVE_TUPLE_V2',
        'builder-source-hash': builder_tuple.get('sourceArchiveSha256') == '764271738ad8578de7d89c522d9cedd1a22ce00d1b8e5d06b271903b52a3923d',
        'preaudit-pass': preaudit.get('passed') is True,
        'preaudit-source-files': preaudit.get('sourceFileCount') == 146,
        'plan-execution-pass': execution.get('passed') is True,
        'plan-correction-exact': execution.get('correction') == {'from': '../../../r7f-evidence', 'to': '$GITHUB_WORKSPACE/r7f-evidence'},
        'plan-skipped-run-exact': execution.get('skippedRunSteps') == ['Persist exact authoritative R7F tuple'],
        'plan-all-run-steps-pass': bool(execution.get('executed')) and all(row.get('exitCode') == 0 for row in execution.get('executed', [])),
        'browser-pass': browser.get('passed') is True,
        'browser-page-checks': browser.get('metrics', {}).get('pageChecks') == 168,
        'axe-zero-violations': browser.get('metrics', {}).get('axeViolationCount') == 0,
        'network-zero-off-origin': browser.get('metrics', {}).get('offOriginRequestCount') == 0,
        'lighthouse-pass': lighthouse.get('passed') is True and lighthouse.get('reportCount') == 4,
        'reproducibility-pass': reproducibility.get('passed') is True and reproducibility.get('fileCount') == 34,
        'stress-files': stress.get('fileCount', 0) >= 534,
        'correction-diff-present': correction_diff_path.stat().st_size > 0,
    }
    source_plan = source_plan_path.read_text(encoding='utf-8')
    expected_corrected = source_plan.replace('../../../r7f-evidence', '$GITHUB_WORKSPACE/r7f-evidence')
    checks['corrected-plan-byte-exact'] = corrected_plan_path.read_text(encoding='utf-8') == expected_corrected
    checks['correction-count-exact'] = execution.get('correctionCount') == source_plan.count('../../../r7f-evidence') and execution.get('correctionCount', 0) > 0

    schema_hashes, schema_checks = schema_audit(root)
    checks.update({f'schema:{key}': value for key, value in schema_checks.items()})
    preaudit_hashes = preaudit.get('schemaHashes', {})
    checks['preaudit-schema-hashes-match'] = all(preaudit_hashes.get(name) == digest for name, digest in schema_hashes.items())

    builder_checks = {}
    if builder_root is not None:
        builder_manifest = verify_manifest(builder_root, 'R7E_ARTIFACT_SHA256SUMS.txt')
        builder_source = unique(builder_manifest['root'], 'BEARING_PRODUCTION_SOURCE')
        require(builder_source.is_dir(), 'builder source is not a directory')
        builder_schema_hashes = {path.name: sha256_file(path) for path in (builder_source / 'schemas').glob('*.json')}
        builder_checks = {
            'builder-artifact-manifest': builder_manifest['entryCount'] > 0,
            'builder-schema-byte-parity': builder_schema_hashes == schema_hashes,
            'builder-package-validation': load(unique(builder_manifest['root'], 'R7E_PACKAGE_VALIDATION.json')).get('passed') is True,
        }
        checks.update(builder_checks)

    failed = sorted(name for name, passed in checks.items() if not passed)
    require(not failed, f'R7F semantic checks failed: {failed}')
    return {
        'checks': checks,
        'failedChecks': [],
        'schemaHashes': schema_hashes,
        'metrics': {
            'r7fManifestEntries': verify_manifest(root, 'R7F_ARTIFACT_SHA256SUMS.txt')['entryCount'],
            'executedRunSteps': len(execution.get('executed', [])),
            'browserPageChecks': browser.get('metrics', {}).get('pageChecks'),
            'independentAxeIncompleteNodes': browser.get('metrics', {}).get('axeIncompleteNodeCount'),
            'lighthouseReports': lighthouse.get('reportCount'),
            'stressDistFiles': stress.get('fileCount'),
        },
    }


def selftests(authentic_root: Path, status: dict) -> dict[str, object]:
    mutations = [
        ('decision-pass', 'R7F_PORTABLE_V2_DECISION.json', lambda data: data.__setitem__('passed', False)),
        ('builder-digest', 'R7E_TUPLE.json', lambda data: data['artifact'].__setitem__('digest', 'sha256:' + '0' * 64)),
        ('schema-dialect', 'profile.schema.json', lambda data: data.__setitem__('$schema', 'https://example.invalid/schema')),
        ('browser-count', 'BROWSER_AUDIT.json', lambda data: data['metrics'].__setitem__('pageChecks', 167)),
        ('execution-status', 'R7F_PLAN_EXECUTION.json', lambda data: data.__setitem__('passed', False)),
    ]
    results = []
    with tempfile.TemporaryDirectory(prefix='r7-audit-selftest-') as temporary:
        base = Path(temporary)
        for name, filename, mutate in mutations:
            target = base / name
            shutil.copytree(authentic_root, target)
            path = unique(target, filename)
            data = load(path)
            mutate(data)
            path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
            regenerate_manifest(target, 'R7F_ARTIFACT_SHA256SUMS.txt')
            rejected = False
            error = None
            try:
                semantic_r7f_audit(target, status, None)
            except AuditFailure as exc:
                rejected = True
                error = str(exc)
            results.append({'name': name, 'rejected': rejected, 'error': error})

        target = base / 'corrected-plan'
        shutil.copytree(authentic_root, target)
        path = unique(target, 'R7F_CORRECTED_PLAN.yml')
        path.write_text(path.read_text(encoding='utf-8') + '\n# unauthorized mutation\n', encoding='utf-8')
        regenerate_manifest(target, 'R7F_ARTIFACT_SHA256SUMS.txt')
        rejected = False
        error = None
        try:
            semantic_r7f_audit(target, status, None)
        except AuditFailure as exc:
            rejected = True
            error = str(exc)
        results.append({'name': 'corrected-plan', 'rejected': rejected, 'error': error})

    passed = len(results) == 6 and all(row['rejected'] for row in results)
    require(passed, f'external audit self-test failure: {results}')
    return {'schema': 'R7_PORTABLE_EXTERNAL_AUDIT_SELFTEST_V2', 'passed': True, 'caseCount': 6, 'passedCaseCount': 6, 'cases': results}


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
    expected = status.get('artifact', {}).get('digest', '')
    require(expected.startswith('sha256:'), 'R7F status digest is invalid')
    require(sha256_file(r7f_zip) == expected.removeprefix('sha256:'), 'R7F outer ZIP digest mismatch')
    builder_expected = status.get('builder', {}).get('artifactDigest', '')
    require(builder_expected.startswith('sha256:'), 'builder status digest is invalid')
    require(sha256_file(r7e_zip) == builder_expected.removeprefix('sha256:'), 'R7E outer ZIP digest mismatch')

    with tempfile.TemporaryDirectory(prefix='r7-portable-external-') as temporary:
        base = Path(temporary)
        r7f_zip_metrics = safe_extract(r7f_zip, base / 'r7f')
        r7e_zip_metrics = safe_extract(r7e_zip, base / 'r7e')
        r7f_manifest = verify_manifest(base / 'r7f', 'R7F_ARTIFACT_SHA256SUMS.txt')
        semantic = semantic_r7f_audit(r7f_manifest['root'], status, base / 'r7e')
        test_report = selftests(r7f_manifest['root'], status)

    report = {
        'schema': 'R7_PORTABLE_EXTERNAL_AUDIT_V2',
        'passed': True,
        'decision': 'R7_PORTABLE_EXTERNAL_AUDIT_PASS',
        'r7fStatus': status,
        'r7fDownloadedZipSha256': sha256_file(r7f_zip),
        'r7eDownloadedZipSha256': sha256_file(r7e_zip),
        'r7fZip': r7f_zip_metrics,
        'r7eZip': r7e_zip_metrics,
        **semantic,
        'selftest': {'passed': True, 'caseCount': 6},
        'scope': 'External audit of portable-schema R7E/R7F evidence only; not a whole-site or deployment certification',
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    Path(args.selftest_output).resolve().write_text(json.dumps(test_report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    try:
        main()
    except AuditFailure as exc:
        raise SystemExit(str(exc))
