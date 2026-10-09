/* ============================================================================
 * Future · 求职学习工作台 — app.js
 * GENERATED FILE — do not edit by hand.
 * Sources: core.part.js, ui.part.js, views.part.js, views2.part.js
 * Rebuild: node scripts/build.mjs
 * ========================================================================= */
'use strict';

/* ===== core.part.js — 1695 lines ===== */

/* ============================================================================
 * Future · 求职学习工作台 — app.js (part 1/2)
 * ----------------------------------------------------------------------------
 * Zero-dependency, no-build ES module. Structure:
 *
 *   §1  CONSTANTS        taxonomy metadata, source registry, theme engine data
 *   §2  UTIL             escape/markdown/date/dom helpers
 *   §3  STATE            central reactive state + localStorage persistence
 *   §4  STORE            the ONLY place that knows the data-layer file layout
 *   §5  THEME            palette + accent application
 *   §6  TOAST            transient notifications
 *   §7  PALETTE          Ctrl-K command palette / global search
 *   §8  ROUTER           hash router
 *   §9  SHELL            rail, topbar, aside wiring
 *   §10 VIEWS            one renderer per route                       (part 2)
 *   §11 DRAWER           generic detail drawer                        (part 2)
 *   §12 BOOT             startup sequence
 *
 * DECOUPLING CONTRACT — the whole point of the design:
 *   The data layer is plain JSON under `../data/`. Store is the single adapter.
 *   Every renderer receives normalized objects and never fetches directly. A
 *   new daily field therefore needs a change in exactly two places: the Python
 *   collector's writer and (optionally) one renderer. Missing files or missing
 *   keys degrade to placeholders rather than throwing, so the workbench keeps
 *   working on a day when the collector half-failed.
 * ========================================================================= */

/* ============================ §1 CONSTANTS ============================== */

const CATEGORIES = [
  // 'unclassified' is the bucket for items where NO keyword matched. It is
  // deliberately visible (and placed first) rather than silently folded into
  // 'trend', because a growing pile here is the signal that the keyword set needs
  // tuning - which is exactly what the automatic keyword tuner acts on.
  { id: 'unclassified', zh: '未分类',         en: 'Unclassified',      icon: 'i-alert',    color: 'var(--fg-3)',
    desc: '没有命中任何分类关键词的条目。堆在这里通常意味着关键词需要调整。',
    goal: '保持这一栏接近零；若持续增长，说明关键词覆盖不足或有新的方向出现。' },
  { id: 'multimodal',   zh: '多模态算法',     en: 'Multimodal',        icon: 'i-layers',   color: 'var(--c-multimodal)',
    desc: '视觉-语言对齐、VLM 架构、跨模态检索与生成、多模态评测。',
    goal: '每日捕获多模态大模型的新架构、对齐方法与评测基准进展。' },
  { id: 'posttraining', zh: '后训练',         en: 'Post-training',     icon: 'i-target',   color: 'var(--c-posttraining)',
    desc: 'SFT、RLHF、DPO/GRPO、RLVR、拒绝采样、蒸馏与偏好优化。',
    goal: '跟踪后训练算法迭代与工程 trick，沉淀可复现的配方。' },
  { id: 'generative',   zh: '生成式模型',     en: 'Generative',        icon: 'i-spark',    color: 'var(--c-generative)',
    desc: 'Diffusion、Flow Matching、自回归生成、视频/3D 生成。',
    goal: '掌握生成建模范式的原理演进与采样加速技术。' },
  { id: 'worldmodel',   zh: '世界模型',       en: 'World Model',       icon: 'i-compass',  color: 'var(--c-worldmodel)',
    desc: '基于模型的强化学习、视频世界模型、VLA、3DGS/NeRF 场景表示。',
    goal: '跟踪世界模型与具身智能的建模与评测路线。' },
  { id: 'rl',           zh: '强化学习',       en: 'Reinforcement Learning', icon: 'i-activity', color: 'var(--c-rl)',
    desc: 'PPO/GAE、GRPO、离线 RL、探索与信用分配。',
    goal: '打牢 RL 数学基础，并连接到 LLM 后训练实践。' },
  { id: 'agent',        zh: 'Agent 理论与实践', en: 'Agents',          icon: 'i-brain',    color: 'var(--c-agent)',
    desc: '工具调用、规划、记忆、多智能体协作、Agent 评测与安全。',
    goal: '理解 Agent 系统设计模式并动手实现最小可用体。' },
  { id: 'foundation',   zh: '基础理论',       en: 'Foundations',       icon: 'i-book',     color: 'var(--c-multimodal)',
    desc: '线性代数、概率统计、优化、Transformer 与深度学习原理。',
    goal: '补齐面试八股背后的第一性原理。' },
  { id: 'engineering',  zh: '工程与系统',     en: 'Engineering',       icon: 'i-terminal', color: 'var(--c-system)',
    desc: '分布式训练、显存优化、推理加速、量化、CUDA 与并行策略。',
    goal: '把算法想法落到可训练、可推理的工程实现上。' },
  { id: 'coding',       zh: '面试手撕题',     en: 'Coding Interviews', icon: 'i-code',     color: 'var(--c-coding)',
    desc: '手写注意力、损失函数、采样、经典算法与数据结构。',
    goal: '形成高频手撕题的肌肉记忆与讲解话术。' },
  { id: 'exam',         zh: '笔试场景题',     en: 'Written Exams',     icon: 'i-list',     color: 'var(--c-coding)',
    desc: '概率题、场景设计题、工程权衡题、选择题考点。',
    goal: '覆盖笔试与面试中的开放场景题。' },
  { id: 'job',          zh: '岗位与招聘',     en: 'Jobs & Hiring',     icon: 'i-briefcase',color: 'var(--c-job)',
    desc: '实时招聘信息、岗位 JD、面试流程、薪资带宽与投递节奏。',
    goal: '每日刷新在招岗位与投递窗口，不漏机会。' },
  { id: 'paper',        zh: '论文与前沿',     en: 'Papers',            icon: 'i-flask',    color: 'var(--c-paper)',
    desc: 'arXiv 新论文、CCF-A 顶会论文、技术报告与综述。',
    goal: '按方向过滤高相关新论文并给出可读摘要。' },
  { id: 'course',       zh: '课程与仓库',     en: 'Courses & Repos',   icon: 'i-repo',     color: 'var(--c-system)',
    desc: '系统课程、开源仓库、教程与学习资源。',
    goal: '维护固定仓库与课程的进度更新。' },
  { id: 'trend',        zh: '技术演进与趋势', en: 'Trends',            icon: 'i-chart',    color: 'var(--c-generative)',
    desc: '技术路线演进、行业讨论、社区热点与方法论。',
    goal: '把零散信息串成可讲述的技术演进叙事。' },
];

const CAT_BY_ID = Object.fromEntries(CATEGORIES.map((c) => [c.id, c]));

const ROUTES = [
  { id: 'dashboard', hash: '#/dashboard', label: '今日工作台', icon: 'i-home',    group: '总览' },
  { id: 'digest',    hash: '#/digest',    label: '每日更新流', icon: 'i-feed',    group: '总览' },
  { id: 'categories',hash: '#/categories',label: '知识分类',   icon: 'i-grid',    group: '总览' },
  { id: 'knowledge', hash: '#/knowledge', label: '知识卡片',   icon: 'i-layers',  group: '知识库' },
  { id: 'formulas',  hash: '#/formulas',  label: '公式剖析',   icon: 'i-sigma',   group: '知识库' },
  { id: 'problems',  hash: '#/problems',  label: '题库定位',   icon: 'i-code',    group: '知识库' },
  { id: 'repos',     hash: '#/repos',     label: '仓库与课程', icon: 'i-repo',    group: '知识库' },
  { id: 'jobs',      hash: '#/jobs',      label: '岗位看板',   icon: 'i-briefcase', group: '求职' },
  { id: 'skills',    hash: '#/skills',    label: '技能矩阵',   icon: 'i-target',  group: '求职' },
  { id: 'roadmap',   hash: '#/roadmap',   label: '学习路线',   icon: 'i-route',   group: '求职' },
  { id: 'progress',  hash: '#/progress',  label: '进度与统计', icon: 'i-chart',   group: '我的' },
  { id: 'starred',   hash: '#/starred',   label: '收藏夹',     icon: 'i-star',    group: '我的' },
  { id: 'pipeline',  hash: '#/pipeline',  label: '采集与运行', icon: 'i-flask',   group: '我的' },
];

const THEMES = [
  { id: 'midnight', zh: '午夜蓝',   kind: 'dark',  accent: 'blue',    swatches: ['#070a10', '#10161f', '#6ea8fe', '#c084fc'] },
  { id: 'daylight', zh: '日光白',   kind: 'light', accent: 'blue',    swatches: ['#f4f6fa', '#ffffff', '#2563eb', '#9333ea'] },
  { id: 'terminal', zh: '终端绿',   kind: 'dark',  accent: 'emerald', swatches: ['#05080a', '#0c1317', '#4ade80', '#38bdf8'] },
  { id: 'aurora',   zh: '极光紫',   kind: 'dark',  accent: 'violet',  swatches: ['#0a0716', '#130f24', '#a78bfa', '#e879f9'] },
  { id: 'sand',     zh: '暖砂纸',   kind: 'light', accent: 'amber',   swatches: ['#f6f1e7', '#fffdf8', '#b45309', '#7e22ce'] },
  { id: 'nord',     zh: 'Nord',     kind: 'dark',  accent: 'cyan',    swatches: ['#242933', '#2e3440', '#88c0d0', '#b48ead'] },
];

const ACCENTS = [
  { id: 'blue',    zh: '蓝', hex: '#60a5fa' },
  { id: 'violet',  zh: '紫', hex: '#a78bfa' },
  { id: 'cyan',    zh: '青', hex: '#22d3ee' },
  { id: 'emerald', zh: '绿', hex: '#34d399' },
  { id: 'amber',   zh: '琥珀', hex: '#fbbf24' },
  { id: 'rose',    zh: '玫瑰', hex: '#fb7185' },
];

/* Source channel registry — used for source filters, favicons and trust labels.
   `p` is the collection priority tier (P0 highest). */
const CHANNELS = {
  arxiv:        { zh: 'arXiv',        en: 'arXiv',           p: 'P0', url: 'https://arxiv.org' },
  hf_papers:    { zh: 'HF Daily',     en: 'HF Daily Papers', p: 'P0', url: 'https://huggingface.co/papers' },
  hf_models:    { zh: 'HF 模型',      en: 'HF Models',       p: 'P1', url: 'https://huggingface.co/models' },
  github:       { zh: 'GitHub',       en: 'GitHub',          p: 'P0', url: 'https://github.com' },
  github_trend: { zh: 'GitHub 趋势',  en: 'GH Trending',     p: 'P1', url: 'https://github.com/trending' },
  gh_trending:  { zh: 'GitHub 趋势',  en: 'GH Trending',     p: 'P1', url: 'https://github.com/trending' },
  openreview:   { zh: 'OpenReview',   en: 'OpenReview',      p: 'P0', url: 'https://openreview.net' },
  s2:           { zh: 'Semantic Scholar', en: 'S2',          p: 'P1', url: 'https://www.semanticscholar.org' },
  pwc:          { zh: 'PapersWithCode',en: 'PWC',            p: 'P2', url: 'https://paperswithcode.com' },
  acl:          { zh: 'ACL Anthology',en: 'ACL',             p: 'P1', url: 'https://aclanthology.org' },
  hn:           { zh: 'Hacker News',  en: 'HN',              p: 'P1', url: 'https://news.ycombinator.com' },
  reddit:       { zh: 'Reddit',       en: 'Reddit',          p: 'P2', url: 'https://www.reddit.com/r/MachineLearning' },
  nowcoder:     { zh: '牛客网',       en: 'Nowcoder',        p: 'P0', url: 'https://www.nowcoder.com' },
  zhihu:        { zh: '知乎',         en: 'Zhihu',           p: 'P1', url: 'https://www.zhihu.com' },
  xiaohongshu:  { zh: '小红书',       en: 'Xiaohongshu',     p: 'P2', url: 'https://www.xiaohongshu.com', login: true },
  boss:         { zh: 'BOSS直聘',     en: 'BOSS Zhipin',     p: 'P1', url: 'https://www.bosszhipin.com',  login: true },
  shixiseng:    { zh: '实习僧',       en: 'Shixiseng',       p: 'P2', url: 'https://www.shixiseng.com',  login: true },
  lagou:        { zh: '拉勾',         en: 'Lagou',           p: 'P2', url: 'https://www.lagou.com',      login: true },
  leetcode:     { zh: 'LeetCode',     en: 'LeetCode',        p: 'P0', url: 'https://leetcode.cn' },
  codeforces:   { zh: 'Codeforces',   en: 'Codeforces',      p: 'P2', url: 'https://codeforces.com' },
  jobs_bytedance:{zh: '字节招聘',     en: 'ByteDance Jobs',  p: 'P0', url: 'https://jobs.bytedance.com' },
  jobs_tencent: { zh: '腾讯招聘',     en: 'Tencent Careers', p: 'P0', url: 'https://careers.tencent.com' },
  jobs_alibaba: { zh: '阿里招聘',     en: 'Alibaba Talent',  p: 'P0', url: 'https://talent.alibaba.com' },
  jobs_zhipu:   { zh: '智谱招聘',     en: 'ZhipuAI',         p: 'P1', url: 'https://zhipuai.cn' },
  jobs_moonshot:{ zh: '月之暗面',     en: 'Moonshot AI',     p: 'P1', url: 'https://www.moonshot.cn' },
  jobs_deepseek:{ zh: 'DeepSeek',     en: 'DeepSeek',        p: 'P1', url: 'https://www.deepseek.com' },
  jobs_minimax: { zh: 'MiniMax',      en: 'MiniMax',         p: 'P1', url: 'https://www.minimaxi.com' },
  jobs_shailab: { zh: '上海AI Lab',   en: 'Shanghai AI Lab', p: 'P1', url: 'https://www.shlab.org.cn' },
  machineheart: { zh: '机器之心',     en: '机器之心',         p: 'P1', url: 'https://www.jiqizhixin.com' },
  qbitai:       { zh: '量子位',       en: '量子位',           p: 'P1', url: 'https://www.qbitai.com' },
  aiera:        { zh: '新智元',       en: '新智元',           p: 'P2', url: 'https://www.aiera.com.cn' },
  rsshub:       { zh: 'RSSHub',       en: 'RSSHub',          p: 'P2', url: 'https://rsshub.app' },
  manual:       { zh: '手动录入',     en: 'Manual',          p: 'P0', url: '' },
  agent:        { zh: '每日调研 Agent', en: 'Daily Agent',   p: 'P0', url: '' },
};

function channelMeta(id) {
  return CHANNELS[id] || { zh: id || '未知来源', en: id || 'unknown', p: 'P2', url: '' };
}

/* ============================== §2 UTIL ================================= */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function esc(s) {
  if (s === null || s === undefined) return '';
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/** Attribute-safe escape (same set; named separately for intent). */
const attr = esc;

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'html') node.innerHTML = v;
    else if (k === 'text') node.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
    else if (k === 'dataset') Object.assign(node.dataset, v);
    else if (v === true) node.setAttribute(k, '');
    else node.setAttribute(k, v);
  }
  for (const c of children.flat(4)) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

function debounce(fn, ms = 220) {
  let t;
  const wrapped = (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  wrapped.cancel = () => clearTimeout(t);
  wrapped.flush = (...args) => { clearTimeout(t); fn(...args); };
  return wrapped;
}

function throttle(fn, ms = 120) {
  let last = 0, timer = null, pending = null;
  return (...args) => {
    pending = args;
    const now = Date.now();
    if (now - last >= ms) { last = now; fn(...pending); }
    else if (!timer) {
      timer = setTimeout(() => { timer = null; last = Date.now(); fn(...pending); }, ms - (now - last));
    }
  };
}

function clamp(n, lo, hi) { return Math.min(hi, Math.max(lo, n)); }

function icon(name, cls = '', size = null) {
  const s = size ? ` style="width:${size}px;height:${size}px"` : '';
  return `<svg class="${cls}"${s} aria-hidden="true"><use href="#${name}"/></svg>`;
}

/* --- Date / time -------------------------------------------------------- */
const SH_TZ = 'Asia/Shanghai';

function shanghaiNow() {
  return new Date(new Date().toLocaleString('en-US', { timeZone: SH_TZ }));
}

function fmtDate(iso, style = 'short') {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  const opts = {
    short: { timeZone: SH_TZ, month: '2-digit', day: '2-digit' },
    medium: { timeZone: SH_TZ, year: 'numeric', month: '2-digit', day: '2-digit' },
    long: { timeZone: SH_TZ, year: 'numeric', month: 'long', day: 'numeric' },
    datetime: { timeZone: SH_TZ, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false },
  }[style] || {};
  return new Intl.DateTimeFormat('zh-CN', opts).format(d);
}

function relTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const diff = Date.now() - d.getTime();
  const abs = Math.abs(diff);
  const mins = Math.round(abs / 60000);
  const suffix = diff >= 0 ? '前' : '后';
  if (mins < 1) return '刚刚';
  if (mins < 60) return `${mins} 分钟${suffix}`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} 小时${suffix}`;
  const days = Math.round(hrs / 24);
  if (days < 31) return `${days} 天${suffix}`;
  return fmtDate(iso, 'medium');
}

function weekdayZh(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][d.getDay()];
}

function dateKey(d = new Date()) {
  return new Intl.DateTimeFormat('en-CA', { timeZone: SH_TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).format(d);
}

/* --- Markdown (small, safe, deliberate subset) -------------------------- */
/** Escapes first, then applies inline rules — never trusts input. */
function inlineMd(s) {
  let out = esc(s);
  out = out.replace(/`([^`]+)`/g, (_, c) => `<code>${c}</code>`);
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  out = out.replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  out = out.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    (_, t, u) => `<a href="${u}" target="_blank" rel="noopener noreferrer">${t}</a>`);
  out = out.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g,
    (_, p, u) => `${p}<a href="${u}" target="_blank" rel="noopener noreferrer">${u}</a>`);
  return out;
}

function md(src) {
  if (!src) return '';
  const text = String(src).replace(/\r\n?/g, '\n');
  const blocks = [];
  // Protect fenced code before block parsing.
  const guarded = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    blocks.push({ lang, code });
    return `\u0000CODE${blocks.length - 1}\u0000`;
  });

  const lines = guarded.split('\n');
  const html = [];
  let list = null; // 'ul' | 'ol'
  let para = [];

  const flushPara = () => {
    if (para.length) { html.push(`<p>${inlineMd(para.join(' '))}</p>`); para = []; }
  };
  const closeList = () => { if (list) { html.push(`</${list}>`); list = null; } };

  for (const raw of lines) {
    const line = raw.replace(/\s+$/, '');
    if (!line.trim()) { flushPara(); closeList(); continue; }

    const codeRef = line.match(/^\u0000CODE(\d+)\u0000$/);
    if (codeRef) {
      flushPara(); closeList();
      const b = blocks[Number(codeRef[1])];
      html.push(`<div class="code-wrap"><div class="code-head"><span>${esc(b.lang || 'text')}</span></div>` +
        `<pre class="code">${highlight(b.code, b.lang)}</pre></div>`);
      continue;
    }

    let m;
    if ((m = line.match(/^(#{1,6})\s+(.*)$/))) {
      flushPara(); closeList();
      const lv = clamp(m[1].length + 1, 2, 6); // page owns h1
      html.push(`<h${lv}>${inlineMd(m[2])}</h${lv}>`);
      continue;
    }
    if (/^>\s?/.test(line)) {
      flushPara(); closeList();
      html.push(`<blockquote>${inlineMd(line.replace(/^>\s?/, ''))}</blockquote>`);
      continue;
    }
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(line.trim())) { flushPara(); closeList(); html.push('<hr>'); continue; }
    if ((m = line.match(/^\s*[-*+]\s+(.*)$/))) {
      flushPara();
      if (list !== 'ul') { closeList(); html.push('<ul>'); list = 'ul'; }
      html.push(`<li>${inlineMd(m[1])}</li>`);
      continue;
    }
    if ((m = line.match(/^\s*\d+[.)]\s+(.*)$/))) {
      flushPara();
      if (list !== 'ol') { closeList(); html.push('<ol>'); list = 'ol'; }
      html.push(`<li>${inlineMd(m[1])}</li>`);
      continue;
    }
    if (/^\|.*\|$/.test(line.trim())) {
      flushPara(); closeList();
      const rows = [];
      let i = lines.indexOf(raw);
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) { rows.push(lines[i]); i++; }
      html.push(renderTable(rows));
      for (let k = 0; k < rows.length - 1; k++) lines[i - k - 1] = '\u0000SKIP\u0000';
      continue;
    }
    if (line.trim() === '\u0000SKIP\u0000') continue;
    para.push(line.trim());
  }
  flushPara(); closeList();
  return html.join('\n');
}

function renderTable(rows) {
  if (rows.length < 2) return '';
  const cells = (r) => r.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
  const head = cells(rows[0]);
  const body = rows.slice(2).map(cells);
  return `<div class="tbl-wrap"><table class="tbl"><thead><tr>${
    head.map((c) => `<th>${inlineMd(c)}</th>`).join('')
  }</tr></thead><tbody>${
    body.map((r) => `<tr>${r.map((c) => `<td>${inlineMd(c)}</td>`).join('')}</tr>`).join('')
  }</tbody></table></div>`;
}

/** Very small tokenizer — enough to make snippets readable, never required. */
function highlight(code, lang = '') {
  let out = esc(code);
  const L = (lang || '').toLowerCase();
  const isPy = L.startsWith('py') || /^\s*(import|from|def|class)\s/m.test(code);
  const isShell = L === 'bash' || L === 'sh' || L === 'shell' || L === 'powershell';
  const kw = isPy
    ? 'def|class|return|if|elif|else|for|while|in|not|and|or|import|from|as|with|try|except|finally|raise|lambda|yield|pass|break|continue|None|True|False|self|async|await|global|assert|del'
    : isShell
      ? 'if|then|else|fi|for|do|done|function|return|export|local|echo|param|foreach|in'
      : 'function|const|let|var|return|if|else|for|while|class|new|import|from|export|default|async|await|try|catch|of|in|typeof|instanceof';
  const strings = [];
  out = out.replace(/(&quot;[^&]*?&quot;|&#39;[^&]*?&#39;|`[^`]*`)/g, (m) => {
    strings.push(m); return `\u0001S${strings.length - 1}\u0001`;
  });
  out = out.replace(/(^|\n)(\s*#[^\n]*)/g, (_, p, c) => `${p}<span class="tok-com">${c}</span>`);
  out = out.replace(/(^|\n)(\s*\/\/[^\n]*)/g, (_, p, c) => `${p}<span class="tok-com">${c}</span>`);
  out = out.replace(new RegExp(`\\b(${kw})\\b`, 'g'), '<span class="tok-kw">$1</span>');
  out = out.replace(/\b(\d+\.?\d*(?:e-?\d+)?)\b/g, '<span class="tok-num">$1</span>');
  out = out.replace(/\b([A-Za-z_]\w*)(?=\()/g, '<span class="tok-fn">$1</span>');
  out = out.replace(/\u0001S(\d+)\u0001/g, (_, i) => `<span class="tok-str">${strings[Number(i)]}</span>`);
  return out;
}

/* --- LaTeX -> HTML (small, deliberate subset) --------------------------- */
/**
 * A tiny LaTeX renderer, not a general one.
 *
 * Why hand-rolled: the workbench is zero-dependency and must run from `file://`,
 * so pulling KaTeX/MathJax from a CDN is not acceptable (offline, and a remote
 * script is a supply-chain surface). The formula cards and the enrichment
 * formulas only ever use a narrow subset, and rendering that subset ourselves
 * means the same engine drives 公式剖析 AND every inline formula on a knowledge
 * card, so they finally look identical.
 *
 * Supported: \frac, \sqrt, ^, _, \sum, \prod, \int, \lim, \log, \exp, \max,
 * \min, \arg\max, \mathrm/\mathbf/\text/\operatorname, \left \right, \cdot,
 * \times, \approx, \le, \ge, \neq, \pm, \to, \in, \mathbb (as blackboard),
 * Greek letters, and Chinese identifiers inside \text{...}.
 * Unsupported input degrades to escaped monospace text rather than throwing.
 */
const GREEK = {
  alpha: 'α', beta: 'β', gamma: 'γ', Gamma: 'Γ', delta: 'δ', Delta: 'Δ',
  epsilon: 'ε', varepsilon: 'ε', zeta: 'ζ', eta: 'η', theta: 'θ', Theta: 'Θ',
  iota: 'ι', kappa: 'κ', lambda: 'λ', Lambda: 'Λ', mu: 'μ', nu: 'ν', xi: 'ξ',
  Xi: 'Ξ', pi: 'π', Pi: 'Π', rho: 'ρ', sigma: 'σ', Sigma: 'Σ', tau: 'τ',
  upsilon: 'υ', phi: 'φ', varphi: 'φ', Phi: 'Φ', chi: 'χ', psi: 'ψ', Psi: 'Ψ',
  omega: 'ω', Omega: 'Ω',
};

const MATH_SYMBOLS = {
  cdot: '·', times: '×', div: '÷', pm: '±', mp: '∓', ast: '∗', star: '⋆',
  // NOTE: `geq` used to map to '≠', which silently rendered "≥" as "not equal" in
  // every formula that used \geq. Caught by scripts/tex-audit.mjs while adding the
  // missing symbols, so the whole table is spelled out here.
  le: '≤', leq: '≤', ge: '≥', geq: '≥', neq: '≠', ne: '≠', equiv: '≡',
  approx: '≈', propto: '∝', sim: '∼', simeq: '≃', ll: '≪', gg: '≫',
  to: '→', rightarrow: '→', leftarrow: '←', Rightarrow: '⇒', implies: '⟹',
  Longrightarrow: '⟹', longrightarrow: '⟶', Longleftrightarrow: '⟺',
  leftrightarrow: '↔', mapsto: '↦', gets: '←',
  in: '∈', notin: '∉', subset: '⊂', subseteq: '⊆', cup: '∪', cap: '∩',
  emptyset: '∅', forall: '∀', exists: '∃', nabla: '∇', partial: '∂',
  infty: '∞', ell: 'ℓ', hbar: 'ℏ', ldots: '…', cdots: '⋯', dots: '…',
  perp: '⊥', parallel: '∥', angle: '∠', triangle: '△', prime: '′',
  top: '⊤', bot: '⊥', oplus: '⊕', otimes: '⊗', circ: '∘', odot: '⊙',
  // Logic operators. \land and \wedge both mean AND, \lor and \vee both OR.
  land: '∧', wedge: '∧', lor: '∨', vee: '∨', neg: '¬', lnot: '¬',
  setminus: '\\', backslash: '\\', lVert: '‖', rVert: '‖', Vert: '‖',
  lceil: '⌈', rceil: '⌉', lfloor: '⌊', rfloor: '⌋',
  langle: '⟨', rangle: '⟩', mid: '|', colon: ':', '%': '%', '#': '#',
  lvert: '|', rvert: '|', '|': '‖', lmoustache: '⎰', rmoustache: '⎱',
  ',': '\u2009', ';': '\u2005', ' ': '\u00a0', quad: '\u2003', qquad: '\u2003\u2003',
};

/* Commands that carry no visual content of their own.
 * `\!` is a NEGATIVE thin space and appears in ~20 stored formulas; before this it
 * leaked to the reader as a literal "\!" because the renderer had no entry for it. */
const TEX_NOOP = new Set(['!', 'hspace', 'hfill', 'vspace', 'phantom', 'limits',
  'nolimits', 'displaystyle', 'textstyle', 'scriptstyle', 'allowbreak', 'mathstrut']);

/* \underbrace{X}_{Y} and \overbrace{X}^{Y}: keep the content, label the brace. */
const TEX_UNDER = { underbrace: 'tex-under', overbrace: 'tex-over',
  underline: 'tex-under', overline: 'tex-over' };

const BIG_OPS = { sum: '∑', prod: '∏', int: '∫', oint: '∮', bigcup: '⋃', bigcap: '⋂' };
const FUNCS = { log: 'log', ln: 'ln', exp: 'exp', sin: 'sin', cos: 'cos', tan: 'tan',
  max: 'max', min: 'min', arg: 'arg', sup: 'sup', inf: 'inf', lim: 'lim',
  det: 'det', dim: 'dim', softmax: 'softmax', mean: 'mean', std: 'std', var: 'Var',
  // Inverse trig, hyperbolics and modular arithmetic show up in the loss and
  // similarity formulas this workbench stores.
  tanh: 'tanh', sinh: 'sinh', cosh: 'cosh', arccos: 'arccos', arcsin: 'arcsin',
  arctan: 'arctan', bmod: 'mod', pmod: 'mod', mod: 'mod', sign: 'sign',
  diag: 'diag', tr: 'tr', rank: 'rank', relu: 'ReLU', gelu: 'GELU' };
// Accents render as a CSS-decorated span around the argument, which is honest
// about what it is and needs no font support.
// NOTE: named TEX_ACCENTS, not ACCENTS - `ACCENTS` is already the accent-colour
// palette used by the theme switcher, and redeclaring it silently killed every
// theme (the palette became this object). Keep the namespace distinct.
const TEX_ACCENTS = {
  bar: 'tex-acc-bar', overline: 'tex-acc-bar', hat: 'tex-acc-hat', widehat: 'tex-acc-hat',
  tilde: 'tex-acc-tilde', widetilde: 'tex-acc-tilde', dot: 'tex-acc-dot',
  ddot: 'tex-acc-ddot', vec: 'tex-acc-vec',
};
// Commands that only set size or are layout hints; drop them silently.
const SIZE_HINTS = new Set(['left', 'right', 'big', 'Big', 'bigg', 'Bigg',
  'bigl', 'bigr', 'Bigl', 'Bigr', 'biggl', 'biggr', 'displaystyle',
  'limits', 'nolimits', 'textstyle', 'scriptstyle', 'mathstrut',
  'phantom', 'hspace', 'vspace', 'ensuremath', 'nonumber']);

function texFindGroupEnd(s, start) {
  // start points at '{'; returns the index of the matching '}' or -1.
  let depth = 0;
  for (let i = start; i < s.length; i += 1) {
    const c = s[i];
    if (c === '\\') { i += 1; continue; }
    if (c === '{') depth += 1;
    else if (c === '}') { depth -= 1; if (depth === 0) return i; }
  }
  return -1;
}

function texArg(s, i) {
  // Read the argument of a command starting at index i. Returns [content, next].
  // A missing argument yields '' (never null) so callers can render it safely.
  while (s[i] === ' ') i += 1;
  if (s[i] === '{') {
    const end = texFindGroupEnd(s, i);
    if (end < 0) return [s.slice(i + 1), s.length];
    return [s.slice(i + 1, end), end + 1];
  }
  if (s[i] === '\\') {
    const m = /^\\[A-Za-z]+/.exec(s.slice(i));
    if (m) return [m[0], i + m[0].length];
  }
  if (i < s.length && typeof s[i] === 'string') return [s[i], i + 1];
  return ['', i];
}

function tex(src) {
  if (!src) return '';
  let s = String(src);
  // Normalise the delimiters people actually paste in.
  s = s.replace(/\\\[|\\\]|\$\$|\\\(|\\\)/g, '');
  s = s.replace(/\\begin\{[a-z*]+\}|\\end\{[a-z*]+\}/g, '');
  // `\n` is a LaTeX line-break command, not the word "n". Turn it into a real
  // newline BEFORE escaping, otherwise it arrives as a literal newline inside a
  // word (observed: "LATEX 源码 \nmathrm{Attention}" rendering as a broken line).
  s = s.replace(/\\\\n(?![A-Za-z])/g, '\n');
  s = esc(s);                                  // escape once; we only add tags below

  const SUB = '₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₓₕₖₗₘₙₚₛₜᵢⱼ';
  const SUP = '⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ';
  // Direct char->char maps. Deriving these by index arithmetic was fragile.
  const SUB_MAP = { '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄', '5': '₅', '6': '₆',
    '7': '₇', '8': '₈', '9': '₉', '+': '₊', '-': '₋', '=': '₌', '(': '₍', ')': '₎',
    a: 'ₐ', e: 'ₑ', x: 'ₓ', h: 'ₕ', k: 'ₖ', l: 'ₗ', m: 'ₘ', n: 'ₙ', p: 'ₚ',
    s: 'ₛ', t: 'ₜ', i: 'ᵢ', j: 'ⱼ' };
  const SUP_MAP = { '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴', '5': '⁵', '6': '⁶',
    '7': '⁷', '8': '⁸', '9': '⁹', '+': '⁺', '-': '⁻', '=': '⁼', '(': '⁽', ')': '⁾',
    n: 'ⁿ', i: 'ⁱ' };

  function renderGroup(t) {
    // Defensive coercion. renderGroup is called recursively (via texArg) on the
    // argument of commands like \sqrt, \frac, \text and the accents, and an
    // argument genuinely may be absent - e.g. a formula that ends with a bare
    // "\sqrt", or "\frac{a}{}" - in which case texArg hands back null/undefined.
    // Without this guard, `t[i]` threw "Cannot read properties of null (reading
    // '0')", which took down the ENTIRE 公式剖析 page because the view render was
    // one big template. A malformed formula must degrade to a small visual defect,
    // never a blank page.
    if (t == null) return '';
    if (typeof t !== 'string') t = String(t);
    const out = [];
    let i = 0;
    while (i < t.length) {
      const c = t[i];

      // ---- commands -----------------------------------------------------
      if (c === '\\') {
        const nameM = /^\\([A-Za-z]+|.)/.exec(t.slice(i));
        if (!nameM) { out.push('\\'); i += 1; continue; }
        const name = nameM[1];
        i += nameM[0].length;

        if (name === 'frac' || name === 'dfrac' || name === 'tfrac') {
          const [num, i2] = texArg(t, i);
          const [den, i3] = texArg(t, i2);
          i = i3;
          out.push(`<span class="frac"><span class="num">${renderGroup(num)}</span><span class="den">${renderGroup(den)}</span></span>`);
          continue;
        }
        if (name === 'sqrt') {
          const [arg, i2] = texArg(t, i);
          i = i2;
          out.push(`<span class="sqrt">√<span class="radicand">${renderGroup(arg)}</span></span>`);
          continue;
        }
        if (name === 'text' || name === 'mathrm' || name === 'operatorname'
            || name === 'mathbf' || name === 'mathit' || name === 'mathcal'
            || name === 'mathbb' || name === 'mathsf' || name === 'texttt') {
          const [arg, i2] = texArg(t, i);
          i = i2;
          const cls = name === 'mathbf' ? ' class="tex-bold"'
            : name === 'mathbb' ? ' class="tex-bb"'
            : name === 'mathcal' ? ' class="tex-cal"'
            : name === 'texttt' ? ' class="tex-mono"' : '';
          out.push(`<span${cls}>${renderGroup(arg)}</span>`);
          continue;
        }
        if (name === 'not') {
          // \not negates the following relation: \not= -> ≠, \not\in -> ∉.
          // Render the combining long solidus overlay over the next symbol's cell,
          // which is honest about the meaning even when no exact glyph exists.
          out.push('<span class="tex-not">\u0338</span>');
          continue;
        }
        if (TEX_UNDER[name]) {
          // \underbrace{X}_{label} / \overbrace{X}^{label}: render X with a labelled
          // brace beneath/above it. The script that follows is consumed here so it is
          // not emitted twice.
          const [arg, i2] = texArg(t, i);
          i = i2;
          let label = '';
          let j = i;
          while (j < t.length && t[j] === ' ') j += 1;
          if (t[j] === '_' || t[j] === '^') {
            const [lab, i3] = texArg(t, j + 1);
            label = renderGroup(lab);
            i = i3;
          }
          const over = TEX_UNDER[name] === 'tex-over';
          out.push(`<span class="${TEX_UNDER[name]}">${over ? '' : renderGroup(arg)}`
            + `<span class="tex-brace-label">${label}</span>`
            + `${over ? renderGroup(arg) : ''}</span>`);
          continue;
        }
        if (name === 'left' || name === 'right' || SIZE_HINTS.has(name)) {
          continue;                                  // size hints are visual noise here
        }
        if (TEX_NOOP.has(name)) {
          // Spacing/styling hints with no glyph of their own. `\!` in particular is a
          // negative thin space used in ~20 of the stored formulas; dropping it is
          // correct, showing "\!" to the reader is not.
          continue;
        }
        if (TEX_ACCENTS[name]) {
          const [arg, i2] = texArg(t, i);
          i = i2;
          out.push(`<span class="${TEX_ACCENTS[name]}">${renderGroup(arg)}</span>`);
          continue;
        }
        if (GREEK[name]) { out.push(`<var class="tex-greek">${GREEK[name]}</var>`); continue; }
        if (BIG_OPS[name]) {
          out.push(`<span class="tex-bigop">${BIG_OPS[name]}</span>`);
          continue;
        }
        if (FUNCS[name]) {
          // \arg\max -> "arg max"
          out.push(`<span class="tex-op">${FUNCS[name]}</span>`);
          continue;
        }
        if (Object.prototype.hasOwnProperty.call(MATH_SYMBOLS, name)) {
          out.push(`<span class="tex-sym">${MATH_SYMBOLS[name]}</span>`);
          continue;
        }
        if (name === '\\') { out.push('<br>'); continue; }
        if (name === '{' || name === '}') { out.push(name); continue; }
        if (name === 'quad' || name === 'qquad') { out.push('<span class="tex-space"></span>'); continue; }
        if (name === ',') { out.push('<span class="tex-thinspace"></span>'); continue; }
        // Unknown command: show it verbatim so a typo is visible, not silent.
        out.push(`<span class="tex-unknown">\\${name}</span>`);
        continue;
      }

      // ---- scripts ------------------------------------------------------
      if (c === '^' || c === '_') {
        const [arg, i2] = texArg(t, i + 1);
        i = i2;
        const inner = renderGroup(arg);
        const map = c === '^' ? SUP_MAP : SUB_MAP;
        const folded = arg.length === 1 ? map[arg] : undefined;
        out.push(folded
          ? (c === '^' ? `<sup class="tex-sup">${folded}</sup>` : `<sub class="tex-sub">${folded}</sub>`)
          : (c === '^' ? `<sup class="tex-sup">${inner}</sup>` : `<sub class="tex-sub">${inner}</sub>`));
        continue;
      }

      // ---- structure -----------------------------------------------------
      if (c === '{') {
        const end = texFindGroupEnd(t, i);
        if (end < 0) { out.push(renderGroup(t.slice(i + 1))); break; }
        out.push(renderGroup(t.slice(i + 1, end)));
        i = end + 1;
        continue;
      }
      if (c === '}') { i += 1; continue; }
      if (c === '&') { out.push('<span class="tex-align"></span>'); i += 1; continue; }

      // ---- identifiers ---------------------------------------------------
      if (/[0-9.]/.test(c)) {
        const m = /^[0-9]+(\.[0-9]+)?/.exec(t.slice(i));
        // `m` is normally guaranteed here, but report the state instead of throwing
        // if it ever is not: a malformed formula must not blank the whole page.
        if (!m) {
          out.push(`<span class="tex-unknown">${esc(c)}</span>`);
          i += 1;
          continue;
        }
        out.push(`<span class="tex-num">${m[0]}</span>`);
        i += m[0].length;
        continue;
      }
      if (/[A-Za-z]/.test(c)) {
        const m = /^[A-Za-z]+/.exec(t.slice(i));
        // Single letters are italic variables (math convention); longer runs are
        // usually function or parameter names and read better upright.
        out.push(m[0].length === 1 ? `<var>${m[0]}</var>` : `<span class="tex-word">${m[0]}</span>`);
        i += m[0].length;
        continue;
      }
      if (c === ' ') { out.push(' '); i += 1; continue; }
      out.push(`<span class="tex-punct">${c}</span>`);
      i += 1;
    }
    return out.join('');
  }

  return renderGroup(s);
}

/** Inline math with the accents removed, for places where a full block is too much. */
function texInline(src, maxLen = 120) {
  const s = String(src || '');
  const short = s.length > maxLen ? s.slice(0, maxLen - 1) + '…' : s;
  return tex(short);
}

/* --- Diagram rendering -------------------------------------------------- */
/**
 * The deep-read layer can attach a `diagram` to any item. Two shapes are
 * supported and both are self-contained so the workbench keeps working offline:
 *   · svg  — inline SVG authored by the layer
 *   · spec — a structured description we draw with HTML/CSS (flow, architecture,
 *            curve, matrix, timeline)
 *
 * Security: `svg` comes from a file the daily layer writes, but this is still
 * untrusted input as far as the browser is concerned, so it is sanitised
 * (no script/style/foreignObject/image/on* attributes/external refs) rather
 * than injected raw.
 */
function sanitizeSvg(svg) {
  if (!svg) return '';
  let s = String(svg);
  // Drop anything executable or remotely-loaded. This is a small allowlist in
  // spirit: remove the dangerous constructs, then strip event handlers.
  s = s.replace(/<\s*(script|style|foreignObject|iframe|image|use|animate|set)[\s\S]*?<\s*\/\s*\1\s*>/gi, '');
  s = s.replace(/<\s*(script|style|foreignObject|iframe|image|use|animate|set)\b[^>]*\/?>/gi, '');
  s = s.replace(/\son[a-z]+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '');
  s = s.replace(/(href|xlink:href|src)\s*=\s*("|')?\s*(?:javascript:|data:|https?:|\/\/)[^"'\s>]*/gi, '');
  if (!/^\s*<svg[\s>]/i.test(s)) return '';
  // Guarantee a viewBox so it scales inside its container.
  if (!/viewBox\s*=/i.test(s)) {
    const w = /\bwidth\s*=\s*["']?(\d+)/i.exec(s);
    const h = /\bheight\s*=\s*["']?(\d+)/i.exec(s);
    if (w && h) s = s.replace(/<svg/i, `<svg viewBox="0 0 ${w[1]} ${h[1]}"`);
  }
  return s;
}

function diagramSpecHtml(spec) {
  if (!spec || typeof spec !== 'object') return '';
  const type = String(spec.type || 'flow');
  const nodes = Array.isArray(spec.nodes) ? spec.nodes : [];
  const edges = Array.isArray(spec.edges) ? spec.edges : [];

  if (type === 'flow' || type === 'architecture') {
    const arrow = type === 'architecture' ? '⟷' : '→';
    return `<div class="dg-flow ${type}">
      ${nodes.map((n, i) => `
        ${i ? `<span class="dg-arrow" aria-hidden="true">${arrow}</span>` : ''}
        <div class="dg-node">
          <div class="dg-node-label">${esc(n.label || '')}</div>
          ${n.detail ? `<div class="dg-node-detail">${esc(n.detail)}</div>` : ''}
        </div>`).join('')}
    </div>
    ${edges.length ? `<ul class="dg-edges">${edges.map((e) => {
      const a = nodes[e.from] ? (nodes[e.from].label || e.from) : e.from;
      const b = nodes[e.to] ? (nodes[e.to].label || e.to) : e.to;
      return `<li><span class="dg-edge-pair">${esc(String(a))} → ${esc(String(b))}</span>${e.label ? ' · ' + esc(e.label) : ''}</li>`;
    }).join('')}</ul>` : ''}`;
  }

  if (type === 'timeline') {
    return `<ol class="dg-timeline">
      ${nodes.map((n) => `<li><span class="dg-tl-dot" aria-hidden="true"></span>
        <div><div class="dg-node-label">${esc(n.label || '')}</div>
        ${n.detail ? `<div class="dg-node-detail">${esc(n.detail)}</div>` : ''}</div></li>`).join('')}
    </ol>`;
  }

  if (type === 'matrix') {
    const body = nodes.map((n) => `<tr><th>${esc(n.label || '')}</th><td>${esc(n.detail || '')}</td></tr>`).join('');
    return `<div class="tbl-wrap"><table class="tbl"><tbody>${body}</tbody></table></div>`;
  }

  if (type === 'curve') {
    // A curve spec is a list of points; the front-end draws the polyline so the
    // layer does not have to hand-author SVG for a simple trend.
    const pts = nodes.map((n) => Number(n.value)).filter((v) => Number.isFinite(v));
    if (pts.length >= 2) {
      return `<div class="dg-curve">${sparkline(pts, { w: 520, h: 120 })}</div>
        <ul class="dg-edges">${nodes.map((n) => `<li>${esc(n.label || '')}${n.detail ? ' · ' + esc(n.detail) : ''}</li>`).join('')}</ul>`;
    }
    return `<ul class="dg-edges">${nodes.map((n) => `<li>${esc(n.label || '')}${n.detail ? ' · ' + esc(n.detail) : ''}</li>`).join('')}</ul>`;
  }

  return `<ul class="dg-edges">${nodes.map((n) => `<li>${esc(n.label || '')}${n.detail ? ' · ' + esc(n.detail) : ''}</li>`).join('')}</ul>`;
}

function diagramHtml(diagram) {
  if (!diagram || typeof diagram !== 'object') return '';
  const svg = sanitizeSvg(diagram.svg);
  const inner = svg
    ? `<div class="dg-svg" role="img" aria-label="${attr(diagram.alt || diagram.title || '图解')}">${svg}</div>`
    : diagramSpecHtml(diagram.spec);
  if (!inner) return '';
  return `<figure class="diagram" data-kind="${attr(diagram.kind || 'diagram')}">
    <figcaption class="dg-head">
      <span class="dg-kind">${esc({ flow: '流程', architecture: '架构', curve: '曲线', matrix: '对比', timeline: '时间线' }[diagram.kind] || '图解')}</span>
      ${diagram.title ? `<span class="dg-title">${esc(diagram.title)}</span>` : ''}
    </figcaption>
    ${inner}
    ${diagram.caption ? `<div class="dg-caption">${esc(diagram.caption)}</div>` : ''}
    ${!svg && diagram.alt ? `<div class="dg-alt">${esc(diagram.alt)}</div>` : ''}
  </figure>`;
}

/* --- Small HTML builders reused across views --------------------------- */
function chip(label, { on = false, cat = null, dot = false, attrs = '' } = {}) {
  const c = cat ? ` data-cat="${cat}"` : '';
  return `<button class="chip${on ? ' is-on' : ''}"${c} ${attrs}>` +
    (dot ? '<span class="chip-dot"></span>' : '') + esc(label) + '</button>';
}

function catPill(catId) {
  const c = CAT_BY_ID[catId];
  if (!c) return '';
  return `<span class="kcard-cat" data-cat="${esc(catId)}">${esc(c.zh)}</span>`;
}

function progressBar(pct, cat = null, cls = '') {
  const p = clamp(Math.round(pct), 0, 100);
  return `<div class="bar ${cls}"${cat ? ` data-cat="${cat}"` : ''} role="progressbar" aria-valuenow="${p}" aria-valuemin="0" aria-valuemax="100"><i style="width:${p}%"></i></div>`;
}

function ring(pct, size = 62, stroke = 6, cat = null, label = '') {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const off = c * (1 - clamp(pct, 0, 100) / 100);
  return `<div style="position:relative;width:${size}px;height:${size}px;flex:0 0 auto"${cat ? ` data-cat="${cat}"` : ''}>
    <svg class="ring" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
      <circle class="track" cx="${size / 2}" cy="${size / 2}" r="${r}" stroke-width="${stroke}"/>
      <circle class="val" cx="${size / 2}" cy="${size / 2}" r="${r}" stroke-width="${stroke}"
        stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${off.toFixed(1)}"/>
    </svg>
    <div style="position:absolute;inset:0;display:grid;place-items:center;font-size:var(--fs-2xs);font-weight:700;color:var(--fg-0)">
      ${label || Math.round(pct) + '%'}
    </div>
  </div>`;
}

function sparkline(values, { w = 240, h = 44, cat = null } = {}) {
  const vals = (values || []).filter((v) => Number.isFinite(v));
  if (vals.length < 2) {
    return `<div class="empty" style="padding:var(--sp-6)"><p>趋势图需要至少 2 天的数据 —— 采集器每天 18:00 运行一次，明天起这里会显示走势。</p></div>`;
  }
  const max = Math.max(...vals, 1);
  const min = Math.min(...vals, 0);
  const span = max - min || 1;
  const step = w / (vals.length - 1);
  const pts = vals.map((v, i) => [i * step, h - 4 - ((v - min) / span) * (h - 10)]);
  const line = pts.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
  const area = `0,${h} ${line} ${w},${h}`;
  const last = pts[pts.length - 1];
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"${cat ? ` data-cat="${cat}"` : ''}>
    <polygon class="area" points="${area}"/>
    <polyline points="${line}"/>
    <circle class="dot" cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="2.6"/>
  </svg>`;
}

function emptyState(title, desc, iconName = 'i-archive', actionHtml = '') {
  return `<div class="empty">${icon(iconName)}<h4>${esc(title)}</h4><p>${esc(desc)}</p>${actionHtml}</div>`;
}

/**
 * Pagination. Added because the knowledge view used to hard-cap at 90 cards, so
 * with 700+ items most of the corpus was unreachable from the UI - it existed in
 * the data layer but a reader could never get to it. Showing everything at once
 * is worse (a 1.7 MB DOM), hence real pages plus an explicit "show all".
 */
function paginate(list, { route = '#/knowledge', extraQuery = '' } = {}) {
  const per = state.perPage;
  if (!per || per === 0 || list.length <= per) {
    return {
      slice: list,
      controls: list.length > 20
        ? `<div class="result-line" style="justify-content:center;margin:var(--sp-5) 0">
             <span>已显示全部 <b>${list.length}</b> 条</span>
             ${list.length > 60 ? `<button class="btn btn-sm btn-ghost" data-act="set-perpage" data-value="60">分页显示</button>` : ''}
           </div>`
        : '',
    };
  }
  const pages = Math.max(1, Math.ceil(list.length / per));
  const cur = clamp(state.page, 1, pages);
  const from = (cur - 1) * per;
  const slice = list.slice(from, from + per);

  // Windowed page numbers so 12 pages do not produce 12 buttons of noise.
  const nums = [];
  const push = (n) => { if (!nums.includes(n) && n >= 1 && n <= pages) nums.push(n); };
  push(1); push(2);
  for (let n = cur - 1; n <= cur + 1; n += 1) push(n);
  push(pages - 1); push(pages);
  nums.sort((a, b) => a - b);
  const withGaps = [];
  let prev = 0;
  for (const n of nums) {
    if (prev && n - prev > 1) withGaps.push('gap');
    withGaps.push(n);
    prev = n;
  }

  const q = (page) => {
    const parts = [];
    if (extraQuery) parts.push(extraQuery);
    if (page > 1) parts.push(`page=${page}`);
    return `${route}${parts.length ? '?' + parts.join('&') : ''}`;
  };

  const controls = `
    <div class="result-line" style="justify-content:center;gap:var(--sp-2);margin:var(--sp-5) 0;flex-wrap:wrap">
      <span>第 <b>${cur}</b> / ${pages} 页 · 共 <b>${list.length}</b> 条（每页 ${per}）</span>
      <div class="row" style="gap:4px">
        <button class="btn btn-sm" data-act="page" data-page="${cur - 1}" ${cur === 1 ? 'disabled' : ''}>上一页</button>
        ${withGaps.map((x) => (x === 'gap'
          ? '<span class="text-3" style="padding:0 2px">…</span>'
          : `<button class="btn btn-sm${x === cur ? ' btn-primary' : ''}" data-act="page" data-page="${x}">${x}</button>`)).join('')}
        <button class="btn btn-sm" data-act="page" data-page="${cur + 1}" ${cur === pages ? 'disabled' : ''}>下一页</button>
      </div>
      <button class="btn btn-sm btn-ghost" data-act="set-perpage" data-value="0">一次显示全部</button>
    </div>`;

  return { slice, controls };
}

function relevanceMeter(score) {
  const s = clamp(Number(score) || 0, 0, 100);
  return `<span class="relevance" data-tip="相关度评分 ${s}/100">
    <span class="relevance-bar"><i style="width:${s}%"></i></span><span class="tnum">${s}</span>
  </span>`;
}

function safeUrl(u) {
  if (!u) return '';
  const s = String(u).trim();
  if (/^(https?:|mailto:)/i.test(s)) return s;
  return '';
}

function hostOf(u) {
  const s = safeUrl(u);
  if (!s) return '';
  try { return new URL(s).hostname.replace(/^www\./, ''); } catch { return ''; }
}

/* ============================== §3 STATE ================================ */

const LS_KEY = 'future.workbench.v1';

const DEFAULT_PREFS = {
  // 暖砂纸 (warm sandpaper) is the default: a low-glare warm light theme that is
  // comfortable for long reading sessions, which is what this workbench is for.
  theme: 'sand',
  accent: 'amber',
  reducedMotion: false,
  showAside: true,
  digestGroup: 'day',      // 'day' | 'category'
  knowledgeSort: 'relevance',
};

const state = {
  /* persisted */
  prefs: { ...DEFAULT_PREFS },
  user: {
    starred: {},     // itemId -> true
    status: {},      // itemId -> 'unread' | 'reading' | 'done'
    mastery: {},     // conceptId -> 0..5
    tasks: {},       // taskKey -> true
    notes: {},       // itemId -> string
    jobStage: {},    // jobId -> stage id
    seen: {},        // itemId -> ISO date first read
  },

  /* data layer */
  ready: false,
  loadErrors: [],
  manifest: null,
  items: [],
  byId: new Map(),
  taxonomy: null,
  channels: null,
  jobs: [],
  skills: [],
  problems: [],
  problemBankMeta: null,   // 题库统计（build_problem_bank.py）：解析完整度 / 主题 / 公司
  formulas: [],
  repos: [],
  courses: [],
  tracks: [],
  digest: null,
  jobsKb: null,
  learningKb: null,
  sourceRegistry: null,
  runs: [],
  index: null,
  proposals: null,      // latest deterministic self-iteration proposal file
  enrichment: {},       // layer-2 agent deep-read output, keyed by item id
  redundancy: null,     // optional redundancy audit (analyze_redundancy.py)
  interview: null,      // optional interview extract (build_interview_index.py)
  problemBank: null,    // 题库定位 (build_problem_bank.py): 题目 + 真实频度 + 深度解析
  enrichedCount: 0,
  papers: [],
  milestones: [],
  studySystem: null,
  skills: [],
  interviewProcess: [],
  salaryBands: [],

  /* view state (ephemeral, never persisted except prefs) */
  route: 'dashboard',
  params: {},
  query: '',
  filters: {
    cat: new Set(),
    src: new Set(),
    tag: new Set(),
    level: null,
    status: null,
    starredOnly: false,
    q: '',
  },
  sort: 'relevance',
  cursor: 0,
  page: 1,              // knowledge/digest pagination (0 = show everything)
  perPage: 60,
  expanded: false,
};

function saveUser() {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({ prefs: state.prefs, user: state.user }));
  } catch (e) { /* storage may be unavailable (file://, private mode) */ }
}

function loadUser() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (parsed.prefs) state.prefs = { ...DEFAULT_PREFS, ...parsed.prefs };
    if (parsed.user) state.user = { ...state.user, ...parsed.user };
  } catch (e) { /* ignore corrupt payload */ }
}

function toggleStar(id) {
  if (state.user.starred[id]) delete state.user.starred[id];
  else state.user.starred[id] = true;
  saveUser();
  return Boolean(state.user.starred[id]);
}

function setStatus(id, status) {
  const cur = state.user.status[id] || 'unread';
  const next = cur === status ? 'unread' : status;
  if (next === 'unread') delete state.user.status[id]; else state.user.status[id] = next;
  if (next === 'done') state.user.mastery[id] = Math.max(state.user.mastery[id] || 0, 3);
  saveUser();
  return next;
}

function starCount() { return Object.keys(state.user.starred).length; }

function statusOf(id) { return state.user.status[id] || 'unread'; }

function completionStats() {
  const total = state.items.length || 1;
  let done = 0, reading = 0, starred = 0;
  for (const it of state.items) {
    const s = statusOf(it.id);
    if (s === 'done') done++;
    else if (s === 'reading') reading++;
    if (state.user.starred[it.id]) starred++;
  }
  return { total, done, reading, starred, pct: (done / total) * 100 };
}

/* ============================== §4 STORE ================================ */
/**
 * The single data-layer adapter. Files are read relative to the page so the
 * whole `web/` folder can be opened directly, served by any static server, or
 * hosted as-is. Every loader is failure-tolerant and records why it failed.
 *
 * The base URL is derived from this script's own <script src> rather than
 * `import.meta.url`, because app.js is deliberately a classic script so that
 * file:// works without a server.
 */
const DATA_ROOT = (() => {
  const src = (document.currentScript && document.currentScript.src) || '';
  try {
    // assets/js/app.js -> assets/js/ -> assets/ -> web/ then into data/
    return new URL('../../data/', src ? new URL(src) : document.baseURI);
  } catch {
    return new URL('data/', document.baseURI);
  }
})();

const Store = {
  async json(relPath, fallback = null) {
    const url = new URL(relPath, DATA_ROOT);
    try {
      const res = await fetch(url, { cache: 'no-cache' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const text = await res.text();
      if (!text.trim()) return fallback;
      return JSON.parse(text);
    } catch (err) {
      state.loadErrors.push({ file: relPath, error: String(err.message || err) });
      return fallback;
    }
  },

  /** Files are addressed with a cache-busting stamp so a fresh daily run is
   *  visible without a hard refresh. */
  async boot() {
    const stamp = Date.now();
    const q = (p) => `${p}?t=${stamp}`;

    const [manifest, digest, jobsKb, learningKb, sourceRegistry, channels, runs, index, proposals, enrichment, deepPlan, redundancy, interview, problemBank] = await Promise.all([
      this.json(q('manifest.json')),
      this.json(q('digest/today.json')),
      this.json(q('jobs.json')),
      this.json(q('learning.json')),
      this.json(q('sources.json')),
      this.json(q('taxonomy.json')),
      this.json(q('logs/runs.json'), []),
      this.json(q('items/index.json')),
      this.json(q('proposals/latest.json')),
      this.json(q('enrichment.json')),
      this.json(q('deep-read-plan.json')),
      // Optional: written by analyze_redundancy.py. Absent on a fresh clone, so it
      // must degrade to null rather than adding a load error to the UI.
      this.json(q('redundancy-report.json'), null),
      // Optional: written by build_interview_index.py (面经速览 panel).
      this.json(q('interview.json'), null),
      // 题库定位 (build_problem_bank.py). Optional so an older dist/ still boots;
      // when absent the view falls back to the hand-curated jobs.json 题库.
      this.json(q('problem-bank.json'), null),
    ]);

    state.manifest = manifest;
    state.digest = digest;
    state.jobsKb = jobsKb;
    state.learningKb = learningKb;
    state.sourceRegistry = sourceRegistry;
    state.channels = channels;
    state.runs = Array.isArray(runs) ? runs : (runs && runs.runs) || [];
    state.proposals = proposals || null;
    state.deepReadPlan = deepPlan || null;
    state.redundancy = redundancy || null;
    state.interview = interview || null;
    state.problemBank = problemBank || null;

    /* Items: prefer the flat search index; otherwise reconstruct from runs. */
    let items = [];
    if (index && Array.isArray(index.items)) items = index.items;
    else if (digest && Array.isArray(digest.items)) items = digest.items;
    else if (Array.isArray(index)) items = index;

    if (!items.length && Array.isArray(state.runs)) {
      const collected = [];
      for (const r of state.runs.slice(0, 14)) {
        if (!r || !r.itemsFile) continue;
        const day = await this.json(q(r.itemsFile), null);
        if (day && Array.isArray(day.items)) collected.push(...day.items);
      }
      items = collected;
    }

    state.items = (items || []).map(normalizeItem).filter(Boolean);

    /* Layer-2 output. The optional agent deep-read writes enrichment.json keyed
       by item id; it is merged in here rather than baked into the index so the
       two layers stay independent (a corpus rebuild cannot lose the analysis,
       and a failed agent run cannot corrupt the corpus). Items with enrichment
       get richer fields plus an `enriched` marker the UI can show. */
    state.enrichment = (enrichment && enrichment.byId) || {};
    const enriched = Object.keys(state.enrichment).length;
    if (enriched) {
      for (const it of state.items) {
        const e = state.enrichment[it.id];
        if (!e) continue;
        it.enriched = true;
        it.tldr = e.tldr || '';
        if (!it.summary && e.tldr) it.summary = e.tldr;
        it.keyPoints = (e.keyPoints && e.keyPoints.length) ? e.keyPoints.map(String) : it.keyPoints;
        if (e.why) it.why = e.why;
        if (e.difficulty) it.difficulty = e.difficulty;
        it.tags = Array.from(new Set([...(it.tags || []), ...(e.tags || []).map(String)]));
        it.entities = Array.from(new Set([...(it.entities || []), ...(e.entities || []).map(String)]));
        it.concepts = Array.isArray(e.concepts) ? e.concepts : [];
        it.selfCheck = e.selfCheck || null;
        it.diagram = e.diagram || null;
        // The teaching layer (progressive depth / Socratic questions / mechanism /
        // boundary / misconceptions / interview phrasing) is a separate enrichment
        // block. It is copied EXPLICITLY because this merge is an allow-list: a new
        // field added by the agent is invisible in the UI until it is named here.
        // That exact omission happened once - the data was on disk and in the drawer
        // payload, but nothing rendered, because `it.teaching` was never assigned.
        it.teaching = (e.teaching && typeof e.teaching === 'object') ? e.teaching : null;
        it.hasTeaching = Boolean(it.teaching);
        // A card counts as "fully parsed" only when it has BOTH a written
        // explanation and a visual. The reader's complaint was that some cards
        // had analysis and some had nothing but a summary/link, so the UI needs
        // to be able to tell the difference.
        it.hasAnalysis = Boolean(it.tldr || (it.concepts && it.concepts.length) || it.keyPoints.length);
        it.hasDiagram = Boolean(it.diagram && (it.diagram.svg || it.diagram.spec));
        // The agent's formulas are also collected into formulas.json, but keeping
        // them on the item lets the detail drawer show "相关公式" in place.
        if (Array.isArray(e.formulas) && e.formulas.length) {
          it.formulas = e.formulas;
        }
      }
      state.enrichedCount = enriched;
    } else {
      state.enrichedCount = 0;
    }

    state.byId = new Map(state.items.map((i) => [i.id, i]));

    state.taxonomy = (channels && Array.isArray(channels.categories)) ? channels
      : (sourceRegistry && Array.isArray(sourceRegistry.taxonomy)) ? { categories: sourceRegistry.taxonomy.map(mapTaxonomy) } : null;

    /* Jobs — support both shapes: {jobs:[...]} from the collector and the
       richer {companies:[...], ...} knowledge base from research. */
    if (jobsKb && Array.isArray(jobsKb.jobs) && jobsKb.jobs.length) {
      state.jobs = jobsKb.jobs.map(normalizeJob).filter(Boolean);
    } else if (jobsKb && Array.isArray(jobsKb.companies)) {
      state.jobs = jobsKb.companies.map(companyToJob).filter(Boolean);
    }

    if (jobsKb) {
      state.skills = (jobsKb.skillMatrix || []).map(normalizeSkill);
    }

    /* 题库定位 —— 数据源优先级（这是「把链接变成被解过的题」的落点）：
     *
     *   1. problem-bank.json（build_problem_bank.py）—— 把三个来源合成一个题目实体：
     *      CodeTop 的「公司 × 题号 × 被考频度」真实记录、算法知识库的题解页、
     *      jobs.json 里的人工题库，并且挂上 daily-agent 写出的深度解析
     *      （可运行代码 / 图解 / 复杂度 / 易错点）。
     *   2. 退化到 jobs.json 的人工题库。
     *
     * 为什么不是简单地把两批合并：同一道题（例如 LeetCode 4）在 codetop、
     * 代码随想录、人工题库里各有一条记录。bank 已经在服务端按题号做了归一，
     * 前端再合并一次会重复计频、也会让「主题热力」的掌握度分母虚高。
     */
    if (problemBank && Array.isArray(problemBank.problems) && problemBank.problems.length) {
      state.problems = problemBank.problems.map(normalizeBankProblem).filter(Boolean);
      state.problemBankMeta = {
        generatedAt: problemBank.generatedAt,
        counts: problemBank.counts || {},
        topics: problemBank.topics || [],
        companies: problemBank.companies || [],
        note: problemBank.note || '',
      };
    } else if (jobsKb) {
      state.problems = [
        ...(jobsKb.handWrittenCoding || []).map((p) => normalizeProblem(p, 'hand')),
        ...(jobsKb.writtenExam || []).map((p) => normalizeProblem(p, 'exam')),
      ];
      state.problemBankMeta = null;
    }
    if (jobsKb) {
      state.interviewProcess = jobsKb.interviewProcess || [];
      state.salaryBands = jobsKb.salaryBands || [];
      state.jobSources = jobsKb.sources || [];
    }

    if (learningKb) {
      state.tracks = (learningKb.tracks || []).map(normalizeTrack);
      state.repos = (learningKb.repos || []).map(normalizeRepo);
      state.courses = (learningKb.courses || []).map(normalizeCourse);
      state.papers = (learningKb.papers || []).map(normalizePaper);
      state.milestones = learningKb.milestones || [];
      state.studySystem = learningKb.studySystem || null;
    } else {
      state.papers = [];
    }

    /* Formulas and daily items may also carry formulas; merge and de-dupe. */
    const fdx = await this.json(q('formulas.json'), null);
    const baseFormulas = (fdx && (fdx.formulas || fdx)) || [];
    state.formulas = (Array.isArray(baseFormulas) ? baseFormulas : []);
    for (const it of state.items) {
      for (const f of it.formulas || []) {
        if (!f) continue;
        const id = f.id || `f-${it.id}-${state.formulas.length}`;
        if (!state.formulas.some((x) => x.id === id)) state.formulas.push({ ...f, id, sourceItem: it.id });
      }
    }

    state.ready = true;
    return state;
  },
};

/* ---- Normalizers: tolerant of every shape the collector (or a human) may
        produce, so one malformed field can never blank the interface. ------ */
function pick(...vals) {
  for (const v of vals) if (v !== undefined && v !== null && v !== '') return v;
  return undefined;
}
const arr = (v) => (Array.isArray(v) ? v : v ? [v] : []);

function normalizeItem(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const id = String(pick(raw.id, raw.uid, raw.url, raw.title, Math.random().toString(36).slice(2)));
  const catRaw = String(pick(raw.category, raw.cat, raw.primaryCategory, 'trend')).toLowerCase();
  const category = CAT_BY_ID[catRaw] ? catRaw : mapCategoryAlias(catRaw);
  const sources = arr(raw.sources).map((s) => (typeof s === 'string' ? { url: s } : s)).filter(Boolean);
  const url = safeUrl(pick(raw.url, raw.canonicalUrl, sources[0] && sources[0].url));
  return {
    id,
    category,
    title: String(pick(raw.title, raw.name, '(无标题)')),
    titleZh: raw.titleZh || raw.title_zh || '',
    summary: String(pick(raw.summary, raw.tldr, raw.abstract, raw.desc, '')),
    keyPoints: arr(pick(raw.keyPoints, raw.key_points, raw.bullets)).map(String),
    why: String(pick(raw.why, raw.relevance, raw.reason, '')),
    url,
    canonicalUrl: safeUrl(raw.canonicalUrl) || url,
    sources: sources.length ? sources : (url ? [{ url, name: hostOf(url) }] : []),
    channel: String(pick(raw.channel, raw.sourceId, raw.source, 'manual')),
    authors: arr(raw.authors).map(String),
    publishedAt: pick(raw.publishedAt, raw.published_at, raw.date, null),
    fetchedAt: pick(raw.fetchedAt, raw.fetched_at, null),
    lang: raw.lang || (/[\u4e00-\u9fa5]/.test(String(raw.title || '')) ? 'zh' : 'en'),
    tags: arr(raw.tags).map(String),
    entities: arr(raw.entities).map(String),
    difficulty: raw.difficulty || null,
    relevance: Number(pick(raw.relevanceScore, raw.relevance, raw.score, 0)) || 0,
    quality: raw.qualitySignals || raw.quality || {},
    venue: pick(raw.venue, (raw.qualitySignals || {}).venue, null),
    ccf: pick(raw.ccf, (raw.qualitySignals || {}).ccfRank, null),
    stars: pick(raw.stars, (raw.qualitySignals || {}).stars, null),
    formulas: arr(raw.formulas),
    examples: arr(raw.examples),
    details: raw.details || raw.body || null,
    date: pick(raw.date, raw.day, (raw.fetchedAt || '').slice(0, 10), null),
  };
}

function mapCategoryAlias(c) {
  if (!c) return 'trend';
  // 'unclassified' is emitted by collect.py when NO keyword matched at all. Calling
  // it 'trend' was actively misleading: the old classifier defaulted zero-hit items
  // to trend, which is how a grammar/pragmatics paper ended up in the trend queue.
  // Keep it as its own label so it is visible and can be filtered out.
  if (/^unclassified$|uncategor/.test(c)) return 'unclassified';
  if (/multi|vision|vlm|mllm/.test(c)) return 'multimodal';
  if (/post|sft|rlhf|align|dpo|grpo/.test(c)) return 'posttraining';
  if (/world|embodied|vla/.test(c)) return 'worldmodel';
  if (/diffus|gen|flow/.test(c)) return 'generative';
  if (/^rl$|reinforce/.test(c)) return 'rl';
  if (/agent|tool/.test(c)) return 'agent';
  if (/code|hand|leet/.test(c)) return 'coding';
  if (/exam|written/.test(c)) return 'exam';
  if (/job|hiring|career/.test(c)) return 'job';
  if (/paper|arxiv/.test(c)) return 'paper';
  if (/course|repo|resource/.test(c)) return 'course';
  if (/engineer|system|infra|train/.test(c)) return 'engineering';
  if (/found|basic|theor/.test(c)) return 'foundation';
  return 'trend';
}

function normalizeJob(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const id = String(pick(raw.id, raw.jobId, `${raw.company}-${raw.title}`, Math.random().toString(36).slice(2)));
  return {
    id,
    company: String(pick(raw.company, raw.companyName, raw.employer, '未知公司')),
    shortName: raw.shortName || String(pick(raw.company, '?')).slice(0, 2),
    tier: raw.tier || 'B',
    title: String(pick(raw.title, raw.role, raw.position, '算法实习生')),
    directions: arr(pick(raw.directions, raw.direction, raw.tags)).map(String),
    cities: arr(pick(raw.cities, raw.city, raw.location)).map(String),
    pay: pick(raw.pay, raw.dailyPay, (raw.internship || {}).dailyPayRange, raw.salary, null),
    duration: pick(raw.duration, (raw.internship || {}).duration, null),
    conversion: pick(raw.conversion, (raw.internship || {}).conversion, null),
    open: raw.open !== false && (raw.internship ? raw.internship.open !== false : true),
    applyUrl: safeUrl(pick(raw.applyUrl, (raw.internship || {}).applyUrl, raw.url)),
    seasonality: pick(raw.seasonality, (raw.internship || {}).seasonality, null),
    highlights: arr(raw.highlights).map(String),
    process: arr(pick(raw.interviewProcess, raw.process)).map(String),
    notes: raw.notes || '',
    confidence: raw.confidence || null,
    relevance: Number(pick(raw.relevance, raw.relevanceScore, raw.score, 0)) || 0,
    sources: arr(raw.sources),
    postedAt: pick(raw.postedAt, raw.updatedAt, null),
    deadline: raw.deadline || null,
  };
}

function companyToJob(c) {
  const j = normalizeJob({
    id: c.id || c.name,
    company: c.name,
    shortName: c.shortName,
    tier: c.tier,
    title: '算法实习生（多方向）',
    directions: c.directions,
    cities: c.cities,
    pay: (c.internship || {}).dailyPayRange,
    duration: (c.internship || {}).duration,
    conversion: (c.internship || {}).conversion,
    open: (c.internship || {}).open,
    applyUrl: (c.internship || {}).applyUrl,
    seasonality: (c.internship || {}).seasonality,
    highlights: c.highlights,
    process: c.interviewProcess,
    notes: c.notes,
    confidence: c.confidence,
    sources: c.sources,
  });
  return j;
}

function normalizeSkill(s) {
  return {
    id: String(pick(s.id, s.skill, Math.random().toString(36).slice(2))),
    skill: String(pick(s.skill, s.name, '—')),
    category: s.category || 'general',
    importance: clamp(Number(pick(s.importance, 3)) || 3, 1, 5),
    demand: arr(pick(s.demandCompanies, s.companies)).map(String),
    evidence: s.evidence || '',
    howToProve: s.howToProve || s.proof || '',
    learnCost: s.learnCost || s.cost || '',
    mastered: 0,
    sources: arr(s.sources),
  };
}

function normalizeProblem(p, kind) {
  const id = String(pick(p.id, p.title, Math.random().toString(36).slice(2)));
  return {
    id: `${kind}-${id}`,
    rawId: id,
    kind, // 'hand' | 'exam'
    title: String(pick(p.title, p.prompt, '—')),
    type: p.type || (kind === 'hand' ? '手撕代码' : '场景题'),
    difficulty: p.difficulty || 'medium',
    frequency: clamp(Number(pick(p.frequency, 3)) || 3, 1, 5),
    topics: arr(pick(p.topics, p.tags)).map(String),
    prompt: p.prompt || p.title || '',
    keyPoints: arr(p.keyPoints).map(String),
    pitfalls: arr(p.pitfalls).map(String),
    solution: p.referenceSolution || p.solution || '',
    answerOutline: arr(p.answerOutline).map(String),
    sources: arr(p.sources),
  };
}

/* ---- 题库定位：把 problem-bank.json 的题目实体归一化成视图模型 --------- */
/* Map a real CodeTop frequency onto the 1–5 star scale the card shows.
 * The raw number is "how many times this problem was actually asked" and ranges from
 * single digits to ~300 (median ≈ 20), so a linear map would make every card 1 star.
 * Breakpoints chosen against that observed distribution. */
function freqStars(n) {
  const v = Number(n) || 0;
  if (v >= 150) return 5;
  if (v >= 80) return 4;
  if (v >= 35) return 3;
  if (v >= 12) return 2;
  return 1;
}

function normalizeBankProblem(p) {
  if (!p || !p.title) return null;
  const a = p.analysis || null;
  const pb = (a && a.problem) || {};
  const sol = pb.solution || {};
  return {
    id: `pb-${p.key || p.title}`,
    rawId: p.key || p.title,
    kind: p.kind === 'exam' ? 'exam' : 'hand',
    type: p.kind === 'exam' ? '笔试场景' : '手撕代码',
    // 赛道：model（模型与训练手撕）/ algorithm（算法与数据结构）/ exam（笔试场景）。
    // model 是读者点名的最高优先级视图，题库页默认展示它。
    track: p.track || (p.kind === 'exam' ? 'exam' : 'algorithm'),
    title: String(p.title),
    number: p.number || null,
    // 题号有两个编号空间：LeetCode（number，显示 #102）与卡码网（kbNumber，
    // 显示 卡码网102）。它们的 102 是两道不同的题，不能混显示。
    namespace: p.namespace || (p.number ? 'leetcode' : 'kb'),
    kbNumber: p.kbNumber || null,
    difficulty: p.difficulty || 'medium',
    frequency: freqStars(p.frequency),
    frequencyRaw: Number(p.frequency) || 0,
    companies: arr(p.companies),
    topics: arr(p.topics).map(String),
    statement: String(pick(pb.statement, p.statement) || ''),
    prompt: String(pick(pb.statement, p.statement) || ''),
    approach: pb.approach || null,
    keyPoints: arr(pick(pb.keyPoints, p.keyPoints)).map(String),
    pitfalls: arr(pick(pb.pitfalls, p.pitfalls)).map(String),
    edgeCases: arr(pick(pb.edgeCases, p.edgeCases)).map(String),
    complexity: pb.complexity || null,
    interviewTips: String(pb.interviewTips || ''),
    solution: String(pick(sol.python, sol.code, p.code) || ''),
    // 模型赛道独有层：同机制的其它实现与横向对比表（深读通用通道不产出）
    variants: arr(pb.variants).map((v) => ({
      name: String(v.name || ''),
      idea: String(v.idea || ''),
      code: String(v.code || ''),
      when: String(v.when || ''),
      cost: String(v.cost || ''),
    })),
    comparison: arr(pb.comparison).map((r) => arr(r.cells).map(String)),
    answerOutline: arr(p.answerOutline).map(String),
    analysis: a,
    analysisStatus: p.analysisStatus || 'none',
    url: safeUrl(p.url) || '',
    sources: arr(p.sources),
    origins: arr(p.origins),
  };
}

function normalizeTrack(t) {  return {
    id: String(pick(t.id, t.name, Math.random().toString(36).slice(2))),
    name: String(pick(t.name, t.title, '—')),
    goal: t.goal || '',
    weeks: Number(pick(t.durationWeeks, t.weeks, 0)) || 0,
    level: t.level || 'core',
    prerequisites: arr(t.prerequisites).map(String),
    modules: arr(t.modules).map((m, i) => ({
      id: String(pick(m.id, `${t.id}-m${i}`)),
      title: String(pick(m.title, m.name, `模块 ${i + 1}`)),
      week: m.week || null,
      hours: Number(pick(m.hours, 0)) || 0,
      objectives: arr(m.objectives).map(String),
      concepts: arr(m.concepts).map(String),
      tasks: arr(m.tasks).map((k, j) => ({
        id: String(pick(k.id, `${t.id}-m${i}-t${j}`)),
        title: String(pick(k.title, k.name, '—')),
        type: k.type || 'study',
        estimateHours: Number(pick(k.estimateHours, k.hours, 0)) || 0,
        deliverable: k.deliverable || '',
        done: k.done || k.acceptance || '',
      })),
      paperIds: arr(m.paperIds),
      repoIds: arr(m.repoIds),
      courseIds: arr(m.courseIds),
    })),
  };
}

function normalizeRepo(r) {
  return {
    id: String(pick(r.id, r.name, Math.random().toString(36).slice(2))),
    owner: r.owner || '',
    name: String(pick(r.name, r.repo, '—')),
    url: safeUrl(pick(r.url, r.htmlUrl)),
    stars: Number(pick(r.stars, r.stargazers, 0)) || 0,
    language: r.language || '',
    area: r.area || '',
    difficulty: r.difficulty || 'medium',
    why: r.why || '',
    studyPlan: arr(r.studyPlan).map(String),
    checkpoints: arr(r.checkpoints).map(String),
    status: r.status || 'active',
    lastVerified: r.lastVerified || null,
  };
}

function normalizeCourse(c) {
  return {
    id: String(pick(c.id, c.title, Math.random().toString(36).slice(2))),
    title: String(pick(c.title, c.name, '—')),
    provider: c.provider || '',
    year: c.year || null,
    url: safeUrl(c.url),
    language: c.language || 'en',
    hours: Number(pick(c.hours, 0)) || 0,
    level: c.level || 'intermediate',
    area: c.area || '',
    hasAssignments: Boolean(c.hasAssignments),
    why: c.why || '',
    modules: arr(c.modules).map(String),
    status: c.status || 'active',
  };
}

function normalizePaper(p) {
  return {
    id: String(pick(p.id, p.title, Math.random().toString(36).slice(2))),
    title: String(pick(p.title, '—')),
    year: p.year || null,
    venue: p.venue || '',
    ccf: p.ccf || null,
    area: p.area || '',
    url: safeUrl(p.url),
    why: p.why || '',
    readingOrder: p.readingOrder || null,
    difficulty: p.difficulty || 'medium',
    mustRead: Boolean(p.mustRead),
    keyIdeas: arr(p.keyIdeas).map(String),
    readTime: p.readTime || '',
    followUps: arr(p.followUps).map(String),
  };
}

function mapTaxonomy(t) {
  return {
    id: t.id,
    zh: t.nameZh || t.name || t.id,
    en: t.nameEn || t.id,
    desc: t.description || '',
    goal: t.collectionGoal || '',
    keywords: arr(t.keywordsZh).concat(arr(t.keywordsEn)),
    cadence: t.updateCadence || '',
  };
}

/* Convenience selectors used by the views. */
function itemsOf(catId) { return state.items.filter((i) => i.category === catId); }

function allTags() {
  const m = new Map();
  for (const it of state.items) for (const t of it.tags) m.set(t, (m.get(t) || 0) + 1);
  return Array.from(m.entries()).sort((a, b) => b[1] - a[1]);
}

function allChannels() {
  const m = new Map();
  for (const it of state.items) m.set(it.channel, (m.get(it.channel) || 0) + 1);
  return Array.from(m.entries()).sort((a, b) => b[1] - a[1]);
}

function dayOf(item) {
  const d = item.date || (item.publishedAt || item.fetchedAt || '').slice(0, 10);
  return d || '未知日期';
}

function groupByDay(items) {
  const m = new Map();
  for (const it of items) {
    const d = dayOf(it);
    if (!m.has(d)) m.set(d, []);
    m.get(d).push(it);
  }
  return Array.from(m.entries())
    .sort((a, b) => String(b[0]).localeCompare(String(a[0])))
    .map(([day, list]) => ({ day, items: list.sort((a, b) => b.relevance - a.relevance) }));
}

/* ============================== §5 THEME ================================ */

function applyPrefs() {
  const p = state.prefs;
  const root = document.documentElement;
  root.dataset.theme = p.theme || 'sand';
  root.dataset.accent = p.accent || 'amber';
  // NOTE: there is deliberately NO `data-density`. The density setting was
  // removed because nothing ever read it - no CSS rule targeted
  // `[data-density]`, so the 舒适/紧凑 toggle had zero visual effect and was
  // purely decorative. Keeping a control that does nothing is worse than not
  // offering it.
  root.dataset.motion = p.reducedMotion ? 'reduced' : 'full';
  const theme = THEMES.find((t) => t.id === p.theme);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta && theme) meta.setAttribute('content', theme.swatches[0]);
}

function setTheme(id) {
  state.prefs.theme = id;
  const t = THEMES.find((x) => x.id === id);
  if (t) state.prefs.accent = t.accent;
  applyPrefs(); saveUser();
}

function setAccent(id) { state.prefs.accent = id; applyPrefs(); saveUser(); }

function toggleThemeKind() {
  const cur = THEMES.find((t) => t.id === state.prefs.theme) || THEMES[0];
  const next = cur.kind === 'dark' ? THEMES.find((t) => t.kind === 'light') : THEMES.find((t) => t.kind === 'dark');
  if (next) setTheme(next.id);
}

/* ============================== §6 TOAST =============================== */

const TOAST_ICON = { ok: 'i-check', warn: 'i-alert', err: 'i-alert', info: 'i-info' };

function toast(message, kind = 'ok', ms = 3200) {
  const root = $('#toasts');
  if (!root) return;
  const node = el('div', { class: `toast ${kind}`, role: 'status' },
    el('span', { html: icon(TOAST_ICON[kind] || 'i-info') }),
    el('span', { text: message }));
  root.append(node);
  setTimeout(() => {
    node.classList.add('out');
    setTimeout(() => node.remove(), 300);
  }, ms);
}

/* ===== ui.part.js — 790 lines ===== */

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

function openThemePopover(anchor) {
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

function openPalette(seed = '') {
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

function closePalette() {
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

function paletteCommit() {
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

function openDrawer({ eyebrow, title, meta = '', body = '', foot = '', cat = null }) {
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

function closeDrawer() {
  const d = $('#drawer');
  d.classList.remove('open');
  d.setAttribute('aria-hidden', 'true');
  $('#scrim').classList.remove('open');
  if (drawerReturnFocus && drawerReturnFocus.focus) drawerReturnFocus.focus();
}

function refreshDrawer() {
  const d = $('#drawer');
  if (!d.classList.contains('open')) return;
  const id = d.dataset.itemId;
  if (id && state.byId.has(id)) openItem(id, { keepScroll: true });
}

/* ============================== ROUTER ================================== */

const VIEWS = {}; // filled by views.js

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [path, qs] = raw.split('?');
  const id = (path || 'dashboard').split('/')[0] || 'dashboard';
  const params = {};
  if (qs) for (const [k, v] of new URLSearchParams(qs)) params[k] = v;
  return { id, params };
}

function go(hash, { replace = false } = {}) {
  if (replace) history.replaceState(null, '', hash);
  else location.hash = hash;
  if (replace) render();
}

let lastRenderKey = '';

function render() {
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

function updateNavCounts() {
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
async function checkForNewBuild() {
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

function reloadData() {
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
function buildFeedbackPayload() {
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
async function exportFeedback() {
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

function exportProgress() {
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

async function copyText(text, okMsg = '已复制到剪贴板') {
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

function installKeyboard() {
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

function installShell() {
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

/* ===== views.part.js — 705 lines ===== */

/* ============================================================================
 * Future · 求职学习工作台 — views.js (part 2)
 * One renderer per route. Each view exposes { title, render(params), after? }.
 * Renderers return HTML strings; `after` wires up anything that needs real DOM
 * (canvases, scroll containers, drag-and-drop).
 * ========================================================================= */

/* ======================= SHARED FILTER / SEARCH ========================= */

function queryMatches(it, q) {
  if (!q) return true;
  const hay = [it.title, it.titleZh, it.summary, it.why, it.category, it.channel,
    ...it.tags, ...it.entities, ...it.keyPoints, it.venue, it.authors.join(' ')]
    .join(' \u0001 ').toLowerCase();
  return String(q).toLowerCase().split(/\s+/).filter(Boolean).every((tok) => hay.includes(tok));
}

function filteredItems() {
  const f = state.filters;
  let list = state.items.slice();
  if (f.cat.size) list = list.filter((i) => f.cat.has(i.category));
  if (f.src.size) list = list.filter((i) => f.src.has(i.channel));
  if (f.tag.size) list = list.filter((i) => i.tags.some((t) => f.tag.has(t)));
  if (f.starredOnly) list = list.filter((i) => state.user.starred[i.id]);
  if (f.status) list = list.filter((i) => statusOf(i.id) === f.status);
  if (f.q) list = list.filter((i) => queryMatches(i, f.q));
  const sorters = {
    relevance: (a, b) => b.relevance - a.relevance || String(b.publishedAt || '').localeCompare(String(a.publishedAt || '')),
    newest: (a, b) => String(b.publishedAt || b.fetchedAt || '').localeCompare(String(a.publishedAt || a.fetchedAt || '')),
    oldest: (a, b) => String(a.publishedAt || a.fetchedAt || '').localeCompare(String(b.publishedAt || b.fetchedAt || '')),
    title: (a, b) => a.title.localeCompare(b.title, 'zh-Hans-CN'),
    difficulty: (a, b) => DIFF_ORDER.indexOf(a.difficulty) - DIFF_ORDER.indexOf(b.difficulty),
  };
  return list.sort(sorters[state.sort] || sorters.relevance);
}
const DIFF_ORDER = ['easy', 'medium', 'hard', null, undefined];

function activeFilterCount() {
  const f = state.filters;
  return f.cat.size + f.src.size + f.tag.size + (f.q ? 1 : 0) + (f.starredOnly ? 1 : 0) + (f.status ? 1 : 0);
}

function filterBar({ cats = true, srcs = true, tags = [], sorts = null, counts = null } = {}) {
  const f = state.filters;
  // `counts` is a category->count Map used for the chips, NOT the result total.
  // Passing it into the "共 N 条" label printed "[object Map]" - the result count
  // is always derived from the actual filtered list.
  const total = filteredItems().length;
  return `
  <div class="filterbar">
    <div class="field" style="width:min(300px,40vw)">
      ${icon('i-search')}
      <input id="q-input" type="search" placeholder="筛选标题、摘要、标签…" value="${attr(f.q)}" aria-label="筛选知识卡片">
      ${f.q ? `<button class="icon-btn" data-act="clear-filters" aria-label="清空">${icon('i-x')}</button>` : ''}
    </div>

    <button class="chip${f.starredOnly ? ' is-on' : ''}" data-act="starred-only">${icon('i-star', '', 11)} 只看收藏</button>

    <div class="segmented" role="group" aria-label="阅读状态">
      ${['', 'unread', 'reading', 'done'].map((s) => `<button class="${f.status === (s || null) ? 'is-on' : ''}"
        data-act="filter-status" data-status="${s}">${s === '' ? '全部' : { unread: '未读', reading: '学习中', done: '已掌握' }[s]}</button>`).join('')}
    </div>

    ${sorts ? `<select class="select select-sm" id="sort-select" aria-label="排序">
      ${sorts.map(([k, label]) => `<option value="${k}"${state.sort === k ? ' selected' : ''}>${esc(label)}</option>`).join('')}
    </select>` : ''}

    <div class="spacer"></div>
    <div class="result-line">共 <b>${total}</b> 条${activeFilterCount() ? ` · ${activeFilterCount()} 个筛选条件` : ''}</div>
    ${activeFilterCount() ? `<button class="btn btn-sm btn-ghost" data-act="clear-filters">${icon('i-x')} 清空</button>` : ''}
  </div>

  ${cats ? `<div class="row" style="flex-wrap:wrap;gap:6px;margin-bottom:var(--sp-4)">
    ${CATEGORIES.filter((c) => counts == null || (counts.get(c.id) || 0) > 0).map((c) => `
      <button class="chip${f.cat.has(c.id) ? ' is-on' : ''}" data-cat="${c.id}" data-act="toggle-cat">
        <span class="chip-dot"></span>${esc(c.zh)}${counts ? ` <span class="tnum" style="opacity:.7">${counts.get(c.id) || 0}</span>` : ''}
      </button>`).join('')}
  </div>` : ''}

  ${srcs && allChannels().length ? `<div class="row" style="flex-wrap:wrap;gap:6px;margin-bottom:var(--sp-4)">
    <span class="eyebrow" style="margin-right:4px">来源</span>
    ${allChannels().map(([ch, n]) => `
      <button class="chip${f.src.has(ch) ? ' is-on' : ''}" data-act="toggle-src" data-src="${attr(ch)}">
        ${esc(channelMeta(ch).zh)} <span class="tnum" style="opacity:.7">${n}</span>
      </button>`).join('')}
  </div>` : ''}

  ${tags.length ? `<div class="row" style="flex-wrap:wrap;gap:6px;margin-bottom:var(--sp-4)">
    <span class="eyebrow" style="margin-right:4px">标签</span>
    ${tags.slice(0, 34).map(([t, n]) => `
      <button class="chip${f.tag.has(t) ? ' is-on' : ''}" data-act="toggle-tag" data-tag="${attr(t)}">
        ${esc(t)} <span class="tnum" style="opacity:.6">${n}</span>
      </button>`).join('')}
  </div>` : ''}`;
}

/* ========================= KNOWLEDGE CARD ============================== */

function knowledgeCard(it, opts = {}) {
  const starred = Boolean(state.user.starred[it.id]);
  const st = statusOf(it.id);
  const src = it.sources[0];
  const srcName = src ? (src.name || channelMeta(it.channel).zh) : channelMeta(it.channel).zh;
  const dt = it.publishedAt || it.fetchedAt;
  const style = opts.delay ? ` style="animation-delay:${opts.delay}ms"` : '';
  return `
  <article class="card card-hover kcard" data-cat="${it.category}"${style} data-act="open-item" data-id="${attr(it.id)}" tabindex="0" role="button"
    aria-label="${attr(it.title)}">
    <div class="kcard-top">
      ${catPill(it.category)}
      <div class="kcard-actions" style="margin-left:auto">
        <button class="icon-btn${starred ? ' is-on' : ''}" data-act="star" data-id="${attr(it.id)}"
          aria-label="${starred ? '取消收藏' : '收藏'}" aria-pressed="${starred}" data-tip="收藏">${icon('i-star')}</button>
        <button class="icon-btn${st === 'done' ? ' is-done' : ''}" data-act="status" data-id="${attr(it.id)}" data-status="done"
          aria-label="标记已掌握" data-tip="${st === 'done' ? '已掌握' : '标记已掌握'}">${icon('i-check')}</button>
      </div>
    </div>

    <h3 class="kcard-title">${esc(it.title)}</h3>

    ${it.why ? `<div class="kcard-why"><b>为什么重要 · </b>${esc(it.why)}</div>` : ''}
    ${it.summary ? `<p class="kcard-summary clamp-4">${esc(it.tldr || it.summary)}</p>` : ''}

    ${it.keyPoints.length ? `<ul class="kcard-points">
      ${it.keyPoints.slice(0, 3).map((k) => `<li><span class="clamp-2">${esc(k)}</span></li>`).join('')}
    </ul>` : ''}

    ${it.tags.length ? `<div class="row" style="flex-wrap:wrap;gap:4px">
      ${it.tags.slice(0, 6).map((t) => `<span class="tag">${esc(t)}</span>`).join('')}
      ${it.ccf ? `<span class="tag tag-accent">CCF-${esc(it.ccf)}</span>` : ''}
      ${it.venue ? `<span class="tag">${esc(it.venue)}</span>` : ''}
      ${it.stars ? `<span class="tag">★ ${esc(String(it.stars))}</span>` : ''}
    </div>` : ''}

    <div class="kcard-foot">
      ${src ? `<a class="kcard-src" href="${attr(safeUrl(src.url))}" target="_blank" rel="noopener noreferrer"
        data-act="none" onclick="event.stopPropagation()">${icon('i-external', '', 11)} ${esc(srcName)}</a>`
        : `<span class="kcard-src">${icon('i-info', '', 11)} ${esc(srcName)}</span>`}
      <div class="kcard-meta">
        ${it.hasDiagram ? `<span class="tag tag-accent" data-tip="含图解与深度解析">深度解析</span>`
          : it.enriched ? `<span class="tag" data-tip="已深读，但深度层未给出图解">深读</span>`
          : `<span class="tag" data-tip="尚未深读：只有采集层摘要与来源链接">仅摘要</span>`}
        ${it.difficulty ? `<span class="tag">${esc(DIFF_ZH[it.difficulty] || it.difficulty)}</span>` : ''}
        ${dt ? `<span data-tip="${attr(fmtDate(dt, 'datetime'))}">${esc(relTime(dt))}</span>` : ''}
        ${relevanceMeter(it.relevance)}
      </div>
    </div>
  </article>`;
}

const DIFF_ZH = { easy: '入门', medium: '进阶', hard: '硬核' };

function renderCards(list, opts = {}) {
  if (!list.length) {
    return emptyState('没有匹配的知识卡片', '试试放宽筛选条件，或清空搜索关键词。', 'i-layers',
      `<button class="btn btn-sm" data-act="clear-filters">清空筛选</button>`);
  }
  // Paginate: the previous hard cap of 90 made most of a 700+ item corpus
  // unreachable. `opts.all` is for the callers that genuinely want everything
  // (the print/starred review list).
  const { slice, controls } = opts.all
    ? { slice: list, controls: '' }
    : paginate(list, {
      route: state.route === 'starred' ? '#/starred' : '#/knowledge',
      extraQuery: state.filters.cat.size ? `cat=${encodeURIComponent([...state.filters.cat][0])}` : '',
    });
  return `<div class="grid grid-auto">${slice.map((it, i) => knowledgeCard(it, { delay: Math.min(i * 22, 240) })).join('')}</div>`
    + controls;
}

/* Today's deterministic TL;DR, produced by collect.py's summarizer. Rendering
   it above the card grids answers "what happened today?" before "what is the
   newest item?", which is the order a person actually wants. */
/* Staleness is the one failure mode that looks exactly like success: the page
   renders fine, the numbers are just old. Say it out loud. */
function staleWarning(m) {
  const last = m && m.lastRunAt;
  const nxt = m && m.schedule && m.schedule.nextRunAt;
  if (!last) {
    return `<div style="margin-top:var(--sp-3)" class="status-line"><span class="warn">尚未运行过采集</span>
      <span class="text-3">运行 scripts/run-daily.ps1 或等待每日 18:00</span></div>`;
  }
  const hours = (Date.now() - new Date(last).getTime()) / 3600000;
  if (hours > 36) {
    return `<div style="margin-top:var(--sp-3);padding:var(--sp-2) var(--sp-3);border-radius:var(--r-sm);background:color-mix(in oklab,var(--err) 12%,transparent);font-size:var(--fs-3xs);color:var(--err)">
      距上次成功采集已 ${Math.round(hours)} 小时，超过 36 小时阈值 —— 定时任务可能没触发（检查任务计划程序状态，或看 data/logs/harness-*.log）。</div>`;
  }
  return `<div style="margin-top:var(--sp-3)" class="status-line"><span class="ok">数据在有效期内</span>
    <span class="text-3">下次 ${esc(nxt ? fmtDate(nxt, 'datetime') : '每日 18:00')} 自动更新</span></div>`;
}

function dailySummaryHtml({ compact = false } = {}) {  const s = (state.digest && state.digest.summary) || (state.manifest && state.manifest.summary);
  if (!s) return '';
  const c = s.counts || {};
  const highlights = (s.highlights || []).slice(0, compact ? 3 : 6);
  const topItems = (s.topItemIds || [])
    .map((id) => state.byId.get(id))
    .filter(Boolean)
    .slice(0, compact ? 3 : 6);
  return `
  <section class="panel" style="margin-bottom:var(--sp-5);animation:card-in var(--t-slow) var(--ease-out) both">
    <div class="panel-head">
      <div class="panel-title">${icon('i-bulb')} 今日速览</div>
      <span class="result-line" style="margin-left:auto">${esc(s.generatedBy || '')}</span>
    </div>
    <div class="panel-body">
      <p style="font-size:var(--fs-sm);color:var(--fg-0);line-height:var(--lh-snug);margin-bottom:var(--sp-4)">${esc(s.headline || '')}</p>
      ${highlights.length ? `<ul class="kcard-points" style="margin-bottom:var(--sp-4)">
        ${highlights.map((h) => `<li><span>${esc(h)}</span></li>`).join('')}</ul>` : ''}
      <div class="row" style="flex-wrap:wrap;gap:var(--sp-5);margin-bottom:${topItems.length ? 'var(--sp-4)' : '0'}">
        <div class="stat"><span class="stat-val" style="font-size:var(--fs-lg)">${esc(String(c.fresh ?? 0))}</span><span class="stat-key">本轮新增</span></div>
        <div class="stat"><span class="stat-val" style="font-size:var(--fs-lg)">${esc(String(c.peerReviewed ?? 0))}</span><span class="stat-key">同行评审</span></div>
        <div class="stat"><span class="stat-val" style="font-size:var(--fs-lg)">${esc(String(c.codeAvailable ?? 0))}</span><span class="stat-key">含开源实现</span></div>
        <div class="stat"><span class="stat-val" style="font-size:var(--fs-lg)">${esc(String(c.zhSources ?? 0))}</span><span class="stat-key">中文来源</span></div>
        <div class="stat"><span class="stat-val" style="font-size:var(--fs-lg)">${esc(String((s.channelsWithItems || []).length))}<small>/${esc(String((s.channelsWithItems || []).length + (s.channelsWithoutItems || []).length))}</small></span><span class="stat-key">渠道有产出</span></div>
      </div>
      ${topItems.length ? `<div class="eyebrow" style="margin-bottom:6px">值得先看</div>
        <div class="col" style="gap:4px">
          ${topItems.map((it) => `<button class="mini-item" style="width:100%;text-align:left;border-radius:var(--r-sm)" data-act="open-item" data-id="${attr(it.id)}" data-cat="${esc(it.category)}">
            <span class="dot"></span>
            <span class="t" style="font-weight:560;color:var(--fg-0)">${esc(it.title.length > 74 ? it.title.slice(0, 74) + '…' : it.title)}</span>
            <span class="n">${esc(String(Math.round(it.relevance)))}</span>
          </button>`).join('')}
        </div>` : ''}
    </div>
  </section>`;
}

/* ============================== DASHBOARD ============================== */

function greeting() {
  const h = shanghaiNow().getHours();
  if (h < 6) return '凌晨好';
  if (h < 11) return '早上好';
  if (h < 14) return '中午好';
  if (h < 18) return '下午好';
  return '晚上好';
}

function daysToDeadline() {
  const target = state.manifest && state.manifest.targetDate;
  if (!target) return null;
  const d = Math.ceil((new Date(target) - new Date()) / 86400000);
  return Number.isFinite(d) ? d : null;
}

const DashboardView = {
  title: '今日工作台',
  render() {
    const s = completionStats();
    const today = dateKey();
    const todayItems = state.items.filter((i) => dayOf(i) === today);
    const recentDays = groupByDay(state.items).slice(0, 7).reverse();
    const spark = recentDays.map((d) => d.items.length);
    const top = [...state.items].sort((a, b) => b.relevance - a.relevance).slice(0, 6);
    const m = state.manifest || {};
    const mh = state.learningKb && state.learningKb.studySystem;
    const dueTrack = state.tracks[0];
    const activeJobs = state.jobs.filter((j) => j.open);
    const stageCounts = jobStageCounts();

    const catCounts = new Map();
    for (const it of state.items) catCounts.set(it.category, (catCounts.get(it.category) || 0) + 1);

    const weekTasks = collectTasks().slice(0, 6);

    return `
    <section class="hero">
      <span class="hero-eyebrow"><span class="pulse"></span> 上海时间 ${esc(shanghaiNow().toLocaleString('zh-CN', { hour12: false }))} · 数据更新于 ${esc(m.lastRunAt ? relTime(m.lastRunAt) : '尚未采集')}</span>
      <h1>${greeting()}，今天把<em>信息差</em>变成<em>竞争力</em></h1>
      <p>面向 <b>多模态算法 / Post-training / 生成式模型 / 世界模型</b> 方向的结构化情报与学习系统。
      每日上海时间 <b>18:00</b> 自动联网调研，把散落在 arXiv、GitHub、牛客、各厂招聘官网的信息，整理成可执行的下一步。</p>

      <div class="hero-stats">
        <div class="stat"><span class="stat-val tnum">${state.items.length}<small>条</small></span><span class="stat-key">知识卡片</span>
          <span class="stat-delta ${todayItems.length ? 'up' : 'flat'}">${todayItems.length ? `+${todayItems.length} 今日` : '今日暂无新增'}</span></div>
        <div class="stat"><span class="stat-val tnum">${activeJobs.length}<small>个</small></span><span class="stat-key">在招岗位</span>
          <span class="stat-delta flat">${state.jobs.filter((j) => j.tier === 'S' || j.tier === 'A').length} 个一线大厂</span></div>
        <div class="stat"><span class="stat-val tnum">${state.problems.length}<small>题</small></span><span class="stat-key">题库沉淀</span>
          <span class="stat-delta flat">手撕 + 场景题</span></div>
        <div class="stat"><span class="stat-val tnum">${Math.round(s.pct)}<small>%</small></span><span class="stat-key">掌握进度</span>
          <span class="stat-delta ${s.done ? 'up' : 'flat'}">${s.done} 已掌握 / ${s.reading} 学习中</span></div>
        ${daysToDeadline() != null ? `<div class="stat"><span class="stat-val tnum">${daysToDeadline()}<small>天</small></span>
          <span class="stat-key">距目标投递</span><span class="stat-delta flat">${esc(m.targetLabel || '目标日期')}</span></div>` : ''}
      </div>
    </section>

    <div class="grid grid-dash">
      <div class="col" style="gap:var(--sp-5)">
        ${dailySummaryHtml({ compact: true })}
        <div>
          <div class="section-head">
            <h2 class="section-title">今日高相关</h2>
            <p class="section-desc">按「方向匹配 × 时效 × 来源质量」加权排序</p>
            <div class="section-actions">
              <button class="btn btn-sm btn-ghost" data-route="#/digest">全部更新 ${icon('i-chevron')}</button>
            </div>
          </div>
          ${top.length ? `<div class="grid grid-2">${top.slice(0, 4).map((it, i) => knowledgeCard(it, { delay: i * 40 })).join('')}</div>`
            : emptyState('还没有知识数据', '运行一次采集（scripts/collect.py）或执行每日 18:00 定时任务后，这里会出现内容。', 'i-database')}
        </div>

        <div class="grid grid-2">
          <div class="panel">
            <div class="panel-head"><div class="panel-title">${icon('i-chart')} 近 7 日采集量</div></div>
            <div class="panel-body">
              ${sparkline(spark)}
              <div class="row" style="justify-content:space-between;margin-top:var(--sp-3);font-size:var(--fs-3xs);color:var(--fg-3)">
                <span>${esc(recentDays[0] ? fmtDate(recentDays[0].day) : '—')}</span>
                <span>合计 <b style="color:var(--fg-1)">${spark.reduce((a, b) => a + b, 0)}</b> 条</span>
                <span>${esc(recentDays.length ? fmtDate(recentDays[recentDays.length - 1].day) : '—')}</span>
              </div>
            </div>
          </div>

          <div class="panel">
            <div class="panel-head"><div class="panel-title">${icon('i-target')} 本周学习安排</div>
              <button class="btn btn-sm btn-ghost" style="margin-left:auto" data-route="#/roadmap">路线 ${icon('i-chevron')}</button></div>
            <div class="panel-body" style="padding:0">
              ${mh && mh.weeklyRhythm ? `<div style="padding:var(--sp-3) var(--sp-4);border-bottom:1px solid var(--line-0)">
                <div class="eyebrow" style="margin-bottom:6px">每周节奏</div>
                <ul style="display:flex;flex-direction:column;gap:4px">
                  ${mh.weeklyRhythm.map((r) => `<li style="font-size:var(--fs-2xs);color:var(--fg-1);display:flex;gap:6px">
                    <span style="color:var(--accent)">▸</span>${esc(r)}</li>`).join('')}
                </ul></div>` : ''}
              <div class="mini-list">
                ${weekTasks.length ? weekTasks.map((t) => `
                  <div class="mini-item">
                    <span class="dot" data-cat="${esc(t.cat)}"></span>
                    <span class="t clamp-2">${esc(t.title)}</span>
                    <span class="n">${esc(t.meta)}</span>
                  </div>`).join('') : `<div style="padding:var(--sp-4);font-size:var(--fs-2xs);color:var(--fg-3)">尚无学习任务数据（等待 learning.json）</div>`}
              </div>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-briefcase')} 岗位与投递节奏</div>
            <button class="btn btn-sm btn-ghost" style="margin-left:auto" data-route="#/jobs">岗位看板 ${icon('i-chevron')}</button></div>
          <div class="panel-body" style="padding:0">
            ${state.jobs.length ? `<div class="mini-list">
              ${activeJobs.slice(0, 6).map((j) => `
                <button class="mini-item job-mini" style="width:100%;text-align:left" data-act="open-job" data-id="${attr(j.id)}">
                  <span class="job-mini-head">
                    <span class="tier" data-tier="${attr(j.tier)}">${esc(j.tier)}</span>
                    <span class="job-mini-name">${esc(j.company)}</span>
                  </span>
                  <span class="job-mini-dirs">${esc(j.directions.slice(0, 3).map(dirZh).join(' · ') || j.title)}</span>
                  <span class="job-mini-pay" data-tip="${attr(j.pay || '面议')}">${esc(j.pay || '面议')}</span>
                </button>`).join('')}
            </div>
            <div style="padding:var(--sp-3) var(--sp-4);border-top:1px solid var(--line-0);display:flex;gap:var(--sp-4);flex-wrap:wrap">
              ${Object.entries(STAGES).map(([k, v]) => `
                <span class="status-line"><span style="width:8px;height:8px;border-radius:2px;background:${v.color};display:inline-block"></span>
                  ${esc(v.label)} <b class="tnum" style="color:var(--fg-0)">${stageCounts[k] || 0}</b></span>`).join('')}
            </div>` : emptyState('暂无岗位数据', '岗位看板会在采集器读取招聘渠道或你手动录入后出现。', 'i-briefcase')}
          </div>
        </div>
      </div>

      <div class="col" style="gap:var(--sp-5)">
        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-shield')} 数据层健康</div>
            <span class="badge ${state.loadErrors.length ? 'badge-warn' : 'badge-ok'}" style="margin-left:auto">
              ${state.loadErrors.length ? '部分缺失' : '正常'}</span></div>
          <div class="panel-body">
            <dl class="kv">
              <dt>最近采集</dt><dd>${esc(m.lastRunAt ? fmtDate(m.lastRunAt, 'datetime') : '—')}</dd>
              <dt>数据新鲜度</dt><dd>${esc(m.lastRunAt ? relTime(m.lastRunAt) : '—')}</dd>
              <dt>采集渠道</dt><dd>${m.channelsOk != null ? `${m.channelsOk} / ${m.channelsTotal} 成功` : '—'}</dd>
              <dt>本次新增</dt><dd>${m.newItems != null ? `${m.newItems} 条` : '—'}</dd>
              <dt>去重后总量</dt><dd>${state.items.length} 条</dd>
              <dt>采集耗时</dt><dd>${m.durationSec != null ? `${m.durationSec}s` : '—'}</dd>
              <dt>缺来源链接</dt><dd>${m.health && m.health.itemsMissingUrl != null ? `${m.health.itemsMissingUrl} 条` : '—'}</dd>
              <dt>缺摘要</dt><dd>${m.health && m.health.emptySummaryItems != null ? `${m.health.emptySummaryItems} 条` : '—'}</dd>
              <dt>下次运行</dt><dd>${esc(m.schedule && m.schedule.nextRunAt ? fmtDate(m.schedule.nextRunAt, 'datetime') : '每日 18:00')}</dd>
              <dt>时区</dt><dd>${esc((m.schedule && m.schedule.timezone) || 'Asia/Shanghai')}</dd>
            </dl>
            ${staleWarning(m)}
            ${state.loadErrors.length ? `<div style="margin-top:var(--sp-3);padding:var(--sp-2) var(--sp-3);border-radius:var(--r-sm);background:color-mix(in oklab,var(--warn) 12%,transparent);font-size:var(--fs-3xs);color:var(--warn)">
              ${state.loadErrors.slice(0, 4).map((e) => `${esc(e.file)} — ${esc(e.error)}`).join('<br>')}
              ${state.loadErrors.length > 4 ? `<br>…另外 ${state.loadErrors.length - 4} 个` : ''}</div>` : ''}
          </div>
        </div>

        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-grid')} 分类分布</div>
            <span class="result-line" style="margin-left:auto">共 ${state.items.length} 条</span></div>
          <div class="panel-body">
            <!-- This panel is about category DISTRIBUTION. It previously also showed
                 a ring chart of learning progress, whose centre read "0%" (nothing
                 marked mastered yet) under a heading about categories - misleading,
                 and it squeezed the legend into a narrow column. The legend now
                 gets the full width and lists every non-empty category. -->
            <div class="legend legend-block">
              ${(() => {
                const rows = CATEGORIES.filter((c) => catCounts.get(c.id));
                if (!rows.length) return '<span class="legend-item">暂无数据</span>';
                const max = Math.max(...rows.map((c) => catCounts.get(c.id)));
                return rows.map((c) => {
                  const n = catCounts.get(c.id);
                  const pct = Math.round((n / max) * 100);
                  return `<div class="legend-item" data-cat="${c.id}">
                    <span class="legend-swatch" style="background:${c.color}"></span>
                    <span class="legend-name truncate">${esc(c.zh)}</span>
                    <span class="legend-bar"><i style="width:${pct}%;background:${c.color}"></i></span>
                    <span class="lv">${n}</span>
                  </div>`;
                }).join('');
              })()}
            </div>
            <button class="btn btn-sm" style="width:100%;margin-top:var(--sp-4)" data-route="#/categories">查看全部分类</button>
          </div>
        </div>

        ${state.formulas.length ? `<div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-sigma')} 公式速览</div>
            <button class="btn btn-sm btn-ghost" style="margin-left:auto" data-route="#/formulas">全部 ${state.formulas.length}</button></div>
          <div class="panel-body" style="padding:0">
            <div class="mini-list">
              ${state.formulas.slice(0, 5).map((f) => `
                <button class="mini-item" style="width:100%;text-align:left" data-route="#/formulas?id=${encodeURIComponent(f.id || '')}" data-cat="${esc(f.category || 'paper')}">
                  <span class="dot"></span><span class="t clamp-2">${esc(f.name || f.title || '未命名公式')}</span>
                  <span class="n">${esc(f.category ? (CAT_BY_ID[f.category] ? CAT_BY_ID[f.category].zh : f.category) : '')}</span>
                </button>`).join('')}
            </div>
          </div>
        </div>` : ''}

        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-flask')} 每日流程</div></div>
          <div class="panel-body">
            <ol style="display:flex;flex-direction:column;gap:var(--sp-3);padding-left:var(--sp-5);list-style:decimal">
              ${[['18:00 触发', 'Windows 任务计划程序调用 run-daily.ps1'],
                 ['并行采集', 'arXiv / HF / GitHub / 招聘官网 / 社区，超时与重试'],
                 ['去重与打分', '规范化 + SimHash + 相关度加权'],
                 ['归纳与自检', 'Agent 生成摘要、公式剖析、易读化解释'],
                 ['原子写入', 'digest/YYYY-MM-DD.json → 索引与状态回写'],
                 ['页面刷新', '工作台读取新数据，无需重新构建']].map(([t, d]) => `
                <li style="font-size:var(--fs-2xs);color:var(--fg-1)"><b style="color:var(--accent);font-weight:680">${esc(t)}</b>
                  <div class="text-2" style="font-size:var(--fs-3xs)">${esc(d)}</div></li>`).join('')}
            </ol>
            <button class="btn btn-sm" style="width:100%;margin-top:var(--sp-4)" data-route="#/pipeline">运行状态与日志</button>
          </div>
        </div>
      </div>
    </div>`;
  },
  after() { wireSortSelect(); wireItemKeyboard(); },
};

function wireSortSelect() {
  const sel = $('#sort-select');
  if (sel) sel.addEventListener('change', () => { state.sort = sel.value; render(); });
}

/* Cards are role=button: Enter/Space should open them. */
function wireItemKeyboard() {
  $$('.kcard').forEach((n) => {
    n.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openItem(n.dataset.id); }
    });
  });
}

function jobStageCounts() {
  const c = {};
  for (const j of state.jobs) {
    const st = state.user.jobStage[j.id] || 'todo';
    c[st] = (c[st] || 0) + 1;
  }
  return c;
}

const STAGES = {
  todo:   { label: '待投递', color: 'var(--fg-3)' },
  applied:{ label: '已投递', color: 'var(--info)' },
  test:   { label: '笔试中', color: 'var(--warn)' },
  inter:  { label: '面试中', color: 'var(--accent)' },
  offer:  { label: '已拿 Offer', color: 'var(--ok)' },
  closed: { label: '已结束', color: 'var(--err)' },
};

function collectTasks() {
  const out = [];
  for (const t of state.tracks) {
    for (const m of t.modules) {
      for (const k of m.tasks) {
        out.push({ key: `${t.id}:${k.id}`, title: k.title, meta: k.estimateHours ? `${k.estimateHours}h` : (m.week ? `W${m.week}` : ''), cat: 'system', track: t });
      }
    }
  }
  return out.sort((a, b) => (state.user.tasks[a.key] ? 1 : 0) - (state.user.tasks[b.key] ? 1 : 0));
}

/* ============================== DIGEST ================================= */

const DigestView = {
  title: '每日更新流',
  render() {
    const list = filteredItems();
    const catCounts = new Map();
    for (const it of state.items) catCounts.set(it.category, (catCounts.get(it.category) || 0) + 1);

    if (!state.items.length) {
      return `<div class="section-head"><div><h2 class="section-title">每日更新流</h2>
        <p class="section-desc">按日期倒序排列的增量情报时间线。</p></div></div>` +
        emptyState('数据层还是空的', '运行 scripts/collect.py 做一次采集，或等待每天 18:00 的定时任务。', 'i-feed');
    }

    const groups = state.prefs.digestGroup === 'category'
      ? CATEGORIES.filter((c) => list.some((i) => i.category === c.id)).map((c) => ({ day: c.zh, cat: c.id, items: list.filter((i) => i.category === c.id) }))
      : groupByDay(list);

    // Cap the rendered cards per group. Without this the page shipped every
    // matched card (700+ nodes, ~1.7 MB of DOM) which is slow on a phone. The
    // header states how many are shown out of how many, and each group links to
    // the paginated knowledge view for the rest.
    const PER_GROUP = state.perPage && state.perPage > 0 ? Math.min(state.perPage, 40) : 0;
    const clipped = PER_GROUP > 0 && list.length > PER_GROUP;
    const groupsOut = clipped
      ? groups.map((g) => ({ ...g, total: g.items.length, items: g.items.slice(0, PER_GROUP) }))
      : groups.map((g) => ({ ...g, total: g.items.length }));

    return `
    <div class="section-head">
      <div>
        <h2 class="section-title">每日更新流</h2>
        <p class="section-desc">${groups.length} 个${state.prefs.digestGroup === 'category' ? '分类' : '日期'}分组 · 共 ${list.length} 条 · 最相关排在最前</p>
      </div>
      <div class="section-actions">
        <div class="segmented" role="group" aria-label="分组方式">
          <button data-act="digest-group" data-group="day" class="${state.prefs.digestGroup === 'day' ? 'is-on' : ''}">按日期</button>
          <button data-act="digest-group" data-group="category" class="${state.prefs.digestGroup === 'category' ? 'is-on' : ''}">按分类</button>
        </div>
      </div>
    </div>

    ${filterBar({ sorts: [['relevance', '相关度优先'], ['newest', '时间最新'], ['oldest', '时间最早'], ['title', '标题排序']], counts: catCounts })}

    ${dailySummaryHtml()}

    ${groupsOut.map((g) => `
      <section class="digest-day">
        <div class="digest-day-head">
          <div class="digest-date">${state.prefs.digestGroup === 'category' && g.cat ? `<span data-cat="${g.cat}">${esc(g.day)}</span>` : esc(g.day)}
            <small>${state.prefs.digestGroup === 'category'
              ? `${g.items.length}${g.total > g.items.length ? ' / ' + g.total : ''} 条`
              : `${esc(weekdayZh(g.day))} · ${g.items.length}${g.total > g.items.length ? ' / ' + g.total : ''} 条`}</small></div>
          <div style="margin-left:auto" class="row">
            ${progressBar((g.items.filter((i) => statusOf(i.id) === 'done').length / g.items.length) * 100, g.cat || null)}
            <span class="result-line">${g.items.filter((i) => statusOf(i.id) === 'done').length}/${g.items.length}</span>
          </div>
        </div>
        <div class="digest-thread">
          ${g.items.map((it, i) => `<div class="digest-node" data-cat="${it.category}">${knowledgeCard(it, { delay: Math.min(i * 20, 240) })}</div>`).join('')}
        </div>
        ${g.total > g.items.length ? `<div class="row" style="justify-content:center;margin:var(--sp-3) 0 var(--sp-5)">
          <button class="btn btn-sm btn-ghost" ${g.cat ? `data-route="#/knowledge?cat=${encodeURIComponent(g.cat)}"` : ''}>${icon('i-chevron')} 查看该组全部 ${g.total} 条</button>
        </div>` : ''}
      </section>`).join('')}

    ${clipped ? `<div class="result-line" style="justify-content:center;gap:var(--sp-3);margin-top:var(--sp-5)">
      <span>每日更新流每组最多显示 ${PER_GROUP} 条，避免手机上渲染上千个卡片</span>
      <button class="btn btn-sm" data-act="set-perpage" data-value="120">每组显示 120 条</button>
      <button class="btn btn-sm btn-ghost" data-act="set-perpage" data-value="0">不限（可能较慢）</button>
    </div>` : ''}`;
  },
  after() { wireSortSelect(); wireItemKeyboard(); },
};

/* ============================ CATEGORIES =============================== */

const CategoriesView = {
  title: '知识分类',
  render() {
    const counts = new Map();
    const doneCounts = new Map();
    for (const it of state.items) {
      counts.set(it.category, (counts.get(it.category) || 0) + 1);
      if (statusOf(it.id) === 'done') doneCounts.set(it.category, (doneCounts.get(it.category) || 0) + 1);
    }
    const tax = state.taxonomy && state.taxonomy.categories ? state.taxonomy.categories : [];
    const taxOf = (id) => tax.find((t) => t.id === id || (t.nameEn || '').toLowerCase() === id);

    return `
    <div class="section-head">
      <div><h2 class="section-title">知识分类体系</h2>
      <p class="section-desc">每个分类都有明确的采集目标、去重规则与更新节奏。分类是从「数据层契约」里读取的，扩展分类不需要改前端。</p></div>
      <div class="section-actions"><button class="btn btn-sm" data-route="#/knowledge">${icon('i-layers')} 浏览全部卡片</button></div>
    </div>

    <div class="grid grid-3">
      ${CATEGORIES.map((c, i) => {
        const n = counts.get(c.id) || 0;
        const d = doneCounts.get(c.id) || 0;
        const t = taxOf(c.id);
        return `
        <article class="card card-hover cat-tile" data-cat="${c.id}" data-route="#/knowledge?cat=${c.id}"
          style="animation:card-in var(--t-slow) var(--ease-out) both;animation-delay:${i * 30}ms">
          <div class="cat-tile-head">
            <span class="cat-tile-icon">${icon(c.icon)}</span>
            <div style="min-width:0">
              <div class="cat-tile-name">${esc(c.zh)}</div>
              <div class="cat-tile-en">${esc(c.en)}</div>
            </div>
          </div>
          <p class="cat-tile-desc">${esc((t && t.desc) || c.desc)}</p>
          ${t && t.goal ? `<div class="kcard-why" style="margin-top:2px"><b>采集目标 · </b>${esc(t.goal)}</div>` : ''}
          <div class="cat-tile-foot">
            <span class="cat-tile-num">${n}<small>条</small></span>
            <div style="flex:1 1 auto;min-width:0">
              ${progressBar(n ? (d / n) * 100 : 0, c.id)}
              <div class="result-line" style="margin-top:4px">已掌握 ${d} / ${n}</div>
            </div>
          </div>
          ${t && t.cadence ? `<div class="eyebrow" style="position:relative;z-index:1">更新节奏 · ${esc(t.cadence)}</div>` : ''}
        </article>`;
      }).join('')}
    </div>

    <div class="rule"></div>
    <div class="grid grid-2">
      <div class="panel">
        <div class="panel-head"><div class="panel-title">${icon('i-database')} 采集渠道与优先级</div></div>
        <div class="panel-body flush">
          <div class="tbl-wrap" style="border:none">
            <table class="tbl">
              <thead><tr><th>渠道</th><th>优先级</th><th class="num">已入库</th><th>登录</th></tr></thead>
              <tbody>
                ${allChannels().slice(0, 20).map(([ch, n]) => {
                  const meta = channelMeta(ch);
                  return `<tr>
                    <td><span style="font-weight:600;color:var(--fg-0)">${esc(meta.zh)}</span>
                      <div class="text-3" style="font-size:var(--fs-3xs)">${esc(meta.en)}</div></td>
                    <td><span class="badge ${meta.p === 'P0' ? 'badge-ok' : meta.p === 'P1' ? 'badge-info' : 'badge-mute'}">${esc(meta.p)}</span></td>
                    <td class="num">${n}</td>
                    <td>${meta.login ? '<span class="badge badge-warn">需登录</span>' : '<span class="badge badge-mute">公开</span>'}</td>
                  </tr>`;
                }).join('') || '<tr><td colspan="4" class="text-3">暂无渠道数据</td></tr>'}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head"><div class="panel-title">${icon('i-list')} 采集与更新规则</div></div>
        <div class="panel-body">
          <div class="prose" style="font-size:var(--fs-2xs)">
            <h3 style="margin-top:0">去重规则</h3>
            <ul>
              <li><strong>ID 级</strong>：<code>sha1(source + externalId)</code> 作为稳定主键。</li>
              <li><strong>URL 级</strong>：剥离 <code>utm_*</code>、<code>ref</code>、<code>spm</code> 等追踪参数后归一化。</li>
              <li><strong>标题级</strong>：去空白/标点/大小写后比较；arXiv 的 v1/v2 视为同一条并保留最新版本。</li>
              <li><strong>近重复</strong>：SimHash 64 位，汉明距离 ≤ 3 判为重复，合并来源而非丢弃。</li>
            </ul>
            <h3>更新规则</h3>
            <ul>
              <li>首次出现 → 新建卡片，写入 <code>firstSeen</code>。</li>
              <li>已存在且内容哈希变化 → 更新摘要与要点，保留你的收藏/进度状态。</li>
              <li>已存在且内容未变 → 仅更新 <code>lastSeen</code>，不重复展示。</li>
              <li>超过 90 天未再次命中且未被收藏 → 归档到 <code>archive/</code>，不占用首屏。</li>
            </ul>
          </div>
        </div>
      </div>
    </div>`;
  },
  after() {},
};

/* ============================= KNOWLEDGE =============================== */

const KnowledgeView = {
  title: '知识卡片',
  render(params) {
    if (params.cat) { state.filters.cat.clear(); state.filters.cat.add(params.cat); }
    if (params.tag) { state.filters.tag.clear(); state.filters.tag.add(params.tag); }
    // The page comes from the URL so pagination survives a reload and the
    // browser back button behaves the way a reader expects.
    if (params.page) state.page = Math.max(1, Number(params.page) || 1);
    else if (!params.cat && !params.tag) state.page = 1;
    const list = filteredItems();
    const catCounts = new Map();
    for (const it of state.items) catCounts.set(it.category, (catCounts.get(it.category) || 0) + 1);
    const header = params.cat && CAT_BY_ID[params.cat]
      ? `<div class="section-head" data-cat="${params.cat}">
           <div><h2 class="section-title">${esc(CAT_BY_ID[params.cat].zh)}</h2>
           <p class="section-desc">${esc(CAT_BY_ID[params.cat].desc)}</p></div>
           <div class="section-actions"><button class="btn btn-sm btn-ghost" data-route="#/knowledge">${icon('i-x')} 返回全部</button></div>
         </div>`
      : `<div class="section-head"><div><h2 class="section-title">知识卡片</h2>
           <p class="section-desc">按相关度、时效与来源质量排序；支持分类、来源、标签与阅读状态多维筛选。</p></div></div>`;

    return header + filterBar({
      sorts: [['relevance', '相关度优先'], ['newest', '最新优先'], ['oldest', '最早优先'], ['title', '标题排序'], ['difficulty', '难度排序']],
      counts: catCounts,
      tags: allTags(),
    }) + renderCards(list);
  },
  after() { wireSortSelect(); wireItemKeyboard(); },
};

/* ===== views2.part.js — 2195 lines ===== */

/* ============================================================================
 * Future · 求职学习工作台 — views2.js (part 3)
 * 公式剖析 · 题库定位 · 仓库与课程 · 岗位看板 · 技能矩阵 · 学习路线 ·
 * 进度统计 · 收藏夹 · 采集运行 · 详情抽屉 · 启动引导
 * ========================================================================= */

/* ============================== FORMULAS =============================== */

const FORMULA_SEED = [
  {
    id: 'f-attention', name: '缩放点积注意力 (Scaled Dot-Product Attention)', category: 'foundation', glyph: 'A',
    tags: ['transformer', 'attention', 'mha'],
    latex: 'Attention(Q,K,V) = softmax( Q Kᵀ / √d_k ) V',
    html: `<var>Attention</var>(<var>Q</var>,<var>K</var>,<var>V</var>) =
      softmax<span style="font-size:1.35em">(</span>
      <span class="frac"><span><var>Q</var><var>K</var><sup>⊤</sup></span><span>√<var>d</var><sub>k</sub></span></span>
      <span style="font-size:1.35em">)</span><var>V</var>`,
    symbols: [
      ['Q ∈ ℝ^{n×d_k}', '查询矩阵：n 个 token 各自「想找什么」'],
      ['K ∈ ℝ^{m×d_k}', '键矩阵：m 个位置「能提供什么」'],
      ['V ∈ ℝ^{m×d_v}', '值矩阵：真正被加权求和的内容'],
      ['√d_k', '缩放因子，防止点积随维度增大而方差爆炸、softmax 进入饱和区'],
    ],
    derivation: [
      '假设 Q、K 各维独立、均值 0、方差 1，则点积 q·k 的方差为 d_k，量级随维度线性增长。',
      '把 logits 除以 √d_k，方差回到 1 量级，softmax 的梯度不会因饱和而消失。',
      '对每一行做 softmax 得到行随机矩阵，再右乘 V 得到上下文向量。',
      '多头：把 d_model 拆成 h 份并行做上式，再拼接并过 W^O —— 让不同子空间学不同的对齐关系。',
    ],
    analogy: '像查字典：Q 是你要查的词，K 是每个词条的索引，点积衡量「匹配度」，softmax 把匹配度变成抽取比例，V 是你真正抄下来的释义。除以 √d_k 相当于把音量调到合适档位——太大会削波（饱和），太小听不见（梯度平坦）。',
    code: `import math, torch, torch.nn as nn

class MHA(nn.Module):
    def __init__(self, d_model=512, n_head=8):
        super().__init__()
        assert d_model % n_head == 0
        self.h, self.dk = n_head, d_model // n_head
        self.qkv = nn.Linear(d_model, 3 * d_model)
        self.proj = nn.Linear(d_model, d_model)

    def forward(self, x, causal=True):
        B, T, C = x.shape
        q, k, v = self.qkv(x).chunk(3, dim=-1)
        # (B, h, T, dk)
        q, k, v = (t.view(B, T, self.h, self.dk).transpose(1, 2) for t in (q, k, v))
        att = q @ k.transpose(-2, -1) / math.sqrt(self.dk)
        if causal:
            mask = torch.triu(torch.ones(T, T, dtype=torch.bool, device=x.device), 1)
            att = att.masked_fill(mask, float("-inf"))
        att = att.softmax(-1)
        out = (att @ v).transpose(1, 2).reshape(B, T, C)
        return self.proj(out)`,
    pitfalls: [
      '忘了 mask 要在 softmax 之前使用 -inf，而不是置 0。',
      '缩放用 √d_k 而不是 √d_model；d_k = d_model / h。',
      'softmax 前若不减最大值，fp16 下容易溢出（面试常问「数值稳定」）。',
    ],
    sources: [{ title: 'Attention Is All You Need', url: 'https://arxiv.org/abs/1706.03762' }],
  },
  {
    id: 'f-dpo', name: 'DPO 直接偏好优化损失', category: 'posttraining', glyph: 'D',
    tags: ['dpo', 'alignment', 'rlhf'],
    html: `<var>L</var><sub>DPO</sub> = −𝔼<sub>(x, y<sub>w</sub>, y<sub>l</sub>)</sub>
      log σ<span style="font-size:1.35em">(</span><var>β</var> log
      <span class="frac"><span><var>π</var><sub>θ</sub>(<var>y</var><sub>w</sub>|<var>x</var>)</span><span><var>π</var><sub>ref</sub>(<var>y</var><sub>w</sub>|<var>x</var>)</span></span>
      − <var>β</var> log
      <span class="frac"><span><var>π</var><sub>θ</sub>(<var>y</var><sub>l</sub>|<var>x</var>)</span><span><var>π</var><sub>ref</sub>(<var>y</var><sub>l</sub>|<var>x</var>)</span></span>
      <span style="font-size:1.35em">)</span>`,
    symbols: [
      ['π_θ', '当前策略（正在训练的语言模型）'],
      ['π_ref', '参考策略（SFT 模型，冻结）'],
      ['y_w / y_l', '偏好数据中的 chosen / rejected 回答'],
      ['β', 'KL 约束强度：越大越贴合参考模型，越小越敢优化'],
    ],
    derivation: [
      '从带 KL 约束的 RLHF 目标出发：max_π E[r(x,y)] − β·KL(π ‖ π_ref)。',
      '该目标的最优解有闭式形式：π*(y|x) ∝ π_ref(y|x)·exp(r(x,y)/β)。',
      '反解得 r(x,y) = β·log(π*(y|x)/π_ref(y|x)) + β·log Z(x)，而配分项 Z(x) 与 y 无关，在 Bradley-Terry 成对比较中会抵消。',
      '把隐式奖励代回偏好似然，即得上式——不再需要单独训练奖励模型，也不需要在线采样。',
    ],
    analogy: '像老师批改作文：参考模型（π_ref）是学生的原有水平，DPO 不直接给分数，而是"相较原来的你，这篇进步了多少"——chosen 进步幅度大于 rejected 就增大它的概率。β 决定你多信任老师的评分标准：β 大则保守，只敢小幅调整。',
    code: `import torch.nn.functional as F

def dpo_loss(policy_chosen_logp, policy_rejected_logp,
             ref_chosen_logp, ref_rejected_logp, beta=0.1):
    """所有 logp 都是「整段回答的对数概率之和」。"""
    pi_logratios  = policy_chosen_logp - policy_rejected_logp
    ref_logratios = ref_chosen_logp  - ref_rejected_logp
    logits = beta * (pi_logratios - ref_logratios)
    losses = -F.logsigmoid(logits)
    # 隐式奖励，便于监控：β·(log π_θ − log π_ref)
    chosen_reward   = beta * (policy_chosen_logp   - ref_chosen_logp).detach()
    rejected_reward = beta * (policy_rejected_logp - ref_rejected_logp).detach()
    return losses.mean(), chosen_reward.mean(), rejected_reward.mean()`,
    pitfalls: [
      'logp 必须在 completion 的 token 上求平均或求和，且要屏蔽 prompt 部分。',
      'π_ref 必须真正冻结；忘记 eval() / no_grad 会导致参考模型漂移。',
      'β 与学习率耦合：β 很小的时候学习率要相应调低，否则训练不稳。',
    ],
    sources: [{ title: 'Direct Preference Optimization', url: 'https://arxiv.org/abs/2305.18290' }],
  },
  {
    id: 'f-grpo', name: 'GRPO 组相对优势', category: 'rl', glyph: 'G',
    tags: ['grpo', 'rlhf', 'advantage'],
    html: `<var>A</var><sub>i</sub> =
      <span class="frac"><span><var>r</var><sub>i</sub> − mean(<var>r</var><sub>1..G</sub>)</span><span>std(<var>r</var><sub>1..G</sub>)</span></span>
      &nbsp;&nbsp;·&nbsp;&nbsp;
      <var>J</var> = 𝔼<span style="font-size:1.35em">[</span>
      <span class="frac"><span>1</span><span><var>G</var></span></span> Σ<sub>i</sub> min<span style="font-size:1.35em">(</span>
      <var>ρ</var><sub>i</sub><var>A</var><sub>i</sub>, clip(<var>ρ</var><sub>i</sub>, 1−ε, 1+ε)<var>A</var><sub>i</sub>
      <span style="font-size:1.35em">)</span> <span style="font-size:1.35em">]</span>`,
    symbols: [
      ['G', '同一 prompt 采样出的回答条数（组大小）'],
      ['r_i', '第 i 条回答的奖励（规则校验或奖励模型）'],
      ['A_i', '组内归一化优势，替代 PPO 的 critic'],
      ['ρ_i', '重要性比 π_θ/π_old，用于离线多次更新'],
      ['ε', 'clip 范围，限制单步策略偏移'],
    ],
    derivation: [
      'PPO 需要 value network 估计 baseline，显存与训练成本翻倍。',
      'GRPO 改用「同一问题采样一组回答」的组内均值作为 baseline：A_i = (r_i − mean)/std。',
      'baseline 与 r_i 相关，因此方差不增；同时完全省掉 critic 网络。',
      '配合 clip 的重要性采样目标，可对同一批数据做多轮更新，提升样本效率。',
    ],
    analogy: '同一道题让 G 个同学各写一份，不给绝对分，只看"你比这组的平均水平高多少"。这样不需要一个单独的老师（critic）来预估绝对分数线，成本更低，也天然抑制了奖励量纲带来的抖动。std 归一化相当于把不同题目的难度差异抹平。',
    code: `import torch

def grpo_advantage(rewards: torch.Tensor) -> torch.Tensor:
    """rewards: (G,) 同一 prompt 下 G 条回答的奖励。
    返回组内标准化优势。G=1 时退化为 0，需在采样端保证 G>=4。"""
    mean = rewards.mean()
    std = rewards.std(unbiased=False) + 1e-4   # 防止除零
    return (rewards - mean) / std

def grpo_loss(logp, logp_old, advantages, clip_eps=0.2):
    ratio = torch.exp(logp - logp_old)          # ρ_i
    unclipped = ratio * advantages
    clipped = torch.clamp(ratio, 1 - clip_eps, 1 + clip_eps) * advantages
    return -torch.min(unclipped, clipped).mean()`,
    pitfalls: [
      '组内 std 为 0（所有回答奖励相同）时优势全为 0，该样本对梯度无贡献，需要过滤。',
      '重要性比要用 token 级 logp 之和，注意与 KL 惩罚项的配合。',
      'G 太小时 baseline 噪声大；工程上常见 G = 4~16。',
    ],
    sources: [{ title: 'DeepSeekMath (GRPO)', url: 'https://arxiv.org/abs/2402.03300' }],
  },
  {
    id: 'f-ddpm', name: 'DDPM 简化训练目标', category: 'generative', glyph: 'ε',
    tags: ['diffusion', 'ddpm', 'generative'],
    html: `<var>L</var><sub>simple</sub> = 𝔼<sub><var>t</var>,<var>x</var><sub>0</sub>,<var>ε</var></sub>
      <span style="font-size:1.4em">‖</span>
      <var>ε</var> − <var>ε</var><sub>θ</sub>
      <span style="font-size:1.4em">(</span>√<var>ᾱ</var><sub>t</sub> <var>x</var><sub>0</sub> + √(1−<var>ᾱ</var><sub>t</sub>) <var>ε</var>, <var>t</var><span style="font-size:1.4em">)</span>
      <span style="font-size:1.4em">‖</span><sup>2</sup>`,
    symbols: [
      ['x_0', '干净样本（图像 / 潜变量 / 视频帧）'],
      ['ε ~ N(0, I)', '当步注入的高斯噪声'],
      ['ᾱ_t = Π α_s', '累积保留系数，决定第 t 步保留多少信号'],
      ['ε_θ', '噪声预测网络（通常为 U-Net 或 DiT）'],
    ],
    derivation: [
      '前向过程 q(x_t|x_0) 可重参数化为一步采样：x_t = √ᾱ_t·x_0 + √(1−ᾱ_t)·ε。',
      '对变分下界逐项化简，去掉与 θ 无关的项，剩下的 KL 项在高斯假设下等价于预测噪声的 MSE。',
      '再丢掉随时间变化的时间权重，得到更简单、实际效果更好的 L_simple。',
      '采样时迭代 x_{t−1} = 1/√α_t (x_t − (1−α_t)/√(1−ᾱ_t)·ε_θ(x_t,t)) + σ_t z，即逐步去噪。',
    ],
    analogy: '像把一张照片反复复印到只剩噪点（前向），再训练一个"去噪师傅"看着模糊程度（时间步 t）把噪点擦掉（反向）。训练时不需要真的走完全部 1000 步——用闭式公式直接跳到任意模糊程度，让师傅每次只负责一步，任务简单且可并行。',
    code: `import torch

def q_sample(x0, t, alphas_bar):
    """闭式加噪：一步得到任意时刻的 x_t"""
    a = alphas_bar[t].view(-1, 1, 1, 1)
    eps = torch.randn_like(x0)
    return a.sqrt() * x0 + (1 - a).sqrt() * eps, eps

def train_step(model, x0, alphas_bar):
    t = torch.randint(0, len(alphas_bar), (x0.shape[0],), device=x0.device)
    x_t, eps = q_sample(x0, t, alphas_bar)
    eps_pred = model(x_t, t)                    # 预测注入的噪声
    return torch.nn.functional.mse_loss(eps_pred, eps)`,
    pitfalls: [
      'ᾱ_t 的数值要预先算好并放到正确 device/dtype，fp16 下容易精度不足。',
      '采样步数与训练步数可以不一致（DDIM / 蒸馏加速就是利用这点）。',
      '和 score matching 的联系常被追问：ε_θ ≈ −√(1−ᾱ_t)·∇log p(x_t)。',
    ],
    sources: [{ title: 'Denoising Diffusion Probabilistic Models', url: 'https://arxiv.org/abs/2006.11239' }],
  },
  {
    id: 'f-rope', name: 'RoPE 旋转位置编码', category: 'foundation', glyph: 'R',
    tags: ['rope', 'position', 'llm'],
    html: `<var>f</var>(<var>x</var>, <var>m</var>) =
      <var>R</var><sub>Θ,<var>m</var></sub><var>x</var> &nbsp;&nbsp;⇒&nbsp;&nbsp;
      ⟨<var>f</var>(<var>q</var>,<var>m</var>), <var>f</var>(<var>k</var>,<var>n</var>)⟩ =
      <var>g</var>(<var>q</var>, <var>k</var>, <var>m</var>−<var>n</var>)`,
    symbols: [
      ['R_{Θ,m}', '按位置 m 构造的分块旋转矩阵'],
      ['Θ = {θ_i = 10000^{-2i/d}}', '每个维度对的旋转基频'],
      ['m − n', '注意力只依赖相对距离，内积形式保持不变'],
    ],
    derivation: [
      '把 d 维向量两两分组，每组视为复平面上的一个数。',
      '位置 m 的编码就是把每个复数乘以 e^{i·m·θ_i}，即按不同频率旋转。',
      '两个向量分别旋转后做内积，旋转角相减，结果只依赖 m−n —— 天然编码相对位置。',
      '外推：NTK-aware / YaRN 通过缩放基频 θ 让模型在训练长度之外依然可用。',
    ],
    analogy: '像钟表：每个维度对是一只走速不同的指针，位置就是各指针的角度组合。比较两个位置时，只有"角度差"有意义，因此绝对位置被自动转成相对距离。调整基频相当于换一套齿轮比，让同一只表还能读出更长的时段（长度外推）。',
    code: `import torch

def rope(x, position, base=10000.0):
    """x: (B, T, H, D)，D 为偶数。原地实现省略，便于阅读。"""
    D = x.shape[-1]
    i = torch.arange(0, D, 2, device=x.device, dtype=torch.float32)
    theta = base ** (-i / D)                      # (D/2,)
    ang = position.float().unsqueeze(-1) * theta  # (T, D/2)
    cos, sin = ang.cos(), ang.sin()
    x1, x2 = x[..., 0::2], x[..., 1::2]           # 复数实部/虚部
    return torch.stack([x1 * cos - x2 * sin,
                        x1 * sin + x2 * cos], dim=-1).flatten(-2)`,
    pitfalls: [
      '缓存 KV 时 RoPE 必须按绝对位置施加，不能用相对偏移直接套。',
      'd 必须为偶数；奇数维要补齐或换用 ALiBi。',
      'sin/cos 缓存的 dtype 与精度会影响长上下文表现。',
    ],
    sources: [{ title: 'RoFormer: Enhanced Transformer with Rotary Position Embedding', url: 'https://arxiv.org/abs/2104.09864' }],
  },
  {
    id: 'f-clip', name: 'CLIP 对比损失 (InfoNCE)', category: 'multimodal', glyph: 'C',
    tags: ['clip', 'contrastive', 'multimodal'],
    html: `<var>L</var> = −
      <span class="frac"><span>1</span><span>2<var>N</var></span></span>
      <span style="font-size:1.4em">(</span>
      Σ<sub>i</sub> log
      <span class="frac"><span>exp(<var>s</var><sub>ii</sub>/<var>τ</var>)</span><span>Σ<sub>j</sub> exp(<var>s</var><sub>ij</sub>/<var>τ</var>)</span></span>
      +
      Σ<sub>i</sub> log
      <span class="frac"><span>exp(<var>s</var><sub>ii</sub>/<var>τ</var>)</span><span>Σ<sub>j</sub> exp(<var>s</var><sub>ji</sub>/<var>τ</var>)</span></span>
      <span style="font-size:1.4em">)</span>`,
    symbols: [
      ['s_ij = ⟨I_i, T_j⟩', '第 i 张图与第 j 条文本的归一化相似度'],
      ['τ', '可学习温度，控制分布的锐度'],
      ['N', 'batch 内的图-文对数量，负样本即其余 2N−1 条'],
    ],
    derivation: [
      '对一个 batch 内的 N 对图-文，构造 N×N 的相似度矩阵，对角线为正样本。',
      '按行做 softmax 得到「图 → 文」的检索分布，按列做 softmax 得到「文 → 图」的分布。',
      '两个方向的交叉熵之和即为对称 InfoNCE 损失。',
      '温度 τ 越小，模型越关注最难的负样本，但训练越不稳定；CLIP 把 τ 设为可学习参数。',
    ],
    analogy: '像把 N 个人和 N 把钥匙混在一起，让模型学会"只把自己的钥匙配给自己的锁"。batch 里其他 N−1 把锁都是干扰项（负样本），batch 越大干扰越多，学到的表示越细致——这也解释了 CLIP 依赖超大 batch 的原因。',
    code: `import torch, torch.nn.functional as F

def clip_loss(img_emb, txt_emb, logit_scale):
    """img_emb / txt_emb: (N, D) 已经各自做过线性投影，未归一化。"""
    img = F.normalize(img_emb, dim=-1)
    txt = F.normalize(txt_emb, dim=-1)
    logits = logit_scale.exp() * img @ txt.t()          # (N, N)
    labels = torch.arange(len(img), device=img.device)  # 对角线为正样本
    l_i = F.cross_entropy(logits, labels)                # 图→文
    l_t = F.cross_entropy(logits.t(), labels)            # 文→图
    return (l_i + l_t) / 2`,
    pitfalls: [
      '务必先 L2 归一化，否则相似度尺度失控。',
      'logit_scale 需要 clamp 上限，否则温度塌缩导致 NaN。',
      '跨卡训练时负样本要 all-gather，否则 batch 语义被破坏（常见追问点）。',
    ],
    sources: [{ title: 'CLIP', url: 'https://arxiv.org/abs/2103.00020' }],
  },
];

function formulaList() {
  const base = state.formulas.length ? state.formulas : FORMULA_SEED;
  return base.map((f, i) => normalizeFormula(f, i));
}

function normalizeFormula(f, i) {
  return {
    id: String(f.id || `f-auto-${i}`),
    name: String(f.name || f.title || `公式 ${i + 1}`),
    category: CAT_BY_ID[f.category] ? f.category : mapCatGuess(f.category || f.tags || []),
    glyph: f.glyph || (f.name || 'ƒ').slice(0, 1).toUpperCase(),
    tags: f.tags || [],
    latex: f.latex || '',
    formula: f.formula || '',
    html: f.html || '',
    symbols: (f.symbols || []).map((s) => (Array.isArray(s) ? s : [s.sym || s.symbol || '', s.meaning || s.desc || ''])),
    derivation: f.derivation || f.steps || [],
    analogy: f.analogy || f.intuition || '',
    code: f.code || f.referenceCode || '',
    pitfalls: f.pitfalls || [],
    sources: f.sources || [],
    usedIn: f.usedIn || [],
  };
}

function mapCatGuess(x) {
  const s = Array.isArray(x) ? x.join(' ') : String(x || '');
  if (/diffus|ddpm|flow|gener/.test(s)) return 'generative';
  if (/dpo|sft|rlhf|align|post/.test(s)) return 'posttraining';
  if (/grpo|ppo|rl|advantage/.test(s)) return 'rl';
  if (/clip|multi|vlm|vision/.test(s)) return 'multimodal';
  if (/rope|attention|transformer|found/.test(s)) return 'foundation';
  if (/world|vla|embodied/.test(s)) return 'worldmodel';
  return 'paper';
}

const FormulasView = {
  title: '公式剖析',
  render(params) {
    const list = formulaList();
    const cats = new Map();
    for (const f of list) cats.set(f.category, (cats.get(f.category) || 0) + 1);
    if (params.id) {
      const f = list.find((x) => x.id === params.id);
      if (f) return formulaDetailHtml(f);
    }
    return `
    <div class="section-head">
      <div><h2 class="section-title">公式剖析</h2>
      <p class="section-desc">每个公式都拆成「符号表 → 推导步骤 → 生活类比 → 可运行代码 → 易错点」五层。
      目标不是记住符号，而是能在面试里从第一性原理讲清楚它为什么长这样。</p></div>
    </div>
    <div class="row" style="flex-wrap:wrap;gap:6px;margin-bottom:var(--sp-4)">
      ${CATEGORIES.filter((c) => cats.get(c.id)).map((c) => `
        <button class="chip${state.filters.cat.has(c.id) ? ' is-on' : ''}" data-cat="${c.id}" data-act="toggle-cat">
          <span class="chip-dot"></span>${esc(c.zh)} <span class="tnum" style="opacity:.7">${cats.get(c.id)}</span></button>`).join('')}
    </div>
    <div class="col" style="gap:var(--sp-4)">
      ${list.filter((f) => !state.filters.cat.size || state.filters.cat.has(f.category)).map((f, i) => `
        <div data-cat="${f.category}" style="animation:card-in var(--t-slow) var(--ease-out) both;animation-delay:${i * 40}ms">
          ${formulaDetailHtml(f, i > 1)}
        </div>`).join('')}
    </div>`;
  },
  after() {},
};

function formulaDetailHtml(f, collapsed = false) {
  const bodyId = `fx-${f.id}`;
  // One rendering engine for every formula in the app: prefer real LaTeX
  // (compiled by our own tex()), fall back to hand-written HTML, then to code.
  const mathHtml = f.latex ? tex(f.latex) : (f.html || (f.code ? '' : esc(f.formula || '')));
  const display = mathHtml || f.html || '';
  return `
  <article class="formula" data-cat="${f.category}">
    <div class="formula-head" data-act="toggle-expand" data-target="${bodyId}" role="button" tabindex="0"
      aria-expanded="${!collapsed}" aria-controls="${bodyId}">
      <span class="formula-glyph">${esc(f.glyph)}</span>
      <div class="grow">
        <div class="formula-title">${esc(f.name)}</div>
        <div class="formula-sub">${esc((CAT_BY_ID[f.category] || {}).zh || '')}${f.tags.length ? ' · ' + esc(f.tags.slice(0, 4).join(' / ')) : ''}</div>
      </div>
      <span class="badge badge-mute">${f.derivation.length} 步推导</span>
      ${icon('i-chevrondown', collapsed ? '' : 'is-open')}
    </div>
    <div class="formula-body" id="${bodyId}"${collapsed ? ' hidden' : ''}>
      ${display ? `<div class="math" data-tex="${attr(f.latex || '')}">${display}</div>` : ''}
      ${f.latex ? `<div class="math-source"><span class="eyebrow">LaTeX 源码</span>
        <code>${esc(f.latex)}</code>
        <button class="icon-btn" data-act="copy" data-copy="${attr(f.latex)}" data-copy-msg="LaTeX 已复制" aria-label="复制 LaTeX">${icon('i-copy')}</button>
      </div>` : ''}

      ${f.symbols.length ? `<dl class="sym-table">${f.symbols.map(([s, m]) => `<dt>${esc(s)}</dt><dd>${esc(m)}</dd>`).join('')}</dl>` : ''}

      ${f.derivation.length ? `<div>
        <div class="eyebrow" style="margin-bottom:var(--sp-2)">推导链条</div>
        <div class="derive">${f.derivation.map((d, i) => `<div class="derive-step"><b>${i + 1}</b><span>${esc(d)}</span></div>`).join('')}</div>
      </div>` : ''}

      ${f.analogy ? `<div class="analogy">${icon('i-bulb')}<p><b>生活类比 · </b>${esc(f.analogy)}</p></div>` : ''}

      ${f.code ? `<div class="code-wrap">
        <div class="code-head"><span>PyTorch</span>
          <button class="icon-btn copy" data-act="copy" data-copy="${attr(f.code)}" data-copy-msg="代码已复制" aria-label="复制代码" style="width:22px;height:22px">${icon('i-copy')}</button>
        </div>
        <pre class="code">${highlight(f.code, 'python')}</pre>
      </div>` : ''}

      ${f.pitfalls.length ? `<div>
        <div class="eyebrow" style="margin-bottom:var(--sp-2)">面试易错点</div>
        <ul class="kcard-points">${f.pitfalls.map((p) => `<li><span>${esc(p)}</span></li>`).join('')}</ul>
      </div>` : ''}

      ${f.sources.length ? `<div class="row" style="flex-wrap:wrap;gap:6px">
        ${f.sources.map((s) => `<a class="btn btn-sm btn-ghost" href="${attr(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">
          ${icon('i-external')} ${esc(s.title || hostOf(s.url))}</a>`).join('')}
      </div>` : ''}
    </div>
  </article>`;
}

/* ============================== PROBLEMS =============================== */

/* ======================= INTERVIEW PANEL ================================ */
/**
 * Renders web/data/interview.json (built by scripts/build_interview_index.py).
 *
 * WHY this is its own panel: interview write-ups are the most PERISHABLE content in
 * the workbench - a 2024 面经 is nearly worthless for a 2026 application - and the raw
 * `summary` of a forum post is mostly venting plus a referral code. The reader asked
 * for deeper, better-organised interview material, so this leads with what is still
 * fresh and answers "which company, which round, what did they ask".
 *
 * The extraction is deterministic rules, not an LLM, so it runs every day and every
 * field can be checked against the source title. Degrades to nothing when absent.
 */
function interviewPanel() {
  const d = state.interview;
  if (!d || !d.count) return '';
  const items = Array.isArray(d.items) ? d.items : [];
  const fresh = items.slice(0, 6);
  const chip = (name, n, cat) => `<span class="chip" data-cat="${attr(cat || 'coding')}"
      style="cursor:default">${esc(name)} <span class="tnum" style="opacity:.65">${n}</span></span>`;

  return `
  <div class="panel" style="margin-bottom:var(--sp-5)">
    <div class="panel-head"><div class="panel-title">${icon('i-briefcase')} 面经速览（时效优先）</div>
      <span class="result-line" style="margin-left:auto">${d.count} 条 · 含手撕题 ${d.withCoding} 条</span></div>
    <div class="panel-body">
      <div class="prose" style="font-size:var(--fs-2xs);margin-bottom:var(--sp-3)">
        <p>面经是这套工作台里<strong>时效性最强</strong>的内容，所以按发布时间倒序，并抽取了公司、轮次、结果与考察主题。
        抽取规则是确定性的（<code>scripts/build_interview_index.py</code>，不用模型），可以逐条对照原帖核对。</p>
      </div>

      <div class="grid grid-2" style="gap:var(--sp-4)">
        <div>
          <div class="eyebrow">公司分布（你正在准备哪几家）</div>
          <div class="row" style="flex-wrap:wrap;gap:6px">
            ${(d.companies || []).slice(0, 10).map((c) => chip(c.name, c.count, 'job')).join('') || '<span class="text-3">—</span>'}
          </div>
          <div class="eyebrow" style="margin-top:var(--sp-3)">轮次</div>
          <div class="row" style="flex-wrap:wrap;gap:6px">
            ${(d.rounds || []).map((c) => chip(c.name, c.count, 'coding')).join('') || '<span class="text-3">—</span>'}
          </div>
          <div class="eyebrow" style="margin-top:var(--sp-3)">结果</div>
          <div class="row" style="flex-wrap:wrap;gap:6px">
            ${(d.outcomes || []).map((c) => chip(c.name, c.count, 'job')).join('') || '<span class="text-3">—</span>'}
          </div>
        </div>
        <div>
          <div class="eyebrow">考察主题（决定你该练什么）</div>
          <div class="row" style="flex-wrap:wrap;gap:6px">
            ${(d.topics || []).map((c) => chip(c.name, c.count, 'posttraining')).join('') || '<span class="text-3">—</span>'}
          </div>
        </div>
      </div>

      <div class="eyebrow" style="margin-top:var(--sp-4)">最近的面经</div>
      <ul class="kcard-points" data-cat="coding">
        ${fresh.map((r) => {
          // Skip a chip whose text is already visible in the title: many 面经 titles
          // contain the round ("面经60：江波龙 | 嵌入式软件 | 二面") and the company, so
          // printing them again read as "…| 二面 · 二面 / 通过 · …".
          const inTitle = (s) => s && String(r.title).includes(s);
          const bits = [r.company, r.round, r.outcome].filter((x) => x && !inTitle(x));
          return `<li><span>${r.url
            ? `<a href="${attr(safeUrl(r.url))}" target="_blank" rel="noopener noreferrer">${esc(r.title)}</a>`
            : esc(r.title)}
            <span class="text-3" style="font-size:var(--fs-3xs)">
              ${bits.length ? ` · ${esc(bits.join(' / '))}` : ''}
              ${r.publishedAt ? ` · ${esc(String(r.publishedAt).slice(0, 10))}` : ''}
              ${r.hasCoding ? ' · <b style="color:var(--accent)">含手撕题</b>' : ''}
            </span></span></li>`;
        }).join('') || '<li><span class="text-3">暂无</span></li>'}
      </ul>
      <div class="text-3" style="font-size:var(--fs-3xs)">
        生成时间 ${esc(String(d.generatedAt || '—'))} · 规则抽取，未命中公司/轮次的条目按标题原样列出
      </div>
    </div>
  </div>`;
}

const ProblemsView = {
  title: '题库定位',
  render(params) {
    const all = state.problems;
    if (!all.length) {
      return `<div class="section-head"><div><h2 class="section-title">题库定位</h2>
        <p class="section-desc">手撕题与笔试场景题，按主题与出现频率定位薄弱环节。</p></div></div>` +
        emptyState('还没有题库数据', '题库由 scripts/build_problem_bank.py 生成：合并 CodeTop 真实频度、算法知识库题解与人工题库，并挂载深读解析。', 'i-code');
    }
    if (params.id) {
      const p = all.find((x) => x.id === params.id || x.rawId === params.id);
      if (p) return problemDetailHtml(p);
    }

    // 赛道：model（模型与训练手撕，读者点名的最高优先级视图）/ algorithm /
    // exam。旧链接的 ?kind=exam 兼容映射到 track=exam。
    const track = params.track || (params.kind === 'exam' ? 'exam' : 'model');
    // 编号空间过滤：LeetCode 与卡码网是两个独立的编号空间（见 build_problem_bank.py
    // 的 KAMACODER_RE 段）。放在 URL 里而不是 state.filters，是为了让「分享一条
    // 筛选后的链接」也能带上它，而且与已有的 track= 过滤保持一致的做法。
    const ns = params.ns || 'all';
    const byTrack = all.filter((p) => (p.track || 'algorithm') === track);
    const list = ns === 'all' ? byTrack : byTrack.filter((p) => (p.namespace || 'kb') === ns);
    const nsCounts = { all: byTrack.length, leetcode: 0, kamacoder: 0, kb: 0 };
    for (const p of byTrack) nsCounts[p.namespace || 'kb'] = (nsCounts[p.namespace || 'kb'] || 0) + 1;
    const qs = (over) => {
      const q = { track, ns, ...over };
      return '#/problems?' + Object.entries(q)
        .filter(([, v]) => v && v !== 'all')
        .map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');
    };
    const topicCounts = new Map();
    for (const p of list) for (const t of p.topics) topicCounts.set(t, (topicCounts.get(t) || 0) + 1);
    const filtered = state.filters.tag.size ? list.filter((p) => p.topics.some((t) => state.filters.tag.has(t))) : list;

    // Coverage: mastered (status done) per topic
    const coverage = new Map();
    for (const t of topicCounts.keys()) {
      const ps = list.filter((p) => p.topics.includes(t));
      const done = ps.filter((p) => statusOf(p.id) === 'done').length;
      coverage.set(t, { total: ps.length, done });
    }

    const meta = state.problemBankMeta;
    const solved = list.filter((p) => p.analysisStatus === 'deep').length;
    const TRACK_DEFS = [
      { id: 'model', label: '模型与训练', tip: 'DPO/GRPO/MHSA/Transformer/RoPE 等与模型、训练策略直接相关的手撕题' },
      { id: 'algorithm', label: '算法与数据结构', tip: 'LeetCode / 卡码网风格的手撕算法题' },
      { id: 'exam', label: '笔试场景', tip: '公司笔试真题风格的应用场景题' },
    ];

    return `
    <div class="section-head">
      <div><h2 class="section-title">题库分类定位</h2>
      <p class="section-desc">每题都带「被考频度、公司分布、深度解析（代码 / 图解 / 复杂度 / 易错点）」。
      标记为「已掌握」的题目会自动从待办中淡出。</p></div>
      <div class="section-actions">
        <div class="segmented" role="group" aria-label="赛道">
          ${TRACK_DEFS.map((t) => `<button data-route="${qs({ track: t.id })}" class="${track === t.id ? 'is-on' : ''}" data-tip="${attr(t.tip)}">${t.label} ${all.filter((p) => (p.track || 'algorithm') === t.id).length}</button>`).join('')}
        </div>
        ${track !== 'exam' ? `<div class="segmented" role="group" aria-label="题号来源" style="margin-left:var(--sp-3)">
          <button data-route="${qs({ ns: 'all' })}" class="${ns === 'all' ? 'is-on' : ''}">全部 ${nsCounts.all}</button>
          <button data-route="${qs({ ns: 'leetcode' })}" class="${ns === 'leetcode' ? 'is-on' : ''}">LeetCode ${nsCounts.leetcode}</button>
          <button data-route="${qs({ ns: 'kamacoder' })}" class="${ns === 'kamacoder' ? 'is-on' : ''}" data-tip="代码随想录配套的笔试练习平台，用独立的题号">卡码网 ${nsCounts.kamacoder}</button>
        </div>` : ''}
      </div>
    </div>

    <div class="panel" style="margin-bottom:var(--sp-5)">
      <div class="panel-head"><div class="panel-title">${icon('i-target')} 题库概览</div>
        <span class="result-line" style="margin-left:auto">已完整解析 <b>${solved}</b> / ${list.length} 题</span></div>
      <div class="panel-body">
        <div class="prose" style="font-size:var(--fs-2xs);margin-bottom:var(--sp-3)">
          <p>题库按**赛道**三分：「模型与训练」（DPO/GRPO/MHSA/Transformer/RoPE 等与模型和训练策略直接相关的手撕题，
          默认视图）、「算法与数据结构」（LeetCode/卡码网风格）、「笔试场景」。两类手撕考的东西不同：算法题考编码与复杂度，
          模型手撕考结构理解 + 向量化实现 + **变体横向对比**——模型赛道的深度解析都带「变体实现」和「对比表」两个板块。</p>
          <p>每道题是一个**实体**：题号来自题干/链接，「被考频度 / 公司 / 难度」来自 CodeTop 的真实记录，
          深度解析由每日深读产出（可运行代码 + 图解 + 复杂度 + 易错点）。排序按「解析完整度 → 被考频度」，
          刻意不按发布时间 —— 高频老题与新题对备考等价。题号分**两个编号空间**：<span class="kcard-cat">#102</span> 是
          LeetCode 第 102 题，<span class="kcard-cat">卡码网 102</span> 是代码随想录配套练习平台的第 102 题。</p>
        </div>
        ${meta && meta.companies && meta.companies.length ? `<div class="eyebrow">高频公司（按出现题数）</div>
        <div class="row" style="flex-wrap:wrap;gap:6px;margin-bottom:var(--sp-3)">
          ${meta.companies.slice(0, 12).map((c) => `<span class="chip" style="cursor:default">${esc(c.name)} <span class="tnum" style="opacity:.65">${c.count}</span></span>`).join('')}
        </div>` : ''}
        <div class="eyebrow" style="margin-bottom:6px">解析完整度</div>
        <div class="row" style="flex-wrap:wrap;gap:6px">
          <span class="chip" style="cursor:default">可照着刷 <span class="tnum" style="opacity:.65">${list.filter((p) => p.analysisStatus === 'deep').length}</span></span>
          <span class="chip" style="cursor:default">部分解析 <span class="tnum" style="opacity:.65">${list.filter((p) => p.analysisStatus === 'partial').length}</span></span>
          <span class="chip" style="cursor:default">待深读 <span class="tnum" style="opacity:.65">${list.filter((p) => p.analysisStatus === 'none').length}</span></span>
        </div>
      </div>
    </div>

    ${interviewPanel()}

    <div class="panel" style="margin-bottom:var(--sp-5)">
      <div class="panel-head"><div class="panel-title">${icon('i-target')} 主题热力与掌握度</div>
        <span class="result-line" style="margin-left:auto">点击主题即可筛选</span></div>
      <div class="panel-body">
        <div class="row" style="flex-wrap:wrap;gap:6px">
          ${Array.from(topicCounts.entries()).sort((a, b) => b[1] - a[1]).map(([t, n]) => {
            const cov = coverage.get(t) || { done: 0, total: n };
            const pct = cov.total ? (cov.done / cov.total) * 100 : 0;
            const on = state.filters.tag.has(t);
            return `<button class="chip${on ? ' is-on' : ''}" data-act="toggle-tag" data-tag="${attr(t)}" data-tip="掌握 ${cov.done}/${cov.total}">
              ${esc(t)} <span class="tnum" style="opacity:.65">${n}</span>
              <span style="width:22px">${progressBar(pct)}</span></button>`;
          }).join('')}
        </div>
      </div>
    </div>

    <div class="row" style="justify-content:space-between;margin-bottom:var(--sp-3)">
      <div class="result-line">共 <b>${filtered.length}</b> 题${state.filters.tag.size ? ` · 已按 ${state.filters.tag.size} 个主题筛选` : ''}</div>
      <div class="row">
        <select class="select select-sm" id="p-sort" aria-label="排序">
          <option value="freq">高频优先</option><option value="diff">难度递增</option><option value="topic">按主题</option>
        </select>
      </div>
    </div>

    <div class="grid grid-auto">
      ${filtered.map((p, i) => problemCard(p, i)).join('')}
    </div>`;
  },
  after() {
    const sel = $('#p-sort');
    if (sel) sel.addEventListener('change', () => {
      const grid = $('.grid-auto');
      if (!grid) return;
      const cards = Array.from(grid.children);
      const key = (c) => ({ freq: Number(c.dataset.freq), diff: DIFF_ORDER.indexOf(c.dataset.diff), topic: c.dataset.topic }[sel.value]);
      cards.sort((a, b) => (sel.value === 'freq' ? key(b) - key(a) : String(key(a)).localeCompare(String(key(b)))));
      cards.forEach((c) => grid.append(c));
    });
  },
};

/* 解析完整度的可视标记。三档刻意用不同措辞而不是「好/中/差」：
 * 读者需要知道的是「这题现在能不能直接照着刷」。 */
const STATUS_BADGE = {
  deep: ['badge-ok', '可照着刷'],
  partial: ['badge-warn', '部分解析'],
  none: ['badge-mute', '待深读'],
};

/**
 * 题号徽标。LeetCode 题号写 `#102`，卡码网题号写 `卡码网 102`。
 *
 * 为什么必须分开：卡码网（代码随想录配套的笔试练习平台）用的是独立编号，
 * 它的第 102 题是「沉没孤岛」，LeetCode 第 102 题是「二叉树的层序遍历」。
 * 两者曾经共用 `lc-102` 这个键，于是卡码网题目顶掉了 LeetCode 题的标题 ——
 * 这正是「#102 沉没孤岛」出现在二叉树层序遍历位置上的原因。现在键已经分开
 * （`lc-<n>` / `km-<n>`），徽标也必须分开显示，否则读者会以为这是同一道题。
 */
function numBadge(p) {
  if (p.namespace === 'kamacoder' && p.kbNumber) {
    return `<span class="kcard-cat" data-tip="卡码网题号（与 LeetCode 题号是两个独立编号空间）">卡码网 ${p.kbNumber}</span>`;
  }
  if (p.number) {
    return `<span class="kcard-cat" data-tip="LeetCode 题号">#${p.number}</span>`;
  }
  return '';
}

function problemCard(p, i = 0) {
  const st = statusOf(p.id);
  const [badgeCls, badgeText] = STATUS_BADGE[p.analysisStatus] || STATUS_BADGE.none;
  return `
  <article class="card card-pad card-hover" data-cat="coding" style="animation:card-in var(--t-slow) var(--ease-out) both;animation-delay:${i * 18}ms"
    data-freq="${p.frequencyRaw}" data-diff="${attr(p.difficulty)}" data-topic="${attr(p.topics[0] || '')}">
    <div class="row" style="align-items:flex-start;gap:var(--sp-2)">
      <span class="kcard-cat">${esc(p.type)}</span>
      ${numBadge(p)}
      <span class="badge ${p.difficulty === 'hard' ? 'badge-err' : p.difficulty === 'medium' ? 'badge-warn' : 'badge-ok'}">${esc(DIFF_ZH[p.difficulty] || p.difficulty)}</span>
      ${p.track === 'model' ? '<span class="badge badge-info" data-tip="模型与训练手撕题，含变体实现与横向对比">模型手撕</span>' : ''}
      <span class="badge ${badgeCls}" data-tip="解析完整度">${badgeText}</span>
      <div class="kcard-actions" style="margin-left:auto">
        <span class="relevance" data-tip="大厂被考频度 ${p.frequencyRaw ? p.frequencyRaw + ' 次' : '未知'}">${'★'.repeat(p.frequency)}${'☆'.repeat(5 - p.frequency)}</span>
        <button class="icon-btn${st === 'done' ? ' is-done' : ''}" data-act="status" data-id="${attr(p.id)}" data-status="done"
          aria-label="标记已掌握" data-tip="标记已掌握">${icon('i-check')}</button>
      </div>
    </div>
    <h3 class="kcard-title" style="margin-top:var(--sp-3)">${esc(p.title)}</h3>
    ${p.statement && p.statement !== p.title ? `<p class="kcard-summary clamp-3">${esc(p.statement)}</p>` : ''}
    ${p.analysis && p.analysis.tldr ? `<p class="kcard-summary clamp-2" style="color:var(--fg-2)">${esc(p.analysis.tldr)}</p>` : ''}
    ${p.companies.length ? `<div class="row" style="flex-wrap:wrap;gap:4px">
      ${p.companies.slice(0, 4).map((c) => `<span class="tag" data-tip="被考 ${c.count} 次">${esc(c.name)} · ${c.count}</span>`).join('')}</div>` : ''}
    <div class="row" style="flex-wrap:wrap;gap:4px;margin-top:auto">
      ${p.topics.slice(0, 5).map((t) => `<span class="tag">${esc(t)}</span>`).join('')}
    </div>
    <div class="kcard-foot">
      <button class="btn btn-sm btn-ghost" data-route="#/problems?id=${encodeURIComponent(p.id)}">${icon('i-play')} 详解与代码</button>
      ${p.sources && p.sources[0] ? `<a class="kcard-src" href="${attr(safeUrl(p.sources[0].url))}" target="_blank" rel="noopener noreferrer" style="margin-left:auto">
        ${icon('i-external', '', 11)} 题源</a>` : ''}
    </div>
  </article>`;
}

/* ---------------------------------------------------------------------------
 * teachingHtml / conceptsHtml
 *
 * The Layer-2 (agent) enrichment carries two narrative payloads that are useful
 * everywhere an item can be read — the item drawer AND the 题库解析页. They used
 * to be rendered inline inside openItem(), which meant the problem page had no
 * way to show them. Extracting them into pure string builders lets both call
 * sites share one implementation, so a fix here lands in both places.
 *
 * Both return '' when there is nothing to show, so callers can interpolate
 * unconditionally. `variant` picks the outer chrome: 'prose' (a section heading,
 * for the item drawer which is a column of prose) or 'panel' (a bordered card,
 * for the 题库解析页 which is a grid of panels).
 * ------------------------------------------------------------------------- */

function teachingHtml(t, variant) {
  if (!t || typeof t !== 'object') return '';
  const body = teachingBody(t);
  if (!body) return '';
  return wrapSection('讲解 · 教学', 'i-bulb', body, variant);
}

function conceptsHtml(concepts, variant) {
  const cards = conceptsBody(concepts);
  if (!cards) return '';
  return wrapSection('概念易读化解析', 'i-book', cards, variant);
}

/** Section chrome: prose heading (drawer) vs panel card (problem page). */
function wrapSection(title, ic, body, variant) {
  if (variant === 'panel') {
    return '<div class="panel"><div class="panel-head"><div class="panel-title">'
      + icon(ic) + ' ' + title + '</div></div><div class="panel-body">' + body + '</div></div>';
  }
  return '<div class="prose"><h2>' + title + '</h2>' + body + '</div>';
}

function teachingBody(t) {
  const blocks = [];
  const prog = Array.isArray(t.progressive) ? t.progressive.filter((p) => p && p.text) : [];
  if (prog.length) {
    blocks.push('<div class="eyebrow">由浅入深</div><ol class="teach-prog">'
      + prog.map((p) => '<li><span class="teach-level">' + esc(p.level || '') + '</span>'
        + '<span>' + esc(p.text) + '</span></li>').join('') + '</ol>');
  }
  const soc = Array.isArray(t.socratic) ? t.socratic.filter((s) => s && s.q) : [];
  if (soc.length) {
    blocks.push('<div class="eyebrow" style="margin-top:var(--sp-3)">追问式理解</div>'
      + soc.map((s) => '<div class="teach-qa"><p class="teach-q">' + esc(s.q) + '</p>'
        + (s.a ? '<p class="teach-a">' + esc(s.a) + '</p>' : '') + '</div>').join(''));
  }
  const row = (label, text) => (text
    ? '<p class="teach-row"><b>' + label + '</b>' + esc(text) + '</p>' : '');
  const core = row('机制 · ', t.mechanism) + row('适用边界 · ', t.boundary)
    + row('类比的失效点 · ', t.analogyBoundary) + row('我的分析 · ', t.ownAnalysis)
    + row('面试怎么答 · ', t.interviewAnswer);
  if (core) blocks.push('<div style="margin-top:var(--sp-3)">' + core + '</div>');
  if (Array.isArray(t.misconceptions) && t.misconceptions.length) {
    blocks.push('<div class="eyebrow" style="margin-top:var(--sp-3)">常见误解</div>'
      + '<ul class="teach-mis">' + t.misconceptions.map((m) => '<li>' + esc(m) + '</li>').join('') + '</ul>');
  }
  if (Array.isArray(t.officialNotes) && t.officialNotes.length) {
    blocks.push('<div class="eyebrow" style="margin-top:var(--sp-3)">官方 / 权威口径</div>'
      + t.officialNotes.map((o) => '<div class="teach-official">' + esc(o.position || '')
        + (o.source ? ' <span class="text-3">— ' + esc(o.source) + '</span>' : '') + '</div>').join(''));
  }
  const sp = t.studyPath || {};
  const pre = Array.isArray(sp.prerequisites) ? sp.prerequisites : [];
  const nxt = Array.isArray(sp.nextSteps) ? sp.nextSteps : [];
  if (pre.length || nxt.length) {
    blocks.push('<div class="teach-path">'
      + (pre.length ? '<div><span class="text-3">读之前先会：</span>' + esc(pre.join('、')) + '</div>' : '')
      + (nxt.length ? '<div style="margin-top:4px"><span class="text-3">读完该练：</span>' + esc(nxt.join('、')) + '</div>' : '')
      + '</div>');
  }
  if (!blocks.length) return '';
  return '<div class="teach">' + blocks.join('') + '</div>';
}

function conceptsBody(concepts) {
  const list = Array.isArray(concepts) ? concepts.filter((c) => c && (c.name || c.readable)) : [];
  if (!list.length) return '';
  const cards = list.map((c) => {
    const rows = [];
    if (c.readable) rows.push('<p style="font-size:var(--fs-xs);color:var(--fg-1);margin-bottom:var(--sp-2)">' + esc(c.readable) + '</p>');
    if (c.analogy) {
      rows.push('<div class="analogy" style="margin-bottom:var(--sp-2)">' + icon('i-bulb')
        + '<p><b>生活类比 · </b>' + esc(c.analogy)
        + (c.analogyBreaksDown ? '<br><b>类比的失效边界 · </b>' + esc(c.analogyBreaksDown) : '')
        + '</p></div>');
    }
    if (c.mechanism) rows.push('<p style="font-size:var(--fs-2xs);color:var(--fg-2);margin-bottom:var(--sp-2)"><b style="color:var(--fg-1)">机制 · </b>' + esc(c.mechanism) + '</p>');
    if (c.visual) {
      rows.push('<div style="padding:var(--sp-2) var(--sp-3);border-radius:var(--r-sm);background:var(--bg-3);font-size:var(--fs-2xs);color:var(--fg-1);margin-bottom:var(--sp-2)">'
        + icon('i-chart', '', 12) + ' <b>可视化方案 · </b>' + esc(c.visual) + '</div>');
    }
    if (c.prerequisites) rows.push('<div class="text-3" style="font-size:var(--fs-3xs);margin-bottom:4px">前置知识：' + esc(Array.isArray(c.prerequisites) ? c.prerequisites.join('、') : c.prerequisites) + '</div>');
    if (Array.isArray(c.selfTest) && c.selfTest.length) {
      rows.push('<div class="eyebrow" style="margin-top:var(--sp-2)">自测题</div><ol style="list-style:decimal;padding-left:var(--sp-5);font-size:var(--fs-2xs);color:var(--fg-1)">'
        + c.selfTest.map((q) => '<li style="margin-bottom:3px">' + esc(q) + '</li>').join('') + '</ol>');
    }
    return '<div class="formula" style="margin-bottom:var(--sp-3)"><div class="formula-head" style="cursor:default">'
      + '<span class="formula-glyph">' + esc((c.name || '?').slice(0, 1)) + '</span>'
      + '<div class="grow"><div class="formula-title">' + esc(c.name || '概念') + '</div></div></div>'
      + '<div class="formula-body">' + rows.join('') + '</div></div>';
  }).join('');
  return cards;
}

function problemDetailHtml(p) {
  const [badgeCls, badgeText] = STATUS_BADGE[p.analysisStatus] || STATUS_BADGE.none;
  const a = p.analysis || null;
  const cx = p.complexity || {};
  const ap = p.approach || null;
  return `
  <div class="section-head">
    <div style="min-width:0">
      <div class="row" style="gap:6px;margin-bottom:6px"><span class="kcard-cat" data-cat="coding">${esc(p.type)}</span>
        ${numBadge(p)}
        <span class="badge ${p.difficulty === 'hard' ? 'badge-err' : p.difficulty === 'medium' ? 'badge-warn' : 'badge-ok'}">${esc(DIFF_ZH[p.difficulty] || p.difficulty)}</span>
        ${p.track === 'model' ? '<span class="badge badge-info">模型手撕</span>' : ''}
        <span class="badge ${badgeCls}">${badgeText}</span>
        <span class="relevance" data-tip="累计出现 ${p.frequencyRaw} 次">频率 ${'★'.repeat(p.frequency)}</span></div>
      <h2 class="section-title">${esc(p.title)}</h2>
      ${p.companies.length ? `<div class="row" style="flex-wrap:wrap;gap:6px;margin-top:6px">
        ${p.companies.slice(0, 8).map((c) => `<span class="chip" style="cursor:default">${esc(c.name)} <span class="tnum" style="opacity:.65">${c.count} 次</span></span>`).join('')}
        ${p.analysisStatus !== 'deep' ? `<span class="text-3" style="font-size:var(--fs-3xs)">该题尚未产出完整解析，已排入下一轮深读队列</span>` : ''}
      </div>` : ''}
    </div>
    <div class="section-actions">
      <button class="btn btn-sm" data-route="#/problems?track=${p.track || 'algorithm'}${p.namespace === 'kamacoder' ? '&ns=kamacoder' : ''}">${icon('i-x')} 返回列表</button>
      <button class="btn btn-sm btn-primary" data-act="status" data-id="${attr(p.id)}" data-status="done">
        ${icon('i-check')} ${statusOf(p.id) === 'done' ? '已掌握' : '标记已掌握'}</button>
    </div>
  </div>

  <div class="grid grid-dash">
    <div class="col" style="gap:var(--sp-4)">
      ${p.statement ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-list')} 题目描述</div></div>
        <div class="panel-body"><div class="prose">${md(p.statement)}</div></div></div>` : ''}

      ${ap ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-bulb')} 解题思路</div></div>
        <div class="panel-body"><div class="prose">
          <p>${md(String(ap.idea || ''))}</p>
          ${ap.steps && ap.steps.length ? `<ol style="list-style:decimal;padding-left:var(--sp-5)">
            ${ap.steps.map((s) => `<li style="margin-bottom:6px">${esc(s)}</li>`).join('')}</ol>` : ''}
          ${ap.whyItWorks ? `<p><b>为什么对：</b>${md(String(ap.whyItWorks))}</p>` : ''}
        </div>
        ${ap.alternatives && ap.alternatives.length ? `<div class="eyebrow" style="margin-top:var(--sp-3)">其它解法</div>
          <ul class="kcard-points">${ap.alternatives.map((x) => `<li><span><b>${esc(x.name || '')}</b>
            ${x.complexity ? `<span class="text-3"> · ${esc(x.complexity)}</span>` : ''}<br><span class="text-3">${esc(x.when || '')}</span></span></li>`).join('')}</ul>` : ''}
        </div></div>` : ''}

      ${p.solution ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-terminal')} 参考实现（Python）</div>
        <button class="icon-btn copy" style="margin-left:auto" data-act="copy" data-copy="${attr(p.solution)}" data-copy-msg="代码已复制"
          aria-label="复制代码">${icon('i-copy')}</button></div>
        <div class="panel-body flush"><pre class="code" style="padding:var(--sp-4)">${highlight(p.solution, 'python')}</pre></div></div>` : ''}

      ${p.variants && p.variants.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-code')} 变体实现（同机制 · 不同写法）</div></div>
        <div class="panel-body"><div class="col" style="gap:var(--sp-4)">
          ${p.variants.map((v) => `<div>
            <div class="eyebrow" style="margin-bottom:4px">${esc(v.name)}${v.cost ? ` <span class="text-3">· ${esc(v.cost)}</span>` : ''}</div>
            ${v.idea ? `<p class="text-3" style="margin:0 0 6px">${md(v.idea)}</p>` : ''}
            ${v.when ? `<p class="text-3" style="margin:0 0 6px"><b>适用：</b>${esc(v.when)}</p>` : ''}
            ${v.code ? `<div style="position:relative"><button class="icon-btn copy" style="position:absolute;top:8px;right:8px" data-act="copy" data-copy="${attr(v.code)}" data-copy-msg="代码已复制" aria-label="复制代码">${icon('i-copy')}</button>
              <pre class="code" style="max-height:320px;overflow:auto">${highlight(v.code, 'python')}</pre></div>` : ''}
          </div>`).join('')}
        </div></div></div>` : ''}

      ${p.comparison && p.comparison.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-grid')} 横向对比</div></div>
        <div class="panel-body" style="overflow-x:auto">
          <table style="width:100%;border-collapse:collapse;font-size:var(--fs-2xs)">
            ${p.comparison.map((row, ri) => `<tr>${row.map((cell, ci) => ri === 0
              ? `<th style="text-align:left;padding:6px 10px;border-bottom:1px solid var(--line-1);white-space:nowrap">${esc(cell)}</th>`
              : `<td style="padding:6px 10px;border-bottom:1px solid var(--line-1)${ci === 0 ? ';font-weight:600' : ''}">${esc(cell)}</td>`).join('')}</tr>`).join('')}
          </table>
        </div></div>` : ''}

      ${p.answerOutline.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-bulb')} 答题框架</div></div>
        <div class="panel-body"><ol class="prose" style="list-style:decimal;padding-left:var(--sp-5)">
          ${p.answerOutline.map((x) => `<li style="margin-bottom:6px">${esc(x)}</li>`).join('')}</ol></div></div>` : ''}

      ${a && a.teaching ? teachingHtml(a.teaching, 'panel') : ''}
      ${a && a.diagram ? diagramHtml(a.diagram) : ''}
      ${a && a.concepts && a.concepts.length ? conceptsHtml(a.concepts, 'panel') : ''}
    </div>

    <div class="col" style="gap:var(--sp-4)">
      ${(cx.time || cx.space) ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-clock')} 复杂度</div></div>
        <div class="panel-body"><div class="row" style="gap:var(--sp-4)">
          <div><div class="eyebrow">时间</div><div style="font-family:var(--font-mono)">${esc(cx.time || '—')}</div></div>
          <div><div class="eyebrow">空间</div><div style="font-family:var(--font-mono)">${esc(cx.space || '—')}</div></div>
        </div>${cx.why ? `<p class="text-3" style="margin-top:var(--sp-2)">${esc(cx.why)}</p>` : ''}</div></div>` : ''}
      ${p.keyPoints.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-target')} 得分要点</div></div>
        <div class="panel-body"><ul class="kcard-points">${p.keyPoints.map((k) => `<li><span>${esc(k)}</span></li>`).join('')}</ul></div></div>` : ''}
      ${p.pitfalls.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-alert')} 常见踩坑</div></div>
        <div class="panel-body"><ul class="kcard-points" data-cat="coding">${p.pitfalls.map((k) => `<li><span>${esc(k)}</span></li>`).join('')}</ul></div></div>` : ''}
      ${p.edgeCases.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-filter')} 边界用例</div></div>
        <div class="panel-body"><ul class="kcard-points">${p.edgeCases.map((k) => `<li><span>${esc(k)}</span></li>`).join('')}</ul></div></div>` : ''}
      ${p.interviewTips ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-briefcase')} 面试怎么说</div></div>
        <div class="panel-body"><div class="prose">${md(p.interviewTips)}</div></div></div>` : ''}
      ${p.origins.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-link')} 来源渠道</div></div>
        <div class="panel-body"><div class="row" style="flex-wrap:wrap;gap:4px">
          ${p.origins.map((o) => `<span class="tag">${esc(o)}</span>`).join('')}</div></div></div>` : ''}
      ${p.sources.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-link')} 题源与题解</div></div>
        <div class="panel-body"><div class="col" style="gap:6px">
          ${p.sources.slice(0, 8).map((s) => `<a class="btn btn-sm btn-ghost" style="justify-content:flex-start" href="${attr(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">
            ${icon('i-external')} <span class="truncate">${esc(s.title || hostOf(s.url))}</span></a>`).join('')}</div></div></div>` : ''}
    </div>
  </div>`;
}

/* ============================ REPOS & COURSES ========================== */

const ReposView = {
  title: '仓库与课程',
  render(params) {
    const repos = state.repos;
    const courses = state.courses;
    const papers = state.papers || [];
    const tab = params.tab || 'repos';
    if (!repos.length && !courses.length && !papers.length) {
      return `<div class="section-head"><div><h2 class="section-title">仓库与课程</h2>
        <p class="section-desc">固定跟进的仓库、系统课程与必读论文。</p></div></div>` +
        emptyState('还没有学习资源数据', '等待 learning.json 生成，或在其中登记你要跟进的仓库与课程。', 'i-repo');
    }
    const tabs = [['repos', `开源仓库 ${repos.length}`], ['courses', `课程 ${courses.length}`], ['papers', `论文 ${papers.length}`]];
    return `
    <div class="section-head">
      <div><h2 class="section-title">仓库与课程</h2>
      <p class="section-desc">固定资源 + 学习计划 + 检查点。把「收藏」变成「跑通」。</p></div>
    </div>
    <div class="tabs">
      ${tabs.map(([k, label]) => `<button class="tab${tab === k ? ' is-on' : ''}" data-route="#/repos?tab=${k}">${esc(label)}</button>`).join('')}
    </div>
    ${tab === 'repos' ? reposHtml(repos) : tab === 'courses' ? coursesHtml(courses) : papersHtml(papers)}`;
  },
  after() {},
};

function reposHtml(repos) {
  if (!repos.length) return emptyState('暂无仓库数据', '在 learning.json 的 repos 字段登记仓库。', 'i-repo');
  const areas = Array.from(new Set(repos.map((r) => r.area).filter(Boolean)));
  return `
  <div class="row" style="flex-wrap:wrap;gap:6px;margin-bottom:var(--sp-4)">
    ${areas.map((a) => `<span class="tag">${esc(a)} · ${repos.filter((r) => r.area === a).length}</span>`).join('')}
  </div>
  <div class="grid grid-auto">
    ${repos.map((r, i) => `
      <article class="card card-pad card-hover" data-cat="course" style="animation:card-in var(--t-slow) var(--ease-out) both;animation-delay:${i * 16}ms">
        <div class="row" style="align-items:flex-start">
          <span class="kcard-cat">${esc(r.language || 'repo')}</span>
          ${r.stars ? `<span class="tag" style="margin-left:auto">★ ${r.stars >= 1000 ? (r.stars / 1000).toFixed(1) + 'k' : r.stars}</span>` : ''}
        </div>
        <h3 class="kcard-title" style="margin-top:var(--sp-3);font-family:var(--font-mono);font-size:var(--fs-sm)">
          <span class="text-3">${esc(r.owner)}/</span>${esc(r.name)}</h3>
        ${r.why ? `<p class="kcard-summary clamp-3">${esc(r.why)}</p>` : ''}
        ${r.studyPlan.length ? `<div>
          <div class="eyebrow" style="margin-bottom:4px">学习计划</div>
          <ul class="kcard-points">${r.studyPlan.slice(0, 4).map((s) => `<li><span>${esc(s)}</span></li>`).join('')}</ul>
        </div>` : ''}
        ${r.checkpoints.length ? `<div class="row" style="flex-wrap:wrap;gap:4px">
          ${r.checkpoints.slice(0, 3).map((c) => `<span class="tag">${esc(c)}</span>`).join('')}</div>` : ''}
        <div class="kcard-foot">
          <span class="badge ${r.status === 'active' ? 'badge-ok' : 'badge-mute'}">${r.status === 'active' ? '活跃' : '待复核'}</span>
          ${r.lastVerified ? `<span class="text-3" data-tip="最近核验">${esc(fmtDate(r.lastVerified))}</span>` : ''}
          <a class="kcard-src" style="margin-left:auto" href="${attr(safeUrl(r.url))}" target="_blank" rel="noopener noreferrer">
            ${icon('i-external', '', 11)} GitHub</a>
        </div>
      </article>`).join('')}
  </div>`;
}

function coursesHtml(courses) {
  if (!courses.length) return emptyState('暂无课程数据', '在 learning.json 的 courses 字段登记课程。', 'i-book');
  return `<div class="grid grid-auto">
    ${courses.map((c, i) => `
      <article class="card card-pad card-hover" data-cat="system" style="animation:card-in var(--t-slow) var(--ease-out) both;animation-delay:${i * 16}ms">
        <div class="row"><span class="kcard-cat">${esc(c.provider || '课程')}</span>
          ${c.year ? `<span class="tag" style="margin-left:auto">${esc(String(c.year))}</span>` : ''}</div>
        <h3 class="kcard-title" style="margin-top:var(--sp-3)">${esc(c.title)}</h3>
        ${c.why ? `<p class="kcard-summary clamp-3">${esc(c.why)}</p>` : ''}
        <dl class="kv" style="margin-top:var(--sp-2)">
          <dt>时长</dt><dd>${c.hours ? c.hours + ' 小时' : '—'}</dd>
          <dt>难度</dt><dd>${esc({ beginner: '入门', intermediate: '进阶', advanced: '高阶' }[c.level] || c.level)}</dd>
          <dt>语言</dt><dd>${c.language === 'zh' ? '中文' : '英文'}</dd>
          <dt>作业</dt><dd>${c.hasAssignments ? '有' : '无'}</dd>
        </dl>
        <div class="kcard-foot">
          ${c.area ? `<span class="tag">${esc(c.area)}</span>` : ''}
          <a class="kcard-src" style="margin-left:auto" href="${attr(safeUrl(c.url))}" target="_blank" rel="noopener noreferrer">
            ${icon('i-external', '', 11)} 课程主页</a>
        </div>
      </article>`).join('')}</div>`;
}

function papersHtml(papers) {
  if (!papers.length) return emptyState('暂无论文数据', '等待每日采集把 arXiv 结果写入工作台。', 'i-flask');
  const must = papers.filter((p) => p.mustRead);
  const rest = papers.filter((p) => !p.mustRead);
  const row = (p, i) => `
    <div class="card card-pad card-hover" data-cat="paper" style="animation:card-in var(--t-slow) var(--ease-out) both;animation-delay:${i * 14}ms">
      <div class="row" style="align-items:flex-start">
        <span class="kcard-cat">${esc(p.venue || p.area || '论文')}${p.year ? ' ' + p.year : ''}</span>
        ${p.ccf ? `<span class="tag tag-accent" style="margin-left:auto">CCF-${esc(p.ccf)}</span>` : ''}
      </div>
      <h3 class="kcard-title" style="margin-top:var(--sp-3);font-size:var(--fs-sm)">${esc(p.title)}</h3>
      ${p.why ? `<div class="kcard-why"><b>为什么读 · </b>${esc(p.why)}</div>` : ''}
      ${p.keyIdeas.length ? `<ul class="kcard-points">${p.keyIdeas.slice(0, 3).map((k) => `<li><span>${esc(k)}</span></li>`).join('')}</ul>` : ''}
      <div class="kcard-foot">
        ${p.readTime ? `<span class="badge badge-mute">${esc(p.readTime)}</span>` : ''}
        ${p.readingOrder ? `<span class="text-3">阅读顺序 #${p.readingOrder}</span>` : ''}
        <span class="text-3" style="margin-left:auto">${esc(DIFF_ZH[p.difficulty] || '')}</span>
        <a class="kcard-src" href="${attr(safeUrl(p.url))}" target="_blank" rel="noopener noreferrer">${icon('i-external', '', 11)} 原文</a>
      </div>
    </div>`;
  return `
  ${must.length ? `<div class="section-head"><div><h3 class="section-title" style="font-size:var(--fs-lg)">必读奠基</h3>
    <p class="section-desc">按阅读顺序编号，先建立主干再补分支。</p></div></div>
    <div class="grid grid-auto" style="margin-bottom:var(--sp-6)">${must.map(row).join('')}</div>` : ''}
  <div class="section-head"><div><h3 class="section-title" style="font-size:var(--fs-lg)">延伸与前沿</h3></div></div>
  <div class="grid grid-auto">${rest.map(row).join('')}</div>`;
}

/* ================================ JOBS ================================= */

const JobsView = {
  title: '岗位看板',
  render(params) {
    const jobs = state.jobs;
    if (!jobs.length) {
      return `<div class="section-head"><div><h2 class="section-title">岗位看板</h2>
        <p class="section-desc">实时招聘信息、JD 要求与投递节奏。</p></div></div>` +
        emptyState('还没有岗位数据', '运行采集器读取各厂招聘官网，或把 jobs.json 中的 companies 补充完整。', 'i-briefcase',
          `<button class="btn btn-sm" data-route="#/pipeline">查看采集配置</button>`);
    }
    if (params.focus) {
      const j = jobs.find((x) => x.id === params.focus);
      if (j) return jobDetailHtml(j);
    }

    const dirs = new Set();
    for (const j of jobs) for (const d of j.directions) dirs.add(d);
    const cities = new Set();
    for (const j of jobs) for (const c of j.cities) cities.add(c);

    const stages = jobStageCounts();
    const filtered = jobs.filter((j) => {
      if (state.filters.cat.size && !j.directions.some((d) => state.filters.cat.has(d))) return false;
      if (state.filters.q) {
        const hay = [j.company, j.title, j.notes, ...j.directions, ...j.cities, ...j.highlights].join(' ').toLowerCase();
        if (!hay.includes(state.filters.q.toLowerCase())) return false;
      }
      return true;
    }).sort((a, b) => (TIER_ORDER.indexOf(a.tier) - TIER_ORDER.indexOf(b.tier)) || b.relevance - a.relevance);

    return `
    <div class="section-head">
      <div><h2 class="section-title">岗位看板</h2>
      <p class="section-desc">共 ${jobs.length} 个机会 · ${jobs.filter((j) => j.open).length} 个开放中 · 按公司梯队与方向匹配排序。</p></div>
      <div class="section-actions">
        <button class="btn btn-sm btn-ghost" data-act="export">${icon('i-download')} 导出进度</button>
      </div>
    </div>

    <div class="grid grid-4" style="margin-bottom:var(--sp-5)">
      ${Object.entries(STAGES).map(([k, v]) => `
        <div class="card card-pad" style="border-left:3px solid ${v.color}">
          <div class="eyebrow">${esc(v.label)}</div>
          <div class="stat-val" style="font-size:var(--fs-xl);margin-top:4px">${stages[k] || 0}<small>个</small></div>
        </div>`).join('')}
    </div>

    <div class="panel" style="margin-bottom:var(--sp-5)">
      <div class="panel-head"><div class="panel-title">${icon('i-route')} 投递漏斗</div>
        <span class="result-line" style="margin-left:auto">点击卡片可拖拽/切换阶段（使用下方按钮）</span></div>
      <div class="panel-body">
        <div class="kanban" id="kanban">
          ${Object.entries(STAGES).map(([k, v]) => {
            const list = jobs.filter((j) => (state.user.jobStage[j.id] || 'todo') === k);
            return `<div class="kan-col" data-stage="${k}">
              <div class="kan-head"><span style="width:8px;height:8px;border-radius:2px;background:${v.color}"></span>
                <span class="kan-title">${esc(v.label)}</span><span class="kan-count">${list.length}</span></div>
              ${list.map((j) => `
                <div class="card kan-card" data-cat="job" draggable="true" data-job="${attr(j.id)}">
                  <div class="row" style="gap:6px"><span class="tier" data-tier="${attr(j.tier)}">${esc(j.tier)}</span>
                    <span style="font-weight:640;color:var(--fg-0)">${esc(j.company)}</span></div>
                  <div class="text-2" style="margin-top:4px">${esc(j.directions.slice(0, 3).join(' · ') || j.title)}</div>
                  <div class="row" style="margin-top:6px;gap:4px">
                    <button class="btn btn-sm btn-ghost" data-act="open-job" data-id="${attr(j.id)}">详情</button>
                  </div>
                </div>`).join('') || `<div class="text-3" style="font-size:var(--fs-3xs);padding:var(--sp-2)">拖拽卡片到此</div>`}
            </div>`;
          }).join('')}
        </div>
      </div>
    </div>

    <div class="row" style="flex-wrap:wrap;gap:6px;margin-bottom:var(--sp-4)">
      <span class="eyebrow" style="margin-right:4px">方向</span>
      ${Array.from(dirs).map((d) => `<button class="chip${state.filters.cat.has(d) ? ' is-on' : ''}" data-act="toggle-cat" data-cat="${attr(d)}">${esc(dirZh(d))}</button>`).join('')}
      <span class="eyebrow" style="margin:0 4px 0 var(--sp-3)">城市</span>
      ${Array.from(cities).map((c) => `<span class="tag">${esc(c)}</span>`).join('')}
    </div>

    <div class="panel">
      <div class="panel-head"><div class="panel-title">${icon('i-list')} 机会清单</div>
        <span class="result-line" style="margin-left:auto">${filtered.length} / ${jobs.length}</span></div>
      <div class="panel-body flush">
        ${filtered.map((j) => `
          <div class="job-row" data-cat="job">
            <div class="job-co">
              <span class="tier" data-tier="${attr(j.tier)}" data-tip="${esc(tierZh(j.tier))}">${esc(j.tier)}</span>
              <div style="min-width:0">
                <div class="job-co-name truncate">${esc(j.company)}</div>
                <div class="job-co-meta">${esc(j.cities.slice(0, 2).join(' · ') || '城市待定')}</div>
              </div>
            </div>
            <div class="job-role">
              <div class="truncate" style="color:var(--fg-0);font-weight:580">${esc(j.title)}</div>
              <div class="dir truncate" style="font-size:var(--fs-3xs)">${esc(j.directions.slice(0, 4).join(' / ') || j.notes.slice(0, 60))}</div>
            </div>
            <div class="job-pay">${esc(j.pay || '面议')}</div>
            <div class="job-city text-3" style="font-size:var(--fs-3xs)">${j.open ? '开放中' : '已关闭'}${j.deadline ? ` · 截止 ${esc(fmtDate(j.deadline))}` : ''}</div>
            <div class="row" style="gap:4px">
              ${j.applyUrl ? `<a class="icon-btn" href="${attr(j.applyUrl)}" target="_blank" rel="noopener noreferrer" data-tip="投递页">${icon('i-external')}</a>` : ''}
              <button class="icon-btn" data-act="open-job" data-id="${attr(j.id)}" data-tip="详情">${icon('i-chevron')}</button>
            </div>
          </div>`).join('')}
      </div>
    </div>`;
  },
  after() { wireKanban(); },
};

const TIER_ORDER = ['S', 'A', 'B', 'C'];
const tierZh = (t) => ({ S: '一线大厂核心组', A: '一线大厂/明星创业', B: '成长型公司', C: '其他' }[t] || '其他');
const dirZh = (d) => ({
  multimodal: '多模态', 'post-training': '后训练', worldmodel: '世界模型', 'world-model': '世界模型',
  generative: '生成式', rl: '强化学习', agent: 'Agent', infra: '工程/推理', embodied: '具身智能', vision: '视觉', nlp: 'NLP',
}[d] || d);

function wireKanban() {
  const board = $('#kanban');
  if (!board) return;
  let dragging = null;
  board.addEventListener('dragstart', (e) => {
    const card = e.target.closest('[data-job]');
    if (!card) return;
    dragging = card.dataset.job;
    card.classList.add('dragging');
    e.dataTransfer.setData('text/plain', dragging);
    e.dataTransfer.effectAllowed = 'move';
  });
  board.addEventListener('dragend', (e) => {
    const card = e.target.closest('[data-job]');
    if (card) card.classList.remove('dragging');
    $$('.kan-col').forEach((c) => c.classList.remove('drop-target'));
    dragging = null;
  });
  board.addEventListener('dragover', (e) => {
    const col = e.target.closest('.kan-col');
    if (!col) return;
    e.preventDefault();
    $$('.kan-col').forEach((c) => c.classList.toggle('drop-target', c === col));
  });
  board.addEventListener('drop', (e) => {
    const col = e.target.closest('.kan-col');
    if (!col) return;
    e.preventDefault();
    const id = e.dataTransfer.getData('text/plain') || dragging;
    if (!id) return;
    state.user.jobStage[id] = col.dataset.stage;
    saveUser();
    toast(`已移动到「${STAGES[col.dataset.stage].label}」`, 'ok', 1500);
    render();
  });
  board.addEventListener('click', (e) => {
    const card = e.target.closest('[data-job]');
    if (!card || e.target.closest('button')) return;
    openJob(card.dataset.job);
  });
}

function jobDetailHtml(j) {
  const st = state.user.jobStage[j.id] || 'todo';
  return `
  <div class="section-head">
    <div style="min-width:0">
      <div class="row" style="gap:6px;margin-bottom:6px">
        <span class="tier" data-tier="${attr(j.tier)}">${esc(j.tier)}</span>
        <span class="badge ${j.open ? 'badge-ok' : 'badge-mute'}">${j.open ? '开放中' : '已关闭'}</span>
        ${j.confidence ? `<span class="badge badge-mute">可信度 ${esc(j.confidence)}</span>` : ''}
      </div>
      <h2 class="section-title">${esc(j.company)} · ${esc(j.title)}</h2>
      <p class="section-desc">${esc(j.cities.join(' / ') || '城市待定')} · ${esc(j.pay || '薪资面议')}${j.duration ? ' · ' + esc(j.duration) : ''}</p>
    </div>
    <div class="section-actions">
      <button class="btn btn-sm" data-route="#/jobs">${icon('i-x')} 返回</button>
      ${j.applyUrl ? `<a class="btn btn-sm btn-primary" href="${attr(j.applyUrl)}" target="_blank" rel="noopener noreferrer">
        ${icon('i-external')} 打开投递页</a>` : ''}
    </div>
  </div>

  <div class="grid grid-dash">
    <div class="col" style="gap:var(--sp-4)">
      ${j.highlights.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-spark')} 团队与亮点</div></div>
        <div class="panel-body"><ul class="kcard-points">${j.highlights.map((h) => `<li><span>${esc(h)}</span></li>`).join('')}</ul></div></div>` : ''}
      ${j.process.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-route')} 面试流程</div></div>
        <div class="panel-body"><div class="timeline">
          ${j.process.map((s, i) => `<div class="tl-item" data-cat="job">
            <span class="tl-dot"></span>
            <div class="tl-head"><span class="tl-title">${esc(s)}</span><span class="tl-week">第 ${i + 1} 步</span></div>
          </div>`).join('')}
        </div></div></div>` : ''}
      ${j.notes ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-info')} 备注与判断</div></div>
        <div class="panel-body"><div class="prose">${md(j.notes)}</div></div></div>` : ''}
      ${j.sources.length ? `<div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-link')} 信息来源</div></div>
        <div class="panel-body"><div class="col" style="gap:6px">
          ${j.sources.map((s) => `<a class="btn btn-sm btn-ghost" style="justify-content:flex-start" href="${attr(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">
            ${icon('i-external')} <span class="truncate">${esc(s.title || hostOf(s.url))}</span></a>`).join('')}</div></div></div>` : ''}
    </div>
    <div class="col" style="gap:var(--sp-4)">
      <div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-flag')} 投递阶段</div></div>
        <div class="panel-body"><div class="col" style="gap:6px">
          ${Object.entries(STAGES).map(([k, v]) => `
            <button class="btn btn-sm${st === k ? ' btn-primary' : ''}" style="justify-content:flex-start"
              data-act="job-stage" data-id="${attr(j.id)}" data-stage="${k}">
              <span style="width:8px;height:8px;border-radius:2px;background:${st === k ? 'currentColor' : v.color};display:inline-block"></span>
              ${esc(v.label)}</button>`).join('')}
        </div></div></div>
      <div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-target')} 匹配方向</div></div>
        <div class="panel-body">
          <div class="row" style="flex-wrap:wrap;gap:4px">${j.directions.map((d) => `<span class="tag">${esc(dirZh(d))}</span>`).join('') || '<span class="text-3">—</span>'}</div>
          ${j.seasonality ? `<div class="kcard-why" style="margin-top:var(--sp-3)"><b>招聘节奏 · </b>${esc(j.seasonality)}</div>` : ''}
          ${j.conversion ? `<div class="kcard-why" style="margin-top:var(--sp-2)"><b>转正 · </b>${esc(j.conversion)}</div>` : ''}
        </div></div>
    </div>
  </div>`;
}

/* ============================== SKILLS ================================= */

const SkillsView = {
  title: '技能矩阵',
  render() {
    const skills = state.skills;
    if (!skills.length) {
      return `<div class="section-head"><div><h2 class="section-title">技能矩阵</h2>
        <p class="section-desc">岗位要求的技能、重要度与你当前掌握度的差距。</p></div></div>` +
        emptyState('还没有技能数据', '等待 jobs.json 的 skillMatrix 字段。', 'i-target');
    }
    const cats = new Map();
    for (const s of skills) cats.set(s.category, (cats.get(s.category) || 0) + 1);
    const sorted = skills.slice().sort((a, b) => b.importance - a.importance);
    const gapScore = (s) => s.importance * 20 - (state.user.mastery[s.id] || 0) * 20;

    return `
    <div class="section-head">
      <div><h2 class="section-title">技能矩阵</h2>
      <p class="section-desc">按「岗位重要度 × 我的掌握度」排序，先补高重要度、低掌握的缺口。</p></div>
      <div class="section-actions">
        <select class="select select-sm" id="skill-cat" aria-label="技能分类">
          <option value="">全部分类</option>
          ${Array.from(cats.entries()).map(([c, n]) => `<option value="${attr(c)}">${esc(c)} (${n})</option>`).join('')}
        </select>
      </div>
    </div>

    <div class="grid grid-2">
      ${sorted.map((s, i) => {
        const m = state.user.mastery[s.id] || 0;
        const gap = gapScore(s);
        return `
        <article class="card card-pad" data-cat="${gap > 40 ? 'posttraining' : gap > 20 ? 'rl' : 'agent'}"
          style="animation:card-in var(--t-slow) var(--ease-out) both;animation-delay:${Math.min(i * 14, 300)}ms">
          <div class="row" style="align-items:flex-start">
            <div class="grow">
              <h3 class="kcard-title" style="font-size:var(--fs-sm)">${esc(s.skill)}</h3>
              <div class="row" style="gap:6px;margin-top:4px">
                <span class="tag">${esc(s.category)}</span>
                ${s.learnCost ? `<span class="tag">约 ${esc(s.learnCost)}</span>` : ''}
              </div>
            </div>
            <div class="col" style="align-items:flex-end;gap:4px">
              <span class="relevance" data-tip="岗位重要度">${'★'.repeat(s.importance)}${'☆'.repeat(5 - s.importance)}</span>
              <span class="text-3" style="font-size:var(--fs-3xs)">重要度 ${s.importance}/5</span>
            </div>
          </div>

          ${s.evidence ? `<p class="kcard-summary" style="margin-top:var(--sp-3)">${esc(s.evidence)}</p>` : ''}
          ${s.howToProve ? `<div class="kcard-why" style="margin-top:var(--sp-2)"><b>如何证明 · </b>${esc(s.howToProve)}</div>` : ''}

          <div style="margin-top:var(--sp-3)">
            <div class="row" style="justify-content:space-between;margin-bottom:6px">
              <span class="eyebrow">我的掌握度</span>
              <span class="text-3" style="font-size:var(--fs-3xs)">差距 ${Math.max(0, gap)} 分</span>
            </div>
            <div class="row" style="gap:4px">
              ${[1, 2, 3, 4, 5].map((v) => `
                <button class="icon-btn" data-act="mastery" data-id="${attr(s.id)}" data-v="${v}"
                  style="width:28px;height:22px;border-radius:var(--r-xs);background:${v <= m ? 'var(--accent)' : 'var(--bg-4)'};color:${v <= m ? 'var(--accent-fg)' : 'var(--fg-3)'}"
                  aria-label="掌握度 ${v}" data-tip="掌握度 ${v}/5">${v}</button>`).join('')}
            </div>
          </div>

          ${s.demand.length ? `<div class="row" style="flex-wrap:wrap;gap:4px;margin-top:var(--sp-3)">
            <span class="eyebrow">需求公司</span>
            ${s.demand.map((d) => `<span class="tag">${esc(d)}</span>`).join('')}</div>` : ''}
        </article>`;
      }).join('')}
    </div>`;
  },
  after() {
    const sel = $('#skill-cat');
    if (sel) sel.addEventListener('change', () => {
      const cat = sel.value;
      $$('.grid-2 > article').forEach((n) => {
        const tag = n.querySelector('.tag');
        n.classList.toggle('hide', Boolean(cat) && (!tag || tag.textContent.trim() !== cat));
      });
    });
  },
};

/* ============================== ROADMAP ================================ */

const RoadmapView = {
  title: '学习路线',
  render(params) {
    const tracks = state.tracks;
    if (!tracks.length) {
      return `<div class="section-head"><div><h2 class="section-title">系统学习路线</h2>
        <p class="section-desc">按方向拆分的模块化路线，含任务、交付物与验收标准。</p></div></div>` +
        emptyState('还没有路线数据', '等待 learning.json 的 tracks 字段。', 'i-route');
    }
    const tasks = collectTasks();
    const doneCount = tasks.filter((t) => state.user.tasks[t.key]).length;
    const active = params.track ? tracks.find((t) => t.id === params.track) : tracks[0];
    const sys = state.studySystem;
    const prof = (state.learningKb && state.learningKb.profile) || null;

    return `
    <div class="section-head">
      <div><h2 class="section-title">系统学习路线</h2>
      <p class="section-desc">${tracks.length} 条路线 · ${tasks.length} 个任务 · 已完成 <b style="color:var(--accent)">${doneCount}</b>
      个（<span data-task-progress>${doneCount}/${tasks.length}</span>）</p>
      <div style="margin-top:var(--sp-3);max-width:520px">
        <div class="bar bar-lg"><i data-task-bar style="width:${tasks.length ? (doneCount / tasks.length) * 100 : 0}%"></i></div>
      </div>
      </div>
    </div>

    ${prof ? `
    <div class="grid grid-2" style="margin-bottom:var(--sp-5)">
      <div class="panel">
        <div class="panel-head"><div class="panel-title">${icon('i-target')} 你的起点与优先级</div>
          <span class="badge badge-info" style="margin-left:auto">已按你的情况重排</span></div>
        <div class="panel-body">
          <div class="grid grid-2" style="gap:var(--sp-3)">
            ${Object.entries(prof.startingPoint || {}).map(([k, v]) => `
              <div class="card card-pad" data-cat="${k === 'coding' ? 'posttraining' : k === 'research' ? 'agent' : 'system'}" style="padding:var(--sp-3)">
                <div class="eyebrow">${esc({ pytorch: 'PyTorch', research: '科研产出', coding: '刷题', rl: '强化学习' }[k] || k)}</div>
                <div style="font-size:var(--fs-sm);font-weight:640;color:var(--fg-0);margin:4px 0">${esc(v.level)}</div>
                <div class="text-2" style="font-size:var(--fs-3xs)">${esc(v.note)}</div>
              </div>`).join('')}
          </div>
          ${prof.priorityOrder ? `<div class="eyebrow" style="margin:var(--sp-4) 0 6px">为什么这样排序</div>
            <ol style="list-style:decimal;padding-left:var(--sp-5);font-size:var(--fs-2xs);color:var(--fg-1)">
              ${prof.priorityOrder.map((p) => `<li style="margin-bottom:3px">${esc(p)}</li>`).join('')}</ol>` : ''}
        </div>
      </div>

      <div class="panel">
        <div class="panel-head"><div class="panel-title">${icon('i-flask')} ICLR 论文 · 抗追问清单</div>
          <span class="result-line" style="margin-left:auto">${(prof.paperQuestions || []).length} 类</span></div>
        <div class="panel-body">
          ${(prof.paperQuestions || []).length ? `
            <div class="text-2" style="font-size:var(--fs-2xs);margin-bottom:var(--sp-3)">
              你已有一篇 ICLR 多模态分割论文 —— 这是你相对同届最硬的资产，面试里会占掉 30%–50% 的时间。
              所以「把它讲清楚」的优先级高于再读十篇新论文。逐条准备下面的追问：</div>
            <ul class="kcard-points" data-cat="paper">
              ${prof.paperQuestions.map((q) => `<li><span>${esc(q)}</span></li>`).join('')}
            </ul>
            <div class="row" style="margin-top:var(--sp-3);gap:var(--sp-2)">
              <button class="btn btn-sm" data-route="#/roadmap?track=paper">${icon('i-route')} 论文讲述路线</button>
              <button class="btn btn-sm btn-ghost" data-route="#/roadmap?track=coding">${icon('i-code')} 手撕题路线</button>
            </div>
          ` : '<div class="status-line"><span class="warn">尚未生成追问清单</span></div>'}
        </div>
      </div>
    </div>` : ''}

    <div class="tabs">
      ${tracks.map((t) => `<button class="tab${active && t.id === active.id ? ' is-on' : ''}" data-route="#/roadmap?track=${encodeURIComponent(t.id)}">
        ${esc(t.name)}<span class="cnt">${t.modules.length}</span></button>`).join('')}
    </div>

    ${active ? `
    <div class="grid grid-dash">
      <div class="col" style="gap:var(--sp-4)">
        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-route')} ${esc(active.name)}</div>
            <span class="badge badge-info" style="margin-left:auto">${active.weeks} 周 · ${esc({ core: '核心', support: '支撑', advanced: '进阶' }[active.level] || active.level)}</span></div>
          <div class="panel-body">
            ${active.goal ? `<div class="kcard-why" style="margin-bottom:var(--sp-4)"><b>目标 · </b>${esc(active.goal)}</div>` : ''}
            ${active.prerequisites.length ? `<div class="row" style="flex-wrap:wrap;gap:4px;margin-bottom:var(--sp-4)">
              <span class="eyebrow">前置</span>${active.prerequisites.map((p) => `<span class="tag">${esc(p)}</span>`).join('')}</div>` : ''}
            <div class="timeline">
              ${active.modules.map((m) => {
                const mTasks = m.tasks.map((k) => `${active.id}:${k.id}`);
                const mDone = mTasks.filter((k) => state.user.tasks[k]).length;
                const pct = m.tasks.length ? (mDone / m.tasks.length) * 100 : 0;
                const bodyId = `mod-${m.id}`;
                return `
                <div class="tl-item" data-cat="system">
                  <span class="tl-dot${pct === 100 ? ' done' : ''}"></span>
                  <div class="tl-head">
                    <span class="tl-title">${esc(m.title)}</span>
                    ${m.week ? `<span class="tl-week">W${m.week}</span>` : ''}
                    ${m.hours ? `<span class="tl-week">${m.hours}h</span>` : ''}
                    <span class="result-line" style="margin-left:auto">${mDone}/${m.tasks.length}</span>
                  </div>
                  <div style="margin:6px 0 var(--sp-3);max-width:420px">${progressBar(pct)}</div>

                  <div class="module">
                    <div class="module-head" data-act="toggle-expand" data-target="${bodyId}" role="button" tabindex="0" aria-controls="${bodyId}">
                      ${icon('i-chevrondown')}
                      <span class="module-name">任务与交付物</span>
                      <span class="module-meta">${m.tasks.length} 个任务 · ${m.tasks.reduce((a, b) => a + b.estimateHours, 0)}h</span>
                    </div>
                    <div class="module-body" id="${bodyId}">
                      ${m.objectives.length ? `<div class="eyebrow" style="margin-bottom:6px">学习目标</div>
                        <ul class="kcard-points" style="margin-bottom:var(--sp-3)">${m.objectives.map((o) => `<li><span>${esc(o)}</span></li>`).join('')}</ul>` : ''}
                      ${m.concepts.length ? `<div class="row" style="flex-wrap:wrap;gap:4px;margin-bottom:var(--sp-3)">
                        ${m.concepts.map((c) => `<span class="tag">${esc(c)}</span>`).join('')}</div>` : ''}
                      ${m.tasks.map((k) => {
                        const key = `${active.id}:${k.id}`;
                        const on = Boolean(state.user.tasks[key]);
                        return `<div class="task${on ? ' on' : ''}">
                          <button class="task-check${on ? ' on' : ''}" data-act="toggle-task" data-key="${attr(key)}"
                            aria-label="标记完成" aria-pressed="${on}"></button>
                          <div class="task-main">
                            <div class="task-title">${esc(k.title)}</div>
                            ${k.done ? `<div class="task-done">验收：${esc(k.done)}</div>` : ''}
                            ${k.deliverable ? `<div class="task-done">交付：${esc(k.deliverable)}</div>` : ''}
                          </div>
                          <div class="task-badges">
                            ${k.estimateHours ? `<span class="tag">${k.estimateHours}h</span>` : ''}
                            <span class="tag">${esc(TASK_TYPE[k.type] || k.type)}</span>
                          </div>
                        </div>`;
                      }).join('')}
                    </div>
                  </div>
                </div>`;
              }).join('')}
            </div>
          </div>
        </div>
      </div>

      <div class="col" style="gap:var(--sp-4)">
        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-layers')} 全部路线</div></div>
          <div class="panel-body" style="padding:0">
            <div class="mini-list">
              ${tracks.map((t) => {
                const ts = collectTasks().filter((x) => x.track.id === t.id);
                const d = ts.filter((x) => state.user.tasks[x.key]).length;
                return `<button class="mini-item" style="width:100%;text-align:left" data-route="#/roadmap?track=${encodeURIComponent(t.id)}">
                  <span class="dot" data-cat="${d === ts.length && ts.length ? 'agent' : 'system'}"></span>
                  <span class="t">${esc(t.name)}<div class="text-3" style="font-size:var(--fs-3xs)">${t.weeks} 周 · ${ts.length} 任务</div></span>
                  <span class="n">${d}/${ts.length}</span>
                </button>`;
              }).join('')}
            </div>
          </div>
        </div>

        ${sys ? `<div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-clock')} 学习系统</div></div>
          <div class="panel-body">
            ${sys.weeklyRhythm ? `<div class="eyebrow" style="margin-bottom:6px">每周节奏</div>
              <ul class="kcard-points" style="margin-bottom:var(--sp-4)">${sys.weeklyRhythm.map((r) => `<li><span>${esc(r)}</span></li>`).join('')}</ul>` : ''}
            ${sys.spacedRepetition ? `<div class="eyebrow" style="margin-bottom:6px">间隔重复</div>
              <div class="text-2" style="font-size:var(--fs-2xs);margin-bottom:var(--sp-3)">
                间隔 ${(sys.spacedRepetition.intervals || []).join(' / ')} 天${sys.spacedRepetition.rule ? ' · ' + esc(sys.spacedRepetition.rule) : ''}</div>` : ''}
            ${sys.noteTemplate ? `<div class="eyebrow" style="margin-bottom:6px">笔记模板</div>
              <ol style="list-style:decimal;padding-left:var(--sp-5);font-size:var(--fs-2xs);color:var(--fg-1)">
                ${sys.noteTemplate.map((n) => `<li style="margin-bottom:3px">${esc(n)}</li>`).join('')}</ol>` : ''}
            ${sys.antiPatterns ? `<div class="eyebrow" style="margin:var(--sp-4) 0 6px">反模式</div>
              <div class="row" style="flex-wrap:wrap;gap:4px">${sys.antiPatterns.map((a) => `<span class="tag" style="border-color:color-mix(in oklab,var(--err) 40%,transparent);color:var(--err)">${esc(a)}</span>`).join('')}</div>` : ''}
          </div>
        </div>` : ''}

        ${state.milestones && state.milestones.length ? `<div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-flag')} 里程碑</div></div>
          <div class="panel-body" style="padding:0">
            <div class="mini-list">
              ${state.milestones.map((m) => `<div class="mini-item">
                <span class="dot" data-cat="agent"></span>
                <span class="t">${esc(m.title)}<div class="text-3" style="font-size:var(--fs-3xs)">${esc((m.acceptance || []).slice(0, 2).join(' · '))}</div></span>
                <span class="n">${m.week ? 'W' + m.week : ''}</span></div>`).join('')}
            </div>
          </div>
        </div>` : ''}
      </div>
    </div>` : ''}`;
  },
  after() { updateTaskProgress(); },
};

const TASK_TYPE = { paper: '论文', code: '代码', course: '课程', project: '项目', drill: '刷题', study: '学习' };

/* ============================== PROGRESS =============================== */

const ProgressView = {
  title: '进度与统计',
  render() {
    const s = completionStats();
    const byCat = CATEGORIES.map((c) => {
      const list = state.items.filter((i) => i.category === c.id);
      const done = list.filter((i) => statusOf(i.id) === 'done').length;
      const reading = list.filter((i) => statusOf(i.id) === 'reading').length;
      return { c, total: list.length, done, reading, pct: list.length ? (done / list.length) * 100 : 0 };
    }).filter((x) => x.total);
    const bySrc = allChannels().slice(0, 12);
    const days = groupByDay(state.items);
    const tasks = collectTasks();
    const taskDone = tasks.filter((t) => state.user.tasks[t.key]).length;
    const skills = state.skills;
    const skillAvg = skills.length ? skills.reduce((a, b) => a + (state.user.mastery[b.id] || 0), 0) / skills.length : 0;
    const problems = state.problems;
    const probDone = problems.filter((p) => statusOf(p.id) === 'done').length;

    return `
    <div class="section-head"><div><h2 class="section-title">进度与统计</h2>
      <p class="section-desc">所有状态保存在浏览器 localStorage。收藏与掌握度可以写成学习信号，让每日采集向你实际在学的方向倾斜。</p></div>
      <div class="section-actions">
        <button class="btn btn-sm btn-ghost" data-act="export">${icon('i-download')} 导出进度</button>
        <button class="btn btn-sm" data-act="export-feedback" data-tip="写出 web/data/feedback.json：采集器会据此调整类目权重与深读配额">${icon('i-refresh')} 写出学习信号</button>
      </div></div>

    <div class="grid grid-4" style="margin-bottom:var(--sp-6)">
      ${[
        ['知识卡片', s.total, `${s.done} 已掌握`],
        ['刷题进度', problems.length, `${probDone} 已完成`],
        ['学习任务', tasks.length, `${taskDone} 已完成`],
        ['平均掌握度', skills.length ? skillAvg.toFixed(1) : '—', skills.length ? `覆盖 ${skills.length} 项技能` : '暂无技能数据'],
      ].map(([k, v, sub]) => `
        <div class="card card-pad">
          <div class="eyebrow">${esc(k)}</div>
          <div class="stat-val" style="font-size:var(--fs-2xl);margin-top:6px">${esc(String(v))}</div>
          <div class="text-3" style="font-size:var(--fs-3xs)">${esc(sub)}</div>
        </div>`).join('')}
    </div>

    <div class="grid grid-dash">
      <div class="col" style="gap:var(--sp-5)">
        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-grid')} 分类掌握度</div></div>
          <div class="panel-body">
            <div class="col" style="gap:var(--sp-4)">
              ${byCat.map(({ c, total, done, reading, pct }) => `
                <div data-cat="${c.id}">
                  <div class="row" style="justify-content:space-between;margin-bottom:6px">
                    <span style="font-size:var(--fs-xs);font-weight:600;color:var(--fg-0)">${esc(c.zh)}</span>
                    <span class="text-3" style="font-size:var(--fs-3xs)">${done} 掌握 · ${reading} 学习中 · ${total} 总计 · ${Math.round(pct)}%</span>
                  </div>
                  ${progressBar(pct, c.id)}
                </div>`).join('') || emptyState('暂无分类数据', '等待首次采集。', 'i-grid')}
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-chart')} 每日采集量</div>
            <span class="result-line" style="margin-left:auto">最近 ${Math.min(days.length, 30)} 天</span></div>
          <div class="panel-body">
            ${sparkline(days.slice(0, 30).reverse().map((d) => d.items.length), { w: 560, h: 90 })}
            <div class="tbl-wrap" style="margin-top:var(--sp-4)">
              <table class="tbl">
                <thead><tr><th>日期</th><th class="num">条数</th><th class="num">已掌握</th><th>热门分类</th></tr></thead>
                <tbody>
                  ${days.slice(0, 12).map((d) => {
                    const cc = new Map();
                    for (const it of d.items) cc.set(it.category, (cc.get(it.category) || 0) + 1);
                    const top = Array.from(cc.entries()).sort((a, b) => b[1] - a[1]).slice(0, 3);
                    return `<tr><td>${esc(d.day)} <span class="text-3">${esc(weekdayZh(d.day))}</span></td>
                      <td class="num">${d.items.length}</td>
                      <td class="num">${d.items.filter((i) => statusOf(i.id) === 'done').length}</td>
                      <td>${top.map(([c, n]) => `<span class="tag" data-cat="${c}">${esc((CAT_BY_ID[c] || {}).zh || c)} ${n}</span>`).join(' ')}</td></tr>`;
                  }).join('')}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <div class="col" style="gap:var(--sp-5)">
        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-star')} 收藏夹概览</div>
            <button class="btn btn-sm btn-ghost" style="margin-left:auto" data-route="#/starred">查看</button></div>
          <div class="panel-body">
            <div class="donut-wrap">
              ${ring(s.total ? (s.starred / s.total) * 100 : 0, 76, 8, 'job', String(s.starred))}
              <div class="legend">
                <div class="legend-item"><span class="legend-swatch" style="background:var(--c-job)"></span>已收藏<span class="lv">${s.starred}</span></div>
                <div class="legend-item"><span class="legend-swatch" style="background:var(--ok)"></span>已掌握<span class="lv">${s.done}</span></div>
                <div class="legend-item"><span class="legend-swatch" style="background:var(--accent)"></span>学习中<span class="lv">${s.reading}</span></div>
                <div class="legend-item"><span class="legend-swatch" style="background:var(--bg-4)"></span>未读<span class="lv">${s.total - s.done - s.reading}</span></div>
              </div>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-database')} 来源分布</div></div>
          <div class="panel-body flush">
            <div class="mini-list">
              ${bySrc.map(([ch, n]) => `<div class="mini-item">
                <span class="dot"></span><span class="t">${esc(channelMeta(ch).zh)}</span>
                <span class="n">${n} · ${Math.round((n / Math.max(1, state.items.length)) * 100)}%</span></div>`).join('')}
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-activity')} 热度日历</div></div>
          <div class="panel-body">
            <div class="heat">
              ${Array.from({ length: 91 }).map((_, i) => {
                const d = new Date(Date.now() - (90 - i) * 86400000);
                const k = dateKey(d);
                const n = (days.find((x) => x.day === k) || { items: [] }).items.length;
                const lv = n === 0 ? 0 : n < 5 ? 1 : n < 12 ? 2 : n < 25 ? 3 : 4;
                return `<span class="heat-cell" data-lv="${lv}" data-tip="${attr(k)} · ${n} 条"></span>`;
              }).join('')}
            </div>
            <div class="row" style="margin-top:var(--sp-3);justify-content:space-between;font-size:var(--fs-3xs);color:var(--fg-3)">
              <span>90 天前</span><span class="row" style="gap:3px">少
                <span class="heat-cell" data-lv="0"></span><span class="heat-cell" data-lv="1"></span>
                <span class="heat-cell" data-lv="2"></span><span class="heat-cell" data-lv="3"></span>
                <span class="heat-cell" data-lv="4"></span> 多</span><span>今天</span>
            </div>
          </div>
        </div>
      </div>
    </div>`;
  },
  after() {},
};

/* ============================== STARRED ================================ */

const StarredView = {
  title: '收藏夹',
  render() {
    state.filters.starredOnly = true;
    const list = filteredItems();
    const notes = Object.entries(state.user.notes || {}).filter(([, v]) => v && v.trim());
    return `
    <div class="section-head"><div><h2 class="section-title">收藏夹</h2>
      <p class="section-desc">${list.length} 条已收藏内容 · 适合面试前集中复习。</p></div>
      <div class="section-actions">
        <button class="btn btn-sm btn-ghost" data-act="print">${icon('i-download')} 打印复习清单</button>
      </div></div>
    ${renderCards(list, { all: true })}
    ${notes.length ? `<div class="rule"></div>
      <div class="panel"><div class="panel-head"><div class="panel-title">${icon('i-list')} 我的笔记</div></div>
      <div class="panel-body flush"><div class="mini-list">
        ${notes.map(([id, v]) => {
          const it = state.byId.get(id);
          return `<div class="mini-item" style="align-items:flex-start">
            <span class="dot"></span>
            <span class="t">${it ? `<b style="color:var(--fg-0)">${esc(it.title)}</b><br>` : ''}<span class="text-2">${esc(v)}</span></span>
            ${it ? `<button class="icon-btn" data-act="open-item" data-id="${attr(id)}">${icon('i-chevron')}</button>` : ''}
          </div>`;
        }).join('')}
      </div></div></div>` : ''}`;
  },
  after() { wireItemKeyboard(); },
};

/* ============================== PIPELINE =============================== */

/* ======================= REDUNDANCY PANEL =============================== */
/**
 * Renders the optional redundancy audit (web/data/redundancy-report.json, written
 * by scripts/analyze_redundancy.py on every daily run).
 *
 * WHY it is surfaced in the UI: redundancy is a slow, silent failure. Nothing errors
 * when the corpus fills with the same thing reported repeatedly or with items that
 * matched no tracked direction - the workbench just gets less useful. Showing the
 * numbers next to channel health makes that drift visible instead of something you
 * discover months later.
 *
 * Degrades to nothing when the report is absent (fresh clone, or a run that predates
 * this feature) rather than showing an empty shell.
 */
function redundancyPanel() {
  const r = state.redundancy;
  if (!r || !r.l0) return '';

  const l0 = r.l0 || {};
  const l3 = r.l3_lowInformation || {};
  const work = Array.isArray(r.worklist) ? r.worklist : [];
  const high = work.filter((a) => a.severity === 'high').length;
  const ent = (r.l1_repeatedEntities || []).slice(0, 5);
  const sat = (r.l2_saturation || []).filter((s) => s.share >= 0.25).slice(0, 4);
  const unclShare = Number(l3.unclassifiedShare || 0);

  const stat = (label, value, tone) => `
    <div class="stat-mini">
      <div class="stat-mini-v ${tone || ''}">${esc(String(value))}</div>
      <div class="stat-mini-l">${esc(label)}</div>
    </div>`;

  return `
  <div class="panel">
    <div class="panel-head"><div class="panel-title">${icon('i-chart')} 知识卡片去冗余体检</div>
      <span class="badge ${high ? 'badge-warn' : 'badge-ok'}" style="margin-left:auto">
        ${high ? `${high} 项待处理` : '指标正常'}</span></div>
    <div class="panel-body">
      <div class="prose" style="font-size:var(--fs-2xs);margin-bottom:var(--sp-3)">
        <p>采集器的四层去重只处理「同一条内容」，处理不了「同一件事被反复收录」和「命中不了任何方向的条目」。
        这一栏是每日运行时的去冗余体检：先看硬重复，再看实体重复、话题饱和、未分类占比。</p>
      </div>

      <div class="grid grid-4" style="gap:var(--sp-3);margin-bottom:var(--sp-4)">
        ${stat('重复 id / 共用 URL', `${l0.duplicateIds || 0} / ${l0.duplicateUrls || 0}`,
               (l0.duplicateIds || l0.duplicateUrls) ? 'is-warn' : '')}
        ${stat('未分类占比', `${(unclShare * 100).toFixed(1)}%`,
               unclShare >= 0.15 ? 'is-warn' : '')}
        ${stat('低于相关度门槛', l3.belowGate || 0)}
        ${stat('摘要 <60 字', l3.shortSummary || 0)}
      </div>

      ${ent.length ? `
      <div class="eyebrow">同一实体反复收录（top ${ent.length}）</div>
      <ul class="kcard-points" data-cat="agent" style="margin-bottom:var(--sp-3)">
        ${ent.map((e) => `<li><span><b>${esc(e.token)}</b> × ${e.items}
          <span class="text-3">${esc(Object.keys(e.categories || {}).join(' / '))}</span></span></li>`).join('')}
      </ul>` : ''}

      ${sat.length ? `
      <div class="eyebrow">话题饱和（分类内某一实词占比 ≥25%）</div>
      <ul class="kcard-points" data-cat="generative" style="margin-bottom:var(--sp-3)">
        ${sat.map((s) => `<li><span>${esc(s.category)} 的 <b>${esc(s.topToken)}</b>
          占 ${(s.share * 100).toFixed(0)}%（${s.count}/${s.items}）</span></li>`).join('')}
      </ul>` : ''}

      <div class="eyebrow">工单</div>
      <ul class="kcard-points" data-cat="posttraining" style="margin-bottom:var(--sp-3)">
        ${work.slice(0, 6).map((a) => `<li><span><b>[${esc(a.kind)}]</b> ${esc(a.text)}</span></li>`).join('')}
      </ul>

      <div class="text-3" style="font-size:var(--fs-3xs)">
        体检时间 ${esc(String(r.generatedAt || '—'))} · 语料 ${esc(String(r.corpus || '—'))} 条 ·
        命令 <code>python scripts/analyze_redundancy.py</code>（只报告；下架需显式
        <code>python scripts/prune_items.py --apply</code>）
      </div>
    </div>
  </div>`;
}

const PipelineView = {
  title: '采集与运行',
  render() {
    const runs = state.runs || [];
    const m = state.manifest || {};
    const reg = state.sourceRegistry;
    const channels = (reg && reg.channels) || [];
    const okCh = channels.filter((c) => c.status === 'ok' || c.reachable).length;
    return `
    <div class="section-head">
      <div><h2 class="section-title">采集与运行</h2>
      <p class="section-desc">每日 18:00 (Asia/Shanghai)触发的联网调研流水线：渠道 → 去重 → 打分 → 归纳 → 自检 → 原子写入。</p></div>
      <div class="section-actions">
        <button class="btn btn-sm btn-ghost" data-act="reload">${icon('i-refresh')} 重新读取</button>
      </div>
    </div>

    <div class="grid grid-4" style="margin-bottom:var(--sp-6)">
      <div class="card card-pad"><div class="eyebrow">最近运行</div>
        <div class="stat-val" style="font-size:var(--fs-lg);margin-top:6px">${esc(m.lastRunAt ? relTime(m.lastRunAt) : '尚未运行')}</div>
        <div class="text-3" style="font-size:var(--fs-3xs)">${esc(m.lastRunAt ? fmtDate(m.lastRunAt, 'datetime') : '等待第一次采集')}</div></div>
      <div class="card card-pad"><div class="eyebrow">渠道成功率</div>
        <div class="stat-val" style="font-size:var(--fs-lg);margin-top:6px">${m.channelsOk != null ? `${m.channelsOk}/${m.channelsTotal}` : channels.length ? `${okCh}/${channels.length}` : '—'}</div>
        <div class="text-3" style="font-size:var(--fs-3xs)">失败渠道自动降级到备用源</div></div>
      <div class="card card-pad"><div class="eyebrow">累计入库</div>
        <div class="stat-val" style="font-size:var(--fs-lg);margin-top:6px">${state.items.length}</div>
        <div class="text-3" style="font-size:var(--fs-3xs)">去重后知识卡片</div></div>
      <div class="card card-pad"><div class="eyebrow">运行次数</div>
        <div class="stat-val" style="font-size:var(--fs-lg);margin-top:6px">${runs.length}</div>
        <div class="text-3" style="font-size:var(--fs-3xs)">保留最近 90 次记录</div></div>
    </div>

    <div class="grid grid-dash">
      <div class="col" style="gap:var(--sp-5)">
        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-activity')} 运行历史</div>
            <span class="result-line" style="margin-left:auto">
              定时任务每天 18:00 一次；标记为「手动」的是调试运行
            </span></div>
          <div class="panel-body flush">
            ${(() => {
              // Tell the reader WHICH runs came from the 18:00 schedule. Without
              // this the history looks alarming: a debugging afternoon shows a
              // dozen runs and reads like the schedule is firing repeatedly.
              const scheduled = runs.filter((r) => r.trigger === 'scheduled').length;
              return runs.length ? `
              <div style="padding:var(--sp-3) var(--sp-4);border-bottom:1px solid var(--line-0)">
                <div class="quality-legend">
                  <span><i class="q-dot" style="background:var(--ok)"></i>定时触发 ${scheduled} 次</span>
                  <span><i class="q-dot" style="background:var(--fg-3)"></i>手动 / 调试 ${runs.length - scheduled} 次</span>
                  <span class="text-3">共记录 ${runs.length} 次（保留最近 120 条）</span>
                </div>
              </div>` : '';
            })()}
            ${runs.length ? `<div class="tbl-wrap" style="border:none"><table class="tbl">
              <thead><tr><th>时间</th><th>触发</th><th>状态</th><th class="num">新增</th><th class="num">渠道</th><th class="num">耗时</th><th>备注</th></tr></thead>
              <tbody>
                ${runs.slice(0, 25).map((r) => {
                  const trig = r.trigger || 'manual';
                  const trigCls = trig === 'scheduled' ? 'badge-ok' : trig === 'debug' ? 'badge-mute' : 'badge-info';
                  const trigZh = { scheduled: '定时', manual: '手动', debug: '调试' }[trig] || trig;
                  const scope = r.narrowRun ? ' · 部分渠道' : '';
                  return `<tr>
                  <td>${esc(fmtDate(r.startedAt || r.at, 'datetime'))}</td>
                  <td><span class="badge ${trigCls}" data-tip="${trig === 'scheduled' ? '由任务计划程序在 18:00 触发' : '人为执行（调试或补跑）'}">${esc(trigZh)}</span>${scope ? `<div class="text-3" style="font-size:var(--fs-3xs)">${esc(scope.trim())}</div>` : ''}</td>
                  <td><span class="badge ${r.status === 'ok' ? 'badge-ok' : r.status === 'partial' ? 'badge-warn' : 'badge-err'}">${esc(r.status || '—')}</span></td>
                  <td class="num">${r.newItems != null ? r.newItems : '—'}</td>
                  <td class="num">${r.channelsOk != null ? `${r.channelsOk}/${r.channelsTotal}` : '—'}</td>
                  <td class="num">${r.durationSec != null ? r.durationSec + 's' : '—'}</td>
                  <td class="text-2">${esc((r.notes || '').slice(0, 90))}</td>
                </tr>`;
                }).join('')}
              </tbody></table></div>`
              : emptyState('还没有运行记录', '每次采集都会向 data/logs/runs.json 追加一条运行日志。', 'i-activity')}
          </div>
        </div>

        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-database')} 渠道清单与策略</div>
            <span class="result-line" style="margin-left:auto">
              ${channels.length} 个已登记${reg && reg.channelsRanCount != null ? ` · 本轮跑 ${reg.channelsRanCount} 个` : ''}
            </span></div>
          <div class="panel-body flush">
            ${channels.length ? `<div class="tbl-wrap" style="border:none"><table class="tbl">
              <thead><tr><th>渠道</th><th>模式</th><th>认证</th><th>频率限制</th><th>本轮</th></tr></thead>
              <tbody>
                ${channels.map((c) => {
                  const st = String(c.status || 'unknown');
                  const cls = st === 'ok' ? 'badge-ok'
                    : st === 'blocked' ? 'badge-err'
                    : st === 'unknown' ? 'badge-mute' : 'badge-warn';
                  const backupNote = c.backupUsed
                    ? `<div class="text-3" style="font-size:var(--fs-3xs)">备用源 ${esc(c.backupUsed)} 生效</div>`
                    : (Array.isArray(c.backupAttempts) && c.backupAttempts.some((a) => a.result !== 'ok')
                      ? `<div class="text-3" style="font-size:var(--fs-3xs)">备用源未取得数据</div>` : '');
                  const staleNote = c.notRunThisPass
                    ? `<div class="text-3" style="font-size:var(--fs-3xs)">本轮未运行${c.staleSince ? ' · ' + esc(String(c.staleSince).slice(0, 10)) : ''}</div>`
                    : '';
                  return `<tr>
                  <td><span style="font-weight:600;color:var(--fg-0)">${esc(c.nameZh || c.name || c.id)}</span>
                    <div class="text-3" style="font-size:var(--fs-3xs)">${esc(c.id || '')}${c.tier ? ' · ' + esc(c.tier) : ''}</div>
                    ${backupNote}${staleNote}</td>
                  <td><span class="tag">${esc(c.recommendedMode || c.mode || '—')}</span></td>
                  <td>${c.authRequired ? '<span class="badge badge-warn">需登录</span>' : '<span class="badge badge-mute">公开</span>'}</td>
                  <td class="text-2">${esc(String(c.rateLimit || '—').slice(0, 40))}</td>
                  <td><span class="badge ${cls}">${esc(st)}</span>
                    ${c.count != null ? `<div class="text-3" style="font-size:var(--fs-3xs)">${esc(String(c.count))} 条</div>` : ''}</td>
                </tr>`;
                }).join('')}
              </tbody></table></div>`
              : emptyState('渠道注册表尚未生成', '运行采集器或把 source_registry.json 复制到 web/data/sources.json。', 'i-database')}
          </div>
        </div>

        ${(() => {
          const proposals = state.proposals || null;
          const q = proposals && Array.isArray(proposals.humanReviewQueue) ? proposals.humanReviewQueue : [];
          const health = proposals && Array.isArray(proposals.channelHealth) ? proposals.channelHealth : [];
          const esc_ = health.filter((h) => h.escalate);
          return `<div class="panel">
            <div class="panel-head"><div class="panel-title">${icon('i-flask')} 自我迭代提案</div>
              <span class="result-line" style="margin-left:auto">${proposals ? esc(String(proposals.date || '')) : '尚未生成'}</span></div>
            <div class="panel-body">
              ${proposals ? `
                <div class="text-2" style="font-size:var(--fs-2xs);margin-bottom:var(--sp-3)">
                  由采集器确定性生成（不依赖模型），只做<strong>建议</strong>；分类增删、渠道升降级、评分权重、去重阈值一律需要人工确认后才生效。</div>
                ${esc_.length ? `<div class="eyebrow" style="margin-bottom:6px">需升级处理的渠道</div>
                  <ul class="kcard-points" style="margin-bottom:var(--sp-3)">
                    ${esc_.slice(0, 6).map((h) => `<li><span>${esc(h.id)} · ${esc(h.status)} × ${esc(String(h.streak))} — ${esc(h.suggestedAction || '')}</span></li>`).join('')}
                  </ul>` : ''}
                ${q.length ? `<div class="eyebrow" style="margin-bottom:6px">人工复核队列（${q.length}）</div>
                  <ul class="kcard-points" data-cat="posttraining">
                    ${q.map((line) => `<li><span>${esc(line)}</span></li>`).join('')}
                  </ul>` : '<div class="status-line"><span class="ok">本轮无需人工介入</span></div>'}
              ` : emptyState('还没有提案文件', '采集器每轮都会写 web/data/proposals/YYYY-MM-DD.json。', 'i-flask')}
            </div>
          </div>`;
        })()}
      </div>

      <div class="col" style="gap:var(--sp-5)">
        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-clock')} 定时任务</div></div>
          <div class="panel-body">
            <dl class="kv">
              <dt>计划时间</dt><dd>每日 18:00</dd>
              <dt>时区</dt><dd>Asia/Shanghai (UTC+8)</dd>
              <dt>触发方式</dt><dd>Windows 任务计划程序</dd>
              <dt>入口脚本</dt><dd class="mono" style="font-size:var(--fs-3xs)">scripts/run-daily.ps1</dd>
              <dt>日志目录</dt><dd class="mono" style="font-size:var(--fs-3xs)">data/logs/</dd>
            </dl>
            <div class="kcard-why" style="margin-top:var(--sp-4)">
              <b>手动运行 · </b>在项目根目录执行
              <code style="display:block;margin-top:6px;font-size:var(--fs-3xs)">powershell -ExecutionPolicy Bypass -File scripts/run-daily.ps1</code>
              <button class="btn btn-sm" style="margin-top:var(--sp-3)" data-act="copy" data-copy="powershell -ExecutionPolicy Bypass -File scripts/run-daily.ps1" data-copy-msg="命令已复制">
                ${icon('i-copy')} 复制命令</button>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-shield')} 真实性与准确性自查</div></div>
          <div class="panel-body">
            <div class="prose" style="font-size:var(--fs-2xs)">
              <ul>
                <li>每条卡片必须带<strong>可访问的来源链接</strong>，无链接的内容直接丢弃。</li>
                <li>摘要只允许来自原文（标题/摘要/README），<strong>禁止推断未出现的事实</strong>。</li>
                <li>数字类信息（薪资、star 数、录用率）标记 <code>confidence</code>，低可信度在界面上显式标注。</li>
                <li>自动生成内容与人工内容分区展示，来源渠道逐一列出。</li>
                <li>每日自检：链接可达性抽检、重复率、空摘要率、分类覆盖率、<strong>去冗余体检</strong>，异常写入运行日志。</li>
              </ul>
            </div>
          </div>
        </div>

        ${redundancyPanel()}

        <div class="panel">
          <div class="panel-head"><div class="panel-title">${icon('i-flask')} 自我迭代机制</div>
            ${state.proposals ? `<span class="badge ${((state.proposals.humanReviewQueue || []).length) ? 'badge-warn' : 'badge-ok'}" style="margin-left:auto">
              待复核 ${((state.proposals.humanReviewQueue || []).length)}</span>` : ''}</div>
          <div class="panel-body">
            <div class="prose" style="font-size:var(--fs-2xs)">
              <ul>
                <li><strong>observe</strong>：每轮记录渠道状态、命中关键词、分类覆盖率与重复率。</li>
                <li><strong>propose</strong>：采集器<strong>确定性地</strong>写 <code>proposals/YYYY-MM-DD.json</code>
                  （不依赖模型，所以即使 Agent 层没凭据也会产出）。</li>
                <li><strong>review</strong>：提案进入「自我迭代提案」面板的人工复核队列。</li>
                <li><strong>apply</strong>：只有「单关键词权重 ≤10% 的微调」可自动生效；分类增删、渠道升降级、
                  评分权重、去重阈值、blocklist 一律需人工确认。</li>
                <li><strong>measure</strong>：下一轮对比相关度分布、分类覆盖率与失败渠道数。</li>
              </ul>
            </div>
            ${state.proposals && Array.isArray(state.proposals.keywordProposals) && state.proposals.keywordProposals.length
              ? `<div class="eyebrow" style="margin-top:var(--sp-3);margin-bottom:4px">关键词精简建议</div>
                 <div class="row" style="flex-wrap:wrap;gap:4px">
                   ${state.proposals.keywordProposals.slice(0, 6).map((k) => `<span class="tag" data-cat="${esc(k.category)}">${esc((CAT_BY_ID[k.category] || {}).zh || k.category)} · 待精简 ${esc(String((k.remove || []).length))}</span>`).join('')}
                 </div>` : ''}
            ${state.proposals
              ? `<div class="row" style="margin-top:var(--sp-3)">
                   <button class="btn btn-sm" data-act="reload">${icon('i-refresh')} 重新读取提案</button>
                   <a class="btn btn-sm btn-ghost" href="data/proposals/latest.json" target="_blank" rel="noopener">${icon('i-external')} 查看原始提案</a>
                 </div>`
              : `<button class="btn btn-sm" style="width:100%;margin-top:var(--sp-3)" data-act="reload">提案文件尚未生成，重新读取</button>`}
          </div>
        </div>
      </div>
    </div>`;
  },
  after() {},
};

/* ============================ DETAIL DRAWER ============================ */

function openItem(id) {
  const it = state.byId.get(id);
  if (!it) return;
  const st = statusOf(it.id);
  const starred = Boolean(state.user.starred[it.id]);
  const dt = it.publishedAt || it.fetchedAt;

  /* Heavy HTML is built from pre-flattened string fragments. Keeping every
     template literal single-level makes this function trivially verifiable and
     avoids the deep nesting that caused a parser-level mistake here before. */
  const parts = [];

  /* Layer-2 (agent) enrichment, when it exists for this item. This is the
     "抽象概念易读化" payload: a one-line conclusion, then each abstract concept
     explained plainly with an analogy, a visualisation recipe and its failure
     boundary. Shown first because it is the most useful thing on the page. */
  if (it.enriched) {
    if (it.tldr) {
      parts.push('<div class="kcard-why" style="margin-bottom:var(--sp-4)"><b>一句话结论 · </b>'
        + esc(it.tldr) + '</div>');
    }
    if (it.diagram) {
      const dg = diagramHtml(it.diagram);
      if (dg) parts.push(dg);
    }
    /* Teaching + concept payloads render through the shared builders defined
       above, so the item drawer and the 题库解析页 cannot drift apart. */
    const teach = teachingHtml(it.teaching);
    if (teach) parts.push(teach);
    const concepts = conceptsHtml(it.concepts);
    if (concepts) parts.push(concepts);
    if (it.selfCheck && ((it.selfCheck.uncertain || []).length || (it.selfCheck.claims || []).length)) {
      const sc = [];
      if ((it.selfCheck.claims || []).length) {
        sc.push('<div class="eyebrow">可核实的断言</div><ul class="kcard-points" data-cat="agent">'
          + it.selfCheck.claims.map((c) => '<li><span>' + esc(c) + '</span></li>').join('') + '</ul>');
      }
      if ((it.selfCheck.uncertain || []).length) {
        sc.push('<div class="eyebrow" style="margin-top:var(--sp-3)">待人工核实</div><ul class="kcard-points" data-cat="posttraining">'
          + it.selfCheck.uncertain.map((c) => '<li><span>' + esc(c) + '</span></li>').join('') + '</ul>');
      }
      parts.push('<div class="prose"><h2>深度层的自检</h2>' + sc.join('') + '</div>');
    }
  } else {
    /* Not yet deep-read. Say so honestly instead of pretending the summary is an
       analysis, and tell the reader where the analysis will come from. */
    const queued = state.deepReadPlan && Array.isArray(state.deepReadPlan.queue)
      && state.deepReadPlan.queue.some((q) => q.id === it.id);
    parts.push('<div class="kcard-why" style="margin-bottom:var(--sp-4);border-left-color:var(--warn)">'
      + '<b>这张卡片还没有深度解析 · </b>'
      + (queued
        ? '它已在深度解析队列里（配额按分类分配，每个方向每天 2–10 条），下一轮运行时会补上：一句话结论、概念易读化、生活类比、图解与自测题。'
        : '当前显示的是采集层的原文摘要与来源链接。你可以在「采集与运行」页看到深度解析的进度与配额。')
      + '</div>');
  }

  if (it.why) {
    parts.push('<div class="kcard-why" style="margin-bottom:var(--sp-4)"><b>为什么重要 · </b>'
      + esc(it.why) + '</div>');
  }

  if (it.summary) {
    parts.push('<div class="prose"><h2>摘要</h2><p>' + esc(it.summary) + '</p></div>');
  }

  if (it.keyPoints.length) {
    const lis = it.keyPoints.map((k) => '<li>' + esc(k) + '</li>').join('');
    parts.push('<div class="prose"><h2>关键要点</h2><ul>' + lis + '</ul></div>');
  }

  if (it.details) {
    parts.push('<div class="prose"><h2>深入解析</h2>' + md(it.details) + '</div>');
  }

  if (it.formulas && it.formulas.length) {
    const cards = it.formulas
      .map((f) => formulaDetailHtml(normalizeFormula(f, 0)))
      .join('');
    parts.push('<div class="prose"><h2>相关公式</h2></div><div class="col" style="gap:var(--sp-3)">'
      + cards + '</div>');
  }

  if (it.examples && it.examples.length) {
    const blocks = it.examples.map((ex) => {
      if (typeof ex === 'string') return '<p>' + esc(ex) + '</p>';
      const head = '<h3>' + esc(ex.title || '示例') + '</h3>';
      const body = ex.body ? '<p>' + esc(ex.body) + '</p>' : '';
      const code = ex.code
        ? '<div class="code-wrap"><div class="code-head"><span>'
          + esc(ex.lang || 'code') + '</span></div><pre class="code">'
          + highlight(ex.code, ex.lang || 'python') + '</pre></div>'
        : '';
      return head + body + code;
    }).join('');
    parts.push('<div class="prose"><h2>实例讲解</h2>' + blocks + '</div>');
  }

  if (it.tags.length || it.entities.length) {
    const tagChips = it.tags
      .map((t) => '<button class="chip" data-act="toggle-tag" data-tag="' + attr(t) + '">' + esc(t) + '</button>')
      .join('');
    const entityTags = it.entities.map((t) => '<span class="tag">' + esc(t) + '</span>').join('');
    parts.push('<div class="prose"><h2>标签与实体</h2><div class="row" style="flex-wrap:wrap;gap:6px">'
      + tagChips + entityTags + '</div></div>');
  }

  const noteValue = (state.user.notes || {})[it.id] || '';
  parts.push(
    '<div class="prose"><h2>我的笔记</h2>'
    + '<textarea data-note-for="' + attr(it.id) + '" rows="4" '
    + 'placeholder="写下你的理解、疑问、可复用片段…" '
    + 'style="width:100%;padding:var(--sp-3);border:1px solid var(--line-1);'
    + 'border-radius:var(--r-md);background:var(--bg-2);color:var(--fg-0);'
    + 'font-size:var(--fs-xs);resize:vertical">' + esc(noteValue) + '</textarea>'
    + '<div class="text-3" style="font-size:var(--fs-3xs);margin-top:4px">'
    + '自动保存到本地（localStorage）。</div></div>'
  );

  if (it.sources.length) {
    const lis = it.sources.map((s) => {
      const url = safeUrl(s.url || s);
      const label = s.title || hostOf(s.url || s) || String(s);
      const origin = s.name ? '<span class="text-3"> · ' + esc(s.name) + '</span>' : '';
      return '<li><a href="' + attr(url) + '" target="_blank" rel="noopener noreferrer">'
        + esc(label) + '</a>' + origin + '</li>';
    }).join('');
    parts.push('<div class="prose"><h2>来源与溯源</h2><ul>' + lis + '</ul></div>');
  }

  const metaJson = JSON.stringify({
    id: it.id, channel: it.channel, category: it.category, lang: it.lang,
    publishedAt: it.publishedAt, fetchedAt: it.fetchedAt,
    relevanceScore: it.relevance, relevanceBreakdown: it.relevanceBreakdown,
    qualitySignals: it.quality, difficulty: it.difficulty,
    venue: it.venue, ccf: it.ccf, contentHash: it.contentHash,
  }, null, 2);
  parts.push('<details style="margin-top:var(--sp-4)">'
    + '<summary style="cursor:pointer;font-size:var(--fs-2xs);color:var(--fg-2)">'
    + '采集元数据（用于准确性与溯源自查）</summary>'
    + '<pre class="code" style="margin-top:var(--sp-3);border:1px solid var(--line-0);'
    + 'border-radius:var(--r-md)">' + esc(metaJson) + '</pre></details>');

  const eyebrow = (CAT_BY_ID[it.category] || {}).zh || '知识';
  const metaChips = [
    catPill(it.category),
    it.difficulty ? '<span class="badge badge-mute">' + esc(DIFF_ZH[it.difficulty] || it.difficulty) + '</span>' : '',
    it.ccf ? '<span class="badge badge-info">CCF-' + esc(it.ccf) + '</span>' : '',
    dt ? '<span class="text-3" style="font-size:var(--fs-3xs)">'
      + esc(fmtDate(dt, 'datetime')) + ' · ' + esc(relTime(dt)) + '</span>' : '',
    it.authors.length ? '<span class="text-3" style="font-size:var(--fs-3xs)">'
      + esc(it.authors.slice(0, 4).join(', ')) + (it.authors.length > 4 ? ' 等' : '') + '</span>' : '',
  ].filter(Boolean).join('');

  const titleHtml = esc(it.title)
    + (it.titleZh
      ? '<div class="text-2" style="font-size:var(--fs-sm);font-weight:500;margin-top:4px">'
        + esc(it.titleZh) + '</div>'
      : '');

  const footParts = [
    it.url
      ? '<a class="btn btn-sm btn-primary" href="' + attr(it.url) + '" target="_blank" '
        + 'rel="noopener noreferrer">' + icon('i-external') + ' 打开原文</a>'
      : '',
    '<button class="btn btn-sm' + (starred ? ' is-on' : '') + '" data-act="star" data-id="'
      + attr(it.id) + '">' + icon('i-star') + (starred ? ' 已收藏' : ' 收藏') + '</button>',
    '<button class="btn btn-sm' + (st === 'reading' ? ' is-on' : '') + '" data-act="status" data-id="'
      + attr(it.id) + '" data-status="reading">' + icon('i-clock') + ' 学习中</button>',
    '<button class="btn btn-sm' + (st === 'done' ? ' is-on' : '') + '" data-act="status" data-id="'
      + attr(it.id) + '" data-status="done">' + icon('i-check') + ' 已掌握</button>',
    '<button class="btn btn-sm btn-ghost" data-act="copy" data-copy="'
      + attr(it.canonicalUrl || it.url || it.title) + '" data-copy-msg="链接已复制">'
      + icon('i-link') + ' 复制链接</button>',
  ].filter(Boolean).join('');

  openDrawer({
    eyebrow: eyebrow + ' · ' + channelMeta(it.channel).zh,
    title: titleHtml,
    cat: it.category,
    meta: metaChips,
    body: parts.join(''),
    foot: footParts,
  });
  $('#drawer').dataset.itemId = it.id;
}

function openJob(id) {
  const j = state.jobs.find((x) => x.id === id);
  if (!j) return;
  openDrawer({
    eyebrow: '岗位详情',
    title: `${esc(j.company)} · ${esc(j.title)}`,
    cat: 'job',
    meta: `<span class="tier" data-tier="${attr(j.tier)}">${esc(j.tier)}</span>
      <span class="badge ${j.open ? 'badge-ok' : 'badge-mute'}">${j.open ? '开放中' : '已关闭'}</span>
      <span class="text-3" style="font-size:var(--fs-3xs)">${esc(j.cities.join(' / ') || '城市待定')} · ${esc(j.pay || '面议')}</span>`,
    body: `<div class="prose">${jobDetailHtml(j).replace(/^[\s\S]*?<div class="grid grid-dash">/, '<div class="grid grid-dash">')}</div>`,
    foot: `${j.applyUrl ? `<a class="btn btn-sm btn-primary" href="${attr(j.applyUrl)}" target="_blank" rel="noopener noreferrer">${icon('i-external')} 投递</a>` : ''}
      <button class="btn btn-sm btn-ghost" data-act="nav" data-hash="#/jobs?focus=${encodeURIComponent(j.id)}">${icon('i-chevron')} 在看板中打开</button>`,
  });
}

/* ================================= BOOT ================================ */

function boot() {
  loadUser();
  applyPrefs();

  VIEWS.dashboard = DashboardView;
  VIEWS.digest = DigestView;
  VIEWS.categories = CategoriesView;
  VIEWS.knowledge = KnowledgeView;
  VIEWS.formulas = FormulasView;
  VIEWS.problems = ProblemsView;
  VIEWS.repos = ReposView;
  VIEWS.jobs = JobsView;
  VIEWS.skills = SkillsView;
  VIEWS.roadmap = RoadmapView;
  VIEWS.progress = ProgressView;
  VIEWS.starred = StarredView;
  VIEWS.pipeline = PipelineView;

  installShell();
  installKeyboard();

  Store.boot().then(() => {
    if (!location.hash) history.replaceState(null, '', '#/dashboard');
    render();
    if (state.loadErrors.length) {
      toast(`${state.loadErrors.length} 个数据文件未找到，界面使用降级数据`, 'warn', 5200);
    } else {
      toast(`数据层已就绪：${state.items.length} 条知识 · ${state.jobs.length} 个岗位`, 'ok', 2600);
    }
    // 非阻塞：核对浏览器里跑的是不是最新发布的脚本（见 ui.part.js 的说明）。
    // 放在 render() 之后并且不 await —— 一次自检失败绝不能拖慢或挡住首屏。
    checkForNewBuild();
  }).catch((err) => {
    $('#view').innerHTML = emptyState('数据层加载失败', String(err && err.message || err), 'i-alert',
      `<button class="btn btn-sm" data-act="reload">重试</button>`);
  });
}

/* ===== entry point ===== */
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => boot());
} else {
  boot();
}
