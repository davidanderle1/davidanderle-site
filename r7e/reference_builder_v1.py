#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from template_site import site_files
from template_verification import verification_files
from template_evidence import evidence_files

UTC = dt.timezone.utc
NODE_VERSION = "24.20.0"
NPM_VERSION = "11.19.0"

OFFICIAL_SOURCES: list[dict[str, Any]] = [
    {"id": "astro-static-output", "topic": "Astro static output", "publisher": "Astro", "url": "https://docs.astro.build/en/reference/configuration-reference/#output", "markers": ["static", "output"]},
    {"id": "astro-content-collections", "topic": "Astro content collections and schema validation", "publisher": "Astro", "url": "https://docs.astro.build/en/guides/content-collections/", "markers": ["defineCollection", "schema"]},
    {"id": "astro-routing", "topic": "Astro routing and static paths", "publisher": "Astro", "url": "https://docs.astro.build/en/guides/routing/", "markers": ["getStaticPaths", "routing"]},
    {"id": "astro-client-scripts", "topic": "Astro client scripts and Web Components", "publisher": "Astro", "url": "https://docs.astro.build/en/guides/client-side-scripts/", "markers": ["Web Components", "script"]},
    {"id": "astro-images", "topic": "Astro local image handling", "publisher": "Astro", "url": "https://docs.astro.build/en/guides/images/", "markers": ["local images", "image"]},
    {"id": "astro-node-support", "topic": "Astro installation and supported Node versions", "publisher": "Astro", "url": "https://docs.astro.build/en/install-and-setup/", "markers": ["Node.js", "supported"]},
    {"id": "sharp-install", "topic": "Sharp installation and runtime behavior", "publisher": "Sharp", "url": "https://sharp.pixelplumbing.com/install", "markers": ["Node-API", "install"]},
    {"id": "sharp-resize", "topic": "Sharp resize and enlargement controls", "publisher": "Sharp", "url": "https://sharp.pixelplumbing.com/api-resize", "markers": ["withoutEnlargement", "resize"]},
    {"id": "playwright-intro", "topic": "Playwright installation and browser testing", "publisher": "Microsoft Playwright", "url": "https://playwright.dev/docs/intro", "markers": ["install", "browser"]},
    {"id": "playwright-webserver", "topic": "Playwright test web server", "publisher": "Microsoft Playwright", "url": "https://playwright.dev/docs/test-webserver", "markers": ["webServer", "url"]},
    {"id": "axe-core", "topic": "axe-core accessibility engine", "publisher": "Deque Systems", "url": "https://github.com/dequelabs/axe-core", "markers": ["accessibility", "axe-core"]},
    {"id": "axe-playwright", "topic": "axe-core Playwright integration", "publisher": "Deque Systems", "url": "https://github.com/dequelabs/axe-core-npm/tree/develop/packages/playwright", "markers": ["playwright", "AxeBuilder"]},
    {"id": "lighthouse", "topic": "Lighthouse measurement", "publisher": "Google Chrome", "url": "https://developer.chrome.com/docs/lighthouse/overview", "markers": ["Lighthouse", "performance"]},
    {"id": "cloudflare-static-assets", "topic": "Cloudflare Workers Static Assets", "publisher": "Cloudflare", "url": "https://developers.cloudflare.com/workers/static-assets/", "markers": ["Static Assets", "assets"]},
    {"id": "cloudflare-static-get-started", "topic": "Workers Static Assets assets-only deployment", "publisher": "Cloudflare", "url": "https://developers.cloudflare.com/workers/static-assets/get-started/", "markers": ["assets", "wrangler"]},
    {"id": "cloudflare-static-configuration", "topic": "Static Assets configuration and custom 404", "publisher": "Cloudflare", "url": "https://developers.cloudflare.com/workers/static-assets/configuration/", "markers": ["not_found_handling", "404-page"]},
    {"id": "cloudflare-static-headers", "topic": "Static Assets _headers", "publisher": "Cloudflare", "url": "https://developers.cloudflare.com/workers/static-assets/headers/", "markers": ["_headers", "headers"]},
    {"id": "cloudflare-static-redirects", "topic": "Static Assets _redirects", "publisher": "Cloudflare", "url": "https://developers.cloudflare.com/workers/static-assets/redirects/", "markers": ["_redirects", "redirects"]},
    {"id": "cloudflare-static-routing", "topic": "Static Assets routing and HTML handling", "publisher": "Cloudflare", "url": "https://developers.cloudflare.com/workers/static-assets/routing/", "markers": ["html_handling", "routing"]},
    {"id": "wrangler-deploy", "topic": "Wrangler deploy dry run", "publisher": "Cloudflare", "url": "https://developers.cloudflare.com/workers/wrangler/commands/#deploy", "markers": ["dry-run", "deploy"]}
]

# These are immutable production-reference pins, not moving dist-tags.  The
# registry is consulted only to verify that the exact requested bytes/version
# coordinate still exists.  TypeScript 6.0.3 is intentionally pinned because
# @astrojs/check 0.9.10 declares support for TypeScript ^5 || ^6, not 7.x.
EXACT_PACKAGE_VERSIONS: dict[str, str] = {
    "astro": "7.2.9",
    "@astrojs/check": "0.9.10",
    "typescript": "6.0.3",
    "sharp": "0.35.4",
    "@playwright/test": "1.62.1",
    "@axe-core/playwright": "4.13.0",
    "lighthouse": "13.4.1",
    "wrangler": "4.127.1",
    "gray-matter": "4.0.3",
    "parse5": "8.0.1",
}
PACKAGES = list(EXACT_PACKAGE_VERSIONS)


def now() -> str:
    return dt.datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8", newline="\n")


def retrieve_official_sources(output: Path) -> dict[str, Any]:
    retrieval_timestamp = now()
    evidence_dir = output / "evidence" / "official-sources"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for source in OFFICIAL_SOURCES:
        started = now()
        status = 0
        final_url = source["url"]
        body = b""
        error = None
        headers: dict[str, str] = {}
        try:
            request = urllib.request.Request(
                source["url"],
                headers={
                    "User-Agent": "David-Anderle-R7E-Evidence-Producer/1.0 (+https://davidanderle.com)",
                    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"
                }
            )
            with urllib.request.urlopen(request, timeout=45) as response:
                status = int(getattr(response, "status", response.getcode()))
                final_url = response.geturl()
                headers = {key.lower(): value for key, value in response.headers.items()}
                body = response.read(4 * 1024 * 1024)
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            final_url = exc.geturl()
            try:
                body = exc.read(1024 * 1024)
            except Exception:
                body = b""
            error = f"HTTPError: {exc}"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        text = body.decode("utf-8", errors="replace")
        marker_hits = sum(1 for marker in source["markers"] if marker.casefold() in text.casefold())
        compressed = gzip.compress(body, compresslevel=9, mtime=0)
        snapshot_path = evidence_dir / f"{source['id']}.html.gz"
        write(snapshot_path, compressed)
        rows.append({
            "id": source["id"],
            "topic": source["topic"],
            "publisher": source["publisher"],
            "requestedUrl": source["url"],
            "finalUrl": final_url,
            "retrievedAtUtc": started,
            "completedAtUtc": now(),
            "httpStatus": status,
            "contentType": headers.get("content-type"),
            "responseBytes": len(body),
            "sha256": sha256_bytes(body) if body else None,
            "compressedSnapshot": f"evidence/official-sources/{snapshot_path.name}",
            "compressedSha256": sha256_bytes(compressed),
            "expectedMarkers": source["markers"],
            "markerHits": marker_hits,
            "error": error
        })
    index = {
        "schema": "davidanderle.r7e.official-source-log.v1",
        "retrievalTimestampUtc": retrieval_timestamp,
        "policy": "Primary official documentation only. Raw responses are preserved as deterministic gzip snapshots; no source is treated as verified when retrieval or semantic marker observation failed.",
        "sources": rows
    }
    write(evidence_dir / "index.json", json.dumps(index, indent=2) + "\n")
    return index


def resolve_versions(output: Path) -> tuple[dict[str, str], dict[str, Any]]:
    evidence_dir = output / "evidence" / "toolchain-resolution"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    versions: dict[str, str] = {}
    for index, package in enumerate(PACKAGES, start=1):
        required = EXACT_PACKAGE_VERSIONS[package]
        coordinate = f"{package}@{required}"
        command = ["npm", "view", coordinate, "version", "--json"]
        started = now()
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        stdout_path = evidence_dir / f"{index:02d}-{package.replace('/', '__').replace('@', '')}.stdout.log"
        stderr_path = evidence_dir / f"{index:02d}-{package.replace('/', '__').replace('@', '')}.stderr.log"
        write(stdout_path, result.stdout)
        write(stderr_path, result.stderr)
        value = None
        if result.returncode == 0:
            try:
                parsed = json.loads(result.stdout)
                value = parsed[-1] if isinstance(parsed, list) else parsed
            except Exception:
                value = result.stdout.strip().strip('"')
        if value != required:
            raise RuntimeError(f"Pinned version verification failed for {coordinate}: observed {value!r}; see {stderr_path}")
        versions[package] = required
        rows.append({
            "package": package,
            "requiredVersion": required,
            "coordinate": coordinate,
            "command": command,
            "workingDirectory": str(Path.cwd()),
            "startTimestampUtc": started,
            "endTimestampUtc": now(),
            "exitCode": result.returncode,
            "stdoutPath": str(stdout_path.relative_to(output)),
            "stderrPath": str(stderr_path.relative_to(output)),
            "stdoutSha256": sha256_file(stdout_path),
            "stderrSha256": sha256_file(stderr_path),
            "registryVerifiedVersion": value
        })
    report = {
        "schema": "davidanderle.r7e.toolchain-resolution.v2",
        "verifiedAtUtc": now(),
        "node": {"required": NODE_VERSION, "observed": subprocess.run(["node", "--version"], stdout=subprocess.PIPE, text=True, check=False).stdout.strip()},
        "npm": {"required": NPM_VERSION, "observed": subprocess.run(["npm", "--version"], stdout=subprocess.PIPE, text=True, check=False).stdout.strip()},
        "registry": subprocess.run(["npm", "config", "get", "registry"], stdout=subprocess.PIPE, text=True, check=False).stdout.strip(),
        "packages": rows,
        "exactVersions": versions,
        "dependencyPolicy": "Immutable exact production-reference pins are declared in reference_builder_v1.py. npm registry lookup verifies each exact coordinate; no moving range, latest tag or runtime-selected version is written to package.json."
    }
    write(output / "R7E_TOOLCHAIN_RESOLUTION.json", json.dumps(report, indent=2) + "\n")
    return versions, report


def official_log_markdown(index: dict[str, Any]) -> str:
    lines = [
        "# R7E official source log",
        "",
        f"Retrieval batch: `{index['retrievalTimestampUtc']}`",
        "",
        "Only primary official documentation was requested. HTTP status, final URL, response hash and marker observations are preserved. A failed retrieval is not treated as verification.",
        "",
        "| Topic | Publisher | Requested source | Retrieved UTC | HTTP | Marker hits | Raw snapshot | SHA-256 |",
        "|---|---|---|---|---:|---:|---|---|"
    ]
    for row in index["sources"]:
        requested = row["requestedUrl"].replace("|", "%7C")
        digest = row["sha256"] or "NOT RETRIEVED"
        lines.append(f"| {row['topic']} | {row['publisher']} | {requested} | {row['retrievedAtUtc']} | {row['httpStatus']} | {row['markerHits']} | `{row['compressedSnapshot']}` | `{digest}` |")
    lines += [
        "",
        "## Implementation decisions tied to the source set",
        "",
        "Astro is configured with explicit static output. Content is loaded through typed collections and build-time static paths. Client code is limited to one route-local custom element. Image derivatives are generated locally with Sharp and reject enlargement. Browser, accessibility and Lighthouse evidence is generated with native tools. Cloudflare is configured with an `assets` directory and no Worker `main` script; `_headers`, `_redirects`, 404-page handling and `wrangler deploy --dry-run` are tested separately.",
        "",
        "These statements describe the implemented interpretation. R7F must compare them against the preserved official snapshots and current upstream documentation."
    ]
    return "\n".join(lines) + "\n"


def source_manifest(output: Path) -> dict[str, Any]:
    rows = []
    for file in sorted(p for p in output.rglob("*") if p.is_file()):
        rel = file.relative_to(output).as_posix()
        rows.append({"path": rel, "bytes": file.stat().st_size, "sha256": sha256_file(file)})
    canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return {"files": len(rows), "bytes": sum(row["bytes"] for row in rows), "treeSha256": hashlib.sha256(canonical).hexdigest(), "entries": rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    workspace = Path(args.workspace).resolve()
    shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True, exist_ok=True)

    official_index = retrieve_official_sources(output)
    versions, _ = resolve_versions(output)

    files: dict[str, str] = {}
    for source in [site_files(versions, NODE_VERSION, NPM_VERSION), verification_files(), evidence_files(NODE_VERSION, NPM_VERSION)]:
        overlap = set(files).intersection(source)
        if overlap:
            raise RuntimeError(f"Template path collision: {sorted(overlap)}")
        files.update(source)

    for relative, content in files.items():
        write(output / relative, content)

    runner_source = workspace / "r7e" / "run_command.py"
    if not runner_source.exists():
        raise RuntimeError(f"Raw command evidence recorder missing: {runner_source}")
    shutil.copy2(runner_source, output / "scripts" / "run_evidence.py")
    os.chmod(output / "scripts" / "run_evidence.py", 0o755)
    os.chmod(output / "scripts" / "package_r7e.py", 0o755)

    write(output / "R7E_OFFICIAL_SOURCE_LOG.md", official_log_markdown(official_index))
    generation = {
        "schema": "davidanderle.r7e.source-generation.v1",
        "generatedAtUtc": now(),
        "builder": "r7e/reference_builder_v1.py",
        "python": sys.version,
        "workspace": str(workspace),
        "output": str(output),
        "templateFiles": len(files) + 1,
        "officialSourcesRetrievedBeforeEmission": True,
        "exactPackageVersionsResolvedBeforePackageJson": True
    }
    write(output / "evidence" / "reports" / "source-generation.json", json.dumps(generation, indent=2) + "\n")
    manifest = source_manifest(output)
    write(output / "evidence" / "reports" / "source-generation-manifest.json", json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"output": str(output), "files": manifest["files"], "bytes": manifest["bytes"], "treeSha256": manifest["treeSha256"], "versions": versions}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
