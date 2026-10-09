#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_problem_bank.py — 把手撕题 / 笔试题整理成「题库定位」页的数据源

要解决的问题（读者的原话）
  「对于算法题和仓库的整理，直接给出仓库链接虽然可以保留，但我更希望你能根据题库
    信息，阅读并自己深度解析相关手撕题、算法题等具体问题并整理到题库定位中附带
    深入的代码解析或配图解析等。」

改造前的状态
  · 「题库定位」页只读 jobs.json 里**人工整理**的 47 条（handWrittenCoding 22 +
    writtenExam 25），与每日采集完全脱节；
  · 每日采集进来的 168 条 kind=problem（codetop 的高频真题、代码随想/卡码笔记的
    题解页）只以卡片形式躺在知识库里，**没有一条**进入题库页；
  · 少数被深读的 problem 条目产出的是通用 enrichment（tldr/概念/图解），
    没有可运行代码、复杂度、易错点 —— 对「刷题」这个用途是不够的。

这个脚本做什么
  1. **归一**：把三个来源合并成同一个题目实体
       · codetop   —— 「公司 × 题号 × 被考频度」的真实真题元数据
       · 知识库题解 —— 代码随想录 / 卡码笔记 / 小林coding 的题解页
       · 人工题库   —— jobs.json 的 handWrittenCoding / writtenExam
     同一道题（同一个 LeetCode 题号，或同一个归一标题）只出现一次，来源并列。
  2. **挂载深度解析**：把 enrichment.json 里该题的分析（讲解 / 图解 / 概念 /
     代码 / 复杂度 / 易错点）挂到题目上，并标出解析完整度：
       deep    有题解代码 + 图解（可直接照着刷）
       partial 有讲解或图解，但缺代码/复杂度
       none    只有题面元数据，尚未深读（会在题库页标「待深读」）
  3. **输出** web/data/problem-bank.json，供前端「题库定位」页与自检读取。

设计约束（与本项目其它部分一致）
  · 不编造：题面/难度/频度/公司全部来自源数据；取不到的字段写 null。
  · 确定性：纯规则，不用模型，所以每天都能跑、结果可逐条核对。
  · 只读 + 写一个文件：不改 items/index.json，不改 enrichment.json。

用法
  python scripts/build_problem_bank.py            # 写入 web/data/problem-bank.json
  python scripts/build_problem_bank.py --show     # 同时打印汇总
  python scripts/build_problem_bank.py --check    # 只统计，不写
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"
OUT = DATA / "problem-bank.json"
CST = timezone(timedelta(hours=8))

try:
    if str(Path(__file__).resolve().parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    import knowledge_quality as KQ
except Exception:                                  # pragma: no cover
    KQ = None

# ---------------------------------------------------------------------------
# 题目实体的归一化
# ---------------------------------------------------------------------------
LC_NUM_RE = re.compile(r"(?:LeetCode|力扣|LC)\s*[#№]?\s*(\d{1,4})", re.I)
PROG_NUM_RE = re.compile(r"^\s*(\d{1,4})\.\s*(.+)$")          # 「1. 两数之和」

# --- 题号的命名空间：卡码网 ≠ LeetCode -------------------------------------
#
# 实测的坑（这也是「#102 沉没孤岛」出现在二叉树层序遍历位置上的原因）：
# 代码随想录的卡码网页面标题形如「102. 沉没孤岛 · 题解」，URL 是
# `algo/graph/kamacoder-0102-sink-isolated-islands.html`。改造前把「N. 标题」
# 前缀一律当成 LeetCode 题号，于是**卡码网第 102 题**和**LeetCode 102
# （二叉树的层序遍历）**共用同一个 key `lc-102`，标题、题面、深读解析互相覆盖，
# 而且因为「短标题优先」的规则，最后展示出来的是「沉没孤岛」。
#
# 全量统计有 9 组这样的撞号（卡码网号 → 被它劫持的 LeetCode 号）：
#   98 所有可达路径 / 98 验证二叉搜索树      101 孤岛的总面积 / 101 对称二叉树
#   102 沉没孤岛 / 102 二叉树的层序遍历      104 建造最大岛屿 / 104 二叉树的最大深度
#   106 岛屿的周长 / 106 中序+后序构造二叉树  108 冗余连接 / 108 有序数组转 BST
#   110 字符串接龙 / 110 平衡二叉树           111 构造二阶行列式 / 111 二叉树的最小深度
#   112 挑战boss / 112 路径总和
#
# 结论：**先判命名空间，再取号**。卡码网的号进 `km-<n>`，LeetCode 的号进 `lc-<n>`，
# 两个编号空间永不相交。这不是展示偏好问题 —— 卡码网是代码随想录配套的笔试练习
# 平台（华为 OD 风格），题目本来就该收，但它的 102 与 LeetCode 的 102 是两道完全
# 不同的题。
KAMACODER_RE = re.compile(r"kamacoder", re.I)
KB_NUM_RE = re.compile(r"kamacoder[-/](\d{1,4})", re.I)
# 代码随想录镜像 LeetCode 的页：`algo/array/0027-remove-element.html`、
# `hot100/0005.longest-palindromic-substring.html` —— 路径里的 4 位号 + slug
# 就是 LeetCode 题号与 slug，比标题前缀可信。
LC_MIRROR_RE = re.compile(r"/(\d{3,4})[.\-]([a-z0-9][a-z0-9\-]*)\.html?$", re.I)

# ---------------------------------------------------------------------------
# 赛道：模型/训练手撕 vs 算法/数据结构
#
# 读者的原话：「和模型、训练策略等直接相关的有 AI 模型面试含金量的题目应该和
# leetcode 那些纯算法或数据结构题做区分……更希望能直观方便和全面地学习如
# DPO/GRPO/MHSA/Transformer 等和模型以及训练等技术直接相关的手撕题」。
#
# 这两类题在面试里考的东西完全不同：算法题考「编码正确性与复杂度」，模型手撕考
# 「对结构/损失/训练机制的理解 + 能不能写出向量化实现 + 会不会横向对比变体」。
# 混在一个平铺列表里，LeetCode 题在数量上占绝对优势（158 vs 17），模型手撕会被
# 完全淹没 —— 这正是读者反馈「想学 DPO/GRPO 却不方便找」的根源。
#
# 判定是确定性的关键词规则，与 TOPIC_RULES 一样放在这里（题库域的判断归
# build_problem_bank.py，与 knowledge_quality.py 管语料域是同一条「一个结论
# 只有一处出处」的原则）。**只看标题与题面摘要**，不看正文 —— 正文里出现一个
# "attention" 太容易是巧合（与 application_domain 的 min_hits 教训一致）。
#
# 刻意收窄的词（避免误伤算法题）：
#   · 不用裸词「采样」——「蓄水池采样」是算法题；
#   · 不用裸词「norm」——只认 layernorm/rmsnorm/batchnorm 等具体层名；
#   · 「clip」只认 clip loss / clip 对比 / infonce 语境，避免命中 CLIP 剪裁。
#   · 「temperature」必须词边界——采样温度是标量，单数才是指它；裸词会命中
#     LeetCode 739「每日温度」英文题面里的 "temperatures"（天气温度），把一道
#     栈与队列的算法题误判进 model 赛道（2026-10-05 修复）。
MODEL_DRILL_RE = re.compile(
    r"mhsa|mha\b|self[- ]?attention|multi[- ]?head|attention机制|多头|注意力|"
    r"gqa|mqa|transformer|decoder[- ]?only|encoder[- ]?decoder|"
    r"layernorm|layer[- ]?norm|rmsnorm|rms[- ]?norm|batchnorm|batch[- ]?norm|"
    r"归一化层|swiglu|glu\b|ffn|前馈网络|残差连接|residual|"
    r"softmax|log[- ]?softmax|logsumexp|cross[- ]?entropy|交叉熵|"
    r"kl\s*(?:divergence|散度)|相对熵|"
    r"\brope\b|rotary|旋转位置|位置编码|positional[- ]?encoding|"
    r"kv\s*cache|flashattention|pagedattention|"
    r"\bdpo\b|\bgrpo\b|\bppo\b|rlhf|\bsft\b|\blora\b|qlora|lora\b|"
    r"beam\s*search|束搜索|长度归一化|"
    r"reward\s*model|奖励模型|偏好对齐|策略梯度|policy\s*gradient|"
    r"advantage|gae\b|信赖域|\btrpo\b|clip\s*(?:loss|对比|损失)|infonce|对比学习|contrastive|"
    r"diffusion|ddpm|去噪|noise\s*schedule|score\s*matching|"
    r"top[- ]?k\s*(?:采样|sampling)|top[- ]?p|nucleus|\btemperature\b|温度采样|"
    r"autograd|反向传播|backprop|手推.*梯度|梯度.*手推|"
    r"tokenizer|bpe\b|分词器|词元|"
    r"激活函数|activation\s*function|\bgelu\b|\brelu\b|\bsilu\b|swish|"
    r"embedding\s*层|词嵌入|query[- ]?key[- ]?value|qkv|"
    r"逻辑回归|logistic\s*regression|k[-]?means|kmeans|\bpca\b|主成分|"
    r"\bsvm\b|支持向量|决策树|随机森林|gbdt|xgboost|\bauc\b|\broc\b|knn|k近邻",
    re.I)

# 模型手撕的深度解析（research/model_drill_analysis.json，作者工具产出）。
# 人工题库（jobs.json）里的模型手撕题只有题面/要点/参考代码，深度解析
# （讲解/图解/概念/对比表/苏格拉底问答）挂在这里，由 merge_curated 并入。
DRILL_ANALYSIS_PATH = ROOT / "research" / "model_drill_analysis.json"

TRACKS = ("model", "algorithm", "exam")
TRACK_ZH = {"model": "模型与训练", "algorithm": "算法与数据结构", "exam": "笔试场景"}


def track_of(kind: str, title: str, summary: str, topics=None) -> str:
    """题目 -> 赛道。三类互斥且并集覆盖全部题：

    model     模型/训练手撕（attention/对齐/损失/归一化/位置编码…）
    algorithm 算法与数据结构（LeetCode / 卡码网 / KMP / 并查集…）
    exam      笔试场景（jobs.json 的 writtenExam）

    exam 优先于关键词：笔试题即使提到「采样」也按笔试场景归类，因为读者
    用这个视图找的就是「笔试里会出现的那类题」。
    """
    if str(kind or "") == "exam":
        return "exam"
    blob = f"{title or ''} {summary or ''}"
    if topics:
        blob += " " + " ".join(str(t) for t in topics)
    if MODEL_DRILL_RE.search(blob):
        return "model"
    return "algorithm"
FREQ_ITEM_RE = re.compile(r"([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z\s\.]{0,12}?)\s*(\d+)\s*次")
FREQ_TOTAL_RE = re.compile(r"共\s*(\d+)\s*次")
DIFF_RE = re.compile(r"难度\s*(简单|中等|困难|easy|medium|hard)", re.I)
LAST_ASK_RE = re.compile(r"最近一次(?:出现|被考)\s*[:：]?\s*(\d{4}-\d{2}-\d{2})")
SLUG_RE = re.compile(r"leetcode(?:\.cn|\.com)/problems/([a-z0-9\-]+)", re.I)
# 「（LeetCode 300）」「（LeetCode 补充题4）」这类采集层后缀，展示时要剥掉
LC_SUFFIX_RE = re.compile(r"\s*[（(]\s*(?:LeetCode|力扣|LC)\s*[#№]?\s*[\d补充满题]*\s*[）)]\s*$", re.I)
# 频度句里的非公司词。实测 `（共 264 次）` 会被 FREQ_ITEM_RE 抓成一个叫「共」的公司。
NOT_COMPANY = {"共", "总计", "合计", "总", "累计", "其中", "约"}

DIFF_ZH = {"简单": "easy", "中等": "medium", "困难": "hard",
           "easy": "easy", "medium": "medium", "hard": "hard"}

# 主题词表：与前端「主题热力」的取值保持一致（build_interview_index.py 的
# TOPICS 是面经视角，这里是刷题视角，所以单独一套）。
#
# 匹配必须带边界，不能是朴素子串。见下面 _kw_re() 与 TOPIC_PREFIX_GUARD 的说明 ——
# 这里踩过两次真实的坑，两次都会直接污染「AI 模型手撕 vs 纯算法题」的判定。
TOPIC_RULES: list[tuple[str, list[str]]] = [
    ("动态规划", ["动态规划", "dp", "背包", "最长递增", "编辑距离", "爬楼梯", "打家劫舍",
                  "stock", "股票", "零钱", "正则匹配"]),
    ("二分查找", ["二分", "binary search", "中位数", "旋转数组", "搜索插入"]),
    ("双指针", ["双指针", "two pointers", "滑动窗口", "三数之和", "盛最多水", "移动零"]),
    ("链表", ["链表", "listnode", "反转链表", "环形", "合并两个有序链表", "相交",
              "倒数第", "重排链表"]),
    ("二叉树", ["二叉树", "树的", "遍历", "层序", "中序", "前序", "后序", "bst",
                "最近公共祖先", "路径和", "镜像"]),
    ("图论", ["图", "岛屿", "拓扑", "course schedule", "并查集", "union", "最短路",
              "flood fill", "旋转图像"]),
    ("回溯", ["回溯", "排列", "子集", "组合", "n 皇后", "全排列", "括号生成"]),
    ("栈与队列", ["栈", "队列", "单调栈", "有效括号", "每日温度", "柱状图", "逆波兰"]),
    ("哈希表", ["哈希", "hashmap", "两数之和", "字母异位", "最长连续序列", "lru"]),
    ("排序与TopK", ["排序", "快排", "归并", "topk", "top-k", "堆", "第k", "数组中的第"]),
    ("字符串", ["字符串", "回文", "子串", "最长公共前缀", "字符串相加", "atoi", "翻转"]),
    ("位运算", ["位运算", "bit", "异或", "只出现一次"]),
    ("数学与模拟", ["数学", "模拟", "位1", "质数", "rand", "幂", "进制"]),
    # --- 算法岗手撕（不是力扣原题，而是手写算子/结构）---
    # 注意：这一组的判定权已经收归 knowledge_quality.py（见 AI_HANDWRITE_* ），
    # 这里保留是给前端「主题热力」用的标签，双边的词表必须保持同源。
    ("深度学习手撕", ["attention", "self-attention", "multi-head", "mha", "transformer",
                      "layernorm", "batchnorm", "softmax", "cross entropy", "交叉熵",
                      "kl", "conv", "卷积", "pooling", "dropout", "rope",
                      "flashattention", "kv cache", "gqa", "mqa", "rmsnorm", "算子",
                      "autograd", "反向传播", "nms", "iou", "损失函数",
                      "dpo", "grpo", "ppo", "lora", "sdpa", "pagedattention"]),
    ("机器学习手撕", ["kmeans", "k-means", "pca", "svm", "逻辑回归", "logistic",
                      "决策树", "gbdt", "auc", "感知机", "kd-tree", "knn"]),
]

# 中文关键词的「跨界守卫」。
#
# WHY：中文没有空格，两个词挨着写会**跨词边界**拼出一个关键词。实测两例（都是真实
# 误判，不是理论风险）：
#   · 「算子」被「计·算」+「子区域/子树」拼出来 —— 卡码网 44「开发商购买土地」
#     （讲前缀和）和 LeetCode 110「平衡二叉树」因此被标成「深度学习手撕」，
#     直接污染「AI 模型手撕 vs 纯算法题」的分栏。
#   · 「图」命中「意图 / 试图 / 地图 / 图像 / 图表」—— 图论主题常年虚高。
# 守卫分两种：不能紧跟在某些字**之后**，不能紧跟着某些字**之后**（后缀）。
# 加词时如果是个容易拼出来的短中文词，必须在这里补一条守卫。
TOPIC_PREFIX_GUARD: dict[str, str] = {
    # 「计算」+「子区域/子树/子问题」= 算子
    "算子": "计算运因可",
    # 「意图/试图/地图/图书/视图/制图/绘图/力图/企图/版图」
    "图": "意试地书视制绘力企版蓝截",
}
TOPIC_SUFFIX_BLOCK: dict[str, str] = {
    # 「图像/图片/图表/图书/图示/图解/图例」都不是图论
    "图": "像片表书示解例标",
    # 「堆积」不是堆
    "堆": "积",
}


def _kw_re(kw: str) -> "re.Pattern[str]":
    """把一个主题关键词编译成带边界的正则。

    两件事：
      1. **英文/数字词走词边界**。`dp` 曾是朴素子串，于是 `DPO`（一道训练策略题）
         被算进「动态规划」；`rope` 会命中 `Europe`；`conv` 会命中 `conversation`。
         边界判定用 `(?<![a-z0-9]) … (?![a-z0-9])`，与 knowledge_quality._term_re()
         同一套思路，并且容忍英文复数（`attention`/`attentions`）。
      2. **中文词走上面两张守卫表**，挡住跨词边界拼出来的假命中。

    中文词不加词边界是因为中文本来就没有词边界；英文词若不在这里收口，短词
    （dp / kl / nn / iou / auc）的假命中率会高到让主题分布失去意义。
    """
    cached = _KW_RE_CACHE.get(kw)
    if cached is not None:
        return cached
    has_cjk = re.search(r"[\u4e00-\u9fff]", kw) is not None
    if not has_cjk and re.search(r"[a-z0-9]$", kw, re.I):
        pat = r"(?<![a-z0-9])" + re.escape(kw) + r"(?:s|es)?" + r"(?![a-z0-9])"
    else:
        pat = re.escape(kw)
    guard = TOPIC_PREFIX_GUARD.get(kw)
    if guard:
        pat = "(?<![" + guard + "])" + pat
    block = TOPIC_SUFFIX_BLOCK.get(kw)
    if block:
        pat = pat + "(?![" + block + "])"
    rx = re.compile(pat, re.I)
    _KW_RE_CACHE[kw] = rx
    return rx


_KW_RE_CACHE: dict[str, "re.Pattern[str]"] = {}


def topic_hits(blob: str) -> list[str]:
    """返回 blob 命中的主题标签（去重、保持 TOPIC_RULES 的顺序）。"""
    out: list[str] = []
    for label, kws in TOPIC_RULES:
        if any(_kw_re(k).search(blob) for k in kws):
            out.append(label)
    return out


def topics_of(*texts: str) -> list[str]:
    blob = " ".join(t for t in texts if t).lower()
    return topic_hits(blob)


def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def load(p: Path, fallback):
    try:
        if p.exists():
            return json.loads(p.read_text("utf-8"))
    except Exception as e:
        print(f"[warn] {p.name}: {e}", file=sys.stderr)
    return fallback


def slug_key(title: str) -> str:
    s = re.sub(r"[\s\u3000]+", "", str(title or "").lower())
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "", s)
    return s[:60]


def problem_identity(title: str, summary: str, url: str) -> dict:
    """题目 -> {namespace, number, kbNumber, slug, key}。

    独立成一个函数的理由：`collect_from_items`（从语料卡片建库）与
    `merge_curated`（从人工题库建库）必须用**同一套**编号规则，否则同一道题
    会按两个不同的 key 各建一行。命名空间的说明见文件上方 KAMACODER_RE 段。

    取号优先级：
      1. URL 里带 `kamacoder`  -> 卡码网空间，号进 kbNumber，key = `km-<n>`
      2. 标题/摘要里显式写「LeetCode 102」  -> 最可信
      3. 代码随想录镜像页路径 `/0101-symmetric-tree.html` -> 号 + slug
      4. 兜底：「1. 两数之和」前缀（**仅在没有卡码网标记时**可用）
    """
    t = str(title or "")
    s = str(summary or "")
    u = str(url or "")

    slug = None
    m = SLUG_RE.search(u)
    if m:
        slug = m.group(1).lower()

    # 1) 卡码网：题号只在自己的编号空间里成立
    if KAMACODER_RE.search(u):
        m = KB_NUM_RE.search(u)
        if m:
            n = int(m.group(1))
            return {"namespace": "kamacoder", "number": None, "kbNumber": n,
                    "slug": None, "key": f"km-{n}"}
        return {"namespace": "kamacoder", "number": None, "kbNumber": None,
                "slug": None, "key": f"kb-{slug_key(t)}"}

    # 2) 标题里点名了 LeetCode 题号
    number = None
    m = LC_NUM_RE.search(t) or LC_NUM_RE.search(s)
    if m:
        number = int(m.group(1))

    # 3) 代码随想录的 LeetCode 镜像页
    m = LC_MIRROR_RE.search(u)
    if m:
        if number is None:
            number = int(m.group(1))
        if slug is None:
            slug = m.group(2).lower()

    # 4) 兜底：「1. 两数之和」
    if number is None:
        base = re.sub(r"\s*·\s*题解\s*$", "", t).strip()
        m = PROG_NUM_RE.match(base)
        if m:
            number = int(m.group(1))

    if number:
        return {"namespace": "leetcode", "number": number, "kbNumber": None,
                "slug": slug, "key": f"lc-{number}"}
    if slug:
        return {"namespace": "leetcode", "number": None, "kbNumber": None,
                "slug": slug, "key": f"lc-slug-{slug}"}
    return {"namespace": "kb", "number": None, "kbNumber": None,
            "slug": None, "key": f"kb-{slug_key(t)}"}


def parse_codetop(summary: str) -> dict:
    """Parse the metadata line codetop publishes into structured fields."""
    if not summary:
        return {}
    out: dict = {}
    total = FREQ_TOTAL_RE.search(summary)
    if total:
        out["frequency"] = int(total.group(1))
    else:
        nums = [int(n) for _c, n in FREQ_ITEM_RE.findall(summary)]
        if nums:
            out["frequency"] = max(nums)
    comps = []
    for name, n in FREQ_ITEM_RE.findall(summary):
        name = name.strip("、，,；;：: ")
        try:
            cnt = int(n)
        except ValueError:
            continue
        if name and name not in NOT_COMPANY and len(name) <= 12 and not name.isdigit():
            comps.append({"name": name, "count": cnt})
    if comps:
        comps.sort(key=lambda c: -c["count"])
        out["companies"] = comps
    m = DIFF_RE.search(summary)
    if m:
        out["difficulty"] = DIFF_ZH.get(m.group(1).lower(), m.group(1).lower())
    m = LAST_ASK_RE.search(summary)
    if m:
        out["lastAsked"] = m.group(1)
    return out


# ---------------------------------------------------------------------------
# 三个来源 -> 统一题目实体
# ---------------------------------------------------------------------------
def collect_from_items(items: list[dict], enrichment: dict) -> dict:
    """把每条 kind=problem 卡片并进题目实体。键的命名空间见 problem_identity()：
    LeetCode 用 `lc-<n>`，卡码网用 `km-<n>`，其余用标题 slug。"""
    bank: dict[str, dict] = {}
    for it in items:
        if KQ is not None:
            if KQ.classify_kind(it) != "problem":
                continue
        elif it.get("kind") != "problem":
            continue
        iid = it.get("id")
        title = str(it.get("title") or "")
        summary = str(it.get("summary") or "")
        url = str(it.get("url") or "")

        # --- 题号 / 命名空间：卡码网与 LeetCode 是两个编号空间 -----------
        ident = problem_identity(title, summary, url)
        number = ident["number"]
        kb_number = ident["kbNumber"]
        lcslug = ident["slug"]
        key = ident["key"]

        # 规范题名：去掉「· 题解」「· 大厂高频手撕题」这类采集层后缀
        clean = re.sub(r"\s*·\s*(题解|大厂高频手撕题|算法题解/知识库|课程笔记|八股|"
                       r"面试题|大模型笔记|算法知识点)\s*$", "", title).strip()
        clean = LC_SUFFIX_RE.sub("", clean).strip()
        clean = re.sub(r"^(\d{1,4})\.\s*", "", clean).strip() or title
        # 卡码网的号不是 LeetCode 号，剥掉前缀后要补一条明确的来源标注，
        # 否则「沉没孤岛」看上去像一道没有出处的题。
        if ident["namespace"] == "kamacoder" and kb_number:
            clean = f"{clean}（卡码网 {kb_number}）"

        meta = parse_codetop(summary)
        row = bank.setdefault(key, {
            "key": key, "namespace": ident["namespace"], "number": number,
            "kbNumber": kb_number, "slug": lcslug, "title": clean,
            "track": track_of(it.get("kind"), title, summary, it.get("tags")),
            "difficulty": None, "frequency": None, "companies": [],
            "lastAsked": None, "topics": [], "kind": "hand",
            "url": None, "sources": [], "origins": [], "itemIds": [],
            "statement": None, "keyPoints": [], "pitfalls": [],
            "code": None, "complexity": None, "edgeCases": [],
            "approach": None, "analysis": None,
        })
        # Which corpus cards make up this problem. plan_deep_read.py needs this:
        # a deep analysis is stored in enrichment.json keyed by the ITEM id, so
        # without the mapping the 题库 cannot be turned into a work list.
        if iid and iid not in row["itemIds"]:
            row["itemIds"].append(iid)
        # 更「像题目」的标题优先（短、不含「本周小结」这类聚合特征）
        if len(clean) < len(row["title"]) and "小结" not in clean:
            row["title"] = clean
        # 赛道合并规则：model 是「粘性」的 —— 一道题只要有一个来源是模型手撕，
        # 它就归模型赛道（宁可错放进模型区被读者看到，也不要被淹没在算法区）。
        ident_track = track_of(it.get("kind"), title, summary, it.get("tags"))
        if row.get("track") != "model" and ident_track == "model":
            row["track"] = "model"
        if number and not row["number"]:
            row["number"] = number
        if lcslug and not row["slug"]:
            row["slug"] = lcslug
        if meta.get("difficulty") and not row["difficulty"]:
            row["difficulty"] = meta["difficulty"]
        if meta.get("frequency") and not row["frequency"]:
            row["frequency"] = meta["frequency"]
        if meta.get("companies") and not row["companies"]:
            row["companies"] = meta["companies"]
        if meta.get("lastAsked") and not row["lastAsked"]:
            row["lastAsked"] = meta["lastAsked"]
        ch = str(it.get("channel") or "")
        if ch not in row["origins"]:
            row["origins"].append(ch)
        # 优先用 LeetCode 官方题页作为主链接（可点开做题），否则用第一个知识库页
        if not row["url"] or "leetcode" in url:
            row["url"] = url
        row["sources"].append({"title": title, "url": url, "channel": ch})
        if not row["statement"] and summary:
            row["statement"] = summary
        for t in topics_of(clean, summary, " ".join(str(x) for x in (it.get("tags") or []))):
            if t not in row["topics"]:
                row["topics"].append(t)

        # --- 挂载深读解析 -------------------------------------------------
        e = enrichment.get(iid)
        if e:
            row["analysis"] = _analysis_of(e, iid)
            row["analysisId"] = iid

    return bank


def _analysis_of(e: dict, iid: str) -> dict:
    """Extract the刷题-relevant layers out of a generic enrichment object."""
    prob = e.get("problem") or {}
    a = {
        "enrichmentId": iid,
        "tldr": e.get("tldr"),
        "why": e.get("why"),
        "diagram": e.get("diagram"),
        "concepts": e.get("concepts") or [],
        "teaching": e.get("teaching"),
        "keyPoints": e.get("keyPoints") or [],
    }
    if prob:
        a["problem"] = prob
    return a


def merge_curated(bank: dict, jobs: dict) -> None:
    """Fold the hand-curated 题库 (jobs.json) into the same entities."""
    for kind, field in (("hand", "handWrittenCoding"), ("exam", "writtenExam")):
        for p in (jobs.get(field) or []):
            title = str(p.get("title") or "")
            pid = str(p.get("id") or slug_key(title))
            # 人工题库的条目没有 URL，所以只会走「标题里点名 LeetCode」这一条路；
            # 没点名就保持原来的 `curated-<id>` 键，避免改动人工题的既有身份。
            ident = problem_identity(title, p.get("prompt") or "", "")
            number = ident["number"]
            key = ident["key"] if number else f"curated-{pid}"
            row = bank.get(key)
            if row is None:
                row = bank.setdefault(key, {
                    "key": key, "namespace": ident["namespace"], "number": number,
                    "kbNumber": ident["kbNumber"], "slug": None, "title": title,
                    "difficulty": None, "frequency": None, "companies": [],
                    "lastAsked": None, "topics": [], "kind": kind,
                    # 人工题库的行没有经过 collect_from_items，track 必须在这里判。
                    # exam 优先（track_of 内部处理），其余按标题/题面关键词判。
                    "track": track_of(kind, title, p.get("prompt") or "",
                                      p.get("topics")),
                    "url": None, "sources": [], "origins": [], "itemIds": [],
                    "statement": None, "keyPoints": [], "pitfalls": [],
                    "code": None, "complexity": None, "edgeCases": [],
                    "approach": None, "analysis": None,
                })
            elif row.get("track") != "model":
                # 已存在的行（采集来的同名题）可能当初没判出 model；
                # 人工题库点名了模型概念时以人工库为准升级，且不降级。
                t = track_of(kind, title, p.get("prompt") or "", p.get("topics"))
                if t == "model":
                    row["track"] = "model"
            row["curated"] = True
            if kind == "exam":
                row["kind"] = "exam"
                # track 不变量：kind=exam ⇒ track=exam（audit_tracks 断言这条）。
                # exam 的优先级高于 model 粘性 —— 笔试场景视图本来就是另一个入口。
                row["track"] = "exam"
            if not row["difficulty"] and p.get("difficulty"):
                row["difficulty"] = p["difficulty"]
            if not row["frequency"] and p.get("frequency"):
                row["frequency"] = p["frequency"]
            for t in (p.get("topics") or []):
                if t not in row["topics"]:
                    row["topics"].append(t)
            for t in topics_of(title, p.get("prompt") or ""):
                if t not in row["topics"]:
                    row["topics"].append(t)
            # 人工题库的题面/要点/易错点/参考代码比采集来的元数据更完整
            if p.get("prompt") and not row["statement"]:
                row["statement"] = p["prompt"]
            for k in (p.get("keyPoints") or []):
                if k not in row["keyPoints"]:
                    row["keyPoints"].append(k)
            for k in (p.get("pitfalls") or []):
                if k not in row["pitfalls"]:
                    row["pitfalls"].append(k)
            if p.get("referenceSolution") and not row["code"]:
                row["code"] = p["referenceSolution"]
            if p.get("answerOutline") and not row["approach"]:
                row["approach"] = p["answerOutline"]
            for s in (p.get("sources") or []):
                if isinstance(s, dict) and s.get("url"):
                    row["sources"].append({"title": s.get("title") or title,
                                           "url": s["url"], "channel": "curated"})
            if "curated" not in row["origins"]:
                row["origins"].append("curated")


def merge_drill_analysis(bank: dict) -> int:
    """把作者工具产出的模型手撕深度解析（research/model_drill_analysis.json）
    并进对应题库实体。返回挂载成功的条数。

    为什么单独一个来源：模型手撕题（MHSA/DPO/GRPO/RoPE…）在人工题库
    （jobs.json）里只有题面 + 参考代码，没有图解、没有变体对比、没有教学层；
    它们大多也没有对应的语料卡片，走不了 enrichment 通道。读者点名要
    「更全面、完整、有对比」，所以这批解析由作者工具直接写进 research/，
    键 = 题库实体键（curated-<id> / lc-<n>）。

    合并规则（与 enrichment.json 的「必须合并写」同一条原则，不许覆盖丢层）：
      · analysis 顶层：drill 只**填补缺失**的键，不覆盖深读已有结论；
      · problem 块：variants / comparison / interviewScript 是 drill 独有的层
        （通用深读从不产出），drill 是唯一出处、直接写入；
        其余键（approach/solution/complexity/…）仍是填补缺失；
      · 列表层（keyPoints/pitfalls/edgeCases）：并集去重。
    """
    drills = load(DRILL_ANALYSIS_PATH, {}) or {}
    items = drills.get("drills") or {}
    if not items:
        return 0
    LIST_KEYS = ("keyPoints", "pitfalls", "edgeCases")
    DRILL_ONLY = ("variants", "comparison", "interviewScript", "references")
    n = 0
    for key, d in items.items():
        row = bank.get(key)
        if row is None:
            print(f"[warn] drill 键没有对应题库实体，已跳过: {key}", file=sys.stderr)
            continue
        a = row.get("analysis") or {}
        for k, v in (d or {}).items():
            if k == "problem":
                pb = dict(a.get("problem") or {})
                for pk, pv in (v or {}).items():
                    if pk in DRILL_ONLY:
                        pb[pk] = pv
                    elif pk in LIST_KEYS:
                        merged = list(pb.get(pk) or [])
                        for x in (pv or []):
                            if x not in merged:
                                merged.append(x)
                        pb[pk] = merged
                    elif not pb.get(pk):
                        pb[pk] = pv
                a["problem"] = pb
            elif k in LIST_KEYS:
                merged = list(a.get(k) or [])
                for x in (v or []):
                    if x not in merged:
                        merged.append(x)
                a[k] = merged
            elif not a.get(k):
                a[k] = v
        a["fromDrill"] = True
        row["analysis"] = a
        n += 1
    return n


def audit_namespaces(problems: list[dict]) -> list[str]:
    """命名空间回归检查。

    上面 KAMACODER_RE 那段注释解释的撞号 bug（卡码网 102 顶掉 LeetCode 102）
    是靠「先判命名空间再取号」修的。这个函数把修好的状态**变成可断言的不变量**，
    否则下次有人调编号规则时，同样的 bug 会以另一种形式回来，而且症状还是
    「某道题的名字看起来不太对」——没人会注意到。

    断言两条：
      1. `km-<n>` 行的每一个来源 URL 都必须是卡码网页（含 kamacoder）；
      2. `lc-<n>` 行**不许**出现卡码网页作为来源。
    """
    bad: list[str] = []
    for p in problems:
        urls = [str(s.get("url") or "") for s in (p.get("sources") or [])]
        if p.get("url"):
            urls.append(str(p["url"]))
        kama = [u for u in urls if KAMACODER_RE.search(u)]
        if p.get("namespace") == "kamacoder":
            other = [u for u in urls if u and not KAMACODER_RE.search(u)]
            if other:
                bad.append(f"{p['key']} 标了卡码网，却混入非卡码网来源: {other[:2]}")
        elif p.get("key", "").startswith("lc-") and kama:
            bad.append(f"{p['key']} 是 LeetCode 键，却混入卡码网来源: {kama[:2]}")
    return bad


def finalize(bank: dict) -> list[dict]:
    out = []
    for row in bank.values():
        # 解析完整度：能照着刷 = deep
        a = row.get("analysis") or {}
        prob = (a.get("problem") or {}) if isinstance(a, dict) else {}
        has_code = bool(row.get("code") or (prob.get("solution") or {}).get("python")
                        or (prob.get("solution") or {}).get("code"))
        has_diag = bool((a.get("diagram") or {}).get("svg")
                        or (a.get("diagram") or {}).get("spec"))
        has_text = bool(row.get("statement") or a.get("tldr"))
        row["analysisStatus"] = ("deep" if (has_code and has_diag)
                                 else "partial" if (has_code or has_diag or has_text)
                                 else "none")
        row["hasCode"] = has_code
        row["hasDiagram"] = has_diag
        # 排序用：解析越完整、被考频度越高越靠前。**不含发布时间** ——
        # 一道 2021 年的高频题和今天新出现的题对备考一样重要（与知识库渠道同一条原则）。
        row["_rank"] = (
            {"deep": 3, "partial": 2, "none": 1}[row["analysisStatus"]],
            int(row["frequency"] or 0),
            len(row.get("companies") or []),
            len(row.get("keyPoints") or []),
        )
        row.pop("analysisId", None)
        out.append(row)
    out.sort(key=lambda r: r["_rank"], reverse=True)
    for r in out:
        r.pop("_rank", None)
    return out


def audit_tracks(problems: list[dict]) -> list[str]:
    """track 不变量：每题都有合法赛道；笔试题必须是 exam 赛道。"""
    bad: list[str] = []
    for p in problems:
        t = p.get("track")
        if t not in TRACKS:
            bad.append(f"{p['key']} track 非法: {t!r}")
        elif p.get("kind") == "exam" and t != "exam":
            bad.append(f"{p['key']} kind=exam 却被判为 {t}")
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="build_problem_bank.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--check", action="store_true", help="统计但不写文件")
    args = ap.parse_args(argv)

    items = load(DATA / "items" / "index.json", {}).get("items") or []
    enrichment = (load(DATA / "enrichment.json", {}) or {}).get("byId") or {}
    jobs = load(DATA / "jobs.json", {}) or {}

    bank = collect_from_items(items, enrichment)
    merge_curated(bank, jobs)
    n_drills = merge_drill_analysis(bank)
    problems = finalize(bank)

    by_status = Counter(p["analysisStatus"] for p in problems)
    by_kind = Counter(p["kind"] for p in problems)
    by_ns = Counter(p.get("namespace") or "kb" for p in problems)
    by_track = Counter(p.get("track") or "algorithm" for p in problems)
    topic_counts = Counter(t for p in problems for t in (p.get("topics") or []))
    comp_counts = Counter(c["name"] for p in problems for c in (p.get("companies") or []))

    doc = {
        "generatedAt": now_iso(),
        "source": "build_problem_bank.py (deterministic; 采集 + 人工题库 + 深读解析 三源合并)",
        "note": ("每道题 = 一个实体：题号来自题干/链接，「被考频度/公司/难度」来自 CodeTop 的"
                 "真实记录，深度解析来自 daily-agent 的题库深读（代码/图解/复杂度/易错点）。"
                 "取不到的字段一律 null，不做推测。按「解析完整度 → 被考频度」排序，"
                 "刻意不按发布时间 —— 高频老题与新题对备考等价。"
                 "题号分命名空间：`number` 只放 LeetCode 题号（lc-<n>），卡码网题号放 "
                 "`kbNumber`（km-<n>）—— 两边的 102 是两道不同的题，不能共用一个键。"),
        "counts": {
            "total": len(problems),
            "deep": by_status.get("deep", 0),
            "partial": by_status.get("partial", 0),
            "none": by_status.get("none", 0),
            "withCode": sum(1 for p in problems if p.get("hasCode")),
            "withDiagram": sum(1 for p in problems if p.get("hasDiagram")),
            "curated": sum(1 for p in problems if p.get("curated")),
            "byKind": dict(by_kind),
            "byNamespace": dict(by_ns),
            "byTrack": dict(by_track),
            "drills": n_drills,
        },
        "topics": [{"name": k, "count": v} for k, v in topic_counts.most_common()],
        "companies": [{"name": k, "count": v} for k, v in comp_counts.most_common(20)],
        "problems": problems,
    }

    if not args.check:
        with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)

    if args.show:
        print("")
        print("=" * 74)
        print(f"题库定位   共 {len(problems)} 题"
              f"（可照着刷 {doc['counts']['deep']} · 部分解析 {doc['counts']['partial']}"
              f" · 待深读 {doc['counts']['none']}）")
        print("=" * 74)
        print(f"  有代码 {doc['counts']['withCode']} · 有图解 {doc['counts']['withDiagram']}"
              f" · 人工题库 {doc['counts']['curated']} · 题型 {doc['counts']['byKind']}")
        print(f"  编号空间 {doc['counts']['byNamespace']}")
        print(f"  赛道 {doc['counts']['byTrack']} · 模型手撕深度解析 {doc['counts']['drills']} 题")
        print("  主题:", "、".join(f"{t['name']}×{t['count']}" for t in doc["topics"][:10]) or "—")
        print("  公司:", "、".join(f"{c['name']}×{c['count']}" for c in doc["companies"][:10]) or "—")
        print("")
        print("  解析最完整的前 12 题：")
        for p in problems[:12]:
            tag = (f"#{p['number']}" if p.get("number")
                   else f"卡码网{p['kbNumber']}" if p.get("kbNumber") else "   ")
            print(f"    [{p['analysisStatus']:<7}] {tag:<9}"
                  f" freq={str(p['frequency'] or '-'):>4} {p['title'][:44]}")
        print("=" * 74)
        print("")
    else:
        print(f"problem-bank: total={len(problems)} deep={doc['counts']['deep']} "
              f"partial={doc['counts']['partial']} none={doc['counts']['none']}")
    if not args.check:
        print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
    ns_bad = audit_namespaces(problems)
    if ns_bad:
        print(f"[WARN] 命名空间混用 {len(ns_bad)} 处（卡码网题号又跑进 LeetCode 键了）：",
              file=sys.stderr)
        for b in ns_bad[:5]:
            print("       " + b, file=sys.stderr)
    track_bad = audit_tracks(problems)
    if track_bad:
        print(f"[WARN] 赛道判定异常 {len(track_bad)} 处：", file=sys.stderr)
        for b in track_bad[:5]:
            print("       " + b, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
