#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scope_deep_read.py — 把深度解析队列缩到可验证的规模

为什么需要它
  `deep-read-plan.json` 现在有 115 条待深读。让 Agent 一次处理完 115 条既是
  很长的一次运行，也不方便你核对质量。这个工具按需截取一个**有代表性的子集**
  （每类取样，保证覆盖面），并保留完整计划，跑完可以一键还原。

  原始完整计划备份到 `deep-read-plan.full.json`，`--restore` 还原。

用法
  python scripts/scope_deep_read.py --per-category 2      # 每类取 2 条
  python scripts/scope_deep_read.py --total 20            # 总共取 20 条（跨类轮转）
  python scripts/scope_deep_read.py --show                # 看当前队列
  python scripts/scope_deep_read.py --restore             # 还原完整队列
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from collections import OrderedDict, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "web" / "data" / "deep-read-plan.json"
BACKUP = ROOT / "web" / "data" / "deep-read-plan.full.json"


def load(p: Path):
    return json.loads(p.read_text("utf-8"))


def save(p: Path, doc) -> None:
    with io.open(p, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-category", type=int, default=0)
    ap.add_argument("--total", type=int, default=0)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--restore", action="store_true")
    args = ap.parse_args()

    if args.restore:
        if not BACKUP.exists():
            print("no deep-read-plan.full.json backup found; nothing to restore")
            return 1
        save(PLAN, load(BACKUP))
        BACKUP.unlink()
        print(f"restored the full queue ({len(load(PLAN).get('queue') or [])} items)")
        return 0

    plan = load(PLAN)
    queue = plan.get("queue") or []

    if args.show or not (args.per_category or args.total):
        by_cat = defaultdict(int)
        for r in queue:
            by_cat[r.get("category")] += 1
        print(f"current queue: {len(queue)} items")
        for k, v in sorted(by_cat.items(), key=lambda x: -x[1]):
            print(f"  {k:<14} {v}")
        if not args.show:
            print("\nuse --per-category N or --total N to scope it")
        return 0

    # Keep the original recoverable before overwriting.
    if not BACKUP.exists():
        save(BACKUP, plan)
        print(f"full queue backed up -> {BACKUP.name}")

    if args.per_category:
        picked, per = [], defaultdict(int)
        for r in queue:
            c = r.get("category")
            if per[c] < args.per_category:
                picked.append(r)
                per[c] += 1
    else:
        # Round-robin across categories so the sample stays broad.
        buckets = OrderedDict()
        for r in queue:
            buckets.setdefault(r.get("category"), []).append(r)
        picked = []
        i = 0
        while len(picked) < args.total:
            added = False
            for c, rows in buckets.items():
                if i < len(rows) and len(picked) < args.total:
                    picked.append(rows[i])
                    added = True
            if not added:
                break
            i += 1

    plan["queue"] = picked
    plan["scopedRun"] = {"requested": args.per_category or args.total,
                         "unit": "perCategory" if args.per_category else "total",
                         "ofFullQueue": len(queue),
                         "note": "verification subset; full plan in deep-read-plan.full.json"}
    save(PLAN, plan)

    print(f"scoped: {len(picked)} items (of {len(queue)})")
    for r in picked:
        print(f"  {r.get('category'):<13} {str(r.get('depthScore')):>6}  {str(r.get('title'))[:56]}")
    print("\nafter the run: python scripts/scope_deep_read.py --restore")
    return 0


if __name__ == "__main__":
    sys.exit(main())
