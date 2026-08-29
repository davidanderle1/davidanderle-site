from __future__ import annotations

from textwrap import dedent


def d(value: str) -> str:
    return dedent(value).lstrip("\n")


def verification_files() -> dict[str, str]:
    return {
        "scripts/lib.mjs": d("""
            import fs from 'node:fs';
            import fsp from 'node:fs/promises';
            import crypto from 'node:crypto';
            import path from 'node:path';

            export async function exists(target) {
              try { await fsp.access(target); return true; } catch { return false; }
            }

            export async function ensureDir(target) { await fsp.mkdir(target, { recursive: true }); }

            export async function readJson(target) { return JSON.parse(await fsp.readFile(target, 'utf8')); }

            export async function writeJson(target, value) {
              await ensureDir(path.dirname(target));
              await fsp.writeFile(target, JSON.stringify(value, null, 2) + '\n', 'utf8');
            }

            export function sha256Buffer(buffer) { return crypto.createHash('sha256').update(buffer).digest('hex'); }

            export async function sha256File(target) {
              const hash = crypto.createHash('sha256');
              await new Promise((resolve, reject) => {
                const stream = fs.createReadStream(target);
                stream.on('data', (chunk) => hash.update(chunk));
                stream.on('error', reject);
                stream.on('end', resolve);
              });
              return hash.digest('hex');
            }

            export async function walk(root, options = {}) {
              const excluded = new Set(options.excludeNames || []);
              const rows = [];
              if (!(await exists(root))) return rows;
              async function visit(current) {
                const entries = await fsp.readdir(current, { withFileTypes: true });
                entries.sort((a, b) => a.name.localeCompare(b.name));
                for (const entry of entries) {
                  if (excluded.has(entry.name)) continue;
                  const full = path.join(current, entry.name);
                  if (entry.isDirectory()) await visit(full);
                  else if (entry.isFile()) rows.push(full);
                }
              }
              await visit(root);
              return rows;
            }

            export async function treeManifest(root) {
              const rows = [];
              for (const file of await walk(root, { excludeNames: ['.DS_Store'] })) {
                const stat = await fsp.stat(file);
                rows.push({ path: path.relative(root, file).split(path.sep).join('/'), bytes: stat.size, sha256: await sha256File(file) });
              }
              const canonical = JSON.stringify(rows);
              return { files: rows.length, bytes: rows.reduce((sum, row) => sum + row.bytes, 0), treeSha256: sha256Buffer(Buffer.from(canonical)), manifest: rows };
            }

            export function isoNow() { return new Date().toISOString(); }

            export function toPosix(value) { return value.split(path.sep).join('/'); }
        """),
        "scripts/verify-official-sources.mjs": d("""
            import path from 'node:path';
            import { readJson, writeJson } from './lib.mjs';

            const sourceIndex = path.resolve('evidence/official-sources/index.json');
            const index = await readJson(sourceIndex);
            const failures = [];
            for (const item of index.sources) {
              if (!(item.httpStatus >= 200 && item.httpStatus < 400)) failures.push(`${item.id}: HTTP ${item.httpStatus}`);
              if (!item.sha256) failures.push(`${item.id}: missing response hash`);
              if (item.expectedMarkers?.length && item.markerHits === 0) failures.push(`${item.id}: no expected marker observed`);
            }
            const report = {
              schema: 'davidanderle.r7e.official-source-observation.v1',
              retrievalTimestampUtc: index.retrievalTimestampUtc,
              sourceCount: index.sources.length,
              successfulHttpResponses: index.sources.filter((x) => x.httpStatus >= 200 && x.httpStatus < 400).length,
              markerConfirmedSources: index.sources.filter((x) => x.markerHits > 0).length,
              failures
            };
            await writeJson('evidence/reports/official-source-verification.json', report);
            if (failures.length) {
              console.error(failures.join('\n'));
              process.exit(2);
            }
            console.log(JSON.stringify(report, null, 2));
        """),
        "scripts/validate-content.mjs": d("""
            import fsp from 'node:fs/promises';
            import path from 'node:path';
            import matter from 'gray-matter';
            import { walk, writeJson } from './lib.mjs';

            const errors = [];
            const warnings = [];
            const projectDir = path.resolve('src/content/projects');
            const noteDir = path.resolve('src/content/notes');
            const scaleDir = path.resolve('src/content/scale');

            async function loadMarkdown(root) {
              const records = [];
              for (const file of (await walk(root)).filter((x) => /\.mdx?$/.test(x))) {
                const parsed = matter(await fsp.readFile(file, 'utf8'));
                records.push({ file, relative: path.relative(process.cwd(), file), data: parsed.data, body: parsed.content });
              }
              return records;
            }

            const projects = await loadMarkdown(projectDir);
            const notes = await loadMarkdown(noteDir);
            const scale = await loadMarkdown(scaleDir);
            const projectSlugs = new Set();
            const noteSlugs = new Set();
            const allowedMaturity = new Set(['working-prototype', 'research-in-progress', 'private-system']);
            const allowedMaterials = new Set(['graphite', 'oxide', 'paper']);
            const forbiddenInflation = [/world[- ]class/i, /guaranteed/i, /production trading platform/i, /published paper/i];

            function requireValue(record, key) {
              if (record.data[key] === undefined || record.data[key] === null || record.data[key] === '') errors.push(`${record.relative}: missing ${key}`);
            }

            for (const record of projects) {
              for (const key of ['title', 'slug', 'summary', 'publishedAt', 'year', 'role', 'maturity', 'authorship', 'access', 'material', 'featured', 'sortOrder', 'evidence', 'links', 'relatedNotes']) requireValue(record, key);
              if (projectSlugs.has(record.data.slug)) errors.push(`${record.relative}: duplicate project slug ${record.data.slug}`);
              projectSlugs.add(record.data.slug);
              if (!allowedMaturity.has(record.data.maturity)) errors.push(`${record.relative}: invalid maturity ${record.data.maturity}`);
              if (!allowedMaterials.has(record.data.material)) errors.push(`${record.relative}: invalid material ${record.data.material}`);
              if (!Array.isArray(record.data.evidence) || record.data.evidence.length < 2) errors.push(`${record.relative}: fewer than two evidence records`);
              const combined = `${record.data.title || ''} ${record.data.summary || ''} ${record.body}`;
              for (const pattern of forbiddenInflation) if (pattern.test(combined)) errors.push(`${record.relative}: unsupported inflation matched ${pattern}`);
            }

            for (const record of notes) {
              for (const key of ['title', 'slug', 'summary', 'publishedAt', 'year', 'status', 'material', 'relatedProjects']) requireValue(record, key);
              if (noteSlugs.has(record.data.slug)) errors.push(`${record.relative}: duplicate note slug ${record.data.slug}`);
              noteSlugs.add(record.data.slug);
              if (!allowedMaterials.has(record.data.material)) errors.push(`${record.relative}: invalid material ${record.data.material}`);
            }

            for (const project of projects) {
              for (const noteSlug of project.data.relatedNotes || []) if (!noteSlugs.has(noteSlug)) errors.push(`${project.relative}: unknown related note ${noteSlug}`);
            }
            for (const note of notes) {
              for (const projectSlug of note.data.relatedProjects || []) if (!projectSlugs.has(projectSlug)) errors.push(`${note.relative}: unknown related project ${projectSlug}`);
            }

            const education = JSON.parse(await fsp.readFile('src/content/data/education.json', 'utf8'));
            const experience = JSON.parse(await fsp.readFile('src/content/data/experience.json', 'utf8'));
            for (const row of education) {
              if (row.startYear > row.endYear) errors.push(`education ${row.id}: startYear after endYear`);
              if (row.id === 'uw-madison-exchange' && row.prominence !== 'secondary') errors.push('UW–Madison must remain secondary context');
            }
            for (const row of experience) {
              if (row.id === 'uw-context' && row.prominence !== 'secondary') errors.push('UW experience context must remain secondary');
            }

            if (projects.length !== 3) errors.push(`expected 3 canonical projects, observed ${projects.length}`);
            if (notes.length !== 3) errors.push(`expected 3 canonical notes, observed ${notes.length}`);
            if (process.env.R7E_SCALE === '1' && scale.length !== 500) errors.push(`scale mode expected 500 records, observed ${scale.length}`);
            if (process.env.R7E_SCALE !== '1' && scale.length > 0) warnings.push(`${scale.length} generated scale records present outside scale mode`);

            const report = {
              schema: 'davidanderle.r7e.content-validation.v1',
              canonicalProjects: projects.length,
              canonicalNotes: notes.length,
              educationRecords: education.length,
              experienceRecords: experience.length,
              scaleRecords: scale.length,
              errors,
              warnings,
              projectSlugs: [...projectSlugs].sort(),
              noteSlugs: [...noteSlugs].sort()
            };
            await writeJson('evidence/reports/content-validation.json', report);
            if (errors.length) {
              console.error(errors.join('\n'));
              process.exit(2);
            }
            console.log(JSON.stringify(report, null, 2));
        """),
        "scripts/select-portrait-source.mjs": d("""
            import fsp from 'node:fs/promises';
            import path from 'node:path';
            import sharp from 'sharp';
            import { walk, sha256File, writeJson } from './lib.mjs';

            const searchRoot = path.resolve(process.argv[2] || '..');
            const destination = path.resolve('src/assets/portrait');
            const evidencePath = path.resolve('evidence/reports/portrait-source-selection.json');
            await fsp.mkdir(destination, { recursive: true });
            const extensions = new Set(['.png', '.jpg', '.jpeg', '.webp', '.avif']);
            const candidates = [];
            for (const file of await walk(searchRoot, { excludeNames: ['.git', 'node_modules', 'dist', 'dist-scale', 'evidence', 'R7E_PACKAGE', 'R7E_OUTPUT'] })) {
              if (!extensions.has(path.extname(file).toLowerCase())) continue;
              if (file.startsWith(process.cwd() + path.sep)) continue;
              try {
                const metadata = await sharp(file).metadata();
                if (metadata.width !== 320 || metadata.height !== 320) continue;
                const rel = path.relative(searchRoot, file).split(path.sep).join('/');
                const lower = rel.toLowerCase();
                let score = 0;
                for (const token of ['portrait', 'profile', 'headshot', 'david', 'photo']) if (lower.includes(token)) score += 10;
                if (lower.includes('320')) score += 4;
                if (lower.includes('approved') || lower.includes('final')) score += 6;
                candidates.push({ file, relativePath: rel, width: metadata.width, height: metadata.height, format: metadata.format, score, bytes: (await fsp.stat(file)).size, sha256: await sha256File(file) });
              } catch { /* invalid image candidates are ignored */ }
            }
            candidates.sort((a, b) => b.score - a.score || a.bytes - b.bytes || a.relativePath.localeCompare(b.relativePath));
            for (const existing of await fsp.readdir(destination)) if (existing.startsWith('approved-source.')) await fsp.rm(path.join(destination, existing), { force: true });

            if (!candidates.length) {
              const report = {
                schema: 'davidanderle.r7e.portrait-selection.v1',
                searchRoot,
                result: 'NO_320_X_320_CANDIDATE',
                compactPhotoEnabled: false,
                r7fAuthorityHashDisposition: 'PENDING_INDEPENDENT_REVIEW',
                candidates: []
              };
              await writeJson(path.join(destination, 'provenance.json'), report);
              await writeJson(evidencePath, report);
              console.log(JSON.stringify(report, null, 2));
              process.exit(0);
            }

            const selected = candidates[0];
            const extension = path.extname(selected.file).toLowerCase() || '.png';
            const target = path.join(destination, `approved-source${extension}`);
            await fsp.copyFile(selected.file, target);
            const report = {
              schema: 'davidanderle.r7e.portrait-selection.v1',
              searchRoot,
              result: 'DIMENSION_MATCH_CANDIDATE_SELECTED',
              compactPhotoEnabled: true,
              selectionBasis: 'Exact 320 x 320 dimensions plus deterministic filename scoring in the incumbent public repository.',
              selected: { ...selected, copiedTo: path.relative(process.cwd(), target).split(path.sep).join('/') },
              candidateCount: candidates.length,
              candidates,
              r7fAuthorityHashDisposition: 'PENDING_INDEPENDENT_R5_HASH_COMPARISON'
            };
            await writeJson(path.join(destination, 'provenance.json'), report);
            await writeJson(evidencePath, report);
            console.log(JSON.stringify(report, null, 2));
        """),
        "scripts/process-images.mjs": d("""
            import fsp from 'node:fs/promises';
            import path from 'node:path';
            import sharp from 'sharp';
            import { walk, sha256File, writeJson } from './lib.mjs';

            const sourceDir = path.resolve('src/assets/portrait');
            const outputDir = path.resolve('public/media');
            await fsp.mkdir(outputDir, { recursive: true });
            const sources = (await walk(sourceDir)).filter((file) => path.basename(file).startsWith('approved-source.') && !file.endsWith('.json'));
            for (const stale of ['portrait-256x320.webp', 'portrait-256x320.avif']) await fsp.rm(path.join(outputDir, stale), { force: true });

            if (sources.length === 0) {
              const report = {
                schema: 'davidanderle.r7e.image-processing.v1',
                result: 'NO_APPROVED_SOURCE_PRESENT',
                compactPhotoEnabled: false,
                noPhotoStateRequired: true
              };
              await writeJson(path.join(outputDir, 'portrait-manifest.json'), report);
              await writeJson('evidence/reports/image-processing.json', report);
              console.log(JSON.stringify(report, null, 2));
              process.exit(0);
            }
            if (sources.length !== 1) throw new Error(`Expected one approved source, observed ${sources.length}`);
            const source = sources[0];
            const metadata = await sharp(source).metadata();
            if (metadata.width !== 320 || metadata.height !== 320) {
              throw new Error(`R5 source envelope violated: expected exactly 320 x 320, observed ${metadata.width} x ${metadata.height}`);
            }
            const left = 32;
            const crop = { left, top: 0, width: 256, height: 320 };
            const webp = path.join(outputDir, 'portrait-256x320.webp');
            const avif = path.join(outputDir, 'portrait-256x320.avif');
            await sharp(source).extract(crop).webp({ quality: 86, smartSubsample: true }).toFile(webp);
            await sharp(source).extract(crop).avif({ quality: 56, effort: 6 }).toFile(avif);
            const webpMeta = await sharp(webp).metadata();
            const avifMeta = await sharp(avif).metadata();
            for (const [label, value] of [['webp', webpMeta], ['avif', avifMeta]]) {
              if (value.width !== 256 || value.height !== 320) throw new Error(`${label} output envelope violated: ${value.width} x ${value.height}`);
              if (value.width > metadata.width || value.height > metadata.height) throw new Error(`${label} output enlarged the source`);
            }
            const report = {
              schema: 'davidanderle.r7e.image-processing.v1',
              result: 'CROP_WITHOUT_ENLARGEMENT',
              deterministicTimestamp: '2026-08-29T00:00:00.000Z',
              source: { path: path.relative(process.cwd(), source).split(path.sep).join('/'), width: metadata.width, height: metadata.height, format: metadata.format, sha256: await sha256File(source) },
              operation: { type: 'extract', crop, enlargement: false },
              outputs: [
                { path: 'public/media/portrait-256x320.webp', width: webpMeta.width, height: webpMeta.height, format: webpMeta.format, sha256: await sha256File(webp) },
                { path: 'public/media/portrait-256x320.avif', width: avifMeta.width, height: avifMeta.height, format: avifMeta.format, sha256: await sha256File(avif) }
              ],
              r7fAuthorityHashDisposition: 'PENDING_INDEPENDENT_R5_HASH_COMPARISON'
            };
            await writeJson(path.join(outputDir, 'portrait-manifest.json'), report);
            await writeJson('evidence/reports/image-processing.json', report);
            console.log(JSON.stringify(report, null, 2));
        """),
        "scripts/verify-source.mjs": d("""
            import fsp from 'node:fs/promises';
            import path from 'node:path';
            import { walk, readJson, writeJson } from './lib.mjs';

            const errors = [];
            const observations = [];
            const packageJson = await readJson('package.json');
            const dependencies = { ...(packageJson.dependencies || {}), ...(packageJson.devDependencies || {}) };
            const exactVersion = /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$/;
            for (const [name, version] of Object.entries(dependencies)) {
              if (version === 'latest' || !exactVersion.test(version)) errors.push(`${name} is not pinned to an exact version: ${version}`);
            }
            for (const forbidden of ['react', 'react-dom', 'vue', 'svelte', '@astrojs/react', '@astrojs/vue', '@astrojs/svelte']) if (dependencies[forbidden]) errors.push(`forbidden framework dependency present: ${forbidden}`);

            const sourceFiles = await walk('src');
            const textFiles = sourceFiles.filter((file) => /\.(astro|ts|js|mjs|css|md|json)$/.test(file));
            let customElementDefinitions = 0;
            let executableScriptBlocks = 0;
            for (const file of textFiles) {
              const content = await fsp.readFile(file, 'utf8');
              if (/client:(load|idle|visible|media|only)/.test(content)) errors.push(`${file}: hydration directive present`);
              customElementDefinitions += (content.match(/customElements\.define\s*\(/g) || []).length;
              if (file.endsWith('.astro')) executableScriptBlocks += (content.match(/<script(?:\s|>)/g) || []).length;
            }
            if (customElementDefinitions !== 1) errors.push(`expected one customElements.define call, observed ${customElementDefinitions}`);
            if (executableScriptBlocks !== 1) errors.push(`expected one Astro script block, observed ${executableScriptBlocks}`);

            const astroConfig = await fsp.readFile('astro.config.mjs', 'utf8');
            if (!/output:\s*['"]static['"]/.test(astroConfig)) errors.push('Astro output is not explicitly static');
            const css = await fsp.readFile('src/styles/global.css', 'utf8');
            if (!css.includes('@media (max-width: 410px) and (min-width: 351px)')) errors.push('dedicated 390 px composition missing');
            if (!css.includes('@media (max-width: 350px)')) errors.push('dedicated 320 px composition missing');
            if (/tailwind|bootstrap|bulma/i.test(css)) errors.push('third-party CSS framework marker present');

            const wrangler = await fsp.readFile('wrangler.jsonc', 'utf8');
            if (!/"assets"\s*:/.test(wrangler)) errors.push('Wrangler assets configuration missing');
            if (/"main"\s*:/.test(wrangler)) errors.push('Wrangler Worker main script present in assets-only reference');
            if (!/"not_found_handling"\s*:\s*"404-page"/.test(wrangler)) errors.push('custom 404 handling not configured');

            const required = ['public/_headers', 'public/_redirects', 'src/pages/404.astro', 'src/pages/about/no-photo.astro', 'src/pages/visual-comparison.astro', 'src/content.config.ts'];
            for (const file of required) {
              try { await fsp.access(file); } catch { errors.push(`required source missing: ${file}`); }
            }
            const home = await fsp.readFile('src/pages/index.astro', 'utf8');
            if (home.indexOf('id="selected-evidence"') > home.indexOf('id="trajectory"')) errors.push('homepage puts trajectory before concrete work evidence');
            const education = await readJson('src/content/data/education.json');
            const madison = education.find((x) => x.id === 'uw-madison-exchange');
            if (!madison || madison.prominence !== 'secondary') errors.push('Madison secondary prominence invariant missing');

            observations.push({ exactPinnedDependencies: Object.keys(dependencies).length, customElementDefinitions, executableScriptBlocks, sourceFiles: sourceFiles.length });
            const report = { schema: 'davidanderle.r7e.source-verification.v1', errors, observations };
            await writeJson('evidence/reports/source-verification.json', report);
            if (errors.length) { console.error(errors.join('\n')); process.exit(2); }
            console.log(JSON.stringify(report, null, 2));
        """),
        "scripts/verify-dist.mjs": d("""
            import fsp from 'node:fs/promises';
            import path from 'node:path';
            import { parse } from 'parse5';
            import sharp from 'sharp';
            import { exists, walk, sha256File, writeJson } from './lib.mjs';

            const dist = path.resolve(process.argv[2] || 'dist');
            const errors = [];
            const ordinaryPaths = ['index.html', 'work/index.html', 'work/research-workspace/index.html', 'work/non-core-real-estate/index.html', 'work/merkle-poseidon/index.html', 'writing/index.html', 'archive/index.html', 'about/index.html', 'about/no-photo/index.html', 'contact/index.html'];

            function attrs(node) { return Object.fromEntries((node.attrs || []).map((item) => [item.name, item.value])); }
            function scripts(node, rows = []) {
              if (node.nodeName === 'script') rows.push(attrs(node));
              for (const child of node.childNodes || []) scripts(child, rows);
              return rows;
            }
            function executable(row) { const type = (row.type || '').toLowerCase(); return !type || type === 'module' || type.includes('javascript') || type === 'text/ecmascript'; }

            const routeMeasurements = [];
            for (const rel of ordinaryPaths) {
              const target = path.join(dist, rel);
              if (!(await exists(target))) { errors.push(`ordinary route output missing: ${rel}`); continue; }
              const html = await fsp.readFile(target, 'utf8');
              const executableCount = scripts(parse(html)).filter(executable).length;
              if (executableCount !== 0) errors.push(`${rel}: executable script count ${executableCount}`);
              routeMeasurements.push({ path: rel, bytes: Buffer.byteLength(html), executableScripts: executableCount, sha256: await sha256File(target) });
            }

            const comparisonPath = path.join(dist, 'visual-comparison/index.html');
            if (!(await exists(comparisonPath))) errors.push('visual comparison output missing');
            else {
              const html = await fsp.readFile(comparisonPath, 'utf8');
              const count = scripts(parse(html)).filter(executable).length;
              if (count !== 1) errors.push(`visual comparison expected one executable script, observed ${count}`);
              routeMeasurements.push({ path: 'visual-comparison/index.html', bytes: Buffer.byteLength(html), executableScripts: count, sha256: await sha256File(comparisonPath) });
            }

            const home = await fsp.readFile(path.join(dist, 'index.html'), 'utf8');
            if (home.indexOf('id="selected-evidence"') < 0 || home.indexOf('id="trajectory"') < 0 || home.indexOf('id="selected-evidence"') > home.indexOf('id="trajectory"')) errors.push('generated homepage evidence ordering invariant failed');
            for (const [route, marker] of [['work/research-workspace/index.html', 'material-graphite'], ['work/non-core-real-estate/index.html', 'material-oxide'], ['work/merkle-poseidon/index.html', 'material-paper']]) {
              const html = await fsp.readFile(path.join(dist, route), 'utf8');
              if (!html.includes(marker)) errors.push(`${route}: material marker ${marker} missing`);
            }
            for (const rel of ['404.html', '_headers', '_redirects', 'sitemap.xml', 'robots.txt']) if (!(await exists(path.join(dist, rel)))) errors.push(`deployment artifact missing: ${rel}`);
            if (await exists(path.join(dist, '404.html'))) {
              const html = await fsp.readFile(path.join(dist, '404.html'), 'utf8');
              if (!html.includes('data-custom-404="bearing"')) errors.push('custom 404 marker missing');
            }
            const headers = await fsp.readFile(path.join(dist, '_headers'), 'utf8');
            for (const marker of ['Content-Security-Policy:', 'X-Content-Type-Options:', 'Referrer-Policy:', 'Permissions-Policy:']) if (!headers.includes(marker)) errors.push(`_headers missing ${marker}`);

            const assetFiles = await walk(path.join(dist, '_astro'));
            const jsAssets = assetFiles.filter((x) => x.endsWith('.js'));
            const cssAssets = assetFiles.filter((x) => x.endsWith('.css'));
            if (jsAssets.length > 1) errors.push(`expected at most one JavaScript asset, observed ${jsAssets.length}`);
            if (cssAssets.length === 0) errors.push('no generated CSS asset observed');
            const assets = [];
            for (const file of [...jsAssets, ...cssAssets]) assets.push({ path: path.relative(dist, file).split(path.sep).join('/'), bytes: (await fsp.stat(file)).size, sha256: await sha256File(file) });

            const photoManifestPath = path.join(dist, 'media', 'portrait-manifest.json');
            let portrait = null;
            if (await exists(photoManifestPath)) portrait = JSON.parse(await fsp.readFile(photoManifestPath, 'utf8'));
            for (const rel of ['media/portrait-256x320.webp', 'media/portrait-256x320.avif']) {
              const target = path.join(dist, rel);
              if (await exists(target)) {
                const meta = await sharp(target).metadata();
                if (meta.width > 256 || meta.height > 320) errors.push(`${rel}: exceeds 256 x 320 envelope`);
              }
            }

            const report = {
              schema: 'davidanderle.r7e.dist-verification.v1',
              dist,
              ordinaryRouteCount: ordinaryPaths.length,
              routeMeasurements,
              assets,
              javascriptAssetCount: jsAssets.length,
              cssAssetCount: cssAssets.length,
              portrait,
              errors
            };
            await writeJson('evidence/reports/dist-verification.json', report);
            if (errors.length) { console.error(errors.join('\n')); process.exit(2); }
            console.log(JSON.stringify(report, null, 2));
        """),
        "scripts/generate-scale-fixtures.mjs": d("""
            import fsp from 'node:fs/promises';
            import path from 'node:path';
            import { ensureDir, sha256File, writeJson } from './lib.mjs';

            const count = Number(process.argv[2] || '500');
            if (count !== 500) throw new Error(`R7E scale fixture is fixed at 500 records, received ${count}`);
            const evidenceDir = path.resolve('evidence/scale/generated-records');
            const contentDir = path.resolve('src/content/scale');
            await fsp.rm(evidenceDir, { recursive: true, force: true });
            await ensureDir(evidenceDir);
            await ensureDir(contentDir);
            for (const file of await fsp.readdir(contentDir)) if (file.endsWith('.md')) await fsp.rm(path.join(contentDir, file));
            const materials = ['graphite', 'oxide', 'paper'];
            const manifest = [];
            for (let sequence = 1; sequence <= count; sequence += 1) {
              const slug = `scale-${String(sequence).padStart(4, '0')}`;
              const year = 2017 + ((sequence - 1) % 10);
              const material = materials[(sequence - 1) % materials.length];
              const body = `---\ntitle: Scale record ${String(sequence).padStart(4, '0')}\nslug: ${slug}\nyear: ${year}\nsequence: ${sequence}\nmaterial: ${material}\nsummary: Deterministic generated record ${sequence} used only to measure validated static build scale.\n---\n\nThis fixture is deterministic, non-canonical and excluded from the public sitemap. It exists to force a native Astro detail-page build at record ${sequence}.\n`;
              const evidencePath = path.join(evidenceDir, `${slug}.md`);
              const contentPath = path.join(contentDir, `${slug}.md`);
              await fsp.writeFile(evidencePath, body, 'utf8');
              await fsp.copyFile(evidencePath, contentPath);
              manifest.push({ slug, year, sequence, material, sha256: await sha256File(evidencePath) });
            }
            await writeJson('evidence/scale/generated-records-manifest.json', { schema: 'davidanderle.r7e.scale-fixture.v1', count, years: [...new Set(manifest.map((x) => x.year))], records: manifest });
            console.log(`Generated ${count} deterministic scale records.`);
        """),
        "scripts/clear-scale-fixtures.mjs": d("""
            import fsp from 'node:fs/promises';
            import path from 'node:path';
            const root = path.resolve('src/content/scale');
            await fsp.mkdir(root, { recursive: true });
            let removed = 0;
            for (const file of await fsp.readdir(root)) if (file.endsWith('.md')) { await fsp.rm(path.join(root, file)); removed += 1; }
            console.log(`Removed ${removed} generated scale records from the production collection directory.`);
        """),
        "scripts/verify-scale.mjs": d("""
            import fsp from 'node:fs/promises';
            import path from 'node:path';
            import { exists, walk, treeManifest, writeJson } from './lib.mjs';

            const errors = [];
            const fixtureFiles = (await walk('evidence/scale/generated-records')).filter((x) => x.endsWith('.md'));
            const detailFiles = (await walk('dist-scale/scale')).filter((x) => /scale-[0-9]{4}\/index\.html$/.test(x.split(path.sep).join('/')));
            if (fixtureFiles.length !== 500) errors.push(`expected 500 generated fixtures, observed ${fixtureFiles.length}`);
            if (detailFiles.length !== 500) errors.push(`expected 500 generated detail pages, observed ${detailFiles.length}`);
            const yearCounts = {};
            for (let year = 2017; year <= 2026; year += 1) {
              const target = path.join('dist-scale', 'scale', 'archive', String(year), 'index.html');
              if (!(await exists(target))) { errors.push(`missing scale archive year ${year}`); continue; }
              const html = await fsp.readFile(target, 'utf8');
              const count = (html.match(/href="\/scale\/scale-[0-9]{4}\//g) || []).length;
              yearCounts[year] = count;
              if (count > 200) errors.push(`year ${year} contains ${count} records, above policy ceiling`);
            }
            const manifest = await treeManifest('dist-scale');
            const report = {
              schema: 'davidanderle.r7e.scale-verification.v1',
              generatedFixtureCount: fixtureFiles.length,
              generatedDetailPageCount: detailFiles.length,
              archiveYearCounts: yearCounts,
              maximumArchivePageRecords: Math.max(...Object.values(yearCounts)),
              distScaleFiles: manifest.files,
              distScaleBytes: manifest.bytes,
              distScaleTreeSha256: manifest.treeSha256,
              errors
            };
            await writeJson('evidence/reports/scale-verification.json', report);
            if (errors.length) { console.error(errors.join('\n')); process.exit(2); }
            console.log(JSON.stringify(report, null, 2));
        """),
        "scripts/prepare-negative-fixture.mjs": d("""
            import fsp from 'node:fs/promises';
            import path from 'node:path';
            import sharp from 'sharp';

            const kind = process.argv[2];
            const destination = path.resolve(process.argv[3] || `../r7e-negative-${kind}`);
            if (!kind) throw new Error('fixture kind required');
            await fsp.rm(destination, { recursive: true, force: true });
            await fsp.cp(process.cwd(), destination, {
              recursive: true,
              filter: (source) => {
                const rel = path.relative(process.cwd(), source);
                const first = rel.split(path.sep)[0];
                return !['node_modules', 'evidence', 'dist', 'dist-scale', 'R7E_PACKAGE', 'R7E_OUTPUT', '.astro'].includes(first);
              }
            });
            await fsp.symlink(path.resolve('node_modules'), path.join(destination, 'node_modules'), 'dir');
            await fsp.mkdir(path.join(destination, 'evidence'), { recursive: true });

            if (kind === 'schema') {
              await fsp.writeFile(path.join(destination, 'src/content/projects/invalid-schema.md'), `---\ntitle: Invalid schema fixture\nslug: invalid-schema\nsummary: This intentionally invalid fixture omits required project fields so Astro schema validation must reject it.\npublishedAt: 2026-08-29\nyear: 2026\n---\n\nExpected rejection.\n`);
            } else if (kind === 'crossref') {
              const target = path.join(destination, 'src/content/projects/research-workspace.md');
              let body = await fsp.readFile(target, 'utf8');
              body = body.replace('relatedNotes:\n  - risk-before-optimization', 'relatedNotes:\n  - note-that-does-not-exist');
              await fsp.writeFile(target, body);
            } else if (kind === 'duplicate') {
              const source = path.join(destination, 'src/content/projects/research-workspace.md');
              await fsp.copyFile(source, path.join(destination, 'src/content/projects/duplicate-slug.md'));
            } else if (kind === 'photo-upscale') {
              const portraitDir = path.join(destination, 'src/assets/portrait');
              await fsp.rm(portraitDir, { recursive: true, force: true });
              await fsp.mkdir(portraitDir, { recursive: true });
              await sharp({ create: { width: 128, height: 128, channels: 3, background: '#777777' } }).png().toFile(path.join(portraitDir, 'approved-source.png'));
            } else if (kind === 'ordinary-js') {
              await fsp.cp(path.resolve('dist'), path.join(destination, 'dist'), { recursive: true });
              const index = path.join(destination, 'dist/index.html');
              let html = await fsp.readFile(index, 'utf8');
              html = html.replace('</body>', '<script src="/forbidden.js"></script></body>');
              await fsp.writeFile(index, html);
            } else {
              throw new Error(`unknown fixture kind ${kind}`);
            }
            console.log(destination);
        """),
        "scripts/run-lighthouse.mjs": d("""
            import fsp from 'node:fs/promises';
            import path from 'node:path';
            import { spawn } from 'node:child_process';
            import { chromium } from '@playwright/test';
            import { ensureDir, isoNow, writeJson } from './lib.mjs';

            const out = path.resolve('evidence/lighthouse');
            await ensureDir(out);
            const serverOut = await fsp.open(path.join(out, 'server.stdout.log'), 'w');
            const serverErr = await fsp.open(path.join(out, 'server.stderr.log'), 'w');
            const server = spawn('python3', ['-m', 'http.server', '4321', '--bind', '127.0.0.1', '--directory', 'dist'], { stdio: ['ignore', serverOut.fd, serverErr.fd] });
            async function waitForServer() {
              for (let i = 0; i < 80; i += 1) {
                try { const response = await fetch('http://127.0.0.1:4321/'); if (response.ok) return; } catch {}
                await new Promise((resolve) => setTimeout(resolve, 250));
              }
              throw new Error('static server did not become ready');
            }
            async function runOne(id, url, extra) {
              const reportPath = path.join(out, `${id}.report.json`);
              const stdoutPath = path.join(out, `${id}.stdout.log`);
              const stderrPath = path.join(out, `${id}.stderr.log`);
              const args = [
                'node_modules/lighthouse/cli/index.js', url,
                '--quiet', '--output=json', `--output-path=${reportPath}`,
                '--only-categories=performance,accessibility,best-practices,seo',
                `--chrome-path=${chromium.executablePath()}`,
                '--chrome-flags=--headless=new --no-sandbox --disable-dev-shm-usage',
                ...extra
              ];
              const started = isoNow();
              const stdout = await fsp.open(stdoutPath, 'w');
              const stderr = await fsp.open(stderrPath, 'w');
              const code = await new Promise((resolve) => {
                const child = spawn(process.execPath, args, { stdio: ['ignore', stdout.fd, stderr.fd] });
                child.on('close', resolve);
              });
              await stdout.close(); await stderr.close();
              return { id, url, command: [process.execPath, ...args], startTimestampUtc: started, endTimestampUtc: isoNow(), exitCode: code, reportPath };
            }
            let commands = [];
            try {
              await waitForServer();
              commands.push(await runOne('home-desktop', 'http://127.0.0.1:4321/', ['--form-factor=desktop', '--screenEmulation.mobile=false', '--throttling-method=provided']));
              commands.push(await runOne('project-mobile', 'http://127.0.0.1:4321/work/non-core-real-estate/', []));
            } finally {
              server.kill('SIGTERM');
              await serverOut.close(); await serverErr.close();
            }
            const summaries = [];
            for (const command of commands) {
              if (command.exitCode !== 0) continue;
              const report = JSON.parse(await fsp.readFile(command.reportPath, 'utf8'));
              summaries.push({
                id: command.id,
                requestedUrl: report.requestedUrl,
                finalUrl: report.finalUrl,
                fetchTime: report.fetchTime,
                lighthouseVersion: report.lighthouseVersion,
                categories: Object.fromEntries(Object.entries(report.categories).map(([key, value]) => [key, Math.round((value.score || 0) * 100)])),
                metrics: {
                  firstContentfulPaintMs: report.audits['first-contentful-paint']?.numericValue,
                  largestContentfulPaintMs: report.audits['largest-contentful-paint']?.numericValue,
                  totalBlockingTimeMs: report.audits['total-blocking-time']?.numericValue,
                  cumulativeLayoutShift: report.audits['cumulative-layout-shift']?.numericValue,
                  speedIndexMs: report.audits['speed-index']?.numericValue
                }
              });
            }
            await writeJson(path.join(out, 'commands.json'), { commands });
            await writeJson(path.join(out, 'summary.json'), { schema: 'davidanderle.r7e.lighthouse-measurement.v1', summaries });
            const failed = commands.filter((x) => x.exitCode !== 0);
            if (failed.length) throw new Error(`Lighthouse command failures: ${failed.map((x) => x.id).join(', ')}`);
            console.log(JSON.stringify(summaries, null, 2));
        """),
        "scripts/test-wrangler-preview.mjs": d("""
            import fsp from 'node:fs/promises';
            import path from 'node:path';
            import { spawn } from 'node:child_process';
            import { ensureDir, isoNow, writeJson } from './lib.mjs';

            const out = path.resolve('evidence/wrangler-preview');
            await ensureDir(out);
            const stdout = await fsp.open(path.join(out, 'stdout.log'), 'w');
            const stderr = await fsp.open(path.join(out, 'stderr.log'), 'w');
            const command = [path.resolve('node_modules/.bin/wrangler'), 'dev', '--local', '--port', '8787'];
            const started = isoNow();
            const child = spawn(command[0], command.slice(1), { stdio: ['ignore', stdout.fd, stderr.fd] });
            const observations = [];
            const errors = [];
            try {
              let ready = false;
              for (let i = 0; i < 120; i += 1) {
                try { const response = await fetch('http://127.0.0.1:8787/'); if (response.status === 200) { ready = true; break; } } catch {}
                await new Promise((resolve) => setTimeout(resolve, 250));
              }
              if (!ready) throw new Error('wrangler local preview did not become ready');
              for (const [id, url, redirect] of [
                ['home', 'http://127.0.0.1:8787/', 'follow'],
                ['custom-404', 'http://127.0.0.1:8787/r7e-route-that-does-not-exist', 'manual'],
                ['legacy-redirect', 'http://127.0.0.1:8787/projects', 'manual']
              ]) {
                const response = await fetch(url, { redirect });
                const body = await response.text();
                const row = { id, url, status: response.status, location: response.headers.get('location'), contentSecurityPolicy: response.headers.get('content-security-policy'), xContentTypeOptions: response.headers.get('x-content-type-options'), bodyContainsCustom404: body.includes('data-custom-404="bearing"') };
                observations.push(row);
              }
              const home = observations.find((x) => x.id === 'home');
              const missing = observations.find((x) => x.id === 'custom-404');
              const redirect = observations.find((x) => x.id === 'legacy-redirect');
              if (home?.status !== 200) errors.push(`home status ${home?.status}`);
              if (!home?.contentSecurityPolicy) errors.push('CSP response header absent');
              if (missing?.status !== 404 || !missing.bodyContainsCustom404) errors.push('custom 404 behavior not observed');
              if (![301, 302, 307, 308].includes(redirect?.status)) errors.push(`legacy redirect status ${redirect?.status}`);
            } finally {
              child.kill('SIGTERM');
              await stdout.close(); await stderr.close();
            }
            const report = { schema: 'davidanderle.r7e.wrangler-preview.v1', command, startTimestampUtc: started, endTimestampUtc: isoNow(), observations, errors };
            await writeJson(path.join(out, 'report.json'), report);
            if (errors.length) { console.error(errors.join('\n')); process.exit(2); }
            console.log(JSON.stringify(report, null, 2));
        """),
        "scripts/verify-reproducibility.mjs": d("""
            import fsp from 'node:fs/promises';
            import path from 'node:path';
            import { spawn } from 'node:child_process';
            import { ensureDir, isoNow, treeManifest, writeJson } from './lib.mjs';

            const out = path.resolve('evidence/reproducibility');
            const workRoot = path.join(out, 'work');
            await fsp.rm(workRoot, { recursive: true, force: true });
            await ensureDir(workRoot);

            async function copySource(destination) {
              await fsp.cp(process.cwd(), destination, {
                recursive: true,
                filter: (source) => {
                  const rel = path.relative(process.cwd(), source);
                  const first = rel.split(path.sep)[0];
                  return !['node_modules', 'evidence', 'dist', 'dist-scale', 'R7E_PACKAGE', 'R7E_OUTPUT', '.astro'].includes(first);
                }
              });
              await fsp.mkdir(path.join(destination, 'src/content/scale'), { recursive: true });
              for (const file of await fsp.readdir(path.join(destination, 'src/content/scale'))) if (file.endsWith('.md')) await fsp.rm(path.join(destination, 'src/content/scale', file));
            }

            async function run(id, cwd, command, env = {}) {
              const stdoutPath = path.join(out, `${id}.stdout.log`);
              const stderrPath = path.join(out, `${id}.stderr.log`);
              const stdout = await fsp.open(stdoutPath, 'w');
              const stderr = await fsp.open(stderrPath, 'w');
              const started = isoNow();
              const code = await new Promise((resolve) => {
                const child = spawn(command[0], command.slice(1), { cwd, env: { ...process.env, ...env }, stdio: ['ignore', stdout.fd, stderr.fd] });
                child.on('close', resolve);
              });
              await stdout.close(); await stderr.close();
              return { id, command, cwd, startTimestampUtc: started, endTimestampUtc: isoNow(), exitCode: code, stdoutPath, stderrPath };
            }

            const a = path.join(workRoot, 'a');
            const b = path.join(workRoot, 'b');
            await copySource(a); await copySource(b);
            const commands = [];
            for (const [label, cwd] of [['a', a], ['b', b]]) {
              commands.push(await run(`${label}-npm-ci`, cwd, ['npm', 'ci']));
              if (commands.at(-1).exitCode !== 0) break;
              commands.push(await run(`${label}-build`, cwd, ['npm', 'run', 'build'], { SOURCE_DATE_EPOCH: '1787961600', TZ: 'UTC' }));
              if (commands.at(-1).exitCode !== 0) break;
            }
            let manifestA = null; let manifestB = null; let equal = false; let differences = [];
            if (commands.every((x) => x.exitCode === 0) && commands.length === 4) {
              manifestA = await treeManifest(path.join(a, 'dist'));
              manifestB = await treeManifest(path.join(b, 'dist'));
              equal = manifestA.treeSha256 === manifestB.treeSha256;
              if (!equal) {
                const left = new Map(manifestA.manifest.map((x) => [x.path, x.sha256]));
                const right = new Map(manifestB.manifest.map((x) => [x.path, x.sha256]));
                for (const key of [...new Set([...left.keys(), ...right.keys()])].sort()) if (left.get(key) !== right.get(key)) differences.push({ path: key, a: left.get(key), b: right.get(key) });
              }
            }
            const report = { schema: 'davidanderle.r7e.reproducibility.v1', commands, buildA: manifestA && { files: manifestA.files, bytes: manifestA.bytes, treeSha256: manifestA.treeSha256 }, buildB: manifestB && { files: manifestB.files, bytes: manifestB.bytes, treeSha256: manifestB.treeSha256 }, equal, differences };
            await writeJson(path.join(out, 'report.json'), report);
            await fsp.rm(workRoot, { recursive: true, force: true });
            if (!equal) { console.error(JSON.stringify(report, null, 2)); process.exit(2); }
            console.log(JSON.stringify(report, null, 2));
        """),
    }
