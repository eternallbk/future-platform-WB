/**
 * verify-text-stacking.mjs — catch labels rendered one character per line.
 *
 * WHY this exists as its own check: `display: grid|inline-grid` with
 * `place-items: center` makes every child a grid item, and a bare text node can be
 * split into one item PER CHARACTER. With `height` fixed and no `white-space`, a
 * two-character Chinese label then stacks vertically - the 认证 column rendered
 * "公" above "开" and the table row looked broken. This is invisible to every static
 * check, does not overflow (so the layout audit is silent), and does not error.
 *
 * Detection: for short text-bearing elements, compare the rendered height against a
 * single line's height. Vertical stacking roughly doubles it. Deliberately limited to
 * leaf elements with few characters so normal wrapping paragraphs are never flagged.
 *
 * Usage: node scripts/verify-text-stacking.mjs [--url URL] [--routes a,b,c]
 */
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { serveDir, waitForRender, RENDERED_EXPR } from './serve-dist.mjs';

const CHROME = [process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean).find((p) => existsSync(p));
if (!CHROME) { console.error('no Chrome/Edge'); process.exit(2); }

const argv = process.argv.slice(2);
const get = (f, d) => { const i = argv.indexOf(f); return i >= 0 ? argv[i + 1] : d; };
// Serve dist/ ourselves unless a URL was given: depending on a server someone else
// started made this guard fail with "connection refused", which trains you to ignore it.
const explicit = get('--url', '');
const server = explicit ? null : await serveDir(join(process.cwd(), 'dist'));
const base = explicit || server.url;
const routes = get('--routes',
  'dashboard,knowledge,jobs,formulas,pipeline,skills,repos,roadmap,progress,digest,categories,starred,exam').split(',');

const port = 9300 + Math.floor(Math.random() * 90);
const profile = join(process.env.TEMP || '/tmp', `stack-${Date.now()}`);
rmSync(profile, { recursive: true, force: true });
mkdirSync(profile, { recursive: true });
const proc = spawn(CHROME, ['--headless=new', '--disable-gpu', '--no-sandbox',
  '--hide-scrollbars', '--disable-http-cache', `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`, '--window-size=1440,1000', 'about:blank'], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function wsUrl() {
  for (let i = 0; i < 60; i++) {
    try {
      const j = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
      if (j.webSocketDebuggerUrl) return j.webSocketDebuggerUrl;
    } catch { /* not ready */ }
    await sleep(250);
  }
  throw new Error('no devtools');
}
const endpoint = await wsUrl();
const socket = await new Promise((res, rej) => {
  const s = new WebSocket(endpoint);
  s.onopen = () => res(s); s.onerror = () => rej(new Error('ws'));
});
let seq = 0; const waiting = new Map();
socket.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && waiting.has(m.id)) {
    const { resolve: rs, reject: rj } = waiting.get(m.id); waiting.delete(m.id);
    m.error ? rj(new Error(JSON.stringify(m.error))) : rs(m.result);
  }
};
const send = (method, params = {}, sid) => new Promise((resolve, reject) => {
  const id = ++seq; waiting.set(id, { resolve, reject });
  socket.send(JSON.stringify({ id, method, params, sessionId: sid }));
});

const PROBE = `(() => {
  const bad = [];
  for (const el of document.querySelectorAll('body *')) {
    if (el.children.length) continue;              // leaf only: containers lie
    const text = (el.textContent || '').trim();
    if (!text || text.length > 12) continue;       // a sentence may wrap
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    if (cs.whiteSpace === 'nowrap' || cs.whiteSpace === 'pre') continue;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) continue;

    // The real signature is a GRID box that forces one item per CHARACTER: the box
    // stays about one character wide while its height grows with the character count.
    // This deliberately requires chars >= 2 AND a box no wider than ~1.5 characters,
    // which excludes the two families that produced false failures while calibrating:
    //   · a table cell is tall because the ROW is tall, not because text stacked
    //     (td.num "270.7s" measured 76px tall while being perfectly horizontal);
    //   · a fixed-size glyph tile (span.formula-glyph, 38x38, one symbol) is square
    //     by design - "𝔼" and "c_k" are single tokens, not stacked characters.
    const isGrid = cs.display === 'grid' || cs.display === 'inline-grid';
    const charW = parseFloat(cs.fontSize) || 12;
    const narrow = r.width < charW * 1.6;
    const chars = Array.from(text).length;
    if (isGrid && narrow && chars >= 2 && r.height >= charW * 1.05) {
      bad.push({
        sel: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
          (typeof el.className === 'string' && el.className
            ? '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.') : ''),
        text, height: Math.round(r.height), width: Math.round(r.width),
        display: cs.display,
      });
    }
  }
  return JSON.stringify(bad.slice(0, 12));
})()`;

let total = 0;
const seen = new Set();
try {
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  const S = (m, p) => send(m, p, sessionId);
  await S('Page.enable'); await S('Runtime.enable');

  console.log('');
  console.log('='.repeat(74));
  console.log('文字竖排（一字一行）检查');
  console.log('='.repeat(74));
  for (const route of routes) {
    await S('Page.navigate', { url: `${base}/index.html#/${route}` });
    // MUST wait for a real render. This guard is a NEGATIVE assertion ("no stacked
    // text"), so on an empty page it passes trivially - measured against the published
    // site it reported "未发现竖排文字" while the page still said "数据加载中…". A failure
    // to render is therefore counted as a failure, not as a clean result.
    const evaluate = async (expr) => (await S('Runtime.evaluate',
      { expression: expr, returnByValue: true })).result.value;
    const rendered = await waitForRender(evaluate, RENDERED_EXPR, 45000);
    if (!rendered) {
      console.log(`  [FAIL] ${route}   页面未完成渲染（无法判定，视为失败）`);
      total++;
      continue;
    }
    const r = await S('Runtime.evaluate', { expression: PROBE, returnByValue: true });
    const bad = JSON.parse(r.result.value);
    if (bad.length) {
      console.log(`  [FAIL] ${route}   ${bad.length} 处竖排`);
      for (const b of bad) {
        const key = b.sel + '|' + b.text;
        if (seen.has(key)) continue;
        seen.add(key);
        total++;
        console.log(`        ${b.sel}  "${b.text}"  高 ${b.height}px / 行高 ${b.line}px  display=${b.display}`);
      }
    } else {
      console.log(`  [OK ] ${route}`);
    }
  }
  console.log('='.repeat(74));
  console.log(total ? `  ${total} 处需要 white-space: nowrap 或改用 flex` : '  未发现竖排文字');
  console.log('');
} finally {
  try { socket.close(); } catch { /* ignore */ }
  try { proc.kill(); } catch { /* ignore */ }
  if (server) { try { await server.close(); } catch { /* ignore */ } }
}
process.exit(total ? 1 : 0);
