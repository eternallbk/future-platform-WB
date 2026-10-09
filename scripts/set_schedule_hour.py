#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
set_schedule_hour.py — 把每日执行时间统一改为指定小时（上海时间）

背景
  执行时间散落在 14 个文件、100+ 处（采集器常量、分类元数据、manifest、
  前端文案、文档、PowerShell 入口、注册表调研产物）。任何一处漏改都会造成
  前后矛盾：界面写 13:00 而任务实际 20:00 跑，或 config 里 cron 是 0 13
  而 manifest.schedule 是 0 20。

  所以用脚本一次性改完，并**扫出所有残留**（正则覆盖任意小时）便于核对。

用法
  python scripts/set_schedule_hour.py --to 20            # 执行（默认从当前值推断）
  python scripts/set_schedule_hour.py --to 20 --check    # 只报告不一致处
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

TARGETS = [
    "scripts/collect.py",
    "scripts/run-daily.ps1",
    "scripts/daily-agent.md",
    "scripts/selfcheck.py",
    "scripts/build_learning_kb.py",
    "scripts/build_site.py",
    "scripts/merge_registry.py",
    "scripts/plan_deep_read.py",
    "scripts/audit_requirements.py",
    # The hand-off message the reader sees after a publish says "下一轮 20:00
    # 会自动重试", so it is schedule text too.
    "scripts/handoff_workbuddy.py",
    "web/assets/js/views2.part.js",
    "web/assets/js/views.part.js",
    "web/assets/js/core.part.js",
    "web/index.html",
    "web/data/taxonomy.json",
    "web/data/manifest.json",
    "web/data/sources.json",
    "config/collector.config.json",
    "README.md",
    "FUTURE.md",
    "docs/信息架构与数据契约.md",
    "docs/登录类渠道操作手册.md",
    # The migration set describes the same schedule as the code, so it goes stale
    # in exactly the same way. It was missing from this list, which is how
    # `20:00 的排期可能失败` survived the 20:00 -> 18:00 move.
    "docs/migration/00-迁移总览.md",
    "docs/migration/01-每日更新流程.md",
    "docs/migration/02-数据契约.md",
    "docs/migration/03-自检与自我迭代.md",
    "docs/migration/05-已知问题与注意事项.md",
    "research/source_registry.json",
]


# ---------------------------------------------------------------------------
# Prose pass — line scoped, not pattern scoped
# ---------------------------------------------------------------------------
# The ordered rules above cover every shape that existed when the schedule last
# moved, but prose keeps inventing new ones: `20:00 的排期可能失败` matched none
# of them and was left behind. So this pass inverts the logic — on any line that
# also mentions a scheduling concept, normalise every standalone clock time.
#
# The negative lookbehind `(?<![\d:+\-T])` is what keeps ISO timestamps out of
# scope: in `2026-10-01T19:25:52+08:00` the `19:25` is preceded by `T` and the
# `08:00` by `+`, so neither can match. That is the guard that makes it safe to
# run this over a single-line JSON file which contains both a schedule and a
# dozen real timestamps.
SCHEDULE_MARKERS = re.compile(
    r"cron|Daily-\d\d|hour=|每日|每天|上海时间|Asia/Shanghai|schedule|NextRun|"
    r"下次运行|计划任务|计划时间|排期|触发|更新频率|updateCadence|localTimeZh|"
    r"automation|automatic|下一轮|下轮",
    re.I,
)
CLOCK = re.compile(r"(?<![\d:+\-T])\d{1,2}:00(?![\d:])")

# A line that documents the LEGACY Windows task name on purpose. The real task
# cannot be renamed (and is `Disabled`), so the rollback note keeps the old name.
# Without this exemption the task-name rule flips such a line between `-20` and
# `-18` on every run, which made the script non-idempotent.
LEGACY_DOC = re.compile(r"历史遗留|历史排期|State=Disabled")


def rewrite(text: str, rules, new_h: int) -> tuple[str, int]:
    """Apply the ordered rules, then the prose pass — line by line.

    Line-scoped rather than whole-text so the LEGACY_DOC exemption can apply
    uniformly. This is behaviour-preserving: none of the patterns can span a
    newline, so a per-line `subn` replaces exactly what a whole-text `subn` did.
    """
    nh = f"{new_h:02d}"
    out, n = [], 0
    for line in text.split("\n"):
        if LEGACY_DOC.search(line):
            out.append(line)
            continue
        for pat, rep in rules:
            line, k = re.subn(pat, rep, line)
            n += k
        if f"{nh}:00" not in line and SCHEDULE_MARKERS.search(line):
            line, k = CLOCK.subn(f"{nh}:00", line)
            n += k
        out.append(line)
    return "\n".join(out), n

# Every place the hour appears, in the shapes the codebase actually uses.
def build_rules(new_h: int) -> list[tuple[str, str]]:
    nh = f"{new_h:02d}"
    rules = [        # task identity
        (r"Future-Workbench-Daily-\d{2}", f"Future-Workbench-Daily-{nh}"),
        # cron, all quoting styles
        (r'"cron"\s*:\s*"0 \d{2} \* \* \*"', f'"cron": "0 {nh} * * *"'),
        (r"'0 \d{2} \* \* \*'", f"'0 {nh} * * *'"),
        (r'"0 \d{2} \* \* \*"', f'"0 {nh} * * *"'),
        (r"0 \d{2} \* \* \*", f"0 {nh} * * *"),
        # code
        (r"hour=\d{1,2}", f"hour={new_h}"),
        # windows task trigger
        (r"-At '\d{2}:\d{2}'", f"-At '{nh}:00'"),
        # `nextRunAt` is a SCHEDULE field, so its hour must move with the schedule.
        # Scope it to that key explicitly: the earlier rule
        # `T\d{2}:00:00\+08:00` rewrote ANY such ISO string, which silently
        # changed an illustrative `publishedAt` example in
        # docs/信息架构与数据契约.md — a data timestamp, not a schedule.
        (r'("nextRunAt"\s*:\s*"[0-9\-]+T)\d{2}(:00)', rf"\g<1>{nh}\g<2>"),
        # natural language (zh + en)
        #
        # The bold forms are listed BEFORE the plain forms and consume BOTH
        # asterisk pairs. Why that matters: a rule like
        # `上海时间\s*\*{0,2}\d{1,2}:\d{2}` matches only `上海时间 **20:00` in
        # `上海时间 **20:00**`, so the trailing `**` survives while the rule
        # inserts a fresh `**` -- and running the script again appends another
        # pair every time. Observed before the fix: 4 runs turned
        # `上海时间 **20:00**` into `上海时间 **18:00********`. Same shape of bug
        # for `每日 **HH:00**`. Matching the closing asterisks makes every rule
        # idempotent: a second run rewrites `18:00` to `18:00`.
        # The bold forms are listed BEFORE the plain forms and consume BOTH
        # asterisk pairs. Why that matters: a rule like
        # `上海时间\s*\*{0,2}\d{1,2}:\d{2}` matches only `上海时间 **20:00` in
        # `上海时间 **20:00**`, so the trailing `**` survives while the rule
        # inserts a fresh `**` -- and running the script again appends another
        # pair every time. Observed before the fix: repeated runs turned
        # `上海时间 **20:00**` into `上海时间 **18:00********`. The plain rule
        # then absorbs any stray trailing asterisks, so it also REPAIRS a file
        # rewritten by the old buggy rule, and a second run is a no-op
        # (`18:00` -> `18:00`) which is what makes the script idempotent.
        (r"每日\s*\*\*\d{1,2}:\d{2}\*\*", f"每日 **{nh}:00**"),
        (r"每天\s*\*\*\d{1,2}:\d{2}\*\*", f"每天 **{nh}:00**"),
        (r"上海时间\s*\*\*\d{1,2}:\d{2}\*\*", f"上海时间 **{nh}:00**"),
        (r"每日\s*\d{1,2}:\d{2}\*{0,4}(?!\*)", f"每日 {nh}:00"),
        (r"每天\s*\d{1,2}:\d{2}\*{0,4}(?!\*)", f"每天 {nh}:00"),
        (r"上海时间\s*\d{1,2}:\d{2}\*{0,4}(?!\*)", f"上海时间 {nh}:00"),
        (r"每日\s*\d{1,2}\s*点", f"每日 {nh} 点"),
        (r"\d{1,2}:00\s*[（(]Asia/Shanghai[)）]", f"{nh}:00 (Asia/Shanghai)"),
        # Same clock, but in the shapes the repo actually uses in prose and markup
        # where the parenthesised form above does not apply. Each one is anchored
        # on a word that only ever accompanies a schedule, so a real timestamp
        # cannot be caught:
        #   "20:00 Asia/Shanghai"  (docstrings / comments, no parentheses)
        #   "20:00 schedule"       (comments explaining the trigger)
        #   "<b>20:00</b>"         (the hero copy the reader actually sees)
        (r"(?<![\d:T+\-])\d{1,2}:00(?=\s+Asia/Shanghai)", f"{nh}:00"),
        (r"(?<![\d:T+\-])\d{1,2}:00(?=\s+schedule)", f"{nh}:00"),
        # English prose in code comments / registry notes:
        #   "Distinguish an automatic 20:00 run from a human/dev invocation"
        #   "the 20:00 automation and a later retry invocation"
        #   "the 20:00 run only READS (no fetching)"
        (r"(?<![\d:T+\-])\d{1,2}:00(?=\s+run\b)", f"{nh}:00"),
        (r"(?<![\d:T+\-])\d{1,2}:00(?=\s+automation\b)", f"{nh}:00"),
        (r"<b>\d{1,2}:00</b>", f"<b>{nh}:00</b>"),
        # Schedule-flavoured prose that is not covered above: "在 13:00 触发",
        # "['13:00 触发', ...]", "13:00 自动执行". Constrained on BOTH sides so it
        # cannot reach a timestamp - an earlier, looser version of this rule
        # rewrote the timezone offset inside ISO strings (`+08:00` -> `+20:00`)
        # in 202 places. The negative lookbehind/lookahead for `+`, `-`, `T` and
        # digits is what keeps `2026-10-01T19:25:52+08:00` out of scope.
        # The optional 会/将 matters: Chinese writes "下一轮 20:00 会自动重试", so the
        # keyword does not follow the time directly. Without this the hand-off
        # message kept `20:00` after the move to 18:00.
        (r"(?<![\d:+\-T])\d{1,2}:00(?=\s*(?:会|将|即|就)?\s*(?:触发|执行|自动|更新|运行|,|，|\]|'|\"))",
         f"{nh}:00"),
        (r"SCHEDULE_HOUR\s*=\s*\d{1,2}", f"SCHEDULE_HOUR = {new_h}"),
    ]
    return rules


def sanity_guard(rel: str, before: str, after: str) -> str | None:
    """Refuse a rewrite that looks like it damaged a timestamp.

    Why this exists: an earlier, looser version of the clock-time rule rewrote
    the timezone offset inside ISO strings (`+08:00` -> `+20:00`) in 202 places,
    and also mangled a time RANGE (`00:00-06:00` -> `20:00-20:00`). Both were
    silent. This guard compares the counts of time-ish patterns before and after
    and rejects the whole file if they changed shape.
    """
    # The check that actually matters is "did THIS rewrite change any timezone
    # offset", because that is exactly what the incident looked like
    # (`+08:00` -> `+20:00`). Comparing the multiset of offsets before/after
    # states that precisely.
    #
    # The previous version instead asked "does the file contain any offset that
    # is not +08:00". That is wrong: `+00:00` is a legitimate UTC offset (see
    # collect.py's ISO parser, `s[:-1] + "+00:00"`), and a source comment may
    # legitimately quote a bad offset to document the past incident. As a
    # result the guard refused to retime scripts/collect.py at all — a
    # false positive that blocked the 20:00 -> 18:00 change.
    OFFSET = re.compile(r"[+\-]\d{2}:\d{2}")

    def offsets(t: str) -> Counter:
        return Counter(OFFSET.findall(t))

    def counts(t: str) -> dict:
        return {
            "iso": len(re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", t)),
            "ranges": len(re.findall(r"\d{2}:\d{2}\s*[-–~]\s*\d{2}:\d{2}", t)),
        }

    b, a = counts(before), counts(after)
    ob, oa = offsets(before), offsets(after)
    problems = []
    if ob != oa:
        diff = ", ".join(
            f"{k}: {ob.get(k, 0)} -> {oa.get(k, 0)}"
            for k in sorted(set(ob) | set(oa)) if ob.get(k) != oa.get(k))
        problems.append(f"时区偏移被改动（{diff}）")
    if b["iso"] != a["iso"]:
        problems.append(f"ISO 时间戳数量变化 {b['iso']} -> {a['iso']}")
    if b["ranges"] != a["ranges"]:
        problems.append(f"时间范围数量变化 {b['ranges']} -> {a['ranges']}")
    return "; ".join(problems) if problems else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="set_schedule_hour.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--to", type=int, required=True, help="target hour, 0-23 (Shanghai time)")
    ap.add_argument("--check", action="store_true", help="report only")
    args = ap.parse_args(argv)

    if not 0 <= args.to <= 23:
        print("hour must be 0-23", file=sys.stderr)
        return 2

    rules = build_rules(args.to)
    nh = f"{args.to:02d}"

    if args.check:
        # Only schedule-relevant lines are reported. A naive scan flags every
        # `HH:MM` in the repo - data timestamps like "checkedAt": "...T17:10:00",
        # log lines, and the correctly-spelled task name itself - which buried the
        # one genuine leftover under >100 false positives. A line only counts as a
        # schedule statement if it also mentions one of these markers.
        markers = re.compile(r"cron|Daily-\d\d|hour=|每日|每天|上海时间|Asia/Shanghai|"
                             r"schedule|NextRun|下次运行|计划任务|计划时间|排期|触发|"
                             r"更新频率|updateCadence|localTimeZh|automation|automatic|"
                             r"下一轮|下轮|taskName", re.I)
        bad = 0
        for rel in TARGETS:
            p = ROOT / rel
            if not p.exists():
                continue
            text = p.read_text("utf-8")
            hits = []
            for i, l in enumerate(text.split("\n"), 1):
                if not markers.search(l):
                    continue
                # A line that explicitly documents the LEGACY Windows task is not
                # an inconsistency: the real task cannot be renamed (and is
                # `Disabled`), so its historical name stays in the rollback note
                # on purpose.
                if re.search(r"历史遗留|历史排期|State=Disabled", l):
                    continue
                # Ignore timezone offsets: "+08:00" is not a clock time, and
                # flagging it was the last false positive in this scan.
                probe = re.sub(r"[+\-]\d{2}:\d{2}", "", l)
                if re.search(r"\d{1,2}:00", probe) and f"{nh}:00" not in l:
                    hits.append((i, l.strip()[:100]))
                elif re.search(r"0 \d{2} \* \* \*", l) and f"0 {nh} " not in l:
                    hits.append((i, l.strip()[:100]))
                elif re.search(r"Daily-\d{2}", l) and f"Daily-{nh}" not in l:
                    hits.append((i, l.strip()[:100]))
                elif re.search(r"hour=\d{1,2}", l) and f"hour={args.to}" not in l:
                    hits.append((i, l.strip()[:100]))
            if hits:
                bad += len(hits)
                print(f"  {rel}:")
                for i, l in hits[:6]:
                    print(f"    {i}: {l}")
        print(f"\n不一致行数: {bad}  (目标小时 {nh})" if bad
              else f"\n[ok] 排期相关位置全部一致，目标小时 {nh}:00")
        return 0

    changed = []
    refused = []
    grand = 0
    for rel in TARGETS:
        p = ROOT / rel
        if not p.exists():
            continue
        try:
            text = p.read_text("utf-8")
        except Exception:
            continue
        new, n = rewrite(text, rules, args.to)
        if n and new != text:
            guard = sanity_guard(rel, text, new)
            if guard:
                print(f"  [REFUSED] {rel}: {guard}")
                refused.append((rel, guard))
                continue
            with io.open(p, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(new)
            changed.append((rel, n))
            grand += n

    print("")
    print("=" * 68)
    print(f"目标：每日 {nh}:00 (Asia/Shanghai)")
    print(f"已修改 {len(changed)} 个文件，共 {grand} 处")
    for rel, n in changed:
        print(f"  {n:>4}  {rel}")
    if refused:
        print(f"\n[!] 因安全检查被拒绝 {len(refused)} 个文件（未写入）：")
        for rel, why in refused:
            print(f"  {rel}: {why}")
    print("=" * 68)

    # Rescan for anything still not matching the target hour.
    leftover = []
    for rel in TARGETS:
        p = ROOT / rel
        if not p.exists():
            continue
        try:
            text = p.read_text("utf-8")
        except Exception:
            continue
        for i, l in enumerate(text.split("\n"), 1):
            if LEGACY_DOC.search(l):
                continue          # documented legacy task name, left as-is on purpose
            if re.search(r"hour=\d{1,2}|0 \d{2} \* \* \*|Daily-\d{2}", l) and f"{nh}" not in l:
                leftover.append((rel, i, l.strip()[:110]))
            elif re.search(r"(每日|每天|上海时间)\s*\*{0,2}\d{1,2}:\d{2}", l) and f"{nh}:00" not in l:
                leftover.append((rel, i, l.strip()[:110]))
    if leftover:
        print(f"\n[!] 仍有 {len(leftover)} 处需人工确认：")
        for rel, i, l in leftover[:20]:
            print(f"  {rel}:{i}: {l}")
    else:
        print(f"\n[ok] 所有排期位置已统一为 {nh}:00")
    print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
