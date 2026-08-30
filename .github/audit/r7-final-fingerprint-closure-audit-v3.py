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


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def vhash(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def fhash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def strlist(value: Any) -> list[str]:
    return [str(x) for x in value] if isinstance(value, list) else []


def nth(parts: list[str]) -> list[int]:
    values: list[int] = []
    for part in parts:
        values.extend(int(x) for x in re.findall(r"li:nth-child\((\d+)\)", part))
    return values


def exact_payload(report_name: str, rule: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    any_rows = node.get("any") or []
    check = any_rows[0] if len(any_rows) == 1 and isinstance(any_rows[0], dict) else {}
    related = [
        {"target": strlist(row.get("target")), "html": str(row.get("html") or "")}
        for row in (check.get("relatedNodes") or [])
    ]
    return {
        "schema": "R7E_AXE_NODE_FINGERPRINT_V1",
        "report": report_name,
        "ruleId": rule.get("id"),
        "nodeTarget": strlist(node.get("target")),
        "nodeHtml": str(node.get("html") or ""),
        "checkId": check.get("id"),
        "impact": check.get("impact") or rule.get("impact"),
        "messageKey": (check.get("data") or {}).get("messageKey"),
        "relatedNodes": related,
    }


def proof_ok(proof: dict[str, Any], width: int) -> bool:
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
            and row.get("backgroundColor") == "rgb(7, 16, 20)"
            and row.get("backgroundImage") == "none"
            and row.get("position") == "relative"
            and row.get("zIndex") == "2"
            and bool(row.get("html"))
            for row in elements
        )
        and (
            (width == 1280 and layers.get("desktopSignatureBelowList") is True)
            or (width == 390 and layers.get("mobilePseudoBelowBackplates") is True)
        )
    )


def resolve_item(proof: dict[str, Any], html: str, target: list[str]) -> tuple[int | None, int | None]:
    elements = proof.get("elements") or []
    matches = [i for i, row in enumerate(elements) if row.get("passed") is True and row.get("html") == html]
    target_indices = nth(target)
    target_item = target_indices[-1] if target_indices else None
    if len(elements) == 12:
        narrowed = [i for i in matches if target_item is None or i // 4 + 1 == target_item]
        if len(narrowed) == 1:
            return narrowed[0], narrowed[0] // 4 + 1
    if len(matches) == 1:
        return matches[0], matches[0] // 4 + 1 if len(elements) == 12 else target_item
    return None, target_item


def recompute(tmp: Path, label: str) -> dict[str, Any]:
    axe_root = tmp / "axe"
    proof_root = tmp / "axe-compensation"
    contrast_path = tmp / "contrast-bounds.json"
    contrast = load(contrast_path) if contrast_path.is_file() else {}
    proofs = {
        width: load(proof_root / f"home-route-backplates-{width}.json")
        if (proof_root / f"home-route-backplates-{width}.json").is_file() else {}
        for width in (1280, 390)
    }
    errors: list[dict[str, Any]] = []
    reports = sorted(axe_root.glob("*.json")) if axe_root.is_dir() else []
    payloads: list[dict[str, Any]] = []
    fingerprints: list[str] = []
    key_counts: Counter[str] = Counter()
    violations = 0
    if {p.name for p in reports} != set(EXPECTED_REPORTS):
        errors.append({"code": "REPORT_SET", "actual": [p.name for p in reports]})
    if not (
        contrast.get("designation") == "R7E_STATIC_CONTRAST_BOUND_V1"
        and contrast.get("passed") is True
        and contrast.get("checkCount") == 32
        and float(contrast.get("minimumObservedRatio", 0)) >= 4.5
        and contrast.get("failed") == []
    ):
        errors.append({"code": "STATIC_CONTRAST_PROOF"})
    for width, proof in proofs.items():
        if not proof_ok(proof, width):
            errors.append({"code": "ROUTE_BACKPLATE_PROOF", "width": width})

    for path in reports:
        report = load(path)
        violations += len(report.get("violations") or [])
        incomplete = report.get("incomplete") or []
        file_counts: Counter[str] = Counter()
        if report.get("violations"):
            errors.append({"code": "AXE_VIOLATION", "report": path.name})
        if len(incomplete) != 1 or incomplete[0].get("id") != "color-contrast" or not incomplete[0].get("nodes"):
            errors.append({"code": "INCOMPLETE_SHAPE", "report": path.name})
        width = 1280 if path.stem.endswith("-1280") else 390
        for rule in incomplete:
            for node in rule.get("nodes") or []:
                payload = exact_payload(path.name, rule, node)
                payloads.append(payload)
                fingerprints.append(vhash(payload))
                key = str(payload.get("messageKey"))
                key_counts[key] += 1
                file_counts[key] += 1
                any_rows = node.get("any") or []
                check = any_rows[0] if len(any_rows) == 1 and isinstance(any_rows[0], dict) else {}
                common = (
                    rule.get("id") == "color-contrast"
                    and len(any_rows) == 1
                    and check.get("id") == "color-contrast"
                    and check.get("impact") == "serious"
                    and not (node.get("all") or [])
                    and not (node.get("none") or [])
                    and bool(payload["nodeTarget"])
                    and bool(payload["nodeHtml"])
                )
                valid = common
                if key == "bgGradient":
                    rel = payload["relatedNodes"]
                    valid = valid and len(rel) == 1 and (
                        (rel[0]["target"] == ["body"] and rel[0]["html"] == "<body>")
                        or (
                            rel[0]["target"] == ["#limitations"]
                            and rel[0]["html"] == '<section class="limitation-block" id="limitations" aria-labelledby="limitations-title">'
                        )
                    )
                elif path.name.startswith("home-") and key in ("elmPartiallyObscuring", "pseudoContent"):
                    proof = proofs[width]
                    element_index, item_index = resolve_item(proof, payload["nodeHtml"], payload["nodeTarget"])
                    valid = valid and proof_ok(proof, width) and element_index is not None
                    if key == "elmPartiallyObscuring":
                        valid = valid and path.name == "home-1280.json" and payload["relatedNodes"] == [] and (proof.get("layers") or {}).get("desktopSignatureBelowList") is True
                    else:
                        rel = payload["relatedNodes"]
                        valid = valid and path.name == "home-390.json" and len(rel) == 1 and (proof.get("layers") or {}).get("mobilePseudoBelowBackplates") is True
                        if len(rel) == 1:
                            related_index = nth(rel[0]["target"])
                            list_host = rel[0]["target"] == ["ol"] and rel[0]["html"] == '<ol class="bearing-list">' and item_index is not None
                            item_host = item_index is not None and len(related_index) == 1 and related_index[0] == item_index and rel[0]["html"].startswith("<li>")
                            valid = valid and (list_host or item_host)
                else:
                    valid = False
                if not valid:
                    errors.append({"code": "UNBOUND_AXE_NODE", "report": path.name, "fingerprint": vhash(payload), "payload": payload})
        if file_counts != Counter(EXPECTED_REPORTS.get(path.name, {})):
            errors.append({"code": "REPORT_KEY_COUNTS", "report": path.name, "expected": EXPECTED_REPORTS.get(path.name), "actual": dict(file_counts)})

    return {
        "label": label,
        "passed": not errors and violations == 0 and len(payloads) == 438 and key_counts == EXPECTED_KEYS,
        "payloadCounter": Counter(canonical(p).decode("utf-8") for p in payloads),
        "fingerprintCounter": Counter(fingerprints),
        "fingerprintMultisetSha256": vhash(sorted(fingerprints)),
        "metrics": {
            "reportCount": len(reports),
            "violationCount": violations,
            "nodeCount": len(payloads),
            "messageKeys": dict(key_counts),
            "minimumStaticContrastRatio": contrast.get("minimumObservedRatio"),
        },
        "errors": errors,
    }


def json_pass(path: Path) -> bool:
    try:
        obj = load(path)
        return obj.get("passed") is True and not obj.get("failedChecks")
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Final independent R7 closure auditor with exact Axe-node fingerprint recomputation")
    parser.add_argument("r7e", type=Path)
    parser.add_argument("r7f", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    r7e = args.r7e.resolve()
    r7f = args.r7f.resolve()
    checks: dict[str, bool] = {}
    evidence: dict[str, Any] = {}

    def check(name: str, value: bool) -> None:
        checks[name] = bool(value)

    check("r7e-gate", (r7e / "R7E_FINGERPRINT_BOUND_GATE_DECISION.txt").read_text().strip() == "R7E FINGERPRINT-BOUND EVIDENCE VERIFIED — READY FOR R7F V6")
    check("r7e-base-gate", "READY FOR INDEPENDENT R7F" in (r7e / "R7E_GATE_DECISION.txt").read_text())
    check("r7e-package", json_pass(r7e / "R7E_PACKAGE_VALIDATION.json"))
    check("r7e-fingerprint-package", json_pass(r7e / "R7E_FINGERPRINT_PACKAGE_VALIDATION.json"))
    check("r7f-gate", (r7f / "R7F_GATE_DECISION.txt").read_text().strip() == "R7F V6 FINGERPRINT-BOUND INDEPENDENT VERIFICATION COMPLETE — R7 MAY CLOSE AFTER FINAL AUDIT")
    check("r7f-package", json_pass(r7f / "R7F_PACKAGE_VALIDATION.json"))

    r7e_required = [
        "R7E_EVIDENCE/reproducibility.json",
        "R7E_EVIDENCE/run1-dist-post-reproducibility.json",
        "R7E_EVIDENCE/stress-lineage.json",
    ]
    for rel in r7e_required:
        check(f"r7e:{rel}", json_pass(r7e / rel))
    lineage = load(r7e / "R7E_EVIDENCE/stress-lineage.json")
    check("r7e-stress-500", all(lineage.get(name) == 500 for name in ("inputRecordCount", "normalizedUniqueIds", "normalizedUniqueSlugs", "normalizedUniqueRoutes", "emittedDetailPageCount", "workIndexCoverage", "archiveCoverage")))

    r7f_required = [
        "R7F_EVIDENCE/run1-run2-reproducibility.json",
        "R7F_EVIDENCE/final-builder-dist-parity.json",
        "R7F_EVIDENCE/final-builder-stress-parity.json",
        "R7F_EVIDENCE/runtime-evidence-gate.json",
        "R7F_EVIDENCE/independent-source-audit.json",
        "R7F_EVIDENCE/independent-run1-production-links-final.json",
        "R7F_EVIDENCE/independent-run1-production-dist-final.json",
        "R7F_EVIDENCE/independent-builder-axe-fingerprint-audit.json",
        "R7F_EVIDENCE/independent-verifier-axe-fingerprint-audit.json",
        "R7F_EVIDENCE/builder-input-lock-v6-gate.json",
        "R7F_EVIDENCE/run1-source-after-fingerprint-audit.json",
    ]
    for rel in r7f_required:
        check(f"r7f:{rel}", json_pass(r7f / rel))

    lock = load(r7f / "R7F_EVIDENCE/builder-input-lock-v6.json")
    builder_inventory_path = r7e / "R7E_EVIDENCE/axe-node-fingerprint-inventory-v1.json"
    inventory = load(builder_inventory_path)
    inventory_without_digest = {key: value for key, value in inventory.items() if key != "inventorySha256"}
    check("inventory-schema", inventory.get("schema") == "R7E_AXE_NODE_FINGERPRINT_INVENTORY_V1")
    check("inventory-passed", inventory.get("passed") is True and inventory.get("failedChecks") == [])
    check("inventory-self-digest", inventory.get("inventorySha256") == vhash(inventory_without_digest))
    records = inventory.get("records") or []
    check("inventory-438", len(records) == 438)
    check("inventory-record-fingerprints", all(row.get("fingerprint") == vhash(row.get("payload")) for row in records))
    check("lock-inventory", lock.get("builderFingerprintInventorySha256") == inventory.get("inventorySha256"))
    check("lock-multiset", lock.get("builderFingerprintMultisetSha256") == inventory.get("fingerprintMultisetSha256"))

    e = recompute(r7e / "R7E_RUN1_TMP", "r7e")
    f = recompute(r7f / "R7F_RUN1_TMP", "r7f")
    inventory_payload_counter = Counter(canonical(row.get("payload")).decode("utf-8") for row in records)
    inventory_fingerprint_counter = Counter(str(row.get("fingerprint")) for row in records)
    check("r7e-raw-recompute", e["passed"])
    check("r7f-raw-recompute", f["passed"])
    check("r7e-vs-inventory-payload", e["payloadCounter"] == inventory_payload_counter)
    check("r7e-vs-inventory-fingerprint", e["fingerprintCounter"] == inventory_fingerprint_counter)
    check("r7f-vs-inventory-payload", f["payloadCounter"] == inventory_payload_counter)
    check("r7f-vs-inventory-fingerprint", f["fingerprintCounter"] == inventory_fingerprint_counter)
    check("r7e-r7f-payload-parity", e["payloadCounter"] == f["payloadCounter"])
    check("r7e-r7f-fingerprint-parity", e["fingerprintCounter"] == f["fingerprintCounter"])
    check("multiset-digest-parity", e["fingerprintMultisetSha256"] == f["fingerprintMultisetSha256"] == inventory.get("fingerprintMultisetSha256"))

    desktop_negative = load(r7f / "R7F_EVIDENCE/negative-control-desktop-target.json")
    mobile_negative = load(r7f / "R7F_EVIDENCE/negative-control-mobile-related-index.json")
    proof_negative = load(r7f / "R7F_EVIDENCE/negative-control-compensation-proof.json")
    check("desktop-negative-rejected", desktop_negative.get("passed") is False and "exact-fingerprint-multiset" in (desktop_negative.get("failedChecks") or []))
    check("mobile-negative-rejected", mobile_negative.get("passed") is False and "exact-fingerprint-multiset" in (mobile_negative.get("failedChecks") or []))
    check("proof-negative-rejected", proof_negative.get("passed") is False and "proof-1280" in (proof_negative.get("failedChecks") or []))

    package = load(r7f / "R7F_PACKAGE_VALIDATION.json")
    package_checks = package.get("checks") or {}
    for name in (
        "desktop-target-negative-rejected",
        "mobile-related-index-negative-rejected",
        "compensation-proof-negative-rejected",
        "builder-exact-fingerprints",
        "verifier-exact-fingerprints",
        "builder-verifier-fingerprint-parity",
        "source-immutable-after-fingerprint-audit",
        "immutable-fingerprint-bound-input-lock",
    ):
        check(f"r7f-package-check:{name}", package_checks.get(name) is True)

    evidence.update({
        "r7eRaw": {"passed": e["passed"], "metrics": e["metrics"], "errors": e["errors"][:20]},
        "r7fRaw": {"passed": f["passed"], "metrics": f["metrics"], "errors": f["errors"][:20]},
        "inventory": {
            "path": str(builder_inventory_path),
            "fileSha256": fhash(builder_inventory_path),
            "inventorySha256": inventory.get("inventorySha256"),
            "fingerprintMultisetSha256": inventory.get("fingerprintMultisetSha256"),
            "recordCount": len(records),
        },
        "lock": lock,
    })
    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "audit": "R7_FINAL_FINGERPRINT_BOUND_CLOSURE_AUDIT_V3",
        "decision": "R7_CLOSED" if not failed else "R7_NOT_CLOSED",
        "passed": not failed,
        "checkCount": len(checks),
        "checks": checks,
        "failedChecks": failed,
        "blockers": failed,
        "evidence": evidence,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
