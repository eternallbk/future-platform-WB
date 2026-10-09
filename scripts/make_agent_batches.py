#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_agent_batches.py — 把 deep-read-plan.json 的 queue/backfill 切成子代理可处理的批次。

输出到 scripts/agent-work/in-<batchId>.json，结构见 scripts/agent-work/INSTRUCTIONS.md。
纯确定性：不改动 web/data/。
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "web" / "data" / "deep-read-plan.json"
INDEX = ROOT / "web" / "data" / "items" / "index.json"
ENRICH = ROOT / "web" / "data" / "enrichment.json"
WORK = ROOT / "scripts" / "agent-work"


def load(p: Path):
    return json.loads(p.read_text("utf-8"))


def dump(p: Path, doc) -> None:
    with io.open(p, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=5)
    ap.add_argument("--only", choices=["all", "problems"], default="all",
                    help="problems = 只出题库批次（用于「题库专项轮次」：这一轮只把"
                         "高频手撕题解析补齐，不动常规深读队列）。")
    args = ap.parse_args()

    plan = load(PLAN)
    idx = {r["id"]: r for r in load(INDEX)["items"]}
    enr = (load(ENRICH).get("byId") or {}) if ENRICH.exists() else {}

    WORK.mkdir(parents=True, exist_ok=True)
    for old in WORK.glob("in-*.json"):
        old.unlink()
    # out-*.json 是一次性产物：它们对应的 in-* 已经被上面的 unlink 清掉，
    # 留着会让 apply_agent_out.py 拿旧批次去比对新输入，报一堆「输入外的 id」。
    for old in WORK.glob("out-*.json"):
        old.unlink()

    def base(item: dict) -> dict:
        src = idx.get(item["id"], {})
        summary = src.get("summary") or ""
        return {
            "id": item["id"],
            "title": item.get("title") or src.get("title"),
            "category": item.get("category") or src.get("category"),
            "channel": item.get("channel") or src.get("channel"),
            "url": item.get("url") or src.get("url"),
            "sources": src.get("sources") or [],
            "tags": src.get("tags") or [],
            "kind": item.get("kind") or src.get("kind"),
            "summary": summary,
            # 没有摘要 = 采集层只拿到了标题和链接（HN 这类源就是这样）。深读层必须
            # 自己去把原文读下来再解析，而不是因为「没有素材」而跳过。
            "needsFetch": not bool(str(summary).strip()),
        }

    written = []

    queue = plan.get("queue") or []
    bf = plan.get("backfill") or []
    if args.only == "all":
        for i in range(0, len(queue), args.size):
            chunk = queue[i : i + args.size]
            bid = "queue-%02d" % (i // args.size + 1)
            dump(
                WORK / f"in-{bid}.json",
                {"batchId": bid, "mode": "full", "items": [base(r) for r in chunk]},
            )
            written.append((bid, "full", len(chunk)))

        for i in range(0, len(bf), args.size):
            chunk = bf[i : i + args.size]
            bid = "backfill-%02d" % (i // args.size + 1)
            rows = []
            for r in chunk:
                row = base(r)
                row["missing"] = r.get("missing") or []
                row["backfillWeight"] = r.get("backfillWeight")
                row["existingEnrichment"] = enr.get(r["id"]) or {}
                rows.append(row)
            dump(WORK / f"in-{bid}.json", {"batchId": bid, "mode": "backfill", "items": rows})
            written.append((bid, "backfill", len(chunk)))

    # ------------------------------------------------------------------
    # 题库批次（problemBankQueue）。
    #
    # 这些条目来自 problem-bank.json —— 按「被考频度」排序的高频手撕/笔试题，与
    # queue 里的条目可能重叠（一道高频题恰好本月也被采集成卡片时），但两者意图不同：
    # queue 回答「今天采进来的什么值得深读」，题库批次回答「读者最可能被问到的题，
    # 哪些还没有可照着刷的解析」。目标 id 可能不在 queue 里（老题不会重新采集），
    # 所以必须单独出批次，否则题库页永远只有题面没有解析。
    #
    # mode=full 是刻意的：题库深读的产出契约（daily-agent.md §2.2）要求完整的
    # tldr / teaching / diagram / problem 块，没有「只补一层」的余地。
    # ------------------------------------------------------------------
    bankq = plan.get("problemBankQueue") or []
    if bankq:
        queue_ids = {r.get("id") for r in queue}
        bid = "problems-01"
        rows = []
        for r in bankq:
            iid = r.get("itemId")
            if not iid:
                continue
            # Already handled by a queue batch this round — a problem reached through
            # the normal queue still gets its mandatory `problem` block (kind=problem),
            # so re-listing it here would just duplicate the work and the merge.
            if iid in queue_ids:
                continue
            row = base({"id": iid, "title": r.get("title"),
                        "url": r.get("url"), "kind": "problem"})
            # 题库上下文：题号/频度/公司是「为什么先解析这道」的依据，
            # agent 要据此写 interviewTips（哪些公司在考、考到什么程度）。
            row["bankKey"] = r.get("key")
            row["problemNumber"] = r.get("number")
            row["examFrequency"] = r.get("frequency")
            row["askingCompanies"] = r.get("companies") or []
            row["lastAsked"] = r.get("lastAsked")
            row["bankTopics"] = r.get("topics") or []
            row["analysisStatus"] = r.get("analysisStatus")
            row["bankSources"] = r.get("sources") or []
            rows.append(row)
        dump(WORK / f"in-{bid}.json", {"batchId": bid, "mode": "full", "items": rows})
        written.append((bid, "full", len(rows)))

    total = sum(w[2] for w in written)
    for bid, mode, n in written:
        print(f"in-{bid}.json  mode={mode:<8} items={n}")
    print(f"\n{len(written)} batch(es), {total} item(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
