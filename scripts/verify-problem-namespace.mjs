/**
 * verify-problem-namespace.mjs — 题库页的题号命名空间在**浏览器里**是否真的分开了？
 *
 * WHY: 曾经的 bug 是「卡码网第 102 题（沉没孤岛）顶掉了 LeetCode 102
 * （二叉树的层序遍历）」。它已经在数据层修好了（见 build_problem_bank.py 的
 * KAMACODER_RE 段与 selfcheck 的 check_problem_bank），但数据层对了不等于页面
 * 对：如果前端把 `kbNumber` 当成 `number` 渲染，页面上还是会出现两个 `#102`；
 * 如果 `ns` 过滤参数没被视图读到，点「卡码网」会什么都不发生。
 *
 * 这个脚本走真实点击路径，因此能抓到「标记渲染了但过滤没生效」这一类
 * DOM 检查看不出来的问题。
 *
 * Usage: node scripts/verify-problem-namespace.mjs [--url URL]
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

const port = 9500 + Math.floor(Math.random() * 90);
const profile = join(process.env.TEMP || '/tmp', `ns-${Date.now()}`);
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

/** Every 题号徽标 currently on the page, paired with its card title. */
const BADGES = `(() => {
  const out = [];
  for (const card of document.querySelectorAll('article[data-cat="coding"]')) {
    const t = card.querySelector('.kcard-title');
    const nums = [...card.querySelectorAll('.kcard-cat')]
      .map((e) => e.textContent.trim())
      .filter((s) => s.startsWith('#') || s.startsWith('卡码网'));
    out.push({ title: t ? t.textContent.trim() : '', badges: nums });
  }
  return JSON.stringify(out);
})()`;

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

  console.log('');
  console.log('='.repeat(74));
  console.log('题库题号命名空间 · 浏览器校验');
  console.log('='.repeat(74));

  // ---- 1) LeetCode 视角：默认列表里 #102 必须是「二叉树的层序遍历」----
  // 2026-10 起题库页改为赛道分段（模型与训练 / 算法与数据结构 / 笔试场景），
  // 默认赛道是 model，而题号命名空间（LeetCode vs 卡码网）只在算法赛道有意义。
  const okLc = await goto('problems?track=algorithm', `document.querySelectorAll('article[data-cat="coding"]').length`);
  say(okLc, '题库页渲染出题目卡片');

  let badges = await evalJson(BADGES);
  const c102 = badges.filter((b) => b.badges.includes('#102'));
  say(c102.length === 1, `LeetCode 视角下 #102 只出现 1 次（实际 ${c102.length}）`);
  if (c102.length) {
    say(c102[0].title === '二叉树的层序遍历',
        `#102 的标题是「二叉树的层序遍历」（实际「${c102[0].title}」）`);
  }
  // 默认视图是「全部」，两个编号空间混排 —— 这是有意的。要求不是「沉没孤岛不出现」，
  // 而是它必须**带着卡码网的徽标**出现：同一个列表里 `#102` 只能属于二叉树层序遍历。
  const sunk = badges.find((b) => b.title.includes('沉没孤岛'));
  say(Boolean(sunk) && sunk.badges.includes('卡码网 102'),
      `默认「全部」视图里 沉没孤岛 带的是「卡码网 102」徽标（${sunk ? sunk.badges.join(' / ') : '未出现'}）`);
  const plain102 = badges.filter((b) => b.badges.filter((x) => x === '#102').length > 1);
  say(plain102.length === 0, '没有任何卡片出现重复的 #102 徽标');

  // 顶部三个编号空间按钮都要在
  const nsBtns = await evalJson(`(() => {
    const g = [...document.querySelectorAll('.segmented')]
      .find((s) => (s.getAttribute('aria-label') || '') === '题号来源');
    return JSON.stringify(g ? [...g.querySelectorAll('button')].map((b) => b.textContent.trim()) : []);
  })()`);
  say(nsBtns.length === 3, `「题号来源」分段控件有 3 个按钮（全部 / LeetCode / 卡码网）：${nsBtns.join(' | ')}`);

  // ---- 1b) 只选 LeetCode：卡码网题必须全部消失 ----
  const okLeet = await goto('problems?track=algorithm&ns=leetcode', `document.querySelectorAll('article[data-cat="coding"]').length`);
  say(okLeet, 'ns=leetcode 视图渲染成功');
  const lcBadges = await evalJson(BADGES);
  const leaked = lcBadges.filter((b) => b.badges.some((x) => x.startsWith('卡码网')));
  say(leaked.length === 0,
      `LeetCode 视图里没有卡码网题（${leaked.length} 张泄漏${leaked.length ? '：' + leaked[0].title : ''}）`);
  const lcSunk = lcBadges.find((b) => b.title.includes('沉没孤岛'));
  say(!lcSunk, `LeetCode 视图里不出现「沉没孤岛」（${lcSunk ? '出现了！' : '未出现'}）`);
  const lc102 = lcBadges.filter((b) => b.badges.includes('#102'));
  say(lc102.length === 1 && lc102[0].title === '二叉树的层序遍历',
      `LeetCode 视图里 #102 唯一且是二叉树层序遍历（${lc102.map((b) => b.title).join('、') || '未出现'}）`);

  // ---- 2) 真实点击「卡码网」按钮 -> 过滤必须生效 ----
  const box = await evalJson(`(() => {
    const g = [...document.querySelectorAll('.segmented')]
      .find((s) => (s.getAttribute('aria-label') || '') === '题号来源');
    const b = [...g.querySelectorAll('button')].find((x) => x.textContent.includes('卡码网'));
    const r = b.getBoundingClientRect();
    return JSON.stringify({ x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) });
  })()`);
  await S('Input.dispatchMouseEvent', { type: 'mousePressed', x: box.x, y: box.y, button: 'left', clickCount: 1 });
  await S('Input.dispatchMouseEvent', { type: 'mouseReleased', x: box.x, y: box.y, button: 'left', clickCount: 1 });
  await sleep(1500);

  const hash = (await S('Runtime.evaluate', { expression: 'location.hash', returnByValue: true })).result.value;
  say(/ns=kamacoder/.test(hash), `点击后路由带上 ns=kamacoder（实际 ${hash}）`);

  badges = await evalJson(BADGES);
  say(badges.length > 0, `卡码网视角下有卡片（${badges.length} 张）`);
  const allKama = badges.every((b) => b.badges.every((x) => x.startsWith('卡码网')));
  say(allKama, '卡码网视角下每张卡片的题号徽标都是「卡码网 N」');
  const km102 = badges.find((b) => b.badges.includes('卡码网 102'));
  say(Boolean(km102), `卡码网 102 出现在列表里（标题「${km102 ? km102.title : '—'}」）`);
  if (km102) {
    say(km102.title.includes('沉没孤岛'), '卡码网 102 的标题是「沉没孤岛」');
  }
  const noHash102 = badges.every((b) => !b.badges.includes('#102'));
  say(noHash102, '卡码网视角下不出现任何 #数字 形式的 LeetCode 徽标');

  // ---- 3) 详情页：卡码网 102 打开后题号徽标不能是 #102 ----
  if (km102) {
    const card = await evalJson(`(() => {
      const c = [...document.querySelectorAll('article[data-cat="coding"]')]
        .find((x) => (x.querySelector('.kcard-title') || {}).textContent
          && x.textContent.includes('卡码网 102'));
      if (!c) return JSON.stringify(null);
      const b = c.querySelector('.kcard-foot button');
      return JSON.stringify({ route: b.getAttribute('data-route') });
    })()`);
    if (card && card.route) {
      await S('Page.navigate', { url: `${base}/index.html${card.route}` });
      await sleep(1500);
      const head = await evalJson(`(() => {
        const h = document.querySelector('.section-title');
        const cats = [...document.querySelectorAll('.section-head .kcard-cat')].map((e) => e.textContent.trim());
        return JSON.stringify({ title: h ? h.textContent.trim() : '', cats });
      })()`);
      say(cats_ok(head.cats), `详情页题号徽标是「卡码网 102」而不是「#102」（实际 ${head.cats.join(' / ')}）`);
      say(head.title.includes('沉没孤岛'), `详情页标题是「沉没孤岛」（实际「${head.title}」）`);
    }
  }

  say(consoleErrors.length === 0,
      `无未捕获的 JS 异常（${consoleErrors.length} 个${consoleErrors.length ? ': ' + consoleErrors[0].slice(0, 120) : ''}）`);

  const shot = await S('Page.captureScreenshot', { format: 'png' });
  mkdirSync('docs/screenshots', { recursive: true });
  writeFileSync('docs/screenshots/_problem-namespace.png', Buffer.from(shot.data, 'base64'));
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

function cats_ok(cats) {
  return cats.some((c) => c.startsWith('卡码网')) && !cats.includes('#102');
}
