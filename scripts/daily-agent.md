# {{DATE}} · Future 工作台每日深读任务

你正在为「Future · 求职学习工作台」执行每日常规深读。工作目录 `{{ROOT}}`。
确定性采集层已经跑完，原始数据已经落盘。你的工作是**在已有数据上做归纳、剖析与易读化**，
并把结果写回数据层。

---

## 0. 铁律（违反即视为任务失败）

1. **禁止编造。** 你写的每一条结论都必须能在 `web/data/items/index.json` 的标题/摘要里
   找到依据。不确定就写「待核实」，绝不猜。
2. **禁止编造 URL。** 只能使用数据里已有的 `url` / `sources[].url`。不要"推测"论文链接。
3. **不抓取需要登录的站点**（小红书 / BOSS直聘 / 拉勾 / 实习僧）。若需要其中内容，
   在提案文件里写明"需人工导入"，不要尝试自动化。
4. **不改前端代码。** 只写 `web/data/` 下的文件，且只写下面列出的文件。
5. **不减小已有数据。** 写 JSON 前先读旧文件，做合并而不是覆盖。
6. **UTF-8 无 BOM。** 用 Python 写文件（`json.dump(..., ensure_ascii=False)`），
   不要用 PowerShell 的 `Set-Content` / `>`（会写 BOM 并可能损坏中文）。

---

## 1. 读入

1. 读 `web/data/manifest.json`：拿到本轮 `newItems`、`status`、失败的渠道列表。
2. **读 `web/data/deep-read-plan.json` —— 这是你的工作清单，不要自己另挑条目。**
   它由 `scripts/plan_deep_read.py` 生成，包含两个清单：
   - **`queue`**：**尚未深读**的条目。已做质量闸门（求职吐槽、泛化提问、内推码广告、
     纯薪资讨论、与技术无关的社区热点、**纯资讯、材料性过低、方向不贴合的求职内容**
     标为 `skimmed`，**不要**深读，它们仍留在卡片库可搜索、参与去重）
     与配额分配（按分类 2–10 条）。
   - **`backfill`**：**已经深读但解析不完整**的条目（缺图解 / 缺公式 / 缺 `teaching`）。
     这些是"有的卡片有解析、有的只有摘要"的历史遗留。**必须一并补全**：
     按 `missing` 字段补齐缺的那几层，不要重写已有内容（合并而非覆盖）。
     `backfillWeight` 越高越优先。
   - **`problemBankQueue`**：按 **CodeTop 真实被考频度**排序、**尚未产出「可照着刷」解析**
     的高频手撕/笔试题。这是**优先级最高的一批**：它回答的是"读者最可能被问到的题，
     哪些还没有代码 + 图解"。每条的 `itemId` 就是写入 `enrichment.json` 的键，
     契约见第 2.2 节。它可能包含 `queue` 里没有的老题 —— 老题不会被重新采集，
     所以只能靠这个清单补。
   三个清单**都**要处理，**每一条都必须产出完整解析（含图解，见第 2 节）**。
   三者都为空时直接跳到第 5 步（只写运行备注）。

   **`needsFetch: true` 的条目不能跳过。** 这类条目在采集层只拿到了标题和链接
   （Hacker News 等源就是这样，源站不给摘要）。读者明确说过："看到某个好的手撕算法
   或领域核心工作但是源信息中没有解析的，你也可以自己逐条深度解析并采集，
   不需要担心 token 消耗。" 所以：
   - 先用 `sources` / `url` 把原文取下来（WebFetch），再按第 2 节的契约解析；
   - 取不到原文时，在 `skipped` 里写明**具体原因**（404 / 需要登录 / 只有标题页），
     不要静默丢弃，也不要凭标题编内容；
   - 判定为"内容与标题无关"的，同样走 `skipped` 并写 evidence。

   队列里每条都带 `kind`（`paper` 论文 / `repo` 仓库 / `interview` 面经 / `problem` 手撕笔试题 /
   `notes` 知识点八股 / `job` 岗位 / `news` 资讯）与 `materiality`（知识材料性 0–1）。
   **深读的价值排序是：可复用的知识 > 一次性的经历**。所以：
   - 论文/仓库：讲清**机制、公式、与已有方法的差别**，不要复述摘要；
   - 面经（`interview`）：提炼**流程、考点、追问链**，让人能照着准备；
   - 手撕题（`problem`）：给**可运行参考实现 + 复杂度 + 易错点**；
   - 知识点/八股（`notes`）：给**原理推导 + 常见误解 + 面试怎么答**。
   这三类是你最应该持续积累的资产，不要因为它们"不是新论文"就写得敷衍。
3. 读 `web/data/digest/today.json` 与 `web/data/items/index.json` 取这些条目的原文摘要。
4. 读 `config/collector.config.json` 了解关注方向与权重。
5. 读 `web/data/formulas.json` 已有的公式 id，避免重复造。

> 为什么改成「按清单做」而不是「自己挑最相关的 8–12 条」：
> 质量优先需要**可复核**的选择依据。清单是确定性生成的，你可以质疑它、人工改它，
> 下一轮还能对比「计划 vs 实际」来评估筛选规则好不好。

---

## 2. 深读：每条都必须有「图解」，并且要**教会**人

只写摘要等于没做。每条深读必须同时满足三件事：

1. **有图解**（下面给出 schema）；
2. **有 `teaching` 讲解层**（下面给出 schema）—— 用**多种方式**讲同一件事；
3. 讲解与图解**互相配合**：图负责建立直觉，文字负责说清机制与边界。

### 2.0 `teaching`：用至少 3 种不同方式讲同一件事

要求「讲解、教学、官方口径、你自己的思考」结合。不要只挑一种方式 ——
同一个概念，用不同角度讲，读者才可能在面试里讲清楚。**至少选 3 种**，
并且必须包含 `mechanism`、`boundary`、`analogyBoundary` 三项（它们是"真懂"的证据）：

```jsonc
"teaching": {
  // ① 由浅入深：先给一个能听懂的版本，再逐层加细节
  "progressive": [
    {"level": "一句话", "text": "≤40 字，外行也能听懂"},
    {"level": "入门",   "text": "≤120 字，有深度学习基础即可"},
    {"level": "进阶",   "text": "≤200 字，说清关键设计选择与取舍"},
    {"level": "专家",   "text": "≤260 字，与其它方法的对比、适用边界"}
  ],
  // ② 苏格拉底式追问：用问题链把读者带到答案
  "socratic": [
    {"q": "如果不做这一步会怎样？", "a": "≤100 字"},
    {"q": "换成更简单的做法为什么不够？", "a": "≤100 字"}
  ],
  // ③ 机制：关键设计 + 它解决了什么（必填）
  "mechanism": "≤200 字，说清『为什么必须这样设计』，而不是『它做了什么』",
  // ④ 边界：什么时候不适用、什么情况下会失效（必填）
  "boundary": "≤160 字，失效条件与适用前提",
  // ⑤ 类比的失效点：类比在哪里不再成立（必填，比类比值钱）
  "analogyBoundary": "≤140 字",
  // ⑥ 常见误解：面试里容易被扣分的错解
  "misconceptions": ["≤80 字/条，2-3 条"],
  // ⑦ 你自己的思考：把摘要信息与已知方法联系起来，或指出可疑之处
  "ownAnalysis": "≤220 字。允许推理，但必须标明是推理而非原文结论",
  // ⑧ 官方/权威口径：只引用数据里已有 url 的来源；没有就写空数组
  "officialNotes": [{"position": "论文/官方怎么说", "source": "来自数据里的 url 或来源名"}],
  // ⑨ 面试怎么答：一段可以照说的答法
  "interviewAnswer": "≤200 字，第一人称、像在面试现场说出来",
  // ⑩ 学习建议：读它之前该先会什么、读完该练什么
  "studyPath": {"prerequisites": ["..."], "nextSteps": ["..."]}
}
```

**纪律**：
- `ownAnalysis` 里凡是推断，必须显式写「（推断）」或「（待核实）」，不要冒充原文结论。
- `officialNotes` **只能**用数据里已有的 `url`/来源名；编链接视为任务失败。
- 讲不清的部分，就在 `selfCheck.uncertain` 里写「待核实」，**不要用空话填满**。
- 不要把整段摘要抄进 `progressive[3].text`；那是采集层已经做的事。

### 2.1 `diagram`（硬性要求）

**`queue` 与 `backfill` 里每一条都要产出 `diagram`。** 图解必须**自包含**：
用内联 SVG 或结构化描述，**不要**依赖外部图片（无法离线、无法版本控制、链接会烂）。

```jsonc
"diagram": {
  "kind": "flow | architecture | curve | matrix | timeline",
  "title": "图的中文标题（≤20 字）",
  "caption": "一句话说明这张图想让你记住什么",
  // 方式 A（优先）：内联 SVG。必须自包含：viewBox、无外部引用、
  // 颜色只用 currentColor / var(--accent) / var(--fg-1) / var(--line-1)
  "svg": "<svg viewBox='0 0 480 200' xmlns='http://www.w3.org/2000/svg'>...</svg>",
  // 方式 B：结构化描述，前端按 type 用 CSS 画。适合流程/对比/时间线
  "spec": {
    "type": "flow",
    "nodes": [{"label": "输入", "detail": "图像 patch"}, {"label": "编码器", "detail": "ViT-L"}],
    "edges": [{"from": 0, "to": 1, "label": "patch 化"}]
  },
  "alt": "给读屏软件的文字替代（必填，一行）"
}
```

**画图纪律**：
- SVG 里不要出现 `<image>`、外链 `<use>`、`style` 里的外部 `url()`。
- 宽高比控制 16:6 ~ 16:9，`viewBox` 留 12px 边距，字号 ≥ 13（手机上要看得到）。
- 颜色只用主题变量或 `currentColor`，六套主题都要能正常显示。
- `spec.type` 只能是 `flow` / `architecture` / `curve` / `matrix` / `timeline`。
- 画不出来**不要编**：宁可用 `spec` 画一个朴素流程，也不要塞一个自己都解释不了的复杂 SVG。

对清单里的每条，产出一个 `enrichment` 对象：

```json
{
  "id": "<与 index.json 中完全一致的 id>",
  "tldr": "一句话结论，≤60 字，中文，直接说它做了什么/结论是什么",
  "keyPoints": ["3-5 条要点，每条 ≤40 字，必须来自原文摘要"],
  "why": "为什么对『多模态/后训练/生成式/世界模型』方向求职者重要，≤80 字",
  "difficulty": "easy|medium|hard",
  "tags": ["3-6 个英文小写标签"],
  "entities": ["方法名/机构名/模型名，来自原文"],
  "diagram": { "kind": "...", "title": "...", "caption": "...", "svg": "...", "spec": {}, "alt": "..." },
  "concepts": [
    {
      "name": "抽象概念名，例如 Group Relative Policy Optimization",
      "readable": "用大白话解释，≤100 字，面向有深度学习基础但没读过这篇论文的人",
      "analogy": "一个生活类比，必须具体、可想象，不要用『就像优化一样』这类空话",
      "analogyBreaksDown": "这个类比在什么地方失效 —— 比类比本身更重要，逼你说出真实边界",
      "mechanism": "机制：关键设计选择与它解决了什么，≤120 字",
      "visual": "用纯文本描述一个可视化方案：画什么轴、什么形状、什么颜色代表什么",
      "prerequisites": ["读它之前需要会什么"],
      "selfTest": ["3 道自测题，能答对才算学会"],
      "formula": "如果该概念有核心公式，给出 LaTeX 与符号表；没有则留空字符串"
    }
  ],
  "problem": { "...见 §2.2，仅当 kind == problem 时必填..." },
  "formulas": [
    {
      "id": "f-<slug>",
      "name": "公式中文名（英文名）",
      "category": "multimodal|posttraining|worldmodel|generative|rl|agent|foundation|engineering",
      "latex": "LaTeX",
      "symbols": [["符号", "含义"]],
      "derivation": ["逐步推导，2-5 步，每步一句话说清动机"],
      "analogy": "生活类比",
      "pitfalls": ["面试易错点"],
      "code": "可运行的 PyTorch/Python 片段（若公式可代码化）",
      "sources": [{"title": "原文标题", "url": "必须来自数据里已有的 url"}]
    }
  ],
  "selfCheck": {
    "claims": ["你能从摘要中直接证实的断言，逐条列出"],
    "uncertain": ["你不确定、需要人工核实的地方，逐条列出；没有就写空数组"]
  }
}
```

**公式剖析必须四层齐全**：符号表 → 推导链条 → 生活类比 → 可运行代码 → 易错点。
这是工作台「公式剖析」页面的核心价值，缺层会被视为未完成。

### 2.2 `problem`：手撕题 / 笔试题必须给「能照着刷」的解析（仅 `kind == problem`）

读者对题库的原话是：**「直接给出仓库链接虽然可以保留，但我更希望你能根据题库信息，
阅读并自己深度解析相关手撕题、算法题等具体问题，附带深入的代码解析或配图解析」**。
所以对 `problem` 类型的条目，光有 tldr + 概念 + 图解是**不够**的：必须真的解出这道题。
`problem` 是**必填**字段（`apply_agent_out.py` 会对 `kind == problem` 的条目做硬校验）。

```jsonc
"problem": {
  // 规范题目名与题号：能从题干/链接读出来就写，读不出写 null。**不要猜题号。**
  "title": "两数之和",
  "number": 1,                       // LeetCode 题号，可为 null
  "difficulty": "easy|medium|hard",
  // 题面：用你自己的话把题目讲清楚（输入/输出/约束）。这是唯一允许「重述」的地方，
  // 但不得引入源信息里没有的约束或示例数字。
  "statement": "≤220 字",
  "examples": [{"input": "nums=[2,7,11,15], target=9", "output": "[0,1]", "why": "≤40 字"}],
  // 思路：先说人话，再说步骤，再说为什么对。三样都要，否则读者只能背代码。
  "approach": {
    "idea": "核心思路，≤160 字",
    "steps": ["1. …", "2. …", "3. …"],           // 3-6 步
    "whyItWorks": "为什么这样做是对的（正确性论证），≤150 字",
    "alternatives": [
      {"name": "暴力枚举", "complexity": "O(n²)/O(1)", "when": "数据规模很小或面试只想先要一个 baseline"}
    ]
  },
  // 参考实现：只要能跑。Python 必填；有更省内存/更快的写法再加 "python_alt"。
  "solution": {
    "python": "可直接运行的 Python 代码（含必要 import 与函数签名）",
    "python_alt": "可选：另一种解法的代码",
    "notes": "实现细节与边界处理，≤160 字"
  },
  "complexity": {"time": "O(n)", "space": "O(n)", "why": "≤80 字，说清哪一步决定了复杂度"},
  "pitfalls": ["面试写挂过的地方，2-4 条，每条 ≤60 字"],
  "edgeCases": ["空输入 / 单元素 / 全相同 / 溢出 …，1-3 条"],
  "interviewTips": "面试怎么写、怎么讲、卡住了怎么争取提示，≤180 字"
}
```

**纪律（比格式更重要）**：

- **必须真的把题解出来**：`solution.python` 要是能跑通这道题的代码，不是伪代码、
  不是「思路是……」。写不出可运行代码时，改为在 `skipped` 里写明原因（例如题面信息
  不足以确定约束），**不要**用空壳代码占位。
- **复杂度必须具体**：`O(n)` / `O(n log n)` / `O(V+E)` 这种，不要写「比较快」。
- **`examples` 里的数字必须自洽**：不要编输入；如果源信息里没有例子，用
  **你自己构造的、能被你的代码验证的**最小例子，并在 `selfCheck.uncertain` 里
  标注「示例为自行构造」。
- **图解仍然必须有**：算法类题画「执行过程 / 指针移动 / 状态转移」，手撕算子类题画
  「张量形状流转」。图要能替代一段文字解释，不是装饰。
- 题目是**可复用资产**，不是新闻：`tldr` 写这道题考什么，不要写「XX 公司考过」。
- 如果条目其实是「题解聚合页 / 系列小结」而不是一道具体的题（例如
  「各个大厂笔试真题（2026）」），就按 `notes` 处理常规 enrichment，
  **不要**硬凑一个 `problem` 块 —— 那种情况下在 `selfCheck.uncertain` 里写明
  「本条为聚合页，非单题」。
- **`number` 只填 LeetCode 题号。** 代码随想录的卡码网页面标题形如「102. 沉没孤岛」，
  它的 URL 是 `.../kamacoder-0102-sink-isolated-islands.html`。这里的 102 是
  **卡码网自己的题号**，不是 LeetCode 102（二叉树的层序遍历）。卡码网的题
  在题库里用 `km-<n>` 键，`number` 留 null；填进 `number` 会让两道不同的题
  在页面上共用同一个 `#102` 徽标，并互相顶掉标题与解析。
  判据：URL 里出现 `kamacoder` 就是卡码网。题库构建时会自动判命名空间
  （`build_problem_bank.py` 的 `problem_identity()`），`selfcheck` 每天会断言一次；
  你写的 `problem.number` 要与它一致，不要另立一套。

### 2.3 `repo`：仓库要给「怎么读、核心在哪」（仅 `kind == repo`）

读者要的是「各领域核心工作」而不是仓库链接。所以仓库类条目除了常规各层外，
**必须**在 `teaching.officialNotes` 里指明核心文件/入口（能读到就写，读不到写「待核实」），
并在 `concepts[].visual` 里描述「从哪个模块读起、数据怎么流」。禁止只复述 README 的一句话简介。


---

## 3. 岗位信息合并

如果本轮 digest 里出现招聘类条目（`category == "job"`），或字节/腾讯/阿里等招聘接口
返回了新的算法实习岗位：

1. 读 `web/data/jobs.json`（已有人工整理 + 每日增量的岗位库）。
2. 把新岗位**追加**到 `jobs` 数组，字段与既有条目保持一致
   （`id, company, title, directions, cities, pay, duration, conversion, open, applyUrl, sources, relevance`）。
3. `id` 用 `slug(company)-slug(title)` 保证稳定，重复岗位不要重复插入。
4. `directions` 只能用这些取值：`multimodal, post-training, world-model, generative, rl, agent, infra, embodied`。
5. 岗位信息里任何数字（日薪、名额、截止时间）若无法从原文确认，写 `null` 并在 `notes` 里标"待核实"。

---

## 4. 提案（自我迭代）

写 `web/data/proposals/{{DATE}}.json`：

```json
{
  "date": "{{DATE}}",
  "generatedBy": "daily-agent",
  "channelHealth": [{"id": "openreview", "status": "blocked", "evidence": "HTTP 403", "suggestedAction": "改为人工导入或寻找替代源"}],
  "taxonomyProposals": [{"action": "add|split|merge|reweight", "category": "worldmodel", "reason": "...", "proposedKeywords": ["..."]}],
  "keywordProposals": [{"category": "posttraining", "add": ["..."], "remove": ["..."], "reason": "近 7 日本方向命中率偏低/噪音偏高"}],
  "newChannelProposals": [{"id": "...", "why": "...", "verifiedUrl": "...", "authRequired": false}],
  "noiseReport": {"overBroadKeywords": ["..."], "underCoveredCategories": ["..."]},
  "humanReviewQueue": ["需要我（人类）确认的事项，逐条写清楚要确认什么"]
}
```
所有提案都只是**建议**，绝不自动生效；它们在「采集与运行」页面显示，等人工确认。

---

## 5. 写回

用 Python 脚本（放在 `scripts/` 下，例如 `scripts/apply_enrichment.py`，可复用）完成：

1. **`web/data/enrichment.json`** — 形如 `{"generatedAt": "...", "byId": {"<item id>": {...enrichment...}}}`。
   读旧文件后合并（新值覆盖同 id 的旧值），不要丢历史。
2. **`web/data/formulas.json`** — `{"generatedAt": "...", "source": "seed+daily", "formulas": [...]}`。
   读旧文件，按 `id` 去重后追加本轮的新公式；保留所有已有公式。
3. **`web/data/jobs.json`** — 见第 3 步（增量合并）。
4. **`web/data/proposals/{{DATE}}.json`** — 见第 4 步。
5. **`web/data/logs/agent-{{DATE}}.json`** — 运行记录：
   `{"date","startedAt","finishedAt","status","enrichedCount","formulaCount","newJobs","notes","errors"}`。

写完后运行一次校验：

```bash
python -c "import json,glob;[json.load(open(f,encoding='utf-8')) for f in glob.glob('web/data/**/*.json',recursive=True)];print('all json ok')"
```

---

## 6. 报告

最后用中文输出一份简短汇报（≤200 字 + 列表）：

- 本轮深读了几条、新增几个公式、几个岗位；
- 数据层健康状况（哪些渠道失败、是否需要人工介入登录类渠道）；
- 你在 `selfCheck.uncertain` 里标记的、需要我确认的事项；
- 下一步建议（1–3 条，具体可执行）。

---

## 附：绝对不要做的事

- 不要把整篇论文摘要复制进 `tldr`（那是采集层已经做的事）。
- 不要生成"这条很重要，建议阅读"这类无信息量的句子。
- 不要为了凑数给低相关度条目写 enrichment。
- 不要把无法验证的内容写成确定语气。
- 不要在 `notes` 里写英文以外的花哨格式；工作台渲染的是纯文本/Markdown 子集。
