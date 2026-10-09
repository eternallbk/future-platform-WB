/**
 * verify-problem-tracks.mjs — 题库页的赛道分段与「变体实现 / 横向对比」层在**浏览器里**是否真的可用？
 *
 * WHY: 2026-10 用户要求把「模型与训练」手撕题（DPO/GRPO/MHSA/Transformer...）
 * 与 LeetCode 式纯算法题区分开，并给模型手撕题配上变体实现与横向对比。
 * 这些都是前端渲染层的新逻辑：track 分段控件、?kind=exam -> track=exam 兼容路由、
 * 详情页的两个新面板。数据层（build_problem_bank.py 的 byTrack）对了不等于页面对。
 *
 * Usage: node scripts/verify-problem-tracks.mjs [--url URL]
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
const explicit = get('--url', '');
const server = explicit ? null : await serveDir(join(process.cwd(), 'dist'));
const base = explicit || server.url;

const port = 9600 + Math.floor(Math.random() * 90);
const profile = join(process.env.TEMP || '/tmp', `trk-${Date.now()}`);
rmSync(profile, { recursive: true, force: true });
mkdirSync(profile, { recursive: true });
const proc = spawn(CHROME, ['--headless=new', '--disable-gpu', '--no-sandbox',
  '--hide-scrollbars', '--disable-http-cache', `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`, '--window-size=1440,1600', 'about:blank'], { stdio: 'ignore' });
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
const consoleErrors = [];
socket.onmessage = (ev) => {
  const m = JSON.parse(ev.data);
  if (m.method === 'Runtime.exceptionThrown') {
    const d = m.params && m.params.exceptionDetails;
    consoleErrors.push((d && (d.exception && d.exception.description || d.text)) || 'unknown');
  }
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
const say = (ok, msg) => { console.log(`  [${ok ? 'OK ' : 'FAIL'}] ${msg}`); if (!ok) fails++; };

try {
  const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
  const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });
  const S = (m, p) => send(m, p, sessionId);
  await S('Page.enable'); await S('Runtime.enable');
  const evalJson = async (expr) => JSON.parse(
    (await S('Runtime.evaluate', { expression: expr, returnByValue: true })).result.value);

  const goto = async (route, waitFor) => {
    await S('Page.navigate', { url: `${base}/index.html#/${route}` });
    await sleep(1200);
    for (let i = 0; i < 45; i++) {
      const q = await S('Runtime.evaluate', { expression: waitFor, returnByValue: true });
      if ((q.result.value || 0) > 0) return true;
      await sleep(1000);
    }
    return false;
  };
  const cardCount = `document.querySelectorAll('article[data-cat="coding"]').length`;

  console.log('');
  console.log('='.repeat(74));
  console.log('题库赛道分段 · 浏览器校验');
  console.log('='.repeat(74));

  // ---- 1) 默认进入 model 赛道 ----
  const okModel = await goto('problems', cardCount);
  say(okModel, '题库页（默认）渲染出题目卡片');

  const trackSeg = await evalJson(`(() => {
    const g = [...document.querySelectorAll('.segmented')]
      .find((s) => (s.getAttribute('aria-label') || '') === '赛道');
    return JSON.stringify(g ? [...g.querySelectorAll('button')].map((b) => b.textContent.trim()) : []);
  })()`);
  say(trackSeg.length === 3, `赛道分段控件有 3 个按钮：${trackSeg.join(' | ')}`);

  // 默认视图 hash 不必带 track=model；用分段控件的激活按钮判断
  const active0 = await evalJson(`(() => JSON.stringify(
    [...document.querySelectorAll('.segmented[aria-label="赛道"] button')]
      .filter((b) => b.classList.contains('is-on') || b.getAttribute('aria-pressed') === 'true')
      .map((b) => b.textContent.trim())))()`);
  say(active0.some((t) => t.includes('模型与训练')), `默认激活赛道是「模型与训练」（实际 ${active0.join(' | ') || '无激活态'}）`);

  const badgeInfo = await evalJson(`(() => JSON.stringify({
    cards: document.querySelectorAll('article[data-cat="coding"]').length,
    modelBadges: [...document.querySelectorAll('article .badge-info')].filter((e) => e.textContent.includes('模型手撕')).length,
  }))()`);
  const m0 = badgeInfo;
  say(m0.cards > 0 && m0.modelBadges === m0.cards,
      `model 赛道 ${m0.cards} 张卡片全部带「模型手撕」徽标（实际 ${m0.modelBadges}）`);

  // ---- 2) 三个赛道的卡量都要 > 0，且路由同步 ----
  const counts = {};
  for (const [t, label] of [['algorithm', '算法与数据结构'], ['exam', '笔试场景']]) {
    const ok = await goto(`problems?track=${t}`, cardCount);
    const n = (await S('Runtime.evaluate', { expression: cardCount, returnByValue: true })).result.value;
    counts[t] = n;
    say(ok && n > 0, `${label}（track=${t}）有 ${n} 张卡片`);
    const h = (await S('Runtime.evaluate', { expression: 'location.hash', returnByValue: true })).result.value;
    if (t === 'exam') say(/track=exam/.test(h), `exam 路由同步（实际 ${h}）`);
  }
  say(counts.algorithm > counts.exam, `算法赛道题量（${counts.algorithm}）多于笔试赛道（${counts.exam}）`);

  // 旧路由兼容：?kind=exam 读取为 exam 赛道（不强制重写 hash）
  await goto('problems?kind=exam', cardCount);
  const examCards = (await S('Runtime.evaluate', { expression: cardCount, returnByValue: true })).result.value;
  const activeOld = await evalJson(`(() => JSON.stringify(
    [...document.querySelectorAll('.segmented[aria-label="赛道"] button.is-on')]
      .map((b) => b.textContent.trim())))()`);
  say(examCards > 0 && activeOld.some((t) => t.includes('笔试场景')),
      `旧路由 ?kind=exam 落在笔试场景赛道且有 ${examCards} 张卡片（激活：${activeOld.join(' | ') || '无'}）`);

  // ---- 3) 模型手撕详情页：变体实现 + 横向对比 面板 ----
  const okBack = await goto('problems?track=model', cardCount);
  say(okBack, '回到 model 赛道渲染成功');
  // 逐张打开卡片详情，直到找到一个带变体实现的（深读过的模型手撕题）
  const routeList = await evalJson(`(() => JSON.stringify(
    [...document.querySelectorAll('article[data-cat="coding"] .kcard-foot button')]
      .map((b) => b.getAttribute('data-route')).filter(Boolean)))()`);
  let found = null;
  for (const r of routeList.slice(0, 20)) {
    await S('Page.navigate', { url: `${base}/index.html${r}` });
    await sleep(1100);
    const pr = await evalJson(`(() => JSON.stringify({
      variants: Boolean([...document.querySelectorAll('h2,h3,.section-title,.panel-title')].find((e) => e.textContent.includes('变体实现'))),
      compare: Boolean([...document.querySelectorAll('h2,h3,.section-title,.panel-title')].find((e) => e.textContent.includes('横向对比'))),
      codeBlocks: document.querySelectorAll('pre').length,
      compareRows: document.querySelectorAll('.panel table tr').length,
      title: (document.querySelector('.section-title') || {}).textContent || '',
    }))()`);
    if (pr.variants && pr.compare) { found = pr; break; }
    // 返回列表继续找
    await S('Page.navigate', { url: `${base}/index.html#/problems?track=model` });
    await sleep(900);
  }
  say(Boolean(found), '在 model 赛道找到带「变体实现 + 横向对比」双面板的手撕题');
  if (found) {
    say(found.codeBlocks >= 2, `详情页代码块 ≥ 2（主实现 + 变体，实际 ${found.codeBlocks}）`);
    say(found.compareRows >= 2, `横向对比表行数 ≥ 2（实际 ${found.compareRows}）`);
    console.log(`        样例：${found.title.trim().slice(0, 40)}`);
  }

  say(consoleErrors.length === 0,
      `无未捕获的 JS 异常（${consoleErrors.length} 个${consoleErrors.length ? ': ' + consoleErrors[0].slice(0, 120) : ''}）`);

  const shot = await S('Page.captureScreenshot', { format: 'png' });
  mkdirSync('docs/screenshots', { recursive: true });
  writeFileSync('docs/screenshots/_problem-tracks.png', Buffer.from(shot.data, 'base64'));
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
