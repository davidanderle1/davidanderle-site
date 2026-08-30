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
EXPECTED_BACKGROUND = "rgb(7, 16, 20)"


def compact(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def value_sha(value: Any) -> str:
    return hashlib.sha256(compact(value)).hexdigest()


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def strings(value: Any) -> list[str]:
    return [str(part) for part in value] if isinstance(value, list) else []


def indices(selector_parts: list[str]) -> list[int]:
    out: list[int] = []
    for part in selector_parts:
        out.extend(int(item) for item in re.findall(r"li:nth-child\((\d+)\)", part))
    return out


def related_rows(check: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"target": strings(item.get("target")), "html": str(item.get("html") or "")}
        for item in (check.get("relatedNodes") or [])
    ]


def payload(report_name: str, rule: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    any_rows = node.get("any") or []
    check = any_rows[0] if len(any_rows) == 1 and isinstance(any_rows[0], dict) else {}
    return {
        "schema": "R7E_AXE_NODE_FINGERPRINT_V1",
        "report": report_name,
        "ruleId": rule.get("id"),
        "nodeTarget": strings(node.get("target")),
        "nodeHtml": str(node.get("html") or ""),
        "checkId": check.get("id"),
        "impact": check.get("impact") or rule.get("impact"),
        "messageKey": (check.get("data") or {}).get("messageKey"),
        "relatedNodes": related_rows(check),
    }


def proof_element(proof: dict[str, Any], node_html: str, node_target: list[str]) -> tuple[int | None, int | None]:
    elements = proof.get("elements") or []
    exact = [i for i, row in enumerate(elements) if row.get("passed") is True and row.get("html") == node_html]
    target_index = indices(node_target)
    target_item = target_index[-1] if target_index else None
    if len(elements) == 12:
        narrowed = [i for i in exact if target_item is None or i // 4 + 1 == target_item]
        if len(narrowed) == 1:
            return narrowed[0], narrowed[0] // 4 + 1
    if len(exact) == 1:
        return exact[0], exact[0] // 4 + 1 if len(elements) == 12 else target_item
    return None, target_item


def validate_proof(proof: dict[str, Any], width: int) -> bool:
    elements = proof.get("elements") or []
    layers = proof.get("layers") or {}
    return (
        proof.get("designation") == "R7E_BEARING_ROUTE_BACKPLATE_V1"
        and proof.get("width") == width
        and proof.get("passed") is True
        and proof.get("expectedElementCount") == 12
        and len(elements) == 12
        and all(
            row.get("passed") is True
            and row.get("backgroundColor") == EXPECTED_BACKGROUND
            and row.get("backgroundImage") == "none"
            and row.get("position") == "relative"
            and row.get("zIndex") == "2"
            and isinstance(row.get("html"), str)
            and bool(row.get("html"))
            for row in elements
        )
        and (
            (width == 1280 and layers.get("desktopSignatureBelowList") is True)
            or (width == 390 and layers.get("mobilePseudoBelowBackplates") is True)
        )
    )


def independently_adjudicate(report_name: str, rule: dict[str, Any], node: dict[str, Any], proof: dict[str, Any] | None) -> tuple[bool, str, dict[str, Any]]:
    any_rows = node.get("any") or []
    check = any_rows[0] if len(any_rows) == 1 and isinstance(any_rows[0], dict) else {}
    rel = related_rows(check)
    target = strings(node.get("target"))
    html = str(node.get("html") or "")
    key = (check.get("data") or {}).get("messageKey")
    common = (
        rule.get("id") == "color-contrast"
        and len(any_rows) == 1
        and check.get("id") == "color-contrast"
        and check.get("impact") == "serious"
        and not (node.get("all") or [])
        and not (node.get("none") or [])
        and bool(target)
        and bool(html)
    )
    if not common:
        return False, "COMMON_SHAPE", {}

    if key == "bgGradient":
        exact = len(rel) == 1 and (
            (rel[0]["target"] == ["body"] and rel[0]["html"] == "<body>")
            or (
                rel[0]["target"] == ["#limitations"]
                and rel[0]["html"] == '<section class="limitation-block" id="limitations" aria-labelledby="limitations-title">'
            )
        )
        return exact, "STATIC_GRADIENT", {"related": rel}

    if not report_name.startswith("home-") or proof is None:
        return False, "HOME_PROOF_MISSING", {}
    width = 1280 if report_name.endswith("-1280.json") else 390
    if not validate_proof(proof, width):
        return False, "HOME_PROOF_INVALID", {}
    element_index, item_index = proof_element(proof, html, target)
    if element_index is None:
        return False, "BACKPLATE_IDENTITY", {"target": target, "html": html}
    layers = proof.get("layers") or {}

    if key == "elmPartiallyObscuring":
        valid = report_name == "home-1280.json" and not rel and layers.get("desktopSignatureBelowList") is True
        return valid, "DESKTOP_EXACT_BACKPLATE", {"elementIndex": element_index, "itemIndex": item_index, "target": target}

    if key == "pseudoContent":
        if report_name != "home-390.json" or len(rel) != 1 or layers.get("mobilePseudoBelowBackplates") is not True:
            return False, "MOBILE_PROOF_SHAPE", {"related": rel}
        rel_target = rel[0]["target"]
        rel_html = rel[0]["html"]
        rel_indices = indices(rel_target)
        list_host = rel_target == ["ol"] and rel_html == '<ol class="bearing-list">' and item_index is not None
        same_item = item_index is not None and len(rel_indices) == 1 and rel_indices[0] == item_index and rel_html.startswith("<li>")
        valid = list_host or same_item
        return valid, "MOBILE_EXACT_RELATION", {
            "elementIndex": element_index,
            "itemIndex": item_index,
            "nodeTarget": target,
            "relatedTarget": rel_target,
            "relatedHtml": rel_html,
            "relatedIndices": rel_indices,
            "sameListItem": same_item,
            "listHost": list_host,
        }

    return False, "UNSUPPORTED_KEY", {"messageKey": key}


def main() -> None:
    parser = argparse.ArgumentParser(description="Independently recompute exact Axe node fingerprints and verify the builder-bound inventory")
    parser.add_argument("tmp_root", type=Path)
    parser.add_argument("builder_inventory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--label", default="candidate")
    args = parser.parse_args()

    tmp = args.tmp_root.resolve()
    inventory_path = args.builder_inventory.resolve()
    builder = load(inventory_path)
    checks: dict[str, bool] = {}
    findings: list[dict[str, Any]] = []

    checks["builder-schema"] = builder.get("schema") == "R7E_AXE_NODE_FINGERPRINT_INVENTORY_V1"
    checks["builder-passed"] = builder.get("passed") is True and builder.get("failedChecks") == []
    supplied_without_digest = {key: value for key, value in builder.items() if key != "inventorySha256"}
    checks["builder-inventory-digest"] = builder.get("inventorySha256") == value_sha(supplied_without_digest)
    builder_records = builder.get("records") or []
    checks["builder-record-count"] = len(builder_records) == 438
    checks["builder-record-self-hashes"] = all(
        isinstance(row, dict)
        and row.get("fingerprint") == value_sha(row.get("payload"))
        for row in builder_records
    )

    contrast_path = tmp / "contrast-bounds.json"
    contrast = load(contrast_path) if contrast_path.is_file() else {}
    checks["contrast-proof"] = (
        contrast.get("designation") == "R7E_STATIC_CONTRAST_BOUND_V1"
        and contrast.get("passed") is True
        and contrast.get("checkCount") == 32
        and float(contrast.get("minimumObservedRatio", 0)) >= 4.5
        and contrast.get("failed") == []
    )

    proof_root = tmp / "axe-compensation"
    proofs: dict[int, dict[str, Any]] = {}
    for width in (1280, 390):
        path = proof_root / f"home-route-backplates-{width}.json"
        proof = load(path) if path.is_file() else {}
        proofs[width] = proof
        checks[f"proof-{width}"] = path.is_file() and validate_proof(proof, width)

    axe_root = tmp / "axe"
    raw_paths = sorted(axe_root.glob("*.json")) if axe_root.is_dir() else []
    checks["exact-report-set"] = {path.name for path in raw_paths} == set(EXPECTED_REPORTS)
    fresh_rows: list[dict[str, Any]] = []
    total_keys: Counter[str] = Counter()
    total_violations = 0
    for path in raw_paths:
        report = load(path)
        violations = report.get("violations") or []
        incomplete = report.get("incomplete") or []
        total_violations += len(violations)
        file_keys: Counter[str] = Counter()
        if violations:
            findings.append({"report": path.name, "code": "AXE_VIOLATIONS", "count": len(violations)})
        if len(incomplete) != 1 or incomplete[0].get("id") != "color-contrast" or not incomplete[0].get("nodes"):
            findings.append({"report": path.name, "code": "INCOMPLETE_RESULT_SET"})
        width = 1280 if path.stem.endswith("-1280") else 390
        for rule in incomplete:
            for node in rule.get("nodes") or []:
                exact_payload = payload(path.name, rule, node)
                fingerprint = value_sha(exact_payload)
                valid, adjudication, binding = independently_adjudicate(path.name, rule, node, proofs.get(width))
                key = str(exact_payload.get("messageKey"))
                total_keys[key] += 1
                file_keys[key] += 1
                fresh_rows.append({
                    "fingerprint": fingerprint,
                    "payload": exact_payload,
                    "adjudication": adjudication,
                    "binding": binding,
                    "passed": valid,
                })
                if not valid:
                    findings.append({"report": path.name, "code": "INDEPENDENT_ADJUDICATION", "fingerprint": fingerprint, "payload": exact_payload, "binding": binding})
        expected = Counter(EXPECTED_REPORTS.get(path.name, {}))
        if file_keys != expected:
            findings.append({"report": path.name, "code": "REPORT_KEY_COUNTS", "expected": dict(expected), "actual": dict(file_keys)})

    fresh_payload_counter = Counter(compact(row["payload"]).decode("utf-8") for row in fresh_rows)
    builder_payload_counter = Counter(compact(row.get("payload")).decode("utf-8") for row in builder_records)
    fresh_fingerprint_counter = Counter(row["fingerprint"] for row in fresh_rows)
    builder_fingerprint_counter = Counter(str(row.get("fingerprint")) for row in builder_records)
    missing_payloads = list((builder_payload_counter - fresh_payload_counter).elements())
    unexpected_payloads = list((fresh_payload_counter - builder_payload_counter).elements())
    missing_fingerprints = list((builder_fingerprint_counter - fresh_fingerprint_counter).elements())
    unexpected_fingerprints = list((fresh_fingerprint_counter - builder_fingerprint_counter).elements())

    checks["zero-violations"] = total_violations == 0
    checks["exact-node-count"] = len(fresh_rows) == 438
    checks["exact-key-counts"] = total_keys == EXPECTED_KEYS
    checks["all-independently-adjudicated"] = not any(not row["passed"] for row in fresh_rows)
    checks["exact-payload-multiset"] = not missing_payloads and not unexpected_payloads
    checks["exact-fingerprint-multiset"] = not missing_fingerprints and not unexpected_fingerprints
    computed_multiset_sha = value_sha(sorted(row["fingerprint"] for row in fresh_rows))
    checks["builder-multiset-digest"] = builder.get("fingerprintMultisetSha256") == computed_multiset_sha
    if missing_payloads or unexpected_payloads:
        findings.append({
            "code": "PAYLOAD_MULTISET_MISMATCH",
            "missingFromCandidate": missing_payloads[:10],
            "unexpectedInCandidate": unexpected_payloads[:10],
            "missingCount": len(missing_payloads),
            "unexpectedCount": len(unexpected_payloads),
        })
    if missing_fingerprints or unexpected_fingerprints:
        findings.append({
            "code": "FINGERPRINT_MULTISET_MISMATCH",
            "missing": missing_fingerprints[:20],
            "unexpected": unexpected_fingerprints[:20],
            "missingCount": len(missing_fingerprints),
            "unexpectedCount": len(unexpected_fingerprints),
        })

    result = {
        "audit": "R7F_INDEPENDENT_AXE_FINGERPRINT_AUDIT_V1",
        "label": args.label,
        "passed": all(checks.values()),
        "checks": checks,
        "failedChecks": [name for name, passed in checks.items() if not passed],
        "metrics": {
            "reportCount": len(raw_paths),
            "violationCount": total_violations,
            "nodeCount": len(fresh_rows),
            "messageKeys": dict(total_keys),
            "fingerprintMultisetSha256": computed_multiset_sha,
            "minimumStaticContrastRatio": contrast.get("minimumObservedRatio"),
        },
        "builderInventory": {
            "path": str(inventory_path),
            "sha256": file_sha(inventory_path),
            "inventorySha256": builder.get("inventorySha256"),
            "fingerprintMultisetSha256": builder.get("fingerprintMultisetSha256"),
        },
        "findings": findings,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
