#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record(checks: dict[str, bool], name: str, value: bool) -> None:
    checks[name] = bool(value)


def require_link_report(checks: dict[str, bool], prefix: str, report: dict[str, Any], stress: bool) -> None:
    minimum_html = 500 if stress else 10
    minimum_refs = 8000 if stress else 200
    minimum_docs = 7000 if stress else 150
    minimum_assets = 500 if stress else 30
    record(checks, f"{prefix}:pass", report.get("pass") is True or report.get("passed") is True)
    record(checks, f"{prefix}:non-vacuous-html", int(report.get("htmlFileCount", 0)) >= minimum_html)
    record(checks, f"{prefix}:non-vacuous-references", int(report.get("referenceCount", 0)) >= minimum_refs)
    record(checks, f"{prefix}:non-vacuous-documents", int(report.get("documentReferenceCount", 0)) >= minimum_docs)
    record(checks, f"{prefix}:non-vacuous-assets", int(report.get("assetReferenceCount", 0)) >= minimum_assets)
    record(checks, f"{prefix}:no-broken", int(report.get("brokenCount", -1)) == 0)
    record(checks, f"{prefix}:inventory-bound", isinstance(report.get("inventorySha256"), str) and len(report["inventorySha256"]) == 64)


def builder_gate(args: argparse.Namespace) -> dict[str, Any]:
    root: Path = args.builder_root.resolve()
    evidence = root / "R7E_EVIDENCE"
    identity = load(evidence / "R7E_CANDIDATE_IDENTITY.json")
    package_validation = load(root / "R7E_PACKAGE_VALIDATION.json")
    source_tree = load(args.source_tree)
    dist_tree = load(args.dist_tree)
    stress_tree = load(args.stress_tree)
    checks: dict[str, bool] = {}

    record(checks, "gate-ready", (root / "R7E_GATE_DECISION.txt").read_text().strip() == "R7E FULL-HISTORY RECONCILED BUILD EVIDENCE COMPLETE — READY FOR INDEPENDENT R7F")
    record(checks, "package-validation-passed", package_validation.get("passed") is True and all(package_validation.get("checks", {}).values()))
    record(checks, "repository-bound", identity.get("repository") == args.repository)
    record(checks, "builder-run-bound", str(identity.get("runId")) == args.expected_run)
    record(checks, "builder-commit-bound", identity.get("workflowCommit") == args.expected_commit)
    record(checks, "source-archive-bound", identity.get("sourceArchiveSha256") == args.expected_source_archive)
    record(checks, "no-correction-layer", identity.get("sourceCorrectionLayer") == "NONE — full-history reconciliation and portable Draft 2020-12 contract folded into canonical packed source")
    record(checks, "source-tree-bound", source_tree.get("treeSha256") == identity.get("frozenSourceTreeSha256") and int(source_tree.get("entryCount", 0)) >= 100)
    record(checks, "dist-tree-bound", dist_tree.get("treeSha256") == identity.get("verifiedDistTreeSha256") and int(dist_tree.get("entryCount", 0)) >= 30)
    record(checks, "stress-tree-bound", stress_tree.get("treeSha256") == identity.get("stressDistTreeSha256") and int(stress_tree.get("entryCount", 0)) >= 530)
    record(checks, "frozen-tar-bound", sha256(root / "BEARING_FROZEN_SOURCE.tar") == identity.get("frozenSourceTarSha256"))
    record(checks, "package-json-bound", sha256(root / "BEARING_PRODUCTION_SOURCE/package.json") == identity.get("packageJsonSha256"))
    record(checks, "package-lock-bound", sha256(root / "BEARING_PRODUCTION_SOURCE/package-lock.json") == identity.get("packageLockSha256"))
    record(checks, "stress-input-bound", sha256(evidence / "stress-input-manifest.json") == identity.get("stressInputManifestSha256"))
    record(checks, "stress-lineage-bound", sha256(evidence / "stress-lineage.json") == identity.get("stressLineageSha256"))
    record(checks, "artifact-metadata-bound", args.expected_artifact_name == f"r7e-portable-self-recording-v4-evidence-{args.expected_commit}" and args.expected_artifact_digest.startswith("sha256:") and len(args.expected_artifact_digest) == 71)

    lineage = load(evidence / "stress-lineage.json")
    for key in ("inputRecordCount", "normalizedUniqueIds", "normalizedUniqueSlugs", "normalizedUniqueRoutes", "emittedDetailPageCount", "workIndexCoverage", "archiveCoverage"):
        record(checks, f"lineage:{key}", lineage.get(key) == 500)
    record(checks, "lineage:passed", lineage.get("passed") is True and lineage.get("designation") == "TEST_ONLY_DO_NOT_DEPLOY")

    require_link_report(checks, "builder-production-links", load(root / "R7E_RUN1_TMP/link-validation-production.json"), stress=False)
    require_link_report(checks, "builder-stress-links", load(root / "R7E_RUN1_TMP/link-validation-stress.json"), stress=True)

    dist_inspection = load(root / "R7E_RUN1_TMP/dist-inspection.json")
    record(checks, "builder-dist-inspection-clean", len(dist_inspection.get("findings", [])) == 0)
    record(checks, "builder-single-executable-script", dist_inspection.get("executableScriptCount") == 1 and len(dist_inspection.get("jsAssets", [])) == 1)

    result = {
        "gate": "builder-authenticity",
        "builderRunId": args.expected_run,
        "builderCommit": args.expected_commit,
        "builderArtifactName": args.expected_artifact_name,
        "builderArtifactDigest": args.expected_artifact_digest,
        "sourceArchiveSha256": args.expected_source_archive,
        "identity": identity,
        "checks": checks,
        "failedChecks": [name for name, passed in checks.items() if not passed],
        "passed": all(checks.values()),
    }
    return result


def runtime_gate(args: argparse.Namespace) -> dict[str, Any]:
    tmp: Path = args.tmp_root.resolve()
    checks: dict[str, bool] = {}

    require_link_report(checks, "candidate-production-links", load(tmp / "link-validation-production.json"), stress=False)
    require_link_report(checks, "candidate-stress-links", load(tmp / "link-validation-stress.json"), stress=True)

    browser = load(tmp / "playwright/browser-results.json")
    browser_stats = browser.get("stats", {})
    record(checks, "browser:expected-42", browser_stats.get("expected") == 42)
    record(checks, "browser:no-skips", browser_stats.get("skipped") == 0)
    record(checks, "browser:no-unexpected", browser_stats.get("unexpected") == 0)
    record(checks, "browser:no-flaky", browser_stats.get("flaky") == 0)
    record(checks, "browser:no-errors", len(browser.get("errors", [])) == 0)
    screenshots = list((tmp / "screenshots").glob("*.png"))
    record(checks, "browser:screenshot-minimum", len(screenshots) >= 40)
    required_screenshots = {
        "home-320.png",
        "work-320.png",
        "archive-320.png",
        "about-320.png",
        "vce-320.png",
        "alternate-long-czech-320.png",
        "alternate-no-js-vce-390.png",
        "alternate-forced-colors-home-390.png",
    }
    record(checks, "browser:torture-evidence", required_screenshots.issubset({path.name for path in screenshots}))

    axe = load(tmp / "playwright/axe-results.json")
    axe_stats = axe.get("stats", {})
    record(checks, "axe:expected-10", axe_stats.get("expected") == 10)
    record(checks, "axe:no-skips", axe_stats.get("skipped") == 0)
    record(checks, "axe:no-unexpected", axe_stats.get("unexpected") == 0)
    record(checks, "axe:no-flaky", axe_stats.get("flaky") == 0)
    raw_axe = sorted((tmp / "axe").glob("*.json"))
    record(checks, "axe:raw-count", len(raw_axe) == 10)
    record(checks, "axe:zero-violations", len(raw_axe) == 10 and all(len(load(path).get("violations", [])) == 0 for path in raw_axe))

    lighthouse = load(tmp / "lighthouse/summary.json")
    reports = lighthouse.get("reports", [])
    record(checks, "lighthouse:pass", lighthouse.get("pass") is True)
    record(checks, "lighthouse:four-reports", len(reports) == 4)
    record(checks, "lighthouse:performance", len(reports) == 4 and all(float(report.get("scores", {}).get("performance", 0)) >= 0.9 for report in reports))
    record(checks, "lighthouse:accessibility", len(reports) == 4 and all(float(report.get("scores", {}).get("accessibility", 0)) >= 0.95 for report in reports))
    record(checks, "lighthouse:zero-cls", len(reports) == 4 and all(float(report.get("cls", 1)) == 0 for report in reports))
    server = lighthouse.get("server", {})
    record(checks, "lighthouse:served-artifact-bound", server.get("expectedHomeSha256") == server.get("servedHomeSha256") and isinstance(server.get("servedHomeSha256"), str))

    network = load(tmp / "network/audit.json")
    record(checks, "network:route-coverage", network.get("expectedRoutes") == 5 and network.get("auditedRoutes") == 5)
    record(checks, "network:no-third-party", network.get("genuineThirdPartyRuntimeRequestCount") == 0)
    record(checks, "network:no-http-errors", network.get("firstPartyHttpErrorCount") == 0)
    record(checks, "network:no-request-failures", network.get("requestFailureCount") == 0)
    record(checks, "network:no-audit-error", network.get("auditError") is None)
    network_server = network.get("server", {})
    record(checks, "network:served-artifact-bound", network_server.get("expectedHomeSha256") == network_server.get("servedHomeSha256") and isinstance(network_server.get("servedHomeSha256"), str))

    lineage = load(tmp / "stress/lineage.json")
    record(checks, "stress:passed", lineage.get("passed") is True and lineage.get("designation") == "TEST_ONLY_DO_NOT_DEPLOY")
    for key in ("inputRecordCount", "normalizedUniqueIds", "normalizedUniqueSlugs", "normalizedUniqueRoutes", "emittedDetailPageCount", "workIndexCoverage", "archiveCoverage"):
        record(checks, f"stress:{key}", lineage.get(key) == 500)
    record(checks, "wrangler:output", (tmp / "wrangler").is_dir() and any(path.is_file() for path in (tmp / "wrangler").rglob("*")))

    result = {
        "gate": "runtime-evidence",
        "checks": checks,
        "failedChecks": [name for name, passed in checks.items() if not passed],
        "metrics": {
            "browserExpected": browser_stats.get("expected"),
            "screenshotCount": len(screenshots),
            "axeExpected": axe_stats.get("expected"),
            "axeRawCount": len(raw_axe),
            "lighthouseReports": len(reports),
            "lighthouseScores": [report.get("scores") for report in reports],
            "networkAuditedRoutes": network.get("auditedRoutes"),
            "stressInputRecordCount": lineage.get("inputRecordCount"),
        },
        "passed": all(checks.values()),
    }
    return result


def write_result(result: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="R7F v3 evidence semantic gates")
    commands = parser.add_subparsers(dest="command", required=True)

    builder = commands.add_parser("builder")
    builder.add_argument("--builder-root", type=Path, required=True)
    builder.add_argument("--source-tree", type=Path, required=True)
    builder.add_argument("--dist-tree", type=Path, required=True)
    builder.add_argument("--stress-tree", type=Path, required=True)
    builder.add_argument("--repository", required=True)
    builder.add_argument("--expected-run", required=True)
    builder.add_argument("--expected-commit", required=True)
    builder.add_argument("--expected-artifact-name", required=True)
    builder.add_argument("--expected-artifact-digest", required=True)
    builder.add_argument("--expected-source-archive", required=True)
    builder.add_argument("--output", type=Path, required=True)

    runtime = commands.add_parser("runtime")
    runtime.add_argument("--tmp-root", type=Path, required=True)
    runtime.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    result = builder_gate(args) if args.command == "builder" else runtime_gate(args)
    write_result(result, args.output)


if __name__ == "__main__":
    main()
