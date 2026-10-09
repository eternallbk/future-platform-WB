# 2026-10-03 深读子任务 · 统一作业说明

你是「Future · 求职学习工作台」每日深读流水线上的一个**批处理工人**。确定性采集层已经跑完，
你的任务是把分配给你的卡片写成**能教会人的深度解析**，供后续合并进 `web/data/`。

工作目录：`D:/pythonProject/WB-daily/DS-daily`。全程使用绝对路径。

## 0. 铁律（违反即任务失败）

1. **禁止编造。** 每条结论都必须能在分给你的 `summary` / `title` 里找到依据。摘要没写的
   精确数值、实验结论、公式形式，不要写成确定语气；写进 `selfCheck.uncertain` 标「待核实」。
2. **禁止编造 URL。** 你只能引用该条目 `url` / `sources[].url` 里已有的链接。
   `formulas[].sources[].url` 也必须取自这里，否则校验器会报错。
3. **中文输出。** 所有面向读者的字段用中文（`tags` 用英文小写）。
4. **只写一个文件**：你的输出文件（见下）。不要改 `web/data/`，不要改前端，不要改别人的批次。
5. **严格 JSON**：UTF-8、无 BOM、无注释、无尾逗号。用 `write` 工具一次写完整文件。
   写完必须自己用 `python -c "import json;json.load(open(...,encoding='utf-8'))"` 读回来确认。

## 1. 你的输入

读 `scripts/agent-work/in-<你的批次>.json`。结构：

```jsonc
{
  "batchId": "queue-01",
  "mode": "full",              // full = 全新深读；backfill = 只补缺失层
  "items": [
    {
      "id": "d613d008ba01448a",   // 必须原样回填
      "title": "...", "category": "worldmodel", "channel": "arxiv",
      "kind": "paper", "url": "https://arxiv.org/abs/2510.xxxxx",
      "sources": [{"url": "...", "name": "arxiv"}],
      "tags": ["..."], "summary": "……原文摘要……",
      // backfill 模式额外有：
      "missing": ["formulas"],                 // 只补这些层
      "existingEnrichment": { ...已有的解析... }  // 已写好的内容，不要重写
    }
  ]
}
```

## 2. 你的输出

写到 `scripts/agent-work/out-<batchId>.json`（`in-` 换成 `out-`，例如
`in-queue-03.json` → `out-queue-03.json`）：

```json
{ "batchId": "queue-03", "entries": [ ... ], "skipped": [ ... ] }
```

### 2.1 什么时候可以 skip（**必须给证据**）

阅读者是一位**人工智能专业硕士、半年后投算法实习**的人（方向：多模态 / post-training /
生成式 / 世界模型）。只有当你能在 `title`+`summary` 里指出**明确证据**说明这条与
「求职 + 上述技术方向」无关时，才把它放进 `skipped`：

```json
{"id": "...", "reason": "off-direction", "evidence": "摘要原文照抄的关键短语，说明为何与算法求职无关"}
```

允许的 `reason`：`off-direction`（学科/领域明显无关，如法学、教育学、医学、天文、
无线感知、纯艺术、纯数学）、`placeholder`（占位/测试条目，如标题为「测试」且无实质内容）、
`job-category`（岗位类条目，请照常深读**不要**skip，除非摘要无实质信息）。

**默认是深读，不是跳过。** 宁可写得简洁，也不要为了省事而 skip。skip 必须逐条可被复核。
被 skip 的条目仍留在卡片库可搜索，只是不占深读名额。

### 2.2 `mode == "full"`：每条都要写完整对象

```jsonc
{
  "id": "<原样>",
  "tldr": "≤60 字，直接说它做了什么/结论是什么，不要写“本文提出了一种方法”这类空话",
  "keyPoints": ["3-5 条，每条 ≤40 字，只能来自摘要"],
  "why": "≤80 字：为什么对多模态/后训练/世界模型/生成式方向求职者重要",
  "difficulty": "easy|medium|hard",
  "tags": ["3-6 个英文小写标签"],
  "entities": ["摘要里出现的方法名/模型名/机构名"],
  "diagram": { ...见 3... },
  "concepts": [ ...见 4，1-3 个... ],
  "formulas": [ ...见 5，1-2 个；确实没有公式就给 [] ... ],
  "selfCheck": {
    "claims": ["能从摘要直接证实的断言，逐条列"],
    "uncertain": ["不确定、需要人工核实的，逐条列；没有就写 []"]
  },
  "teaching": { ...见 6，十项必填... }
}
```

### 2.3 `mode == "backfill"`：只写 `missing` 里列的层

* **只输出 `{"id": "...", "<缺失层>": {...}}`**，不要重复输出 `existingEnrichment` 里已有的内容
  （合并脚本会把新层并进旧对象，旧字段保留）。
* 但要先读 `existingEnrichment`，让补的层**与已有 tldr / 概念名 / 图解标题一致**，不要自相矛盾。
* 本次 backfill 的 `missing` 全部是 `formulas`：为这两个仓库补 1-2 条**可代码化**的核心公式
  （五层齐全），`sources[].url` 必须取自输入里已有的 `url`/`sources`。

## 3. `diagram`（每条必有一个图解）

```jsonc
{
  "kind": "flow|architecture|curve|matrix|timeline",
  "title": "中文标题 ≤20 字",
  "caption": "一句话：这张图想让你记住什么",
  "svg": "<svg ...>...</svg>",   // 方式 A，优先
  "spec": {"type": "flow", "nodes": [{"label": "输入", "detail": "..."}],
           "edges": [{"from": 0, "to": 1, "label": "..."}]},   // 方式 B
  "alt": "给读屏软件的一行文字替代（必填）"
}
```

* **方式 A（SVG）**：推荐用于 `flow` / `architecture`。必须自包含：有 `viewBox`、
  不出现 `<image>` `<use>` `<style>` `<script>`、不出现 `url()`、不出现 `on*=` 事件属性。
  颜色只用 `currentColor` / `var(--accent)` / `var(--fg-1)` / `var(--line-1)`。
  所有 `font-size` ≥ 13。宽高比 16:9 ~ 16:6（如 `viewBox='0 0 480 240'`）。
* **方式 B（spec）**：适合 `matrix`（对比表）、`timeline`（时间线）、`curve`（曲线）。
  `curve` 的 `nodes` 用 `{"label": "...", "value": 数字, "detail": "..."}`。
* 可以**同时**给 svg 和 spec；前端优先用 svg。**画不出来不要编** —— 用 spec 画朴素流程即可。
* 可直接改写这个竖排流程模板（保证合规）：

```
<svg viewBox='0 0 480 240' xmlns='http://www.w3.org/2000/svg' role='img' aria-label='...'>
<rect x='56' y='16' width='368' height='38' rx='8' fill='none' stroke='var(--line-1)' stroke-width='1.4'/>
<text x='72' y='40' font-size='14' text-anchor='start' fill='currentColor' font-weight='bold'>第一层</text>
<text x='408' y='40' font-size='13' text-anchor='end' fill='currentColor'>一句话细节</text>
<line x1='240' y1='54' x2='240' y2='62' stroke='var(--line-1)' stroke-width='1.6'/>
<polygon points='240,70 236,62 244,62' fill='var(--line-1)'/>
<rect x='56' y='70' width='368' height='38' rx='8' fill='none' stroke='var(--line-1)' stroke-width='1.4'/>
<text x='72' y='94' font-size='14' text-anchor='start' fill='currentColor' font-weight='bold'>第二层</text>
<text x='408' y='94' font-size='13' text-anchor='end' fill='currentColor'>一句话细节</text>
</svg>
```
（继续同样的 `line`+`polygon`+`rect`+两段 `<text>` 模式往下排，`y` 每次 +54；最后一条不加箭头。）

## 4. `concepts`（1-3 个抽象概念，每个 9 个字段都要有）

```jsonc
{
  "name": "概念名（English Term）",
  "readable": "大白话解释 ≤100 字，面向有深度学习基础但没读过这篇的人",
  "analogy": "生活类比，必须具体可想象，禁止“就像优化一样”这种空话",
  "analogyBreaksDown": "这个类比在哪里失效 ≤120 字（比类比本身值钱，必填）",
  "mechanism": "关键设计选择 + 它解决了什么 ≤120 字",
  "visual": "纯文本可视化方案：画什么轴、什么形状、什么颜色代表什么",
  "prerequisites": ["读它之前需要会什么"],
  "selfTest": ["3 道自测题，答对才算学会"],
  "formula": "有核心公式就给 LaTeX；没有就给空字符串 \"\""
}
```

## 5. `formulas`（1-2 个，五层齐全）

```jsonc
{
  "id": "f-<kebab-slug>",
  "name": "公式中文名（English Name）",
  "category": "multimodal|posttraining|worldmodel|generative|rl|agent|foundation|engineering",
  "latex": "LaTeX 源码",
  "symbols": [["符号", "含义"], ["符号", "含义"]],
  "derivation": ["第 1 步：动机 + 式子", "第 2 步：…（2-5 步）"],
  "analogy": "生活类比",
  "pitfalls": ["面试易错点", "…"],
  "code": "可运行的 PyTorch/Python 片段（10 行内，能说明该公式怎么算）",
  "sources": [{"title": "原文标题", "url": "<只能取自该条目已有的 url>"}]
}
```

* `id` 用 `f-` 前缀 + 英文小写 slug，**全批次内不要重复**；与你条目已有的公式 id 不要冲突。
* 摘要没有给出精确公式形式时，写通用形式并在 `selfCheck.uncertain` 标
  「公式为按摘要重建的通用形式，需核对原文」。
* 纯链接/仓库/清单类卡片（`summary` < 400 字且没给方法细节）允许 `"formulas": []`。
* `latex` 必须能被 KaTeX 渲染：**不要用** `\begin{align}`、`\text{}` 里套中文、
  自定义宏、`\substack`、`\bm`。用 `\mathrm{}`/`\operatorname{}`、`aligned` 环境或分行写。

## 6. `teaching`（十项，全部必填；用至少 3 种不同方式讲同一件事）

```jsonc
{
  "progressive": [
    {"level": "一句话", "text": "≤40 字，外行也能听懂"},
    {"level": "入门",   "text": "≤120 字，有深度学习基础即可"},
    {"level": "进阶",   "text": "≤200 字，说清关键设计选择与取舍"},
    {"level": "专家",   "text": "≤260 字，与其它方法对比、适用边界"}
  ],
  "socratic": [ {"q": "如果不做这一步会怎样？", "a": "≤100 字"},
                {"q": "换成更简单的做法为什么不够？", "a": "≤100 字"} ],
  "mechanism": "≤200 字，说清『为什么必须这样设计』，不是『它做了什么』",
  "boundary": "≤160 字，什么时候不适用/会失效",
  "analogyBoundary": "≤140 字，类比在哪里不再成立",
  "misconceptions": ["2-3 条面试里容易被扣分的错解 ≤80 字"],
  "ownAnalysis": "≤220 字，把摘要与已知方法联系起来或指出可疑处；推断必须标「（推断）」",
  "officialNotes": [ {"position": "论文/官方口径（只依据摘要）", "source": "来源名或已有 url"} ],
  "interviewAnswer": "≤200 字，第一人称，像在面试现场说出来",
  "studyPath": {"prerequisites": ["..."], "nextSteps": ["..."]}
}
```

`officialNotes` 没有权威口径依据时写 `[]`。不要把整段摘要抄进 `progressive[3].text`。

## 7. 写之前的自检

* [ ] 每个 item 都出现在 `entries` 或 `skipped` 里，`id` 与输入完全一致，**不多不少**。
* [ ] full 模式：10 个顶层字段齐全；backfill 模式：只补了 `missing` 里的层。
* [ ] 每条的 `diagram` 有 `kind`/`title`/`caption`/`alt`，svg 合规（或给了 spec）。
* [ ] `teaching` 十项齐全，`progressive` 四档齐全。
* [ ] 所有 URL 都来自输入里的 `url` / `sources`。
* [ ] 文件是合法 JSON（读回来验证过）。

完成后，**只回复三行**：批次号、entries 数 / skipped 数、遇到的任何不确定点（一行一个）。
