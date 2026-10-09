#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_repair_literals.py — 把 _gen_bank_problems.py 里被当成源码插进去的裸中文串补上引号。

背景：_fix_teaching.py 在重建 teaching() 调用时，把 FILL 里的**字符串值**当成源码
片段写了进去，于是出现 `ownAnalysis=这是……,` 这种非法语法。
本脚本做最小修复：只处理 `ownAnalysis=` / `interviewAnswer=` 这两行（内容单行、
以句号断句），把它们渲染成相邻字符串字面量。其它内容一律不动。
"""
from __future__ import annotations

import io
import re
from pathlib import Path

P = Path(__file__).resolve().parent / "_gen_bank_problems.py"
FIELD_RE = re.compile(r"^(\s*)(ownAnalysis|interviewAnswer)=(.+),$")
BS = chr(92)
DQ = chr(34)


def quote(text: str) -> str:
    escaped = text.replace(BS, BS + BS).replace(DQ, BS + DQ)
    return DQ + escaped + DQ


def render(value: str, indent: int) -> str:
    """按句号断句，渲染成若干相邻字符串字面量（换行 + 对齐缩进）。"""
    parts = [p for p in re.split(r"(?<=。)", value) if p]
    if not parts:
        return DQ + DQ
    pad = " " * indent
    return ("\n" + pad).join(quote(p) for p in parts)


def main() -> int:
    src = io.open(P, encoding="utf-8").read()
    out, fixed = [], 0
    for ln in src.split("\n"):
        m = FIELD_RE.match(ln)
        if m and not m.group(3).lstrip().startswith((DQ, "'")):
            indent = len(m.group(1)) + len(m.group(2)) + 1
            out.append(f"{m.group(1)}{m.group(2)}={render(m.group(3), indent)},")
            fixed += 1
        else:
            out.append(ln)
    io.open(P, "w", encoding="utf-8", newline="\n").write("\n".join(out))
    print(f"repaired {fixed} bare literal(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
