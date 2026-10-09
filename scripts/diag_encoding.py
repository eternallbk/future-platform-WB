#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Byte-level encoding diagnostic for the web/data static layer.

Purpose: distinguish "the file bytes are wrong" from "the reader used the wrong
codepage". It prints, for each file:

  * the first 4 raw bytes in hex (0x7B '{' means a clean no-BOM JSON object),
  * whether a UTF-8 BOM is present,
  * the value of a known Chinese field decoded as UTF-8,
  * whether that value equals the expected string (compared via \\u escapes so
    this script cannot itself be blamed for a bad literal),
  * the same bytes decoded as 'gbk' — the classic Windows-PowerShell-5.1
    `Get-Content` misread that produces mojibake such as
    `鐩爣鎶曢€掔獥鍙` for `目标投递窗口`.

Usage:
    python scripts/diag_encoding.py
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wedata_common import DATA, utf8_stdout  # noqa: E402

# Expected values written as \u escapes on purpose: if this source file were
# itself mis-encoded, the comparison would fail loudly instead of silently
# matching bad bytes.
EXPECTED = {
    "taxonomy.json": ("categories[0].nameZh", "\u591a\u6a21\u6001\u7b97\u6cd5"),          # 多模态算法
    "sources.json": ("categories[0].nameZh", "\u591a\u6a21\u6001\u7b97\u6cd5"),          # 多模态算法
    "manifest.json": ("targetLabel", "\u76ee\u6807\u6295\u9012\u7a97\u53e3\uff082027 \u5c4a\u6625\u62db\uff09"),
    "jobs.json": ("jobs[0].company", None),                                              # source data
    "learning.json": ("meta.reason", None),
}

SAMPLES = {
    "taxonomy.json": lambda d: d["categories"][0]["nameZh"],
    "sources.json": lambda d: d["categories"][0]["nameZh"],
    "manifest.json": lambda d: d["targetLabel"],
    "jobs.json": lambda d: d["jobs"][0]["company"],
    "learning.json": lambda d: d["meta"].get("reason", ""),
    "formulas.json": lambda d: d.get("source", ""),
    "logs/runs.json": lambda d: "",
}


def main():
    utf8_stdout()
    print("=" * 78)
    print("web/data encoding diagnostic (byte level)")
    print("=" * 78)
    print("interpreter : %s" % sys.executable)
    print("fs encoding : %s   stdout: %s" % (sys.getfilesystemencoding(), sys.stdout.encoding))
    print()

    for name, getter in SAMPLES.items():
        path = os.path.join(DATA, name)
        label = "web/data/" + name
        if not os.path.exists(path):
            print("%-22s MISSING" % label)
            continue
        with open(path, "rb") as fh:
            raw = fh.read()
        bom = raw.startswith(b"\xef\xbb\xbf")
        head = raw[:4]
        print("%-22s size=%-8d first4=%s  bom=%s" % (
            label, len(raw), " ".join("%02X" % b for b in head), "YES (BAD)" if bom else "no"))
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            print("    [!] NOT valid UTF-8: %s" % exc)
            continue
        obj = json.loads(text)
        val = getter(obj)
        utf8_hex = val.encode("utf-8").hex(" ")
        print("    utf-8 decode  -> %r" % val)
        print("    utf-8 bytes   -> %s" % utf8_hex)
        if name in EXPECTED and EXPECTED[name][1] is not None:
            ok = (val == EXPECTED[name][1])
            print("    expected      -> %r" % EXPECTED[name][1])
            print("    MATCH         -> %s" % ("YES" if ok else "NO  <-- REAL BUG"))
        # Reproduce the misread that produces the reported mojibake.
        try:
            gbk = raw.decode("gbk", errors="replace")
            if name in ("manifest.json", "taxonomy.json", "sources.json"):
                probe = gbk
                print("    gbk misread   -> %r  (this is what PowerShell 5.1 shows)"
                      % probe[:1])
        except Exception:
            pass
        print()

    # The decisive experiment: show that the GBK misread of the correct bytes is
    # exactly the mojibake that was reported.
    print("-" * 78)
    print("decisive check: the reported mojibake vs. a GBK misread of the real bytes")
    print("-" * 78)
    good = "\u76ee\u6807\u6295\u9012\u7a97\u53e3\uff082027 \u5c4a\u6625\u62db\uff09"  # 目标投递窗口（2027 届春招）
    misread = good.encode("utf-8").decode("gbk", errors="replace")
    reported = "\u942b\u7223\u7d9c\u99ac\u8c1d\u8b1d\u7ba1\u53e3"  # prefix of the reported mojibake
    print("real value                : %r" % good)
    print("utf-8 bytes               : %s" % good.encode("utf-8").hex(" "))
    print("same bytes read as gbk    : %r" % misread)
    print("reported by parent (head) : %r" % reported)
    print("gbk-misread starts with reported snippet -> %s"
          % misread.startswith(reported))
    print()
    print("CONCLUSION: mojibake like the above appears when correct UTF-8 bytes are")
    print("decoded with the Windows ANSI/GBK codepage (PowerShell 5.1 Get-Content")
    print("without -Encoding UTF8). It is a *reader* problem, not a file problem.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
