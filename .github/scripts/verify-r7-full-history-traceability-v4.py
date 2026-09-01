#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

PHASES = {f'R{number}' for number in range(1, 14)}
RESOLVED = {'SATISFIED_R7', 'SATISFIED_BY_SUPERSESSION', 'USER_WAIVER_BOUND', 'DEVIATION_ACCEPTED'}
DEFERRED = {f'DEFERRED_BOUND_R{number}' for number in range(8, 14)}
ALLOWED = RESOLVED | DEFERRED | {'OPEN_R7_BLOCKER'}


class VerificationFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationFailure(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def verify(corpus: dict[str, Any], traceability: dict[str, Any], carry: dict[str, Any], readiness: dict[str, Any], paths: dict[str, Path]) -> dict[str, Any]:
    checks: dict[str, bool] = {}

    def check(name: str, condition: bool) -> None:
        checks[name] = bool(condition)

    check('corpus-schema', corpus.get('schema') == 'R7_FULL_HISTORY_CORPUS_MANIFEST_V4')
    check('corpus-id', isinstance(corpus.get('corpusId'), str) and bool(corpus.get('corpusId')))
    check('corpus-visible-messages', corpus.get('conversation', {}).get('visibleMessageCount') == 847)
    check('corpus-message-sum', corpus.get('conversation', {}).get('userMessageCount', 0) + corpus.get('conversation', {}).get('assistantMessageCount', 0) == 847)
    check('corpus-top-level-packages', corpus.get('historicalPackages', {}).get('suppliedTopLevelPackageCount', 0) >= 28)
    check('corpus-nested-zips', corpus.get('historicalPackages', {}).get('nestedZipCount', 0) >= 32)
    check('corpus-files', corpus.get('historicalPackages', {}).get('recursiveFileRecordCountMinimum', 0) >= 10000)
    check('corpus-text-documents', corpus.get('historicalPackages', {}).get('textDocumentCountMinimum', 0) >= 8800)
    check('corpus-authorities', corpus.get('historicalPackages', {}).get('authoritativeSourceCount', 0) >= 55)
    check('corpus-integrity-recorded', corpus.get('integrity', {}).get('reuploadedArchivesTested') is True and corpus.get('integrity', {}).get('reuploadedArchiveIntegrityResult') == 'PASS')
    check('corpus-not-publicly-republished', corpus.get('integrity', {}).get('rawSourceBytesCommittedToPublicRepository') is False)

    check('traceability-schema', traceability.get('schema') == 'R7_FULL_HISTORY_TRACEABILITY_V4')
    check('traceability-corpus-link', traceability.get('corpusId') == corpus.get('corpusId'))
    requirements = traceability.get('requirements', [])
    check('requirements-list', isinstance(requirements, list) and len(requirements) >= 75)
    ids = [row.get('id') for row in requirements if isinstance(row, dict)]
    check('requirements-unique', len(ids) == len(set(ids)) and len(ids) == len(requirements))
    check('requirements-material', all(row.get('material') is True for row in requirements if isinstance(row, dict)))
    check('requirements-phase', all(row.get('phase') in PHASES for row in requirements if isinstance(row, dict)))
    check('requirements-status', all(row.get('status') in ALLOWED for row in requirements if isinstance(row, dict)))
    check('requirements-text', all(isinstance(row.get('requirement'), str) and bool(row.get('requirement').strip()) for row in requirements if isinstance(row, dict)))
    check('requirements-sources', all(isinstance(row.get('sourceLocators'), list) and row.get('sourceLocators') for row in requirements if isinstance(row, dict)))
    check('requirements-resolved-evidence', all(isinstance(row.get('evidence'), list) and row.get('evidence') for row in requirements if isinstance(row, dict) and row.get('status') in RESOLVED))
    check('requirements-no-open-blocker', not any(row.get('status') == 'OPEN_R7_BLOCKER' for row in requirements if isinstance(row, dict)))
    check('requirements-waiver-bound', all(isinstance(row.get('waiverId'), str) and bool(row.get('waiverId')) for row in requirements if isinstance(row, dict) and row.get('status') == 'USER_WAIVER_BOUND'))
    check('requirements-deviation-bound', all(isinstance(row.get('deviationId'), str) and bool(row.get('deviationId')) for row in requirements if isinstance(row, dict) and row.get('status') == 'DEVIATION_ACCEPTED'))
    check('traceability-orphans-zero', traceability.get('orphanedRequirementIds') == [])
    check('traceability-contradictions-zero', traceability.get('contradictions') == [])
    check('traceability-unexplained-deviations-zero', traceability.get('unexplainedDeviations') == [])
    check('traceability-exact-scope', traceability.get('requestedClosureClaims') == ['R7_TECHNICAL_ARCHITECTURE_CLOSED'])

    review = traceability.get('rawNormativeReview', {})
    check('review-counting-unit-honest', review.get('rawLexicalClauseCountNotClaimed') is True and isinstance(review.get('countingUnit'), str) and bool(review.get('countingUnit')))
    check('review-corpus-hash', review.get('corpusManifestSha256') == sha256_file(paths['corpus']))
    total = review.get('totalClauses')
    categories = sum(review.get(key, 0) for key in ('mappedMaterialClauses', 'supersededClauses', 'executionBoilerplateClauses', 'researchMethodClauses', 'duplicateClauses'))
    check('review-total-positive', isinstance(total, int) and total > 0)
    check('review-accounting', isinstance(total, int) and total == categories)
    check('review-material-complete', review.get('materialClauses') == review.get('mappedMaterialClauses') == len(requirements))
    check('review-unresolved-zero', review.get('unresolvedMaterialClauses') == [])

    check('carry-schema', carry.get('schema') == 'R7_CARRY_FORWARD_REGISTER_V4')
    check('carry-corpus-link', carry.get('corpusId') == corpus.get('corpusId'))
    entries = carry.get('entries', [])
    check('carry-list', isinstance(entries, list))
    entry_ids = [row.get('id') for row in entries if isinstance(row, dict)]
    check('carry-unique', len(entry_ids) == len(set(entry_ids)) == len(entries))
    check('carry-fields', all(row.get('status') == 'BOUND' and row.get('targetPhase') in {f'R{number}' for number in range(8, 14)} and isinstance(row.get('requirementId'), str) and isinstance(row.get('gate'), str) and bool(row.get('gate')) and isinstance(row.get('rationale'), str) and bool(row.get('rationale')) for row in entries if isinstance(row, dict)))
    check('carry-unbound-zero', carry.get('unboundEntries') == [])

    deferred_rows = [row for row in requirements if isinstance(row, dict) and row.get('status') in DEFERRED]
    deferred_ids = [row.get('carryForwardId') for row in deferred_rows]
    check('deferred-carry-present', all(isinstance(value, str) and bool(value) for value in deferred_ids))
    check('deferred-carry-bijection', set(deferred_ids) == set(entry_ids) and len(deferred_ids) == len(entry_ids))
    requirement_by_id = {row['id']: row for row in requirements}
    check('carry-requirement-links', all(row.get('requirementId') in requirement_by_id for row in entries if isinstance(row, dict)))
    check('carry-phase-links', all(requirement_by_id[row['requirementId']]['status'] == f"DEFERRED_BOUND_{row['targetPhase']}" for row in entries if row.get('requirementId') in requirement_by_id))
    target_counts = Counter(row.get('targetPhase') for row in entries)
    check('carry-all-future-phases-covered', all(target_counts.get(f'R{number}', 0) >= 1 for number in range(8, 14)))

    summary = traceability.get('summary', {})
    check('summary-requirement-count', summary.get('requirementCount') == len(requirements))
    check('summary-deferred-count', summary.get('deferredRequirementCount') == len(deferred_rows) == len(entries))
    check('summary-open-zero', summary.get('openR7BlockerCount') == 0)
    check('summary-orphan-zero', summary.get('orphanedRequirementCount') == 0)

    check('readiness-schema', readiness.get('schema') == 'R7_ZERO_ORPHAN_READINESS_V4')
    check('readiness-pass', readiness.get('passed') is True and readiness.get('decision') == 'ZERO_ORPHAN_TRACEABILITY_READY')
    check('readiness-corpus-hash', readiness.get('corpusManifestSha256') == sha256_file(paths['corpus']))
    check('readiness-trace-hash', readiness.get('traceabilitySha256') == sha256_file(paths['traceability']))
    check('readiness-carry-hash', readiness.get('carryForwardSha256') == sha256_file(paths['carry']))
    check('readiness-counts', readiness.get('requirementCount') == len(requirements) and readiness.get('deferredRequirementCount') == len(entries))
    check('readiness-zeroes', all(readiness.get(key) == 0 for key in ('openR7BlockerCount','orphanedRequirementCount','unresolvedMaterialClauseCount','contradictionCount','unexplainedDeviationCount')))
    check('readiness-ownership-honesty', readiness.get('formalBlindOwnershipProtocolClaimedComplete') is False)

    required_ids = {
        'R1-002','R1-004','R1-008','R4-005','R4-006','R4-007','R4-008',
        'R6-001','R6-004','R6-005','R6-006',
        'R7-001','R7-003','R7-004','R7-005','R7-010','R7-011','R7-013','R7-014',
        'R7-015','R7-016','R7-018','R7-019','R7-020','R7-022','R7-023','R7-025','R7-026','R7-027','R7-029','R7-031',
        'R8-003','R9-004','R10-001','R11-001','R12-001','R13-001',
    }
    check('critical-requirements-present', required_ids.issubset(set(ids)))
    check('ownership-waiver-exact', requirement_by_id.get('R6-004', {}).get('waiverId') == 'WAIVER-BEARING-FORMAL-BLIND-PROTOCOL-R7')
    check('portable-schema-satisfied', requirement_by_id.get('R7-003', {}).get('status') == 'SATISFIED_R7')
    check('historical-pii-deferred-r8', requirement_by_id.get('R1-008', {}).get('status') == 'DEFERRED_BOUND_R8')
    check('external-profile-deferred-r9', requirement_by_id.get('R1-007', {}).get('status') == 'DEFERRED_BOUND_R9')

    failed = sorted(name for name, passed in checks.items() if not passed)
    require(not failed, f'traceability verification failed: {failed}')
    return {
        'schema': 'R7_FULL_HISTORY_TRACEABILITY_VERIFICATION_V4',
        'passed': True,
        'decision': 'ZERO_ORPHAN_TRACEABILITY_VERIFIED',
        'checkCount': len(checks),
        'passedCheckCount': len(checks),
        'failedChecks': [],
        'checks': checks,
        'metrics': {
            'requirementCount': len(requirements),
            'deferredRequirementCount': len(entries),
            'resolvedRequirementCount': len(requirements) - len(entries),
            'futurePhaseCounts': dict(sorted(target_counts.items())),
            'corpusVisibleMessages': corpus.get('conversation', {}).get('visibleMessageCount'),
            'authoritativeSources': corpus.get('historicalPackages', {}).get('authoritativeSourceCount'),
        },
        'inputSha256': {name: sha256_file(path) for name, path in paths.items()},
        'scope': 'Full-history requirement accounting for the R7 technical-architecture closure decision; R8-R13 remain explicitly open.',
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ('corpus','traceability','carry','readiness','output'):
        parser.add_argument(f'--{name}', required=True)
    args = parser.parse_args()
    paths = {name: Path(getattr(args, name)).resolve() for name in ('corpus','traceability','carry','readiness')}
    try:
        report = verify(*(load(paths[name]) for name in ('corpus','traceability','carry','readiness')), paths)
    except VerificationFailure as exc:
        report = {'schema':'R7_FULL_HISTORY_TRACEABILITY_VERIFICATION_V4','passed':False,'decision':'TRACEABILITY_REJECTED','error':str(exc)}
        Path(args.output).resolve().write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, indent=2))
        raise SystemExit(1)
    Path(args.output).resolve().write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
