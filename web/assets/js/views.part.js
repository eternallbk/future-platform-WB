/* ============================================================================
 * Future · 求职学习工作台 — views.js (part 2)
 * One renderer per route. Each view exposes { title, render(params), after? }.
 * Renderers return HTML strings; `after` wires up anything that needs real DOM
 * (canvases, scroll containers, drag-and-drop).
 * ========================================================================= */

/* ======================= SHARED FILTER / SEARCH ========================= */

export function queryMatches(it, q) {
  if (!q) return true;
  const hay = [it.title, it.titleZh, it.summary, it.why, it.category, it.channel,
    ...it.tags, ...it.entities, ...it.keyPoints, it.venue, it.authors.join(' ')]
    .join(' \u0001 ').toLowerCase();
  return String(q).toLowerCase().split(/\s+/).filter(Boolean).every((tok) => hay.includes(tok));
}

export function filteredItems() {
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

export function activeFilterCount() {
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

export function knowledgeCard(it, opts = {}) {
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

export function renderCards(list, opts = {}) {
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

export const DashboardView = {
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

export const STAGES = {
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

export const DigestView = {
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

export const CategoriesView = {
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

export const KnowledgeView = {
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
