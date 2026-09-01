#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import zipfile


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def fail(message: str) -> None:
    raise SystemExit(message)


def parse_manifest(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
        if not raw.strip():
            continue
        if '  ' not in raw:
            fail(f'invalid checksum line {line_number}: {raw!r}')
        digest, relative = raw.split('  ', 1)
        relative = relative.lstrip('*')
        pure = PurePosixPath(relative)
        if len(digest) != 64 or any(ch not in '0123456789abcdef' for ch in digest):
            fail(f'invalid checksum digest at line {line_number}')
        if pure.is_absolute() or '..' in pure.parts or relative in rows:
            fail(f'unsafe or duplicate checksum path: {relative}')
        rows[relative] = digest
    if not rows:
        fail('checksum manifest is empty')
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--zip', required=True, dest='zip_path')
    parser.add_argument('--tuple', required=True, dest='tuple_path')
    parser.add_argument('--extract', required=True, dest='extract_path')
    parser.add_argument('--source-copy', required=True, dest='source_copy')
    parser.add_argument('--report', required=True, dest='report_path')
    args = parser.parse_args()

    zip_path = Path(args.zip_path).resolve()
    tuple_path = Path(args.tuple_path).resolve()
    extract_path = Path(args.extract_path).resolve()
    source_copy = Path(args.source_copy).resolve()
    report_path = Path(args.report_path).resolve()
    tuple_data = json.loads(tuple_path.read_text(encoding='utf-8'))

    expected_digest = str(tuple_data['artifact']['digest'])
    if not expected_digest.startswith('sha256:'):
        fail('tuple artifact digest is not SHA-256')
    actual_zip_sha = sha256_file(zip_path)
    if actual_zip_sha != expected_digest.removeprefix('sha256:'):
        fail('downloaded R7E artifact digest mismatch')

    if extract_path.exists():
        shutil.rmtree(extract_path)
    extract_path.mkdir(parents=True)
    names: set[str] = set()
    zip_entry_hashes: dict[str, str] = {}
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            pure = PurePosixPath(info.filename)
            mode = info.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if pure.is_absolute() or '..' in pure.parts:
                fail(f'unsafe ZIP path: {info.filename}')
            if info.filename in names:
                fail(f'duplicate ZIP entry: {info.filename}')
            names.add(info.filename)
            if file_type == stat.S_IFLNK:
                fail(f'ZIP symlink rejected: {info.filename}')
            if not info.is_dir():
                zip_entry_hashes[info.filename] = sha256_bytes(archive.read(info))
        archive.extractall(extract_path)

    manifest_candidates = list(extract_path.rglob('R7E_ARTIFACT_SHA256SUMS.txt'))
    if len(manifest_candidates) != 1:
        fail(f'expected one R7E checksum manifest, found {len(manifest_candidates)}')
    manifest_path = manifest_candidates[0]
    artifact_root = manifest_path.parent
    manifest = parse_manifest(manifest_path)
    actual_files = {
        path.relative_to(artifact_root).as_posix()
        for path in artifact_root.rglob('*')
        if path.is_file() and path != manifest_path
    }
    if set(manifest) != actual_files:
        missing = sorted(actual_files - set(manifest))
        extra = sorted(set(manifest) - actual_files)
        fail(f'internal manifest coverage mismatch missing={missing[:10]} extra={extra[:10]}')
    for relative, expected in manifest.items():
        actual = sha256_file(artifact_root / relative)
        if actual != expected:
            fail(f'internal checksum mismatch: {relative}')

    validation_candidates = list(artifact_root.rglob('R7E_PACKAGE_VALIDATION.json'))
    if len(validation_candidates) != 1:
        fail(f'expected one package validation, found {len(validation_candidates)}')
    package_validation = json.loads(validation_candidates[0].read_text(encoding='utf-8'))
    if package_validation.get('passed') is not True:
        fail('R7E package validation is not passing')

    source_candidates = [path for path in artifact_root.rglob('BEARING_PRODUCTION_SOURCE') if path.is_dir()]
    if len(source_candidates) != 1:
        fail(f'expected one BEARING_PRODUCTION_SOURCE, found {len(source_candidates)}')
    source_root = source_candidates[0]

    required = [
        'package.json',
        'package-lock.json',
        'astro.config.mjs',
        'src/content.config.ts',
        'src/content-schemas.ts',
        'schemas/index.json',
        'schemas/canonical-content.schema.json',
        'docs/PORTABLE_JSON_SCHEMA.md',
        'scripts/generate-json-schemas.mjs',
        'scripts/run-portable-schema-contract.mjs',
        'scripts/validate-json-schema.mjs',
    ]
    missing_required = [relative for relative in required if not (source_root / relative).is_file()]
    if missing_required:
        fail(f'portable source required paths missing: {missing_required}')

    package = json.loads((source_root / 'package.json').read_text(encoding='utf-8'))
    lock = json.loads((source_root / 'package-lock.json').read_text(encoding='utf-8'))
    checks = {
        'package-manager': package.get('packageManager') == 'npm@11.19.0',
        'node-engine': package.get('engines', {}).get('node') == '24.20.0',
        'npm-engine': package.get('engines', {}).get('npm') == '11.19.0',
        'lockfile-version': lock.get('lockfileVersion') == 3,
        'ajv-package-pin': package.get('devDependencies', {}).get('ajv') == '8.20.0',
        'ajv-lock-pin': lock.get('packages', {}).get('node_modules/ajv', {}).get('version') == '8.20.0',
    }

    schema_dir = source_root / 'schemas'
    schema_files = sorted(schema_dir.glob('*.json'))
    index = json.loads((schema_dir / 'index.json').read_text(encoding='utf-8'))
    checks.update({
        'schema-file-count': len(schema_files) == 9,
        'schema-index-version': index.get('contractVersion') == '1.0.0',
        'schema-index-dialect': index.get('dialect') == 'https://json-schema.org/draft/2020-12/schema',
        'schema-index-count': len(index.get('schemas', [])) == 8,
    })
    schema_hashes: dict[str, str] = {}
    for schema_path in schema_files:
        schema_hashes[schema_path.name] = sha256_file(schema_path)
        if schema_path.name == 'index.json':
            continue
        data = json.loads(schema_path.read_text(encoding='utf-8'))
        checks[f'{schema_path.name}:dialect'] = data.get('$schema') == 'https://json-schema.org/draft/2020-12/schema'
        checks[f'{schema_path.name}:contract-version'] = data.get('x-contract-version') == '1.0.0'
        checks[f'{schema_path.name}:stable-id'] = isinstance(data.get('$id'), str) and data['$id'].startswith('https://davidanderle.com/schemas/')

    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        fail(f'portable source pre-audit failed: {failed}')

    if source_copy.exists():
        shutil.rmtree(source_copy)
    shutil.copytree(source_root, source_copy, symlinks=False)

    identity_candidates = list(artifact_root.rglob('*CANDIDATE_IDENTITY*.json'))
    identity_summaries = []
    for identity_path in identity_candidates:
        try:
            identity = json.loads(identity_path.read_text(encoding='utf-8'))
        except Exception:
            continue
        identity_summaries.append({
            'file': identity_path.relative_to(artifact_root).as_posix(),
            'sha256': sha256_file(identity_path),
            'schema': identity.get('schema'),
            'sourceArchiveSha256': identity.get('sourceArchiveSha256'),
            'verifiedDistTreeSha256': identity.get('verifiedDistTreeSha256'),
            'stressDistTreeSha256': identity.get('stressDistTreeSha256'),
            'axeIncompleteNodeCount': identity.get('axeIncompleteNodeCount'),
        })

    report = {
        'schema': 'R7F_PORTABLE_R7E_PREAUDIT_V2',
        'passed': True,
        'tuple': tuple_data,
        'downloadedZipSha256': actual_zip_sha,
        'zipEntryCount': len(names),
        'zipRegularFileCount': len(zip_entry_hashes),
        'internalManifestEntryCount': len(manifest),
        'artifactRoot': artifact_root.relative_to(extract_path).as_posix() or '.',
        'sourceRoot': source_root.relative_to(artifact_root).as_posix(),
        'sourceFileCount': sum(1 for path in source_root.rglob('*') if path.is_file()),
        'checks': checks,
        'failedChecks': [],
        'schemaHashes': schema_hashes,
        'candidateIdentities': identity_summaries,
        'packageValidationSha256': sha256_file(validation_candidates[0]),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
