#!/usr/bin/env python3
"""Execute one native command and preserve auditable raw evidence.

This utility intentionally separates the native process exit code from the wrapper
exit code.  --soft keeps the surrounding evidence-production workflow alive while
recording a failure exactly as observed; it never rewrites the native exit code.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

UTC = dt.timezone.utc


def utc_now() -> str:
    return dt.datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def directory_manifest(path: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in sorted(p for p in path.rglob("*") if p.is_file() and ".git" not in p.parts):
        rel = item.relative_to(path).as_posix()
        rows.append({"path": rel, "bytes": item.stat().st_size, "sha256": sha256_file(item)})
    canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return {
        "kind": "directory",
        "path": str(path.resolve()),
        "files": len(rows),
        "bytes": sum(row["bytes"] for row in rows),
        "tree_sha256": hashlib.sha256(canonical).hexdigest(),
        "manifest": rows,
    }


def artifact_record(raw: str, cwd: Path) -> dict[str, Any]:
    path = Path(raw)
    if not path.is_absolute():
        path = cwd / path
    if not path.exists():
        return {"path": str(path.resolve()), "exists": False}
    if path.is_dir():
        record = directory_manifest(path)
        record["exists"] = True
        return record
    return {
        "kind": "file",
        "path": str(path.resolve()),
        "exists": True,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def detect_tool_version(command: list[str], cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    if not command:
        return {"status": "unknown"}
    executable = command[0]
    probes: list[list[str]] = []
    name = Path(executable).name.lower()
    if name in {"node", "npm", "npx", "python", "python3", "wrangler", "astro"}:
        probes.append([executable, "--version"])
    elif name in {"bash", "sh"}:
        probes.append([executable, "--version"])
    probes.append([executable, "-V"])
    for probe in probes:
        try:
            result = subprocess.run(
                probe,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=20,
                check=False,
            )
        except Exception:
            continue
        output = (result.stdout or result.stderr).strip()
        if result.returncode == 0 and output:
            return {"probe": probe, "exit_code": result.returncode, "output": output[:2000]}
    return {"status": "unresolved", "executable": executable}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True, help="Evidence directory")
    parser.add_argument("--id", required=True, help="Stable command identifier")
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--artifact", action="append", default=[])
    parser.add_argument("--env", action="append", default=[])
    parser.add_argument("--expect", choices=("zero", "nonzero", "any"), default="zero")
    parser.add_argument("--soft", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("native command required after --")

    cwd = Path(args.cwd).resolve()
    evidence = Path(args.evidence).resolve()
    raw_dir = evidence / "raw"
    command_dir = evidence / "commands"
    raw_dir.mkdir(parents=True, exist_ok=True)
    command_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = raw_dir / f"{args.id}.stdout.log"
    stderr_path = raw_dir / f"{args.id}.stderr.log"
    metadata_path = command_dir / f"{args.id}.json"

    env = os.environ.copy()
    injected_env: dict[str, str] = {}
    for assignment in args.env:
        if "=" not in assignment:
            parser.error(f"invalid --env value: {assignment}")
        key, value = assignment.split("=", 1)
        env[key] = value
        injected_env[key] = value

    started = utc_now()
    start_monotonic = dt.datetime.now(UTC)
    launch_error: str | None = None
    try:
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            process = subprocess.run(command, cwd=cwd, env=env, stdout=stdout, stderr=stderr, check=False)
        native_exit = int(process.returncode)
    except Exception as exc:  # command launch failures remain raw failures
        native_exit = 127
        launch_error = f"{type(exc).__name__}: {exc}"
        stderr_path.write_text(launch_error + "\n", encoding="utf-8")
        stdout_path.touch()
    ended = utc_now()
    duration = (dt.datetime.now(UTC) - start_monotonic).total_seconds()

    if args.expect == "zero":
        expectation_met = native_exit == 0
    elif args.expect == "nonzero":
        expectation_met = native_exit != 0
    else:
        expectation_met = True

    metadata: dict[str, Any] = {
        "schema": "davidanderle.r7e.command-evidence.v1",
        "id": args.id,
        "command_argv": command,
        "command_shell_escaped": shlex.join(command),
        "working_directory": str(cwd),
        "injected_environment": injected_env,
        "start_timestamp_utc": started,
        "end_timestamp_utc": ended,
        "duration_seconds": round(duration, 6),
        "native_exit_code": native_exit,
        "expected_exit": args.expect,
        "expectation_met": expectation_met,
        "wrapper_soft_mode": bool(args.soft),
        "launch_error": launch_error,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "stdout_sha256": sha256_file(stdout_path),
        "stderr_sha256": sha256_file(stderr_path),
        "tool_version": detect_tool_version(command, cwd, env),
        "host": {
            "python": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "runner_name": env.get("RUNNER_NAME"),
            "runner_os": env.get("RUNNER_OS"),
            "runner_arch": env.get("RUNNER_ARCH"),
            "github_repository": env.get("GITHUB_REPOSITORY"),
            "github_ref": env.get("GITHUB_REF"),
            "github_sha": env.get("GITHUB_SHA"),
            "github_run_id": env.get("GITHUB_RUN_ID"),
            "github_run_attempt": env.get("GITHUB_RUN_ATTEMPT"),
        },
        "artifacts": [artifact_record(raw, cwd) for raw in args.artifact],
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.soft:
        return 0
    return 0 if expectation_met else (native_exit if native_exit != 0 else 1)


if __name__ == "__main__":
    raise SystemExit(main())
