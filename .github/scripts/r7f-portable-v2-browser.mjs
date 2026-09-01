#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import crypto from 'node:crypto';

const [baseUrl, outputPath] = process.argv.slice(2);
if (!baseUrl || !outputPath) {
  throw new Error('usage: r7f-portable-v2-browser.mjs BASE_URL OUTPUT_JSON');
}

const candidateRequire = createRequire(path.join(process.cwd(), 'package.json'));
let playwright;
try {
  playwright = candidateRequire('playwright');
} catch {
  playwright = candidateRequire('@playwright/test');
}
const axeSource = fs.readFileSync(candidateRequire.resolve('axe-core/axe.min.js'), 'utf8');

const routes = [
  '/',
  '/work/',
  '/work/volatility-cascade-engine/',
  '/work/merkle-poseidon/',
  '/writing/',
  '/writing/protecting-retail-investors/',
  '/archive/',
  '/about/',
  '/about/no-photo/',
  '/cv/',
  '/contact/',
  '/privacy/',
  '/security/',
  '/404.html',
];
const viewports = [
  { name: 'mobile-320', width: 320, height: 800 },
  { name: 'mobile-375', width: 375, height: 812 },
  { name: 'tablet-768', width: 768, height: 1024 },
  { name: 'desktop-1440', width: 1440, height: 900 },
];
const engines = [
  ['chromium', playwright.chromium],
  ['firefox', playwright.firefox],
  ['webkit', playwright.webkit],
];
const axeViewports = new Set(['mobile-375', 'desktop-1440']);
const failures = [];
const results = [];
const axeNodes = [];

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  }
  return value;
}
function digest(value) {
  return crypto.createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex');
}
function addFailure(kind, detail) {
  failures.push({ kind, ...detail });
}

for (const [engineName, engine] of engines) {
  const browser = await engine.launch({ headless: true });
  try {
    for (const viewport of viewports) {
      const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
        reducedMotion: 'reduce',
        colorScheme: 'dark',
      });
      try {
        for (const route of routes) {
          const page = await context.newPage();
          const consoleErrors = [];
          const pageErrors = [];
          const failedRequests = [];
          const requests = [];
          page.on('console', (message) => {
            if (message.type() === 'error') consoleErrors.push(message.text());
          });
          page.on('pageerror', (error) => pageErrors.push(String(error)));
          page.on('requestfailed', (request) => failedRequests.push({ url: request.url(), failure: request.failure()?.errorText ?? null }));
          page.on('request', (request) => requests.push(request.url()));
          const url = new URL(route, baseUrl).href;
          let response;
          try {
            response = await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
          } catch (error) {
            addFailure('navigation', { engine: engineName, viewport: viewport.name, route, error: String(error) });
            await page.close();
            continue;
          }
          const status = response?.status() ?? 0;
          const dom = await page.evaluate(() => {
            const executableScripts = [...document.scripts]
              .filter((script) => (script.type || '').toLowerCase() !== 'application/ld+json')
              .map((script) => ({ type: script.type || 'classic', src: script.src || null, inlineBytes: script.src ? 0 : (script.textContent || '').length }));
            return {
              title: document.title,
              lang: document.documentElement.lang,
              h1Count: document.querySelectorAll('h1').length,
              mainCount: document.querySelectorAll('main').length,
              navCount: document.querySelectorAll('nav').length,
              horizontalOverflow: Math.max(document.documentElement.scrollWidth, document.body?.scrollWidth || 0) - document.documentElement.clientWidth,
              executableScripts,
              brokenImages: [...document.images]
                .filter((image) => !image.complete || image.naturalWidth === 0)
                .map((image) => image.currentSrc || image.src),
              duplicateIds: [...document.querySelectorAll('[id]')]
                .map((element) => element.id)
                .filter((id, index, all) => all.indexOf(id) !== index),
              activeElement: document.activeElement?.tagName || null,
            };
          });
          const offOrigin = requests.filter((requestUrl) => {
            const parsed = new URL(requestUrl);
            const expected = new URL(baseUrl);
            return parsed.origin !== expected.origin;
          });
          const isEnhancedRoute = route === '/work/volatility-cascade-engine/';
          if (status !== 200) addFailure('http-status', { engine: engineName, viewport: viewport.name, route, status });
          if (!dom.title) addFailure('missing-title', { engine: engineName, viewport: viewport.name, route });
          if (dom.lang !== 'en') addFailure('document-lang', { engine: engineName, viewport: viewport.name, route, lang: dom.lang });
          if (dom.h1Count !== 1) addFailure('h1-count', { engine: engineName, viewport: viewport.name, route, count: dom.h1Count });
          if (dom.mainCount !== 1) addFailure('main-count', { engine: engineName, viewport: viewport.name, route, count: dom.mainCount });
          if (dom.horizontalOverflow > 1) addFailure('horizontal-overflow', { engine: engineName, viewport: viewport.name, route, pixels: dom.horizontalOverflow });
          if (dom.brokenImages.length) addFailure('broken-images', { engine: engineName, viewport: viewport.name, route, images: dom.brokenImages });
          if (dom.duplicateIds.length) addFailure('duplicate-ids', { engine: engineName, viewport: viewport.name, route, ids: [...new Set(dom.duplicateIds)] });
          if (consoleErrors.length) addFailure('console-error', { engine: engineName, viewport: viewport.name, route, errors: consoleErrors });
          if (pageErrors.length) addFailure('page-error', { engine: engineName, viewport: viewport.name, route, errors: pageErrors });
          if (failedRequests.length) addFailure('request-failed', { engine: engineName, viewport: viewport.name, route, requests: failedRequests });
          if (offOrigin.length) addFailure('off-origin-network', { engine: engineName, viewport: viewport.name, route, requests: offOrigin });
          if (!isEnhancedRoute && dom.executableScripts.length !== 0) {
            addFailure('ordinary-route-javascript', { engine: engineName, viewport: viewport.name, route, scripts: dom.executableScripts });
          }
          if (isEnhancedRoute && (dom.executableScripts.length !== 1 || !dom.executableScripts[0].src || dom.executableScripts[0].type !== 'module')) {
            addFailure('enhanced-route-boundary', { engine: engineName, viewport: viewport.name, route, scripts: dom.executableScripts });
          }

          let axe = null;
          if (engineName === 'chromium' && axeViewports.has(viewport.name)) {
            await page.addScriptTag({ content: axeSource });
            axe = await page.evaluate(async () => {
              const result = await globalThis.axe.run(document, {
                resultTypes: ['violations', 'incomplete'],
                rules: { 'color-contrast': { enabled: true } },
              });
              return {
                violations: result.violations,
                incomplete: result.incomplete,
              };
            });
            if (axe.violations.length) {
              addFailure('axe-violations', {
                engine: engineName,
                viewport: viewport.name,
                route,
                rules: axe.violations.map((item) => ({ id: item.id, impact: item.impact, nodes: item.nodes.length })),
              });
            }
            for (const finding of axe.incomplete) {
              for (const node of finding.nodes) {
                const record = {
                  route,
                  viewport: viewport.name,
                  rule: finding.id,
                  impact: finding.impact,
                  target: node.target,
                  html: node.html,
                  failureSummary: node.failureSummary,
                  any: node.any,
                  all: node.all,
                  none: node.none,
                };
                axeNodes.push({ ...record, fingerprint: digest(record) });
              }
            }
          }
          results.push({
            engine: engineName,
            viewport: viewport.name,
            route,
            status,
            requestCount: requests.length,
            offOriginRequestCount: offOrigin.length,
            executableScriptCount: dom.executableScripts.length,
            horizontalOverflow: dom.horizontalOverflow,
            axeViolationCount: axe?.violations.length ?? null,
            axeIncompleteNodeCount: axe ? axe.incomplete.reduce((sum, finding) => sum + finding.nodes.length, 0) : null,
          });
          await page.close();
        }
      } finally {
        await context.close();
      }
    }
  } finally {
    await browser.close();
  }
}

const uniqueFingerprints = new Set(axeNodes.map((node) => node.fingerprint));
if (uniqueFingerprints.size !== axeNodes.length) {
  addFailure('duplicate-axe-fingerprint', { total: axeNodes.length, unique: uniqueFingerprints.size });
}
const report = {
  schema: 'R7F_PORTABLE_BROWSER_AUDIT_V2',
  passed: failures.length === 0,
  baseUrl,
  engines: engines.map(([name]) => name),
  viewports,
  routes,
  metrics: {
    pageChecks: results.length,
    expectedPageChecks: engines.length * viewports.length * routes.length,
    axePageChecks: results.filter((row) => row.axeViolationCount !== null).length,
    axeViolationCount: results.reduce((sum, row) => sum + (row.axeViolationCount || 0), 0),
    axeIncompleteNodeCount: axeNodes.length,
    axeUniqueFingerprintCount: uniqueFingerprints.size,
    offOriginRequestCount: results.reduce((sum, row) => sum + row.offOriginRequestCount, 0),
  },
  failures,
  results,
  axeNodes,
  axeFingerprintSetSha256: digest([...uniqueFingerprints].sort()),
};
fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ passed: report.passed, metrics: report.metrics, failedChecks: failures.length }, null, 2));
if (!report.passed) process.exit(1);
