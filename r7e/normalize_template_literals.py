#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

TARGETS = [
    Path('r7e/template_verification.py'),
    Path('r7e/template_evidence.py'),
]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    rows = []
    for path in TARGETS:
        before = path.read_bytes()
        text = before.decode('utf-8')
        count = text.count('d("""')
        if count == 0:
            if 'd(r"""' not in text:
                raise RuntimeError(f'{path}: neither legacy nor normalized template calls found')
            after = before
            status = 'already-normalized'
        else:
            text = text.replace('d("""', 'd(r"""')
            after = text.encode('utf-8')
            path.write_bytes(after)
            status = 'normalized'
        rows.append({
            'path': path.as_posix(),
            'status': status,
            'legacyCallsRewritten': count,
            'beforeSha256': sha256(before),
            'afterSha256': sha256(after),
        })
    report = {
        'schema': 'davidanderle.r7e.template-normalization.v1',
        'reason': 'Embedded JavaScript/Python templates require raw Python triple strings so backslash escapes such as \\n remain source-code escapes instead of becoming literal newlines before emission.',
        'targets': rows,
    }
    out = Path('R7E_TEMPLATE_NORMALIZATION.json')
    out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
