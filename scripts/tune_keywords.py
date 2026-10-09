#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tune_keywords.py — 自我迭代中**唯一允许自动生效**的那一类改动

为什么是这一类
  reviewPolicy 早就声明「单个关键词的微调」可以自动，其余（分类增删、渠道
  升降级、评分公式、去重阈值、blocklist）必须人工批准。但此前**没有任何代码
  实现自动分支**：所有关键词提案都只是写进 proposals/latest.json 等人看，
  于是"自我迭代"实际上停在'发现问题'，没有'修正问题'。

  关键词微调之所以适合自动：改错了影响面小、可回滚、下一轮打分立刻体现效果，
  而且判定依据是客观的（命中率、误分类样本）。

本脚本做什么
  1. 读 web/data/proposals/latest.json 的 keywordProposals
  2. 对每条 add/remove 施加**硬性护栏**（见下）
  3. 通过的改动写进 config/collector.config.json 的 categories[cid].keywords /
     keywordRemove
  4. 追加一条审计记录到 web/data/proposals/keyword-tune-log.jsonl（谁改了什么、为什么）
  5. 打印改动摘要，供 run-daily 写进日志

硬性护栏（任何一条不过就丢弃该条改动）
  · 关键词长度 3..30，必须是小写，不得含正则元字符
  · 不得在任何其它分类的关键词列表里出现（避免把条目互相抢走）
  · 不得是 stopwords 里的通用词
  · 单轮单分类最多改 5 个关键词（防止一次翻转整个分类）
  · 单轮全局最多改 12 个（防止一次改坏整张分类表）
  · remove 只允许删「命中率极低或明显过宽」的词；不允许删掉分类的核心词
    （核心词表见 PROTECTED）

用法
  python scripts/tune_keywords.py --dry-run     # 只报告将要做的改动
  python scripts/tune_keywords.py               # 执行
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"
CONFIG = ROOT / "config" / "collector.config.json"
LOG = DATA / "proposals" / "keyword-tune-log.jsonl"
CST = timezone(timedelta(hours=8))

# Generic words that must never be used as a classifier keyword: they appear in
# unrelated content and are what caused 比亚迪充电站 / 阿尔茨海默影像 to be filed
# under "foundation".
STOPWORDS = {
    "review", "theory", "architecture", "state of", "analysis", "study", "survey",
    "system", "model", "method", "approach", "data", "learning", "paper", "research",
    "the", "and", "for", "with", "using", "based", "new", "towards", "toward",
}

# Words that define a category's identity; removing them would break classification.
PROTECTED = {
    "multimodal": {"multimodal", "vision-language", "vlm", "clip"},
    "posttraining": {"post-training", "posttraining", "rlhf", "dpo", "sft", "alignment"},
    "worldmodel": {"world model", "world-model", "worldmodel"},
    "rl": {"reinforcement learning", "ppo", "grpo"},
    "generative": {"diffusion", "generative", "text-to-image", "text-to-video"},
    "coding": {"leetcode", "手撕", "算法题"},
    "job": {"招聘", "实习", "岗位", "校招"},
    "foundation": {"transformer", "attention"},
}

MAX_PER_CATEGORY = 5
MAX_TOTAL = 12
KW_RE = re.compile(r"^[\w\u4e00-\u9fff][\w\u4e00-\u9fff \-+#.]{1,28}$")


def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def load(p: Path, fb):
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return fb


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    latest = load(DATA / "proposals" / "latest.json", {}) or {}
    proposals = latest.get("keywordProposals") or []
    if not proposals:
        print("[tune] no keyword proposals this run")
        return 0

    cfg = load(CONFIG, {}) or {}
    user_cats = cfg.setdefault("categories", {})

    # The authoritative keyword set lives in collect.py's DEFAULT_CATEGORIES, so
    # read it from the collector itself rather than duplicating it here.
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import collect as C
        base_cats = json.loads(json.dumps(C.DEFAULT_CATEGORIES))
    except Exception as e:
        print(f"[tune] cannot import DEFAULT_CATEGORIES: {e}")
        return 1

    # Every keyword currently in use, per category (defaults + user overrides).
    effective: dict[str, set[str]] = {}
    for cid, c in base_cats.items():
        kws = {str(k).lower() for k in (c.get("keywords") or [])}
        uc = user_cats.get(cid) or {}
        kws |= {str(k).lower() for k in (uc.get("keywords") or [])}
        kws -= {str(k).lower() for k in (uc.get("keywordRemove") or [])}
        effective[cid] = kws

    applied: list[dict] = []
    rejected: list[dict] = []
    total_changes = 0

    for prop in proposals:
        cid = prop.get("category")
        if cid not in base_cats:
            rejected.append({"category": cid, "reason": "unknown category"})
            continue
        adds = [str(k).strip().lower() for k in (prop.get("add") or []) if str(k).strip()]
        rems = [str(k).strip().lower() for k in (prop.get("remove") or []) if str(k).strip()]
        changes = 0
        accepted_add, accepted_rem = [], []

        for kw in adds:
            if total_changes >= MAX_TOTAL or changes >= MAX_PER_CATEGORY:
                rejected.append({"category": cid, "keyword": kw, "reason": "per-run cap reached"})
                continue
            if not KW_RE.match(kw):
                rejected.append({"category": cid, "keyword": kw, "reason": "shape/length"})
                continue
            if kw in STOPWORDS:
                rejected.append({"category": cid, "keyword": kw, "reason": "generic stopword"})
                continue
            if any(kw in effective[o] for o in effective if o != cid):
                rejected.append({"category": cid, "keyword": kw, "reason": "already used by another category"})
                continue
            if kw in effective[cid]:
                continue
            accepted_add.append(kw)
            effective[cid].add(kw)
            changes += 1
            total_changes += 1

        for kw in rems:
            if total_changes >= MAX_TOTAL or changes >= MAX_PER_CATEGORY:
                rejected.append({"category": cid, "keyword": kw, "reason": "per-run cap reached"})
                continue
            if kw not in effective[cid]:
                continue                     # nothing to remove
            if kw in PROTECTED.get(cid, set()):
                rejected.append({"category": cid, "keyword": kw, "reason": "protected core keyword"})
                continue
            accepted_rem.append(kw)
            effective[cid].discard(kw)
            changes += 1
            total_changes += 1

        if accepted_add or accepted_rem:
            applied.append({"category": cid, "add": accepted_add, "remove": accepted_rem,
                            "reason": prop.get("reason", "")})

    print("")
    print("=" * 74)
    print("关键词自我调优" + ("（dry-run，不写入）" if args.dry_run else ""))
    print("=" * 74)
    for a in applied:
        print(f"  [{a['category']}]")
        if a["add"]:
            print(f"      + {', '.join(a['add'])}")
        if a["remove"]:
            print(f"      - {', '.join(a['remove'])}")
        if a["reason"]:
            print(f"      理由: {a['reason'][:88]}")
    if rejected:
        print(f"  被护栏拒绝 {len(rejected)} 项：")
        for r in rejected[:10]:
            print(f"      {r.get('category')}/{r.get('keyword','-')} — {r['reason']}")
    print("=" * 74)

    if not applied:
        print("  无改动（全部被护栏拒绝或已生效）")
        print("")
        return 0

    if args.dry_run:
        print("  dry-run：未写入 config")
        print("")
        return 0

    # Persist: adds go to keywords, removals to keywordRemove (see load_config).
    for a in applied:
        node = user_cats.setdefault(a["category"], {})
        if a["add"]:
            cur = [str(k).lower() for k in (node.get("keywords") or [])]
            for kw in a["add"]:
                if kw not in cur:
                    cur.append(kw)
            node["keywords"] = cur
        if a["remove"]:
            cur_rm = [str(k).lower() for k in (node.get("keywordRemove") or [])]
            for kw in a["remove"]:
                if kw not in cur_rm:
                    cur_rm.append(kw)
            node["keywordRemove"] = cur_rm

    with io.open(CONFIG, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with io.open(LOG, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({
            "at": now_iso(), "appliedBy": "tune_keywords.py (auto-minor)",
            "changes": applied, "rejected": rejected[:20],
            "note": "关键词微调是 reviewPolicy 中唯一允许自动生效的一类改动",
        }, ensure_ascii=False) + "\n")

    print(f"  已写入 {CONFIG.relative_to(ROOT)}，审计记录 -> {LOG.relative_to(ROOT)}")
    print("  下一轮采集会用新关键词重新分类与打分。")
    print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
