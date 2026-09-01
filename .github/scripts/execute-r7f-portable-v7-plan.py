#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

BASE_PATH = Path(__file__).with_name('execute-r7f-portable-v5-plan.py')
spec = importlib.util.spec_from_file_location('r7f_v5_executor', BASE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit('cannot load R7F v5 executor primitives')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

WRANGLER_RELATIVE_BLOCK = '''          test -n "$(find r7f-evidence/wrangler -type f -print -quit)"
          find r7f-evidence/wrangler -type f -print | sort > r7f-evidence/wrangler-files.txt
'''
WRANGLER_ABSOLUTE_BLOCK = '''          test -n "$(find "$GITHUB_WORKSPACE/r7f-evidence/wrangler" -type f -print -quit)"
          find "$GITHUB_WORKSPACE/r7f-evidence/wrangler" -type f -print | sort > "$GITHUB_WORKSPACE/r7f-evidence/wrangler-files.txt"
'''

base.CORRECTIONS = [
    ('../../../r7f-evidence', '$GITHUB_WORKSPACE/r7f-evidence', 'absolute evidence paths'),
    ('cd r7f-input/run1', 'cd "$GITHUB_WORKSPACE/r7f-input/run1"', 'absolute candidate run directory'),
    ("root=Path('r7f-evidence/lighthouse')", "root=Path(__import__('os').environ['GITHUB_WORKSPACE'])/'r7f-evidence/lighthouse'", 'absolute Lighthouse report root'),
    ("Path('r7f-evidence/LIGHTHOUSE_AUDIT.json').write_text", "(Path(__import__('os').environ['GITHUB_WORKSPACE'])/'r7f-evidence/LIGHTHOUSE_AUDIT.json').write_text", 'absolute Lighthouse summary output'),
    (WRANGLER_RELATIVE_BLOCK, WRANGLER_ABSOLUTE_BLOCK, 'absolute Wrangler inventory paths'),
]


def main() -> None:
    if len(sys.argv) != 5:
        raise SystemExit('usage: execute-r7f-portable-v7-plan.py INPUT_YAML CORRECTED_YAML DIFF REPORT')
    base.main()
    report_path = Path(sys.argv[4]).resolve()
    report = json.loads(report_path.read_text(encoding='utf-8'))
    report['schema'] = 'R7F_CORRECTED_PLAN_EXECUTION_V7'
    report['correctionModel'] = 'EXACT_FIVE_CLASS_PATH_REPAIR_R2'
    report['correctionClassCount'] = 5
    report['anchorCorrection'] = 'Wrangler inventory block preserves the original test -n predicate.'
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({
        'schema': report['schema'],
        'passed': report.get('passed'),
        'correctionModel': report['correctionModel'],
        'correctionClassCount': report['correctionClassCount'],
        'totalReplacementCount': report.get('totalReplacementCount'),
        'executedRunStepCount': len(report.get('executed', [])),
    }, indent=2))


if __name__ == '__main__':
    main()
