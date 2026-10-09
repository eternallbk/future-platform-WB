#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plan_deep_read.py — 每日「深度解析配额」规划器

背景（你要的两件事）
  1. 不是所有采集到的条目都值得做深度解析。招聘帖、灌水讨论、重复转载这类内容
     进了卡片库只会造成冗余，还会稀释「今日速览」的信号。
  2. 你要的是**每个分类 2–10 条、有深度解析**，而不是几百条只有摘要的卡片。

所以这一步做两件事：
  A. **质量闸门**：给每条打分一个「是否值得深度解析」的判定，低价值内容标为
     `skim`（仍保留在库里可搜索、参与去重，但不会出现在深度解析队列里，
     也不会占用「今日速览」的位置）。
  B. **配额分配**：按分类给出 2–10 条的名额，用「相关度 + 内容完整度 + 类型多样性」
     排序挑出该深读的条目，写成一个**给 Agent 用的明确任务清单**。

为什么单独一个脚本：
  确定性层（collect.py）不该知道「深度解析」这件事，而 Agent 层需要一个稳定的
  输入契约。这个脚本把两者接起来，并且可以在不跑 Agent 的情况下单独检查配额是否合理。

用法:
  python scripts/plan_deep_read.py                 # 生成今日计划
  python scripts/plan_deep_read.py --per-category-min 3 --per-category-max 8
  python scripts/plan_deep_read.py --show          # 打印计划详情
退出码: 0 = 正常（即使队列为空）
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
CST = timezone(timedelta(hours=8))
PLAN = DATA / "deep-read-plan.json"

# ---------------------------------------------------------------------------
# Shared knowledge-quality judgement (scripts/knowledge_quality.py).
#
# WHY: this file used to carry its own NOISE_RULES while prune_items.py carried a
# DIFFERENT set, so the same card could be "not worth a deep read" here and "fine"
# there. The rules now live in one place, and this module only decides QUOTA.
# ---------------------------------------------------------------------------
try:
    if str(Path(__file__).resolve().parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    import knowledge_quality as KQ
    KQ_POLICY = KQ.load_policy()
except Exception as _kq_err:                      # pragma: no cover
    KQ = None
    KQ_POLICY = {}
    print(f"[warn] knowledge_quality unavailable ({_kq_err}); "
          f"falling back to the local noise rules", file=sys.stderr)

# ---------------------------------------------------------------------------
# 质量闸门规则
# ---------------------------------------------------------------------------
# 这些是**模式**而不是黑名单网站：同一个站点既有高价值内容也有灌水。
# 每条规则都要给出理由，方便日后复核是否误杀。
#
# 规则本体已经搬到 scripts/knowledge_quality.py（与卡片清理共用同一份），
# 这里只保留同名的数据结构，让深读计划文件的 policy 字段形状保持不变。
NOISE_RULES = ([{"id": rid, "why": why, "patterns": pats} for rid, why, pats in KQ.NOISE_RULES]
               if KQ is not None else [])

# 分类的价值权重：决定配额怎么倾斜。核心方向多给名额，趋势类少给。
CATEGORY_DEPTH_VALUE = {
    "multimodal": 1.00,
    "posttraining": 1.00,
    "worldmodel": 1.00,
    "rl": 0.90,
    "generative": 0.85,
    "coding": 1.00,
    "paper": 0.95,
    "foundation": 0.70,
    "engineering": 0.65,
    "agent": 0.60,
    "course": 0.55,
    "job": 0.50,      # 岗位信息进岗位看板，不需要逐条深度解析
    "exam": 0.80,
    "trend": 0.45,    # 趋势类留少量即可
}

# 值得深度解析的来源（同行评审 / 官方博客 / 一手仓库）
HIGH_TRUST_CHANNELS = {"arxiv", "openreview", "hf_papers", "s2", "openai_rss",
                       "hf_blog_rss", "github", "gh_trending", "inbox"}


def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def load(path: Path, fallback):
    try:
        if path.exists():
            return json.loads(path.read_text("utf-8"))
    except Exception as e:
        print(f"[warn] {path.name}: {e}", file=sys.stderr)
    return fallback


def category_mismatch(item: dict) -> str | None:
    """Return a reason when the item cannot plausibly belong to its category.

    Why this exists: the keyword classifier assigns a category from word hits, so
    unrelated items land in specialised buckets and then consume that bucket's
    deep-read quota. Measured on 2026-10-01, the top-scoring plan entry for
    `course` was "Algorithmic Justice and Responsible AI Journalism" and the top
    `exam` entry was "FIREWALL: A surrogate model for ..." - neither is a course
    or a practice problem. Surfacing them under those headings is worse than
    leaving the quota unfilled, so they are excluded from the plan.

    These categories expect an explicit marker; without it the item is treated as
    misclassified rather than silently relabelled.
    """
    cat = item.get("category")
    blob = f"{item.get('title') or ''} {item.get('summary') or ''}".lower()
    if cat == "course":
        if not re.search(r"课程|课|lecture|tutorial|mooc|coursera|cs\d{2,3}|"
                         r"公开课|读书会|walkthrough|bootcamp|教材|textbook|系列教程", blob):
            return "看起来不是课程（缺少课程/lecture/tutorial/公开课等标志）"
    elif cat == "exam":
        if not re.search(r"面试|笔试|手撕|手写|面经|真题|leetcode|算法题|编程题|"
                         r"八股|onsite|interview|coding (?:problem|question)|"
                         r"take-?home|题目|题库", blob):
            return "看起来不是笔试题（缺少面试/手撕/LeetCode/真题等标志）"
    elif cat == "job":
        if not re.search(r"工程师|研究员|实习|招聘|岗位|offer|算法专家|engineer|intern|"
                         r"scientist|developer|hiring|job|校招|社招|薪资|package", blob):
            return "看起来不是岗位信息（缺少招聘/工程师/实习等标志）"
    elif cat == "coding":
        if not re.search(r"算法题|手撕|手写|leetcode|题解|面经|八股|动态规划|"
                         r"binary search|two pointers|滑动窗口|并查集|单调栈|"
                         r"interview|coding|problem|solution", blob):
            return "看起来不是手撕题（本文归类可能错误）"
    elif cat == "unclassified":
        # No keyword matched at all. There is nothing to deep-read against a
        # category, and spending a quota slot on it would take that slot away from a
        # real direction. These items are reported instead (see the proposal's
        # noiseReport) so the keyword set can be extended deliberately.
        return "未命中任何分类关键词（应扩充关键词，而不是给它深度解析）"
    return None


def noise_reason(item: dict) -> str | None:
    """Return the rule id that marks this item as not worth a deep read."""
    if KQ is None:
        return None
    hit = KQ.noise_ids(item)
    return hit[0] if hit else None


def depth_score(item: dict) -> tuple[float, dict]:
    """How much does this item deserve a deep read? Higher is better.

    Delegates to knowledge_quality.depth_value so the ordering used for the daily
    quota is the same judgement the collector, the pruner and the self-check use.
    The difference that matters: a pure news item's ceiling is pinned low, and
    「面经 / 手撕题 / 八股笔记」rank level with papers - the reader asked for those
    to accumulate, not just new papers.

    `parts` is kept because the plan file exposes a scoreBreakdown to the UI.
    """
    rel = float(item.get("relevanceScore") or 0)
    if KQ is None:
        return rel, {"relevance": round(rel, 1)}
    kind = item.get("kind") or KQ.classify_kind(item)
    mat = item.get("materiality")
    if mat is None:
        mat = KQ.materiality(item, kind)
    mat = float(mat)
    score = KQ.depth_value(item, kind, mat)
    career = KQ.career_usability(item, kind)
    parts = {
        "kind": kind,
        "kindZh": KQ.KIND_ZH.get(kind, kind),
        "relevance": round(rel * 0.32, 1),
        "materiality": round(mat * 100 * 0.30, 1),
        "career": round(career * 100 * 0.20, 1),
        "directionFit": item.get("directionFit", KQ.direction_fit(item)),
    }
    return score, parts


def deep_read_blocker(item: dict) -> str | None:
    """Why this item must NOT take a deep-read quota slot (None = eligible).

    The reader's goal is deep analysis of **knowledge**: core concepts, algorithm
    derivations, interview write-ups and problem walkthroughs. Content that cannot
    be deepened - a funding announcement, a vent post, a Java-backend interview that
    has nothing to do with the target directions - is reported instead of analysed.
    """
    if KQ is None:
        return None
    # Recompute rather than trusting the stored value: after a rule change the stored
    # kind is stale (see collect.refresh_kq_fields), and a stale `notes` for what is
    # now `news` would let a generic AI-news item occupy a deep-read slot.
    kind = KQ.classify_kind(item)
    mat = KQ.materiality(item, kind)
    mat = float(mat)
    if kind == "news":
        return "资讯类（无法做深度解析，属于易逝信息）"
    if mat < float(KQ_POLICY.get("minMaterialityForDepth", 0.28)):
        return f"知识材料性过低（{mat:.2f}）：没有可深挖的实质内容"
    if kind in ("interview", "problem", "notes"):
        fit = item.get("directionFit")
        if fit is None:
            fit = KQ.direction_fit(item)
        if float(fit) < 0.25 and mat < 0.45:
            return ("求职内容与目标方向无关（例：后端/运维面经），"
                    f"贴合度 {float(fit):.2f} 且材料性 {mat:.2f} 不足")
    return None


FORMULA_CATEGORIES = {
    "multimodal", "posttraining", "worldmodel", "generative",
    "rl", "agent", "foundation", "engineering",
}


def build_backfill_queue(items: list[dict], enrichment: dict) -> list[dict]:
    """Items that are already enriched but whose analysis is INCOMPLETE.

    Why this exists: every enrichment written before the diagram mandate (and before
    the concept sub-fields were added) is thinner than what the workbench now
    promises. 12 entries had no diagram at all and 6 had no formula, which is
    exactly the "some cards explain, some don't" inconsistency the reader reported.
    New runs only ever look at un-enriched items, so those old entries would stay
    thin forever. This queue makes completing them an explicit, finite task.

    Ordered by how much is missing, so the worst entries are fixed first.
    """
    out = []
    for it in items:
        iid = it.get("id")
        e = enrichment.get(iid)
        if not e:
            continue                      # not analysed at all -> normal queue
        cat = str(it.get("category") or "")
        # Only these categories have a core formula worth extracting. For a job
        # posting, an interview write-up or a tutorial repo there IS no formula, so
        # demanding one would either waste a quota slot or invite the agent to invent
        # a generic equation - which is exactly the kind of fabrication the prompt
        # forbids. Measured: the naive rule asked for formulas on
        # "微信小店-推荐算法工程师" and "携程AI应用开发实习一面（OC）".
        wants_formula = cat in FORMULA_CATEGORIES
        missing = []
        if not (e.get("diagram") or {}).get("svg") and not (e.get("diagram") or {}).get("spec"):
            missing.append("diagram")
        if wants_formula and not e.get("formulas"):
            missing.append("formulas")
        if not e.get("concepts"):
            missing.append("concepts")
        # New teaching layers: the reader asked every deep analysis to explain by
        # teaching, not just summarise.
        if not e.get("teaching"):
            missing.append("teaching")
        if not missing:
            continue
        # Weight diagram gaps highest: a card without a figure is the visible defect.
        weight = 0.0
        if "diagram" in missing:
            weight += 3
        if "teaching" in missing:
            weight += 2
        if "formulas" in missing:
            weight += 1
        if "concepts" in missing:
            weight += 1
        out.append({
            "id": iid,
            "title": it.get("title"),
            "category": it.get("category"),
            "channel": it.get("channel"),
            "url": it.get("url"),
            "missing": missing,
            "backfillWeight": weight,
            "hasSummary": bool(str(it.get("summary") or "").strip()),
        })
    out.sort(key=lambda r: (-r["backfillWeight"], str(r["id"])))
    return out


def build_problem_bank_queue(enrichment: dict, cap: int) -> list[dict]:
    """Rank the 题库 by 被考频度 and return the problems still lacking a real analysis.

    Reads web/data/problem-bank.json (written earlier in the same run by
    build_problem_bank.py), which merges CodeTop 公司×题号×频度 + 知识库题解页 +
    人工题库. `analysisStatus` there is computed from what actually exists:
      · deep    = 已有可运行代码 + 图解 → 可照着刷，跳过
      · partial = 只有讲解/题面/人工代码之一 → 值得补齐
      · none    = 只有题面元数据 → 最需要解析

    Ordering: 状态优先（none 先于 partial，因为「什么都没有」比「缺个图」更急），
    同级按被考频度降序 —— 频度是唯一真实的「会不会被问到」信号，刻意不看发布日期。
    """
    bank = load(DATA / "problem-bank.json", {}) or {}
    problems = bank.get("problems") or []
    rank = {"none": 0, "partial": 1}
    rows: list[dict] = []
    for p in problems:
        status = str(p.get("analysisStatus") or "none")
        if status == "deep":
            continue
        ids = [i for i in (p.get("itemIds") or []) if i]
        # 没有语料卡片就没有可写的位置：enrichment.json 是按 item id 键控的。
        if not ids:
            continue
        target = next((i for i in ids if i not in enrichment), ids[0])
        rows.append({
            "itemId": target,
            "allItemIds": ids,
            "key": p.get("key"),
            "number": p.get("number"),
            "title": p.get("title"),
            "track": p.get("track"),
            "difficulty": p.get("difficulty"),
            "frequency": int(p.get("frequency") or 0),
            "companies": [c.get("name") for c in (p.get("companies") or [])][:8],
            "lastAsked": p.get("lastAsked"),
            "topics": p.get("topics") or [],
            "analysisStatus": status,
            "hasCode": bool(p.get("hasCode")),
            "hasDiagram": bool(p.get("hasDiagram")),
            "url": p.get("url"),
            "sources": [{"title": s.get("title"), "url": s.get("url")}
                        for s in (p.get("sources") or [])[:4]],
        })
    # 排序：**模型与训练赛道最优先**（读者点名「DPO/GRPO/MHSA/Transformer
    # 这类和模型训练直接相关的手撕题」是最高优先级），赛道内仍是
    # 「解析越缺越急 → 被考频度越高越急」。track 字段可能缺（旧数据），缺了当 algorithm。
    rows.sort(key=lambda r: (0 if r.get("track") == "model" else 1,
                             rank.get(r["analysisStatus"], 2),
                             -r["frequency"], -len(r["companies"]), str(r["title"])))
    return rows[:max(0, cap)]


def build_plan(per_min: int, per_max: int, fresh_only: bool) -> dict:
    index = load(DATA / "items" / "index.json", {}) or {}
    items = index.get("items") or []
    digest = load(DATA / "digest" / "today.json", {}) or {}
    fresh_ids = {i.get("id") for i in (digest.get("items") or [])}
    enrichment = (load(DATA / "enrichment.json", {}) or {}).get("byId") or {}

    # ------------------------------------------------------------------
    # Refresh `kind` for the whole corpus before planning.
    #
    # WHY: items/index.json is a snapshot written by the collector. Its `kind`
    # was judged by whatever knowledge_quality.py looked like THAT day. When the
    # classifier changes (e.g. a repo landing page stops counting as `problem`,
    # or an aggregation 题解页 is downgraded to `notes`), a stale index keeps the
    # old verdict and the planner would spend deep-read quota on the wrong rows —
    # this is exactly how 「本周小结！」汇总页 and 仓库首页 ended up at the top of
    # the 题库 deep-read queue. Recomputing here makes the plan always reflect the
    # current rules without waiting for the next collection run.
    # ------------------------------------------------------------------
    drift = 0
    if KQ is not None:
        for it in items:
            fresh = KQ.classify_kind(it)
            if it.get("kind") != fresh:
                drift += 1
                it["kindStale"] = it.get("kind")
                it["kind"] = fresh
        if drift:
            print(f"[plan] refreshed kind on {drift} item(s) whose stored verdict "
                  f"was stale")

    # Items already analysed but with an incomplete analysis (no diagram etc).
    backfill = build_backfill_queue(items, enrichment)

    # Candidates: not already enriched, and (optionally) only today's fresh items.
    pool = [i for i in items
            if i.get("id") not in enrichment
            and (not fresh_only or i.get("id") in fresh_ids)]

    by_cat: dict[str, list] = {}
    skim: list[dict] = []
    for it in pool:
        reason = noise_reason(it)
        if reason:
            skim.append({"id": it.get("id"), "title": (it.get("title") or "")[:90],
                         "category": it.get("category"), "rule": reason,
                         "why": next(r["why"] for r in NOISE_RULES if r["id"] == reason)})
            it["_noise"] = reason
            continue
        mismatch = category_mismatch(it)
        if mismatch:
            skim.append({"id": it.get("id"), "title": (it.get("title") or "")[:90],
                         "category": it.get("category"), "rule": "category-mismatch",
                         "why": mismatch})
            continue
        # Knowledge-quality gate: news, near-empty and off-direction career items
        # do not get a deep-read slot. They stay in the library, searchable.
        blocker = deep_read_blocker(it)
        if blocker:
            skim.append({"id": it.get("id"), "title": (it.get("title") or "")[:90],
                         "category": it.get("category"), "rule": "deep-read-blocker",
                         "kind": it.get("kind"),
                         "why": blocker})
            continue
        by_cat.setdefault(it.get("category") or "trend", []).append(it)

    selected: list[dict] = []
    per_category: dict[str, dict] = {}
    # Learning signals let the quota follow what the reader actually studies.
    # Without this the plan is blind to the reader's own behaviour and always
    # spends depth on the same static category weights.
    feedback = load(DATA / "feedback.json", {}) or {}
    fb_cat = feedback.get("byCategory") or {}
    max_fb = max(fb_cat.values()) if fb_cat else 0

    for cat, rows in sorted(by_cat.items()):
        scored = []
        for it in rows:
            s, parts = depth_score(it)
            # A small depth bonus for categories the reader engages with, capped at
            # +6 so an interest cannot starve the other directions.
            if max_fb:
                s = round(s + 6.0 * (fb_cat.get(cat, 0) / max_fb), 2)
            scored.append((s, parts, it))
        scored.sort(key=lambda x: (-x[0], str(x[2].get("id"))))

        catw = CATEGORY_DEPTH_VALUE.get(cat, 0.5)
        # Interest can lift the quota by up to +1 slot (never below the base).
        if max_fb and fb_cat.get(cat):
            catw = min(1.0, catw + 0.1 * (fb_cat[cat] / max_fb))
        quota = int(round(per_min + (per_max - per_min) * catw))
        quota = max(per_min, min(per_max, quota))

        picked = []
        # Diversify by channel so one chatty source cannot fill a category.
        seen_channel: dict[str, int] = {}
        for s, parts, it in scored:
            if len(picked) >= quota:
                break
            ch = str(it.get("channel") or "unknown")
            if seen_channel.get(ch, 0) >= max(2, quota // 2):
                continue
            seen_channel[ch] = seen_channel.get(ch, 0) + 1
            picked.append({
                "id": it.get("id"), "title": it.get("title"),
                "category": cat, "channel": ch,
                "kind": it.get("kind"),
                "relevanceScore": it.get("relevanceScore"),
                "materiality": it.get("materiality"),
                "depthScore": s, "url": it.get("url"),
                "hasSummary": bool(str(it.get("summary") or "").strip()),
                "scoreBreakdown": parts,
            })
        # If diversity filtering starved the category, top up from the remainder.
        if len(picked) < quota:
            taken = {p["id"] for p in picked}
            for s, parts, it in scored:
                if len(picked) >= quota:
                    break
                if it.get("id") in taken:
                    continue
                picked.append({
                    "id": it.get("id"), "title": it.get("title"),
                    "category": cat, "channel": str(it.get("channel") or "unknown"),
                    "kind": it.get("kind"),
                    "relevanceScore": it.get("relevanceScore"),
                    "materiality": it.get("materiality"),
                    "depthScore": s, "url": it.get("url"),
                    "hasSummary": bool(str(it.get("summary") or "").strip()),
                    "scoreBreakdown": parts,
                })
        selected += picked
        per_category[cat] = {
            "quota": quota, "picked": len(picked),
            "candidates": len(rows), "categoryWeight": catw,
        }

    # ------------------------------------------------------------------
    # 手撕题 / 笔试题的保底名额。
    #
    # WHY: the reader's newest requirement is to raise the priority of
    # 「手撕算法、各领域核心工作或问题」等面试能直接用的信息. Quota is allocated per
    # CATEGORY, and problems share `coding` / `exam` with 题解页、面经、八股笔记 - so a
    # high-frequency 手撕题 could be crowded out by a same-category article that merely
    # has a longer summary. This gives `problem` its own floor, in the same spirit as
    # the paper cap (that population has its own rules). It only ADDS slots - no
    # category loses any of its quota.
    # ------------------------------------------------------------------
    skimmed_ids = {s.get("id") for s in skim}
    picked_ids = {r.get("id") for r in selected}
    problem_floor = int(KQ_POLICY.get("minProblemsPerRun", 6))
    problem_cap = int(KQ_POLICY.get("maxProblemsPerRun", 14))

    def _as_row(score, parts, it, cat):
        return {
            "id": it.get("id"), "title": it.get("title"),
            "category": cat, "channel": str(it.get("channel") or "unknown"),
            "kind": it.get("kind"), "relevanceScore": it.get("relevanceScore"),
            "materiality": it.get("materiality"),
            "depthScore": score, "url": it.get("url"),
            "hasSummary": bool(str(it.get("summary") or "").strip()),
            # 没有摘要的条目（HN / 只给标题的源）不能跳过 —— 深读层要真的把原文抓下来
            # 再解析。这与 knowledge_quality 里「无摘要但方向贴合则保留」是同一条约定。
            "needsFetch": not bool(str(it.get("summary") or "").strip()),
            "scoreBreakdown": parts,
        }

    have_problems = [r for r in selected if r.get("kind") == "problem"]
    added_problems: list[str] = []
    if len(have_problems) < problem_floor:
        cand = []
        for it in pool:
            if it.get("id") in skimmed_ids or it.get("id") in picked_ids:
                continue
            if KQ is not None and KQ.classify_kind(it) != "problem":
                continue
            s, parts = depth_score(it)
            cand.append((s, parts, it))
        cand.sort(key=lambda x: (-x[0], str(x[2].get("id"))))
        room = min(problem_cap - len(have_problems), problem_floor - len(have_problems))
        for s, parts, it in cand[:max(0, room)]:
            row = _as_row(s, parts, it, it.get("category") or "coding")
            selected.append(row)
            added_problems.append(it.get("id"))

    problem_queue = [r for r in selected if r.get("kind") == "problem"]

    # ------------------------------------------------------------------
    # 题库驱动的深读清单。
    #
    # WHY this exists (the reader's core ask): 「根据题库信息，阅读并自己深度解析相关
    # 手撕题、算法题」. The per-category quota above can only pick problems that happen
    # to have arrived as a CARD this month — so a 264-次 高频题 that was collected last
    # month never gets (re)analysed, while a low-frequency 题解页 that happened to be
    # fresh does. Ranking must come from the 题库 (CodeTop 公司×题号×频度), which is
    # the only real "what gets asked" signal we have.
    #
    # This is an ADDITIONAL list, not a replacement: it is ordered by 被考频度, and it
    # only contains problems that are not yet 「可照着刷」(analysisStatus != deep) and
    # that we can actually write into — a deep analysis is stored in enrichment.json
    # keyed by ITEM id, so a problem with no corpus card is not actionable here.
    # ------------------------------------------------------------------
    bank_queue = build_problem_bank_queue(enrichment, problem_cap)

    selected.sort(key=lambda x: -x["depthScore"])
    return {
        "generatedAt": now_iso(),
        "generatedBy": "plan_deep_read.py",
        "policy": {
            "perCategoryMin": per_min,
            "perCategoryMax": per_max,
            "freshOnly": fresh_only,
            "note": ("每个分类挑 2–10 条做深度解析；其余条目仍保留在卡片库里可搜索、"
                     "参与去重，但不会进入深度解析队列，也不会挤占「今日速览」。"),
            "noiseRules": [{"id": r["id"], "why": r["why"]} for r in NOISE_RULES],
        },
        "totals": {
            "corpus": len(items),
            "alreadyEnriched": len(enrichment),
            "candidates": len(pool),
            "skimmed": len(skim),
            "selected": len(selected),
            "categories": len(per_category),
            "problems": len(problem_queue),
            "bankProblems": len(bank_queue),
        },
        "perCategory": per_category,
        "queue": selected,
        # The `problem` slice of the queue, surfaced separately because it has its own
        # output contract: a hand-writing problem must be analysed into runnable code +
        # complexity + pitfalls + diagram (see scripts/daily-agent.md §2.2), and the
        # result is fed into the 题库定位 page (web/data/problem-bank.json).
        "problemQueue": problem_queue,
        "problemQuota": {"floor": problem_floor, "cap": problem_cap,
                         "selected": len(problem_queue),
                         "addedByFloor": added_problems},
        # 题库优先级清单：按被考频度排序、尚未「可照着刷」的题。agent 应优先处理这批
        # （详见 scripts/daily-agent.md §2.2 的题库深读契约），产出直接进题库页。
        "problemBankQueue": bank_queue,
        # Entries whose EXISTING analysis is incomplete (no diagram / no formula /
        # no teaching layer). The agent must complete these as well - they are the
        # "some cards have analysis, some don't" cases the reader reported. Finite
        # work: each backfill shrinks this list permanently.
        "backfill": backfill,
        "backfillTotal": len(backfill),
        "skimSample": skim[:40],
        "skimByRule": _count_by(skim, "rule"),
    }


def _count_by(rows: list[dict], key: str) -> dict:
    out: dict = {}
    for r in rows:
        out[str(r.get(key))] = out.get(str(r.get(key)), 0) + 1
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="plan_deep_read.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--per-category-min", type=int, default=2)
    ap.add_argument("--per-category-max", type=int, default=10)
    ap.add_argument("--all", action="store_true",
                    help="consider the whole corpus, not just today's fresh items. "
                         "The daily runner passes this: a fresh-only plan describes at "
                         "most one day of work and silently discards the backlog of "
                         "cards that were never deep-read.")
    ap.add_argument("--fresh-only", action="store_true",
                    help="explicitly restrict the plan to today's fresh items")
    ap.add_argument("--show", action="store_true", help="print the queue")
    ap.add_argument("--dry-run", action="store_true", help="do not write the plan file")
    args = ap.parse_args(argv)

    # Default to the WHOLE corpus. Fresh-only is the special case, not the norm:
    # a card that was collected last week and never deep-read is exactly the
    # backlog this queue exists to drain.
    fresh_only = bool(args.fresh_only) and not args.all
    plan = build_plan(max(1, args.per_category_min), max(1, args.per_category_max),
                      fresh_only=fresh_only)

    t = plan["totals"]
    print(f"corpus={t['corpus']} candidates={t['candidates']} "
          f"skimmed={t['skimmed']} selected={t['selected']} over {t['categories']} categories")
    print("noise filtered by rule: " + (json.dumps(plan["skimByRule"], ensure_ascii=False) or "{}"))
    print("")
    print(f"{'category':<14}{'quota':>6}{'picked':>7}{'candidates':>11}  weight")
    for cat, info in sorted(plan["perCategory"].items(), key=lambda kv: -kv[1]["picked"]):
        marker = "  <-- under quota" if info["picked"] < info["quota"] else ""
        print(f"{cat:<14}{info['quota']:>6}{info['picked']:>7}{info['candidates']:>11}"
              f"  {info['categoryWeight']:.2f}{marker}")

    if args.show:
        print("")
        print("--- deep-read queue (top 25) ---")
        for row in plan["queue"][:25]:
            print(f"  {row['depthScore']:>6}  {row['category']:<13} {str(row['title'])[:62]}")

    if args.dry_run:
        print("\n--dry-run: plan not written")
        return 0

    with io.open(PLAN, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(plan, fh, ensure_ascii=False, indent=1)
    print(f"\nwrote {PLAN} ({PLAN.stat().st_size} bytes)")
    print("the daily agent layer reads this file as its work list "
          "(scripts/daily-agent.md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
