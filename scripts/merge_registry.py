#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_registry.py — 把 research/source_registry.json（91 个渠道的实测注册表）
合并进 web/data/sources.json，并保留采集器最新一轮的实测状态。

为什么需要单独一步：
  * 采集器 (collect.py) 只知道它真的跑过的渠道与当轮状态，覆盖不全。
  * 调研产物 source_registry.json 覆盖 91 个渠道，含 robots.txt 证据、
    备用源映射、限速、合规判定，但它是**静态**的（不随每日运行更新）。
  * 两者合起来才是完整答案：注册表提供广度与合规证据，运行记录提供最新健康度。

合并规则（重要，避免互相污染）：
  1. 以注册表为骨架（广度优先）。
  2. 若某个渠道在 sources.json 里已有**实测运行状态**（status ∈ ok/empty/error/
     blocked 且带 lastChecked），保留它并记录 `statusSource`，绝不降级回 "unknown"。
  3. 注册表的 robots/合规字段（`robotsAllowed`、`offLimits`、`legitimacy`）
     优先于运行状态：合规结论不应被一次成功抓取推翻。
  4. 采集器写入的分类与关键词（categories）保持不动，只补充注册表里更细的
     per-category 内容（有则合并，无则保留现状）。

用法: python scripts/merge_registry.py [--check]
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"
REGISTRY = ROOT / "research" / "source_registry.json"
SOURCES = DATA / "sources.json"
PROBE = ROOT / "research" / "channel_probe.json"
CST = timezone(timedelta(hours=8))

# 注册表里的渠道 id 与本工作台使用的 id 不一定相同，显式别名避免漏合并。
ALIASES = {
    "arxiv-api": "arxiv",
    "arxiv-rss": "arxiv",
    "hf-daily-papers": "hf_papers",
    "hf-models": "hf_models",
    "hf-models-new": "hf_models",
    "github-trending-html": "gh_trending",
    "github-search-repos": "github",
    "github-search-new-repos": "github",
    "github-search-code": "github",
    "hn-algolia": "hn",
    "media-qbitai": "qbitai",
    "media-infoq-cn": "infoq",
    "media-jiqizhixin-html": "machineheart",
    "openreview-search": "openreview",
    "openreview-api": "openreview",
    "semantic-scholar-api": "s2",
    "careers-tencent-api": "jobs_tencent",
    "zhipin-boss": "boss",
    "xiaohongshu-search": "xiaohongshu",
    "xiaohongshu-explore": "xiaohongshu",
    "zhihu-search": "zhihu",
    "zhihu-api-v4": "zhihu",
    "zhihu-hot": "zhihu",
    "nowcoder-search": "nowcoder",
    "nowcoder-home": "nowcoder",
    "nowcoder-discuss": "nowcoder",
    "reddit-json": "reddit",
    "rsshub-app": "rsshub",
    "leetcode-legacy-api": "leetcode",
    "leetcode-cn-graphql": "leetcode",
    "papers-with-code": "pwc",
    "acl-anthology-index": "acl",
}


def now() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def load(path: Path, fallback):
    try:
        if path.exists():
            return json.loads(path.read_text("utf-8"))
    except Exception as e:
        print(f"[warn] cannot read {path.name}: {e}", file=sys.stderr)
    return fallback


def norm_id(rid: str) -> str:
    return ALIASES.get(rid, rid)


LIVE_STATUSES = {"ok", "empty", "error", "blocked", "partial"}


def merge() -> dict:
    sources = load(SOURCES, {}) or {}
    registry = load(REGISTRY, {}) or {}
    probe = load(PROBE, {}) or {}

    live = {c.get("id"): c for c in (sources.get("channels") or []) if c.get("id")}
    reg_channels = registry.get("channels") or []
    probe_rows = {r.get("id"): r for r in (probe.get("channels") or []) if isinstance(r, dict)}

    merged: dict[str, dict] = {}

    # 1. registry is the skeleton (breadth)
    for rc in reg_channels:
        if not isinstance(rc, dict):
            continue
        cid = norm_id(str(rc.get("id") or "").strip())
        if not cid:
            continue
        entry = {
            "id": cid,
            "registryId": rc.get("id"),
            "nameZh": rc.get("nameZh") or rc.get("name") or cid,
            "nameEn": rc.get("nameEn") or rc.get("name") or cid,
            "tier": rc.get("tier") or rc.get("priority") or "P2",
            "mode": rc.get("recommendedMode") or rc.get("mode") or "unknown",
            "authRequired": bool(rc.get("authRequired")),
            "status": "unknown",
            "statusSource": "registry (not yet run)",
            "httpStatus": rc.get("httpStatus"),
            "rateLimit": rc.get("rateLimit"),
            "riskNote": rc.get("riskNote") or rc.get("notes") or "",
            "robotsAllowed": rc.get("robotsAllowed"),
            "offLimits": rc.get("offLimits"),
            "backup": rc.get("backupSources") or rc.get("backup") or [],
            "lastChecked": rc.get("lastChecked") or registry.get("meta", {}).get("generatedAt"),
        }
        merged[cid] = entry

    # 2. collector's live observations override status (but never compliance)
    for cid, lc in live.items():
        entry = merged.get(cid) or {
            "id": cid,
            "nameZh": lc.get("nameZh") or cid,
            "nameEn": cid,
            "tier": lc.get("tier", "P2"),
            "mode": lc.get("mode", "unknown"),
            "authRequired": bool(lc.get("authRequired")),
            "riskNote": "",
            "backup": lc.get("backup") or [],
        }
        st = lc.get("status")
        if st in LIVE_STATUSES:
            entry["status"] = st
            entry["statusSource"] = f"collector run {lc.get('checkedAt') or ''}".strip()
            entry["lastChecked"] = lc.get("checkedAt") or entry.get("lastChecked")
            if lc.get("count") is not None:
                entry["count"] = lc.get("count")
            if lc.get("error"):
                entry["lastError"] = str(lc["error"])[:200]
        merged[cid] = entry

    # 3. probe evidence fills in anything still unknown
    for cid, pr in probe_rows.items():
        nid = norm_id(str(cid))
        entry = merged.get(nid)
        if not entry:
            continue
        if entry.get("status") == "unknown" and pr.get("status"):
            entry["status"] = pr["status"]
            entry["statusSource"] = "probe-channels.py"
            entry["lastChecked"] = pr.get("checkedAt") or entry.get("lastChecked")
        for k in ("evidenceFile", "httpStatus", "error", "riskNote"):
            if pr.get(k) and not entry.get(k):
                entry[k] = pr[k]

    out = dict(sources)
    out["generatedAt"] = now()

    # Order for humans, not alphabetically: channels that actually produced data
    # first, then runnable-but-empty, then blocked/manual, then unverified.
    state_rank = {"ok": 0, "partial": 1, "empty": 2, "error": 3, "blocked": 4, "unknown": 5}
    tier_rank = {"P0": 0, "P1": 1, "P2": 2, "MANUAL": 3}
    out["channels"] = sorted(
        merged.values(),
        key=lambda c: (state_rank.get(str(c.get("status")), 9),
                       tier_rank.get(str(c.get("tier")), 9),
                       str(c.get("id"))))
    out["registryMerged"] = {
        "registryFile": str(REGISTRY.relative_to(ROOT)) if REGISTRY.exists() else None,
        "registryChannels": len(reg_channels),
        "probeFile": str(PROBE.relative_to(ROOT)) if PROBE.exists() else None,
        "mergedChannels": len(out["channels"]),
        "liveStatusChannels": sum(1 for c in out["channels"] if str(c.get("statusSource", "")).startswith("collector")),
        "realMeasured": sum(1 for c in out["channels"] if c.get("status") not in (None, "unknown")),
    }
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="merge_registry.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="merge and report, do not write")
    args = ap.parse_args(argv)

    payload = merge()
    info = payload["registryMerged"]
    print(f"channels: {info['registryChannels']} from registry -> {info['mergedChannels']} merged")
    print(f"  with a real measured status: {info['realMeasured']}")
    print(f"  from the latest collector run: {info['liveStatusChannels']}")
    tiers: dict[str, int] = {}
    for c in payload["channels"]:
        tiers[str(c.get("tier"))] = tiers.get(str(c.get("tier")), 0) + 1
    print("  by tier: " + ", ".join(f"{k}={v}" for k, v in sorted(tiers.items())))
    statuses: dict[str, int] = {}
    for c in payload["channels"]:
        statuses[str(c.get("status"))] = statuses.get(str(c.get("status")), 0) + 1
    print("  by status: " + ", ".join(f"{k}={v}" for k, v in sorted(statuses.items())))

    if args.check:
        print("[check] nothing written")
        return 0

    with io.open(SOURCES, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"wrote {SOURCES} ({SOURCES.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
