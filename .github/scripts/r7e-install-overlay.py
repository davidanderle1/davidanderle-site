#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import stat
import sys
import tarfile
from pathlib import Path, PurePosixPath


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    return digest(path.read_bytes())


def clean_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts:
        raise SystemExit(f'unsafe overlay path: {value!r}')
    normalized = path.as_posix().lstrip('./')
    if not normalized:
        raise SystemExit(f'empty overlay path: {value!r}')
    return normalized


def replace_exact(root: Path, relative: str, old: str, new: str, label: str) -> None:
    target = root / relative
    text = target.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one source pattern in {relative}, found {count}')
    target.write_text(text.replace(old, new), encoding='utf-8')


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit('usage: r7e-install-overlay.py <candidate-root>')

    scripts_dir = Path(__file__).resolve().parent
    candidate = Path(sys.argv[1]).resolve()
    parts_dir = scripts_dir / 'r7e-hardening-overlay-parts'
    manifest_path = scripts_dir / 'r7e-hardening-overlay-manifest.json'

    if not (candidate / 'package.json').is_file():
        raise SystemExit(f'candidate source missing: {candidate}')

    part_names = [f'part{i:02d}.b64' for i in range(1, 7)]
    part_paths = [parts_dir / name for name in part_names]
    missing_parts = [str(path) for path in part_paths if not path.is_file()]
    if missing_parts:
        raise SystemExit(f'missing overlay chunks: {missing_parts}')

    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    rows = manifest.get('files')
    if manifest.get('version') != 1 or not isinstance(rows, list) or not rows:
        raise SystemExit('invalid overlay manifest')

    encoded = ''.join(''.join(path.read_text(encoding='ascii').split()) for path in part_paths)
    try:
        archive_bytes = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise SystemExit(f'overlay chunks are not valid base64: {exc}') from exc

    archive_sha = digest(archive_bytes)
    if archive_sha != manifest.get('archiveSha256'):
        raise SystemExit(f'overlay archive digest mismatch: {archive_sha}')

    expected = {clean_path(str(row['path'])): row for row in rows}
    if len(expected) != len(rows):
        raise SystemExit('duplicate paths in overlay manifest')

    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as archive:
        members: dict[str, tarfile.TarInfo] = {}
        for member in archive.getmembers():
            name = clean_path(member.name)
            if member.isdir():
                continue
            if not member.isfile():
                raise SystemExit(f'unsupported overlay member type: {member.name!r}')
            members[name] = member

        if set(members) != set(expected):
            raise SystemExit(json.dumps({
                'missing': sorted(set(expected) - set(members)),
                'unexpected': sorted(set(members) - set(expected)),
            }, indent=2))

        installed = []
        for relative, row in sorted(expected.items()):
            stream = archive.extractfile(members[relative])
            if stream is None:
                raise SystemExit(f'cannot read overlay member: {relative}')
            data = stream.read()
            expected_size = int(row['bytes'])
            expected_sha = str(row['sha256'])
            if len(data) != expected_size or digest(data) != expected_sha:
                raise SystemExit(f'overlay member verification failed: {relative}')

            target = candidate / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            expected_mode = int(str(row.get('mode', '0o644')), 8)
            os.chmod(target, expected_mode)
            if target.stat().st_size != expected_size or file_digest(target) != expected_sha:
                raise SystemExit(f'installed overlay verification failed: {relative}')
            if stat.S_IMODE(target.stat().st_mode) != expected_mode:
                raise SystemExit(f'installed overlay mode mismatch: {relative}')
            installed.append({'path': relative, 'bytes': expected_size, 'sha256': expected_sha, 'mode': oct(expected_mode)})

    # Final stress-lineage corrections discovered by the first hardened execution.
    # They keep stress-only collection files isolated, ensure every synthetic evidence URL resolves,
    # and derive the homepage selected-work signal from the canonical collection rather than a hard-coded VCE route.
    content_config = 'src/content.config.ts'
    for collection_file in ('milestones.json', 'public-documents.json', 'redirects.json', 'tombstones.json'):
        replace_exact(
            candidate,
            content_config,
            f"loader: file('src/content/{collection_file}'),",
            f"loader: file(process.env.R7E_CONTENT_ROOT ? `${{process.env.R7E_CONTENT_ROOT}}/{collection_file}` : 'src/content/{collection_file}'),",
            f'stress collection isolation for {collection_file}',
        )

    replace_exact(
        candidate,
        'scripts/generate-stress-fixtures.mjs',
        "evidenceLinks: [{label:'Fixture marker',href:`/stress/${n}/`,kind:'artifact'}]",
        "evidenceLinks: [{label:'Fixture route',href:`/work/synthetic-test-record-${n}/`,kind:'artifact'}]",
        'stress evidence link integrity',
    )

    replace_exact(
        candidate,
        'src/pages/index.astro',
        "const work = (await getPublicWork()).filter((entry) => entry.data.featured);",
        "const publicWork = await getPublicWork();\nconst featuredWork = publicWork.filter((entry) => entry.data.featured);\nconst work = featuredWork.length > 0 ? featuredWork : publicWork.slice(0, 3);\nconst primaryWork = publicWork.find((entry) => entry.data.immutableId === 'work-vce') ?? publicWork[0];",
        'canonical selected-work derivation',
    )
    replace_exact(
        candidate,
        'src/pages/index.astro',
        '    <SelectedWorkSignal />',
        '    {primaryWork && <SelectedWorkSignal href={primaryWork.data.route} title={primaryWork.data.title} status={primaryWork.data.summary} />}',
        'canonical selected-work signal',
    )

    delta_paths = [
        'src/content.config.ts',
        'scripts/generate-stress-fixtures.mjs',
        'src/pages/index.astro',
    ]

    package = json.loads((candidate / 'package.json').read_text(encoding='utf-8'))
    scripts = package.get('scripts', {})
    checks = {
        'stressLineageScript': scripts.get('test:stress:lineage') == 'node scripts/verify-stress-lineage.mjs',
        'wranglerOutdir': scripts.get('wrangler:validate') == 'wrangler deploy --dry-run --config wrangler.jsonc --outdir .r7e-tmp/wrangler',
        'threeBearingStops': 'milestones.slice(0, 3)' in (candidate / 'src/pages/index.astro').read_text(encoding='utf-8'),
        'futurePseudoStopRemoved': 'Deeper quantitative and research training' not in (candidate / 'src/pages/index.astro').read_text(encoding='utf-8'),
        'threeColumnBearing': 'repeat(3, 1fr)' in (candidate / 'src/styles/bearing.css').read_text(encoding='utf-8'),
        'longTitleWrap': 'overflow-wrap: anywhere' in (candidate / 'src/styles/project.css').read_text(encoding='utf-8'),
        'axeRawEvidence': '.r7e-tmp/axe' in (candidate / 'tests/accessibility.spec.ts').read_text(encoding='utf-8'),
        'fourLongContentStates': 'metadata-only' in (candidate / 'tests/browser.spec.ts').read_text(encoding='utf-8'),
        'lighthouseRepeatedRuns': 'runsPerRoute = 2' in (candidate / 'scripts/run-lighthouse.mjs').read_text(encoding='utf-8'),
        'networkFailureGate': 'firstPartyHttpErrorCount' in (candidate / 'scripts/network-audit.mjs').read_text(encoding='utf-8'),
        'stressMilestonesIsolated': 'R7E_CONTENT_ROOT}/milestones.json' in (candidate / 'src/content.config.ts').read_text(encoding='utf-8'),
        'stressEvidenceLinksResolve': 'Fixture route' in (candidate / 'scripts/generate-stress-fixtures.mjs').read_text(encoding='utf-8') and '/stress/${n}/' not in (candidate / 'scripts/generate-stress-fixtures.mjs').read_text(encoding='utf-8'),
        'selectedSignalUsesCanonicalWork': 'primaryWork && <SelectedWorkSignal' in (candidate / 'src/pages/index.astro').read_text(encoding='utf-8'),
    }
    if not all(checks.values()):
        raise SystemExit(json.dumps({'passed': False, 'checks': checks}, indent=2))

    print(json.dumps({
        'passed': True,
        'patchSha256': archive_sha,
        'overlayManifestSha256': file_digest(manifest_path),
        'overlayParts': [{'path': path.name, 'bytes': path.stat().st_size, 'sha256': file_digest(path)} for path in part_paths],
        'installedFileCount': len(installed),
        'installedFiles': installed,
        'postOverlayDeltaFiles': [
            {'path': relative, 'bytes': (candidate / relative).stat().st_size, 'sha256': file_digest(candidate / relative)}
            for relative in delta_paths
        ],
        'checks': checks,
        'packageJsonSha256': file_digest(candidate / 'package.json'),
        'packageLockSha256': file_digest(candidate / 'package-lock.json'),
    }, indent=2))


if __name__ == '__main__':
    main()
