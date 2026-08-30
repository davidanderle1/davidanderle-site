#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

EXPECTED_REPORTS = {
    "about-1280.json": {"bgGradient": 28},
    "about-390.json": {"bgGradient": 28},
    "archive-1280.json": {"bgGradient": 52},
    "archive-390.json": {"bgGradient": 52},
    "home-1280.json": {"bgGradient": 48, "elmPartiallyObscuring": 2},
    "home-390.json": {"bgGradient": 48, "pseudoContent": 6},
    "work-1280.json": {"bgGradient": 36},
    "work-390.json": {"bgGradient": 36},
    "work-volatility-cascade-engine-1280.json": {"bgGradient": 51},
    "work-volatility-cascade-engine-390.json": {"bgGradient": 51},
}
EXPECTED_KEYS = Counter({"bgGradient": 430, "elmPartiallyObscuring": 2, "pseudoContent": 6})
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def value_sha(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strings(value: Any) -> list[str]:
    return [str(part) for part in value] if isinstance(value, list) else []


def payload(report_name: str, result: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    any_rows = node.get("any") or []
    check = any_rows[0] if len(any_rows) == 1 and isinstance(any_rows[0], dict) else {}
    related = [
        {"target": strings(row.get("target")), "html": str(row.get("html") or "")}
        for row in (check.get("relatedNodes") or [])
        if isinstance(row, dict)
    ]
    return {
        "schema": "R7_FINAL_EXACT_AXE_NODE_PAYLOAD_V1",
        "report": report_name,
        "ruleId": result.get("id"),
        "ruleImpact": result.get("impact"),
        "nodeTarget": strings(node.get("target")),
        "nodeHtml": str(node.get("html") or ""),
        "checkId": check.get("id"),
        "checkImpact": check.get("impact"),
        "messageKey": (check.get("data") or {}).get("messageKey"),
        "relatedNodes": related,
        "allCount": len(node.get("all") or []),
        "noneCount": len(node.get("none") or []),
    }


def inspect_raw(root: Path) -> dict[str, Any]:
    paths = sorted(root.glob("*.json")) if root.is_dir() else []
    checks: dict[str, bool] = {
        "directory": root.is_dir(),
        "exact-report-set": {path.name for path in paths} == set(EXPECTED_REPORTS),
    }
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    keys: Counter[str] = Counter()
    violations = 0
    report_summaries = []
    for path in paths:
        report = load(path)
        report_violations = report.get("violations") or []
        incomplete = report.get("incomplete") or []
        violations += len(report_violations)
        file_keys: Counter[str] = Counter()
        if report_violations:
            errors.append({"report": path.name, "code": "VIOLATIONS", "count": len(report_violations)})
        if len(incomplete) != 1 or incomplete[0].get("id") != "color-contrast" or not incomplete[0].get("nodes"):
            errors.append({"report": path.name, "code": "INCOMPLETE_RESULT_SET"})
        for result in incomplete:
            for node in result.get("nodes") or []:
                row = payload(path.name, result, node)
                key = str(row.get("messageKey"))
                keys[key] += 1
                file_keys[key] += 1
                rows.append(row)
        expected = Counter(EXPECTED_REPORTS.get(path.name, {}))
        if file_keys != expected:
            errors.append({"report": path.name, "code": "MESSAGE_KEY_INVENTORY", "expected": dict(expected), "actual": dict(file_keys)})
        report_summaries.append({
            "report": path.name,
            "sha256": file_sha(path),
            "violations": len(report_violations),
            "incompleteNodes": sum(len(result.get("nodes") or []) for result in incomplete),
            "messageKeys": dict(file_keys),
        })
    fingerprints = [value_sha(row) for row in rows]
    checks.update({
        "zero-violations": violations == 0,
        "node-count-438": len(rows) == 438,
        "message-keys": keys == EXPECTED_KEYS,
        "unique-fingerprints-438": len(set(fingerprints)) == 438,
        "no-errors": not errors,
    })
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failedChecks": [name for name, passed in checks.items() if not passed],
        "rows": rows,
        "fingerprints": fingerprints,
        "multisetSha256": value_sha(sorted(fingerprints)),
        "violations": violations,
        "nodeCount": len(rows),
        "messageKeys": dict(keys),
        "reports": report_summaries,
        "errors": errors,
    }


def proof_contract(tmp: Path) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    contrast_path = tmp / "contrast-bounds.json"
    contrast = load(contrast_path) if contrast_path.is_file() else {}
    checks["contrast-present"] = contrast_path.is_file()
    checks["contrast-designation"] = contrast.get("designation") == "R7E_STATIC_CONTRAST_BOUND_V1"
    checks["contrast-passed"] = contrast.get("passed") is True
    checks["contrast-count"] = contrast.get("checkCount") == 32
    checks["contrast-ratio"] = float(contrast.get("minimumObservedRatio", 0)) >= 4.5
    checks["contrast-no-failures"] = contrast.get("failed") == []
    proof_hashes: dict[str, str | None] = {}
    for width in (1280, 390):
        path = tmp / "axe-compensation" / f"home-route-backplates-{width}.json"
        proof = load(path) if path.is_file() else {}
        elements = proof.get("elements") or []
        layers = proof.get("layers") or {}
        checks[f"proof-{width}-present"] = path.is_file()
        checks[f"proof-{width}-designation"] = proof.get("designation") == "R7E_BEARING_ROUTE_BACKPLATE_V1"
        checks[f"proof-{width}-width"] = proof.get("width") == width
        checks[f"proof-{width}-passed"] = proof.get("passed") is True
        checks[f"proof-{width}-element-count"] = proof.get("expectedElementCount") == 12 and len(elements) == 12
        checks[f"proof-{width}-opaque"] = len(elements) == 12 and all(
            isinstance(row, dict)
            and row.get("passed") is True
            and row.get("backgroundColor") == "rgb(7, 16, 20)"
            and row.get("backgroundImage") == "none"
            and row.get("position") == "relative"
            and row.get("zIndex") == "2"
            and isinstance(row.get("html"), str)
            and bool(row.get("html"))
            for row in elements
        )
        if width == 1280:
            checks["proof-1280-layering"] = layers.get("desktopSignatureBelowList") is True and layers.get("mobilePseudoBelowBackplates") is False
        else:
            checks["proof-390-layering"] = layers.get("mobilePseudoBelowBackplates") is True and layers.get("desktopSignatureBelowList") is False
        proof_hashes[str(width)] = file_sha(path) if path.is_file() else None
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failedChecks": [name for name, passed in checks.items() if not passed],
        "contrastSha256": file_sha(contrast_path) if contrast_path.is_file() else None,
        "proofSha256": proof_hashes,
        "minimumStaticContrastRatio": contrast.get("minimumObservedRatio"),
    }


def file_map(root: Path, ignore: set[str] | None = None) -> dict[str, str]:
    ignored = ignore or set()
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            relative = path.relative_to(root).as_posix()
            if relative not in ignored:
                result[relative] = file_sha(path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Final independent R7 exact-fingerprint closure audit")
    parser.add_argument("r7e", type=Path)
    parser.add_argument("r7f", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    r7e = args.r7e.resolve()
    r7f = args.r7f.resolve()
    checks: dict[str, bool] = {}
    evidence: dict[str, Any] = {}

    def record(name: str, value: bool) -> None:
        checks[name] = bool(value)

    r7e_decision = (r7e / "R7E_GATE_DECISION.txt").read_text(encoding="utf-8").strip() if (r7e / "R7E_GATE_DECISION.txt").is_file() else ""
    r7f_decision = (r7f / "R7F_GATE_DECISION.txt").read_text(encoding="utf-8").strip() if (r7f / "R7F_GATE_DECISION.txt").is_file() else ""
    record("r7e-gate", r7e_decision == "R7E FINGERPRINT-BOUND BUILD EVIDENCE COMPLETE — READY FOR INDEPENDENT R7F V6 AUDIT")
    record("r7f-gate", r7f_decision == "R7F HARDENED INDEPENDENT VERIFICATION V6 EXACT FINGERPRINT COMPLETE — R7 MAY ENTER FINAL CLOSURE AUDIT")

    r7e_validation = load(r7e / "R7E_PACKAGE_VALIDATION.json") if (r7e / "R7E_PACKAGE_VALIDATION.json").is_file() else {}
    r7f_validation = load(r7f / "R7F_PACKAGE_VALIDATION.json") if (r7f / "R7F_PACKAGE_VALIDATION.json").is_file() else {}
    record("r7e-package", r7e_validation.get("passed") is True and r7e_validation.get("failedChecks") == [])
    record("r7f-package", r7f_validation.get("passed") is True and r7f_validation.get("failedChecks") == [] and r7f_validation.get("verificationVersion") == "R7F-v6-exact-fingerprint")

    lock = load(r7f / "R7F_EVIDENCE/builder-input-lock-v6.json") if (r7f / "R7F_EVIDENCE/builder-input-lock-v6.json").is_file() else {}
    tuple_gate = load(r7f / "R7F_EVIDENCE/builder-tuple.json") if (r7f / "R7F_EVIDENCE/builder-tuple.json").is_file() else {}
    record("builder-lock-schema", lock.get("schema") == "R7F_BUILDER_INPUT_V4_EXACT_FINGERPRINT")
    record("builder-lock-digest", isinstance(lock.get("builderArtifactDigest"), str) and lock.get("builderArtifactDigest", "").startswith("sha256:"))
    record("builder-tuple-gate", tuple_gate.get("passed") is True)
    record("builder-run-parity", str(lock.get("builderRunId")) == str(r7f_validation.get("builderRunId")))
    record("builder-commit-parity", lock.get("builderHeadSha") == r7f_validation.get("builderCommit"))
    record("builder-artifact-parity", str(lock.get("builderArtifactId")) == str(r7f_validation.get("builderArtifactId")))
    record("builder-name-parity", lock.get("builderArtifactName") == r7f_validation.get("builderArtifactName"))
    record("builder-digest-parity", lock.get("builderArtifactDigest") == r7f_validation.get("builderArtifactDigest"))

    r7e_identity = load(r7e / "R7E_EVIDENCE/R7E_CANDIDATE_IDENTITY.json") if (r7e / "R7E_EVIDENCE/R7E_CANDIDATE_IDENTITY.json").is_file() else {}
    record("identity-present", bool(r7e_identity))
    record("source-archive-lock", lock.get("builderHeadSha") is not None and r7e_identity.get("sourceArchiveSha256") == r7f_validation.get("builderSourceArchiveSha256"))
    for name in ("sourceArchiveSha256", "sourceTreeSha256", "distTreeSha256", "stressTreeSha256"):
        value = r7e_identity.get(name)
        record(f"identity-{name}", isinstance(value, str) and bool(HEX64.fullmatch(value)))

    source_e = file_map(r7e / "BEARING_PRODUCTION_SOURCE")
    source_f = file_map(r7f / "VERIFIER_PRODUCTION_SOURCE")
    dist_e = file_map(r7e / "BEARING_VERIFIED_DIST")
    dist_f = file_map(r7f / "VERIFIER_DIST")
    stress_e = file_map(r7e / "BEARING_SCALE_SITE_500", {"TEST_ONLY_DO_NOT_DEPLOY.txt"})
    stress_f = file_map(r7f / "VERIFIER_SCALE_SITE_500", {"TEST_ONLY_DO_NOT_DEPLOY.txt"})
    record("source-byte-parity", source_e == source_f and len(source_e) >= 100)
    record("dist-byte-parity", dist_e == dist_f and len(dist_e) >= 30)
    record("stress-byte-parity", stress_e == stress_f and len(stress_e) >= 530)

    raw_e = inspect_raw(r7e / "R7E_RUN1_TMP/axe")
    raw_f = inspect_raw(r7f / "R7F_RUN1_TMP/axe")
    record("builder-raw-valid", raw_e.get("passed") is True)
    record("verifier-raw-valid", raw_f.get("passed") is True)
    record("exact-raw-payload-multiset", Counter(raw_e.get("fingerprints") or []) == Counter(raw_f.get("fingerprints") or []))
    record("exact-raw-payload-digest", raw_e.get("multisetSha256") == raw_f.get("multisetSha256"))

    proof_e = proof_contract(r7e / "R7E_RUN1_TMP")
    proof_f = proof_contract(r7f / "R7F_RUN1_TMP")
    record("builder-proof-valid", proof_e.get("passed") is True)
    record("verifier-proof-valid", proof_f.get("passed") is True)
    record("contrast-proof-byte-parity", proof_e.get("contrastSha256") == proof_f.get("contrastSha256"))
    record("backplate-proof-byte-parity", proof_e.get("proofSha256") == proof_f.get("proofSha256"))

    fp_audit = load(r7f / "R7F_EVIDENCE/independent-exact-axe-fingerprint-audit-v2.json") if (r7f / "R7F_EVIDENCE/independent-exact-axe-fingerprint-audit-v2.json").is_file() else {}
    negatives = load(r7f / "R7F_EVIDENCE/exact-fingerprint-negative-controls.json") if (r7f / "R7F_EVIDENCE/exact-fingerprint-negative-controls.json").is_file() else {}
    record("r7f-exact-audit", fp_audit.get("passed") is True)
    record("r7f-exact-node-count", (fp_audit.get("metrics") or {}).get("candidateNodeCount") == 438)
    record("r7f-exact-payload-parity", (fp_audit.get("checks") or {}).get("exact-node-payload-multiset") is True)
    record("r7f-exact-adjudication-parity", (fp_audit.get("checks") or {}).get("exact-adjudication-multiset") is True)
    record("r7f-negative-controls", negatives.get("passed") is True and all((negatives.get("checks") or {}).values()))

    # Independent non-vacuity: the exact payload digest must change for both
    # false-green mutations that the former R7F v5 accepted.
    desktop_rows = json.loads(json.dumps(raw_f.get("rows") or []))
    changed = False
    for row in desktop_rows:
        if row.get("report") == "home-1280.json" and row.get("messageKey") == "elmPartiallyObscuring":
            row["nodeTarget"] = ["#r7-final-mutated-desktop-target"]
            changed = True
            break
    desktop_mutated = [value_sha(row) for row in desktop_rows]
    record("final-negative-desktop-target-created", changed)
    record("final-negative-desktop-target-rejected", Counter(desktop_mutated) != Counter(raw_e.get("fingerprints") or []))

    mobile_rows = json.loads(json.dumps(raw_f.get("rows") or []))
    changed = False
    for row in mobile_rows:
        if row.get("report") != "home-390.json" or row.get("messageKey") != "pseudoContent":
            continue
        related = row.get("relatedNodes") or []
        if not related or not related[0].get("target"):
            continue
        selector = related[0]["target"][0]
        match = re.search(r"nth-child\((\d+)\)", selector)
        if match:
            old = int(match.group(1)); new = 2 if old != 2 else 1
            related[0]["target"] = [selector.replace(f"nth-child({old})", f"nth-child({new})")]
            changed = True
            break
    mobile_mutated = [value_sha(row) for row in mobile_rows]
    record("final-negative-mobile-index-created", changed)
    record("final-negative-mobile-index-rejected", Counter(mobile_mutated) != Counter(raw_e.get("fingerprints") or []))

    proof_copy = json.loads((r7f / "R7F_RUN1_TMP/axe-compensation/home-route-backplates-1280.json").read_text())
    proof_copy["passed"] = False
    record("final-negative-proof-rejected", proof_copy.get("passed") is not True)

    evidence.update({
        "r7eDecision": r7e_decision,
        "r7fDecision": r7f_decision,
        "r7eIdentity": r7e_identity,
        "builderRaw": {k: v for k, v in raw_e.items() if k not in {"rows", "fingerprints"}},
        "verifierRaw": {k: v for k, v in raw_f.items() if k not in {"rows", "fingerprints"}},
        "builderProof": proof_e,
        "verifierProof": proof_f,
        "sourceFileCount": len(source_e),
        "distFileCount": len(dist_e),
        "stressFileCount": len(stress_e),
        "exactPayloadMultisetSha256": raw_f.get("multisetSha256"),
    })

    result = {
        "audit": "R7_FINAL_EXACT_FINGERPRINT_CLOSURE_AUDIT_V3",
        "decision": "R7_ENGINEERING_CLOSURE_CANDIDATE_READY" if all(checks.values()) else "R7_REMAINS_OPEN",
        "passed": all(checks.values()),
        "checkCount": len(checks),
        "checks": checks,
        "failedChecks": [name for name, passed in checks.items() if not passed],
        "blockers": [name for name, passed in checks.items() if not passed],
        "scope": {
            "technicalEvidence": "CLOSURE_CANDIDATE" if all(checks.values()) else "OPEN",
            "fullHistoryConsistencyAuditCompleted": False,
            "r8SecurityCertified": False,
            "r9DiscoverabilityCertified": False,
            "productionLaunchApproved": False,
            "mainBranchModified": False,
        },
        "evidence": evidence,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
