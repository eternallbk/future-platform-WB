#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
personalize_plan.py — 按你的真实起点重排学习路线（一次性、可重复执行）

为什么需要单独一步：
  `build_learning_kb.py` 生成的是**通用**路线（假设从零开始、四条方向等权重）。
  但你的情况是：PyTorch 熟练、已有一篇 ICLR 多模态分割论文、刷题只覆盖了 hot100 的一部分。
  这直接改变优先级：
    · 最大面试风险 = 手撕题，而不是理论 → 手撕题必须单独成一条 core 路线，且排在前面
    · 已有产出 = 论文 → 需要的是「把它讲成 3 个长度、扛住 12 类追问」，而不是再读一堆论文
    · 后训练 / 世界模型 是你目标方向里最缺的两块 → 提到最前
    · 生成式模型（Diffusion）可以降为支撑（你已有论文带来的表示学习直觉，学起来更快）

这一步只改 tracks 的顺序/等级、加入你的 profile、并注入针对性的手撕清单；
它不动 papers/repos/courses 的具体内容，也不碰 build_learning_kb.py 的源数据。

用法: python scripts/personalize_plan.py [--interests-lite]
   --interests-lite  同时把采集器的 interests 权重从「均衡」改为「按你的优先级倾斜」
"""
from __future__ import annotations

import argparse
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"
LEARN = DATA / "learning.json"
CONFIG = ROOT / "config" / "collector.config.json"
CST = timezone(timedelta(hours=8))

PROFILE = {
    "updatedAt": None,   # filled at runtime
    "degree": "人工智能专业在读硕士",
    "target": "算法实习（多模态 / 后训练 / 生成式 / 世界模型）",
    "horizonMonths": 6,
    "startingPoint": {
        "pytorch": {"level": "熟练", "note": "能独立写训练脚本；面试里这项是加分项，要在项目叙述里体现"},
        "research": {"level": "已有产出", "note": "一篇多模态分割方向 ICLR 论文"},
        "coding": {"level": "偏弱", "note": "LeetCode Hot 100 只覆盖了一部分；这是当前最大面试风险"},
        "rl": {"level": "待确认", "note": "后训练与世界模型都依赖 RL 基础，请按第一周模块自测后回调"},
    },
    "priorityOrder": [
        "1. 手撕题（最大风险，必须现在就补，且要贯穿全程）",
        "2. ICLR 论文的项目化讲述（已有资产，立刻变成面试武器）",
        "3. 后训练 SFT→DPO→GRPO 闭环（目标方向里最缺、岗位最热）",
        "4. 世界模型 / VLA（第二目标方向）",
        "5. 多模态深化（已有论文打底，重点是补齐 VLM 架构与评测）",
        "6. 生成式模型 / 工程与系统（支撑，按需按岗位补）",
    ],
    "howToUse": [
        "每天固定 40 分钟手撕题，限时、写完立刻对照参考实现；不要攒到面试前一周",
        "论文讲述要现在就建立模板，之后每读一篇新论文都用同一套结构复述",
        "每条路线的任务都带验收标准，勾到 100% 才算完成；工作台「学习路线」页可勾选",
    ],
}

CODING_TRACK = {
    "id": "coding",
    "name": "手撕题冲刺（针对你的短板）",
    "level": "core",
    "durationWeeks": 3,
    "goal": ("把 LeetCode Hot 100 的缺口补齐，并掌握大模型岗特有的「手写算子」题型。"
             "验收：任何一道 Hot 100 中等题能在 18 分钟内无提示写出并通过；"
             "能在 15 分钟内从零写出数值稳定的 Multi-Head Self-Attention。"),
    "prerequisites": ["Python 基本语法", "会看复杂度（时间/空间）"],
    "modules": [
        {
            "title": "数组 / 滑动窗口 / 双指针（Hot 100 最高频）",
            "week": 1, "hours": 8,
            "objectives": ["把最高频的数组类模板练成肌肉记忆", "能一眼判断该用滑窗还是双指针"],
            "concepts": ["滑动窗口", "双指针", "前缀和", "原地哈希"],
            "tasks": [
                {"title": "两数之和 → 三数之和（哈希 → 排序双指针）", "type": "drill", "estimateHours": 1.5,
                 "deliverable": "两份代码 + 复杂度说明", "done": "能解释为什么三数之和要先排序、如何去重"},
                {"title": "无重复字符的最长子串 + 找到字符串中所有字母异位词", "type": "drill", "estimateHours": 1.5,
                 "deliverable": "滑窗模板", "done": "能不看模板写出可变/固定窗口两种写法"},
                {"title": "移动零 + 盛最多水的容器 + 接雨水", "type": "drill", "estimateHours": 2,
                 "deliverable": "代码 + 边界用例", "done": "接雨水能写出双指针 O(1) 空间解法"},
                {"title": "只出现一次的数字 + 多数元素", "type": "drill", "estimateHours": 1,
                 "deliverable": "位运算笔记", "done": "能解释异或的性质与 Boyer-Moore 投票的正确性"},
            ],
            "paperIds": [], "repoIds": ["the_algorithms"], "courseIds": [],
        },
        {
            "title": "链表 / 二叉树（必考，且容易写错指针）",
            "week": 1, "hours": 7,
            "objectives": ["掌握链表指针操作与二叉树遍历三类模板"],
            "concepts": ["虚拟头结点", "快慢指针", "递归/迭代遍历", "BST 性质"],
            "tasks": [
                {"title": "反转链表 + K 个一组翻转 + 合并两个有序链表", "type": "drill", "estimateHours": 2,
                 "deliverable": "代码 + 手画指针变化图", "done": "K 个一组能一次写对边界（不足 K 个不翻转）"},
                {"title": "环形链表 II（快慢指针找入口）", "type": "drill", "estimateHours": 1,
                 "deliverable": "推导笔记", "done": "能推导出相遇点到入口的距离关系"},
                {"title": "二叉树的中/前/后/层序遍历（递归 + 迭代）", "type": "drill", "estimateHours": 2,
                 "deliverable": "四套模板", "done": "能默写迭代版中序遍历与层序遍历"},
                {"title": "最近公共祖先 + 验证二叉搜索树", "type": "drill", "estimateHours": 1.5,
                 "deliverable": "代码", "done": "能说清 BST 校验为什么不能只比较父子节点"},
            ],
            "paperIds": [], "repoIds": ["the_algorithms"], "courseIds": [],
        },
        {
            "title": "动态规划 / 单调栈 / 并查集",
            "week": 2, "hours": 10,
            "objectives": ["建立 DP 的状态定义直觉", "掌握单调栈与并查集模板"],
            "concepts": ["状态定义", "转移方程", "单调栈", "并查集", "拓扑排序"],
            "tasks": [
                {"title": "爬楼梯 + 打家劫舍 + 最长递增子序列", "type": "drill", "estimateHours": 2,
                 "deliverable": "三份代码 + 状态定义说明", "done": "LIS 能写出 O(n log n) 的贪心+二分"},
                {"title": "零钱兑换 + 编辑距离 + 最长回文子串", "type": "drill", "estimateHours": 3,
                 "deliverable": "DP 表格手推", "done": "能手工填出编辑距离的 DP 表并解释转移"},
                {"title": "每日温度 + 柱状图中最大的矩形（单调栈）", "type": "drill", "estimateHours": 2,
                 "deliverable": "单调栈模板", "done": "能说清单调栈里存的是下标而不是值的原因"},
                {"title": "岛屿数量 + 省份数量（并查集 / DFS）", "type": "drill", "estimateHours": 1.5,
                 "deliverable": "并查集模板（含路径压缩）", "done": "能默写带路径压缩与按秩合并的并查集"},
                {"title": "课程表（拓扑排序）", "type": "drill", "estimateHours": 1.5,
                 "deliverable": "BFS/DFS 两种解法", "done": "能解释环检测的判断点在哪"},
            ],
            "paperIds": [], "repoIds": ["the_algorithms"], "courseIds": [],
        },
        {
            "title": "大模型岗特有手写题（与你的方向直接相关）",
            "week": 3, "hours": 10,
            "objectives": ["把面试最常考的手写算子练到能一次写对"],
            "concepts": ["MHA", "RoPE", "RMSNorm", "交叉熵", "采样策略", "对比损失"],
            "tasks": [
                {"title": "从零写 Multi-Head Self-Attention（含 causal mask 与缩放）", "type": "drill",
                 "estimateHours": 2, "deliverable": "可运行代码 + 单元测试",
                 "done": "能与 nn.MultiheadAttention 数值对齐（误差 <1e-5）"},
                {"title": "手写数值稳定的 softmax 与交叉熵", "type": "drill", "estimateHours": 1,
                 "deliverable": "代码 + 解释", "done": "能说明减最大值的必要性并给出溢出反例"},
                {"title": "手写 RMSNorm 与 SwiGLU", "type": "drill", "estimateHours": 1.5,
                 "deliverable": "代码", "done": "能解释 RMSNorm 相对 LayerNorm 省掉了什么"},
                {"title": "手写 RoPE（含位置缓存）", "type": "drill", "estimateHours": 1.5,
                 "deliverable": "代码", "done": "能解释内积为何只依赖相对距离"},
                {"title": "手写 top-k / top-p / 温度采样", "type": "drill", "estimateHours": 1.5,
                 "deliverable": "代码", "done": "能说清三者叠加时的顺序与影响"},
                {"title": "手写 CLIP 双向对比损失（用你的论文方向做例子）", "type": "drill", "estimateHours": 1.5,
                 "deliverable": "代码 + 与论文的对应关系", "done": "能解释负样本数量与 batch size 的关系"},
            ],
            "paperIds": [], "repoIds": ["minGPT", "the_algorithms"], "courseIds": [],
        },
    ],
}

PAPER_TRACK = {
    "id": "paper",
    "name": "ICLR 论文的项目化讲述（把你的已有资产变成武器）",
    "level": "core",
    "durationWeeks": 2,
    "goal": ("同一篇多模态分割论文，能分别用 30 秒 / 2 分钟 / 5 分钟讲清楚，并能扛住 12 类高频追问。"
             "验收：模拟面试里连续追问 5 轮不卡壳；能主动指出自己方法的失效边界。"),
    "prerequisites": ["你已经发表的那篇 ICLR 论文"],
    "modules": [
        {
            "title": "三档长度的讲法",
            "week": 1, "hours": 6,
            "objectives": ["按面试官给的时间自由伸缩", "把 motivation 压缩成一句话"],
            "concepts": ["问题定义", "方法动机", "核心贡献", "实验结论"],
            "tasks": [
                {"title": "写 30 秒版：问题 → 为什么现有方法不行 → 你的关键想法 → 结果", "type": "project",
                 "estimateHours": 2, "deliverable": "逐字稿（≤120 字）",
                 "done": "说给不懂该方向的人听，对方能复述出你的核心贡献"},
                {"title": "写 2 分钟版：加上方法细节与消融证据", "type": "project", "estimateHours": 2,
                 "deliverable": "逐字稿 + 结构图", "done": "不看稿能讲完，且不超过 2 分 15 秒"},
                {"title": "写 5 分钟版：加上与同行的对比、局限与未来工作", "type": "project",
                 "estimateHours": 2, "deliverable": "逐字稿 + 3 张图", "done": "能回答「和 XXX 方法比强在哪」"},
            ],
            "paperIds": [], "repoIds": [], "courseIds": [],
        },
        {
            "title": "抗追问清单（12 类高频问题）",
            "week": 2, "hours": 6,
            "objectives": ["提前准备每一类追问的答案", "把弱点转化成可信度"],
            "concepts": ["消融设计", "基线选择", "失效边界", "复现成本"],
            "tasks": [
                {"title": "准备 12 类追问的答案（见下方清单）", "type": "study", "estimateHours": 3,
                 "deliverable": "问答文档", "done": "每类都能给出一句结论 + 一个证据"},
                {"title": "准备「失败实验」故事：哪些尝试没 work，为什么", "type": "study",
                 "estimateHours": 1.5, "deliverable": "一段 60 秒叙述",
                 "done": "能说清从失败中学到什么、如何影响后续设计"},
                {"title": "对着录音讲 3 遍并回听，标出卡壳点", "type": "project", "estimateHours": 1.5,
                 "deliverable": "复盘记录", "done": "第二遍不再出现同类卡壳"},
            ],
            "paperIds": [], "repoIds": [], "courseIds": [],
        },
    ],
}

# 12 类高频追问，写进 profile 供你逐个准备
PAPER_QUESTIONS = [
    "1. 一句话说清你这篇解决了什么问题？为什么这个问题重要？",
    "2. 你的方法和最接近的那篇工作（baseline）核心区别是什么？",
    "3. 你方法里最关键的设计是哪一个？去掉它会掉多少？（要能报出消融数字）",
    "4. 为什么用这个损失函数 / 这个监督信号？换成别的会怎样？",
    "5. 训练需要多少数据 / 多少卡 / 多久？复现成本评估过吗？",
    "6. 你的评测指标能真正反映你想解决的问题吗？有没有指标失效的情况？",
    "7. 在什么场景下你的方法会失效？边界条件是什么？",
    "8. 如果给你更多算力，你会优先做什么？为什么不是别的？",
    "9. 这篇工作能被工业界用起来还差什么？",
    "10. 你做这个课题时走过哪些弯路？失败实验给了你什么信息？",
    "11. 如果现在重做，你会改哪一步？",
    "12. 这篇工作和多模态大模型（VLM）的关系是什么？能不能接到 LLM 上？",
]

# 按你的优先级重排（数字越小越靠前）
TRACK_ORDER = ["posttrain", "paper", "coding", "world", "mllm", "gen", "eng", "agent"]
LEVEL_OVERRIDE = {"posttrain": "core", "paper": "core", "coding": "core", "world": "core",
                  "mllm": "core", "gen": "support", "eng": "support", "agent": "support"}
# 里程碑重排：先把最大风险（手撕）与既有资产（论文）排到最前
MILESTONE_ORDER = ["m4", "m5", "m1", "m2", "m10", "m11", "m12", "m3", "m8", "m6", "m7", "m9"]

# 采集权重：按你的方向倾斜（multimodal/posttraining/worldmodel 提权，其余降权）
INTERESTS = {
    "multimodal": 1.00,
    "posttraining": 1.00,
    "worldmodel": 1.00,
    "rl": 0.90,          # 后训练与世界模型都依赖它，不能低
    "generative": 0.75,
    "agent": 0.70,
    "foundation": 0.60,
    "engineering": 0.65,
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="personalize_plan.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--interests-lite", action="store_true",
                    help="also retune config/collector.config.json interests to your direction")
    args = ap.parse_args(argv)

    if not LEARN.exists():
        print(f"missing {LEARN}; run scripts/build_learning_kb.py first")
        return 1

    payload = json.loads(LEARN.read_text("utf-8"))
    tracks = payload.get("tracks") or []
    by_id = {t["id"]: t for t in tracks}

    before = [t["id"] for t in tracks]

    # Inject the two new personalised tracks.
    by_id["coding"] = CODING_TRACK
    by_id["paper"] = PAPER_TRACK

    for tid, level in LEVEL_OVERRIDE.items():
        if tid in by_id:
            by_id[tid]["level"] = level

    ordered = [by_id[t] for t in TRACK_ORDER if t in by_id]
    for t in tracks:                      # keep any track I did not list
        if t["id"] not in TRACK_ORDER:
            ordered.append(t)

    # Re-order milestones so the highest-risk / highest-leverage ones come first.
    ms = payload.get("milestones") or []
    ms_by_id = {m["id"]: m for m in ms}
    new_ms = [ms_by_id[i] for i in MILESTONE_ORDER if i in ms_by_id]
    for m in ms:
        if m["id"] not in MILESTONE_ORDER:
            new_ms.append(m)
    for idx, m in enumerate(new_ms, 1):
        m["priority"] = idx

    # Two extra milestones that match the new tracks.
    if "mCoding" not in {m["id"] for m in new_ms}:
        new_ms.insert(1, {
            "id": "mCoding", "week": 1, "priority": 2,
            "title": "手撕题：Hot 100 缺口补齐第一轮",
            "acceptance": ["数组/链表/二叉树三类模板能默写",
                           "每天 40 分钟限时训练，连续 7 天不断",
                           "整理出自己的易错清单（≥10 条）"],
            "evidence": "题库进度 + 易错清单文件", "trackIds": ["coding"],
        })
    if "mPaper" not in {m["id"] for m in new_ms}:
        new_ms.insert(0, {
            "id": "mPaper", "week": 1, "priority": 1,
            "title": "ICLR 论文：30 秒 / 2 分钟 / 5 分钟三档讲法完成",
            "acceptance": ["三档逐字稿各一份且不看稿能讲完",
                           "12 类追问每类都有答案 + 证据",
                           "录音复盘两轮，第二轮无同类卡壳"],
            "evidence": "逐字稿 + 问答文档 + 录音", "trackIds": ["paper"],
        })

    PROFILE["updatedAt"] = datetime.now(CST).isoformat(timespec="seconds")
    PROFILE["paperQuestions"] = PAPER_QUESTIONS
    PROFILE["personalizedFrom"] = "generic plan (all directions equal weight, assumed zero coding)"

    payload["tracks"] = ordered
    payload["milestones"] = new_ms
    payload["profile"] = PROFILE
    payload.setdefault("meta", {})
    payload["meta"]["personalizedAt"] = PROFILE["updatedAt"]
    payload["meta"]["personalizedBy"] = "personalize_plan.py"
    payload["meta"]["counts"] = {
        "tracks": len(ordered),
        "papers": len(payload.get("papers") or []),
        "repos": len(payload.get("repos") or []),
        "courses": len(payload.get("courses") or []),
        "milestones": len(new_ms),
    }

    with io.open(LEARN, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    total_tasks = sum(len(m["tasks"]) for t in ordered for m in t["modules"])
    total_hours = sum(k["estimateHours"] for t in ordered for m in t["modules"] for k in m["tasks"])
    print(f"wrote {LEARN} ({LEARN.stat().st_size} bytes)")
    print(f"  track order: {' -> '.join(before)}")
    print(f"           ==>  {' -> '.join(t['id'] for t in ordered)}")
    print(f"  tracks={len(ordered)} tasks={total_tasks} hours={total_hours} milestones={len(new_ms)}")
    print(f"  profile written with {len(PAPER_QUESTIONS)} paper questions")

    if args.interests_lite and CONFIG.exists():
        cfg = json.loads(CONFIG.read_text("utf-8"))
        old = dict(cfg.get("interests") or {})
        cfg["interests"] = dict(INTERESTS)
        with io.open(CONFIG, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
        print(f"retuned interests: {old} -> {INTERESTS}")
        print("run `python scripts/collect.py --rescore` so existing items pick up the new weights")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
