#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

EXPECTED_FILES: dict[str, dict[str, int]] = {
    'about-1280.json': {'bgGradient': 28},
    'about-390.json': {'bgGradient': 28},
    'archive-1280.json': {'bgGradient': 52},
    'archive-390.json': {'bgGradient': 52},
    'home-1280.json': {'bgGradient': 48, 'elmPartiallyObscuring': 2},
    'home-390.json': {'bgGradient': 48, 'pseudoContent': 6},
    'work-1280.json': {'bgGradient': 36},
    'work-390.json': {'bgGradient': 36},
    'work-volatility-cascade-engine-1280.json': {'bgGradient': 51},
    'work-volatility-cascade-engine-390.json': {'bgGradient': 51},
}
EXPECTED_TOTAL = Counter({'bgGradient': 430, 'elmPartiallyObscuring': 2, 'pseudoContent': 6})
EXPECTED_BACKGROUND = 'rgb(7, 16, 20)'


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def value_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def string_array(value: Any) -> list[str] | None:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    return None


def canonical_node(report: str, result_index: int, result: dict[str, Any], node_index: int, node: dict[str, Any]) -> dict[str, Any]:
    any_rows = node.get('any') if isinstance(node.get('any'), list) else []
    check = any_rows[0] if len(any_rows) == 1 and isinstance(any_rows[0], dict) else {}
    related_rows = check.get('relatedNodes') if isinstance(check.get('relatedNodes'), list) else []
    data = check.get('data') if isinstance(check.get('data'), dict) else {}
    return {
        'schema': 'R7_AXE_NODE_FINGERPRINT_V1',
        'report': report,
        'resultIndex': result_index,
        'resultId': result.get('id') if isinstance(result.get('id'), str) else None,
        'nodeIndex': node_index,
        'target': string_array(node.get('target')),
        'html': node.get('html') if isinstance(node.get('html'), str) else None,
        'checkId': check.get('id') if isinstance(check.get('id'), str) else None,
        'impact': check.get('impact') if isinstance(check.get('impact'), str) else None,
        'messageKey': data.get('messageKey') if isinstance(data.get('messageKey'), str) else None,
        'relatedNodes': [
            {
                'target': string_array(row.get('target')) if isinstance(row, dict) else None,
                'html': row.get('html') if isinstance(row, dict) and isinstance(row.get('html'), str) else None,
            }
            for row in related_rows
        ],
    }


def valid_contrast_proof(proof: dict[str, Any]) -> bool:
    return (
        proof.get('designation') == 'R7E_STATIC_CONTRAST_BOUND_V1'
        and proof.get('passed') is True
        and proof.get('checkCount') == 32
        and float(proof.get('minimumObservedRatio') or 0) >= 4.5
        and proof.get('failed') == []
    )


def valid_backplate_proof(proof: dict[str, Any], width: int) -> bool:
    elements = proof.get('elements') if isinstance(proof.get('elements'), list) else []
    layers = proof.get('layers') if isinstance(proof.get('layers'), dict) else {}
    list_info = proof.get('list') if isinstance(proof.get('list'), dict) else {}
    targets = [canonical_json(row.get('target')) for row in elements if isinstance(row, dict)]
    common = (
        proof.get('designation') == 'R7E_BEARING_ROUTE_BACKPLATE_V2'
        and proof.get('passed') is True
        and proof.get('width') == width
        and proof.get('expectedBackground') == EXPECTED_BACKGROUND
        and proof.get('expectedElementCount') == 12
        and list_info.get('tagName') == 'OL'
        and list_info.get('className') == 'bearing-list'
        and list_info.get('target') == ['ol']
        and list_info.get('openingHtml') == '<ol class="bearing-list">'
        and len(elements) == 12
        and len(set(targets)) == 12
        and all(
            isinstance(row, dict)
            and row.get('kind') in {'stop-index', 'time', 'heading', 'paragraph'}
            and isinstance(row.get('target'), list)
            and len(row['target']) == 1
            and all(isinstance(item, str) for item in row['target'])
            and isinstance(row.get('ownerTarget'), list)
            and len(row['ownerTarget']) == 1
            and all(isinstance(item, str) for item in row['ownerTarget'])
            and isinstance(row.get('ownerHtml'), str)
            and row['ownerHtml'].startswith('<li>')
            and isinstance(row.get('html'), str)
            and bool(row['html'])
            and row.get('backgroundColor') == EXPECTED_BACKGROUND
            and row.get('backgroundImage') == 'none'
            and row.get('position') == 'relative'
            and row.get('zIndex') == '2'
            and row.get('passed') is True
            for row in elements
        )
    )
    if not common:
        return False
    if width == 1280:
        return layers.get('desktopSignatureBelowList') is True and layers.get('mobilePseudoBelowBackplates') is False
    return layers.get('mobilePseudoBelowBackplates') is True and layers.get('desktopSignatureBelowList') is False


def classify(
    canonical: dict[str, Any],
    contrast_valid: bool,
    contrast_sha: str | None,
    proof_by_width: dict[int, dict[str, Any]],
    proof_sha_by_width: dict[int, str | None],
) -> tuple[str, dict[str, Any] | None, bool, list[str]]:
    errors: list[str] = []
    target = canonical.get('target')
    html = canonical.get('html')
    message_key = canonical.get('messageKey')
    related = canonical.get('relatedNodes') if isinstance(canonical.get('relatedNodes'), list) else []

    if not isinstance(target, list) or not target:
        errors.append('TARGET_SHAPE')
    if not isinstance(html, str) or not html:
        errors.append('HTML_SHAPE')
    if canonical.get('resultId') != 'color-contrast':
        errors.append('RESULT_ID')
    if canonical.get('checkId') != 'color-contrast':
        errors.append('CHECK_ID')
    if canonical.get('impact') != 'serious':
        errors.append('IMPACT')
    if message_key not in {'bgGradient', 'elmPartiallyObscuring', 'pseudoContent'}:
        errors.append('MESSAGE_KEY')

    if message_key == 'bgGradient':
        exact_related = len(related) == 1 and (
            related[0] == {'target': ['body'], 'html': '<body>'}
            or related[0] == {
                'target': ['#limitations'],
                'html': '<section class="limitation-block" id="limitations" aria-labelledby="limitations-title">',
            }
        )
        if not contrast_valid:
            errors.append('CONTRAST_PROOF')
        if not exact_related:
            errors.append('GRADIENT_RELATED_IDENTITY')
        return (
            'STATIC_GRADIENT_BOUND',
            {'proof': 'contrast-bounds.json', 'proofSha256': contrast_sha},
            not errors,
            errors,
        )

    report = str(canonical.get('report') or '')
    width = 1280 if report.endswith('-1280.json') else 390 if report.endswith('-390.json') else 0
    proof = proof_by_width.get(width) or {}
    proof_valid = valid_backplate_proof(proof, width) if width in (1280, 390) else False
    if not proof_valid:
        errors.append('BACKPLATE_PROOF')
    elements = proof.get('elements') if isinstance(proof.get('elements'), list) else []
    exact_elements = [
        row for row in elements
        if isinstance(row, dict)
        and row.get('passed') is True
        and row.get('target') == target
        and row.get('html') == html
    ]
    exact_element = exact_elements[0] if len(exact_elements) == 1 else None
    if exact_element is None:
        errors.append('ROUTE_TARGET_NOT_BOUND')
    layers = proof.get('layers') if isinstance(proof.get('layers'), dict) else {}

    if message_key == 'elmPartiallyObscuring':
        if report != 'home-1280.json':
            errors.append('DESKTOP_REPORT')
        if exact_element is None or exact_element.get('kind') != 'paragraph':
            errors.append('DESKTOP_ELEMENT_KIND')
        if related:
            errors.append('DESKTOP_RELATED_NODES')
        if layers.get('desktopSignatureBelowList') is not True:
            errors.append('DESKTOP_LAYERING')
        return (
            'OPAQUE_BACKPLATE_DESKTOP_AXIS',
            {
                'proof': 'axe-compensation/home-route-backplates-1280.json',
                'proofSha256': proof_sha_by_width.get(1280),
                'elementTarget': exact_element.get('target') if exact_element else None,
                'elementKind': exact_element.get('kind') if exact_element else None,
            },
            not errors,
            errors,
        )

    if message_key == 'pseudoContent':
        if report != 'home-390.json':
            errors.append('MOBILE_REPORT')
        if layers.get('mobilePseudoBelowBackplates') is not True:
            errors.append('MOBILE_LAYERING')
        if len(related) != 1:
            errors.append('MOBILE_RELATED_COUNT')
        related_identity = related[0] if len(related) == 1 else None
        kind = exact_element.get('kind') if exact_element else None
        if kind == 'stop-index':
            expected = {
                'target': exact_element.get('ownerTarget'),
                'html': exact_element.get('ownerHtml'),
            }
            if related_identity != expected:
                errors.append('RELATED_OWNER_MISMATCH')
        elif kind == 'time':
            list_info = proof.get('list') if isinstance(proof.get('list'), dict) else {}
            expected = {
                'target': list_info.get('target'),
                'html': list_info.get('openingHtml'),
            }
            if related_identity != expected:
                errors.append('RELATED_LIST_MISMATCH')
        else:
            errors.append('MOBILE_ELEMENT_KIND')
        return (
            'OPAQUE_BACKPLATE_MOBILE_PSEUDO',
            {
                'proof': 'axe-compensation/home-route-backplates-390.json',
                'proofSha256': proof_sha_by_width.get(390),
                'elementTarget': exact_element.get('target') if exact_element else None,
                'elementKind': kind,
                'relatedIdentity': related,
            },
            not errors,
            errors,
        )

    return 'UNCLASSIFIED', None, False, [*errors, 'UNCLASSIFIED']


def main() -> None:
    parser = argparse.ArgumentParser(description='Independent exact-node Axe fingerprint adjudicator for R7F v6')
    parser.add_argument('tmp_root', type=Path)
    parser.add_argument('builder_inventory', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--label', default='candidate')
    args = parser.parse_args()

    tmp = args.tmp_root.resolve()
    builder_path = args.builder_inventory.resolve()
    builder = load(builder_path)
    checks: dict[str, bool] = {}
    findings: list[dict[str, Any]] = []

    def check(name: str, passed: bool) -> None:
        checks[name] = bool(passed)

    builder_entries = builder.get('entries') if isinstance(builder.get('entries'), list) else []
    check('builder-inventory-present', builder_path.is_file())
    check('builder-schema', builder.get('schema') == 'R7E_AXE_FINGERPRINT_ADJUDICATION_V1')
    check('builder-passed', builder.get('passed') is True and builder.get('failedChecks') == [] and builder.get('errors') == [])
    check('builder-entry-count', len(builder_entries) == 438)
    check('builder-fingerprint-algorithm', (builder.get('fingerprintAlgorithm') or {}).get('name') == 'sha256-canonical-json')
    check(
        'builder-node-self-hashes',
        len(builder_entries) == 438
        and all(
            isinstance(entry, dict)
            and entry.get('nodeFingerprint') == value_sha256(entry.get('canonical'))
            for entry in builder_entries
        ),
    )
    check(
        'builder-adjudication-self-hashes',
        len(builder_entries) == 438
        and all(
            isinstance(entry, dict)
            and entry.get('adjudicationFingerprint') == value_sha256({
                'schema': 'R7_AXE_ADJUDICATION_FINGERPRINT_V1',
                'nodeFingerprint': entry.get('nodeFingerprint'),
                'classification': entry.get('classification'),
                'proofBinding': entry.get('proofBinding'),
                'passed': entry.get('passed'),
            })
            for entry in builder_entries
        ),
    )
    builder_node_fingerprints = [entry.get('nodeFingerprint') for entry in builder_entries if isinstance(entry, dict)]
    builder_adjudication_fingerprints = [entry.get('adjudicationFingerprint') for entry in builder_entries if isinstance(entry, dict)]
    builder_projection = [
        {
            'nodeFingerprint': entry.get('nodeFingerprint'),
            'adjudicationFingerprint': entry.get('adjudicationFingerprint'),
            'canonical': entry.get('canonical'),
            'classification': entry.get('classification'),
            'proofBinding': entry.get('proofBinding'),
            'passed': entry.get('passed'),
        }
        for entry in builder_entries if isinstance(entry, dict)
    ]
    check('builder-ordered-node-self-hash', builder.get('orderedNodeFingerprintSha256') == value_sha256(builder_node_fingerprints))
    check('builder-ordered-adjudication-self-hash', builder.get('orderedAdjudicationFingerprintSha256') == value_sha256(builder_adjudication_fingerprints))
    check('builder-node-set-self-hash', builder.get('nodeFingerprintSetSha256') == value_sha256(sorted(set(builder_node_fingerprints))))
    check('builder-binding-set-self-hash', builder.get('bindingFingerprintSetSha256') == value_sha256(sorted(set(builder_adjudication_fingerprints))))
    check('builder-inventory-self-hash', builder.get('inventorySha256') == value_sha256(builder_projection))

    contrast_path = tmp / 'contrast-bounds.json'
    contrast = load(contrast_path) if contrast_path.is_file() else {}
    contrast_valid = contrast_path.is_file() and valid_contrast_proof(contrast)
    contrast_sha = file_sha256(contrast_path) if contrast_path.is_file() else None
    check('contrast-proof-valid', contrast_valid)

    proof_by_width: dict[int, dict[str, Any]] = {}
    proof_sha_by_width: dict[int, str | None] = {}
    for width in (1280, 390):
        proof_path = tmp / 'axe-compensation' / f'home-route-backplates-{width}.json'
        proof = load(proof_path) if proof_path.is_file() else {}
        proof_by_width[width] = proof
        proof_sha_by_width[width] = file_sha256(proof_path) if proof_path.is_file() else None
        check(f'backplate-proof-{width}', proof_path.is_file() and valid_backplate_proof(proof, width))

    check('builder-proof-digest-contrast', (builder.get('proofDigests') or {}).get('contrast') == contrast_sha)
    check('builder-proof-digest-home1280', (builder.get('proofDigests') or {}).get('home1280') == proof_sha_by_width[1280])
    check('builder-proof-digest-home390', (builder.get('proofDigests') or {}).get('home390') == proof_sha_by_width[390])

    axe_root = tmp / 'axe'
    raw_paths = sorted(axe_root.glob('*.json')) if axe_root.is_dir() else []
    check('exact-raw-report-set', [path.name for path in raw_paths] == sorted(EXPECTED_FILES))

    entries: list[dict[str, Any]] = []
    report_summaries: list[dict[str, Any]] = []
    total_keys: Counter[str] = Counter()
    total_violations = 0

    for report_path in raw_paths:
        report_name = report_path.name
        report = load(report_path)
        violations = report.get('violations') if isinstance(report.get('violations'), list) else []
        incomplete = report.get('incomplete') if isinstance(report.get('incomplete'), list) else []
        total_violations += len(violations)
        file_keys: Counter[str] = Counter()
        if violations:
            findings.append({'code': 'AXE_VIOLATIONS', 'report': report_name, 'count': len(violations)})
        if len(incomplete) != 1 or not isinstance(incomplete[0], dict) or incomplete[0].get('id') != 'color-contrast' or not isinstance(incomplete[0].get('nodes'), list) or not incomplete[0]['nodes']:
            findings.append({'code': 'INCOMPLETE_RESULT_SET', 'report': report_name})

        for result_index, result in enumerate(incomplete):
            if not isinstance(result, dict):
                continue
            nodes = result.get('nodes') if isinstance(result.get('nodes'), list) else []
            for node_index, node in enumerate(nodes):
                if not isinstance(node, dict):
                    continue
                canonical = canonical_node(report_name, result_index, result, node_index, node)
                node_fingerprint = value_sha256(canonical)
                classification, proof_binding, passed, errors = classify(
                    canonical,
                    contrast_valid,
                    contrast_sha,
                    proof_by_width,
                    proof_sha_by_width,
                )
                adjudication_canonical = {
                    'schema': 'R7_AXE_ADJUDICATION_FINGERPRINT_V1',
                    'nodeFingerprint': node_fingerprint,
                    'classification': classification,
                    'proofBinding': proof_binding,
                    'passed': passed,
                }
                adjudication_fingerprint = value_sha256(adjudication_canonical)
                entry = {
                    'report': report_name,
                    'resultIndex': result_index,
                    'nodeIndex': node_index,
                    'nodeFingerprint': node_fingerprint,
                    'adjudicationFingerprint': adjudication_fingerprint,
                    'canonical': canonical,
                    'classification': classification,
                    'proofBinding': proof_binding,
                    'passed': passed,
                    'errors': errors,
                }
                entries.append(entry)
                key = str(canonical.get('messageKey'))
                file_keys[key] += 1
                total_keys[key] += 1
                if not passed:
                    findings.append({
                        'code': 'INDEPENDENT_NODE_ADJUDICATION',
                        'report': report_name,
                        'resultIndex': result_index,
                        'nodeIndex': node_index,
                        'nodeFingerprint': node_fingerprint,
                        'errors': errors,
                    })
        if dict(file_keys) != EXPECTED_FILES.get(report_name, {}):
            findings.append({
                'code': 'REPORT_MESSAGE_KEY_INVENTORY',
                'report': report_name,
                'expected': EXPECTED_FILES.get(report_name, {}),
                'actual': dict(file_keys),
            })
        report_summaries.append({
            'report': report_name,
            'rawSha256': file_sha256(report_path),
            'violations': len(violations),
            'incompleteResults': len(incomplete),
            'incompleteNodes': sum(len(row.get('nodes') or []) for row in incomplete if isinstance(row, dict)),
            'messageKeys': dict(file_keys),
        })

    node_fingerprints = [entry['nodeFingerprint'] for entry in entries]
    adjudication_fingerprints = [entry['adjudicationFingerprint'] for entry in entries]
    node_set = sorted(set(node_fingerprints))
    binding_set = sorted(set(adjudication_fingerprints))
    inventory_projection = [
        {
            'nodeFingerprint': entry['nodeFingerprint'],
            'adjudicationFingerprint': entry['adjudicationFingerprint'],
            'canonical': entry['canonical'],
            'classification': entry['classification'],
            'proofBinding': entry['proofBinding'],
            'passed': entry['passed'],
        }
        for entry in entries
    ]
    computed = {
        'orderedNodeFingerprintSha256': value_sha256(node_fingerprints),
        'orderedAdjudicationFingerprintSha256': value_sha256(adjudication_fingerprints),
        'nodeFingerprintSetSha256': value_sha256(node_set),
        'bindingFingerprintSetSha256': value_sha256(binding_set),
        'inventorySha256': value_sha256(inventory_projection),
    }

    check('zero-violations', total_violations == 0)
    check('exact-node-count', len(entries) == 438)
    check('unique-node-fingerprints', len(node_set) == 438)
    check('unique-adjudication-fingerprints', len(binding_set) == 438)
    check('exact-message-key-inventory', total_keys == EXPECTED_TOTAL)
    check('all-nodes-independently-adjudicated', all(entry['passed'] and entry['errors'] == [] for entry in entries))
    check('builder-metrics', builder.get('metrics') == {
        'rawFileCount': 10,
        'totalViolations': 0,
        'totalIncompleteNodes': 438,
        'uniqueNodeFingerprintCount': 438,
        'uniqueBindingFingerprintCount': 438,
        'messageKeys': dict(EXPECTED_TOTAL),
        'minimumStaticContrastRatio': contrast.get('minimumObservedRatio'),
    })
    check('builder-report-summaries-exact', builder.get('reportSummaries') == report_summaries)
    check('builder-entries-exact', builder_entries == entries)
    for key, value in computed.items():
        check(f'builder-{key}', builder.get(key) == value)

    if builder_entries != entries:
        mismatch_index = next((i for i, (left, right) in enumerate(zip(builder_entries, entries)) if left != right), None)
        findings.append({
            'code': 'BUILDER_ENTRY_MISMATCH',
            'builderCount': len(builder_entries),
            'computedCount': len(entries),
            'firstMismatchIndex': mismatch_index,
            'builderAtMismatch': builder_entries[mismatch_index] if mismatch_index is not None else None,
            'computedAtMismatch': entries[mismatch_index] if mismatch_index is not None else None,
        })

    result = {
        'audit': 'R7F_INDEPENDENT_AXE_FINGERPRINT_ADJUDICATION_V2',
        'label': args.label,
        'passed': all(checks.values()),
        'checks': checks,
        'failedChecks': [name for name, passed in checks.items() if not passed],
        'metrics': {
            'reportCount': len(raw_paths),
            'violationCount': total_violations,
            'nodeCount': len(entries),
            'uniqueNodeFingerprintCount': len(node_set),
            'uniqueAdjudicationFingerprintCount': len(binding_set),
            'messageKeys': dict(total_keys),
            'minimumStaticContrastRatio': contrast.get('minimumObservedRatio'),
            **computed,
        },
        'builderInventory': {
            'path': str(builder_path),
            'fileSha256': file_sha256(builder_path),
            'schema': builder.get('schema'),
            'inventorySha256': builder.get('inventorySha256'),
            'nodeFingerprintSetSha256': builder.get('nodeFingerprintSetSha256'),
            'bindingFingerprintSetSha256': builder.get('bindingFingerprintSetSha256'),
        },
        'findings': findings,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
