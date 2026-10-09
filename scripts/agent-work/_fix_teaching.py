#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_fix_teaching.py — 一次性修补脚本（作者工具）。

背景：在给 14 道题手写内容时，第 6~14 道题的 teaching() 调用里误把 problem() 的
edge_cases / tips 写了进去，同时漏了 ownAnalysis / officialNotes / interviewAnswer
三个必填字段。手改 9 处容易越改越乱，所以用 AST 定位、按参数名重建调用。

做法：
  1. 用 ast 找到每个 teaching() 调用，取各参数的源码片段；
  2. 丢掉误混的 edge_cases / tips；
  3. 插入本文件里给出的三个字段（内容逐题手写，不是自动生成）；
  4. 按契约顺序重建调用文本，写回文件。
"""
from __future__ import annotations

import ast
import io
from pathlib import Path

P = Path(__file__).resolve().parent / "_gen_bank_problems.py"

# 逐题补齐的三个字段：key = 题号（用于人工核对），内容按题写好。
FILL = {
    6: dict(
        ownAnalysis=(
            "这道题值得迁移的是「读写指针的相对位置决定要不要缓冲」这条判断。"
            "同一份数据上，只要写指针始终落在读指针「已消费」的一侧，就可以原地改写而不丢信息。"
            "这个视角在「移除元素」「移动零」「原地归并」里完全一样，"
            "只是「哪一侧安全」的结论不同。写原地算法时先画一次读写两指针的位置关系，"
            "比直接凭直觉写要可靠得多。"),
        officialNotes=[
            {"position": "官方题解的第一解就是「双指针从后向前」，"
                         "并明确指出它避免了 nums1 前段被覆盖的问题。",
             "source": "LeetCode 88 官方题解 · 合并两个有序数组"},
            {"position": "归并两个有序序列是稳定排序的基础操作；"
                         "从后向前归并只在「目标数组尾部有空位」时可用。",
             "source": "算法导论 · 归并排序"},
        ],
        interviewAnswer=(
            "一句话开场：「从后往前，三个指针，O(1) 额外空间」。"
            "然后写代码，写完立刻解释「k 永远在未读区的右边，所以不会覆盖」。"
            "主动对比一句「从前向后需要 O(m) 缓冲，因为 nums1 前段会被覆盖」——"
            "这一句能证明你不是背下来的，而是理解取舍。"),
    ),
    7: dict(
        ownAnalysis=(
            "这题最值得记的是「pre 不动、cur 恒为段尾」这个不变式。"
            "链表题的复杂度几乎全在「有几个指针、各自指向哪、什么时候动」上；"
            "把不变式先写下来（哪怕只是在注释里），正确率会明显提升。"
            "另外它演示了「局部问题 = 区间定位 + 区间内操作」的分解方式，"
            "同一套分解直接用在「K 个一组翻转」上。"),
        officialNotes=[
            {"position": "官方题解给出「一次遍历 + 头插」的 O(1) 空间解法，"
                         "并强调用哑结点统一 left == 1 的情形。",
             "source": "LeetCode 92 官方题解 · 反转链表 II"},
        ],
        interviewAnswer=(
            "先说结构：「哑结点 + 头插法，pre 全程不动」。"
            "然后强调两处细节：循环次数是 right-left，以及 pre 不前进。"
            "写完用手动例子走一遍（1→2→3→4→5, left=2, right=4），边写边报三个指针的位置。"
            "如果被问另一种做法，答「切段反转再拼接，但要管 4 个接点」。"),
    ),
    8: dict(
        ownAnalysis=(
            "这道题的价值在于「组合」：它本身没有新算法，"
            "而是把快慢指针、链表反转、交替合并三件已有零件串成流水线。"
            "面试里这类题的区分度其实更高——因为任何一件零件记错都会让整个程序崩，"
            "而崩的方式往往是死循环（成环）而不是报错。"
            "养成「每次断链/接链后画一遍指针图」的习惯，比背题更有用。"),
        officialNotes=[
            {"position": "官方题解明确要求「不能只改变结点内部的值」，"
                         "并把最优解定为「找中点 + 反转后半段 + 交替合并」的 O(1) 空间版本。",
             "source": "LeetCode 143 官方题解 · 重排链表"},
        ],
        interviewAnswer=(
            "开口报三步，第二步末尾主动强调「必须把 slow.next 置 None，否则成环死循环」"
            "——这句话通常是面试官在等的。然后用手动例子（长度 4 与长度 5 各一次）"
            "展示奇偶两种切分的差别。最后报 O(n) 时间、O(1) 空间，"
            "并说明「数组法也行但空间是 O(n)」。"),
    ),
    9: dict(
        ownAnalysis=(
            "模拟题的通用套路是「对齐 + 逐位 + 进位」三件套。"
            "真正容易错的是循环边界：必须让「还有进位」成为一个独立的继续条件。"
            "这条经验在乘法、阶乘、任意进制转换里都会再遇到——"
            "凡是「低位影响高位」的计算，边界都要多留一轮。"),
        officialNotes=[
            {"position": "官方题解给出「模拟竖式」解法，并强调不能使用内建大整数类型；"
                         "Python 因整数无溢出，官方也提示了这一点。",
             "source": "LeetCode 415 官方题解 · 字符串相加"},
            {"position": "配套题「二进制求和」（67）与「两数相加」（2）共用同一骨架，"
                         "只是基数或取位方式不同。",
             "source": "LeetCode 67 / 2"},
        ],
        interviewAnswer=(
            "两个关键句：循环条件必须含 carry、结果用 list + join 而不是字符串首插。"
            "开场就抛出 \"9\"+\"1\" 这个反例，直接证明你知道边界在哪。"
            "如果被问「Python 不是有 int 吗」，如实说明有、但按要求写模拟，"
            "并且这个骨架能直接复用到二进制求和与链表两数相加。"),
    ),
    10: dict(
        ownAnalysis=(
            "Floyd 判圈的真正知识点是「相对速度」，而不是「快慢指针」这四个字。"
            "一旦理解「快指针相对慢指针每轮净追 1 格」，"
            "就能自己推出为什么一定会相遇、以及为什么快指针不能改走 3 步。"
            "同一套相对运动的思路还能解释 142 的「相遇后重置指针找入口」，"
            "值得把它当成一个推导而不是两条结论来记。"),
        officialNotes=[
            {"position": "官方题解给出「哈希表」与「Floyd 判圈」两种解法，"
                         "并把后者作为满足 O(1) 空间要求的解法。",
             "source": "LeetCode 141 官方题解 · 环形链表"},
        ],
        interviewAnswer=(
            "重点讲清「相对速度恒为 1，所以必然相遇」，而不是背代码。"
            "写代码时显式写出 `while fast and fast.next` 并解释双判空的原因"
            "（要安全访问 fast.next.next）。如果面试官顺势问 142，"
            "答「相遇后把慢指针放回头部、两者同速前进，再次相遇点即入口」，"
            "并说明这需要额一次推导。"),
    ),
    11: dict(
        ownAnalysis=(
            "这题的核心识别点是「判断下一对」这个技巧——它把「需要 prev 才能删当前结点」"
            "变成「站在前驱位置上删后继」，于是省掉一个指针。"
            "更值得记的是复杂度论证方式：嵌套 while 但内层每轮永久摘掉一个结点，"
            "所以总代价仍是线性的。面试里遇到双层循环先别急着报 O(n²)，"
            "数一数内层「消耗了什么不可再生的资源」。"),
        officialNotes=[
            {"position": "官方题解使用哑结点 + 一次遍历，"
                         "并在发现重复值后把该值的整段全部跳过。",
             "source": "LeetCode 82 官方题解 · 删除排序链表中的重复元素 II"},
        ],
        interviewAnswer=(
            "第一句点明与 83 的差别：「重复的整段删除，一个都不留」。"
            "然后强调哑结点（消掉删头特判）与「看下一对」（省掉 prev）。"
            "被问复杂度时主动给出「内层每轮摘掉一个结点，总代价线性」的论证，"
            "这一步往往比代码本身更能体现水平。"),
    ),
    12: dict(
        ownAnalysis=(
            "「定距双指针」的本质是把「倒序位置」换算成「下标差」。"
            "由于单链表只能正向走，无法预知长度，所以用两个指针的相对位置替代绝对长度。"
            "同一思想在数组上就是固定窗口（滑动窗口），"
            "在链表上就是这道题——理解「相对距离可以替代绝对位置」"
            "是很多双指针题能一眼看出解法的原因。"),
        officialNotes=[
            {"position": "官方题解给出两种解法：计算链表长度后删除（两趟），"
                         "以及用双指针一趟完成；后者满足进阶要求。",
             "source": "LeetCode 19 官方题解 · 删除链表的倒数第 N 个结点"},
        ],
        interviewAnswer=(
            "两个必说点：从 dummy 起步（覆盖 n == 链表长度，也就是删头）、"
            "第二阶段以 fast.next 为终止条件（slow 才停在待删结点之前）。"
            "写完用手动例子（1→2→3→4→5, n=2）演示两个指针的位置。"
            "被问「能不能不用哑结点」时答「可以，但要单独处理删头」。"),
    ),
    13: dict(
        ownAnalysis=(
            "树形 DP 的通用模式是「返回值服务于父结点，附加状态记录以自己为根的答案」。"
            "本题是它最简洁的形态：返回值是单边链、答案是双边和。"
            "掌握这个「返回 / 更新」双职责后，「树的直径」「打家劫舍 III」"
            "（返回两个状态：抢/不抢）都能顺着同一思路推出来，"
            "不需要分别背题。"),
        officialNotes=[
            {"position": "官方题解指出「路径的最高点可以是任意结点」，"
                         "并用后序 DFS 在每个结点处更新答案、同时向上返回单边最大贡献。",
             "source": "LeetCode 124 官方题解 · 二叉树中的最大路径和"},
        ],
        interviewAnswer=(
            "开口就把双职责讲清：「向上返回单边、答案用双边」，"
            "并说明「路径不能在父结点处分岔」这个理由。"
            "然后解释 `max(..., 0)` 与 `best = -inf` 两处初始化。"
            "最后用 [-3] 说明为什么 best 不能初始化为 0——"
            "这个用例能一次性证明你理解「路径至少含一个结点」。"),
    ),
    14: dict(
        ownAnalysis=(
            "定段数划分的回溯模板是「dfs(起点, 已选部分) + 段数上限 + 合法性判据」。"
            "把它和「分割回文串」放在一起看，差别只在「段数是否固定」与「判据是什么」。"
            "本题另一个值得记的习惯是「非法时 break 而不是 continue」——"
            "这在候选长度单调递增时普遍成立，能省掉大量无效分支，"
            "而且在解释「为什么可以提前结束」时是一个清晰的得分点。"),
        officialNotes=[
            {"position": "官方题解使用回溯（DFS）枚举每段长度，"
                         "并给出段长 1~3、无前导零、≤ 255 三条合法性判据。",
             "source": "LeetCode 93 官方题解 · 复原 IP 地址"},
        ],
        interviewAnswer=(
            "一次性把五条判据报道：段长 1~3、无前导零、≤ 255、必须 4 段、必须用尽整串。"
            "写 DFS 时把两个终止条件的先后写清楚，并解释「为什么非法可以 break」。"
            "最后用 \"010010\" 与 \"0000\" 自证边界正确——"
            "面试官几乎一定会拿其中一个来验证你。"),
    ),
}

ORDER = ["progressive", "socratic", "mechanism", "boundary", "analogyBoundary",
         "misconceptions", "ownAnalysis", "officialNotes", "interviewAnswer",
         "prereq", "next_steps"]


def main() -> int:
    src = io.open(P, encoding="utf-8").read()
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)

    # 收集所有 teaching() 调用，按出现顺序编号（第 1 个 = 第 1 题，依此类推）
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "teaching"]
    calls.sort(key=lambda n: n.lineno)

    edits = []                       # (start_offset, end_offset, replacement)
    offset_of_line = []
    acc = 0
    for ln in lines:
        offset_of_line.append(acc)
        acc += len(ln)

    fixed = 0
    for idx, call in enumerate(calls, start=1):
        seg = {k.arg: ast.get_source_segment(src, k.value) for k in call.keywords if k.arg}
        dirty = ("edge_cases" in seg or "tips" in seg)
        missing = [k for k in ORDER if k not in seg]
        if not dirty and not missing:
            continue
        if idx not in FILL:
            print(f"[skip] 第 {idx} 个 teaching() 需要修补，但 FILL 里没有对应内容")
            continue
        seg.update(FILL[idx])
        # 丢掉误混进来的 problem() 字段
        for bad in ("edge_cases", "tips", "pitfalls", "time_c", "space_c",
                    "why_c", "whyItWorks"):
            seg.pop(bad, None)

        body = ",\n".join(f"        {k}={seg[k]}" for k in ORDER if k in seg)
        new = "teaching(\n" + body + ",\n    )"

        start = offset_of_line[call.lineno - 1] + call.col_offset
        end = offset_of_line[call.end_lineno - 1] + call.end_col_offset
        edits.append((start, end, new))
        fixed += 1

    if not edits:
        print("无需修补")
        return 0

    for start, end, new in sorted(edits, reverse=True):
        src = src[:start] + new + src[end:]
    io.open(P, "w", encoding="utf-8", newline="\n").write(src)
    print(f"已修补 {fixed} 个 teaching() 调用")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
