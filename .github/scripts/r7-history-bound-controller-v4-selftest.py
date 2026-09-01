#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path(__file__).with_name('r7-history-bound-controller-v4.py')
spec = importlib.util.spec_from_file_location('r7_controller_v4', MODULE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit('cannot load controller v4')
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


def load(path: str):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ('r7e','r7f','external','traceability','carry','authority','roadmap','ownership','live','output'):
        parser.add_argument(f'--{name}', required=True)
    args = parser.parse_args()
    names = ('r7e','r7f','external','traceability','carry','authority','roadmap','ownership','live')
    authentic = {name: load(getattr(args, name)) for name in names}

    def evaluate(dataset):
        return controller.evaluate(*(dataset[name] for name in names))

    authentic_result = evaluate(authentic)
    if not authentic_result.get('passed'):
        raise SystemExit('authentic controller v4 input does not pass')

    cases = []

    def run_case(name, expected, mutate):
        data = copy.deepcopy(authentic)
        mutate(data)
        result = evaluate(data)
        rejected = result.get('passed') is False and expected in result.get('failedChecks', [])
        cases.append({'name':name,'expectedFailedCheck':expected,'rejected':rejected,'decision':result.get('decision'),'failedChecks':result.get('failedChecks',[])})

    run_case('r7f-schema','r7f-v5-schema',lambda d:d['r7f'].__setitem__('schema','R7F_PORTABLE_JSON_SCHEMA_AUTHORITATIVE_TUPLE_V4'))
    run_case('r7f-correction-model','r7f-v5-correction-model',lambda d:d['r7f'].__setitem__('correctionModel','UNRECORDED_PATCH'))
    run_case('external-schema','external-v4-schema',lambda d:d['external'].__setitem__('schema','R7_PORTABLE_EXTERNAL_AUDIT_TUPLE_V3'))
    run_case('external-correction-model','external-v4-correction-model',lambda d:d['external'].__setitem__('correctionModel','UNRECORDED_PATCH'))
    run_case('r7e-artifact-digest','core:r7e-artifact-digest',lambda d:d['r7e']['artifact'].__setitem__('digest','sha256:'+'0'*64))
    run_case('r7f-builder-link','core:r7f-builder-commit-link',lambda d:d['r7f']['builder'].__setitem__('commit','0'*40))
    run_case('external-r7f-link','core:external-r7f-digest-link',lambda d:d['external']['r7f'].__setitem__('artifactDigest','sha256:'+'1'*64))
    run_case('main-mutation','core:live-main-unchanged',lambda d:d['live']['main'].__setitem__('currentSha','2'*40))
    run_case('orphaned-requirement','core:traceability-orphan-list-empty',lambda d:d['traceability'].__setitem__('orphanedRequirementIds',['INJECTED']))
    def blocker(data):
        data['traceability']['requirements'][0]['status']='OPEN_R7_BLOCKER'
        data['traceability']['summary']['openR7BlockerCount']=1
    run_case('open-r7-blocker','core:traceability-no-open-r7-blocker',blocker)
    run_case('missing-carry','core:deferred-carry-bijection',lambda d:d['carry']['entries'].pop())
    def reorder(data):
        values=data['authority']['orderedAuthorities']; values[0],values[1]=values[1],values[0]
    run_case('authority-order','core:authority-order',reorder)
    run_case('ownership-rewrite','core:ownership-formal-blind-not-recorded',lambda d:d['ownership'].__setitem__('formalQuantitativeBlindProtocolRecorded',True))
    run_case('whole-site-claim','core:no-forbidden-closure-claims',lambda d:d['traceability']['requestedClosureClaims'].append('WHOLE_SITE_COMPLETE'))

    passed=len(cases)==14 and all(row['rejected'] for row in cases)
    report={'schema':'R7_HISTORY_BOUND_CONTROLLER_SELFTEST_V4','passed':passed,'caseCount':len(cases),'passedCaseCount':sum(row['rejected'] for row in cases),'authenticDecision':authentic_result.get('decision'),'cases':cases}
    output=Path(args.output).resolve(); output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if not passed: raise SystemExit(1)


if __name__=='__main__':
    main()
