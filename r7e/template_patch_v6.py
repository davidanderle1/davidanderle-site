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
    reproducibility = must_replace(
        reproducibility,
        "const workRoot = path.resolve('../r7e-reproducibility-work');\nawait fsp.rm(workRoot, { recursive: true, force: true });",
        "const workRoot = path.resolve('../r7e-reproducibility-work');\nawait ensureDir(out);\nawait fsp.rm(workRoot, { recursive: true, force: true });",
        "reproducibility evidence directory",
    )
    reproducibility = must_replace(
        reproducibility,
        "for (const [label, cwd] of [['a', a], ['b', b]]) {",
        "for (const [label, cwd] of [['clean-run-1', a], ['clean-run-2', b]]) {",
        "named clean reproducibility runs",
    )
    reproducibility = must_replace(
        reproducibility,
        "const report = { schema: 'davidanderle.r7e.reproducibility.v1', commands, buildA: manifestA && { files: manifestA.files, bytes: manifestA.bytes, treeSha256: manifestA.treeSha256 }, buildB: manifestB && { files: manifestB.files, bytes: manifestB.bytes, treeSha256: manifestB.treeSha256 }, equal, differences };",
        "const cleanRun1 = manifestA && { label: 'clean-run-1', files: manifestA.files, bytes: manifestA.bytes, treeSha256: manifestA.treeSha256 };\nconst cleanRun2 = manifestB && { label: 'clean-run-2', files: manifestB.files, bytes: manifestB.bytes, treeSha256: manifestB.treeSha256 };\nconst report = { schema: 'davidanderle.r7e.reproducibility.v2', commands, cleanRun1, cleanRun2, buildA: cleanRun1, buildB: cleanRun2, equal, differences };",
        "explicit clean run report",
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

    package = files["scripts/package_r7e.py"]
    package = must_replace(
        package,
        "copy_tree(ROOT / 'dist', PACKAGE / 'BEARING_GENERATED_SITE')\ncopy_tree(ROOT / 'dist-scale', PACKAGE / 'BEARING_SCALE_SITE_500')",
        "copy_tree(ROOT / 'dist', PACKAGE / 'BEARING_GENERATED_SITE')\ncopy_tree(ROOT / 'dist', PACKAGE / 'BEARING_VERIFIED_DIST')\ncopy_tree(ROOT / 'dist-scale', PACKAGE / 'BEARING_SCALE_SITE_500')",
        "verified dist package tree",
    )
    package = must_replace(
        package,
        "'R7E_AUTHORITY_REQUIREMENT_MATRIX.md', 'R7E_INPUT_PACKAGE_DECLARATION.json'",
        "'R7E_AUTHORITY_REQUIREMENT_MATRIX.md', 'R7E_INPUT_PACKAGE_DECLARATION.json', 'R7E_FINAL_GATE.json'",
        "final gate package root",
    )
    package = must_replace(
        package,
        "This archive contains the production-reference Astro source, generated launch site, 500-record scale build and raw evidence.",
        "This archive contains the production-reference Astro source, generated launch site, independently named verified dist copy, 500-record scale build, two-clean-run reproducibility evidence and raw evidence. The producer final gate completed successfully before packaging.",
        "truthful complete package readme",
    )
    files["scripts/package_r7e.py"] = package

    files["scripts/verify-final-gate.mjs"] = """import fsp from 'node:fs/promises';
import { exists, readJson, treeManifest, writeJson } from './lib.mjs';

const errors = [];
const index = await readJson('R7E_EVIDENCE_INDEX.json');
const unacceptable = index.gates.filter((gate) => ['OBSERVED_FAILURE', 'NOT_VERIFIED'].includes(gate.producerObservation));
for (const gate of unacceptable) errors.push(`${gate.id}: ${gate.producerObservation}`);

for (const required of ['package-lock.json', 'dist', 'dist-scale', 'evidence/reproducibility/report.json', 'evidence/reports/scale-verification.json', 'evidence/reports/dist-verification.json', 'evidence/reports/official-source-verification.json']) {
  if (!(await exists(required))) errors.push(`missing required artifact: ${required}`);
}

let reproducibility = null;
if (await exists('evidence/reproducibility/report.json')) {
  reproducibility = await readJson('evidence/reproducibility/report.json');
  if (reproducibility.equal !== true) errors.push('reproducibility.equal is not true');
  if (!reproducibility.cleanRun1 || !reproducibility.cleanRun2) errors.push('clean-run-1/clean-run-2 summaries missing');
  if (!Array.isArray(reproducibility.commands) || reproducibility.commands.length !== 4 || reproducibility.commands.some((row) => row.exitCode !== 0)) errors.push('clean-run command set is not four native successes');
  if (reproducibility.cleanRun1?.treeSha256 !== reproducibility.cleanRun2?.treeSha256) errors.push('clean-run output tree hashes differ');
}

let scale = null;
if (await exists('evidence/reports/scale-verification.json')) {
  scale = await readJson('evidence/reports/scale-verification.json');
  if (scale.generatedFixtureCount !== 500) errors.push(`scale fixture count ${scale.generatedFixtureCount}, expected 500`);
  if (scale.generatedDetailPageCount !== 500) errors.push(`scale detail page count ${scale.generatedDetailPageCount}, expected 500`);
  if (Array.isArray(scale.errors) && scale.errors.length) errors.push(`scale verification errors: ${scale.errors.join('; ')}`);
}

let official = null;
if (await exists('evidence/reports/official-source-verification.json')) {
  official = await readJson('evidence/reports/official-source-verification.json');
  if (Array.isArray(official.failures) && official.failures.length) errors.push(`official source failures: ${official.failures.join('; ')}`);
}

let distVerification = null;
if (await exists('evidence/reports/dist-verification.json')) {
  distVerification = await readJson('evidence/reports/dist-verification.json');
  if (Array.isArray(distVerification.errors) && distVerification.errors.length) errors.push(`dist verification errors: ${distVerification.errors.join('; ')}`);
}

const dist = await treeManifest('dist');
const distScale = await treeManifest('dist-scale');
const report = {
  schema: 'davidanderle.r7e.final-producer-gate.v1',
  generatedAtUtc: new Date().toISOString(),
  result: errors.length ? 'FAIL' : 'PASS',
  errors,
  evidenceGateCount: index.gates.length,
  unacceptableEvidenceGates: unacceptable.map((gate) => ({ id: gate.id, producerObservation: gate.producerObservation })),
  packageLockPresent: await exists('package-lock.json'),
  canonicalDist: { files: dist.files, bytes: dist.bytes, treeSha256: dist.treeSha256 },
  scaleDist: { files: distScale.files, bytes: distScale.bytes, treeSha256: distScale.treeSha256 },
  reproducibility,
  scale,
  officialSources: official,
  distVerification,
  authorityBoundary: 'This is the R7E producer completion gate. Independent R7F verification remains required for release certification.'
};
await writeJson('R7E_FINAL_GATE.json', report);
await writeJson('evidence/reports/R7E_FINAL_GATE.json', report);
if (errors.length) {
  console.error(JSON.stringify(report, null, 2));
  process.exit(2);
}
console.log(JSON.stringify(report, null, 2));
"""

    return files
