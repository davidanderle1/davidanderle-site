#!/usr/bin/env node
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const [runRootArg, distRootArg, outputArg, portArg = '4197'] = process.argv.slice(2);
if (!runRootArg || !distRootArg || !outputArg) {
  console.error('Usage: r7f-independent-browser-audit.mjs <run-root> <dist-root> <output-dir> [port]');
  process.exit(2);
}

const runRoot = path.resolve(runRootArg);
const distRoot = path.resolve(distRootArg);
const outputDir = path.resolve(outputArg);
const port = Number(portArg);
const baseURL = `http://127.0.0.1:${port}`;
const noJsScreenshot = path.join(outputDir, 'independent-no-js-vce-390.png');
const enhancedScreenshot = path.join(outputDir, 'independent-vce-enhanced-price-impact-390.png');
const reportPath = path.join(outputDir, 'report.json');
const serverStdoutPath = path.join(outputDir, 'server.stdout.txt');
const serverStderrPath = path.join(outputDir, 'server.stderr.txt');

const routes = [
  { name: 'home', url: '/', heading: 'David Anderle' },
  { name: 'work', url: '/work/', heading: 'Work.' },
  { name: 'merkle', url: '/work/merkle-poseidon/', heading: 'Merkle Commitments with Poseidon in Rust' },
  { name: 'vce', url: '/work/volatility-cascade-engine/', heading: 'Volatility Cascade Engine' },
  { name: 'writing', url: '/writing/', heading: 'Writing.' },
  { name: 'article', url: '/writing/protecting-retail-investors/', heading: 'Protecting Retail Investors: A Framework for Transparency and Risk Controls in High-Volatility Trading' },
  { name: 'archive', url: '/archive/', heading: 'Record.' },
  { name: 'about', url: '/about/', heading: 'Current context.' },
  { name: 'about-no-photo', url: '/about/no-photo/', heading: 'David Anderle.' },
  { name: 'cv', url: '/cv/', heading: 'Facts.' },
  { name: 'contact', url: '/contact/', heading: 'Contact.' },
  { name: 'privacy', url: '/privacy/', heading: 'Privacy.' },
  { name: 'security', url: '/security/', heading: 'Security.' },
  { name: '404', url: '/404.html', heading: 'Off route.' },
];

class AuditFailure extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.name = 'AuditFailure';
    this.code = code;
    this.details = details;
  }
}

function ensure(condition, code, message, details = {}) {
  if (!condition) throw new AuditFailure(code, message, details);
}

function sha256File(file) {
  return createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

function normalizeText(value) {
  return String(value ?? '').replace(/\s+/g, ' ').trim();
}

async function waitForServer(server) {
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (server.exitCode !== null) {
      throw new AuditFailure('SERVER_EXITED', `Static server exited with code ${server.exitCode}`);
    }
    try {
      const response = await fetch(`${baseURL}/`, { signal: AbortSignal.timeout(1_000) });
      if (response.status === 200) return;
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  throw new AuditFailure('SERVER_TIMEOUT', `Static server did not become ready at ${baseURL}`);
}

async function stopServer(server) {
  if (!server || server.exitCode !== null) return;
  server.kill('SIGTERM');
  await Promise.race([
    new Promise(resolve => server.once('exit', resolve)),
    new Promise(resolve => setTimeout(resolve, 5_000)),
  ]);
  if (server.exitCode === null) server.kill('SIGKILL');
}

fs.rmSync(outputDir, { recursive: true, force: true });
fs.mkdirSync(outputDir, { recursive: true });
ensure(fs.existsSync(path.join(runRoot, 'package.json')), 'RUN_ROOT_INVALID', 'Run root lacks package.json', { runRoot });
ensure(fs.existsSync(path.join(runRoot, 'scripts', 'serve-dist.mjs')), 'SERVER_SCRIPT_MISSING', 'Run root lacks scripts/serve-dist.mjs', { runRoot });
ensure(fs.existsSync(path.join(distRoot, 'index.html')), 'DIST_INVALID', 'Dist root lacks index.html', { distRoot });

const requireFromRun = createRequire(path.join(runRoot, 'package.json'));
const { chromium } = requireFromRun('@playwright/test');
const serverStdout = fs.openSync(serverStdoutPath, 'w');
const serverStderr = fs.openSync(serverStderrPath, 'w');
const server = spawn(process.execPath, [path.join(runRoot, 'scripts', 'serve-dist.mjs'), distRoot], {
  cwd: runRoot,
  env: { ...process.env, HOST: '127.0.0.1', PORT: String(port) },
  stdio: ['ignore', serverStdout, serverStderr],
});

let browser;
const report = {
  designation: 'R7F_V4_INDEPENDENT_BROWSER_AUDIT',
  passed: false,
  runRoot,
  distRoot,
  baseURL,
  routeCountExpected: routes.length,
  noJavaScript: null,
  enhancement: null,
  ordinaryRouteIsolation: null,
  failure: null,
};

try {
  await waitForServer(server);
  browser = await chromium.launch({ headless: true });

  const noJsContext = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
  const noJsPage = await noJsContext.newPage();
  const noJsRows = [];
  let noJsVce = null;
  for (const route of routes) {
    const scriptRequests = [];
    const listener = request => {
      if (request.resourceType() === 'script') scriptRequests.push(request.url());
    };
    noJsPage.on('request', listener);
    const response = await noJsPage.goto(`${baseURL}${route.url}`, { waitUntil: 'load' });
    ensure(response, 'NO_RESPONSE', `No response for ${route.url}`, { route });
    ensure(response.status() === 200, 'STATUS_MISMATCH', `Expected 200 for ${route.url}`, { route, actual: response.status() });
    const finalPathname = new URL(noJsPage.url()).pathname;
    ensure(finalPathname === route.url, 'PATHNAME_MISMATCH', `Final pathname mismatch for ${route.url}`, { route, actual: finalPathname });
    const main = noJsPage.locator('main');
    ensure(await main.count() === 1, 'MAIN_COUNT', `Expected exactly one main for ${route.url}`, { route, actual: await main.count() });
    ensure(await main.isVisible(), 'MAIN_NOT_VISIBLE', `Main is not visible for ${route.url}`, { route });
    const heading = normalizeText(await main.locator('h1').first().innerText());
    ensure(heading === route.heading, 'HEADING_MISMATCH', `H1 mismatch for ${route.url}`, { route, actual: heading });
    const mainText = normalizeText(await main.innerText());
    ensure(mainText.length > 20, 'MAIN_TEXT_TOO_SHORT', `Essential content is too short for ${route.url}`, { route, characters: mainText.length });
    if (route.name !== 'vce') {
      ensure(scriptRequests.length === 0, 'NO_JS_ORDINARY_SCRIPT_REQUEST', `Ordinary no-JS route requested a script: ${route.url}`, { route, scriptRequests });
    }
    if (route.name === 'about-no-photo') {
      ensure(await main.locator('img').count() === 0, 'NO_PHOTO_ROUTE_IMAGE', 'No-photo route contains an image', { route });
    }
    if (route.name === 'vce') {
      const panels = main.locator('.sequence-list > li');
      const panelCount = await panels.count();
      let visiblePanelCount = 0;
      for (let index = 0; index < panelCount; index += 1) {
        if (await panels.nth(index).isVisible()) visiblePanelCount += 1;
      }
      const status = normalizeText(await main.locator('.sequence-status').innerText());
      ensure(panelCount === 4, 'NO_JS_VCE_PANEL_COUNT', 'No-JS VCE panel count must be four', { panelCount });
      ensure(visiblePanelCount === 4, 'NO_JS_VCE_VISIBILITY', 'All four VCE panels must remain visible without JavaScript', { visiblePanelCount });
      ensure(status === 'Static sequence: all steps visible.', 'NO_JS_VCE_STATUS', 'Unexpected no-JS VCE status', { status });
      await noJsPage.screenshot({ path: noJsScreenshot, fullPage: true });
      noJsVce = {
        panelCount,
        visiblePanelCount,
        status,
        scriptRequests,
        screenshot: path.basename(noJsScreenshot),
        screenshotSha256: sha256File(noJsScreenshot),
      };
    }
    noJsRows.push({
      name: route.name,
      url: route.url,
      finalPathname,
      status: response.status(),
      heading,
      mainTextCharacters: mainText.length,
      scriptRequestCount: scriptRequests.length,
    });
    noJsPage.off('request', listener);
  }
  ensure(noJsRows.length === routes.length, 'NO_JS_ROUTE_COUNT', 'No-JS route coverage is incomplete', { expected: routes.length, actual: noJsRows.length });
  ensure(noJsVce !== null, 'NO_JS_VCE_MISSING', 'No-JS VCE evidence was not captured');
  report.noJavaScript = { javaScriptEnabled: false, routeCount: noJsRows.length, routes: noJsRows, vce: noJsVce };
  await noJsContext.close();

  const enhancedContext = await browser.newContext({ javaScriptEnabled: true, viewport: { width: 390, height: 844 } });
  const enhancedPage = await enhancedContext.newPage();
  const vceScriptRequests = [];
  enhancedPage.on('request', request => {
    if (request.resourceType() === 'script') vceScriptRequests.push(request.url());
  });
  const vceResponse = await enhancedPage.goto(`${baseURL}/work/volatility-cascade-engine/`, { waitUntil: 'networkidle' });
  ensure(vceResponse?.status() === 200, 'ENHANCEMENT_STATUS', 'Enhanced VCE route did not return 200', { actual: vceResponse?.status() ?? null });
  const component = enhancedPage.locator('vce-sequence');
  const buttons = component.locator('[data-step]');
  const panels = component.locator('[data-panel]');
  const status = component.locator('.sequence-status');
  ensure(await component.getAttribute('data-ready') === 'true', 'ENHANCEMENT_NOT_READY', 'VCE custom element did not become ready');
  ensure(await buttons.count() === 4, 'ENHANCEMENT_BUTTON_COUNT', 'VCE must expose four buttons', { actual: await buttons.count() });
  ensure(await panels.count() === 4, 'ENHANCEMENT_PANEL_COUNT', 'VCE must expose four panels', { actual: await panels.count() });

  const selectedIndex = async () => buttons.evaluateAll(elements => elements.findIndex(element => element.getAttribute('aria-pressed') === 'true'));
  const visiblePanelCount = async () => {
    let visible = 0;
    for (let index = 0; index < await panels.count(); index += 1) if (await panels.nth(index).isVisible()) visible += 1;
    return visible;
  };
  ensure(await selectedIndex() === 0, 'ENHANCEMENT_INITIAL_SELECTION', 'Initial selected VCE step must be zero', { actual: await selectedIndex() });
  ensure(await visiblePanelCount() === 1, 'ENHANCEMENT_INITIAL_VISIBILITY', 'Exactly one VCE panel must be visible after enhancement', { actual: await visiblePanelCount() });
  ensure(normalizeText(await status.innerText()) === 'Showing Initial loss.', 'ENHANCEMENT_INITIAL_STATUS', 'Unexpected initial VCE status', { actual: normalizeText(await status.innerText()) });

  await buttons.nth(2).click();
  ensure(await selectedIndex() === 2, 'ENHANCEMENT_CLICK_SELECTION', 'Click did not select Forced sales', { actual: await selectedIndex() });
  ensure(await visiblePanelCount() === 1 && await panels.nth(2).isVisible(), 'ENHANCEMENT_CLICK_VISIBILITY', 'Forced-sales panel visibility is incorrect');
  ensure(normalizeText(await status.innerText()) === 'Showing Forced sales. Essential content remains available without JavaScript.', 'ENHANCEMENT_CLICK_STATUS', 'Unexpected click status', { actual: normalizeText(await status.innerText()) });

  await buttons.nth(2).focus();
  await enhancedPage.keyboard.press('ArrowRight');
  ensure(await buttons.nth(3).evaluate(element => element === document.activeElement), 'ENHANCEMENT_ARROW_FOCUS', 'ArrowRight did not move focus to Price impact');
  ensure(await selectedIndex() === 3, 'ENHANCEMENT_ARROW_SELECTION', 'ArrowRight did not select Price impact', { actual: await selectedIndex() });
  ensure(await visiblePanelCount() === 1 && await panels.nth(3).isVisible(), 'ENHANCEMENT_ARROW_VISIBILITY', 'Price-impact panel visibility is incorrect');
  ensure(normalizeText(await status.innerText()) === 'Showing Price impact. Essential content remains available without JavaScript.', 'ENHANCEMENT_ARROW_STATUS', 'Unexpected ArrowRight status', { actual: normalizeText(await status.innerText()) });
  await enhancedPage.screenshot({ path: enhancedScreenshot, fullPage: true });

  await enhancedPage.keyboard.press('Home');
  ensure(await buttons.nth(0).evaluate(element => element === document.activeElement), 'ENHANCEMENT_HOME_FOCUS', 'Home did not return focus to the first step');
  ensure(await selectedIndex() === 0, 'ENHANCEMENT_HOME_SELECTION', 'Home did not return selection to the first step', { actual: await selectedIndex() });
  ensure(await visiblePanelCount() === 1 && await panels.nth(0).isVisible(), 'ENHANCEMENT_HOME_VISIBILITY', 'Initial panel visibility after Home is incorrect');
  const homeStatus = normalizeText(await status.innerText());
  ensure(homeStatus === 'Showing Initial loss. Essential content remains available without JavaScript.', 'ENHANCEMENT_HOME_STATUS', 'Unexpected Home status', { actual: homeStatus });
  const uniqueVceScripts = [...new Set(vceScriptRequests.filter(url => /\/assets\/js\/vce-sequence\.[a-f0-9]+\.js(?:\?|$)/.test(url)))];
  ensure(uniqueVceScripts.length === 1, 'ENHANCEMENT_SCRIPT_REQUEST', 'Expected exactly one hashed VCE script request', { scriptRequests: vceScriptRequests, matching: uniqueVceScripts });
  report.enhancement = {
    route: '/work/volatility-cascade-engine/',
    componentReady: await component.getAttribute('data-ready'),
    buttonCount: await buttons.count(),
    panelCount: await panels.count(),
    selectedIndexAfterHome: await selectedIndex(),
    visiblePanelCountAfterHome: await visiblePanelCount(),
    statusAfterHome: homeStatus,
    scriptRequests: vceScriptRequests,
    matchingScriptRequests: uniqueVceScripts,
    screenshotSelectedIndex: 3,
    screenshot: path.basename(enhancedScreenshot),
    screenshotSha256: sha256File(enhancedScreenshot),
  };
  await enhancedContext.close();

  const isolationRows = [];
  for (const route of routes.filter(item => item.name !== 'vce')) {
    const context = await browser.newContext({ javaScriptEnabled: true, viewport: { width: 390, height: 844 } });
    const page = await context.newPage();
    const scriptRequests = [];
    page.on('request', request => {
      if (request.resourceType() === 'script') scriptRequests.push(request.url());
    });
    const response = await page.goto(`${baseURL}${route.url}`, { waitUntil: 'networkidle' });
    ensure(response?.status() === 200, 'ISOLATION_STATUS', `Ordinary route did not return 200: ${route.url}`, { actual: response?.status() ?? null });
    ensure(scriptRequests.length === 0, 'ORDINARY_ROUTE_SCRIPT_REQUEST', `Ordinary route requested executable JavaScript: ${route.url}`, { route, scriptRequests });
    isolationRows.push({ name: route.name, url: route.url, status: response.status(), scriptRequestCount: scriptRequests.length });
    await context.close();
  }
  ensure(isolationRows.length === routes.length - 1, 'ISOLATION_ROUTE_COUNT', 'Ordinary-route isolation coverage is incomplete', { expected: routes.length - 1, actual: isolationRows.length });
  report.ordinaryRouteIsolation = { routeCount: isolationRows.length, routes: isolationRows };
  report.passed = true;
} catch (error) {
  const failure = error instanceof AuditFailure
    ? { code: error.code, message: error.message, details: error.details }
    : { code: 'UNEXPECTED_ERROR', message: error instanceof Error ? error.stack ?? error.message : String(error), details: {} };
  report.failure = failure;
  process.exitCode = 1;
} finally {
  if (browser) await browser.close().catch(() => {});
  await stopServer(server).catch(() => {});
  fs.closeSync(serverStdout);
  fs.closeSync(serverStderr);
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify(report, null, 2));
}
