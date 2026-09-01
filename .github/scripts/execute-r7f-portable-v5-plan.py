#!/usr/bin/env python3
from __future__ import annotations

import difflib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import time
from typing import Any

ROOT = Path.cwd().resolve()
ALLOWED_USES = ('actions/checkout@', 'actions/setup-node@', 'actions/upload-artifact@')
SKIPPED_RUN_STEPS = {'Persist exact authoritative R7F tuple'}
EXPRESSIONS = {
    '${{ github.sha }}': os.environ.get('GITHUB_SHA', ''),
    '${{ github.run_id }}': os.environ.get('GITHUB_RUN_ID', ''),
    '${{ github.run_attempt }}': os.environ.get('GITHUB_RUN_ATTEMPT', ''),
    '${{ github.repository }}': os.environ.get('GITHUB_REPOSITORY', ''),
    '${{ github.ref }}': os.environ.get('GITHUB_REF', ''),
    '${{ github.ref_name }}': os.environ.get('GITHUB_REF_NAME', ''),
    '${{ github.workflow }}': os.environ.get('GITHUB_WORKFLOW', ''),
    '${{ github.token }}': os.environ.get('GH_TOKEN', ''),
}
CORRECTIONS = [
    ('../../../r7f-evidence', '$GITHUB_WORKSPACE/r7f-evidence', 'absolute evidence paths'),
    ('cd r7f-input/run1', 'cd "$GITHUB_WORKSPACE/r7f-input/run1"', 'absolute candidate run directory'),
    ("root=Path('r7f-evidence/lighthouse')", "root=Path(__import__('os').environ['GITHUB_WORKSPACE'])/'r7f-evidence/lighthouse'", 'absolute Lighthouse report root'),
    ("Path('r7f-evidence/LIGHTHOUSE_AUDIT.json').write_text", "(Path(__import__('os').environ['GITHUB_WORKSPACE'])/'r7f-evidence/LIGHTHOUSE_AUDIT.json').write_text", 'absolute Lighthouse summary output'),
]


def fail(message: str) -> None:
    raise SystemExit(message)


def substitute(value: str) -> str:
    rendered = value
    for expression, replacement in EXPRESSIONS.items():
        rendered = rendered.replace(expression, replacement)
    if '${{' in rendered:
        fail(f'unsupported GitHub expression remains: {rendered}')
    return rendered


def parse_yaml(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        ['ruby', '-ryaml', '-rjson', '-e', "data=YAML.safe_load(File.read(ARGV[0]), aliases: true); STDOUT.write(JSON.generate(data))", str(path)],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        fail(f'YAML parse failed: {result.stderr}')
    data = json.loads(result.stdout)
    if not isinstance(data, dict):
        fail('workflow root is not an object')
    return data


def safe_cwd(raw: Any) -> Path:
    if not raw:
        return ROOT
    rendered = substitute(str(raw))
    pure = PurePosixPath(rendered)
    if pure.is_absolute() or '..' in pure.parts:
        fail(f'unsafe working directory: {rendered}')
    target = (ROOT / Path(*pure.parts)).resolve()
    if target != ROOT and ROOT not in target.parents:
        fail(f'working directory escapes checkout: {rendered}')
    if not target.is_dir():
        fail(f'working directory missing: {rendered}')
    return target


def merged_env(*layers: Any) -> dict[str, str]:
    env = os.environ.copy()
    for layer in layers:
        if layer is None:
            continue
        if not isinstance(layer, dict):
            fail('env layer is not an object')
        for key, value in layer.items():
            env[str(key)] = substitute(str(value))
    return env


def main() -> None:
    if len(sys.argv) != 5:
        fail('usage: execute-r7f-portable-v5-plan.py INPUT_YAML CORRECTED_YAML DIFF REPORT')
    source_path = Path(sys.argv[1]).resolve()
    corrected_path = Path(sys.argv[2]).resolve()
    diff_path = Path(sys.argv[3]).resolve()
    report_path = Path(sys.argv[4]).resolve()
    original = source_path.read_text(encoding='utf-8')
    corrected = original
    correction_rows = []
    for old, new, label in CORRECTIONS:
        count = corrected.count(old)
        if count < 1:
            fail(f'{label}: expected correction anchor is absent: {old!r}')
        corrected = corrected.replace(old, new)
        correction_rows.append({'label': label, 'from': old, 'to': new, 'count': count})
    for old, _, label in CORRECTIONS:
        if old in corrected:
            fail(f'{label}: correction incomplete')
    corrected_path.parent.mkdir(parents=True, exist_ok=True)
    corrected_path.write_text(corrected, encoding='utf-8')
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_path.write_text(''.join(difflib.unified_diff(
        original.splitlines(keepends=True),
        corrected.splitlines(keepends=True),
        fromfile=source_path.as_posix(),
        tofile=corrected_path.as_posix(),
    )), encoding='utf-8')

    workflow = parse_yaml(corrected_path)
    jobs = workflow.get('jobs')
    if not isinstance(jobs, dict) or set(jobs) != {'verify'}:
        fail(f'expected exactly one verify job, got {list(jobs or {})}')
    job = jobs['verify']
    if not isinstance(job, dict) or job.get('runs-on') != 'ubuntu-24.04':
        fail('unexpected verifier job or runner')
    steps = job.get('steps')
    if not isinstance(steps, list) or not steps:
        fail('verifier steps missing')

    executed: list[dict[str, Any]] = []
    skipped_actions: list[dict[str, str]] = []
    skipped_runs: list[str] = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            fail(f'step {index} is not an object')
        name = str(step.get('name') or f'step-{index}')
        uses = step.get('uses')
        run = step.get('run')
        if bool(uses) == bool(run):
            fail(f'step {name!r} must contain exactly one of uses/run')
        if uses:
            text = str(uses)
            if not text.startswith(ALLOWED_USES):
                fail(f'disallowed action: {text}')
            skipped_actions.append({'name': name, 'uses': text})
            continue
        if name in SKIPPED_RUN_STEPS:
            skipped_runs.append(name)
            continue
        condition = str(step.get('if') or '').strip()
        if condition:
            fail(f'conditional run step is not allowed in executable plan: {name}: {condition}')
        if str(step.get('shell') or 'bash') != 'bash':
            fail(f'unsupported shell in {name}')
        script = substitute(str(run))
        cwd = safe_cwd(step.get('working-directory'))
        env = merged_env(workflow.get('env'), job.get('env'), step.get('env'))
        script_path = ROOT / '.r7f-v5-plan-step.sh'
        script_path.write_text('set -euo pipefail\n' + script + '\n', encoding='utf-8')
        started = time.time()
        print(f'::group::{index:02d} {name}', flush=True)
        result = subprocess.run(['bash', '--noprofile', '--norc', str(script_path)], cwd=cwd, env=env)
        print('::endgroup::', flush=True)
        executed.append({
            'index': index,
            'name': name,
            'workingDirectory': str(cwd.relative_to(ROOT)) if cwd != ROOT else '.',
            'exitCode': result.returncode,
            'elapsedSeconds': round(time.time() - started, 3),
        })
        report = {
            'schema': 'R7F_CORRECTED_PLAN_EXECUTION_V5',
            'passed': all(row['exitCode'] == 0 for row in executed),
            'sourcePlan': str(source_path.relative_to(ROOT)),
            'correctedPlan': str(corrected_path.relative_to(ROOT)),
            'corrections': correction_rows,
            'totalReplacementCount': sum(row['count'] for row in correction_rows),
            'skippedAllowedActions': skipped_actions,
            'skippedRunSteps': skipped_runs,
            'executed': executed,
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        if result.returncode != 0:
            fail(f'R7F v5 plan step failed: {name} (exit {result.returncode})')
    script_path.unlink(missing_ok=True)
    if not executed or skipped_runs != ['Persist exact authoritative R7F tuple']:
        fail(f'unexpected executor coverage: executed={len(executed)} skippedRuns={skipped_runs}')
    report = json.loads(report_path.read_text(encoding='utf-8'))
    report['passed'] = True
    report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
