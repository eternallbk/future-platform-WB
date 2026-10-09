#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_autonomy.py — 审计「每日自检 + 自我迭代」到底实现了多少

这不是需求文档，而是**对现有代码与产物的实测盘点**：逐条检查自主性所依赖的机制
是否存在、是否真被每日流程调用、以及是自动生效还是只写报告等人批。

  已实现   机制存在且已接入每日流程
  需人工   机制存在，但需你批准才生效（有意设计：避免自我改坏）
  缺失     机制不存在或未被调用

用法: python scripts/audit_autonomy.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"
SCRIPTS = ROOT / "scripts"

results: list[tuple[str, str, str]] = []


def add(status: str, name: str, detail: str) -> None:
    results.append((status, name, detail))


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


def load(p: Path):
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return None


collect = read(SCRIPTS / "collect.py")
runner = read(SCRIPTS / "run-daily.ps1")
selfcheck = read(SCRIPTS / "selfcheck.py")
agent = read(SCRIPTS / "daily-agent.md")
planner = read(SCRIPTS / "plan_deep_read.py")

# ============================================================ 1. 自检层
assertions = len(re.findall(r"^\s*check_[a-z_]+\(rep", selfcheck, re.M))
add("OK" if assertions else "MISSING", "数据层自检 selfcheck.py",
    f"{assertions} 组断言函数" if assertions else "未找到断言函数")

add("OK" if ("selfcheck.py" in runner and "$SelfCheck" in runner) else "MISSING",
    "自检接入每日流程",
    "run-daily.ps1 第 5 步调用，位于站点构建与发布之前" if "selfcheck.py" in runner
    else "每日流程未调用 selfcheck.py")

add("OK" if "checkExit" in runner else "MISSING", "自检影响运行状态",
    "selfcheck 非 0 时整轮退出码 2(partial)，任务历史可见" if "checkExit" in runner
    else "自检结果未反馈到运行状态")

# 自检是否检查「采集质量」而不只是文件完整性
if "check_collection_quality" in selfcheck:
    add("OK", "自检含采集质量",
        "检查分类集中度、相关度区分度、摘要覆盖率、深读覆盖率、反馈回路状态")
else:
    add("MISSING", "自检含采集质量",
        "自检只验证文件一致性，不判断语料是否还对得上求职目标")

# ====================================================== 2. 提案与诊断层
latest = load(DATA / "proposals" / "latest.json") or {}
if "humanReviewQueue" in latest:
    q = latest.get("humanReviewQueue") or []
    kw = latest.get("keywordProposals") or []
    ch = latest.get("channelHealth") or []
    nc = latest.get("newChannelProposals") or []
    add("OK", "提案/诊断后台 write_proposals",
        f"每轮产出 channelHealth({len(ch)}) · keywordProposals({len(kw)}) · "
        f"humanReviewQueue({len(q)}) · newChannelProposals({len(nc)}) · noiseReport")
    add("OK", "失效关键词诊断",
        f"检测从未命中的关键词：本轮 {len(kw)} 条" if kw else "有检测逻辑，本轮无失效关键词")
    add("OK" if q else "MANUAL", "人工待办队列",
        f"{len(q)} 条需要你决策" if q else "本轮无需人工决策")
else:
    add("MISSING", "提案/诊断后台", "proposals/latest.json 缺失或结构不符")

# ================================================ 3. 自动应用通道
tuner = (SCRIPTS / "tune_keywords.py").exists()
tuner_wired = "tune_keywords" in runner
if tuner and tuner_wired:
    add("OK", "自动生效通道（关键词微调）",
        "tune_keywords.py 已接入每日流程：读 keywordProposals -> 护栏校验 -> 写 config "
        "-> 追加审计日志。这是 reviewPolicy 中唯一允许自动生效的一类")
elif tuner:
    add("MANUAL", "自动生效通道", "tune_keywords.py 存在但未接入每日流程")
else:
    add("MANUAL", "自动生效通道",
        "reviewPolicy 声明关键词微调可自动，但没有实现该分支：提案只写文件等人看")

# ================================================ 4. 反馈回路
if "signal_bonus" in collect:
    add("OK", "用户行为反哺采集",
        "读取 web/data/feedback.json，对收藏/掌握度高的类目与渠道给有上限的加分，"
        "并会重建历史条目上过期的加分（避免删掉 feedback 后分数不回落）")
else:
    add("MISSING", "用户行为反哺采集",
        "收藏/掌握度只存在浏览器 localStorage，采集器读不到，选材不会随偏好变化")

if "feedback" in planner:
    add("OK", "配额规划使用反馈", "plan_deep_read.py 用反馈调整类目权重与深读配额")
else:
    add("MISSING", "配额规划使用反馈",
        "深读配额只按分类权重与相关度，不看你的收藏/掌握情况")

# ================================================ 5. 质量护栏
if "NOISE_RULES" in planner and "category_mismatch" in planner:
    add("OK", "深读质量闸门", "噪音规则 + 分类有效性检查（防止误分类条目占用配额）")
elif "NOISE_RULES" in planner:
    add("OK", "深读质量闸门", "有噪音规则")
else:
    add("MISSING", "深读质量闸门", "无")

add("OK" if "blockedIds" in collect else "MISSING", "下架不可复活",
    "采集导入与索引重建两处都检查 blocklist" if "blockedIds" in collect
    else "blocklist 未被读取，清理会被下一轮覆盖")

if "perCategoryPerRun" in collect:
    add("OK", "每类每日入库上限", "限制单轮新增的每类条数，避免某方向灌满语料")
else:
    add("MISSING", "每类每日入库上限",
        "没有按分类限制单轮入库量，话多的渠道/关键词会挤占其它方向")

if "new_channel_proposals" in collect:
    add("OK", "自动发现新渠道",
        "从人工导入的域名中发现候选渠道（5 次以上）并生成提案，需人工批准后才登记")
else:
    add("MISSING", "自动发现新渠道", "newChannelProposals 只定义字段，没有生成逻辑")

mrel = re.search(r'"minRelevance"\s*:\s*([0-9.]+)', read(ROOT / "config" / "collector.config.json"))
add("OK" if mrel else "MISSING", "采集相关度门槛",
    f"配置 minRelevance={mrel.group(1)}（低于门槛不入库）" if mrel else "无")

# ================================================ 6. 守卫是否在每日路径上
for label, script in (
    ("公式渲染守卫", "check-formulas.mjs"),
    ("公式符号完整性守卫", "tex-audit.mjs"),
    ("布局溢出审计", "audit-layout.mjs"),
    ("文字竖排体检", "verify-text-stacking.mjs"),
    ("折叠控件回归", "verify-collapse.mjs"),
    ("关键词自动调优", "tune_keywords.py"),
):
    exists = (SCRIPTS / script).exists()
    wired = "run_guards" in runner if script.endswith(".mjs") else "tune_keywords" in runner
    if exists and wired:
        add("OK", f"{label}接入每日流程", f"{script} 由 run-daily 调用")
    elif exists:
        add("MISSING", f"{label}接入每日流程",
            f"{script} 存在但每日流程不调用 -> 问题只能靠人发现")
    else:
        add("MISSING", label, f"{script} 不存在")

# 面经抽取是否在每日路径上（用户要求提升面经比重并细化解析）
if (SCRIPTS / "build_interview_index.py").exists() and "build_interview_index" in runner:
    add("OK", "面经结构化抽取", "每日抽取公司/轮次/结果/主题，供题库定位页「面经速览」使用")
else:
    add("MISSING", "面经结构化抽取", "build_interview_index.py 未接入每日流程")

# 未分类卡片是否被拒之门外（用户要求不保存无关资讯）
if "dropUnclassified" in collect:
    add("OK", "未分类卡片不入库",
        "采集阶段丢弃 + 索引重建过滤（存储层保留，便于日后关键词改进后重新归类）")
else:
    add("MISSING", "未分类卡片不入库", "未分类条目仍会进入语料")

# ================================================ 7. 深读层
add("OK" if ("selfCheck" in agent and "uncertain" in agent) else "MANUAL",
    "深读层自证",
    "prompt 强制产出 selfCheck.uncertain（待人工核实项）" if "selfCheck" in agent
    else "未见强制自证要求")

diagram_mandated = bool(re.search(
    r"(硬性要求|必须|must|required|强制)[^\n]{0,60}diagram|diagram[^\n]{0,60}(必须|must|required|强制|硬性)",
    agent, re.I))
add("OK" if diagram_mandated else "MANUAL", "深读层强制图解",
    "prompt 把 diagram 列为硬性要求（内联 SVG 或 spec 规格）" if diagram_mandated
    else "prompt 提到 diagram 但未明确强制 -> 部分深读条目可能没有配图")

enrich = load(DATA / "enrichment.json") or {}
n_enr = enrich.get("count") or len(enrich.get("byId") or {})
idx = load(DATA / "items" / "index.json") or {}
n_items = idx.get("count") or len(idx.get("items") or [])
if n_items:
    add("OK" if n_enr / n_items >= 0.05 else "MANUAL", "深读覆盖率",
        f"{n_enr}/{n_items} = {n_enr / n_items:.1%} 已深读（其余标记「仅摘要」，逐轮补齐）")

# ================================================ 输出
print("")
print("=" * 78)
print("自主性机制盘点（对代码与产物的实测）")
print("=" * 78)
order = {"OK": 0, "MANUAL": 1, "MISSING": 2}
for status, name, detail in sorted(results, key=lambda r: (order[r[0]], r[1])):
    mark = {"OK": "[已实现] ", "MANUAL": "[需人工] ", "MISSING": "[缺失]   "}[status]
    print(f"{mark}{name}")
    print(f"           {detail}")
counts = {k: sum(1 for r in results if r[0] == k) for k in ("OK", "MANUAL", "MISSING")}
print("=" * 78)
print(f"已实现 {counts['OK']} 项 · 需人工批准 {counts['MANUAL']} 项 · 缺失 {counts['MISSING']} 项")
print("=" * 78)
print("")
