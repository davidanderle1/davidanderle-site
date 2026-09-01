#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

PHASES = [f'R{number}' for number in range(1, 14)]
RESOLVED_STATUSES = {
    'SATISFIED_R7',
    'SATISFIED_BY_SUPERSESSION',
    'USER_WAIVER_BOUND',
    'DEVIATION_ACCEPTED',
}
DEFERRED_STATUSES = {f'DEFERRED_BOUND_R{number}' for number in range(8, 14)}
ALLOWED_STATUSES = RESOLVED_STATUSES | DEFERRED_STATUSES | {'OPEN_R7_BLOCKER'}
EXPECTED_AUTHORITY_ORDER = [
    'CURRENT_FACTUAL_TRUTH_AND_PRIVACY',
    'R5_PHOTOGRAPHY_AUTHORITY',
    'R6C_R6D_BEARING_AUTHORITY',
    'R4_IDENTITY_CONTENT_AND_IA_AUTHORITY',
    'CURRENT_OFFICIAL_TECHNICAL_DOCUMENTATION_AND_EMPIRICAL_EVIDENCE',
    'R7_TECHNICAL_ARCHITECTURE_AUTHORITY',
    'OLDER_PROTOTYPES_AND_AUXILIARY_MATERIAL',
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def sha256_digest(value: Any) -> bool:
    return isinstance(value, str) and value.startswith('sha256:') and len(value) == 71 and all(ch in '0123456789abcdef' for ch in value[7:])


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
    checks: dict[str, bool] = {}
    blockers: list[dict[str, str]] = []

    def check(name: str, condition: bool, blocker: str | None = None) -> None:
        checks[name] = bool(condition)
        if not condition:
            blockers.append({'check': name, 'blocker': blocker or name})

    # Exact evidence-chain schemas and cryptographic linkage.
    check('r7e-schema', r7e.get('schema') == 'R7E_PORTABLE_JSON_SCHEMA_AUTHORITATIVE_TUPLE_V3')
    check('r7e-pass', r7e.get('passed') is True)
    check('r7e-branch', r7e.get('branch') == 'r7e-portable-authoritative-v3-20260901')
    check('r7e-source-hash', r7e.get('sourceArchiveSha256') == '764271738ad8578de7d89c522d9cedd1a22ce00d1b8e5d06b271903b52a3923d')
    check('r7e-source-count', r7e.get('sourceFileCount') == 146)
    check('r7e-artifact-digest', sha256_digest(r7e.get('artifact', {}).get('digest')))
    check('r7e-portable-dialect', r7e.get('portableSchema', {}).get('dialect') == 'https://json-schema.org/draft/2020-12/schema')
    check('r7e-portable-version', r7e.get('portableSchema', {}).get('contractVersion') == '1.0.0')

    check('r7f-schema', r7f.get('schema') == 'R7F_PORTABLE_JSON_SCHEMA_AUTHORITATIVE_TUPLE_V4')
    check('r7f-pass', r7f.get('passed') is True)
    check('r7f-branch', r7f.get('branch') == 'r7f-portable-authoritative-v2-20260901')
    check('r7f-artifact-digest', sha256_digest(r7f.get('artifact', {}).get('digest')))
    check('r7f-builder-commit-link', r7f.get('builder', {}).get('commit') == r7e.get('commit'))
    check('r7f-builder-digest-link', r7f.get('builder', {}).get('artifactDigest') == r7e.get('artifact', {}).get('digest'))

    check('external-schema', external.get('schema') == 'R7_PORTABLE_EXTERNAL_AUDIT_TUPLE_V3')
    check('external-pass', external.get('passed') is True)
    check('external-branch', external.get('branch') == 'r7-portable-external-audit-v2-20260901')
    check('external-artifact-digest', sha256_digest(external.get('artifact', {}).get('digest')))
    check('external-r7f-commit-link', external.get('r7f', {}).get('commit') == r7f.get('commit'))
    check('external-r7f-digest-link', external.get('r7f', {}).get('artifactDigest') == r7f.get('artifact', {}).get('digest'))
    check('external-r7e-commit-link', external.get('r7e', {}).get('commit') == r7e.get('commit'))
    check('external-r7e-digest-link', external.get('r7e', {}).get('artifactDigest') == r7e.get('artifact', {}).get('digest'))

    # Live GitHub metadata must prove each recorded tuple rather than merely repeat it.
    check('live-schema', live.get('schema') == 'R7_LIVE_GITHUB_BINDING_V3')
    check('live-pass', live.get('passed') is True)
    check('live-main-unchanged', live.get('main', {}).get('currentSha') == live.get('main', {}).get('baselineSha'))
    check('live-main-baseline', live.get('main', {}).get('baselineSha') == 'bcc55fa7125013615f076dd7cf28a8ec9c5f232b')
    check('live-production-authorization-false', live.get('productionDeploymentAuthorized') is False)
    check('live-whole-site-complete-false', live.get('wholeSiteComplete') is False)

    for label, status in (('r7e', r7e), ('r7f', r7f), ('external', external)):
        binding = live.get(label, {})
        run = binding.get('run', {})
        artifact = binding.get('artifact', {})
        check(f'live-{label}-commit', run.get('head_sha') == status.get('commit'))
        check(f'live-{label}-branch', run.get('head_branch') == status.get('branch'))
        check(f'live-{label}-run-id', run.get('id') == status.get('runId'))
        check(f'live-{label}-run-success', run.get('status') == 'completed' and run.get('conclusion') == 'success')
        check(f'live-{label}-artifact-id', artifact.get('id') == status.get('artifact', {}).get('id'))
        check(f'live-{label}-artifact-name', artifact.get('name') == status.get('artifact', {}).get('name'))
        check(f'live-{label}-artifact-digest', artifact.get('digest') == status.get('artifact', {}).get('digest'))
        check(f'live-{label}-artifact-active', artifact.get('expired') is False)
        check(f'live-{label}-artifact-run-link', artifact.get('workflow_run', {}).get('id') == status.get('runId'))

    # Authority and programme roadmap are explicit and immutable for this decision.
    check('authority-schema', authority.get('schema') == 'R7_AUTHORITY_HIERARCHY_V3')
    check('authority-order', authority.get('orderedAuthorities') == EXPECTED_AUTHORITY_ORDER)
    check('authority-bearing-frozen', authority.get('designIdentity') == 'BEARING' and authority.get('designFrozen') is True)
    check('authority-truth-first', authority.get('orderedAuthorities', [None])[0] == 'CURRENT_FACTUAL_TRUTH_AND_PRIVACY')
    check('authority-r7-scope', authority.get('r7Scope') == 'TECHNICAL_ARCHITECTURE_AND_EMPIRICAL_VERIFICATION_ONLY')

    check('roadmap-schema', roadmap.get('schema') == 'DAVID_ANDERLE_WEBSITE_PROGRAMME_ROADMAP_V3')
    roadmap_rows = roadmap.get('phases', [])
    check('roadmap-phase-count', isinstance(roadmap_rows, list) and len(roadmap_rows) == 13)
    check('roadmap-phase-order', [row.get('id') for row in roadmap_rows if isinstance(row, dict)] == PHASES)
    check('roadmap-r7-current', next((row.get('status') for row in roadmap_rows if row.get('id') == 'R7'), None) == 'CLOSURE_CANDIDATE')
    check('roadmap-r8-r13-not-closed', all(next((row.get('status') for row in roadmap_rows if row.get('id') == phase), None) in {'NOT_STARTED', 'PENDING'} for phase in PHASES[7:]))

    # The ownership history must not be rewritten into a test that never occurred.
    check('ownership-schema', ownership.get('schema') == 'BEARING_OWNERSHIP_DECISION_V3')
    check('ownership-substantive-approval', ownership.get('substantiveApproval') == 'USER_DELEGATED_SUBSTANTIVE_APPROVAL')
    check('ownership-formal-blind-not-recorded', ownership.get('formalQuantitativeBlindProtocolRecorded') is False)
    check('ownership-release-gates', ownership.get('requiredFutureGates') == ['R10', 'R12'])
    check('ownership-not-falsely-certified', ownership.get('formalProtocolClaim') == 'NOT_PERFORMED_OR_NOT_RECORDED')
    check('ownership-r7-nonblocking-rationale', nonempty_string(ownership.get('r7Disposition')) and ownership.get('r7Blocking') is False)

    # Full-history traceability and raw-clause accounting.
    check('traceability-schema', traceability.get('schema') == 'R7_FULL_HISTORY_TRACEABILITY_V4')
    requirements = traceability.get('requirements', [])
    check('traceability-nonempty', isinstance(requirements, list) and len(requirements) >= 40)
    ids = [row.get('id') for row in requirements if isinstance(row, dict)]
    check('traceability-unique-ids', len(ids) == len(set(ids)) and all(nonempty_string(value) for value in ids))
    check('traceability-known-phases', all(row.get('phase') in PHASES for row in requirements if isinstance(row, dict)))
    check('traceability-known-statuses', all(row.get('status') in ALLOWED_STATUSES for row in requirements if isinstance(row, dict)))
    check('traceability-all-material', all(row.get('material') is True for row in requirements if isinstance(row, dict)))
    check('traceability-source-locators', all(isinstance(row.get('sourceLocators'), list) and row.get('sourceLocators') and all(nonempty_string(item) for item in row.get('sourceLocators')) for row in requirements if isinstance(row, dict)))
    check('traceability-requirement-text', all(nonempty_string(row.get('requirement')) for row in requirements if isinstance(row, dict)))
    check('traceability-no-open-r7-blocker', not any(row.get('status') == 'OPEN_R7_BLOCKER' for row in requirements if isinstance(row, dict)))
    check('traceability-orphan-list-empty', traceability.get('orphanedRequirementIds') == [])
    check('traceability-contradictions-empty', traceability.get('contradictions') == [])
    check('traceability-deviations-explained', traceability.get('unexplainedDeviations') == [])

    review = traceability.get('rawNormativeReview', {})
    total_clauses = review.get('totalClauses')
    classified_clauses = sum(review.get(key, 0) for key in ('mappedMaterialClauses', 'supersededClauses', 'executionBoilerplateClauses', 'researchMethodClauses', 'duplicateClauses'))
    check('raw-review-positive-total', isinstance(total_clauses, int) and total_clauses > 0)
    check('raw-review-accounting', isinstance(total_clauses, int) and classified_clauses == total_clauses)
    check('raw-review-material-complete', review.get('mappedMaterialClauses') == review.get('materialClauses'))
    check('raw-review-zero-unresolved', review.get('unresolvedMaterialClauses') == [])
    check('raw-review-corpus-bound', nonempty_string(review.get('corpusManifestSha256')) and len(review.get('corpusManifestSha256', '')) == 64)

    satisfied_rows = [row for row in requirements if row.get('status') in RESOLVED_STATUSES]
    check('satisfied-requirements-have-evidence', all(isinstance(row.get('evidence'), list) and row.get('evidence') and all(nonempty_string(item) for item in row.get('evidence')) for row in satisfied_rows))
    waived_rows = [row for row in requirements if row.get('status') == 'USER_WAIVER_BOUND']
    check('waivers-explicitly-bound', all(nonempty_string(row.get('waiverId')) for row in waived_rows))
    deviation_rows = [row for row in requirements if row.get('status') == 'DEVIATION_ACCEPTED']
    check('deviations-explicitly-bound', all(nonempty_string(row.get('deviationId')) for row in deviation_rows))

    # Carry-forward entries must form a bijection with every deferred requirement.
    check('carry-schema', carry.get('schema') == 'R7_CARRY_FORWARD_REGISTER_V4')
    entries = carry.get('entries', [])
    check('carry-list', isinstance(entries, list))
    carry_ids = [row.get('id') for row in entries if isinstance(row, dict)]
    check('carry-unique-ids', len(carry_ids) == len(set(carry_ids)) and all(nonempty_string(value) for value in carry_ids))
    entry_by_id = {row.get('id'): row for row in entries if isinstance(row, dict)}
    deferred_rows = [row for row in requirements if row.get('status') in DEFERRED_STATUSES]
    deferred_carry_ids = [row.get('carryForwardId') for row in deferred_rows]
    check('deferred-requirements-have-carry-id', all(nonempty_string(value) for value in deferred_carry_ids))
    check('deferred-carry-ids-unique', len(deferred_carry_ids) == len(set(deferred_carry_ids)))
    check('deferred-carry-bijection', set(deferred_carry_ids) == set(entry_by_id))
    check('carry-unbound-empty', carry.get('unboundEntries') == [])
    check('carry-status-bound', all(row.get('status') == 'BOUND' for row in entries if isinstance(row, dict)))
    check('carry-fields-complete', all(nonempty_string(row.get('requirementId')) and nonempty_string(row.get('gate')) and nonempty_string(row.get('rationale')) and row.get('targetPhase') in PHASES[7:] for row in entries if isinstance(row, dict)))
    requirement_by_id = {row.get('id'): row for row in requirements if isinstance(row, dict)}
    check('carry-requirement-links', all(row.get('requirementId') in requirement_by_id for row in entries if isinstance(row, dict)))
    check('carry-phase-links', all(requirement_by_id[row.get('requirementId')].get('status') == f"DEFERRED_BOUND_{row.get('targetPhase')}" for row in entries if isinstance(row, dict) and row.get('requirementId') in requirement_by_id))
    check('carry-forward-count-recorded', traceability.get('summary', {}).get('deferredRequirementCount') == len(deferred_rows) == len(entries))

    status_counts = Counter(row.get('status') for row in requirements if isinstance(row, dict))
    phase_counts = Counter(row.get('phase') for row in requirements if isinstance(row, dict))
    check('traceability-summary-count', traceability.get('summary', {}).get('requirementCount') == len(requirements))
    check('traceability-summary-open-zero', traceability.get('summary', {}).get('openR7BlockerCount') == 0)
    check('traceability-summary-orphan-zero', traceability.get('summary', {}).get('orphanedRequirementCount') == 0)

    # Scope guardrails: this verdict is deliberately narrower than completion or release.
    forbidden_scope_claims = {
        'WHOLE_SITE_COMPLETE',
        'PRODUCTION_READY',
        'DEPLOYMENT_APPROVED',
        'R8_COMPLETE',
        'R9_COMPLETE',
        'R10_COMPLETE',
        'R11_COMPLETE',
        'R12_COMPLETE',
        'R13_COMPLETE',
    }
    requested_claims = set(traceability.get('requestedClosureClaims', []))
    check('no-forbidden-closure-claims', requested_claims.isdisjoint(forbidden_scope_claims))
    check('exact-closure-claim', requested_claims == {'R7_TECHNICAL_ARCHITECTURE_CLOSED'})

    passed = not blockers
    return {
        'schema': 'R7_HISTORY_BOUND_FINAL_CONTROLLER_V3',
        'passed': passed,
        'decision': 'R7_CLOSED' if passed else 'R7_NOT_CLOSED',
        'maximumAuthorizedVerdict': 'R7_TECHNICAL_ARCHITECTURE_CLOSED' if passed else 'NO_CLOSURE_AUTHORIZED',
        'checks': checks,
        'checkCount': len(checks),
        'passedCheckCount': sum(checks.values()),
        'failedChecks': [name for name, value in checks.items() if not value],
        'blockers': blockers,
        'metrics': {
            'requirementCount': len(requirements),
            'deferredRequirementCount': len(deferred_rows),
            'carryForwardCount': len(entries),
            'rawNormativeClauseCount': total_clauses,
            'statusCounts': dict(sorted(status_counts.items())),
            'phaseCounts': dict(sorted(phase_counts.items())),
        },
        'evidenceChain': {
            'r7e': {'commit': r7e.get('commit'), 'runId': r7e.get('runId'), 'artifact': r7e.get('artifact')},
            'r7f': {'commit': r7f.get('commit'), 'runId': r7f.get('runId'), 'artifact': r7f.get('artifact')},
            'external': {'commit': external.get('commit'), 'runId': external.get('runId'), 'artifact': external.get('artifact')},
        },
        'scope': {
            'closed': 'R7 technical architecture and empirical verification',
            'notClosed': ['whole website programme', 'R8 security', 'R9 discoverability', 'R10 final authority', 'R11 clean-room build', 'R12 release red team', 'R13 live audit'],
            'mainMutationAuthorized': False,
            'productionDeploymentAuthorized': False,
        },
        'ownershipCaveatPreserved': True if checks.get('ownership-formal-blind-not-recorded') else False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ('r7e', 'r7f', 'external', 'traceability', 'carry', 'authority', 'roadmap', 'ownership', 'live', 'output'):
        parser.add_argument(f'--{name}', required=True)
    args = parser.parse_args()
    paths = {name: Path(getattr(args, name)).resolve() for name in ('r7e', 'r7f', 'external', 'traceability', 'carry', 'authority', 'roadmap', 'ownership', 'live')}
    result = evaluate(*(load(paths[name]) for name in ('r7e', 'r7f', 'external', 'traceability', 'carry', 'authority', 'roadmap', 'ownership', 'live')))
    result['inputSha256'] = {name: sha256_file(path) for name, path in paths.items()}
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
