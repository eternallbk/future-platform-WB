#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build ``web/data/jobs.json`` from ``research/jobs_kb.json``.

The front-end (``web/assets/js/core.part.js``) prefers ``jobsKb.jobs`` when it is
present and non-empty, so this script derives exactly one *job posting* per
company record in the knowledge base and passes every other section through
verbatim.

Nothing here is invented. Each output field is either

  * copied verbatim from ``research/jobs_kb.json``, or
  * computed by one of the deterministic, documented rules below.

Usage:
    python scripts/build_jobs_json.py
"""

from __future__ import annotations

import os
import sys
from collections import Counter, OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wedata_common import (  # noqa: E402
    DATA,
    RESEARCH,
    arr,
    ensure_dirs,
    load_json,
    now_iso,
    utf8_stdout,
    write_json,
)

SRC = os.path.join(RESEARCH, "jobs_kb.json")
DST = os.path.join(DATA, "jobs.json")

# ---------------------------------------------------------------------------
# 1. Canonical direction tokens
# ---------------------------------------------------------------------------
# The workbench renders directions through `dirZh()` in views2.part.js, which
# understands exactly these tokens.
CANONICAL_DIRECTIONS = [
    "multimodal",
    "post-training",
    "world-model",
    "generative",
    "rl",
    "agent",
    "infra",
    "embodied",
]

DIRECTION_ALIASES = {
    # multimodal
    "multimodal": "multimodal",
    "multi-modal": "multimodal",
    "multi modal": "multimodal",
    "mllm": "multimodal",
    "vlm": "multimodal",
    "vision": "multimodal",
    "vision-language": "multimodal",
    # post-training
    "post-training": "post-training",
    "posttraining": "post-training",
    "post_training": "post-training",
    "post training": "post-training",
    "sft": "post-training",
    "rlhf": "post-training",
    "alignment": "post-training",
    "dpo": "post-training",
    # world model
    "world-model": "world-model",
    "worldmodel": "world-model",
    "world_model": "world-model",
    "world model": "world-model",
    # embodied
    "embodied": "embodied",
    "embodied-ai": "embodied",
    "vla": "embodied",
    "robotics": "embodied",
    # generative
    "generative": "generative",
    "generation": "generative",
    "gen": "generative",
    "diffusion": "generative",
    # rl
    "rl": "rl",
    "reinforcement-learning": "rl",
    "reinforcement learning": "rl",
    # agent
    "agent": "agent",
    "agents": "agent",
    "tool": "agent",
    "tool-use": "agent",
    # infra
    "infra": "infra",
    "infrastructure": "infra",
    "engineering": "infra",
    "system": "infra",
    "systems": "infra",
    "inference": "infra",
}

# Chinese labels used to synthesise a realistic 算法实习 job title. These are
# display labels chosen by this builder (reported in `build.assumptions`), not
# facts taken from the knowledge base.
TITLE_ZH = {
    "multimodal": "多模态",
    "post-training": "后训练",
    "world-model": "世界模型",
    "generative": "生成式",
    "rl": "强化学习",
    "agent": "Agent",
    "infra": "基础架构",
    "embodied": "具身智能",
}

TIER_INDEX = {"S": 5, "A": 4, "B": 3, "C": 2}
TIER_ORDER = ["S", "A", "B", "C"]
DEFAULT_TIER = "C"

RELEVANCE_FORMULA = "min(100, 55 + 12*(5-tierIndex) + 4*len(directions))"

# ---------------------------------------------------------------------------
# 2. Required key sets (from core.part.js normalizers)
# ---------------------------------------------------------------------------
HAND_REQUIRED = [
    "id",
    "title",
    "difficulty",
    "frequency",
    "topics",
    "prompt",
    "keyPoints",
    "pitfalls",
    "referenceSolution",
    "answerOutline",
    "sources",
]
EXAM_REQUIRED = list(HAND_REQUIRED)

PROBLEM_ARRAY_FIELDS = {"topics", "keyPoints", "pitfalls", "answerOutline", "sources"}
PROBLEM_STRING_FIELDS = {"id", "title", "prompt", "referenceSolution", "difficulty", "type"}
# `frequency` is numeric; the builder leaves it null when the source has no value
# because core.js already falls back to 3 via `pick(p.frequency, 3) || 3`.
PROBLEM_NULL_FIELDS = {"frequency"}

MISSING = object()


# ---------------------------------------------------------------------------
# 3. Derivation rules
# ---------------------------------------------------------------------------
def canonical_directions(raw_dirs):
    """Map source direction strings onto canonical tokens, preserving the
    source's own ordering and dropping duplicates."""
    out, unknown = [], []
    for item in arr(raw_dirs):
        key = str(item).strip().lower()
        token = DIRECTION_ALIASES.get(key)
        if token is None:
            unknown.append(str(item))
            continue
        if token not in out:
            out.append(token)
    return out, unknown


def make_title(directions):
    """Realistic 算法实习 title.

    * no direction  -> "算法实习生"
    * one direction -> "<方向>算法实习生"   (e.g. 多模态算法实习生)
    * many          -> "算法实习生（A / B / C）" using the first three
                        directions in source order.
    """
    if not directions:
        return "算法实习生"
    if len(directions) == 1:
        return "%s算法实习生" % TITLE_ZH.get(directions[0], directions[0])
    head = " / ".join(TITLE_ZH.get(d, d) for d in directions[:3])
    return "算法实习生（%s）" % head


def relevance_of(tier, n_directions):
    idx = TIER_INDEX.get(tier, TIER_INDEX[DEFAULT_TIER])
    return int(min(100, 55 + 12 * (5 - idx) + 4 * n_directions))


def tier_rank(tier):
    try:
        return TIER_ORDER.index(tier)
    except ValueError:
        return len(TIER_ORDER)


def company_to_job(company, posted_at):
    intern = company.get("internship") or {}
    directions, unknown = canonical_directions(company.get("directions"))
    tier = company.get("tier") or DEFAULT_TIER

    return OrderedDict(
        [
            ("id", company.get("id")),
            ("company", company.get("name")),
            ("shortName", company.get("shortName")),
            ("tier", tier),
            ("title", make_title(directions)),
            ("directions", directions),
            ("cities", arr(company.get("cities"))),
            ("pay", intern.get("dailyPayRange")),
            ("duration", intern.get("duration")),
            ("conversion", intern.get("conversion")),
            ("open", intern.get("open") is not False),
            ("applyUrl", intern.get("applyUrl")),
            ("seasonality", intern.get("seasonality")),
            ("highlights", arr(company.get("highlights"))),
            ("process", arr(company.get("interviewProcess"))),
            ("notes", company.get("notes") or ""),
            ("confidence", company.get("confidence")),
            ("sources", [dict(s) for s in arr(company.get("sources")) if isinstance(s, dict)]),
            ("relevance", relevance_of(tier, len(directions))),
            ("postedAt", posted_at),
            ("deadline", company.get("deadline")),  # null unless the source states one
        ]
    ), unknown


def order_and_fill(raw, required):
    """Required keys first (never missing / never None for arrays+strings),
    then any extra keys the source carries, preserved verbatim."""
    out = OrderedDict()
    for key in required:
        val = raw.get(key, MISSING)
        out[key] = None if val is MISSING else val
    for key, val in raw.items():
        if key not in out:
            out[key] = val
    for key in required:
        if out[key] is None:
            if key in PROBLEM_ARRAY_FIELDS:
                out[key] = []
            elif key in PROBLEM_STRING_FIELDS:
                out[key] = ""
            elif key in PROBLEM_NULL_FIELDS:
                out[key] = None
    return out


# ---------------------------------------------------------------------------
# 4. Build
# ---------------------------------------------------------------------------
def main():
    utf8_stdout()
    ensure_dirs()

    kb = load_json(SRC)
    if kb is None:
        print("[x] missing source: %s" % SRC)
        return 1

    built_at = now_iso()

    jobs, unknown_tokens, mapped = [], Counter(), Counter()
    for company in kb.get("companies") or []:
        job, unknown = company_to_job(company, built_at)
        jobs.append(job)
        for d in job["directions"]:
            mapped[d] += 1
        unknown_tokens.update(unknown)

    jobs.sort(key=lambda j: (tier_rank(j["tier"]), -j["relevance"], str(j["id"])))

    hand = [order_and_fill(p, HAND_REQUIRED) for p in (kb.get("handWrittenCoding") or [])]
    exam = [order_and_fill(p, EXAM_REQUIRED) for p in (kb.get("writtenExam") or [])]
    skills = kb.get("skillMatrix") or []
    interviews = kb.get("interviewProcess") or []
    salaries = kb.get("salaryBands") or []

    doc = OrderedDict(
        [
            ("jobs", jobs),
            ("skillMatrix", skills),
            ("handWrittenCoding", hand),
            ("writtenExam", exam),
            ("interviewProcess", interviews),
            ("salaryBands", salaries),
            ("confidenceSummary", kb.get("confidenceSummary") or {}),
            ("meta", kb.get("meta") or {}),
            (
                "build",
                OrderedDict(
                    [
                        ("builtAt", built_at),
                        ("builder", "scripts/build_jobs_json.py"),
                        ("sourceFile", "research/jobs_kb.json"),
                        (
                            "counts",
                            OrderedDict(
                                [
                                    ("companiesIn", len(kb.get("companies") or [])),
                                    ("jobsOut", len(jobs)),
                                    ("skillMatrix", len(skills)),
                                    ("handWrittenCoding", len(hand)),
                                    ("writtenExam", len(exam)),
                                    ("interviewProcess", len(interviews)),
                                    ("salaryBands", len(salaries)),
                                ]
                            ),
                        ),
                        ("relevanceFormula", RELEVANCE_FORMULA),
                        ("tierIndex", TIER_INDEX),
                        ("canonicalDirections", CANONICAL_DIRECTIONS),
                        (
                            "assumptions",
                            [
                                "job.id = the source company id (verbatim)",
                                "job.title is synthesised: 1 direction -> '<方向>算法实习生'; "
                                ">1 -> '算法实习生（前三个方向 / 分隔）'; 0 -> '算法实习生'",
                                "job.postedAt = this build's timestamp for every job (the knowledge "
                                "base carries no per-posting publication date)",
                                "job.deadline = company.deadline if the source ever states one, otherwise null",
                                "job.open mirrors internship.open (all 21 source records say true)",
                                "job.pay/duration/conversion/applyUrl/seasonality come from internship.*",
                                "job.process = company.interviewProcess",
                            ],
                        ),
                        ("unmappedDirectionStrings", dict(unknown_tokens)),
                    ]
                ),
            ),
        ]
    )

    size = write_json(DST, doc)
    print("[ok] wrote %s (%d bytes)" % (DST, size))
    print("     jobs=%d (from %d companies)" % (len(jobs), len(kb.get("companies") or [])))
    print("     canonical direction coverage: %s" % dict(sorted(mapped.items())))
    print("     unmapped direction strings: %s" % (dict(unknown_tokens) or "none"))
    print("     handWrittenCoding=%d writtenExam=%d skillMatrix=%d"
          % (len(hand), len(exam), len(doc["skillMatrix"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
