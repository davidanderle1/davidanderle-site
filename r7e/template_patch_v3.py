from __future__ import annotations

import re


def must_replace(value: str, old: str, new: str, label: str) -> str:
    count = value.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: token count {count}, expected 1")
    return value.replace(old, new, 1)


def must_sub(value: str, pattern: str, replacement: str, label: str, count: int = 1) -> str:
    updated, observed = re.subn(pattern, replacement, value, count=count, flags=re.MULTILINE)
    if observed != count:
        raise RuntimeError(f"{label}: regex replacements {observed}, expected {count}")
    return updated


def apply_v3_patches(files: dict[str, str]) -> dict[str, str]:
    config = files["src/content.config.ts"]
    config = must_sub(config, r"^\s*id: z\.string\(\),\n(?=\s*organization: z\.string\(\),)", "", "experience file-loader ID")
    config = must_sub(config, r"^\s*id: z\.string\(\),\n(?=\s*institution: z\.string\(\),)", "", "education file-loader ID")
    files["src/content.config.ts"] = config

    validation = files["scripts/validate-content.mjs"]
    validation = must_replace(
        validation,
        "const forbiddenInflation = [/world[- ]class/i, /guaranteed/i, /production trading platform/i, /published paper/i];",
        "const forbiddenInflation = [/world[- ]class/i, /guaranteed/i, /published paper/i];",
        "inflation disclaimer"
    )
    validation = must_replace(
        validation,
        "await writeJson('evidence/reports/content-validation.json', report);",
        "const modePath = process.env.R7E_SCALE === '1' ? 'evidence/reports/content-validation-scale.json' : 'evidence/reports/content-validation-canonical.json';\nawait writeJson(modePath, report);\nawait writeJson('evidence/reports/content-validation.json', report);",
        "separate validation reports"
    )
    files["scripts/validate-content.mjs"] = validation

    finalize = files["scripts/finalize-evidence.mjs"]
    finalize = must_replace(
        finalize,
        "rows.push({ path: rel, exists: await exists(target), sha256: await exists(target) ? await sha256File(target) : null, bytes: await exists(target) ? (await fsp.stat(target)).size : null });",
        "const present = await exists(target);\nif (!present) { rows.push({ path: rel, exists: false, sha256: null, bytes: null }); continue; }\nconst stat = await fsp.stat(target);\nif (stat.isDirectory()) {\n  const manifest = await treeManifest(target);\n  rows.push({ path: rel, exists: true, kind: 'directory', files: manifest.files, bytes: manifest.bytes, treeSha256: manifest.treeSha256 });\n} else {\n  rows.push({ path: rel, exists: true, kind: 'file', sha256: await sha256File(target), bytes: stat.size });\n}",
        "directory-aware raw evidence hashing"
    )
    old_manifest = """const manifests = {};
for (const [name, target] of [['source', '.'], ['dist', 'dist'], ['distScale', 'dist-scale'], ['evidence', 'evidence']]) {
  if (!(await exists(target))) { manifests[name] = null; continue; }
  const manifest = await treeManifest(target);
  manifests[name] = { files: manifest.files, bytes: manifest.bytes, treeSha256: manifest.treeSha256 };
}"""
    new_manifest = """const manifests = {};
const generatedSourceManifest = 'evidence/reports/source-generation-manifest.json';
if (await exists(generatedSourceManifest)) {
  const sourceManifest = JSON.parse(await fsp.readFile(generatedSourceManifest, 'utf8'));
  manifests.sourceBeforeInstall = { files: sourceManifest.files, bytes: sourceManifest.bytes, treeSha256: sourceManifest.treeSha256 };
} else manifests.sourceBeforeInstall = null;
for (const [name, target] of [['dist', 'dist'], ['distScale', 'dist-scale'], ['evidence', 'evidence']]) {
  if (!(await exists(target))) { manifests[name] = null; continue; }
  const manifest = await treeManifest(target);
  manifests[name] = { files: manifest.files, bytes: manifest.bytes, treeSha256: manifest.treeSha256 };
}"""
    finalize = must_replace(finalize, old_manifest, new_manifest, "bounded tree summary")
    finalize = must_replace(finalize, "reports: ['src/content.config.ts', 'evidence/reports/content-validation.json']", "reports: ['src/content.config.ts', 'evidence/reports/content-validation-canonical.json']", "typed content report")
    finalize = must_replace(finalize, "reports: ['evidence/reports/content-validation.json']", "reports: ['evidence/reports/content-validation-canonical.json']", "cross-record report")
    finalize = must_replace(finalize, "reports: ['evidence/scale/generated-records-manifest.json', 'evidence/reports/scale-verification.json']", "reports: ['evidence/scale/generated-records-manifest.json', 'evidence/reports/content-validation-scale.json', 'evidence/reports/scale-verification.json']", "scale report")
    files["scripts/finalize-evidence.mjs"] = finalize

    css = files["src/styles/global.css"]
    css = must_replace(css, ".evidence-card.material-graphite .eyebrow, .material-graphite .eyebrow { color: #ef976e; }", ".evidence-card.material-graphite .eyebrow, .material-graphite .eyebrow { color: #fffdf8; }", "graphite contrast")
    css = must_replace(css, ".evidence-card.material-oxide .eyebrow, .material-oxide .eyebrow { color: #ffe0cf; }", ".evidence-card.material-oxide .eyebrow, .material-oxide .eyebrow { color: #fffdf8; }", "oxide contrast")
    files["src/styles/global.css"] = css

    package = files["scripts/package_r7e.py"]
    package = must_replace(
        package,
        "shutil.copy2(command_dir / '320-package.json', PACKAGE / 'R7E_RAW_EVIDENCE/commands/320-package.json')",
        "(PACKAGE / 'R7E_RAW_EVIDENCE/commands').mkdir(parents=True, exist_ok=True)\n(PACKAGE / 'R7E_RAW_EVIDENCE/raw').mkdir(parents=True, exist_ok=True)\nshutil.copy2(command_dir / '320-package.json', PACKAGE / 'R7E_RAW_EVIDENCE/commands/320-package.json')",
        "package evidence directories"
    )
    files["scripts/package_r7e.py"] = package
    return files
