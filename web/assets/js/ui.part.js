/* ============================================================================
 * Future · 求职学习工作台 — ui.js (part 1b)
 * Theme popover · Toast wiring · Command palette & global search · Detail
 * drawer · Hash router · Shell (rail/topbar/aside) · Global event delegation
 * ========================================================================= */

/* ======================== THEME POPOVER ================================= */

let popoverNode = null;

function closePopover() {
  if (popoverNode) { popoverNode.remove(); popoverNode = null; }
  document.removeEventListener('click', onDocClickForPopover, true);
  document.removeEventListener('keydown', onKeyForPopover, true);
}
function onDocClickForPopover(e) {
  if (popoverNode && !popoverNode.contains(e.target) && !e.target.closest('#btn-theme')) closePopover();
}
function onKeyForPopover(e) { if (e.key === 'Escape') closePopover(); }

export function openThemePopover(anchor) {
  if (popoverNode) { closePopover(); return; }
  const p = state.prefs;
  const node = el('div', { class: 'popover', role: 'dialog', 'aria-label': '主题设置' });
  node.innerHTML = `
    <div class="popover-title">配色主题</div>
    <div class="theme-grid">
      ${THEMES.map((t) => `
        <button class="theme-opt${t.id === p.theme ? ' is-on' : ''}" data-act="set-theme" data-theme-id="${t.id}">
          <span class="swatches">${t.swatches.map((s) => `<i class="swatch" style="background:${s}"></i>`).join('')}</span>
          <span>${esc(t.zh)}</span>
        </button>`).join('')}
    </div>
    <div class="popover-title" style="margin-top:var(--sp-3)">强调色</div>
    <div class="accent-row">
      ${ACCENTS.map((a) => `<button class="accent-dot${a.id === p.accent ? ' is-on' : ''}" data-act="set-accent"
        data-accent-id="${a.id}" style="background:${a.hex}" title="${esc(a.zh)}" aria-label="强调色 ${esc(a.zh)}"></button>`).join('')}
    </div>
    <div class="popover-title" style="margin-top:var(--sp-3)">显示</div>
    <div style="display:flex;flex-direction:column;gap:6px;padding:0 var(--sp-2)">
      <label class="row" style="justify-content:space-between;font-size:var(--fs-2xs);cursor:pointer">
        <span>减少动画</span>
        <span class="switch" role="switch" tabindex="0" aria-checked="${p.reducedMotion}" data-act="toggle-motion"></span>
      </label>
    </div>`;

  document.body.append(node);
  const r = anchor.getBoundingClientRect();
  const width = node.offsetWidth || 250;
  node.style.top = `${r.bottom + 8}px`;
  node.style.left = `${Math.max(12, Math.min(r.right - width, window.innerWidth - width - 12))}px`;
  popoverNode = node;
  setTimeout(() => {
    document.addEventListener('click', onDocClickForPopover, true);
    document.addEventListener('keydown', onKeyForPopover, true);
  }, 0);
}

/* ======================= COMMAND PALETTE / SEARCH ======================= */

const paletteState = { open: false, cursor: 0, rows: [] };

export function openPalette(seed = '') {
  if (paletteState.open) return;
  paletteState.open = true;
  paletteState.cursor = 0;

  const wrap = el('div', { class: 'palette-wrap', id: 'palette-wrap' });
  wrap.innerHTML = `
    <div class="palette" role="dialog" aria-modal="true" aria-label="命令面板">
      <div class="palette-input">
        ${icon('i-search')}
        <input id="palette-input" type="text" placeholder="搜索知识卡片、岗位、题目、仓库、分类…  或输入 > 执行命令"
               autocomplete="off" spellcheck="false" aria-label="搜索">
        <button class="icon-btn" data-act="close-palette" aria-label="关闭">${icon('i-x')}</button>
      </div>
      <div class="palette-body" id="palette-body" role="listbox" aria-label="搜索结果"></div>
      <div class="palette-foot">
        <span><kbd>↑</kbd><kbd>↓</kbd> 选择</span>
        <span><kbd>Enter</kbd> 打开</span>
        <span><kbd>Esc</kbd> 关闭</span>
        <span style="margin-left:auto">共 ${state.items.length} 条知识 · ${state.jobs.length} 个岗位 · ${state.problems.length} 道题</span>
      </div>
    </div>`;
  $('#palette-root').append(wrap);

  const input = $('#palette-input');
  input.value = seed;
  input.addEventListener('input', () => { paletteState.cursor = 0; renderPalette(input.value); });
  wrap.addEventListener('mousedown', (e) => { if (e.target === wrap) closePalette(); });
  input.focus();
  if (seed) input.select();
  renderPalette(seed);
}

export function closePalette() {
  paletteState.open = false;
  const w = $('#palette-wrap');
  if (w) w.remove();
}

function paletteMove(delta) {
  if (!paletteState.rows.length) return;
  paletteState.cursor = (paletteState.cursor + delta + paletteState.rows.length) % paletteState.rows.length;
  paintPaletteCursor();
}

function paintPaletteCursor() {
  const body = $('#palette-body');
  if (!body) return;
  $$('.pal-item', body).forEach((n, i) => n.classList.toggle('is-cursor', i === paletteState.cursor));
  const cur = $$('.pal-item', body)[paletteState.cursor];
  if (cur) cur.scrollIntoView({ block: 'nearest' });
}

export function paletteCommit() {
  const row = paletteState.rows[paletteState.cursor];
  if (!row) return;
  closePalette();
  row.run();
}

const COMMANDS = [
  { id: 'cmd:digest', label: '前往：每日更新流', icon: 'i-feed', group: '命令', run: () => go('#/digest') },
  { id: 'cmd:kb', label: '前往：知识卡片', icon: 'i-layers', group: '命令', run: () => go('#/knowledge') },
  { id: 'cmd:formula', label: '前往：公式剖析', icon: 'i-sigma', group: '命令', run: () => go('#/formulas') },
  { id: 'cmd:problems', label: '前往：题库定位', icon: 'i-code', group: '命令', run: () => go('#/problems') },
  { id: 'cmd:jobs', label: '前往：岗位看板', icon: 'i-briefcase', group: '命令', run: () => go('#/jobs') },
  { id: 'cmd:skills', label: '前往：技能矩阵', icon: 'i-target', group: '命令', run: () => go('#/skills') },
  { id: 'cmd:roadmap', label: '前往：学习路线', icon: 'i-route', group: '命令', run: () => go('#/roadmap') },
  { id: 'cmd:repos', label: '前往：仓库与课程', icon: 'i-repo', group: '命令', run: () => go('#/repos') },
  { id: 'cmd:starred', label: '前往：收藏夹', icon: 'i-star', group: '命令', run: () => go('#/starred') },
  { id: 'cmd:progress', label: '前往：进度与统计', icon: 'i-chart', group: '命令', run: () => go('#/progress') },
  { id: 'cmd:pipeline', label: '前往：采集与运行', icon: 'i-flask', group: '命令', run: () => go('#/pipeline') },
  { id: 'cmd:theme', label: '切换主题（深/浅）', icon: 'i-sun', group: '命令', run: () => { toggleThemeKind(); toast('已切换主题', 'info', 1500); } },
  { id: 'cmd:accent', label: '更换强调色', icon: 'i-palette', group: '命令', run: () => openThemePopover($('#btn-theme')) },
  { id: 'cmd:refresh', label: '重新加载本地数据层', icon: 'i-refresh', group: '命令', run: () => reloadData() },
  { id: 'cmd:export', label: '导出我的进度（JSON）', icon: 'i-download', group: '命令', run: () => exportProgress() },
  { id: 'cmd:feedback', label: '写出学习信号（让采集器学习你的偏好）', icon: 'i-refresh', group: '命令', run: () => exportFeedback() },
  { id: 'cmd:print', label: '打印当前视图', icon: 'i-download', group: '命令', run: () => window.print() },
  { id: 'cmd:today', label: '只看今天的更新', icon: 'i-clock', group: '命令', run: () => { go('#/digest'); } },
];

function fuzzyScore(needle, hay) {
  const n = needle.toLowerCase();
  const h = String(hay || '').toLowerCase();
  if (!n) return 1;
  const idx = h.indexOf(n);
  if (idx >= 0) return 1000 - idx * 3 - Math.min(h.length, 400) * 0.05;
  // subsequence fallback
  let i = 0, hits = 0;
  for (const ch of h) { if (ch === n[i]) { i++; hits++; if (i === n.length) break; } }
  return i === n.length ? 240 - h.length * 0.05 + hits : 0;
}

function scoreRow(q, row) {
  if (!q) return 1;
  let best = fuzzyScore(q, row.label) * 1.5;
  for (const t of row.extra || []) best = Math.max(best, fuzzyScore(q, t));
  return best;
}

function renderPalette(query) {
  const q = String(query || '').trim();
  const body = $('#palette-body');
  if (!body) return;

  const rows = [];

  // Commands: shown when empty, or when prefixed with >
  const commandMode = q.startsWith('>');
  const cq = commandMode ? q.slice(1).trim() : q;

  if (!q || commandMode) {
    for (const c of COMMANDS) {
      if (cq && fuzzyScore(cq, c.label) <= 0) continue;
      rows.push({ kind: 'cmd', group: '命令', label: c.label, icon: c.icon, hint: '⌘', run: c.run, extra: [c.id] });
    }
  }

  if (!commandMode) {
    if (!q) {
      // Recents + today's top items when the palette is empty.
      const top = [...state.items].sort((a, b) => b.relevance - a.relevance).slice(0, 6);
      for (const it of top) {
        rows.push(itemRow(it, '今日高相关'));
      }
      for (const c of CATEGORIES) {
        rows.push({ kind: 'cat', group: '分类', label: `${c.zh} · ${c.en}`, icon: c.icon, cat: c.id,
          hint: `${itemsOf(c.id).length}`, run: () => go(`#/knowledge?cat=${c.id}`) });
      }
    } else {
      for (const it of state.items) {
        const s = scoreRow(q, { label: it.title, extra: [it.titleZh, it.summary, it.category, ...it.tags, ...it.entities, it.channel] });
        if (s > 0) rows.push({ ...itemRow(it, CAT_BY_ID[it.category] ? CAT_BY_ID[it.category].zh : '知识'), score: s + it.relevance * 0.5 });
      }
      for (const j of state.jobs) {
        const s = scoreRow(q, { label: `${j.company} ${j.title}`, extra: [...j.directions, ...j.cities, j.notes] });
        if (s > 0) rows.push({ kind: 'job', group: '岗位', label: `${j.company} · ${j.title}`, icon: 'i-briefcase', hint: j.pay || '', cat: 'job', score: s, run: () => go(`#/jobs?focus=${encodeURIComponent(j.id)}`) });
      }
      for (const p of state.problems) {
        const s = scoreRow(q, { label: p.title, extra: [...p.topics, p.prompt] });
        if (s > 0) rows.push({ kind: 'problem', group: '题库', label: p.title, icon: 'i-code', hint: p.difficulty, cat: 'coding', score: s, run: () => go(`#/problems?id=${encodeURIComponent(p.id)}`) });
      }
      for (const r of state.repos) {
        const s = scoreRow(q, { label: `${r.owner}/${r.name}`, extra: [r.why, r.area, ...(r.studyPlan || [])] });
        if (s > 0) rows.push({ kind: 'repo', group: '仓库', label: `${r.owner}/${r.name}`, icon: 'i-repo', hint: r.stars ? `★${r.stars}` : '', cat: 'course', score: s, run: () => r.url && window.open(r.url, '_blank', 'noopener') });
      }
      for (const t of state.tracks) {
        const s = scoreRow(q, { label: t.name, extra: [t.goal, ...t.modules.map((m) => m.title)] });
        if (s > 0) rows.push({ kind: 'track', group: '路线', label: t.name, icon: 'i-route', hint: `${t.weeks}周`, cat: 'system', score: s, run: () => go(`#/roadmap?track=${encodeURIComponent(t.id)}`) });
      }
    }
  }

  const sorted = q && !commandMode ? rows.sort((a, b) => (b.score || 0) - (a.score || 0)) : rows;
  const limited = sorted.slice(0, 60);
  paletteState.rows = limited;
  paletteState.cursor = clamp(paletteState.cursor, 0, Math.max(0, limited.length - 1));

  if (!limited.length) {
    body.innerHTML = `<div class="empty" style="padding:var(--sp-8)">${icon('i-search')}<h4>没有匹配结果</h4>
      <p>试试「多模态」「DPO」「世界模型」，或用 <code>&gt;</code> 前缀执行命令。</p></div>`;
    return;
  }

  const groups = new Map();
  for (const r of limited) {
    const g = r.group || '结果';
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g).push(r);
  }
  let idx = 0;
  const html = [];
  for (const [g, list] of groups) {
    html.push(`<div class="pal-group-label">${esc(g)}</div>`);
    for (const r of list) {
      const i = idx++;
      const hl = q && !commandMode ? highlightMatch(r.label, q) : esc(r.label);
      html.push(`<div class="pal-item${i === paletteState.cursor ? ' is-cursor' : ''}" role="option" data-idx="${i}"
        ${r.cat ? `data-cat="${esc(r.cat)}"` : ''}>${icon(r.icon || 'i-info')}<span>${hl}</span>
        ${r.hint ? `<span class="pal-hint">${esc(String(r.hint))}</span>` : ''}</div>`);
    }
  }
  body.innerHTML = html.join('');
  body.querySelectorAll('.pal-item').forEach((node) => {
    node.addEventListener('click', () => {
      paletteState.cursor = Number(node.dataset.idx) || 0;
      paletteCommit();
    });
    node.addEventListener('mousemove', () => {
      paletteState.cursor = Number(node.dataset.idx) || 0;
      paintPaletteCursor();
    });
  });
}

function highlightMatch(label, q) {
  const s = String(label);
  const i = s.toLowerCase().indexOf(String(q).toLowerCase());
  if (i < 0) return esc(s);
  return esc(s.slice(0, i)) + '<mark>' + esc(s.slice(i, i + q.length)) + '</mark>' + esc(s.slice(i + q.length));
}

function itemRow(it, group) {
  return {
    kind: 'item', group, label: it.title, icon: 'i-layers', cat: it.category,
    hint: relTime(it.publishedAt || it.fetchedAt),
    run: () => openItem(it.id),
  };
}

/* ============================== DRAWER ================================== */

let drawerReturnFocus = null;

export function openDrawer({ eyebrow, title, meta = '', body = '', foot = '', cat = null }) {
  const d = $('#drawer');
  drawerReturnFocus = document.activeElement;
  $('#drawer-eyebrow').textContent = eyebrow || '详情';
  $('#drawer-title').innerHTML = title || '—';
  $('#drawer-meta').innerHTML = meta;
  $('#drawer-body').innerHTML = body;
  $('#drawer-foot').innerHTML = foot;
  if (cat) d.dataset.cat = cat; else delete d.dataset.cat;
  d.classList.add('open');
  d.setAttribute('aria-hidden', 'false');
  $('#scrim').classList.add('open');
  $('#drawer-close').focus();
}

export function closeDrawer() {
  const d = $('#drawer');
  d.classList.remove('open');
  d.setAttribute('aria-hidden', 'true');
  $('#scrim').classList.remove('open');
  if (drawerReturnFocus && drawerReturnFocus.focus) drawerReturnFocus.focus();
}

export function refreshDrawer() {
  const d = $('#drawer');
  if (!d.classList.contains('open')) return;
  const id = d.dataset.itemId;
  if (id && state.byId.has(id)) openItem(id, { keepScroll: true });
}

/* ============================== ROUTER ================================== */

export const VIEWS = {}; // filled by views.js

export function parseHash() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [path, qs] = raw.split('?');
  const id = (path || 'dashboard').split('/')[0] || 'dashboard';
  const params = {};
  if (qs) for (const [k, v] of new URLSearchParams(qs)) params[k] = v;
  return { id, params };
}

export function go(hash, { replace = false } = {}) {
  if (replace) history.replaceState(null, '', hash);
  else location.hash = hash;
  if (replace) render();
}

let lastRenderKey = '';

export function render() {
  const { id, params } = parseHash();
  const view = VIEWS[id] || VIEWS.dashboard;
  const key = `${id}|${JSON.stringify(params)}|${state.filters.q}|${[...state.filters.cat].join(',')}|${[...state.filters.src].join(',')}|${state.sort}|${params.id || ''}|${params.track || ''}`;

  state.route = id;
  state.params = params;

  const host = $('#view');
  const sameView = lastRenderKey.split('|')[0] === id;
  const scrollTop = $('.main').scrollTop;
  host.innerHTML = view.render(params);
  if (typeof view.after === 'function') view.after(params);

  // Only jump to top when the route (not just its filters) changed.
  if (!sameView) $('.main').scrollTop = 0;
  else $('.main').scrollTop = scrollTop;

  lastRenderKey = key;

  $$('.nav-item').forEach((b) => b.classList.toggle('is-active', b.dataset.route === `#/${id}`));
  document.title = `${view.title || '工作台'} · Future`;
  if (window.innerWidth <= 940) $('#rail').classList.remove('open');
  updateNavCounts();
}

/* =============================== SHELL ================================== */

export function updateNavCounts() {
  const byCat = new Map();
  for (const it of state.items) byCat.set(it.category, (byCat.get(it.category) || 0) + 1);
  const set = (sel, n) => { const n2 = $(sel); if (n2) n2.textContent = String(n); };
  set('#nav-count-digest', state.items.filter((i) => dayOf(i) === dateKey()).length || state.items.length);
  set('#nav-count-cats', CATEGORIES.filter((c) => byCat.get(c.id)).length);
  set('#nav-count-kb', state.items.length);
  set('#nav-count-formula', state.formulas.length);
  set('#nav-count-problems', state.problems.length);
  set('#nav-count-repos', state.repos.length + state.courses.length);
  set('#nav-count-jobs', state.jobs.length);
  set('#nav-count-skills', state.skills.length);
  set('#nav-count-star', starCount());
  set('#nav-count-pipeline', state.runs.length);

  const railCats = $('#rail-cats');
  if (railCats) {
    railCats.innerHTML = CATEGORIES.map((c) => {
      const n = byCat.get(c.id) || 0;
      if (!n) return '';
      return `<button class="nav-item" data-route="#/knowledge?cat=${c.id}" data-cat="${c.id}">
        <span class="nav-dot"></span><span class="nav-label">${esc(c.zh)}</span><span class="nav-count">${n}</span></button>`;
    }).join('') || `<div style="padding:var(--sp-2) var(--sp-3);font-size:var(--fs-3xs);color:var(--fg-3)">暂无分类数据</div>`;
  }

  const st = $('#rail-status');
  if (st) {
    const m = state.manifest;
    const last = m && (m.lastRunAt || m.generatedAt);
    const okCh = m && m.channelsOk != null ? m.channelsOk : null;
    const totCh = m && m.channelsTotal != null ? m.channelsTotal : null;
    const cls = state.loadErrors.length ? 'warn' : 'ok';
    st.innerHTML = `${icon('i-database', cls, 13)}
      <span class="${cls}">${state.loadErrors.length ? `${state.loadErrors.length} 个数据文件缺失` : '数据层正常'}</span>
      ${buildStamp()
        ? `<span class="tnum" data-tip="当前页面运行的构建指纹（发布时按资源内容哈希生成）。若你刚更新过工作台、但这里没变，说明浏览器还在用缓存的旧脚本 —— 强制刷新一次即可（Ctrl+F5 / Cmd+Shift+R）。">${esc(buildStamp().slice(0, 6))}</span>`
        : ''}
      ${last ? `<span style="margin-left:auto" data-tip="最近一次采集">${esc(relTime(last))}</span>` : ''}
      ${okCh != null && totCh != null ? `<span data-tip="采集渠道成功率" class="tnum">${okCh}/${totCh}</span>` : ''}`;
  }
}

/** 当前页面运行的构建指纹，来自 index.html 的 `<meta name="app-build">`。
 *  build_site.py 在发布时把它替换成资源内容哈希，所以它同时是「资源 URL 的
 *  版本号」和「排障用的指纹」。本地直接开 web/index.html 时是 'dev'，
 *  此时返回空串，不在界面上显示无意义的 dev。 */
function buildStamp() {
  const el = document.querySelector('meta[name="app-build"]');
  const v = el ? String(el.getAttribute('content') || '') : '';
  return v && v !== 'dev' ? v : '';
}

/** 启动后核对「页面上跑的脚本」是不是最新发布的那一版，并在必要时自愈。
 *
 *  WHY: 线上站点用的是**同一条固定链接**，每次发布都原地覆盖 assets/js/app.js。
 *  浏览器若缓存了旧脚本，工作台不会报错，只会「少显示内容」—— 第一次暴露这个
 *  故障的现象是「题库定位只有 47 题」（47 = 22 手撕 + 25 笔试，正是退回到
 *  jobs.json 备用分支的结果），非常容易被误判成服务端数据坏了。
 *
 *  两道保险：
 *    1. `_headers` 把 HTML 设成 no-cache、assets 带内容哈希 —— 托管方读它时，
 *       新版在下一次普通刷新就生效。但 `_headers` 是**可选的**（脚本注释里也
 *       写了「不读它的主机只是忽略它」），所以不能只靠它。
 *    2. 这个函数：index.html 取回来比对指纹。不一致就带一个新查询串跳转一次 ——
 *       查询串一变，浏览器必须重新取 index.html，而新 index.html 里的 `?v=`
 *       指向正确的资源，于是页面回到一致状态。
 *
 *  自动跳转只做一次（sessionStorage 记账），所以「托管方连 index.html 都发旧的」
 *  这种极端情况下也不会来回刷屏：第二次只提示、不再跳。
 */
export async function checkForNewBuild() {
  const local = buildStamp();
  if (!local) return;                       // 本地开发或无指纹，不做检查
  let remote = '';
  try {
    const res = await fetch(`index.html?_buildcheck=${Date.now()}`, { cache: 'no-store' });
    if (!res.ok) return;
    const text = await res.text();
    const m = text.match(/<meta name="app-build" content="([^"]*)">/);
    remote = m ? m[1] : '';
  } catch {
    return;                                  // 离线/跨域失败：静默跳过，一次自检失败不影响使用
  }
  if (!remote || remote === 'dev' || remote === local) return;

  const KEY = 'future.buildReloadedFor';
  let seen = '';
  try { seen = sessionStorage.getItem(KEY) || ''; } catch { /* 隐私模式 */ }

  if (seen !== remote) {
    try { sessionStorage.setItem(KEY, remote); } catch { /* 隐私模式 */ }
    const url = `${location.pathname}?v=${encodeURIComponent(remote)}${location.hash || ''}`;
    location.replace(url);
    return;
  }

  // 已经自动跳过一次仍是旧版 -> 托管端大概率连 HTML 都在发缓存，只能请读者出手。
  toast(`工作台有新版本（${remote.slice(0, 6)}），当前页面是 ${local.slice(0, 6)}。`
      + `强制刷新一次即可看到最新内容（Ctrl+F5 / Cmd+Shift+R）。`, 'info', 14000);
}

/* ====================== GLOBAL EVENT DELEGATION ========================= */

export function reloadData() {
  toast('正在重新读取数据层…', 'info', 1600);
  Store.boot().then(() => {
    applyPrefs();
    render();
    toast(`数据已刷新：${state.items.length} 条知识、${state.jobs.length} 个岗位`, 'ok');
  });
}

/* Build the signal payload the collector consumes.
 *
 * WHY THIS EXISTS: stars, reading status and mastery all live in localStorage,
 * which the Python collector cannot read. Without an export, content selection
 * can never adapt to what the reader actually values - the workbench would keep
 * scoring purely on keyword/relevance heuristics forever. This payload is written
 * to web/data/feedback.json (locally, or via the File System Access API when the
 * browser supports it) and collect.py uses it to (a) give a small scoring bonus to
 * categories and channels the reader engages with, and (b) let plan_deep_read.py
 * prefer those categories when filling its quota.
 *
 * Privacy: it contains item ids and category names only - no notes, no personal
 * data - and web/data/feedback.json is excluded from the published site.
 */
export function buildFeedbackPayload() {
  const catOf = new Map(state.items.map((i) => [i.id, i.category]));
  const chanOf = new Map(state.items.map((i) => [i.id, i.channel]));
  const byCategory = {};
  const byChannel = {};
  const bump = (obj, key, n = 1) => {
    if (!key) return;
    obj[key] = (obj[key] || 0) + n;
  };

  for (const id of Object.keys(state.user.starred)) {
    bump(byCategory, catOf.get(id));
    bump(byChannel, chanOf.get(id));
  }
  for (const [id, st] of Object.entries(state.user.status || {})) {
    // "已掌握" is the strongest signal; "学习中" a weaker one.
    bump(byCategory, catOf.get(id), st === 'done' ? 3 : 1);
    bump(byChannel, chanOf.get(id), st === 'done' ? 2 : 1);
  }
  for (const [id, lv] of Object.entries(state.user.mastery || {})) {
    bump(byCategory, catOf.get(id), Number(lv) || 0);
  }

  return {
    version: 1,
    exportedAt: new Date().toISOString(),
    exportedBy: 'Future workbench (browser)',
    summary: completionStats(),
    starredCount: Object.keys(state.user.starred).length,
    byCategory,
    byChannel,
    // Read states per item are useful for a future "resurface what I stalled on".
    stalledIds: Object.entries(state.user.status || {})
      .filter(([, v]) => v === 'reading').map(([k]) => k).slice(0, 200),
  };
}

/** Persist the feedback file next to the other data files.
 *
 * Two transports, because there is no server:
 *   · File System Access API (Chrome/Edge): writes straight into web/data/ after
 *     a one-time directory grant. This is the path that makes the loop automatic.
 *   · Otherwise: falls back to a normal download, and the README explains to drop
 *     it into web/data/feedback.json.
 */
export async function exportFeedback() {
  const payload = buildFeedbackPayload();
  const text = JSON.stringify(payload, null, 2);
  try {
    if (window.showDirectoryPicker) {
      const dir = await window.showDirectoryPicker({ id: 'future-data', mode: 'readwrite' });
      const fh = await dir.getFileHandle('feedback.json', { create: true });
      const w = await fh.createWritable();
      await w.write(text);
      await w.close();
      toast('已写入 feedback.json，下一轮采集会使用你的收藏与进度', 'ok', 4200);
      return;
    }
  } catch (e) {
    if (e && e.name === 'AbortError') return;   // user cancelled the picker
    // fall through to the download path
  }
  const blob = new Blob([text], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'feedback.json';
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  toast('已导出 feedback.json，请放入 web/data/ 后重新采集', 'warn', 5200);
}

export function exportProgress() {
  const payload = {
    exportedAt: new Date().toISOString(),
    app: 'Future · 求职学习工作台',
    prefs: state.prefs,
    user: state.user,
    summary: completionStats(),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `future-progress-${dateKey()}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  toast('进度已导出为 JSON', 'ok');
}

export async function copyText(text, okMsg = '已复制到剪贴板') {
  try {
    await navigator.clipboard.writeText(text);
    toast(okMsg, 'ok', 1800);
  } catch {
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.append(ta); ta.select();
    try { document.execCommand('copy'); toast(okMsg, 'ok', 1800); }
    catch { toast('复制失败，请手动选择文本', 'warn'); }
    ta.remove();
  }
}

const ACTIONS = {
  'set-theme': (t) => { setTheme(t.dataset.themeId); closePopover(); openThemePopover($('#btn-theme')); },
  'set-accent': (t) => { setAccent(t.dataset.accentId); closePopover(); openThemePopover($('#btn-theme')); },
  'toggle-motion': () => { state.prefs.reducedMotion = !state.prefs.reducedMotion; applyPrefs(); saveUser(); if (popoverNode) { closePopover(); openThemePopover($('#btn-theme')); } },

  'close-palette': () => closePalette(),
  'open-palette': () => openPalette(),
  'close-drawer': () => closeDrawer(),
  'open-theme': (t) => openThemePopover(t),
  'reload': () => reloadData(),
  'export': () => exportProgress(),
  'export-feedback': () => exportFeedback(),
  'print': () => window.print(),
  'copy': (t) => copyText(t.dataset.copy || '', t.dataset.copyMsg || '已复制'),
  'toggle-rail': () => $('#rail').classList.toggle('open'),

  'star': (t) => {
    const on = toggleStar(t.dataset.id);
    t.classList.toggle('is-on', on);
    t.setAttribute('aria-pressed', String(on));
    updateNavCounts();
    toast(on ? '已加入收藏' : '已取消收藏', on ? 'ok' : 'info', 1400);
  },
  'status': (t) => {
    const next = setStatus(t.dataset.id, t.dataset.status);
    toast({ unread: '已标记为未读', reading: '标记为学习中', done: '标记为已掌握' }[next], next === 'done' ? 'ok' : 'info', 1400);
    render();
  },
  'open-item': (t) => openItem(t.dataset.id),
  'open-job': (t) => openJob(t.dataset.id),
  'open-problem': (t) => { go(`#/problems?id=${encodeURIComponent(t.dataset.id)}`); },
  'open-track': (t) => { go(`#/roadmap?track=${encodeURIComponent(t.dataset.id)}`); },
  'open-repo': (t) => { const r = state.repos.find((x) => x.id === t.dataset.id); if (r && r.url) window.open(r.url, '_blank', 'noopener'); },

  'toggle-cat': (t) => {
    const c = t.dataset.cat;
    if (state.filters.cat.has(c)) state.filters.cat.delete(c); else state.filters.cat.add(c);
    render();
  },
  'toggle-src': (t) => {
    const c = t.dataset.src;
    if (state.filters.src.has(c)) state.filters.src.delete(c); else state.filters.src.add(c);
    render();
  },
  'toggle-tag': (t) => {
    const c = t.dataset.tag;
    if (state.filters.tag.has(c)) state.filters.tag.delete(c); else state.filters.tag.add(c);
    render();
  },
  'clear-filters': () => { state.filters.cat.clear(); state.filters.src.clear(); state.filters.tag.clear(); state.filters.q = ''; state.filters.starredOnly = false; state.filters.status = null; state.sort = 'relevance'; render(); },
  'filter-status': (t) => { state.filters.status = t.dataset.status || null; render(); },
  'digest-group': (t) => { state.prefs.digestGroup = t.dataset.group || 'day'; saveUser(); render(); },
  'sort': (t) => { state.sort = t.dataset.sort; state.page = 1; render(); },
  'page': (t) => {
    const n = Number(t.dataset.page);
    if (!Number.isFinite(n) || n < 1) return;
    state.page = n;
    render();
    const m = document.querySelector('.main');
    if (m) m.scrollTo({ top: 0, behavior: 'smooth' });
  },
  'set-perpage': (t) => {
    const v = Number(t.dataset.value);
    state.perPage = Number.isFinite(v) ? v : 60;
    state.page = 1;
    saveUser();
    render();
  },
  'starred-only': () => { state.filters.starredOnly = !state.filters.starredOnly; render(); },
  'toast': (t) => toast(t.dataset.msg || '', t.dataset.kind || 'info'),
  'print-view': () => window.print(),
  'toggle-expand': (t) => {
    const target = document.getElementById(t.dataset.target);
    if (!target) return;
    const open = target.hasAttribute('hidden') === false;
    if (open) target.setAttribute('hidden', ''); else target.removeAttribute('hidden');
    t.classList.toggle('is-open', !open);
    t.setAttribute('aria-expanded', String(!open));
    const svg = t.querySelector('svg');
    if (svg) svg.classList.toggle('is-open', !open);
  },
  'toggle-task': (t) => {
    const k = t.dataset.key;
    if (state.user.tasks[k]) delete state.user.tasks[k]; else state.user.tasks[k] = true;
    saveUser();
    t.classList.toggle('on', Boolean(state.user.tasks[k]));
    const row = t.closest('.task'); if (row) row.classList.toggle('on', Boolean(state.user.tasks[k]));
    updateTaskProgress();
  },
  'nav': (t) => go(t.dataset.hash),
  'open-url': (t) => { const u = safeUrl(t.dataset.url); if (u) window.open(u, '_blank', 'noopener'); },
  'job-stage': (t) => {
    const { id, stage } = t.dataset;
    state.user.jobStage[id] = stage; saveUser(); render();
    toast('已更新投递状态', 'ok', 1400);
  },
  'mastery': (t) => {
    const id = t.dataset.id;
    const v = Number(t.dataset.v);
    state.user.mastery[id] = state.user.mastery[id] === v ? v - 1 : v;
    saveUser(); render();
  },
  'focus-q': () => { const i = $('#q-input'); if (i) { i.focus(); i.select(); } },
  'scroll-to': (t) => {
    const n = document.getElementById(t.dataset.target);
    if (n) n.scrollIntoView({ behavior: 'smooth', block: 'start' });
  },
};

function updateTaskProgress() {
  const all = $$('.task').length;
  if (!all) return;
  const done = $$('.task.on').length;
  $$('[data-task-progress]').forEach((n) => { n.textContent = `${done}/${all}`; });
  $$('[data-task-bar]').forEach((n) => { n.style.width = `${(done / all) * 100}%`; });
}

document.addEventListener('click', (e) => {
  const t = e.target.closest('[data-act]');
  if (!t) return;
  const fn = ACTIONS[t.dataset.act];
  if (!fn) return;
  e.preventDefault();
  e.stopPropagation();
  fn(t);
});

/* In-place editing of a personal note inside the drawer. */
document.addEventListener('input', (e) => {
  const t = e.target.closest('[data-note-for]');
  if (!t) return;
  state.user.notes[t.dataset.noteFor] = t.value;
  debouncedSave();
});
const debouncedSave = debounce(saveUser, 600);

export function installKeyboard() {
  document.addEventListener('keydown', (e) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement && document.activeElement.tagName);

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); paletteState.open ? closePalette() : openPalette(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'p') { /* let browser print */ return; }

    if (paletteState.open) {
      if (e.key === 'ArrowDown') { e.preventDefault(); paletteMove(1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); paletteMove(-1); }
      else if (e.key === 'Enter') { e.preventDefault(); paletteCommit(); }
      else if (e.key === 'Escape') { e.preventDefault(); closePalette(); }
      return;
    }

    if (e.key === 'Escape') {
      if ($('#drawer').classList.contains('open')) { closeDrawer(); return; }
      if (popoverNode) { closePopover(); return; }
      $('#rail').classList.remove('open');
      return;
    }

    if (typing) return;

    if (e.key === '/') { e.preventDefault(); openPalette(); return; }
    if (e.key.toLowerCase() === 'g') { pendingG = true; setTimeout(() => { pendingG = false; }, 900); return; }
    if (pendingG) {
      const map = { d: '#/digest', k: '#/knowledge', j: '#/jobs', r: '#/roadmap', p: '#/problems', f: '#/formulas', h: '#/dashboard', s: '#/starred', c: '#/categories' };
      const target = map[e.key.toLowerCase()];
      if (target) { e.preventDefault(); pendingG = false; go(target); }
    }
  });
}
let pendingG = false;

export function installShell() {
  $('#rail-open').addEventListener('click', () => $('#rail').classList.toggle('open'));
  $('#rail-close').addEventListener('click', () => $('#rail').classList.remove('open'));
  $('#cmd-trigger').addEventListener('click', () => openPalette());
  $('#btn-theme').addEventListener('click', (e) => openThemePopover(e.currentTarget));
  $('#btn-refresh').addEventListener('click', reloadData);
  $('#btn-print').addEventListener('click', () => window.print());
  $('#drawer-close').addEventListener('click', closeDrawer);
  $('#scrim').addEventListener('click', closeDrawer);

  document.addEventListener('click', (e) => {
    const link = e.target.closest('[data-route]');
    if (!link) return;
    if (link.dataset.act) return; // explicit actions win
    e.preventDefault();
    go(link.dataset.route);
  });

  window.addEventListener('hashchange', render);
  window.addEventListener('resize', debounce(() => { if (window.innerWidth > 940) $('#rail').classList.remove('open'); }, 200));

  // Delegated listener for the filter inputs, wired per-render by views.
  document.addEventListener('keydown', (e) => {
    if (e.target && e.target.id === 'q-input' && e.key === 'Enter') {
      state.filters.q = e.target.value.trim();
      render();
    }
  });
  document.addEventListener('input', debounce((e) => {
    if (e.target && e.target.id === 'q-input') {
      state.filters.q = e.target.value.trim();
      render();
    }
  }, 260));
}
