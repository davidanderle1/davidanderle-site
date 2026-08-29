#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path

SOURCE_EXCLUDED_TOP = {'.git', 'node_modules', 'dist', '.astro', '.r7e-tmp', '.wrangler'}
SOURCE_EXCLUDED_PREFIXES = (
    'public/assets/portrait/',
    'public/assets/js/',
    'public/artifacts/',
    'src/data/generated/',
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def excluded_source(rel: str) -> bool:
    parts = rel.split('/')
    if parts and parts[0] in SOURCE_EXCLUDED_TOP:
        return True
    return any(rel == prefix.rstrip('/') or rel.startswith(prefix) for prefix in SOURCE_EXCLUDED_PREFIXES)


def entries(root: Path, profile: str) -> list[dict]:
    result: list[dict] = []
    for path in sorted(root.rglob('*'), key=lambda item: item.relative_to(root).as_posix()):
        rel = path.relative_to(root).as_posix()
        if profile == 'source' and excluded_source(rel):
            continue
        st = path.lstat()
        mode = stat.S_IMODE(st.st_mode)
        if path.is_symlink():
            result.append({'path': rel, 'type': 'symlink', 'mode': mode, 'target': os.readlink(path)})
        elif path.is_file():
            row = {'path': rel, 'type': 'file', 'size': st.st_size, 'sha256': sha256_file(path)}
            if profile == 'source':
                row['mode'] = mode
            result.append(row)
        elif path.is_dir() and profile == 'source':
            result.append({'path': rel, 'type': 'dir', 'mode': mode})
    return result


def write_manifest(root: Path, output: Path, profile: str) -> None:
    if not root.is_dir():
        raise SystemExit(f'root not found: {root}')
    data = {'profile': profile, 'entries': entries(root, profile)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    print(f'manifest profile={profile} entries={len(data["entries"])} root={root}')


def compare(left: Path, right: Path) -> None:
    left_data = json.loads(left.read_text())
    right_data = json.loads(right.read_text())
    if left_data.get('profile') != right_data.get('profile'):
        raise SystemExit(f'profile mismatch {left_data.get("profile")} != {right_data.get("profile")}')
    left_entries = left_data.get('entries', [])
    right_entries = right_data.get('entries', [])
    if left_entries != right_entries:
        left_map = {row['path']: row for row in left_entries}
        right_map = {row['path']: row for row in right_entries}
        only_left = sorted(set(left_map) - set(right_map))
        only_right = sorted(set(right_map) - set(left_map))
        changed = sorted(path for path in set(left_map) & set(right_map) if left_map[path] != right_map[path])
        print(json.dumps({'match': False, 'onlyLeft': only_left[:100], 'onlyRight': only_right[:100], 'changed': changed[:100]}, indent=2))
        raise SystemExit(1)
    print(f'tree_manifest_match profile={left_data.get("profile")} entries={len(left_entries)}')


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    manifest = commands.add_parser('manifest')
    manifest.add_argument('root', type=Path)
    manifest.add_argument('output', type=Path)
    manifest.add_argument('--profile', choices=['source', 'dist'], required=True)
    compare_parser = commands.add_parser('compare')
    compare_parser.add_argument('left', type=Path)
    compare_parser.add_argument('right', type=Path)
    args = parser.parse_args()
    if args.command == 'manifest':
        write_manifest(args.root, args.output, args.profile)
    else:
        compare(args.left, args.right)


if __name__ == '__main__':
    main()
