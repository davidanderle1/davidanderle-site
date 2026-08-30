#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

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


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Independent semantic audit of R7E/R7F raw axe evidence and non-vacuous contrast compensation")
    parser.add_argument("tmp_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    tmp = args.tmp_root.resolve()
    axe_root = tmp / "axe"
    compensation_root = tmp / "axe-compensation"
    checks: dict[str, bool] = {}
    errors: list[dict[str, Any]] = []

    def record(name: str, value: bool) -> None:
        checks[name] = bool(value)

    contrast_path = tmp / "contrast-bounds.json"
    contrast = load(contrast_path) if contrast_path.is_file() else {}
    record("contrast-proof:present", contrast_path.is_file())
    record("contrast-proof:designation", contrast.get("designation") == "R7E_STATIC_CONTRAST_BOUND_V1")
    record("contrast-proof:passed", contrast.get("passed") is True)
    record("contrast-proof:check-count-32", contrast.get("checkCount") == 32)
    record("contrast-proof:minimum-ratio", float(contrast.get("minimumObservedRatio", 0)) >= 4.5)
    record("contrast-proof:no-failures", contrast.get("failed") == [])

    proofs: dict[int, dict[str, Any]] = {}
    proof_summaries: dict[str, Any] = {}
    for width in (1280, 390):
        path = compensation_root / f"home-route-backplates-{width}.json"
        proof = load(path) if path.is_file() else {}
        proofs[width] = proof
        elements = proof.get("elements") or []
        layers = proof.get("layers") or {}
        record(f"proof:{width}:present", path.is_file())
        record(f"proof:{width}:designation", proof.get("designation") == "R7E_BEARING_ROUTE_BACKPLATE_V1")
        record(f"proof:{width}:width", proof.get("width") == width)
        record(f"proof:{width}:passed", proof.get("passed") is True)
        record(f"proof:{width}:expected-element-count", proof.get("expectedElementCount") == 12)
        record(f"proof:{width}:element-count", len(elements) == 12)
        record(
            f"proof:{width}:opaque-backplates",
            len(elements) == 12
            and all(
                element.get("passed") is True
                and element.get("backgroundColor") == EXPECTED_BACKGROUND
                and element.get("backgroundImage") == "none"
                and element.get("position") == "relative"
                and element.get("zIndex") == "2"
                and isinstance(element.get("html"), str)
                and bool(element.get("html"))
                for element in elements
            ),
        )
        if width == 1280:
            record("proof:1280:layering", layers.get("desktopSignatureBelowList") is True and layers.get("mobilePseudoBelowBackplates") is False)
        else:
            record("proof:390:layering", layers.get("mobilePseudoBelowBackplates") is True and layers.get("desktopSignatureBelowList") is False)
        proof_summaries[str(width)] = {
            "path": str(path.relative_to(tmp)) if path.is_file() else str(path),
            "sha256": sha256(path) if path.is_file() else None,
            "passed": proof.get("passed"),
            "elementCount": len(elements),
            "expectedBackground": proof.get("expectedBackground"),
            "layers": layers,
        }

    raw_paths = sorted(axe_root.glob("*.json")) if axe_root.is_dir() else []
    record("axe:raw-directory", axe_root.is_dir())
    record("axe:exact-file-inventory", {path.name for path in raw_paths} == set(EXPECTED_FILES))

    total_keys: Counter[str] = Counter()
    raw_summaries: list[dict[str, Any]] = []
    total_violations = 0
    total_nodes = 0

    for path in raw_paths:
        report = load(path)
        violations = report.get("violations") or []
        incomplete = report.get("incomplete") or []
        total_violations += len(violations)
        file_keys: Counter[str] = Counter()
        file_errors: list[dict[str, Any]] = []

        if violations:
            file_errors.append({"code": "AXE_VIOLATIONS", "count": len(violations), "ids": [row.get("id") for row in violations]})
        if len(incomplete) != 1 or incomplete[0].get("id") != "color-contrast" or not incomplete[0].get("nodes"):
            file_errors.append({"code": "UNEXPECTED_INCOMPLETE_RESULT_SET", "ids": [row.get("id") for row in incomplete]})

        width = 1280 if path.stem.endswith("-1280") else 390 if path.stem.endswith("-390") else 0
        proof = proofs.get(width, {})
        exact_html = {element.get("html") for element in (proof.get("elements") or []) if element.get("passed") is True}
        layers = proof.get("layers") or {}

        for result in incomplete:
            for node in result.get("nodes") or []:
                total_nodes += 1
                any_rows = node.get("any") or []
                all_rows = node.get("all") or []
                none_rows = node.get("none") or []
                check = any_rows[0] if len(any_rows) == 1 else {}
                message_key = (check.get("data") or {}).get("messageKey")
                related = check.get("relatedNodes") or []
                file_keys[str(message_key)] += 1
                total_keys[str(message_key)] += 1
                valid = False

                common = (
                    result.get("id") == "color-contrast"
                    and len(any_rows) == 1
                    and check.get("id") == "color-contrast"
                    and check.get("impact") == "serious"
                    and not all_rows
                    and not none_rows
                )
                if common and message_key == "bgGradient" and len(related) == 1:
                    target = related[0].get("target") or []
                    html = related[0].get("html")
                    valid = (target == ["body"] and html == "<body>") or (
                        target == ["#limitations"]
                        and html == '<section class="limitation-block" id="limitations" aria-labelledby="limitations-title">'
                    )
                elif common and path.name.startswith("home-") and proof.get("passed") is True and node.get("html") in exact_html:
                    if message_key == "elmPartiallyObscuring":
                        valid = not related and layers.get("desktopSignatureBelowList") is True
                    elif message_key == "pseudoContent" and len(related) == 1:
                        target = related[0].get("target") or []
                        html = related[0].get("html") or ""
                        valid = (
                            layers.get("mobilePseudoBelowBackplates") is True
                            and len(target) == 1
                            and (target[0] == "ol" or re.fullmatch(r"ol > li:nth-child\([1-3]\)", target[0] or "") is not None)
                            and (html == '<ol class="bearing-list">' or html.startswith("<li>"))
                        )

                if not valid:
                    file_errors.append(
                        {
                            "code": "UNCOMPENSATED_INCOMPLETE_NODE",
                            "target": node.get("target"),
                            "html": node.get("html"),
                            "messageKey": message_key,
                            "relatedNodes": related,
                        }
                    )

        expected = Counter(EXPECTED_FILES.get(path.name, {}))
        if file_keys != expected:
            file_errors.append({"code": "FILE_MESSAGE_KEY_INVENTORY", "expected": dict(expected), "actual": dict(file_keys)})
        if file_errors:
            errors.extend({"file": path.name, **row} for row in file_errors)
        raw_summaries.append(
            {
                "file": path.name,
                "sha256": sha256(path),
                "violations": len(violations),
                "incompleteResultCount": len(incomplete),
                "incompleteNodeCount": sum(len(row.get("nodes") or []) for row in incomplete),
                "messageKeys": dict(file_keys),
                "errors": file_errors,
            }
        )

    record("axe:zero-violations", total_violations == 0)
    record("axe:exact-total-node-count", total_nodes == 438)
    record("axe:exact-message-key-inventory", total_keys == Counter(EXPECTED_TOTAL_KEYS))
    record("axe:no-uncompensated-nodes", not errors)

    playwright_path = tmp / "playwright/axe-results.json"
    playwright = load(playwright_path) if playwright_path.is_file() else {}
    stats = playwright.get("stats") or {}
    record("playwright:axe-result-present", playwright_path.is_file())
    record("playwright:expected-10", stats.get("expected") == 10)
    record("playwright:no-skips", stats.get("skipped") == 0)
    record("playwright:no-unexpected", stats.get("unexpected") == 0)
    record("playwright:no-flaky", stats.get("flaky") == 0)
    record("playwright:no-errors", playwright.get("errors") == [])

    result = {
        "audit": "R7F_INDEPENDENT_AXE_COMPENSATION_AUDIT_V1",
        "passed": all(checks.values()),
        "tmpRoot": str(tmp),
        "checks": checks,
        "failedChecks": [name for name, passed in checks.items() if not passed],
        "metrics": {
            "rawFileCount": len(raw_paths),
            "totalViolations": total_violations,
            "totalIncompleteNodes": total_nodes,
            "messageKeys": dict(total_keys),
            "staticContrastMinimumObservedRatio": contrast.get("minimumObservedRatio"),
        },
        "proofs": proof_summaries,
        "rawReports": raw_summaries,
        "errors": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
