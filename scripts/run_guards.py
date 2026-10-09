#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_guards.py — 在每日流程里跑「产物守卫」，把只在手动跑时才发现的问题前移

背景
  scripts/check-formulas.mjs 与 scripts/audit-layout.mjs 都是真实有效的守卫，
  但此前**只有在人手动执行时才跑**。结果是：
    · 深读层夜里写入一条畸形 LaTeX -> 公式剖析页整页空白，直到有人打开才发现
    · 卡片文案变长导致溢出 -> 内容被 overflow 裁掉，肉眼很难确认
  这个脚本把两者串起来，由 run-daily.ps1 在「构建站点之前」调用，并汇总成一个
  退出码，写进运行日志。

  公式守卫是**门禁**（失败会导致页面空白，必须知道）；
  布局审计是**体检**（失败说明有内容被裁，不阻断发布，但记录在案）。

用法:
  python scripts/run_guards.py              # 跑全部守卫
  python scripts/run_guards.py --skip-layout  # 只跑公式门禁（快）
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

NODE = "node"


def run(label: str, args: list[str], timeout: int = 900) -> tuple[bool, str]:
    """Run a guard and return (ok, tail-of-output)."""
    try:
        p = subprocess.run(
            args, cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
    except FileNotFoundError:
        return False, f"{args[0]} not found on PATH"
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"
    out = ((p.stdout or "") + (p.stderr or "")).strip()
    tail = "\n".join(out.splitlines()[-6:])
    return p.returncode == 0, tail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-layout", action="store_true",
                    help="skip the (slower) browser-based layout audit")
    args = ap.parse_args()

    results: list[tuple[str, bool, str]] = []

    # --- Gate: a formula that throws blanks the entire 公式剖析 page ---
    formula_guard = SCRIPTS / "check-formulas.mjs"
    if formula_guard.exists():
        ok, tail = run("formulas", [NODE, str(formula_guard)])
        results.append(("公式渲染门禁", ok, tail))
    else:
        results.append(("公式渲染门禁", False, "check-formulas.mjs missing"))

    # --- Gate: a formula that RENDERS but leaks raw LaTeX ---
    # check-formulas.mjs only proves nothing throws. tex() deliberately degrades an
    # unknown command into a visible marker, so a formula can pass that gate while
    # showing the reader a literal "\!" or "\odot". Measured once: 38 of 155 formulas
    # leaked a command, which looked like broken math in the drawer. Counting them
    # here turns a missing symbol into a number instead of something to spot by eye.
    tex_audit = SCRIPTS / "tex-audit.mjs"
    if tex_audit.exists():
        ok, tail = run("tex-audit", [NODE, str(tex_audit)])
        results.append(("公式符号完整性（不泄漏 LaTeX）", ok, tail))
    else:
        results.append(("公式符号完整性（不泄漏 LaTeX）", False, "tex-audit.mjs missing"))

    # --- Health check: content wider than its box gets silently clipped ---
    layout_audit = SCRIPTS / "audit-layout.mjs"
    if not args.skip_layout:
        if layout_audit.exists():
            ok, tail = run("layout", [NODE, str(layout_audit),
                                      "--width", "1200,1440", "--routes", "dashboard,jobs,knowledge"],
                           timeout=1500)
            results.append(("布局溢出体检", ok, tail))
        else:
            results.append(("布局溢出体检", False, "audit-layout.mjs missing"))

    # --- Health check: interaction regressions that no static check can see ---
    #
    # Both of these were REAL bugs found this way, and both are invisible to every
    # other check: they neither overflow nor error, the markup is valid, and the DOM
    # state is correct. Only driving the browser reveals them.
    #   text-stacking : a `place-items: center` grid split a Chinese label one
    #                   character per line ("公" above "开"), which read as a broken
    #                   table column;
    #   collapse      : the author rule `.formula-body { display: grid }` beat the
    #                   user-agent `[hidden] { display: none }`, so every collapse
    #                   control set the attribute, updated aria, and changed nothing
    #                   on screen - the button looked completely dead.
    if not args.skip_layout:                      # same browser cost class as layout
        for label, script, extra in (
            ("文字竖排（一字一行）体检", "verify-text-stacking.mjs",
             ["--routes", "dashboard,knowledge,formulas,pipeline,skills,exam"]),
            ("折叠控件行为回归", "verify-collapse.mjs", ["--route", "formulas"]),
        ):
            p = SCRIPTS / script
            if p.exists():
                ok, tail = run("ui", [NODE, str(p)] + extra, timeout=1500)
                results.append((label, ok, tail))
            else:
                results.append((label, False, f"{script} missing"))

    print("")
    print("=" * 74)
    print("产物守卫")
    print("=" * 74)
    gate_failed = False
    for name, ok, tail in results:
        print(f"  [{'通过' if ok else '未通过'}] {name}")
        for line in (tail or "").splitlines()[-4:]:
            print(f"          {line}")
        if not ok and name in ("公式渲染门禁", "公式符号完整性（不泄漏 LaTeX）"):
            gate_failed = True
    print("=" * 74)
    if gate_failed:
        print("公式门禁未通过：畸形或无法解析的 LaTeX 会让公式页显示原始命令、甚至整页空白，需立即修。")
    else:
        print("门禁通过。布局体检失败只代表「有内容被裁」，不阻断发布，但会记入日志。")
    print("")

    # Only the formula gate is fatal; a layout finding must not block a data refresh.
    return 1 if gate_failed else 0


if __name__ == "__main__":
    sys.exit(main())
