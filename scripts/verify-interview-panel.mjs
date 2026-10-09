/**
 * verify-interview-panel.mjs — the 面经速览 panel must render on /problems.
 * Optional data file + big template string = silent empty panel if a field drifts.
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

const port = 9000 + Math.floor(Math.random() * 90);
const profile = join(process.env.TEMP || '/tmp', `iv-${Date.now()}`);
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

let fails = 0;
try {
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  const S = (m, p) => send(m, p, sessionId);
  await S('Page.enable'); await S('Runtime.enable');
  await S('Page.navigate', { url: `${base}/index.html#/problems` });
  await sleep(5200);

  const probe = await S('Runtime.evaluate', {
    expression: `(() => {
      const t = document.body.innerText;
      const panels = Array.from(document.querySelectorAll('.panel-title'))
        .map(e => e.textContent.trim());
      return JSON.stringify({
        panels,
        hasInterview: t.includes('面经速览'),
        hasCompany: t.includes('公司分布'),
        hasTopics: t.includes('考察主题'),
        hasRecent: t.includes('最近的面经'),
        chips: document.querySelectorAll('.panel .chip').length,
        consoleErrs: 0,
      });
    })()`,
    returnByValue: true,
  });
  const d = JSON.parse(probe.result.value);
  console.log('');
  console.log('='.repeat(74));
  console.log('题库定位 · 面经速览面板');
  console.log('='.repeat(74));
  console.log(`  panels: ${d.panels.join(' | ')}`);
  for (const [label, ok] of [['面板「面经速览」', d.hasInterview],
    ['公司分布', d.hasCompany], ['考察主题', d.hasTopics],
    ['最近的面经', d.hasRecent], ['至少 5 个聚合 chip', d.chips >= 5]]) {
    if (!ok) fails++;
    console.log(`  [${ok ? 'OK ' : 'FAIL'}] ${label}`);
  }

  await S('Runtime.evaluate', {
    expression: `(() => { const h = Array.from(document.querySelectorAll('.panel-title'))
      .find(e => e.textContent.includes('面经速览'));
      if (h) h.closest('.panel').scrollIntoView({block:'start'}); })()`,
  });
  await sleep(500);
  const shot = await S('Page.captureScreenshot', { format: 'png' });
  writeFileSync('docs/screenshots/_interview.png', Buffer.from(shot.data, 'base64'));
  console.log('');
  console.log('  截图 -> docs/screenshots/_interview.png');
  console.log('='.repeat(74));
  console.log(fails ? `  ${fails} 项未通过` : '  全部通过');
  console.log('');
} finally {
  try { socket.close(); } catch { /* ignore */ }
  try { proc.kill(); } catch { /* ignore */ }
}
process.exit(fails ? 1 : 0);
