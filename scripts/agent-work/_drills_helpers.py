# -*- coding: utf-8 -*-
"""_drills_helpers.py — 模型手撕深度解析生成器的公共构件。

与 _gen_bank_problems.py 的构件同构（teaching/concept/problem/svg_*），但这里
服务的是「模型与训练」赛道：图解以「张量流向 / 结构图 / 对比表」为主，而不是
数组状态快照。产物 research/model_drill_analysis.json 的每个条目形状：

    {"tldr", "why", "teaching", "diagram", "concepts", "problem"}

其中 problem 除沿用题库 problem 块的全部字段外，新增两层（深读通用通道不产出，
由本生成器独有）：

    variants    同一机制的其它实现/变体，每条带自己的代码与适用条件；
    comparison  横向对比表（rows of cells），前端渲染成表格。

SVG 纪律与上一轮完全一致：显式几何 + 内联属性（sanitizeSvg 会剥 <style>/<use>），
viewBox 起始 0 0 680，font-size ≥ 13，文字用 currentColor、强调用 var(--warn)。
"""

ACC = "var(--warn)"
LINE = "var(--line-1)"
OK = "var(--ok)"


def _x(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("'", "&#39;"))


def _svg(inner: str, w: int, h: int, alt: str) -> str:
    return (f"<svg viewBox='0 0 {w} {h}' xmlns='http://www.w3.org/2000/svg' "
            f"role='img' aria-label='{_x(alt)}'>{inner}</svg>")


def diagram(kind, title, caption, alt, svg):
    return {"kind": kind, "title": title, "caption": caption, "alt": alt,
            "svg": svg}


# ---------------------------------------------------------------------------
# 图 1：竖排「张量流」块图 —— 输入(shape) -> [算子] -> 输出(shape)，
#       支持在右侧挂注解。适合 attention/norm/LoRA 这类有明确数据流的题。
# ---------------------------------------------------------------------------
def svg_flow(rows, alt, w=680):
    """rows: [{"label": 算子名, "in": 输入shape, "out": 输出shape, "note": 注解,
               "hot": bool}]"""
    parts, y = [], 14
    bw, bx = 250, 150
    for r in rows:
        hot = r.get("hot")
        parts.append(f"<rect x='{bx}' y='{y}' width='{bw}' height='30' rx='8' "
                     f"fill='none' stroke='{ACC if hot else LINE}' "
                     f"stroke-width='{2.1 if hot else 1.3}'/>")
        parts.append(f"<text x='{bx + bw / 2}' y='{y + 20}' font-size='14' "
                     f"text-anchor='middle' font-weight='bold' "
                     f"fill='currentColor'>{_x(r['label'])}</text>")
        parts.append(f"<text x='{bx - 10}' y='{y + 20}' font-size='13' "
                     f"text-anchor='end' fill='currentColor' "
                     f"opacity='0.8'>{_x(r.get('in') or '')}</text>")
        parts.append(f"<text x='{bx + bw + 10}' y='{y + 20}' font-size='13' "
                     f"fill='currentColor' opacity='0.8'>{_x(r.get('out') or '')}</text>")
        if r.get("note"):
            parts.append(f"<text x='{bx}' y='{y + 46}' font-size='13' "
                         f"opacity='0.72' fill='currentColor'>{_x(r['note'])}</text>")
        y += 58
        if r is not rows[-1]:
            parts.append(f"<line x1='{bx + bw / 2}' y1='{y - 24}' x2='{bx + bw / 2}' "
                         f"y2='{y - 4}' stroke='{LINE}' stroke-width='1.3'/>")
            parts.append(f"<polygon points='{bx + bw / 2 - 4},{y - 10} "
                         f"{bx + bw / 2 + 4},{y - 10} {bx + bw / 2},{y - 3}' "
                         f"fill='{LINE}'/>")
    return _svg("".join(parts), w, y, alt)


# ---------------------------------------------------------------------------
# 图 2：横向对比板 —— 两/三列并排小卡片，各自列要点，底部一行「差异核心」。
#       适合 pre-norm vs post-norm、MHA vs GQA vs MQA 这类结构对比。
# ---------------------------------------------------------------------------
def svg_compare(cols, alt, bottom="", w=680):
    """cols: [{"title", "lines": [..], "hot": bool}]；bottom: 一句差异总结。"""
    parts, y0 = [], 14
    n = len(cols)
    cw = (w - 20 * (n + 1)) // n
    ch = 60 + 24 * max(len(c["lines"]) for c in cols)
    for i, c in enumerate(cols):
        x = 20 + i * (cw + 20)
        hot = c.get("hot")
        parts.append(f"<rect x='{x}' y='{y0}' width='{cw}' height='{ch}' rx='10' "
                     f"fill='none' stroke='{ACC if hot else LINE}' "
                     f"stroke-width='{2.1 if hot else 1.3}'/>")
        parts.append(f"<text x='{x + cw / 2}' y='{y0 + 24}' font-size='14' "
                     f"text-anchor='middle' font-weight='bold' "
                     f"fill='currentColor'>{_x(c['title'])}</text>")
        for j, ln in enumerate(c["lines"]):
            parts.append(f"<text x='{x + 12}' y='{y0 + 50 + j * 24}' font-size='13' "
                         f"fill='currentColor' opacity='0.85'>{_x(ln)}</text>")
    yb = y0 + ch + 34
    if bottom:
        parts.append(f"<text x='{w / 2}' y='{yb}' font-size='13' "
                     f"text-anchor='middle' font-weight='bold' "
                     f"fill='currentColor'>{_x(bottom)}</text>")
        yb += 10
    return _svg("".join(parts), w, yb, alt)


# ---------------------------------------------------------------------------
# 图 3：矩阵网格 —— 行列都有标签，格子可高亮。适合因果掩码 / KV-Cache 分块 /
#       FlashAttention 的 tile 结构。
# ---------------------------------------------------------------------------
def svg_matrix(row_labels, col_labels, cells, alt, w=680, cell=34, hot=None):
    """cells[i][j] 为格子文本；hot 是 {(i, j), ...} 高亮集合。"""
    x0, y0 = 110, 40
    parts = []
    for j, cl in enumerate(col_labels):
        parts.append(f"<text x='{x0 + j * cell + cell / 2}' y='{y0 - 8}' "
                     f"font-size='13' text-anchor='middle' "
                     f"fill='currentColor'>{_x(cl)}</text>")
    for i, rl in enumerate(row_labels):
        y = y0 + i * cell
        parts.append(f"<text x='{x0 - 8}' y='{y + cell / 2 + 5}' font-size='13' "
                     f"text-anchor='end' fill='currentColor'>{_x(rl)}</text>")
        for j in range(len(col_labels)):
            x = x0 + j * cell
            on = (i, j) in (hot or set())
            parts.append(f"<rect x='{x}' y='{y}' width='{cell - 2}' "
                         f"height='{cell - 2}' rx='4' fill='none' "
                         f"stroke='{ACC if on else LINE}' "
                         f"stroke-width='{1.8 if on else 1.0}'/>")
            v = cells[i][j]
            if v:
                parts.append(f"<text x='{x + (cell - 2) / 2}' "
                             f"y='{y + cell / 2 + 4}' font-size='13' "
                             f"text-anchor='middle' fill='currentColor'>{_x(v)}</text>")
    h = y0 + len(row_labels) * cell + 14
    return _svg("".join(parts), w, h, alt)


# ---------------------------------------------------------------------------
# 公共段落构造器（与 _gen_bank_problems.py 同形）
# ---------------------------------------------------------------------------
def teaching(progressive, socratic, mechanism, boundary, analogyBoundary,
             misconceptions, ownAnalysis, officialNotes, interviewAnswer,
             prereq, next_steps):
    """参数名刻意用 JSON 里的 camelCase 键名，避免「写的时候记错映射」。"""
    return {
        "progressive": progressive,
        "socratic": socratic,
        "mechanism": mechanism,
        "boundary": boundary,
        "analogyBoundary": analogyBoundary,
        "misconceptions": misconceptions,
        "ownAnalysis": ownAnalysis,
        "officialNotes": officialNotes,
        "interviewAnswer": interviewAnswer,
        "studyPath": {"prerequisites": prereq, "nextSteps": next_steps},
    }


def lv(level, text):
    return {"level": level, "text": text}


def qa(q, a):
    return {"q": q, "a": a}


def concept(name, readable, analogy, breaks, mech, visual, prereq, self_test,
            formula=""):
    return {
        "name": name, "readable": readable, "analogy": analogy,
        "analogyBreaksDown": breaks, "mechanism": mech, "visual": visual,
        "prerequisites": prereq, "selfTest": self_test, "formula": formula,
    }


def variant(name, idea, code, when, cost=""):
    """variants 条目：同一机制的另一种写法。code 必须可独立 exec。"""
    return {"name": name, "idea": idea, "code": code, "when": when, "cost": cost}


def comparison_row(cells):
    return {"cells": cells}


def problem(statement, idea, steps, python, notes, pitfalls, tips, **kw):
    """题库 problem 块。必填：statement/idea/steps/python/notes/pitfalls/tips；
    可选（kwargs）：whyItWorks, examples, alternatives, time, space, why,
    edgeCases, keyPoints, variants, comparison, interviewScript, pythonAlt。"""
    return {
        "statement": statement,
        "examples": [{"input": i, "output": o, "explanation": e}
                     for i, o, e in (kw.get("examples") or [])],
        "approach": {
            "idea": idea,
            "steps": steps,
            "whyItWorks": kw.get("whyItWorks"),
            "alternatives": [{"name": n, "complexity": c, "when": w}
                             for n, c, w in (kw.get("alternatives") or [])],
        },
        "solution": {"python": python, "python_alt": kw.get("pythonAlt"),
                     "notes": notes},
        "complexity": {"time": kw.get("time"), "space": kw.get("space"),
                       "why": kw.get("why")},
        "keyPoints": kw.get("keyPoints") or [],
        "pitfalls": pitfalls,
        "edgeCases": kw.get("edgeCases") or [],
        "interviewTips": tips,
        # --- 模型赛道独有层 ---
        "variants": kw.get("variants") or [],
        "comparison": kw.get("comparison") or [],
        "interviewScript": kw.get("interviewScript"),
    }


# ---------------------------------------------------------------------------
# 自测架：每个 drill 的 python/variant code 都要 exec 过才算数。
# 「写进库里的那段」= 「跑过的那段」。numpy 在受管 venv 里可用。
# ---------------------------------------------------------------------------
def run_all(drills: dict) -> None:
    import numpy as np  # noqa: F401  (注入到 exec 的名字空间)
    ns_template = {"np": np}
    n_code, n_var = 0, 0
    for key, d in drills.items():
        prob = (d.get("problem") or {})
        code = (prob.get("solution") or {}).get("python")
        if code:
            exec(compile(code, f"<drill:{key}>", "exec"), dict(ns_template))
            n_code += 1
        for v in (prob.get("variants") or []):
            if v.get("code"):
                exec(compile(v["code"], f"<drill:{key}:{v['name']}>", "exec"),
                     dict(ns_template))
                n_var += 1
    print(f"[verify] exec 通过：主实现 {n_code} 段 + 变体 {n_var} 段")
