#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prune_items.py — 存量知识卡片的解析自查与清理

要解决的问题
  采集器的 `minRelevance` 只有 12 分（满分 100），目的是「宁滥勿缺」。代价是库里
  积累了一批**对算法实习没有指导价值**的卡片：求职吐槽、泛化提问、内推码、
  与技术无关的社区热榜、只有标题没有内容的条目。它们不会出现在搜索的前排，
  但会拉低「今日速览」的信噪比，也让「每类都要有深度解析」变得不可达。

它做什么
  A. **自查**：给每张卡片打一个 `importance` 分（0–100），并归入三档：
       core    —— 方向内的论文/仓库/课程/手撕题/正式岗位信息（保留）
       useful  —— 有信息量的招聘、面经、行业动态（保留）
       noise   —— 无指导价值（建议下架）
     同时做**近似重复检测**：同一标题骨架出现多条时，只留最完整的那条。
  B. **优化**：默认只**报告**（dry-run）。要真正下架需显式 `--apply`。
     下架方式默认是 `--mode archive`：从 `items/index.json` 移出、写入
     `web/data/archive/pruned-YYYY-MM-DD.json` 并登记进 state 的 blocklist，
     这样**采集器不会再把它收回来**（否则下次采集立刻复活）。
     `--mode delete` 直接丢弃（不推荐，无法回溯）。

为什么默认 archive 而不是 delete
  下架决策是主观的，将来可能想找回来；但如果不写 blocklist，下一轮采集就会
  把同一条目重新收进来，下架等于白做。archive + blocklist 两者都满足。

用法
  python scripts/prune_items.py                      # 只报告
  python scripts/prune_items.py --show 30            # 报告并列出下架明细
  python scripts/prune_items.py --apply              # 执行（archive 模式）
  python scripts/prune_items.py --apply --mode delete
  python scripts/prune_items.py --min-keep-score 30  # 提高保留门槛
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"
CST = timezone(timedelta(hours=8))

INDEX = DATA / "items" / "index.json"
ITEMS_COPY = DATA / "items.json"
STATE = DATA / "state" / "collector-state.json"
ARCHIVE_DIR = DATA / "archive"

# ---------------------------------------------------------------------------
# Shared knowledge-quality judgement (scripts/knowledge_quality.py).
#
# This file used to own a second set of noise rules and its own importance model,
# which could disagree with plan_deep_read.py about the same card. The judgement
# now lives in one module; this file keeps only the ARCHIVE/BLOCKLIST machinery:
# deciding what to do with a card is a human action, deciding its value is not.
# ---------------------------------------------------------------------------
try:
    if str(Path(__file__).resolve().parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    import knowledge_quality as KQ
except Exception as _kq_err:                      # pragma: no cover
    KQ = None
    print(f"[error] knowledge_quality unavailable ({_kq_err}); cannot score cards",
          file=sys.stderr)

MATERIAL_CHANNELS = KQ.MATERIAL_CHANNELS if KQ else set()
MATERIAL_CATEGORIES = KQ.MATERIAL_CATEGORIES if KQ else set()
NOISE_RULES = KQ.NOISE_RULES if KQ else []


def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def load(path: Path, fallback):
    try:
        if path.exists():
            return json.loads(path.read_text("utf-8"))
    except Exception as e:
        print(f"[warn] {path.name}: {e}", file=sys.stderr)
    return fallback


def title_key(t: str) -> str:
    """Loose skeleton of a title, for near-duplicate detection."""
    s = re.sub(r"[\s\u3000]+", "", str(t or "").lower())
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "", s)
    return s


def noise_reason(item: dict) -> tuple[str, str] | None:
    if KQ is None:
        return None
    hits = KQ.noise_flags(item)
    return hits[0] if hits else None


def channel_quality_floor(item: dict) -> tuple[str, str] | None:
    """Channel-specific quality floors (moved into knowledge_quality.py so the
    collector, the planner and this pruner all apply the same ones)."""
    return KQ.channel_quality_floor(item) if KQ else None


def score_item(item: dict) -> tuple[int, str, list[str]]:
    """Return (importance 0-100, tier, reasons).

    Delegates to the shared judgement: relevance + knowledge materiality +
    direction fit + kind-specific value (面经 / 手撕题 / 八股 score as knowledge,
    not as chatter). The three tiers `core / useful / noise` are unchanged.
    """
    if KQ is None:
        return 0, "noise", ["knowledge_quality 不可用，无法评分"]
    return KQ.importance(item)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="prune_items.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually prune (default: report only)")
    ap.add_argument("--mode", choices=["archive", "delete"], default="archive")
    ap.add_argument("--min-keep-score", type=int, default=25,
                    help="cards below this importance are candidates for removal (default 25)")
    ap.add_argument("--keep-jobs", action="store_true", default=True,
                    help="never prune items whose category is job (default on)")
    ap.add_argument("--prune-jobs", dest="keep_jobs", action="store_false")
    ap.add_argument("--show", type=int, default=0, help="print this many removal candidates")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    index = load(INDEX, {}) or {}
    items = index.get("items") or []
    if not items:
        print("items/index.json is empty; nothing to do")
        return 0

    state = load(STATE, {}) or {}
    blocked_ids = set(state.get("blockedIds") or [])
    blocked_titles = set(state.get("blockedTitleKeys") or [])
    enrich = (load(DATA / "enrichment.json", {}) or {}).get("byId") or {}

    for it in items:
        it["enriched"] = it.get("id") in enrich

    scored = []
    for it in items:
        s, tier, why = score_item(it)
        scored.append({"item": it, "score": s, "tier": tier, "reasons": why,
                       "noise": noise_reason(it)})

    # --- near-duplicate detection -----------------------------------------
    by_key: dict[str, list] = {}
    for row in scored:
        by_key.setdefault(title_key(row["item"].get("title")), []).append(row)
    dup_drop = []
    for key, rows in by_key.items():
        if not key or len(rows) < 2:
            continue
        rows.sort(key=lambda r: (-r["score"], -(len(str(r["item"].get("summary") or "")))))
        for r in rows[1:]:
            dup_drop.append({**r, "dupOf": rows[0]["item"].get("id")})

    dup_ids = {r["item"].get("id") for r in dup_drop}

    # --- removal decision --------------------------------------------------
    remove, keep = [], []
    for row in scored:
        it = row["item"]
        iid = it.get("id")
        if iid in dup_ids:
            why = f"与 {next(d['dupOf'] for d in dup_drop if d['item'].get('id') == iid)} 标题近似重复"
            remove.append({**row, "removeWhy": why})
            continue
        if args.keep_jobs and it.get("category") == "job" and row["tier"] != "noise":
            keep.append(row)
            continue
        if row["tier"] == "noise" or row["score"] < args.min_keep_score:
            if row["noise"]:
                why = row["noise"][1]
            elif row["tier"] == "noise":
                # The tier came from a rule (off-direction career content, news,
                # no summary...). Report that rule instead of the misleading
                # "score below threshold" when the score is actually high.
                why = next((r for r in reversed(row["reasons"]) if r.startswith("判定：")),
                           "；".join(row["reasons"][:2]) or "判定为低价值")
            else:
                why = f"重要度 {row['score']} 低于保留门槛 {args.min_keep_score}"
            remove.append({**row, "removeWhy": why})
        else:
            keep.append(row)

    tiers = Counter(r["tier"] for r in scored)
    tier_map = {r["item"].get("id"): r["tier"] for r in scored}

    # --- per-category paper cap (redundancy) ------------------------------
    # Runs on the SURVIVORS above, so it only ever decides between cards that are
    # each worth keeping. Without it the library mirrors arXiv: measured before
    # this rule, 89 post-training and 72 agent papers had accumulated, none of
    # them literal duplicates but the tail of each adding nothing to interview prep.
    cap_drop = KQ.library_over_cap(
        [r["item"] for r in keep],
        tier_of=lambda it: tier_map.get(it.get("id"), "useful")) if KQ else {}
    if cap_drop:
        moved = [r for r in keep if r["item"].get("id") in cap_drop]
        keep = [r for r in keep if r["item"].get("id") not in cap_drop]
        for r in moved:
            remove.append({**r, "removeWhy": cap_drop[r["item"].get("id")],
                           "capRule": True})

    rules = Counter(r["noise"][0] for r in scored if r["noise"])
    by_cat_remove = Counter(r["item"].get("category") for r in remove)

    report = {
        "generatedAt": now_iso(),
        "policy": {"minKeepScore": args.min_keep_score, "mode": args.mode,
                   "keepJobs": bool(args.keep_jobs),
                   "note": "archive 模式会写入 blocklist，避免下一轮采集把下架条目收回来"},
        "totals": {"inLibrary": len(items), "keep": len(keep), "remove": len(remove),
                   "duplicates": len(dup_drop), "alreadyBlocked": len(blocked_ids)},
        "tiers": dict(tiers),
        "noiseByRule": dict(rules),
        "cappedByCategory": dict(Counter(r["item"].get("category")
                                         for r in remove if r.get("capRule"))),
        "removalsByCategory": dict(by_cat_remove),
        "removalsByRule": dict(Counter(r["noise"][0] for r in remove if r["noise"])),
        "samples": [{"id": r["item"].get("id"), "title": str(r["item"].get("title"))[:90],
                     "category": r["item"].get("category"), "channel": r["item"].get("channel"),
                     "score": r["score"], "tier": r["tier"], "why": r["removeWhy"]}
                    for r in remove[:40]],
        "keepSamples": [{"title": str(r["item"].get("title"))[:78], "score": r["score"],
                         "tier": r["tier"], "category": r["item"].get("category")}
                        for r in sorted(keep, key=lambda r: -r["score"])[:12]],
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0

    print("")
    print("=" * 78)
    print("知识卡片自查与清理" + ("（--apply：将执行）" if args.apply else "（仅报告）"))
    print("=" * 78)
    print(f"  库内卡片        : {len(items)}")
    print(f"  分档            : core={tiers.get('core', 0)}  useful={tiers.get('useful', 0)}  noise={tiers.get('noise', 0)}")
    print(f"  建议保留 / 下架 : {len(keep)} / {len(remove)}"
          f"（其中近似重复 {len(dup_drop)} 条）")
    cap_n = sum(1 for r in remove if r.get("capRule"))
    if cap_n:
        print(f"  其中论文饱和上限: {cap_n} 条  "
              + ", ".join(f"{k}={v}" for k, v in
                          Counter(r['item'].get('category') for r in remove
                                  if r.get('capRule')).most_common()))
    if rules:
        print("  命中噪音规则    : " + ", ".join(f"{k}={v}" for k, v in rules.most_common()))
    if by_cat_remove:
        print("  下架按分类      : " + ", ".join(f"{k}={v}" for k, v in by_cat_remove.most_common(8)))
    print("")
    print("  —— 保留的样本（重要度最高的 12 条）——")
    for s in report["keepSamples"]:
        print(f"    {s['score']:>3} [{s['tier']:<6}] {s['category']:<13} {s['title']}")
    if args.show:
        print("")
        print(f"  —— 下架候选（前 {args.show} 条）——")
        for r in remove[:args.show]:
            print(f"    {r['score']:>3} [{r['tier']:<5}] {str(r['item'].get('category')):<12} "
                  f"{str(r['item'].get('title'))[:56]}")
            print(f"         理由：{r['removeWhy']}")
    print("=" * 78)

    if not args.apply:
        print("")
        print("这是**只报告**模式，没有改动任何数据。要执行：")
        print("  python scripts/prune_items.py --apply")
        print("")
        return 0

    # --- apply -------------------------------------------------------------
    remove_ids = {r["item"].get("id") for r in remove}
    kept_items = [it for it in items if it.get("id") not in remove_ids]

    if args.mode == "archive":
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        day = datetime.now(CST).strftime("%Y-%m-%d")
        payload = {"archivedAt": now_iso(), "count": len(remove),
                   "policy": report["policy"],
                   "items": [r["item"] for r in remove]}
        with io.open(ARCHIVE_DIR / f"pruned-{day}.json", "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        print(f"  archived {len(remove)} items -> data/archive/pruned-{day}.json")

    # Write the trimmed index (and the local copy the app also reads).
    for path in (INDEX, ITEMS_COPY):
        doc = dict(load(path, {}) or {})
        doc["items"] = kept_items
        doc["count"] = len(kept_items)
        doc["prunedAt"] = now_iso()
        doc["prunedCount"] = len(remove)
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"  index rewritten: {len(items)} -> {len(kept_items)} items")

    # manifest.totalItems must follow the index, or selfcheck reports a mismatch
    # ("manifest.totalItems=760 but index has 554 items") and the UI header lies.
    man_path = DATA / "manifest.json"
    man = dict(load(man_path, {}) or {})
    if man:
        man["totalItems"] = len(kept_items)
        man["prunedAt"] = now_iso()
        man["prunedCount"] = len(remove)
        stats = dict(man.get("stats") or {})
        by_cat: dict = {}
        for it in kept_items:
            c = it.get("category") or "trend"
            by_cat[c] = by_cat.get(c, 0) + 1
        stats["byCategory"] = by_cat
        man["stats"] = stats
        # The summary headline embeds the corpus size, so it goes stale the moment
        # items are pruned ("累计 760 条" while the index holds 554).
        summ = dict(man.get("summary") or {})
        if summ:
            counts = dict(summ.get("counts") or {})
            counts["total"] = len(kept_items)
            summ["counts"] = counts
            headline = str(summ.get("headline") or "")
            if headline:
                headline = re.sub(r"累计\s*\d+\s*条", f"累计 {len(kept_items)} 条", headline)
                summ["headline"] = headline
            man["summary"] = summ
        with io.open(man_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(man, fh, ensure_ascii=False, separators=(",", ":"))
        print(f"  manifest.totalItems -> {len(kept_items)}")

    # The day's digest still lists items we just removed, which selfcheck reports
    # as "orphans" and the 每日更新流 would render as links to nothing. Prune the
    # digest too, and recompute its summary so the counts stay truthful.
    kept_ids = {it.get("id") for it in kept_items}
    for rel in ("digest/today.json",):
        dpath = DATA / rel
        dg = load(dpath, None)
        if not isinstance(dg, dict):
            continue
        before = len(dg.get("items") or [])
        dg["items"] = [i for i in (dg.get("items") or []) if i.get("id") in kept_ids]
        dg["updated"] = [i for i in (dg.get("updated") or []) if i.get("id") in kept_ids]
        if dg.get("summary"):
            counts = dict(dg["summary"].get("counts") or {})
            counts["fresh"] = len(dg["items"])
            counts["total"] = len(kept_items)
            dg["summary"]["counts"] = counts
            dg["summary"]["topItemIds"] = [i for i in (dg["summary"].get("topItemIds") or [])
                                           if i in kept_ids]
        dg["prunedAt"] = now_iso()
        with io.open(dpath, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(dg, fh, ensure_ascii=False, separators=(",", ":"))
        day = dg.get("date")
        if day:
            dated = DATA / "digest" / f"{day}.json"
            with io.open(dated, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(dg, fh, ensure_ascii=False, separators=(",", ":"))
        if before != len(dg["items"]):
            print(f"  digest fresh items: {before} -> {len(dg['items'])} (orphans removed)")

    # Blocklist so the next collection does not re-import what we just removed.
    # Without this the prune is undone on the next 14:00 run.
    state["blockedIds"] = sorted(blocked_ids | remove_ids)
    keys = {title_key(r["item"].get("title")) for r in remove}
    state["blockedTitleKeys"] = sorted(blocked_titles | {k for k in keys if k})
    state["lastPruneAt"] = now_iso()
    with io.open(STATE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(state, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"  blocklist updated: {len(state['blockedIds'])} ids, "
          f"{len(state['blockedTitleKeys'])} title keys")
    print("")
    print("  下一步：python scripts/selfcheck.py  （确认数据层仍然自洽）")
    print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
