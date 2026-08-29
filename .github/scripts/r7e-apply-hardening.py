#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import stat
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def safe_member_name(name: str) -> str:
    normalized = PurePosixPath(name)
    if normalized.is_absolute() or '..' in normalized.parts:
        raise SystemExit(f'unsafe archive member: {name!r}')
    clean = normalized.as_posix().lstrip('./')
    if not clean or clean == '.':
        raise SystemExit(f'invalid archive member: {name!r}')
    return clean


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit('usage: r7e-apply-hardening.py <candidate-root>')

    script_dir = Path(__file__).resolve().parent
    candidate = Path(sys.argv[1]).resolve()
    archive_b64_path = script_dir / 'r7e-hardening-overlay.tar.gz.b64'
    manifest_path = script_dir / 'r7e-hardening-overlay-manifest.json'

    if not (candidate / 'package.json').is_file():
        raise SystemExit(f'candidate source missing: {candidate}')
    if not archive_b64_path.is_file():
        raise SystemExit(f'overlay archive missing: {archive_b64_path}')
    if not manifest_path.is_file():
        raise SystemExit(f'overlay manifest missing: {manifest_path}')

    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('version') != 1:
        raise SystemExit(f'unsupported overlay manifest version: {manifest.get("version")!r}')
    declared_files = manifest.get('files')
    if not isinstance(declared_files, list) or not declared_files:
        raise SystemExit('overlay manifest has no files')

    raw_b64 = ''.join(archive_b64_path.read_text(encoding='ascii').split())
    try:
        archive_bytes = base64.b64decode(raw_b64, validate=True)
    except Exception as exc:
        raise SystemExit(f'invalid base64 overlay archive: {exc}') from exc

    archive_sha = sha256_bytes(archive_bytes)
    expected_archive_sha = manifest.get('archiveSha256')
    if archive_sha != expected_archive_sha:
        raise SystemExit(f'overlay archive SHA-256 mismatch: {archive_sha} != {expected_archive_sha}')

    expected_by_path: dict[str, dict] = {}
    for row in declared_files:
        rel = safe_member_name(str(row.get('path', '')))
        if rel in expected_by_path:
            raise SystemExit(f'duplicate path in overlay manifest: {rel}')
        expected_by_path[rel] = row

    with tempfile.TemporaryDirectory(prefix='r7e-overlay-') as tmp_name:
        tmp = Path(tmp_name)
        archive_path = tmp / 'overlay.tar.gz'
        archive_path.write_bytes(archive_bytes)
        extracted = tmp / 'extracted'
        extracted.mkdir()

        with tarfile.open(archive_path, mode='r:gz') as archive:
            actual_file_members: set[str] = set()
            for member in archive.getmembers():
                rel = safe_member_name(member.name)
                if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                    raise SystemExit(f'unsupported overlay archive member type: {member.name!r}')
                if member.isfile():
                    actual_file_members.add(rel)
                elif not member.isdir():
                    raise SystemExit(f'unsupported overlay archive member: {member.name!r}')
            expected_paths = set(expected_by_path)
            if actual_file_members != expected_paths:
                raise SystemExit(json.dumps({
                    'overlayArchiveMembershipMismatch': True,
                    'missing': sorted(expected_paths - actual_file_members),
                    'unexpected': sorted(actual_file_members - expected_paths),
                }, indent=2))
            archive.extractall(extracted, filter='data')

        verified_rows = []
        for rel, expected in sorted(expected_by_path.items()):
            source = extracted / rel
            if not source.is_file():
                raise SystemExit(f'overlay extraction missing file: {rel}')
            actual_size = source.stat().st_size
            actual_sha = sha256_file(source)
            expected_size = int(expected['bytes'])
            expected_sha = str(expected['sha256'])
            if actual_size != expected_size or actual_sha != expected_sha:
                raise SystemExit(json.dumps({
                    'overlayFileMismatch': rel,
                    'expectedBytes': expected_size,
                    'actualBytes': actual_size,
                    'expectedSha256': expected_sha,
                    'actualSha256': actual_sha,
                }, indent=2))

            mode_text = str(expected.get('mode', '0o644'))
            expected_mode = int(mode_text, 8)
            target = candidate / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            os.chmod(target, expected_mode)

            target_size = target.stat().st_size
            target_sha = sha256_file(target)
            target_mode = stat.S_IMODE(target.stat().st_mode)
            if target_size != expected_size or target_sha != expected_sha or target_mode != expected_mode:
                raise SystemExit(f'installed overlay verification failed: {rel}')
            verified_rows.append({
                'path': rel,
                'bytes': target_size,
                'sha256': target_sha,
                'mode': oct(target_mode),
            })

    package = json.loads((candidate / 'package.json').read_text(encoding='utf-8'))
    scripts = package.get('scripts', {})
    required_scripts = {
        'test:stress:lineage': 'node scripts/verify-stress-lineage.mjs',
        'wrangler:validate': 'wrangler deploy --dry-run --config wrangler.jsonc --outdir .r7e-tmp/wrangler',
    }
    for name, expected in required_scripts.items():
        if scripts.get(name) != expected:
            raise SystemExit(f'unexpected package script {name}={scripts.get(name)!r}')

    assertions = {
        'threeBearingStops': 'milestones.slice(0, 3)' in (candidate / 'src/pages/index.astro').read_text(encoding='utf-8'),
        'noFuturePseudoStop': 'Deeper quantitative and research training' not in (candidate / 'src/pages/index.astro').read_text(encoding='utf-8'),
        'threeColumnBearing': 'repeat(3, 1fr)' in (candidate / 'src/styles/bearing.css').read_text(encoding='utf-8'),
        'longTitleWrap': 'overflow-wrap: anywhere' in (candidate / 'src/styles/project.css').read_text(encoding='utf-8'),
        'stressLineagePresent': (candidate / 'scripts/verify-stress-lineage.mjs').is_file(),
        'axeRawEvidence': '.r7e-tmp/axe' in (candidate / 'tests/accessibility.spec.ts').read_text(encoding='utf-8'),
        'fourLongContentStates': 'metadata-only' in (candidate / 'tests/browser.spec.ts').read_text(encoding='utf-8'),
        'lighthouseRepeatedRuns': 'runsPerRoute = 2' in (candidate / 'scripts/run-lighthouse.mjs').read_text(encoding='utf-8'),
        'networkFailureGate': 'firstPartyHttpErrorCount' in (candidate / 'scripts/network-audit.mjs').read_text(encoding='utf-8'),
    }
    if not all(assertions.values()):
        raise SystemExit(json.dumps({'passed': False, 'assertions': assertions}, indent=2))

    result = {
        'passed': True,
        'patchSha256': archive_sha,
        'overlayManifestSha256': sha256_file(manifest_path),
        'installedFileCount': len(verified_rows),
        'installedFiles': verified_rows,
        'assertions': assertions,
        'packageJsonSha256': sha256_file(candidate / 'package.json'),
        'packageLockSha256': sha256_file(candidate / 'package-lock.json'),
    }
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
