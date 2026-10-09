/**
 * verify-collapse.mjs — does the formula/module collapse control actually work?
 *
 * WHY: the toggle is wired through event delegation (`data-act="toggle-expand"`), so
 * a passing DOM check proves only that the markup exists. This test drives the real
 * click path and asserts the resulting state, which is the only way to catch
 * "the button renders but nothing happens".
 *
 * Usage: node scripts/verify-collapse.mjs [--url URL]
 */
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { serveDir } from './serve-dist.mjs';

const CHROME = [process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean).find((p) => existsSync(p));
if (!CHROME) { console.error('no Chrome/Edge'); process.exit(2); }

const argv = process.argv.slice(2);
const get = (f, d) => { const i = argv.indexOf(f); return i >= 0 ? argv[i + 1] : d; };
// Serve dist/ ourselves unless a URL was given (see serve-dist.mjs for why).
const explicit = get('--url', '');
const server = explicit ? null : await serveDir(join(process.cwd(), 'dist'));
const base = explicit || server.url;
const route = get('--route', 'formulas');

const port = 9400 + Math.floor(Math.random() * 90);
const profile = join(process.env.TEMP || '/tmp', `col-${Date.now()}`);
rmSync(profile, { recursive: true, force: true });
mkdirSync(profile, { recursive: true });
const proc = spawn(CHROME, ['--headless=new', '--disable-gpu', '--no-sandbox',
  '--hide-scrollbars', '--disable-http-cache', `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`, '--window-size=1440,1400', 'about:blank'], { stdio: 'ignore' });
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

// Read the state of the first collapsible on the page.
const STATE = `(() => {
  const head = document.querySelector('[data-act="toggle-expand"]:not([hidden])');
  if (!head) return JSON.stringify({ error: 'no collapsible head found' });
  const body = document.getElementById(head.dataset.target);
  if (!body) return JSON.stringify({ error: 'target missing: ' + head.dataset.target,
                                     target: head.dataset.target });
  const cs = getComputedStyle(body);
  return JSON.stringify({
    target: head.dataset.target,
    hiddenAttr: body.hasAttribute('hidden'),
    display: cs.display,
    visible: body.getBoundingClientRect().height > 0,
    headOpenClass: head.classList.contains('is-open'),
    ariaExpanded: head.getAttribute('aria-expanded'),
    headHasIcon: Boolean(head.querySelector('svg')),
  });
})()`;

let fails = 0;
try {
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  const S = (m, p) => send(m, p, sessionId);
  await S('Page.enable'); await S('Runtime.enable');
  await S('Page.navigate', { url: `${base}/index.html#/${route}` });
  // Poll for the view rather than waiting a fixed time. Against the PUBLISHED site the
  // payload is ~4 MB over the network, so a fixed 5.2s caught the page mid-load and
  // reported "no collapsible head found" - a measurement artefact that looks exactly
  // like a site regression. This check must work against both dist/ and the live URL.
  await sleep(1200);
  for (let i = 0; i < 45; i++) {
    const q = await S('Runtime.evaluate', {
      expression: `document.querySelectorAll('[data-act="toggle-expand"]').length`,
      returnByValue: true,
    });
    if ((q.result.value || 0) > 0) break;
    await sleep(1000);
  }

  const evalJson = async (expr) => JSON.parse(
    (await S('Runtime.evaluate', { expression: expr, returnByValue: true })).result.value);

  const before = await evalJson(STATE);
  console.log('');
  console.log('='.repeat(74));
  console.log(`折叠控件测试  route=${route}`);
  console.log('='.repeat(74));
  if (before.error) {
    console.log(`  [FAIL] ${before.error}`);
    fails++;
  } else {
    console.log(`  点击前: hidden=${before.hiddenAttr} visible=${before.visible} ` +
                `is-open=${before.headOpenClass} aria=${before.ariaExpanded}`);
    if (!before.visible) {
      console.log('  [FAIL] 初始状态就已经是收起的（预期展开）');
      fails++;
    }

    // Real click through the browser's own hit-testing, so a swallowed event or a
    // missing delegation root shows up as "nothing happened".
    const box = await evalJson(`(() => {
      const h = document.querySelector('[data-act="toggle-expand"]');
      const r = h.getBoundingClientRect();
      return JSON.stringify({x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2)});
    })()`);
    await S('Input.dispatchMouseEvent', { type: 'mousePressed', x: box.x, y: box.y, button: 'left', clickCount: 1 });
    await S('Input.dispatchMouseEvent', { type: 'mouseReleased', x: box.x, y: box.y, button: 'left', clickCount: 1 });
    await sleep(500);

    const after = await evalJson(STATE);
    console.log(`  点击后: hidden=${after.hiddenAttr} visible=${after.visible} ` +
                `is-open=${after.headOpenClass} aria=${after.ariaExpanded}`);

    const collapsed = after.hiddenAttr || !after.visible;
    if (!collapsed) {
      console.log('  [FAIL] 点击后没有收起（事件没有生效）');
      fails++;
    } else {
      console.log('  [OK ] 点击后收起');
    }
    if (after.ariaExpanded === before.ariaExpanded) {
      console.log('  [FAIL] aria-expanded 没有变化（无障碍状态未同步）');
      fails++;
    } else {
      console.log('  [OK ] aria-expanded 已同步');
    }

    // And back open again, so a one-way toggle is caught too.
    await S('Input.dispatchMouseEvent', { type: 'mousePressed', x: box.x, y: box.y, button: 'left', clickCount: 1 });
    await S('Input.dispatchMouseEvent', { type: 'mouseReleased', x: box.x, y: box.y, button: 'left', clickCount: 1 });
    await sleep(500);
    const again = await evalJson(STATE);
    console.log(`  再点击: hidden=${again.hiddenAttr} visible=${again.visible}`);
    if (!again.visible) {
      console.log('  [FAIL] 第二次点击没有重新展开');
      fails++;
    } else {
      console.log('  [OK ] 第二次点击重新展开');
    }
  }

  const shot = await S('Page.captureScreenshot', { format: 'png' });
  writeFileSync('docs/screenshots/_collapse.png', Buffer.from(shot.data, 'base64'));
  console.log('');
  console.log('='.repeat(74));
  console.log(fails ? `  ${fails} 项未通过` : '  全部通过');
  console.log('');
} finally {
  try { socket.close(); } catch { /* ignore */ }
  try { proc.kill(); } catch { /* ignore */ }
  if (server) { try { await server.close(); } catch { /* ignore */ } }
}
process.exit(fails ? 1 : 0);
