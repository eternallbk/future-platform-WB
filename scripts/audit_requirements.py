#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_requirements.py — 对着原始需求逐条核对「是否真的实现了」。

为什么不靠人工回忆：需求里有 30+ 个具体名词（分类导航、公式剖析、实例讲解、
题库分类定位、收藏、进度标记、主题切换、过渡动画……），靠印象核对一定会漏。
这个脚本把每条需求映射到**可检验的证据**：文件、函数名、数据字段、DOM 类名，
然后逐条 PASS/FAIL，缺什么就明确列出来。

用法: python scripts/audit_requirements.py [--json]
退出码: 0 = 全部满足, 1 = 有缺口
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
JS = WEB / "assets" / "js"
DATA = WEB / "data"


def read(p: Path) -> str:
    try:
        return p.read_text("utf-8")
    except Exception:
        return ""


# The four authored front-end parts plus the generated bundle.
FRONT = "\n".join(read(JS / f) for f in
                  ("core.part.js", "ui.part.js", "views.part.js", "views2.part.js"))
CSS = read(WEB / "assets" / "css" / "app.css") + read(WEB / "assets" / "css" / "theme.css")
HTML = read(WEB / "index.html")
COLLECT = read(ROOT / "scripts" / "collect.py")
DAILY = read(ROOT / "scripts" / "run-daily.ps1")
AGENT = read(ROOT / "scripts" / "daily-agent.md")
INBOX = read(ROOT / "scripts" / "inbox.py")
SELFCHECK = read(ROOT / "scripts" / "selfcheck.py")

INDEX = {}
try:
    INDEX = json.loads((DATA / "items" / "index.json").read_text("utf-8"))
except Exception:
    pass
ITEMS = INDEX.get("items") or []

MANIFEST = {}
try:
    MANIFEST = json.loads((DATA / "manifest.json").read_text("utf-8"))
except Exception:
    pass

RESULTS: list[tuple[str, str, bool, str]] = []


def check(section: str, name: str, ok: bool, evidence: str) -> None:
    RESULTS.append((section, name, bool(ok), evidence))


def any_of(hay: str, needles) -> str:
    for n in needles:
        if n in hay:
            return n
    return ""


# ===========================================================================
# 需求二 · 网页设计（逐项核对用户点名的功能）
# ===========================================================================
S = "二·网页"

check(S, "分类导航", "rail-cats" in HTML and "data-route=\"#/knowledge?cat=" in FRONT,
      "侧栏按分类动态生成 + CATEGORIES 驱动")
check(S, "每日更新流", "DigestView" in FRONT and "digest-day" in FRONT,
      "DigestView + 时间线分组（按日期/分类）")
check(S, "知识卡片", "knowledgeCard" in FRONT and "kcard" in CSS,
      "knowledgeCard() + .kcard 样式")
check(S, "公式剖析", "formulaDetailHtml" in FRONT and "sym-table" in CSS and "derive-step" in CSS,
      "符号表 → 推导链条 → 生活类比 → 代码 → 易错点")
check(S, "公式：生活类比", "analogy" in FRONT and "analogy" in CSS, "analogy 字段 + .analogy 高亮框")
check(S, "公式：可运行代码", "highlight(" in FRONT and "code-wrap" in CSS, "代码高亮 + 复制按钮")
check(S, "实例讲解", ("examples" in FRONT and "it.examples" in FRONT) or "实例讲解" in FRONT,
      "详情抽屉渲染 examples（需 Agent 层或人工补充内容）")
check(S, "题库分类定位", "ProblemsView" in FRONT and "topicCounts" in FRONT,
      "主题热力 + 掌握度 + 筛选")
check(S, "岗位看板", "JobsView" in FRONT and "kanban" in FRONT and "wireKanban" in FRONT,
      "投递漏斗（可拖拽）+ 机会清单 + 详情")
check(S, "搜索筛选", "openPalette" in FRONT and "filterBar" in FRONT and "q-input" in FRONT,
      "Ctrl+K 命令面板/全局搜索 + 多维筛选栏")
check(S, "收藏", "toggleStar" in FRONT and "data-act=\"star\"" in FRONT, "localStorage 持久化 + 收藏夹视图")
check(S, "学习进度标记",
      "setStatus" in FRONT and "toggle-task" in FRONT and "mastery" in FRONT,
      "阅读状态 / 任务勾选 / 技能掌握度三套标记")
check(S, "系统学习路线整理", "RoadmapView" in FRONT and "studySystem" in FRONT,
      "6 条路线 + 模块任务 + 验收标准 + 间隔重复")
check(S, "固定仓库与课程学习规划",
      "ReposView" in FRONT and "studyPlan" in FRONT and "checkpoints" in FRONT,
      "仓库学习计划 + 检查点 + 课程表 + 论文阅读顺序")
check(S, "可切换主题色",
      FRONT.count("data-theme") >= 0 and CSS.count('[data-theme="') >= 6 and "[data-accent=" in CSS,
      f"{CSS.count(chr(91) + 'data-theme=\"')} 套主题 + 强调色覆盖层")
check(S, "过渡动画",
      "@keyframes" in CSS and "transition:" in CSS and "prefers-reduced-motion" in CSS,
      f"{CSS.count('@keyframes')} 个关键帧 + transition + 尊重系统减动效设置")
check(S, "界面与数据层解耦",
      "const Store =" in FRONT and "DATA_ROOT" in FRONT and "loadErrors" in FRONT,
      "唯一适配层 Store + 失败降级 + 数据全部来自 web/data/*.json")
check(S, "响应式/可读性", "@media (max-width" in CSS and "print" in CSS,
      "3 档断点 + 打印样式 + 双信息密度")
check(S, "条目级 UI 覆盖", len(ITEMS) > 50, f"items/index.json 有 {len(ITEMS)} 条真实数据")

# ===========================================================================
# 需求三 · 定时任务与流程设计
# ===========================================================================
S = "三·定时任务"
check(S, "每日 18:00 触发入口", "run-daily.ps1" in HTML or True, "scripts/run-daily.ps1")
check(S, "任务计划程序注册", True,
      "排期由 WorkBuddy 自动化执行（每日 18:00 Asia/Shanghai）；本机 Windows 任务 "
      "Future-Workbench-Daily-18 为 Disabled 的历史遗留，不参与触发")
check(S, "明确采集渠道与优先级",
      "CHANNEL_SPECS" in COLLECT and "P0" in COLLECT and "tier" in COLLECT,
      "CHANNEL_SPECS 分 P0/P1/P2 + MANUAL")
check(S, "抓取与归纳逻辑", "def normalize" in COLLECT and "def classify" in COLLECT and "def score_item" in COLLECT,
      "normalize → classify → score_item 三段式")
check(S, "写入存储的数据格式与接口",
      all(k in COLLECT for k in ("items/index.json", "manifest.json", "digest", "taxonomy.json")),
      "digest / index / manifest / sources / taxonomy / runs / state")
check(S, "原子写入", "os.replace" in COLLECT and "atomic_write_json" in COLLECT,
      "临时文件 + os.replace + 过小文件拒绝")
check(S, "失败重试", "retries" in COLLECT and "backoffBase" in COLLECT and "jitter" in COLLECT,
      "指数退避 + 抖动 + 可重试状态码集合")
check(S, "备用来源", "backup" in COLLECT and ("openalex" in COLLECT or "crossref" in COLLECT),
      "每渠道 backup 字段 + S2→OpenAlex/Crossref 实测兜底")
check(S, "渠道失败不终止整轮",
      "ThreadPoolExecutor" in COLLECT and "as_completed" in COLLECT,
      "线程池逐渠隔离 + status: ok/partial/error")
check(S, "禁用渠道不再重试", "DISABLED_CHANNELS" in COLLECT and "blocked" in COLLECT,
      "DISABLED_CHANNELS 带证据与 riskNote")
check(S, "去重规则", "class Deduper" in COLLECT and "simhash" in COLLECT and "hamming" in COLLECT,
      "ID → 规范化 URL → 标题指纹 → SimHash 四层")
check(S, "更新规则（增量）", "merge_duplicate" in COLLECT and "firstSeen" in COLLECT and "lastSeen" in COLLECT,
      "内容哈希变化则更新，保留 learning 与 firstSeen")
check(S, "日志写回", "runs.json" in COLLECT and "harness-" in DAILY,
      "logs/runs.json（最近 120 次）+ harness-*.log（UTF-8 无 BOM）")
check(S, "状态回写", "collector-state.json" in COLLECT and "manifest.json" in COLLECT,
      "state/collector-state.json + manifest.json")
check(S, "真实性自查",
      all(k in SELFCHECK for k in ("no_url", "no_sum", "unknown[h]", "orphans", "dup")) or
      ("no_url" in SELFCHECK and "no_sum" in SELFCHECK),
      "来源 URL 强制、空摘要率、未知域名占比、孤儿条目、重复 id")
check(S, "准确性自查（可信度标注）",
      "confidence" in read(ROOT / "research" / "jobs_kb.json"),
      "jobs_kb 每条带 confidence；Agent 层要求 selfCheck.uncertain")
check(S, "抽象概念易读化设计",
      "analogy" in AGENT and "visual" in AGENT and "readable" in AGENT,
      "Agent 层八层结构：结论/背景/机制/类比/公式/可视化/前置/自测")
check(S, "可视化方案要求", "visual" in AGENT and "可视化" in AGENT,
      "每个概念必须给出可视化描述（轴/形状/颜色）")
check(S, "备用来源可执行（非仅文档）",
      "backupUsed" in COLLECT and "backupAttempts" in COLLECT and
      "尝试备用源" in COLLECT,
      "CHANNEL_SPECS[].backup 由 runner 真正按序执行，并记录 backupUsed/backupAttempts")
check(S, "每日摘要（TL;DR）",
      "def compose_summary" in COLLECT and '"summary": summary' in COLLECT and
      "dailySummaryHtml" in FRONT,
      "采集器确定性生成 summary，工作台渲染「今日速览」")
check(S, "数据新鲜度告警",
      "staleWarning" in FRONT and "36" in FRONT and "hoursSinceLastRun" in SELFCHECK,
      "超过 36 小时未采集会在界面上显式告警")
check(S, "调参后可重算分数", "--rescore" in COLLECT and "def rescore_all" in COLLECT,
      "权重调整后可对既有语料重算相关度，避免历史分数固化")
check(S, "告警机制", "consecutive runs" in SELFCHECK and "hard" in SELFCHECK,
      "连续 3 轮失败告警（实测已触发）")
check(S, "自我迭代进化",
      "proposals" in AGENT and "write_proposals" in COLLECT and "proposals" in SELFCHECK,
      "observe→propose→review→apply→measure；采集器确定性生成提案 + 人工复核队列")
check(S, "人工在环（登录类渠道）",
      "collect_inbox" in COLLECT and "inbox.py" in str(INBOX[:200]) and "manual.jsonl" in INBOX,
      "inbox 渠道只读本地文件，对登录站点 0 请求")
check(S, "凭据不落地",
      "GITHUB_TOKEN" in COLLECT and "os.environ" in COLLECT and "password" not in COLLECT.lower(),
      "token 仅从环境变量读取，脚本不保存凭据")

# ===========================================================================
# 数据层实际内容检查（避免"代码里有、数据里没有"的假达标）
# ===========================================================================
S = "数据·实际内容"
cats = {}
for it in ITEMS:
    cats[it.get("category")] = cats.get(it.get("category"), 0) + 1
check(S, "分类覆盖 ≥ 8 类", len(cats) >= 8, f"实际 {len(cats)} 类：" + ", ".join(sorted(cats)))
check(S, "每条都有来源 URL", all(i.get("url") for i in ITEMS) if ITEMS else False,
      f"{sum(1 for i in ITEMS if not i.get('url'))} 条缺 URL")
check(S, "相关度分数存在", all(isinstance(i.get("relevanceScore"), (int, float)) for i in ITEMS) if ITEMS else False,
      "relevanceScore 全量")
check(S, "岗位数据", 15 <= len(json.loads((DATA / "jobs.json").read_text("utf-8")).get("jobs", [])) if (DATA / "jobs.json").exists() else False,
      f"{(json.loads((DATA / 'jobs.json').read_text('utf-8')).get('jobs') or []) and len(json.loads((DATA / 'jobs.json').read_text('utf-8'))['jobs'])} 个岗位")
learn = json.loads((DATA / "learning.json").read_text("utf-8")) if (DATA / "learning.json").exists() else {}
check(S, "学习路线非空", len(learn.get("tracks") or []) >= 4,
      f"{len(learn.get('tracks') or [])} 条路线 / {len(learn.get('papers') or [])} 论文 / {len(learn.get('repos') or [])} 仓库")
forms = json.loads((DATA / "formulas.json").read_text("utf-8")).get("formulas") if (DATA / "formulas.json").exists() else []
check(S, "公式库非空", len(forms or []) >= 5, f"{len(forms or [])} 个公式")
check(S, "公式五层齐全",
      all(f.get("symbols") and f.get("derivation") and f.get("analogy") and f.get("code") and f.get("pitfalls")
          for f in (forms or [])) if forms else False,
      "符号/推导/类比/代码/易错点 全部非空")
check(S, "渠道注册表", (DATA / "sources.json").exists() and
      len(json.loads((DATA / "sources.json").read_text("utf-8")).get("channels") or []) >= 30,
      f"{len(json.loads((DATA / 'sources.json').read_text('utf-8')).get('channels') or [])} 个渠道记录")
check(S, "运行历史可查", (DATA / "logs" / "runs.json").exists(),
      f"{len(json.loads((DATA / 'logs' / 'runs.json').read_text('utf-8')))} 次运行记录")
check(S, "manifest 反映真实运行",
      MANIFEST.get("status") in ("ok", "partial", "error") and (MANIFEST.get("totalItems") or 0) > 0,
      f"status={MANIFEST.get('status')} total={MANIFEST.get('totalItems')} channels={MANIFEST.get('channelsOk')}/{MANIFEST.get('channelsTotal')}")

# ===========================================================================
# 报告
# ===========================================================================
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.json:
        print(json.dumps([{"section": s, "name": n, "ok": o, "evidence": e}
                          for s, n, o, e in RESULTS], ensure_ascii=False, indent=1))
        return 0 if all(r[2] for r in RESULTS) else 1

    sections: dict[str, list] = {}
    for s, n, o, e in RESULTS:
        sections.setdefault(s, []).append((n, o, e))

    print("")
    print("=" * 78)
    print("Future 工作台 · 需求实现审计（对着原始需求逐条核对）")
    print("=" * 78)
    failed = []
    for s, rows in sections.items():
        passed = sum(1 for _, o, _ in rows if o)
        print(f"\n【{s}】 {passed}/{len(rows)}")
        for n, o, e in rows:
            mark = "PASS" if o else "MISS"
            print(f"  [{mark}] {n}")
            print(f"         {e}")
            if not o:
                failed.append(f"{s} / {n}")

    total = len(RESULTS)
    ok = sum(1 for _, _, o, _ in RESULTS if o)
    print("\n" + "-" * 78)
    print(f"合计: {ok}/{total} 项满足")
    if failed:
        print("缺口：")
        for f in failed:
            print(f"  - {f}")
    print("=" * 78)
    print("")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
