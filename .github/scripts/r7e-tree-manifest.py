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
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def excluded_source(rel: str) -> bool:
    parts = rel.split('/')
    if parts and parts[0] in SOURCE_EXCLUDED_TOP:
        return True
    return any(rel == prefix.rstrip('/') or rel.startswith(prefix) for prefix in SOURCE_EXCLUDED_PREFIXES)


def entries(root: Path, profile: str) -> list[dict]:
    out: list[dict] = []
    for p in sorted(root.rglob('*'), key=lambda x: x.relative_to(root).as_posix()):
        rel = p.relative_to(root).as_posix()
        if profile == 'source' and excluded_source(rel):
            continue
        st = p.lstat()
        mode = stat.S_IMODE(st.st_mode)
        if p.is_symlink():
            out.append({'path': rel, 'type': 'symlink', 'mode': mode, 'target': os.readlink(p)})
        elif p.is_file():
            row = {'path': rel, 'type': 'file', 'size': st.st_size, 'sha256': sha256_file(p)}
            if profile == 'source':
                row['mode'] = mode
            out.append(row)
        elif p.is_dir():
            if profile == 'source':
                out.append({'path': rel, 'type': 'dir', 'mode': mode})
    return out


def write_manifest(root: Path, output: Path, profile: str) -> None:
    if not root.is_dir():
        raise SystemExit(f'root not found: {root}')
    data = {'profile': profile, 'root': str(root), 'entries': entries(root, profile)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    print(f'manifest profile={profile} entries={len(data["entries"])} root={root}')


def compare(left: Path, right: Path) -> None:
    a = json.loads(left.read_text())
    b = json.loads(right.read_text())
    if a.get('profile') != b.get('profile'):
        raise SystemExit(f'profile mismatch {a.get("profile")} != {b.get("profile")}')
    ae = a.get('entries', [])
    be = b.get('entries', [])
    if ae != be:
        amap = {x['path']: x for x in ae}
        bmap = {x['path']: x for x in be}
        only_a = sorted(set(amap) - set(bmap))
        only_b = sorted(set(bmap) - set(amap))
        changed = sorted(k for k in set(amap) & set(bmap) if amap[k] != bmap[k])
        print(json.dumps({'match': False, 'onlyLeft': only_a[:50], 'onlyRight': only_b[:50], 'changed': changed[:50]}, indent=2))
        raise SystemExit(1)
    print(f'tree_manifest_match profile={a.get("profile")} entries={len(ae)}')


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='cmd', required=True)
    m = sub.add_parser('manifest')
    m.add_argument('root', type=Path)
    m.add_argument('output', type=Path)
    m.add_argument('--profile', choices=['source', 'dist'], required=True)
    c = sub.add_parser('compare')
    c.add_argument('left', type=Path)
    c.add_argument('right', type=Path)
    args = parser.parse_args()
    if args.cmd == 'manifest':
        write_manifest(args.root, args.output, args.profile)
    else:
        compare(args.left, args.right)

if __name__ == '__main__':
    main()
