#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""merge_agent_parts.py - assemble out-<batchId>.json from per-item part files.

WHY THIS EXISTS
---------------
A deep-read subagent used to write its whole batch as ONE large JSON file
(out-queue-01.json). With 5 fully enriched items that file reaches ~30-50 KB,
and the agent's per-response output budget ran out mid-write: the file ended
inside a string and json.load() failed with "Unterminated string".

Observed evidence (2026-10-05 evening run): out-queue-01.json truncated at
19,514 chars, out-queue-02.json truncated at 31,922 chars - both cut off in
the middle of a value. Batch size was not the only factor; the single giant
write was.

FIX: the agent writes ONE entry per file into
    scripts/agent-work/parts/<batchId>/NN.json        (a single entry object)
    scripts/agent-work/parts/<batchId>/skipped.json   ({"skipped":[...]})
Each write is ~4-6 KB, comfortably inside a single response. This script then
assembles the canonical out-<batchId>.json that apply_agent_out.py expects.

Part files deliberately live in parts/ and are NOT named out-*.json, otherwise
apply_agent_out.py's `glob("out-*.json")` would treat each fragment as a batch.

Usage
  python scripts/merge_agent_parts.py            # merge every batch that has parts
  python scripts/merge_agent_parts.py --check    # report only
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "scripts" / "agent-work"
PARTS = WORK / "parts"


def load(p: Path):
    return json.loads(p.read_text("utf-8"))


def dump(p: Path, doc) -> None:
    with io.open(p, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report only, do not write")
    args = ap.parse_args()

    if not PARTS.exists():
        print("no parts/ directory - nothing to merge")
        return 0

    total_entries = total_skipped = 0
    merged = []
    for d in sorted(PARTS.iterdir()):
        if not d.is_dir():
            continue
        bid = d.name
        inp = WORK / f"in-{bid}.json"
        if not inp.exists():
            print(f"[skip] {bid}: no in-{bid}.json (stale parts dir?)")
            continue

        want = [it["id"] for it in load(inp).get("items") or []]
        entries, skipped, bad = [], [], []

        for f in sorted(d.glob("*.json")):
            if f.name == "skipped.json":
                doc = load(f)
                skipped.extend(doc.get("skipped") or (doc if isinstance(doc, list) else []))
                continue
            doc = load(f)
            # A part file is either a bare entry object or {"entries":[...]}.
            rows = doc.get("entries") if isinstance(doc, dict) and "entries" in doc else [doc]
            for r in rows:
                if not isinstance(r, dict) or not r.get("id"):
                    bad.append(f"{f.name}: not an entry object")
                    continue
                entries.append(r)

        got = [e["id"] for e in entries]
        dupes = {i for i in got if got.count(i) > 1}
        missing = [i for i in want if i not in got]
        extra = [i for i in got if i not in want]

        status = "ok"
        if dupes or missing or extra or bad:
            status = "ATTENTION"
        print(f"[{status}] {bid}: entries={len(entries)} skipped={len(skipped)} "
              f"missing={len(missing)} extra={len(extra)} dupes={len(dupes)} bad={len(bad)}")
        if bad:
            for b in bad:
                print("        bad:", b)
        if missing:
            print("        missing ids:", ", ".join(missing[:8]))
        if extra:
            print("        extra ids:", ", ".join(extra[:8]))
        if dupes:
            print("        duplicate ids:", ", ".join(sorted(dupes)))

        total_entries += len(entries)
        total_skipped += len(skipped)
        merged.append((bid, entries, skipped))

    if args.check:
        print(f"\nCHECK ONLY: {len(merged)} batch(es), {total_entries} entries, {total_skipped} skipped")
        return 0

    for bid, entries, skipped in merged:
        dump(WORK / f"out-{bid}.json",
             {"batchId": bid, "entries": entries, "skipped": skipped})
        print(f"wrote out-{bid}.json  entries={len(entries)} skipped={len(skipped)}")

    print(f"\n{len(merged)} batch(es) assembled, {total_entries} entries, {total_skipped} skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
