#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
handoff_workbuddy.py — 打印 WorkBuddy 发布的交接口径与排障说明（中文）

为什么单独一个 Python 文件：Windows PowerShell 5.1 用系统 ANSI 代码页解码
无 BOM 的 .ps1，所以 .ps1 里不能出现中文（会被解成非法语法）。所有中文输出
统一由这个脚本负责，它用 UTF-8 正常打印。

这个文件替代了原来的 handoff_ghpages.py / handoff_publish.py（GitHub Pages 版）。
两者都已删除：工作台不再提交、不再推送、没有 gh-pages 分支，也没有
*.github.io 地址。公开发布由 WorkBuddy 托管。

用法: python scripts/handoff_workbuddy.py [--ready|--trouble]
"""
from __future__ import annotations

import argparse
import sys

READY = """
发布交接（WorkBuddy 托管，国内直连）

  · 发布对象是 dist/ —— build_site.py 用白名单生成的「可公开产物」。
    state/、inbox/、harness 日志、*.part.js 都不会进入 dist/。

  · 发布是**平台动作**，不是一个 git 命令：由 WorkBuddy 把 dist/ 目录上传，
    并保持「一个目录 = 一条稳定分享链接」。所以脚本只负责审计与交接，
    真正的上传由每日自动化紧接着执行。

  · 链接是稳定的：同一个目录重复发布会**覆盖**上一条链接的内容，
    不会产生新地址。因此不需要把 URL 写进任何文件。

  · 发布失败不影响本地数据：web/data/ 已更新，线上停在上一次成功发布的版本，
    下一轮 18:00 会自动重试。

  手动发布一次（排障用）：
      powershell -ExecutionPolicy Bypass -File scripts\\publish-workbuddy.ps1 -Rebuild
    然后让 WorkBuddy 发布 dist/ 目录即可。
"""

TROUBLE = """
发布失败的常见原因与处理：

  A) 隐私审计不通过（脚本会直接打印 AUDIT FAILED）
     dist/ 里出现了 collector-state.json / inbox/ / harness 日志 / sk- 形状的
     凭据字符串。这通常是 build_site.py 的白名单被改动导致的。
     修法：不要往 dist/ 手工放文件；数据文件要在 build_site.py 的
     DATA_FILES / DATA_DIRS 里显式登记后才会发布。
     审计不通过时**不会上传任何内容**，线上旧站点保持不变。

  B) dist/index.html 缺失
     说明 build_site.py 没跑成功。先跑：
       python scripts\\build_site.py
     看它打印的隐私检查是否为「通过」。

  C) 公式门禁失败导致发布被跳过
     每日流程里 run_guards.py 若判定公式畸形，会主动**拒绝发布**并保留线上
     旧站点（宁可旧，不可坏）。修 web/data/formulas.json 里那条 LaTeX 后重跑。

  D) 上传本身失败（网络 / 平台侧）
     本地数据不受影响。恢复后重跑发布即可，不需要重跑整个采集流程。

  安全说明：上传前会独立再做一次隐私审计（与 build_site.py 的审计相互独立，
  两次检查都很便宜，而泄露不可挽回）。
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ready", action="store_true")
    ap.add_argument("--trouble", action="store_true")
    args = ap.parse_args()
    print(TROUBLE if args.trouble else READY)
    return 0


if __name__ == "__main__":
    sys.exit(main())
