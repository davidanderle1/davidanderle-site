#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

PATH = Path('.github/workflows/r7-full-history-traceability-final.yml')
TARGET = "and rb.get('R7-032',{}).get('status')==SAT"
INSERT = "and all(r['status'].startswith('DEFERRED_BOUND_') for r in rs if r['phase'] in {f'R{i}' for i in range(8,14)})"


def main() -> None:
    lines = PATH.read_text(encoding='utf-8').splitlines(keepends=True)
    if sum(INSERT in line for line in lines):
        raise SystemExit('future-phase deferral invariant already present')
    matches = [i for i, line in enumerate(lines) if TARGET in line]
    if len(matches) != 1:
        raise SystemExit(f'future-phase anchor count={len(matches)}')
    index = matches[0]
    line = lines[index]
    prefix = line[: line.index(TARGET)]
    if len(prefix) < 10 or prefix.strip():
        raise SystemExit(f'unexpected YAML/Python indentation prefix: {prefix!r}')
    lines.insert(index + 1, prefix + INSERT + '\n')
    PATH.write_text(''.join(lines), encoding='utf-8')
    print(f'patched {PATH} with prefix length {len(prefix)}')


if __name__ == '__main__':
    main()
