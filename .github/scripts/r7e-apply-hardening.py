#!/usr/bin/env python3
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit('usage: r7e-apply-hardening.py <candidate-root>')

    script_dir = Path(__file__).resolve().parent
    candidate = Path(sys.argv[1]).resolve()
    overlay = script_dir / 'r7e-hardening-overlay'
    core = script_dir / 'r7e-apply-hardening-core.py'

    if not (candidate / 'package.json').is_file():
        raise SystemExit(f'candidate source missing: {candidate}')
    if not overlay.is_dir():
        raise SystemExit(f'overlay directory missing: {overlay}')
    if not core.is_file():
        raise SystemExit(f'hardening core missing: {core}')

    for item in sorted(overlay.rglob('*')):
        relative = item.relative_to(overlay)
        target = candidate / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)

    completed = subprocess.run(
        [sys.executable, str(core), str(candidate)],
        check=False,
        text=True,
        capture_output=True,
    )
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


if __name__ == '__main__':
    main()
