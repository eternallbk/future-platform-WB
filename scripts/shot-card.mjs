/**
 * shot-card.mjs — open one knowledge card and screenshot its drawer.
 *
 * WHY: verifying that the deep-read "teaching" layer actually RENDERS cannot be done
 * by grepping app.js. The card body is produced by a big template string, so a typo
 * in a field name silently renders nothing while every static check still passes.
 * This drives a real browser over the DevTools protocol, calls the app's own
 * openItem(), and reports whether the expected sections made it into the DOM.
 *
 * Usage: node scripts/shot-card.mjs <itemId> <outPng> [--url http://127.0.0.1:PORT]
 */
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';

const CHROME_CANDIDATES = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean);

const args = process.argv.slice(2);
const itemId = args[0];
const outPng = resolve(args[1] || 'docs/screenshots/_card.png');
let base = 'http://127.0.0.1:8796';
const ui = args.indexOf('--url');
if (ui >= 0) base = args[ui + 1];

if (!itemId) {
  console.error('usage: node scripts/shot-card.mjs <itemId> <outPng> [--url URL]');
  process.exit(2);
}

const chrome = CHROME_CANDIDATES.find((p) => existsSync(p));
if (!chrome) {
  console.error('no Chrome/Edge found; set CHROME_PATH');
  process.exit(2);
}

const port = 9222 + Math.floor(Math.random() * 300);
const profile = join(process.env.TEMP || '/tmp', `cdp-${Date.now()}`);
rmSync(profile, { recursive: true, force: true });
mkdirSync(profile, { recursive: true });
mkdirSync(dirname(outPng), { recursive: true });

const proc = spawn(chrome, [
  '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
  '--disable-http-cache', `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`, '--window-size=1200,1400',
  'about:blank',
], { stdio: 'ignore' });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function getWsUrl() {
  for (let i = 0; i < 60; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/json/version`);
      const j = await r.json();
      if (j.webSocketDebuggerUrl) return j.webSocketDebuggerUrl;
    } catch { /* not up yet */ }
    await sleep(250);
  }
  throw new Error('devtools endpoint never came up');
}

function connect(url) {
  return new Promise((res, rej) => {
    const ws = new WebSocket(url);
    ws.onopen = () => res(ws);
    ws.onerror = (e) => rej(new Error('ws error: ' + (e.message || 'unknown')));
  });
}

async function main() {
  const ws = await connect(await getWsUrl());
  let id = 0;
  const pending = new Map();
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { res, rej } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? rej(new Error(JSON.stringify(msg.error))) : res(msg.result);
    }
  };
  const send = (method, params = {}, sessionId) => new Promise((res, rej) => {
    const mid = ++id;
    pending.set(mid, { res, rej });
    ws.send(JSON.stringify({ id: mid, method, params, sessionId }));
  });

  // Attach to a fresh page target.
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  const S = (m, p) => send(m, p, sessionId);

  await S('Page.enable');
  await S('Runtime.enable');
  await S('Page.navigate', { url: `${base}/index.html#/knowledge` });
  await sleep(4500);                       // let boot() fetch and render

  // Open the card through the app's own function so the real code path runs.
  const opened = await S('Runtime.evaluate', {
    expression: `typeof openItem === 'function' ? (openItem(${JSON.stringify(itemId)}), 'ok') : 'no-openItem'`,
    returnByValue: true,
  });
  if (opened.result.value !== 'ok') {
    console.error('openItem unavailable:', opened.result.value);
    process.exit(1);
  }
  await sleep(1600);

  // Report which sections rendered, so a silent field-name typo is caught.
  const probe = await S('Runtime.evaluate', {
    expression: `(() => {
      const d = document.querySelector('#drawer');
      const q = (s) => d.querySelectorAll(s).length;
      return JSON.stringify({
        open: d.classList.contains('open'),
        h2: Array.from(d.querySelectorAll('.prose h2')).map(e => e.textContent.trim()),
        teach: q('.teach'),
        progLevels: q('.teach-level'),
        qa: q('.teach-qa'),
        rows: q('.teach-row'),
        misconceptions: q('.teach-mis li'),
        official: q('.teach-official'),
        path: q('.teach-path'),
        svg: q('.diagram svg, svg'),
        formulas: q('.formula'),
        height: Math.round(d.scrollHeight),
      });
    })()`,
    returnByValue: true,
  });
  const info = JSON.parse(probe.result.value);
  console.log('[shot] drawer sections:', JSON.stringify(info, null, 1));

  // The drawer body is its own scroll container. Rather than fighting the app's
  // layout with CSS overrides (which shifted the whole drawer and produced a
  // misleading image), scroll the real container to the requested offset and
  // capture the viewport exactly as a reader would see it.
  const scrollTo = Number((args.find((a) => a.startsWith('--scroll=')) || '--scroll=0').split('=')[1]) || 0;
  const scrolled = await S('Runtime.evaluate', {
    expression: `(() => {
      const d = document.querySelector('#drawer');
      const body = d.querySelector('.drawer-body') || d;
      body.scrollTop = ${scrollTo};
      return JSON.stringify({scrollTop: Math.round(body.scrollTop), scrollHeight: body.scrollHeight,
                             clientHeight: body.clientHeight});
    })()`,
    returnByValue: true,
  });
  console.log('[shot] scroll:', scrolled.result.value);
  await sleep(500);

  const shot = await S('Page.captureScreenshot', { format: 'png' });
  writeFileSync(outPng, Buffer.from(shot.data, 'base64'));
  console.log('[shot] wrote', outPng);

  ws.close();
  proc.kill();
  process.exit(info.teach > 0 && info.progLevels > 0 ? 0 : 3);
}

main().catch((e) => {
  console.error('[shot] failed:', e.message);
  try { proc.kill(); } catch { /* ignore */ }
  process.exit(1);
});
