#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build ``web/data/learning.json`` from ``research/learning_kb.json``.

If the research artifact is missing (it is produced by a separate agent), this
script writes a *minimal but valid* placeholder instead, so the workbench's
仓库与课程 / 学习路线 / 进展 views render their empty states rather than erroring.

Normalisation never invents values: the output objects mirror core.part.js's
``normalizeTrack`` / ``normalizeRepo`` / ``normalizeCourse`` / ``normalizePaper``
key sets exactly, using the same `pick()` fallbacks (including the front-end's
own literal defaults such as 0 / '' / false / []), and every extra key the source
carries is preserved verbatim.

Usage:
    python scripts/build_learning_json.py
"""

from __future__ import annotations

import os
import sys
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wedata_common import (  # noqa: E402
    DATA,
    RESEARCH,
    SEED_COLLECTOR_VERSION,
    arr,
    ensure_dirs,
    load_json,
    now_iso,
    pick,
    utf8_stdout,
    write_json,
)

SRC = os.path.join(RESEARCH, "learning_kb.json")
DST = os.path.join(DATA, "learning.json")


def tail_extra(raw, out):
    """Append any source key the normaliser did not already emit."""
    for key, val in raw.items():
        if key not in out:
            out[key] = val
    return out


def n_task(raw, index, track_id, module_index):
    raw = raw if isinstance(raw, dict) else {}
    out = OrderedDict(
        [
            ("id", str(pick(raw.get("id"), "%s-m%d-t%d" % (track_id, module_index, index)))),
            ("title", str(pick(raw.get("title"), raw.get("name"), "—"))),
            ("type", raw.get("type") or "study"),
            ("estimateHours", float(pick(raw.get("estimateHours"), raw.get("hours"), 0) or 0)),
            ("deliverable", raw.get("deliverable") or ""),
            ("done", raw.get("done") or raw.get("acceptance") or ""),
        ]
    )
    return tail_extra(raw, out)


def n_module(raw, index, track_id):
    raw = raw if isinstance(raw, dict) else {}
    out = OrderedDict(
        [
            ("id", str(pick(raw.get("id"), "%s-m%d" % (track_id, index)))),
            ("title", str(pick(raw.get("title"), raw.get("name"), "模块 %d" % (index + 1)))),
            ("week", raw.get("week")),
            ("hours", float(pick(raw.get("hours"), 0) or 0)),
            ("objectives", [str(x) for x in arr(raw.get("objectives"))]),
            ("concepts", [str(x) for x in arr(raw.get("concepts"))]),
            ("tasks", [n_task(t, j, track_id, index) for j, t in enumerate(arr(raw.get("tasks")))]),
            ("paperIds", arr(raw.get("paperIds"))),
            ("repoIds", arr(raw.get("repoIds"))),
            ("courseIds", arr(raw.get("courseIds"))),
        ]
    )
    return tail_extra(raw, out)


def n_track(raw):
    raw = raw if isinstance(raw, dict) else {}
    track_id = str(pick(raw.get("id"), raw.get("name"), "track"))
    out = OrderedDict(
        [
            ("id", track_id),
            ("name", str(pick(raw.get("name"), raw.get("title"), "—"))),
            ("goal", raw.get("goal") or ""),
            ("weeks", float(pick(raw.get("durationWeeks"), raw.get("weeks"), 0) or 0)),
            ("level", raw.get("level") or "core"),
            ("prerequisites", [str(x) for x in arr(raw.get("prerequisites"))]),
            ("modules", [n_module(m, i, track_id) for i, m in enumerate(arr(raw.get("modules")))]),
        ]
    )
    return tail_extra(raw, out)


def n_repo(raw):
    raw = raw if isinstance(raw, dict) else {}
    out = OrderedDict(
        [
            ("id", str(pick(raw.get("id"), raw.get("name"), "repo"))),
            ("owner", raw.get("owner") or ""),
            ("name", str(pick(raw.get("name"), raw.get("repo"), "—"))),
            ("url", pick(raw.get("url"), raw.get("htmlUrl")) or ""),
            ("stars", float(pick(raw.get("stars"), raw.get("stargazers"), 0) or 0)),
            ("language", raw.get("language") or ""),
            ("area", raw.get("area") or ""),
            ("difficulty", raw.get("difficulty") or "medium"),
            ("why", raw.get("why") or ""),
            ("studyPlan", [str(x) for x in arr(raw.get("studyPlan"))]),
            ("checkpoints", [str(x) for x in arr(raw.get("checkpoints"))]),
            ("status", raw.get("status") or "active"),
            ("lastVerified", raw.get("lastVerified")),
        ]
    )
    return tail_extra(raw, out)


def n_course(raw):
    raw = raw if isinstance(raw, dict) else {}
    out = OrderedDict(
        [
            ("id", str(pick(raw.get("id"), raw.get("title"), "course"))),
            ("title", str(pick(raw.get("title"), raw.get("name"), "—"))),
            ("provider", raw.get("provider") or ""),
            ("year", raw.get("year")),
            ("url", raw.get("url") or ""),
            ("language", raw.get("language") or "en"),
            ("hours", float(pick(raw.get("hours"), 0) or 0)),
            ("level", raw.get("level") or "intermediate"),
            ("area", raw.get("area") or ""),
            ("hasAssignments", bool(raw.get("hasAssignments"))),
            ("why", raw.get("why") or ""),
            ("modules", [str(x) for x in arr(raw.get("modules"))]),
            ("status", raw.get("status") or "active"),
        ]
    )
    return tail_extra(raw, out)


def n_paper(raw):
    raw = raw if isinstance(raw, dict) else {}
    out = OrderedDict(
        [
            ("id", str(pick(raw.get("id"), raw.get("title"), "paper"))),
            ("title", str(pick(raw.get("title"), "—"))),
            ("year", raw.get("year")),
            ("venue", raw.get("venue") or ""),
            ("ccf", raw.get("ccf")),
            ("area", raw.get("area") or ""),
            ("url", raw.get("url") or ""),
            ("why", raw.get("why") or ""),
            ("readingOrder", raw.get("readingOrder")),
            ("difficulty", raw.get("difficulty") or "medium"),
            ("mustRead", bool(raw.get("mustRead"))),
            ("keyIdeas", [str(x) for x in arr(raw.get("keyIdeas"))]),
            ("readTime", raw.get("readTime") or ""),
            ("followUps", [str(x) for x in arr(raw.get("followUps"))]),
        ]
    )
    return tail_extra(raw, out)


def placeholder(reason):
    """The exact minimal shape requested by the delegating agent.

    Deliberately NOT padded with extra metadata: `meta.placeholder == True` plus
    `meta.reason` is all a reader needs to know this is an empty state and not
    real researched content.
    """
    return OrderedDict(
        [
            (
                "meta",
                OrderedDict(
                    [
                        ("generatedAt", now_iso()),
                        ("placeholder", True),
                        ("reason", reason),
                    ]
                ),
            ),
            ("tracks", []),
            ("papers", []),
            ("repos", []),
            ("courses", []),
            ("milestones", []),
            ("studySystem", None),
        ]
    )


def main():
    utf8_stdout()
    ensure_dirs()

    kb = load_json(SRC)
    if not isinstance(kb, dict):
        doc = placeholder("learning_kb.json not available")
        size = write_json(DST, doc)
        print("[!] %s not found -> wrote placeholder %s (%d bytes)" % (SRC, DST, size))
        return 0

    tracks = [n_track(t) for t in arr(kb.get("tracks"))]
    repos = [n_repo(r) for r in arr(kb.get("repos"))]
    courses = [n_course(c) for c in arr(kb.get("courses"))]
    papers = [n_paper(p) for p in arr(kb.get("papers"))]
    milestones = [m for m in arr(kb.get("milestones"))]
    study = kb.get("studySystem")
    meta = kb.get("meta") or {}

    doc = OrderedDict(
        [
            ("meta", meta),
            ("tracks", tracks),
            ("papers", papers),
            ("repos", repos),
            ("courses", courses),
            ("milestones", milestones),
            ("studySystem", study),
            (
                "build",
                OrderedDict(
                    [
                        ("builtAt", now_iso()),
                        ("builder", "scripts/build_learning_json.py"),
                        ("sourceFile", "research/learning_kb.json"),
                        ("placeholder", False),
                        (
                            "counts",
                            OrderedDict(
                                [
                                    ("tracks", len(tracks)),
                                    ("papers", len(papers)),
                                    ("repos", len(repos)),
                                    ("courses", len(courses)),
                                    ("milestones", len(milestones)),
                                ]
                            ),
                        ),
                    ]
                ),
            ),
        ]
    )
    size = write_json(DST, doc)
    print("[ok] wrote %s (%d bytes)" % (DST, size))
    print("     tracks=%d papers=%d repos=%d courses=%d milestones=%d studySystem=%s"
          % (len(tracks), len(papers), len(repos), len(courses), len(milestones),
             "yes" if study else "no"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
