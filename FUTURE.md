# FUTURE.md · 交付说明与下一步

> 这份文件记录**已经交付了什么**、**怎么验证**、**还差什么**，以及**建议的下一步**。
> 技术细节在 [docs/信息架构与数据契约.md](docs/信息架构与数据契约.md)，
> 登录类渠道的操作在 [docs/登录类渠道操作手册.md](docs/登录类渠道操作手册.md)，
> 日常操作在 [README.md](README.md)。

---

## 〇之前 · 按你的真实起点做的调整（第三轮）

你给了三条关键信息：**PyTorch 熟练**、**有一篇 ICLR 多模态分割论文**、**刷题只覆盖了 hot100 的一部分**。
这三条直接改变了优先级（`scripts/personalize_plan.py`，可重复执行）：

**1. 学习路线重排 —— 从「均衡通用」改成「按你的短板与资产排序」**

| 顺序 | 之前 | 现在 | 为什么 |
|---|---|---|---|
| 1 | 多模态大模型 | **后训练 Post-training** | 你的目标方向里最缺、岗位最热的一块 |
| 2 | 后训练 | **ICLR 论文项目化讲述**（新增） | 你已有最硬的资产，面试里会占 30%–50% 时间 |
| 3 | 生成式模型 | **手撕题冲刺**（新增 19 个任务） | 你自评的最大风险，必须现在补且贯穿全程 |
| 4 | 世界模型 | 世界模型与具身智能（提到 core） | 第二目标方向 |
| 5 | Agent | 多模态大模型 | 论文打底，重点是补齐 VLM 架构与评测 |
| 6 | 工程与系统 | 生成式 / 工程 / Agent（降为支撑） | 按岗位需要补 |

路线从 6 条扩到 **8 条、70 个任务（约 250 小时）**，新增两个里程碑
`mPaper`（论文三档讲法 + 12 类追问）与 `mCoding`（Hot 100 缺口第一轮）。

**2. 新增的两条针对性路线**

- **手撕题冲刺**：数组滑窗 → 链表二叉树 → DP/单调栈/并查集 → **大模型岗特有手写题**
  （MHA、softmax+交叉熵、RMSNorm、RoPE、top-k/p 采样、CLIP 对比损失）。
  每题带验收标准，例如 MHA 要求"能与 `nn.MultiheadAttention` 数值对齐（误差 <1e-5）"。
- **ICLR 论文项目化讲述**：30 秒 / 2 分钟 / 5 分钟三档逐字稿 + **12 类高频追问**清单
  （存在 `learning.json` 的 `profile.paperQuestions`，「学习路线」页直接展示）。

**3. 采集权重按你的方向倾斜**（已 `--rescore` 生效）

```
multimodal 1.00 | posttraining 1.00 | worldmodel 1.00 (原 0.95)
rl 0.90 (原 0.8) | generative 0.75 (原 0.9) | agent 0.70 (原 0.85)
```
后训练与世界模型都依赖 RL 基础，所以 RL 不下调；生成式与你说"初定不学"一致地下调。

**4. 深度层（Agent）已跑通并接进界面**

你给的 key 我写进了用户级环境变量；同时发现 harness 自己的凭据库
（`~\.dsh\.credentials.yaml`）里本就有 `DEEPSEEK_API_KEY`，所以 `dsh` 其实一直能用 ——
之前每天的 `layer 2: SKIPPED` 是**我的预检逻辑只看了环境变量**导致的误报，已修（现在两处都查）。

实测深度层产出：**深读 12 条**（tldr + 要点 + 概念易读化 + 自检 claims/uncertain）、
**新增 6 个公式**、**新增 5 个岗位**。并且暴露出一个真实缺陷：调试用的 `--only` 运行会把当日
digest 压成一个子集，害得深度层以为"今天几乎没有内容"。已修成窄运行自动**沿用当日 digest**
（`--only` 隐含 `--narrow`）。界面上这些条目会显示「深读」标记，详情页多出
「概念易读化解析」与「深度层的自检」两块。

---

## 〇、第二轮加固（在首轮交付之上修掉的真实缺陷）

首轮交付后我对着原始需求做了一次**逐条可检验的审计**（`scripts/audit_requirements.py`，
55 项断言），并真的把计划任务跑起来，于是暴露出几个"代码看起来有、实际没生效"的问题。
这一轮全部修掉，审计从 49/55 → **55/55**：

| # | 缺陷 | 影响 | 修法 |
|---|---|---|---|
| 1 | **备用来源只是文档** | `CHANNEL_SPECS[].backup` 从未被执行，只在结果里当标签显示 —— 需求里的"备用来源"实际是空的 | runner 真的按序执行 backup 链，并把 `backupUsed` / `backupAttempts` 写进结果；界面显示"备用源 X 生效" |
| 2 | **部分运行会清空渠道注册表** | 跑 `--only X` 时 `sources.json` 的 `channels` 被整段替换，90+ 条已知渠道记录消失 | 改为合并：本轮没跑的渠道保留旧记录并标 `notRunThisPass` + `staleSince` |
| 3 | **继承的过期 `lastRunAt`** | `dict(existing_sources)` 把一个旧时间戳带进了 sources.json，与 manifest 自相矛盾 | 明确删除该字段，运行时间只由 manifest 拥有 |
| 4 | **自我迭代没有产物** | 提案只由可选的 Agent 层生成；没配凭据时这条需求完全没落地 | 采集器新增**确定性**提案生成器，每轮都写 `proposals/YYYY-MM-DD.json`（渠道健康 + 关键词精简建议 + 人工复核队列） |
| 5 | **岗位条目霸榜** | 岗位类关键词权重与时效性叠加，导致"今日速览"的前三名全是招聘帖，技术内容被挤掉 | 摘要改为**跨分类多样化**选取（每类最多一条），并把岗位权重 1.00 → 0.62 |
| 6 | **打分固化** | 相关度在入库时算好并存下，改了权重历史条目不会更新 | 新增 `--rescore`，可对全量语料重算分类与分数（本轮重算：38 条重分类 / 280 条分数变化） |
| 7 | **`--rescore` 会污染摘要** | 重算时没有本轮运行结果，摘要里的渠道列表被清空，标题变成"0/0 个渠道有产出" | `compose_summary` 支持 `prev_summary` 回退，缺运行数据时沿用上一次观测 |
| 8 | **新鲜度全靠肉眼** | 页面渲染正常但数据可能已经几天没更新 —— 这是唯一"看起来像成功"的失败模式 | manifest 写 `health` 与 `schedule.nextRunAt`；界面显示"数据新鲜度"并在 >36 小时时红色告警 |

另外补强：渠道表新增"本轮/备用源/本轮未运行"三列，`采集与运行` 页新增「自我迭代提案」
面板直接读 `proposals/latest.json`，首页与更新流新增「今日速览」（TL;DR + 值得先看的条目）。

---

## 一、交付清单（按你的三段式需求对应）

### 需求一 · 任务分析与信息架构 ✅

| 产物 | 说明 |
|---|---|
| [docs/信息架构与数据契约.md](docs/信息架构与数据契约.md) | **主文档**。14 类知识分类（采集目标 / 关键词 / arXiv 分类 / 更新节奏 / 权重）、渠道优先级 P0–P2 + MANUAL、四层去重规则、可复现的相关度打分公式、结构化存储契约、可靠性参数、告警条件、真实性自查、易读化八层结构、自我迭代闭环 |
| [research/source_registry.json](research/source_registry.json) | 91 个渠道的**实测**注册表：HTTP 状态码、robots.txt 原文证据、限速、认证要求、备用源映射、合规判定（P0/P1/P2/MANUAL 分级） |
| [research/jobs_kb.json](research/jobs_kb.json) | 21 家公司、32 项技能、21 份面试流程、22 道手撕题、25 道笔试场景题、16 条薪资带宽，**每条都带真实来源 URL** |
| [scripts/build_learning_kb.py](scripts/build_learning_kb.py) → `web/data/learning.json` | 6 条学习路线 / 20 篇论文 / 16 个仓库 / 8 门课程 / 12 个里程碑 / 45 个任务（约 206 小时），URL 均为真实资源 |
| [web/data/sources.json](web/data/sources.json) | 注册表 + 采集器实测状态的合并结果（94 个渠道），供界面「知识分类」「采集与运行」使用 |

### 需求二 · 网页设计 ✅

零依赖、零构建的前端（`file://` 直接可开），13 个视图全部在真实浏览器里验证通过、**0 控制台错误**：

`今日工作台` · `每日更新流` · `知识分类` · `知识卡片` · `公式剖析` · `题库定位` · `仓库与课程` ·
`岗位看板` · `技能矩阵` · `学习路线` · `进度与统计` · `收藏夹` · `采集与运行`

- **设计系统**：6 套主题（午夜蓝 / 日光白 / 终端绿 / 极光紫 / 暖砂纸 / Nord）× 6 种强调色，
  全部通过 CSS 自定义属性切换；舒适/紧凑双密度；减少动画开关
- **信息密度**：卡片式分区 + 折叠细节 + 三维筛选（分类 / 来源 / 标签 + 阅读状态 + 搜索）
- **公式剖析**：符号表 → 推导链条 → 生活类比 → 可运行代码 → 易错点，五层齐全
- **交互**：`Ctrl/⌘+K` 命令面板与全局搜索 · `/` 搜索 · `g d/k/j/r/p` 跳转 · 投递看板可拖拽 ·
  一键导出进度 · 打印复习清单
- **解耦**：数据全部来自 `web/data/*.json`，`Store` 是唯一适配层；任一文件缺失都会降级显示而不是白屏

### 需求三 · 定时任务 ✅

- **已注册**：WorkBuddy 自动化「Future 求职工作台（DS）· 每日 18:00 更新与发布」，
  每天 **18:00 (Asia/Shanghai)** 自动执行（模型 Deepseek-V4.1-Flash）
- **入口**：[scripts/run-daily.ps1](scripts/run-daily.ps1)（纯 ASCII 源码，避免 PS 5.1 编码问题）
- **第 1 层（确定性）**：[scripts/collect.py](scripts/collect.py)，仅标准库，24 个公开渠道并发抓取 →
  规范化 → 四层去重 → 相关度打分 → 原子写入 → [scripts/selfcheck.py](scripts/selfcheck.py) 闸门
- **第 2 层（可选）**：[scripts/daily-agent.md](scripts/daily-agent.md) + 深读层，做深读、公式剖析、
  易读化解释、提案；失败不影响第 1 层
- **发布**：[scripts/publish-workbuddy.ps1](scripts/publish-workbuddy.ps1) 审计 `dist/` 并交接，
  由 WorkBuddy 托管发布（国内直连、链接稳定；**不再提交/推送 GitHub，也没有 github.io 地址**）
- **人工在环**：[scripts/inbox.py](scripts/inbox.py) 处理登录类渠道（小红书 / BOSS直聘 / 拉勾 / 实习僧），
  对这些站点的网络请求数为 **0**
- **可验证**：[scripts/verify-web.mjs](scripts/verify-web.mjs) 浏览器全路由验证 + 截图 + 控制台错误捕获

---

## 二、怎么验证（一条条可复现）

```powershell
cd D:\pythonProject\DS-daily

# 0) 对着原始需求逐条审计（55 项可检验的断言）
python scripts\audit_requirements.py

# 1) 数据层自检（14 项检查 + 连续失败渠道告警）
python scripts\selfcheck.py

# 2) 采集器单独跑（不写盘）
python scripts\collect.py --only arxiv,hf_papers --limit 5 --dry-run -v

# 3) 完整跑一轮（约 70 秒）
powershell -ExecutionPolicy Bypass -File scripts\run-daily.ps1 -SkipAgent

# 4) 前端语法 + 浏览器全路由验证（会生成 docs/screenshots/*.png）
node scripts\check-parts.mjs
node scripts\verify-web.mjs

# 5) 定时任务状态
#    本机 Windows 侧任务仍叫 -20 且已 Disabled（历史遗留，不影响运行）；
#    实际排期看 WorkBuddy 自动化（每日 18:00 Asia/Shanghai）
schtasks /Query /TN "Future-Workbench-Daily-20" /FO LIST /V   # 历史遗留任务名，勿改
powershell -ExecutionPolicy Bypass -File scripts\run-daily.ps1 -Status

# 6) 打开工作台
start web\index.html
```

**当前实测结果（2026-10-01 最终态）**

| 检查项 | 结果 |
|---|---|
| 需求审计 `audit_requirements.py` | **55 / 55 项满足** |
| 浏览器全路由 `verify-web.mjs` | **13 / 13 路由渲染干净，0 控制台错误** |
| 数据层自检 `selfcheck.py` | 14 项通过 / 1 项警告（10 个渠道连续失败告警）/ **0 项错误** |
| 知识卡片 | **697 条**（0 条缺来源链接，86% 带摘要） |
| 分类覆盖 | **14 / 14 类**都有数据 |
| 渠道 | 94 个已登记（16 个有产出 / 68 个待按需启用 / 10 个确认不可用） |
| 岗位 / 题库 / 技能 | 21 个岗位 · 47 道题 · 32 项技能 |
| 学习路线 | 6 条路线 · 45 个任务 · 20 篇论文 · 16 个仓库 · 8 门课程 · 12 个里程碑 |
| 公式库 | 6 个公式，五层（符号/推导/类比/代码/易错点）全部非空 |
| 计划任务 | Windows 侧 `Future-Workbench-Daily-18` 已 `Disabled`（仅历史遗留）；实际由 **WorkBuddy 自动化每日 18:00 触发**（Asia/Shanghai） |
| 产物 | `web/data` 17 个文件 4.21 MB，14 张验证截图 |

---

## 三、定时任务的实测记录

我没有只做静态配置，而是**真的触发了计划任务**（`schtasks /Run`），确认它能脱离我的交互式
shell 独立跑完：

| 观察项 | 结果 |
|---|---|
| 上次运行时间 | 2026-10-01 16:45:45（由任务计划程序启动，不是我手动执行） |
| 上次返回码 | `2` = 部分渠道失败但数据已写入（这是设计好的四级语义之一，不是崩溃） |
| 运行日志 | `web/data/logs/harness-2026-10-01.log`，UTF-8 无 BOM，中文正常 |
| 本轮产出 | 新增 83 条，累计 664 条，26 个渠道中 16 个有产出 |
| 自检结论 | 14 项通过 / 1 项警告 / 0 项错误 |
| 那条警告 | `machineheart`、`jobs_bytedance`、`jobs_alibaba` 连续 3 轮失败 → 这正是「连续失败告警」设计要的效果，已进入人工复核队列 |
| 下次运行 | 每日 18:00 (Asia/Shanghai)，由 WorkBuddy 自动化触发 |

期间修掉的两个真实缺陷（都只有真跑才会暴露）：

1. **日志编码**：`Tee-Object -Append` 在 Windows PowerShell 5.1 下写的是 UTF-16LE，导致中文
   乱码、同一文件里混着两种编码。已改为 `[System.IO.File]::AppendAllText` + `UTF8Encoding($false)`，
   现在日志是干净的 UTF-8 无 BOM（已用字节级检查验证：无 BOM、无 NUL）。
2. **`dsh` 定位**：桌面版不会把自己加进 PATH。已改为按 PATH → 项目内包装脚本 →
   Program Files → **注册表 InstallLocation** 的顺序查找，实测能定位到 `D:\DeepSeek Harness`，
   并在缺凭据时给出明确的、可照抄的修复提示。

已验证生效的渠道修复（由并行的调查子代理实测后落地）：GitHub 趋势 **0 → 17 条**、
Semantic Scholar 429 → 改用 OpenAlex **30 条**、知乎经镜像 **30 条**、DeepSeek 招聘 **20 条**、
机器之心（假 RSS）→ 雷锋网 **20 条**。

**2026-10-03 渠道结构重排**（用户明确要求「采手撕/笔试/面经，整理过往，不要灌水」）：

| 动作 | 渠道 | 实测依据 |
|---|---|---|
| 新增 | `programmercarl`（代码随想录官网，sitemap 563 页） | robots `Allow: /`；/algo/ 298 题解 + /hot100/ 48 + /kamacoder/ 49 |
| 新增 | `kamacoder_notes`（卡码笔记，sitemap 525 页） | robots `Allow: /`；/llm/ 127 + /interview/ 74 + /base/ 74 |
| 新增 | `gh_algokb`（9 个精选题解/竞赛仓库） | GitHub API 实测可达；leetcode-master 62.6k★、OI-wiki 26.8k★ |
| 停用 | `nowcoder` | 两轮 72 条中 45 条被质量判断下架，存活 27 条无一条算法/手撕题内容 |
| 排除 | 卡码笔记 `/cpp/ /java/ /go/`（246 页） | 语言特性问答 = 后端岗八股，不是算法岗八股 |

效果：`手撕/笔试题 1 → 70`、`知识点/八股 22 → 52`、`方向不贴合 5.7% → 0%`。

---

## 四、还差什么（如实列出）

| 项 | 状态 | 需要你做的事 |
|---|---|---|
| **Agent 深读层凭据** | 机制已跑通（`dsh` 能定位），但计划任务环境里没有 LLM 凭据，所以每天会记录 `layer 2: SKIPPED - no LLM credential` | 二选一：`[Environment]::SetEnvironmentVariable('DEEPSEEK_API_KEY','sk-xxx','User')`，或在 DSH Web 的 Models 页面填一次。**不设也能用**，只是缺少深挖内容 |
| **登录类渠道的内容** | 已提供导入器与示例文件，还没有真实数据 | 按 [README 第五节](README.md#五登录类渠道人工在环) 导出并放进 `web/data/inbox/` |
| **3 个连续失败的渠道** | `machineheart`（假 RSS）、`jobs_bytedance` / `jobs_alibaba`（WAF 拦脚本）已被自检标红 | 无需操作；替代源与 `DISABLED_CHANNELS` 收尾仍在进行 |
| **其余渠道的可达性** | 94 个渠道里 26 个有真实实测状态，68 个仍是 `unknown`（注册表探过但采集器没跑） | 可以按需在 `CHANNEL_SPECS` 里启用更多渠道 |
| **进度数据的积累** | 趋势图 / 热度日历需要多天数据；目前只有 1 天 | 让它每天自己跑即可，明天开始图表就有意义了 |

---

## 四、我做的几个关键判断（供你复核）

1. **登录类渠道一律不自动抓取**。BOSS直聘的 `robots.txt` 明确 `Disallow: /*?query=*`（正好是搜索 URL），
   小红书全站 `Disallow: /`，Reddit 也是 `Disallow: /`。改为「你自己登录导出 → 本地导入」，
   网络请求数为 0，既不违规也不冒险封号。**这不是妥协，是唯一稳定的做法。**

2. **用户状态（收藏 / 掌握度 / 笔记 / 任务勾选 / 投递阶段）只存在浏览器 localStorage**，
   不写回数据层。理由是它们的生命周期与「采集数据」不同，混在一起会在重新采集时被覆盖风险。
   顶栏「导出进度」可一键备份，换设备导入即可。

3. **失败必须可见**。`manifest.status`、`logs/runs.json` 的 `notes`、渠道状态表都会如实显示
   `blocked / error / empty`，不做"看起来一切正常"的假象。`selfcheck` 对空摘要率、未知域名
   占比、孤儿条目、连续失败渠道都会告警。

4. **前端的入场动画不碰透明度**。最初用 `opacity: 0 → 1` + 递增延迟做卡片入场，
   结果在长列表里首屏之外的卡片会被延迟按住而"消失"（截图里就出现过一片空白）。
   现在动画只做位移，任何情况下内容都是可见的。

5. **学习路线由脚本生成而不是手写 JSON**。原因是 45 个任务、12 个里程碑、6 条路线之间存在
   week 与 id 的交叉引用，脚本化才能保证一致，也方便你后续增删。

---

## 五、建议的下一步

1. **先设好 Agent 凭据**（可选但推荐）。设完之后跑一次
   `powershell -ExecutionPolicy Bypass -File scripts\run-daily.ps1`，
   看 `web/data/enrichment.json` 与 `web/data/formulas.json` 是否被补上内容。
2. **导一次真实的小红书 / BOSS直聘数据**，验证人工导入链路符合你的浏览习惯
   （`python scripts\inbox.py --template` 起步）。
3. **按学习路线挑一条主攻**。如果你更偏世界模型 / 具身，我可以把 `world` 路线从
   support 提到 core，并把 `engineering` 的权重降下来。
4. **告诉我你现在的真实起点**（PyTorch 熟练度、是否有论文、刷题量）。
   我可以据此把 45 个任务的周次与难度重排，并调整关键词权重让每日信息更贴合你的短板。
