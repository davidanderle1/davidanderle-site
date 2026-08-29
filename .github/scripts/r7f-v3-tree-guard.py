#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path

SOURCE_EXCLUDED_TOP = {'.git', 'node_modules', 'dist', '.astro', '.r7e-tmp'}
SOURCE_EXCLUDED_PREFIXES = (
    'public/assets/portrait/',
    'public/assets/js/',
    'public/artifacts/',
    'src/data/generated/',
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def skip_source(relative: str) -> bool:
    parts = relative.split('/')
    return bool(parts and parts[0] in SOURCE_EXCLUDED_TOP) or relative.startswith(SOURCE_EXCLUDED_PREFIXES)


def scan(root: Path, source_mode: bool = False) -> list[dict[str, object]]:
    root = root.resolve()
    rows: list[dict[str, object]] = []
    for path in sorted(root.rglob('*'), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if source_mode and skip_source(relative):
            continue
        metadata = path.lstat()
        mode = stat.S_IMODE(metadata.st_mode)
        if path.is_symlink():
            rows.append({'path': relative, 'type': 'symlink', 'mode': oct(mode), 'target': os.readlink(path)})
        elif path.is_file():
            rows.append({'path': relative, 'type': 'file', 'mode': oct(mode), 'size': metadata.st_size, 'sha256': sha256_file(path)})
    return rows


def tree_digest(rows: list[dict[str, object]]) -> str:
    encoded = (json.dumps(rows, sort_keys=True, separators=(',', ':')) + '\n').encode()
    return hashlib.sha256(encoded).hexdigest()


def manifest(root: Path, output: Path, source_mode: bool) -> dict[str, object]:
    rows = scan(root, source_mode)
    result = {'root': str(root.resolve()), 'sourceMode': source_mode, 'entryCount': len(rows), 'treeSha256': tree_digest(rows), 'entries': rows}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'entryCount': len(rows), 'treeSha256': result['treeSha256'], 'output': str(output)}, indent=2))
    return result


def compare(first: Path, second: Path, output: Path, source_mode: bool) -> dict[str, object]:
    first_rows = scan(first, source_mode)
    second_rows = scan(second, source_mode)
    first_by_path = {row['path']: row for row in first_rows}
    second_by_path = {row['path']: row for row in second_rows}
    only_first = sorted(set(first_by_path) - set(second_by_path))
    only_second = sorted(set(second_by_path) - set(first_by_path))
    changed = sorted(path for path in set(first_by_path) & set(second_by_path) if first_by_path[path] != second_by_path[path])
    result = {
        'passed': not only_first and not only_second and not changed,
        'sourceMode': source_mode,
        'first': {'root': str(first.resolve()), 'entryCount': len(first_rows), 'treeSha256': tree_digest(first_rows)},
        'second': {'root': str(second.resolve()), 'entryCount': len(second_rows), 'treeSha256': tree_digest(second_rows)},
        'onlyFirst': only_first,
        'onlySecond': only_second,
        'changed': changed,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    if not result['passed']:
        raise SystemExit(1)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    manifest_parser = commands.add_parser('manifest')
    manifest_parser.add_argument('root', type=Path)
    manifest_parser.add_argument('output', type=Path)
    manifest_parser.add_argument('--source', action='store_true')
    compare_parser = commands.add_parser('compare')
    compare_parser.add_argument('first', type=Path)
    compare_parser.add_argument('second', type=Path)
    compare_parser.add_argument('output', type=Path)
    compare_parser.add_argument('--source', action='store_true')
    args = parser.parse_args()
    if args.command == 'manifest':
        manifest(args.root, args.output, args.source)
    else:
        compare(args.first, args.second, args.output, args.source)


if __name__ == '__main__':
    main()
