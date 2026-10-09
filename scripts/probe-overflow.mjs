/**
 * probe-overflow.mjs — does #app still need `overflow-x: clip`?
 *
 * WHY: `#app { overflow-x: clip }` was added to contain a 4px horizontal overflow.
 * But per spec `clip` forces `overflow-y: clip` too, which makes #app a clipping
 * ancestor for absolutely-positioned popovers - that is what cut off the topbar
 * tooltips. If the 4px overflow no longer exists (the flex-shrink fixes may have
 * removed it), the guard can be dropped and the tooltip problem disappears at the
 * source instead of being patched per component.
 *
 * This measures document-level horizontal overflow with #app's clip disabled, at
 * several widths, and names the widest offender when one exists.
 */
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';

const CHROME = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean).find((p) => existsSync(p));
if (!CHROME) { console.error('no Chrome/Edge found'); process.exit(2); }

const argv = process.argv.slice(2);
const get = (f, d) => { const i = argv.indexOf(f); return i >= 0 ? argv[i + 1] : d; };
const base = get('--url', 'http://127.0.0.1:8796');
const widths = get('--widths', '1024,1200,1440,1680').split(',').map(Number);
const routes = get('--routes', 'dashboard,knowledge,jobs,formulas').split(',');

const port = 9700 + Math.floor(Math.random() * 200);
const profile = join(process.env.TEMP || '/tmp', `ovf-${Date.now()}`);
rmSync(profile, { recursive: true, force: true });
mkdirSync(profile, { recursive: true });
const proc = spawn(CHROME, [
  '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
  '--disable-http-cache', `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`, 'about:blank',
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
    const { resolve, reject } = waiting.get(m.id); waiting.delete(m.id);
    m.error ? reject(new Error(JSON.stringify(m.error))) : resolve(m.result);
  }
};
const send = (method, params = {}, sid) => new Promise((resolve, reject) => {
  const id = ++seq; waiting.set(id, { resolve, reject });
  socket.send(JSON.stringify({ id, method, params, sessionId: sid }));
});

try {
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  const S = (m, p) => send(m, p, sessionId);
  await S('Page.enable'); await S('Runtime.enable');
  await S('Emulation.setDeviceMetricsOverride',
    { width: widths[0], height: 900, deviceScaleFactor: 1, mobile: false });

  const probe = `(() => {
    const app = document.getElementById('app');
    app.style.overflowX = 'visible';
    app.style.overflowY = 'visible';
    const de = document.documentElement;
    const docOverflow = de.scrollWidth - de.clientWidth;
    const offenders = [];
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect();
      if (r.width > window.innerWidth + 1 || r.right > window.innerWidth + 1) {
        offenders.push({
          sel: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') +
            (typeof el.className === 'string' && el.className
              ? '.' + el.className.trim().split(/\\s+/).slice(0, 2).join('.') : ''),
          right: Math.round(r.right), width: Math.round(r.width),
        });
      }
    }
    offenders.sort((a, b) => b.right - a.right);
    return JSON.stringify({ docOverflow, offenders: offenders.slice(0, 4) });
  })()`;

  for (const w of widths) {
    await S('Emulation.setDeviceMetricsOverride',
      { width: w, height: 900, deviceScaleFactor: 1, mobile: false });
    for (const route of routes) {
      await S('Page.navigate', { url: `${base}/index.html#/${route}` });
      await sleep(2600);
      const r = await S('Runtime.evaluate', { expression: probe, returnByValue: true });
      const d = JSON.parse(r.result.value);
      const tag = d.docOverflow > 0 ? 'OVERFLOW' : 'ok';
      console.log(`  ${String(w).padStart(5)}px  ${route.padEnd(11)} ${tag.padEnd(9)} docOverflow=${d.docOverflow}px`);
      for (const o of d.offenders) {
        console.log(`          -> ${o.sel}  right=${o.right} width=${o.width}`);
      }
    }
  }
} finally {
  try { socket.close(); } catch { /* ignore */ }
  try { proc.kill(); } catch { /* ignore */ }
}
