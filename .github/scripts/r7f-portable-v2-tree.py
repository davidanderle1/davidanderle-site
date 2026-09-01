#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('root')
    parser.add_argument('output')
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output).resolve()
    rows = []
    for path in sorted((item for item in root.rglob('*') if item.is_file()), key=lambda p: p.relative_to(root).as_posix().encode()):
        relative = path.relative_to(root).as_posix()
        rows.append({'path': relative, 'bytes': path.stat().st_size, 'sha256': sha256_file(path)})
    canonical = json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()
    result = {
        'schema': 'R7F_DETERMINISTIC_TREE_V1',
        'root': root.name,
        'fileCount': len(rows),
        'totalBytes': sum(row['bytes'] for row in rows),
        'treeSha256': hashlib.sha256(canonical).hexdigest(),
        'files': rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('fileCount','totalBytes','treeSha256')}, indent=2))


if __name__ == '__main__':
    main()
