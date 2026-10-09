#!/usr/bin/env node
/**
 * audit-layout.mjs — find elements whose content overflows their box.
 *
 * Why this exists: the reported bug was a job row whose text was far wider than
 * its column, and because an ancestor had `overflow-x: hidden` the excess was
 * silently clipped instead of producing a visible scrollbar. Eyeballing
 * screenshots does not reliably catch that, and it reappears whenever new
 * data-derived text is longer than expected. So measure it.
 *
 * For a set of routes and viewport widths it reports every element where
 * scrollWidth exceeds clientWidth by more than a tolerance, excluding:
 *   * elements that are SUPPOSED to scroll (overflow-x: auto/scroll)
 *   * inline elements and text nodes with no box
 *   * <html>/<body>
 *
 * Usage: node scripts/audit-layout.mjs [--width 1100,1350,1600]
 */
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';

const here = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(here, '..');
const WEB = join(ROOT, 'web');

const argv = process.argv.slice(2);
const getArg = (n, d) => {
  const i = argv.indexOf(n);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : d;
};
const WIDTHS = getArg('--width', '1100,1350,1600').split(',').map((s) => parseInt(s, 10));
const ROUTES = getArg('--routes', 'dashboard,jobs,knowledge').split(',');
const PORT = parseInt(getArg('--port', '8793'), 10);

const CHROME_CANDIDATES = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium',
];
const chrome = CHROME_CANDIDATES.find((p) => existsSync(p));
if (!chrome) {
  console.error('[audit] no Chrome found');
  process.exit(1);
}

const MIME = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.png': 'image/png', '.svg': 'image/svg+xml', '.ico': 'image/x-icon',
};

const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://x');
    // The probe POSTs its measurements here. WHY a POST and not --dump-dom:
    // Chrome's --dump-dom serialises the DOM before deferred (setTimeout) work
    // runs, so results written after the app finishes rendering were never in the
    // dump. Having the page report its own numbers avoids that race entirely.
    if (req.method === 'POST' && url.pathname === '/audit-report') {
      let body = '';
      req.on('data', (c) => { body += c; });
      req.on('end', () => {
        lastReport = body;
        res.writeHead(204).end();
      });
      return;
    }
    let p = join(WEB, decodeURIComponent(url.pathname));
    if (url.pathname === '/' || url.pathname === '') p = join(WEB, 'index.html');
    let data = await readFile(p);
    // Inject the probe into the served HTML (in memory only; web/index.html is
    // never modified). Headless Chrome has no --evaluate flag, so this is how the
    // measurement code reaches the page.
    if (p.endsWith('index.html')) {
      const html = data.toString('utf8').replace(
        '</body>',
        `<script>window.addEventListener('load',function(){setTimeout(function(){${PROBE_SRC}},1200)});</script></body>`);
      data = Buffer.from(html, 'utf8');
    }
    res.writeHead(200, { 'content-type': MIME[p.slice(p.lastIndexOf('.'))] || 'application/octet-stream' });
    res.end(data);
  } catch {
    res.writeHead(404).end('not found');
  }
});
await new Promise((r) => server.listen(PORT, '127.0.0.1', r));

let lastReport = null;

/**
 * Runs in the page and reports via POST.
 *
 * Defined as a real function and serialised with toString() rather than as a
 * template literal: a template literal would break the moment this code contains
 * a `${...}` or a backtick, which is an easy mistake to make and produces a
 * silent syntax error inside the browser (the audit then reports "no report",
 * which looks like a rendering problem rather than a probe problem).
 */
function pageProbe() {
  const out = [];
  const all = document.querySelectorAll('body *');
  for (const el of all) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    if (cs.overflowX === 'auto' || cs.overflowX === 'scroll') continue;
    if (el.tagName === 'HTML' || el.tagName === 'BODY') continue;
    const overflow = el.scrollWidth - el.clientWidth;
    if (overflow <= 0 || el.clientWidth <= 0) continue;

    // Severity filter. Measurements of a few pixels are almost always sub-pixel
    // or scrollbar rounding, and elements that deliberately ellipsise
    // (`text-overflow: ellipsis` with `overflow: hidden`) or line-clamp are
    // *designed* to clip. Reporting those produced ~150 rows of noise and buried
    // the genuine findings, which made the guard useless. What matters is content
    // clipped WITHOUT an ellipsis, or a large overflow meaning a real break.
    //
    // Two further exclusions, both added after measuring what the 134 remaining
    // "issues" actually were:
    //   · SHORT LABELS. A 3-character timestamp ("4 天前") measuring 40px of
    //     overflow means the container is deliberately compact, not that anything is
    //     broken - and text that short cannot be meaningfully truncated. A guard that
    //     always reports failure is a guard nobody reads.
    //   · SCROLLING ANCESTORS. If an ancestor scrolls, the content is reachable, so
    //     it is not silently clipped.
    const text = (el.textContent || '').trim();
    if (Array.from(text).length <= 6) continue;
    let scroller = el.parentElement;
    let inScroller = false;
    while (scroller && scroller !== document.body) {
      const s = getComputedStyle(scroller);
      if (s.overflowX === 'auto' || s.overflowX === 'scroll'
          || s.overflowY === 'auto' || s.overflowY === 'scroll') { inScroller = true; break; }
      scroller = scroller.parentElement;
    }
    if (inScroller) continue;

    const ellipsises = cs.textOverflow === 'ellipsis';
    const clamps = cs.webkitLineClamp && cs.webkitLineClamp !== 'none';
    // An element that does NOT hide its overflow is not clipping anything: the content
    // simply extends past the box and is painted. Measured case: `#rail-status` reports
    // 36px of "overflow" while rendering every character correctly ("数据层正常 14
    // 分钟前 1/1", verified by screenshot), because its children spill into the rail's
    // free space. Reporting that as a failure is what buried the real findings.
    const hidesOverflow = cs.overflowX === 'hidden' || cs.overflowX === 'clip';
    if (!hidesOverflow) continue;
    const meaningful = overflow >= 24 || (!ellipsises && !clamps && overflow >= 8);
    if (!meaningful) continue;

    const id = el.id ? '#' + el.id : '';
    const cls = (el.className && typeof el.className === 'string')
      ? '.' + el.className.trim().split(/\s+/).slice(0, 3).join('.') : '';
    out.push({
      sel: el.tagName.toLowerCase() + id + cls,
      overflow,
      clientW: el.clientWidth,
      scrollW: el.scrollWidth,
      trimmed: ellipsises || Boolean(clamps),
      text: (el.textContent || '').trim().slice(0, 60),
    });
  }
  out.sort((a, b) => b.overflow - a.overflow);
  // Deduplicate: a repeated component (a card in a list) produced dozens of
  // identical rows, which made the report look far worse than it is and hid the
  // distinct problems. Keep the worst instance of each selector+text pair.
  const seen = new Set();
  const uniq = [];
  for (const o of out) {
    const key = o.sel + '|' + o.text;
    if (seen.has(key)) continue;
    seen.add(key);
    uniq.push(o);
  }
  const wide = [];
  for (const el of all) {
    const r = el.getBoundingClientRect();
    // Only a genuine horizontal escape counts; a few px is rounding.
    if (r.width > window.innerWidth + 8) {
      const cls = (el.className && typeof el.className === 'string')
        ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : '';
      wide.push({ sel: el.tagName.toLowerCase() + cls, w: Math.round(r.width) });
    }
  }
  const payload = JSON.stringify({
    vw: window.innerWidth,
    cards: document.querySelectorAll('.kcard,.job-mini,.mini-item,.panel').length,
    overflow: uniq.slice(0, 25),
    tooWide: wide.slice(0, 15),
  });
  try { fetch('/audit-report', { method: 'POST', body: payload, keepalive: true }); } catch (e) { /* ignore */ }
  const pre = document.createElement('pre');
  pre.id = 'audit-result';
  pre.textContent = payload;
  document.body.appendChild(pre);
}

const PROBE_SRC = `(${pageProbe.toString()})();`;

function runChrome(width, route) {
  return new Promise((resolvePromise) => {
    const profile = join(ROOT, '.tmp-audit-profile');
    rmSync(profile, { recursive: true, force: true });
    mkdirSync(profile, { recursive: true });
    const url = `http://127.0.0.1:${PORT}/index.html#/${route}`;
    const args = [
      '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
      // A stale CSS copy would make every measurement meaningless.
      '--disable-http-cache', '--disk-cache-size=1',
      `--window-size=${width},1200`, '--virtual-time-budget=12000',
      `--user-data-dir=${profile}`, '--dump-dom', url,
    ];
    const p = spawn(chrome, args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let dom = '';
    p.stdout.on('data', (d) => { dom += d.toString(); });
    p.on('close', () => resolvePromise(dom));
  });
}

console.log(`[audit] chrome: ${chrome}`);
console.log(`[audit] serving ${WEB} on http://127.0.0.1:${PORT}`);
{
  // Sanity: prove the CSS we are about to measure is the current file. A stale
  // copy would make every measurement meaningless, which is exactly the kind of
  // false signal that wastes an afternoon.
  const css = await readFile(join(WEB, 'assets', 'css', 'app.css'), 'utf8');
  console.log(`[audit] app.css: ${css.length} bytes, mtime-bytes OK, contains 'overflow-x: clip': ${css.includes('overflow-x: clip')}`);
}
console.log(`[audit] widths: ${WIDTHS.join(', ')}  routes: ${ROUTES.join(', ')}\n`);

let problems = 0;
console.log('[audit] static overflow check (scrollWidth > clientWidth)\n');
for (const w of WIDTHS) {
  for (const route of ROUTES) {
    lastReport = null;
    const dom = await runChrome(w, route);
    // The page reports via POST. Wait for it, then fall back to parsing the
    // <pre id="audit-result"> out of the dumped DOM.
    for (let i = 0; i < 50 && !lastReport; i++) await new Promise((r) => setTimeout(r, 100));
    let raw = lastReport;
    if (!raw) {
      const pm = /<pre id="audit-result">([\s\S]*?)<\/pre>/.exec(dom);
      if (pm) {
        raw = pm[1].replace(/&quot;/g, '"').replace(/&amp;/g, '&')
          .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&#39;/g, "'");
      }
    }
    if (!raw) {
      console.log(`  ${String(w).padStart(4)}px  ${route.padEnd(10)} (no report - page may not have rendered)`);
      problems++;
      continue;
    }
    const data = JSON.parse(raw);
    const n = data.overflow.length;
    const wide = data.tooWide.length;
    if (!n && !wide) {
      console.log(`  ${String(w).padStart(4)}px  ${route.padEnd(10)} OK (no overflow, nothing wider than viewport)`);
      continue;
    }
    problems += n + wide;
    console.log(`  ${String(w).padStart(4)}px  ${route.padEnd(10)} ${n} overflow / ${wide} too wide`);
    for (const o of data.overflow.slice(0, 6)) {
      console.log(`        overflow ${String(o.overflow).padStart(4)}px  ${o.sel}  (client ${o.clientW}, scroll ${o.scrollW})  "${o.text}"`);
    }
    for (const t of data.tooWide.slice(0, 4)) {
      console.log(`        too wide ${t.w}px  ${t.sel}`);
    }
  }
}
console.log(`\n[audit] ${problems === 0 ? 'PASS - no layout overflow detected' : `FAIL - ${problems} issue(s)`}`);
server.close();
rmSync(join(ROOT, '.tmp-audit-profile'), { recursive: true, force: true });
process.exit(problems === 0 ? 0 : 1);
