#!/usr/bin/env python3
from pathlib import Path
import shutil
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else 'candidate').resolve()
source = Path(__file__).resolve().parent / 'r7e-hardening-overlay'
if not source.is_dir():
    raise SystemExit(f'overlay directory missing: {source}')
for item in source.rglob('*'):
    rel = item.relative_to(source)
    target = root / rel
    if item.is_dir():
        target.mkdir(parents=True, exist_ok=True)
    elif item.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
print(f'applied file overlay from {source} to {root}')
