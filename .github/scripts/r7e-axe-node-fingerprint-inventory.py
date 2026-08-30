#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA = "R7E_AXE_NODE_FINGERPRINT_INVENTORY_V1"
RECORD_SCHEMA = "R7E_AXE_NODE_FINGERPRINT_V1"
EXPECTED_FILES = {
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
EXPECTED_TOTAL_KEYS = {"bgGradient": 430, "elmPartiallyObscuring": 2, "pseudoContent": 6}
EXPECTED_BACKGROUND = "rgb(7, 16, 20)"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def target_strings(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def nth_indices(target: list[str]) -> list[int]:
    found: list[int] = []
    for part in target:
        found.extend(int(match) for match in re.findall(r"li:nth-child\((\d+)\)", part))
    return found


def exact_related(related: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "target": target_strings(row.get("target")),
            "html": str(row.get("html") or ""),
        }
        for row in related
    ]


def payload_for(report_name: str, result: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    any_rows = node.get("any") or []
    check = any_rows[0] if len(any_rows) == 1 and isinstance(any_rows[0], dict) else {}
    return {
        "schema": RECORD_SCHEMA,
        "report": report_name,
        "ruleId": result.get("id"),
        "nodeTarget": target_strings(node.get("target")),
        "nodeHtml": str(node.get("html") or ""),
        "checkId": check.get("id"),
        "impact": check.get("impact") or result.get("impact"),
        "messageKey": (check.get("data") or {}).get("messageKey"),
        "relatedNodes": exact_related(check.get("relatedNodes") or []),
    }


def proof_match(proof: dict[str, Any], html: str, target: list[str]) -> tuple[int | None, int | None, list[int]]:
    elements = proof.get("elements") or []
    matches = [index for index, element in enumerate(elements) if element.get("passed") is True and element.get("html") == html]
    inferred = nth_indices(target)
    inferred_index = inferred[-1] if inferred else None
    if len(elements) == 12:
        compatible = [index for index in matches if inferred_index is None or index // 4 + 1 == inferred_index]
        if len(compatible) == 1:
            index = compatible[0]
            return index, index // 4 + 1, matches
    if len(matches) == 1:
        index = matches[0]
        return index, index // 4 + 1 if len(elements) == 12 else None, matches
    return None, inferred_index, matches


def classify(
    report_name: str,
    result: dict[str, Any],
    node: dict[str, Any],
    proof: dict[str, Any] | None,
) -> tuple[bool, str, dict[str, Any], list[str]]:
    errors: list[str] = []
    any_rows = node.get("any") or []
    all_rows = node.get("all") or []
    none_rows = node.get("none") or []
    check = any_rows[0] if len(any_rows) == 1 and isinstance(any_rows[0], dict) else {}
    key = (check.get("data") or {}).get("messageKey")
    related = exact_related(check.get("relatedNodes") or [])
    target = target_strings(node.get("target"))
    html = str(node.get("html") or "")
    common = (
        result.get("id") == "color-contrast"
        and len(any_rows) == 1
        and check.get("id") == "color-contrast"
        and check.get("impact") == "serious"
        and not all_rows
        and not none_rows
        and bool(target)
        and bool(html)
    )
    if not common:
        return False, "invalid-common-shape", {}, ["COMMON_SHAPE"]

    if key == "bgGradient":
        allowed = (
            len(related) == 1
            and (
                (related[0]["target"] == ["body"] and related[0]["html"] == "<body>")
                or (
                    related[0]["target"] == ["#limitations"]
                    and related[0]["html"] == '<section class="limitation-block" id="limitations" aria-labelledby="limitations-title">'
                )
            )
        )
        if not allowed:
            errors.append("GRADIENT_RELATED_NODE")
        return allowed, "static-gradient-bound", {"related": related}, errors

    if not report_name.startswith("home-") or not proof or proof.get("passed") is not True:
        return False, "missing-home-proof", {}, ["HOME_PROOF"]

    element_index, expected_list_index, html_matches = proof_match(proof, html, target)
    layers = proof.get("layers") or {}
    binding: dict[str, Any] = {
        "proofDesignation": proof.get("designation"),
        "proofWidth": proof.get("width"),
        "proofElementIndex": element_index,
        "proofHtmlMatchIndices": html_matches,
        "expectedListIndex": expected_list_index,
        "nodeTargetIndices": nth_indices(target),
    }
    if element_index is None:
        errors.append("EXACT_BACKPLATE_BINDING")

    if key == "elmPartiallyObscuring":
        allowed = (
            report_name == "home-1280.json"
            and element_index is not None
            and not related
            and layers.get("desktopSignatureBelowList") is True
        )
        if not allowed:
            errors.append("DESKTOP_LAYER_BINDING")
        return allowed, "desktop-opaque-backplate", binding, errors

    if key == "pseudoContent":
        related_target = related[0]["target"] if len(related) == 1 else []
        related_html = related[0]["html"] if len(related) == 1 else ""
        related_indices = nth_indices(related_target)
        same_item = (
            expected_list_index is not None
            and len(related_indices) == 1
            and related_indices[0] == expected_list_index
        )
        list_host = related_target == ["ol"] and related_html == '<ol class="bearing-list">'
        item_host = (
            len(related_indices) == 1
            and related_html.startswith("<li>")
            and same_item
        )
        binding.update(
            {
                "relatedTarget": related_target,
                "relatedHtml": related_html,
                "relatedListIndices": related_indices,
                "sameListItem": same_item,
                "listHostContainsAffectedItem": list_host and expected_list_index is not None,
            }
        )
        allowed = (
            report_name == "home-390.json"
            and element_index is not None
            and len(related) == 1
            and layers.get("mobilePseudoBelowBackplates") is True
            and (list_host or item_host)
        )
        if not allowed:
            errors.append("MOBILE_PSEUDO_EXACT_RELATION")
        return allowed, "mobile-opaque-backplate", binding, errors

    return False, "unsupported-message-key", binding, ["MESSAGE_KEY"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build exact fingerprint-bound adjudication inventory from R7E raw Axe evidence")
    parser.add_argument("artifact_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    root = args.artifact_root.resolve()
    tmp = root / "R7E_RUN1_TMP"
    axe_root = tmp / "axe"
    proof_root = tmp / "axe-compensation"
    contrast_path = tmp / "contrast-bounds.json"
    checks: dict[str, bool] = {}
    errors: list[dict[str, Any]] = []

    raw_paths = sorted(axe_root.glob("*.json")) if axe_root.is_dir() else []
    checks["raw-directory"] = axe_root.is_dir()
    checks["exact-report-inventory"] = {path.name for path in raw_paths} == set(EXPECTED_FILES)

    contrast = load(contrast_path) if contrast_path.is_file() else {}
    checks["contrast-proof"] = (
        contrast.get("designation") == "R7E_STATIC_CONTRAST_BOUND_V1"
        and contrast.get("passed") is True
        and contrast.get("checkCount") == 32
        and float(contrast.get("minimumObservedRatio", 0)) >= 4.5
        and contrast.get("failed") == []
    )

    proofs: dict[int, dict[str, Any]] = {}
    proof_hashes: dict[str, str] = {}
    for width in (1280, 390):
        path = proof_root / f"home-route-backplates-{width}.json"
        proof = load(path) if path.is_file() else {}
        proofs[width] = proof
        proof_hashes[str(width)] = digest_file(path) if path.is_file() else ""
        elements = proof.get("elements") or []
        layers = proof.get("layers") or {}
        checks[f"proof-{width}"] = (
            path.is_file()
            and proof.get("designation") == "R7E_BEARING_ROUTE_BACKPLATE_V1"
            and proof.get("width") == width
            and proof.get("passed") is True
            and proof.get("expectedElementCount") == 12
            and len(elements) == 12
            and all(
                element.get("passed") is True
                and element.get("backgroundColor") == EXPECTED_BACKGROUND
                and element.get("backgroundImage") == "none"
                and element.get("position") == "relative"
                and element.get("zIndex") == "2"
                and isinstance(element.get("html"), str)
                and bool(element.get("html"))
                for element in elements
            )
            and (
                (width == 1280 and layers.get("desktopSignatureBelowList") is True)
                or (width == 390 and layers.get("mobilePseudoBelowBackplates") is True)
            )
        )

    records: list[dict[str, Any]] = []
    report_summaries: list[dict[str, Any]] = []
    total_keys: Counter[str] = Counter()
    total_violations = 0

    for path in raw_paths:
        report = load(path)
        violations = report.get("violations") or []
        incomplete = report.get("incomplete") or []
        total_violations += len(violations)
        file_keys: Counter[str] = Counter()
        file_records: list[str] = []
        if violations:
            errors.append({"report": path.name, "code": "AXE_VIOLATIONS", "count": len(violations)})
        if len(incomplete) != 1 or incomplete[0].get("id") != "color-contrast" or not incomplete[0].get("nodes"):
            errors.append({"report": path.name, "code": "INCOMPLETE_RESULT_SET"})
        width = 1280 if path.stem.endswith("-1280") else 390 if path.stem.endswith("-390") else 0
        ordinal = 0
        for result_index, result in enumerate(incomplete):
            for node_index, node in enumerate(result.get("nodes") or []):
                payload = payload_for(path.name, result, node)
                fingerprint = digest_value(payload)
                passed, classification, proof_binding, node_errors = classify(path.name, result, node, proofs.get(width))
                key = str(payload.get("messageKey"))
                file_keys[key] += 1
                total_keys[key] += 1
                ordinal += 1
                record = {
                    "recordId": f"{path.name}#{ordinal:04d}",
                    "resultIndex": result_index,
                    "nodeIndex": node_index,
                    "fingerprint": fingerprint,
                    "payload": payload,
                    "classification": classification,
                    "proofBinding": proof_binding,
                    "passed": passed,
                    "errors": node_errors,
                }
                records.append(record)
                file_records.append(fingerprint)
                if not passed:
                    errors.append({"report": path.name, "code": "UNADJUDICATED_NODE", "record": record})
        expected = Counter(EXPECTED_FILES.get(path.name, {}))
        if file_keys != expected:
            errors.append({"report": path.name, "code": "MESSAGE_KEY_INVENTORY", "expected": dict(expected), "actual": dict(file_keys)})
        report_summaries.append(
            {
                "report": path.name,
                "rawSha256": digest_file(path),
                "violationCount": len(violations),
                "incompleteNodeCount": len(file_records),
                "messageKeys": dict(file_keys),
                "fingerprintsSha256": digest_value(sorted(file_records)),
            }
        )

    checks["zero-violations"] = total_violations == 0
    checks["exact-node-count"] = len(records) == 438
    checks["exact-message-key-inventory"] = total_keys == Counter(EXPECTED_TOTAL_KEYS)
    checks["all-nodes-adjudicated"] = not errors
    records.sort(key=lambda row: (row["payload"]["report"], row["fingerprint"], row["recordId"]))
    fingerprint_multiset = sorted(row["fingerprint"] for row in records)
    inventory = {
        "schema": SCHEMA,
        "passed": all(checks.values()),
        "checks": checks,
        "failedChecks": [name for name, passed in checks.items() if not passed],
        "metrics": {
            "reportCount": len(raw_paths),
            "violationCount": total_violations,
            "nodeCount": len(records),
            "messageKeys": dict(total_keys),
            "minimumStaticContrastRatio": contrast.get("minimumObservedRatio"),
        },
        "sourceEvidence": {
            "contrastProofSha256": digest_file(contrast_path) if contrast_path.is_file() else None,
            "routeProofSha256": proof_hashes,
            "reports": sorted(report_summaries, key=lambda row: row["report"]),
        },
        "fingerprintMultisetSha256": digest_value(fingerprint_multiset),
        "recordsSha256": digest_value(records),
        "records": records,
        "errors": errors,
    }
    inventory["inventorySha256"] = digest_value({key: value for key, value in inventory.items() if key != "inventorySha256"})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: inventory[key] for key in ("schema", "passed", "failedChecks", "metrics", "fingerprintMultisetSha256", "recordsSha256", "inventorySha256")}, indent=2))
    if not inventory["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
