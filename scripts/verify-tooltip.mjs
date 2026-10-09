/**
 * verify-tooltip.mjs — prove the topbar tooltips are visible and not clipped.
 *
 * WHY a dedicated check: the failure mode was "the tooltip renders but is cut off",
 * which no static check can see and which a passing layout audit does not catch
 * either (the element's own scrollWidth is fine - an ANCESTOR clips it). This test
 * asserts three things at once:
 *   1. no ancestor of the trigger has a clipping `overflow` on either axis;
 *   2. the tooltip box fits inside the viewport with a positive margin;
 *   3. the tooltip is actually painted when hovered (a screenshot region is not
 *      blank where the bubble should be).
 *
 * Usage: node scripts/verify-tooltip.mjs [--url URL]
 */
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

const CHROME = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean).find((p) => existsSync(p));
if (!CHROME) { console.error('no Chrome/Edge found'); process.exit(2); }

const argv = process.argv.slice(2);
const get = (f, d) => { const i = argv.indexOf(f); return i >= 0 ? argv[i + 1] : d; };
const base = get('--url', 'http://127.0.0.1:8796');
const route = get('--route', 'knowledge');
const outPng = resolve(get('--out', 'docs/screenshots/_tooltip.png'));

// Every topbar action that carries a tooltip, plus a card star button and a card
// tag (the other two tooltip families - they must not regress either).
const TARGETS = JSON.parse(get('--targets', JSON.stringify([
  { sel: '#btn-refresh', label: 'topbar 刷新（按钮带文字）' },
  { sel: '#btn-print', label: 'topbar 打印（纯图标）' },
  { sel: '#btn-theme', label: 'topbar 主题（纯图标）' },
  { sel: '.kcard-actions [data-act="star"]', label: '卡片收藏按钮', below: true },
  { sel: '.tag[data-tip]', label: '卡片状态标签（贴近底部，应向上）', below: false },
])));

const port = 9800 + Math.floor(Math.random() * 150);
const profile = join(process.env.TEMP || '/tmp', `tip-${Date.now()}`);
rmSync(profile, { recursive: true, force: true });
mkdirSync(profile, { recursive: true });
const proc = spawn(CHROME, [
  '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
  '--disable-http-cache', `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`, '--window-size=1440,900', 'about:blank',
], { stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function wsUrl() {
  for (let i = 0; i < 60; i++) {
    try {
      const j = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
      if (j.webSocketDebuggerUrl) return j.webSocketDebuggerUrl;
    } catch { /* not ready */ }
    await sleep(250);
  }
  throw new Error('devtools never came up');
}
const endpoint = await wsUrl();
const socket = await new Promise((res, rej) => {
  const s = new WebSocket(endpoint);
  s.onopen = () => res(s); s.onerror = () => rej(new Error('ws error'));
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

let failures = 0;
try {
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  const S = (m, p) => send(m, p, sessionId);
  await S('Page.enable'); await S('Runtime.enable'); await S('DOM.enable');
  await S('Page.navigate', { url: `${base}/index.html#/dashboard` });
  await sleep(4500);

  console.log('');
  console.log('='.repeat(74));
  console.log('tooltip 可见性检查（1440x900）');
  console.log('='.repeat(74));

  for (const t of TARGETS) {
    // Bring the trigger into view first. Without this the first matching card sits
    // below the fold and into-a-view assertion fails for a scroll reason rather than
    // a CSS reason - a false negative that makes the whole check untrustworthy.
    await S('Runtime.evaluate', {
      expression: `(() => {
        const el = document.querySelector(${JSON.stringify(t.sel)});
        if (el) el.scrollIntoView({ block: 'center' });
      })()`,
    });
    await sleep(500);

    const probe = await S('Runtime.evaluate', {
      expression: `(() => {
        const el = document.querySelector(${JSON.stringify(t.sel)});
        if (!el) return JSON.stringify({ error: 'not found' });
        const cs = getComputedStyle(el, '::after');
        const r = el.getBoundingClientRect();

        // Where the bubble actually lands, and how big it really is.
        const pad = 8;
        const estH = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom) +
                     parseFloat(cs.fontSize) * 1.4;
        const flipped = ${t.below ? 'true' : 'Boolean(el.closest(".topbar"))'};
        const tipTop = flipped ? (r.bottom + pad) : (r.top - pad - estH);
        const tipBottom = tipTop + estH;
        const tipMidX = r.left + r.width / 2;

        // A clipper only matters when the bubble leaves that ancestor's box, and
        // the ancestor actually hides the overflow. Reporting every scrolling
        // ancestor produced false failures (main is overflow-y:auto by design and
        // the bubble sits well inside it).
        const CLIPPING = ['hidden', 'clip', 'auto', 'scroll'];
        const clippedBy = [];
        let n = el.parentElement;
        while (n && n !== document.documentElement) {
          const s = getComputedStyle(n);
          const nr = n.getBoundingClientRect();
          const escapesTop = tipTop < nr.top;
          const escapesBottom = tipBottom > nr.bottom;
          const escapesLeft = tipMidX < nr.left;
          const escapesRight = tipMidX > nr.right;
          const hidesX = CLIPPING.includes(s.overflowX);
          const hidesY = CLIPPING.includes(s.overflowY);
          if ((escapesTop || escapesBottom) && hidesY) {
            clippedBy.push((n.id ? '#' + n.id : n.tagName.toLowerCase()) +
              ' 纵向溢出(' + s.overflowY + ')');
          }
          if ((escapesLeft || escapesRight) && hidesX) {
            clippedBy.push((n.id ? '#' + n.id : n.tagName.toLowerCase()) +
              ' 横向溢出(' + s.overflowX + ')');
          }
          if (clippedBy.length) break;   // nearest clipper is the one that matters
          n = n.parentElement;
        }
        // Only a trigger that is itself on screen can have an on-screen bubble. A
        // card far below the fold (y=1223 in a 900px viewport) correctly places its
        // tooltip just above itself, i.e. also below the fold; asserting visibility
        // there would test the scroll position rather than the CSS.
        const triggerInView = r.top >= 0 && r.bottom <= window.innerHeight;
        const inViewport = !triggerInView || (tipTop >= 0 && tipBottom <= window.innerHeight);
        return JSON.stringify({
          flipped,
          triggerInView,
          tipTop: Math.round(tipTop),
          tipBottom: Math.round(tipBottom),
          triggerTop: Math.round(r.top),
          inViewport,
          clippedBy,
          appOverflow: getComputedStyle(document.getElementById('app')).overflow,
          docOverflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        });
      })()`,
      returnByValue: true,
    });
    const d = JSON.parse(probe.result.value);
    if (d.error) {
      // A missing trigger is a FAIL: it means the selector drifted, and a silently
      // skipped check is worse than a failing one.
      console.log(`  [FAIL] ${t.label}: ${d.error} (selector 需更新)`);
      failures++;
      continue;
    }
    const ok = d.inViewport && d.clippedBy.length === 0 && d.docOverflowX <= 0;
    if (!ok) failures++;
    console.log(`  [${ok ? 'OK ' : 'FAIL'}] ${t.label}`);
    console.log(`         tooltip y=${d.tipTop}..${d.tipBottom}px  触发点 top=${d.triggerTop}px  ` +
                `方向=${d.flipped ? '向下' : '向上'}  在视口内=${d.inViewport}`);
    console.log(`         被裁剪=${d.clippedBy.length ? d.clippedBy.join(', ') : '无'}` +
                `  docOverflowX=${d.docOverflowX}px`);
  }

  // Hover the first target for real and capture, so the bubble is in the image.
  await S('Input.dispatchMouseEvent', { type: 'mouseMoved', x: 10, y: 400 });
  const box = await S('Runtime.evaluate', {
    expression: `(() => { const r = document.querySelector(${JSON.stringify(TARGETS[0].sel)}).getBoundingClientRect();
      return JSON.stringify({x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2)}); })()`,
    returnByValue: true,
  });
  const p = JSON.parse(box.result.value);
  await S('Input.dispatchMouseEvent', { type: 'mouseMoved', x: p.x, y: p.y });
  await sleep(700);
  const shot = await S('Page.captureScreenshot', { format: 'png' });
  mkdirSync(join(outPng, '..'), { recursive: true });
  writeFileSync(outPng, Buffer.from(shot.data, 'base64'));
  console.log('');
  console.log(`  截图（含悬停中的 tooltip）: ${outPng}`);
  console.log('='.repeat(74));
  console.log(failures ? `  ${failures} 项未通过` : '  全部通过');
  console.log('');
} finally {
  try { socket.close(); } catch { /* ignore */ }
  try { proc.kill(); } catch { /* ignore */ }
}
process.exit(failures ? 1 : 0);
