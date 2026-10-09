#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Verify every generated file in the web/data static layer.

Checks, in order:
  1. the file exists and is non-empty;
  2. the raw bytes carry NO UTF-8 BOM;
  3. the raw bytes decode as UTF-8;
  4. `json.load(open(p, encoding='utf-8'))` succeeds;
  5. the top-level keys the front-end reads are present.

Exits non-zero if any file fails a hard check.

Usage:
    python scripts/verify_web_data.py
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wedata_common import DATA, RESEARCH, arr, utf8_stdout  # noqa: E402

TARGETS = [
    ("web/data/jobs.json", "jobs.json"),
    ("web/data/learning.json", "learning.json"),
    ("web/data/sources.json", "sources.json"),
    ("web/data/taxonomy.json", "taxonomy.json"),
    ("web/data/manifest.json", "manifest.json"),
    ("web/data/logs/runs.json", "logs/runs.json"),
    ("web/data/formulas.json", "formulas.json"),
]

REQUIRED_KEYS = {
    "jobs.json": ["jobs", "skillMatrix", "handWrittenCoding", "writtenExam",
                  "interviewProcess", "salaryBands", "confidenceSummary", "meta"],
    "learning.json": ["meta", "tracks", "papers", "repos", "courses", "milestones", "studySystem"],
    "sources.json": ["generatedAt", "collectorVersion", "categories", "channels",
                     "manualChannels", "scoring", "dedupe", "reliability", "logging",
                     "legitimacy", "evolution"],
    "taxonomy.json": ["generatedAt", "source", "categories"],
    "manifest.json": ["generatedAt", "lastRunAt", "date", "collectorVersion", "channelsOk",
                      "channelsTotal", "newItems", "totalItems", "durationSec", "targetDate",
                      "targetLabel", "status", "itemsFile", "stats"],
    "logs/runs.json": [],
    "formulas.json": ["generatedAt", "source", "formulas"],
}

CANONICAL_DIRECTIONS = ["multimodal", "post-training", "world-model",
                        "generative", "rl", "agent", "infra", "embodied"]
REQUIRED_CATEGORY_IDS = ["multimodal", "posttraining", "worldmodel", "generative", "rl",
                         "agent", "foundation", "engineering", "coding", "exam", "job",
                         "paper", "course", "trend"]
REQUIRED_CHANNEL_IDS = ["arxiv", "hf_papers", "hf_models", "github", "gh_trending", "openreview",
                        "s2", "pwc", "acl", "hn", "reddit", "nowcoder", "zhihu", "xiaohongshu",
                        "boss", "shixiseng", "lagou", "leetcode", "codeforces", "jobs_bytedance",
                        "jobs_tencent", "jobs_alibaba", "jobs_zhipu", "jobs_moonshot",
                        "jobs_deepseek", "jobs_minimax", "jobs_shailab", "machineheart",
                        "qbitai", "rsshub", "manual"]
LOGIN_WALLED = ["xiaohongshu", "boss", "shixiseng", "lagou"]

PROBLEM_KEYS = ["id", "title", "difficulty", "frequency", "topics", "prompt", "keyPoints",
                "pitfalls", "referenceSolution", "answerOutline", "sources"]
JOB_KEYS = ["id", "company", "shortName", "tier", "title", "directions", "cities", "pay",
            "duration", "conversion", "open", "applyUrl", "seasonality", "highlights",
            "process", "notes", "confidence", "sources", "relevance", "postedAt", "deadline"]

failures = []
warnings = []


def fail(msg):
    failures.append(msg)
    print("  [x] %s" % msg)


def warn(msg):
    warnings.append(msg)
    print("  [!] %s" % msg)


def count_of(val):
    if isinstance(val, list):
        return "%d items" % len(val)
    if isinstance(val, dict):
        return "%d keys" % len(val)
    if val is None:
        return "null"
    if isinstance(val, str):
        return "str(%d)" % len(val)
    return repr(val)


def main():
    utf8_stdout()
    print("=" * 78)
    print("web/data static layer verification")
    print("=" * 78)

    loaded = {}

    # ---------------- pass 1: existence / BOM / UTF-8 / json.load ----------
    print("\n--- [1] file integrity: bytes, no BOM, utf-8, json.load ---")
    for rel, name in TARGETS:
        path = os.path.join(os.path.dirname(DATA), rel.replace("web/data/", ""))
        path = os.path.join(DATA, name)
        if not os.path.exists(path):
            fail("%s does not exist" % rel)
            continue
        size = os.path.getsize(path)
        with open(path, "rb") as fh:
            raw = fh.read()
        bom = raw.startswith(b"\xef\xbb\xbf")
        if bom:
            fail("%s starts with a UTF-8 BOM" % rel)
        if size == 0 and name != "logs/runs.json":
            fail("%s is empty" % rel)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            fail("%s is not valid UTF-8: %s" % (rel, exc))
            continue
        try:
            obj = json.loads(text)
        except Exception as exc:
            fail("%s does not parse: %s" % (rel, exc))
            continue
        # The literal contract from the brief.
        try:
            with open(path, encoding="utf-8") as fh:
                json.load(fh)
        except Exception as exc:
            fail("%s fails json.load(open(p, encoding='utf-8')): %s" % (rel, exc))
            continue
        loaded[name] = (path, size, obj)
        print("  [ok] %-22s %8d bytes  utf-8, no BOM, parses" % (rel, size))

    # ---------------- pass 2: top-level keys ------------------------------
    print("\n--- [2] top-level keys and item counts ---")
    for rel, name in TARGETS:
        if name not in loaded:
            continue
        path, size, obj = loaded[name]
        print("  %s  (%d bytes)" % (path, size))
        if isinstance(obj, list):
            print("      <root> : %s" % count_of(obj))
        elif isinstance(obj, dict):
            for key, val in obj.items():
                print("      %-20s : %s" % (key, count_of(val)))
        else:
            print("      <root> : %s" % count_of(obj))
        for key in REQUIRED_KEYS[name]:
            if isinstance(obj, dict) and key not in obj:
                fail("%s is missing required top-level key %r" % (name, key))

    # ---------------- pass 3: jobs.json semantics -------------------------
    print("\n--- [3] jobs.json semantics ---")
    jobs_doc = loaded.get("jobs.json", (None, None, None))[2]
    if isinstance(jobs_doc, dict):
        jobs = jobs_doc.get("jobs") or []
        print("  companies -> jobs: %d jobs" % len(jobs))
        tier_counts = Counter(j.get("tier") for j in jobs)
        print("  tiers: %s" % dict(sorted(tier_counts.items())))
        dir_cov = Counter()
        bad_tokens = Counter()
        missing_job_keys = Counter()
        bad_relevance = []
        for j in jobs:
            for d in j.get("directions") or []:
                if d in CANONICAL_DIRECTIONS:
                    dir_cov[d] += 1
                else:
                    bad_tokens[d] += 1
            for k in JOB_KEYS:
                if k not in j:
                    missing_job_keys[k] += 1
            # recompute relevance exactly as specified
            idx = {"S": 5, "A": 4, "B": 3, "C": 2}.get(j.get("tier"), 2)
            expect = min(100, 55 + 12 * (5 - idx) + 4 * len(j.get("directions") or []))
            if j.get("relevance") != expect:
                bad_relevance.append((j.get("id"), j.get("relevance"), expect))
        print("  canonical direction coverage: %s"
              % dict(sorted(dir_cov.items(), key=lambda kv: (-kv[1], kv[0]))))
        for tok in CANONICAL_DIRECTIONS:
            if tok not in dir_cov:
                print("      (no company carries %r in jobs.json)" % tok)
        if bad_tokens:
            fail("non-canonical direction tokens present: %s" % dict(bad_tokens))
        if missing_job_keys:
            fail("job objects missing keys: %s" % dict(missing_job_keys))
        if bad_relevance:
            fail("relevance mismatch: %s" % bad_relevance[:5])
        else:
            print("  relevance formula verified for all %d jobs" % len(jobs))
        order = {"S": 0, "A": 1, "B": 2, "C": 3}
        keys = [(order.get(j.get("tier"), 9), -j.get("relevance", 0)) for j in jobs]
        if keys != sorted(keys):
            fail("jobs are not sorted by tier then relevance")
        else:
            print("  sorted by tier then relevance: ok")
        src_shapes = [s for j in jobs for s in (j.get("sources") or [])]
        bad_src = [s for s in src_shapes if not (isinstance(s, dict) and "title" in s and "url" in s)]
        print("  job source links: %d total, %d malformed" % (len(src_shapes), len(bad_src)))
        if bad_src:
            fail("malformed job sources entries: %s" % bad_src[:3])
        if any(j.get("postedAt") is None for j in jobs):
            fail("some jobs have no postedAt")
        dl = {j.get("id"): j.get("deadline") for j in jobs}
        print("  deadlines: %s" % ("all null" if all(v is None for v in dl.values())
                                   else "non-null for %s" % [k for k, v in dl.items() if v]))

        print("  skillMatrix      : %d articles" % len(jobs_doc.get("skillMatrix") or []))
        hand = jobs_doc.get("handWrittenCoding") or []
        exam = jobs_doc.get("writtenExam") or []
        print("  handWrittenCoding: %d articles" % len(hand))
        print("  writtenExam      : %d articles" % len(exam))
        print("  interviewProcess : %d articles" % len(jobs_doc.get("interviewProcess") or []))
        print("  salaryBands      : %d articles" % len(jobs_doc.get("salaryBands") or []))
        for label, group in (("handWrittenCoding", hand), ("writtenExam", exam)):
            miss = Counter()
            for p in group:
                for k in PROBLEM_KEYS:
                    if k not in p:
                        miss[k] += 1
            nulls = Counter()
            for p in group:
                for k in PROBLEM_KEYS:
                    if p.get(k) is None:
                        nulls[k] += 1
            if miss:
                fail("%s missing keys: %s" % (label, dict(miss)))
            else:
                print("  %s: all %d required keys present in every entry" % (label, len(group)))
            if nulls:
                print("      explicit nulls (front-end default applies): %s" % dict(nulls))
            for p in group:
                for k in ("topics", "keyPoints", "pitfalls", "answerOutline", "sources"):
                    if not isinstance(p.get(k), list):
                        fail("%s.%s must be a list for id=%r" % (label, k, p.get("id")))
                        break

        skills = jobs_doc.get("skillMatrix") or []
        skill_keys = ["id", "skill", "category", "importance", "demandCompanies", "evidence",
                      "howToProve", "learnCost", "sources"]
        s_miss = [k for k in skill_keys if any(k not in s for s in skills)]
        if s_miss:
            fail("skillMatrix missing keys: %s" % s_miss)
        else:
            print("  skillMatrix: all %d required keys present in every entry" % len(skill_keys))

    # ---------------- pass 4: learning.json ------------------------------
    print("\n--- [4] learning.json content ---")
    learn = loaded.get("learning.json", (None, None, None))[2]
    if isinstance(learn, dict):
        meta = learn.get("meta") or {}
        is_placeholder = bool(meta.get("placeholder")) or meta.get("source") == "placeholder"
        counts = OrderedDict(
            [
                ("tracks", len(learn.get("tracks") or [])),
                ("papers", len(learn.get("papers") or [])),
                ("repos", len(learn.get("repos") or [])),
                ("courses", len(learn.get("courses") or [])),
                ("milestones", len(learn.get("milestones") or [])),
            ]
        )
        print("  kind      : %s" % ("PLACEHOLDER (research/learning_kb.json missing)" if is_placeholder
                                    else "REAL CONTENT from research/learning_kb.json"))
        print("  counts    : %s" % dict(counts))
        print("  studySystem: %s" % ("present" if learn.get("studySystem") else "null"))
        print("  meta keys : %s" % list(meta.keys()))
        if is_placeholder and any(counts.values()):
            fail("placeholder learning.json should be empty")

    # ---------------- pass 5: sources.json -------------------------------
    print("\n--- [5] sources.json registry ---")
    src = loaded.get("sources.json", (None, None, None))[2]
    if isinstance(src, dict):
        cats = src.get("categories") or []
        chans = src.get("channels") or []
        manual = src.get("manualChannels") or []
        cat_ids = [c.get("id") for c in cats]
        chan_ids = [c.get("id") for c in chans]
        print("  categories: %d -> %s" % (len(cats), cat_ids))
        print("  channels  : %d" % len(chans))
        print("  manualChannels: %s" % [m.get("id") for m in manual])
        missing_cats = [c for c in REQUIRED_CATEGORY_IDS if c not in cat_ids]
        missing_chans = [c for c in REQUIRED_CHANNEL_IDS if c not in chan_ids]
        if missing_cats:
            fail("missing required category ids: %s" % missing_cats)
        if missing_chans:
            fail("missing required channel ids: %s" % missing_chans)
        if len(cats) < 14:
            fail("fewer than 14 categories")
        bad_cat_keys = Counter()
        cat_fields = ["id", "nameZh", "nameEn", "description", "collectionGoal", "updateCadence",
                      "relevanceWeight", "keywordsZh", "keywordsEn", "arxivCategories"]
        for c in cats:
            for k in cat_fields:
                if k not in c:
                    bad_cat_keys[k] += 1
        if bad_cat_keys:
            fail("category objects missing keys: %s" % dict(bad_cat_keys))
        else:
            print("  all %d category objects carry the 10 required fields" % len(cats))
        chan_fields = ["id", "nameZh", "tier", "mode", "authRequired", "status", "rateLimit",
                       "lastChecked", "riskNote"]
        bad_chan = Counter()
        modes = Counter()
        for c in chans:
            for k in chan_fields:
                if k not in c:
                    bad_chan[k] += 1
            modes[c.get("mode")] += 1
        if bad_chan:
            fail("channel objects missing keys: %s" % dict(bad_chan))
        else:
            print("  all %d channel objects carry the 9 required fields" % len(chans))
        print("  modes: %s" % dict(modes))
        bad_modes = [k for k in modes if k not in ("api", "rss", "html", "manual")]
        if bad_modes:
            fail("invalid channel modes: %s" % bad_modes)
        for cid in LOGIN_WALLED:
            ch = next((c for c in chans if c.get("id") == cid), None)
            if ch and ch.get("authRequired") is not True:
                fail("%s must have authRequired: true" % cid)
        statuses = Counter(c.get("status") for c in chans)
        print("  statuses: %s" % dict(statuses))
        # A channel may only claim "ok" if it carries a recorded observation.
        unbacked = []
        for c in chans:
            if c.get("status") != "ok":
                continue
            provenance = str(c.get("statusSource") or "")
            if "live collect.py run" in provenance or "source_registry.json probe" in provenance:
                continue
            unbacked.append(c.get("id"))
        if unbacked:
            fail("channels claim status 'ok' with no recorded observation: %s" % unbacked)
        else:
            print("  every 'ok' status is backed by a recorded observation "
                  "(live run or registry probe) in statusSource")
        verified_ok = [c.get("id") for c in chans if c.get("status") == "ok"]
        if verified_ok:
            print("  channels reporting ok: %s" % verified_ok)
        for key in ("scoring", "dedupe", "reliability", "logging", "legitimacy", "evolution"):
            v = src.get(key)
            print("  %-12s: %s" % (key, ("%d keys" % len(v)) if isinstance(v, dict) else count_of(v)))
            if not isinstance(v, dict) or not v:
                fail("%s must be a non-empty object" % key)

    # ---------------- pass 6: taxonomy.json -----------------------------
    print("\n--- [6] taxonomy.json ---")
    tax = loaded.get("taxonomy.json", (None, None, None))[2]
    if isinstance(tax, dict):
        cats = tax.get("categories") or []
        print("  source=%r categories=%d" % (tax.get("source"), len(cats)))
        ids = [c.get("id") for c in cats]
        missing = [c for c in REQUIRED_CATEGORY_IDS if c not in ids]
        if missing:
            fail("taxonomy.json missing category ids: %s" % missing)
        else:
            print("  all 14 required ids present")
        # CategoriesView reads t.desc / t.goal / t.cadence / t.nameEn off these raw objects.
        alias_missing = [c.get("id") for c in cats
                         if not all(k in c for k in ("desc", "goal", "cadence", "nameEn"))]
        if alias_missing:
            warn("taxonomy categories missing front-end aliases desc/goal/cadence/nameEn: %s"
                 % alias_missing)
        else:
            print("  front-end aliases desc/goal/cadence/nameEn present on every category")
        if isinstance(src, dict) and src.get("categories") != cats:
            warn("taxonomy.json categories differ from sources.json categories")
        else:
            print("  taxonomy.json categories are identical to sources.json categories")

    # ---------------- pass 7: seed / collector-owned files ---------------
    # manifest.json, logs/runs.json and formulas.json are written by
    # scripts/collect.py once a real run happens; before that they are seeds.
    # Either state is valid - only an *inconsistent* pair is a problem.
    print("\n--- [7] manifest / runs / formulas (collector-owned after the first run) ---")
    man = loaded.get("manifest.json", (None, None, None))[2]
    runs = loaded.get("logs/runs.json", (None, None, None))[2]
    run_count = len(runs) if isinstance(runs, list) else None
    if isinstance(man, dict):
        status = man.get("status")
        phase = "seed (no run yet)" if status == "seed" else "real run recorded"
        print("  manifest: status=%r collectorVersion=%r channelsOk=%s/%s totalItems=%s newItems=%s"
              % (status, man.get("collectorVersion"), man.get("channelsOk"),
                 man.get("channelsTotal"), man.get("totalItems"), man.get("newItems")))
        print("  phase   : %s" % phase)
        print("  target  : %s  %s" % (man.get("targetDate"), man.get("targetLabel")))
        if status == "seed" and run_count:
            fail("manifest says status='seed' but logs/runs.json holds %d run(s)" % run_count)
        if status != "seed" and man.get("lastRunAt") is None:
            fail("manifest claims a real run but lastRunAt is null")
        if status != "seed" and not run_count:
            warn("manifest shows a real run but logs/runs.json is empty")
        if status == "seed" and man.get("targetDate") is None:
            fail("seed manifest must carry targetDate")
    if run_count is not None:
        print("  logs/runs.json: %d run(s)" % run_count)
        if runs:
            r0 = runs[0] if isinstance(runs[0], dict) else {}
            print("      latest: startedAt=%s status=%s newItems=%s channels=%s/%s durationSec=%s"
                  % (r0.get("startedAt") or r0.get("at"), r0.get("status"), r0.get("newItems"),
                     r0.get("channelsOk"), r0.get("channelsTotal"), r0.get("durationSec")))
    forms = loaded.get("formulas.json", (None, None, None))[2]
    if isinstance(forms, dict):
        print("  formulas.json: source=%r formulas=%d (empty -> front-end FORMULA_SEED fallback)"
              % (forms.get("source"), len(forms.get("formulas") or [])))
        if forms.get("formulas"):
            print("      formulas are populated, so the front-end will NOT use its built-in seed")

    # ---------------- pass 8: research artifact availability -------------
    print("\n--- [8] research artifacts ---")
    for name in ("jobs_kb.json", "learning_kb.json", "source_registry.json"):
        p = os.path.join(RESEARCH, name)
        print("  %-22s %s" % (name, ("%d bytes" % os.path.getsize(p)) if os.path.exists(p)
                              else "MISSING"))

    # ---------------- summary -------------------------------------------
    print("\n" + "=" * 78)
    if failures:
        print("RESULT: FAIL (%d hard failures, %d warnings)" % (len(failures), len(warnings)))
        for f in failures:
            print("  - %s" % f)
        print("=" * 78)
        return 1
    print("RESULT: PASS - all 7 files exist, are BOM-free UTF-8, and parse with "
          "json.load(open(p, encoding='utf-8'))")
    print("        %d warning(s)" % len(warnings))
    for w in warnings:
        print("  - %s" % w)
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
