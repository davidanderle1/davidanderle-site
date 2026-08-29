#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import reference_builder_v1 as base
from template_site import site_files
from template_verification import verification_files
from template_evidence import evidence_files
from template_patch_v3 import apply_v3_patches


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    workspace = Path(args.workspace).resolve()
    shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True, exist_ok=True)

    official_index = base.retrieve_official_sources(output)
    versions, _ = base.resolve_versions(output)

    files: dict[str, str] = {}
    for source in [site_files(versions, base.NODE_VERSION, base.NPM_VERSION), verification_files(), evidence_files(base.NODE_VERSION, base.NPM_VERSION)]:
        overlap = set(files).intersection(source)
        if overlap:
            raise RuntimeError(f"Template path collision: {sorted(overlap)}")
        files.update(source)
    files = apply_v3_patches(files)

    for relative, content in files.items():
        base.write(output / relative, content)

    runner_source = workspace / "r7e" / "run_command.py"
    if not runner_source.exists():
        raise RuntimeError(f"Raw command evidence recorder missing: {runner_source}")
    shutil.copy2(runner_source, output / "scripts" / "run_evidence.py")
    os.chmod(output / "scripts" / "run_evidence.py", 0o755)
    os.chmod(output / "scripts" / "package_r7e.py", 0o755)

    base.write(output / "R7E_OFFICIAL_SOURCE_LOG.md", base.official_log_markdown(official_index))
    generation = {
        "schema": "davidanderle.r7e.source-generation.v3",
        "generatedAtUtc": base.now(),
        "builder": "r7e/reference_builder_v3.py",
        "baseBuilder": "r7e/reference_builder_v1.py",
        "patchSet": "r7e/template_patch_v3.py",
        "python": sys.version,
        "workspace": str(workspace),
        "output": str(output),
        "templateFiles": len(files) + 1,
        "officialSourcesRetrievedBeforeEmission": True,
        "exactPackageVersionsResolvedBeforePackageJson": True
    }
    base.write(output / "evidence" / "reports" / "source-generation.json", json.dumps(generation, indent=2) + "\n")
    manifest = base.source_manifest(output)
    base.write(output / "evidence" / "reports" / "source-generation-manifest.json", json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"output": str(output), "files": manifest["files"], "bytes": manifest["bytes"], "treeSha256": manifest["treeSha256"], "versions": versions, "patchSet": "v3"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
