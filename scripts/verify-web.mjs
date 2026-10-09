/**
 * verify-web.mjs — headless browser verification for the workbench.
 *
 * Serves `web/` over http and loads every route in Chrome, capturing:
 *   · whether the view actually rendered (not the "loading" placeholder)
 *   · every console error / uncaught exception
 *   · a PNG screenshot per route
 *
 * Why http and not file://: the app is designed to work from file:// too, but
 * http://localhost is the realistic deployment and avoids any file-URL
 * permission quirks, so failures here are unambiguous.
 *
 * Usage:
 *   node scripts/verify-web.mjs                 # all routes, screenshots
 *   node scripts/verify-web.mjs --only dashboard,jobs
 *   node scripts/verify-web.mjs --port 8791
 */
import { createServer } from 'node:http';
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join, resolve, extname, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const here = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(here, '..');
// Default to web/, but allow verifying any built output (e.g. dist/) via
// WEB_ROOT, so the published artifact gets tested and not just the source tree.
const WEB = process.env.WEB_ROOT ? resolve(process.env.WEB_ROOT) : join(ROOT, 'web');
const SHOTS = join(ROOT, 'docs', 'screenshots');

const argv = process.argv.slice(2);
const argVal = (name, dflt) => {
  const i = argv.indexOf(name);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : dflt;
};
const PORT = Number(argVal('--port', '8791'));
const ONLY = argVal('--only', '');

const ROUTES = [
  ['dashboard', '#/dashboard'],
  ['digest', '#/digest'],
  ['categories', '#/categories'],
  ['knowledge', '#/knowledge'],
  ['formulas', '#/formulas'],
  ['problems', '#/problems'],
  ['repos', '#/repos'],
  ['jobs', '#/jobs'],
  ['skills', '#/skills'],
  ['roadmap', '#/roadmap'],
  ['progress', '#/progress'],
  ['starred', '#/starred'],
  ['pipeline', '#/pipeline'],
].filter(([id]) => !ONLY || ONLY.split(',').includes(id));

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
};

function findChrome() {
  const cands = [
    process.env.CHROME_PATH,
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    join(process.env.LOCALAPPDATA || '', 'Google\\Chrome\\Application\\chrome.exe'),
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ].filter(Boolean);
  return cands.find((p) => existsSync(p)) || null;
}

function startServer() {
  const server = createServer(async (req, res) => {
    try {
      const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
      let rel = decodeURIComponent(url.pathname);
      if (rel === '/' || rel === '') rel = '/index.html';
      const full = join(WEB, rel);
      if (!full.startsWith(WEB)) { res.writeHead(403).end('forbidden'); return; }
      const body = await readFile(full);
      res.writeHead(200, {
        'Content-Type': MIME[extname(full).toLowerCase()] || 'application/octet-stream',
        'Cache-Control': 'no-store',
      });
      res.end(body);
    } catch {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' }).end('not found');
    }
  });
  return new Promise((ok) => server.listen(PORT, '127.0.0.1', () => ok(server)));
}

/** Load one URL in headless Chrome and report console output + screenshot. */
async function loadRoute(chrome, url, shotPath, profileDir) {
  const args = [
    '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
    '--window-size=1680,1400', '--virtual-time-budget=12000',
    '--enable-logging=stderr', '--v=0',
    `--user-data-dir=${profileDir}`,
    `--screenshot=${shotPath}`,
    url,
  ];
  let stderr = '';
  try {
    const r = await execFileAsync(chrome, args, { maxBuffer: 64 * 1024 * 1024, timeout: 120000 });
    stderr = r.stderr || '';
  } catch (err) {
    stderr = String(err.stderr || err.message || '');
  }
  const consoleErrors = [];
  for (const line of stderr.split('\n')) {
    const m = /CONSOLE:\d+\]\s+"?(.*?)"?,?\s*source:/.exec(line);
    if (m) consoleErrors.push(m[1].replace(/\\"/g, '"'));
    else if (/Uncaught|SyntaxError|TypeError|ReferenceError/.test(line)) {
      const t = line.trim();
      if (t && !/external_registry_loader/.test(t)) consoleErrors.push(t.slice(0, 300));
    }
  }
  return consoleErrors;
}

/** Read the rendered DOM text through the DevTools HTTP endpoint is overkill;
 *  instead we re-run with --dump-dom. */
async function dumpDom(chrome, url, profileDir) {
  const args = [
    '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
    '--window-size=1680,1400', '--virtual-time-budget=10000',
    `--user-data-dir=${profileDir}`, '--dump-dom', url,
  ];
  try {
    const r = await execFileAsync(chrome, args, { maxBuffer: 64 * 1024 * 1024, timeout: 120000 });
    return r.stdout || '';
  } catch (err) {
    return String(err.stdout || '');
  }
}

const main = async () => {
  const chrome = findChrome();
  if (!chrome) {
    console.error('[verify] no Chrome/Edge found; set CHROME_PATH and retry');
    process.exit(2);
  }
  console.log(`[verify] browser: ${chrome}`);
  await mkdir(SHOTS, { recursive: true });
  const profileDir = join(ROOT, '.tmp-verify-profile');
  await mkdir(profileDir, { recursive: true });

  const server = await startServer();
  console.log(`[verify] serving ${WEB} on http://127.0.0.1:${PORT}`);

  let failures = 0;
  const summary = [];

  for (const [id, hash] of ROUTES) {
    const url = `http://127.0.0.1:${PORT}/index.html${hash}`;
    const shot = join(SHOTS, `${id}.png`);
    const errors = await loadRoute(chrome, url, shot, profileDir);
    const dom = await dumpDom(chrome, url, profileDir);

    const stillLoading = dom.includes('正在初始化工作台');
    const loadFailed = dom.includes('数据层加载失败');
    const hasView = /class="main-inner"/.test(dom) && dom.length > 12000;
    const sections = (dom.match(/class="(card|panel|kcard|formula|empty)[ "]/g) || []).length;

    const bad = errors.length > 0 || stillLoading || loadFailed;
    if (bad) failures += 1;

    summary.push({
      route: id, errors: errors.length, domBytes: dom.length,
      blocks: sections, stillLoading, loadFailed, hasView,
    });

    const flag = bad ? 'FAIL' : ' ok ';
    console.log(`[${flag}] ${id.padEnd(11)} dom=${String(dom.length).padStart(6)}b blocks=${String(sections).padStart(4)} errors=${errors.length}${stillLoading ? ' STILL_LOADING' : ''}${loadFailed ? ' LOAD_FAILED' : ''}`);
    for (const e of errors.slice(0, 4)) console.log(`         ! ${e}`);
  }

  await writeFile(join(SHOTS, 'verify-report.json'),
    JSON.stringify({ generatedAt: new Date().toISOString(), chrome, port: PORT, routes: summary },
      null, 2), 'utf8');

  server.close();
  console.log(`\n[verify] screenshots -> ${SHOTS}`);
  console.log(`[verify] ${ROUTES.length - failures}/${ROUTES.length} routes rendered cleanly`);
  process.exit(failures ? 1 : 0);
};

main().catch((e) => { console.error('[verify] crashed:', e); process.exit(2); });
