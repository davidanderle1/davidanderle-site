#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

PATH = Path('.github/workflows/r7-full-history-traceability-final.yml')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one anchor, found {count}')
    return text.replace(old, new, 1)


def main() -> None:
    text = PATH.read_text(encoding='utf-8')

    text = replace_once(
        text,
        "          carry.append({'id':'CF-R6-008-R12','sourceRequirementId':'R6-008','targetPhase':'R12','mandatoryGate':'Independent release reviewer must confirm BEARING still feels owned rather than templated','status':'BOUND_NOT_YET_EXECUTED'})\n",
        "          carry.append({'id':'CF-R6-008-R12','sourceRequirementId':'R6-008','targetPhase':'R12','mandatoryGate':'Independent release reviewer must confirm BEARING still feels owned rather than templated','status':'BOUND_NOT_YET_EXECUTED'})\n"
        "          next(r for r in rows if r['id']=='R6-008')['additionalCarryForwardIds']=['CF-R6-008-R12']\n",
        'second ownership carry-forward binding',
    )

    text = replace_once(
        text,
        "          row_by_id={r['id']:r for r in rows}\n          checks={\n",
        "          row_by_id={r['id']:r for r in rows}\n"
        "          expected_carry_ids=set()\n"
        "          for row in rows:\n"
        "              if 'carryForwardId' in row: expected_carry_ids.add(row['carryForwardId'])\n"
        "              expected_carry_ids.update(row.get('additionalCarryForwardIds') or [])\n"
        "          checks={\n",
        'canonical carry-forward set',
    )

    text = replace_once(
        text,
        "  'carryForwardBijection':set(r['carryForwardId'] for r in rows if 'carryForwardId' in r).issubset(set(cids)),\n",
        "  'carryForwardBijection':expected_carry_ids==set(cids),\n",
        'exact carry-forward bijection',
    )

    text = replace_once(
        text,
        "          def verify(m,c):\n              rs=m['requirements']; rb={r['id']:r for r in rs}; cs=c['items'];\n              return (\n",
        "          def verify(m,c):\n"
        "              rs=m['requirements']; rb={r['id']:r for r in rs}; cs=c['items'];\n"
        "              expected=set()\n"
        "              for row in rs:\n"
        "                  if 'carryForwardId' in row: expected.add(row['carryForwardId'])\n"
        "                  expected.update(row.get('additionalCarryForwardIds') or [])\n"
        "              return (\n",
        'self-test carry-forward set',
    )

    text = replace_once(
        text,
        "      and set(r['carryForwardId'] for r in rs if 'carryForwardId' in r).issubset({x['id'] for x in cs})\n",
        "      and expected=={x['id'] for x in cs}\n",
        'self-test exact carry-forward bijection',
    )

    anchor = "      and rb.get('R7-032',{}).get('status')==SAT\n"
    text = replace_once(
        text,
        anchor,
        anchor
        + "      and all(r['status'].startswith('DEFERRED_BOUND_') for r in rs if r['phase'] in {f'R{i}' for i in range(8,14)})\n",
        'future programme deferral invariant',
    )

    required = (
        'additionalCarryForwardIds',
        'expected_carry_ids==set(cids)',
        "expected=={x['id'] for x in cs}",
        "all(r['status'].startswith('DEFERRED_BOUND_')",
    )
    missing = [item for item in required if item not in text]
    if missing:
        raise SystemExit(f'traceability patch missing required invariants: {missing}')

    PATH.write_text(text, encoding='utf-8')
    print(f'patched {PATH} bytes={PATH.stat().st_size}')


if __name__ == '__main__':
    main()
