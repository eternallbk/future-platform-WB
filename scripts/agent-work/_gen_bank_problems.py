#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_gen_bank_problems.py — 生成题库批次的深读产出 out-problems-01.json。

作者工具，不进流水线。它把所有可复用的部分（图解画法、教学层的公共段落结构）收敛成
函数，剩下的逐题内容才是真正需要一条条写的部分。产出交给 apply_agent_out.py 校验后
合并进 enrichment.json，再由 build_problem_bank.py 挂到题目实体上。

约束（与 apply_agent_out.py 的校验一一对应）
  · SVG：必须含 viewBox；不能出现 <style>/<use>/<image>/on* / url(；font-size ≥ 13。
  · diagram 需要 kind/title/caption/alt，kind ∈ flow|architecture|curve|matrix|timeline。
  · teaching 需要 10 个键，progressive ≥ 4 档，mechanism/boundary/analogyBoundary 非空。
  · problem 需要 title/statement/examples/approach/solution/complexity/pitfalls/edgeCases，
    approach 要 idea/steps/whyItWorks/alternatives，complexity 要 time/space/why 且用 O(...)。
  · latex 里 \\text{} 不能有中文（本批不加公式，formulas 留空列表）。
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _solutions import (  # noqa: E402
    SOLUTIONS, QUICK_SORT_ALT, LIS_ALT, MERGE_LISTS_ALT, LEVEL_ORDER_ALT,
    VALID_PAREN_ALT, MERGE_ARRAY_ALT, REVERSE_II_ALT, REORDER_LIST_ALT,
    ADD_STRINGS_ALT, HAS_CYCLE_ALT, DELETE_DUP_II_ALT, REMOVE_NTH_ALT,
    MAX_PATH_SUM_ALT, RESTORE_IP_ALT,
)

OUT = HERE / "out-problems-01.json"

# ===========================================================================
# 图解构造器
#
# 全部用「显式几何 + 内联属性」画：sanitizeSvg 会剥掉 <style>/<use>，所以不能靠
# CSS 类；颜色沿用项目既有约定（--line-1 描边、currentColor 文字、--warn 强调），
# 这样浅色/深色主题都能正常显示。
# ===========================================================================
ACC = "var(--warn)"
LINE = "var(--line-1)"


def _x(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("'", "&#39;"))


def _svg(inner: str, w: int, h: int, alt: str) -> str:
    return (f"<svg viewBox='0 0 {w} {h}' xmlns='http://www.w3.org/2000/svg' "
            f"role='img' aria-label='{_x(alt)}'>{inner}</svg>")


def svg_trace(rows, alt, w=660, cell=46, cw=48):
    """逐行「状态快照」表：每行 = 一轮迭代的数组/字符串状态 + 一句注解。

    适合展示「循环不变量」——分区、进位、tails 数组、切分点都属于这一类。
    """
    parts, y = [], 16
    for r in rows:
        parts.append(f"<text x='10' y='{y + 18}' font-size='13' font-weight='bold' "
                     f"fill='currentColor'>{_x(r['label'])}</text>")
        cx = 122
        for i, c in enumerate(r.get("cells") or []):
            if c is None:
                cx += cw
                continue
            hi = i in (r.get("hi") or [])
            parts.append(f"<rect x='{cx}' y='{y + 2}' width='{cell}' height='26' rx='6' "
                         f"fill='none' stroke='{ACC if hi else LINE}' "
                         f"stroke-width='{2.0 if hi else 1.2}'/>")
            parts.append(f"<text x='{cx + cell / 2:.0f}' y='{y + 20}' font-size='14' "
                         f"text-anchor='middle' fill='currentColor'>{_x(c)}</text>")
            cx += cw
        if r.get("note"):
            parts.append(f"<text x='122' y='{y + 45}' font-size='13' opacity='0.72' "
                         f"fill='currentColor'>{_x(r['note'])}</text>")
        y += 60
    return _svg("".join(parts), w, y + 4, alt)


def svg_chain(nodes, alt, marks=None, w=660, box=62, gap=30):
    """链表：结点方框 + 箭头，第二行放指针标记（pre / cur / next）。"""
    parts, x, y0 = [], 20, 30
    for i, n in enumerate(nodes):
        parts.append(f"<rect x='{x}' y='{y0}' width='{box}' height='34' rx='8' "
                     f"fill='none' stroke='{LINE}' stroke-width='1.3'/>")
        parts.append(f"<text x='{x + box / 2:.0f}' y='{y0 + 22}' font-size='14' "
                     f"text-anchor='middle' fill='currentColor'>{_x(n)}</text>")
        x += box
        if i < len(nodes) - 1:
            parts.append(f"<line x1='{x}' y1='{y0 + 17}' x2='{x + gap - 10}' y2='{y0 + 17}' "
                         f"stroke='{LINE}' stroke-width='1.4'/>")
            parts.append(f"<polygon points='{x + gap - 2},{y0 + 17} {x + gap - 10},{y0 + 13} "
                         f"{x + gap - 10},{y0 + 21}' fill='{LINE}'/>")
            x += gap
    parts.append(f"<text x='{x + 6}' y='{y0 + 22}' font-size='14' opacity='0.7' "
                 f"fill='currentColor'>NULL</text>")
    for idx, label in (marks or []):
        cx = 20 + idx * (box + gap)
        parts.append(f"<line x1='{cx + box / 2:.0f}' y1='{y0 + 34}' x2='{cx + box / 2:.0f}' "
                     f"y2='{y0 + 44}' stroke='{ACC}' stroke-width='1.6'/>")
        parts.append(f"<text x='{cx + box / 2:.0f}' y='{y0 + 60}' font-size='13' "
                     f"text-anchor='middle' font-weight='bold' fill='currentColor'>"
                     f"{_x(label)}</text>")
    return _svg("".join(parts), w, y0 + 78, alt)


def svg_tree(levels, alt, hi=(), w=660, r=19, dy=72):
    """二叉树：levels 是按深度给的槽位列表（缺失写 None），坐标按槽位均匀分布。"""
    parts = []
    for d, lv in enumerate(levels):
        y = 30 + d * dy
        step = w / (len(lv) + 1)
        for i, v in enumerate(lv):
            if v is None:
                continue
            cx = step * (i + 1)
            if d + 1 < len(levels):
                nxt, step2 = levels[d + 1], w / (len(levels[d + 1]) + 1)
                for ci in (2 * i, 2 * i + 1):
                    if ci < len(nxt) and nxt[ci] is not None:
                        parts.append(f"<line x1='{cx:.0f}' y1='{y + r}' x2='{step2 * (ci + 1):.0f}' "
                                     f"y2='{y + dy - r}' stroke='{LINE}' stroke-width='1.2'/>")
        for i, v in enumerate(lv):
            if v is None:
                continue
            cx = step * (i + 1)
            hot = (d, i) in hi
            parts.append(f"<circle cx='{cx:.0f}' cy='{y}' r='{r}' fill='none' "
                         f"stroke='{ACC if hot else LINE}' stroke-width='{2.2 if hot else 1.5}'/>")
            parts.append(f"<text x='{cx:.0f}' y='{y + 5}' font-size='14' text-anchor='middle' "
                         f"fill='currentColor'>{_x(v)}</text>")
    return _svg("".join(parts), w, 30 + len(levels) * dy + 8, alt)


# ===========================================================================
# 公共段落：这些内容对「刷题」这件事是共通的，逐题重复写只会稀释注意力。
# 每题只需要给出自己的具体版本。
# ===========================================================================
def teaching(progressive, socratic, mechanism, boundary, analogyBoundary,
             misconceptions, ownAnalysis, officialNotes, interviewAnswer,
             prereq, next_steps):
    """参数名刻意用 JSON 里的 camelCase 键名，避免「写的时候记错映射」这一类低级错。"""
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


_ALIAS = {
    "why_it_works": "whyItWorks", "whyItWorks": "whyItWorks",
    "edge_cases": "edgeCases", "edgeCases": "edgeCases",
    "time_c": "time", "time": "time",
    "space_c": "space", "space": "space",
    "why_c": "why", "why": "why",
}


def _take(kw: dict, key: str):
    """按 _ALIAS 的多种拼法取一个必填项，取不到就带着字段名报错。

    这样写 `problem(edge_cases=[...])` 和 `problem(edgeCases=[...])` 都能跑，
    避免因为记错一种拼法而整批生成失败。
    """
    for alias, target in _ALIAS.items():
        if target == key and alias in kw:
            return kw.pop(alias)
    raise TypeError(f"problem() 缺少字段 {key}（可用拼法："
                    f"{[a for a, t in _ALIAS.items() if t == key]}")


def problem(title, statement, examples, idea, steps, alternatives,
            python, python_alt, notes, pitfalls, tips, **kw):
    extra = set(kw) - set(_ALIAS)
    if extra:
        raise TypeError(f"problem() 收到未知字段：{sorted(extra)}")
    return {
        "title": title,
        "statement": statement,
        "examples": [{"input": i, "output": o, "explanation": e} for i, o, e in examples],
        "approach": {
            "idea": idea,
            "steps": steps,
            "whyItWorks": _take(kw, "whyItWorks"),
            "alternatives": [{"name": n, "complexity": c, "when": w} for n, c, w in alternatives],
        },
        "solution": {"python": python, "python_alt": python_alt, "notes": notes},
        "complexity": {"time": _take(kw, "time"), "space": _take(kw, "space"),
                       "why": _take(kw, "why")},
        "pitfalls": pitfalls,
        "edgeCases": _take(kw, "edgeCases"),
        "interviewTips": tips,
    }


# ===========================================================================
# 逐题内容（按 CodeTop 被考频度降序：264 → 60）
# ===========================================================================
CONTENT: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# 1. 手撕快速排序（freq 264）
# ---------------------------------------------------------------------------
CONTENT["1ce9f0a6715ffa8f"] = {
    "tldr": "快排的全部难点在分区函数：用「挖坑 + 填坑」把 pivot 归位，再递归左右两半；"
            "基准随机化是防止已排序输入退化成 O(n²) 的唯一廉价手段。",
    "why": "它是面试里最常见的「手写排序」，考的不是排序本身，而是你能不能说清"
           "「为什么平均 O(n log n)、最坏什么时候变 O(n²)、怎么避免」。"
           "同一套分区思想还直接复用在「数组中的第 K 个最大元素」和「荷兰国旗」上。",
    "difficulty": "medium",
    "tags": ["sorting", "quicksort", "partition", "divide-and-conquer", "手撕"],
    "entities": ["Hoare 划分", "Lomuto 划分", "三数取中", "荷兰国旗问题"],
    "diagram": {
        "kind": "flow",
        "title": "快排分区的「挖坑填坑」一轮走完",
        "caption": "以 [3,1,4,1,5] 为例：基准取 3，右指针先找比基准小的填左坑，"
                   "左指针再找比基准大的填右坑，两指针相遇的位置就是基准的最终位置。",
        "alt": "快排一轮分区的四步状态：初始数组、右指针填坑、左指针填坑、基准归位",
        "svg": svg_trace(
            [
                {"label": "初始", "cells": ["3", "1", "4", "1", "5"], "hi": [0],
                 "note": "pivot = 3（已交换到 lo），i = 0，j = 4"},
                {"label": "① 右往左", "cells": ["3", "1", "4", "1", "5"], "hi": [4, 0],
                 "note": "nums[4]=5 ≥ 3 不是目标；nums[3]=1 < 3 → 填进左坑，i = 0"},
                {"label": "② 左往右", "cells": ["1", "1", "4", "1", "5"], "hi": [1, 2],
                 "note": "nums[1]=1 ≤ 3 继续；nums[2]=4 > 3 → 填进右坑，j = 3"},
                {"label": "③ 相遇", "cells": ["1", "1", "4", "4", "5"], "hi": [2],
                 "note": "i == j == 2，把 pivot 写回 nums[2]"},
                {"label": "结果", "cells": ["1", "1", "3", "4", "5"], "hi": [2],
                 "note": "左边全 ≤ 3，右边全 ≥ 3；再对 [0,1] 和 [3,4] 递归"},
            ],
            "快速排序挖坑法单轮分区的状态变化"),
    },
    "concepts": [concept(
        "分区的循环不变量",
        "分区过程中数组被两个指针切成三段：左边已经确定 ≤ pivot、右边已经确定 ≥ pivot、"
        "中间是还没看的「坑区」。",
        "像整理一摞卡片：你手里拿着一张基准卡，从两头往中间收，比它小的往左扔、"
        "比它大的往右扔，最后中间空出来的那个位置天然就是基准该在的位置。",
        "「左边 ≤ pivot」指的是**已经处理过的**部分，不是整个左半区——分区没结束时，"
        "左半区里还夹着没比较过的元素，把它当成有序会推出错误的终止条件。",
        "i 从左往右找「≤ pivot 就该留在左边」的元素，j 从右往左找「≥ pivot 就该留在右边」"
        "的元素；每找到一个就把它的值写到对方的坑里，于是坑交替转移，i、j 相遇时坑正好"
        "落在基准的最终下标上。",
        "把数组画成一条格子带，i、j 两个箭头从两端相向移动，坑的位置用空心格标出；"
        "每轮把箭头和坑的位置画一格，五格就能看完一轮。",
        ["数组下标与两指针不变式", "递归与递归基", "比较类排序的下界"],
        ["i 和 j 相遇时为什么不需要再比较 nums[i] 与 pivot？",
         "如果所有元素都比 pivot 大，第一轮分区后 pivot 会落在哪个下标？",
         "把 nums[j] >= pivot 改成 > pivot 会怎样？"],
    )],
    "formulas": [],
    "selfCheck": {
        "claims": [
            "挖坑法一轮分区后，pivot 落在它的最终有序位置上。",
            "随机选基准后，已排序 / 逆序输入不再触发最坏 O(n²)。",
            "分区是原地操作，额外空间只来自递归栈（平均 O(log n)）。",
        ],
        "uncertain": [
            "递归栈深度在「每次基准都取到极值」时是 O(n)，面试若被追问需要答出"
            "「可以用尾递归消除较小一侧的递归」或「改用三路划分 + 显式栈」。",
        ],
    },
    "teaching": teaching(
        progressive=[
            lv("第 1 层 · 能背", "写出一个能跑的快排：选基准、分区、递归左右两半。"),
            lv("第 2 层 · 能说清", "说清分区后「基准已在最终位置」这条不变量，"
                                  "以及为什么递归的两半不包含基准本身。"),
            lv("第 3 层 · 能推复杂度", "推出平均 O(n log n)：每层分区总代价 O(n)，"
                                      "期望递归深度 O(log n)。并说出最坏 O(n²) 的触发条件"
                                      "（每次取到极值）与随机化为什么能打散它。"),
            lv("第 4 层 · 能权衡", "比较挖坑法 / Hoare 划分 / 三路划分的交换次数与"
                                  "重复元素表现，并说出「数组中的第 K 个」为什么只递归一侧"
                                  "就能到 O(n)。"),
        ],
        socratic=[
            qa("分区结束后，基准左边的元素一定全都比它小吗？",
               "不一定，是 ≤ —— 重复元素会落在左边。这正是快排在重复元素非常多时"
               "退化成 O(n²) 的原因，也是三路划分（< / = / >）存在的理由。"),
            qa("为什么随机选基准能避免最坏情况？",
               "最坏情况要求每一层都切出 0 : n-1 的极端分裂，这需要基准几乎每次都是极值。"
               "随机化让「连续每层都抽到极值」的概率降到可以忽略，期望深度变成 O(log n)。"
               "注意：它只降低概率，不改变最坏上界。"),
            qa("快排比归并排序快在哪里？",
               "常数因子。快排的分区是原地顺序扫描，缓存友好；归并需要额外数组和反复拷贝。"
               "但归并是稳定排序而且最坏 O(n log n)，所以要求稳定或最坏保证时该选归并。"),
        ],
        mechanism="分区函数用「挖坑填坑」把比较与写入合二为一：j 从右往左扫到第一个小于"
                  "基准的元素，立刻把它写进左边的坑（i 位置），坑转移到 j；i 再从左往右"
                  "扫到第一个大于基准的元素，写进 j 位置的坑，坑回到左边。任一时刻数组里"
                  "只有一个坑，所以写入永远不会覆盖还没被读过的元素，这就是它能原地工作的原因。",
        boundary="适合：数组、需要原地、内存受限、只需要「平均快」。不适合：要求稳定排序"
                 "（用归并）、要求最坏 O(n log n) 保证（用归并/堆排）、链表（分区要随机访问，"
                 "链表的「快排」通常是另一套指针玩法，实际更常用归并）。",
        analogyBoundary="「整理卡片」的类比会让人以为每张卡片只被移动一次 —— 实际挖坑法里"
                        "元素常常被搬两次（填坑一次、再被填回一次）。只按「移动次数」估代价"
                        "会把交换次数算少一半左右。",
        misconceptions=[
            "「随机基准 = 最坏情况消失」——错。它只把最坏情况的概率压到极低，"
            "渐进最坏上界仍是 O(n²)。",
            "「分区后左边严格小于基准」——错，重复元素会落在左边（≤）。"
            "这就是重复元素多时退化的原因。",
            "「快排是稳定排序」——错，跨位置的写入与交换会打乱相等元素的相对顺序。",
            "「递归两半要包含基准下标」——错，基准已经在最终位置，再包含进去会导致"
            "区间不收缩而死循环。",
        ],
        ownAnalysis="真正值得记的是「只递归一侧就能做 Top-K」这一步：找第 K 大不需要全排序，"
                    "分区后如果基准下标正好是 K 就返回，否则只递归包含 K 的那一侧，"
                    "期望时间从 O(n log n) 降到 O(n)（n + n/2 + n/4 + … 收敛到 2n）。"
                    "面试里把「快排」和「快速选择」连着讲出来，是明显的加分项。",
        officialNotes=[
            {"position": "比较排序的下界是 Ω(n log n)，快排只在这个意义上「平均最优」，"
                         "并不优于归并的理论上界。",
             "source": "算法导论 · 第 8 章排序下界"},
            {"position": "CPython 的 list.sort 用的是 Timsort（归并/插入混合、稳定），"
                         "而不是快排——因为工业实现更看重稳定与最坏表现。",
             "source": "Python 官方文档 · sorting"},
        ],
        interviewAnswer="先一句话给结论：快排是「选基准 → 分区 → 递归」，核心是分区后基准"
                         "落在最终位置。然后立刻手写分区（挖坑法），边写边报不变量。写完主动"
                         "说三点：平均 O(n log n)、最坏 O(n²) 及其触发条件、随机化如何避免。"
                         "如果面试官继续追问，再补「只递归一侧就是 O(n) 找第 K 大」。",
        prereq=["递归与分治", "数组原地交换", "期望值的线性可加性", "大 O 记号"],
        next_steps=["实现「数组中的第 K 个最大元素」并分析为什么是期望 O(n)",
                    "实现三路划分（荷兰国旗），对比重复元素下的表现",
                    "对比归并排序：稳定性与最坏保证的取舍"],
    ),
    "problem": problem(
        title="手撕快速排序",
        statement="给定一个整数数组，用快速排序把它升序排列。要求原地排序（不允许开辟与 n 同阶的"
                  "额外数组），并说明平均与最坏复杂度。面试常追加两问：如何避免最坏情况？"
                  "如果要找第 K 大元素，能不能不做完整排序？",
        examples=[
            ("nums = [3,1,4,1,5]", "[1,1,3,4,5]", "重复元素 1 都保留，快排本身不稳定但数值有序"),
            ("nums = [5,4,3,2,1]", "[1,2,3,4,5]", "完全逆序；若基准固定取左端会退化成 O(n²)，"
                                                  "随机化后仍接近 O(n log n)"),
            ("nums = []", "[]", "空数组直接返回，递归基必须覆盖 lo >= hi"),
        ],
        idea="把「排序 n 个数」拆成「把基准放到最终位置」+「排序左右两段」。"
             "分区用挖坑法：先随机选一个基准并换到 lo（避免有序输入退化），"
             "然后 i、j 从两端相向扫，各自把不合位置的元素写到对方的坑里；"
             "两指针相遇处就是基准的最终下标，最后把基准写回该处。",
        steps=[
            "随机取 k ∈ [lo, hi]，交换 nums[lo] 与 nums[k]，令 pivot = nums[lo]、i = lo、j = hi。",
            "j 从右往左找第一个 nums[j] < pivot，把它写入 nums[i]（填左坑）。",
            "i 从左往右找第一个 nums[i] > pivot，把它写入 nums[j]（填右坑）。",
            "重复 2–3 直到 i == j，此时把 pivot 写入 nums[i]，分区结束。",
            "对 [lo, i-1] 与 [i+1, hi] 递归；区间长度 ≤ 1 时停止。",
        ],
        why_it_works="不变量是「任一时刻数组里只有一个坑，坑里的值已经安全地保存到别处」。"
                     "因此每次写入都不会覆盖尚未读取的元素。i、j 相遇时，相遇点左侧已验证 ≤ pivot、"
                     "右侧已验证 ≥ pivot，所以把 pivot 放到相遇点，左侧全部 ≤ 它、右侧全部 ≥ 它，"
                     "该位置就是它的最终有序位置 —— 之后无需再参与排序。",
        alternatives=[
            ("Hoare 划分 + 三数取中", "O(n log n) 平均 / O(1) 额外空间",
             "交换次数更少（约为挖坑法的一半），且三数取中比随机化更便宜；"
             "但划分返回的下标是「分界」而不是基准位置，递归区间写法不同，容易写错。"),
            ("三路划分（荷兰国旗）", "O(n log n) 平均，重复元素多时退化到 O(n)",
             "数组里重复值很多时首选：一次分区把元素分成 < / = / > 三段，等于段直接跳过，"
             "彻底消除「重复元素导致的退化」。"),
            ("归并排序", "O(n log n) 最坏 / O(n) 额外空间",
             "要求稳定排序、或要求最坏 O(n log n) 保证时用；链表排序也优先选它。"),
            ("堆排序", "O(n log n) 最坏 / O(1) 额外空间",
             "只要最坏保证且不在乎常数、也不需要稳定性时用；实际比快排慢一个常数因子。"),
        ],
        python=SOLUTIONS["1ce9f0a6715ffa8f"][1],
        python_alt=QUICK_SORT_ALT,
        notes="写进库里的这段是**实际跑过并断言通过**的版本：随机基准 + 挖坑法分区，"
              "在空数组、单元素、全等、已排序、逆序五个用例上都验证过。"
              "面试时建议先写这段（不容易错），有时间再补 Hoare 版。",
        time_c="O(n log n) 平均，O(n²) 最坏",
        space_c="O(log n) 平均，O(n) 最坏（递归栈）",
        why_c="每层分区总代价 O(n)；随机基准下期望递归深度 O(log n)，故平均 O(n log n)。"
              "最坏情况是每层都切出 0 : n-1 的极端分裂，深度 n、总代价 O(n²)。"
              "空间只来自递归栈：在递归前先对较短的一侧递归、较长的一侧用循环处理，"
              "可以把栈深压到 O(log n) 最坏。",
        pitfalls=[
            "基准固定取 nums[lo]：输入已排序或逆序时每次分裂都极端，退化成 O(n²) 并可能爆栈。",
            "内外层比较符号写反（外层用 <、内层用 ≤）：结果是死循环或分区越界，"
            "而且在小用例上往往看不出来。",
            "递归区间写成 [lo, i] 而不是 [lo, i-1]：区间不收缩，直接栈溢出。",
            "漏掉 i == j 的终止判断：两指针会互相越过，把已填好的坑再覆盖掉。",
            "以为快排稳定：相等元素会被跨位置交换打乱顺序。",
        ],
        edge_cases=[
            "空数组 / 单元素：递归基 lo >= hi 必须最先判断。",
            "全是相同元素：挖坑法会退化成每层只切掉一个元素，应当用三路划分。",
            "已排序、逆序：随机化基准的直接目标场景。",
            "只有两个元素且相等：验证 <= 与 >= 的取舍不会造成死循环。",
            "含负数与极值：比较逻辑与符号无关，用来验证没有把值当真值判断。",
        ],
        tips="被问「快排为什么快」时不要只说「分治」——要说常数因子和缓存友好性。"
             "被问「怎么找第 K 大」时，直接说「只递归包含 K 的那一侧，期望 O(n)」，"
             "并写出 n + n/2 + n/4 + … < 2n 的收敛过程。"
             "如果面试官问「工程里为什么不用快排」，答案是 CPython 用 Timsort（稳定）、"
             "C++ std::sort 是内省排序（快排 + 堆排兜底最坏 + 小区间插排）。",
    ),
}

# ---------------------------------------------------------------------------
# 2. 最长上升子序列 LeetCode 300（freq 223）
# ---------------------------------------------------------------------------
CONTENT["541b3f61c94a86a7"] = {
    "tldr": "O(n²) 的 dp 是「以 i 结尾」，O(n log n) 的贪心是「长度为 k 的最小结尾」；"
            "两者不是同一个状态的优化，而是换了一个状态定义，这一步换位才是本题考点。",
    "why": "它是「同一个问题、两套状态定义」的最佳教材。面试官几乎必问「能不能更快」，"
           "答不上 O(n log n) 就只有一半分；而 tails 数组的「替换而不是删除」"
           "恰恰是很多人写错的地方。它同时是 LIS 家族（俄罗斯套娃信封、最长数对链）的模板。",
    "difficulty": "medium",
    "tags": ["dynamic-programming", "binary-search", "greedy", "lis", "面试高频"],
    "entities": ["patience sorting", "tails 数组", "bisect_left", "Dilworth 定理"],
    "diagram": {
        "kind": "flow",
        "title": "tails 数组的维护过程（nums = [10,9,2,5,3,7,101,18]）",
        "caption": "每读一个数 x：在 tails 里二分找第一个 ≥ x 的位置。找到就替换（把该长度的"
                   "结尾改小，给后续元素留更多余地），没找到就追加（最长长度 +1）。"
                   "最终答案 = tails 的长度 = 4。关键是 tails 本身并不是某条真实子序列。",
        "alt": "LIS 的 tails 数组在八个输入上的逐步变化，最终长度为 4",
        "svg": svg_trace(
            [
                {"label": "10", "cells": ["10"], "hi": [0], "note": "tails 为空 → 追加"},
                {"label": "9", "cells": ["9"], "hi": [0],
                 "note": "第一个 ≥ 9 的位置是下标 0 → 用 9 替换 10"},
                {"label": "2", "cells": ["2"], "hi": [0], "note": "替换下标 0"},
                {"label": "5", "cells": ["2", "5"], "hi": [1], "note": "没有 ≥ 5 的 → 追加，长度 2"},
                {"label": "3", "cells": ["2", "3"], "hi": [1], "note": "第一个 ≥ 3 是下标 1 → 替换 5"},
                {"label": "7", "cells": ["2", "3", "7"], "hi": [2], "note": "追加，长度 3"},
                {"label": "101", "cells": ["2", "3", "7", "101"], "hi": [3], "note": "追加，长度 4"},
                {"label": "18", "cells": ["2", "3", "7", "18"], "hi": [3],
                 "note": "下标 3 的 101 被替换成 18 → 长度仍是 4"},
            ],
            "LIS 的 tails 数组逐步维护过程"),
    },
    "concepts": [concept(
        "tails[k] 的语义",
        "tails[k] 是「所有长度为 k+1 的上升子序列里，结尾最小的那个值」。"
        "它是长度信息，不是一条具体子序列的还原路径。",
        "像给不同长度的队伍记录「最矮的收尾队员」：队伍越长越难接人，所以你要让每个长度的"
        "末尾尽量矮，后面来的人才接得上。",
        "最诱人的误用是「tails 就是答案子序列」——完全不是。上面的例子里最终 tails = [2,3,7,18]，"
        "但真实的一条 LIS 是 [2,3,7,101] 或 [2,5,7,101]。要还原具体子序列必须另开"
        "前驱数组 + 记录每个元素进入时的长度，这也是「输出 LIS」与「求 LIS 长度」难度差一截的原因。",
        "tails 数组天然严格递增（长度为 k+1 的最小结尾必然大于长度为 k 的最小结尾，"
        "否则后者能接上前者），因此可以二分。替换 tails[i] = x 之所以正确，是因为"
        "「以 x 结尾、长度 i+1 的子序列」比原来那条结尾更小，严格更优，"
        "既不影响已有长度，又为后续元素放宽了条件。",
        "把每个长度画成一行，行里只显示当前最小结尾；输入元素像小球一样落下，"
        "落在「第一个比自己大的行」上并把它压下去。动画一次落一颗，八颗看完。",
        ["动态规划的状态定义", "二分查找（lower_bound）", "贪心的交换论证"],
        ["为什么 tails 一定严格递增？（提示：反证）",
         "把 bisect_left 换成 bisect_right 会得到什么？答案是「最长非降子序列」。",
         "本题只要求长度；如果要求输出一条具体的 LIS，需要额外维护什么？"],
    )],
    "formulas": [],
    "selfCheck": {
        "claims": [
            "O(n log n) 解的关键是 tails 数组严格递增，因此可以二分。",
            "返回值是 len(tails)，不是 max(tails) 也不是 sum。",
            "O(n²) 与 O(n log n) 两种实现在全部边界用例上结果一致（已交叉验证）。",
        ],
        "uncertain": [
            "粗粒度符号比较（如「最长递增子序列」与「最长不下降子序列」的区别）在中文语境里"
            "有时混用，需要看题目是否允许相等。",
        ],
    },
    "teaching": teaching(
        progressive=[
            lv("第 1 层 · 能写", "写出 O(n²)：dp[i] = 以 nums[i] 结尾的 LIS 长度，"
                                "答案为 max(dp)。"),
            lv("第 2 层 · 能解释", "解释「以 i 结尾」这个状态定义的必要性："
                                  "只有固定结尾才能 O(1) 地判断能否接上。"),
            lv("第 3 层 · 能优化", "说出 O(n log n)：换成 tails 状态，靠二分在 O(log n) 内"
                                  "定位替换 / 追加的位置。"),
            lv("第 4 层 · 能说边界", "说清 tails 不是子序列、替换为什么安全、"
                                    "以及要还原路径需要加什么。"),
        ],
        socratic=[
            qa("dp[i] 为什么必须定义成「以 nums[i] 结尾」而不是「前 i 个数的最长」？",
               "因为「前 i 个的最长」无法 O(1) 判断 nums[i] 能不能接上——你不知道那条最长链的"
               "结尾是多少。把结尾固定在 i，状态才含有可比较的信息。"),
            qa("为什么把 tails[i] 换成更小的值不会「破坏」已经算出的长度？",
               "因为我们只关心长度和「该长度的最优结尾」。结尾变小意味着这条链更容易被接续，"
               "严格优于原状态，不会让任何已成立的结论失效。"),
            qa("为什么最终 tails 的长度是 4，但 tails 的最后一个元素是 18？",
               "18 是「长度 4 的上升子序列的最小结尾」，而 [2,3,7,101] 那条链的结尾是 101。"
               "tails 记录的是每个长度的最优收尾，不是某一条链。"),
        ],
        mechanism="读入 x 时，在 tails 中二分定位第一个 ≥ x 的下标 i：若 i == len(tails)，"
                  "说明 x 比所有「各长度的最小结尾」都大，于是存在一条长度 len+1 的上升子序列，"
                  "追加；否则把 tails[i] 改成 x —— 即「长度 i+1 取得了更小的结尾」。"
                  "两种情况都只修改一个位置，所以单步 O(log n)、总计 O(n log n)。",
        boundary="严格递增（<）：用 bisect_left。允许相等（≤，即不下降）：用 bisect_right。"
                 "二维问题（俄罗斯套娃信封）需要先按一维排序、另一维降序再套用本算法，"
                 "排序方向搞错是这类题最常见的错。",
        analogyBoundary="「最矮收尾的队伍」这个类比会导致「用 tails 还原子序列」的错误直觉 ——"
                        "因为被替换掉的那些结尾曾被写入数组，直觉上像是「曾经存在过」，"
                        "但数组里留不下历史。还原必须另存前驱，类比不提供这条信息。",
        misconceptions=[
            "「tails 就是一条 LIS」——错，它是每个长度的最小结尾，元素可能来自不同的链。",
            "「答案可以取 max(tails) 或 tails[-1]」——错，答案是 len(tails)。"
            "tails[-1] 只是最后一个长度的最小结尾。",
            "「O(n log n) 只是把内层循环换成了二分」——不是，它是换了一个状态定义；"
            "把 O(n²) 的 dp 内层直接二分是错的。",
            "「替换时要检查 x 是否大于前一个」——不需要，tails 严格递增保证了定位即合法。",
        ],
        ownAnalysis="把这道题和「俄罗斯套娃信封」放在一起看，会发现 LIS 是一种可复用的" 
                    "**降维工具**：只要能把二维偏序问题按一维排序、在另一维上求 LIS，"
                    "就能在 O(n log n) 内解掉。所以这道题的真实价值不是「背下 tails」，"
                    "而是「认出哪类问题可以降成 LIS」。",
        officialNotes=[
            {"position": "该算法等价于 patience sorting，tails 的长度等于最少需要的牌堆数；"
                         "由 Dilworth 定理，这也等于最长递减子序列的长度。",
             "source": "算法导论 · 动态规划 / patience sorting"},
            {"position": "Python 的 bisect_left 返回「第一个 ≥ x」的下标，"
                         "正是本题需要的 lower_bound 语义；bisect_right 则是 upper_bound。",
             "source": "Python 官方文档 · bisect"},
        ],
        interviewAnswer="先说 O(n²) 并写出来（30 秒，体现定义能力），再主动说「可以优化到"
                         "O(n log n)，但要换状态：不再以元素结尾，而是维护每个长度的最小结尾」。"
                         "写 O(n log n) 时明确讲出「替换 vs 追加」两个分支和 bisect_left 的语义。"
                         "最后补一句「注意 tails 本身不是子序列」，这一句往往能直接终结追问。",
        prereq=["动态规划基本框架", "二分查找 lower_bound", "序列与子序列（不要求连续）的区别"],
        next_steps=["做「俄罗斯套娃信封」体会排序 + LIS 的降维套路",
                    "做「最长数对链」并对比与 LIS 的状态差异",
                    "练习「输出具体 LIS」（前驱数组），理解长度与路径的区别"],
    ),
    "problem": problem(
        title="最长上升子序列（LeetCode 300）",
        statement="给定整数数组 nums，找到其中最长严格递增子序列的长度。子序列由数组删除"
                  "（或不删除）元素而不改变其余元素顺序得到，不要求连续。"
                  "进阶要求：把复杂度从 O(n²) 优化到 O(n log n)。",
        examples=[
            ("nums = [10,9,2,5,3,7,101,18]", "4",
             "最长上升子序列之一是 [2,3,7,101]，长度 4；注意 2、3 在 9、10 之后，"
             "子序列不要求连续"),
            ("nums = [0,1,0,3,2,3]", "4", "[0,1,2,3] 或 [0,1,2,3]（取第二个 3），长度 4"),
            ("nums = [7,7,7,7]", "1", "严格递增，相等不能接续，只能取一个"),
        ],
        idea="换状态定义。O(n²) 用 dp[i] = 以 nums[i] 结尾的 LIS 长度（结尾固定才能 O(1) 判断接续）；"
             "O(n log n) 用 tails[k] = 所有长度为 k+1 的上升子序列中结尾的最小值。"
             "读入 x 时二分找到 tails 里第一个 ≥ x 的位置：不存在就追加（长度 +1），"
             "存在就把该位置改成 x（该长度取得更优结尾）。",
        steps=[
            "初始化 tails = []。",
            "对每个 x ∈ nums：用二分求 i = 第一个满足 tails[i] ≥ x 的下标。",
            "若 i == len(tails)：追加 x（说明出现了更长的上升子序列）。",
            "否则令 tails[i] = x（把长度 i+1 的结尾改小）。",
            "遍历结束后返回 len(tails)。",
        ],
        whyItWorks="tails 严格递增：若 tails[k] ≥ tails[k+1]，则长度为 k+2 的那条链去掉末尾元素"
                   "会得到一条结尾 ≤ tails[k+1] 的长度 k+1 的子序列，与 tails[k+1] 是" 
                   "「最小结尾」矛盾。因此二分定位合法。替换之所以安全，是因为它只把某个长度的"
                   "最优结尾改小，不放宽任何已成立的结论，却让后续元素更容易接上——"
                   "这保证了长度信息单调不减、最终结果正确。",
        alternatives=[
            ("O(n²) DP", "O(n²) 时间 / O(n) 空间",
             "n ≤ 2500 的规模、或面试开场先给定义时用。逻辑直白，不容易写错。"),
            ("tails + bisect_right", "O(n log n) 时间 / O(n) 空间",
             "题目变成「非降子序列」（允许相等）时用；把严格递增的判据放宽一格。"),
            ("树状数组 / 线段树求前缀最大", "O(n log n) 时间 / O(n) 空间",
             "需要在「值域」上做前缀最大、或要同时处理二维偏序时用；"
             "比 tails 更通用，但代码长得多。"),
            ("还原具体子序列（前驱数组）", "O(n log n) 时间 / O(n) 空间",
             "题目要求输出路径而不只是长度时；额外维护 pos[i] 记录每个元素进入 tails 时的"
             "长度，再回溯即可。"),
        ],
        python=SOLUTIONS["541b3f61c94a86a7"][1],
        python_alt=LIS_ALT,
        notes="两个版本都跑过并互相验证（O(n log n) 与 O(n²) 在 6 组用例上结果一致），"
              "包括空数组、全等数组、纯上升、纯下降。bisect_left 的语义是「第一个 ≥ x」，"
              "正好对应本题；换成 bisect_right 会变成非降子序列。",
        time_c="O(n log n)",
        space_c="O(n)",
        why_c="外层遍历 n 次；每次在 tails 上二分，tails 长度最多 n，故单次 O(log n)，"
              "合计 O(n log n)。空间是 tails 数组本身，最坏 O(n)。"
              "注意「替换不增加长度」并不影响总复杂度——总追加次数 ≤ n。",
        pitfalls=[
            "把答案写成 tails[-1] 或 max(tails)：正确答案是 len(tails)。",
            "以为 tails 就是一条合法子序列，用它回答「输出该子序列」——会给出非子序列的结果。",
            "用 bisect_right 处理严格递增：会把相等元素接上去，答案偏大（变成非降）。",
            "只写 O(n²) 就收工：本题几乎必被追问 O(n log n)。",
            "内层循环写成 for j in range(i) 却用 dp[i] = max(dp[j]) 忘记 +1。",
        ],
        edge_cases=[
            "空数组：返回 0（tails 长度为 0）。",
            "单元素：返回 1。",
            "全部相等：[7,7,7] → 1，验证严格递增的判据。",
            "完全逆序：[5,4,3] → 1；完全顺序：[1,2,3] → n（追加 n 次）。",
            "大规模 n = 250000：只有 O(n log n) 版本能过，用来暴露 O(n²) 的性能问题。",
        ],
        tips="开场先给 O(n²) 的定义解法，再主动说「可以优化」——面试官往往就是在等这句。"
             "讲 O(n log n) 时把重点放在「状态定义换成了什么」，而不是「我把内层换成了二分」。"
             "主动说一句「tails 不是子序列」能省掉一个高频追问。"
             "如果被问「怎么输出具体路径」，答「另存前驱数组，按长度回溯」即可。",
    ),
}

# ---------------------------------------------------------------------------
# 3. 合并两个有序链表 LeetCode 21（freq 202）
# ---------------------------------------------------------------------------
CONTENT["034602d65c3c3d83"] = {
    "tldr": "哑结点 + 尾插：谁小接谁，最后把没走完的那条整段挂上（不是逐个复制），"
            "O(m+n) 时间、O(1) 额外空间。递归版只有 5 行但会把栈深变成链表长度。",
    "why": "哑结点是链表题的通用起手式，这道题是它最干净的示范。它同时是"
           "「排序链表（归并）」和「合并 K 个有序链表」两块题目的基础件——"
           "前者用归并、后者用堆，都建立在本题之上。面试里考的是边界处理，"
           "不是算法本身。",
    "difficulty": "easy",
    "tags": ["linked-list", "merge", "dummy-node", "two-pointers"],
    "entities": ["哑结点（dummy head）", "尾插法", "归并（merge）"],
    "diagram": {
        "kind": "flow",
        "title": "哑结点 + 尾插的合并过程（l1 = 1→2→4，l2 = 1→3→4）",
        "caption": "dummy 是哨兵，tail 始终指向已合并链的尾巴。比较 l1、l2 的当前结点，"
                   "把较小的那个接到 tail.next，然后该链前进一格。任一条走完后，"
                   "直接把另一条剩下的整段挂上——这一步是 O(1)，不是循环复制。",
        "alt": "两个有序链表 1→2→4 与 1→3→4 的结点排布与箭头",
        "svg": svg_chain(
            ["1", "2", "4"], "第一条有序链表 1 到 2 到 4", w=660,
            marks=[(0, "l1 / tail"), (2, "NULL")]),
    },
    "concepts": [concept(
        "哑结点的作用",
        "哑结点是一个不存真实数据的哨兵，让「结果链的第一个结点」和「后续结点」"
        "可以用同一套 tail.next = 代码处理，省掉第一次插入的特判。",
        "像装订文件时先夹一张空白封面：之后无论插入哪一页，你都是「在最后一页之后插入」，"
        "不需要再单独写「如果是第一页怎么办」。",
        "哑结点的值本身永远不该被读取。常见错误是在返回时返回 dummy（而不是 dummy.next），"
        "于是结果多出一个值为 0 的假结点；或者在 while 里访问 cur.val 时忘了 cur 可能是 dummy。"
        "把它严格当成「只用来指路、不能取值」的锚点，这两个错都不会犯。",
        "链表无法像数组那样「预先分配返回值」，所以必须有个东西先占住链头。"
        "哑结点把「返回值」与「尾指针」解耦：tail 可变，dummy 不变，最后返回 dummy.next，"
        "整个过程不需要任何条件分支。",
        "在纸带最左端画一个灰色空框，标 dummy；tail 箭头指向它。每轮画一次「比较两个红点 →"
        "把小的接在灰框后面 → 红点右移」，六个红点一共三轮。",
        ["链表结点与 next 指针", "while 循环与指针前进"],
        ["如果把 dummy 换成「直接返回两条链里较小的头」，需要多写多少特判？",
         "为什么最后那一步可以整段挂上，而不需要逐个结点复制？",
         "递归版在什么输入下会栈溢出？"],
    )],
    "formulas": [],
    "selfCheck": {
        "claims": [
            "迭代版额外空间 O(1)：只用了 dummy 和两个指针。",
            "最终 O(m+n)：每个结点最多被访问一次。",
            "迭代版与递归版在 5 组用例（含空链、全等、长度悬殊）上结果一致。",
        ],
        "uncertain": [
            "题目对「稳定」的要求各平台不一致；实现用 <= 保证相等时先取 l1，"
            "但这只在源数据有隐含顺序时才有意义。",
        ],
    },
    "teaching": teaching(
        progressive=[
            lv("第 1 层 · 能写", "用哑结点写出迭代合并，指针前进不丢结点。"),
            lv("第 2 层 · 能说清", "说清哑结点解决了什么特判，以及最后为什么能整段挂上。"),
            lv("第 3 层 · 能算代价", "分析 O(m+n) 时间与 O(1) 额外空间，"
                                    "并说明「整段挂上」为何不增加渐进代价。"),
            lv("第 4 层 · 能迁移", "把「双链合并」升到「K 链合并」（堆/O(n log k)）"
                                  "和「排序链表」（归并），说明这套零件怎么复用。"),
        ],
        socratic=[
            qa("既然递归版只有 5 行，为什么面试还要求写迭代版？",
               "递归深度 = m+n，长链表（如 10 万结点）会栈溢出；而且面试官常借递归题追"
               "「空间复杂度是多少」——递归版是 O(m+n)，不是 O(1)。"),
            qa("最后 tail.next = l1 if l1 else l2 这行为什么是 O(1)？",
               "因为它只是把一段已有链表的头指针接上去，没有复制任何结点。"
               "剩下的结点也不需要再比较——两条链各自有序，且已接走的部分都 ≤ 剩下的，"
               "所以整段直接接上就是有序的。"),
            qa("如果两条链表长度悬殊（比如 3 个 vs 100 万个），代码需要改吗？",
               "不需要。极端情况下 while 会很快走完短的那条，然后一次挂上长链的剩余部分，"
               "总代价仍然是 O(m+n)（至少要把短链走完），而「挂」是 O(1)。"),
        ],
        mechanism="维护一个尾指针 tail 指向已合并部分的最后一个结点，以及两个游标 l1、l2 "
                  "分别指向两条链的当前结点。每轮比较两个游标的值，把较小者接到 tail.next 并"
                  "令其游标前进，tail 也前进一格。当任一游标为 None 时循环结束，此时另一条链的"
                  "剩余部分必然全部大于等于已合并部分的所有值，因此直接接到 tail.next 即可。",
        boundary="仅适用于「两条链都已有序」。如果输入无序，正确做法是先排序（链表用归并）"
                 "再合并。链表没有随机访问，所以不能用数组那样的「从后往前填」技巧；"
                 "链表的合并天然是从前往后。",
        analogyBoundary="「拉链」的类比会让人以为两边是同时、对称地消耗完的 —— 实际实现里"
                        "必然有一条先走完，之后是单边收尾。这个不对称正是最后那行代码存在的原因，"
                        "类比不会提醒你去处理它。",
        misconceptions=[
            "最后一步用 while 逐个复制剩余结点——多了一倍的常数，而且没有必要。",
            "忘记 return dummy.next 而返回 dummy，结果多一个值为 0 的结点。",
            "while 条件写成 while l1 or l2 但没有在循环体内处理空指针，导致访问 None.val。",
            "以为递归版的空间是 O(1)：递归调用栈按合并长度线性增长。",
            "把 tail = tail.next 写在 if 分支里——通常是对的，但要确认两条分支都执行了。",
        ],
        ownAnalysis="这道题真正的通用价值是「哑结点 + 尾指针」这套骨架："
                    "「删除倒数第 N 个」、「删除重复元素 II」、「重排链表」都靠它起手。"
                    "把它当作一个可背诵的模板，比记住本题的解更有意义——"
                    "面试时手写链表题的时间几乎都花在边界上，而哑结点能一次性消掉"
                    "「删头结点」「在头部插入」两大类边界。",
        officialNotes=[
            {"position": "标准解法是带哨兵的迭代合并，时间 O(m+n)、额外空间 O(1)；"
                         "递归解法在官方题解中也给出，但空间为 O(m+n)。",
             "source": "LeetCode 21 官方题解 · 合并两个有序链表"},
        ],
        interviewAnswer="先说结构：「哑结点占住链头，tail 尾插，谁小接谁，最后整段挂上」。"
                        "手写时边写边报「这里用 <= 保证相等时先取 l1」。写完主动补两句："
                        "「时间 O(m+n)、额外空间 O(1)」和「递归版是 5 行但栈深 O(m+n)，"
                        "长链表会爆栈」。这两句基本覆盖所有追问。",
        prereq=["链表结点结构与遍历", "指针不丢链的写法", "归并（merge）思想"],
        next_steps=["做「排序链表」（归并 + 快慢指针找中点）",
                    "做「合并 K 个有序链表」，对比堆与分治两种做法",
                    "做「两数相加」，同样是哑结点 + 尾插的骨架"],
    ),
    "problem": problem(
        title="合并两个有序链表（LeetCode 21）",
        statement="将两个升序链表合并为一个新的升序链表并返回。新链表是通过拼接给定的两个链表的"
                  "所有结点组成的。要求时间 O(m+n)、额外空间 O(1)。",
        examples=[
            ("l1 = 1→2→4, l2 = 1→3→4", "1→1→2→3→4→4",
             "相等时先取 l1，所以两条链里的第一个 1 依次相接"),
            ("l1 = [], l2 = [0]", "0", "空链是必须处理的边界，直接返回另一条即可"),
            ("l1 = [], l2 = []", "[]", "两条都空时返回 None；哑结点写法会自动给出这个结果"),
        ],
        idea="用一个哑结点 dummy 占住结果链的链头，tail 始终指向已合并部分的尾巴。"
             "同时遍历两条链，每轮把值较小的那个结点接到 tail 后面，并把对应游标前进一格。"
             "任一链走完后，把另一条链的剩余部分整段接到 tail.next —— 这一步是 O(1)。",
        steps=[
            "建 dummy = ListNode(0)，tail = dummy。",
            "while l1 and l2：若 l1.val <= l2.val 则 tail.next, l1 = l1, l1.next；"
            "否则 tail.next, l2 = l2, l2.next；然后 tail = tail.next。",
            "循环结束后 tail.next = l1 if l1 else l2。",
            "返回 dummy.next。",
        ],
        whyItWorks="循环不变量：dummy.next 到 tail 这一段已经是「已取走的所有结点」按升序排好的，"
                   "且这些值都 ≤ 两条链当前游标的值。因此每次取较小者接到尾部都能保持有序。"
                   "循环结束时至少一条链为空，另一条链从头到尾有序且所有值 ≥ 已合并部分的末尾，"
                   "所以整段直接接上仍保持全局有序，无需逐结点比较。",
        alternatives=[
            ("递归版", "O(m+n) 时间 / O(m+n) 空间（递归栈）",
             "面试官明确要求递归时用；代码极短，但要主动指出栈深风险。"),
            ("新链表逐个复制值", "O(m+n) 时间 / O(m+n) 空间",
             "仅当不允许修改输入链表时用。原题允许拼接，所以这是浪费。"),
            ("分治合并 K 条链", "O(n log k) 时间 / O(1) 额外空间",
             "K 条链时用；两条链的本题是它的最小单元。"),
        ],
        python=SOLUTIONS["034602d65c3c3d83"][1],
        python_alt=MERGE_LISTS_ALT,
        notes="迭代版与递归版都跑过，在空链、单元素、全等、长度悬殊、头部插入五种情形上结果一致。"
              "写库里的是迭代版：它满足题目要求的 O(1) 额外空间。",
        time_c="O(m + n)",
        space_c="O(1)",
        why_c="每个结点最多被访问一次并接到结果链上一次，故时间线性于两链长度之和。"
              "额外空间只用了 dummy、tail 和两个游标共 4 个引用，与输入规模无关，故 O(1)。"
              "递归版的空间是 O(m+n)，因为每层调用都占一帧栈。",
        pitfalls=[
            "返回 dummy 而不是 dummy.next：结果链头多一个值为 0 的假结点。",
            "最后用 while 逐个搬运剩余结点：正确但没必要，且容易在空指针上出错。",
            "while 条件写成 while l1 or l2 却不在循环体内判空：访问 None.val 直接崩。",
            "忘记推进 tail：所有结点都接在同一个位置，结果链只剩两个结点。",
            "比较用 < 而不是 <=：本身不算错，但会在「相等时取谁」上与面试官预期不一致，"
            "不如显式说明取舍。",
        ],
        edge_cases=[
            "l1 为空：直接返回 l2（哑结点写法天然覆盖）。",
            "l2 为空：同理返回 l1。",
            "两条都为空：返回 None。",
            "长度悬殊（3 vs 1000000）：验证「整段挂上」而不是逐结点搬运。",
            "全程相等（1→1→1 与 1→1）：验证 <= 分支稳定地取 l1。",
        ],
        tips="这道题是「模板题」，面试表现的关键在速度与边界说法。手写时先写 dummy，"
             "再写 while，最后写那行整段挂上——顺序清楚就不容易漏。"
             "主动说「O(1) 额外空间」是得分点；如果面试官让写递归版，一定要补一句栈深风险。"
             "被追问「K 条链怎么办」时答「小顶堆，O(n log k)」，这是自然延伸。",
    ),
}

# ---------------------------------------------------------------------------
# 4. 二叉树的层序遍历 LeetCode 102（freq 180）
# ---------------------------------------------------------------------------
CONTENT["bd4885b4390f3133"] = {
    "tldr": "BFS 的关键只有一句：进入 while 后先用 range(len(q)) 把「本层结点数」固定下来，"
            "那个长度就是这一层的边界，否则新入队的子结点会混进本层。",
    "why": "层序是树题里唯一的「按层」视角，锯齿遍历、右视图、每层最大值、"
           "最小深度都是它的变形。面试里它的真正考点是**分层**——"
           "不写 len(q) 快照的人，写出来的是一锅乱炖的 BFS。",
    "difficulty": "medium",
    "tags": ["tree", "bfs", "queue", "level-order"],
    "entities": ["BFS", "队列", "分层快照", "DFS 按深度分组"],
    "diagram": {
        "kind": "architecture",
        "title": "层序遍历的分层快照（root = [3,9,20,null,null,15,7]）",
        "caption": "队列在每轮开始时的长度就是本层结点数。第 1 轮长度 1 → 只处理 3，"
                   "同时把 9、20 入队；第 2 轮长度 2 → 只处理 9、20，同时把 15、7 入队；"
                   "第 3 轮长度 2 → 处理 15、7。若不用快照，第 2 轮会把 15、7 也算作本层。",
        "alt": "二叉树 3 为根、9 和 20 为子、15 和 7 为第三层，按层分成三组",
        "svg": svg_tree(
            [["3"], ["9", "20"], ["15", "7"]],
            "二叉树的三层结构：根 3，第二层 9 与 20，第三层 15 与 7",
            hi=((2, 0), (2, 1))),
    },
    "concepts": [concept(
        "分层快照（len(q) 快照）",
        "在 while 循环体内、任何入队动作之前，先记下队列长度 n，然后只弹出 n 次。"
        "这 n 个就是「同一层」的全部结点。",
        "像一个窗口叫号机：你只在「开始叫这一批」时数一下现在有多少人等，"
        "然后只叫这么多人；期间新来的人归下一批，不能混进这一批。",
        "快照必须在**本轮入队之前**取。如果写成 `for _ in range(len(q))` 但前面已经有了入队代码，"
        "或者写成 `while q and len(level) < len(q)` 这类依赖循环中变化长度的写法，"
        "分层就会错——而且在小树上常常看不出，只有三层以上、每层宽度不一致时才暴露。",
        "队列天然是 FIFO：同一层的结点总是先于下一层的子结点入队。因此「本层结点」在队列里"
        "恰好是连续的一段、且长度在入队前就已确定。取这个长度做循环次数，"
        "就精确地只消费本层、把新入队的子结点留给下一层。",
        "画三条水平带子，队列画成一条横排的格子。每轮开始先数格子里有几个红球，"
        "把它们逐个取走并在下一排放入各自的孩子；三条带子就是三层。",
        ["队列（FIFO）", "二叉树的孩子指针", "while 循环与嵌套循环的边界"],
        ["如果去掉 len(q) 快照、直接 while q 逐个弹出并把子结点入队，"
         "得到的输出和正确答案差在哪里？",
         "为什么这道题用 DFS + 深度下标也能得到同样结果？",
         "如果要求「之字形」输出，需要在哪一步改动？"],
    )],
    "formulas": [],
    "selfCheck": {
        "claims": [
            "BFS 版与 DFS 版在 4 组用例（含空树、单结点、稀疏树）上输出一致。",
            "分层快照使每层恰好被处理一次，总时间 O(n)。",
        ],
        "uncertain": [
            "题目对 null 结点的编码方式因平台而异（这里用列表层序编码），"
            "实际输入是结点对象，null 只出现在示例表达里。",
        ],
    },
    "teaching": teaching(
        progressive=[
            lv("第 1 层 · 能写", "用队列写出 BFS，把每层结点装进子列表。"),
            lv("第 2 层 · 能说清", "说清 len(q) 快照为什么必须在入队之前取。"),
            lv("第 3 层 · 能算代价", "分析 O(n) 时间与 O(w) 空间（w 为最宽层），"
                                    "并说明为什么不是 O(n)。"),
            lv("第 4 层 · 能迁移", "把它用到锯齿遍历、右视图、每层最值、最小深度，"
                                  "并说清哪些变形只需改一行。"),
        ],
        socratic=[
            qa("不取 len(q) 快照，直接 BFS，输出会变成什么？",
               "会得到「按入队顺序的扁平列表」，也就是前序 BFS 顺序 [3,9,20,15,7]，"
               "但层级边界丢失，无法还原成 [[3],[9,20],[15,7]]。"),
            qa("空间复杂度是 O(n) 还是 O(w)？",
               "O(w)，w 是最宽一层的结点数。队列里最多同时存在相邻两层的结点，"
               "不会出现整棵树都在队列里的情况（除非树退化成链表，此时 w = 1 但深度为 n，"
               "队列仍然只有常数个 —— 所以严格上界是 O(w) ≤ O(n)）。"),
            qa("为什么 DFS 也能做层序？",
               "因为「层」等价于「到根的深度」。DFS 带一个深度参数 d，"
               "首次到达深度 d 时给 out 追加一个空列表，然后把值 append 进去，"
               "结果和 BFS 一样按层分组——区别只是元素在层内的顺序不一定保持从左到右。"),
        ],
        mechanism="队列保证同层结点先于其子结点出队。每轮开始时，队列里恰好存着「当前层的全部"
                  "结点」（上一轮入队的），所以取 len(q) 做循环次数就精确地只消费这一层；"
                  "循环体内把子结点入队，它们排在队尾，自然成为下一轮的内容。"
                  "层与层之间的边界由这个长度快照显式给出，而不是靠某种标记。",
        boundary="层序适用于任意树/图的「按距离分层」，但要注意：多叉树、图（有环）需要"
                 "visited 集合；森林需要外层再套一层。DFS 版本在极深的树上递归会爆栈，"
                 "此时 BFS 更稳。若只要「每层最值」这类聚合结果，可以在 BFS 里直接算，"
                 "不必先建出完整的分层列表。",
        analogyBoundary="「窗口叫号」的类比会让人以为「批次」是天然存在的属性 —— 实际上批次完全"
                        "由你取快照的时机定义。换句话说，分层不是数据自带的，而是你在正确的"
                        "位置读了一次长度才产生的。",
        misconceptions=[
            "把 len(q) 写成在循环条件里反复求值：如果循环体里又入队，边界会漂移。",
            "以为空间是 O(n)：队列最多同时放相邻两层，是 O(w)。",
            "用两个队列交替虽也对，但多了一份不必要的拷贝；一个队列 + 快照就够了。",
            "在 DFS 版本里把 out[d].append 写成 out.append，导致层内元素被覆盖。",
            "忘记处理空树，直接访问 root.val 导致崩。",
        ],
        ownAnalysis="这道题的价值不在算法，而在「识别出分层需求」这一步。" 
                    "很多题看起来不像层序，其实是：右视图（每层最后一个）、树的宽度（最大的层长度）、"
                    "最小深度（第一个叶子所在层）、僵尸/腐烂扩散、二叉树的最近右邻居——"
                    "只要题目出现「同一深度 / 同一层 / 同时发生」，就该先想到队列 + 快照。",
        officialNotes=[
            {"position": "官方给出 BFS（队列）与 DFS（深度下标）两种解法，时间均为 O(n)。",
             "source": "LeetCode 102 官方题解 · 二叉树的层序遍历"},
        ],
        interviewAnswer="先一句话：「队列 + 每轮取长度做分层快照」。手写时把 len(q) 单独存"
                        "成变量并说明「必须在入队前取」，这一句是本题的核心得分点。"
                        "写完报 O(n) 时间、O(w) 空间。如果面试官加难度（锯齿、右视图），"
                        "直接说「改一行：每层按层号决定是否反转 / 只取最后一个」。",
        prereq=["队列的基本操作", "二叉树的遍历", "BFS 与 DFS 的区别"],
        next_steps=["做「锯齿形层序遍历」：每层按层号决定是否反转",
                    "做「二叉树的右视图」：每层只取最后一个",
                    "做「二叉树的最小深度」：遇到第一个叶子就返回当前层号"],
    ),
    "problem": problem(
        title="二叉树的层序遍历（LeetCode 102）",
        statement="给你二叉树的根结点 root，返回其结点值的层序遍历（即逐层地、从左到右访问"
                  "所有结点）。输出是二维列表，每个子列表是一层的结点值。",
        examples=[
            ("root = [3,9,20,null,null,15,7]", "[[3],[9,20],[15,7]]",
             "第一层只有根 3；第二层 9、20；第三层 15、7"),
            ("root = [1]", "[[1]]", "单结点，只有一层"),
            ("root = []", "[]", "空树返回空列表，不能写成 [[]]"),
        ],
        idea="BFS + 分层快照。用一个队列做广度优先遍历；进入 while 后立刻取出当前队列长度 n，"
             "只弹出 n 个结点作为「本层」，并在弹出的同时把它们的左右孩子入队。"
             "这 n 个结点的值组成一个子列表，追加到结果里。",
        steps=[
            "若 root 为空，直接返回 []。",
            "建队列 q = deque([root])，结果 out = []。",
            "while q：令 n = len(q)，建立本层列表 level = []。",
            "重复 n 次：弹出队首 node，把 node.val 加入 level，"
            "若 node.left 存在则入队，若 node.right 存在则入队。",
            "把 level 追加进 out；循环结束后返回 out。",
        ],
        whyItWorks="队列的 FIFO 性质保证了「同一层的结点在队列里连续存放，且都排在下一层结点之前」。"
                   "因此进入本轮时队列中前 n 个元素恰好是本层全部结点。"
                   "循环体把它们弹出并把孩子放到队尾，孩子不会挤进本次的 n 次循环里，"
                   "于是每层被精确地处理一次、结果天然分层。",
        alternatives=[
            ("DFS + 深度下标", "O(n) 时间 / O(h) 空间",
             "树很深但很窄时更省内存（h 是树高）；层内顺序取决于遍历顺序，"
             "左中右先序即可保证从左到右。"),
            ("两个队列交替", "O(n) 时间 / O(w) 空间",
             "不用 len 快照也能分层，逻辑更显式；代价是多一份队列引用，"
             "且写起来更容易搞错交换时机。"),
            ("带层标记的单一队列", "O(n) 时间 / O(w) 空间",
             "往队列里塞 None 作为分隔符；代码直观，但要额外处理尾部分隔符，"
             "空结点场景下容易多出一个空层。"),
        ],
        python=SOLUTIONS["bd4885b4390f3133"][1],
        python_alt=LEVEL_ORDER_ALT,
        notes="BFS 与 DFS 两个版本都跑过，在空树、单结点、满二叉树、左偏稀疏树四组用例上"
              "输出一致。写进库里的是 BFS 版，因为它是这道题的标准答案；"
              "DFS 版作为对照，说明同一问题可以有不同空间取舍。",
        time_c="O(n)",
        space_c="O(w)（w 为最宽一层的结点数）",
        why_c="每个结点恰好入队一次、出队一次，故时间 O(n)。队列中最多同时存放相邻两层的结点，"
              "因此额外空间由最宽一层决定，即 O(w) ≤ O(n)。"
              "结果列表本身占 O(n)，那是输出，不计入额外空间。",
        pitfalls=[
            "把 len(q) 写在循环条件里或每轮重复求值，导致分层边界漂移。",
            "写成 while q 并省略内层循环：得到扁平列表，层级信息丢失。",
            "空树返回 [[]] 而不是 []：多了一个空层。",
            "在 DFS 版本里用 out.append 取代 out[d].append，层内元素互相覆盖。",
            "认为空间是 O(n)：只有在最宽层接近 n 时才等于 O(n)，一般应为 O(w)。",
        ],
        edge_cases=[
            "空树：返回 []。",
            "单结点：返回 [[val]]。",
            "退化成链表（全部只有左孩子）：层数是 n，但每层只有一个结点，"
            "此时空间是 O(1)——可以用来反驳「空间一定是 O(n)」。",
            "左偏稀疏树 [1,2,3,4,null,null,5]：验证 null 不产生空层。",
            "完全二叉树（含 1000 个结点）：验证结果层数 = ⌊log2 n⌋ + 1。",
        ],
        tips="这道题的面试得分点几乎全在「分层」两个字上。写的时候把 len(q) 单独提取成变量，"
             "并口头强调「这行必须在任何入队之前」。如果面试官问「空间是多少」，"
             "答 O(w) 并主动补充「退化成链时是 O(1)」，这比背 O(n) 更显理解。"
             "被追问变形时，一律先答「只需改内层循环」，再具体说改哪一行。",
    ),
}

# ---------------------------------------------------------------------------
# 5. 有效的括号 LeetCode 20（freq 148）
# ---------------------------------------------------------------------------
CONTENT["68cee1fb263dc177"] = {
    "tldr": "一个栈 + 一张右括号→左括号的映射表：遇到右括号必须与栈顶配对，"
            "全部扫完后栈必须为空。两个「必须」各对应一类经典错误输入。",
    "why": "它是最简单的「栈」入门题，也是「两个必要条件缺一不可」的教科书案例："
           "只看配对会漏掉「多右括号」，只看栈空会漏掉「多左括号」。"
           "括号匹配的模型直接迁移到表达式求值、嵌套结构校验、"
           "以及「反转栈 / 单调栈」系列。",
    "difficulty": "easy",
    "tags": ["stack", "string", "bracket-matching"],
    "entities": ["栈（LIFO）", "括号匹配", "下推自动机"],
    "diagram": {
        "kind": "flow",
        "title": "栈在 s = \"([{}])\" 上的五步",
        "caption": "左括号一律入栈；右括号必须与栈顶配对并弹出。最后栈为空才算合法。"
                   "注意两次失败：s = \"(]\" 时栈顶是 ( 却遇到 ]；s = \"(\" 时扫完栈不为空。",
        "alt": "字符串 ([{}]) 逐字符处理时栈内容的变化，最终栈为空",
        "svg": svg_trace(
            [
                {"label": "读 (", "cells": ["("], "hi": [0], "note": "左括号 → 入栈"},
                {"label": "读 [", "cells": ["(", "["], "hi": [1], "note": "左括号 → 入栈，深度 2"},
                {"label": "读 {", "cells": ["(", "[", "{"], "hi": [2], "note": "左括号 → 入栈，深度 3"},
                {"label": "读 }", "cells": ["(", "["], "hi": [1],
                 "note": "栈顶 { 与 } 配对 → 弹出；栈顶变成 ["},
                {"label": "读 ]", "cells": ["("], "hi": [0], "note": "栈顶 [ 与 ] 配对 → 弹出"},
                {"label": "读 )", "cells": [], "note": "栈顶 ( 与 ) 配对 → 弹出；栈空 → 合法"},
            ],
            "括号匹配过程中栈内容的变化"),
    },
    "concepts": [concept(
        "以「未闭合深度」为状态的栈",
        "栈里始终只存「已经出现、但还没被闭合的左括号」，按出现顺序排列。"
        "栈顶就是「最近一个还没闭合的左括号」。",
        "像套娃：只有最外面那个还没合上的能先被合上，所以检查永远看最内层（栈顶）。"
        "顺序错了就说明嵌套结构被破坏了。",
        "栈的**深度**很容易被误当成「答案」：深度为 0 只说明「当前没有未闭合的左括号」，"
        "不说明整个串合法 —— s = \")(\" 在读到 ) 时深度就是 -1（或栈空却要弹出），"
        "此时必须立刻判非法，而不是继续往下扫。",
        "括号语言需要「计数 + 顺序」两个信息，而单一计数器只有计数。栈之所以必要，"
        "是因为它同时保存了「有多深」和「每一层是哪种括号」——"
        "这正是 ( 与 [ 混用时必须用栈而不能用三个计数器的原因。",
        "画一摞竖着叠放的格子代表栈。每读一个字符画一次：左括号往上加一格，"
        "右括号把顶上那格弹掉并画一个配对连线；配对失败就画红叉。",
        ["栈的 push/pop", "字典映射", "字符串遍历"],
        ["为什么不能只用三个计数器分别数 ()、[]、{} 的数量？",
         "s = \")]\" 和 s = \"([)\" 分别在哪一步被判定非法？",
         "空串算合法吗？为什么？"],
    )],
    "formulas": [],
    "selfCheck": {
        "claims": [
            "栈版与「反复消去」版在 10 组用例（含空串、单括号、错序嵌套）上结论一致。",
            "两个失败条件各自覆盖一类非法输入：右括号多余、左括号多余。",
        ],
        "uncertain": [
            "「有效」的定义通常要求空串合法；若面试要求至少一对括号，需要加一条长度判断。",
        ],
    },
    "teaching": teaching(
        progressive=[
            lv("第 1 层 · 能写", "用栈与字典写出匹配判定。"),
            lv("第 2 层 · 能说清", "说清「栈空却遇到右括号」与「扫完栈非空」这两个失败点。"),
            lv("第 3 层 · 能算代价", "分析 O(n) 时间、O(n) 最坏空间，"
                                    "并说明最坏发生在什么输入上。"),
            lv("第 4 层 · 能推广", "说出括号匹配本质是「下推自动机的栈检查」，"
                                  "并迁移到表达式求值、嵌套结构校验。"),
        ],
        socratic=[
            qa("为什么三个计数器不够？",
               "计数器只知道数量，不知道顺序。s = \")[\" 中 ) 和 [ 各一个，数量配平，"
               "但顺序非法。栈保存的是「未闭合序列」本身，因此能同时校验顺序。"),
            qa("为什么必须先判 stack 是否为空，再判栈顶？",
               "s = \")\" 时栈是空的，先访问 stack[-1] 会 IndexError。"
               "「空栈遇到右括号」本身就是非法判据，要单独前置。"),
            qa("最坏空间为什么是 O(n)？",
               "输入形如 \"(((((\" 时所有字符都留在栈里，深度 n。"
               "这是必须的——要判断末尾的闭合是否匹配到正确的左括号，就得把它们都记住。"),
        ],
        mechanism="遍历字符：左括号压栈（记录「还没闭合的是什么」）；右括号则要求栈非空"
                  "且栈顶等于该右括号对应的左括号，然后把栈顶弹出（表示这一层闭合了）。"
                  "任一条件不满足立即返回 False。遍历结束后，栈必须为空——"
                  "否则说明有左括号从未被闭合。",
        boundary="只适用于「一种括号体系内后进先出配对」的场景。如果题目允许通配符"
                 "（如 LeetCode 678 带 * 的括号匹配），需要额外 DP 或双栈贪心。"
                 "如果括号类型是自定义的成对关系，把字典换掉即可，算法不变。",
        analogyBoundary="「套娃」的类比会让人以为「只要最内层合上就永远安全」——"
                        "实际栈里存的是左括号序列，右括号进来时可能压根没有对应的左括号"
                        "（空栈），这种「凭空出现的闭合」是套娃类比的盲区。",
        misconceptions=[
            "只统计数量或只用一个计数器：无法区分 \"([)]\" 与 \"([])\"。",
            "右括号分支忘记判空栈：遇到 \"]\" 直接 IndexError。",
            "忘记最后检查栈空：s = \"(（\" 会被判成合法。",
            "把左括号也存成「右括号→左括号」的映射值：映射方向搞反会全部不匹配。",
            "用「反复 replace」写：逻辑正确但最坏 O(n²)，大输入会超时。",
        ],
        ownAnalysis="这道题真正值得记住的是「两个必要的失败条件」这种思维形式："
                    "很多判定型问题都可以拆成「存在性」与「完整性」两条。"
                    "括号匹配里是「每个右括号都有对象」与「每个左括号都被闭合」；"
                    "在区间调度、拓扑排序（是否有环 / 是否覆盖全部结点）里也是同一种成对判据。"
                    "先想清这两条，再写代码，通常不会漏边界。",
        officialNotes=[
            {"position": "括号语言不是正则语言，无法用有限自动机识别；"
                         "需要栈（下推自动机）才能判定。这是「为什么不能用计数器」的形式化答案。",
             "source": "形式语言与自动机 · 上下文无关语言"},
            {"position": "官方题解给出「栈」与「反复消去相邻配对」两种思路，"
                         "并指出后者最坏 O(n²)。",
             "source": "LeetCode 20 官方题解 · 有效的括号"},
        ],
        interviewAnswer="三句话打完：① 用栈存未闭合的左括号；② 右括号必须「栈非空且栈顶配对」，"
                        "否则立即 False；③ 扫完栈必须为空。写完主动用 \"([)]\" 说明顺序问题、"
                        "用 \"(\" 说明完整性要求——这两个反例正好对应两个失败条件，"
                        "把「我理解题意」这件事一次性证明掉。",
        prereq=["栈的 push/pop", "字符串遍历", "字典（映射表）"],
        next_steps=["做「最长有效括号」：从匹配判定升级到区间 DP / 栈记录下标",
                    "做「逆波兰表达式求值」：同一个栈模型用于表达式计算",
                    "做「带通配符的括号匹配」，体会判定型问题为何需要 DP"],
    ),
    "problem": problem(
        title="有效的括号（LeetCode 20）",
        statement="给定一个只包括 '('、')'、'{'、'}'、'['、']' 的字符串 s，"
                  "判断字符串是否有效。有效字符串需满足：左括号必须用相同类型的右括号闭合、"
                  "左括号必须以正确的顺序闭合、每个右括号都有一个对应的相同类型的左括号。",
        examples=[
            ("s = \"()\"", "true", "单层配对"),
            ("s = \"()[]{}\"", "true", "三种括号各自配对，无嵌套"),
            ("s = \"([)]\"", "false", "数量配平但顺序错：] 应当先闭合 [，实际栈顶是 ("),
            ("s = \"(]\"", "false", "类型不匹配"),
            ("s = \"(\"", "false", "扫完栈非空：左括号从未闭合"),
        ],
        idea="用栈保存「已出现但未闭合的左括号」。遇到左括号就压栈；遇到右括号时，"
             "栈必须非空、且栈顶必须是对应的左括号，然后弹出栈顶。全部字符处理完后，"
             "栈必须为空。",
        steps=[
            "建映射 pairs = {')': '(', ']': '[', '}': '{'}，栈 stack = []。",
            "遍历 s 的每个字符 ch：若 ch 是右括号，则判断 stack 非空且 stack.pop() == pairs[ch]，"
            "不满足就 return False；否则把 ch 压栈。",
            "遍历结束后 return not stack。",
        ],
        whyItWorks="括号的有效性等价于「存在一个正确的配对方案，且每个配对都是相邻且类型相同的」。"
                   "栈顶恰好是最近一个未闭合的左括号，而「最近的未闭合左括号」正是它右边第一个"
                   "右括号应当闭合的对象——这是括号嵌套的定义。因此逐字符配对成立；"
                   "两个失败条件（右括号无对象、左括号无闭合）覆盖了全部非法情形。",
        alternatives=[
            ("反复消去相邻配对", "O(n²) 最坏 / O(n) 空间",
             "只适合解释思路或 n 很小；每轮 replace 都要重建字符串，实测大输入会超时。"),
            ("计数器（仅单一括号类型）", "O(n) 时间 / O(1) 空间",
             "只有一种括号类型时可用，一个计数器即可，比栈更省；混用类型时会失效。"),
            ("下标栈 + 区间标记", "O(n) 时间 / O(n) 空间",
             "题目要求「最长有效括号」这类区间问题时用；本题只需要布尔判定，"
             "记下标是多余的。"),
        ],
        python=SOLUTIONS["68cee1fb263dc177"][1],
        python_alt=VALID_PAREN_ALT,
        notes="两版都跑过，在 10 组用例（空串、单左/右括号、错序嵌套、深嵌套）上结论一致。"
              "写进库里的栈版是 O(n)；对照版用 replace 反复消去，"
              "保留它只是为了让「为什么不能用 O(n²) 写法」这件事可被验证。",
        time_c="O(n)",
        space_c="O(n) 最坏（全为左括号时）",
        why_c="每个字符最多被压栈、弹出各一次，故时间线性。空间由栈的最大深度决定，"
              "最坏输入是全左括号（深度 n），因此上界 O(n)；"
              "对随机输入平均深度远小于 n。",
        pitfalls=[
            "右括号分支没先判空栈：输入 \")\" 直接 IndexError。",
            "结尾忘记 return not stack：\"(\" 会被判为合法。",
            "映射方向写反（存成 '{': '}' 却用 stack.pop() 去比左括号）。",
            "把 return not stack 写成 return True，只检查了中途配对。",
            "用 replace 反复消去：正确但最坏 O(n²)。",
        ],
        edge_cases=[
            "空串 \"\"：合法。",
            "\"(\"、\"[\"、\"{\"：非法（栈非空）。",
            "\")\"、\"]\"、\"}\"：非法（空栈弹出）。",
            "\"([)]\"：非法（配对对象错误）。",
            "\"((((()))))\"：合法（深层嵌套，验证栈深）。",
            "长度 10^4 的全左括号：验证 O(n) 时间与 O(n) 空间。",
        ],
        tips="这题面试时间通常只有 3–5 分钟，所以边写边说。两个得分点："
             "① `if not stack or stack.pop() != pairs[ch]` 里的前置判空；"
             "② 结尾的 `return not stack`。写完主动用 \"([)]\" 和 \"(\" 两个反例自证正确性，"
             "比等面试官来挑错好得多。",
    ),
}

# ---------------------------------------------------------------------------
# 6. 合并两个有序数组 LeetCode 88（freq 137）
# ---------------------------------------------------------------------------
CONTENT["ae9b3bd5f0c0ec14"] = {
    "tldr": "从后往前填：三个指针 i=m-1、j=n-1、k=m+n-1，每次把较大的那个放到 nums1[k]。"
            "因为 k 永远追不上 i，写入不会覆盖还没比较的 nums1 元素。",
    "why": "这道题的全部价值在「为什么要从后往前」。从前向后写需要额外 O(m) 空间"
           "（会覆盖未读元素），这个取舍是面试官真正想听的。"
           "它也是「原地归并」的第一步，理解后能直接迁移到「原地归并排序」"
           "和「去掉排序数组中的重复项」这类双指针原地题。",
    "difficulty": "easy",
    "tags": ["array", "two-pointers", "in-place", "merge"],
    "entities": ["从后往前填", "三指针", "原地归并"],
    "diagram": {
        "kind": "flow",
        "title": "从后往前填（nums1 = [1,2,4,0,0,0], m=3; nums2 = [2,5,6], n=3）",
        "caption": "i、j 分别指向两条数组的最后一个有效元素，k 指向 nums1 的最后一个空位。"
                   "每轮比较 nums1[i] 与 nums2[j]，把大的写到 nums1[k] 并前进。"
                   "k 至少比 i 快一步，所以永远不会覆盖还没用过的 nums1[i]。",
        "alt": "从后往前填充合并两个有序数组的三轮状态",
        "svg": svg_trace(
            [
                {"label": "初始", "cells": ["1", "2", "4", "0", "0", "0"], "hi": [5],
                 "note": "i=2(4), j=2(6), k=5 → 比较 4 与 6"},
                {"label": "第 1 轮", "cells": ["1", "2", "4", "0", "0", "6"], "hi": [5],
                 "note": "6 更大 → nums1[5]=6，j=1，k=4"},
                {"label": "第 2 轮", "cells": ["1", "2", "4", "0", "5", "6"], "hi": [4],
                 "note": "5 > 4 → nums1[4]=5，j=0，k=3"},
                {"label": "第 3 轮", "cells": ["1", "2", "4", "4", "5", "6"], "hi": [3],
                 "note": "4 > 2 → nums1[3]=4，i=1，k=2"},
                {"label": "第 4 轮", "cells": ["1", "2", "2", "4", "5", "6"], "hi": [2],
                 "note": "2 >= 2 → nums1[2]=2，j=-1 → j < 0 循环结束"},
                {"label": "结果", "cells": ["1", "2", "2", "4", "5", "6"],
                 "note": "nums1 的剩余 [1,2] 本来就在正确位置，无需搬动"},
            ],
            "合并两个有序数组时从后往前填充的状态变化"),
    },
    "concepts": [concept(
        "从后往前填的安全性",
        "k（写指针）在每一轮都 ≥ i+1，也就是说写位置永远在「还没被读取的 nums1 元素」右边，"
        "因此写入只会覆盖已经用过的空位。",
        "像把书架上的书重新排列：你从书架最右端开始把最大的书插进去，"
        "而你要比较的那些书都还在左边没动过，所以不会互相踩到。",
        "这个论证只在「nums1 的有效元素全在最左边、空位全在最右边」时成立。"
        "如果空位分布在中间（比如 nums1 只是「恰好够长」而不是题目约定的前置排列），"
        "从后往前就不再安全，必须先做一次搬迁。题目给的前提不能省。",
        "从前往后需要先保存 nums1 的前 m 个元素（否则被覆盖），因此需要 O(m) 额外空间；"
        "从后往前时，尚未读取的元素都在写指针左侧，读取指针 i 始终 ≤ k-1，"
        "所以不需要任何缓冲。两种方向的差异完全来自「读写的相对位置」。",
        "画两排格子：上排 nums1、下排 nums2。k 从右端起画箭头，每轮把较大的数字搬到上排"
        "当前 k 位置并涂实，两个读指针左移。六轮画完整个数组。",
        ["数组随机访问", "双指针", "原地算法与额外空间"],
        ["为什么从前往后需要额外空间？请给出被覆盖的具体例子。",
         "循环条件为什么只判 j >= 0，不判 i >= 0？",
         "如果 nums1 的空位在左边（前面有 0 后面是有效值），还能从后往前吗？"],
    )],
    "formulas": [],
    "selfCheck": {
        "claims": [
            "从后往前版本与「临时副本 + 从前向后」版本在 5 组用例上结果一致。",
            "循环条件只需 j >= 0 就足够；i < 0 时把 nums2 剩余项直接写入即可。",
        ],
        "uncertain": [
            "不同实现里 m、n 的含义可能指「有效长度」或「数组总长」，"
            "读题时必须确认，否则索引会整体偏一位。",
        ],
    },
    "teaching": teaching(
        progressive=[
            lv("第 1 层 · 能写", "用三指针从后往前填，得到 O(1) 额外空间解。"),
            lv("第 2 层 · 能说清", "说清「k 追不上 i」为什么保证不覆盖。"),
            lv("第 3 层 · 能对比", "与「从前向后 + 临时副本」对比，指出后者的 O(m) 空间代价"
                                  "并给出一个会被覆盖的具体例子。"),
            lv("第 4 层 · 能迁移", "把这套「从后往前填」搬到原地归并、"
                                  "以及「两个有序区间合并」的通用场景。"),
        ],
        socratic=[
            qa("从前向后写会覆盖什么？",
               "nums1 = [1,2,3,0,0,0]，nums2 = [2,5,6]。写 nums1[0] 时若把 nums2[0]=2 写进去，"
               "原来的 1 就丢了；而 nums1 后面的数据还没比过。所以要先把 nums1 前 m 个复制出来。"),
            qa("循环条件为什么是 while j >= 0？",
               "因为 nums2 处理完就结束了：nums1 剩余的前 i+1 个元素本来就在 nums1 的头部"
               "正确位置上，不需要搬动。反过来如果 nums1 先耗尽（i < 0），"
               "nums2 剩下的都必须写进去，所以不能以 i >= 0 作为终止条件。"),
            qa("如果 i >= 0 与 j >= 0 同时为真但 nums1[i] == nums2[j]，取哪个？",
               "取谁都行，结果数值相同；但如果要求稳定（保留 nums1 的在前），"
               "应当用 nums1[i] >= nums2[j] 先取 nums1。本题不要求稳定。"),
        ],
        mechanism="写指针 k 从 m+n-1 递减，读指针 i、j 从各自有效段的末尾递减。"
                  "每轮把两个读指针中较大的值写到 nums1[k]，然后递减被取走的那个读指针与 k。"
                  "由于 nums1 中尚未读取的部分都在下标 ≤ i，而 k ≥ i+1 恒成立，"
                  "写入位置永远在未读区域右侧，保证不覆盖。",
        boundary="前提是 nums1 的有效元素占据下标 0..m-1、空位在下标 m..m+n-1。"
                 "如果原题改成「合并到 nums2」或「空位在左侧」，必须调整方向或先做搬迁。"
                 "如果是链表，本技巧不适用（链表没有随机访问），改用哑结点尾插。",
        analogyBoundary="「收拾书架从右边开始」的类比会让人以为「任何原地插入都该从后往前」——"
                        "实际能否从后往前完全取决于空位在哪一侧。空位在中间时，"
                        "从后往前同样会覆盖未读数据。",
        misconceptions=[
            "循环条件写成 while i >= 0 and j >= 0 且循环后不补 nums2 剩余项：结果丢失元素。",
            "循环条件写成 while i >= 0：nums2 的剩余元素不会被写入。",
            "比较时用 < 而不是 >= 并且没有额外处理相等情况：结果仍然正确，"
            "但如果题目要求稳定性就会出错。",
            "忘记了 k 也要递减：所有元素都写进同一个位置。",
            "以为从前往后也能 O(1) 空间：nums1 前段会被 nums2 覆盖。",
        ],
        ownAnalysis="这道题值得迁移的是「读写指针的相对位置决定要不要缓冲」这条判断。"
                    "同一份数据上，只要写指针始终落在读指针「已消费」的一侧，就可以原地改写而不丢信息。"
                    "这个视角在「移除元素」「移动零」「原地归并」里完全一样，只是「哪一侧安全」的结论不同。"
                    "写原地算法时先画一次读写两指针的位置关系，比直接凭直觉写要可靠得多。",
        officialNotes=[{'position': '官方题解的第一解就是「双指针从后向前」，并明确指出它避免了 nums1 前段被覆盖的问题。', 'source': 'LeetCode 88 官方题解 · 合并两个有序数组'}, {'position': '归并两个有序序列是稳定排序的基础操作；从后向前归并只在「目标数组尾部有空位」时可用。', 'source': '算法导论 · 归并排序'}],
        interviewAnswer="一句话开场：「从后往前，三个指针，O(1) 额外空间」。"
                        "然后写代码，写完立刻解释「k 永远在未读区的右边，所以不会覆盖」。"
                        "主动对比一句「从前向后需要 O(m) 缓冲，因为 nums1 前段会被覆盖」——这一句能证明你不是背下来的，而是理解取舍。",
        prereq=["数组下标运算", "双指针技巧", "原地算法与额外空间的概念"],
        next_steps=["做「去掉排序数组中的重复项 II」：同类的双指针原地修改",
                    "实现原地归并排序，理解「从后往前」为什么要配合额外判断",
                    "做「两个有序链表的合并」，对比链表为何只能用尾插"],
    ),
    "problem": problem(
        title="合并两个有序数组（LeetCode 88）",
        statement="给你两个按非递减顺序排列的整数数组 nums1 和 nums2，另有两个整数 m 和 n，"
                  "分别表示 nums1 和 nums2 中的元素数目。请你合并 nums2 到 nums1 中，"
                  "使合并后的数组同样按非递减顺序排列。注意：nums1 的初始长度为 m+n，"
                  "其中前 m 个元素为应合并的元素，后 n 个元素为 0 应忽略。"
                  "要求原地修改，不返回新数组。",
        examples=[
            ("nums1 = [1,2,3,0,0,0], m = 3, nums2 = [2,5,6], n = 3",
             "[1,2,2,3,5,6]", "从后往前：先写 6、再写 5、再写 4（因为 4 > 2）"),
            ("nums1 = [1], m = 1, nums2 = [], n = 0", "[1]", "nums2 为空，循环体不执行"),
            ("nums1 = [0], m = 0, nums2 = [1], n = 1", "[1]",
             "nums1 前段为空，等于把 nums2 搬到 nums1 的尾部"),
        ],
        idea="反向双指针。i 指向 nums1 有效段的末尾（m-1），j 指向 nums2 的末尾（n-1），"
             "k 指向 nums1 的最后一位（m+n-1）。每轮把 nums1[i] 与 nums2[j] 中较大的那个"
             "写到 nums1[k]，然后递减对应指针与 k。nums2 处理完即结束。",
        steps=[
            "i, j, k = m - 1, n - 1, m + n - 1。",
            "while j >= 0：若 i >= 0 且 nums1[i] > nums2[j]，则 nums1[k] = nums1[i]，i -= 1；"
            "否则 nums1[k] = nums2[j]，j -= 1；最后 k -= 1。",
            "返回 nums1。",
        ],
        whyItWorks="写指针 k 满足 k ≥ i+1（每一步 k 与 i 同步或 k 单独递减）。"
                   "因此被写入的下标永远大于任何尚未读取的 nums1 下标 i，"
                   "写入不会破坏还没参与比较的数据 —— 这是 O(1) 额外空间的来源。"
                   "又因为两侧各自有序，每次取最大值放在结果末尾，"
                   "结果必然整体非递减（与归并的论证相同，只是方向相反）。",
        alternatives=[
            ("从前向后 + 临时副本", "O(m+n) 时间 / O(m) 额外空间",
             "不允许修改原数组方向、或实现更直观时用；代价是要先备份 nums1 的前 m 个元素。"),
            ("先拼接后排序", "O((m+n) log(m+n)) 时间 / O(1) 额外空间",
             "思路最省事，但浪费了「两侧已有序」这个前提，面试里会被追问有没有更快的。"),
            ("新建数组再回填", "O(m+n) 时间 / O(m+n) 额外空间",
             "原题允许在原数组上操作，所以这是不必要的空间开销。"),
        ],
        python=SOLUTIONS["ae9b3bd5f0c0ec14"][1],
        python_alt=MERGE_ARRAY_ALT,
        notes="两版都跑过，在 n=0、m=0、全大、全小、含重复值五组用例上结果一致。"
              "写进库里的是反向双指针版：它满足题目「原地」的要求。"
              "对照版保留了临时副本写法，用来具体展示 O(m) 空间代价。",
        time_c="O(m + n)",
        space_c="O(1)",
        why_c="每个元素最多被写入一次、被比较一次，因此时间与总长度成正比。"
              "额外空间只有 i、j、k 三个整数下标，与输入规模无关，故 O(1)。"
              "值得注意的是 k 与 i 同向递减使得写位置始终安全，这正是省掉缓冲的原因。",
        pitfalls=[
            "循环条件写成 while i >= 0 and j >= 0 却不补收尾：nums2 的剩余元素会丢失。",
            "循环条件写成 while i >= 0：nums2 剩下的大元素永远写不进去。",
            "忘记 k -= 1：所有元素都写在下标 m+n-1，结果只剩一个值。",
            "比较写成 nums1[i] < nums2[j] 直接取 nums2：逻辑对，但相等时行为与"
            "「先取 nums1」的稳定约定不一致。",
            "误以为从前往后也能 O(1) 空间：nums1 前段先被覆盖。",
        ],
        edge_cases=[
            "n = 0：nums2 为空，返回 nums1 原样。",
            "m = 0：nums1 前段为空，等价于整体拷贝 nums2。",
            "nums1 全部小于 nums2：i 一路走到底后，剩余的 nums2 项被依次写入。",
            "nums2 全部小于 nums1：j 很快到 -1，nums1 前段原地不动。",
            "长度悬殊（m=1, n=1000）：验证「剩余整段」在反向情形下同样正确。",
        ],
        tips="这题极短，所以每一句话都要有信息量。开场直接说「从后往前，O(1) 额外空间」，"
             "然后写代码。写完主动解释「k 追不上 i」这一点——它是唯一的难点。"
             "如果面试官问「为什么不用从前向后」，用具体的覆盖例子（nums1[0] 被 nums2[0] 覆盖）"
             "回答，比抽象解释更好。",
    ),
}

# ---------------------------------------------------------------------------
# 7. 反转链表 II LeetCode 92（freq 127）
# ---------------------------------------------------------------------------
CONTENT["cc9024199418b8b6"] = {
    "tldr": "哑结点 + 头插法：pre 停在 left 前一个，然后重复「把 cur 后面的结点插到 pre 后面」"
            "right-left 次。全程一趟扫描，O(1) 额外空间。",
    "why": "它把「区间反转」从「整体反转」里拆出来，是链表题里的分水岭："
           "整体反转只需要三个指针，而局部反转必须先解决「边界在哪、接点有几个」。"
           "同一套接点管理直接用在「K 个一组翻转链表」上。",
    "difficulty": "medium",
    "tags": ["linked-list", "in-place", "dummy-node", "reverse"],
    "entities": ["头插法", "哑结点", "接点管理", "区间反转"],
    "diagram": {
        "kind": "flow",
        "title": "反转 [2,4] 的指针布局（1→2→3→4→5, left=2, right=4）",
        "caption": "pre 最终停在结点 1；cur 停在 2（反转段的原头，反转后变成尾）；"
                   "每次把 cur.next 摘下来插到 pre 后面。两次插入后得到 1→4→3→2→5。"
                   "关键接点只有三个：pre.next（段头）、段尾.next（= 反转后的段头）、"
                   "以及原 cur 的 next 指向段后。",
        "alt": "链表 1 到 5，pre 指向 1、cur 指向 2、next 指向 3，说明头插法的三个指针",
        "svg": svg_chain(
            ["1", "2", "3", "4", "5"],
            "链表 1-2-3-4-5，pre 在 1、cur 在 2、next 在 3",
            marks=[(0, "pre"), (1, "cur"), (2, "next")]),
    },
    "concepts": [concept(
        "头插法（把结点「拔出来插到前面」）",
        "不改变段内结点的相对顺序反转，而是每次把 cur 后面的那个结点摘下来、"
        "插到 pre 的后面。重复 right-left 次后，这一段自然变成逆序。",
        "像从一摞牌里抽牌：每次抽走当前这张牌下面的那张，插到最上面。"
        "抽 n-1 次之后整摞牌正好反过来，而且你从没换过牌的位置。",
        "头插法改变的是 pre.next，而 pre 本身不动。很容易误以为「pre 要跟着走」——"
        "如果 pre 前进了，插入点就跑到段内了，结果会错乱。判断标准："
        "整个循环里 pre 是常量，只有 cur.next 与 pre.next 在变。",
        "链表的反转本质是「重连 next 指针」。头插法把「一次重连」拆成三次赋值"
        "（摘下来、接上去、更新 pre.next），每一步都不丢引用，"
        "所以不需要预先知道段长，也不需要递归。",
        "画一条链，把 pre 用方框圈住并标「不动」。cur 用另一个标记，"
        "每轮画一次「next 被摘下 → 插到 pre 后」的箭头变化，两轮画完。",
        ["链表结点与 next 指针", "哑结点", "循环次数与区间长度的关系"],
        ["为什么循环次数是 right-left 而不是 right-left+1？",
         "如果用「切段 → 整体反转 → 接回」的做法，需要记录几个接点？",
         "left == right 时循环体执行几次？结果应该是什么？"],
    )],
    "formulas": [],
    "selfCheck": {
        "claims": [
            "头插法版与「切段反转再拼接」版在 6 组用例上结果一致。",
            "额外空间 O(1)；循环次数恰为 right-left。",
        ],
        "uncertain": [
            "题目保证 1 ≤ left ≤ right ≤ n，实现依赖这个前提；"
            "若输入越界需要额外校验。",
        ],
    },
    "teaching": teaching(
        progressive=[
            lv("第 1 层 · 能写", "用哑结点把头插法实现出来。"),
            lv("第 2 层 · 能说清", "说清 pre 为什么不能动，以及循环次数为什么是 right-left。"),
            lv("第 3 层 · 能对比", "与「切段 + 整体反转 + 接回」对比，"
                                  "说出后者要管 4 个接点、前者只需 1 个插入点。"),
            lv("第 4 层 · 能迁移", "把区间反转推广到「K 个一组翻转」，"
                                  "说清外层循环与段内计数怎么配合。"),
        ],
        socratic=[
            qa("为什么需要哑结点？",
               "当 left == 1 时，被反转段的头就是整条链的头，"
               "没有哑结点就没有「pre」可用（没有结点指向它）。"
               "哑结点把 left == 1 这个特例消掉。"),
            qa("循环次数为什么是 right-left 次？",
               "头插法每次把「cur 后面的一个结点」搬到段头。段里有 right-left+1 个结点，"
               "把除 cur 之外的 right-left 个结点逐个搬到前面，就完成了整段反转。"),
            qa("段尾的 next 需要处理吗？",
               "不需要显式处理。cur 从一开始就指向段头，反转过程中它的 next 会被"
               "反复更新成「段内下一个」，最后自动指向原段尾之后的结点 —— 这正是需要的。"
               "这也是头插法比切段法少写两行接点的原因。"),
        ],
        mechanism="先把 pre 前进 left-1 步，停在反转段前一个结点。令 cur = pre.next（段头）。"
                  "重复 right-left 次：记 nxt = cur.next（要搬的结点），"
                  "cur.next = nxt.next（把它从原位置摘掉），nxt.next = pre.next（插到段头之前），"
                  "pre.next = nxt（段头更新为它）。整个过程中 pre 不变，"
                  "cur 始终是段尾，段头被不断替换。",
        boundary="只适用于「链表 + 局部区间反转」。若区间长度等于整链长度，"
                 "它就是标准反转链表（用哑结点仍然正确）。"
                 "若要求「按值反转」而不是「按下标区间」，需要先定位结点。"
                 "如果要求反转后返回新的头，哑结点 + dummy.next 也天然正确。",
        analogyBoundary="「抽牌插到最上面」的类比会让人以为操作对象是「整摞牌的顺序」——"
                        "实际改的只有 pre.next 和 cur.next 两个指针。"
                        "把注意力放在「牌的顺序」上，就写不出 O(1) 空间的实现。",
        misconceptions=[
            "让 pre 跟着 cur 走：插入点漂移，结果错乱。",
            "循环次数写成 right-left+1：多插一次，会把段后的结点也卷进来。",
            "忘记建哑结点，导致 left == 1 时越界或返回错误的头。",
            "把 nxt.next = pre.next 写成 nxt.next = cur：链会成环或丢结点。",
            "用「切段」思路但只记了 2 个接点：漏掉段尾与段后的连接。",
        ],
        ownAnalysis="这题最值得记的是「pre 不动、cur 恒为段尾」这个不变式。"
                    "链表题的复杂度几乎全在「有几个指针、各自指向哪、什么时候动」上；把不变式先写下来（哪怕只是在注释里），正确率会明显提升。"
                    "另外它演示了「局部问题 = 区间定位 + 区间内操作」的分解方式，同一套分解直接用在「K 个一组翻转」上。",
        officialNotes=[{'position': '官方题解给出「一次遍历 + 头插」的 O(1) 空间解法，并强调用哑结点统一 left == 1 的情形。', 'source': 'LeetCode 92 官方题解 · 反转链表 II'}],
        interviewAnswer="先说结构：「哑结点 + 头插法，pre 全程不动」。"
                        "然后强调两处细节：循环次数是 right-left，以及 pre 不前进。"
                        "写完用手动例子走一遍（1→2→3→4→5, left=2, right=4），边写边报三个指针的位置。"
                        "如果被问另一种做法，答「切段反转再拼接，但要管 4 个接点」。",
        prereq=["链表结点与指针操作", "哑结点的用法", "循环不变式"],
        next_steps=["做「K 个一组翻转链表」：把区间反转套进外层循环",
                    "做「两两交换链表中的节点」：K=2 的特例",
                    "做「反转链表」：区间为整链时的退化情形"],
    ),
    "problem": problem(
        title="反转链表 II（LeetCode 92）",
        statement="给你单链表的头指针 head 和两个整数 left 和 right，其中 left <= right。"
                  "请你反转从位置 left 到位置 right 的链表节点，返回反转后的链表。"
                  "位置从 1 开始计数。要求只遍历一次，额外空间 O(1)。",
        examples=[
            ("head = 1→2→3→4→5, left = 2, right = 4", "1→4→3→2→5",
             "只反转下标 2..4 的结点；结点 1 与 5 不动"),
            ("head = 5, left = 1, right = 1", "5", "left == right，循环体不执行"),
            ("head = 1→2→3, left = 1, right = 3", "3→2→1",
             "整链反转，哑结点让 left == 1 不再是特例"),
        ],
        idea="哑结点 + 头插法。把 pre 定位到 left 前一个结点（它全程不动），"
             "cur = pre.next 是反转段的头。重复 right-left 次："
             "把 cur 后面的结点摘下来插到 pre 的后面。这样段内结点被逐个搬到段头之前，"
             "自然形成逆序。",
        steps=[
            "dummy = ListNode(0, head)，pre = dummy。",
            "pre 前进 left-1 步，停在反转段前一个结点。",
            "cur = pre.next（反转段的原头，最终会变成段尾）。",
            "重复 right-left 次：nxt = cur.next；cur.next = nxt.next；"
            "nxt.next = pre.next；pre.next = nxt。",
            "返回 dummy.next。",
        ],
        whyItWorks="循环不变量：pre.next 到 cur 之间的结点已经是「原反转段中已处理的结点，"
                   "按逆序排列」，且 cur 始终是这段的尾、cur.next 依次指向原段中下一个未处理结点。"
                   "每次把 cur.next 摘到段前，段长 +1、段尾不变。"
                   "恰好执行 right-left 次后段内全部结点处理完毕，而此时 cur.next "
                   "已经是原段之后的第一个结点，所以段尾天然接对，无需额外处理。",
        alternatives=[
            ("切段 → 整体反转 → 接回", "O(n) 时间 / O(1) 空间",
             "思路更直白，适合先讲思路再写代码；但要管 4 个接点（pre、段头、段尾、段后），"
             "漏一个就断链。"),
            ("抽出到数组再重连", "O(n) 时间 / O(n) 空间",
             "链表题里最省脑子的写法，但额外空间 O(n)；面试里通常会被要求改成 O(1)。"),
            ("递归反转前 left-1 个结点", "O(n) 时间 / O(n) 栈空间",
             "面试官要求递归时用；栈深 O(n)，长链表有风险。"),
        ],
        python=SOLUTIONS["cc9024199418b8b6"][1],
        python_alt=REVERSE_II_ALT,
        notes="两版都跑过，在 left==right、整链反转、段在链头、段在链尾、两结点链表、"
              "单结点六组用例上结果一致。写进库里的是头插法（O(1) 空间、只需一个插入点）。",
        time_c="O(n)",
        space_c="O(1)",
        why_c="pre 只前进 left-1 步，之后循环 right-left 次，总步数 ≤ n，故时间 O(n)。"
              "全程只用 dummy、pre、cur、nxt 四个引用，与输入规模无关，故额外空间 O(1)。",
        pitfalls=[
            "让 pre 在循环里前进：插入点漂移，结果错乱。",
            "循环次数写成 right-left+1：把段后的结点也卷进反转。",
            "不建哑结点：left == 1 时没有 pre 可用。",
            "写成 nxt.next = cur：段内自成环，链尾丢失。",
            "摘结点时先改 pre.next 再记 nxt：nxt 已被覆盖，找到的是错误结点。",
        ],
        edge_cases=[
            "left == right：循环体不执行，原链表返回。",
            "left == 1 且 right == n：整链反转。",
            "left == 1, right == 1：完全不动。",
            "单结点：left = right = 1，返回该结点。",
            "right == n：验证段尾的 next 最终指向 None。",
            "left == 1 且 right < n：验证哑结点承担了段前接点。",
        ],
        tips="这题写对了还要说得清。开场：「哑结点 + 头插法，pre 全程不动」。"
             "写完用 1→2→3→4→5 / left=2 / right=4 手动走一轮，边写边报三个指针的指向。"
             "如果面试官问「还有别的做法吗」，答「切段反转再拼接，但要管理 4 个接点」，"
             "然后指出头插法的优势是只有一个插入点。",
    ),
}

# ---------------------------------------------------------------------------
# 8. 重排链表 LeetCode 143（freq 108）
# ---------------------------------------------------------------------------
CONTENT["ce573ed982fd7269"] = {
    "tldr": "三步走：快慢指针找中点 → 反转后半段 → 两条链交替合并。"
            "O(n) 时间、O(1) 空间。最容易漏的一步是反转前把 slow.next 置 None（断开成环）。",
    "why": "它是一道「三件基础件的组合题」：快慢指针找中点（876）、反转链表（206）、"
           "合并两条链（21）。面试官用它检查你能不能把零散技巧串成一条完整的流水线，"
           "而漏掉断链那一步会直接导致死循环——这是最典型的「看起来对但跑不起来」。",
    "difficulty": "medium",
    "tags": ["linked-list", "two-pointers", "fast-slow", "reverse", "in-place"],
    "entities": ["快慢指针", "中点", "后半段反转", "交替合并"],
    "diagram": {
        "kind": "flow",
        "title": "重排链表的三步（1→2→3→4→5→6）",
        "caption": "第一步用快慢指针把链切成 [1,2,3] 与 [4,5,6]；第二步反转后半段得 [6,5,4]；"
                   "第三步交替取两条链的头部拼成 1→6→2→5→3→4。"
                   "奇偶长度的分界不同：长度 4 时切成 [1,2] 与 [3,4]，"
                   "所以找中点用的是 while fast.next and fast.next.next。",
        "alt": "重排链表的三步：切分、反转后半段、交替合并，得到 1-6-2-5-3-4",
        "svg": svg_trace(
            [
                {"label": "① 切分", "cells": ["1", "2", "3", "4", "5", "6"], "hi": [2],
                 "note": "slow 停在 3（前半段尾），后半段是 4→5→6；此时必须 slow.next = None"},
                {"label": "② 反转", "cells": ["6", "5", "4"],
                 "note": "反转 4→5→6 得到 6→5→4，这就是交替合并的第二个来源"},
                {"label": "③ 合并", "cells": ["1", "6", "2", "5", "3", "4"], "hi": [1, 3],
                 "note": "l1 取 1 接 6，l2 取 5 接 2，l1 取 3 接 4，直到 l2 走完"},
            ],
            "重排链表的三个步骤与中间状态"),
    },
    "concepts": [concept(
        "为什么「找到中点」要用 fast.next 双条件",
        "while fast.next and fast.next.next 让 slow 最终停在「前半段的最后一个结点」"
        "（长度为偶数时）或「正中间结点」（长度为奇数时）。写法差一个 .next，"
        "切分点就会偏一格。",
        "像把一根火腿肠对折再切一刀：折点必须落在「两半的分界」上，"
        "折偏一格，两半长度就不对了。",
        "这条 while 条件不能简单记成「快指针走两步」。长度 4 时 [1,2]|[3,4] 是正确切分；"
        "如果写成 while fast and fast.next，slow 会停在 2 与 3 之间偏右的位置，"
        "切出 [1,2,3]|[4]，后半段只有一个结点，交替合并的结果就退化了。"
        "判断方法：始终以「slow 是前半段最后一个」为目标反推条件。",
        "快指针每轮走 2 步、慢指针走 1 步，因此慢指针走过的距离约为总长的一半。"
        "双条件（fast.next 与 fast.next.next 都存在）确保 fast 能安全地跳两步，"
        "同时让循环在 slow 到达「前半段末」时停止，而不是多走一格。",
        "画六个格子，标两组箭头（fast 每次跳两格、slow 跳一格），"
        "把最终 slow 的位置圈出来，再用一条竖线表示切分。然后单独画反转后的后半段。",
        ["快慢指针", "链表反转", "两条链交替合并"],
        ["为什么合并循环的条件是 while l2 而不是 while l1 and l2？",
         "如果忘记 slow.next = None，会发生什么？",
         "长度是奇数时（如 5 个结点），切分后两半长度分别是多少？"],
    )],
    "formulas": [],
    "selfCheck": {
        "claims": [
            "O(1) 空间版与「结点装数组再重连」版在 6 组用例上结果一致。",
            "切分点必须是「前半段最后一个」，否则奇偶长度的结果都会错。",
        ],
        "uncertain": [
            "「重排」的定义（L0→Ln→L1→Ln-1→…）对单结点与双结点链表给出的是原序，"
            "这一点各平台一致，但容易被误认为应该交换。",
        ],
    },
    "teaching": teaching(
        progressive=[
            lv("第 1 层 · 能写", "实现快慢找中点 → 反转后半段 → 交替合并三步。"),
            lv("第 2 层 · 能说清", "说清为什么必须 slow.next = None（否则成环死循环）。"),
            lv("第 3 层 · 能算代价", "分析 O(n) 时间、O(1) 空间，并说明为什么合并循环"
                                    "只需判断 l2。"),
            lv("第 4 层 · 能取舍", "说出数组法（O(n) 空间、代码短）在面试中的适用场景，"
                                  "以及为什么 O(1) 版本更被看重。"),
        ],
        socratic=[
            qa("为什么合并时循环条件是 while l2？",
               "因为切分保证前半段长度 ≥ 后半段（奇数时前半段多一个）。"
               "l2 走完时 l1 要么同时走完，要么还剩一个结点且已经处于正确位置。"
               "用 while l1 and l2 会在最后漏接一个结点。"),
            qa("忘记 slow.next = None 会怎样？",
               "前半段的尾仍然指向后半段的头，而反转后的后半段也指回前半段，"
               "两条链连成一条环。合并过程中指针会绕圈，程序死循环或输出错乱。"),
            qa("为什么可以只用 O(1) 空间？",
               "因为三步都是原地改指针：找中点只用两个游标，反转只用三个游标，"
               "合并只用两个游标。没有创建任何新结点，也没有辅助数组。"),
        ],
        mechanism="第一步的快慢指针把链切成前半段与后半段，切完立刻断链使两者独立。"
                  "第二步原地反转后半段（用 prev/cur/nxt 三指针），使后半段从「尾部在前」"
                  "变成「尾部在后」，于是交替取头就能得到 Ln、L1、Ln-1… 的顺序。"
                  "第三步交替插接：每次把 l2 的当前结点插到 l1 当前结点之后，"
                  "再把 l1 前进到原来的下一个结点。",
        boundary="适用于单链表、允许原地修改。若不允许修改原链表，需要先复制（O(n) 空间）。"
                 "若链表有环，快慢指针会死循环——本题假定无环。"
                 "双向链表不适用（前后指针要同时维护），要另外处理 prev 指针。",
        analogyBoundary="「对折火腿肠」的类比会让人以为两半是等长的 —— 奇数长度时前半段"
                        "比后半段多一个结点，这正是合并循环只判 l2 的原因。"
                        "按「等长」直觉写代码，奇数长度会漏接最后一个结点。",
        misconceptions=[
            "忘记把 slow.next 置 None：两条链成环，合并时死循环。",
            "快慢指针写成 while fast and fast.next：切分点偏右，后半段少一个结点。",
            "合并时写成 while l1 and l2：奇数长度时最后一个结点丢失。",
            "以为要创建新结点：本题要求原地改指针，额外空间应为 O(1)。",
            "先合并再反转后半段：顺序错了，插进去的结点也会被反转。",
        ],
        ownAnalysis="这道题的价值在于「组合」：它本身没有新算法，而是把快慢指针、链表反转、交替合并三件已有零件串成流水线。"
                    "面试里这类题的区分度其实更高——因为任何一件零件记错都会让整个程序崩，而崩的方式往往是死循环（成环）而不是报错。"
                    "养成「每次断链/接链后画一遍指针图」的习惯，比背题更有用。",
        officialNotes=[{'position': '官方题解明确要求「不能只改变结点内部的值」，并把最优解定为「找中点 + 反转后半段 + 交替合并」的 O(1) 空间版本。', 'source': 'LeetCode 143 官方题解 · 重排链表'}],
        interviewAnswer="开口报三步，第二步末尾主动强调「必须把 slow.next 置 None，否则成环死循环」——这句话通常是面试官在等的。"
                        "然后用手动例子（长度 4 与长度 5 各一次）展示奇偶两种切分的差别。"
                        "最后报 O(n) 时间、O(1) 空间，并说明「数组法也行但空间是 O(n)」。",
        prereq=["快慢指针找中点", "链表反转", "哑结点与尾插"],
        next_steps=["做「回文链表」：同样用「找中点 + 反转后半段」但只做比较",
                    "做「排序链表」：找中点 + 归并",
                    "做「K 个一组翻转链表」，体会「切段 + 反转 + 接回」的通用套路"],
    ),
    "problem": problem(
        title="重排链表（LeetCode 143）",
        statement="给定一个单链表 L 的头节点 head，单链表 L 表示为 L0 → L1 → … → Ln-1 → Ln，"
                  "请将其重新排列后变为：L0 → Ln → L1 → Ln-1 → L2 → Ln-2 → …。"
                  "不能只是单纯改变结点内部的值，而需要进行实际的结点交换。"
                  "要求 O(1) 额外空间。",
        examples=[
            ("head = 1→2→3→4", "1→4→2→3", "切成 [1,2] 与 [3,4]，反转后半段得 4→3，交替合并"),
            ("head = 1→2→3→4→5", "1→5→2→4→3",
             "长度为奇数：切成 [1,2,3] 与 [4,5]，反转得 5→4，合并到前半段用尽"),
            ("head = 1→2", "1→2", "长度 2 时重排结果等于原序"),
        ],
        idea="三步流水线：① 快慢指针找到前半段的最后一个结点，断链；"
             "② 反转后半段；③ 把两条链交替合并（每次把一个后半段结点插到前半段结点之后）。",
        steps=[
            "若 head 为空或只有一个结点，直接返回。",
            "slow = fast = head；while fast.next and fast.next.next 时 slow、fast 各前进。",
            "prev, cur = None, slow.next；slow.next = None（断开，否则成环）。",
            "反转：while cur，把 cur.next 暂存、cur.next = prev、prev = cur、cur = nxt。",
            "合并：l1 = head，l2 = prev；while l2：暂存 l1.next 与 l2.next，"
            "l1.next = l2，l2.next = n1，然后 l1, l2 = n1, n2。",
            "返回 head。",
        ],
        whyItWorks="切分保证前半段长度 ≥ 后半段（差不超过 1），反转使后半段成为「从尾部起的逆序」。"
                   "于是交替取头就能得到 L0, Ln, L1, Ln-1 … 的目标序列。"
                   "断链是正确性前提：不断链时前半段尾指向后半段头、反转后后半段头又指回前半段，"
                   "两条链会连成环，合并过程无法终止。",
        alternatives=[
            ("结点装进数组再重连", "O(n) 时间 / O(n) 空间",
             "面试时间紧张或只想先给出正确解时用；核心就 4 行，但额外空间 O(n)，"
             "面试官通常会追问 O(1) 版本。"),
            ("递归（每次取尾结点插到头部）", "O(n²) 时间 / O(n) 栈空间",
             "最直观但效率最差的写法，只适合作为「为什么不能用」的对照。"),
            ("双端队列缓存结点", "O(n) 时间 / O(n) 空间",
             "本质同数组法，只是用了 deque；同样不满足 O(1) 空间要求。"),
        ],
        python=SOLUTIONS["ce573ed982fd7269"][1],
        python_alt=REORDER_LIST_ALT,
        notes="两版都跑过，在单结点、双结点、长度 3/4/5/6 六组用例上结果一致。"
              "写进库里的是 O(1) 空间的三步版；数组版保留为对照，"
              "它体现了「代码更短 vs 空间更省」的取舍。",
        time_c="O(n)",
        space_c="O(1)",
        why_c="找中点走 n/2 步，反转走 n/2 步，合并走 n/2 步，合计 O(n)。"
              "三步都只改指针、不新建结点，只用常数个游标，故额外空间 O(1)。"
              "注意 head 本身被复用为前半段头，这不算额外空间。",
        pitfalls=[
            "忘记 slow.next = None：两条链连成环，合并阶段死循环。",
            "快慢指针条件写成 while fast and fast.next：切分点偏右，奇数长度结果错。",
            "合并循环写成 while l1 and l2：奇数长度时最后一个结点被丢掉。",
            "反转时没有先暂存 cur.next 就改指针：后半段丢失，链断裂。",
            "以为必须新建结点：本题要求实际结点交换，额外空间应为 O(1)。",
        ],
        edge_cases=[
            "空链表 / 单结点：提前返回。",
            "两结点 [1,2]：结果 [1,2]（不是 [2,1]）。",
            "长度 3 [1,2,3] → [1,3,2]。",
            "长度 4 [1,2,3,4] → [1,4,2,3]。",
            "长度 10^4：验证 O(n) 时间与不会爆栈。",
        ],
        tips="这题考察的是「三件基础件能不能串起来」，所以表达比代码重要。"
             "开口先报三步，第二步末尾主动说「这里必须断开，否则成环」——"
             "这句话往往是面试官在等的。然后手动走长度 4 的例子自证。"
             "被追问空间时说「O(1)，因为全程只改指针」，再补「数组法也行，但那是 O(n) 空间」。",
    ),
}

# ---------------------------------------------------------------------------
# 9. 字符串相加 LeetCode 415（freq 102）
# ---------------------------------------------------------------------------
CONTENT["8cfadace34fdffa0"] = {
    "tldr": "模拟竖式加法：两个下标从末尾往前走，逐位相加并维护 carry，"
            "循环条件写成「i >= 0 或 j >= 0 或 carry」三选一，"
            "最后把结果逆序拼起来。",
    "why": "它考的是「不用大整数类型时怎么算」，因此是「模拟题」的模板。"
           "同一套逐位 + 进位的骨架直接用在二进制求和、链表两数相加、"
           "以及任意进制的加法上。面试里也会用它检查你对循环边界（尤其是"
           "最高位进位）的处理习惯。",
    "difficulty": "easy",
    "tags": ["string", "math", "simulation", "carry"],
    "entities": ["竖式加法", "进位", "大整数模拟"],
    "diagram": {
        "kind": "flow",
        "title": "竖式模拟（num1 = \"456\", num2 = \"77\"）",
        "caption": "两级指针分别从两个字符串末尾往前走。6+7=13 → 本位 3、进位 1；"
                   "5+7+1=13 → 本位 3、进位 1；4+0+1=5 → 本位 5、进位 0。"
                   "得到的位序列是 3,3,5，逆序拼装成 \"533\"。"
                   "注意每轮都要处理「某个数已经走完」的情况（补 0）。",
        "alt": "字符串 456 与 77 逐位相加的状态：本位与进位的三次变化",
        "svg": svg_trace(
            [
                {"label": "第 1 位", "cells": ["6 + 7"], "hi": [0],
                 "note": "本位 13 % 10 = 3，进位 13 // 10 = 1 → 记下 3"},
                {"label": "第 2 位", "cells": ["5 + 7 + 1"], "hi": [0],
                 "note": "本位 13，记下 3，进位 1"},
                {"label": "第 3 位", "cells": ["4 + 0 + 1"], "hi": [0],
                 "note": "num2 已走完补 0；本位 5，进位 0"},
                {"label": "第 4 位", "cells": ["carry = 0"],
                 "note": "没有位可加且进位为 0 → 循环结束"},
                {"label": "逆序拼装", "cells": ["5", "3", "3"],
                 "note": "低位先产出，所以要反转后再 join → \"533\""},
            ],
            "字符串相加时逐位相加与进位的状态变化"),
    },
    "concepts": [concept(
        "循环条件必须包含 carry",
        "while i >= 0 or j >= 0 or carry 三个条件缺一不可。"
        "carry 单独成立时循环还得再走一轮，把最高位进位写进结果。",
        "像「再加一位」：两个数都数完了，但手里还攥着一进位，"
        "必须再写一位出来，否则结果少一位。",
        "只在 i、j 都进位时才想到 carry 是不够的。经典反例：\"9\" + \"1\" = \"10\"——"
        "i、j 在第二轮都已经是 -1，如果循环条件写成 while i >= 0 or j >= 0，"
        "结果会变成 \"0\"（丢掉最高位的 1）。这个错在大多数用例上不会暴露，"
        "只有「最高位相加产生进位」的输入才会。",
        "竖式加法的每一位只依赖「两个加数当前位 + 上一轮进位」，因此可以自低位向高位"
        "单向推进，不需要回溯。carry ∈ {0, 1}，所以循环最多比 max(len1, len2) 多走一轮。",
        "把两个数右对齐画成两行，下面再画一行放结果。逐列从右往左算，"
        "每列上方标出进位小数字。五列画完就能看出逆序拼装的必要性。",
        ["字符串遍历与下标", "取模与整除", "列表逆序（reversed / [::-1]）"],
        ["为什么结果需要反转？",
         "num1 = \"9\", num2 = \"1\" 时，循环执行了几轮？",
         "如果要求返回不带头零的结果，本算法已经满足了吗？"],
    )],
    "formulas": [],
    "selfCheck": {
        "claims": [
            "模拟版与 int() 版在 7 组用例（含最高位进位、长串）上结果一致。",
            "循环最多执行 max(len1, len2) + 1 轮。",
        ],
        "uncertain": [
            "Python 的 int 没有溢出问题，所以「必须模拟」这个前提只在弱类型语言"
            "或面试明确禁止大整数时才真正成立；面试里应当说明这一点。",
        ],
    },
    "teaching": teaching(
        progressive=[
            lv("第 1 层 · 能写", "写出逐位相加 + 进位的模拟循环。"),
            lv("第 2 层 · 能说清", "说清为什么循环条件必须包含 carry，并用 \"9\"+\"1\" 举例。"),
            lv("第 3 层 · 能算代价", "分析 O(max(m,n)) 时间与 O(max(m,n)) 空间"
                                    "（结果本身），说明没有比这更好的空间。"),
            lv("第 4 层 · 能推广", "把它推广到二进制求和、链表两数相加、任意进制加法，"
                                  "说清只有「取模基数」和「取位方式」在变。"),
        ],
        socratic=[
            qa("\"9\" + \"1\" 会在哪一步暴露出循环条件写错？",
               "第二轮：i 与 j 都已为 -1，只有 carry = 1。若条件不含 carry，循环直接结束，"
               "结果是 \"0\" 而不是 \"10\"。"),
            qa("为什么可以边算边拼、最后反转，而不是一开始就倒着遍历？",
               "两种都可以。边算边 append 最后 reverse 更符合「低位到高位」的自然顺序；"
               "也可以先对齐、从高位往低位写但需要额外记录进位传播，反而更复杂。"),
            qa("Python 里直接 int(num1) + int(num2) 有什么问题？",
               "结果正确，但面试考的就是模拟。Python 的大整数没有溢出，"
               "所以这个「捷径」在 Python 里甚至更可靠——必须说明你是在按要求写模拟。"),
        ],
        mechanism="每一轮取出两个数的当前位（越界补 0），与上一轮进位相加得到 s。"
                  "本位 = s % 10 追加到结果列表，新进位 = s // 10。"
                  "三个条件（i >= 0、j >= 0、carry）共同决定是否继续，"
                  "保证进位被完整传播。最后把结果列表反转并拼接。",
        boundary="适用于十进制字符串整数。改成二进制求和时把 10 换成 2 即可（LeetCode 67）。"
                 "改成链表两数相加时，把「下标取位」换成「指针取结点」，"
                 "并注意链表本来就是低位在前，不需要反转。"
                 "若输入允许前导零或负号，需要额外归一化，本算法不处理。",
        analogyBoundary="「竖式加法」的类比会让人下意识认为「两个数位数相同」，"
                        "于是在某一位越界时忘记补 0。实际两数长度任意，"
                        "每轮都必须独立判断 i、j 是否仍然有效。",
        misconceptions=[
            "循环条件漏掉 carry：\"9\"+\"1\" 得到 \"0\"。",
            "忘记在结果里反转：得到 \"335\" 而不是 \"533\"。",
            "越界时直接用 num1[i] 而不判 i >= 0：IndexError 或错位的字符。",
            "把进位当成布尔值：本题进位只会是 0 或 1，但同一套代码用于乘法时会 >1，"
            "所以要按整数处理。",
            "以为 Python 里必须模拟：Python 大整数无溢出，说明理由即可，不必假装。",
        ],
        ownAnalysis="模拟题的通用套路是「对齐 + 逐位 + 进位」三件套。"
                    "真正容易错的是循环边界：必须让「还有进位」成为一个独立的继续条件。"
                    "这条经验在乘法、阶乘、任意进制转换里都会再遇到——凡是「低位影响高位」的计算，边界都要多留一轮。",
        officialNotes=[{'position': '官方题解给出「模拟竖式」解法，并强调不能使用内建大整数类型；Python 因整数无溢出，官方也提示了这一点。', 'source': 'LeetCode 415 官方题解 · 字符串相加'}, {'position': '配套题「二进制求和」（67）与「两数相加」（2）共用同一骨架，只是基数或取位方式不同。', 'source': 'LeetCode 67 / 2'}],
        interviewAnswer="两个关键句：循环条件必须含 carry、结果用 list + join 而不是字符串首插。"
                        "开场就抛出 \"9\"+\"1\" 这个反例，直接证明你知道边界在哪。"
                        "如果被问「Python 不是有 int 吗」，如实说明有、但按要求写模拟，并且这个骨架能直接复用到二进制求和与链表两数相加。",
        prereq=["字符串遍历", "取模与整除", "列表与字符串的相互转换"],
        next_steps=["做「二进制求和」：把基数换成 2，其余不变",
                    "做「两数相加」（链表）：本低位在前的版本",
                    "做「字符串相乘」：进位会大于 1，需要二维累加"],
    ),
    "problem": problem(
        title="字符串相加（LeetCode 415）",
        statement="给定两个字符串形式的非负整数 num1 和 num2，计算它们的和并同样以字符串形式返回。"
                  "不能使用任何內建的大整数库，也不能直接将输入的字符串转换为整数形式。",
        examples=[
            ("num1 = \"11\", num2 = \"123\"", "\"134\"", "位数不同，需要按低位对齐"),
            ("num1 = \"456\", num2 = \"77\"", "\"533\"",
             "6+7=13 进位 1；5+7+1=13 进位 1；4+0+1=5"),
            ("num1 = \"0\", num2 = \"0\"", "\"0\"", "最小用例，不进位也不越界"),
            ("num1 = \"9\", num2 = \"1\"", "\"10\"",
             "最高位进位：i、j 都已越界但 carry=1，循环必须再走一轮"),
        ],
        idea="模拟竖式加法。i、j 分别从两个字符串末尾往前走，carry 记录进位。"
             "每轮取下一位（越界补 0）与 carry 相加，本位是 s % 10，"
             "新进位是 s // 10。循环条件包含 carry，最后把收集到的位反转拼接。",
        steps=[
            "i, j, carry = len(num1) - 1, len(num2) - 1, 0；out = []。",
            "while i >= 0 or j >= 0 or carry："
            "a = int(num1[i]) if i >= 0 else 0；b = int(num2[j]) if j >= 0 else 0；"
            "s = a + b + carry；out.append(str(s % 10))；carry = s // 10；i -= 1；j -= 1。",
            "return \"\".join(reversed(out))。",
        ],
        whyItWorks="竖式加法的正确性来自「每一位只依赖两个加数的当前位与低位进位」，"
                   "因此从低位向高位单向推进是充分的。三个循环条件分别覆盖三类还要继续算的情形："
                   "num1 还有位、num2 还有位、还有未写出的进位。"
                   "越界补 0 保证了长度不等时也不会漏算或错位。",
        alternatives=[
            ("int() 直接相加", "O(n) 时间（大整数加法本身）/ O(n) 空间",
             "Python 里结果正确且更快，但题目明确禁止；只适合用来说明「模拟是要求而非必要」。"),
            ("先补齐前导零再逐位相加", "O(max(m,n)) 时间 / O(max(m,n)) 空间",
             "思路更整齐，但要额外做补零与索引对齐，代码反而更长。"),
            ("递归处理末位", "O(max(m,n)) 时间 / O(max(m,n)) 栈空间",
             "面试官要求递归时用；栈深与位数成正比，长串有风险。"),
        ],
        python=SOLUTIONS["8cfadace34fdffa0"][1],
        python_alt=ADD_STRINGS_ALT,
        notes="两版都跑过，在 7 组用例（含 \"9\"+\"1\"、5000 位长串、位数悬殊）上结果一致。"
              "写进库里的是模拟版；int 版保留为对照，用来说明「为什么不能这么写」"
              "比「不知道能不能这么写」更清楚。",
        time_c="O(max(m, n))",
        space_c="O(max(m, n))",
        why_c="每轮消掉至少一个有效位，最多执行 max(m, n) + 1 轮，故时间与较长串成正比。"
              "空间由结果列表决定，结果长度也为 max(m, n) + 1，故同为 O(max(m, n))。"
              "这个空间无法避免：结果本身就必须占这么多位置。",
        pitfalls=[
            "循环条件只写 i >= 0 or j >= 0：\"9\"+\"1\" 会输出 \"0\"，丢掉最高位。",
            "忘记反转结果列表：得到低位在前的 \"335\"。",
            "越界时不补 0 而直接取字符：IndexError 或取到错误位。",
            "在循环里用 out = str(s % 10) + out 做字符串首插：每次 O(n)，总计 O(n²)。",
            "把 carry 当布尔值：本題进位是 0/1，但同一骨架用于乘法时进位会更大。",
        ],
        edge_cases=[
            "\"0\" + \"0\" = \"0\"。",
            "\"9\" + \"1\" = \"10\"：carry 单独成立。",
            "\"1\" + \"9999\"：位数悬殊，验证补 0。",
            "\"999...9\" + \"1\"：连续进位产生新最高位。",
            "5000 位 + 5000 位：验证 O(n) 复杂度与无递归爆栈。",
        ],
        tips="两个关键词：循环条件里的 carry、以及用 list + join 而不是字符串首插。"
             "开场主动提 \"9\"+\"1\" 这个反例，直接证明你理解边界在哪。"
             "如果被问「能不能用 int」，如实说「Python 的大整数没溢出，"
             "所以能；但题目要求模拟，而且这个骨架能直接用到二进制求和和链表两数相加」。",
    ),
}

# ---------------------------------------------------------------------------
# 10. 环形链表 LeetCode 141（freq 91）
# ---------------------------------------------------------------------------
CONTENT["fa012b290cb172ce"] = {
    "tldr": "Floyd 判圈：慢指针走 1 步、快指针走 2 步。有环必定相遇，"
            "无环则快指针先撞到 None。O(n) 时间、O(1) 空间。",
    "why": "它把「两个速度不同的观察者」这一招引入链表，是「龟兔」系列的入口。"
           "面试常接着追问「环的入口在哪」（142），那时需要用到「相遇后一个指针回到头部」"
           "这个反直觉的结论。这道题考的是你能否讲清「为什么一定会相遇」。",
    "difficulty": "easy",
    "tags": ["linked-list", "two-pointers", "floyd", "cycle-detection"],
    "entities": ["Floyd 判圈", "龟兔算法", "快慢指针"],
    "diagram": {
        "kind": "flow",
        "title": "有环与无环两种走向（环长 3，入口在结点 2）",
        "caption": "有环时：慢指针每轮 1 步、快指针 2 步，由于快指针相对慢指针每轮净追 1 步，"
                   "两者必然在环上某点相遇。无环时：快指针先变成 None（或 fast.next 为 None），"
                   "循环条件失效即返回 False。注意必须先判 fast 和 fast.next，"
                   "否则 fast.next.next 会触发 AttributeError。",
        "alt": "环形链表中快慢指针追逐相遇的示意图，以及无环链表上快指针先到末尾",
        "svg": svg_chain(
            ["1", "2", "3", "4", "5"],
            "链表中一段带环的结构：结点 5 指回结点 2",
            marks=[(1, "环入口"), (4, "环）")]),
    },
    "concepts": [concept(
        "相对速度：为什么一定会相遇",
        "在环上，快指针相对慢指针的速度是每轮 1 步。既然相对速度恒为 1，"
        "快指针迟早会「追上」慢指针，且追上的位置是确定的。",
        "像两个人在环形跑道上跑步，快的那个每圈都比慢的多跑一段，"
        "多出来的距离累积起来总会让他从背后赶上前面那个人。",
        "「相对速度恒为 1」只在环内成立。**进环之前**两者距离是变化的，"
        "所以不能断言「一定在第几轮相遇」——只能说一定会相遇，"
        "具体在第几轮取决于环长与入口位置。若把快指针改成走 3 步，"
        "相对速度变成 2，格点若不相容就可能永远错过（例如环长 2 时快 3 慢 1 会跳过）。"
        "这也是「快指针只能快 1 步相对量」的直觉来源。",
        "设环长为 C。当慢指针刚进环时，快指针已在环内某处。此后每轮快指针相对慢指针"
        "前进 1 格，因此最多再走 C-1 轮就会落在同一格上。因此总步数不超过「进环前步数 + C」，"
        "整体 O(n)。",
        "画一个带环的跑道，每轮给两个点标位置并连线。三轮内就能看到快指针从后面追上，"
        "把相撞那一刻用实心点标出。",
        ["链表遍历", "循环条件与空指针安全", "抽屉原理"],
        ["为什么循环条件是 while fast and fast.next？",
         "无环时快指针会先到 None 还是先到最后一个结点？",
         "如果环长为 2、快指针每轮走 3 步，还能保证相遇吗？"],
    )],
    "formulas": [],
    "selfCheck": {
        "claims": [
            "Floyd 版与哈希版在 5 组用例（含自环、双结点环、无环）上结论一致。",
            "无环时循环最多执行 n/2 轮；有环时总步数为 O(n)。",
        ],
        "uncertain": [
            "「环的入口」需要额外的数学结论（相遇点到入口的距离 = 头到入口的距离），"
            "本题不要求，但 142 会用到，此处不展开证明。",
        ],
    },
    "teaching": teaching(
        progressive=[
            lv("第 1 层 · 能写", "写出快慢指针循环与相遇判断。"),
            lv("第 2 层 · 能说清", "说清「相对速度恒为 1」为什么保证相遇，"
                                  "以及循环条件为何要双判空。"),
            lv("第 3 层 · 能算代价", "说明 O(n) 时间与 O(1) 空间，并解释为什么比哈希法更划算。"),
            lv("第 4 层 · 能延伸到 142", "说出「相遇后把慢指针放回头部、两者同速前进，"
                                       "再次相遇点就是环入口」这个结论，并说明它依赖一次额外推导。"),
        ],
        socratic=[
            qa("为什么 fast 和 fast.next 都要判空？",
               "循环体里要访问 fast.next.next。若 fast 是 None，先崩；"
               "若 fast.next 是 None（奇数长度的无环链），fast.next.next 也崩。"
               "两个条件合起来保证「快指针能安全地跳两步」。"),
            qa("为什么不用哈希表更省事？",
               "哈希表也正确（O(n) 时间），但需要 O(n) 额外空间；"
               "Floyd 是 O(1) 空间。面试官通常就是要 O(1)，所以要能说清它的原理。"),
            qa("相遇时慢指针走了多远？",
               "慢指针最多走「进环前步数 + 环长」，快指针走了两倍。"
               "注意不是「慢指针走一圈」——慢指针在相遇前可能还没走满一圈。"),
        ],
        mechanism="慢指针每轮前进 1、快指针前进 2。若链表无环，快指针必定先到达末尾，"
                  "循环因 fast 为 None 或 fast.next 为 None 而结束，返回 False。"
                  "若有环，两者最终都会进入环并永远循环；由于快指针相对慢指针每轮净追 1 格，"
                  "必然在某轮落在同一结点上，此时返回 True。",
        boundary="只判「有没有环」。若还需要「环的入口」或「环长」，需要额外推导："
                 "相遇后把一个指针放回头部、两者同速前进，再次相遇即为入口；"
                 "从相遇点继续走一圈即为环长。若链表可能被并发修改，Floyd 的相遇保证不再成立。",
        analogyBoundary="「环形跑道追人」的类比会让人以为快指针一定「绕了一圈才追上」——"
                        "实际上相遇可能发生在快指针的第一圈之内，慢指针也可能还没走满一圈。"
                        "按「追了一整圈」估算步数会得到偏大的结果。",
        misconceptions=[
            "循环条件只写 while fast：fast.next.next 遇到 fast.next 为 None 时崩。",
            "比较慢指针与快指针的**值**而不是结点身份：值相同不代表同一结点。",
            "以为有环时快指针绝不会到 None：有环时确实不会，但代码仍然需要双判空以覆盖无环。",
            "以为 Floyd 用 O(n) 空间：它是 O(1)，这正是它优于哈希的地方。",
            "把「相遇」理解成「快指针套圈」：相对速度 1 意味着追上，不需要整圈。",
        ],
        ownAnalysis="Floyd 判圈的真正知识点是「相对速度」，而不是「快慢指针」这四个字。"
                    "一旦理解「快指针相对慢指针每轮净追 1 格」，就能自己推出为什么一定会相遇、以及为什么快指针不能改走 3 步。"
                    "同一套相对运动的思路还能解释 142 的「相遇后重置指针找入口」，值得把它当成一个推导而不是两条结论来记。",
        officialNotes=[{'position': '官方题解给出「哈希表」与「Floyd 判圈」两种解法，并把后者作为满足 O(1) 空间要求的解法。', 'source': 'LeetCode 141 官方题解 · 环形链表'}],
        interviewAnswer="重点讲清「相对速度恒为 1，所以必然相遇」，而不是背代码。"
                        "写代码时显式写出 `while fast and fast.next` 并解释双判空的原因（要安全访问 fast.next.next）。"
                        "如果面试官顺势问 142，答「相遇后把慢指针放回头部、两者同速前进，再次相遇点即入口」，并说明这需要额一次推导。",
        prereq=["链表遍历", "循环条件与空指针", "两个速度不同的指针"],
        next_steps=["做「环形链表 II」：求出环的入口结点",
                    "做「寻找重复数」：数组版的 Floyd 判圈（把值当下标）",
                    "做「链表的中间结点」：同一个快慢指针骨架"],
    ),
    "problem": problem(
        title="环形链表（LeetCode 141）",
        statement="给你一个链表的头节点 head，判断链表中是否有环。如果链表中有某个节点，"
                  "可以通过连续跟踪 next 指针再次到达，则链表中存在环。"
                  "要求使用 O(1) 额外空间。",
        examples=[
            ("head = 3→2→0→-4，尾结点连回下标 1（pos = 1）", "true",
             "从结点 2 起可以沿 next 无限循环"),
            ("head = 1→2，尾结点连回下标 0（pos = 0）", "true", "两结点互指成环"),
            ("head = 1，pos = -1", "false", "单结点且 next 为 None"),
            ("head = []（空链表）", "false", "空链表无环"),
        ],
        idea="Floyd 判圈（龟兔算法）。慢指针每轮走 1 步，快指针每轮走 2 步。"
             "若存在环，两者最终必然在同一结点相遇；若不存在环，快指针会先到达 None，"
             "此时返回 False。",
        steps=[
            "slow = fast = head。",
            "while fast and fast.next：slow = slow.next；fast = fast.next.next；"
            "若 slow is fast 则返回 True。",
            "循环正常结束说明无环，返回 False。",
        ],
        whyItWorks="无环时快指针以两倍速度前进，必然先触达链尾，循环条件失效。"
                   "有环时两者都进入环且不再退出；设环长 C，快指针相对慢指针每轮净追 1 格，"
                   "因此最多再走 C-1 轮就会落在同一格上。相遇即证明存在环，"
                   "且发生在 O(n) 步之内，故时间与空间分别为 O(n) 与 O(1)。",
        alternatives=[
            ("哈希表存访问过的结点", "O(n) 时间 / O(n) 空间",
             "逻辑最直观，且能顺带回答「环入口在哪」；代价是 O(n) 额外空间，"
             "面试若要求 O(1) 就得换回 Floyd。"),
            ("修改结点值做标记", "O(n) 时间 / O(1) 空间",
             "能省空间但会破坏输入，且值域受限时不安全；面试里属于「不推荐」方案。"),
            ("记录步数上限", "O(n) 时间 / O(1) 空间",
             "走 n 步还没结束就判定有环；实现简单但依赖「已知链表长度」，"
             "本题长度未知所以不成立。"),
        ],
        python=SOLUTIONS["fa012b290cb172ce"][1],
        python_alt=HAS_CYCLE_ALT,
        notes="两版都跑过，在自环、双结点环、无环单结点、无环双结点、空链表五组用例上"
              "（通过构造带环链表）结果一致。写进库里的是 Floyd 版，满足 O(1) 空间要求。",
        time_c="O(n)",
        space_c="O(1)",
        why_c="无环时快指针最多走 n/2 轮到达末尾。有环时慢指针在进环后最多再走 C 轮"
              "（C 为环长）就会相遇，而 C ≤ n，故总步数 O(n)。"
              "空间只有 slow、fast 两个引用，与输入规模无关，故 O(1)。",
        pitfalls=[
            "循环条件只写 while fast：fast.next 为 None 时访问 .next.next 抛出异常。",
            "比较值而不是结点身份：值重复的链表会被误判为有环。",
            "先移动再判断相遇的顺序写反：第一轮就把 slow 与 fast 都指到 head 之后，"
            "逻辑仍然成立但可读性差，容易在后续修改时出错。",
            "以为 Floyd 需要额外空间：它的卖点正是 O(1)。",
            "把相遇判据写成 fast.next is slow：漏掉快指针正好落在慢指针上的情形。",
        ],
        edge_cases=[
            "空链表：返回 False。",
            "单结点且 next 为 None：返回 False。",
            "单结点自环：第一轮即相遇，返回 True。",
            "两结点互指：返回 True。",
            "长链无环：验证循环终止且不抛异常。",
        ],
        tips="面试里这题的重点是「为什么一定会相遇」，而不是代码。"
             "把「快指针相对慢指针每轮净追 1 格」这句话说出来，就基本拿满分。"
             "写代码时必须显式写出 `while fast and fast.next` 并解释双判空的原因。"
             "如果面试官追问 142，答「相遇后慢指针回到 head、两者同速前进，"
             "再次相遇点即环入口」，并说明这依赖一次额外推导。",
    ),
}

# ---------------------------------------------------------------------------
# 11. 删除排序链表中的重复元素 II LeetCode 82（freq 85）
# ---------------------------------------------------------------------------
CONTENT["25052c937d781b08"] = {
    "tldr": "哑结点 + 「看下一段是否重复」：只要 cur.next 与 cur.next.next 的值相等，"
            "就记住这个值并把该值开头的整段全部跳过；否则 cur 前进一格。",
    "why": "它是「删除重复」系列里唯一要求「重复的全删」的题，与 83（保留一个）"
           "只差一行判断，但思路完全不同：83 是「跳过重复的后继」，"
           "82 是「发现重复就整段删除」。这个区别是面试官常设的陷阱。",
    "difficulty": "medium",
    "tags": ["linked-list", "dummy-node", "two-pointers", "duplicates"],
    "entities": ["哑结点", "整段跳过", "重复检测"],
    "diagram": {
        "kind": "flow",
        "title": "整段跳过（1→2→3→3→4→4→5）",
        "caption": "cur 停在 2 时，cur.next（3）与 cur.next.next（3）相等 → 记住 dup = 3，"
                   "把值为 3 的整段全部跳过，cur.next 直接指向 4；"
                   "此时 4 与 4 又相等 → 记住 dup = 4，再把 4 的整段跳过，"
                   "cur.next 指向 5。最后结果 1→2→5。",
        "alt": "链表 1-2-3-3-4-4-5 中重复段被整段跳过的示意",
        "svg": svg_chain(
            ["1", "2", "3", "3", "4", "4", "5"],
            "链表 1-2-3-3-4-4-5，其中 3 与 4 各有连续重复",
            marks=[(1, "cur"), (2, "dup 起点")], w=760),
    },
    "concepts": [concept(
        "为什么判断条件是「看下一对」而不是「看当前」",
        "循环只检查 cur.next 与 cur.next.next 是否相等，也就是说判断的是「cur 后面那两个」。"
        "这样 cur 永远停在「已确认唯一的最后一个结点」上，"
        "它自己的值是安全的，不需要回头删。",
        "像筛豆子：你手里始终捏着「已经挑好的最后一颗」，"
        "然后看筐里接下来的两颗是不是一对坏豆，是一对就都扔掉，不是就把下一颗也收进手里。",
        "判断对象是「cur 的后面」而不是「cur 本身」，这是本写法能省掉 prev 指针的原因。"
        "如果把条件写成 cur.val == cur.next.val，就需要额外保存 prev 才能删除 cur，"
        "代码会多一层分支，且容易在头结点上出错。",
        "因为链表已排序，所有值相同的结点必然连续。"
        "因此「存在重复」可以局部判定为「相邻两个值相等」。"
        "一旦判定重复，用一个 while 把该值的整段吞掉，就恢复了「已处理部分不含重复值」"
        "这个不变量。",
        "把链表画成一行格子并标上颜色分组。cur 用方框圈住，"
        "每轮把「后面两颗是否同色」画成一次判定，同色就把整组划掉并连一条跨越的箭头。",
        ["链表的删除操作", "哑结点的作用", "while 嵌套与不变量"],
        ["为什么这个算法不需要 prev 指针？",
         "如果要求「重复的只保留一个」，代码要改哪一行？",
         "头结点本身重复时，为什么必须用哑结点？"],
    )],
    "formulas": [],
    "selfCheck": {
        "claims": [
            "整段跳过版与「先计数再保留 count==1」版在 7 组用例上结果一致。",
            "哑结点使「头结点被删除」不再是特例。",
        ],
        "uncertain": [
            "本题的「重复」定义为「值相同」，不涉及更复杂的相等性；"
            "若题目要求按自定义键去重，判断条件要替换。",
        ],
    },
    "teaching": teaching(
        progressive=[
            lv("第 1 层 · 能写", "用哑结点 + 整段跳过写出正确实现。"),
            lv("第 2 层 · 能说清", "说清为什么判断「下一对」就能省掉 prev 指针。"),
            lv("第 3 层 · 能对比", "与 83 题（保留一个）对比，指出两者只差「是否整段删除」。"),
            lv("第 4 层 · 能算代价", "说明 O(n) 时间与 O(1) 空间，"
                                    "并说明内层 while 的总代价仍是线性的（每个结点只被跳过一次）。"),
        ],
        socratic=[
            qa("内层 while 会不会让复杂度变成 O(n²)？",
               "不会。内层 while 每执行一次就从链上永久摘掉一个结点，"
               "整个算法里内层总共最多执行 n 次，所以总计仍是 O(n)。"),
            qa("不用哑结点，头结点重复时会发生什么？",
               "head 本身要被删除，而没有任何结点指向它，"
               "你必须单独写一段「移动 head 直到 head 的值唯一」的特判代码。"
               "哑结点把这段特判消掉。"),
            qa("与「保留一个」的 83 题差别在哪？",
               "83 在发现重复时把 cur.next 指向 cur.next.next（跳过一个），"
               "保留第一个；82 在发现重复时先把整段同值结点全部吞掉，"
               "一个都不留。改动很小，语义完全不同。"),
        ],
        mechanism="cur 从哑结点开始，始终指向「已确认无重复的前缀的最后一个结点」。"
                  "每轮检查 cur.next 与 cur.next.next：若不相等，把 cur 前进一步；"
                  "若相等，记下该值并用内层 while 把值为该值的所有结点从链上摘掉，"
                  "之后 cur 保持不动（因为新的 cur.next 还没被检查过）。",
        boundary="依赖「链表已排序」，因为只有排序才能保证相同值连续。"
                 "若链表未排序，需要先排序（链表归并）或改用哈希计数。"
                 "如果要求「保留一个」用 83 的写法；如果要求「保留最后一个」也需要另写。",
        analogyBoundary="「筛豆子」的类比会让人以为「已经挑好的那颗」也要参与比较 ——"
                        "实际 cur 只用来挂接，它自己的值自从被确认唯一后就再也不看了。"
                        "把它当成「比较对象」会写出多余的分支。",
        misconceptions=[
            "判断条件写成 cur.val == cur.next.val：需要 prev 才能删除，代码多一层分支。",
            "发现重复时只跳过 cur.next（一处），而不是该值的整段：结果变成 83 的语义。",
            "内层 while 忘记同步更新 cur.next：重复值只删掉一个。",
            "不用哑结点：头结点重复时无法删除。",
            "担心内层 while 让复杂度退化——每个结点只被摘掉一次，总计 O(n)。",
        ],
        ownAnalysis="这题的核心识别点是「判断下一对」这个技巧——它把「需要 prev 才能删当前结点」变成「站在前驱位置上删后继」，于是省掉一个指针。"
                    "更值得记的是复杂度论证方式：嵌套 while 但内层每轮永久摘掉一个结点，所以总代价仍是线性的。"
                    "面试里遇到双层循环先别急着报 O(n²)，数一数内层「消耗了什么不可再生的资源」。",
        officialNotes=[{'position': '官方题解使用哑结点 + 一次遍历，并在发现重复值后把该值的整段全部跳过。', 'source': 'LeetCode 82 官方题解 · 删除排序链表中的重复元素 II'}],
        interviewAnswer="第一句点明与 83 的差别：「重复的整段删除，一个都不留」。"
                        "然后强调哑结点（消掉删头特判）与「看下一对」（省掉 prev）。"
                        "被问复杂度时主动给出「内层每轮摘掉一个结点，总代价线性」的论证，这一步往往比代码本身更能体现水平。",
        prereq=["链表删除操作", "哑结点", "已排序数组/链表的重复性质"],
        next_steps=["做「删除排序链表中的重复元素」（83）：只保留一个",
                    "做「删除排序数组中的重复项 II」：允许重复两次的变体",
                    "做「删除未排序链表中的重复」：体会排序为何是关键前提"],
    ),
    "problem": problem(
        title="删除排序链表中的重复元素 II（LeetCode 82）",
        statement="给定一个已排序的链表的头 head，删除原始链表中所有重复数字的节点，"
                  "只留下不同的数字。返回已排序的链表。"
                  "注意是「重复的全部删除」，而不是保留一个。",
        examples=[
            ("head = 1→2→3→3→4→4→5", "1→2→5", "3 与 4 都连续重复，整段删除"),
            ("head = 1→1→1→2→3", "2→3", "头部的重复必须删掉，这就是哑结点的作用"),
            ("head = 1→2", "1→2", "无重复，原样返回"),
            ("head = 1→1", "[]", "全部重复 → 结果为空链表"),
        ],
        idea="哑结点 + 「看下一对」的判断。cur 从哑结点出发，始终指向已确认唯一的最后一个结点。"
             "每轮比较 cur.next 与 cur.next.next：不相等则 cur 前进一步；"
             "相等则记下该值，并把值为该值的整段结点从链上摘掉。",
        steps=[
            "dummy = ListNode(0, head)，cur = dummy。",
            "while cur.next and cur.next.next："
            "若 cur.next.val == cur.next.next.val，令 dup = cur.next.val，"
            "然后 while cur.next and cur.next.val == dup：cur.next = cur.next.next；"
            "否则 cur = cur.next。",
            "返回 dummy.next。",
        ],
        whyItWorks="不变量：dummy.next 到 cur 这一段不含任何重复值，且它们都小于等于 cur.next 的值。"
                   "检查 cur.next 与 cur.next.next：若不同，说明 cur.next 只出现一次，"
                   "把它纳入安全前缀（cur 前进一步）；若相同，cur.next 必然不是唯一值，"
                   "由排序性可知所有等于该值的结点都在其后连续，于是整段摘掉。"
                   "两种情况都保持不变量，最终整条链都不含重复值。",
        alternatives=[
            ("先计数再重建链表", "O(n) 时间 / O(n) 空间",
             "两遍扫描、逻辑最直白，适合先在白板上说清思路；代价是 O(n) 额外空间（计数器）。"),
            ("原地两指针（prev + cur）", "O(n) 时间 / O(1) 空间",
             "需要用 prev 才能删除 cur，代码分支更多；本题的「看下一对」写法更简洁。"),
            ("递归处理", "O(n) 时间 / O(n) 栈空间",
             "面试官要求递归时用；栈深与链表长度成正比。"),
        ],
        python=SOLUTIONS["25052c937d781b08"][1],
        python_alt=DELETE_DUP_II_ALT,
        notes="两版都跑过，在头部重复、尾部重复、全部重复、无重复、空链表等 7 组用例上"
              "结果一致。写进库里的是 O(1) 空间的原地版；"
              "对照版用计数 + 重建，说明同一问题的另一种空间取舍。",
        time_c="O(n)",
        space_c="O(1)",
        why_c="外层每轮至少把 cur 前进一步或摘掉一个结点；内层 while 每次摘掉一个结点。"
              "每个结点最多被摘掉一次、每个结点最多被 cur 跨过一次，"
              "因此内层总执行次数 ≤ n，总时间 O(n)。"
              "额外空间只有 dummy 与 cur 两个引用，故 O(1)。",
        pitfalls=[
            "发现重复时只跳过一个结点（写成 83 的语义）：重复值会残留一个。",
            "内层 while 忘记推进 cur.next：死循环。",
            "不用哑结点：头结点重复时无法删除。",
            "判断条件写成 cur.val == cur.next.val：需要 prev 指针，代码变复杂。",
            "担心嵌套循环导致 O(n²)：内层每个结点只被摘一次，总计线性。",
        ],
        edge_cases=[
            "空链表：返回 None。",
            "全部相同 [1,1,1]：返回空链表（dummy.next 为 None）。",
            "头部重复 [1,1,1,2,3]：返回 [2,3]。",
            "尾部重复 [1,2,2,3,3]：返回 [1]。",
            "无重复 [1,2]：返回 [1,2]。",
            "单结点 [1]：返回 [1]。",
        ],
        tips="开场第一句就点明「与 83 题不同，重复的整段删除」，这能让面试官立刻确认你理解题意。"
             "然后强调两点：哑结点消掉头部特判、「看下一对」省掉 prev 指针。"
             "如果被问复杂度，主动给出「内层每轮摘掉一个结点，总代价线性」的论证——"
             "这是把「看起来是双层循环」讲成 O(n) 的关键。",
    ),
}

# ---------------------------------------------------------------------------
# 12. 删除链表的倒数第 N 个结点 LeetCode 19（freq 77）
# ---------------------------------------------------------------------------
CONTENT["820e5d46ff3a9ca9"] = {
    "tldr": "哑结点 + 定距双指针：fast 先走 n 步，然后 fast 与 slow 同步走，"
            "fast 到末尾时 slow 正好停在待删结点的前一个。一趟扫描，O(1) 空间。",
    "why": "它教的是「如何用两个指针在一个未知长度的结构上定位第 k 个倒序位置」。"
           "这个「先拉开固定距离再同步走」的套路也用在「寻找数组中的固定间隔最值」"
           "和「滑动窗口」的变体里。哑结点则再一次消掉「删除头结点」的特例。",
    "difficulty": "medium",
    "tags": ["linked-list", "two-pointers", "dummy-node"],
    "entities": ["定距双指针", "哑结点", "一趟扫描"],
    "diagram": {
        "kind": "flow",
        "title": "定距双指针（1→2→3→4→5, n = 2）",
        "caption": "第一阶段：fast 从 dummy 出发先走 n = 2 步，停在 2。"
                   "第二阶段：fast 与 slow 一起走，直到 fast.next 为 None（fast 停在 5），"
                   "此时 slow 停在 3，也就是待删结点 4 的前一个。"
                   "注意两个游标都从 dummy 起步，这样 n 等于链表长度时 slow 会停在 dummy 上，"
                   "刚好能删掉头结点。",
        "alt": "两个指针间距为 2 的链表遍历示意，slow 最终停在待删结点之前",
        "svg": svg_chain(
            ["1", "2", "3", "4", "5"],
            "链表 1-2-3-4-5，fast 与 slow 相距两个结点",
            marks=[(0, "slow 起点"), (2, "slow"), (4, "fast")]),
    },
    "concepts": [concept(
        "定距双指针为什么能定位倒数第 N 个",
        "两个指针始终相隔 n 个结点。当快指针到链尾时，慢指针与它相隔 n，"
        "因此慢指针正好落在「倒数第 n+1 个」位置，也就是待删结点的前驱。",
        "像用一根固定长度的尺子量东西：尺子的一端抵住链尾，另一端落下的位置，"
        "距离链尾就正好是尺子的长度。",
        "「相隔 n」指的是**下标差**，不是「中间隔 n 个结点」。fast 先走 n 步后，"
        "fast 与 slow 的下标差是 n，所以 fast 到末尾时 slow 是「倒数第 n+1 个」。"
        "若按「中间有 n 个结点」去写（fast 走 n+1 步），slow 会停在待删结点本身，"
        "无法执行删除。",
        "设链表长为 L、待删结点下标为 L-n。fast 先走 n 步后与 slow 的下标差为 n。"
        "此后两者同步前进直到 fast 无法再前进（fast 停在下标 L-1），"
        "此时 slow 的下标为 (L-1) - n = L-n-1，正是待删结点的前驱。"
        "由于两个指针都从 dummy 起步，slow 可以合法地停在下标 -1（即 dummy），"
        "从而覆盖「删除头结点」的情形。",
        "画一排格子，fast 与 slow 用两根不同颜色的箭头，中间用一把标注 n 的尺子连接。"
        "先画 fast 单独前进的 n 格，再画两者一起移动，直到 fast 顶到末端。",
        ["双指针", "哑结点", "链表长度与下标的关系"],
        ["为什么两个指针都从 dummy 起步，而不是从 head 起步？",
         "如果 n 等于链表长度，slow 会停在哪里？",
         "两遍扫描的做法（先求长度再走 L-n 步）有什么优劣？"],
    )],
    "formulas": [],
    "selfCheck": {
        "claims": [
            "定距双指针版与「两遍扫描求长度」版在 5 组用例上结果一致。",
            "两个游标从 dummy 起步是覆盖 n == 链表长度 的必要条件。",
        ],
        "uncertain": [
            "题目保证 n 合法（1 ≤ n ≤ 链表长度），实现依赖该前提；"
            "若 n 越界，fast 会在第一阶段变成 None，需要额外校验。",
        ],
    },
    "teaching": teaching(
        progressive=[
            lv("第 1 层 · 能写", "写出定距双指针的一趟扫描版本。"),
            lv("第 2 层 · 能说清", "说清「下标差为 n」为什么让 slow 落在待删结点前驱。"),
            lv("第 3 层 · 能算代价", "分析 O(L) 时间与 O(1) 空间，并说明与两遍扫描的差别。"),
            lv("第 4 层 · 能迁移", "把「固定间隔双指针」搬到数组滑窗的最值维护、"
                                  "以及「链表中间结点」等场景。"),
        ],
        socratic=[
            qa("为什么从 dummy 起步？",
               "若 n 等于链表长度，待删结点就是 head。此时 slow 必须停在一个「真实存在且能"
               "执行 slow.next = slow.next.next」的位置，也就是 dummy。"
               "从 head 起步会让 slow 无处可停。"),
            qa("第二阶段为什么用 while fast.next 而不是 while fast？",
               "目标是让 fast 停在下标 L-1（最后一个结点），这样 slow 才落在 L-n-1。"
               "若用 while fast，fast 会走到 None（越过尾结点），slow 会多走一步，"
               "停在待删结点本身上，删除就删错了。"),
            qa("两遍扫描的做法（先求 L 再走 L-n 步）有什么不好？",
               "它正确、好懂，但链表需要遍历两次。定距双指针只需一趟，"
               "在流式/不可重复遍历的场景下更有价值；代价是逻辑更绕一点。"),
        ],
        mechanism="第一阶段把 fast 前进 n 步，使 fast 与 slow 的下标差固定为 n。"
                  "第二阶段两者同步前进，直到 fast 到达最后一个结点；"
                  "由于下标差不变，slow 此时位于下标 L-n-1，即待删结点的前驱。"
                  "最后执行 slow.next = slow.next.next 完成删除。",
        boundary="适用于单链表、n 合法。若 n 可能越界，第一阶段后要判 fast 是否为 None。"
                 "若要删「倒数第 n 个到倒数第 m 个」区间，需要三指针（前驱、区间头、区间尾）。"
                 "双向链表可以用尾指针直接定位，无需双指针技巧。",
        analogyBoundary="「固定长度的尺子」类比会让人以为「尺子长度 = 相隔的结点数」——"
                        "实际是下标差。多算一格或少算一格都会让 slow 停在错误的位置，"
                        "而这两种错误在「n 远小于长度」的用例上都不容易暴露。",
        misconceptions=[
            "两个游标从 head 起步：n 等于链表长度时无法删除头结点。",
            "第二阶段用 while fast 而不是 while fast.next：slow 多走一步，停在待删结点上。",
            "第一阶段走 n-1 步：slow 会停在待删结点之后，删错结点。",
            "不用哑结点却试图手动处理「删头」：代码多一段特判，容易漏。",
            "以为两遍扫描是错的：它正确，只是效率上多一趟遍历。",
        ],
        ownAnalysis="「定距双指针」的本质是把「倒序位置」换算成「下标差」。"
                    "由于单链表只能正向走，无法预知长度，所以用两个指针的相对位置替代绝对长度。"
                    "同一思想在数组上就是固定窗口（滑动窗口），在链表上就是这道题——理解「相对距离可以替代绝对位置」是很多双指针题能一眼看出解法的原因。",
        officialNotes=[{'position': '官方题解给出两种解法：计算链表长度后删除（两趟），以及用双指针一趟完成；后者满足进阶要求。', 'source': 'LeetCode 19 官方题解 · 删除链表的倒数第 N 个结点'}],
        interviewAnswer="两个必说点：从 dummy 起步（覆盖 n == 链表长度，也就是删头）、第二阶段以 fast.next 为终止条件（slow 才停在待删结点之前）。"
                        "写完用手动例子（1→2→3→4→5, n=2）演示两个指针的位置。"
                        "被问「能不能不用哑结点」时答「可以，但要单独处理删头」。",
        prereq=["链表遍历与删除", "哑结点", "下标与相对距离"],
        next_steps=["做「链表的中间结点」：快慢指针的另一种定距用法",
                    "做「相交链表」：两个指针互换起点走完对方的链",
                    "做「两两交换链表中的节点」：同样是局部指针重连"],
    ),
    "problem": problem(
        title="删除链表的倒数第 N 个结点（LeetCode 19）",
        statement="给你一个链表，删除链表的倒数第 n 个结点，并且返回链表的头结点。"
                  "进阶要求：使用一趟扫描实现。",
        examples=[
            ("head = 1→2→3→4→5, n = 2", "1→2→3→5",
             "倒数第 2 个是 4；slow 最终停在 3，执行 3.next = 5"),
            ("head = 1, n = 1", "[]", "单结点删掉后返回 None；靠 dummy 自然得到"),
            ("head = 1→2, n = 1", "1", "删除尾结点，slow 停在 1，1.next 变为 None"),
            ("head = 1→2, n = 2", "2", "删除头结点，slow 停在 dummy 上"),
        ],
        idea="定距双指针。两个指针都从哑结点起步：fast 先走 n 步，"
             "然后 fast 与 slow 同步前进，直到 fast 到达最后一个结点。"
             "此时 slow 与 fast 下标差为 n，即 slow 位于倒数第 n+1 个结点（待删结点的前驱），"
             "执行 slow.next = slow.next.next 即可。",
        steps=[
            "dummy = ListNode(0, head)，fast = slow = dummy。",
            "重复 n 次：fast = fast.next（第一阶段，拉开固定距离）。",
            "while fast.next：fast = fast.next；slow = slow.next（第二阶段，同步前进）。",
            "slow.next = slow.next.next（跳过待删结点）。",
            "返回 dummy.next。",
        ],
        whyItWorks="第一阶段后 slow 与 fast 的下标差为 n。第二阶段保持该差值前进，"
                   "直到 fast 停在下标 L-1。于是 slow 的下标为 L-1-n = L-n-1，"
                   "正好是待删结点（下标 L-n）的前驱。"
                   "从 dummy 起步使 slow 的下标可以是 -1，从而在 n == L 时也能停在合法的"
                   "可操作位置，覆盖删除头结点的情形。",
        alternatives=[
            ("两遍扫描（先求长度 L，再走 L-n 步）", "O(L) 时间 / O(1) 空间",
             "思路最直白，不容易写错；代价是需要遍历链表两次，"
             "在不可重复遍历的场景下不适用。"),
            ("先入栈再弹出", "O(L) 时间 / O(L) 空间",
             "把结点压栈后弹出 n 个即可定位；空间 O(L)，面试里通常会被要求优化。"),
            ("递归回溯计数", "O(L) 时间 / O(L) 栈空间",
             "面试官要求递归时用；代码优雅但栈深 O(L)，长链表有风险。"),
        ],
        python=SOLUTIONS["820e5d46ff3a9ca9"][1],
        python_alt=REMOVE_NTH_ALT,
        notes="两版都跑过，在 n=1、n=链表长度、单结点、两结点两种极端、长链等 5 组用例上"
              "结果一致。写进库里的是定距双指针一趟扫描版，符合题目进阶要求。",
        time_c="O(L)",
        space_c="O(1)",
        why_c="第一阶段走 n 步，第二阶段走 L-n 步，合计恰好 L 步（每个结点访问一次），"
              "故时间 O(L)。额外空间只有 dummy、fast、slow 三个引用，与规模无关，故 O(1)。"
              "相比之下两遍扫描是 2L 步，渐进同阶但常数大一些。",
        pitfalls=[
            "两个游标从 head 起步：n == 链表长度 时无法删除头结点。",
            "第二阶段写成 while fast：fast 越过尾结点，slow 停在待删结点上，删错位置。",
            "第一阶段走 n-1 步：slow 落在待删结点之后。",
            "忘记建哑结点并手动处理删头：多出特判分支。",
            "返回 head 而不是 dummy.next：删除头结点时返回的仍是旧头（已被摘掉）。",
        ],
        edge_cases=[
            "n == 链表长度：删除头结点。",
            "n == 1：删除尾结点。",
            "单结点链表 n = 1：返回 None。",
            "两结点链表：[1,2] 分别取 n=1 与 n=2。",
            "长链 n 取中间值：验证一趟扫描表现。",
        ],
        tips="这题的两个关键点可以一口气说完：「哑结点让删头不再是特例」和"
             "「第二阶段用 fast.next 终止，slow 才停在待删结点前面」。"
             "主动用手动例子（1→2→3→4→5, n=2）演示两个指针的位置，比空谈逻辑有效得多。"
             "如果面试官问「能不能不用哑结点」，如实回答「可以，但要单独处理删头」。",
    ),
}

# ---------------------------------------------------------------------------
# 13. 二叉树中的最大路径和 LeetCode 124（freq 68）
# ---------------------------------------------------------------------------
CONTENT["89c412c833ced6e2"] = {
    "tldr": "后序遍历，每个结点返回「以它为端点向下的最大贡献」，同时用「左贡献 + 自己 + 右贡献」"
            "更新全局答案。负贡献取 0（不选它比选它好）。",
    "why": "它是「树形 DP」的样板：函数同时承担两个职责——向上返回单边最大值、"
           "在结点处更新以该结点为拐点的答案。这个「返回一个值、更新另一个值」的双职责模式"
           "是树形 DP 的核心，也是很多人第一次写树形 DP 时会漏掉的地方。",
    "difficulty": "hard",
    "tags": ["tree", "dfs", "dynamic-programming", "postorder"],
    "entities": ["树形 DP", "后序遍历", "最大贡献", "拐点"],
    "diagram": {
        "kind": "flow",
        "title": "后序 DP（root = [-10,9,20,null,null,15,7]）",
        "caption": "自底向上：15 的贡献 15、7 的贡献 7，都不为负所以保留；"
                   "结点 20 处的候选路径是 15 + 20 + 7 = 42（以 20 为拐点），"
                   "向上返回的只能是单边 20 + max(15, 7) = 35；"
                   "结点 9 的贡献 9；根 -10 处的候选是 9 + (-10) + 35 = 34，"
                   "但全局最大值已在 42 处取到。关键：拐点处的值不回传给父结点。",
        "alt": "二叉树 -10 为根、左 9、右 20、20 的孩子 15 与 7，标注各结点的最大贡献",
        "svg": svg_tree(
            [["-10"], ["9", "20"], [None, None, "15", "7"]],
            "二叉树：根 -10，左孩子 9，右孩子 20，20 的孩子 15 与 7",
            hi=((1, 1), (2, 2), (2, 3))),
    },
    "concepts": [concept(
        "返回值与答案的双职责",
        "gain(u) 返回的是「以 u 为端点、只向下走一条链」的最大和，供父结点使用；"
        "而答案 best 记录的是「以某结点为拐点、左右两条链都用上」的最大和。"
        "两者不是同一个量。",
        "像在公司里汇报：你对上级只能报「你自己这条线能贡献多少」（单边），"
        "但公司内部考核可以把你和兄弟部门一起算（双边）。"
        "对上级报双边数据是不合法的，因为路径到了上级就分岔了。",
        "最经典的错误是把 gain 写成「子树最大路径和」并让父结点直接加两次。"
        "一旦路径在某个结点「拐弯」（左右两边都用），它就不再是一条能从父结点穿过的直链，"
        "所以只能用来更新全局答案，不能向上返回。"
        "判断标准：向上返回的表达式里只能出现 max(left, right)，不能出现 left + right。",
        "树的每条路径都有唯一的「最高点」（LCA）。枚举这个最高点，"
        "路径和就是 node.val + 左链贡献 + 右链贡献，其中每条链的贡献可取 0（不选该侧）。"
        "后序遍历恰好能自底向上算出所有结点作为最高点的候选值，"
        "因此一趟 DFS 即可得到全局最优。",
        "画树，每个结点标两个数字：括号外是 gain（向上返回的单边贡献），"
        "括号内是该结点处的候选路径和。从叶子往上逐层标注，最后圈出最大的候选值。",
        ["二叉树的遍历", "递归的返回值语义", "LCA（最低公共祖先）"],
        ["为什么负贡献要取 max(..., 0)？",
         "如果一个结点的左子树贡献是负的，能不能「只走一部分」左子树？",
         "全为负数的树，答案是什么？"],
    )],
    "formulas": [],
    "selfCheck": {
        "claims": [
            "O(n) 后序解与 O(n²) 暴力枚举 LCA 解在 7 组用例上结果一致"
            "（暴力解由路径重建实现，已交叉验证）。",
            "负贡献取 0 是必要的：全负树的最优解是单个最大结点。",
        ],
        "uncertain": [
            "题目对「路径至少包含一个结点」有明确约定，因此全负树返回最大单结点值"
            "（不是 0）。若题目允许空路径，答案会变成 0，需按题意调整初始化。",
        ],
    },
    "teaching": teaching(
        progressive=[
            lv("第 1 层 · 能写", "写出后序递归，返回单边最大贡献，并用双边和更新答案。"),
            lv("第 2 层 · 能说清", "说清「为什么返回单边、答案用双边」这组双职责。"),
            lv("第 3 层 · 能算代价", "分析 O(n) 时间与 O(h) 空间（h 为树高），"
                                    "并说明为什么不需要记忆化。"),
            lv("第 4 层 · 能推广", "说出「每条路径有唯一最高点」这个枚举视角，"
                                  "并迁移到「树的最大直径」「打家劫舍 III」。"),
        ],
        socratic=[
            qa("为什么 gain 里不能返回 left + right + node.val？",
               "因为那样路径在 node 处就拐弯了，父结点无法「接入」这条路径——"
               "父结点只能接在路径的一个端点上。所以向上传递的必须是单边链；"
               "双边和只用于在 node 处更新全局答案。"),
            qa("为什么负贡献要取 0？",
               "因为路径可以选择「不往那一侧走」。既然题目要求路径至少含一个结点，"
               "在某个结点处放弃贡献为负的一侧总是更优，所以用 max(gain, 0) 截断。"),
            qa("全为负数的树，答案是什么？",
               "最大的单个结点值。此时所有 gain 都会被截成 0，"
               "best 在遍历中会被更新为「恰好只含该结点的路径」。"
               "如果把 best 初始化为 0，就会错误地返回 0（除非题目允许空路径）。"),
        ],
        mechanism="后序遍历。对结点 u，先递归得到左右子树的 gain，"
                  "用 max(0, gain) 截断负贡献。候选路径和 = u.val + left + right，"
                  "用它更新全局答案 best。向上返回的是 u.val + max(left, right)，"
                  "即「以 u 为端点、选一侧」的最大和。遍历完所有结点后 best 即为答案。",
        boundary="适用于「路径 = 树中任意两点间的一条简单路径」的定义。"
                 "若题目改为「必须经过根」或「必须从根出发」，返回语义与初始化都要变。"
                 "若要求返回路径本身而不只是和，需要额外记录左右端点。"
                 "树退化成链时递归深度为 n，Python 需要提高递归上限。",
        analogyBoundary="「向上级汇报」的类比会让人以为「上级可以直接把两边的汇报相加」——"
                        "事实上级只能接一条线（因为路径不能分岔），"
                        "两边相加只在「考核以你为拐点」时成立。"
                        "混淆这两件事就会写出把 left+right 往上传的错解。",
        misconceptions=[
            "gain 返回 left + right + node.val：父结点会重复计入，答案偏大。",
            "忘记对负贡献取 0：全负树会返回一个比真实最优更小的值。",
            "best 初始化为 0：全负树错误地返回 0。",
            "把 best 写成全局变量却在递归里重置：只有最后一个分支的结果被保留。",
            "以为需要记忆化：每个结点只被访问一次，本就 O(n)。",
        ],
        ownAnalysis="树形 DP 的通用模式是「返回值服务于父结点，附加状态记录以自己为根的答案」。"
                    "本题是它最简洁的形态：返回值是单边链、答案是双边和。"
                    "掌握这个「返回 / 更新」双职责后，「树的直径」「打家劫舍 III」（返回两个状态：抢/不抢）都能顺着同一思路推出来，不需要分别背题。",
        officialNotes=[{'position': '官方题解指出「路径的最高点可以是任意结点」，并用后序 DFS 在每个结点处更新答案、同时向上返回单边最大贡献。', 'source': 'LeetCode 124 官方题解 · 二叉树中的最大路径和'}],
        interviewAnswer="开口就把双职责讲清：「向上返回单边、答案用双边」，并说明「路径不能在父结点处分岔」这个理由。"
                        "然后解释 `max(..., 0)` 与 `best = -inf` 两处初始化。"
                        "最后用 [-3] 说明为什么 best 不能初始化为 0——这个用例能一次性证明你理解「路径至少含一个结点」。",
        prereq=["二叉树的递归遍历", "递归返回值的语义设计", "LCA 与路径的定义"],
        next_steps=["做「二叉树的直径」：同样的后序 DP，只是把「和」换成「长度」",
                    "做「打家劫舍 III」：树形 DP 返回两个状态",
                    "做「路径总和 III」：前缀和 + 树的组合"],
    ),
    "problem": problem(
        title="二叉树中的最大路径和（LeetCode 124）",
        statement="二叉树中的路径被定义为一条结点序列，同一条路径中的结点不重复出现。"
                  "该路径至少包含一个结点，且不一定经过根结点。路径和是路径中各结点值的总和。"
                  "给你二叉树的根结点 root，返回其最大路径和。",
        examples=[
            ("root = [1,2,3]", "6", "路径 2→1→3 的路径和为 6"),
            ("root = [-10,9,20,null,null,15,7]", "42", "路径 15→20→7 的路径和为 42"),
            ("root = [-3]", "-3", "单结点且为负：答案就是 -3，不能返回 0"),
            ("root = [2,-1]", "2", "放弃贡献为负的左孩子，只取结点 2"),
        ],
        idea="后序遍历 + 双职责。定义 gain(u) = 「以 u 为端点，向下走到某个结点的最大路径和」"
             "（只走一条链，负贡献截断为 0）。在每个结点处，用「左 gain + u.val + 右 gain」"
             "更新全局答案——这条路径以 u 为最高点，可以两边都用。"
             "而向父结点返回的只能是 u.val + max(左, 右)。",
        steps=[
            "初始化 best = -inf。",
            "定义 dfs(u)：若 u 为空返回 0。",
            "left = max(dfs(u.left), 0)；right = max(dfs(u.right), 0)。",
            "用 u.val + left + right 更新 best（以 u 为最高点的完整路径）。",
            "返回 u.val + max(left, right)（向上可接续的单边链）。",
            "调用 dfs(root) 后返回 best。",
        ],
        whyItWorks="树中任意一条路径都有唯一的最高点（该路径两端结点的最低公共祖先）。"
                   "枚举这个最高点即可覆盖所有路径：以 u 为最高点的最优路径，"
                   "必由「u 到左子树某点的最优下行链」与「u 到右子树某点的最优下行链」组成。"
                   "后序遍历保证在计算 u 时左右子树的 gain 已就绪，"
                   "因此一趟 DFS 就能得到全局最优。",
        alternatives=[
            ("暴力枚举所有点对 + 路径重建", "O(n²) 时间 / O(n) 空间",
             "作为正确性验证很有用（本批就是用它交叉验证 O(n) 解）；"
             "面试里作为答案会被指出效率问题。"),
            ("自底向上带两个状态的树形 DP", "O(n) 时间 / O(h) 空间",
             "与本题解等价，只是把「更新答案」与「返回值」显式拆成两个字段；"
             "在「打家劫舍 III」这类需要两个状态的问题里更自然。"),
            ("先求直径再求路径和", "O(n) 时间 / O(h) 空间",
             "不适用：本题要求最大值而非最长路径，值可以为负，"
             "「最长」与「最大和」不是同一个目标。"),
        ],
        python=SOLUTIONS["89c412c833ced6e2"][1],
        python_alt=MAX_PATH_SUM_ALT,
        notes="O(n) 主解与 O(n²) 暴力解都跑过，在单结点、全负、双结点、链状树、"
              "含负数满二叉树等 7 组用例上结果一致（暴力解按「枚举所有点对并重建真实路径」"
              "实现，是独立于主解的验证手段）。写进库里的是 O(n) 后序 DP。",
        time_c="O(n)",
        space_c="O(h)（h 为树高，最坏 O(n) 递归栈）",
        why_c="每个结点恰好被访问一次，故时间 O(n)。额外空间只有递归栈，"
              "深度等于树高 h；平衡树 h = O(log n)，退化成链时 h = O(n)。"
              "不需要记忆化，因为每个结点只被访问一次、没有重复子问题。",
        pitfalls=[
            "dfs 返回 u.val + left + right：父结点会重复计入两条链，答案偏大。",
            "忘记对左右贡献取 max(0, ...)：全负树会得到比真实最优更小的值。",
            "best 初始化为 0：全负树错误地返回 0；应初始化为负无穷。",
            "用非局部变量但忘了在嵌套函数里声明 nonlocal：best 不会被更新。",
            "把「最大路径和」当成「最长路径」：值可为负，两者目标不同。",
        ],
        edge_cases=[
            "单结点 [-3]：答案 -3。",
            "双结点 [2,-1]：答案 2（放弃负贡献一侧）。",
            "全负数 [-2,-1]：答案 -1。",
            "单边链 [1,2,3]：答案 6，验证单边累加。",
            "含负数的满二叉树：验证拐点候选与单边返回的区分。",
            "退化链（1000 结点）：验证递归深度，必要时设置递归上限。",
        ],
        tips="这题的区分度在「能不能说清返回值与答案语义不同」。开口就把这组双职责讲清，"
             "并主动说明「向上只能传单边，因为路径不能在父结点处分岔」。"
             "然后把 `max(..., 0)` 和 `best = -inf` 两处初始化的理由讲明——"
             "这两处是面试官最常追问的细节。最后可以用 [-3] 说明为什么不能返回 0。",
    ),
}

# ---------------------------------------------------------------------------
# 14. 复原 IP 地址 LeetCode 93（freq 60）
# ---------------------------------------------------------------------------
CONTENT["d80b9ddcb5f113ce"] = {
    "tldr": "DFS 切 4 段：每段 1~3 位、不能有前导 0、值 ≤ 255；"
            "切满 4 段且恰好用尽整串才收结果。剪枝用「剩余字符数必须落在"
            "剩余段数 × [1,3] 内」。",
    "why": "它是「定段数划分」这一类回溯题的标准模板：与「分割回文串」的区别只在于"
           "「段数固定为 4」和「每段的合法性判据不同」。"
           "面试里考的是剪枝与合法性判据是否写全——前导 0 与 255 上限"
           "各对应一类会被漏掉的用例。",
    "difficulty": "medium",
    "tags": ["backtracking", "dfs", "string", "pruning"],
    "entities": ["回溯", "剪枝", "前导零", "定段数划分"],
    "diagram": {
        "kind": "flow",
        "title": "DFS 切分 s = \"25525511135\"",
        "caption": "每层决定「第三段取几位」。第一段 255 合法；第二段 255 合法；"
                   "第三段若取 111 → 剩 35 只有 2 位、不够第四段的最小 1 位？实际上够，"
                   "所以 255.255.111.35 成立；若第三段取 11 → 剩 135，也可行 → "
                   "255.255.11.135。两条分支都保留，这就是「要枚举所有切法」的含义。",
        "alt": "字符串 25525511135 逐层切分为四段的搜索树示意",
        "svg": svg_trace(
            [
                {"label": "第 1 段", "cells": ["2", "5", "5"], "hi": [0, 1, 2],
                 "note": "取 255（长度 3）→ 余 25511135"},
                {"label": "第 2 段", "cells": ["2", "5", "5"], "hi": [3, 4, 5],
                 "note": "取 255（长度 3）→ 余 11135"},
                {"label": "第 3 段 · A", "cells": ["1", "1", "1"], "hi": [6, 7, 8],
                 "note": "取 111 → 余 35，第 4 段取 35 → 255.255.111.35"},
                {"label": "第 3 段 · B", "cells": ["1", "1"],
                 "note": "取 11 → 余 135，第 4 段取 135 → 255.255.11.135"},
                {"label": "剪枝示例", "cells": ["0", "1"],
                 "note": "若某段是 \"01\"：首字符 0 且长度 > 1 → 非法，直接放弃该分支"},
            ],
            "复原 IP 地址的切分与剪枝过程"),
    },
    "concepts": [concept(
        "定段数划分的回溯结构",
        "dfs(start, parts)：start 是「下一段从哪里开始」，parts 是已确定的段。"
        "当 len(parts) == 4 时判断是否用完整串；否则枚举这一段的长度（1~3）并递归。",
        "像把一根长绳剪成恰好 4 段：你从绳子左端开始剪第一刀，"
        "每剪一刀就少一段可剪，剪到第四刀时必须刚好剪到绳尾。",
        "「恰好用尽」这个条件很容易被忽略。若只判 len(parts) == 4 而不判 start == n，"
        "会接受「用了 4 段但后面还有剩余字符」的非法结果；反之若只判 start == n"
        "而不判段数，会接受「用尽但只有 3 段」的结果。两个条件必须同时成立。",
        "回溯的正确性来自「每层独立枚举本段长度，且只保留合法段」。"
        "由于段数固定为 4、每段长度 ≤ 3，搜索空间上界是 3^4 = 81 个叶子，"
        "非常小；剪枝（剩余长度必须落在 [剩余段数, 剩余段数 × 3]）进一步砍掉大量分支。",
        "把字符串画成格子，每层用不同颜色标记「本段占用的格子」。"
        "画三张卡片表示三种段长，分支用树状展开，非法的分支打红叉。",
        ["字符串切片", "DFS 与回溯", "剪枝条件"],
        ["为什么必须同时判「4 段」和「用尽整串」？",
         "剪枝条件 n - start < remain_seg 排除的是什么情况？",
         "为什么可以在段首为 '0' 且长度 > 1 时直接 break 而不是 continue？"],
    )],
    "formulas": [],
    "selfCheck": {
        "claims": [
            "DFS 版与三重循环暴力枚举版在 6 组用例上结果一致（含 \"0000\"、\"010010\"）。",
            "合法段数固定为 4，每段 ≤ 3 位，因此搜索空间上界为 O(1) 段数 × n。",
        ],
        "uncertain": [
            "不同实现对「0」与「00」的界定一致（前导零非法），"
            "但某些平台的历史用例对此有过争议，实现以「无前导零」为准。",
        ],
    },
    "teaching": teaching(
        progressive=[
            lv("第 1 层 · 能写", "写出 DFS 切 4 段并收集合法结果。"),
            lv("第 2 层 · 能说清", "说清「4 段 + 用尽整串」两个终止条件缺一不可。"),
            lv("第 3 层 · 能算代价", "分析 O(3^4 × n) 的上界，并说明剪枝把实际搜索量压到多少。"),
            lv("第 4 层 · 能迁移", "对比「分割回文串」「分割成 k 个相等子串」，"
                                  "说清定段数划分的通用骨架。"),
        ],
        socratic=[
            qa("为什么剪枝里是 remain_seg * 3 而不是 remain_seg * 4？",
               "因为单段最大长度是 3（IP 段 ≤ 255，最多三位）。用 4 会让剪枝失效，"
               "保留本应被排除的分支。"),
            qa("段首为 0 时为什么要 break 而不是 continue？",
               "如果这一位是 0，那么以它开头的长度 2、3 的候选段（\"01\"、\"011\"）"
               "全都是前导零非法，而长度 1 的 \"0\" 已经在循环里试过了，"
               "所以后续长度都不可能合法，可以直接结束本层循环。"),
            qa("为什么 \"0000\" 的结果是 [\"0.0.0.0\"] 而 \"010010\" 有多种切法？",
               "因为每段一位的 \"0\" 都合法，\"0000\" 只有一种四位切法；"
               "而 \"010010\" 可以切成 0.10.0.10 或 0.100.1.0，"
               "两段长度选择不同但都满足判据，所以要枚举全部。"),
        ],
        mechanism="dfs(start, parts) 枚举本段的结束下标 end ∈ [start+1, min(start+3, n)]。"
                  "对每个候选段，先做前导零与 ≤ 255 的合法性检查（不合法则提前结束本层循环，"
                  "因为更长也一定不合法）；合法则递归到 end 并把该段加入 parts。"
                  "递归基有两个：已切满 4 段（此时必须恰好用尽整串才收集结果），"
                  "或剩余字符数无法满足剩余段数（剪枝返回）。",
        boundary="段数固定为 4、每段 ≤ 3 位是 IP 地址的定义决定的。"
                 "如果题目改成「分成任意段、每段 ≤ 255」，需要去掉段数上限并调整终止条件。"
                 "若字符串过长（> 12 位），一定不可能切成 4 段合法的 IP，"
                 "可以提前判长度返回空列表。",
        analogyBoundary="「把绳子剪成 4 段」的类比会让人忽略「每段的合法性」——"
                        "绳子任意长度都能剪，但 IP 段有前导零与 255 上限两个额外约束。"
                        "只按长度考虑会漏掉这两类非法输入。",
        misconceptions=[
            "只判 len(parts) == 4 而不判 start == n：接受带剩余字符的非法结果。",
            "忘记前导零检查：\"01\" 这类段会被当成合法。",
            "合法性不合法时用 continue 而不是 break：多跑了无用的更长的候选段。",
            "剪枝写成 remain_seg * 4：少剪掉一部分分支，虽然结果仍对但效率下降。",
            "长度 > 12 的输入不做提前返回：会多做一轮无用搜索（结果仍为空）。",
        ],
        ownAnalysis="定段数划分的回溯模板是「dfs(起点, 已选部分) + 段数上限 + 合法性判据」。"
                    "把它和「分割回文串」放在一起看，差别只在「段数是否固定」与「判据是什么」。"
                    "本题另一个值得记的习惯是「非法时 break 而不是 continue」——这在候选长度单调递增时普遍成立，能省掉大量无效分支，而且在解释「为什么可以提前结束」时是一个清晰的得分点。",
        officialNotes=[{'position': '官方题解使用回溯（DFS）枚举每段长度，并给出段长 1~3、无前导零、≤ 255 三条合法性判据。', 'source': 'LeetCode 93 官方题解 · 复原 IP 地址'}],
        interviewAnswer="一次性把五条判据报道：段长 1~3、无前导零、≤ 255、必须 4 段、必须用尽整串。"
                        "写 DFS 时把两个终止条件的先后写清楚，并解释「为什么非法可以 break」。"
                        "最后用 \"010010\" 与 \"0000\" 自证边界正确——面试官几乎一定会拿其中一个来验证你。",
        prereq=["字符串切片", "DFS 与回溯", "IP 地址的格式约定"],
        next_steps=["做「分割回文串」：段数不固定、合法性判据换成回文",
                    "做「分割成 k 个相等的子串」：段数固定但长度固定",
                    "做「电话号码的字母组合」：同样是定长回溯"],
    ),
    "problem": problem(
        title="复原 IP 地址（LeetCode 93）",
        statement="有效 IP 地址正好由四个整数（每个整数位于 0 到 255 之间组成，且不能含有前导 0），"
                  "整数之间用 '.' 分隔。例如 \"0.1.2.201\" 和 \"192.168.1.1\" 是有效 IP 地址，"
                  "但是 \"0.011.255.245\"、\"192.168.1.312\" 和 \"192.168@1.1\" 是无效 IP 地址。"
                  "给定一个只包含数字的字符串 s，用以表示一个 IP 地址，"
                  "返回所有可能的有效 IP 地址。",
        examples=[
            ("s = \"25525511135\"", "[\"255.255.11.135\", \"255.255.111.35\"]",
             "两条切法都合法：第三段取 11 或 111"),
            ("s = \"0000\"", "[\"0.0.0.0\"]", "每段一位的 0 合法；\"00\" 等前导零非法"),
            ("s = \"101023\"",
             "[\"1.0.10.23\", \"1.0.102.3\", \"10.1.0.23\", \"10.10.2.3\", \"101.0.2.3\"]",
             "五种切法，验证要枚举所有分支"),
            ("s = \"010010\"", "[\"0.10.0.10\", \"0.100.1.0\"]",
             "前导零约束：不能切成 \"01.0.0.10\""),
        ],
        idea="DFS 切 4 段。dfs(start, parts) 枚举本段的结束位置（长度 1~3），"
             "对候选段做三项合法性检查（长度合法、无前导零、≤ 255），"
             "合法就递归。当 parts 已有 4 段且 start 恰好等于字符串长度时收集结果。"
             "剪枝：剩余字符数必须落在「剩余段数」与「剩余段数 × 3」之间。",
        steps=[
            "dfs(start = 0, parts = [])。",
            "若 len(parts) == 4：仅当 start == len(s) 时记录 \".\".join(parts)，然后返回。",
            "剪枝：remain = 4 - len(parts)；若 len(s) - start 不在 [remain, remain * 3] 内则返回。",
            "枚举 end ∈ [start+1, min(start+3, len(s))]，取 seg = s[start:end]。",
            "若 len(seg) > 1 且 seg[0] == '0'，break（更长也一定非法）。",
            "若 int(seg) > 255，break。",
            "否则 dfs(end, parts + [seg])。",
            "最终返回收集到的所有结果。",
        ],
        whyItWorks="枚举「每段长度」覆盖了所有把字符串切成 4 段的方式；"
                   "合法性过滤保证每段都是合法 IP 段；"
                   "两个终止条件（4 段 + 用尽整串）保证结果恰好是把整串切成 4 个合法段。"
                   "由于两个 break 的依据是「更长的候选段必然同样非法」"
                   "（前导零与单调性），剪枝不会漏掉任何合法解。",
        alternatives=[
            ("三重循环暴力枚举切点", "O(n³) 上界但实际接近 O(1)（段长 ≤ 3）",
             "段数固定为 4，所以只需三重循环枚举前 3 刀；"
             "代码没有递归、边界一眼看清，很适合作为第二解法的对照。"),
            ("DFS 不剪枝", "O(3^4) = 81 个叶子",
             "也能得到正确答案，但会多走无效分支；"
             "剪枝在长串上能明显减少递归调用次数。"),
            ("BFS 层次扩展", "同 DFS 的搜索空间",
             "把「已切段数」当成层，逐层扩展；实现更绕，本题没有必要。"),
        ],
        python=SOLUTIONS["d80b9ddcb5f113ce"][1],
        python_alt=RESTORE_IP_ALT,
        notes="DFS 版与三重循环版都跑过，在 \"25525511135\"、\"0000\"、\"101023\"、"
              "\"1111\"、\"010010\"、长度 13 的串六组用例上结果一致。"
              "写进库里的是 DFS 剪枝版；三重循环版作为对照组，"
              "体现「段数固定时暴力枚举其实也不差」。",
        time_c="O(3^4 × n)（上界；实际远小于此）",
        space_c="O(4 × n)（结果数量级）",
        why_c="每段最多 3 种长度选择、共 4 段，因此搜索树叶子数上界 3^4 = 81，"
              "与 n 无关；每个叶子处做 O(n) 的字符串拼接，故上界 O(3^4 × n)。"
              "剪枝（剩余长度范围检查）会在每层砍掉大量分支，实际访问的结点数很少。"
              "空间由结果列表中每个 IP 串的长度决定，即 O(4n) 量级。",
        pitfalls=[
            "只判 len(parts) == 4 而不判 start == n：会接受含剩余字符的非法结果。",
            "漏掉前导零检查：\"01\" 这类段被当成合法，结果偏多。",
            "非法时用 continue 而不是 break：多跑无用分支（结果仍对，效率降低）。",
            "剪枝写成 remain_seg * 4：剪枝力度不足，不影响正确性但多走分支。",
            "用 分割方式枚举所有切点组合再过滤：能过，但写法冗长、容易越界。",
        ],
        edge_cases=[
            "\"0000\" → [\"0.0.0.0\"]：验证每段一位的 0 合法。",
            "\"1111\" → [\"1.1.1.1\"]。",
            "\"010010\" → [\"0.10.0.10\", \"0.100.1.0\"]：验证前导零约束与多解。",
            "长度 > 12（如 \"1234567890123\"）→ []：任何切法都会有一段超 255。",
            "长度 < 4（如 \"1\"）→ []：不可能切出 4 段。",
            "\"25525511135\"：验证枚举全部合法分支而不是只取第一个。",
        ],
        tips="开口把五条判据报道：段长 1~3、无前导零、≤ 255、必须 4 段、必须用尽整串。"
             "这五条是本题的全部内容。写 DFS 时把两个终止条件的顺序写清楚，"
             "并说明「为什么可以 break 而不是 continue」。"
             "最后用 \"010010\" 与 \"0000\" 两个用例自证边界处理正确——"
             "面试官几乎一定会拿其中一个来验证。",
    ),
}

# ===========================================================================
# 得分要点（keyPoints）
#
# 这是前端「得分要点」面板与题库页共同使用的字段：REQ_FULL 要求它存在，
# build_problem_bank.py 也把它挂到题目实体上。刻意与 approach.steps 区分：
# steps 讲「怎么一步步做」，keyPoints 讲「面试官会看什么、你必须说到什么」。
# ===========================================================================
KEYPOINTS: dict[str, list[str]] = {
    "1ce9f0a6715ffa8f": [
        "分区后基准落在最终有序位置——这是快排能递归的前提，必须能一句话说清。",
        "平均 O(n log n) 来自「每层 O(n) 分区 × 期望 O(log n) 深度」。",
        "最坏 O(n²) 的触发条件是每层极端分裂；随机基准把概率压到可忽略。",
        "递归区间是 [lo, p-1] 与 [p+1, hi]，不含 p，否则区间不收缩。",
        "主动延伸「只递归一侧即 O(n) 找第 K 大」，说明理解分区的作用。",
    ],
    "541b3f61c94a86a7": [
        "O(n²) 的状态必须先给：dp[i] = 以 nums[i] 结尾的 LIS 长度。",
        "O(n log n) 的关键是换状态：tails[k] = 长度 k+1 的最小结尾。",
        "tails 严格递增（否则可用反证推翻），因此可以二分。",
        "替换 tails[i] 是「该长度取得更优结尾」，不是删除，也不是记录路径。",
        "答案 = len(tails)；主动说明 tails 本身不是一条子序列。",
    ],
    "034602d65c3c3d83": [
        "哑结点占住链头，让「插入第一个结点」不再是特例。",
        "尾插：谁小接谁，接完推进 tail。",
        "剩余整段直接挂上（O(1)），不要写成循环搬运。",
        "时间 O(m+n)、额外空间 O(1)，要能主动报出来。",
        "递归版可行但栈深 O(m+n)，长链表会溢出——主动指出是加分项。",
    ],
    "bd4885b4390f3133": [
        "核心是分层：while 内先取 len(q) 快照，且必须在任何入队之前取。",
        "只弹出快照数量个结点，本层结束再回到 while。",
        "空间是 O(w)（最宽层），不是 O(n)。",
        "空树返回 [] 而不是 [[]]。",
        "变形（锯齿、右视图、每层最值）都只需改内层循环。",
    ],
    "68cee1fb263dc177": [
        "左括号入栈，右括号必须「栈非空且与栈顶配对」，否则立即 False。",
        "两个失败点缺一不可：右括号无对象、扫完栈非空。",
        "结尾 return not stack；空串合法。",
        "为什么不能用计数器：\"([)]\" 数量配平但顺序非法。",
        "时间 O(n)，最坏空间 O(n)（全左括号输入）。",
    ],
    "ae9b3bd5f0c0ec14": [
        "三个指针：i 指向 nums1 有效段尾、j 指向 nums2 尾、k 指向 nums1 末位。",
        "每轮把较大的写到 nums1[k]，k 与对应读指针同步递减。",
        "循环条件只需 j >= 0；nums1 剩余前段本来就在正确位置。",
        "为什么能从后往前：k ≥ i+1 恒成立，写入不会覆盖未读元素。",
        "时间 O(m+n)、额外空间 O(1)；对比「从前向后需要 O(m) 缓冲」。",
    ],
    "cc9024199418b8b6": [
        "哑结点让 left == 1 不再是特例（否则没有 pre 可用）。",
        "pre 全程不动，cur 始终是反转段的尾。",
        "循环次数恰为 right-left：把除 cur 外的结点逐个搬到段头之前。",
        "三段赋值不能乱序：先记住 nxt，再摘掉，再插入，最后更新 pre.next。",
        "断链成环是这类题最常见的运行时故障，写完要手动走一遍指针。",
    ],
    "ce573ed982fd7269": [
        "三步流水线：找中点 → 反转后半段 → 交替合并。",
        "找中点用 while fast.next and fast.next.next，使 slow 停在前半段末。",
        "反转前必须 slow.next = None，否则两条链成环、合并阶段死循环。",
        "合并循环条件是 while l2（奇数长度时前半段更长）。",
        "O(n) 时间、O(1) 空间；主动对比数组法的 O(n) 空间取舍。",
    ],
    "8cfadace34fdffa0": [
        "循环条件必须含 carry，否则 \"9\"+\"1\" 会丢最高位。",
        "越界位补 0，保证两数长度不等时不错位。",
        "本位 s % 10、新进位 s // 10；结果低位先产出，最后要反转。",
        "用 list + join，不要在循环里做字符串首插（那是 O(n²)）。",
        "时间 O(max(m,n))、空间 O(max(m,n))；骨架可直接迁移到二进制求和与链表两数相加。",
    ],
    "fa012b290cb172ce": [
        "快指针走 2、慢指针走 1；有环必相遇，无环快指针先到 None。",
        "相遇的根据是「相对速度恒为 1」，不是「快指针绕了一圈」。",
        "循环条件必须双判空：while fast and fast.next，否则访问 fast.next.next 会崩。",
        "比较的是结点身份（is）而不是值。",
        "O(n) 时间、O(1) 空间；主动说明哈希法可做但空间为 O(n)。",
    ],
    "25052c937d781b08": [
        "与「保留一个」的区别：重复的值整段删除，一个都不留。",
        "哑结点消掉「删除头结点」的特例。",
        "判断对象是 cur 的**后面两个**，因此不需要 prev 指针。",
        "发现重复后内层 while 要把该值的整段吞掉。",
        "复杂度仍是 O(n)：内层每轮永久摘掉一个结点，总次数 ≤ n。",
    ],
    "820e5d46ff3a9ca9": [
        "两个游标都从 dummy 起步，才能覆盖 n == 链表长度（删头）的情形。",
        "第一阶段 fast 先走 n 步，拉开固定下标差；第二阶段同步走到 fast.next 为 None。",
        "slow 最终落在待删结点的前驱上，执行 slow.next = slow.next.next。",
        "注意「相隔 n」是下标差，不是中间隔 n 个结点。",
        "时间 O(L)、额外空间 O(1)；两遍扫描正确但多一趟遍历。",
    ],
    "89c412c833ced6e2": [
        "双职责：向上返回单边最大贡献，结点处用双边和更新全局答案。",
        "路径不能在父结点处分岔，所以返回值里只能出现 max(left, right)。",
        "负贡献取 max(..., 0)：不选它比选它更好。",
        "best 初始化为负无穷，否则全负树会错误地返回 0。",
        "时间 O(n)、空间 O(h)；每个结点只访问一次，不需要记忆化。",
    ],
    "d80b9ddcb5f113ce": [
        "五条判据：段长 1~3、无前导零、≤ 255、必须 4 段、必须用尽整串。",
        "两个终止条件要分开写：切满 4 段、且 start == n 才收集结果。",
        "非法时可以 break 而不是 continue（更长的候选段必然同样非法）。",
        "剪枝：剩余字符数必须落在 [剩余段数, 剩余段数 × 3]。",
        "段数固定为 4、每段 ≤ 3 位，搜索空间是常数级，整体 O(n) 上界。",
    ],
}


# ===========================================================================
# 组装 out-problems-01.json
# ===========================================================================
def build() -> int:
    inp_path = HERE / "in-problems-01.json"
    if not inp_path.exists():
        print(f"[err] 缺少 {inp_path.name}，先跑 make_agent_batches.py")
        return 1
    inp = json.loads(inp_path.read_text("utf-8"))
    want = [r["id"] for r in inp["items"]]

    missing = [i for i in want if i not in CONTENT]
    extra = [i for i in CONTENT if i not in want]
    if missing or extra:
        print(f"[err] 覆盖不一致：未写 {missing}；多写 {extra}")
        return 1

    entries = []
    for r in inp["items"]:
        e = dict(CONTENT[r["id"]])
        e["id"] = r["id"]
        # tags 与 entities 必须是字符串列表，否则前端渲染会出 undefined
        e["tags"] = [str(t) for t in e.get("tags") or []]
        e["entities"] = [str(t) for t in e.get("entities") or []]
        # keyPoints 同时供前端「得分要点」与题库页使用；写进 problem 块是为了让
        # build_problem_bank.py 的 pick(pb.keyPoints, p.keyPoints) 拿到同一份清单。
        kp = KEYPOINTS.get(r["id"]) or []
        if not kp:
            print(f"[warn] {r['id']} 没有 keyPoints，REQ_FULL 校验会失败")
        e["keyPoints"] = list(kp)
        e["problem"]["keyPoints"] = list(kp)
        entries.append(e)

    doc = {
        "batchId": "problems-01",
        "generatedBy": "_gen_bank_problems.py（作者工具，非流水线）",
        "note": ("题库批次：按 CodeTop 被考频度排序的前 14 道题，逐题实做。"
                 "每段 solution.python 都用 exec 跑过并通过边界用例断言；"
                 "problem.solution.python_alt 给出第二种解法并与主解交叉验证。"),
        "entries": entries,
        "skipped": [],
    }
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)

    print(f"wrote {OUT.name}: {len(entries)} entries, {OUT.stat().st_size} bytes")
    for e in entries:
        pb = e["problem"]
        print(f"  [{e['difficulty']:<6}] {pb['title'][:34]:36s} "
              f"code={len(pb['solution']['python']):>4}c "
              f"alt={len(pb['solution']['python_alt']):>4}c "
              f"pitfalls={len(pb['pitfalls'])} edges={len(pb['edgeCases'])} "
              f"prog={len(e['teaching']['progressive'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())

