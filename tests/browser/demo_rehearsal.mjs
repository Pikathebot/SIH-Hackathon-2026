// Rehearse docs/DEMO_SCRIPT.md in headless Chrome and check every stated outcome.
//
//   cd tests/browser && npm install
//   node demo_rehearsal.mjs                      # real engine, http://localhost:3000
//   node demo_rehearsal.mjs --mock               # AI_SERVICE_MODE=mock: UI flow only, no content checks
//   node demo_rehearsal.mjs --base http://127.0.0.1:3000 --out ./out
//
// Chrome: CHROME_PATH, else the usual Windows/macOS/Linux install locations.
// Screenshots and downloads go to --out (default ./out). Exits 1 if any check fails.
import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const args = process.argv.slice(2);
const opt = (name, dflt) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : dflt; };
const MOCK = args.includes('--mock');
const BASE = opt('--base', 'http://localhost:3000').replace(/\/$/, '');
const HERE = path.dirname(fileURLToPath(import.meta.url));
const SD = path.resolve(HERE, '../../sample_data');
const OUT = path.resolve(opt('--out', path.join(HERE, 'out')));
const CHROME = process.env.CHROME_PATH || [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser',
].find((p) => fs.existsSync(p));
if (!CHROME) { console.error('Chrome not found; set CHROME_PATH.'); process.exit(2); }

fs.rmSync(OUT, { recursive: true, force: true });
const DL = path.join(OUT, 'downloads');
fs.mkdirSync(DL, { recursive: true });

const results = [];
const check = (step, ok, info = '') => { results.push([step, !!ok, info]); console.log(`${ok ? 'PASS' : 'FAIL'} ${step}${info ? '  -- ' + info : ''}`); };
/** A content check: enforced against the real engine, reported only in mock mode. */
const expect = (step, ok, info = '') => (MOCK ? console.log(`SKIP ${step} (mock)  -- ${info}`) : check(step, ok, info));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, defaultViewport: { width: 1440, height: 960 } });
const page = await browser.newPage();
const cdp = await page.createCDPSession();
await cdp.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: DL });
const pageErrors = [];
page.on('pageerror', (e) => { pageErrors.push(e.message); console.log('  [pageerror]', e.message); });
page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource/.test(m.text())) pageErrors.push(m.text()); });

let n = 0;
const shot = (name) => page.screenshot({ path: path.join(OUT, `${String(++n).padStart(2, '0')}-${name}.png`) });
const text = () => page.evaluate(() => document.body.textContent);
const clickText = (sel, t) => page.evaluate((sel, t) => {
  const el = [...document.querySelectorAll(sel)].find((e) => e.textContent.includes(t) && !e.disabled);
  if (el) el.click();
  return !!el;
}, sel, t);
const lastAnswer = () => page.evaluate(() => { const c = [...document.querySelectorAll('.border-l-3')]; return c[c.length - 1]?.innerText || ''; });
const lastBoxCount = () => page.evaluate(() => {
  const t = [...document.querySelectorAll('button')].map((b) => b.textContent).filter((s) => /^Boxes \(\d+\)$/.test(s)).at(-1);
  return t ? Number(t.match(/\d+/)[0]) : 0;
});

async function preset(title) {
  await clickText('button', 'Sample Questions');
  await sleep(500);
  const ok = await page.evaluate((title) => {
    const card = [...document.querySelectorAll('div.group')].find((d) => d.querySelector('h3')?.textContent.trim() === title);
    card?.querySelector('button')?.click();
    return !!card;
  }, title);
  if (!ok) throw new Error('no preset ' + title);
  await page.waitForFunction(() => !document.querySelector('form button[type=submit]')?.disabled, { timeout: 60000 });
}
async function analyze(name) {
  const before = (await page.$$('.border-l-3')).length;
  const t0 = Date.now();
  await clickText('form button[type=submit]', 'Analyze');
  await page.waitForFunction((b) => document.querySelectorAll('.border-l-3').length > b, { timeout: 600000 }, before);
  await sleep(800);
  await shot(name);
  return Date.now() - t0;
}
async function setQuery(q) { await page.click('#query-input', { clickCount: 3 }); await page.type('#query-input', q); }

try {
  // Step 1 — sign up
  await page.goto(`${BASE}/register`, { waitUntil: 'networkidle0' });
  await page.type('input[type=email]', `demo-${Date.now()}@example.com`);
  for (const p of await page.$$('input[type=password]')) await p.type('demo-password-123');
  await clickText('button[type=submit]', 'Create account');
  await page.waitForSelector('#query-input', { timeout: 30000 });
  await sleep(1500);
  check('pre-flight: top bar says AI Online', (await text()).includes('AI Online'));
  check('1 sign up', true);

  // Step 2 — caption, hover coordinates, details
  await preset('Scene Description');
  let ms = await analyze('2-caption');
  let a = await lastAnswer();
  check('2 caption answered', a.length > 40, `${ms} ms: ${a.slice(0, 90)}`);
  const box = (await page.$$('.cursor-crosshair')).at(-1);
  await box.scrollIntoView();
  const r = await box.boundingBox();
  await page.mouse.move(r.x + r.width / 2, r.y + r.height / 2);
  await sleep(300);
  const readout = await page.evaluate(() => [...document.querySelectorAll('.font-mono')].map((e) => e.textContent).find((t) => t.includes('Lat')));
  const extent = await page.evaluate(() => [...document.querySelectorAll('span')].map((e) => e.textContent).find((t) => t.startsWith('Extent:')));
  check('2 hover shows lat/lon and extent badge', !!readout && !!extent, `${readout} / ${extent}`);
  await clickText('button', 'Analysis Details');
  await sleep(500);
  check('2 details panel names the task', (await text()).includes('Image Captioning'));
  await shot('2-details');

  // Step 3 — yes/no
  await preset('Scene Description');
  await setQuery('Is there a river in this image?');
  ms = await analyze('3-river');
  a = await lastAnswer();
  expect('3 yes/no answered "No"', /^\s*No\b/.test(a), `${ms} ms: ${a.slice(0, 90)}`);

  // Step 4 — VQA on the port
  await preset('Visual Question Answering');
  ms = await analyze('4-port');
  a = await lastAnswer();
  expect('4 port VQA says "Yes"', /^\s*Yes\b/.test(a), `${ms} ms: ${a.slice(0, 90)}`);

  // Step 5 — localization + GeoJSON
  await preset('Object & Facility Localization');
  ms = await analyze('5-boxes');
  const nBoxes = await lastBoxCount();
  check('5 boxes drawn', nBoxes > 0, `${ms} ms: ${nBoxes} boxes`);
  expect('5 about 13 aircraft boxed (11-15)', nBoxes >= 11 && nBoxes <= 15, `${nBoxes}`);
  await page.evaluate(() => [...document.querySelectorAll('button')].filter((b) => b.textContent.includes('GeoJSON')).at(-1).click());
  await sleep(1500);
  const gj = fs.readdirSync(DL).find((f) => f.endsWith('.geojson'));
  const feats = gj ? JSON.parse(fs.readFileSync(path.join(DL, gj))).features : [];
  check('5 GeoJSON has one polygon per box', feats.filter((f) => f.geometry?.type === 'Polygon').length === nBoxes, `${gj}: ${feats.length} features`);

  // Step 6 — JP2 water mask
  await preset('Water & Land Cover Highlight');
  ms = await analyze('6-water');
  expect('6 mask shown with band-order notice', (await text()).includes('Band Order Unverified'), `${ms} ms`);

  // Step 7 — change detection
  await preset('Temporal Change Detection');
  ms = await analyze('7-change');
  a = await lastAnswer();
  check('7 change answer + split slider', (await text()).includes('Split:') && a.length > 40, `${ms} ms: ${a.slice(0, 90)}`);

  // Step 8 — fusion
  await preset('Optical + Radar (SAR) Fusion');
  ms = await analyze('8-fusion');
  a = await lastAnswer();
  check('8 fusion answered', a.length > 40, `${ms} ms`);
  const water = Number((a.match(/(\d+(?:\.\d+)?)% Water/) || [])[1]);
  expect('8 fusion reports cloud cover and ~52% water (45-60)', a.includes('cloud-covered') && water >= 45 && water <= 60, a.slice(0, 160));

  // Step 9 — history survives a reload; PDF report
  await page.reload({ waitUntil: 'networkidle0' });
  await sleep(1500);
  const cards = (await page.$$('.border-l-3')).length;
  check('9 reload keeps history', cards >= 7, `${cards} results after reload`);
  const popupP = new Promise((res) => browser.once('targetcreated', (t) => res(t)));
  await page.evaluate(() => [...document.querySelectorAll('button')].filter((b) => b.textContent.includes('PDF Report')).at(-1).click());
  const target = await Promise.race([popupP, sleep(5000).then(() => null)]);
  const popup = target && (await target.page());
  if (popup) {
    await sleep(1000);
    const ph = await popup.evaluate(() => document.body.innerText);
    check('9 PDF report window opens', ph.length > 200, ph.slice(0, 80).replace(/\n/g, ' '));
    await popup.close();
  } else check('9 PDF report window opens', false, 'no popup');

  // Step 10 — guardrail: two SAR images
  const input = await page.$('input[type=file]');
  await input.uploadFile(path.join(SD, 'sar/sar_port_rotterdam.tif'));
  await sleep(1500);
  await input.uploadFile(path.join(SD, 'cross_modal_fusion/penetrating_sar_scene.tif'));
  await sleep(1500);
  await page.evaluate(() => {
    const set = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
    for (const s of document.querySelectorAll('select')) { set.call(s, 'sar'); s.dispatchEvent(new Event('change', { bubbles: true })); }
  });
  await setQuery('Compare these radar scenes.');
  await sleep(500);
  await shot('10-guardrail');
  const disabled = await page.evaluate(() => document.querySelector('form button[type=submit]').disabled);
  check('10 two SAR: warning + Analyze disabled', disabled && (await text()).includes('Supported 2-image tasks'));
  for (let i = 0; i < 3; i++) { const b = await page.$('button[title="Remove image"]'); if (b) { await b.click(); await sleep(200); } }

  // Troubleshooting row: a missing sample file (simulate the SPA fallback serving index.html)
  await page.setRequestInterception(true);
  page.on('request', (req) => (req.url().includes('/samples/real_sentinel2_austria_tci.tif')
    ? req.respond({ status: 200, contentType: 'text/html', body: '<!doctype html><div id=root></div>' })
    : req.continue()));
  await clickText('button', 'Sample Questions');
  await sleep(400);
  await page.evaluate(() => [...document.querySelectorAll('div.group')]
    .find((d) => d.querySelector('h3')?.textContent.trim() === 'Scene Description').querySelector('button').click());
  await sleep(1500);
  check('troubleshooting: missing sample message', (await text()).includes('is missing. Run scripts/build_demo_samples.py'));
  await shot('missing-sample');

  check('no uncaught page errors', pageErrors.length === 0, pageErrors.slice(0, 3).join(' | '));
} catch (e) {
  check('ERROR', false, e.message);
  await shot('error').catch(() => {});
} finally {
  await browser.close();
  const passed = results.filter((r) => r[1]).length;
  console.log(`\n${passed}/${results.length} checks passed${MOCK ? ' (mock: content checks skipped)' : ''}; screenshots in ${OUT}`);
  process.exitCode = passed === results.length ? 0 : 1;
}
