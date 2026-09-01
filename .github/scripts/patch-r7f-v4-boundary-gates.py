#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

GATE = Path('.github/scripts/r7f-evidence-gates.py')
WORKFLOW = Path('.github/workflows/r7f-portable-final-verification.yml')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one anchor, found {count}')
    return text.replace(old, new, 1)


def main() -> None:
    gate = GATE.read_text(encoding='utf-8')
    old_correction = 'identity.get("sourceCorrectionLayer") == "NONE — full-history reconciliation folded into canonical packed source"'
    new_correction = 'identity.get("sourceCorrectionLayer") == "NONE — full-history reconciliation and portable Draft 2020-12 contract folded into canonical packed source"'
    old_artifact = 'args.expected_artifact_name.startswith("r7e-full-history-reconciled-evidence-") and args.expected_artifact_digest.startswith("sha256:") and len(args.expected_artifact_digest) == 71'
    new_artifact = 'args.expected_artifact_name == f"r7e-portable-self-recording-v4-evidence-{args.expected_commit}" and args.expected_artifact_digest.startswith("sha256:") and len(args.expected_artifact_digest) == 71'
    gate = replace_once(gate, old_correction, new_correction, 'source-correction identity')
    gate = replace_once(gate, old_artifact, new_artifact, 'artifact metadata identity')
    GATE.write_text(gate, encoding='utf-8')

    workflow = WORKFLOW.read_text(encoding='utf-8')
    replacement_anchor = '''            ('R7E_FULL_HISTORY_RECONCILED_PACKAGE_VALIDATION_V1',
             'R7E_PORTABLE_JSON_SCHEMA_PACKAGE_VALIDATION_V1',
             'builder package schema'),
'''
    replacement_insert = replacement_anchor + '''            ('identity.get("sourceCorrectionLayer") == "NONE — full-history reconciliation folded into canonical packed source"',
             'identity.get("sourceCorrectionLayer") == "NONE — full-history reconciliation and portable Draft 2020-12 contract folded into canonical packed source"',
             'builder source-correction identity'),
            ('args.expected_artifact_name.startswith("r7e-full-history-reconciled-evidence-") and args.expected_artifact_digest.startswith("sha256:") and len(args.expected_artifact_digest) == 71',
             'args.expected_artifact_name == f"r7e-portable-self-recording-v4-evidence-{args.expected_commit}" and args.expected_artifact_digest.startswith("sha256:") and len(args.expected_artifact_digest) == 71',
             'builder artifact metadata identity'),
'''
    workflow = replace_once(workflow, replacement_anchor, replacement_insert, 'adaptation replacements')

    required_anchor = '''            'builder candidate identity schema',
            'authenticate immutable commit instead of mutable branch head',
'''
    required_insert = '''            'builder candidate identity schema',
            'builder source-correction identity',
            'builder artifact metadata identity',
            'authenticate immutable commit instead of mutable branch head',
'''
    workflow = replace_once(workflow, required_anchor, required_insert, 'required adaptation classes')

    aligned_anchor = '''            'builder candidate identity schema':'R7E_PORTABLE_JSON_SCHEMA_CANDIDATE_IDENTITY_V1',
'''
    aligned_insert = aligned_anchor + '''            'builder source-correction identity':'NONE — full-history reconciliation and portable Draft 2020-12 contract folded into canonical packed source',
            'builder artifact metadata identity':'r7e-portable-self-recording-v4-evidence-',
'''
    workflow = replace_once(workflow, aligned_anchor, aligned_insert, 'already-aligned tokens')

    required_tokens = (
        'builder source-correction identity',
        'builder artifact metadata identity',
        'r7e-portable-self-recording-v4-evidence-',
        'portable Draft 2020-12 contract folded into canonical packed source',
    )
    missing = [token for token in required_tokens if token not in workflow]
    if missing:
        raise SystemExit(f'workflow missing explicit portable-boundary evidence: {missing}')
    WORKFLOW.write_text(workflow, encoding='utf-8')
    print(f'patched {GATE} and {WORKFLOW}')


if __name__ == '__main__':
    main()
