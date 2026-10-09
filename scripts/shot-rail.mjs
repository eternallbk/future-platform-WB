/**
 * shot-rail.mjs — screenshot the sidebar footer so the status line can be inspected.
 * Complements verify-text-stacking: that catches stacked characters, this shows whether
 * the row overflows into its neighbours or renders cleanly.
 */
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { serveDir } from './serve-dist.mjs';

const CHROME = [process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe'].filter(Boolean).find((p) => existsSync(p));
const server = await serveDir(join(process.cwd(), 'dist'));
const port = 8800 + Math.floor(Math.random() * 90);
const profile = join(process.env.TEMP || '/tmp', `railshot-${Date.now()}`);
rmSync(profile, { recursive: true, force: true });
mkdirSync(profile, { recursive: true });
const proc = spawn(CHROME, ['--headless=new', '--disable-gpu', '--no-sandbox',
  '--hide-scrollbars', '--disable-http-cache', `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`, '--window-size=1200,900', 'about:blank'], { stdio: 'ignore' });
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
try {
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  const S = (m, p) => send(m, p, sessionId);
  await S('Page.enable'); await S('Runtime.enable');
  await S('Page.navigate', { url: `${server.url}/index.html#/dashboard` });
  await sleep(4600);
  // Clip precisely around the rail footer, in page coordinates.
  const clip = await S('Runtime.evaluate', {
    expression: `(() => {
      const f = document.querySelector('.rail-foot') || document.querySelector('#rail-status');
      const r = f.getBoundingClientRect();
      return JSON.stringify({ x: Math.max(0, Math.round(r.left) - 6),
        y: Math.max(0, Math.round(r.top + window.scrollY) - 6),
        width: Math.round(r.width) + 12, height: Math.round(r.height) + 12 });
    })()`,
    returnByValue: true,
  });
  const c = JSON.parse(clip.result.value);
  const shot = await S('Page.captureScreenshot',
    { format: 'png', captureBeyondViewport: true, clip: { ...c, scale: 3 } });
  mkdirSync('docs/screenshots', { recursive: true });
  writeFileSync('docs/screenshots/_rail.png', Buffer.from(shot.data, 'base64'));
  console.log('[rail] wrote docs/screenshots/_rail.png', JSON.stringify(c));
} finally {
  try { socket.close(); } catch { /* ignore */ }
  try { proc.kill(); } catch { /* ignore */ }
  try { await server.close(); } catch { /* ignore */ }
}
