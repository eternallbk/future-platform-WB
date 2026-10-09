#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_agent_out.py — 校验并合并深读子代理的产出。

用法
  python scripts/apply_agent_out.py --check     # 只校验，不改数据
  python scripts/apply_agent_out.py --apply     # 校验通过后合并写入 web/data/

契约（见 scripts/daily-agent.md / scripts/agent-work/INSTRUCTIONS.md）
  · enrichment.json 按 item id 键控，**必须合并写**：full 条目覆盖同 id，backfill 条目深合并。
  · formulas.json 按 id 去重后追加，保留全部已有公式。
  · 不手工改 items/index.json。
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"
WORK = ROOT / "scripts" / "agent-work"

# kind 判定必须用与采集 / 清理同一个权威（knowledge_quality），否则「哪些条目必须
# 交代码解析」会与题库页 / 计划的判断不一致。
try:
    if str(Path(__file__).resolve().parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    import knowledge_quality as KQ
except Exception:                                  # pragma: no cover
    KQ = None


def src_kind(src: dict) -> str:
    """kind of the SOURCE item, recomputed (stored values can be stale)."""
    if KQ is None:
        return str(src.get("kind") or "")
    return KQ.classify_kind(src)

REQ_FULL = [
    "id", "tldr", "keyPoints", "why", "difficulty", "tags", "entities",
    "diagram", "concepts", "formulas", "selfCheck", "teaching",
]
TEACHING_KEYS = [
    "progressive", "socratic", "mechanism", "boundary", "analogyBoundary",
    "misconceptions", "ownAnalysis", "officialNotes", "interviewAnswer", "studyPath",
]
DIAGRAM_KINDS = {"flow", "architecture", "curve", "matrix", "timeline"}
SPEC_TYPES = {"flow", "architecture", "curve", "matrix", "timeline"}
CONCEPT_KEYS = [
    "name", "readable", "analogy", "analogyBreaksDown", "mechanism",
    "visual", "prerequisites", "selfTest", "formula",
]
FORMULA_KEYS = ["id", "name", "category", "latex", "symbols", "derivation",
                "analogy", "pitfalls", "code", "sources"]
FORMULA_CATS = {"multimodal", "posttraining", "worldmodel", "generative",
                "rl", "agent", "foundation", "engineering"}

# --- 手撕题 / 笔试题的强制解析层（scripts/daily-agent.md §2.2）----------------
# 读者要求：题库里的题必须给出「深入的代码解析或配图解析」，不能只留一个仓库链接。
# 所以 kind == problem 的条目必须自带 problem 块；缺了就是 error。
PROBLEM_REQ = ["title", "statement", "examples", "approach", "solution",
               "complexity", "pitfalls", "edgeCases"]
PROBLEM_APPROACH_REQ = ["idea", "steps", "whyItWorks", "alternatives"]
PROBLEM_COMPLEXITY_REQ = ["time", "space", "why"]
# 例外：题解聚合页 / 系列小结 / 真题汇总不是「一道题」，硬凑 problem 块只会催生编造。
# 这类条目按 notes 处理，且必须在 selfCheck.uncertain 里说明。
PROBLEM_AGG_RE = re.compile(
    r"小结|汇总|合集|题解导航|系列(?:一|二|三|四|五|\d)|真题（20|题库|刷题攻略|"
    # 「真题」后面的计数既可能是全角括号（真题（2026）），也可能是冒号（真题：200+算法题），
    # 两种都是聚合页；只认前一种会把「2026大厂笔试真题：200+算法题」误判成单题。
    r"真题[:：]?\s*\d|"
    r"知识库|目录|索引|总览|合集|指南|路线|从零|入门")

SVG_BAD = ["<image", "<use", "<style", "<script", "url(", " onload", " onerror", " onclick"]
LATEX_BAD = [r"\begin{align}", r"\bm", r"\substack", r"\newcommand", r"\def ", r"\tag{"]
CJK = re.compile(r"[\u4e00-\u9fff]")


def load(p: Path):
    return json.loads(p.read_text("utf-8"))


def dump(p: Path, doc) -> None:
    with io.open(p, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    errs: list[str] = []
    warns: list[str] = []

    idx = {r["id"]: r for r in load(DATA / "items" / "index.json")["items"]}
    old_enr = load(DATA / "enrichment.json").get("byId") or {}
    old_formulas = load(DATA / "formulas.json").get("formulas") or []
    existing_fids = {f.get("id") for f in old_formulas}

    merged: dict[str, dict] = {}
    new_formulas: list[dict] = []
    seen_fids: set[str] = set()
    skips: list[dict] = []
    enriched_ids: list[str] = []
    replaced_ids: list[str] = []
    stats = {"full": 0, "backfill": 0, "entries": 0}

    for out in sorted(WORK.glob("out-*.json")):
        doc = load(out)
        bid = doc.get("batchId") or out.stem.replace("out-", "")
        inp_path = WORK / f"in-{bid}.json"
        if not inp_path.exists():
            errs.append(f"{bid}: 找不到输入文件 {inp_path.name}")
            continue
        inp = load(inp_path)
        mode = inp["mode"]
        by_id = {r["id"]: r for r in inp["items"]}

        entries = doc.get("entries") or []
        skipped = doc.get("skipped") or []
        got = [e.get("id") for e in entries] + [s.get("id") for s in skipped]

        missing_ids = sorted(set(by_id) - set(got))
        extra_ids = sorted(set(got) - set(by_id))
        dup_ids = sorted({i for i in got if got.count(i) > 1})
        if missing_ids:
            errs.append(f"{bid}: 未处理 {missing_ids}")
        if extra_ids:
            errs.append(f"{bid}: 出现输入外的 id {extra_ids}")
        if dup_ids:
            errs.append(f"{bid}: id 重复 {dup_ids}")

        for s in skipped:
            if not s.get("evidence"):
                errs.append(f"{bid}/{s.get('id')}: skip 缺 evidence")
            skips.append({"batchId": bid, **s})

        for e in entries:
            iid = e.get("id")
            src = by_id.get(iid)
            if src is None:
                continue
            stats["entries"] += 1

            if mode == "full":
                for k in REQ_FULL:
                    if k not in e:
                        errs.append(f"{bid}/{iid}: full 缺字段 {k}")
                for k in ("tldr", "why"):
                    if not str(e.get(k) or "").strip():
                        errs.append(f"{bid}/{iid}: {k} 为空")
                if not (e.get("keyPoints") or []):
                    errs.append(f"{bid}/{iid}: keyPoints 为空")
                t = e.get("teaching") or {}
                for k in TEACHING_KEYS:
                    if k not in t:
                        errs.append(f"{bid}/{iid}: teaching 缺 {k}")
                prog = t.get("progressive") or []
                if len(prog) < 4:
                    errs.append(f"{bid}/{iid}: progressive 不足 4 档")
                for k in ("mechanism", "boundary", "analogyBoundary"):
                    if not str(t.get(k) or "").strip():
                        errs.append(f"{bid}/{iid}: teaching.{k} 为空（必填）")
                if not (t.get("misconceptions") or []):
                    errs.append(f"{bid}/{iid}: misconceptions 为空")
                if not (t.get("socratic") or []):
                    errs.append(f"{bid}/{iid}: socratic 为空")

                # ---- problem block（手撕题 / 笔试题的强制解析）----
                # 契约见 scripts/daily-agent.md §2.2：题目必须被真的解出来 ——
                # 可运行代码 + 具体复杂度 + 易错点 + 边界用例，而不是一篇泛泛的讲解。
                kind = src_kind(src)
                is_agg = bool(PROBLEM_AGG_RE.search(str(src.get("title") or "")))
                pb = e.get("problem")
                if kind == "problem" and not is_agg:
                    if not isinstance(pb, dict):
                        errs.append(f"{bid}/{iid}: kind=problem 但缺 problem 块"
                                    f"（题库页需要代码/复杂度/易错点；如果是聚合页请在 "
                                    f"selfCheck.uncertain 里说明）")
                    else:
                        for k in PROBLEM_REQ:
                            if pb.get(k) in (None, "", [], {}):
                                errs.append(f"{bid}/{iid}: problem 缺 {k}")
                        ap = pb.get("approach") or {}
                        for k in PROBLEM_APPROACH_REQ:
                            if ap.get(k) in (None, "", [], {}):
                                errs.append(f"{bid}/{iid}: problem.approach 缺 {k}")
                        sol = pb.get("solution") or {}
                        code = str(sol.get("python") or sol.get("code") or "").strip()
                        if not code:
                            errs.append(f"{bid}/{iid}: problem.solution.python 为空"
                                        f"（写不出可运行代码就该走 skipped 并写明原因）")
                        elif len(code) < 40:
                            errs.append(f"{bid}/{iid}: problem.solution.python 过短"
                                        f"（{len(code)} 字符，疑似占位）")
                        cx = pb.get("complexity") or {}
                        for k in PROBLEM_COMPLEXITY_REQ:
                            if not str(cx.get(k) or "").strip():
                                errs.append(f"{bid}/{iid}: problem.complexity 缺 {k}")
                        # 复杂度必须是具体记号，不接受「比较快」这类形容词
                        for k in ("time", "space"):
                            v = str(cx.get(k) or "")
                            if v and not re.search(r"O\s*\(|Θ\s*\(|Ω\s*\(", v):
                                errs.append(f"{bid}/{iid}: problem.complexity.{k} "
                                            f"不是大 O 记号：{v[:40]!r}")
                        if len(pb.get("pitfalls") or []) < 2:
                            errs.append(f"{bid}/{iid}: problem.pitfalls 少于 2 条")
                        if not (pb.get("edgeCases") or []):
                            errs.append(f"{bid}/{iid}: problem.edgeCases 为空")
                        if not (pb.get("examples") or []):
                            errs.append(f"{bid}/{iid}: problem.examples 为空")
                elif kind == "problem" and is_agg and pb is None:
                    # 聚合页：不要求 problem 块，但必须自述清楚，避免「悄悄跳过」。
                    warns.append(f"{bid}/{iid}: 题解聚合页，未产出 problem 块（按 notes 处理）")
                elif pb is not None and kind != "problem":
                    warns.append(f"{bid}/{iid}: kind={kind} 却带了 problem 块（已忽略语义）")

                merged[iid] = {k: v for k, v in e.items() if k != "id"}
                if iid in old_enr:
                    replaced_ids.append(iid)
                else:
                    enriched_ids.append(iid)
                stats["full"] += 1
            else:
                allowed = set(inp["items"][0].get("missing") or []) | {"id"}
                # missing 是逐条的；按本条自己的 missing 校验
                this_missing = set(
                    next((r.get("missing") or [] for r in inp["items"] if r["id"] == iid), [])
                )
                extra = set(e.keys()) - {"id"} - this_missing
                if extra:
                    errs.append(f"{bid}/{iid}: backfill 输出了未请求的层 {sorted(extra)}")
                if not this_missing <= set(e.keys()):
                    errs.append(
                        f"{bid}/{iid}: backfill 缺层 {sorted(this_missing - set(e.keys()))}"
                    )
                base = dict(old_enr.get(iid) or {})
                patch = {k: v for k, v in e.items() if k != "id"}
                base.update(patch)          # 深合并：只覆盖本轮补的层
                merged[iid] = base
                if iid in old_enr:
                    replaced_ids.append(iid)
                else:
                    enriched_ids.append(iid)
                stats["backfill"] += 1

            # ---- diagram ----
            dg = e.get("diagram") or {}
            if mode == "full" or "diagram" in (e.keys() & {"diagram"}):
                if dg:
                    if dg.get("kind") not in DIAGRAM_KINDS:
                        errs.append(f"{bid}/{iid}: diagram.kind 非法 {dg.get('kind')!r}")
                    for k in ("title", "caption", "alt"):
                        if not str(dg.get(k) or "").strip():
                            errs.append(f"{bid}/{iid}: diagram 缺 {k}")
                    svg = dg.get("svg") or ""
                    spec = dg.get("spec") or {}
                    if not svg and not spec:
                        errs.append(f"{bid}/{iid}: diagram 既无 svg 也无 spec")
                    if svg:
                        if "viewBox" not in svg:
                            errs.append(f"{bid}/{iid}: svg 缺 viewBox")
                        low = svg.lower()
                        for bad in SVG_BAD:
                            if bad in low:
                                errs.append(f"{bid}/{iid}: svg 含违规 {bad!r}")
                        for fs in re.findall(r"font-size\s*[:=]\s*['\"]?(\d+)", svg):
                            if int(fs) < 13:
                                errs.append(f"{bid}/{iid}: svg font-size {fs} < 13")
                    if spec and spec.get("type") not in SPEC_TYPES:
                        errs.append(f"{bid}/{iid}: spec.type 非法 {spec.get('type')!r}")

            # ---- concepts ----
            for c in e.get("concepts") or []:
                for k in CONCEPT_KEYS:
                    if k not in c:
                        errs.append(f"{bid}/{iid}: concept 缺 {k}（{c.get('name')}）")
                if not str(c.get("analogyBreaksDown") or "").strip():
                    warns.append(f"{bid}/{iid}: concept 的 analogyBreaksDown 为空")

            # ---- formulas ----
            item_urls = {src.get("url")} | {s.get("url") for s in (src.get("sources") or [])}
            item_urls.discard(None)
            for f in e.get("formulas") or []:
                fid = f.get("id")
                if not fid:
                    errs.append(f"{bid}/{iid}: formula 缺 id")
                    continue
                if fid in seen_fids:
                    errs.append(f"{bid}/{iid}: formula id 本轮重复 {fid}")
                if fid in existing_fids:
                    warns.append(f"{bid}/{iid}: formula id 已存在，将跳过 {fid}")
                seen_fids.add(fid)
                for k in FORMULA_KEYS:
                    if k not in f:
                        errs.append(f"{bid}/{iid}/{fid}: formula 缺 {k}")
                if f.get("category") not in FORMULA_CATS:
                    errs.append(f"{bid}/{iid}/{fid}: formula.category 非法 {f.get('category')!r}")
                for k in ("symbols", "derivation", "pitfalls", "sources"):
                    if not (f.get(k) or []):
                        errs.append(f"{bid}/{iid}/{fid}: formula 缺层 {k}（四层齐全）")
                if not str(f.get("code") or "").strip():
                    warns.append(f"{bid}/{iid}/{fid}: formula 无 code")
                for s in f.get("sources") or []:
                    if s.get("url") not in item_urls:
                        errs.append(
                            f"{bid}/{iid}/{fid}: formula source url 不在条目 URL 白名单 {s.get('url')!r}"
                        )
                latex = str(f.get("latex") or "")
                if not latex.strip():
                    errs.append(f"{bid}/{iid}/{fid}: latex 为空")
                for bad in LATEX_BAD:
                    if bad in latex:
                        errs.append(f"{bid}/{iid}/{fid}: latex 含 KaTeX 不支持 {bad!r}")
                for m in re.findall(r"\\text\{([^}]*)\}", latex):
                    if CJK.search(m):
                        errs.append(f"{bid}/{iid}/{fid}: latex \\text{{}} 内出现中文")
                if latex.count("{") != latex.count("}"):
                    errs.append(f"{bid}/{iid}/{fid}: latex 花括号不配对")
                if fid not in existing_fids:
                    new_formulas.append(f)

    # 输入里的 id 必须都被覆盖
    all_input_ids = set()
    for inp_path in WORK.glob("in-*.json"):
        for r in load(inp_path)["items"]:
            all_input_ids.add(r["id"])
    uncovered = sorted(all_input_ids - set(merged) - {s["id"] for s in skips})
    if uncovered:
        errs.append(f"共 {len(uncovered)} 个 id 既未深读也未 skip: {uncovered[:8]}")

    print(f"[entries] full={stats['full']} backfill={stats['backfill']} "
          f"skipped={len(skips)} formulas+{len(new_formulas)}")
    print(f"[errors] {len(errs)}   [warnings] {len(warns)}")
    for e in errs[:40]:
        print("  E", e)
    if len(errs) > 40:
        print(f"  ... 其余 {len(errs) - 40} 条")
    for w in warns[:12]:
        print("  W", w)
    if len(warns) > 12:
        print(f"  ... 其余 {len(warns) - 12} 条 warning")

    if not args.apply:
        return 1 if errs else 0
    if errs:
        print("\n存在 error，拒绝写入。")
        return 1

    now = dt.datetime.now().astimezone().replace(microsecond=0).isoformat()
    by_id = dict(old_enr)
    by_id.update(merged)
    dump(DATA / "enrichment.json", {"generatedAt": now, "byId": by_id})

    formulas = list(old_formulas) + new_formulas
    dump(DATA / "formulas.json",
         {"generatedAt": now, "source": "seed+daily", "formulas": formulas})

    dump(WORK / "skips.json",
         {"generatedAt": now, "count": len(skips), "skipped": skips})

    print(f"\n[apply] enrichment: {len(old_enr)} -> {len(by_id)} (+{len(merged)})")
    print(f"[apply] formulas: {len(old_formulas)} -> {len(formulas)} (+{len(new_formulas)})")
    print(f"[apply] 本轮新增深读 {len(enriched_ids)} 条，覆盖已有 {len(replaced_ids)} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
