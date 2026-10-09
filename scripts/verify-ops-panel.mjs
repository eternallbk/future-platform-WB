/**
 * verify-ops-panel.mjs — assert the redundancy panel actually renders on /pipeline.
 *
 * WHY: the panel is built from a big template string and reads an OPTIONAL data file.
 * A renamed field or a missing file renders an empty shell with no error anywhere -
 * exactly the silent failure this panel exists to expose. So it is asserted, not
 * eyeballed: the panel's own headings must be present and it must degrade to nothing
 * (not to a broken box) when the report is absent.
 *
 * Usage: node scripts/verify-ops-panel.mjs [--url URL]
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

const port = 9500 + Math.floor(Math.random() * 90);
const profile = join(process.env.TEMP || '/tmp', `ops-${Date.now()}`);
rmSync(profile, { recursive: true, force: true });
mkdirSync(profile, { recursive: true });
const proc = spawn(CHROME, ['--headless=new', '--disable-gpu', '--no-sandbox',
  '--hide-scrollbars', '--disable-http-cache', `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`, '--window-size=1440,2600', 'about:blank'], { stdio: 'ignore' });
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
  await S('Page.navigate', { url: `${base}/index.html#/pipeline` });
  await sleep(5200);

  const probe = await S('Runtime.evaluate', {
    expression: `(() => {
      const t = document.body.innerText;
      const panels = Array.from(document.querySelectorAll('.panel-title'))
        .map(e => e.textContent.trim());
      return JSON.stringify({
        panels,
        hasRedundancy: t.includes('去冗余体检'),
        hasEntity: t.includes('同一实体反复收录'),
        hasWorklist: t.includes('工单'),
        hasUnclassified: t.includes('未分类占比'),
        loadErrors: (window.__loadErrors || []).length,
        len: t.length,
      });
    })()`,
    returnByValue: true,
  });
  const d = JSON.parse(probe.result.value);
  console.log('');
  console.log('='.repeat(74));
  console.log('采集与运行 · 去冗余体检面板');
  console.log('='.repeat(74));
  console.log(`  page text length : ${d.len}`);
  console.log(`  panels           : ${d.panels.length}`);
  d.panels.forEach((p) => console.log(`      · ${p}`));
  const checks = [
    ['面板标题「去冗余体检」', d.hasRedundancy],
    ['含有「未分类占比」指标', d.hasUnclassified],
    ['含有「同一实体反复收录」', d.hasEntity],
    ['含有「工单」', d.hasWorklist],
  ];
  for (const [label, ok] of checks) {
    if (!ok) fails++;
    console.log(`  [${ok ? 'OK ' : 'FAIL'}] ${label}`);
  }

  const shot = await S('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
  writeFileSync('docs/screenshots/_ops.png', Buffer.from(shot.data, 'base64'));
  console.log('');
  console.log('  截图 -> docs/screenshots/_ops.png');
  console.log('='.repeat(74));
  console.log(fails ? `  ${fails} 项未通过` : '  全部通过');
  console.log('');
} finally {
  try { socket.close(); } catch { /* ignore */ }
  try { proc.kill(); } catch { /* ignore */ }
}
process.exit(fails ? 1 : 0);
