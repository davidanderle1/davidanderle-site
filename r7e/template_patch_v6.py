from __future__ import annotations

import re

from template_patch_v4 import apply_v4_patches
from template_patch_v3 import must_replace


def one_sub(value: str, pattern: str, replacement: str, label: str) -> str:
    updated, count = re.subn(pattern, replacement, value, count=1, flags=re.MULTILINE | re.DOTALL)
    if count != 1:
        raise RuntimeError(f"{label}: regex replacements {count}, expected 1")
    return updated


def apply_v6_patches(files: dict[str, str]) -> dict[str, str]:
    files = apply_v4_patches(files)

    comparison = files["src/components/ComparisonExplorer.astro"]
    comparison = must_replace(
        comparison,
        "const buttons = Array.from(this.querySelectorAll('button[data-view]'));",
        "const buttons = Array.from(this.querySelectorAll<HTMLButtonElement>('button[data-view]'));",
        "typed comparison buttons",
    )
    comparison = must_replace(
        comparison,
        "const cards = Array.from(this.querySelectorAll('[data-category]'));",
        "const cards = Array.from(this.querySelectorAll<HTMLElement>('[data-category]'));",
        "typed comparison cards",
    )
    files["src/components/ComparisonExplorer.astro"] = comparison

    selector = files["scripts/select-portrait-source.mjs"]
    selector = one_sub(
        selector,
        r"candidates\.sort\(\(a, b\) => b\.score - a\.score \|\| a\.bytes - b\.bytes \|\| a\.relativePath\.localeCompare\(b\.relativePath\)\);\n\s*for \(const existing of await fsp\.readdir\(destination\)\) if \(existing\.startsWith\('approved-source\.'\)\) await fsp\.rm\(path\.join\(destination, existing\), \{ force: true \}\);\n\n\s*if \(!candidates\.length\) \{.*?\n\s*const selected = candidates\[0\];",
        """candidates.sort((a, b) => b.score - a.score || a.bytes - b.bytes || a.relativePath.localeCompare(b.relativePath));
for (const existing of await fsp.readdir(destination)) if (existing.startsWith('approved-source.')) await fsp.rm(path.join(destination, existing), { force: true });

const approvedHashes = new Set((process.env.R7E_APPROVED_PORTRAIT_SHA256 || '').split(',').map((value) => value.trim().toLowerCase()).filter(Boolean));
const approvedPath = process.env.R7E_APPROVED_PORTRAIT_PATH ? path.resolve(process.env.R7E_APPROVED_PORTRAIT_PATH) : null;
const selected = candidates.find((candidate) => approvedHashes.has(candidate.sha256.toLowerCase()) || (approvedPath && path.resolve(candidate.file) === approvedPath));
if (!selected) {
  const report = {
    schema: 'davidanderle.r7e.portrait-selection.v2',
    searchRoot,
    result: candidates.length ? 'DIMENSION_CANDIDATES_FOUND_BUT_NOT_R5_AUTHORIZED' : 'NO_320_X_320_CANDIDATE',
    compactPhotoEnabled: false,
    authorizationInputs: { approvedHashes: [...approvedHashes], approvedPath },
    candidateCount: candidates.length,
    candidates,
    r7fAuthorityHashDisposition: 'NOT_VERIFIED_PENDING_R5_AUTHORIZATION'
  };
  await writeJson(path.join(destination, 'provenance.json'), report);
  await writeJson(evidencePath, report);
  console.log(JSON.stringify(report, null, 2));
  process.exit(0);
}
""",
        "portrait authority selection",
    )
    selector = must_replace(
        selector,
        "schema: 'davidanderle.r7e.portrait-selection.v1',",
        "schema: 'davidanderle.r7e.portrait-selection.v2',",
        "authorized portrait schema",
    )
    selector = must_replace(
        selector,
        "selectionBasis: 'Exact 320 x 320 dimensions plus deterministic filename scoring in the incumbent public repository.',",
        "selectionBasis: 'Exact 320 x 320 dimensions plus explicit R5 source-path or SHA-256 authorization.',",
        "authorized portrait basis",
    )
    selector = must_replace(
        selector,
        "r7fAuthorityHashDisposition: 'PENDING_INDEPENDENT_R5_HASH_COMPARISON'",
        "r7fAuthorityHashDisposition: 'AUTHORIZED_INPUT_RECORDED_PENDING_INDEPENDENT_REVIEW'",
        "authorized portrait disposition",
    )
    files["scripts/select-portrait-source.mjs"] = selector

    reproducibility = files["scripts/verify-reproducibility.mjs"]
    reproducibility = must_replace(
        reproducibility,
        "const workRoot = path.join(out, 'work');",
        "const workRoot = path.resolve('../r7e-reproducibility-work');",
        "external reproducibility workspace",
    )
    files["scripts/verify-reproducibility.mjs"] = reproducibility

    finalizer = files["scripts/finalize-evidence.mjs"]
    finalizer = must_replace(
        finalizer,
        "else if (observations.some((x) => x.observation === 'EXPECTED_REJECTION_OBSERVED')) producerObservation = 'MIXED_NATIVE_SUCCESS_AND_EXPECTED_REJECTION';",
        """else if (observations.some((x) => x.observation === 'EXPECTED_REJECTION_OBSERVED')) producerObservation = 'MIXED_NATIVE_SUCCESS_AND_EXPECTED_REJECTION';
  if (claim.id === 'R7E-G06-PHOTOGRAPHY-PIPELINE') {
    const reportPath = 'evidence/reports/image-processing.json';
    if (!(await exists(reportPath))) producerObservation = 'NOT_VERIFIED';
    else {
      const imageReport = JSON.parse(await fsp.readFile(reportPath, 'utf8'));
      if (imageReport.result !== 'CROP_WITHOUT_ENLARGEMENT') producerObservation = 'NOT_VERIFIED';
    }
  }""",
        "semantic portrait gate",
    )
    files["scripts/finalize-evidence.mjs"] = finalizer

    return files
