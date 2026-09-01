#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

NEGATIVE_TERMS = (
    "orphan",
    "openr7blocker",
    "open_r7_blocker",
    "unresolvedmaterial",
    "unresolved_material",
    "unmappedmaterial",
    "unmapped_material",
    "missingrequirement",
    "missing_requirement",
    "forgottenrequirement",
    "forgotten_requirement",
    "contradictioncount",
    "contradiction_count",
)
ALLOWED_DEFERRED_PHASES = {f"R{number}" for number in range(8, 14)}


def canonical_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def walk(value: Any, path: str = "$") -> Iterable[tuple[str, Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, f"{path}[{index}]")


def row_value(row: dict[str, Any], names: set[str]) -> Any:
    for key, value in row.items():
        if canonical_key(key) in names:
            return value
    return None


def collect_candidate_lists(documents: list[tuple[Path, Any]]) -> list[tuple[Path, str, list[dict[str, Any]]]]:
    candidates: list[tuple[Path, str, list[dict[str, Any]]]] = []
    for source, document in documents:
        for location, value in walk(document):
            if not isinstance(value, list) or len(value) < 5 or not all(isinstance(row, dict) for row in value):
                continue
            candidates.append((source, location, value))
    return candidates


def requirement_score(rows: list[dict[str, Any]]) -> tuple[int, int]:
    id_names = {"id", "requirementid", "requirementkey", "requirement"}
    status_names = {"status", "resolution", "disposition", "state"}
    phase_names = {"phase", "stage", "targetphase", "ownerphase"}
    complete = sum(
        row_value(row, id_names) is not None
        and row_value(row, status_names) is not None
        and row_value(row, phase_names) is not None
        for row in rows
    )
    return complete, len(rows)


def carry_score(rows: list[dict[str, Any]]) -> tuple[int, int]:
    id_names = {"id", "carryforwardid", "gateid", "taskid", "requirementid"}
    phase_names = {"phase", "targetphase", "ownerphase", "stage", "gate"}
    complete = sum(
        row_value(row, id_names) is not None
        and bool(re.search(r"R(?:8|9|10|11|12|13)", str(row_value(row, phase_names) or ""), re.I))
        for row in rows
    )
    return complete, len(rows)


def extract_phase(value: Any) -> str | None:
    match = re.search(r"\bR(1[0-3]|[1-9])\b", str(value or ""), re.I)
    return f"R{match.group(1)}" if match else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.resolve()

    checks: dict[str, bool] = {}
    findings: list[dict[str, Any]] = []
    json_documents: list[tuple[Path, Any]] = []
    text_parts: list[str] = []
    files: list[dict[str, Any]] = []

    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        files.append({"path": relative, "sha256": sha256(path), "size": path.stat().st_size})
        if path.suffix.lower() in {".json", ".md", ".txt", ".csv", ".yml", ".yaml"} and path.stat().st_size < 10_000_000:
            text = path.read_text(encoding="utf-8", errors="replace")
            text_parts.append(f"\n--- {relative} ---\n{text}")
            if path.suffix.lower() == ".json":
                try:
                    json_documents.append((path, json.loads(text)))
                except json.JSONDecodeError as error:
                    findings.append({"code": "INVALID_JSON", "path": relative, "error": str(error)})

    checks["nonempty-traceability-tree"] = len(files) >= 5
    checks["json-documents-present"] = len(json_documents) >= 2
    corpus = "\n".join(text_parts)
    corpus_lower = corpus.lower()

    status_path = root / ".github/r7-status/full-history-traceability-v4.json"
    checks["persistent-status-present"] = status_path.is_file()
    status: dict[str, Any] = {}
    if status_path.is_file():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception as error:
            findings.append({"code": "STATUS_PARSE_ERROR", "error": str(error)})
    status_decision = str(status.get("decision", ""))
    checks["persistent-status-pass"] = status.get("passed") is True
    checks["persistent-status-positive-decision"] = "PASS" in status_decision.upper() or "READY" in status_decision.upper()

    negative_counter_failures: list[dict[str, Any]] = []
    positive_zero_flags = 0
    for source, document in json_documents:
        for location, value in walk(document):
            leaf = canonical_key(location.rsplit(".", 1)[-1])
            matched = any(canonical_key(term) in leaf for term in NEGATIVE_TERMS)
            if not matched:
                continue
            if isinstance(value, bool):
                if "zero" in leaf and value is True:
                    positive_zero_flags += 1
                elif any(prefix in leaf for prefix in ("has", "present", "exists")) and value is True:
                    negative_counter_failures.append({"source": source.relative_to(root).as_posix(), "location": location, "value": value})
            elif isinstance(value, (int, float)) and value != 0:
                negative_counter_failures.append({"source": source.relative_to(root).as_posix(), "location": location, "value": value})
            elif isinstance(value, list) and value:
                negative_counter_failures.append({"source": source.relative_to(root).as_posix(), "location": location, "length": len(value)})
    checks["no-negative-material-counters"] = not negative_counter_failures

    candidates = collect_candidate_lists(json_documents)
    requirement_candidates = sorted(candidates, key=lambda item: requirement_score(item[2]), reverse=True)
    requirement_source: Path | None = None
    requirement_location: str | None = None
    requirements: list[dict[str, Any]] = []
    if requirement_candidates:
        source, location, rows = requirement_candidates[0]
        complete, total = requirement_score(rows)
        if total >= 20 and complete / total >= 0.65:
            requirement_source, requirement_location, requirements = source, location, rows

    checks["requirements-matrix-detected"] = bool(requirements)
    checks["material-requirement-count"] = len(requirements) >= 80
    id_names = {"id", "requirementid", "requirementkey", "requirement"}
    status_names = {"status", "resolution", "disposition", "state"}
    phase_names = {"phase", "stage", "targetphase", "ownerphase"}
    carry_names = {"carryforwardid", "carryforward", "gateid", "deferredto", "targetgate"}
    requirement_ids = [str(row_value(row, id_names)) for row in requirements if row_value(row, id_names) is not None]
    checks["requirement-ids-complete"] = len(requirement_ids) == len(requirements)
    checks["requirement-ids-unique"] = len(requirement_ids) == len(set(requirement_ids))

    open_requirements: list[dict[str, Any]] = []
    deferred_requirements: list[dict[str, Any]] = []
    requirement_phases: set[str] = set()
    for row in requirements:
        status_value = str(row_value(row, status_names) or "")
        phase = extract_phase(row_value(row, phase_names))
        if phase:
            requirement_phases.add(phase)
        upper = status_value.upper()
        if any(term in upper for term in ("OPEN_R7_BLOCKER", "UNRESOLVED", "ORPHAN", "MISSING", "UNMAPPED_MATERIAL")):
            open_requirements.append(row)
        if upper.startswith("DEFERRED"):
            deferred_requirements.append(row)
            target = extract_phase(status_value) or phase
            if target not in ALLOWED_DEFERRED_PHASES:
                open_requirements.append({"reason": "invalid-deferred-phase", "row": row})
    checks["no-open-material-requirements"] = not open_requirements
    checks["roadmap-phases-represented"] = all(f"R{number}" in requirement_phases or f"R{number}".lower() in corpus_lower for number in range(1, 14))

    carry_candidates = sorted(candidates, key=lambda item: carry_score(item[2]), reverse=True)
    carry_source: Path | None = None
    carry_location: str | None = None
    carry_rows: list[dict[str, Any]] = []
    if carry_candidates:
        source, location, rows = carry_candidates[0]
        complete, total = carry_score(rows)
        if total >= 3 and complete / total >= 0.5:
            carry_source, carry_location, carry_rows = source, location, rows
    carry_ids = [str(row_value(row, {"id", "carryforwardid", "gateid", "taskid", "requirementid"})) for row in carry_rows if row_value(row, {"id", "carryforwardid", "gateid", "taskid", "requirementid"}) is not None]
    checks["carry-forward-register-detected"] = bool(carry_rows)
    checks["carry-forward-ids-unique"] = len(carry_ids) == len(set(carry_ids))
    checks["carry-forward-phases-bounded"] = all(extract_phase(row_value(row, phase_names | {"gate"})) in ALLOWED_DEFERRED_PHASES for row in carry_rows)
    checks["deferred-requirements-have-register"] = not deferred_requirements or bool(carry_rows)

    direct_carry_links = 0
    missing_direct_links: list[str] = []
    carry_id_set = set(carry_ids)
    for row in deferred_requirements:
        requirement_id = str(row_value(row, id_names) or "unknown")
        reference = row_value(row, carry_names)
        if reference is None:
            continue
        direct_carry_links += 1
        references = reference if isinstance(reference, list) else [reference]
        if not all(str(item) in carry_id_set or extract_phase(item) in ALLOWED_DEFERRED_PHASES for item in references):
            missing_direct_links.append(requirement_id)
    checks["explicit-carry-links-valid"] = not missing_direct_links

    authority_tokens = {
        "truth": "truth" in corpus_lower,
        "privacy": "privacy" in corpus_lower,
        "photography-r5": bool(re.search(r"\bR5\b", corpus, re.I)),
        "bearing-r6c-r6d": bool(re.search(r"R6C", corpus, re.I)) and bool(re.search(r"R6D", corpus, re.I)) and "bearing" in corpus_lower,
        "content-r4": bool(re.search(r"\bR4\b", corpus, re.I)),
        "technical-r7": bool(re.search(r"\bR7\b", corpus, re.I)),
    }
    checks["authority-hierarchy-material-present"] = all(authority_tokens.values())
    formal_blind_not_recorded = bool(re.search(r"formal.{0,80}blind.{0,120}(not recorded|not performed|not completed|did not occur)", corpus, re.I | re.S)) or (
        "formal" in corpus_lower and "blind" in corpus_lower and "not recorded" in corpus_lower
    )
    delegated_approval = bool(re.search(r"(user[- ]delegated|delegated.{0,80}approval|substantive.{0,40}approval)", corpus, re.I | re.S))
    checks["ownership-formal-blind-caveat"] = formal_blind_not_recorded
    checks["ownership-delegated-approval-recorded"] = delegated_approval
    checks["r8-r13-deferred-material-present"] = all(bool(re.search(rf"\bR{number}\b", corpus, re.I)) for number in range(8, 14))
    checks["no-vague-later-only-deferral"] = not any(
        str(row_value(row, status_names) or "").strip().lower() in {"later", "tbd", "todo", "deferred"}
        for row in requirements
    )

    matrix_projection = [
        {
            "id": str(row_value(row, id_names)),
            "phase": extract_phase(row_value(row, phase_names)),
            "status": str(row_value(row, status_names) or ""),
            "carryForward": row_value(row, carry_names),
        }
        for row in requirements
    ]
    matrix_sha = hashlib.sha256(json.dumps(matrix_projection, sort_keys=True, separators=(",", ":")).encode()).hexdigest() if requirements else None
    tree_sha = hashlib.sha256((json.dumps(files, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()
    failed_checks = [name for name, passed in checks.items() if not passed]
    result = {
        "schema": "R7_FULL_HISTORY_TRACEABILITY_INDEPENDENT_AUDIT_V5",
        "decision": "R7_FULL_HISTORY_TRACEABILITY_INDEPENDENT_PASS" if not failed_checks and not findings else "R7_FULL_HISTORY_TRACEABILITY_INDEPENDENT_FAIL",
        "passed": not failed_checks and not findings,
        "root": str(root),
        "checks": checks,
        "failedChecks": failed_checks,
        "findings": findings,
        "negativeCounterFailures": negative_counter_failures,
        "openRequirements": open_requirements,
        "missingDirectCarryLinks": missing_direct_links,
        "metrics": {
            "fileCount": len(files),
            "jsonDocumentCount": len(json_documents),
            "requirementCount": len(requirements),
            "deferredRequirementCount": len(deferred_requirements),
            "carryForwardCount": len(carry_rows),
            "directCarryLinkCount": direct_carry_links,
            "positiveZeroFlagCount": positive_zero_flags,
            "openR7BlockerCount": len(open_requirements),
            "orphanedMaterialRequirementCount": len(negative_counter_failures),
        },
        "sources": {
            "persistentStatus": status_path.relative_to(root).as_posix() if status_path.is_file() else None,
            "requirementsMatrix": requirement_source.relative_to(root).as_posix() if requirement_source else None,
            "requirementsLocation": requirement_location,
            "carryForwardRegister": carry_source.relative_to(root).as_posix() if carry_source else None,
            "carryForwardLocation": carry_location,
        },
        "hashes": {
            "traceabilityTreeSha256": tree_sha,
            "requirementsProjectionSha256": matrix_sha,
            "persistentStatusSha256": sha256(status_path) if status_path.is_file() else None,
        },
        "authorityTokens": authority_tokens,
        "scope": "Audits R1-R13 requirement accounting for R7 closure; deferred work remains bound to R8-R13 and is not declared complete.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "failedChecks": failed_checks, "metrics": result["metrics"], "sources": result["sources"]}, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
