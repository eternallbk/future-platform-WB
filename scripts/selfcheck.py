#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selfcheck.py - integrity / authenticity gate for the Future workbench data layer.
================================================================================
Run after every collection. It answers one question: "can the workbench trust
what is on disk right now?"

Checks
  A. Every JSON file under web/data parses (catches a half-written file).
  B. Required artifacts exist: manifest.json, items/index.json, digest/today.json,
     sources.json, taxonomy.json.
  C. Index consistency: unique ids, every item has a source URL, a category
     drawn from the taxonomy, and a plausible relevance score.
  D. Cross-file consistency: manifest.totalItems matches the index size;
     digest item ids are a subset of the index (no orphans).
  E. Authenticity signals: share of items with an empty summary, share of items
     whose URL host is not a known source host (possible junk), duplicate rate.
  F. Staleness: how long since the last successful run, and whether any channel
     has been failing for 3+ consecutive runs (the alert condition).

Exit codes
  0 = all checks pass
  2 = warnings only (data is usable, but something needs human attention)
  1 = errors (data is not trustworthy / missing)

Usage
  python scripts/selfcheck.py            # full report
  python scripts/selfcheck.py --status   # compact status for the console
  python scripts/selfcheck.py --summary  # one-line summary for logs
  python scripts/selfcheck.py --json     # machine-readable
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"
CST = timezone(timedelta(hours=8))

REQUIRED = [
    "manifest.json",
    "items/index.json",
    "digest/today.json",
    "sources.json",
    "taxonomy.json",
]

# Hosts we expect to see. Anything else is reported (not rejected) so that a
# mis-parsed page cannot silently pollute the knowledge base.
KNOWN_HOSTS = {
    "arxiv.org", "huggingface.co", "github.com", "openreview.net",
    "semanticscholar.org", "news.ycombinator.com", "reddit.com",
    "jiqizhixin.com", "qbitai.com", "openai.com", "rsshub.app",
    "nowcoder.com", "zhihu.com", "jobs.bytedance.com", "careers.tencent.com",
    "talent.alibaba.com", "zhipuai.cn", "moonshot.cn", "deepseek.com",
    "minimaxi.com", "shlab.org.cn", "aclanthology.org", "paperswithcode.com",
    "leetcode.cn", "codeforces.com", "youtube.com", "bilibili.com",
    # Algorithm knowledge bases (first-party sites of the 代码随想录 / 卡码笔记 公众号).
    "programmercarl.com", "notes.kamacoder.com", "kamacoder.com", "codefun2000.com",
    "xiaolincoding.com", "codetop.cc",
}


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []
        self.metrics: dict = {}

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def ok(self, msg):
        self.info.append(msg)


def load(path: Path, rep: Report):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except Exception as exc:
        rep.err(f"{path.relative_to(DATA)}: unparsable ({type(exc).__name__}: {exc})")
        return None


def check_all_json(rep: Report):
    bad = 0
    total = 0
    for p in sorted(DATA.rglob("*.json")):
        total += 1
        try:
            with open(p, encoding="utf-8") as fh:
                json.load(fh)
        except Exception as exc:
            bad += 1
            rep.err(f"{p.relative_to(DATA)}: {type(exc).__name__} {exc}")
    rep.metrics["jsonFiles"] = total
    if total and not bad:
        rep.ok(f"{total} JSON files parse cleanly")


def check_required(rep: Report):
    for rel in REQUIRED:
        p = DATA / rel
        if not p.exists():
            rep.err(f"missing required artifact: {rel}")
        elif p.stat().st_size < 3:
            rep.err(f"required artifact is empty: {rel}")
        else:
            rep.ok(f"{rel} present ({p.stat().st_size / 1024:.1f} KiB)")


def check_index(rep: Report, index, taxonomy, manifest):
    if not index:
        return
    items = index.get("items") or []
    rep.metrics["totalItems"] = len(items)
    if not items:
        rep.warn("items/index.json contains no items - has the collector ever succeeded?")
        return

    ids = [i.get("id") for i in items]
    dupes = [k for k, n in Counter(ids).items() if n > 1]
    if dupes:
        rep.err(f"{len(dupes)} duplicate item ids, e.g. {dupes[:3]}")
    else:
        rep.ok(f"{len(items)} items, all ids unique")

    cat_ids = {c.get("id") for c in (taxonomy or {}).get("categories", [])}
    no_url = [i for i in items if not i.get("url")]
    no_sum = [i for i in items if not (i.get("summary") or "").strip()]
    no_cat = [i for i in items if not i.get("category")]
    bad_cat = [i for i in items if cat_ids and i.get("category") not in cat_ids]
    bad_rel = [i for i in items if not isinstance(i.get("relevanceScore"), (int, float))]

    if no_url:
        rep.err(f"{len(no_url)} items have no source URL (they must be dropped at ingest)")
    if no_cat:
        rep.err(f"{len(no_cat)} items have no category")
    if bad_cat:
        rep.warn(f"{len(bad_cat)} items use a category not in taxonomy.json, e.g. "
                 f"{sorted({i.get('category') for i in bad_cat})[:5]}")
    if bad_rel:
        rep.warn(f"{len(bad_rel)} items have no numeric relevanceScore")
    sum_pct = 100.0 * (len(items) - len(no_sum)) / len(items)
    if sum_pct < 80:
        rep.warn(f"only {sum_pct:.0f}% of items carry a summary (target >= 80%)")
    else:
        rep.ok(f"{sum_pct:.0f}% of items carry a summary")

    hosts = Counter()
    unknown = Counter()
    for i in items:
        h = urlsplit(i.get("url") or "").netloc.lower().replace("www.", "")
        if not h:
            continue
        hosts[h] += 1
        if not any(h == k or h.endswith("." + k) for k in KNOWN_HOSTS):
            unknown[h] += 1
    rep.metrics["topHosts"] = hosts.most_common(8)
    if unknown:
        share = sum(unknown.values()) / max(1, len(items))
        msg = (f"{len(unknown)} source hosts are outside the known-host list "
               f"({share * 100:.0f}% of items), e.g. {unknown.most_common(4)}")
        (rep.warn if share > 0.15 else rep.ok)(msg)
    else:
        rep.ok("every source host is a recognised channel host")

    if manifest and manifest.get("totalItems") is not None:
        if int(manifest["totalItems"]) != len(items):
            rep.warn(f"manifest.totalItems={manifest['totalItems']} but index has {len(items)} items")
        else:
            rep.ok(f"manifest.totalItems matches the index ({len(items)})")

    # digest <-> index consistency
    digest = None
    p = DATA / "digest" / "today.json"
    if p.exists():
        try:
            digest = json.loads(p.read_text("utf-8"))
        except Exception:
            digest = None
    if digest:
        idset = set(ids)
        fresh = digest.get("items") or []
        orphans = [i.get("id") for i in fresh if i.get("id") not in idset]
        if orphans:
            rep.warn(f"{len(orphans)} digest items are absent from the index (orphans)")
        else:
            rep.ok(f"digest/today.json is a consistent subset ({len(fresh)} fresh items)")

    cats = Counter(i.get("category") for i in items)
    chans = Counter(i.get("channel") for i in items)
    rep.metrics["byCategory"] = dict(cats.most_common())
    rep.metrics["byChannel"] = dict(chans.most_common(12))
    if cat_ids:
        uncovered = sorted(cat_ids - set(cats))
        if uncovered:
            rep.info.append(f"categories with no items yet: {', '.join(uncovered)}")


def check_runs(rep: Report, manifest):
    runs = None
    p = DATA / "logs" / "runs.json"
    try:
        if p.exists():
            runs = json.loads(p.read_text("utf-8"))
    except Exception as exc:
        rep.err(f"logs/runs.json unparsable: {exc}")
        return
    if not isinstance(runs, list) or not runs:
        rep.warn("no run history recorded yet")
        return
    rep.metrics["runs"] = len(runs)
    last = runs[0]
    when = last.get("startedAt")
    rep.ok(f"last run {when} status={last.get('status')} new={last.get('newItems')} "
           f"channels={last.get('channelsOk')}/{last.get('channelsTotal')}")

    if when:
        try:
            age = datetime.now(CST) - datetime.fromisoformat(when)
            hours = age.total_seconds() / 3600
            rep.metrics["hoursSinceLastRun"] = round(hours, 1)
            if hours > 36:
                rep.warn(f"last run was {hours:.0f}h ago - the 18:00 schedule may be failing")
            else:
                rep.ok(f"last run was {hours:.1f}h ago")
        except Exception:
            pass

    # channels failing 3+ consecutive runs -> alert (per the reliability spec)
    fails: Counter = Counter()
    for r in runs[:6]:
        for part in str(r.get("notes") or "").split(";"):
            part = part.strip()
            m = re.match(r"^([\w\-]+)=(error|blocked|empty)$", part)
            if m and m.group(2) in ("error", "blocked"):
                fails[m.group(1)] += 1
    hard = {k: v for k, v in fails.items() if v >= 3}
    if hard:
        rep.warn(f"channels failing for 3+ consecutive runs: {hard} -> needs human review "
                 f"(see web/data/proposals/)")
    rep.metrics["channelFailureStreaks"] = dict(fails)


def check_proposals(rep: Report):
    p = DATA / "proposals"
    if not p.exists():
        rep.info.append("no proposals directory yet (created by the agent deep-read layer)")
        return
    files = sorted(p.glob("*.json"))
    if not files:
        rep.info.append("no proposals queued for human review")
    else:
        rep.ok(f"{len(files)} proposal file(s) waiting for human review: "
               f"{', '.join(f.name for f in files[-3:])}")


def check_collection_quality(rep: Report, index, manifest):
    """Is the corpus still pointed at the goal (algorithms / job hunting)?

    WHY: the integrity checks above only prove the FILES are consistent. A corpus
    can be perfectly consistent and still be useless - e.g. if one talkative channel
    floods a category, or the relevance gate drifts so low that everything is
    "relevant", or items start arriving with no summary. Those are the failure modes
    that actually reduce the workbench's value, so they are asserted here too.
    """
    items = (index or {}).get("items") or []
    if not items:
        return

    # 1. Category concentration. One category dominating means either over-collection
    #    from one channel or a mis-tuned keyword set.
    from collections import Counter
    cats = Counter(i.get("category") for i in items)
    total = len(items)
    top_cat, top_n = cats.most_common(1)[0]
    share = top_n / total
    if share > 0.30 and top_cat not in ("agent",):
        rep.warn(f"category '{top_cat}' holds {share:.0%} of the corpus "
                 f"({top_n}/{total}) - possible over-collection or keyword drift")
    else:
        rep.ok(f"category balance acceptable (largest: {top_cat} {share:.0%})")

    # 2. Relevance spread. If nearly everything scores high, the score stops
    #    discriminating and the ranking cannot surface the best items.
    rels = [float(i.get("relevanceScore") or 0) for i in items]
    high = sum(1 for r in rels if r >= 70) / max(1, len(rels))
    low = sum(1 for r in rels if r < 30) / max(1, len(rels))
    if high > 0.60:
        rep.warn(f"{high:.0%} of items score >=70 - the relevance score is no longer "
                 f"discriminating; consider raising minRelevance or reweighting")
    else:
        rep.ok(f"relevance spread is discriminating (>=70: {high:.0%}, <30: {low:.0%})")

    # 3. Summary coverage.
    #
    # 没有摘要不再等于「无法深读」：源站不给摘要的渠道（Hacker News 只给标题和链接）
    # 由采集层标为 needsFetch，深读层负责把原文取下来再解析。所以这里只提醒「需要抓取」，
    # 不再是「无法处理」。数量应当很小 —— 若显著上升，说明某个源站改了返回格式。
    no_sum = sum(1 for i in items if not str(i.get("summary") or "").strip())
    if no_sum:
        rep.warn(f"{no_sum} item(s) carry no summary — the deep-read layer fetches these "
                 f"URLs first (needsFetch). A sudden increase means a source changed "
                 f"its response format")
    else:
        rep.ok("every item carries a summary")

    # 4. Feedback loop. Without feedback.json, ranking never adapts to the reader.
    fb = load(DATA / "feedback.json", rep)
    if isinstance(fb, dict) and (fb.get("byCategory") or fb.get("byChannel")):
        n_star = fb.get("starredCount", 0)
        rep.ok(f"learning signals active ({n_star} starred, "
               f"{len(fb.get('byCategory') or {})} categories) - ranking follows your study")
    else:
        rep.warn("no learning signals: ranking is purely keyword-based. Use "
                 "「写出学习信号」on the 进度与统计 page to let it follow your interests")

    # 5. Deep-read coverage trend, so a stalled agent layer is visible.
    enrich = load(DATA / "enrichment.json", rep) or {}
    n_enr = enrich.get("count") or len(enrich.get("byId") or {})
    if n_enr:
        rep.ok(f"deep-read coverage {n_enr}/{total} = {n_enr / total:.1%}")
    else:
        rep.warn("no deep-read enrichment yet - layer 2 may not be running")

    # 6. Technical-material purity and paper saturation.
    #
    # WHY these two: the checks above prove the corpus is CONSISTENT and roughly
    # on-goal. Neither notices the two ways a 求职 workbench quietly degrades:
    #   (a) papers that are really physics / medicine / other people's domain
    #       applications drifting in on a keyword, and
    #   (b) one direction silently accumulating far more papers than anyone can
    #       use - the "冗余" the reader asked about. Neither is an error; both
    #       make the library worse every day. Judged by the same module the
    #       collector and the pruner use, so all three can never disagree.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import knowledge_quality as KQ          # noqa: PLC0415
    except Exception as e:                       # pragma: no cover
        rep.warn(f"knowledge-quality checks unavailable: {e}")
        return

    papers = [i for i in items if KQ.classify_kind(i) == "paper"]
    if papers:
        off_dir = [i for i in papers if KQ.technical_reject(i, "paper")]
        share = len(off_dir) / len(papers)
        if off_dir:
            rep.warn(f"{len(off_dir)}/{len(papers)} ({share:.0%}) 的论文与目标方向无具体技术关联或"
                     f"属于领域外/单一领域应用，例如「{(off_dir[0].get('title') or '')[:44]}」"
                     f" -> python scripts/prune_items.py --apply")
        else:
            rep.ok(f"论文方向纯度良好（{len(papers)} 篇全部与目标方向有具体技术关联）")

        # Saturation: per-category paper counts against the configured caps.
        policy = KQ.load_policy()
        base_cap = int(policy.get("maxPapersPerCategory", 22))
        target_cap = int(policy.get("maxPapersPerCategoryTarget", 40))
        from collections import Counter as _C
        per_cat = _C(i.get("category") for i in papers)
        over = {c: n for c, n in per_cat.items()
                if n > (target_cap if c in KQ.TARGET_DIRECTIONS else base_cap)}
        if over:
            rep.warn("论文数量超过分类上限（冗余）："
                     + "；".join(f"{c}={n}" for c, n in sorted(over.items(), key=lambda kv: -kv[1])[:4])
                     + " -> python scripts/prune_items.py --apply")
        else:
            rep.ok(f"论文数量未超上限（最大类别 {max(per_cat.values()) if per_cat else 0} 篇）")


def check_redundancy(rep: Report):
    """Is the corpus accumulating redundant or attention-diluting content?

    WHY this belongs in the daily self-check: every other check here proves the data
    is CONSISTENT. None of them notices that the corpus is slowly filling with the
    same thing reported repeatedly, or with items that matched no tracked direction
    at all. That is the "后期冗余" failure - it never errors, it just makes the
    workbench less useful every day.

    Implemented by reusing analyze_redundancy.build_report() so the daily gate and the
    on-demand report can never disagree about what counts as redundant.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import analyze_redundancy as AR          # noqa: PLC0415  (optional at runtime)
    except Exception as e:                        # pragma: no cover
        rep.warn(f"redundancy analysis unavailable: {e}")
        return
    try:
        items = (load(DATA / "items" / "index.json", rep) or {}).get("items") or []
        if not items:
            return
        enrich = (load(DATA / "enrichment.json", rep) or {}).get("byId") or {}
        r = AR.build_report(items, enrich)
    except Exception as e:
        rep.warn(f"redundancy analysis failed: {e}")
        return

    l0, l3 = r["l0"], r["l3_lowInformation"]
    if l0["duplicateUrls"] or l0["duplicateIds"]:
        rep.warn(f"硬重复：{l0['duplicateIds']} 个重复 id、{l0['duplicateUrls']} 个共用 URL "
                 f"-> 跑 python scripts/dedupe_deep.py --apply")
    else:
        rep.ok("无硬重复（重复 id / 共用 URL 均为 0）")

    share = l3["unclassifiedShare"]
    if share >= 0.15:
        rep.warn(f"未分类占 {share:.1%}（{l3['unclassified']} 条）：这些条目没有命中任何方向关键词，"
                 f"属于纯注意力占用 -> 补关键词后 python scripts/collect.py --rescore")
    elif share >= 0.05:
        rep.warn(f"未分类占 {share:.1%}（{l3['unclassified']} 条），建议补关键词")
    else:
        rep.ok(f"未分类占比健康（{share:.1%}）")

    # Repetition: N titles in one category all opening with the same words. Measured
    # on a healthy 720-item corpus the worst category is ~3%, so >10% is a real signal
    # rather than the noise a token-frequency metric produced.
    over = [s for s in r["l2_saturation"] if s["share"] >= 0.10]
    if over:
        rep.warn("标题套式重复：" + "；".join(
            f"{s['category']} 有 {s['count']} 条都以 '{s['topToken']}' 开头（{s['share']:.0%}）"
            for s in over[:3]))
    else:
        rep.ok("无标题套式重复（同类目标题前缀重合率均 <10%）")

    homo = [h for h in r["l4_homogeneity"] if h["nearPairShare"] >= 0.10]
    if homo:
        rep.warn("分类内主题同质化：" + "；".join(
            f"{h['category']} 相似配对 {h['nearPairShare']:.0%}" for h in homo[:3]))
    else:
        rep.ok("分类内主题分散度正常")

    high = [a for a in r["worklist"] if a["severity"] == "high"]
    rep.metrics["redundancy"] = {
        "duplicateUrls": l0["duplicateUrls"],
        "unclassifiedShare": share,
        "belowGate": l3["belowGate"],
        "highSeverity": len(high),
    }


def check_knowledge_quality(rep: Report, index):
    """Is the corpus ACCUMULATING KNOWLEDGE, or just filling up?

    WHY this is a separate check from check_collection_quality: that one proves the
    files are internally coherent (unique ids, balanced categories, summaries
    present). A corpus can be perfectly coherent and still be the wrong corpus -
    full of fresh-but-ephemeral news and off-direction interview write-ups while
    the things the reader actually studies (algorithm derivations, target-direction
    interview questions, 八股 notes, hand-written problems) never accumulate.

    Every number comes from scripts/knowledge_quality.py, the same authority the
    collector, the deep-read planner and the pruner use - so this check cannot
    disagree with what actually got ingested or queued.

    Thresholds are set so a HEALTHY corpus passes: a warning here means a real,
    actionable gap, not a stylistic preference. A guard that always fails is the
    same as no guard.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import knowledge_quality as KQ
    except Exception as e:                            # pragma: no cover
        rep.warn(f"knowledge-quality check unavailable: {e}")
        return
    items = (index or {}).get("items") or []
    if not items:
        return
    try:
        enrich = (load(DATA / "enrichment.json", rep) or {}).get("byId") or {}
        kq = KQ.quality_report(items, enrich)
    except Exception as e:
        rep.warn(f"knowledge-quality analysis failed: {e}")
        return

    rep.metrics["knowledgeQuality"] = {
        "byKind": kq["byKind"],
        "kindShare": kq["kindShare"],
        "materiality": kq["materiality"],
        "newsShare": kq["newsShare"],
        "lowSignalShare": kq["lowSignalShare"],
        "career": kq["career"],
    }

    # 1. Corpus composition by knowledge type - the headline number for "what is
    #    this library made of".
    zh = "、".join(f"{KQ.KIND_ZH.get(k, k)} {v}" for k, v in list(kq["byKind"].items())[:6])
    rep.ok(f"知识类型分布：{zh}")

    # 2. Ephemeral news. The reader explicitly does not want unrelated news, and a
    #    news item is worthless the day after it lands.
    if kq["newsShare"] > 5.0:
        rep.warn(f"资讯类占 {kq['newsShare']}% 偏高：这类内容会过期、不能积累，"
                 f"建议收紧趋势类关键词（trend 权重仍是最低的一档）")
    else:
        rep.ok(f"资讯占比健康（{kq['newsShare']}%）")

    # 3. Thin cards. Measured per population on purpose: a knowledge-base card is a
    #    POINTER to reference material (a 题解 page's one-sentence meta description,
    #    a CodeTop problem's metadata) and is short by design; a feed card is
    #    supposed to carry its own content. Asserting on the combined number made a
    #    healthy corpus look like it was filling with empty cards.
    feed_share = kq.get("lowSignalShareFeed", kq["lowSignalShare"])
    if feed_share > 20.0:
        rep.warn(f"信息流里低材料性条目占 {feed_share}%：有一批没有实质内容的卡片，"
                 f"跑 python scripts/prune_items.py --show 20 复核")
    else:
        rep.ok(f"信息流低材料性占比可接受（{feed_share}%）")
    rep.info.append(
        f"参考资料型卡片 {kq.get('referenceShare', 0)}%（{kq.get('lowSignalShareRef', 0)}% 摘要较短，"
        f"属参考资料本来的形态：题解页的 meta 描述、题号/频度元数据）")

    # 4. Materiality must stay discriminating, or the ranking cannot surface depth.
    if kq["materiality"]["p50"] < 0.35:
        rep.warn(f"材料性中位数只有 {kq['materiality']['p50']}：一半以上的卡片"
                 f"知识含量偏低")
    else:
        rep.ok(f"知识材料性中位数 {kq['materiality']['p50']}")

    # 5. Target directions must be covered by KNOWLEDGE, not by news.
    thin = [c for c in KQ.TARGET_DIRECTIONS
            if (kq["directions"].get(c) or {}).get("knowledge", 0) < 15]
    if thin:
        rep.warn("以下目标方向的知识型条目不足 15 条：" + "、".join(
            f"{c}({(kq['directions'].get(c) or {}).get('knowledge', 0)})" for c in thin))
    else:
        rep.ok("四个目标方向都有足量知识型条目")

    # 6. Career knowledge assets - the reader named these explicitly as things that
    #    should keep accumulating. Measured: 手撕题 sat at 1 inventory-wide until
    #    this check existed, which is exactly the kind of silent gap it catches.
    c = kq["career"]
    gaps = [(KQ.KIND_ZH[k], c[k]) for k in ("interview", "problem", "notes") if c[k] < 8]
    if gaps:
        rep.warn("求职知识资产积累不足（目标各 ≥8）：" + "、".join(f"{n} {v}" for n, v in gaps)
                 + "；这不是内容稀缺，是采集盲区（见 proposals 里的 kindGapProposals）")
    else:
        rep.ok("求职知识资产（面经/手撕题/知识点）均已形成积累："
               + "、".join(f"{KQ.KIND_ZH[k]} {c[k]}" for k in ("interview", "problem", "notes")))

    # 7. Off-direction career content that only landed in the library because the
    #    title contained 「面经」.
    if kq["offDirectionShare"] > 10.0:
        rep.warn(f"{kq['offDirectionShare']}% 的求职类条目与目标方向无关"
                 f"（后端/运维面经等）：来源关键词过宽，建议收窄")
    else:
        rep.ok(f"求职类内容方向贴合度正常（不贴合 {kq['offDirectionShare']}%）")


def check_problem_bank(rep: Report):
    """题库的键空间是否还分得清「LeetCode 题号」与「卡码网题号」。

    WHY this belongs in the daily self-check: 这两套题号曾经共用一个键空间，
    于是卡码网第 102 题（沉没孤岛）顶掉了 LeetCode 102（二叉树的层序遍历）——
    标题、题面、深读解析互相覆盖。症状是「某道题的名字看起来不太对」，属于
    不会报错、只会悄悄让题库不可信的那一类故障。所以把修好之后的状态变成
    每天都会断言一次的不变量。

    复用 build_problem_bank.audit_namespaces()，保证「构建时」与「自检时」
    用的是同一套判据（与 knowledge_quality 同一条原则：一个结论只有一处来源）。
    """
    bank = load(DATA / "problem-bank.json", rep)
    if not isinstance(bank, dict):
        return
    problems = bank.get("problems") or []
    if not problems:
        rep.warn("problem-bank.json 里没有题目 —— 题库页会是空的")
        return
    keys = [str(p.get("key") or "") for p in problems]
    dupes = [k for k, n in Counter(keys).items() if n > 1]
    if dupes:
        rep.err(f"problem-bank 有重复键 {dupes[:3]} —— 两道不同的题又合并了")
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import build_problem_bank as BPB            # noqa: PLC0415
        bad = BPB.audit_namespaces(problems)
    except Exception as e:                          # pragma: no cover
        rep.warn(f"题库命名空间检查不可用: {e}")
        return
    if bad:
        rep.err(f"{len(bad)} 处题号命名空间混用（卡码网题号跑进了 LeetCode 键）：{bad[:2]}")
    else:
        ns = Counter(p.get("namespace") or "kb" for p in problems)
        deep = sum(1 for p in problems if p.get("analysisStatus") == "deep")
        rep.ok(f"题库 {len(problems)} 题键空间干净（LeetCode {ns.get('leetcode', 0)} · "
               f"卡码网 {ns.get('kamacoder', 0)} · 其他 {ns.get('kb', 0)}），"
               f"其中可照着刷 {deep}")


def build_report() -> Report:
    rep = Report()
    check_all_json(rep)
    check_required(rep)
    manifest = load(DATA / "manifest.json", rep) or {}
    index = load(DATA / "items" / "index.json", rep)
    taxonomy = load(DATA / "taxonomy.json", rep)
    check_index(rep, index, taxonomy, manifest)
    check_runs(rep, manifest)
    check_proposals(rep)
    check_collection_quality(rep, index, manifest)
    check_knowledge_quality(rep, index)
    check_redundancy(rep)
    check_problem_bank(rep)
    rep.metrics["generatedAt"] = datetime.now(CST).isoformat(timespec="seconds")
    return rep


def print_report(rep: Report):
    print("")
    print("=" * 72)
    print("Future 工作台 · 数据层自检报告")
    print("=" * 72)
    for line in rep.info:
        print(f"  [ok]   {line}")
    for line in rep.warnings:
        print(f"  [warn] {line}")
    for line in rep.errors:
        print(f"  [ERR]  {line}")
    print("-" * 72)
    print(f"  结论: {len(rep.info)} 项通过, {len(rep.warnings)} 项警告, {len(rep.errors)} 项错误")
    m = rep.metrics
    if m.get("byCategory"):
        top = list(m["byCategory"].items())[:6]
        print("  分类分布: " + ", ".join(f"{k}={v}" for k, v in top))
    if m.get("byChannel"):
        top = list(m["byChannel"].items())[:6]
        print("  渠道分布: " + ", ".join(f"{k}={v}" for k, v in top))
    if m.get("topHosts"):
        print("  主要域名: " + ", ".join(f"{h}({n})" for h, n in m["topHosts"][:5]))
    print("=" * 72)
    print("")


def print_status(rep: Report):
    m = rep.metrics
    print("")
    print("── Future 工作台 · 数据层状态 ─────────────────────────────")
    print(f"  条目总数      : {m.get('totalItems', 0)}")
    print(f"  运行历史      : {m.get('runs', 0)} 次")
    if m.get("hoursSinceLastRun") is not None:
        print(f"  距上次运行    : {m['hoursSinceLastRun']:.1f} 小时")
    print(f"  自检结论      : {len(rep.info)} 通过 / {len(rep.warnings)} 警告 / {len(rep.errors)} 错误")
    if m.get("byCategory"):
        print("  分类分布      : " + ", ".join(f"{k}={v}" for k, v in list(m['byCategory'].items())[:8]))
    for line in rep.errors:
        print(f"  [ERR]  {line}")
    for line in rep.warnings[:6]:
        print(f"  [warn] {line}")
    print("──────────────────────────────────────────────────────────")
    print("")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="selfcheck.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true", help="compact console status")
    ap.add_argument("--summary", action="store_true", help="one-line summary for the log")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)

    rep = build_report()

    if args.json:
        print(json.dumps({"errors": rep.errors, "warnings": rep.warnings,
                          "info": rep.info, "metrics": rep.metrics},
                         ensure_ascii=False, indent=2))
    elif args.summary:
        ok = len(rep.info); w = len(rep.warnings); e = len(rep.errors)
        print(f"[selfcheck] items={rep.metrics.get('totalItems', 0)} "
              f"passed={ok} warnings={w} errors={e}")
        for line in rep.errors[:3]:
            print(f"[selfcheck][ERR] {line}")
    elif args.status:
        print_status(rep)
    else:
        print_report(rep)

    return 1 if rep.errors else (2 if rep.warnings else 0)


if __name__ == "__main__":
    sys.exit(main())
