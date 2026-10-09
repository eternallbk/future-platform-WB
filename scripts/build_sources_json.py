#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build ``web/data/sources.json`` (channel + taxonomy registry) and the matching
``web/data/taxonomy.json`` (read by the 知识分类 page).

Sources of truth, in priority order:

1. ``research/source_registry.json`` when it exists — its probed channels,
   taxonomy, scoring, dedupe, reliability, logging, legitimacy and evolution
   win over the fallbacks.
2. The *live* ``web/data/sources.json`` already on disk. ``scripts/collect.py``
   rewrites its ``channels`` array from an actual run, and an observed run result
   is stronger evidence than any probe, so a live ``status`` is never downgraded
   back to ``unknown``.
3. ``scripts/collect.py``'s own ``DEFAULT_CATEGORIES``, ``CHANNEL_SPECS``,
   ``CHANNEL_NAMES``, ``DEFAULT_CONFIG`` — imported, never copied by hand, so the
   static layer and the daily collector can never drift apart.
4. A small hand-written table in this file, used ONLY for the channels the
   collector does not know about (pwc, acl, leetcode, codeforces, manual).

Honesty rules enforced here:
* ``status`` is ``"unknown"`` unless a real observation exists (registry probe or
  live collector run). Every inferred status records its ``statusSource`` and the
  ``httpStatus`` / ``evidenceFile`` it came from, so the claim is auditable.
* This builder makes no network call of its own.
* ``rateLimit`` is the registry's measured value when available, otherwise an
  explicitly self-imposed throttle ("自设").

Usage:
    python scripts/build_sources_json.py
"""

from __future__ import annotations

import os
import re
import sys
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wedata_common import (  # noqa: E402
    DATA,
    RESEARCH,
    ensure_dirs,
    import_collect,
    load_json,
    now_iso,
    utf8_stdout,
    write_json,
)

SOURCES_DST = os.path.join(DATA, "sources.json")
TAXONOMY_DST = os.path.join(DATA, "taxonomy.json")
REGISTRY_SRC = os.path.join(RESEARCH, "source_registry.json")

CJK = re.compile(r"[\u4e00-\u9fff]")

# The 14 ids the workbench's CATEGORIES table and the task brief both require,
# in the brief's order.
REQUIRED_CATEGORY_IDS = [
    "multimodal",
    "posttraining",
    "worldmodel",
    "generative",
    "rl",
    "agent",
    "foundation",
    "engineering",
    "coding",
    "exam",
    "job",
    "paper",
    "course",
    "trend",
]

# The channel ids the brief requires, in the brief's order.
REQUIRED_CHANNEL_IDS = [
    "arxiv",
    "hf_papers",
    "hf_models",
    "github",
    "gh_trending",
    "openreview",
    "s2",
    "pwc",
    "acl",
    "hn",
    "reddit",
    "nowcoder",
    "zhihu",
    "xiaohongshu",
    "boss",
    "shixiseng",
    "lagou",
    "leetcode",
    "codeforces",
    "jobs_bytedance",
    "jobs_tencent",
    "jobs_alibaba",
    "jobs_zhipu",
    "jobs_moonshot",
    "jobs_deepseek",
    "jobs_minimax",
    "jobs_shailab",
    "machineheart",
    "qbitai",
    "rsshub",
    "manual",
]

# Channels the collector also knows about, kept as a bonus.
EXTRA_COLLECTOR_CHANNEL_IDS = ["hf_blog_rss", "openai_rss"]

LOGIN_WALLED = ["xiaohongshu", "boss", "shixiseng", "lagou"]

# ---------------------------------------------------------------------------
# research/source_registry.json -> this file's id space.
# The registry probes concrete endpoints (arxiv-api, github-trending-html, ...),
# which is a finer granularity than the workbench's one-entry-per-source channel
# list. These explicit maps are the only place the two are bridged.
# ---------------------------------------------------------------------------
REGISTRY_CHANNEL_ALIASES = {
    "arxiv": "arxiv-api",
    "hf_papers": "hf-daily-papers",
    "hf_models": "hf-models",
    "github": "github-search-repos",
    "gh_trending": "github-trending-html",
    "openreview": "openreview-api2",
    "s2": "semantic-scholar-api",
    "pwc": "paperswithcode-api",
    "acl": "acl-anthology-events",
    "hn": "hn-algolia",
    "reddit": "reddit-json",
    "nowcoder": "nowcoder-feed-api",
    "zhihu": "zhihu-api-v4",
    "xiaohongshu": "xiaohongshu-search",
    "boss": "zhipin-boss",
    "shixiseng": "shixiseng",
    "lagou": "lagou",
    "leetcode": "leetcode-graphql",
    "codeforces": "codeforces-api",
    "jobs_bytedance": "jobs-bytedance-api",
    "jobs_tencent": "careers-tencent-api",
    "jobs_alibaba": "talent-alibaba",
    "jobs_zhipu": "zhipu-careers",
    "jobs_moonshot": "moonshot-careers",
    "jobs_deepseek": "deepseek-careers",
    "jobs_minimax": "minimax-careers",
    "jobs_shailab": "shlab-careers",
    "machineheart": "media-jiqizhixin",
    "qbitai": "media-qbitai",
    "rsshub": "rsshub-public",
    "manual": None,  # purely human
    "hf_blog_rss": "hf-blog-rss",
    "openai_rss": "lab-openai-rss",
}

# registry taxonomy ids that stand for the same concept as an app category id.
REGISTRY_TAXONOMY_ALIASES = {
    "multimodal": "multimodal-algorithm",
    "posttraining": "post-training",
    "generative": "generative-models",
    "worldmodel": "world-model",
    "foundation": "llm-foundation",
    "agent": "agent",
    "engineering": "training-infra",
    "job": "job-hunting",
}

# Channels the collector does not define. Tiers mirror the workbench's own
# CHANNELS table (core.part.js); modes are this builder's best-effort choice,
# overridden by the registry probe when one exists.
EXTRA_CHANNEL_SPECS = {
    "pwc": {"tier": "P2", "mode": "html", "nameZh": "PapersWithCode", "auth": False,
            "rateLimit": "自设：串行 ≤1 次/5s，单次 ≤10 条",
            "riskNote": "站点长期改版，HTML 结构不稳定；无官方公开 API。"},
    "acl": {"tier": "P1", "mode": "html", "nameZh": "ACL Anthology", "auth": False,
            "rateLimit": "自设：串行 ≤1 次/3s，单次 ≤20 条",
            "riskNote": "静态页面，需自行解析 BibTeX/HTML。"},
    "leetcode": {"tier": "P0", "mode": "api", "nameZh": "LeetCode", "auth": False,
                 "rateLimit": "自设：串行 ≤1 次/2s，单次 ≤30 条",
                 "riskNote": "无公开文档化 API，依赖站点内部 GraphQL 端点，可能触发反爬或需登录。"},
    "codeforces": {"tier": "P2", "mode": "api", "nameZh": "Codeforces", "auth": False,
                   "rateLimit": "自设：串行 ≤1 次/5s，单次 ≤10 条",
                   "riskNote": "官方公开 API 有调用间隔要求，需串行。"},
    "manual": {"tier": "P0", "mode": "manual", "nameZh": "手动录入", "auth": False,
               "rateLimit": "不自动请求（人工录入）",
               "riskNote": "无网络请求。人工录入的条目必须自带可访问来源链接。"},
    "hf_blog_rss": {"tier": "P2", "mode": "rss", "nameZh": "HF Blog", "auth": False,
                    "rateLimit": "自设：串行 ≤1 次/5s，单次 ≤10 条", "riskNote": "RSS 可用性由 registry 探测。"},
    "openai_rss": {"tier": "P2", "mode": "rss", "nameZh": "OpenAI News", "auth": False,
                   "rateLimit": "自设：串行 ≤1 次/5s，单次 ≤10 条", "riskNote": "RSS 可用性由 registry 探测。"},
}

TIER_RATE_LIMIT = {
    "P0": "自设：串行 ≤1 次/2s，单次 ≤30 条",
    "P1": "自设：串行 ≤1 次/3s，单次 ≤20 条",
    "P2": "自设：串行 ≤1 次/5s，单次 ≤10 条",
}

RISK_NOTES = {
    "arxiv": "官方 API 条款要求请求间隔 ≥3s、单连接；robots.txt 对 export 域全站 Disallow，使用需自行判断合规。",
    "hf_papers": "依赖 HF 对外 JSON 端点，字段可能调整。",
    "hf_models": "公开 API，需翻页节流。",
    "github": "未认证调用配额低，需自设节流；搜索结果噪声大。",
    "gh_trending": "无官方 API，HTML 结构变更会导致解析失败。",
    "openreview": "API 版本（v1/v2）差异大，venue 端点需逐个适配。",
    "s2": "公开 Graph API 有速率限制，无 key 时更严。",
    "pwc": "域名已整体重定向到 huggingface.co/papers；原 API 路径不再独立可用。",
    "acl": "部分 anthology RSS 端点 404，需退回索引页解析。",
    "hn": "公开 API 稳定，但内容与算法岗相关性低，需强过滤。",
    "reddit": "公开 JSON 端点限流严格，可能返回 429。",
    "nowcoder": "讨论页为动态渲染，解析易碎；登录后内容更多。",
    "zhihu": "完整回答/热榜需登录，未授权接口属越界。",
    "xiaohongshu": "robots.txt 全站 Disallow + 接口签名；列为 off-limits，仅人工导入。",
    "boss": "robots.txt 点名禁止搜索类 URL + 强风控；列为 off-limits，仅人工导入。",
    "shixiseng": "列表页有滑块验证；列为 off-limits，仅人工导入。",
    "lagou": "阿里云 WAF 直接拦截（verify/captcha）；列为 off-limits，仅人工导入。",
    "leetcode": "无公开文档化 API，依赖站点内部 GraphQL 端点。",
    "codeforces": "官方公开 API 有调用间隔要求。",
    "jobs_bytedance": "招聘页为动态渲染/内部接口，结构易变。",
    "jobs_tencent": "招聘接口需 POST JSON，参数可能变动。",
    "jobs_alibaba": "招聘页动态渲染，岗位页链接需二次解析。",
    "jobs_zhipu": "公司招聘页结构简单但改版频繁。",
    "jobs_moonshot": "岗位页为单页应用，需渲染后取数。",
    "jobs_deepseek": "官网岗位列表更新不规律。",
    "jobs_minimax": "岗位页为单页应用，需渲染后取数。",
    "jobs_shailab": "机构官网岗位页与校招页分离，需人工确认入口。",
    "machineheart": "正文有反爬与付费墙。",
    "qbitai": "落地页广告与推荐位噪声大。",
    "rsshub": "公共实例不稳定，自建更可靠。",
    "manual": "无网络请求。",
}

DEFAULT_RISK = "该渠道在 research/source_registry.json 中无对应记录，且未在实采运行中出现过，风险未评估。"


def split_keywords(keywords):
    zh, en = [], []
    for kw in keywords or []:
        (zh if CJK.search(str(kw)) else en).append(kw)
    return zh, en


def registry_status(reg):
    """Derive an honest status from a registry probe record.

    The registry verified every channel (``verified: true``) and recorded
    ``httpStatus`` plus a robots/ToS assessment. Only a 200 probe counts as
    ``ok``; anything else is a real failure, not a silent 'unknown'.
    """
    mode = reg.get("recommendedMode") or ""
    hs = reg.get("httpStatus")
    if mode in ("off-limits", "unreachable"):
        return "error"
    if hs == 200:
        return "ok"
    if isinstance(hs, int):
        return "error"
    return "unknown"


def registry_mode(reg, fallback):
    """Map the registry's richer mode vocabulary onto the required enum."""
    mapping = {
        "api": "api",
        "rss": "rss",
        "html-scrape": "html",
        "manual/needs-login": "manual",
    }
    return mapping.get(reg.get("recommendedMode") or "", fallback)


def status_source(cid, reg, live):
    """A one-line audit trail for the status we are about to publish."""
    if live and live.get("status"):
        return ("live collect.py run %s (status=%s, count=%s)"
                % (live.get("lastChecked") or live.get("checkedAt") or "?",
                   live.get("status"), live.get("count")))
    if reg:
        ev = reg.get("evidenceFile")
        return ("source_registry.json probe %s (httpStatus=%s, verified=%s%s)"
                % (reg.get("lastChecked") or "?", reg.get("httpStatus"),
                   reg.get("verified"), ", evidence=%s" % ev if ev else ""))
    return "no observation available - status is unknown on purpose"


def build_categories(collect, registry):
    """Return the merged category list (always the 14 required ids first)."""
    reg_cats, reg_extra = {}, {}
    if isinstance(registry, dict):
        for key in ("categories", "taxonomy"):
            for cat in registry.get(key) or []:
                if isinstance(cat, dict) and cat.get("id"):
                    reg_cats[cat["id"]] = cat

    used_reg_ids = set()

    def make(cid):
        alias = REGISTRY_TAXONOMY_ALIASES.get(cid)
        base = {}
        if alias and alias in reg_cats:
            base = reg_cats[alias]
            used_reg_ids.add(alias)
        elif cid in reg_cats:
            base = reg_cats[cid]
            used_reg_ids.add(cid)
        src = collect.DEFAULT_CATEGORIES.get(cid, {}) or {}

        keywords = base.get("keywords") or src.get("keywords") or []
        kw_zh = base.get("keywordsZh") or [k for k in keywords if CJK.search(str(k))]
        kw_en = base.get("keywordsEn") or [k for k in keywords if not CJK.search(str(k))]
        description = base.get("description") or src.get("desc") or ""
        goal = base.get("collectionGoal") or src.get("goal") or ""
        # The pipeline really runs on this cron (collect.py schedule == registry
        # tiers.schedule), so prefer the concrete value over a bare "daily".
        cadence = "每日 14:00 (Asia/Shanghai)"
        weight = base.get("relevanceWeight")
        if weight is None:
            weight = src.get("weight", 0.8)

        out = OrderedDict(
            [
                ("id", cid),
                ("nameZh", base.get("nameZh") or src.get("zh") or cid),
                ("nameEn", base.get("nameEn") or src.get("en") or cid),
                ("description", description),
                ("collectionGoal", goal),
                ("updateCadence", cadence),
                ("relevanceWeight", weight),
                ("keywordsZh", list(kw_zh)),
                ("keywordsEn", list(kw_en)),
                ("arxivCategories", list(base.get("arxivCategories") or src.get("arxiv") or [])),
                # Aliases: the 知识分类 page reads taxonomy.json categories raw and
                # looks up `t.desc` / `t.goal` / `t.cadence` (views.part.js:499-508).
                ("desc", description),
                ("goal", goal),
                ("cadence", cadence),
                ("keywords", list(kw_en) + list(kw_zh)),
            ]
        )
        for extra in ("dedupeRules", "storagePath", "tier", "registryId", "registryUpdateCadence"):
            val = base.get(extra) if extra in base else None
            if extra == "registryId":
                val = alias if alias in reg_cats else (cid if cid in reg_cats else None)
            if extra == "registryUpdateCadence":
                val = base.get("updateCadence")
            if val is not None:
                out[extra] = val
        return out

    out = [make(cid) for cid in REQUIRED_CATEGORY_IDS]
    # Anything the collector knows beyond the required 14 (none today, but keep
    # the merge honest if collect.py grows a category).
    for cid in collect.DEFAULT_CATEGORIES:
        if cid not in REQUIRED_CATEGORY_IDS:
            out.append(make(cid))
    # Registry taxonomy entries that stand for a concept the app does not model.
    for cid, cat in reg_cats.items():
        if cid not in used_reg_ids:
            reg_extra[cid] = cat
    return out, reg_extra


def build_channels(collect, registry, live):
    specs = dict(collect.CHANNEL_SPECS)
    names = dict(collect.CHANNEL_NAMES)
    for cid, spec in EXTRA_CHANNEL_SPECS.items():
        specs.setdefault(cid, {"tier": spec["tier"], "mode": spec["mode"], "auth": spec["auth"]})
        names.setdefault(cid, spec["nameZh"])

    implemented = set(getattr(collect, "COLLECTORS", {}) or {})
    reg_by_id = {}
    if isinstance(registry, dict):
        for ch in registry.get("channels") or []:
            if isinstance(ch, dict) and ch.get("id"):
                reg_by_id[ch["id"]] = ch
    live_by_id = {}
    if isinstance(live, dict):
        for ch in live.get("channels") or []:
            if isinstance(ch, dict) and ch.get("id"):
                live_by_id[ch["id"]] = ch

    order = list(REQUIRED_CHANNEL_IDS) + list(EXTRA_COLLECTOR_CHANNEL_IDS)
    for cid in specs:
        if cid not in order:
            order.append(cid)

    used_reg_ids, preserved, out = set(), [], []
    for cid in order:
        spec = specs.get(cid, {})
        extra = EXTRA_CHANNEL_SPECS.get(cid, {})
        reg_id = REGISTRY_CHANNEL_ALIASES.get(cid, cid)
        reg = (reg_by_id.get(reg_id) if reg_id else None) or reg_by_id.get(cid) or {}
        if reg:
            used_reg_ids.add(reg.get("id"))
        live_ch = live_by_id.get(cid) or {}

        tier = reg.get("tier") or live_ch.get("tier") or spec.get("tier") or extra.get("tier") or "P2"
        auth = bool(spec.get("auth") or extra.get("auth") or reg.get("authRequired")
                    or live_ch.get("authRequired"))
        if cid in LOGIN_WALLED:
            auth = True
        mode = spec.get("mode") or extra.get("mode") or "html"
        mode = registry_mode(reg, mode)
        if auth and cid in LOGIN_WALLED:
            mode = "manual"

        # Precedence: a live run result beats a registry probe, which beats nothing.
        if live_ch.get("status"):
            status = live_ch["status"]
        elif reg:
            status = registry_status(reg)
        else:
            status = "unknown"
        if live_ch.get("status"):
            preserved.append(cid)

        rate = reg.get("rateLimit")
        if not rate or str(rate).lower() == "unknown":
            rate = live_ch.get("rateLimit") or extra.get("rateLimit")
        if not rate:
            rate = TIER_RATE_LIMIT.get(tier, TIER_RATE_LIMIT["P2"]) if mode != "manual" else "不自动请求（人工导入）"

        rec = OrderedDict(
            [
                ("id", cid),
                ("nameZh", reg.get("nameZh") or live_ch.get("nameZh") or names.get(cid)
                 or extra.get("nameZh") or cid),
                ("tier", tier),
                ("mode", mode),
                ("authRequired", auth),
                ("status", status),
                ("rateLimit", rate),
                ("lastChecked", live_ch.get("lastChecked") or live_ch.get("checkedAt")
                 or reg.get("lastChecked")),
                ("riskNote", RISK_NOTES.get(cid) or reg.get("riskNote") or extra.get("riskNote")
                 or DEFAULT_RISK),
                ("collectorImplemented", bool(live_ch.get("collectorImplemented",
                                                          cid in implemented))),
                # ---- audit trail for the status claim above -------------------
                ("statusSource", status_source(cid, reg, live_ch)),
                ("verified", bool(reg.get("verified"))),
                ("httpStatus", reg.get("httpStatus") if reg else None),
                ("registryId", reg.get("id")),
                ("homepage", reg.get("homepage")),
                ("probeUrl", reg.get("probeUrl")),
                ("robotsPolicy", reg.get("robotsPolicy")),
                ("authDetail", reg.get("authDetail")),
            ]
        )
        out.append(rec)

    unmapped = [cid for cid in reg_by_id if cid not in used_reg_ids]
    return out, unmapped, preserved


def build_manual_channels(collect):
    """The human-import workflow for the login-walled channels."""
    names = dict(collect.CHANNEL_NAMES)
    for cid, spec in EXTRA_CHANNEL_SPECS.items():
        names.setdefault(cid, spec["nameZh"])
    how_to = "人工登录后导出 CSV/JSON 放入 web/data/inbox/，下次运行时自动合并。"
    steps = [
        "在浏览器中手动登录该站点（不使用脚本保存或复用登录态，不绕过风控/验证码）。",
        "用站点自带导出，或手动复制整理为 CSV/JSON，字段：title, company, city, url, pay, postedAt。",
        "保存到 web/data/inbox/，文件名形如 <channel>-<YYYYMMDD>.csv。",
        "手动运行 scripts/collect.py（或 scripts/run-daily.ps1）后，条目与自动采集结果一起入库。",
    ]
    out = []
    for cid in LOGIN_WALLED:
        out.append(
            OrderedDict(
                [
                    ("id", cid),
                    ("nameZh", names.get(cid, cid)),
                    ("authRequired", True),
                    ("mode", "manual"),
                    ("howTo", how_to),
                    ("steps", list(steps)),
                    ("importPath", "web/data/inbox/"),
                    ("acceptedFormats", ["csv", "json"]),
                    ("autoMergeImplemented", False),
                    ("notes", "collect.py 在运行时会直接跳过 MANUAL_ONLY 渠道；inbox 自动合并尚未实现，"
                              "该工作流以 collect.py 自身写入的说明为准。"),
                ]
            )
        )
    return out


def default_scoring(collect):
    scoring = dict(collect.DEFAULT_CONFIG.get("scoring") or {})
    scoring.setdefault("minRelevance", 12.0)
    return scoring


def default_dedupe(collect):
    d = dict(collect.DEFAULT_CONFIG.get("dedupe") or {})
    d["levels"] = ["id", "canonicalUrl", "title", "simhash"]
    d["notes"] = "collect.py 的 Deduper 按 id → canonical url → 归一化标题 → simhash 逐层去重。"
    return d


def default_reliability(collect):
    http = collect.DEFAULT_CONFIG.get("http") or {}
    return OrderedDict(
        [
            ("perChannelIsolation", True),
            ("policy", "每个渠道在独立线程中运行并捕获异常，单渠道失败不会中断整轮采集；"
                       "失败渠道的结果仍写入运行日志。"),
            ("statuses", ["ok", "empty", "error", "unknown"]),
            ("retries", OrderedDict([
                ("maxRetries", http.get("maxRetries", 2)),
                ("backoffBase", http.get("backoffBase", 1.6)),
                ("jitter", http.get("jitter", 0.35)),
                ("delayBetweenSec", http.get("delayBetween", 0.4)),
            ])),
            ("timeoutSec", http.get("defaultTimeout", 25)),
            ("backupChannelFallback", True),
            ("degradeAfterConsecutiveFailures", 3),
            ("degradeAction", "标记为 degraded、写入运行日志并暂停该渠道，等待人工复核后再启用。"),
            ("consecutiveFailureTrackingImplemented", False),
            ("notes", "重试/退避/超时/渠道隔离来自 scripts/collect.py 的既定配置与实现；"
                      "「连续失败 3 次自动降级」目前只写在工作台文案里，collector 尚未实现该计数器。"),
        ]
    )


def default_logging(collect):
    retention = collect.DEFAULT_CONFIG.get("retention") or {}
    return OrderedDict(
        [
            ("runsFile", "web/data/logs/runs.json"),
            ("keepRuns", 120),
            ("manifestFile", "web/data/manifest.json"),
            ("digestDir", "web/data/digest"),
            ("itemsIndex", "web/data/items/index.json"),
            ("stateFile", "web/data/state/collector-state.json"),
            ("levels", ["step", "ok", "warn", "err"]),
            ("runRecordFields", ["startedAt", "status", "newItems", "channelsOk",
                                 "channelsTotal", "durationSec", "notes"]),
            ("retention", OrderedDict([
                ("archiveAfterDays", retention.get("archiveAfterDays", 90)),
                ("keepDayFiles", retention.get("keepDayFiles", 400)),
            ])),
            ("notes", "collect.py 以 runs[:120] 截断写入；工作台「采集与运行」页展示最近 25 条。"),
        ]
    )


def default_legitimacy(collect):
    ua = (collect.DEFAULT_CONFIG.get("http") or {}).get("userAgent", "")
    return OrderedDict(
        [
            ("personalUseOnly", True),
            ("purpose", "个人学术研究与求职信息整理；不做二次分发、不做商业用途。"),
            ("userAgent", ua),
            ("publicSourcesOnly", True),
            ("loginWalledChannels", list(LOGIN_WALLED)),
            ("loginWalledPolicy", "不自动抓取需登录站点；collect.py 的 MANUAL_ONLY 在运行前直接跳过这些渠道，"
                                  "只接受人工登录后自行导出、放入 web/data/inbox/ 的数据。"),
            ("robotsTxtChecked", False),
            ("termsOfServiceReviewed", False),
            ("minDelaySec", (collect.DEFAULT_CONFIG.get("http") or {}).get("delayBetween", 0.4)),
            ("throttlingPolicy", "所有渠道串行请求，默认 0.4s 间隔 + 指数退避（base 1.6、抖动 0.35）；"
                                 "单渠道单轮默认 ≤30 条。"),
            ("dataRetention", "仅保存在本地；每条记录必须保留可访问的原始链接以便回溯，不抓取付费/私密内容。"),
            ("notes", "本对象描述的是既定使用意图与代码中已实现的约束。robots.txt 与各站点 ToS 的人工复核"
                      "尚未执行，因此对应字段为 false，不做未经核实的合规声明。"),
        ]
    )


def default_evolution(collect):
    return OrderedDict(
        [
            ("signals", ["未被点击 / 未收藏的条目", "渠道连续失败", "空摘要率", "分类覆盖率", "重复率"]),
            ("weeklyProposalFile", "web/data/proposals.json"),
            ("implemented", False),
            ("proposedActions", ["新增渠道", "新增分类", "调整分类关键词权重", "降级长期无产出的渠道"]),
            ("reviewWorkflow", "提案写入 proposals.json → 在「采集与运行」页人工复核 → 确认后更新 "
                               "config/collector.config.json 才生效。"),
            ("notes", "该流程来自工作台「自我迭代」面板的既定设计；collect.py 目前只写入运行日志与 manifest，"
                      "proposals.json 尚未实现。"),
        ]
    )


def main():
    utf8_stdout()
    ensure_dirs()
    collect = import_collect()

    # Read the live file BEFORE overwriting it: collect.py's run results are
    # stronger evidence than any probe and must survive this rebuild.
    live = load_json(SOURCES_DST)
    registry = load_json(REGISTRY_SRC)
    has_reg = isinstance(registry, dict)
    reg_status = ("loaded: %s (generatedAt=%s, %d probed channels)"
                  % (REGISTRY_SRC, (registry.get("meta") or {}).get("generatedAt"),
                     len(registry.get("channels") or []))) if has_reg else (
                  "absent: %s" % REGISTRY_SRC)

    categories, reg_cat_extras = build_categories(collect, registry)
    channels, unmapped, preserved = build_channels(collect, registry, live)
    manual = build_manual_channels(collect)
    generated_at = now_iso()

    def from_reg(key, fallback):
        if has_reg and registry.get(key):
            return registry[key]
        return fallback

    doc = OrderedDict(
        [
            ("generatedAt", generated_at),
            ("collectorVersion", collect.COLLECTOR_VERSION),
            ("categories", categories),
            ("channels", channels),
            ("manualChannels", manual),
            ("scoring", from_reg("scoring", default_scoring(collect))),
            ("dedupe", from_reg("dedupe", default_dedupe(collect))),
            ("reliability", from_reg("reliability", default_reliability(collect))),
            ("logging", from_reg("logging", default_logging(collect))),
            ("legitimacy", from_reg("legitimacy", default_legitimacy(collect))),
            ("evolution", from_reg("evolution", default_evolution(collect))),
            ("tiers", from_reg("tiers", {})),
            ("schemas", from_reg("schemas", {})),
            ("summarization", from_reg("summarization", {})),
            ("registryMeta", (registry.get("meta") if has_reg else None)),
            ("lastRunAt", (live or {}).get("lastRunAt")),
            ("notes", "本文件由 scripts/build_sources_json.py 生成，生成过程未发起任何网络请求。"
                      "status 一律来自真实观测：优先本机 collect.py 的实采结果，其次是 "
                      "research/source_registry.json 的实测探针；两者都没有时才是 \"unknown\"。"
                      "每个渠道的 statusSource 字段记录了该状态的具体出处。"),
            ("build", OrderedDict([
                ("builtAt", generated_at),
                ("builder", "scripts/build_sources_json.py"),
                ("registrySource", reg_status),
                ("categoriesIn", len(categories)),
                ("channelsIn", len(channels)),
                ("liveObservationsPreserved", preserved),
                ("registryChannelIndex", sorted(unmapped)),
                ("registryTaxonomyExtras", sorted(reg_cat_extras)),
                ("assumptions", [
                    "分类字段优先来自 research/source_registry.json 的 taxonomy（按 "
                    "REGISTRY_TAXONOMY_ALIASES 逐条对应），缺失处回退 scripts/collect.py 的 DEFAULT_CATEGORIES。",
                    "updateCadence 统一写实际调度值「每日 14:00 (Asia/Shanghai)」（collect.py 与 registry "
                    "tiers.schedule 一致）；registry 原始值保留在 registryUpdateCadence。",
                    "channels 的 id 空间沿用 collect.py / 前端 CHANNELS（arxiv、gh_trending…），"
                    "registry 里更细粒度的端点 id 通过 REGISTRY_CHANNEL_ALIASES 映射；"
                    "registryChannelIndex 列出未被映射的 registry 渠道。",
                    "status 优先级：本机实采结果 > registry 探针 > unknown。registry 探针只在 "
                    "httpStatus==200 且非 off-limits/unreachable 时记为 ok，其余记为 error。",
                    "gh_trending 是本文件与 collect.py 使用的 id；前端 core.part.js 的 CHANNELS 常量里"
                    "同一渠道叫 github_trend。",
                    "rateLimit 优先采用 registry 实测文本，缺失时才用自设节流策略。",
                ]),
            ])),
        ]
    )

    size = write_json(SOURCES_DST, doc)
    tax = OrderedDict([
        ("generatedAt", generated_at),
        ("source", "sources.json"),
        ("categories", categories),
    ])
    tax_size = write_json(TAXONOMY_DST, tax)

    print("[ok] wrote %s (%d bytes)" % (SOURCES_DST, size))
    print("[ok] wrote %s (%d bytes)" % (TAXONOMY_DST, tax_size))
    print("     registry: %s" % reg_status)
    print("     categories=%d channels=%d manualChannels=%d"
          % (len(categories), len(channels), len(manual)))
    print("     live statuses preserved from previous sources.json: %s" % (preserved or "none"))
    missing = [c for c in REQUIRED_CHANNEL_IDS if c not in {x["id"] for x in channels}]
    print("     required channels missing: %s" % (missing or "none"))
    from collections import Counter
    print("     statuses: %s" % dict(Counter(c["status"] for c in channels)))
    print("     channels without a collect.py collector: %s"
          % ", ".join(c["id"] for c in channels if not c["collectorImplemented"]))
    print("     registry channels not mapped: %d" % len(unmapped))
    print("     registry taxonomy entries not merged: %s" % sorted(reg_cat_extras))
    return 0


if __name__ == "__main__":
    sys.exit(main())
