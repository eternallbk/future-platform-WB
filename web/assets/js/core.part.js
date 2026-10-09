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

export const CATEGORIES = [
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

export const CAT_BY_ID = Object.fromEntries(CATEGORIES.map((c) => [c.id, c]));

export const ROUTES = [
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

export const THEMES = [
  { id: 'midnight', zh: '午夜蓝',   kind: 'dark',  accent: 'blue',    swatches: ['#070a10', '#10161f', '#6ea8fe', '#c084fc'] },
  { id: 'daylight', zh: '日光白',   kind: 'light', accent: 'blue',    swatches: ['#f4f6fa', '#ffffff', '#2563eb', '#9333ea'] },
  { id: 'terminal', zh: '终端绿',   kind: 'dark',  accent: 'emerald', swatches: ['#05080a', '#0c1317', '#4ade80', '#38bdf8'] },
  { id: 'aurora',   zh: '极光紫',   kind: 'dark',  accent: 'violet',  swatches: ['#0a0716', '#130f24', '#a78bfa', '#e879f9'] },
  { id: 'sand',     zh: '暖砂纸',   kind: 'light', accent: 'amber',   swatches: ['#f6f1e7', '#fffdf8', '#b45309', '#7e22ce'] },
  { id: 'nord',     zh: 'Nord',     kind: 'dark',  accent: 'cyan',    swatches: ['#242933', '#2e3440', '#88c0d0', '#b48ead'] },
];

export const ACCENTS = [
  { id: 'blue',    zh: '蓝', hex: '#60a5fa' },
  { id: 'violet',  zh: '紫', hex: '#a78bfa' },
  { id: 'cyan',    zh: '青', hex: '#22d3ee' },
  { id: 'emerald', zh: '绿', hex: '#34d399' },
  { id: 'amber',   zh: '琥珀', hex: '#fbbf24' },
  { id: 'rose',    zh: '玫瑰', hex: '#fb7185' },
];

/* Source channel registry — used for source filters, favicons and trust labels.
   `p` is the collection priority tier (P0 highest). */
export const CHANNELS = {
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

export function channelMeta(id) {
  return CHANNELS[id] || { zh: id || '未知来源', en: id || 'unknown', p: 'P2', url: '' };
}

/* ============================== §2 UTIL ================================= */

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function esc(s) {
  if (s === null || s === undefined) return '';
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/** Attribute-safe escape (same set; named separately for intent). */
export const attr = esc;

export function el(tag, attrs = {}, ...children) {
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

export function debounce(fn, ms = 220) {
  let t;
  const wrapped = (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  wrapped.cancel = () => clearTimeout(t);
  wrapped.flush = (...args) => { clearTimeout(t); fn(...args); };
  return wrapped;
}

export function throttle(fn, ms = 120) {
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

export function clamp(n, lo, hi) { return Math.min(hi, Math.max(lo, n)); }

export function icon(name, cls = '', size = null) {
  const s = size ? ` style="width:${size}px;height:${size}px"` : '';
  return `<svg class="${cls}"${s} aria-hidden="true"><use href="#${name}"/></svg>`;
}

/* --- Date / time -------------------------------------------------------- */
const SH_TZ = 'Asia/Shanghai';

export function shanghaiNow() {
  return new Date(new Date().toLocaleString('en-US', { timeZone: SH_TZ }));
}

export function fmtDate(iso, style = 'short') {
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

export function relTime(iso) {
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

export function weekdayZh(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][d.getDay()];
}

export function dateKey(d = new Date()) {
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

export function md(src) {
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
export function highlight(code, lang = '') {
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

export function tex(src) {
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
export function texInline(src, maxLen = 120) {
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
export function sanitizeSvg(svg) {
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

export function diagramHtml(diagram) {
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
export function chip(label, { on = false, cat = null, dot = false, attrs = '' } = {}) {
  const c = cat ? ` data-cat="${cat}"` : '';
  return `<button class="chip${on ? ' is-on' : ''}"${c} ${attrs}>` +
    (dot ? '<span class="chip-dot"></span>' : '') + esc(label) + '</button>';
}

export function catPill(catId) {
  const c = CAT_BY_ID[catId];
  if (!c) return '';
  return `<span class="kcard-cat" data-cat="${esc(catId)}">${esc(c.zh)}</span>`;
}

export function progressBar(pct, cat = null, cls = '') {
  const p = clamp(Math.round(pct), 0, 100);
  return `<div class="bar ${cls}"${cat ? ` data-cat="${cat}"` : ''} role="progressbar" aria-valuenow="${p}" aria-valuemin="0" aria-valuemax="100"><i style="width:${p}%"></i></div>`;
}

export function ring(pct, size = 62, stroke = 6, cat = null, label = '') {
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

export function sparkline(values, { w = 240, h = 44, cat = null } = {}) {
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

export function emptyState(title, desc, iconName = 'i-archive', actionHtml = '') {
  return `<div class="empty">${icon(iconName)}<h4>${esc(title)}</h4><p>${esc(desc)}</p>${actionHtml}</div>`;
}

/**
 * Pagination. Added because the knowledge view used to hard-cap at 90 cards, so
 * with 700+ items most of the corpus was unreachable from the UI - it existed in
 * the data layer but a reader could never get to it. Showing everything at once
 * is worse (a 1.7 MB DOM), hence real pages plus an explicit "show all".
 */
export function paginate(list, { route = '#/knowledge', extraQuery = '' } = {}) {
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

export function relevanceMeter(score) {
  const s = clamp(Number(score) || 0, 0, 100);
  return `<span class="relevance" data-tip="相关度评分 ${s}/100">
    <span class="relevance-bar"><i style="width:${s}%"></i></span><span class="tnum">${s}</span>
  </span>`;
}

export function safeUrl(u) {
  if (!u) return '';
  const s = String(u).trim();
  if (/^(https?:|mailto:)/i.test(s)) return s;
  return '';
}

export function hostOf(u) {
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

export const state = {
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

export function saveUser() {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({ prefs: state.prefs, user: state.user }));
  } catch (e) { /* storage may be unavailable (file://, private mode) */ }
}

export function loadUser() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (parsed.prefs) state.prefs = { ...DEFAULT_PREFS, ...parsed.prefs };
    if (parsed.user) state.user = { ...state.user, ...parsed.user };
  } catch (e) { /* ignore corrupt payload */ }
}

export function toggleStar(id) {
  if (state.user.starred[id]) delete state.user.starred[id];
  else state.user.starred[id] = true;
  saveUser();
  return Boolean(state.user.starred[id]);
}

export function setStatus(id, status) {
  const cur = state.user.status[id] || 'unread';
  const next = cur === status ? 'unread' : status;
  if (next === 'unread') delete state.user.status[id]; else state.user.status[id] = next;
  if (next === 'done') state.user.mastery[id] = Math.max(state.user.mastery[id] || 0, 3);
  saveUser();
  return next;
}

export function starCount() { return Object.keys(state.user.starred).length; }

export function statusOf(id) { return state.user.status[id] || 'unread'; }

export function completionStats() {
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

export const Store = {
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

export function normalizeItem(raw) {
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
export function itemsOf(catId) { return state.items.filter((i) => i.category === catId); }

export function allTags() {
  const m = new Map();
  for (const it of state.items) for (const t of it.tags) m.set(t, (m.get(t) || 0) + 1);
  return Array.from(m.entries()).sort((a, b) => b[1] - a[1]);
}

export function allChannels() {
  const m = new Map();
  for (const it of state.items) m.set(it.channel, (m.get(it.channel) || 0) + 1);
  return Array.from(m.entries()).sort((a, b) => b[1] - a[1]);
}

export function dayOf(item) {
  const d = item.date || (item.publishedAt || item.fetchedAt || '').slice(0, 10);
  return d || '未知日期';
}

export function groupByDay(items) {
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

export function applyPrefs() {
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

export function setTheme(id) {
  state.prefs.theme = id;
  const t = THEMES.find((x) => x.id === id);
  if (t) state.prefs.accent = t.accent;
  applyPrefs(); saveUser();
}

export function setAccent(id) { state.prefs.accent = id; applyPrefs(); saveUser(); }

export function toggleThemeKind() {
  const cur = THEMES.find((t) => t.id === state.prefs.theme) || THEMES[0];
  const next = cur.kind === 'dark' ? THEMES.find((t) => t.kind === 'light') : THEMES.find((t) => t.kind === 'dark');
  if (next) setTheme(next.id);
}

/* ============================== §6 TOAST =============================== */

const TOAST_ICON = { ok: 'i-check', warn: 'i-alert', err: 'i-alert', info: 'i-info' };

export function toast(message, kind = 'ok', ms = 3200) {
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
