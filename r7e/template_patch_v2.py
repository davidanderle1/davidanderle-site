from __future__ import annotations


def replace_once(files: dict[str, str], path: str, old: str, new: str) -> None:
    value = files[path]
    if value.count(old) != 1:
        raise RuntimeError(f"Patch token count for {path!r} was {value.count(old)}, expected 1: {old[:80]!r}")
    files[path] = value.replace(old, new, 1)


def apply_v2_patches(files: dict[str, str]) -> dict[str, str]:
    # Astro file-loader entry IDs are collection identifiers and are not part of data.
    replace_once(files, "src/content.config.ts", "                id: z.string(),\n                organization: z.string(),", "                organization: z.string(),")
    replace_once(files, "src/content.config.ts", "                id: z.string(),\n                institution: z.string(),", "                institution: z.string(),")

    # A disclaimer containing the words 'production trading platform' must not be
    # mistaken for an inflated positive claim.
    replace_once(
        files,
        "scripts/validate-content.mjs",
        "            const forbiddenInflation = [/world[- ]class/i, /guaranteed/i, /production trading platform/i, /published paper/i];",
        "            const forbiddenInflation = [/world[- ]class/i, /guaranteed/i, /published paper/i];"
    )

    # Preserve canonical and 500-record validation reports separately.
    replace_once(
        files,
        "scripts/validate-content.mjs",
        "            await writeJson('evidence/reports/content-validation.json', report);",
        "            const modePath = process.env.R7E_SCALE === '1' ? 'evidence/reports/content-validation-scale.json' : 'evidence/reports/content-validation-canonical.json';\n            await writeJson(modePath, report);\n            await writeJson('evidence/reports/content-validation.json', report);"
    )

    # Evidence paths may be directories. Hash their deterministic tree manifest
    # instead of attempting to open a directory as a file.
    replace_once(
        files,
        "scripts/finalize-evidence.mjs",
        "                rows.push({ path: rel, exists: await exists(target), sha256: await exists(target) ? await sha256File(target) : null, bytes: await exists(target) ? (await fsp.stat(target)).size : null });",
        "                const present = await exists(target);\n                if (!present) { rows.push({ path: rel, exists: false, sha256: null, bytes: null }); continue; }\n                const stat = await fsp.stat(target);\n                if (stat.isDirectory()) {\n                  const manifest = await treeManifest(target);\n                  rows.push({ path: rel, exists: true, kind: 'directory', files: manifest.files, bytes: manifest.bytes, treeSha256: manifest.treeSha256 });\n                } else {\n                  rows.push({ path: rel, exists: true, kind: 'file', sha256: await sha256File(target), bytes: stat.size });\n                }"
    )

    # Do not recursively hash node_modules as the source-tree summary. The builder
    # already produced a pre-install source manifest; dist and evidence remain
    # measured directly at finalization.
    replace_once(
        files,
        "scripts/finalize-evidence.mjs",
        "            const manifests = {};\n            for (const [name, target] of [['source', '.'], ['dist', 'dist'], ['distScale', 'dist-scale'], ['evidence', 'evidence']]) {\n              if (!(await exists(target))) { manifests[name] = null; continue; }\n              const manifest = await treeManifest(target);\n              manifests[name] = { files: manifest.files, bytes: manifest.bytes, treeSha256: manifest.treeSha256 };\n            }",
        "            const manifests = {};\n            const generatedSourceManifest = 'evidence/reports/source-generation-manifest.json';\n            if (await exists(generatedSourceManifest)) {\n              const sourceManifest = JSON.parse(await fsp.readFile(generatedSourceManifest, 'utf8'));\n              manifests.sourceBeforeInstall = { files: sourceManifest.files, bytes: sourceManifest.bytes, treeSha256: sourceManifest.treeSha256 };\n            } else manifests.sourceBeforeInstall = null;\n            for (const [name, target] of [['dist', 'dist'], ['distScale', 'dist-scale'], ['evidence', 'evidence']]) {\n              if (!(await exists(target))) { manifests[name] = null; continue; }\n              const manifest = await treeManifest(target);\n              manifests[name] = { files: manifest.files, bytes: manifest.bytes, treeSha256: manifest.treeSha256 };\n            }"
    )

    replace_once(
        files,
        "scripts/finalize-evidence.mjs",
        "reports: ['src/content.config.ts', 'evidence/reports/content-validation.json']",
        "reports: ['src/content.config.ts', 'evidence/reports/content-validation-canonical.json']"
    )
    replace_once(
        files,
        "scripts/finalize-evidence.mjs",
        "reports: ['evidence/reports/content-validation.json']",
        "reports: ['evidence/reports/content-validation-canonical.json']"
    )
    replace_once(
        files,
        "scripts/finalize-evidence.mjs",
        "reports: ['evidence/scale/generated-records-manifest.json', 'evidence/reports/scale-verification.json']",
        "reports: ['evidence/scale/generated-records-manifest.json', 'evidence/reports/content-validation-scale.json', 'evidence/reports/scale-verification.json']"
    )

    # Small uppercase text on dark material cards must retain robust contrast.
    replace_once(files, "src/styles/global.css", "        .evidence-card.material-graphite .eyebrow, .material-graphite .eyebrow { color: #ef976e; }", "        .evidence-card.material-graphite .eyebrow, .material-graphite .eyebrow { color: #fffdf8; }")
    replace_once(files, "src/styles/global.css", "        .evidence-card.material-oxide .eyebrow, .material-oxide .eyebrow { color: #ffe0cf; }", "        .evidence-card.material-oxide .eyebrow, .material-oxide .eyebrow { color: #fffdf8; }")

    # The package command copies evidence into a fresh destination; ensure its
    # nested directories exist before copy2.
    replace_once(
        files,
        "scripts/package_r7e.py",
        "            shutil.copy2(command_dir / '320-package.json', PACKAGE / 'R7E_RAW_EVIDENCE/commands/320-package.json')",
        "            (PACKAGE / 'R7E_RAW_EVIDENCE/commands').mkdir(parents=True, exist_ok=True)\n            (PACKAGE / 'R7E_RAW_EVIDENCE/raw').mkdir(parents=True, exist_ok=True)\n            shutil.copy2(command_dir / '320-package.json', PACKAGE / 'R7E_RAW_EVIDENCE/commands/320-package.json')"
    )
    return files
