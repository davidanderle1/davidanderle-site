#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canon_sha(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def bool_checks_pass(value: Any) -> bool:
    return isinstance(value, dict) and bool(value) and all(v is True for v in value.values())


def safe_extract_and_verify(
    archive_path: Path,
    extraction_root: Path,
    manifest_name: str,
) -> tuple[Path, dict[str, Any]]:
    shutil.rmtree(extraction_root, ignore_errors=True)
    extraction_root.mkdir(parents=True, exist_ok=True)
    names: set[str] = set()
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            pure = PurePosixPath(info.filename)
            if pure.is_absolute() or ".." in pure.parts or "\\" in info.filename:
                raise ValueError(f"unsafe ZIP member: {info.filename}")
            if info.filename in names:
                raise ValueError(f"duplicate ZIP member: {info.filename}")
            names.add(info.filename)
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise ValueError(f"symlink ZIP member: {info.filename}")
        archive.extractall(extraction_root)

    manifests = list(extraction_root.rglob(manifest_name))
    if len(manifests) != 1:
        raise ValueError(f"{manifest_name}: expected one manifest, found {len(manifests)}")
    manifest = manifests[0]
    artifact_root = manifest.parent
    expected: dict[str, str] = {}
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        digest, relative = raw.split("  ", 1)
        relative = relative.lstrip("*")
        if relative.startswith("./"):
            relative = relative[2:]
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts or "\\" in relative:
            raise ValueError(f"unsafe manifest path: {relative}")
        if relative in expected:
            raise ValueError(f"duplicate manifest path: {relative}")
        expected[relative] = digest

    actual = {
        path.relative_to(artifact_root).as_posix()
        for path in artifact_root.rglob("*")
        if path.is_file() and path != manifest
    }
    if set(expected) != actual:
        missing = sorted(set(expected) - actual)
        extra = sorted(actual - set(expected))
        raise ValueError(f"manifest coverage mismatch missing={missing[:5]} extra={extra[:5]}")
    mismatches = [
        relative
        for relative, digest in expected.items()
        if sha256(artifact_root / relative) != digest
    ]
    if mismatches:
        raise ValueError(f"manifest hash mismatch: {mismatches[:5]}")
    return artifact_root, {
        "zipMemberCount": len(names),
        "manifestEntryCount": len(expected),
        "manifestSha256": sha256(manifest),
        "artifactTreeDigest": canon_sha(sorted(expected.items())),
    }


def verify_metadata(lock: dict[str, Any], input_dir: Path) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    main = load(input_dir / "MAIN_BRANCH.json")
    checks["main-baseline"] = (main.get("commit") or {}).get("sha") == lock["mainBaselineSha"]

    mapping = [
        ("r7e", "R7E", "evidenceArtifact"),
        ("r7f", "R7F", "artifact"),
        ("external", "EXTERNAL", "artifact"),
        ("traceability", "TRACEABILITY", "artifact"),
    ]
    for key, prefix, artifact_key in mapping:
        spec = lock[key]
        run = load(input_dir / f"{prefix}_RUN.json")
        artifact = load(input_dir / f"{prefix}_ARTIFACT.json")
        checks[f"{key}-run"] = (
            run.get("id") == spec["runId"]
            and run.get("run_attempt") == spec["runAttempt"]
            and run.get("head_branch") == spec["branch"]
            and run.get("head_sha") == spec["commit"]
            and run.get("path") == spec["workflowPath"]
            and run.get("status") == "completed"
            and run.get("conclusion") == "success"
        )
        artifact_spec = spec[artifact_key]
        checks[f"{key}-artifact"] = (
            artifact.get("id") == artifact_spec["id"]
            and artifact.get("name") == artifact_spec["name"]
            and artifact.get("digest") == artifact_spec["digest"]
            and artifact.get("expired") is False
            and (artifact.get("workflow_run") or {}).get("id") == spec["runId"]
            and (artifact.get("workflow_run") or {}).get("head_sha") == spec["commit"]
        )
        checks[f"{key}-outer-digest"] = (
            "sha256:" + sha256(input_dir / f"{prefix}.zip") == artifact_spec["digest"]
        )

    r7e = lock["r7e"]
    lineage_artifact = load(input_dir / "R7E_LINEAGE_ARTIFACT.json")
    lineage_spec = r7e["lineageArtifact"]
    checks["r7e-lineage-artifact"] = (
        lineage_artifact.get("id") == lineage_spec["id"]
        and lineage_artifact.get("name") == lineage_spec["name"]
        and lineage_artifact.get("digest") == lineage_spec["digest"]
        and lineage_artifact.get("expired") is False
        and (lineage_artifact.get("workflow_run") or {}).get("id") == r7e["runId"]
        and (lineage_artifact.get("workflow_run") or {}).get("head_sha") == r7e["commit"]
    )
    checks["r7e-lineage-outer-digest"] = (
        "sha256:" + sha256(input_dir / "R7E_LINEAGE.zip") == lineage_spec["digest"]
    )
    checks["external-duplicate-name-does-not-select"] = (
        lock["external"].get("duplicateNameOlderArtifactId")
        != lock["external"]["artifact"]["id"]
    )
    return checks


def requirement_carry_ids(row: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    if row.get("carryForwardId"):
        result.add(row["carryForwardId"])
    result.update(row.get("additionalCarryForwardIds") or [])
    return result


def semantic_state(
    lock: dict[str, Any],
    roots: dict[str, Path],
) -> tuple[dict[str, Any], dict[str, bool]]:
    checks: dict[str, bool] = {}

    r7e_root = roots["r7e"]
    r7e_lineage_root = roots["r7e_lineage"]
    r7f_root = roots["r7f"]
    external_root = roots["external"]
    trace_root = roots["traceability"]

    r7e_pkg = load(r7e_root / "R7E_PACKAGE_VALIDATION.json")
    r7e_identity = load(r7e_root / "R7E_EVIDENCE/R7E_CANDIDATE_IDENTITY.json")
    r7e_tuple = load(r7e_lineage_root / "portable-r7e-v4.json")
    r7e_execution = load(r7e_lineage_root / "generated-plan-execution.json")
    r7e_spec = lock["r7e"]

    checks["r7e-gate"] = (
        (r7e_root / "R7E_GATE_DECISION.txt").read_text(encoding="utf-8").strip()
        == "R7E PORTABLE JSON SCHEMA BUILD EVIDENCE COMPLETE — READY FOR INDEPENDENT R7F"
    )
    checks["r7e-package"] = (
        r7e_pkg.get("passed") is True
        and not r7e_pkg.get("failedChecks")
        and bool_checks_pass(r7e_pkg.get("checks"))
    )
    checks["r7e-identity"] = (
        r7e_identity.get("schema") == "R7E_PORTABLE_JSON_SCHEMA_CANDIDATE_IDENTITY_V1"
        and r7e_identity.get("repository") == lock["repository"]
        and r7e_identity.get("workflowCommit") == r7e_spec["commit"]
        and str(r7e_identity.get("runId")) == str(r7e_spec["runId"])
        and r7e_identity.get("sourceCorrectionLayer")
        == "NONE — full-history reconciliation and portable Draft 2020-12 contract folded into canonical packed source"
        and r7e_identity.get("portableSchemaContractVersion") == "1.0.0"
        and r7e_identity.get("portableSchemaDialect")
        == "https://json-schema.org/draft/2020-12/schema"
        and r7e_identity.get("axeIncompleteNodeCount") == 498
    )
    checks["r7e-lineage-tuple"] = (
        r7e_tuple.get("schema") == "R7E_PORTABLE_SELF_RECORDING_AUTHORITATIVE_TUPLE_V4"
        and r7e_tuple.get("passed") is True
        and r7e_tuple.get("branchHeadUnchanged") is True
        and r7e_tuple.get("repository") == lock["repository"]
        and r7e_tuple.get("branch") == r7e_spec["branch"]
        and r7e_tuple.get("workflowPath") == r7e_spec["workflowPath"]
        and r7e_tuple.get("commit") == r7e_spec["commit"]
        and r7e_tuple.get("runId") == r7e_spec["runId"]
        and r7e_tuple.get("runAttempt") == r7e_spec["runAttempt"]
        and r7e_tuple.get("artifact") == r7e_spec["evidenceArtifact"]
        and r7e_tuple.get("sourceFileCount") == 146
        and (r7e_tuple.get("generatedPlan") or {}).get("executedRunStepCount") == 18
        and (r7e_tuple.get("candidateIdentity") or {}).get("axeIncompleteNodeCount") == 498
    )
    checks["r7e-generated-execution"] = (
        r7e_execution.get("schema") == "R7E_GENERATED_PLAN_EXECUTION_V2"
        and r7e_execution.get("passed") is True
        and r7e_execution.get("executedRunStepCount") == 18
        and r7e_execution.get("skippedAllowedUsesCount") == 3
        and r7e_execution.get("skippedConditionCount") == 1
        and r7e_execution.get("firstFailure") is None
        and all(row.get("exitCode") == 0 for row in r7e_execution.get("steps", []))
    )
    checks["r7e-portable-schema-files"] = (
        len(list((r7e_root / "BEARING_PRODUCTION_SOURCE/schemas").glob("*.json"))) == 9
    )

    r7f_pkg = load(r7f_root / "R7F_PACKAGE_VALIDATION.json")
    r7f_selection = load(r7f_root / "R7F_EVIDENCE/r7e-selection.json")
    adaptations = load(r7f_root / "R7F_EVIDENCE/verifier-adaptations.json")
    builder_portable = load(r7f_root / "R7F_EVIDENCE/independent-portable-schema-builder.json")
    verifier_portable = load(r7f_root / "R7F_EVIDENCE/independent-portable-schema-verifier.json")
    portable_parity = load(r7f_root / "R7F_EVIDENCE/portable-schema-builder-verifier-parity.json")
    builder_axe = load(r7f_root / "R7F_EVIDENCE/independent-builder-axe-fingerprint-v2.json")
    verifier_axe = load(r7f_root / "R7F_EVIDENCE/independent-verifier-axe-fingerprint-v2.json")
    r7f_spec = lock["r7f"]

    checks["r7f-gates"] = (
        (r7f_root / "R7F_GATE_DECISION.txt").read_text(encoding="utf-8").strip()
        == "R7F FULL-HISTORY DYNAMIC FINGERPRINT INDEPENDENT VERIFICATION COMPLETE — READY FOR HISTORY-BOUND CONTROLLER"
        and (r7f_root / "R7F_PORTABLE_GATE_DECISION.txt").read_text(encoding="utf-8").strip()
        == "R7F PORTABLE JSON SCHEMA INDEPENDENT VERIFICATION COMPLETE — READY FOR EXTERNAL AUDIT"
    )
    checks["r7f-package"] = (
        r7f_pkg.get("passed") is True
        and not r7f_pkg.get("failedChecks")
        and bool_checks_pass(r7f_pkg.get("checks"))
        and r7f_pkg.get("verificationVersion") == "R7F-generator-bound-portable-final"
        and r7f_pkg.get("repository") == lock["repository"]
        and r7f_pkg.get("verifierCommit") == r7f_spec["commit"]
        and str(r7f_pkg.get("verifierRunId")) == str(r7f_spec["runId"])
    )
    checks["r7f-r7e-binding"] = (
        r7f_pkg.get("builderCommit") == r7e_spec["commit"]
        and str(r7f_pkg.get("builderRunId")) == str(r7e_spec["runId"])
        and str(r7f_pkg.get("builderArtifactId")) == str(r7e_spec["evidenceArtifact"]["id"])
        and r7f_pkg.get("builderArtifactName") == r7e_spec["evidenceArtifact"]["name"]
        and r7f_pkg.get("builderArtifactDigest") == r7e_spec["evidenceArtifact"]["digest"]
        and (r7f_selection.get("lock") or {}).get("builderCommit", (r7f_selection.get("lock") or {}).get("builderHeadSha"))
        == r7e_spec["commit"]
        and (r7f_selection.get("lock") or {}).get("builderArtifactDigest")
        == r7e_spec["evidenceArtifact"]["digest"]
    )
    required_adaptations = {
        "builder gate identity",
        "builder candidate identity schema",
        "builder package schema",
        "builder source-correction identity",
        "builder artifact metadata identity",
        "authenticate immutable commit instead of mutable branch head",
    }
    checks["r7f-adaptations"] = (
        adaptations.get("passed") is True
        and adaptations.get("unboundedChanges") is False
        and set(adaptations.get("allowedClasses") or []) == required_adaptations
    )
    checks["r7f-portable"] = all(
        report.get("passed") is True
        and not report.get("errors")
        for report in (builder_portable, verifier_portable, portable_parity)
    )
    checks["r7f-axe"] = (
        builder_axe.get("passed") is True
        and verifier_axe.get("passed") is True
        and (builder_axe.get("metrics") or {}).get("nodeCount") == 498
        and (verifier_axe.get("metrics") or {}).get("nodeCount") == 498
        and (builder_axe.get("metrics") or {}).get("inventorySha256")
        == (verifier_axe.get("metrics") or {}).get("inventorySha256")
        and (builder_axe.get("metrics") or {}).get("nodeFingerprintSetSha256")
        == (verifier_axe.get("metrics") or {}).get("nodeFingerprintSetSha256")
        and (builder_axe.get("metrics") or {}).get("bindingFingerprintSetSha256")
        == (verifier_axe.get("metrics") or {}).get("bindingFingerprintSetSha256")
    )
    negative_names = [
        "negative-control-desktop-target-v2.json",
        "negative-control-mobile-related-owner-v2.json",
        "negative-control-proof-binding-v2.json",
        "negative-control-self-consistent-inventory-v2.json",
    ]
    checks["r7f-negative-controls"] = all(
        load(r7f_root / "R7F_EVIDENCE" / name).get("passed") is False
        and bool(load(r7f_root / "R7F_EVIDENCE" / name).get("failedChecks"))
        for name in negative_names
    )
    parity_names = [
        "run1-run2-reproducibility.json",
        "run1-builder-dist-parity.json",
        "verifier-builder-stress-parity.json",
        "source-tar-directory-parity.json",
        "staged-source-parity.json",
        "staged-dist-parity.json",
        "staged-stress-parity.json",
        "run1-source-after-independent-browser.json",
        "run1-source-after-exact-fingerprint-v2.json",
    ]
    checks["r7f-parity"] = all(
        load(r7f_root / "R7F_EVIDENCE" / name).get("passed") is True
        for name in parity_names
    )
    checks["r7f-browser"] = (
        load(r7f_root / "R7F_EVIDENCE/independent-browser-gate.json").get("passed") is True
        and len(list((r7f_root / "R7F_RUN1_TMP/screenshots").glob("*.png"))) >= 41
    )

    external_report = load(external_root / "R7_PORTABLE_FINAL_EXTERNAL_AUDIT.json")
    external_semantic = load(external_root / "external-semantic-audit.json")
    external_portable = load(external_root / "external-portable-schema-audit.json")
    checks["external-report"] = (
        external_report.get("schema") == "R7_PORTABLE_FINAL_EXTERNAL_AUDIT_TUPLE_V1"
        and external_report.get("passed") is True
        and external_report.get("decision") == "R7_PORTABLE_FINAL_EXTERNAL_AUDIT_PASS"
        and external_report.get("r7f") == {
            "branch": r7f_spec["branch"],
            "workflowPath": r7f_spec["workflowPath"],
            "headSha": r7f_spec["commit"],
            "runId": r7f_spec["runId"],
            "artifactId": r7f_spec["artifact"]["id"],
            "artifactName": r7f_spec["artifact"]["name"],
            "artifactDigest": r7f_spec["artifact"]["digest"],
        }
        and external_report.get("finalR7ClosureAuthorized") is False
    )
    checks["external-semantic"] = (
        external_semantic.get("passed") is True
        and not external_semantic.get("failedChecks")
        and len(external_semantic.get("adversarialCases") or []) == 8
        and all(row.get("rejected") is True for row in external_semantic.get("adversarialCases") or [])
    )
    checks["external-portable"] = (
        external_portable.get("passed") is True
        and external_portable.get("recordCount") == 12
        and not external_portable.get("errors")
        and bool_checks_pass(external_portable.get("checks"))
    )

    trace_tuple = load(trace_root / "R7_FULL_HISTORY_TRACEABILITY_TUPLE_V5.json")
    trace_matrix = load(trace_root / "R7_REQUIREMENTS_TRACEABILITY_V5.json")
    trace_carry = load(trace_root / "R7_CARRY_FORWARD_REGISTER_V5.json")
    trace_selftest = load(trace_root / "R7_TRACEABILITY_SELFTEST_V5.json")
    trace_spec = lock["traceability"]
    requirements = trace_matrix.get("requirements") or []
    carry_items = trace_carry.get("items") or []
    requirement_ids = [row.get("id") for row in requirements]
    carry_ids = [row.get("id") for row in carry_items]
    expected_carry = set().union(*(requirement_carry_ids(row) for row in requirements))
    actual_carry = set(carry_ids)

    checks["trace-tuple"] = (
        trace_tuple.get("schema") == "R7_FULL_HISTORY_TRACEABILITY_TUPLE_V5"
        and trace_tuple.get("decision") == "R7_FULL_HISTORY_TRACEABILITY_PASS"
        and trace_tuple.get("passed") is True
        and trace_tuple.get("repository") == lock["repository"]
        and trace_tuple.get("workflowCommit") == trace_spec["commit"]
        and str(trace_tuple.get("runId")) == str(trace_spec["runId"])
        and str(trace_tuple.get("runAttempt")) == str(trace_spec["runAttempt"])
        and trace_tuple.get("requirementCount") == 109
        and trace_tuple.get("carryForwardCount") == 32
        and trace_tuple.get("openR7BlockerCount") == 0
        and trace_tuple.get("orphanedMaterialRequirementCount") == 0
        and not trace_tuple.get("failedChecks")
        and not trace_tuple.get("blockers")
        and bool_checks_pass(trace_tuple.get("checks"))
        and trace_tuple.get("wholeWebsiteCompletionAuthorized") is False
        and trace_tuple.get("mainMutationAuthorized") is False
        and trace_tuple.get("productionDeploymentAuthorized") is False
    )
    checks["trace-matrix"] = (
        trace_matrix.get("schema") == "R7_FULL_HISTORY_NORMALIZED_REQUIREMENTS_MATRIX_V5"
        and trace_matrix.get("requirementCount") == 109
        and len(requirements) == 109
        and len(requirement_ids) == len(set(requirement_ids))
        and trace_matrix.get("roadmap") == [f"R{i}" for i in range(1, 14)]
        and trace_matrix.get("authorityHierarchy") == [
            "CURRENT_FACTUAL_TRUTH_AND_PRIVACY",
            "R5_PHOTOGRAPHY_AUTHORITY",
            "R6C_R6D_BEARING_AUTHORITY",
            "R4_CONTENT_IDENTITY_IA",
            "CURRENT_PRIMARY_TECHNICAL_EVIDENCE",
            "R7_ARCHITECTURE",
            "OLDER_PROTOTYPES",
        ]
        and all(
            row.get("status", "").startswith("DEFERRED_BOUND_")
            for row in requirements
            if row.get("phase") in {f"R{i}" for i in range(8, 14)}
        )
        and not any(
            row.get("phase") == "R7"
            and row.get("status") not in {"SATISFIED_R7", "SATISFIED_BY_SUPERSESSION", "USER_WAIVER_BOUND"}
            for row in requirements
        )
    )
    ownership = next(row for row in requirements if row.get("id") == "R6-008")
    checks["trace-ownership"] = (
        ownership.get("status") == "USER_WAIVER_BOUND"
        and "unperformed" in ownership.get("notes", "")
        and set(ownership.get("additionalCarryForwardIds") or []) == {"CF-R6-008-R12"}
        and ownership.get("carryForwardId") == "CF-R6-008"
    )
    checks["trace-carry"] = (
        trace_carry.get("count") == 32
        and len(carry_items) == 32
        and len(carry_ids) == len(set(carry_ids))
        and expected_carry == actual_carry
        and all(row.get("status") == "BOUND_NOT_YET_EXECUTED" for row in carry_items)
        and all(row.get("sourceRequirementId") in set(requirement_ids) for row in carry_items)
    )
    checks["trace-selftest"] = (
        trace_selftest.get("passed") is True
        and trace_selftest.get("authenticAccepted") is True
        and trace_selftest.get("caseCount") == 12
        and len(trace_selftest.get("cases") or []) == 12
        and all(row.get("rejected") is True for row in trace_selftest.get("cases") or [])
        and not trace_selftest.get("failedCases")
    )

    state = {
        "expected": {
            "r7eCommit": r7e_spec["commit"],
            "r7eEvidenceDigest": r7e_spec["evidenceArtifact"]["digest"],
            "r7eLineageDigest": r7e_spec["lineageArtifact"]["digest"],
            "r7fCommit": r7f_spec["commit"],
            "r7fArtifactDigest": r7f_spec["artifact"]["digest"],
            "externalCommit": lock["external"]["commit"],
            "externalArtifactDigest": lock["external"]["artifact"]["digest"],
            "traceabilityCommit": trace_spec["commit"],
            "traceabilityArtifactDigest": trace_spec["artifact"]["digest"],
            "mainSha": lock["mainBaselineSha"],
        },
        "r7e": {
            "commit": r7e_spec["commit"],
            "runId": r7e_spec["runId"],
            "evidenceDigest": r7e_spec["evidenceArtifact"]["digest"],
            "lineageDigest": r7e_spec["lineageArtifact"]["digest"],
            "passed": all(checks[name] for name in checks if name.startswith("r7e")),
        },
        "r7f": {
            "commit": r7f_spec["commit"],
            "runId": r7f_spec["runId"],
            "artifactDigest": r7f_spec["artifact"]["digest"],
            "builderCommit": r7f_pkg.get("builderCommit"),
            "builderDigest": r7f_pkg.get("builderArtifactDigest"),
            "passed": all(checks[name] for name in checks if name.startswith("r7f-")),
        },
        "external": {
            "commit": lock["external"]["commit"],
            "runId": lock["external"]["runId"],
            "artifactDigest": lock["external"]["artifact"]["digest"],
            "r7fCommit": (external_report.get("r7f") or {}).get("headSha"),
            "r7fDigest": (external_report.get("r7f") or {}).get("artifactDigest"),
            "passed": all(checks[name] for name in checks if name.startswith("external-")),
        },
        "traceability": {
            "commit": trace_spec["commit"],
            "runId": trace_spec["runId"],
            "artifactDigest": trace_spec["artifact"]["digest"],
            "requirementCount": trace_tuple.get("requirementCount"),
            "carryForwardCount": trace_tuple.get("carryForwardCount"),
            "openR7BlockerCount": trace_tuple.get("openR7BlockerCount"),
            "orphanedMaterialRequirementCount": trace_tuple.get("orphanedMaterialRequirementCount"),
            "roadmap": trace_matrix.get("roadmap"),
            "authorityHierarchy": trace_matrix.get("authorityHierarchy"),
            "ownershipCaveat": trace_tuple.get("ownershipCaveat"),
            "futureProgrammeStillDeferred": checks["trace-matrix"],
            "passed": all(checks[name] for name in checks if name.startswith("trace-")),
        },
        "scope": copy.deepcopy(lock["scope"]),
        "mainSha": lock["mainBaselineSha"],
    }
    return state, checks


def controller_accepts(state: dict[str, Any]) -> bool:
    expected_authority = [
        "CURRENT_FACTUAL_TRUTH_AND_PRIVACY",
        "R5_PHOTOGRAPHY_AUTHORITY",
        "R6C_R6D_BEARING_AUTHORITY",
        "R4_CONTENT_IDENTITY_IA",
        "CURRENT_PRIMARY_TECHNICAL_EVIDENCE",
        "R7_ARCHITECTURE",
        "OLDER_PROTOTYPES",
    ]
    return (
        state["r7e"]["commit"] == state["expected"]["r7eCommit"]
        and state["r7e"]["evidenceDigest"] == state["expected"]["r7eEvidenceDigest"]
        and state["r7e"]["lineageDigest"] == state["expected"]["r7eLineageDigest"]
        and state["r7f"]["commit"] == state["expected"]["r7fCommit"]
        and state["r7f"]["artifactDigest"] == state["expected"]["r7fArtifactDigest"]
        and state["external"]["commit"] == state["expected"]["externalCommit"]
        and state["external"]["artifactDigest"] == state["expected"]["externalArtifactDigest"]
        and state["traceability"]["commit"] == state["expected"]["traceabilityCommit"]
        and state["traceability"]["artifactDigest"] == state["expected"]["traceabilityArtifactDigest"]
        and state["mainSha"] == state["expected"]["mainSha"]
        and state["r7e"]["passed"] is True
        and state["r7f"]["passed"] is True
        and state["external"]["passed"] is True
        and state["traceability"]["passed"] is True
        and state["r7f"]["builderCommit"] == state["r7e"]["commit"]
        and state["r7f"]["builderDigest"] == state["r7e"]["evidenceDigest"]
        and state["external"]["r7fCommit"] == state["r7f"]["commit"]
        and state["external"]["r7fDigest"] == state["r7f"]["artifactDigest"]
        and state["traceability"]["requirementCount"] == 109
        and state["traceability"]["carryForwardCount"] == 32
        and state["traceability"]["openR7BlockerCount"] == 0
        and state["traceability"]["orphanedMaterialRequirementCount"] == 0
        and state["traceability"]["roadmap"] == [f"R{i}" for i in range(1, 14)]
        and state["traceability"]["authorityHierarchy"] == expected_authority
        and "not recorded" in state["traceability"]["ownershipCaveat"]
        and state["traceability"]["futureProgrammeStillDeferred"] is True
        and state["scope"]["maximumAuthorizedVerdict"] == "R7_TECHNICAL_ARCHITECTURE_CLOSED"
        and state["scope"]["wholeWebsiteCompletionAuthorized"] is False
        and state["scope"]["r8ThroughR13Closed"] is False
        and state["scope"]["mainMutationAuthorized"] is False
        and state["scope"]["productionDeploymentAuthorized"] is False
        and state["mainSha"] == "74d24bd30090991295429ad7600df6f33f668e44"
    )


def run_selftest(state: dict[str, Any]) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []

    def case(name: str, mutate) -> None:
        candidate = copy.deepcopy(state)
        mutate(candidate)
        cases.append({"name": name, "rejected": not controller_accepts(candidate)})

    case("mutate-r7e-evidence-digest", lambda s: s["r7e"].__setitem__("evidenceDigest", "sha256:" + "0" * 64))
    case("mutate-r7e-lineage-digest", lambda s: s["r7e"].__setitem__("lineageDigest", "sha256:" + "0" * 64))
    case("break-r7f-r7e-commit-link", lambda s: s["r7f"].__setitem__("builderCommit", "0" * 40))
    case("break-r7f-r7e-digest-link", lambda s: s["r7f"].__setitem__("builderDigest", "sha256:" + "0" * 64))
    case("mutate-r7f-artifact-digest", lambda s: s["r7f"].__setitem__("artifactDigest", "sha256:" + "0" * 64))
    case("break-external-r7f-commit-link", lambda s: s["external"].__setitem__("r7fCommit", "0" * 40))
    case("break-external-r7f-digest-link", lambda s: s["external"].__setitem__("r7fDigest", "sha256:" + "0" * 64))
    case("open-r7-blocker", lambda s: s["traceability"].__setitem__("openR7BlockerCount", 1))
    case("add-orphaned-requirement", lambda s: s["traceability"].__setitem__("orphanedMaterialRequirementCount", 1))
    case("remove-r13-roadmap", lambda s: s["traceability"]["roadmap"].remove("R13"))
    case("reorder-authority", lambda s: s["traceability"]["authorityHierarchy"].reverse())
    case("erase-ownership-caveat", lambda s: s["traceability"].__setitem__("ownershipCaveat", "formal protocol passed"))
    case("claim-future-programme-complete", lambda s: s["traceability"].__setitem__("futureProgrammeStillDeferred", False))
    case("claim-whole-site-complete", lambda s: s["scope"].__setitem__("wholeWebsiteCompletionAuthorized", True))
    case("claim-r8-r13-closed", lambda s: s["scope"].__setitem__("r8ThroughR13Closed", True))
    case("authorize-main-mutation", lambda s: s["scope"].__setitem__("mainMutationAuthorized", True))
    case("authorize-production-deployment", lambda s: s["scope"].__setitem__("productionDeploymentAuthorized", True))
    case("change-main-baseline", lambda s: s.__setitem__("mainSha", "0" * 40))
    case("mark-r7e-failed", lambda s: s["r7e"].__setitem__("passed", False))
    case("mark-external-failed", lambda s: s["external"].__setitem__("passed", False))

    return {
        "schema": "R7_HISTORY_BOUND_CONTROLLER_SELFTEST_V6",
        "passed": controller_accepts(state) and all(row["rejected"] for row in cases),
        "authenticAccepted": controller_accepts(state),
        "caseCount": len(cases),
        "passedCaseCount": sum(row["rejected"] for row in cases),
        "cases": cases,
        "failedCases": [row["name"] for row in cases if not row["rejected"]],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    lock = load(args.lock)
    input_dir = args.input.resolve()
    output_dir = args.output.resolve()
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True)

    checks = verify_metadata(lock, input_dir)
    work = input_dir / "extracted"
    roots: dict[str, Path] = {}
    manifests: dict[str, Any] = {}
    for key, archive_name, manifest_name in (
        ("r7e", "R7E.zip", "R7E_ARTIFACT_SHA256SUMS.txt"),
        ("r7e_lineage", "R7E_LINEAGE.zip", "EXECUTOR_LINEAGE_SHA256SUMS.txt"),
        ("r7f", "R7F.zip", "R7F_ARTIFACT_SHA256SUMS.txt"),
        ("external", "EXTERNAL.zip", "R7_PORTABLE_FINAL_EXTERNAL_AUDIT_SHA256SUMS.txt"),
        ("traceability", "TRACEABILITY.zip", "R7_TRACEABILITY_SHA256SUMS.txt"),
    ):
        try:
            roots[key], manifests[key] = safe_extract_and_verify(
                input_dir / archive_name,
                work / key,
                manifest_name,
            )
            checks[f"{key}-zip-and-manifest"] = True
        except Exception as exc:
            checks[f"{key}-zip-and-manifest"] = False
            manifests[key] = {"error": str(exc)}

    if all(checks.get(f"{key}-zip-and-manifest") for key in roots):
        state, semantic_checks = semantic_state(lock, roots)
        checks.update(semantic_checks)
    else:
        state = {
            "expected": {
                "r7eCommit": lock["r7e"]["commit"],
                "r7eEvidenceDigest": lock["r7e"]["evidenceArtifact"]["digest"],
                "r7eLineageDigest": lock["r7e"]["lineageArtifact"]["digest"],
                "r7fCommit": lock["r7f"]["commit"],
                "r7fArtifactDigest": lock["r7f"]["artifact"]["digest"],
                "externalCommit": lock["external"]["commit"],
                "externalArtifactDigest": lock["external"]["artifact"]["digest"],
                "traceabilityCommit": lock["traceability"]["commit"],
                "traceabilityArtifactDigest": lock["traceability"]["artifact"]["digest"],
                "mainSha": lock["mainBaselineSha"],
            },
            "r7e": {"passed": False},
            "r7f": {"passed": False},
            "external": {"passed": False},
            "traceability": {"passed": False},
            "scope": copy.deepcopy(lock["scope"]),
            "mainSha": lock["mainBaselineSha"],
        }

    authentic = all(checks.values()) and controller_accepts(state)
    selftest = run_selftest(state)
    passed = authentic and selftest["passed"]
    report = {
        "schema": "R7_HISTORY_BOUND_FINAL_CONTROLLER_V6",
        "decision": "R7_CLOSED" if passed else "R7_NOT_CLOSED",
        "passed": passed,
        "repository": lock["repository"],
        "inputLockSha256": sha256(args.lock),
        "checkCount": len(checks),
        "passedCheckCount": sum(checks.values()),
        "checks": checks,
        "failedChecks": [name for name, value in checks.items() if not value],
        "blockers": (
            []
            if passed
            else [name for name, value in checks.items() if not value]
            + ([] if controller_accepts(state) else ["controller-semantic-acceptance"])
            + ([] if selftest["passed"] else ["controller-adversarial-selftest"])
        ),
        "artifactManifests": manifests,
        "stateDigest": canon_sha(state),
        "state": state,
        "selftestPassed": selftest["passed"],
        "selftestCaseCount": selftest["caseCount"],
        "maximumAuthorizedVerdict": "R7_TECHNICAL_ARCHITECTURE_CLOSED" if passed else "NONE",
        "scope": copy.deepcopy(lock["scope"]),
        "ownershipCaveat": state.get("traceability", {}).get("ownershipCaveat"),
        "wholeWebsiteCompletionAuthorized": False,
        "r8ThroughR13Closed": False,
        "mainMutationAuthorized": False,
        "productionDeploymentAuthorized": False,
    }

    (output_dir / "R7_HISTORY_BOUND_FINAL_CONTROLLER_V6.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "R7_HISTORY_BOUND_CONTROLLER_SELFTEST_V6.json").write_text(
        json.dumps(selftest, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "R7_CONTROLLER_INPUT_LOCK_V6.json").write_text(
        json.dumps(lock, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "R7_CONTROLLER_DECISION.txt").write_text(
        (
            "R7 TECHNICAL ARCHITECTURE CLOSED — R8-R13 REMAIN OPEN; NO MAIN MUTATION OR PRODUCTION DEPLOYMENT AUTHORIZED\n"
            if passed
            else "R7 NOT CLOSED — CONTROLLER INPUT OR SEMANTIC CHECK FAILED\n"
        ),
        encoding="utf-8",
    )
    evidence_summary = {
        "schema": "R7_CONTROLLER_UPSTREAM_EVIDENCE_SUMMARY_V6",
        "outerArtifactDigests": {
            "r7eEvidence": lock["r7e"]["evidenceArtifact"]["digest"],
            "r7eLineage": lock["r7e"]["lineageArtifact"]["digest"],
            "r7f": lock["r7f"]["artifact"]["digest"],
            "external": lock["external"]["artifact"]["digest"],
            "traceability": lock["traceability"]["artifact"]["digest"],
        },
        "upstreamManifestSummaries": manifests,
        "controllerStateDigest": report["stateDigest"],
    }
    (output_dir / "R7_CONTROLLER_UPSTREAM_EVIDENCE_SUMMARY_V6.json").write_text(
        json.dumps(evidence_summary, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest_path = output_dir / "R7_CONTROLLER_ARTIFACT_SHA256SUMS.txt"
    files = sorted(path for path in output_dir.rglob("*") if path.is_file() and path != manifest_path)
    manifest_path.write_text(
        "".join(f"{sha256(path)}  ./{path.relative_to(output_dir).as_posix()}\n" for path in files),
        encoding="utf-8",
    )

    print(json.dumps(report, indent=2))
    print(json.dumps(selftest, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
