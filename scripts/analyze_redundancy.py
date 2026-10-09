#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_redundancy.py — 知识卡片的去冗余体检 + 可执行工单

为什么需要它（而不是只靠 dedupe_deep.py）
  dedupe_deep.py 解决"**同一件事的同一条内容**"被多处收录：规范化标题骨架、
  canonicalUrl（去 arXiv 版本号）、标题 3-gram Jaccard >= 0.86。对 720 条实测：
  重复组 0 —— 采集器的四层去重 + 第二轮深去重已经把同一条内容清干净了。

  但用户说的"后期冗余"是另外几层，dedupe 类工具天生看不见：
    L1 同一实体反复收录   —— 同一个项目/模型/机构反复出现在不同条目里
    L2 话题饱和          —— 某个话题把某个分类的注意力占满
    L3 低信息量占位       —— 零命中未分类、摘要过短、纯工具仓库
    L4 主题同质          —— 分类内两两相似度偏高（选材不够发散）
  这些不是"重复条目"而是"注意力摊薄"，处理方式是**配额与关键词**，不是删条目。
  所以本工具输出的是**分区间的工单**（补词 / 调参 / 回填 / 发散），可复核可执行。

关键设计：分词必须去掉套话
  上一版把 'explicit' / 'pipelines' / 'collection' 当成"实体"，结论全是噪声。
  本版用一张针对本语料实测产生的套话表，并要求"实体"token 必须是**罕见词**
  （在全库出现的条目数在 [3, 1%] 之间），才可能是一个真实体。

用法:
  python scripts/analyze_redundancy.py                  # 报告
  python scripts/analyze_redundancy.py --top 20
  python scripts/analyze_redundancy.py --json out.json  # 机器可读（供 selfcheck 用）
  python scripts/analyze_redundancy.py --gate           # 只做阈值判定，退出码即结论
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"
CST = timezone(timedelta(hours=8))

# Domain boilerplate: appears in a large fraction of titles/summaries and therefore
# carries no discriminating information. The first version of this script treated
# these as "entities" and produced a meaningless report ("x7 knowledge", "x7 built").
# This list was built by running the analysis and inspecting what it wrongly flagged.
BOILER = set("""
the of for and with via using from into toward towards beyond when how what why
new novel based learning model models method methods approach paper survey review
analysis study system systems framework data training inference language large
scaling efficient improved improving understanding rethinking unifying unified
show hn launch introducing a an on in to at by is are be it its this that these
open source github repository repo project toolkit library release
knowledge semantic workflows built intelligence discovery across physical
foundation agent agents multimodal video world generation token tokens
大模型 模型 方法 论文 技术 综述 研究 分析 一种 面向 基于 实现 提升 优化 学习 系统
""".split())

# Entity-ish proper nouns are the useful signal. A bare token like "agent" is a
# category, not an entity, so repeated-entity detection requires either a capitalised
# ASCII token or a CJK 2+ gram - both of which are how model/company names appear.
CAP_RE = re.compile(r"\b([A-Z][A-Za-z0-9\-]{2,})\b")


def load(p: Path, fb):
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return fb


def topic_tokens(text: str) -> set[str]:
    """Discriminating tokens only: ASCII words >=4 chars that are not boilerplate,
    plus CJK bigrams. Kept deliberately strict - a false "entity" is worse than a
    missed one, because it turns the report into noise."""
    t = (text or "").lower()
    out = {w for w in re.findall(r"[a-z][a-z0-9\-]{3,}", t) if w not in BOILER}
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", t):
        for i in range(len(run) - 1):
            g = run[i:i + 2]
            if g not in BOILER:
                out.add(g)
    return out


def entity_tokens(text: str) -> set[str]:
    """Tokens that identify "the same thing": CJK bigrams plus ASCII names.

    Empirical calibration (this matters - two earlier versions were useless):
      · Generic topic words gave "x7 knowledge / x7 built": pure noise. Fixed by the
        BOILER list.
      · ANY capitalised word gave "x14 Latent / x13 Planning / x13 Visual" - English
        titles are Title Case, so every word looks like a proper noun. Fixed by
        excluding ASCII words that also appear lowercase in the corpus (see
        filter_by_lowercase) and by preferring CJK bigrams, which are far more
        reliable in this corpus: they produced the genuinely actionable findings
        (面试 x14, 秋招 x12, 微信 x12).
    """
    out: set[str] = set()
    for run in re.findall(r"[\u4e00-\u9fff]{2,}", text or ""):
        for i in range(len(run) - 1):
            g = run[i:i + 2]
            if g not in BOILER:
                out.add(g)
    for m in CAP_RE.finditer(text or ""):
        w = m.group(1)
        if w.lower() not in BOILER and len(w) >= 4:
            out.add(w)
    return out


def filter_by_lowercase(items: list[dict], ents: dict[str, set[str]]) -> set[str]:
    """Drop ASCII candidates that also occur in lowercase somewhere in the corpus.

    A real proper noun (VLM, GRPO, DeepSeek) is almost always written the same way,
    whereas an ordinary word at the start of a Title-Case headline also appears
    lowercase in summaries. This is a cheap, data-driven proper-noun test.
    """
    lower_blob = " ".join(
        (str(it.get("title") or "") + " " + str(it.get("summary") or "")).lower()
        for it in items)
    keep = set()
    for w in {w for s in ents.values() for w in s if w.isascii()}:
        if w.lower() not in lower_blob:
            keep.add(w)
    return keep


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    i = len(a & b)
    return i / (len(a) + len(b) - i)


def build_report(items: list[dict], enrich: dict) -> dict:
    total = len(items)
    toks = {it["id"]: topic_tokens(it.get("title") or "") for it in items}
    rep: dict = {"generatedAt": datetime.now(CST).isoformat(timespec="seconds"),
                 "corpus": total, "enriched": len(enrich)}

    # ---- L0 hard duplicates ------------------------------------------------
    urls = Counter()
    for it in items:
        u = (it.get("canonicalUrl") or it.get("url") or "").rstrip("/").lower()
        if u:
            urls[u] += 1
    rep["l0"] = {
        "duplicateIds": total - len({i.get("id") for i in items}),
        "duplicateUrls": sum(1 for n in urls.values() if n > 1),
    }

    # ---- L1 repeated entities ---------------------------------------------
    # Use proper-noun tokens, not generic topic words: "the same thing reported
    # repeatedly" shows up as a repeated NAME (a model, a company, a project).
    ents = {it["id"]: entity_tokens(it.get("title") or "") for it in items}
    ascii_ok = filter_by_lowercase(items, ents)
    for iid in ents:
        ents[iid] = {w for w in ents[iid] if (not w.isascii()) or w in ascii_ok}
    df = Counter()
    for it in items:
        for w in ents[it["id"]]:
            df[w] += 1
    lo, hi = 3, max(4, int(total * 0.02))
    rare = {w for w, n in df.items() if lo <= n <= hi}
    groups: dict[str, list] = defaultdict(list)
    for it in items:
        for w in (ents[it["id"]] & rare):
            groups[w].append(it)
    repeated = {w: v for w, v in groups.items() if len(v) >= 3}
    repeated = dict(sorted(repeated.items(), key=lambda kv: -len(kv[1])))
    rep["l1_repeatedEntities"] = [
        {"token": w, "items": len(v),
         "categories": dict(Counter(i.get("category") for i in v).most_common(3)),
         "sampleTitles": [str(i.get("title"))[:80] for i in v[:3]]}
        for w, v in list(repeated.items())[:40]
    ]

    # ---- L2 title-pattern repetition ---------------------------------------
    # This replaced a former "topic saturation" metric (most frequent token divided by
    # category size). That metric had to be abandoned: Chinese has no word boundaries,
    # so bigram tokenisation slices 算法工程师 into fragments like 程师 and 法工, and
    # every whitelist attempt merely produced the NEXT fragment. A metric whose output
    # is an artefact of the tokenizer is worse than having no metric at all.
    #
    # Instead: count how many titles in a category share the same normalised PREFIX.
    # "N titles that all open with the same words" is unambiguous evidence of a
    # repeated naming pattern, and it needs no segmentation.
    def prefix_key(title: str, words: int = 2) -> str:
        t = re.sub(r"[^\w\u4e00-\u9fff ]+", " ", str(title or "").lower())
        parts = [x for x in t.split() if x and x not in BOILER]
        if not parts:
            return ""
        out = []
        for x in parts[:words]:
            out.append(x if x.isascii() else x[:2])
        return " ".join(out)

    sat = []
    for cat in sorted({i.get("category") for i in items}):
        rows = [i for i in items if i.get("category") == cat]
        if len(rows) < 20:
            continue
        c = Counter(prefix_key(i.get("title")) for i in rows)
        c.pop("", None)
        if not c:
            continue
        w, k = c.most_common(1)[0]
        sat.append({"category": cat, "items": len(rows), "topToken": w,
                    "count": k, "share": round(k / len(rows), 4)})
    sat.sort(key=lambda r: -r["share"])
    rep["l2_saturation"] = sat
    rep["l2_metric"] = "title-prefix repetition (segmentation-free)"

    # ---- L3 low-information -------------------------------------------------
    short = [i for i in items if len(str(i.get("summary") or "").strip()) < 60]
    nosum = [i for i in items if not str(i.get("summary") or "").strip()]
    uncl = [i for i in items if i.get("category") == "unclassified"]
    low = [i for i in items if float(i.get("relevanceScore") or 0) < 45]
    # Unclassified items are the strongest redundancy signal: they matched NO keyword,
    # so they cannot be serving any of the tracked directions.
    rep["l3_lowInformation"] = {
        "shortSummary": len(short), "noSummary": len(nosum),
        "unclassified": len(uncl), "belowGate": len(low),
        "unclassifiedShare": round(len(uncl) / total, 4),
        "unclassifiedSample": [
            {"id": i.get("id"), "score": i.get("relevanceScore"),
             "title": str(i.get("title"))[:80]} for i in uncl[:15]],
    }

    # ---- L4 within-category homogeneity ------------------------------------
    random.seed(7)
    homo = []
    for cat in sorted({i.get("category") for i in items}):
        rows = [i for i in items if i.get("category") == cat]
        if len(rows) < 25:
            continue
        sample = random.sample(rows, min(110, len(rows)))
        vals = []
        near = 0
        pairs = 0
        for a in range(len(sample)):
            for b in range(a + 1, len(sample)):
                s = jaccard(toks[sample[a]["id"]], toks[sample[b]["id"]])
                vals.append(s)
                pairs += 1
                if s >= 0.5:
                    near += 1
        homo.append({"category": cat, "items": len(rows),
                     "avgSim": round(sum(vals) / max(1, len(vals)), 4),
                     "nearPairShare": round(near / max(1, pairs), 4)})
    homo.sort(key=lambda r: -r["nearPairShare"])
    rep["l4_homogeneity"] = homo

    # ---- worklist ----------------------------------------------------------
    acts = []
    if rep["l0"]["duplicateUrls"]:
        acts.append({"kind": "去重", "severity": "high",
                     "text": f"{rep['l0']['duplicateUrls']} 个 URL 被多条共用 -> dedupe_deep.py --apply"})
    if len(uncl) / max(1, total) >= 0.05:
        acts.append({"kind": "补词", "severity": "high",
                     "text": (f"未分类 {len(uncl)} 条 = {len(uncl)/total:.1%}；其中 "
                              f"{sum(1 for i in uncl if float(i.get('relevanceScore') or 0) < 45)} 条同时低于相关度门槛。"
                              "这些是纯粹的注意力占用：补关键词或提高门槛后 --rescore")})
    for s in sat:
        if s["share"] >= 0.40 and s["topToken"] not in ("agent", "llm"):
            acts.append({"kind": "调参", "severity": "medium",
                         "category": s["category"],
                         "text": f"{s['category']} 内 '{s['topToken']}' 占 {s['share']:.0%} -> 话题过饱和"})
    if len(short) / max(1, total) >= 0.05:
        acts.append({"kind": "回填", "severity": "medium",
                     "text": f"摘要 <60 字 {len(short)} 条 -> 开摘要回填或人工补"})
    for h in homo:
        if h["nearPairShare"] >= 0.10:
            acts.append({"kind": "发散", "severity": "medium", "category": h["category"],
                         "text": f"{h['category']} 相似配对 {h['nearPairShare']:.0%} -> 选材过于集中"})
    for e in rep["l1_repeatedEntities"][:6]:
        if e["items"] >= 5:
            acts.append({"kind": "观察", "severity": "low",
                         "text": f"'{e['token']}' 出现在 {e['items']} 条里 -> 确认是否同一事物的多个版本"})
    if not acts:
        acts.append({"kind": "保持", "severity": "none", "text": "各层指标均在阈值内"})
    rep["worklist"] = acts
    return rep


def print_report(rep: dict, top: int) -> None:
    total = rep["corpus"]
    print("")
    print("=" * 78)
    print(f"知识卡片去冗余体检   语料 {total} 条   已深读 {rep['enriched']} 条")
    print("=" * 78)
    l0 = rep["l0"]
    print("")
    print("[L0] 硬重复")
    print(f"     重复 id : {l0['duplicateIds']}    重复 URL : {l0['duplicateUrls']}")

    print("")
    print("[L1] 同一实体反复收录（罕见词出现在 >=3 条标题里）")
    if not rep["l1_repeatedEntities"]:
        print("     无")
    for e in rep["l1_repeatedEntities"][:top]:
        print(f"     {e['token']:<26} x{e['items']:<3} {e['categories']}")
        print(f"        e.g. {e['sampleTitles'][0][:70]}")

    print("")
    print("[L2] 话题饱和（分类内最高频实词占比）")
    for s in rep["l2_saturation"][:top]:
        flag = "偏高" if s["share"] >= 0.40 else ("关注" if s["share"] >= 0.25 else "ok")
        print(f"     {s['category']:<13} {s['items']:>4} 条  '{s['topToken']}' "
              f"{s['count']:>3} 条 = {s['share']:5.1%}  {flag}")

    l3 = rep["l3_lowInformation"]
    print("")
    print("[L3] 低信息量 / 未分类")
    print(f"     未分类           : {l3['unclassified']:>4}  ({l3['unclassifiedShare']:.1%})")
    print(f"     相关度 <45       : {l3['belowGate']:>4}")
    print(f"     摘要 <60 字      : {l3['shortSummary']:>4}")
    print(f"     完全无摘要       : {l3['noSummary']:>4}")
    if l3["unclassifiedSample"]:
        print("     未分类样例：")
        for s in l3["unclassifiedSample"][:6]:
            print(f"       {s['score']:>5} {s['title'][:66]}")

    print("")
    print("[L4] 分类内主题同质化（抽样两两相似度）")
    for h in rep["l4_homogeneity"][:top]:
        flag = "同质偏高" if h["nearPairShare"] >= 0.10 else ("关注" if h["nearPairShare"] >= 0.05 else "ok")
        print(f"     {h['category']:<13} {h['items']:>4} 条  平均相似 {h['avgSim']:.3f}  "
              f"相似>=0.5 {h['nearPairShare']:5.1%}  {flag}")

    print("")
    print("=" * 78)
    print("工单")
    print("=" * 78)
    for a in rep["worklist"]:
        print(f"  [{a['severity']:<6}][{a['kind']}] {a['text']}")
    print("")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--json", type=str, default="")
    ap.add_argument("--gate", action="store_true",
                    help="只做阈值判定：有 high 级工单则退出码 2，medium 级 1，否则 0")
    args = ap.parse_args()

    items = (load(DATA / "items" / "index.json", {}) or {}).get("items") or []
    if not items:
        print("no items")
        return 1
    enrich = (load(DATA / "enrichment.json", {}) or {}).get("byId") or {}
    rep = build_report(items, enrich)

    if args.json:
        Path(args.json).write_text(json.dumps(rep, ensure_ascii=False, indent=2), "utf-8")

    if not args.gate:
        print_report(rep, args.top)
        if args.json:
            print(f"报告已写入 {args.json}")

    sev = {a["severity"] for a in rep["worklist"]}
    if args.gate:
        if "high" in sev:
            return 2
        if "medium" in sev:
            return 1
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
