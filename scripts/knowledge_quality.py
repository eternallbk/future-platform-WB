#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
knowledge_quality.py — 全工作台唯一的「知识质量」判断层。

为什么要单独一个模块
  在这之前，「这条内容值不值得留 / 值不值得深读」这件事被写在三个地方，
  而且三份规则互不一致：

    collect.py        minRelevance 一个全局分数门槛（45 分）
    plan_deep_read.py 一套 NOISE_RULES（4 条）+ category_mismatch
    prune_items.py    另一套 NOISE_RULES（5 条）+ 自己的 channel_quality_floor
    selfcheck.py      第三套「未分类占比」的说法

  结果是：同一张卡片在「采集」这里是好的、在「深读队列」那里被 skim、
  在「清理」那里又不必下架 —— 没有任何一处能回答用户真正关心的问题：
  **库里积累的到底是不是可复用的知识？**

  用户的原话是：工作台收集的应该是「各个领域的核心 / 关键 / 扩展知识、算法深度解析、
  相关岗位与大厂面经、八股知识、算法知识点」的**不断积累**，而不是「一看最新或关联就
  放进来」的资讯。所以这个模块给出的就是这条判断本身，并让四处共用同一个答案。

它提供什么
  classify_kind(item)   -> 知识类型：paper / repo / interview / problem / notes /
                           course / job / news / other
  noise_flags(item)     -> 命中「不是知识」的硬规则（吐槽、泛问、内推码、薪资帖、
                           与技术无关的社区热点、纯推广）
  materiality(item)     -> 0–1 的**知识耐久性**：有实质内容、可复用、有证据
                           （代码 / 同行评审 / CCF / star / 公式 / 面经流程），
                           而不是「刚发布」这一件事
  importance(item)      -> 0–100 的重要度 + core/useful/noise 三档（清理用）
  depth_value(item)     -> 深读优先级（配额规划用）
  quality_report(...)   -> 聚合指标（自检与自我迭代提案共用）

契约
  * 只用标准库；不改任何既有字段的语义，只**新增** kind / materiality / qualityFlags。
  * 判定必须可解释：每条结论都带原因字符串，写进报告而不是黑箱。
  * 宁少勿滥：拿不准时判为低价值，但**不要**把有实质内容的技术材料误杀。
  * 这是"判断"，不是"决定"：真正的下架仍由 prune_items.py 的 --apply 执行。
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"
CST = timezone(timedelta(hours=8))

# ---------------------------------------------------------------------------
# 方向定义（用户画像里的四个目标方向 + 求职相关的三类）
# ---------------------------------------------------------------------------
TARGET_DIRECTIONS = ("multimodal", "posttraining", "worldmodel", "generative")
# 求职侧：这三个方向靠「面经 / 手撕题 / 八股笔记 / 岗位」积累
CAREER_DIRECTIONS = ("coding", "exam", "job")

KINDS = ("paper", "repo", "interview", "problem", "notes", "course", "job", "news", "other")

KIND_ZH = {
    "paper": "论文",
    "repo": "开源仓库",
    "interview": "面经",
    "problem": "手撕/笔试题",
    "notes": "知识点/八股",
    "course": "课程",
    "job": "岗位",
    "news": "资讯",
    "other": "其它",
}

# 类型本身的知识耐久性：论文/面经/手撕题是能反复用的资产，资讯几乎不是。
KIND_DURABILITY = {
    "paper": 0.90,
    "interview": 0.90,
    "repo": 0.85,
    "problem": 0.85,
    "notes": 0.80,
    "course": 0.70,
    "job": 0.55,
    "other": 0.45,
    "news": 0.15,
}

# ---------------------------------------------------------------------------
# 渠道先验：某些渠道产出什么类型是结构性的，不必靠关键词猜
# ---------------------------------------------------------------------------
CHANNEL_KIND = {
    "arxiv": "paper", "openreview": "paper", "hf_papers": "paper", "s2": "paper",
    "aclanthology": "paper", "hf_blog_rss": "notes", "openai_rss": "news",
    "github": "repo", "gh_trending": "repo", "hf_models": "repo",
    # gh_algokb 是「精选算法题解仓库」渠道：每一条就是一个 GitHub 仓库。
    # 不加这条先验时它们会靠标题里的「题解/算法题」被分类器判成 problem，
    # 于是 106 条题解页与 17 个仓库混在同一个 kind 里 —— 深读时给的产出形态
    # （「可运行实现」vs「读源码讲机制」）本来就是两回事。
    "gh_algokb": "repo",
    "jobs_bytedance": "job", "jobs_tencent": "job", "jobs_alibaba": "job",
    "jobs_zhipu": "job", "jobs_moonshot": "job", "jobs_deepseek": "job",
    "jobs_minimax": "job", "jobs_shailab": "job",
    "boss": "job", "lagou": "job", "shixiseng": "job",
    "machineheart": "news", "leiphone": "news", "qbitai": "news", "rsshub": "news",
}

# 一手技术材料来源（有实质内容的概率高）
MATERIAL_CHANNELS = {"arxiv", "openreview", "hf_papers", "s2", "hf_blog_rss",
                     "github", "gh_trending", "nowcoder", "zhihu", "inbox",
                     "aclanthology", "hf_models"}
# 技术分类（能承载深度解析）
MATERIAL_CATEGORIES = {"multimodal", "posttraining", "worldmodel", "generative",
                       "rl", "coding", "foundation", "engineering", "agent",
                       "paper", "course", "exam", "notes"}

# ---------------------------------------------------------------------------
# 类型识别的关键词（中英混合，ASCII 词按词边界匹配）
# ---------------------------------------------------------------------------
KIND_PATTERNS = [
    ("interview", 3.0, [r"面经", r"一面", r"二面", r"三面", r"四面", r"hr面", r"终面",
                        r"面试", r"onsite", r"interview", r"面试官", r"面试题"]),
    # 手撕/笔试题的权重略高于面经：一条标题里同时出现「面经」与「手撕/算法题」时，
    # 它对本工作台的积累价值是**可复用的题**，而不只是一次面试的经历记录。
    ("problem",   3.2, [r"手撕", r"手写", r"leetcode", r"算法题", r"题解", r"题库",
                        r"编程题", r"真题", r"机试", r"two pointers", r"滑动窗口",
                        r"动态规划", r"并查集", r"单调栈", r"binary search",
                        r"coding (?:problem|question)", r"take-?home"]),
    ("notes",     2.0, [r"八股", r"知识点", r"原理", r"总结", r"梳理", r"笔记", r"详解",
                        r"速查", r"cheat ?sheet", r"deep ?dive", r"explained",
                        r"从零", r"入门", r"tutorial"]),
    ("course",    2.0, [r"公开课", r"lecture", r"mooc", r"coursera", r"cs\d{2,3}",
                        r"教材", r"textbook", r"系列教程", r"walkthrough", r"读书会"]),
    ("news",      1.6, [r"融资", r"收购", r"估值", r"发布会", r"宣布", r"上线", r"财报",
                        r"股价", r"裁员", r"人事", r"任命", r"离职", r"签约", r"合作",
                        r"raises", r"funding", r"acquires", r"announces", r"launch",
                        r"ipo", r"layoff", r"partnership", r"unveils"]),
    ("paper",     1.6, [r"论文", r"arxiv", r"we propose", r"we present", r"we introduce",
                        r"abstract", r"preprint", r"benchmark", r"state-of-the-art",
                        r"outperforms"]),
    ("repo",      1.4, [r"github", r"开源", r"代码", r"复现", r"framework", r"toolkit",
                        r"library", r"implementation", r"toolbox"]),
]

# 「题解」这个词会让「本周小结！（回溯算法系列一）· 题解」被判成 problem，但它是一篇
# 目录型汇总 —— 没有可刷的题目实体。这类页面一旦进题库，就会占掉真正高频题的名额，
# 也会把深读预算浪费在「指路」而不是「解题」上。判据是两个条件同时成立：
#   ① 标题带汇总特征（小结 / 合集 / 题单 / 系列（一）…）；
#   ② 标题看不出「一道具体题」的身份（没有题号，也没有手撕/手写这类动作词）。
# 注意：只认「系列（一）」这种带序号的写法，不认泛化的「XX算法系列」，
# 否则「二叉树系列：翻转二叉树」这种真题页会被误杀。
PROBLEM_AGG_MARKERS = [
    r"本周小结", r"周小结", r"小结", r"复盘", r"合集", r"汇总", r"目录", r"总览",
    r"题单", r"索引", r"导览", r"刷题攻略", r"刷题路线", r"复习提纲", r"总结篇",
    r"系列\s*[（(]\s*[一二三四五六七八九十\d]",
]
PROBLEM_IDENTITY = [
    r"(?:LeetCode|力扣|LC)\s*[#№]?\s*\d", r"^\s*\d{1,4}\s*[.、]", r"手撕", r"手写",
    r"实现", r"复现", r"从零写", r"coding (?:problem|question)",
]


def is_problem_aggregate(title: str) -> bool:
    """标题像「题解汇总页」而不是「一道题」。见上面 PROBLEM_AGG_MARKERS 的说明。"""
    t = str(title or "")
    if not _hit(PROBLEM_AGG_MARKERS, t):
        return False
    return not _hit(PROBLEM_IDENTITY, t)


# 明确表示"这是可复用知识"的证据词 —— 有它就给材料性加分
KNOWLEDGE_EVIDENCE = [
    r"公式", r"推导", r"损失函数", r"注意力", r"训练", r"微调", r"评测", r"复现",
    r"实现", r"架构", r"步骤", r"对比", r"消融", r"实验", r"机制", r"原理",
    r"formula", r"derivation", r"loss", r"attention", r"training", r"fine-?tun",
    r"evaluation", r"architecture", r"implementation", r"ablation", r"algorithm",
]

# 易逝 / 无积累价值的措辞（不是硬噪音，只降权，用来识别"资讯"）
EPHEMERAL_HINTS = [
    r"最新", r"刚刚", r"今日", r"快讯", r"重磅", r"惊呆了", r"刷屏", r"热议",
    r"breaking", r"just (?:released|announced)", r"hot take",
]

# ---------------------------------------------------------------------------
# 方向贴合度：这条内容是不是「我要找的那个方向」的
#
# 为什么必须有这一层：分类器靠关键词命中把「面经」塞进 coding，
# 于是 Java/后端/运维 的面经与「多模态/后训练」的面经同样算数 —— 实测
# 库里的 coding 分类有一半是后台开发面经、秋招情绪帖与无关广告。
# 用户要的是**目标方向的大厂面经 / 算法题 / 八股**，所以这里再判一次：
# 内容里有没有目标方向的技术词，或经典算法/八股的关键词。
# ---------------------------------------------------------------------------
# 方向技术词分三组。分开是因为它们回答的不是同一个问题：
#   CORE_DIRECTION_TERMS —— 「具体的技术方向词」。一篇论文命中它才算真的落在
#                           多模态/后训练/生成式/世界模型（含 RL、Agent、工程、原理）里。
#   CS_BASICS_TERMS      —— 计算机基础八股。求职内容（面经/八股）靠它算「在方向上」，
#                           但它不能救一篇论文（论文里出现 "cache" 不代表它是八股）。
#   BROAD_AI_TERMS       —— 宽口径兜底。几乎任何 ML 内容都会命中（ai / cv / nlp /
#                           算法 / 机器学习…），所以**不能**当作「方向内」的证据，
#                           只用于避免把「算法工程师」这类真岗位误判为不相关。
CORE_DIRECTION_TERMS = [
    # 四个目标方向 + 支撑方向的技术词
    "multimodal", "multi-modal", "vision-language", "vlm", "mllm", "lvlm", "clip",
    "blip", "llava", "qwen-vl", "internvl", "cross-modal", "多模态", "视觉语言",
    "post-training", "post training", "sft", "instruction tuning", "rlhf", "dpo",
    "grpo", "rlvr", "reward model", "preference optimization", "distillation",
    "verifier", "process reward", "reasoning model", "后训练", "指令微调", "偏好优化",
    "world model", "world-model", "model-based rl", "dreamer", "genie", "vla",
    "vision-language-action", "embodied", "sim2real", "gaussian splatting", "nerf",
    "世界模型", "具身", "机器人",
    "diffusion", "flow matching", "rectified flow", "consistency model", "ddpm",
    "ddim", "text-to-image", "text-to-video", "video generation", "dit", "adaln",
    "扩散模型", "视频生成", "生成式",
    "reinforcement learning", "ppo", "gae", "actor-critic", "q-learning", "offline rl",
    "exploration", "credit assignment", "mcts", "policy gradient", "强化学习", "策略梯度",
    "agent", "agentic", "tool use", "function calling", "multi-agent", "reflexion",
    "mcp", "智能体",
    "transformer", "attention", "self-attention", "rope", "alibi", "rmsnorm", "layernorm",
    "normalization", "optimizer", "adamw", "scaling law", "注意力",
    "inference", "serving", "vllm", "sglang", "quantization", "kv cache", "flash attention",
    "fsdp", "deepspeed", "megatron", "cuda", "推理加速", "分布式训练", "显存",
    "embedding", "tokenizer", "softmax", "batch norm", "dropout", "backprop",
    "gradient", "loss function", "cross entropy", "perplexity", "fine-tune", "finetune",
    "预训练", "微调", "损失函数", "反向传播", "梯度",
    "大模型", "llm", "large language model", "vision language model",
]
# 计算机基础八股：任何技术岗面试都会问，与岗位族无关，所以算在方向上。
# （语言特性问答如「Go 的 slice 和 array 区别」不算 —— 那是后端岗的八股。）
CS_BASICS_TERMS = [
    "操作系统", "计算机网络", "数据库", "计算机组成", "编译原理", "linux",
    "进程", "线程", "死锁", "虚拟内存", "文件系统", "tcp", "udp", "http", "https",
    "索引", "事务", "缓存", "内存管理", "并发", "锁",
]
# 宽口径兜底：避免把「算法工程师」这类真岗位/真面经误判为不相关。
BROAD_AI_TERMS = [
    "算法", "机器学习", "深度学习", "神经网络", "aigc", "cv", "nlp",
    "推荐算法", "搜索算法", "广告算法", "感知算法", "ai", "人工智能",
]

DIRECTION_TERMS = CORE_DIRECTION_TERMS + CS_BASICS_TERMS + BROAD_AI_TERMS

# 经典算法/八股关键词：即使不含 ML 词，也属于「算法知识点/手撕题」，算在方向上。
ALGO_TERMS = [
    "leetcode", "手撕", "手写", "算法题", "题解", "题库", "笔试", "机试", "真题",
    "动态规划", "贪心", "回溯", "二分", "双指针", "two pointers", "滑动窗口",
    "链表", "二叉树", "图论", "并查集", "单调栈", "堆", "哈希", "排序", "快排",
    "归并", "位运算", "trie", "kmp", "topk", "top-k", "binary search", "hashmap",
    "八股", "操作系统", "计算机网络", "数据库", "计网", "面经", "知识点",
]


_TERM_CACHE: dict[str, "re.Pattern[str]"] = {}


def _term_re(t: str) -> "re.Pattern[str]":
    """Compile one direction term into a boundary-tolerant pattern.

    Why this is not a plain `re.escape`: the original pattern was
    `(?<![0-9a-z])term(?![0-9a-z])`, which silently failed on every inflected
    form. Measured on the real corpus:

        "llm"          did NOT match  "evaluation of LLMs"
        "scaling law"  did NOT match  "Scaling Laws for …"
        "agent"        did NOT match  "agents in the wild"
        "diffusion"    did NOT match  "diffusions"

    That under-matching made genuinely on-direction papers look off-direction
    (an LLM-evaluation paper scored directionFit 0.0), and it made the
    off-direction rules unreliable. Fixes:
      * optional English plural / possessive suffix (`s`, `es`, `'s`);
      * hyphen and space treated as interchangeable ("post-training" == "post training").
    Chinese terms have no suffix and are left exact.
    """
    if t in _TERM_CACHE:
        return _TERM_CACHE[t]
    if re.search(r"[a-z0-9]$", t):
        # English-ish term: split on spaces/hyphens so the two forms are equivalent.
        parts = [re.escape(p) for p in re.split(r"[\s\-]+", t) if p]
        esc = r"[\s\-]+".join(parts)
        esc += r"(?:s|es|'s)?"
    else:
        esc = re.escape(t)
    pat = re.compile(r"(?<![0-9a-z])" + esc + r"(?![0-9a-z])")
    _TERM_CACHE[t] = pat
    return pat


def _count_terms(terms, blob: str) -> int:
    n = 0
    for t in terms:
        if _term_re(t).search(blob):
            n += 1
    return n


# 非算法岗位族：标题里只要出现这些且没有明确的算法岗位词，就判定为「方向不贴合」。
# 这不是说这些岗位不好，而是这个工作台服务的是「算法实习」。
OFF_ROLE_TERMS = [
    "后端", "服务端", "前端", "全栈", "运维", "测试开发", "测试工程师", "客户端",
    "安卓", "android", "ios", "嵌入式", "驱动", "硬件", "网络工程师", "技术支持",
    "dba", "sre", "数据运营", "数据分析师", "产品经理", "交付", "售前", "实施",
    "运营岗", "管培", "管培生", "销售", "财务", "人力资源", "行政", "银行",
    "java开发", "go开发", "c++开发", "web开发", "软件开发工程师",
    "backend", "frontend", "devops",
]
# 明确的算法岗位族：出现这些时不适用上面那条降权。
ON_ROLE_TERMS = [
    "算法工程师", "算法专家", "算法实习", "算法研究员", "算法岗", "算法开发",
    "机器学习", "深度学习", "多模态", "大模型", "llm", "cv算法", "nlp算法",
    "推荐算法", "搜索算法", "广告算法", "感知算法", "决策规划", "具身",
    "research scientist", "machine learning engineer", "mle", "ai算法",
]


def direction_fit(item: dict) -> float:
    """0–1：这条内容与「我的目标方向 + 算法岗」的贴合度。

    0 表示它是一篇与目标方向无关的内容（例如 Java 后端面经、秋招情绪帖、
    无关广告）——它仍然可以有信息量，但不该占用本工作台的注意力。

    除了看有没有方向技术词，还要看**岗位族**：一篇「字节后端开发实习一面」里
    出现 "AI" 两个字并不代表它是算法岗内容。实测：仅靠技术词判定时，
    「AI全栈开发工程师」「计算机算法岗面试经验分享」都会拿到 0.5+ 的贴合度。
    所以非算法岗位族且没有明确算法岗位词的，直接降到三成。
    """
    blob = _blob(item)
    ml = _count_terms(DIRECTION_TERMS, blob)
    algo = _count_terms(ALGO_TERMS, blob)
    raw = ml * 1.0 + algo * 0.35
    fit = min(1.0, raw / 2.5)
    if _hit(OFF_ROLE_TERMS, blob) and not _hit(ON_ROLE_TERMS, blob):
        fit *= 0.3
    return round(fit, 3)


def core_fit(item: dict) -> float:
    """0–1：只由**具体技术词**（CORE_DIRECTION_TERMS）算出的方向贴合度。

    与 direction_fit 的区别很重要：direction_fit 含「宽口径兜底词」
    （ai / cv / nlp / 算法 / 机器学习…），几乎任何 ML 内容都能命中，因此它是
    「这条内容是不是求职相关的技术内容」；core_fit 回答的是更严的问题——
    「这篇论文有没有落在我的四个目标方向（含 RL/Agent/工程/原理）上」。

    用途：论文/仓库的取舍。一篇「AI 用于某医学影像」的论文 direction_fit 可能
    0.4，但 core_fit 为 0 —— 它只是在用别人的方法做一个领域应用，对备考算法岗
    没有技术迁移价值（读者原话：虽然很新但对求职无用）。
    """
    blob = _blob(item)
    core = _count_terms(CORE_DIRECTION_TERMS, blob)
    return round(min(1.0, core / 2.0), 3)


# ---------------------------------------------------------------------------
# 学科归属与「窄领域应用」判定
# ---------------------------------------------------------------------------
# arXiv 学科分类。只保留与算法/计算机有关的；一篇 cond-mat / math.AP /
# astro-ph 的论文与四个目标方向无关，它是通过关键词误撞进来的。
CS_ARXIV_TAGS = {
    "stat.ML", "stat.ME", "eess.AS", "eess.IV", "eess.SP",
}


def arxiv_field_tags(item: dict) -> list[str]:
    """Return arXiv-style field tags only (`cs.CV`, `cond-mat.quant-gas`, …).

    HuggingFace / Semantic Scholar reuse `tags` for free-form topic words, so the
    shape of an arXiv tag is what distinguishes them.
    """
    out = []
    for t in (item.get("tags") or []):
        if re.match(r"^[a-z][a-z\-]*\.[A-Za-z][A-Za-z\-]*$", str(t)):
            out.append(str(t))
    return out


def off_field(item: dict) -> str | None:
    """Return the offending field when an arXiv paper is outside CS/ML entirely."""
    tags = arxiv_field_tags(item)
    if not tags:
        return None
    if any(t.startswith("cs.") or t in CS_ARXIV_TAGS for t in tags):
        return None
    return tags[0]


# 窄领域应用：内容讲的是「把 AI 用在某个具体行业」，而不是「AI 方法本身」。
# 这些论文对新方法没有贡献，面试也问不到方法细节，属于读者说的「对求职无用」。
#
# 每条正则都刻意**收窄**过。第一版用了宽词，实测出现了三类误杀：
#   * `diagnos\w*` —— 命中 "diagnosing a runtime interaction failure"（CUA-SWE，实为 agent 论文）
#   * `business`   —— 命中 "a business event fits in a single table"（Argo-Bench，实为数据 agent 基准）
#   * `crop`       —— 命中 "motion-biased crop selection"（图像裁剪，与农业无关）
# 所以这里只保留**无歧义**的领域词：宁可漏判几个，也不误杀方向内的技术内容。
APPLICATION_DOMAINS = [
    ("医学/生物", r"\b(medical|clinical|biomedical|healthcare|patient|mri|ct scan|eeg|ecg|"
                  r"x-?ray|tumou?r|cancer|alzheim\w*|histopatholog\w*|radiolog\w*|"
                  r"tractograph\w*|protein|genom\w*|drug discovery|clinical trial)\b"),
    ("地球/遥感", r"\b(remote sensing|satellite imagery|geospatial|climate change|"
                  r"weather forecast|seismic|hydrolog\w*|agricultur\w*|geolog\w*)\b"),
    ("物理/化学", r"\b(quantum|photonic|molecul\w*|chemistry|chemical (?:reaction|compound)|"
                  r"astrophysic\w*|galax\w*|plasma|tokamak|kilonova|qubit|"
                  r"thermodynamic\w*|particle physics)\b"),
    ("工业/能源", r"\b(power (?:system|grid)|wind turbine|manufacturing|supply chain|"
                  r"logistics|railway)\b"),
    # `law` 需要负向环视：`Scaling Law` 是机器学习里的常见标题词（"Scaling Laws for
    # Neural Language Models"），把它当成「法学应用」会误杀一篇核心方向论文。
    # 实测漏判的：「AI Applicability in Law: Opportunities, Limitations, and Governance…」。
    # `governance` 已从这里移除：AI agent 语境里 "agent-governance"/"AI governance" 是
    # 正经的 AI 话题，实测 GitHub 仓库的 topics 里就带 `agent-governance`，
    # 于是「omnigent-ai/omnigent（开源 agent 框架）」被判成「金融/社科领域应用」。
    # 法学领域改用 `legal (...)` / `judicial` / `antitrust` 这些无歧义的词来判。
    ("金融/社科", r"\b(financial|stock market|trading strateg\w*|economic\w*|social science|"
                  r"marital|journalism|legal (?:document|reasoning|judgment|system|ai)|"
                  r"judicial|antitrust|education|"
                  r"(?<!(?i:scaling ))(?<!(?i:power ))\blaw\b)\b"),
]

# 「方法论文」信号：标题以短的专名开头（`DAGent:` / `Mem++:` / `CARM:`），或带开源实现。
# 用来区分「提出方法的论文」与「把 AI 用在某外来领域的论文」。实测：
#   「Future of AI in English Language Education: Trends and Predictions」  无 -> 领域应用
#   「A foundation for systematic analysis of transformers and RNNs for tractography」无 -> 领域应用
#   「DAGent: Evaluate-then-Grow Planning for Deep Research」              有 -> 方法论文
#   「OSWorld-Science: A Benchmark of Computer Use Agents…」（标题不含领域词）不受影响
METHOD_NAME_RE = re.compile(r"^\s*[A-Za-z][\w\-\+\.]{0,18}\s*[:：]")


def has_method_signal(item: dict) -> bool:
    if item.get("codeAvailable") or (item.get("qualitySignals") or {}).get("codeAvailable"):
        return True
    return bool(METHOD_NAME_RE.match(str(item.get("title") or "")))


def application_domain(item: dict, title_only: bool = False,
                       min_hits: int = 1) -> str | None:
    """Which foreign application domain the text names — or None.

    `min_hits` 要求**不同**的领域词至少出现这么多个。为什么需要它：正文里出现一个
    领域词太容易是巧合，实测两例误杀：
      · 「How Much Is an AI Token Worth? Scaling Laws for Wild AI-Generated Web Text」
        正文里 `...than the best existing law over all ai ratios` —— 这里的 law 是
        「规律」，不是法学；
      · 「omnigent-ai/omnigent」的 GitHub topics 里有 `agent-governance` —— 这是 AI 话题，
        不是社科。
    单命中就不再足以判定「这是一篇某领域应用论文」。标题层的命中不受此限（标题点名
    领域就是主题级证据），所以调用方在标题层用 min_hits=1、正文层用 min_hits=2。
    """
    text = str(item.get("title") or "").lower() if title_only else _blob(item)
    for label, pat in APPLICATION_DOMAINS:
        hits = {m.group(0).lower() for m in re.finditer(pat, text, re.I)}
        if len(hits) >= min_hits:
            return label
    return None


def domain_applied_only(item: dict) -> str | None:
    """Paper is a narrow field application with NO real method contribution.

    Two tiers, because "the domain word appears" means different things in the title
    and in the abstract:

      标题点名了外来领域  -> 这篇论文的**主题**就是把 AI 用在那个领域，所以只有带
                            方法信号（专名 / 开源实现）才保留；
      只有正文沾到       -> 可能只是用了该领域的数据或提了一句任务，仍然按原来的
                            规则判（core_fit < 1.0 才视为纯应用）。

    为什么要分两层：把两处混在一起时，实测出现两个方向相反的错：
      · 「Future of AI in English Language Education: Trends and Predictions」
        （教育学综述）与「A foundation for systematic analysis of transformers and
        RNNs for tractography」（弥散磁共振影像重建）只命中 2 个具体技术词，
        core_fit 恰好 = 1.0，于是原规则放行；
      · 而「OSWorld-Science: A Benchmark of Computer Use Agents…」是正经的 agent
        基准论文，只是正文里出现了 "molecular"，如果按正文判定就会被误杀。
    标题层 + 方法信号正好把这两个错分开：教育/法学/影像重建的标题里没有专名，
    OSWorld-Science 的标题里根本没有领域词。
    """
    dom = application_domain(item, title_only=True)
    if dom:
        if has_method_signal(item):
            return None
        return dom
    # 正文层要求至少两个不同的领域词：单个词（"existing law"、"agent-governance"）
    # 不足以证明这是一篇领域应用论文。见 application_domain 的 min_hits 说明。
    dom = application_domain(item, min_hits=2)
    if not dom:
        return None
    if core_fit(item) >= 1.0:
        # Two or more specific direction terms: this reads as a method paper that
        # happens to use a dataset from that field. Keep it.
        return None
    return dom


def technical_reject(item: dict, kind: str | None = None) -> str | None:
    """Reason this 论文/仓库/课程 should not be kept — or None to keep it.

    Single source of truth for two call sites that MUST agree:
      · `collect.py` 的入库闸门 —— 不合格的论文根本不进库（也就不必等清理）；
      · `importance()` 的分档  —— 已经在库里的历史条目走同一判断。
    两处共用同一个函数，所以不可能出现「采集放进来、清理又要删掉」的漂移。

    `knowledgeBase` 白名单渠道（代码随想录 / 卡码笔记 / 小林coding / CodeTop /
    题解仓库）不受此限：它们的 family 白名单本身就是方向过滤器。
    """
    kind = kind or classify_kind(item)
    if kind not in ("paper", "repo", "course"):
        return None
    if item.get("knowledgeBase"):
        return None
    policy = load_policy()

    if kind == "paper":
        off = off_field(item)
        if off:
            return f"非计算机学科论文（arXiv {off}）—— 与四个目标方向无关"

    applied = domain_applied_only(item) if kind in ("paper", "repo") else None
    if applied:
        return (f"单一领域应用（{applied}）且没有方法层面的贡献 —— "
                f"方法不可迁移，对备考算法岗无用")

    cfit = core_fit(item)
    min_core = float(policy.get("minCoreFitForTechnical", 0.5))
    if cfit < min_core:
        return (f"与目标方向没有具体技术关联（方向技术贴合 {cfit:.2f} < {min_core}）"
                f"—— 只靠泛化的 AI 词命中，不构成可积累的技术内容")

    mat = materiality(item, kind)
    min_mat = float(policy.get("minKeepMateriality", 0.22))
    if mat < min_mat:
        return f"知识材料性 {mat:.2f} 低于保留门槛 {min_mat}"
    return None


def ingest_reject(item: dict, policy: dict | None = None) -> str | None:
    """采集入库闸门：返回「这条不该进库」的理由，None = 收下。

    为什么要把闸门本身也收进这一个模块：原先 collect.py 里散着四条判断
    （news 材料性下限 / flagged 材料性下限 / technical_reject / dropUnclassified），
    而清理脚本走的是 importance()。两处各写一遍就必然漂移 —— 实测就出现过
    「采集放进来、清理又要删」的付费教程。现在采集侧只调这一个函数。

    判定顺序（从硬到软）：
      1. NEVER_KEEP_RULES —— 付费教程/内推码/卖课引流/资源包下载，材料性再高也不收；
      2. 资讯类 —— 没有技术实质的直接不收；有实质但材料性过低的也不收；
      3. 命中其它硬噪音规则且材料性过低 —— 不收（有实质内容的带噪条目仍保留）；
      4. 论文/仓库/课程的 technical_reject —— 方向不对的不收。
    """
    policy = policy or load_policy()
    # Always RECOMPUTE rather than trusting the stored `kind` / `materiality`.
    # Measured bug: the stored fields are written at ingest time, so after a rule
    # change they are stale - reading them here made `ingest_reject()` answer
    # "keep" for items whose freshly-computed kind was `news` with no technical
    # substance. Recomputing is deterministic and cheap, and it is what makes the
    # gate agree with the pruner.
    kind = classify_kind(item)
    mat = materiality(item, kind)

    hits = noise_ids(item)
    never = [h for h in hits if h in NEVER_KEEP_RULES]
    if never:
        return f"命中不可保留的噪音规则（{never[0]}）—— 不是知识"

    if kind == "news":
        if not news_has_substance(item):
            return "泛 AI 资讯：没有公式/推导/实验/数据集等技术实质，读者明确要求不收"
        if mat < float(policy.get("minMaterialityForNews", 0.34)):
            return f"资讯材料性 {mat:.2f} 低于下限 {policy.get('minMaterialityForNews', 0.34)}"

    if hits and mat < float(policy.get("minMaterialityForFlagged", 0.40)):
        return f"命中噪音规则（{hits[0]}）且材料性 {mat:.2f} 过低"

    return technical_reject(item, kind)

# ---------------------------------------------------------------------------
# 硬噪音规则（命中 = 不是知识）
#
# 合并了原先 plan_deep_read.py 与 prune_items.py 的两套规则，并补了两条用户
# 明确不要的类别：与技术无关的社区热点、纯推广/招生贴。原规则一条未删。
# ---------------------------------------------------------------------------
NOISE_RULES = [
    ("career-vent", "求职吐槽 / 情绪帖，无信息量",
     [r"处境.*未来", r"勤勤恳恳", r"不摸鱼", r"升职加薪.*轮不到", r"要不要跑",
      r"劝退", r"后悔", r"焦虑", r"破防", r"内卷.*值得", r"值不值得.*主攻"]),
    ("generic-question", "泛化提问 / 求帮选，无法结构化成知识",
     [r"^为什么很多人", r"^如何评价", r"^大家怎么看", r"^有人知道吗", r"^请问",
      r"^求推荐", r"^求问", r"^如何看待", r"offer.*(?:帮选|怎么选|如何选|选择)",
      r"怎么选\s*[？?]", r"给点建议", r"^求.*建议"]),
    ("referral-code", "内推码 / 内推广告，只需进岗位信息",
     [r"内推码", r"内推链接", r"内推", r"扫.*码.*投递", r"急招.*加微信"]),
    ("salary-thread", "纯薪资讨论 / 薪资汇总，数字无法核实且易重复",
     [r"薪资.*(?:爆料|汇总|报告|揭秘|倒挂)", r"offer.*对比.*薪资", r"总包.*多少",
      r"\d{4}\s*届?.*薪资(?:汇总|报告)", r"薪资倒挂"]),
    ("off-topic-hot", "与技术无关的社区热榜",
     [r"土豆", r"减肥", r"转专业", r"永动机", r"食堂", r"宿舍", r"考研英语",
      r"公务员", r"考公", r"相亲", r"房价", r"裁员潮.*怎么办"]),
    ("promo", "推广 / 卖课 / 招生 / 引流，不是知识（含「八股汇总」类标题党实为卖课）",
     [r"限时优惠", r"领取.*资料包", r"扫码.*(?:进群|关注|领取)", r"报名.*(?:直播|公开课|训练营)",
      r"免费试听", r"点击.*购买", r"课程.*促销",
      # 卖课 / 训练营 / 包就业
      r"培训营", r"训练营", r"就业班", r"保offer", r"包过", r"包就业",
      r"一对一辅导", r"付费课程", r"卖课", r"招生",
      # 引流话术
      r"公众号(?:后台)?回复", r"后台回复", r"加群", r"进群", r"领取完整版",
      r"完整版资料", r"资料免费领", r"免费领取",
      # 标题党：看起来是知识汇总，实际是索取/引流入口
      r"(?:八股|面经|笔记|资料|汇总|合集).*(?:领取|免费|加群|扫码|回复|购买|报名)",
      r"(?:领取|加群|扫码|回复).*(?:八股|面经|笔记|资料|汇总|合集)"]),
    # 付费开通 / 充值教程 —— 读者明确点名要清掉的一类。
    #
    # 为什么单独一条：它是最典型的「看起来像技术笔记、其实与求职学习无关」的内容。
    # 实测三条漏进来的（都在白名单知识库里，所以绕过了全部质量闸门）：
    #   「2026年最新ChatGPT充值教程，支持国内支付宝和微信充值 GPT-6、Plus、Pro、Codex等」
    #   「怎么给ChatGPT充值？开通Plus使用Codex的支付宝微信方案」
    #   「Claude Pro怎么充值？开通Claude Code的国内订阅攻略」
    # 它们讲的是「怎么付钱」，不含任何可被面试追问的原理 —— 与四个目标方向无关。
    # 关键词刻意收窄：`订阅` / `会员` 单独出现有可能是正文里的「事件订阅」「会员制」，
    # 会误杀系统类文章，所以只保留无歧义的付款语义组合。
    ("paid-guide", "付费充值 / 订阅开通教程，与求职学习无关（只讲怎么付钱，没有可追问的原理）",
     [r"充值", r"代充", r"礼品卡", r"虚拟信用卡", r"\bvcc\b", r"激活码",
      r"订阅攻略", r"开通\s*(?:plus|pro|max|会员|订阅|会员制)",
      r"(?:plus|pro|max|会员|订阅).{0,8}(?:怎么|如何).{0,6}(?:充|开通|购买|买)",
      r"(?:怎么|如何|哪里).{0,8}(?:充值|开通\s*plus|订阅\s*claude|买\s*api)",
      r"按量(?:付费|计费)", r"计费(?:说明|规则|方式)", r"api\s*(?:额度|余额|充值)",
      r"账号(?:购买|交易|出售|代购)", r"价格(?:对比表|对比图)",
      r"白嫖\s*(?:api|额度|key)"]),
    # 资料包下载引流：标题是「全系列 PDF / 合集下载 / 网盘提取」的，本质是引流入口。
    #
    # 实测漏进来的：「小林图解全系列PDF+1000道Java/C++/Go面试真题PDF下载 · 八股」——
    # 它的「八股 / 真题」字样让它看起来是知识，实际正文只有下载引导。
    # 这与 promo 的区别：promo 是卖课/加群，这一类是「资源包」话术。
    ("download-bait", "资料包 / PDF 打包下载引流，不是知识本身",
     [r"pdf\s*(?:下载|合集|打包|免费|领取)", r"(?:全套|全系列|完整版).{0,12}(?:pdf|资料包|笔记合集)",
      r"(?:资料|笔记|合集|题解)\s*(?:包|打包).{0,6}(?:下载|网盘|提取码)",
      r"(?:网盘|云盘)\s*(?:链接|地址|提取码|分享|下载)",
      r"提取码", r"(?:打包|一键|批量)下载",
      r"(?:回复|私信).{0,6}(?:获取|领取).{0,8}(?:pdf|资料|完整版|合集)"]),
]

HARD_NOISE_IDS = {r[0] for r in NOISE_RULES}

# 「无论材料性多高都不保留」的硬噪音。
#
# 为什么需要这个子集：入库闸门原本只丢「命中噪音规则 **且** 材料性 < 0.40」的条目
# （见 collect.py 的 minMaterialityForFlagged）。这条 AND 对吐槽帖是合理的（它可能
# 有很长的正文，材料性不低），但对下面这几类是错的 —— 它们的摘要写得又长又像样，
# 材料性反而更高。实测：`Claude Pro怎么充值？…国内订阅攻略` 的材料性是 0.474，
# 高于 0.40，所以旧规则会把它放进来。付费教程、内推码、卖课引流、资源包下载
# 这四类不存在「内容扎实所以值得留」的情况，直接丢。
NEVER_KEEP_RULES = {"paid-guide", "download-bait", "promo", "referral-code"}

# ---------------------------------------------------------------------------
# 资讯渠道：默认产出「资讯」，只有带明确知识标记时才当知识
# ---------------------------------------------------------------------------
# 问题：把 leiphone / qbitai 这类 AI 行业媒体当成普通源，标题里出现「架构」「开源」
# 「手撕」等词就会被分类器塞进 notes / repo / paper，于是产品实测稿、公司评论稿披着
# 「知识点」「仓库」的外衣留了下来。实测该渠道最近 12 条里 11 条是这个形态：
#   「AI办公进入「上下文战争」，百度如何出牌？」（企业访谈）
#   「实测 Seedance 2.5 vs 可灵 3.0，谁能让我们无痛当上视频导演？」（产品实测）
#   「从 Codex Harness 开源，看 AI 公司的护城河是什么？」（商业评论）
#   「越大越强，不再是 LLM 的专利：PixVerse R2 攻克实时世界模型 Scaling 难题」（发布会稿）
# 读者明确要求不收「泛 AI 新闻、融资与发布会报道」。所以这里让渠道先验说话。
#
# 注意：这是**默认值**而不是一刀切。标题里出现下面这些「知识型标记」时仍然按内容分类，
# 因为同一个站点偶尔也会发真正的技术解析（实测：leiphone 的「Kimi 和 DeepSeek，
# 为什么出现在同一张模型架构图里？」就属于这一类）。
NEWS_CHANNEL_PRIOR = {cid for cid, k in CHANNEL_KIND.items() if k == "news"}

KNOWLEDGE_TITLE_MARKERS = [
    r"题解", r"八股", r"知识点", r"原理", r"推导", r"教程", r"源码",
    r"实现", r"论文", r"综述", r"详解", r"面经", r"面试题", r"速查",
    r"复现", r"消融", r"benchmark", r"tutorial", r"explained", r"deep ?dive",
    r"cheat ?sheet", r"from scratch", r"implementation",
]
# 注意这里**刻意不含**「手撕 / 手写 / 从零 / 深入」这类动词性词：行业媒体把「手撕」
# 当clickbait 用（实测：「DeepSeek 开源算子工具大礼包…手撕 CUDA 绑定！」是一条开源
# 发布资讯，却因为标题有「手撕」被判成手撕题，会白占一个题库深读名额）。

# 资讯内容的「技术实质」证据。**刻意收窄**：只保留只会在「本文讲了做法」时出现的词。
#
# 为什么不用「架构 / 算法 / 训练 / 推理」这些：它们几乎出现在每一篇 AI 新闻里，
# 用来当证据等于没筛。这里要回答的是「这篇文章有没有可被面试追问的技术细节」。
NEWS_SUBSTANCE_TERMS = [
    r"公式", r"推导", r"损失函数", r"消融", r"ablation", r"基准(?:测试)?", r"benchmark",
    r"数据集", r"实验(?:设置|结果|对比)", r"参数量", r"超参", r"收敛", r"梯度",
    r"复杂度", r"伪代码", r"代码实现", r"开源实现", r"复现", r"算子", r"kernel",
    r"训练细节", r"预训练细节", r"技术报告", r"论文", r"paper", r"arxiv",
    r"自注意力", r"注意力机制", r"tokenizer", r"位置编码", r"推理加速", r"吞吐",
]


def news_has_substance(item: dict) -> bool:
    """一条资讯有没有「可被面试追问的技术实质」。

    判据刻意用组合而不是单词：一条资讯要留下，必须至少命中 2 个**不同的**技术证据词
    （或自带代码 / 同行评审 / 高 star 仓库）。实测：
      「AI办公进入「上下文战争」，百度如何出牌？」            0 个 -> 丢
      「实测 Seedance 2.5 vs 可灵 3.0，谁能让我们无痛当上视频导演？」 0 个 -> 丢
      「PixVerse R2 攻克实时世界模型 Scaling 难题」            0 个 -> 丢
    而一篇真正的技术解读（含数据集 / 消融 / 公式）会命中 2 个以上，保留。
    """
    blob = _blob(item)
    hits = sum(1 for p in NEWS_SUBSTANCE_TERMS if re.search(p, blob))
    if item.get("codeAvailable") or (item.get("qualitySignals") or {}).get("codeAvailable"):
        return True
    if item.get("peerReviewed"):
        return True
    try:
        if float(item.get("stars") or (item.get("qualitySignals") or {}).get("stars") or 0) >= 300:
            return True
    except (TypeError, ValueError):
        pass
    return hits >= 2

# ---------------------------------------------------------------------------
# 配置读取（阈值可调，不写死在代码里）
# ---------------------------------------------------------------------------
DEFAULT_POLICY = {
    # 入库门槛：低于此材料性的「资讯」不入库（论文/仓库/面经/题不受此限）
    "minMaterialityForNews": 0.34,
    # 低于此材料性且在硬噪音名单里的条目，入库即丢
    "minMaterialityForFlagged": 0.40,
    # 深读配额的最低材料性（低于它不占用深度解析名额）
    "minMaterialityForDepth": 0.28,
    # 清理门槛
    "minKeepImportance": 25,
    "minKeepMateriality": 0.22,
    # 打分时的材料性分量上限（加成/扣分对称，范围 ±此值）
    "scoreMaterialityWeight": 10.0,
    # 「资讯」类型的固定扣分
    "scoreEphemeralPenalty": 8.0,
}


_POLICY_CACHE: dict = {"mtime": None, "policy": None}


def load_policy() -> dict:
    """Read the `knowledge` block of collector.config.json, falling back to defaults.

    Cached on (path, mtime): this is called several times per item by
    importance() / technical_reject() / library_over_cap(), and on an ~800-card
    corpus that was thousands of redundant file reads per run. The mtime key
    keeps it correct when tune_keywords.py rewrites the config mid-run.
    """
    path = ROOT / "config" / "collector.config.json"
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        mtime = None
    if _POLICY_CACHE["mtime"] == mtime and _POLICY_CACHE["policy"] is not None:
        return _POLICY_CACHE["policy"]
    policy = dict(DEFAULT_POLICY)
    try:
        cfg = json.loads(path.read_text("utf-8"))
        policy.update(cfg.get("knowledge") or {})
    except Exception:
        pass
    _POLICY_CACHE.update({"mtime": mtime, "policy": policy})
    return policy


def _blob(item: dict) -> str:
    return " ".join([
        str(item.get("title") or ""),
        str(item.get("summary") or ""),
        " ".join(str(t) for t in (item.get("tags") or [])),
        str(item.get("venue") or ""),
    ]).lower()


def _hit(patterns, text: str) -> bool:
    """True when any pattern matches.

    Case-insensitive on purpose. The rules were written for Chinese text, where case
    is irrelevant - but several ASCII patterns ("pdf", "vcc", "api 额度") silently
    failed on "PDF" / "VCC" / "API", which is exactly how
    「小林图解全系列PDF+1000道…真题PDF下载」 got past the download-bait rule.
    Making this one comparison case-insensitive fixes the whole class in one place.
    """
    for p in patterns:
        try:
            if re.search(p, text, re.I):
                return True
        except re.error:
            continue
    return False


# ===========================================================================
# 1. 知识类型
# ===========================================================================
def classify_kind(item: dict) -> str:
    """论文 / 仓库 / 面经 / 手撕题 / 知识点 / 课程 / 岗位 / 资讯 / 其它。

    判定顺序刻意如此：
      1) 渠道先验（arxiv 就是论文，招聘渠道就是岗位）——最稳定，不被措辞带偏；
      2) 求职三件套（面经 / 手撕题 / 八股笔记）优先于泛化的"资讯/其它"，
         因为它们是这套工作台最想要、也最容易混进热榜帖的资产；
      3) 关键词打分兜底，分数相同按 KIND_PATTERNS 的先后。
    """
    blob = _blob(item)
    title = str(item.get("title") or "").lower()
    ch = str(item.get("channel") or item.get("sourceId") or "")
    cat = str(item.get("category") or "")

    # (1) 渠道先验。招聘 / 论文渠道是结构性的，直接采信。
    prior = CHANNEL_KIND.get(ch)
    if prior in ("job",):
        return "job"
    if prior in ("paper",):
        # 论文渠道里也会出现"某某发布模型"这类宣传稿，但不该反客为主。
        if not _hit(KIND_PATTERNS[0][2], title):          # 标题没有面试字样
            return "paper"
    if prior in ("repo",) and ch in ("github", "gh_trending", "hf_models", "gh_algokb"):
        return "repo"
    if prior == "news":
        # 行业媒体默认产出资讯。只有标题出现明确的知识型标记时才继续按内容分类，
        # 否则直接判为 news —— 这样 `news_has_substance()` 才有机会拦下产品实测稿
        # 与公司评论稿（见 NEWS_CHANNEL_PRIOR 上方的实测样例）。
        if not _hit(KNOWLEDGE_TITLE_MARKERS, title):
            return "news"

    # (2) 求职三件套：标题命中权重更高（标题即主题）
    scores = Counter()
    for kind, weight, pats in KIND_PATTERNS:
        if _hit(pats, title):
            scores[kind] += weight * 2.0
        if _hit(pats, blob):
            scores[kind] += weight
    if scores:
        # 资讯只有在没有更具体的知识类型时才成立
        best = max(scores.items(), key=lambda kv: (kv[1], -KINDS.index(kv[0])))
        k = best[0]
        if k == "news" and len(scores) > 1:
            other = max((s for s in scores.items() if s[0] != "news"),
                        key=lambda kv: kv[1], default=None)
            if other and other[1] >= best[1] * 0.6:
                return other[0]
        if k == "problem" and is_problem_aggregate(str(item.get("title") or "")):
            # 汇总页：它讲的是「这一周做了哪些题」，不是「这道题怎么做」。
            # 归到 notes 仍然保留可检索性，只是不再占用题库与深读名额。
            return "notes"
        return k

    # (3) 分类兜底
    if cat == "job":
        return "job"
    if cat in ("coding", "exam"):
        if is_problem_aggregate(str(item.get("title") or "")):
            return "notes"
        return "problem"
    if cat == "course":
        return "course"
    if cat == "paper":
        return "paper"
    if cat == "trend":
        return "news"
    if cat in MATERIAL_CATEGORIES:
        return "notes"
    return "other"


# ===========================================================================
# 2. 硬噪音
# ===========================================================================
def noise_flags(item: dict) -> list[tuple[str, str]]:
    """Return [(rule_id, why)] for rules that say "this is not knowledge"."""
    title = str(item.get("title") or "")
    summary = str(item.get("summary") or "")
    blob = f"{title} {summary}"
    out = []
    for rid, why, pats in NOISE_RULES:
        if _hit(pats, blob):
            # A referral code inside a real JD is fine; only flag it when the item
            # is essentially just the code.
            if rid == "referral-code" and len(summary) > 200:
                continue
            out.append((rid, why))
    return out


def noise_ids(item: dict) -> list[str]:
    return [r for r, _ in noise_flags(item)]


# ===========================================================================
# 3. 材料性（知识耐久性）0–1
# ===========================================================================
def materiality(item: dict, kind: str | None = None) -> float:
    """How much durable knowledge does this item actually carry?

    四分量，各自 0–1，加权后归一到 0–1：

      substance     摘要里有多少实质信息（空摘要 = 书签，不是卡片）
      evidence      可核验的证据：代码 / 同行评审 / CCF / star / upvote
      reusability   是否含可复用材料（公式、推导、实现、评测、机制…）
      durability    类型本身的可积累程度（论文/面经高，资讯低）

    刻意**不含"新鲜度"**：用户要的正是不要因为"最新"就收进来。
    新鲜度已经在 score_item 的 freshness 分量里，两者职责分开。
    """
    kind = kind or classify_kind(item)
    summary = str(item.get("summary") or "").strip()
    blob = _blob(item)
    qs = item.get("qualitySignals") or {}

    n = len(summary)
    substance = 1.0 if n >= 600 else 0.75 if n >= 300 else 0.45 if n >= 120 \
        else 0.15 if n >= 40 else 0.0

    ev = 0.0
    if item.get("codeAvailable") or qs.get("codeAvailable"):
        ev += 0.30
    if item.get("peerReviewed"):
        ev += 0.22
    if item.get("ccf"):
        ev += 0.15
    stars = item.get("stars") or qs.get("stars") or 0
    try:
        stars = float(stars)
    except (TypeError, ValueError):
        stars = 0.0
    if stars >= 1000:
        ev += 0.25
    elif stars >= 300:
        ev += 0.15
    elif stars >= 80:
        ev += 0.07
    try:
        up = float(item.get("upvotes") or qs.get("upvotes") or 0)
    except (TypeError, ValueError):
        up = 0.0
    if up >= 200:
        ev += 0.15
    elif up >= 50:
        ev += 0.07
    evidence = min(1.0, ev)

    hits = sum(1 for p in KNOWLEDGE_EVIDENCE if re.search(p, blob))
    reusability = min(1.0, hits / 4.0)

    durability = KIND_DURABILITY.get(kind, 0.45)

    score = (0.40 * substance + 0.25 * evidence
             + 0.15 * reusability + 0.20 * durability)

    # 方向贴合度：内容再充实，如果讲的是别的方向（Java 后端面经、与目标方向无关的
    # 工程博客），对这个工作台也不是要积累的知识。求职类（面经/题/八股）要求更严。
    fit = direction_fit(item)
    if kind in ("interview", "problem", "notes", "job", "news"):
        score *= (0.45 + 0.55 * fit)
    else:
        score *= (0.65 + 0.35 * fit)

    # 硬噪音先砍一半：它可能有摘要，但不是知识。
    if noise_ids(item):
        score *= 0.5
    return round(max(0.0, min(1.0, score)), 3)


# ===========================================================================
# 4. 求职可用性（这条内容离面试有多近）
# ===========================================================================
# 读者的原始诉求：「把手撕算法、各领域核心工作或问题等求职面试能直接用上的信息
# 提高采集优先级」。所以需要第三个维度，它回答的问题和另外两个都不同：
#
#   kind        这条是什么形态（论文 / 手撕题 / 面经 / 资讯…）
#   materiality 这条能不能积累（有实质内容、可复用、有证据）
#   career      这条**离面试有多近** —— 能不能被面试官直接追问到原理/公式/代码层面
#
# 为什么不能只用 materiality：一篇「AI 用于某医学影像」的论文可以材料性很高
# （有实验、有数据集、有代码），但面试官不会问它；一道高频手撕题的材料性可能只有
# 0.5（摘要就是一行元数据），但它恰恰是最该优先深读的东西。
#
# 分档依据全部可复核：形态 + 方向贴合度 + 是否有可复现证据 + 是否带题号/频度。
FREQ_RE = re.compile(r"(?:LeetCode|力扣|LC)\s*\d+|\d+\s*次|\d+\s*道|共\s*\d+", re.IGNORECASE)


def career_usability(item: dict, kind: str | None = None) -> float:
    """0–1：直接拿来准备面试的价值。越高越该优先采集与优先深读。"""
    kind = kind or classify_kind(item)
    fit = direction_fit(item)
    cfit = core_fit(item)
    blob = _blob(item)
    title = str(item.get("title") or "")

    if kind == "problem":
        # 手撕/笔试题永远排第一档：它是「面试当场要写出来的东西」。
        # 带真实题号或大厂频度的再抬到顶格（codetop 卡就是这种）。
        base = 0.95 if fit >= 0.25 else 0.55
        if FREQ_RE.search(title) or FREQ_RE.search(str(item.get("summary") or "")):
            base = 1.0
        return base
    if kind == "interview":
        # 面经：时效强、形态是一次性经历，所以方向贴合度必须把关
        # （后端/嵌入式面经贴合度低，会被压到 0.35）。
        return 0.95 if fit >= 0.25 else 0.35
    if kind == "notes":
        # 八股/知识点：方向内且是真技术原理的高；计算机基础八股（TCP/OS/DB）次之。
        if fit >= 0.25 and cfit >= 0.5:
            return 0.85
        if fit >= 0.25:
            return 0.6
        return 0.3
    if kind == "paper":
        # 论文：能问到的只有「机制/公式/与已有方法的差别」。
        # 目标方向核心 + 有开源实现 = 可以直接复现、能手撕，最高。
        if cfit >= 1.0 and (item.get("codeAvailable")
                            or (item.get("qualitySignals") or {}).get("codeAvailable")):
            return 0.9
        if cfit >= 1.0:
            return 0.75
        if cfit >= 0.5:
            return 0.5
        return 0.25
    if kind == "repo":
        # 仓库：价值在「能跑、能读源码」。白名单知识库（题解/八股仓库）本来就是
        # 为求职准备的，直接给高。
        if item.get("knowledgeBase"):
            return 0.85
        if cfit >= 0.5:
            return 0.8
        if fit >= 0.4:
            return 0.5
        return 0.2
    if kind == "course":
        return 0.5
    if kind == "job":
        # 岗位 JD 有用，但面试不会考 JD 本身 —— 它靠岗位看板，不靠深读。
        return 0.15
    return 0.05


# ===========================================================================
# 5. 深读优先级
# ===========================================================================
def depth_value(item: dict, kind: str | None = None, mat: float | None = None) -> float:
    """0–100：这条值不值得占用一个深度解析名额。

    与旧的 depth_score 相比，关键差别是**资讯类型的上限被压死**，并且
    「面经 / 手撕题 / 八股笔记」这类求职资产被明确提到与论文同级 ——
    用户要的是这几类内容的持续积累。

    2026-10-03 起新增 `career` 分量（权重 0.20）：读者要求把「求职面试能直接用上的
    信息」提优先级。在此之前排序只看「相关度 + 材料性」，于是一道摘要只有一行
    元数据的高频手撕题会输给一篇摘要很长的外围论文。现在career 把前者拉回来。
    """
    kind = kind or classify_kind(item)
    mat = materiality(item, kind) if mat is None else mat
    rel = float(item.get("relevanceScore") or 0)

    kind_weight = {
        "paper": 1.00, "interview": 1.00, "problem": 1.00, "repo": 0.95,
        "notes": 0.90, "course": 0.75, "job": 0.45, "news": 0.20, "other": 0.40,
    }.get(kind, 0.4)

    trust = 1.0 if str(item.get("channel") or "") in MATERIAL_CHANNELS else 0.0
    career = career_usability(item, kind)
    base = (rel * 0.32 + mat * 100 * 0.30 + trust * 100 * 0.08
            + min(1.0, len(str(item.get("summary") or "")) / 900.0) * 100 * 0.10
            + career * 100 * 0.20)
    return round(base * kind_weight, 2)


# ===========================================================================
# 6. 重要度（清理用）
# ===========================================================================
def importance(item: dict) -> tuple[int, str, list[str]]:
    """Return (0–100 importance, 'core'|'useful'|'noise', reasons).

    Replaces prune_items.score_item. Same three-tier contract; the difference is
    that the tiers now come from the shared kind/materiality authority, so the
    pruner and the deep-read planner can no longer disagree about the same card.
    """
    policy = load_policy()
    reasons: list[str] = []
    kind = classify_kind(item)
    mat = materiality(item, kind)
    rel = float(item.get("relevanceScore") or 0)
    cat = str(item.get("category") or "trend")
    ch = str(item.get("channel") or "")
    summary = str(item.get("summary") or "").strip()
    title = str(item.get("title") or "").strip()

    # 渠道质量门槛（HuggingFace 低人气社区模型等）仍是硬否决，保留原行为。
    floor = channel_quality_floor(item)
    if floor:
        return 0, "noise", [f"命中渠道质量门槛({floor[0]})：{floor[1]}"]

    flags = noise_flags(item)
    if flags:
        return 0, "noise", [f"命中噪音规则({flags[0][0]})：{flags[0][1]}"]

    # 无实质内容的资讯：不是知识，留着只会过期。
    #
    # 为什么放在这里而不是只放在采集闸门：采集闸门只拦「还没进来的」；库里已经
    # 有一批（实测 leiphone 的产品实测稿、公司评论稿、发布会稿）。清理走的是本函数，
    # 所以这条判断必须在这里也成立，否则「采集不收、清理也不删」会漂移。
    if kind == "news" and not news_has_substance(item):
        return 0, "noise", ["判定：泛 AI 资讯（无公式/推导/实验/数据集等技术实质），"
                            "读者明确要求不收"]

    score = rel * 0.40
    reasons.append(f"相关度 {rel:.0f} ×0.40")

    score += mat * 26.0
    reasons.append(f"知识材料性 {mat:.2f} ×26")

    fit = direction_fit(item)
    score += fit * 10.0
    reasons.append(f"方向贴合度 {fit:.2f} ×10")

    # 求职可用性：读者要求把「面试能直接用上」的内容提优先级。
    # 权重 14 与「方向贴合度 ×10」同量级，但因为它是 0–1 且大部分条目落在 0.2–0.9，
    # 实际影响是「手撕题/面经/核心论文往前排」，不会压倒相关度这个主信号。
    career = career_usability(item, kind)
    score += career * 14.0
    reasons.append(f"求职可用性 {career:.2f} ×14")

    if cat in MATERIAL_CATEGORIES:
        score += 16
        reasons.append(f"技术分类({cat}) +16")
    if ch in MATERIAL_CHANNELS:
        score += 12
        reasons.append(f"一手来源({ch}) +12")

    if kind == "interview":
        score += 9
        reasons.append("面经（面试流程/考点可复用）+9")
    elif kind == "problem":
        score += 9
        reasons.append("手撕/笔试真题 +9")
    elif kind == "notes":
        score += 5
        reasons.append("知识点/八股笔记 +5")

    if item.get("peerReviewed"):
        score += 6
        reasons.append("同行评审 +6")
    if item.get("codeAvailable"):
        score += 5
        reasons.append("有开源实现 +5")
    if item.get("ccf"):
        score += 4
        reasons.append(f"CCF-{item['ccf']} +4")

    if len(summary) >= 400:
        score += 6
        reasons.append("摘要充实 +6")
    elif len(summary) >= 120:
        score += 3
        reasons.append("摘要可用 +3")
    elif not summary:
        # 只降分、不再单独判死：是否保留由上面的分档决定（方向贴合的无摘要条目会被
        # 标为 useful 并转给深读层抓原文）。这里仍扣分，避免它挤占「今日速览」前排。
        score -= 30
        reasons.append("没有摘要（需深读层抓原文）-30")
    elif len(summary) < 80:
        score -= 10
        reasons.append("摘要过短 -10")

    if item.get("enriched"):
        score += 8
        reasons.append("已有深度解析 +8")
    if len(title) < 14:
        score -= 6
        reasons.append("标题过短 -6")
    if kind == "news":
        score -= 18
        reasons.append("资讯类（不可积累，读者明确要求少收）-18")
    if _hit(EPHEMERAL_HINTS, f"{title} {summary}") and kind == "news":
        score -= 6
        reasons.append("措辞易逝（最新/快讯类）-6")

    score = max(0, min(100, round(score)))

    # The tier decision is recorded as a reason too, so an archive report can say
    # WHY a card was removed instead of only "score below threshold" (which read as
    # nonsense when the tier came from a rule rather than from the number).
    min_mat = float(policy.get("minKeepMateriality", 0.22))
    if not summary:
        # 源信息里没有摘要 ≠ 不值得收。
        #
        # 读者的原话：「看到某个好的手撕算法或领域核心工作但是源信息中没有解析的，
        # 你也可以自己逐条深度解析并采集」。所以方向贴合的无摘要条目（典型是 HN /
        # Product Hunt 这类只给标题和链接的源）**不删**，而是标记出来交给深读层抓原文。
        # 只有「没摘要 + 方向也不贴」才按书签处理。
        if fit >= 0.5 and kind in ("paper", "repo", "problem", "notes",
                                   "interview", "course"):
            tier = "useful"
            reasons.append("无摘要但方向贴合 —— 保留，交给深读层抓原文后再解析")
        else:
            tier = "noise"
            reasons.append("判定：完全没有摘要且方向不贴合 —— 是书签，不是知识卡片")
    elif kind == "news" and mat < 0.5:
        tier = "noise"
        reasons.append(f"判定：纯资讯且材料性低（{mat:.2f}）—— 无法积累，只会过期")
    elif item.get("knowledgeBase"):
        # Reference cards from an allow-listed knowledge base. Two rules do NOT
        # apply to them, for one reason: the channel's family allow-list is already
        # the direction filter (I chose /algo/ /hot100/ /network/ /os/ /llm/ and
        # excluded 语言八股 / 银行面经 / 后端 at the source), and the summary is a
        # POINTER by design - a 题解 page's one-sentence meta description, or a
        # problem's metadata. So:
        #   * the content-depth floor would remove exactly the cards the reader
        #     asked for ("寻找两个正序数组的中位数（LeetCode 4）· 大厂高频手撕题"
        #     sat at 0.21 against a 0.22 floor);
        #   * the direction-fit rule would remove 计算机基础八股 (TCP 四次挥手 /
        #     epoll / malloc) that any technical interview asks.
        # Hard noise rules and the empty-summary rule above still apply.
        tier = "core"
        reasons.append("判定：参考资料型卡片（白名单知识库；摘要为指针，方向已由 family 白名单把关）")
    elif kind in ("interview", "problem", "notes") and fit < 0.25 and mat < 0.45:
        # 方向不贴合 **且** 内容不足以支撑它自己：Java/后端/运维面经、秋招情绪帖、
        # 与算法岗无关的「面试经验」。它们进 coding 只是因为标题里有「面经」两个字。
        # 两个条件是 AND，所以一篇内容扎实的偏方向面经不会被这条误杀 —— 避免出现
        # 「因为差 0.003 越过阈值就被删」这种说不清楚的判定。
        tier = "noise"
        reasons.append(f"判定：求职内容与目标方向无关（贴合度 {fit:.2f}，材料性 {mat:.2f}）")
    elif kind == "job" and fit < 0.10:
        tier = "noise"
        reasons.append(f"判定：岗位与本方向无关（贴合度 {fit:.2f}）")
    elif kind == "job":
        # 岗位 JD 天生就是短文本，不能因为没有摘要就判为噪音 —— 用户明确要
        # 「相关岗位」的持续积累。真正该下架的岗位由硬噪音规则（内推广告）拦。
        tier = "useful"
        reasons.append("判定：在招岗位（短 JD 不算低价值）")
    elif kind in ("paper", "repo", "course") and not item.get("knowledgeBase"):
        # 论文 / 仓库 / 课程：读者要的是「关键、核心、延伸扩展」的内容，而不是
        # 「一看最新或关联就放进来」。判断本身在 technical_reject() 里 —— 采集
        # 闸门用的是同一个函数，所以两处不可能给出不同结论。
        rej = technical_reject(item, kind)
        cfit = core_fit(item)
        if rej:
            tier = "noise"
            reasons.append(f"判定：{rej}")
        elif cfit >= 1.0 and (mat >= 0.55 or item.get("codeAvailable")
                              or item.get("peerReviewed")):
            tier = "core"
            reasons.append(f"判定：目标方向的核心论文/实现（技术贴合 {cfit:.2f}）")
        else:
            tier = "useful"
            reasons.append(f"判定：目标方向的延伸材料（技术贴合 {cfit:.2f}）")
    elif mat < min_mat:
        tier = "noise"
        reasons.append(f"判定：知识材料性 {mat:.2f} 低于保留门槛 {min_mat}")
    elif kind in ("interview", "problem", "notes") and mat >= 0.40:
        tier = "core"
        reasons.append("判定：方向相关的求职知识资产（面经/手撕题/八股）")
    elif cat in MATERIAL_CATEGORIES and mat >= 0.55:
        tier = "core"
        reasons.append("判定：技术方向且材料性充足")
    elif cat in ("job", "trend", "exam", "course") or ch in (
            "jobs_tencent", "jobs_deepseek", "nowcoder", "zhihu", "inbox"):
        tier = "useful"
        reasons.append(f"判定：求职/信息类（{cat}）")
    else:
        tier = "useful" if score >= 40 else "noise"
        reasons.append("判定：" + ("可用信息" if tier == "useful" else f"重要度 {score} 偏低"))
    return score, tier, reasons


def channel_quality_floor(item: dict) -> tuple[str, str] | None:
    """Channel-specific quality floors, mirroring the collectors' own gates.

    Kept here (moved from prune_items.py) because a rule that only lives in the
    collector cannot clean the corpus ingested BEFORE the rule existed.

    Note: older hf_models cards stored the counts in the summary TEXT rather than
    in qualitySignals, so both places are read.
    """
    ch = str(item.get("channel") or "")
    qs = item.get("qualitySignals") or {}
    if ch == "hf_models":
        dl = qs.get("downloads")
        likes = qs.get("likes")
        if dl is None or likes is None:
            m = re.search(r"downloads=(\d+).*?likes=(\d+)", str(item.get("summary") or ""))
            if not m:
                m = re.search(r"下载\s*(\d+)[^\d]+点赞\s*(\d+)", str(item.get("summary") or ""))
            if m:
                dl = int(m.group(1))
                likes = int(m.group(2))
        dl = int(dl or 0)
        likes = int(likes or 0)
        if dl < 2000 and likes < 15:
            return ("hf-model-low-popularity",
                    f"HuggingFace 社区低人气模型（下载 {dl} / 点赞 {likes}），"
                    f"多为个人上传，没有领域信号")
    return None


# ===========================================================================
# 6b. 论文主题饱和上限（清理「冗余」）
# ===========================================================================
# 为什么需要它
#   实测：文献库里没有任何「字面重复」（近似标题 Jaccard≥0.45 的对为 0），
#   但**数量严重饱和** —— 后训练 89 篇、Agent 72 篇、世界模型 59 篇、多模态 57 篇。
#   对求职备考来说，第 60 篇「又一个 GRPO 变体」的边际价值接近零，而它会把
#   真正关键的少数几篇淹掉。用户要的是「关键、核心、延伸扩展」，不是全量镜像
#   arXiv。所以这里给**论文**设分类上限：目标方向留宽（要深度），邻近方向留窄。
#
# 排序刻意**不以新鲜度为第一优先**（用户明确要求不要因为最新就收录）：
#   技术贴合 → 材料性 → 有没有开源实现 → 同行评审/CCF → 相关度（仅用于同档打平）
def paper_value_key(item: dict) -> float:
    """Value score used to decide WHICH papers survive a saturated category."""
    mat = materiality(item, "paper")
    cfit = core_fit(item)
    val = 3.0 * cfit + 2.5 * mat
    if item.get("codeAvailable"):
        val += 1.5          # 能复现、能手撕
    if item.get("peerReviewed") or item.get("ccf"):
        val += 1.5          # 顶会/CCF -> 更可能是里程碑方法
    val += 0.02 * float(item.get("relevanceScore") or 0)   # 仅作同档打平
    return round(val, 4)


def library_over_cap(items: list[dict], tier_of=None, policy: dict | None = None) -> dict:
    """Return {item id: reason} for paper cards over the per-category cap.

    `tier_of(item)` should return 'core' | 'useful' | 'noise'; cards already
    judged `noise` by another rule are skipped (they are removed anyway), so the
    cap only decides between cards that are all worth keeping on their own.
    """
    policy = policy or load_policy()
    if not policy.get("enforcePaperCap", True):
        return {}
    base_cap = int(policy.get("maxPapersPerCategory", 22))
    target_cap = int(policy.get("maxPapersPerCategoryTarget", 40))

    groups: dict[str, list] = {}
    for it in items:
        if classify_kind(it) != "paper":
            continue
        if it.get("knowledgeBase"):
            continue                       # 白名单知识库不受此限
        if tier_of is not None and tier_of(it) == "noise":
            continue
        groups.setdefault(str(it.get("category") or "trend"), []).append(it)

    out: dict = {}
    for cat, lst in groups.items():
        cap = target_cap if cat in TARGET_DIRECTIONS else base_cap
        if len(lst) <= cap:
            continue
        lst = sorted(lst, key=paper_value_key, reverse=True)
        for rank, it in enumerate(lst[cap:], start=cap + 1):
            out[it.get("id")] = (
                f"分类「{cat}」论文已达上限 {cap} 篇：本篇按「技术贴合/材料性/开源实现/"
                f"同行评审」排序第 {rank} 位（共 {len(lst)} 篇），属可查证的冗余")
    return out


# ===========================================================================
# 7. 聚合报告（自检 + 自我迭代提案共用）
# ===========================================================================
def _pct(x, n) -> float:
    return round(100.0 * x / n, 1) if n else 0.0


def quality_report(items: list[dict], enrichment: dict | None = None) -> dict:
    """Corpus-level knowledge-quality metrics.

    This is the answer to "库里积累的到底是不是知识". Every number here is
    asserted somewhere: selfcheck warns, and write_proposals turns the worst
    offenders into a reviewable proposal. One computation, two consumers.
    """
    enrichment = enrichment or {}
    n = len(items)
    kinds, cats, chans = Counter(), Counter(), Counter()
    mat_values: list[float] = []
    direction_stats: dict[str, dict] = {}
    career = Counter()
    news_items, low_signal = [], []
    off_direction: list[dict] = []
    channel_noise: dict[str, dict] = {}

    for it in items:
        kind = classify_kind(it)
        cat = str(it.get("category") or "trend")
        ch = str(it.get("channel") or "unknown")
        mat = materiality(it, kind)
        fit = direction_fit(it)
        kept = it.get("id") in enrichment
        kinds[kind] += 1
        cats[cat] += 1
        chans[ch] += 1
        mat_values.append(mat)

        row = channel_noise.setdefault(ch, {"total": 0, "news": 0, "lowSignal": 0})
        row["total"] += 1
        if kind == "news":
            row["news"] += 1
        if mat < 0.35:
            row["lowSignal"] += 1

        if kind in ("interview", "problem", "notes") and fit < 0.25 and mat < 0.45:
            off_direction.append({"id": it.get("id"), "kind": kind, "channel": ch,
                                  "directionFit": fit, "materiality": mat,
                                  "title": str(it.get("title"))[:78]})

        if cat in TARGET_DIRECTIONS or cat in ("rl", "agent", "foundation", "engineering",
                                               "paper", "course"):
            d = direction_stats.setdefault(cat, {"total": 0, "knowledge": 0, "news": 0, "deepRead": 0})
            d["total"] += 1
            if kind != "news":
                d["knowledge"] += 1
            else:
                d["news"] += 1
            if kept:
                d["deepRead"] += 1
        if kind in ("interview", "problem", "notes"):
            career[kind] += 1
        if cat == "job":
            career["job"] += 1

        if kind == "news":
            news_items.append({"id": it.get("id"), "title": str(it.get("title"))[:78],
                               "channel": ch, "materiality": mat})
        if mat < 0.35:
            low_signal.append({"id": it.get("id"), "title": str(it.get("title"))[:78],
                               "kind": kind, "channel": ch, "materiality": mat,
                               "ref": bool(it.get("knowledgeBase"))})

    mat_values.sort()
    mean_mat = round(sum(mat_values) / n, 3) if n else 0.0

    def q(p: float) -> float:
        if not mat_values:
            return 0.0
        return mat_values[min(len(mat_values) - 1, int(p * len(mat_values)))]

    offenders = sorted(
        ({"channel": c, **v, "newsShare": _pct(v["news"], v["total"]),
          "lowSignalShare": _pct(v["lowSignal"], v["total"])}
         for c, v in channel_noise.items() if v["total"] >= 5),
        key=lambda r: (-(r["newsShare"] + r["lowSignalShare"]), -r["total"]))

    return {
        "generatedAt": datetime.now(CST).isoformat(timespec="seconds"),
        "total": n,
        "byKind": dict(kinds.most_common()),
        "kindZh": {k: KIND_ZH.get(k, k) for k in kinds},
        "kindShare": {k: _pct(v, n) for k, v in kinds.most_common()},
        "byCategory": dict(cats.most_common()),
        "materiality": {
            "mean": mean_mat, "p25": q(0.25), "p50": q(0.50), "p75": q(0.75),
            "shareBelow035": _pct(len(low_signal), n),
        },
        "newsShare": _pct(kinds.get("news", 0), n),
        "lowSignalShare": _pct(len(low_signal), n),
        # Split the "thin cards" metric by population, because the two are not
        # comparable: a knowledge-base card is a POINTER to reference material
        # (one-sentence meta description, or a problem's metadata), while a feed
        # card is supposed to carry its own content. Measuring them together made
        # a healthy corpus look like it was filling with empty cards.
        "lowSignalShareFeed": _pct(sum(1 for it in low_signal if not it["ref"]),
                                   max(1, n - sum(1 for it in items if it.get("knowledgeBase")))),
        "lowSignalShareRef": _pct(sum(1 for it in low_signal if it["ref"]), n),
        "referenceShare": _pct(sum(1 for it in items if it.get("knowledgeBase")), n),
        "offDirectionShare": _pct(len(off_direction), n),
        "directions": direction_stats,
        "career": {
            "interview": career.get("interview", 0),
            "problem": career.get("problem", 0),
            "notes": career.get("notes", 0),
            "job": career.get("job", 0),
            "offDirection": len(off_direction),
        },
        "channelQuality": offenders[:10],
        "newsSamples": news_items[:25],
        "lowSignalSamples": low_signal[:25],
        "offDirectionSamples": off_direction[:25],
    }


def print_report(rep: dict) -> None:
    print("")
    print("=" * 74)
    print("知识质量报告（kind / materiality）")
    print("=" * 74)
    print(f"  条目总数      : {rep['total']}")
    print(f"  类型分布      : " + ", ".join(
        f"{KIND_ZH.get(k, k)}={v}" for k, v in list(rep["byKind"].items())[:9]))
    m = rep["materiality"]
    print(f"  材料性        : mean={m['mean']} p25={m['p25']} p50={m['p50']} p75={m['p75']}")
    print(f"  资讯占比      : {rep['newsShare']}%")
    print(f"  摘要偏薄      : 信息流 {rep.get('lowSignalShareFeed')}%"
          f"（参考资料型卡片 {rep.get('referenceShare')}% 里 {rep.get('lowSignalShareRef')}% 摘要短，"
          f"属其本来的形态：题解页 meta 描述 / 题号频度元数据）")
    c = rep["career"]
    print(f"  求职资产      : 面经={c['interview']} 手撕/笔试题={c['problem']} "
          f"知识点/八股={c['notes']} 岗位={c['job']}"
          f"   方向不贴合={c.get('offDirection', 0)}")
    if rep["directions"]:
        print("  方向覆盖（知识型/总数，已深读）:")
        for k, v in sorted(rep["directions"].items(), key=lambda kv: -kv[1]["total"]):
            print(f"      {k:<14} {v['knowledge']:>4}/{v['total']:<4}  deepRead={v['deepRead']}")
    if rep["channelQuality"]:
        print("  渠道噪音榜（资讯占比 / 低信号占比）:")
        for r in rep["channelQuality"][:6]:
            print(f"      {r['channel']:<16} n={r['total']:<4} "
                  f"news={r['newsShare']}%  lowSignal={r['lowSignalShare']}%")
    print("=" * 74)
    print("")


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="knowledge_quality.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    ap.add_argument("--write", action="store_true",
                    help="also write web/data/knowledge-quality.json")
    args = ap.parse_args(argv)

    try:
        index = json.loads((DATA / "items" / "index.json").read_text("utf-8"))
    except Exception as e:
        print(f"cannot read items/index.json: {e}", file=sys.stderr)
        return 1
    items = index.get("items") or []
    enrich = {}
    try:
        enrich = (json.loads((DATA / "enrichment.json").read_text("utf-8")) or {}).get("byId") or {}
    except Exception:
        pass

    rep = quality_report(items, enrich)
    if args.write:
        (DATA / "knowledge-quality.json").write_text(
            json.dumps(rep, ensure_ascii=False, indent=1), "utf-8")
        print(f"wrote {DATA / 'knowledge-quality.json'}")
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    else:
        print_report(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
