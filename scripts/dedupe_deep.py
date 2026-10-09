#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dedupe_deep.py — 第二轮去重：找出去重器漏掉的"同一件事的多个版本"

为什么要第二轮
  采集器的四层去重（ID / 规范 URL / 标题指纹 / SimHash）在**当轮**工作，
  但它对两类情况无能为力：
    1. **同一模型/论文的不同打包或改名**：例如同一个 AEON 模型被上传成
       `-NVFP4` / `-MLX` / `-NVF` 三个仓库；同一篇论文在 arXiv 与 OpenAlex
       各出现一次；同一篇报道被多个中文媒体转载。
    2. **标题差异过大**：SimHash 汉明距离 > 3 就不算重复，但人一眼能看出
       是同一件事（例如「DeepSeek 发布 V4」与「DeepSeek V4 技术报告解读」）。

  这些剩余重复不会让程序崩溃，但会让「今日速览」和分类列表里出现两份几乎
  相同的内容，正是用户说的"不必要的冗余"。

判定手段（可解释、可复核）
  A. 规范化标题骨架完全相同 -> 重复
  B. 规范化标题骨架互为前缀且长度差 <= 6 -> 同一事物的不同后缀（-MLX / -NVFP4 / 中文副标题）
  C. 同一 canonicalUrl（去掉 arXiv 版本号后）-> 重复
  D. 标题骨架的 3-gram Jaccard >= 0.86 且同渠道/同分类 -> 近似重复
  保留策略：保留信息更完整的那条（摘要更长 > 有深度解析 > 相关度更高），
  并把被删除条目的 URL 合并进保留条目的 sources，避免丢来源。

用法
  python scripts/dedupe_deep.py                 # 只报告
  python scripts/dedupe_deep.py --apply         # 执行（归档 + blocklist）
  python scripts/dedupe_deep.py --threshold 0.9 # 收紧 Jaccard
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"
INDEX = DATA / "items" / "index.json"
COPY = DATA / "items.json"
STATE = DATA / "state" / "collector-state.json"
ARCHIVE = DATA / "archive"
CST = timezone(timedelta(hours=8))

# Suffixes that mark repackagings of the same artifact rather than new work.
REPACK_SUFFIX = re.compile(
    r"(?:[-_](?:mlx|nvf|nvfp4|nvfp\d|gguf|awq|gptq|int\d|fp\d|bpw|4bit|8bit|w4a16|"
    r"quantized|quant|cuda|onnx|triton|vllm|sglang|safetensors|full|base|instruct|chat|"
    r"preview|beta|rc\d*|v\d+))+$", re.I)


def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def load(p: Path, fb):
    try:
        if p.exists():
            return json.loads(p.read_text("utf-8"))
    except Exception as e:
        print(f"[warn] {p.name}: {e}", file=sys.stderr)
    return fb


def skeleton(title: str) -> str:
    """Normalise a title to a comparison skeleton."""
    s = str(title or "").lower()
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"[\s\u3000]+", "", s)
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "", s)
    return s


def strip_repack(title: str) -> str:
    s = skeleton(title)
    prev = None
    while prev != s:
        prev = s
        s = REPACK_SUFFIX.sub("", s)
    return s or skeleton(title)


def trigrams(s: str) -> set:
    if len(s) <= 3:
        return {s} if s else set()
    return {s[i:i + 3] for i in range(len(s) - 2)}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def canonical_of(item: dict) -> str:
    """A URL identity that is safe to group on, or '' if the URL cannot identify.

    Two traps here, both of which produced a wrong merge of 29 Tencent postings:

      1. Stripping the whole query string destroyed the identity. Tencent serves
         every posting at the SAME path - `careers.tencent.com/jobdesc.html` -
         and distinguishes them only by `?postId=...`. Removing the query made all
         29 postings look like one duplicated URL.
      2. Tracking parameters (?utm_source, ?ref, ?spm) DO need removing, but only
         an explicit list, never the entire query.

      3. A bare host/path with no distinguishing segment is not an identity at
         all: `news.ycombinator.com/item` is every HN post. Such URLs return ''
         so the caller falls back to title-based comparison.
    """
    raw = str(item.get("canonicalUrl") or item.get("url") or "").strip()
    if not raw:
        return ""
    u = raw.split("#", 1)[0]
    # Drop only known tracking parameters.
    if "?" in u:
        base, q = u.split("?", 1)
        keep = [kv for kv in q.split("&")
                if kv and not re.match(r"(?i)^(utm_\w+|ref|ref_src|source|spm|from|share_\w+|"
                                      r"fbclid|gclid|igshid|si|_hsenc|_hsmi)=", kv)]
        u = base + ("?" + "&".join(sorted(keep)) if keep else "")
    # Normalise arXiv version suffixes so v1/v2 are the same paper.
    u = re.sub(r"(arxiv\.org/(?:abs|pdf)/\d{4}\.\d{4,5})v\d+", r"\1", u)
    u = u.rstrip("/").lower()
    # Reject URLs that carry no distinguishing information.
    stripped = re.sub(r"^https?://", "", u)
    path = stripped.split("?", 1)[0]
    has_query = "?" in u and len(u.split("?", 1)[1]) >= 3
    # host + a real path, or host + a real query
    if not has_query and path.count("/") < 2:
        return ""
    if len(path) <= len("host.com/x"):
        return ""
    return u


def richness(item: dict) -> tuple:
    """Higher is better: this is the one we keep."""
    return (
        1 if item.get("enriched") else 0,
        len(str(item.get("summary") or "")),
        float(item.get("relevanceScore") or 0),
        len(str(item.get("title") or "")),
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="dedupe_deep.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--threshold", type=float, default=0.86,
                    help="3-gram Jaccard threshold for near-duplicates (default 0.86)")
    ap.add_argument("--show", type=int, default=15)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args(argv)

    doc = load(INDEX, {}) or {}
    items = doc.get("items") or []
    if not items:
        print("index empty")
        return 0
    enrich = set(((load(DATA / "enrichment.json", {}) or {}).get("byId") or {}).keys())
    for it in items:
        it["enriched"] = it.get("id") in enrich

    # ---- A: identical, fully normalised titles ----------------------------
    # Candidate pairs come from a shared skeleton key, but key equality alone is
    # NOT sufficient: "微信小店-推荐算法工程师" and "微信-大模型后训练算法专家"
    # both contain "算法工程师", so a substring relationship makes many distinct
    # postings share a skeleton key. Every candidate below must additionally pass
    # a real similarity test.
    by_skel: dict[str, list] = defaultdict(list)
    for it in items:
        by_skel[strip_repack(it.get("title"))].append(it)

    def similar(a: str, b: str) -> bool:
        """Same artefact in different packaging? Requires near-identity."""
        if a == b:
            return True
        if abs(len(a) - len(b)) > 4:
            return False
        return jaccard(trigrams(a), trigrams(b)) >= 0.90

    groups: list[list] = []
    seen_pairs: set = set()
    for skel, rows in by_skel.items():
        if len(rows) < 2:
            continue
        # Cluster within this key by real similarity, not by key membership.
        clusters: list[list] = []
        for it in rows:
            s = strip_repack(it.get("title"))
            placed = False
            for cl in clusters:
                if similar(s, strip_repack(cl[0].get("title"))):
                    cl.append(it)
                    placed = True
                    break
            if not placed:
                clusters.append([it])
        for cl in clusters:
            if len(cl) > 1:
                groups.append(cl)

    # ---- B: prefix relationships (repack suffixes like -mlx / -nvfp4) ------
    keys = sorted(by_skel.keys(), key=len)
    for i, a in enumerate(keys):
        if not a or len(a) < 14:
            continue
        for b in keys[i + 1:]:
            if len(b) - len(a) > 4:
                break
            if b.startswith(a) and similar(a, b):
                pair = tuple(sorted([a, b]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                groups.append(by_skel[a] + by_skel[b])

    # ---- C: same canonical url -------------------------------------------
    by_url: dict[str, list] = defaultdict(list)
    for it in items:
        u = canonical_of(it)
        if u:
            by_url[u].append(it)
    for u, rows in by_url.items():
        if len(rows) > 1:
            groups.append(rows)

    # ---- C: near-duplicate by trigram Jaccard within the same channel ------
    #
    # Kept deliberately strict. Short Chinese strings have few trigrams, so two
    # unrelated postings that merely share a common component ("微信小店的推荐"
    # vs "微信小店的风控") score high: that produced a false merge of 28 Tencent
    # job postings. Guards: the skeleton must be long enough to carry identity,
    # and the score must be very high. The cheap exact/prefix rules above already
    # catch genuine repackagings, so this rule only needs to catch long-title
    # republications.
    by_channel: dict[str, list] = defaultdict(list)
    for it in items:
        by_channel[str(it.get("channel"))].append(it)
    pair_threshold = max(args.threshold, 0.95)
    for ch, rows in by_channel.items():
        if len(rows) < 2:
            continue
        sigs = []
        for it in rows:
            s = strip_repack(it.get("title"))
            if len(s) >= 12:
                sigs.append((it, s, trigrams(s)))
        for i in range(len(sigs)):
            for j in range(i + 1, len(sigs)):
                a, sa, ta = sigs[i]
                b, sb, tb = sigs[j]
                if abs(len(sa) - len(sb)) > 6:
                    continue
                if jaccard(ta, tb) >= pair_threshold:
                    groups.append([a, b])

    # ---- resolve overlap between groups ----------------------------------
    assigned: dict[str, int] = {}
    final: list[list] = []
    for g in groups:
        ids = [it.get("id") for it in g]
        seen = {assigned.get(i) for i in ids if i in assigned}
        seen.discard(None)
        if seen:
            # merge into the first existing group
            gi = sorted(seen)[0]
            have = {it.get("id") for it in final[gi]}
            for it in g:
                if it.get("id") not in have:
                    final[gi].append(it)
                    have.add(it.get("id"))
            for i in ids:
                assigned[i] = gi
            continue
        idx = len(final)
        final.append(list(g))
        for i in ids:
            assigned[i] = idx

    # ---- decide keep / drop ----------------------------------------------
    drops: list[dict] = []
    merges: list[dict] = []
    for g in final:
        if len(g) < 2:
            continue
        g_sorted = sorted(g, key=richness, reverse=True)
        keep = g_sorted[0]
        gone = g_sorted[1:]
        for it in gone:
            drops.append({
                "id": it.get("id"), "title": it.get("title"),
                "channel": it.get("channel"), "category": it.get("category"),
                "url": it.get("url"), "keptAs": keep.get("id"),
                "keptTitle": keep.get("title"),
            })
        merges.append({
            "kept": {"id": keep.get("id"), "title": keep.get("title"),
                     "channel": keep.get("channel")},
            "dropped": [{"id": it.get("id"), "title": it.get("title"),
                         "url": it.get("url")} for it in gone],
        })

    drop_ids = {d["id"] for d in drops}
    if args.debug:
        print(f"[debug] groups={len(groups)} final={len(final)}")
        from collections import Counter as _C
        sizes = _C(len(g) for g in final if len(g) > 1)
        print(f"[debug] group sizes: {dict(sizes)}")
        big = max(final, key=len) if final else []
        if len(big) > 3:
            print(f"[debug] largest group has {len(big)} members:")
            for it in big[:6]:
                print(f"          {it.get('channel')}: {str(it.get('title'))[:60]}")
            print(f"          skeleton: {strip_repack(big[0].get('title'))!r}")
    print("")
    print("=" * 78)
    print("第二轮深度去重（同一事物的多个版本）" + ("（--apply：将执行）" if args.apply else "（仅报告）"))
    print("=" * 78)
    print(f"  库内卡片        : {len(items)}")
    print(f"  重复组          : {len([g for g in final if len(g) > 1])}")
    print(f"  建议下架        : {len(drops)}")
    print(f"  Jaccard 阈值    : {args.threshold}")
    if drops:
        print(f"  下架按渠道      : " + ", ".join(f"{k}={v}" for k, v in
              Counter(d['channel'] for d in drops).most_common(8)))
    print("")
    for m in merges[:args.show]:
        print(f"  保留: {str(m['kept']['title'])[:66]}  [{m['kept']['channel']}]")
        for d in m["dropped"]:
            print(f"    合并: {str(d['title'])[:62]}")
    print("=" * 78)

    if not args.apply:
        print("")
        print("只报告模式，未改动数据。执行： python scripts/dedupe_deep.py --apply")
        print("")
        return 0

    # ---- apply ------------------------------------------------------------
    # Merge the dropped items' URLs into the kept item's sources so no source is
    # lost by de-duplication.
    by_id = {it.get("id"): it for it in items}
    for m in merges:
        keep = by_id.get(m["kept"]["id"])
        if not keep:
            continue
        srcs = list(keep.get("sources") or [])
        have = {s.get("url") for s in srcs if isinstance(s, dict)}
        for d in m["dropped"]:
            if d.get("url") and d["url"] not in have:
                srcs.append({"url": d["url"], "name": "merged-duplicate"})
                have.add(d["url"])
        keep["sources"] = srcs[:8]
        keep["mergedDuplicates"] = (keep.get("mergedDuplicates") or 0) + len(m["dropped"])

    kept_items = [it for it in items if it.get("id") not in drop_ids]

    ARCHIVE.mkdir(parents=True, exist_ok=True)
    day = datetime.now(CST).strftime("%Y-%m-%d")
    payload = {"archivedAt": now_iso(), "reason": "second-pass semantic de-duplication",
               "threshold": args.threshold, "count": len(drops),
               "merges": merges, "items": [it for it in items if it.get("id") in drop_ids]}
    with io.open(ARCHIVE / f"deduped-{day}.json", "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    print(f"  archived {len(drops)} -> data/archive/deduped-{day}.json")

    for path in (INDEX, COPY):
        d = dict(load(path, {}) or {})
        d["items"] = kept_items
        d["count"] = len(kept_items)
        d["dedupedAt"] = now_iso()
        d["dedupedCount"] = len(drops)
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(d, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"  index rewritten: {len(items)} -> {len(kept_items)}")

    state = load(STATE, {}) or {}
    state["blockedIds"] = sorted(set(state.get("blockedIds") or []) | drop_ids)
    state["lastDedupeAt"] = now_iso()
    with io.open(STATE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(state, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"  blocklist now: {len(state['blockedIds'])} ids")

    # manifest + digest consistency (same reasoning as prune_items.py)
    man = dict(load(DATA / "manifest.json", {}) or {})
    if man:
        man["totalItems"] = len(kept_items)
        man["dedupedAt"] = now_iso()
        man["dedupedCount"] = len(drops)
        s = dict(man.get("summary") or {})
        if s:
            c = dict(s.get("counts") or {})
            c["total"] = len(kept_items)
            s["counts"] = c
            if s.get("headline"):
                s["headline"] = re.sub(r"累计\s*\d+\s*条", f"累计 {len(kept_items)} 条", str(s["headline"]))
            man["summary"] = s
        with io.open(DATA / "manifest.json", "w", encoding="utf-8", newline="\n") as fh:
            json.dump(man, fh, ensure_ascii=False, separators=(",", ":"))
        print(f"  manifest.totalItems -> {len(kept_items)}")

    kept_ids = {it.get("id") for it in kept_items}
    dpath = DATA / "digest" / "today.json"
    dg = load(dpath, None)
    if isinstance(dg, dict):
        before = len(dg.get("items") or [])
        dg["items"] = [i for i in (dg.get("items") or []) if i.get("id") in kept_ids]
        if dg.get("summary"):
            c = dict(dg["summary"].get("counts") or {})
            c["fresh"] = len(dg["items"])
            c["total"] = len(kept_items)
            dg["summary"]["counts"] = c
            dg["summary"]["topItemIds"] = [x for x in (dg["summary"].get("topItemIds") or [])
                                           if x in kept_ids]
        with io.open(dpath, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(dg, fh, ensure_ascii=False, separators=(",", ":"))
        dd = dg.get("date")
        if dd:
            with io.open(DATA / "digest" / f"{dd}.json", "w", encoding="utf-8", newline="\n") as fh:
                json.dump(dg, fh, ensure_ascii=False, separators=(",", ":"))
        if before != len(dg["items"]):
            print(f"  digest fresh items: {before} -> {len(dg['items'])}")
    print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
