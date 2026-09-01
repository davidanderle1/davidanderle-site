#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

CORE_PATH = Path(__file__).with_name('r7-history-bound-controller-v3.py')
spec = importlib.util.spec_from_file_location('r7_controller_core_v3', CORE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit('cannot load R7 controller core v3')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def evaluate(
    r7e: dict[str, Any],
    r7f: dict[str, Any],
    external: dict[str, Any],
    traceability: dict[str, Any],
    carry: dict[str, Any],
    authority: dict[str, Any],
    roadmap: dict[str, Any],
    ownership: dict[str, Any],
    live: dict[str, Any],
) -> dict[str, Any]:
    adapter_checks = {
        'r7e-v3-schema': r7e.get('schema') == 'R7E_PORTABLE_JSON_SCHEMA_AUTHORITATIVE_TUPLE_V3',
        'r7f-v7-schema': r7f.get('schema') == 'R7F_PORTABLE_JSON_SCHEMA_AUTHORITATIVE_TUPLE_V7',
        'r7f-v7-correction-model': r7f.get('correctionModel') == 'EXACT_FIVE_CLASS_PATH_REPAIR_R2',
        'r7f-v7-correction-count': r7f.get('correctionClassCount') == 5,
        'external-v5-schema': external.get('schema') == 'R7_PORTABLE_EXTERNAL_AUDIT_TUPLE_V5',
        'external-v5-correction-model': external.get('correctionModel') == 'EXACT_FIVE_CLASS_PATH_REPAIR_R2',
        'external-v5-correction-count': external.get('correctionClassCount') == 5,
    }
    if not all(adapter_checks.values()):
        failed = [name for name, passed in adapter_checks.items() if not passed]
        return {
            'schema': 'R7_HISTORY_BOUND_FINAL_CONTROLLER_V5',
            'passed': False,
            'decision': 'R7_NOT_CLOSED',
            'maximumAuthorizedVerdict': 'NO_CLOSURE_AUTHORIZED',
            'checks': adapter_checks,
            'checkCount': len(adapter_checks),
            'passedCheckCount': sum(adapter_checks.values()),
            'failedChecks': failed,
            'blockers': [{'check': name, 'blocker': name} for name in failed],
            'compatibilityAdapter': {
                'passed': False,
                'allowedTransformations': [
                    'R7F tuple schema V7 to the core V4 label only',
                    'External audit tuple schema V5 to the core V3 label only',
                ],
                'digestOrLinkMutationAllowed': False,
            },
        }

    normalized_r7f = copy.deepcopy(r7f)
    normalized_external = copy.deepcopy(external)
    normalized_r7f['schema'] = 'R7F_PORTABLE_JSON_SCHEMA_AUTHORITATIVE_TUPLE_V4'
    normalized_external['schema'] = 'R7_PORTABLE_EXTERNAL_AUDIT_TUPLE_V3'
    result = core.evaluate(
        r7e,
        normalized_r7f,
        normalized_external,
        traceability,
        carry,
        authority,
        roadmap,
        ownership,
        live,
    )
    core_checks = result.get('checks', {})
    combined_checks = {**adapter_checks, **{f'core:{name}': passed for name, passed in core_checks.items()}}
    failed = [name for name, passed in combined_checks.items() if not passed]
    passed = not failed and result.get('passed') is True
    result.update({
        'schema': 'R7_HISTORY_BOUND_FINAL_CONTROLLER_V5',
        'passed': passed,
        'decision': 'R7_CLOSED' if passed else 'R7_NOT_CLOSED',
        'maximumAuthorizedVerdict': 'R7_TECHNICAL_ARCHITECTURE_CLOSED' if passed else 'NO_CLOSURE_AUTHORIZED',
        'checks': combined_checks,
        'checkCount': len(combined_checks),
        'passedCheckCount': sum(combined_checks.values()),
        'failedChecks': failed,
        'blockers': [] if passed else [{'check': name, 'blocker': name} for name in failed],
        'compatibilityAdapter': {
            'passed': True,
            'allowedTransformations': [
                {'field': 'r7f.schema', 'from': 'R7F_PORTABLE_JSON_SCHEMA_AUTHORITATIVE_TUPLE_V7', 'toCoreLabel': 'R7F_PORTABLE_JSON_SCHEMA_AUTHORITATIVE_TUPLE_V4'},
                {'field': 'external.schema', 'from': 'R7_PORTABLE_EXTERNAL_AUDIT_TUPLE_V5', 'toCoreLabel': 'R7_PORTABLE_EXTERNAL_AUDIT_TUPLE_V3'},
            ],
            'digestOrLinkMutationAllowed': False,
            'correctionModelsValidatedBeforeNormalization': True,
            'originalR7fArtifactDigest': r7f.get('artifact', {}).get('digest'),
            'normalizedR7fArtifactDigest': normalized_r7f.get('artifact', {}).get('digest'),
            'originalExternalArtifactDigest': external.get('artifact', {}).get('digest'),
            'normalizedExternalArtifactDigest': normalized_external.get('artifact', {}).get('digest'),
        },
    })
    result['evidenceChain'] = {
        'r7e': {'commit': r7e.get('commit'), 'runId': r7e.get('runId'), 'artifact': r7e.get('artifact')},
        'r7f': {'commit': r7f.get('commit'), 'runId': r7f.get('runId'), 'artifact': r7f.get('artifact')},
        'external': {'commit': external.get('commit'), 'runId': external.get('runId'), 'artifact': external.get('artifact')},
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    names = ('r7e','r7f','external','traceability','carry','authority','roadmap','ownership','live')
    for name in (*names, 'output'):
        parser.add_argument(f'--{name}', required=True)
    args = parser.parse_args()
    paths = {name: Path(getattr(args, name)).resolve() for name in names}
    result = evaluate(*(load(paths[name]) for name in names))
    result['inputSha256'] = {name: sha256_file(path) for name, path in paths.items()}
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    if not result.get('passed'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
