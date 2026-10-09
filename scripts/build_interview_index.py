#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_interview_index.py — 从面经/面试条目里抽取结构化信息，做成「面经速览」

为什么要单独抽一层
  采集层给面经条目存的 `summary` 是论坛原帖摘要（常常是吐槽 + 流水账 + 内推码），
  信息密度低：想回答"字节二面考了什么"必须点开每一条自己读。而面经是这套工作台里
  **时效性最强**的内容 —— 2024 年的面经对 2026 年的投递几乎没有参考价值。

  所以这里做一次**确定性**抽取（不用 LLM，因此每天都能跑、结果可复核）：
    公司 / 轮次 / 是否拿到 offer / 考察主题 / 是否含手撕题
  再按公司与主题聚合，直接回答"我在准备哪家、重点练什么"。

为什么用规则而不是让 agent 抽
  规则会漏，但不会编。面经标题的写法高度固定（"腾讯IEG后台开发实习一面面经（已过等二面）"），
  规则在这个场景下足够准；而且结果可以逐条核对。Agent 抽取放到深读层做补充更合适。

用法:
  python scripts/build_interview_index.py            # 写入 web/data/interview.json
  python scripts/build_interview_index.py --show     # 同时打印汇总
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"
CST = timezone(timedelta(hours=8))

# Company aliases, matched longest-first so "上海AI Lab" is not shadowed by anything
# short. Order matters: the first hit wins.
COMPANIES: list[tuple[str, str]] = [
    ("字节跳动", "字节跳动"), ("字节", "字节跳动"), ("bytedance", "字节跳动"), ("tiktok", "字节跳动"),
    ("腾讯", "腾讯"), ("tencent", "腾讯"), ("wxg", "腾讯"), ("ieg", "腾讯"), ("csig", "腾讯"),
    ("阿里", "阿里巴巴"), ("alibaba", "阿里巴巴"), ("淘天", "阿里巴巴"), ("通义", "阿里巴巴"),
    ("美团", "美团"), ("百度", "百度"), ("京东", "京东"), ("快手", "快手"), ("kuaishou", "快手"),
    ("小红书", "小红书"), ("xiaohongshu", "小红书"),
    ("华为", "华为"), ("huawei", "华为"), ("商汤", "商汤"), ("sensetime", "商汤"),
    ("旷视", "旷视"), ("megvii", "旷视"), ("智谱", "智谱AI"), ("zhipu", "智谱AI"),
    ("月之暗面", "月之暗面"), ("moonshot", "月之暗面"), ("minimax", "MiniMax"),
    ("阶跃", "阶跃星辰"), ("stepfun", "阶跃星辰"), ("deepseek", "DeepSeek"),
    ("地平线", "地平线"), ("小鹏", "小鹏汽车"), ("蔚来", "蔚来"), ("理想", "理想汽车"),
    ("比亚迪", "比亚迪"), ("得物", "得物"), ("携程", "携程"), ("trip.com", "携程"),
    ("网易", "网易"), ("netease", "网易"), ("小米", "小米"), ("oppo", "OPPO"), ("vivo", "vivo"),
    ("shopee", "Shopee"), ("微软", "微软"), ("microsoft", "微软"), ("英伟达", "NVIDIA"),
    ("nvidia", "NVIDIA"), ("amd", "AMD"), ("英特尔", "Intel"), ("intel", "Intel"),
    ("上海ai lab", "上海AI Lab"), ("上海人工智能实验室", "上海AI Lab"), ("shailab", "上海AI Lab"),
    ("普渡", "普渡机器人"), ("pudu", "普渡机器人"), ("联想", "联想"), ("lenovo", "联想"),
    ("平安", "平安"), ("招银", "招银网络"), ("中金", "中金"), ("蚂蚁", "蚂蚁集团"),
    ("ant group", "蚂蚁集团"), ("度小满", "度小满"), ("货拉拉", "货拉拉"), ("lalamove", "货拉拉"),
]

# Interview round, matched in order; the most specific pattern wins.
ROUNDS: list[tuple[str, str]] = [
    ("hr面", "HR面"), (r"hr\s*面", "HR面"),
    ("三面", "三面"), ("3面", "三面"),
    ("二面", "二面"), ("2面", "二面"),
    ("一面", "一面"), ("1面", "一面"),
    ("初面", "初面"), ("终面", "终面"), ("加面", "加面"),
    ("笔试", "笔试"), ("机试", "机试"),
]

OUTCOMES: list[tuple[str, str]] = [
    # NEGATIVE FIRST. "凉经" contains no 通过-ish substring, but "已过二面" and
    # "过" are extremely common, so a positive pattern checked first would swallow
    # failures. Measured bug: "字节国际化广告后端实习一二面凉经" was labelled 通过
    # because the bare "过" pattern matched before "凉经" was ever tested.
    ("已挂", "未通过"), ("挂经", "未通过"), ("挂了", "未通过"), ("凉经", "未通过"),
    ("凉了", "未通过"), ("婉拒", "未通过"), ("感谢信", "未通过"), ("没有offer", "未通过"),
    ("等offer", "待定"), ("等待", "待定"), ("流程中", "待定"), ("泡池子", "待定"),
    ("offer", "通过"), ("oc", "通过"), ("意向书", "通过"), ("上岸", "通过"),
    ("已过", "通过"), ("已拿", "通过"), ("通过", "通过"),
]

# Topics worth counting, because these are what the reader actually revises.
TOPICS: list[tuple[str, list[str]]] = [
    ("手撕/算法题", ["手撕", "手写", "算法题", "coding", "leetcode", "动态规划", "双指针",
                     "二叉树", "链表", "排序", "最长", "括号", "零钱", "滑动窗口"]),
    ("大模型/LLM", ["大模型", "llm", "transformer", "attention", "自注意力", "gpt", "token",
                    " kv ", "预训练", "微调", "sft", "rlhf", "dpo", "后训练"]),
    ("多模态/CV", ["多模态", "视觉", "vlm", "图像", "检测", "分割", "clip", "diffusion",
                   "视频", "cv"]),
    ("机器学习基础", ["bn", "batchnorm", "dropout", "过拟合", "正则", "损失函数", "梯度",
                      "反向传播", "优化器", "adam", "交叉熵", "softmax"]),
    ("强化学习", ["强化学习", "rl", "ppo", "grpo", "奖励", "reward", "策略", "q-learning"]),
    ("工程/系统", ["并发", "锁", "kafka", "mysql", "redis", "缓存", "数据库", "网络",
                   "tcp", "http", "操作系统", "线程", "分布式", "消息堆积", "调优"]),
    ("Agent/RAG", ["agent", "rag", "工具调用", "tool", "检索", "向量库", "记忆", "harness"]),
    ("项目/论文深挖", ["项目", "论文", "实习经历", "科研", "自我介绍", "为什么"]),
]


def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def load(p: Path, fb):
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return fb


def match_company(text: str) -> str:
    low = text.lower()
    for alias, canonical in COMPANIES:
        if alias in low:
            return canonical
    return ""


def match_round(text: str) -> str:
    low = text.lower()
    for pat, label in ROUNDS:
        if re.search(pat, low):
            return label
    return ""


def match_outcome(text: str) -> str:
    low = text.lower()
    for pat, label in OUTCOMES:
        if pat in low:
            return label
    return ""


def match_topics(blob: str) -> list[str]:
    low = blob.lower()
    hits = []
    for label, kws in TOPICS:
        if any(k.lower() in low for k in kws):
            hits.append(label)
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    idx = load(DATA / "items" / "index.json", {}) or {}
    items = idx.get("items") or []
    if not items:
        print("no items")
        return 1

    # A 面经 title is recognisable by STRUCTURE, not by containing "面试".
    # Measured: the loose pattern pulled in generic discussion posts
    # ("千万不要对面试官抱有太多滤镜！", "offer选择求助") which have no interview content.
    # Require either a write-up marker (面经/挂经/凉经/笔经) or a round word
    # (一面/二面/三面/HR面), optionally with a company name present.
    STRONG = re.compile(r"面经|挂经|凉经|笔经|机经|面試|面试题|手撕|hr面|hr 面", re.IGNORECASE)
    ROUND_W = re.compile(r"(?<![0-9])(一面|二面|三面|四面|初面|终面|加面|1面|2面|3面)(?!面)", re.IGNORECASE)
    rows = []
    for it in items:
        title = str(it.get("title") or "")
        summary = str(it.get("summary") or "")
        if not (STRONG.search(title) or ROUND_W.search(title)):
            continue                      # not an interview write-up
        blob = f"{title} {summary}"
        rows.append({
            "id": it.get("id"),
            "title": title,
            "url": it.get("url"),
            "channel": it.get("channel"),
            "category": it.get("category"),
            "publishedAt": it.get("publishedAt"),
            "lastSeen": it.get("lastSeen"),
            "company": match_company(blob),
            "round": match_round(blob),
            "outcome": match_outcome(blob),
            "topics": match_topics(blob),
            "hasCoding": any(k in blob.lower() for k in
                             ("手撕", "手写", "算法题", "coding", "leetcode", "写代码")),
            "summary": summary[:400],
        })

    # Freshest first: interview material is the most perishable content here, so the
    # UI should lead with what is still relevant.
    def sort_key(r: dict):
        return (r.get("publishedAt") or r.get("lastSeen") or "")
    rows.sort(key=sort_key, reverse=True)

    by_company = Counter(r["company"] for r in rows if r["company"])
    by_round = Counter(r["round"] for r in rows if r["round"])
    by_topic = Counter(t for r in rows for t in r["topics"])
    by_outcome = Counter(r["outcome"] for r in rows if r["outcome"])

    doc = {
        "generatedAt": now_iso(),
        "source": "build_interview_index.py (deterministic rules, no LLM)",
        "count": len(rows),
        "note": "面经时效性最强，按发布时间倒序；公司/轮次/结果/主题由规则抽取，可逐条核对",
        "companies": [{"name": k, "count": v} for k, v in by_company.most_common()],
        "rounds": [{"name": k, "count": v} for k, v in by_round.most_common()],
        "topics": [{"name": k, "count": v} for k, v in by_topic.most_common()],
        "outcomes": [{"name": k, "count": v} for k, v in by_outcome.most_common()],
        "withCoding": sum(1 for r in rows if r["hasCoding"]),
        "items": rows,
    }
    (DATA / "interview.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), "utf-8")

    if args.show:
        print("")
        print("=" * 74)
        print(f"面经速览   共 {doc['count']} 条   含手撕题 {doc['withCoding']} 条")
        print("=" * 74)
        print("  公司:", "、".join(f"{c['name']}×{c['count']}" for c in doc["companies"][:10]) or "—")
        print("  轮次:", "、".join(f"{c['name']}×{c['count']}" for c in doc["rounds"]) or "—")
        print("  结果:", "、".join(f"{c['name']}×{c['count']}" for c in doc["outcomes"]) or "—")
        print("  主题:", "、".join(f"{c['name']}×{c['count']}" for c in doc["topics"]) or "—")
        print("")
        print("  最近 8 条：")
        for r in rows[:8]:
            bits = " ".join(x for x in (r["company"], r["round"], r["outcome"]) if x)
            print(f"    [{(r.get('publishedAt') or '')[:10]}] {bits:<22} {r['title'][:56]}")
        print("=" * 74)
        print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
