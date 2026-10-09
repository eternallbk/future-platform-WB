# 2026-10-04 深读批次 · 本轮补充契约（与 INSTRUCTIONS.md 同时生效，冲突时以本文件为准）

先读 `scripts/agent-work/INSTRUCTIONS.md`（完整契约）与 `scripts/daily-agent.md` 第 2 节，
再读本文件，然后读你的输入 `scripts/agent-work/in-<你的批次>.json`。

## A. full 模式 12 个顶层字段（缺一即失败）
`id, tldr, keyPoints, why, difficulty, tags, entities, diagram, concepts, formulas, selfCheck, teaching`

## B. teaching 十项必填，progressive 必须满 4 档
`progressive`(4 档：一句话/入门/进阶/专家), `socratic`(≥2), `mechanism`, `boundary`,
`analogyBoundary`, `misconceptions`(≥2), `ownAnalysis`, `officialNotes`, `interviewAnswer`,
`studyPath`{prerequisites, nextSteps}

## C. diagram 必填
`kind` ∈ {flow, architecture, curve, matrix, timeline}，且 `title`/`caption`/`alt` 齐全。
优先给自包含内联 SVG：必须有 `viewBox`；颜色只用 `currentColor` / `var(--accent)` /
`var(--fg-1)` / `var(--line-1)`；**font-size ≥ 13**；**禁止** `<image>` `<use>` `<style>`
`<script>` `url(` 与任何 `on*=` 事件属性。给不了 SVG 就退化为 `spec`（`type` 取值同上）。

## D. concepts 1–3 个，每个 9 字段齐全
`name, readable, analogy, analogyBreaksDown, mechanism, visual, prerequisites, selfTest(3 题), formula`

## E. formulas 1–2 个（纯链接/清单类卡片允许 `[]`），每个 10 字段
`id`(f-<kebab-slug>，全批不重复), `name`, `category`, `latex`, `symbols`, `derivation`(2–5 步),
`analogy`, `pitfalls`, `code`, `sources`[{title,url}]。
`category` ∈ {multimodal, posttraining, worldmodel, generative, rl, agent, foundation, engineering}。
**`sources[].url` 必须取自该 item 输入里已有的 `url` / `sources[].url`，否则校验报错。**

## F. problem 块（仅当 kind == "problem"）
必须给：`title, number, statement, examples[], approach{idea,steps[],whyItWorks,alternatives[]},
solution{python（可运行，≥40 字符）, python_alt?, notes}, complexity{time,space,why},
pitfalls(≥2), edgeCases(≥1), interviewTips`。
- `complexity.time` / `.space` **必须是大 O 记号**（形如 `O(n log n)`），不接受「比较快」。
- `number` 只填 **LeetCode 题号**；卡码网题（URL 含 `kamacoder`）填 `null`，不要猜。
- 题解**聚合页 / 系列小结**（标题含 小结/汇总/合集/指南/真题（20/题库/刷题攻略 等）：
  **不写** problem 块，按 notes 处理，并在 `selfCheck.uncertain` 写明「本条为聚合页，非单题」。

## G. 模型赛道手撕题（本轮最高优先级）——额外两层，硬性要求
以下 item 若出现在你的批次里，`problem` 块**必须**再加两层：
`f228fcfd7135e465`(手撕Attention)、`c73d5194d929ec92`(手撕FFN)、`9262c69bc12f0945`(手撕LayerNorm+残差)、
`626fb94347658a17`(手撕MHA)、`75ebbbbb519ddf80`(手撕Tiny Transformer)、`32e22928e5f8f424`(手撕Transformer Block)
另外，输入里凡 `track` 标注为 `model`、或标题含「手撕/手写 + 模型结构」的，都按本条处理。

- `problem.variants`：数组，**≥1 条**，每条 `{"name","idea","when","cost"}`
  （同机制的其它写法，例：MHA 可用「单头循环 / einsum / F.scaled_dot_product_attention」三种）。
- `problem.comparison`：数组，**≥2 行**（横向对比表），每行如
  `{"aspect":"显存","optionA":"MHA O(S²)","optionB":"GQA 更省 KV","note":"..."}`。

## H. LaTeX 禁令（第二条门禁会扫，违反即失败）
禁止：`\varnothing`、`\dagger`、`\underset`、`\begin{align}`、`\bm`、`\substack`、
`\newcommand`、`\def `、`\tag{`。`\text{}` 内**不得有中文**。花括号必须配对。
需要文字就用 `\mathrm{}` / `\operatorname{}`，需要多行就用 `aligned`。

## I. 铁律
禁止编造（结论必须能在该 item 的 title/summary 找到依据，不确定写入 `selfCheck.uncertain` 标「待核实」）；
禁止编造 URL；中文输出（`tags` 用英文小写）；只写你自己的 `out-<批次>.json`，不改 `web/data/` 与前端；
严格 JSON（UTF-8 无 BOM、无注释、无尾逗号）。**写完必须读回来验证 JSON 合法。**

## J. 收尾
只回复 3 行：批次号、entries 数 / skipped 数、不确定点（一行一个）。
