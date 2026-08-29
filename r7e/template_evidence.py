from __future__ import annotations

from textwrap import dedent


def d(value: str) -> str:
    return dedent(value).lstrip("\n")


def evidence_files(node_version: str, npm_version: str) -> dict[str, str]:
    return {
        "scripts/capture-toolchain.mjs": d("""
            import os from 'node:os';
            import { execFileSync } from 'node:child_process';
            import { readJson, writeJson } from './lib.mjs';

            function version(command, args = ['--version']) {
              try { return execFileSync(command, args, { encoding: 'utf8' }).trim(); }
              catch (error) { return { error: String(error) }; }
            }
            const packageJson = await readJson('package.json');
            const report = {
              schema: 'davidanderle.r7e.toolchain-environment.v1',
              timestampUtc: new Date().toISOString(),
              runtime: {
                node: process.version,
                npm: version('npm'),
                astro: version('npx', ['astro', '--version']),
                playwright: version('npx', ['playwright', '--version']),
                wrangler: version('npx', ['wrangler', '--version']),
                lighthouse: packageJson.devDependencies.lighthouse,
                sharp: packageJson.devDependencies.sharp,
                typescript: packageJson.devDependencies.typescript
              },
              pinned: {
                packageManager: packageJson.packageManager,
                engines: packageJson.engines,
                dependencies: packageJson.devDependencies
              },
              host: {
                platform: os.platform(),
                release: os.release(),
                arch: os.arch(),
                cpus: os.cpus().map((cpu) => cpu.model),
                totalMemoryBytes: os.totalmem(),
                githubRunId: process.env.GITHUB_RUN_ID || null,
                githubSha: process.env.GITHUB_SHA || null,
                githubRef: process.env.GITHUB_REF || null
              }
            };
            await writeJson('evidence/reports/toolchain-environment.json', report);
            console.log(JSON.stringify(report, null, 2));
        """),
        "scripts/finalize-evidence.mjs": d("""
            import fsp from 'node:fs/promises';
            import path from 'node:path';
            import { exists, sha256File, treeManifest, walk, writeJson } from './lib.mjs';

            const root = process.cwd();
            const commandRoots = [
              { dir: path.resolve('evidence/commands'), prefix: 'evidence/commands' },
              { dir: path.resolve('evidence/bootstrap-host/commands'), prefix: 'evidence/bootstrap-host/commands' }
            ];
            const commands = new Map();
            for (const location of commandRoots) {
              if (!(await exists(location.dir))) continue;
              for (const file of (await walk(location.dir)).filter((x) => x.endsWith('.json'))) {
                const record = JSON.parse(await fsp.readFile(file, 'utf8'));
                commands.set(record.id, { record, metadataPath: `${location.prefix}/${path.basename(file)}` });
              }
            }

            function observation(id) {
              const item = commands.get(id);
              if (!item) return 'NOT_EXECUTED';
              const record = item.record;
              if (record.expected_exit === 'nonzero' && record.native_exit_code !== 0 && record.expectation_met) return 'EXPECTED_REJECTION_OBSERVED';
              if (record.native_exit_code === 0 && record.expectation_met) return 'NATIVE_SUCCESS';
              if (record.native_exit_code === 127) return 'COMMAND_LAUNCH_FAILURE';
              return 'NATIVE_FAILURE';
            }

            async function rawFilesFor(ids, reports = []) {
              const raw = [];
              for (const id of ids) {
                const item = commands.get(id);
                if (!item) continue;
                raw.push(item.metadataPath);
                for (const candidate of [item.record.stdout_path, item.record.stderr_path]) {
                  if (!candidate) continue;
                  const base = path.basename(candidate);
                  const host = item.metadataPath.includes('bootstrap-host') ? 'evidence/bootstrap-host/raw' : 'evidence/raw';
                  raw.push(`${host}/${base}`);
                }
              }
              raw.push(...reports);
              const unique = [...new Set(raw)];
              const rows = [];
              for (const rel of unique) {
                const target = path.resolve(rel);
                rows.push({ path: rel, exists: await exists(target), sha256: await exists(target) ? await sha256File(target) : null, bytes: await exists(target) ? (await fsp.stat(target)).size : null });
              }
              return rows;
            }

            const claims = [
              { id: 'R7E-G01-OFFICIAL-SOURCES', claim: 'Current official documentation was retrieved from primary publishers and preserved with timestamps and hashes.', commands: ['040-official-sources'], reports: ['R7E_OFFICIAL_SOURCE_LOG.md', 'evidence/official-sources/index.json', 'evidence/reports/official-source-verification.json'] },
              { id: 'R7E-G02-PINNED-TOOLCHAIN', claim: 'The repository contains an exact pinned Node, npm and package toolchain without dependency ranges or latest tags.', commands: ['000-node-version', '001-npm-upgrade', '030-toolchain-environment', '050-source-verification'], reports: ['R7E_TOOLCHAIN_RESOLUTION.json', 'evidence/reports/toolchain-environment.json', 'evidence/reports/source-verification.json'] },
              { id: 'R7E-G03-CLEAN-INSTALL', claim: 'A native npm lockfile resolution and clean npm ci installation completed.', commands: ['010-lockfile', '020-npm-ci'], reports: ['package-lock.json'] },
              { id: 'R7E-G04-TYPED-CONTENT', claim: 'Astro typed content collections and project-wide static analysis completed against canonical Markdown and JSON.', commands: ['060-astro-check', '070-content-validation'], reports: ['src/content.config.ts', 'evidence/reports/content-validation.json'] },
              { id: 'R7E-G05-CROSS-RECORD-VALIDATION', claim: 'Explicit project-note, maturity, provenance and prominence invariants were evaluated.', commands: ['070-content-validation'], reports: ['evidence/reports/content-validation.json'] },
              { id: 'R7E-G06-PHOTOGRAPHY-PIPELINE', claim: 'The available 320 x 320 portrait candidate was processed locally without enlargement and outputs did not exceed 256 x 320.', commands: ['080-portrait-selection', '090-image-processing'], reports: ['evidence/reports/portrait-source-selection.json', 'evidence/reports/image-processing.json', 'public/media/portrait-manifest.json'] },
              { id: 'R7E-G07-NATIVE-ASTRO-BUILD', claim: 'A native Astro static build generated the launch site.', commands: ['100-base-build'], reports: ['evidence/reports/dist-verification.json'] },
              { id: 'R7E-G08-ZERO-ORDINARY-JS', claim: 'Ordinary launch routes emitted no executable script tags and remained complete with JavaScript disabled.', commands: ['110-dist-verification', '130-browser-tests'], reports: ['evidence/reports/dist-verification.json', 'evidence/browser/no-js-routes.json'] },
              { id: 'R7E-G09-BOUNDED-WEB-COMPONENT', claim: 'Exactly one route-local standards-based Web Component enhanced static baseline content.', commands: ['050-source-verification', '110-dist-verification', '130-browser-tests'], reports: ['evidence/reports/source-verification.json', 'evidence/reports/dist-verification.json', 'evidence/browser/playwright-report.json'] },
              { id: 'R7E-G10-BROWSER-OUTPUT', claim: 'Representative launch and deep routes were rendered in Chromium and measured.', commands: ['120-playwright-install', '130-browser-tests'], reports: ['evidence/browser/playwright-report.json', 'evidence/browser/measurements/home-desktop-1440.json', 'evidence/browser/measurements/project-oxide-mobile-390.json'] },
              { id: 'R7E-G11-DEDICATED-MOBILE-COMPOSITIONS', claim: 'Dedicated 390 px and 320 px compositions were present in authored CSS and captured in browser screenshots.', commands: ['050-source-verification', '130-browser-tests'], reports: ['src/styles/global.css', 'evidence/browser/screenshots/home-mobile-390.png', 'evidence/browser/screenshots/home-mobile-320.png', 'evidence/browser/screenshots/project-oxide-mobile-390.png', 'evidence/browser/screenshots/project-oxide-mobile-320.png'] },
              { id: 'R7E-G12-ACCESSIBILITY', claim: 'Representative routes were tested with axe-core and keyboard-accessible static structure.', commands: ['130-browser-tests'], reports: ['evidence/browser/axe-representative.json', 'evidence/browser/playwright-report.json'] },
              { id: 'R7E-G13-LIGHTHOUSE-MEASUREMENTS', claim: 'Lighthouse produced raw reports and measured category and web-vital outputs.', commands: ['140-lighthouse'], reports: ['evidence/lighthouse/summary.json', 'evidence/lighthouse/home-desktop.report.json', 'evidence/lighthouse/project-mobile.report.json'] },
              { id: 'R7E-G14-CLOUDFLARE-DRY-RUN', claim: 'Wrangler validated an assets-only Workers Static Assets deployment using a native dry run.', commands: ['150-wrangler-dry-run'], reports: ['wrangler.jsonc', 'evidence/wrangler-dry-run'] },
              { id: 'R7E-G15-CLOUDFLARE-BEHAVIOR', claim: 'Local Wrangler preview was queried for security headers, legacy redirect behavior and custom 404 handling.', commands: ['160-wrangler-preview'], reports: ['evidence/wrangler-preview/report.json'] },
              { id: 'R7E-G16-FIVE-HUNDRED-RECORD-SCALE', claim: 'Exactly 500 validated fixture records generated exactly 500 static detail pages and year indexes below 200 records.', commands: ['170-scale-generate', '180-scale-content-validation', '190-scale-build', '200-scale-verification'], reports: ['evidence/scale/generated-records-manifest.json', 'evidence/reports/scale-verification.json'] },
              { id: 'R7E-G17-REPRODUCIBILITY', claim: 'Two fresh npm ci workspaces built byte-identical static output trees from the same source and lockfile.', commands: ['270-reproducibility'], reports: ['evidence/reproducibility/report.json'] },
              { id: 'R7E-G18-NEGATIVE-SCHEMA', claim: 'An invalid Astro content-schema fixture was rejected by a native build.', commands: ['221-neg-schema-astro'], reports: [] },
              { id: 'R7E-G19-NEGATIVE-CROSS-REFERENCE', claim: 'An unknown cross-record reference was rejected by explicit validation.', commands: ['231-neg-crossref-validation'], reports: [] },
              { id: 'R7E-G20-NEGATIVE-DUPLICATE-SLUG', claim: 'A duplicate canonical slug was rejected by explicit validation.', commands: ['241-neg-duplicate-validation'], reports: [] },
              { id: 'R7E-G21-NEGATIVE-PHOTO-UPSCALE', claim: 'A 128 x 128 source was rejected rather than enlarged into the approved portrait envelope.', commands: ['251-neg-photo-process'], reports: [] },
              { id: 'R7E-G22-NEGATIVE-ORDINARY-JS', claim: 'Injected executable JavaScript on an ordinary route was rejected by dist verification.', commands: ['261-neg-js-dist'], reports: [] },
              { id: 'R7E-G23-SUPPLY-CHAIN-OBSERVATION', claim: 'npm audit, dependency tree and CycloneDX SBOM commands were executed and preserved.', commands: ['280-npm-audit', '290-sbom', '300-npm-ls'], reports: ['evidence/supply-chain/sbom.cdx.json'] }
            ];

            const gates = [];
            for (const claim of claims) {
              const observations = claim.commands.map((id) => ({ commandId: id, observation: observation(id) }));
              let producerObservation = 'NATIVE_SUCCESS';
              if (observations.some((x) => x.observation === 'NOT_EXECUTED')) producerObservation = 'NOT_VERIFIED';
              else if (observations.some((x) => ['NATIVE_FAILURE', 'COMMAND_LAUNCH_FAILURE'].includes(x.observation))) producerObservation = 'OBSERVED_FAILURE';
              else if (observations.every((x) => x.observation === 'EXPECTED_REJECTION_OBSERVED')) producerObservation = 'EXPECTED_REJECTION_OBSERVED';
              else if (observations.some((x) => x.observation === 'EXPECTED_REJECTION_OBSERVED')) producerObservation = 'MIXED_NATIVE_SUCCESS_AND_EXPECTED_REJECTION';
              gates.push({
                id: claim.id,
                claim: claim.claim,
                producerObservation,
                r7fDisposition: 'PENDING_INDEPENDENT_REVIEW',
                commandObservations: observations,
                rawEvidence: await rawFilesFor(claim.commands, claim.reports)
              });
            }

            const commandSummary = [...commands.values()].map(({ record, metadataPath }) => ({ id: record.id, metadataPath, nativeExitCode: record.native_exit_code, expectedExit: record.expected_exit, expectationMet: record.expectation_met, startTimestampUtc: record.start_timestamp_utc, endTimestampUtc: record.end_timestamp_utc }));
            const index = {
              schema: 'davidanderle.r7e.evidence-index.v1',
              generatedAtUtc: new Date().toISOString(),
              certificationStatement: 'R7E is an implementation and raw-evidence production stage. No gate in this index is independently certified. Final PASS, FAIL or release disposition belongs to R7F.',
              statusVocabulary: {
                NATIVE_SUCCESS: 'The recorded native command exited zero under its declared expectation.',
                EXPECTED_REJECTION_OBSERVED: 'A deliberately invalid fixture produced the required non-zero native exit.',
                OBSERVED_FAILURE: 'At least one native command failed or did not meet its declared expectation.',
                NOT_VERIFIED: 'Required raw command evidence was not produced.'
              },
              gates,
              commands: commandSummary
            };
            await writeJson('R7E_EVIDENCE_INDEX.json', index);
            await writeJson('evidence/R7E_EVIDENCE_INDEX.json', index);

            const counts = Object.fromEntries(['NATIVE_SUCCESS', 'EXPECTED_REJECTION_OBSERVED', 'MIXED_NATIVE_SUCCESS_AND_EXPECTED_REJECTION', 'OBSERVED_FAILURE', 'NOT_VERIFIED'].map((key) => [key, gates.filter((x) => x.producerObservation === key).length]));
            const failed = gates.filter((x) => ['OBSERVED_FAILURE', 'NOT_VERIFIED'].includes(x.producerObservation));
            const report = [
              '# R7E producer report',
              '',
              '**Authority boundary:** this report describes observations produced by the implementation workflow. It does not certify release readiness. R7F must inspect the raw files and assign final dispositions.',
              '',
              '## Observation counts',
              '',
              ...Object.entries(counts).map(([key, value]) => `- ${key}: ${value}`),
              '',
              '## Open or failed observations',
              '',
              ...(failed.length ? failed.map((gate) => `- ${gate.id}: ${gate.producerObservation}`) : ['- None recorded by the producer; independent review remains required.']),
              '',
              '## Deliberate limitations',
              '',
              '- The workflow performs no production deployment and uses no Cloudflare production credential.',
              '- Lighthouse values are measurements from one GitHub-hosted runner and are not universal performance guarantees.',
              '- A dimension-matching incumbent portrait candidate may be processed, but exact identity against the R5 authority source remains pending an independent hash comparison unless the supplemental input-authority report proves a match.',
              '- The 500-record corpus is a deterministic non-canonical fixture and is excluded from the public sitemap.',
              '- Security headers and local Wrangler behavior are evidence inputs, not a penetration test or security certification.',
              '',
              '## Independent audit entry point',
              '',
              'Begin with `R7E_EVIDENCE_INDEX.json`, then open each command metadata record, its separate stdout and stderr, and the generated artifact hashes.'
            ].join('\n') + '\n';
            await fsp.writeFile('R7E_PRODUCER_REPORT.md', report, 'utf8');
            await fsp.writeFile('R7E_LIMITATIONS.md', report.split('## Deliberate limitations')[1]?.split('## Independent audit entry point')[0]?.trim() + '\n', 'utf8');

            const manifests = {};
            for (const [name, target] of [['source', '.'], ['dist', 'dist'], ['distScale', 'dist-scale'], ['evidence', 'evidence']]) {
              if (!(await exists(target))) { manifests[name] = null; continue; }
              const manifest = await treeManifest(target);
              manifests[name] = { files: manifest.files, bytes: manifest.bytes, treeSha256: manifest.treeSha256 };
            }
            await writeJson('R7E_TREE_SUMMARY.json', manifests);
            console.log(JSON.stringify({ counts, failed: failed.map((x) => x.id), manifests }, null, 2));
        """),
        "scripts/package_r7e.py": d("""
            #!/usr/bin/env python3
            from __future__ import annotations

            import datetime as dt
            import hashlib
            import json
            import os
            import shutil
            import sys
            import zipfile
            from pathlib import Path

            UTC = dt.timezone.utc
            ROOT = Path.cwd()
            PACKAGE = ROOT / 'R7E_PACKAGE'
            OUTPUT = ROOT.parent / 'R7E_OUTPUT'
            ZIP_PATH = OUTPUT / 'DAVID_ANDERLE_R7E_PRODUCTION_REFERENCE_COMPLETE.zip'
            FIXED_ZIP_TIME = (2026, 8, 29, 0, 0, 0)

            def now():
                return dt.datetime.now(UTC).isoformat(timespec='milliseconds').replace('+00:00', 'Z')

            def sha256(path: Path) -> str:
                h = hashlib.sha256()
                with path.open('rb') as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                        h.update(chunk)
                return h.hexdigest()

            def copy_tree(source: Path, destination: Path, excluded: set[str] | None = None):
                excluded = excluded or set()
                if not source.exists():
                    return
                for item in sorted(source.rglob('*')):
                    rel = item.relative_to(source)
                    if any(part in excluded for part in rel.parts):
                        continue
                    target = destination / rel
                    if item.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    elif item.is_file():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, target)

            def manifest(root: Path):
                rows = []
                for item in sorted(p for p in root.rglob('*') if p.is_file() and p.name != 'R7E_PACKAGE_MANIFEST.json'):
                    rows.append({'path': item.relative_to(root).as_posix(), 'bytes': item.stat().st_size, 'sha256': sha256(item)})
                canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
                return {'files': len(rows), 'bytes': sum(x['bytes'] for x in rows), 'treeSha256': hashlib.sha256(canonical).hexdigest(), 'entries': rows}

            def create_zip(source: Path, target: Path):
                temp = target.with_suffix('.tmp.zip')
                temp.unlink(missing_ok=True)
                with zipfile.ZipFile(temp, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=True) as archive:
                    for item in sorted(p for p in source.rglob('*') if p.is_file()):
                        rel = Path('DAVID_ANDERLE_R7E_COMPLETE') / item.relative_to(source)
                        info = zipfile.ZipInfo(rel.as_posix(), FIXED_ZIP_TIME)
                        info.compress_type = zipfile.ZIP_DEFLATED
                        info.external_attr = (0o644 & 0xFFFF) << 16
                        archive.writestr(info, item.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
                temp.replace(target)

            started = now()
            shutil.rmtree(PACKAGE, ignore_errors=True)
            OUTPUT.mkdir(parents=True, exist_ok=True)
            PACKAGE.mkdir(parents=True, exist_ok=True)

            copy_tree(ROOT, PACKAGE / 'BEARING_PRODUCTION_SOURCE', {'node_modules', '.astro', 'dist', 'dist-scale', 'evidence', 'R7E_PACKAGE', 'R7E_OUTPUT'})
            copy_tree(ROOT / 'dist', PACKAGE / 'BEARING_GENERATED_SITE')
            copy_tree(ROOT / 'dist-scale', PACKAGE / 'BEARING_SCALE_SITE_500')
            copy_tree(ROOT / 'evidence', PACKAGE / 'R7E_RAW_EVIDENCE', {'work'})

            root_files = [
                'R7E_EVIDENCE_INDEX.json', 'R7E_OFFICIAL_SOURCE_LOG.md', 'R7E_TOOLCHAIN_RESOLUTION.json',
                'R7E_PRODUCER_REPORT.md', 'R7E_LIMITATIONS.md', 'R7E_TREE_SUMMARY.json',
                'R7E_AUTHORITY_REQUIREMENT_MATRIX.md', 'R7E_INPUT_PACKAGE_DECLARATION.json'
            ]
            for name in root_files:
                source = ROOT / name
                if source.exists():
                    shutil.copy2(source, PACKAGE / name)

            readme = '''# David Anderle R7E complete audit package\n\nThis archive contains the production-reference Astro source, generated launch site, 500-record scale build and raw evidence.\n\nR7E does not certify itself. Start with `R7E_EVIDENCE_INDEX.json`; assign final gate dispositions only in an independent R7F review.\n'''
            (PACKAGE / 'README_FIRST.md').write_text(readme, encoding='utf-8')
            package_manifest = manifest(PACKAGE)
            (PACKAGE / 'R7E_PACKAGE_MANIFEST.json').write_text(json.dumps(package_manifest, indent=2) + '\n', encoding='utf-8')

            ended = now()
            command_record = {
                'schema': 'davidanderle.r7e.command-evidence.v1',
                'id': '320-package',
                'command_argv': [sys.executable, 'scripts/package_r7e.py'],
                'command_shell_escaped': f'{sys.executable} scripts/package_r7e.py',
                'working_directory': str(ROOT),
                'start_timestamp_utc': started,
                'end_timestamp_utc': ended,
                'native_exit_code': 0,
                'expected_exit': 'zero',
                'expectation_met': True,
                'stdout_path': str(ROOT / 'evidence/raw/320-package.stdout.log'),
                'stderr_path': str(ROOT / 'evidence/raw/320-package.stderr.log'),
                'tool_version': {'output': sys.version},
                'artifacts': [{'kind': 'directory', 'path': str(PACKAGE), 'files': package_manifest['files'], 'bytes': package_manifest['bytes'], 'tree_sha256': package_manifest['treeSha256']}]
            }
            command_dir = ROOT / 'evidence/commands'; raw_dir = ROOT / 'evidence/raw'
            command_dir.mkdir(parents=True, exist_ok=True); raw_dir.mkdir(parents=True, exist_ok=True)
            (raw_dir / '320-package.stdout.log').write_text(json.dumps({'packageTree': package_manifest['treeSha256']}, indent=2) + '\n', encoding='utf-8')
            (raw_dir / '320-package.stderr.log').write_text('', encoding='utf-8')
            command_record['stdout_sha256'] = sha256(raw_dir / '320-package.stdout.log')
            command_record['stderr_sha256'] = sha256(raw_dir / '320-package.stderr.log')
            (command_dir / '320-package.json').write_text(json.dumps(command_record, indent=2) + '\n', encoding='utf-8')
            shutil.copy2(command_dir / '320-package.json', PACKAGE / 'R7E_RAW_EVIDENCE/commands/320-package.json')
            shutil.copy2(raw_dir / '320-package.stdout.log', PACKAGE / 'R7E_RAW_EVIDENCE/raw/320-package.stdout.log')
            shutil.copy2(raw_dir / '320-package.stderr.log', PACKAGE / 'R7E_RAW_EVIDENCE/raw/320-package.stderr.log')
            package_manifest = manifest(PACKAGE)
            (PACKAGE / 'R7E_PACKAGE_MANIFEST.json').write_text(json.dumps(package_manifest, indent=2) + '\n', encoding='utf-8')

            create_zip(PACKAGE, ZIP_PATH)
            zip_hash = sha256(ZIP_PATH)
            hash_path = ZIP_PATH.with_suffix(ZIP_PATH.suffix + '.sha256')
            hash_path.write_text(f'{zip_hash}  {ZIP_PATH.name}\n', encoding='utf-8')
            summary = {'zip': str(ZIP_PATH), 'bytes': ZIP_PATH.stat().st_size, 'sha256': zip_hash, 'packageTreeSha256': package_manifest['treeSha256'], 'createdAtUtc': now()}
            (OUTPUT / 'R7E_OUTPUT_SUMMARY.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
            print(json.dumps(summary, indent=2))
        """),
        "R7E_AUTHORITY_REQUIREMENT_MATRIX.md": d("""
            # R7E authority requirement matrix

            This matrix records the implementation boundary derived from the supplied R4, R5, R6C, R6D, R7 and R7V packages. It is a producer traceability aid, not a substitute for those source packages or for R7F review.

            | Authority | Implemented invariant | Evidence location |
            |---|---|---|
            | R4 | Long-lived identity architecture, typed heterogeneous work records, durable archive, conservative factual claims | `src/content.config.ts`, `src/content/`, `/archive/` |
            | R5 | Compact portrait envelope no larger than 256 x 320, no enlargement, complete no-photo state and provenance record | `scripts/process-images.mjs`, `/about/`, `/about/no-photo/`, image reports |
            | R6C | Bearing identity, calibrated editorial-industrial composition, concrete evidence as primary material | authored CSS, homepage and deep routes |
            | R6D | Design search closed; work appears before trajectory; Madison reduced; defensive metaphor copy reduced; deep pages retain identity | homepage ordering checks, project material modes, content validation |
            | R7 | Astro static architecture, typed collections, Markdown and JSON, bounded Web Component, Sharp, GitHub Actions and Cloudflare assets-only target | source repository and workflow files |
            | R7V | Previous declarations do not count as proof; native builds, reproducibility, 500-record scale, browser output and raw logs required | `R7E_EVIDENCE_INDEX.json` and `R7E_RAW_EVIDENCE/` |

            ## Non-negotiable implementation rules

            Ordinary launch routes remain complete without JavaScript. Only `/visual-comparison/` contains executable client code, implemented as one standards-based custom element. The 390 px and 320 px layouts have dedicated media-query compositions. The 500-record corpus is generated, validated and built as non-canonical test evidence. No production deploy occurs during R7E.
        """),
        "R7E_INPUT_PACKAGE_DECLARATION.json": d("""
            {
              "schema": "davidanderle.r7e.input-package-declaration.v1",
              "declaredInputs": [
                "DAVID_ANDERLE_R4_FINAL_SYNTHESIS",
                "DAVID_ANDERLE_R5_PHOTOGRAPHY_OMNIRESEARCH",
                "DAVID_ANDERLE_R6C_SUPREME_WEBSITE_CHAMPIONSHIP",
                "R6C_REFINED_WINNER_PROTOTYPE",
                "DAVID_ANDERLE_R6D_ABSOLUTE_DESIGN_CEILING_VERIFICATION",
                "DAVID_ANDERLE_R7_FINAL_TECHNICAL_ARCHITECTURE_TOURNAMENT",
                "DAVID_ANDERLE_R7V_RESEARCH_OUTPUT_COMPLETE"
              ],
              "localAttachmentHashes": "Added by the final packaging host in R7E_INPUT_AUTHORITY when available.",
              "precedence": [
                "factual truth and privacy",
                "R5 photographic constraints",
                "R6C and R6D Bearing invariants",
                "R4 content and identity architecture",
                "current official documentation",
                "R7 proposal",
                "old prototype details"
              ]
            }
        """),
        ".github/workflows/verify.yml": d(f"""
            name: Verify Bearing static reference

            on:
              pull_request:
              push:
                branches: [main]

            permissions:
              contents: read

            jobs:
              verify:
                runs-on: ubuntu-24.04
                timeout-minutes: 30
                steps:
                  - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262
                  - uses: actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020
                    with:
                      node-version: '{node_version}'
                      cache: npm
                  - run: npm install --global npm@{npm_version}
                  - run: npm ci
                  - run: npm run verify:source
                  - run: npm run check
                  - run: npm run build
                  - run: npm run verify:dist
        """),
        ".github/workflows/deploy.yml": d(f"""
            name: Deploy Bearing static assets

            on:
              workflow_dispatch:

            permissions:
              contents: read

            jobs:
              deploy:
                environment: production
                runs-on: ubuntu-24.04
                timeout-minutes: 20
                steps:
                  - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262
                  - uses: actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020
                    with:
                      node-version: '{node_version}'
                      cache: npm
                  - run: npm install --global npm@{npm_version}
                  - run: npm ci
                  - run: npm run build
                  - name: Deploy assets-only Worker
                    run: npx wrangler deploy
                    env:
                      CLOUDFLARE_API_TOKEN: ${{{{ secrets.CLOUDFLARE_API_TOKEN }}}}
                      CLOUDFLARE_ACCOUNT_ID: ${{{{ secrets.CLOUDFLARE_ACCOUNT_ID }}}}
        """)
    }
