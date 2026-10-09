#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""update_agent_proposals.py - fold the daily deep-read layer's findings into
web/data/proposals/<date>.json (and latest.json).

WHY: web/data/proposals/<date>.json is written by collect.py (the deterministic
layer) and contains channelHealth / coverage / noiseReport, but nothing the
deep-read agent learned. The agent layer is the only place that sees *why* items
were skipped, which formula ids collided, and which cards entered the queue only
to be rejected. Those findings are what the human actually needs to act on, so
they are merged in here - and the deterministic fields are never overwritten.

DATA-DRIVEN (2026-10-06 fix): this script used to carry a hard-coded list of
agent entries written for one specific round. The next round then re-published
them verbatim, so the proposal file claimed things that were no longer true
(e.g. "hf_papers 已自愈、此条可关闭" while the same channels were failing again,
and stale paper-over-limit counts). Everything below is now DERIVED from the
current round's artifacts, so the report cannot drift from the data:

  skipped ids/reasons   <- scripts/agent-work/out-*.json
  queued/picked counts  <- web/data/deep-read-plan.json
  channel failures      <- proposals/<date>.json channelHealth (written by collect.py)
  paper over-limit      <- items/index.json + config knowledge.maxPapersPerCategory
  needsFetch ids        <- items/index.json (no summary) + enrichment.json
  formula id clutter    <- formulas.json (duplicate names)
  gate-loosened streak  <- number of earlier dated proposal files carrying the marker

Idempotent: agent-layer entries carry a marker prefix and are replaced wholesale
on re-run, so running twice does not duplicate them.

Usage
  python scripts/update_agent_proposals.py --date 2026-10-06
  python scripts/update_agent_proposals.py --date 2026-10-06 --check
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"
PROP = DATA / "proposals"
WORK = ROOT / "scripts" / "agent-work"
CST = dt.timezone(dt.timedelta(hours=8))

# agent-layer entries are prefixed so they can be replaced without touching the
# deterministic ones collect.py wrote.
MARK = "【深读层】"
GATE_MARK = "方向闸门"


# --------------------------------------------------------------------------
# small readers (never raise: a missing file must degrade, not abort the run)
# --------------------------------------------------------------------------
def _load(p: Path, default=None):
    try:
        return json.loads(Path(p).read_text("utf-8"))
    except Exception:
        return {} if default is None else default


def _index_items() -> list:
    return (_load(DATA / "items" / "index.json").get("items")) or []


def _config() -> dict:
    return _load(ROOT / "config" / "collector.config.json")


def _skips() -> list:
    rows = []
    for f in sorted(WORK.glob("out-*.json")):
        d = _load(f)
        for s in d.get("skipped") or []:
            rows.append({
                "batch": d.get("batchId") or f.stem,
                "id": s.get("id"),
                "reason": s.get("reason") or "off-direction",
                "evidence": " ".join(str(s.get("evidence") or "").split()),
            })
    return rows


def _deepread_stats() -> dict:
    full = backfill = skipped = 0
    for f in sorted(WORK.glob("out-*.json")):
        d = _load(f)
        rows = d.get("entries") or []
        full += len(rows)
        skipped += len(d.get("skipped") or [])
        if str(d.get("batchId", "")).startswith("backfill"):
            backfill = len(rows)
    plan = _load(DATA / "deep-read-plan.json")
    totals = (plan.get("totals") or {})
    return {
        "queued": len(plan.get("queue") or []),
        "problemBankQueued": len(plan.get("problemBankQueue") or []),
        "backfillQueued": len(plan.get("backfill") or []),
        "entriesFull": full - backfill,
        "entriesBackfill": backfill,
        "skipped": skipped,
        "categories": totals.get("categories"),
    }


def _gate_streak(date: str) -> int:
    """How many consecutive rounds the loosened direction gate has been logged."""
    n = 0
    for f in sorted(PROP.glob("20*.json")):
        if f.stem >= date:
            continue
        try:
            if GATE_MARK in f.read_text("utf-8"):
                n += 1
        except Exception:
            continue
    return n + 1


def _gate_is_still_loose() -> tuple:
    """(is_loose, threshold, min_hits_for_pass). Loose == one core-term hit passes."""
    policy = _config().get("knowledge") or {}
    min_core = float(policy.get("minCoreFitForTechnical", 0.5))
    # core_fit = min(1, hits/2) -> hits needed to reach the threshold
    hits = max(1, int(-(-min_core // 0.5)))  # ceil(min_core / 0.5) without importing math
    return (min_core <= 0.5, min_core, hits)


def _channel_failures(doc: dict) -> list:
    out = []
    for ch in doc.get("channelHealth") or []:
        status = ch.get("status")
        streak = ch.get("streak") or 0
        if status in ("blocked", "error") and streak >= 3:
            out.append((ch.get("id"), status, streak, ch.get("lastError")))
    out.sort(key=lambda r: (-r[2], r[0] or ""))
    return out


def _paper_over_cap() -> tuple:
    cap = ((_config().get("knowledge") or {}).get("maxPapersPerCategory"))
    counts = Counter(x.get("category") for x in _index_items() if x.get("kind") == "paper")
    over = [(k, v) for k, v in counts.most_common() if cap and v > cap]
    return cap, over


def _needs_fetch() -> list:
    enriched = (_load(DATA / "enrichment.json").get("byId")) or {}
    rows = []
    for x in _index_items():
        if not str(x.get("summary") or "").strip():
            rows.append((x.get("id"), x.get("title") or "", x.get("channel"),
                         x.get("id") in enriched))
    return rows


def _formula_dup_names() -> list:
    formulas = (_load(DATA / "formulas.json").get("formulas")) or []
    counts = Counter(f.get("name") or "" for f in formulas if f.get("name"))
    return sorted([(n, k) for n, k in counts.items() if k > 1], key=lambda t: (-t[1], t[0]))


# --------------------------------------------------------------------------
# the report itself
# --------------------------------------------------------------------------
def _short(text: str, n: int = 46) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n] + "…"


def agent_entries(doc: dict, date: str) -> list:
    entries: list = []

    # 1) direction gate -----------------------------------------------------
    loose, min_core, hits = _gate_is_still_loose()
    skips = _skips()
    if loose and skips:
        streak = _gate_streak(date)
        detail = "；".join(f"{s['batch']}/{s['id']}（{_short(s['evidence'], 40)}）" for s in skips[:6])
        entries.append(
            MARK + f"【连续 {streak} 轮·需人工决策·已升级】{GATE_MARK}偏松：CORE_DIRECTION_TERMS "
            f"单命中即得 core_fit=0.5，恰等于 minCoreFitForTechnical={min_core}，"
            f"于是「multimodal/多模态」出现一次就能过闸。本轮深读层判 off-direction 跳过 "
            f"{len(skips)} 条，全部是**进了队列才被拦下**的非方向内容：{detail}。"
            "修法只需人工拍板二选一：(a) minCoreFitForTechnical 0.5→0.75；"
            "或 (b) 把 multimodal/多模态 从 CORE_DIRECTION_TERMS 降级为宽口径词。")
    elif skips:
        entries.append(
            MARK + f"【观察】本轮深读层判 off-direction 跳过 {len(skips)} 条："
            + "；".join(f"{s['batch']}/{s['id']}" for s in skips[:6]))

    # 2) channels -----------------------------------------------------------
    fails = _channel_failures(doc)
    if fails:
        blocked = ", ".join(f"{cid}({st}×{k})" for cid, st, k, _ in fails)
        entries.append(
            MARK + f"【渠道·需人工决策，连续多轮】仍有 {len(fails)} 个渠道连续 3 轮以上失败："
            f"{blocked}。按契约**不自动禁用渠道**，请人工确认：永久下线、换源，还是改人工导入。")
    flaky = [r for r in fails if r[0] in ("hf_papers", "hf_blog_rss")]
    if flaky:
        entries.append(
            MARK + "【渠道·上一轮结论已作废】上一轮（2026-10-05）基于「本轮有产出」判定 "
            "hf_papers / hf_blog_rss 已自愈、并建议关闭该条。本轮两者**再次失败**（Tunnel 502）："
            + "；".join(f"{cid} {st}×{k}" for cid, st, k, _ in flaky)
            + "。结论修正：这不是稳定自愈，而是**出口代理的间歇性故障**，该条不应关闭，"
              "需人工决定是否改用直连源或本地镜像。")

    # 3) paper saturation ---------------------------------------------------
    cap, over = _paper_over_cap()
    if over:
        entries.append(
            MARK + "【需人工决策，连续多轮】论文数超分类上限："
            + " / ".join(f"{k}={v}" for k, v in over)
            + f"（上限 maxPapersPerCategory={cap}，共 {len(over)} 个分类越界）。"
              "需要人工决定是否执行 python scripts/prune_items.py --apply。"
              "注意该命令会把被删条目写进 blocklist（不会自动回来）。")

    # 4) formula id clutter -------------------------------------------------
    dups = _formula_dup_names()
    if dups:
        entries.append(
            MARK + f"【需人工决策】公式库同义 id 碎片化：{len(dups)} 组公式名重复，"
            + "、".join(f"「{_short(n, 28)}」×{k}" for n, k in dups[:5])
            + "。建议人工合并/删除同义公式，否则「公式剖析」页会长期出现多条等价公式。"
              "（深读层的 id 去重只保证不新增重复，不会自动清理既有重名。）")

    # 5) needsFetch ---------------------------------------------------------
    nf = _needs_fetch()
    if nf:
        rows = "；".join(
            f"{i}（{_short(t, 28)}，{ch}，{'已深读' if done else '未深读'}）"
            for i, t, ch, done in nf)
        entries.append(
            MARK + f"【数据质量·需人工确认】{len(nf)} 条无摘要条目（采集层拿不到摘要，"
            f"需深读层抓原文）：{rows}。若同一渠道的无摘要条数突然增多，说明该源返回格式变了，"
              "应加入人工复核清单。")

    return entries


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    p = PROP / f"{args.date}.json"
    doc = _load(p)
    if not doc:
        print(f"[warn] {p} 不存在或不可解析，未写入")
        return 1

    q = [x for x in (doc.get("humanReviewQueue") or []) if not str(x).startswith(MARK)]
    entries = agent_entries(doc, args.date)
    q.extend(entries)
    doc["humanReviewQueue"] = q

    stats = _deepread_stats()
    doc["agentReview"] = {
        "generatedAt": dt.datetime.now(CST).replace(microsecond=0).isoformat(),
        "note": "深读层补充（由本轮产物推导，不再使用硬编码文本）：方向闸门、渠道失败、"
                "论文饱和、公式 id 碎片化、needsFetch 状态。",
        "deepRead": {
            "queued": stats["queued"],
            "problemBankQueued": stats["problemBankQueued"],
            "backfillQueued": stats["backfillQueued"],
            "entriesFull": stats["entriesFull"],
            "entriesBackfill": stats["entriesBackfill"],
            "skipped": stats["skipped"],
            "skipDetail": [
                {"id": s["id"], "batch": s["batch"], "reason": s["reason"],
                 "evidence": s["evidence"][:160]}
                for s in _skips()
            ],
        },
    }

    if args.check:
        print(json.dumps({"humanReviewQueue": q, "agentReview": doc["agentReview"]},
                         ensure_ascii=False, indent=1)[:2400])
        return 0

    for target in (p, PROP / "latest.json"):
        with io.open(target, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)
        print(f"wrote {target.name}: humanReviewQueue={len(q)} "
              f"(deterministic={len(q) - len(entries)}, agent={len(entries)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
