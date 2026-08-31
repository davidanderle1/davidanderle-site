#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path

REQUIRED_PATHS = [
    "package.json",
    "package-lock.json",
    ".node-version",
    ".nvmrc",
    "astro.config.mjs",
    "astro.stress.config.mjs",
    "src/content.config.ts",
    "docs/R7_HISTORY_RECONCILIATION.md",
    "src/components/HomepageRecordPreview.astro",
    "src/components/WritingRecordPreview.astro",
    "src/lib/profile-copy.ts",
    "src/pages/index.astro",
    "src/pages/work/[slug].astro",
    "src/pages/writing/[slug].astro",
    "src/components/BearingRoute.astro",
    "src/components/ResponsiveMedia.astro",
    "src/components/VceSequence.astro",
    "src/scripts/vce-sequence.ts",
    "src/styles/global.css",
    "src/styles/project.css",
    "scripts/clean-generated.mjs",
    "scripts/inspect-dist.mjs",
    "scripts/source-preflight.mjs",
    "scripts/validate-content.mjs",
    "scripts/validate-links.mjs",
    "scripts/verify-stress-lineage.mjs",
    ".github/workflows/production-reference.yml",
    "verification/clean-run.sh",
    "verification/clean-run.ps1",
    "wrangler.jsonc",
]
VERIFY_ALL_ORDER = [
    "clean:generated",
    "preflight:workspace",
    "check",
    "build",
    "html:validate",
    "links:validate",
    "validate:fixtures",
    "test:stress",
    "test:browser",
    "test:axe",
    "test:lighthouse",
    "network:audit",
    "wrangler:validate",
]
BAD_VERSION_RE = re.compile(r"(?:\^|~|\*|\bx\b|latest|>|<|\|\|)", re.I)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def audit(root: Path) -> dict[str, object]:
    root = root.resolve()
    if not root.is_dir():
        raise SystemExit(f"Source root is not a directory: {root}")
    findings: list[dict[str, object]] = []
    checks: dict[str, bool] = {}

    for required in REQUIRED_PATHS:
        present = (root / required).is_file()
        checks[f"required:{required}"] = present
        if not present:
            findings.append({"code": "MISSING_REQUIRED_PATH", "path": required})

    files: list[Path] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            findings.append({"code": "SOURCE_SYMLINK", "path": relative, "target": os.readlink(path)})
        elif path.is_file():
            files.append(path)
        elif not path.is_dir():
            findings.append({"code": "UNSUPPORTED_SOURCE_ENTRY", "path": relative})

    forbidden_directories = [".git", "node_modules", "dist", ".astro", ".r7e-tmp"]
    for directory in forbidden_directories:
        absent = not (root / directory).exists()
        checks[f"forbidden-directory-absent:{directory}"] = absent
        if not absent:
            findings.append({"code": "FORBIDDEN_SOURCE_DIRECTORY", "path": directory})

    generated_prefixes = ["public/assets/portrait", "public/assets/js", "public/artifacts", "src/data/generated"]
    for prefix in generated_prefixes:
        generated_files = [path.relative_to(root).as_posix() for path in files if path.relative_to(root).as_posix().startswith(f"{prefix}/")]
        absent = not generated_files
        checks[f"generated-output-absent:{prefix}"] = absent
        if not absent:
            findings.append({"code": "GENERATED_SOURCE_OUTPUT", "path": prefix, "files": generated_files})

    package_path = root / "package.json"
    lock_path = root / "package-lock.json"
    package: dict[str, object] = json.loads(read(package_path)) if package_path.is_file() else {}
    lock: dict[str, object] = json.loads(read(lock_path)) if lock_path.is_file() else {}
    package_manager = package.get("packageManager")
    engines = package.get("engines") if isinstance(package.get("engines"), dict) else {}
    checks["exact-package-manager"] = package_manager == "npm@11.19.0"
    checks["exact-node-engine"] = engines.get("node") == "24.20.0"
    checks["exact-npm-engine"] = engines.get("npm") == "11.19.0"
    checks["lockfile-version-3"] = lock.get("lockfileVersion") == 3
    lock_packages = lock.get("packages") if isinstance(lock.get("packages"), dict) else {}
    checks["complete-lockfile"] = len(lock_packages) >= 500

    non_exact_dependencies: list[dict[str, str]] = []
    for group in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        values = package.get(group)
        if not isinstance(values, dict):
            continue
        for name, version in sorted(values.items()):
            if not isinstance(version, str) or BAD_VERSION_RE.search(version):
                non_exact_dependencies.append({"group": group, "name": name, "version": str(version)})
    checks["exact-dependency-pins"] = not non_exact_dependencies
    if non_exact_dependencies:
        findings.append({"code": "NON_EXACT_DEPENDENCIES", "dependencies": non_exact_dependencies})

    scripts = package.get("scripts") if isinstance(package.get("scripts"), dict) else {}
    verify_all = str(scripts.get("verify:all", ""))
    positions = [verify_all.find(f"npm run {name}") for name in VERIFY_ALL_ORDER]
    checks["verify-all-complete-and-ordered"] = all(position >= 0 for position in positions) and positions == sorted(positions)
    checks["production-link-validator-non-linkinator"] = str(scripts.get("links:validate", "")).startswith("node scripts/validate-links.mjs ")
    checks["stress-link-validator-non-linkinator"] = str(scripts.get("test:stress:links", "")).startswith("node scripts/validate-links.mjs ")
    checks["workspace-preflight-separated"] = scripts.get("preflight:workspace") == "node scripts/source-preflight.mjs --allow-node-modules"
    checks["frozen-preflight-strict"] = scripts.get("preflight:source") == "node scripts/source-preflight.mjs"
    checks["stress-chain-includes-lineage-and-links"] = all(token in str(scripts.get("test:stress", "")) for token in ("test:stress:generate", "test:stress:validate", "test:stress:build", "test:stress:lineage", "test:stress:links"))

    link_validator = read(root / "scripts/validate-links.mjs") if (root / "scripts/validate-links.mjs").is_file() else ""
    checks["candidate-link-gate-explicit-vacuity-failures"] = all(token in link_validator for token in ("VACUOUS_HTML_SET", "VACUOUS_REFERENCE_SET", "VACUOUS_INTERNAL_SET", "VACUOUS_DOCUMENT_SET", "VACUOUS_ASSET_SET"))
    dist_inspector = read(root / "scripts/inspect-dist.mjs") if (root / "scripts/inspect-dist.mjs").is_file() else ""
    checks["candidate-dist-wide-js-gate"] = all(token in dist_inspector for token in ("EXECUTABLE_SCRIPT_SCOPE", "EXECUTABLE_SCRIPT_COUNT", "JS_ASSET_SCOPE"))

    workflow = read(root / ".github/workflows/production-reference.yml") if (root / ".github/workflows/production-reference.yml").is_file() else ""
    checks["production-workflow-frozen-preflight-before-install"] = workflow.find("npm run preflight:source") >= 0 and workflow.find("npm run preflight:source") < workflow.find("npm ci --audit=false --fund=false")
    checks["production-workflow-canonical-gate"] = "npm run verify:all" in workflow
    checks["production-workflow-browser-install"] = "playwright install --with-deps chromium" in workflow
    checks["production-workflow-tested-dist-manifest"] = "dist-sha256.json" in workflow and "deployed-dist-sha256.json" in workflow and "diff -u dist-sha256.json deployed-dist-sha256.json" in workflow

    astro_files = [path for path in files if path.suffix == ".astro"]
    checks["native-astro-source"] = len(astro_files) >= 10
    checks["real-content-config"] = "defineCollection" in read(root / "src/content.config.ts") if (root / "src/content.config.ts").is_file() else False
    checks["dynamic-work-route"] = (root / "src/pages/work/[slug].astro").is_file()
    checks["dynamic-writing-route"] = (root / "src/pages/writing/[slug].astro").is_file()

    source_text = "\n".join(read(path) for path in files if path.suffix.lower() in {".astro", ".ts", ".js", ".mjs", ".json"} and path.stat().st_size < 1_000_000)
    checks["no-pregenerated-response-symbol"] = "pregeneratedResponse" not in source_text
    checks["no-pregenerated-html-symbol"] = "pregeneratedHtml" not in source_text

    client_scripts = sorted(path.relative_to(root).as_posix() for path in files if path.relative_to(root).as_posix().startswith("src/scripts/") and path.suffix == ".ts")
    checks["single-bounded-client-source"] = client_scripts == ["src/scripts/vce-sequence.ts"]
    astro_script_tags = []
    for path in astro_files:
        count = len(re.findall(r"<script\b", read(path), re.I))
        if count:
            astro_script_tags.append({"path": path.relative_to(root).as_posix(), "count": count})
    checks["bounded-script-tags"] = astro_script_tags == [{"path": "src/components/StructuredData.astro", "count": 1}, {"path": "src/components/VceSequence.astro", "count": 1}]
    checks["structured-data-nonexecutable"] = "application/ld+json" in read(root / "src/components/StructuredData.astro")
    index_source = read(root / "src/pages/index.astro") if (root / "src/pages/index.astro").is_file() else ""
    bearing_source = read(root / "src/components/BearingRoute.astro") if (root / "src/components/BearingRoute.astro").is_file() else ""
    media_source = read(root / "src/components/ResponsiveMedia.astro") if (root / "src/components/ResponsiveMedia.astro").is_file() else ""
    vce_source = read(root / "src/components/VceSequence.astro") if (root / "src/components/VceSequence.astro").is_file() else ""
    checks["single-route-local-executable-script"] = 'type="module"' in vce_source and "src={manifest.file}" in vce_source
    global_css = read(root / "src/styles/global.css") if (root / "src/styles/global.css").is_file() else ""
    project_css = read(root / "src/styles/project.css") if (root / "src/styles/project.css").is_file() else ""
    content_source = read(root / "src/lib/content.ts") if (root / "src/lib/content.ts").is_file() else ""
    profile_copy_source = read(root / "src/lib/profile-copy.ts") if (root / "src/lib/profile-copy.ts").is_file() else ""
    writing_record = read(root / "src/content/writing/writing-protecting-retail-investors.md") if (root / "src/content/writing/writing-protecting-retail-investors.md").is_file() else ""
    checks["history-reconciliation-document"] = (root / "docs/R7_HISTORY_RECONCILIATION.md").is_file()
    checks["history-reconciled-homepage-selection"] = all(token in index_source for token in ("getHomepageSelection", "HomepageRecordPreview", "homepageSelection.map"))
    checks["history-reconciled-generic-milestones"] = all(token in index_source for token in ("getBearingMilestones", "workRouteById", "bearingMilestones.map")) and "work-vce" not in index_source
    checks["history-reconciled-public-indexability"] = all(token in content_source for token in ("isPublicRecord", "isIndexableRecord", "data.indexability === 'index'"))
    checks["history-reconciled-profile-copy"] = all(token in profile_copy_source for token in ("stageSentence", "directionSentence", "firstPersonEducationSentence"))
    checks["history-reconciled-writing-credit"] = "structuredDataCredit: contributor" in writing_record
    checks["bearing-three-svg-nodes"] = len(re.findall(r"<circle\b", bearing_source, re.I)) == 3
    checks["compact-portrait-decorative-alt"] = '<ResponsiveMedia alt=""' in index_source and "alt={alt}" in media_source
    checks["narrow-navigation-hardening"] = ".nav-list" in global_css and "overflow-x: auto" in global_css and "flex-wrap: nowrap" in global_css
    checks["long-title-hardening"] = "overflow-wrap: anywhere" in project_css
    checks["static-vce-explanation"] = "Static sequence: all steps visible." in vce_source
    public_rationale_hits = [path.relative_to(root).as_posix() for path in files if path.suffix.lower() in {".astro", ".md", ".json"} and re.search(r"why bearing|design rationale|bearing rationale", read(path), re.I)]
    checks["no-public-design-rationale"] = not public_rationale_hits

    for name, passed in checks.items():
        if not passed:
            findings.append({"code": "FAILED_CHECK", "check": name})

    result: dict[str, object] = {
        "auditor": "r7f-independent-source-audit.py",
        "root": str(root),
        "sourceFileCount": len(files),
        "astroFileCount": len(astro_files),
        "lockPackageCount": len(lock_packages),
        "packageJsonSha256": sha256(package_path) if package_path.is_file() else None,
        "packageLockSha256": sha256(lock_path) if lock_path.is_file() else None,
        "clientScripts": client_scripts,
        "astroScriptTags": astro_script_tags,
        "nonExactDependencies": non_exact_dependencies,
        "publicRationaleHits": public_rationale_hits,
        "checks": checks,
        "findingCount": len(findings),
        "findings": findings,
        "passed": not findings,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Independent canonical Astro source and governance audit")
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = audit(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
