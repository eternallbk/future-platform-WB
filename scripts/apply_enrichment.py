#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge the daily-agent deep-read payload into the ``web/data`` layer.

This is the write-back half of the optional layer-2 agent described in
``scripts/daily-agent.md``.  It never invents content: it only merges a payload
file that a human or an agent authored, and it never shrinks existing data.

What it touches (and nothing else):

* ``web/data/enrichment.json``            -- byId merge (new value wins per id)
* ``web/data/formulas.json``              -- append new formulas, de-dupe by id
* ``web/data/jobs.json``                  -- append new jobs, de-dupe by id/applyUrl
* ``web/data/proposals/<date>.json``      -- merge agent proposals over the
                                             deterministic collector proposals
* ``web/data/proposals/latest.json``      -- mirror of the above (the front-end
                                             only reads ``latest.json``)
* ``web/data/logs/agent-<date>.json``     -- run record

Usage
-----
    python scripts/apply_enrichment.py                          # today, auto input
    python scripts/apply_enrichment.py --date 2026-10-01
    python scripts/apply_enrichment.py --input scripts/agent-input-2026-10-01.json
    python scripts/apply_enrichment.py --dry-run
    python scripts/apply_enrichment.py --data-dir web/data

Payload shape
-------------
    {
      "date": "YYYY-MM-DD",
      "enrichment": [ {"id": "...", ..., "formulas": [ {...} ]} ],
      "jobs":       [ {...} ],
      "proposals":  { "channelHealth": [...], ... },
      "log":        { "status": "ok", "notes": "...", "errors": [] }
    }

All files are written as UTF-8 **without BOM** (never use PowerShell
``Set-Content`` / ``>`` for these files: they add a BOM and can corrupt CJK).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA_DIR = os.path.join(ROOT, "web", "data")

# Fields the front-end's normalizeFormula() reads; used for a soft warning only.
FORMULA_LAYERS = ("symbols", "derivation", "analogy", "code", "pitfalls")

# Invariants owned by scripts/build_jobs_json.py -- jobs.json must keep them.
TIER_INDEX = {"S": 5, "A": 4, "B": 3, "C": 2}
TIER_ORDER = ["S", "A", "B", "C"]
RELEVANCE_FORMULA = "min(100, 55 + 12*(5-tierIndex) + 4*len(directions))"
CANONICAL_DIRECTIONS = {"multimodal", "post-training", "world-model", "generative",
                        "rl", "agent", "infra", "embodied"}


def job_relevance(tier, n_directions):
    idx = TIER_INDEX.get(tier, TIER_INDEX["C"])
    return min(100, 55 + 12 * (5 - idx) + 4 * n_directions)


def job_sort_key(job):
    tier = job.get("tier")
    rank = TIER_ORDER.index(tier) if tier in TIER_ORDER else len(TIER_ORDER)
    return (rank, -int(job.get("relevance") or 0), str(job.get("id")))


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def now_iso() -> str:
    return _dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, obj, style="pretty2"):
    """Write UTF-8 / no BOM / LF.

    ``style`` matches each existing file's own producer, so a merge does not
    reformat a whole file:

    * ``compact``  -- ``separators=(",", ":")``, one line (collect.py output:
                       proposals, digest, sources, items/index.json)
    * ``pretty1``  -- ``indent=1`` (seed_formulas.py: formulas.json)
    * ``pretty2``  -- ``indent=2`` + trailing newline (wedata_common.write_json:
                       jobs.json and the files this script creates)
    """
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        if style == "compact":
            json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))
        elif style == "pretty1":
            json.dump(obj, fh, ensure_ascii=False, indent=1)
        else:
            json.dump(obj, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    os.replace(tmp, path)
    return os.path.getsize(path)


def canon(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def dedupe_dicts(existing, incoming, key):
    """Union two list-of-dicts, incoming wins on a duplicate key, order stable."""
    out, seen = [], {}
    for item in list(existing or []) + list(incoming or []):
        if not isinstance(item, dict):
            continue
        k = canon(item.get(key)) if key else canon(item)
        if k in seen:
            out[seen[k]] = item  # incoming overwrites, position preserved
        else:
            seen[k] = len(out)
            out.append(item)
    return out


def slug(text) -> str:
    keep = []
    for ch in str(text):
        if ch.isalnum():
            keep.append(ch.lower())
        elif keep and keep[-1] != "-":
            keep.append("-")
    return "".join(keep).strip("-")


# --------------------------------------------------------------------------- #
# merge steps
# --------------------------------------------------------------------------- #
def merge_enrichment(data_dir, payload, stamp):
    path = os.path.join(data_dir, "enrichment.json")
    old = read_json(path, {}) or {}
    by_id = dict(old.get("byId") or {})
    added, replaced = [], []
    for entry in payload.get("enrichment") or []:
        item_id = entry.get("id")
        if not item_id:
            raise SystemExit("enrichment entry without an id: %s" % canon(entry)[:200])
        if item_id in by_id:
            replaced.append(item_id)
        else:
            added.append(item_id)
        by_id[item_id] = entry
    doc = {
        "generatedAt": stamp,
        "source": "daily-agent",
        "count": len(by_id),
        "byId": by_id,
    }
    return path, doc, {"added": added, "replaced": replaced, "total": len(by_id)}


def collect_formulas(payload):
    """Formulas live inside each enrichment entry (daily-agent.md section 5.2)."""
    out = []
    for entry in payload.get("enrichment") or []:
        for formula in entry.get("formulas") or []:
            out.append(formula)
    for formula in payload.get("formulas") or []:
        out.append(formula)
    return out


def merge_formulas(data_dir, payload, stamp, logger):
    path = os.path.join(data_dir, "formulas.json")
    old = read_json(path, {}) or {}
    existing = list(old.get("formulas") or [])
    positions = {f.get("id"): i for i, f in enumerate(existing) if isinstance(f, dict)}
    appended, updated, skipped = [], [], []
    for formula in collect_formulas(payload):
        fid = formula.get("id")
        if not fid:
            logger("  ! formula without id, skipped: %s" % canon(formula)[:120])
            continue
        missing = [k for k in FORMULA_LAYERS if not formula.get(k)]
        if missing:
            logger("  ! formula %s is missing layers %s (front-end shows what exists)" % (fid, missing))
        pos = positions.get(fid)
        if pos is None:
            positions[fid] = len(existing)
            existing.append(formula)
            appended.append(fid)
        elif existing[pos] != formula:
            # The payload is authoritative for the formulas it declares (so a
            # correction propagates); formulas it does not mention are kept.
            existing[pos] = formula
            updated.append(fid)
        else:
            skipped.append(fid)
    doc = {
        "generatedAt": stamp,
        "source": "seed+daily",
        "count": len(existing),
        "formulas": existing,
    }
    return path, doc, {"appended": appended, "updated": updated,
                       "skipped": skipped, "total": len(existing)}


def merge_jobs(data_dir, payload, stamp, logger):
    path = os.path.join(data_dir, "jobs.json")
    old = read_json(path, {}) or {}
    jobs = list(old.get("jobs") or [])
    have_ids = {j.get("id") for j in jobs if isinstance(j, dict)}
    have_urls = {(j.get("applyUrl") or "").strip() for j in jobs if isinstance(j, dict)}
    added, skipped = [], []
    for job in payload.get("jobs") or []:
        jid = job.get("id")
        url = (job.get("applyUrl") or "").strip()
        if not jid:
            raise SystemExit("job without an id: %s" % canon(job)[:200])
        if jid in have_ids or (url and url in have_urls):
            skipped.append(jid)
            continue
        bad = [d for d in (job.get("directions") or []) if d not in CANONICAL_DIRECTIONS]
        if bad:
            raise SystemExit("job %s uses non-canonical directions: %s" % (jid, bad))
        # keep build_jobs_json.py's relevance invariant regardless of payload input
        want = job_relevance(job.get("tier"), len(job.get("directions") or []))
        if job.get("relevance") != want:
            logger("  ! job %s relevance %s -> %s (%s)"
                   % (jid, job.get("relevance"), want, RELEVANCE_FORMULA))
            job["relevance"] = want
        jobs.append(job)
        have_ids.add(jid)
        have_urls.add(url)
        added.append(jid)

    # keep the invariant across the whole file (also repairs earlier merges)
    for job in jobs:
        want = job_relevance(job.get("tier"), len(job.get("directions") or []))
        if job.get("relevance") != want:
            logger("  ! job %s relevance %s -> %s (%s)"
                   % (job.get("id"), job.get("relevance"), want, RELEVANCE_FORMULA))
            job["relevance"] = want

    jobs.sort(key=job_sort_key)   # same key as build_jobs_json.py:276
    doc = dict(old)
    doc["jobs"] = jobs
    date = payload.get("date")
    increments = list(doc.get("agentIncrements") or [])
    prev = next((x for x in increments if x.get("date") == date), None)
    # "this payload's contribution for this date" -- stable across re-runs.
    date_ids = list((prev or {}).get("addedIds") or [])
    for jid in added:
        if jid not in date_ids:
            date_ids.append(jid)
    if added:
        increments = [x for x in increments if x.get("date") != date]
        increments.append({
            "date": date,
            "by": "daily-agent",
            "addedIds": date_ids,
            "at": stamp,
            "note": "本文件由 scripts/build_jobs_json.py 从 research/jobs_kb.json 整体重建，重建会丢掉这里追加的岗位。",
        })
        doc["agentIncrements"] = increments
    else:
        doc.setdefault("agentIncrements", increments)
    return path, doc, {"added": added, "skipped": skipped, "total": len(jobs),
                       "dateIds": date_ids}


def merge_proposals(data_dir, payload, date, stamp):
    agent = payload.get("proposals") or {}
    path_day = os.path.join(data_dir, "proposals", "%s.json" % date)
    old = read_json(path_day, {}) or {}
    merged = dict(old)
    merged["date"] = date
    merged["generatedBy"] = (
        "collect.py deterministic layer + daily-agent" if old else "daily-agent"
    )
    if old.get("generatedAt"):
        merged["generatedAt"] = old["generatedAt"]
    merged["agentGeneratedAt"] = stamp

    merged["channelHealth"] = dedupe_dicts(old.get("channelHealth"), agent.get("channelHealth"), "id")
    # taxonomy/keyword proposals have no stable id -> dedupe on full content.
    merged["taxonomyProposals"] = dedupe_dicts(old.get("taxonomyProposals"), agent.get("taxonomyProposals"), None)
    merged["keywordProposals"] = dedupe_dicts(old.get("keywordProposals"), agent.get("keywordProposals"), None)
    merged["newChannelProposals"] = dedupe_dicts(old.get("newChannelProposals"), agent.get("newChannelProposals"), "id")

    noise = dict(old.get("noiseReport") or {})
    noise.update(agent.get("noiseReport") or {})
    merged["noiseReport"] = noise

    queue = list(old.get("humanReviewQueue") or [])
    for item in agent.get("humanReviewQueue") or []:
        if item not in queue:
            queue.append(item)
    merged["humanReviewQueue"] = queue
    merged["reviewPolicy"] = old.get("reviewPolicy") or {
        "autoApplicable": ["单个关键词权重 <=10% 的微调"],
        "requiresHumanApproval": ["分类增删改名", "渠道增删与升降级", "评分公式与权重", "去重阈值", "blocklist", "robots.txt 状态变化"],
    }
    stats = dict(old.get("stats") or {})
    stats["enrichedByAgent"] = len(payload.get("enrichment") or [])
    merged["stats"] = stats
    return path_day, merged


def cross_check_ids(data_dir, payload, logger):
    """Rule 1 of daily-agent.md: only enrich items that really exist in the corpus."""
    index = read_json(os.path.join(data_dir, "items", "index.json"), None)
    if not index or not isinstance(index.get("items"), list):
        logger("  ! items/index.json unavailable -> skipped id cross-check")
        return None
    known = {i.get("id") for i in index["items"] if isinstance(i, dict)}
    unknown = [e.get("id") for e in (payload.get("enrichment") or [])
               if e.get("id") not in known]
    if unknown:
        logger("  ! %d enrichment id(s) not present in items/index.json: %s"
               % (len(unknown), unknown))
    return unknown


def merge_log(data_dir, payload, date, stamp, counts, started):
    path = os.path.join(data_dir, "logs", "agent-%s.json" % date)
    log = payload.get("log") or {}
    # enrichedCount / formulaCount / newJobs describe what THIS payload
    # contributed for this date, so a later idempotent re-run keeps reporting
    # the real contribution instead of zeroes.
    payload_enrich_ids = [e.get("id") for e in (payload.get("enrichment") or [])]
    payload_formula_ids = [f.get("id") for f in collect_formulas(payload)]
    doc = {
        "date": date,
        "startedAt": started,
        "finishedAt": stamp,
        "status": log.get("status") or "ok",
        "enrichedCount": len(payload_enrich_ids),
        "formulaCount": len(payload_formula_ids),
        "newJobs": len(counts["jobs"].get("dateIds") or []),
        "notes": log.get("notes") or "",
        "errors": list(log.get("errors") or []),
        "selection": payload.get("selection") or {},
        "generatedBy": "daily-agent",
        "details": {
            "enrichedIds": payload_enrich_ids,
            "formulaIds": payload_formula_ids,
            "jobIds": counts["jobs"].get("dateIds") or [],
            "enrichmentInsertedThisRun": counts["enrichment"]["added"],
            "enrichmentReplacedThisRun": counts["enrichment"]["replaced"],
            "formulasAppendedThisRun": counts["formulas"]["appended"],
            "formulasUpdatedThisRun": counts["formulas"]["updated"],
            "formulasAlreadyPresent": counts["formulas"]["skipped"],
            "jobsAppendedThisRun": counts["jobs"]["added"],
            "jobsAlreadyPresent": counts["jobs"]["skipped"],
            "unknownEnrichmentIds": counts.get("unknownIds"),
        },
    }
    if doc["errors"] and doc["status"] == "ok":
        doc["status"] = "partial"
    return path, doc


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main(argv=None):
    parser = argparse.ArgumentParser(description="Merge the daily-agent payload into web/data.")
    parser.add_argument("--input", default=None,
                        help="payload JSON (default: scripts/agent-input-<date>.json)")
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (default: payload date, else today)")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="data root (default: web/data)")
    parser.add_argument("--dry-run", action="store_true", help="report changes without writing")
    args = parser.parse_args(argv)

    started = now_iso()

    date = args.date
    payload_path = args.input
    if not payload_path:
        guess = date or _dt.date.today().isoformat()
        payload_path = os.path.join(ROOT, "scripts", "agent-input-%s.json" % guess)
    if not os.path.isabs(payload_path):
        payload_path = os.path.join(ROOT, payload_path)
    if not os.path.exists(payload_path):
        raise SystemExit("payload not found: %s" % payload_path)

    payload = read_json(payload_path)
    date = date or payload.get("date") or _dt.date.today().isoformat()
    data_dir = args.data_dir if os.path.isabs(args.data_dir) else os.path.join(ROOT, args.data_dir)
    if not os.path.isdir(data_dir):
        raise SystemExit("data dir not found: %s" % data_dir)

    stamp = now_iso()
    log = lambda msg: print(msg)

    log("payload  : %s" % payload_path)
    log("date     : %s" % date)
    log("data dir : %s" % data_dir)
    log("mode     : %s" % ("dry-run" if args.dry_run else "write"))

    e_path, e_doc, e_info = merge_enrichment(data_dir, payload, stamp)
    unknown_ids = cross_check_ids(data_dir, payload, log)
    f_path, f_doc, f_info = merge_formulas(data_dir, payload, stamp, log)
    j_path, j_doc, j_info = merge_jobs(data_dir, payload, stamp, log)
    p_path, p_doc = merge_proposals(data_dir, payload, date, stamp)
    l_path, l_doc = merge_log(
        data_dir, payload, date, stamp,
        {"enrichment": e_info, "formulas": f_info, "jobs": j_info,
         "unknownIds": unknown_ids}, started,
    )
    latest_path = os.path.join(data_dir, "proposals", "latest.json")

    counts = {"enrichment": e_info, "formulas": f_info, "jobs": j_info}
    log("")
    log("enrichment.json : +%d new, %d updated, total %d" % (len(e_info["added"]), len(e_info["replaced"]), e_info["total"]))
    log("formulas.json   : +%d appended, %d updated, %d unchanged, total %d"
        % (len(f_info["appended"]), len(f_info["updated"]), len(f_info["skipped"]), f_info["total"]))
    log("jobs.json       : +%d appended, %d already present, total %d" % (len(j_info["added"]), len(j_info["skipped"]), j_info["total"]))
    log("proposals       : %s (+ latest.json mirror)" % p_path)
    log("agent log       : %s" % l_path)
    log("payload record  : enriched=%d formulas=%d jobs=%d -> %s"
        % (l_doc["enrichedCount"], l_doc["formulaCount"], l_doc["newJobs"], l_path))
    if unknown_ids:
        log("WARNING         : %d enrichment id(s) missing from items/index.json" % len(unknown_ids))

    if args.dry_run:
        log("\ndry-run: nothing written.")
        return 0

    write_json(e_path, e_doc, style="pretty2")   # new file
    write_json(f_path, f_doc, style="pretty1")   # seed_formulas.py style
    write_json(j_path, j_doc, style="pretty2")   # wedata_common.write_json style
    write_json(p_path, p_doc, style="compact")   # collect.py style
    write_json(latest_path, p_doc, style="compact")
    write_json(l_path, l_doc, style="pretty2")   # new file

    log("\nverifying every JSON under %s ..." % data_dir)
    files = sorted(glob.glob(os.path.join(data_dir, "**", "*.json"), recursive=True))
    bad = []
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                json.load(fh)
        except Exception as exc:  # noqa: BLE001 - we want the file name in the report
            bad.append((f, str(exc)))
    if bad:
        for f, err in bad:
            log("  ! %s -> %s" % (f, err))
        log("JSON check FAILED: %d bad file(s)" % len(bad))
        return 1
    log("all json ok (%d files)" % len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
