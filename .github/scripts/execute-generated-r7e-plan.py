#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import time
from typing import Any

ROOT = Path.cwd().resolve()
ALLOWED_USES = (
    "actions/checkout@",
    "actions/setup-node@",
    "actions/upload-artifact@",
)
GITHUB_EXPRESSIONS = {
    "${{ github.sha }}": os.environ.get("GITHUB_SHA", ""),
    "${{ github.run_id }}": os.environ.get("GITHUB_RUN_ID", ""),
    "${{ github.run_attempt }}": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
    "${{ github.repository }}": os.environ.get("GITHUB_REPOSITORY", ""),
    "${{ github.ref }}": os.environ.get("GITHUB_REF", ""),
    "${{ github.ref_name }}": os.environ.get("GITHUB_REF_NAME", ""),
    "${{ github.workflow }}": os.environ.get("GITHUB_WORKFLOW", ""),
    "${{ github.token }}": os.environ.get("GH_TOKEN", ""),
}


def fail(message: str) -> None:
    raise SystemExit(message)


def substitute(value: str) -> str:
    rendered = value
    for expression, replacement in GITHUB_EXPRESSIONS.items():
        rendered = rendered.replace(expression, replacement)
    if "${{" in rendered:
        fail(f"Unsupported GitHub expression remains: {rendered}")
    return rendered


def load_workflow(path: Path) -> dict[str, Any]:
    command = [
        "ruby",
        "-ryaml",
        "-rjson",
        "-e",
        "data=YAML.safe_load(File.read(ARGV[0]), aliases: true); STDOUT.write(JSON.generate(data))",
        str(path),
    ]
    try:
        completed = subprocess.run(command, check=True, text=True, capture_output=True)
    except FileNotFoundError:
        fail("Ruby YAML parser is unavailable on the pinned runner image")
    except subprocess.CalledProcessError as exc:
        fail(f"Workflow YAML parse failed: {exc.stderr}")
    data = json.loads(completed.stdout)
    if not isinstance(data, dict):
        fail("Generated workflow root is not an object")
    return data


def safe_working_directory(raw: str | None) -> Path:
    if not raw:
        return ROOT
    rendered = substitute(str(raw))
    relative = PurePosixPath(rendered)
    if relative.is_absolute() or ".." in relative.parts:
        fail(f"Unsafe working-directory: {rendered}")
    target = (ROOT / Path(*relative.parts)).resolve()
    if target != ROOT and ROOT not in target.parents:
        fail(f"Working-directory escapes checkout: {rendered}")
    if not target.is_dir():
        fail(f"Working-directory does not exist: {rendered}")
    return target


def normalized_env(*layers: Any) -> dict[str, str]:
    env = os.environ.copy()
    for layer in layers:
        if layer is None:
            continue
        if not isinstance(layer, dict):
            fail("Workflow env layer is not an object")
        for key, value in layer.items():
            env[str(key)] = substitute(str(value))
    return env


def main() -> None:
    if len(sys.argv) != 3:
        fail("usage: execute-generated-r7e-plan.py WORKFLOW REPORT")
    workflow_path = Path(sys.argv[1]).resolve()
    report_path = Path(sys.argv[2]).resolve()
    if not workflow_path.is_file():
        fail(f"Generated workflow missing: {workflow_path}")

    workflow = load_workflow(workflow_path)
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict) or set(jobs) != {"verify"}:
        fail(f"Generated workflow must contain exactly one verify job, got {list(jobs or {})}")
    job = jobs["verify"]
    if not isinstance(job, dict):
        fail("verify job is not an object")
    if job.get("runs-on") != "ubuntu-24.04":
        fail(f"Unexpected runner: {job.get('runs-on')}")
    steps = job.get("steps")
    if not isinstance(steps, list) or not steps:
        fail("verify steps are missing")

    workflow_env = workflow.get("env") or {}
    job_env = job.get("env") or {}
    executed: list[dict[str, Any]] = []
    skipped_uses: list[dict[str, str]] = []
    skipped_conditions: list[dict[str, str]] = []
    failed = False
    first_failure: dict[str, Any] | None = None
    script_path = ROOT / ".r7e-plan-step.sh"
    workflow_display = (
        str(workflow_path.relative_to(ROOT))
        if workflow_path == ROOT or ROOT in workflow_path.parents
        else str(workflow_path)
    )

    def persist_report() -> None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "schema": "R7E_GENERATED_PLAN_EXECUTION_V2",
            "passed": not failed,
            "workflow": workflow_display,
            "workflowSha256": subprocess.check_output(["sha256sum", str(workflow_path)], text=True).split()[0],
            "runner": job.get("runs-on"),
            "executedRunStepCount": len(executed),
            "skippedAllowedUsesCount": len(skipped_uses),
            "skippedAllowedUses": skipped_uses,
            "skippedConditionCount": len(skipped_conditions),
            "skippedConditions": skipped_conditions,
            "firstFailure": first_failure,
            "steps": executed,
        }
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            fail(f"Step {index} is not an object")
        name = str(step.get("name") or f"step-{index}")
        uses = step.get("uses")
        run = step.get("run")
        if bool(uses) == bool(run):
            fail(f"Step {name!r} must contain exactly one of uses/run")

        if uses:
            uses_text = str(uses)
            if not uses_text.startswith(ALLOWED_USES):
                fail(f"Disallowed action in generated plan: {uses_text}")
            skipped_uses.append({"name": name, "uses": uses_text})
            continue

        condition = str(step.get("if") or "").strip()
        if condition in ("", "success()", "${{ success() }}"):
            condition_kind = "success"
        elif condition in ("always()", "${{ always() }}"):
            condition_kind = "always"
        elif condition in ("failure()", "${{ failure() }}"):
            condition_kind = "failure"
        else:
            fail(f"Unsupported run-step condition in {name!r}: {condition}")

        should_run = (
            condition_kind == "always"
            or (condition_kind == "success" and not failed)
            or (condition_kind == "failure" and failed)
        )
        if not should_run:
            skipped_conditions.append({"name": name, "condition": condition_kind})
            continue

        shell = str(step.get("shell") or "bash")
        if shell not in ("bash", "bash --noprofile --norc -e -o pipefail {0}"):
            fail(f"Unsupported shell in {name!r}: {shell}")

        script = substitute(str(run))
        cwd = safe_working_directory(step.get("working-directory"))
        env = normalized_env(workflow_env, job_env, step.get("env"))
        script_path.write_text("set -euo pipefail\n" + script + "\n", encoding="utf-8")
        started = time.time()
        print(f"::group::{index:02d} {name}", flush=True)
        completed = subprocess.run(
            ["bash", "--noprofile", "--norc", str(script_path)],
            cwd=cwd,
            env=env,
            text=True,
        )
        print("::endgroup::", flush=True)
        elapsed = round(time.time() - started, 3)
        row = {
            "index": index,
            "name": name,
            "condition": condition_kind,
            "workingDirectory": str(cwd.relative_to(ROOT)) if cwd != ROOT else ".",
            "exitCode": completed.returncode,
            "elapsedSeconds": elapsed,
        }
        executed.append(row)
        if completed.returncode != 0:
            failed = True
            if first_failure is None:
                first_failure = dict(row)
        persist_report()

    script_path.unlink(missing_ok=True)
    if not executed:
        fail("Generated plan executed no run steps")
    persist_report()
    print(report_path.read_text(encoding="utf-8"))
    if failed:
        assert first_failure is not None
        fail(
            f"Generated plan failed at {first_failure['name']} "
            f"(exit {first_failure['exitCode']})"
        )


if __name__ == "__main__":
    main()
