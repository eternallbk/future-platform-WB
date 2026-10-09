/**
 * verify-columns.mjs — screenshot the 采集与运行 channel table and assert its
 * 认证/模式 cells render on ONE line.
 *
 * WHY a dedicated check: the earlier defect was a Chinese label stacking one
 * character per line inside a `place-items: center` grid box, which reads as a
 * "串行" (misaligned column) table. It does not overflow, so the layout audit stays
 * silent, and the markup is valid, so no static check catches it.
 *
 * Usage: node scripts/verify-columns.mjs [--url URL]
 */
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const CHROME = [process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean).find((p) => existsSync(p));
if (!CHROME) { console.error('no Chrome/Edge'); process.exit(2); }

const argv = process.argv.slice(2);
const get = (f, d) => { const i = argv.indexOf(f); return i >= 0 ? argv[i + 1] : d; };
const base = get('--url', 'http://127.0.0.1:8797');

const port = 9100 + Math.floor(Math.random() * 90);
const profile = join(process.env.TEMP || '/tmp', `cols-${Date.now()}`);
rmSync(profile, { recursive: true, force: true });
mkdirSync(profile, { recursive: true });
const proc = spawn(CHROME, ['--headless=new', '--disable-gpu', '--no-sandbox',
  '--hide-scrollbars', '--disable-http-cache', `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`, '--window-size=1440,1200', 'about:blank'], { stdio: 'ignore' });
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

// Any multi-character text node whose client rects split into >1 line is stacked.
const STACKED = `(() => {
  const bad = [];
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walk.nextNode())) {
    const t = (n.textContent || '').trim();
    if (Array.from(t).length < 2 || Array.from(t).length > 8) continue;
    const el = n.parentElement;
    if (!el) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const range = document.createRange();
    range.selectNodeContents(n);
    const rects = Array.from(range.getClientRects())
      .filter((r) => r.width > 0.5 && r.height > 0.5);
    // More than one rect at the same x but different y = wrapped/stacked text that
    // the author meant to keep on one line (short label).
    const tops = new Set(rects.map((r) => Math.round(r.top)));
    if (rects.length > 1 && tops.size > 1 && rects.every((r) => r.width <= 24)) {
      bad.push({ text: t, tag: el.tagName.toLowerCase(),
                 cls: typeof el.className === 'string' ? el.className : '',
                 rects: rects.length, tops: tops.size });
    }
    if (bad.length > 10) break;
  }
  return JSON.stringify(bad);
})()`;

let fails = 0;
try {
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  const S = (m, p) => send(m, p, sessionId);
  await S('Page.enable'); await S('Runtime.enable');
  await S('Page.navigate', { url: `${base}/index.html#/pipeline` });
  await sleep(5200);

  const r = await S('Runtime.evaluate', { expression: STACKED, returnByValue: true });
  const bad = JSON.parse(r.result.value);
  console.log('');
  console.log('='.repeat(74));
  console.log('采集与运行 · 短文本换行/竖排检查');
  console.log('='.repeat(74));
  if (!bad.length) {
    console.log('  [OK ] 所有 2-8 字短文本都渲染在单行');
  } else {
    fails += bad.length;
    for (const b of bad) {
      console.log(`  [FAIL] "${b.text}"  ${b.tag}.${b.cls}  断成 ${b.rects} 段 / ${b.tops} 行`);
    }
  }

  // Screenshot the channel-table region so the fix is visible, not just asserted.
  // Scroll it to the top first: with `captureBeyondViewport` a clip is in PAGE
  // coordinates, and mixing in window.scrollY produced a blank image.
  await S('Runtime.evaluate', {
    expression: `(() => {
      const h = Array.from(document.querySelectorAll('.panel-title'))
        .find(e => e.textContent.includes('渠道清单'));
      if (h) h.closest('.panel').scrollIntoView({ block: 'start' });
    })()`,
  });
  await sleep(600);
  const shot = await S('Page.captureScreenshot', { format: 'png' });
  writeFileSync('docs/screenshots/_channels.png', Buffer.from(shot.data, 'base64'));
  console.log('');
  console.log('  截图 -> docs/screenshots/_channels.png');
  console.log('='.repeat(74));
  console.log(fails ? `  ${fails} 处未通过` : '  全部通过');
  console.log('');
} finally {
  try { socket.close(); } catch { /* ignore */ }
  try { proc.kill(); } catch { /* ignore */ }
}
process.exit(fails ? 1 : 0);
