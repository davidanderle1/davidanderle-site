#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path(__file__).with_name('r7-history-bound-controller-v3.py')
spec = importlib.util.spec_from_file_location('r7_controller_v3', MODULE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit('cannot load controller module')
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


def load(path: str):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ('r7e', 'r7f', 'external', 'traceability', 'carry', 'authority', 'roadmap', 'ownership', 'live', 'output'):
        parser.add_argument(f'--{name}', required=True)
    args = parser.parse_args()
    names = ('r7e', 'r7f', 'external', 'traceability', 'carry', 'authority', 'roadmap', 'ownership', 'live')
    authentic = {name: load(getattr(args, name)) for name in names}

    def evaluate(dataset):
        return controller.evaluate(*(dataset[name] for name in names))

    authentic_result = evaluate(authentic)
    if not authentic_result.get('passed'):
        raise SystemExit('authentic controller input does not pass; self-test is not meaningful')

    mutations = []

    def add(name, expected, mutate):
        mutations.append((name, expected, mutate))

    add('r7e-artifact-digest', 'r7e-artifact-digest', lambda d: d['r7e']['artifact'].__setitem__('digest', 'sha256:' + '0' * 64))
    add('r7f-builder-link', 'r7f-builder-commit-link', lambda d: d['r7f']['builder'].__setitem__('commit', '0' * 40))
    add('external-pass', 'external-pass', lambda d: d['external'].__setitem__('passed', False))
    add('main-mutation', 'live-main-unchanged', lambda d: d['live']['main'].__setitem__('currentSha', '1' * 40))
    add('orphaned-requirement', 'traceability-orphan-list-empty', lambda d: d['traceability'].__setitem__('orphanedRequirementIds', ['ORPHAN-INJECTED']))

    def open_blocker(data):
        data['traceability']['requirements'][0]['status'] = 'OPEN_R7_BLOCKER'
        data['traceability']['summary']['openR7BlockerCount'] = 1
    add('open-r7-blocker', 'traceability-no-open-r7-blocker', open_blocker)

    def missing_carry(data):
        data['carry']['entries'].pop()
    add('missing-carry-forward', 'deferred-carry-bijection', missing_carry)

    def authority_reorder(data):
        values = data['authority']['orderedAuthorities']
        values[0], values[1] = values[1], values[0]
    add('authority-reorder', 'authority-order', authority_reorder)

    add('ownership-history-rewrite', 'ownership-formal-blind-not-recorded', lambda d: d['ownership'].__setitem__('formalQuantitativeBlindProtocolRecorded', True))

    def close_r8(data):
        next(row for row in data['roadmap']['phases'] if row['id'] == 'R8')['status'] = 'COMPLETED'
    add('premature-r8-closure', 'roadmap-r8-r13-not-closed', close_r8)

    add('whole-site-completion-claim', 'no-forbidden-closure-claims', lambda d: d['traceability']['requestedClosureClaims'].append('WHOLE_SITE_COMPLETE'))
    add('raw-clause-accounting', 'raw-review-accounting', lambda d: d['traceability']['rawNormativeReview'].__setitem__('duplicateClauses', d['traceability']['rawNormativeReview']['duplicateClauses'] + 1))

    results = []
    for name, expected_check, mutate in mutations:
        dataset = copy.deepcopy(authentic)
        mutate(dataset)
        result = evaluate(dataset)
        rejected = result.get('passed') is False and expected_check in result.get('failedChecks', [])
        results.append({
            'name': name,
            'expectedFailedCheck': expected_check,
            'rejected': rejected,
            'decision': result.get('decision'),
            'failedChecks': result.get('failedChecks', []),
        })

    passed = len(results) == 12 and all(row['rejected'] for row in results)
    report = {
        'schema': 'R7_HISTORY_BOUND_CONTROLLER_SELFTEST_V3',
        'passed': passed,
        'caseCount': len(results),
        'passedCaseCount': sum(row['rejected'] for row in results),
        'authenticDecision': authentic_result.get('decision'),
        'cases': results,
    }
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
