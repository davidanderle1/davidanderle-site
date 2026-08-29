import fs from 'node:fs';
import path from 'node:path';
import { parseMarkdownFile } from './lib/frontmatter.mjs';

const stressRoot = path.resolve('.r7e-tmp/stress');
const contentRoot = path.join(stressRoot, 'content');
const stressDist = path.join(stressRoot, 'dist');
const releaseDist = path.resolve('dist');
const reportPath = path.join(stressRoot, 'lineage.json');

const normalize = (value) => String(value).normalize('NFC').toLocaleLowerCase('en-US');

const files = fs.readdirSync(path.join(contentRoot, 'work'))
  .filter((name) => name.endsWith('.md'))
  .sort();
if (files.length !== 500) throw new Error(`Expected exactly 500 stress WorkRecords, found ${files.length}`);

const records = files.map((name) => {
  const data = parseMarkdownFile(path.join(contentRoot, 'work', name)).data;
  return {
    file: name,
    immutableId: data.immutableId,
    canonicalSlug: data.canonicalSlug,
    route: data.route,
    testFixture: data.testFixture
  };
});

const required = ['immutableId','canonicalSlug','route'];
for (const record of records) {
  for (const key of required) if (!record[key]) throw new Error(`Missing ${key} in ${record.file}`);
  if (record.testFixture !== true) throw new Error(`Stress record is not marked testFixture: ${record.file}`);
  if (record.route !== `/work/${record.canonicalSlug}/`) throw new Error(`Route/slug mismatch in ${record.file}`);
}
for (const field of ['immutableId','canonicalSlug','route']) {
  const normalized = records.map((record) => normalize(record[field]));
  if (new Set(normalized).size !== 500) throw new Error(`${field} values are not unique under NFC + lowercase normalization`);
}

const expectedSlugs = new Set(records.map((record) => normalize(record.canonicalSlug)));
const detailSlugs = [];
for (const entry of fs.readdirSync(path.join(stressDist, 'work'), { withFileTypes: true })) {
  if (!entry.isDirectory()) continue;
  const index = path.join(stressDist, 'work', entry.name, 'index.html');
  if (fs.existsSync(index) && entry.name.startsWith('synthetic-test-record-')) detailSlugs.push(normalize(entry.name));
}
if (detailSlugs.length !== 500 || new Set(detailSlugs).size !== 500) throw new Error(`Expected 500 unique stress detail pages, found ${detailSlugs.length}`);
if (detailSlugs.some((slug) => !expectedSlugs.has(slug)) || [...expectedSlugs].some((slug) => !detailSlugs.includes(slug))) {
  throw new Error('Stress input/output route bijection failed');
}

const hrefs = (html) => [...html.matchAll(/href=["']([^"']+)["']/gi)].map((match) => match[1]);
const linkedStressSlugs = (file) => {
  const html = fs.readFileSync(file, 'utf8');
  return new Set(hrefs(html)
    .filter((href) => /^\/work\/synthetic-test-record-\d{3}\/(?:[#?].*)?$/.test(href))
    .map((href) => normalize(href.split(/[?#]/)[0].split('/').filter(Boolean).at(-1))));
};
const workIndexLinks = linkedStressSlugs(path.join(stressDist, 'work', 'index.html'));
const archiveLinks = linkedStressSlugs(path.join(stressDist, 'archive', 'index.html'));
if (workIndexLinks.size !== 500) throw new Error(`Stress /work/ index links ${workIndexLinks.size}/500 records`);
if (archiveLinks.size !== 500) throw new Error(`Stress /archive/ links ${archiveLinks.size}/500 records`);

let structuredDetailPages = 0;
for (const slug of expectedSlugs) {
  const html = fs.readFileSync(path.join(stressDist, 'work', slug, 'index.html'), 'utf8');
  if (/<script[^>]+type=["']application\/ld\+json["']/i.test(html)) structuredDetailPages++;
}
if (structuredDetailPages !== 500) throw new Error(`Structured data present on ${structuredDetailPages}/500 stress detail pages`);

function resolvesLocal(href) {
  if (!href.startsWith('/') || href.startsWith('//')) return true;
  const pathname = href.split(/[?#]/)[0];
  const candidate = path.join(stressDist, pathname.replace(/^\/+/, ''));
  return fs.existsSync(candidate) || fs.existsSync(path.join(candidate, 'index.html'));
}
const broken = [];
function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    return entry.isDirectory() ? walk(full) : [full];
  });
}
for (const htmlFile of walk(stressDist).filter((file) => file.endsWith('.html'))) {
  const html = fs.readFileSync(htmlFile, 'utf8');
  for (const href of hrefs(html)) if (!resolvesLocal(href)) broken.push({ file: path.relative(stressDist, htmlFile), href });
}
if (broken.length) throw new Error(`Broken local links in stress output: ${JSON.stringify(broken.slice(0, 20))}`);

const releaseHtml = walk(releaseDist).filter((file) => file.endsWith('.html')).map((file) => fs.readFileSync(file, 'utf8')).join('\n');
const leaked = records.filter((record) => releaseHtml.includes(record.canonicalSlug) || releaseHtml.includes(record.immutableId));
if (leaked.length) throw new Error(`Stress records leaked into production dist: ${leaked.slice(0, 10).map((record) => record.canonicalSlug).join(', ')}`);

const result = {
  passed: true,
  inputWorkRecords: 500,
  uniqueImmutableIds: 500,
  uniqueCanonicalSlugs: 500,
  uniqueCanonicalRoutes: 500,
  astroDetailPages: 500,
  workIndexLinks: 500,
  archiveLinks: 500,
  structuredDataDetailPages: 500,
  brokenLocalLinks: 0,
  productionContamination: 0
};
fs.writeFileSync(reportPath, JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify(result, null, 2));
