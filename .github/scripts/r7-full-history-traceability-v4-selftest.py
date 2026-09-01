#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path(__file__).with_name('verify-r7-full-history-traceability-v4.py')
spec = importlib.util.spec_from_file_location('traceability_v4', MODULE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit('cannot load traceability verifier')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def load(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ('corpus','traceability','carry','readiness','output'):
        parser.add_argument(f'--{name}', required=True)
    args = parser.parse_args()
    paths = {name: Path(getattr(args, name)).resolve() for name in ('corpus','traceability','carry','readiness')}
    authentic = {name: load(path) for name, path in paths.items()}
    authentic_report = verifier.verify(
        authentic['corpus'], authentic['traceability'], authentic['carry'], authentic['readiness'], paths
    )
    if not authentic_report.get('passed'):
        raise SystemExit('authentic traceability does not pass')

    cases = []

    def run_case(name, mutate):
        data = copy.deepcopy(authentic)
        mutate(data)
        rejected = False
        error = None
        try:
            verifier.verify(data['corpus'], data['traceability'], data['carry'], data['readiness'], paths)
        except verifier.VerificationFailure as exc:
            rejected = True
            error = str(exc)
        cases.append({'name': name, 'rejected': rejected, 'error': error})

    run_case('duplicate-requirement-id', lambda d: d['traceability']['requirements'][1].__setitem__('id', d['traceability']['requirements'][0]['id']))
    run_case('open-r7-blocker', lambda d: d['traceability']['requirements'][0].__setitem__('status', 'OPEN_R7_BLOCKER'))
    run_case('missing-source-locator', lambda d: d['traceability']['requirements'][0].__setitem__('sourceLocators', []))
    run_case('missing-resolved-evidence', lambda d: d['traceability']['requirements'][0].__setitem__('evidence', []))
    run_case('orphan-injection', lambda d: d['traceability'].__setitem__('orphanedRequirementIds', ['ORPHAN-INJECTED']))
    run_case('raw-accounting-mismatch', lambda d: d['traceability']['rawNormativeReview'].__setitem__('duplicateClauses', 1))
    run_case('remove-carry-entry', lambda d: d['carry']['entries'].pop())
    run_case('wrong-carry-phase', lambda d: d['carry']['entries'][0].__setitem__('targetPhase', 'R13'))
    run_case('premature-whole-site-claim', lambda d: d['traceability']['requestedClosureClaims'].append('WHOLE_SITE_COMPLETE'))
    run_case('ownership-waiver-erasure', lambda d: d['traceability']['requirements'][next(i for i,r in enumerate(d['traceability']['requirements']) if r['id']=='R6-004')].pop('waiverId'))

    passed = len(cases) == 10 and all(row['rejected'] for row in cases)
    report = {
        'schema': 'R7_FULL_HISTORY_TRACEABILITY_SELFTEST_V4',
        'passed': passed,
        'caseCount': len(cases),
        'passedCaseCount': sum(row['rejected'] for row in cases),
        'authenticDecision': authentic_report.get('decision'),
        'cases': cases,
    }
    output = Path(args.output).resolve()
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
