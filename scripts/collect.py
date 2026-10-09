#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Future 求职学习工作台 — 每日联网调研采集器（确定性层）
================================================================================
Why this file exists
  A daily workbench needs a *boring*, dependable half: something that runs at
  18:00 Asia/Shanghai, hits public endpoints, normalizes, de-duplicates, scores
  and stores — with no LLM in the loop, no third-party packages, and no single
  channel able to break the run. The creative half (summarising, formula
  breakdowns, concept explanations) is a separate, optional Agent pass driven by
  scripts/daily-agent.md.

Pipeline
  load config -> fan out over channels (thread pool, per-channel timeout+retry)
  -> normalize -> classify -> score -> dedupe (id / canonical url / title / simhash)
  -> merge into state -> atomically write digest + index + manifest + logs

Reliability rules (why the code looks the way it does)
  * A dead endpoint must not mean a dead channel. Every fixed channel tries its
    primary URL first and then the verified alternatives in `FALLBACKS`, in
    order, and logs which source actually served the data. `CHANNEL_SPECS[..]
    ["backup"]` mirrors those ids so the run log and web/data/sources.json tell
    the reader that a channel has a second home.
  * A channel that is CONFIRMED impossible (bot challenge, login wall, retired
    API, robots.txt) is listed in `DISABLED_CHANNELS` together with the evidence
    that killed it. The runner then records `status: "blocked"` plus a
    `riskNote` instead of re-hammering the host on every run. The collector
    function stays in place, so re-enabling is a one-line change; `--only id`
    still runs a blocked channel on purpose, for re-testing.
  * `parse_error` is deliberately a different status from `empty`: "the host
    answered and we could not read it" is a bug on our side, "the host answered
    with nothing" is not. Neither can abort the run.

What it deliberately does NOT do
  * No scraping of login-walled sites (Xiaohongshu, BOSS Zhipin, Lagou,
    Shixiseng). Those are handled by a human export -> import flow; see
    `manualChannels` in web/data/sources.json and the `inbox` channel.
  * No ignoring robots.txt. Reddit sits in DISABLED_CHANNELS purely because
    https://www.reddit.com/robots.txt answers `User-agent: * / Disallow: /` —
    even though its .rss feed is technically reachable.
  * No fabrication. Summaries come only from the source payload
    (title / abstract / README / description). If there is no source URL the
    item is dropped.

Usage
  python scripts/collect.py                  # full run, writes web/data
  python scripts/collect.py --only arxiv,hn  # subset, for debugging
  python scripts/collect.py --limit 20       # cap per channel
  python scripts/collect.py --dry-run        # print only, write nothing
  python scripts/collect.py --probe          # reachability table only, writes nothing
  python scripts/collect.py --init-config    # write a config template
  python scripts/collect.py -v               # per-item trace

Outputs (all under web/data, all UTF-8 without BOM)
  digest/YYYY-MM-DD.json   digest/today.json   items/index.json   items.json
  manifest.json            logs/runs.json      sources.json       state/collector-state.json
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import hashlib
import html
import json
import os
import random
import re
import socket
import ssl
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

COLLECTOR_VERSION = "1.1.0"
CST = timezone(timedelta(hours=8))          # Asia/Shanghai has no DST
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 FutureWorkbench/1.0 "
      "(+personal academic research; contact: local)")

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "collector.config.json"
DATA_DIR = ROOT / "web" / "data"

# ---------------------------------------------------------------------------
# Shared knowledge-quality judgement.
#
# WHY a separate module: "is this worth keeping / worth a deep read?" used to be
# answered by three different rule sets (here, plan_deep_read.py, prune_items.py)
# with different outcomes for the same card. knowledge_quality.py is now the one
# authority for kind / materiality / direction-fit / noise, so collection,
# planning, pruning and self-check can no longer disagree.
#
# Guarded on purpose: the collector is the layer that MUST work, so a problem in
# the judgement module degrades to the old behaviour instead of breaking a run.
# ---------------------------------------------------------------------------
try:
    if str(Path(__file__).resolve().parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    import knowledge_quality as KQ
    KQ_POLICY = KQ.load_policy()
except Exception as _kq_err:                      # pragma: no cover
    KQ = None
    KQ_POLICY = {}
    print(f"[warn] knowledge_quality unavailable ({_kq_err}); "
          f"falling back to keyword-only scoring", file=sys.stderr)
LOGS_DIR = DATA_DIR / "logs"
DIGEST_DIR = DATA_DIR / "digest"
INDEX_DIR = DATA_DIR / "items"
STATE_PATH = DATA_DIR / "state" / "collector-state.json"
RUNS_PATH = LOGS_DIR / "runs.json"


def now_cst() -> datetime:
    return datetime.now(CST)


def iso(dt: datetime) -> str:
    return dt.astimezone(CST).isoformat(timespec="seconds")


def date_key(dt: datetime) -> str:
    return dt.astimezone(CST).strftime("%Y-%m-%d")


# ============================================================================
# 1. TAXONOMY — mirrors the front-end CATEGORIES; keywords are tunable in config
# ============================================================================
DEFAULT_CATEGORIES = {
    # `unclassified` is the bucket classify() returns when NOTHING matched. It is a
    # first-class category here (weight 0, no keywords) so that:
    #   · taxonomy.json describes it, and selfcheck stops flagging 85 items as
    #     "using a category not in taxonomy.json" - noise that hid real warnings;
    #   · it can be filtered and counted on purpose.
    # It has no keywords by design: adding any would defeat its purpose.
    "unclassified": {
        "zh": "未分类", "en": "Unclassified", "weight": 0.0,
        "desc": "没有命中任何分类关键词的条目。堆在这里通常意味着关键词需要调整。",
        "goal": "保持接近零；持续增长说明关键词覆盖不足或出现了新方向。",
        "keywords": [], "arxiv": []},
    "multimodal": {
        "zh": "多模态算法", "en": "Multimodal", "weight": 1.00,
        "desc": "视觉-语言对齐、VLM 架构、跨模态检索与生成、多模态评测。",
        "goal": "每日捕获多模态大模型的新架构、对齐方法与评测基准进展。",
        "keywords": ["multimodal", "multi-modal", "vision-language", "vlm", "mllm", "lvlm",
                     "clip", "blip", "llava", "qwen-vl", "internvl", "video-llm", "image-text",
                     "visual instruction", "cross-modal", "audio-visual", "omni-modal",
                     "segment anything", "visual tokenizer", "多模态", "视觉语言", "图文"],
        "arxiv": ["cs.CV", "cs.CL", "cs.MM"]},
    "posttraining": {
        "zh": "后训练", "en": "Post-training", "weight": 1.00,
        "desc": "SFT、RLHF、DPO/GRPO、RLVR、拒绝采样、蒸馏与偏好优化。",
        "goal": "跟踪后训练算法迭代与工程 trick，沉淀可复现的配方。",
        "keywords": ["post-training", "post training", "sft", "instruction tuning", "rlhf",
                     "dpo", "ipo", "kto", "orpo", "grpo", "rlvr", "reward model",
                     "preference optimization", "rejection sampling", "distillation",
                     "self-play", "verifier", "process reward", "reasoning model",
                     "后训练", "指令微调", "偏好优化", "蒸馏"],
        "arxiv": ["cs.CL", "cs.LG", "cs.AI"]},
    "worldmodel": {
        "zh": "世界模型", "en": "World Model", "weight": 0.95,
        "desc": "基于模型的强化学习、视频世界模型、VLA、3DGS/NeRF 场景表示。",
        "goal": "跟踪世界模型与具身智能的建模与评测路线。",
        "keywords": ["world model", "world-model", "model-based rl", "dreamer", "genie",
                     "vla", "vision-language-action", "embodied", "robot learning", "sim2real",
                     "3d gaussian", "gaussian splatting", "nerf", "neural radiance",
                     "interactive environment", "latent dynamics", "world simulator",
                     "世界模型", "具身", "机器人"],
        "arxiv": ["cs.LG", "cs.RO", "cs.CV", "cs.AI"]},
    "generative": {
        "zh": "生成式模型", "en": "Generative", "weight": 0.95,
        "desc": "Diffusion、Flow Matching、自回归生成、视频/3D 生成。",
        "goal": "掌握生成建模范式的原理演进与采样加速技术。",
        "keywords": ["diffusion", "flow matching", "rectified flow", "consistency model",
                     "ddpm", "ddim", "text-to-image", "text-to-video", "video generation",
                     "image generation", "autoregressive generation", "3d generation",
                     "dit", "adaln", "生成式", "扩散模型", "视频生成"],
        "arxiv": ["cs.CV", "cs.LG"]},
    "rl": {
        "zh": "强化学习", "en": "Reinforcement Learning", "weight": 0.85,
        "desc": "PPO/GAE、GRPO、离线 RL、探索与信用分配。",
        "goal": "打牢 RL 数学基础，并连接到 LLM 后训练实践。",
        "keywords": ["reinforcement learning", "ppo", "gae", "actor-critic", "q-learning",
                     "offline rl", "exploration", "credit assignment", "mcts", "bandit",
                     "policy gradient", "强化学习", "策略梯度"],
        "arxiv": ["cs.LG", "cs.AI"]},
    "agent": {
        "zh": "Agent 理论与实践", "en": "Agents", "weight": 0.90,
        "desc": "工具调用、规划、记忆、多智能体协作、Agent 评测与安全。",
        "goal": "理解 Agent 系统设计模式并动手实现最小可用体。",
        "keywords": ["agent", "agentic", "tool use", "tool calling", "function calling",
                     "multi-agent", "planning", "memory", "react", "reflexion", "workflow",
                     "computer use", "browser agent", "agent benchmark", "mcp",
                     "agent 框架", "智能体"],
        "arxiv": ["cs.AI", "cs.CL", "cs.SE"]},
    "engineering": {
        "zh": "工程与系统", "en": "Engineering", "weight": 0.70,
        "desc": "分布式训练、显存优化、推理加速、量化、CUDA 与并行策略。",
        "goal": "把算法想法落到可训练、可推理的工程实现上。",
        "keywords": ["inference", "serving", "vllm", "sglang", "quantization", "kv cache",
                     "flash attention", "distributed training", "fsdp", "deepspeed",
                     "megatron", "cuda", "tensorrt", "throughput", "latency",
                     "推理加速", "分布式训练", "显存"],
        "arxiv": ["cs.DC", "cs.LG"]},
    "foundation": {
        "zh": "基础理论", "en": "Foundations", "weight": 0.60,
        "desc": "线性代数、概率统计、优化、Transformer 与深度学习原理。",
        "goal": "补齐面试八股背后的第一性原理。",
        "keywords": ["transformer", "attention", "position encoding", "rope", "alibi",
                     "normalization", "rmsnorm", "layernorm", "optimizer", "scaling law",
                     "generalization", "theory", "architecture", "基础", "理论", "缩放定律"],
        "arxiv": ["cs.LG", "stat.ML"]},
    "job": {
        "zh": "岗位与招聘", "en": "Jobs & Hiring", "weight": 0.62,
        "desc": "实时招聘信息、岗位 JD、面试流程、薪资带宽与投递节奏。",
        "goal": "每日刷新在招岗位与投递窗口，不漏机会。",
        "keywords": ["招聘", "实习", "算法工程师", "校招", "社招", "jd", "intern",
                     "internship", "hiring", "recruit", "opening", "career", "岗位"],
        "arxiv": []},
    "coding": {
        "zh": "面试手撕题", "en": "Coding Interviews", "weight": 0.95,
        "desc": "手写注意力、损失函数、采样、经典算法与数据结构。",
        "goal": "形成高频手撕题的肌肉记忆与讲解话术。",
        "keywords": ["leetcode", "手撕", "面经", "算法题", "cracking", "interview question",
                     "system design", "coding interview", "八股", "笔试"],
        "arxiv": []},
    "exam": {
        "zh": "笔试场景题", "en": "Written Exams", "weight": 0.75,
        "desc": "概率题、场景设计题、工程权衡题、选择题考点。",
        "goal": "覆盖笔试与面试中的开放场景题。",
        "keywords": ["笔试", "场景题", "概率题", "选择题", "written test", "oa", "quiz"],
        "arxiv": []},
    "paper": {
        "zh": "论文与前沿", "en": "Papers", "weight": 0.90,
        "desc": "arXiv 新论文、CCF-A 顶会论文、技术报告与综述。",
        "goal": "按方向过滤高相关新论文并给出可读摘要。",
        # 刻意**不含** arxiv / benchmark / state-of-the-art：
        #   · "arxiv" 是采集器自己写进 tags 的**元数据**，不是内容词 —— 它让每一篇
        #     arXiv 论文都自动落进这个分类，等于把「论文」变成无法被方向过滤的兜底桶；
        #   · "benchmark" / "state-of-the-art" 太泛，任何 ML 论文的摘要里都有。
        # 实测：去掉这三个词后只有 11 条变动，其中 9 条本来就该是 unclassified
        # （它们此前是"靠元数据混进来的"）。真正方向内的论文仍靠各自方向的关键词
        # 与 arXiv 学科标签（cs.CV / cs.CL / cs.LG）分类。
        "keywords": ["paper", "preprint", "survey", "论文", "综述", "顶会"],
        "arxiv": ["cs.CV", "cs.CL", "cs.LG"]},
    "course": {
        "zh": "课程与仓库", "en": "Courses & Repos", "weight": 0.70,
        "desc": "系统课程、开源仓库、教程与学习资源。",
        "goal": "维护固定仓库与课程的进度更新。",
        "keywords": ["tutorial", "course", "awesome", "handbook", "cookbook", "guide",
                     "implementation", "from scratch", "教程", "课程", "仓库"],
        "arxiv": []},
    "trend": {
        "zh": "技术演进与趋势", "en": "Trends", "weight": 0.65,
        "desc": "技术路线演进、行业讨论、社区热点与方法论。",
        "goal": "把零散信息串成可讲述的技术演进叙事。",
        "keywords": ["roadmap", "trend", "state of", "review", "opinion", "discussion",
                     "趋势", "演进", "复盘", "讨论"],
        "arxiv": []},
}

# ============================================================================
# 2. CHANNEL REGISTRY — tier drives scoring weight and run priority
# ============================================================================
CHANNEL_SPECS = {
    "arxiv":          {"tier": "P0", "mode": "api",    "timeout": 30, "retries": 2, "backup": []},
    "hf_papers":      {"tier": "P0", "mode": "api",    "timeout": 30, "retries": 2, "backup": ["hf_blog_rss"]},
    "hf_models":      {"tier": "P1", "mode": "api",    "timeout": 25, "retries": 1, "backup": []},
    "github":         {"tier": "P0", "mode": "api",    "timeout": 30, "retries": 2, "backup": ["gh_trending"]},
    "gh_trending":    {"tier": "P1", "mode": "html",   "timeout": 25, "retries": 1, "backup": ["github_rest_search"]},
    "openreview":     {"tier": "P0", "mode": "api",    "timeout": 30, "retries": 2, "backup": ["s2"]},
    "s2":             {"tier": "P1", "mode": "api",    "timeout": 30, "retries": 1, "backup": ["openalex", "crossref"]},
    "hn":             {"tier": "P1", "mode": "api",    "timeout": 25, "retries": 2, "backup": []},
    "reddit":         {"tier": "P2", "mode": "rss",    "timeout": 25, "retries": 1, "backup": []},
    "hf_blog_rss":    {"tier": "P2", "mode": "rss",    "timeout": 25, "retries": 1, "backup": []},
    "openai_rss":     {"tier": "P2", "mode": "rss",    "timeout": 25, "retries": 1, "backup": []},
    "machineheart":   {"tier": "P1", "mode": "rss",    "timeout": 20, "retries": 1, "backup": ["leiphone"]},
    "leiphone":       {"tier": "P1", "mode": "rss",    "timeout": 25, "retries": 1, "backup": ["qbitai"]},
    "qbitai":         {"tier": "P1", "mode": "rss",    "timeout": 20, "retries": 1, "backup": ["leiphone"]},
    "rsshub":         {"tier": "P2", "mode": "rss",    "timeout": 25, "retries": 1, "backup": ["zhihu"]},
    # --- 算法知识库（非"最新"驱动；整理的是可复用题解/八股，见 COLLECTORS 上方注释）---
    # `knowledgeBase: True` gives them a scoring component independent of publish
    # date and lets the ingest path keep pages whose value does not decay.
    "programmercarl":  {"tier": "P0", "mode": "html",  "timeout": 30, "retries": 2,
                        "backup": [], "knowledgeBase": True},
    "kamacoder_notes": {"tier": "P0", "mode": "html",  "timeout": 30, "retries": 2,
                        "backup": [], "knowledgeBase": True},
    "gh_algokb":       {"tier": "P1", "mode": "api",   "timeout": 30, "retries": 2,
                        "backup": [], "knowledgeBase": True},
    "xiaolincoding":   {"tier": "P0", "mode": "html",  "timeout": 30, "retries": 2,
                        "backup": [], "knowledgeBase": True},
    # CodeTop: 大厂真实高频题的频度统计。metadata-only，见 collect_codetop 的说明。
    "codetop":         {"tier": "P0", "mode": "api",   "timeout": 30, "retries": 2,
                        "backup": [], "knowledgeBase": True},
    # nowcoder: DISABLED (2026-10-03).
    #
    # Measured over two runs: the public /discuss list yields almost no material for
    # this workbench. Of 72 items, 45 were removed by the knowledge-quality pass -
    # Java/backend/embedded/banking interview write-ups, 秋招 vent posts, referral
    # ads and unrelated chatter - and of the 27 that survived, every one was a
    # general-role post rather than an algorithm/hand-writing problem. The specific
    # 面经 that matter need a logged-in session, which this project does not use
    # (see docs/登录类渠道操作手册.md). Its useful role is now filled by the
    # first-party knowledge bases above, which publish the same kind of material
    # openly and are allowed by robots.txt.
    # Re-enable per run for re-testing: python scripts/collect.py --only nowcoder
    "nowcoder":       {"tier": "P2", "mode": "html",   "timeout": 25, "retries": 1,
                       "backup": [], "disabled": True},
    # zhihu: DISABLED.
    #
    # The only reachable feed is a general hot list (mirror rss.injahow.cn), and a
    # general hot list has nothing to do with algorithm internships. Audit of 41
    # ingested items: film reviews, a phone review, a fraud news story and an
    # entertainment question were keyword-classified into posttraining / rl /
    # foundation, i.e. it was actively polluting the technical categories.
    # The targeted alternative is `nowcoder` (面经/招聘) plus the official blogs.
    # To fetch specific Zhihu questions instead, ingest their URLs by hand into
    # web/data/inbox/ - that keeps the signal and drops the firehose.
    "zhihu":          {"tier": "P2", "mode": "rss",    "timeout": 25, "retries": 1,
                       "backup": [], "disabled": True},
    # Human-in-the-loop import for login-walled channels.
    #
    # Disabled by default on purpose: login-channel collection is paused for now
    # (the reader will provide exports later). This channel never touches the
    # network either way - it only reads LOCAL files from web/data/inbox/ - but
    # keeping it off means a daily run does not imply any login-channel work is
    # happening, which is the honest default.
    # Re-enable per run:  python scripts/collect.py --only inbox
    # Re-enable permanently: "enableInbox": true in config/collector.config.json
    "inbox":          {"tier": "P0", "mode": "local",  "timeout": 5,  "retries": 0,
                       "backup": [], "disabled": True},
    "jobs_bytedance": {"tier": "P0", "mode": "api",    "timeout": 30, "retries": 2, "backup": []},
    "jobs_tencent":   {"tier": "P0", "mode": "api",    "timeout": 30, "retries": 2, "backup": []},
    "jobs_alibaba":   {"tier": "P1", "mode": "api",    "timeout": 30, "retries": 1, "backup": []},
    "jobs_zhipu":     {"tier": "P2", "mode": "html",   "timeout": 25, "retries": 1, "backup": []},
    "jobs_moonshot":  {"tier": "P2", "mode": "html",   "timeout": 25, "retries": 1, "backup": []},
    "jobs_deepseek":  {"tier": "P2", "mode": "html",   "timeout": 25, "retries": 1, "backup": ["moka_high_flyer"]},
    "jobs_minimax":   {"tier": "P2", "mode": "html",   "timeout": 25, "retries": 1, "backup": []},
    "jobs_shailab":   {"tier": "P2", "mode": "html",   "timeout": 25, "retries": 1, "backup": []},
    # login-walled: never scraped automatically
    "xiaohongshu":    {"tier": "P2", "mode": "manual", "timeout": 0,  "retries": 0, "backup": [], "auth": True},
    "boss":           {"tier": "P1", "mode": "manual", "timeout": 0,  "retries": 0, "backup": [], "auth": True},
    "lagou":          {"tier": "P2", "mode": "manual", "timeout": 0,  "retries": 0, "backup": [], "auth": True},
    "shixiseng":      {"tier": "P2", "mode": "manual", "timeout": 0,  "retries": 0, "backup": [], "auth": True},
}

# Channels that are CONFIRMED impossible from a script. Every reason below was
# observed with a real request (see research/channel_probe.json and
# scripts/probe-channels.py). The runner records them as `status: "blocked"`
# with the matching `riskNote` and does NOT spend a request on them; the
# collector functions are kept so re-enabling is one line. `--only <id>` still
# runs a disabled channel on purpose, because re-testing is how we notice that
# an upstream situation changed.
DISABLED_CHANNELS = {
    "openreview":
        "Bot challenge: api2 AND api1 /notes both answer 200 text/html "
        "'Verifying your browser | OpenReview' (earlier runs saw 403 "
        "ChallengeRequiredError). Only a browser can pass it; arXiv + s2 cover papers.",
    "reddit":
        "robots.txt: https://www.reddit.com/robots.txt is 'User-agent: * / Disallow: /', "
        "so we do not scrape it even though <sub>/top/.rss answers 200. No substitute "
        "either: lobste.rs has the same blanket Disallow. HN already covers the signal.",
    "machineheart":
        "Feed retired: /rss and /feed both answer 200 text/html (机器之心·数据服务 landing "
        "page) instead of RSS, /rss/articles is 404, and the only reachable RSSHub mirror "
        "404s on /jiqizhixin/daily. Replaced by the `leiphone` channel (雷锋网 AI feed).",
    "rsshub":
        "Every public instance is down or blocking: rsshub.app 403 Cloudflare challenge, "
        "rsshub.rssforever.com 503, rsshub.ktachibana.party 404/503, rsshub.pseudoyu.com TLS "
        "error; the single reachable mirror (rss.injahow.cn) serves only /zhihu/hotlist and "
        "/solidot, and the zhihu route is already consumed by the fixed `zhihu` channel.",
    "jobs_bytedance":
        "Edge/WAF blocks scripted clients: GET /api/v1/search/job/posts answers 200 with the "
        "HTML page 字节跳动猎头平台, POST with the documented JSON body answers 405 (0 bytes), "
        "POST with a trailing slash answers 307, /referral/api/... is 404. The JS bundle "
        "confirms the path is right, so this is the edge, not our request. Needs a browser.",
    "jobs_alibaba":
        "Anti-bot gated: the real API is POST https://talent.alibaba.com/position/search "
        "(GET -> 405, POST without CSRF -> 403). With the page's own XSRF-TOKEN replayed as "
        "?_csrf= it answers 200 but {\"success\":true,\"datas\":null,\"totalCount\":0} for "
        "every payload shape, and /searchCondition/list returns searchItems=null: the backend "
        "wants a token only the baxia browser script can mint. Needs a browser.",
    "jobs_zhipu":
        "No machine-readable listing: zhipuai.cn/joinus (200, 783KB) server-renders job "
        "*categories* (算法/校招 labels) but no per-job data, exposes no ATS host, and none of "
        "its 15 Next.js chunks reference a job API. Needs a browser or a human import.",
    "jobs_moonshot":
        "No machine-readable listing: www.moonshot.cn/careers (200, 95KB) contains zero job "
        "keywords and now delegates to careers.kimi.com, which is an 11.6KB JS shell with no "
        "embedded data (/jobs and /positions are 404) and no job API in its chunks.",
    "jobs_minimax":
        "No machine-readable listing: minimaxi.com/careers embeds a Feishu ATSX portal "
        "(vrfi1sk8a0.jobs.feishu.cn). Its index page carries no job data, its API answers 405 "
        "like ByteDance's (same ATSX edge), and minimaxi.com/robots.txt disallows /api/. "
        "Needs a browser or a human import.",
    "jobs_shailab":
        "No machine-readable listing: /joinus, /joinus/social and /joinus/campus return the "
        "same 70KB marketing page with no job rows; the openings are fetched by JS and no "
        "ATS/API endpoint is referenced. Needs a browser or a human import.",
}

CHANNEL_NAMES = {
    "arxiv": "arXiv 论文", "hf_papers": "HF 每日论文", "hf_models": "HF 模型",
    "github": "GitHub 搜索", "gh_trending": "GitHub 趋势", "openreview": "OpenReview",
    "s2": "Semantic Scholar", "hn": "Hacker News", "reddit": "Reddit",
    "machineheart": "机器之心", "qbitai": "量子位", "leiphone": "雷锋网 AI", "hf_blog_rss": "HF Blog",
    "openai_rss": "OpenAI News", "rsshub": "RSSHub", "nowcoder": "牛客网（已停用）",
    "zhihu": "知乎热榜（已停用）",
    "programmercarl": "代码随想录", "kamacoder_notes": "卡码笔记", "gh_algokb": "算法题解仓库",
    "xiaolincoding": "小林coding", "codetop": "CodeTop 大厂高频题",
    "jobs_bytedance": "字节招聘", "jobs_tencent": "腾讯招聘", "jobs_alibaba": "阿里招聘",
    "jobs_zhipu": "智谱招聘", "jobs_moonshot": "月之暗面", "jobs_deepseek": "DeepSeek",
    "jobs_minimax": "MiniMax", "jobs_shailab": "上海 AI Lab",
    "inbox": "人工导入",
    "xiaohongshu": "小红书", "boss": "BOSS直聘", "lagou": "拉勾", "shixiseng": "实习僧",
}

MANUAL_ONLY = {cid for cid, s in CHANNEL_SPECS.items() if s.get("auth") or s["mode"] == "manual"}

# Hosts we expect to see in the knowledge base. Anything else is not rejected
# (a legitimate new source may appear) but is reported in the daily proposals
# file so a mis-parsed page cannot silently pollute the corpus unnoticed.
# Mirrors the list in scripts/selfcheck.py on purpose: the collector proposes,
# the self-check verifies, and a human decides.
KNOWN_HOSTS = {
    "arxiv.org", "export.arxiv.org", "huggingface.co", "github.com", "githubusercontent.com",
    "api.github.com", "openreview.net", "api2.openreview.net", "semanticscholar.org",
    "api.semanticscholar.org", "openalex.org", "api.openalex.org", "crossref.org",
    "doi.org", "news.ycombinator.com", "reddit.com", "jiqizhixin.com", "qbitai.com",
    "leiphone.com", "infoq.cn", "openai.com", "deepmind.google", "blog.google",
    "microsoft.com", "nvidia.com", "anthropic.com", "rsshub.app", "rss.injahow.cn",
    "nowcoder.com", "zhihu.com", "v2ex.com", "aclanthology.org", "paperswithcode.com",
    "papers.cool", "alphaxiv.org", "leetcode.cn", "leetcode.com", "codeforces.com",
    "jobs.bytedance.com", "careers.tencent.com", "talent.alibaba.com", "zhipuai.cn",
    "moonshot.cn", "kimi.com", "deepseek.com", "talent.deepseek.com", "minimaxi.com",
    "shlab.org.cn", "sensetime.com", "youtube.com", "bilibili.com", "twitter.com", "x.com",
    # Algorithm knowledge bases (first-party sites of the 公众号 authors).
    "programmercarl.com", "notes.kamacoder.com", "kamacoder.com", "codefun2000.com",
    "xiaolincoding.com", "codetop.cc", "leetcode.cn",
}

DEFAULT_CONFIG = {
    "collectorVersion": COLLECTOR_VERSION,
    "targetDate": "2027-04-01",
    "targetLabel": "目标投递窗口（2027 届春招）",
    "interests": {"multimodal": 1.0, "posttraining": 1.0, "worldmodel": 0.95,
                  "generative": 0.9, "rl": 0.8, "agent": 0.85},
    "http": {"userAgent": UA, "defaultTimeout": 25, "maxRetries": 2,
             "backoffBase": 1.6, "jitter": 0.35, "delayBetween": 0.4},
    "limits": {"perChannel": 30, "maxNewPerRun": 400},
    "scoring": {"freshnessHalfLifeDays": 7.0,
                "sourceTierWeight": {"P0": 1.0, "P1": 0.85, "P2": 0.7},
                "qualityBoost": 8.0, "minRelevance": 12.0},
    "dedupe": {"simhashBits": 64, "hammingThreshold": 3},
    "arxiv": {"queryTerms": [], "maxPerQuery": 25, "lookbackDays": 10},
    "github": {"queries": [], "minStars": 40, "lookbackDays": 30},
    "categories": {},
    "retention": {"archiveAfterDays": 90, "keepDayFiles": 400},
}


# ============================================================================
# 3. UTILITIES
# ============================================================================
def safe_print(text: str = "") -> None:
    """Print without ever raising UnicodeEncodeError.

    WHY: the collector prints Chinese channel names and item titles, and a
    Windows console is still often GBK. A crashing `print` in the --dry-run /
    --probe path would turn a successful run into exit code 1.
    """
    try:
        print(text, flush=True)
    except UnicodeEncodeError:                           # pragma: no cover - legacy consoles
        enc = sys.stdout.encoding or "ascii"
        try:
            sys.stdout.write(str(text).encode(enc, "replace").decode(enc, "replace") + "\n")
            sys.stdout.flush()
        except Exception:
            pass


class Logger:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.lines: list = []

    def __call__(self, msg: str, level: str = "info") -> None:
        prefix = {"info": "  ", "ok": "[ok] ", "warn": "[!] ", "err": "[x] ", "step": "== "}.get(level, "  ")
        line = f"[{now_cst().strftime('%H:%M:%S')}] {prefix}{msg}"
        self.lines.append(line)
        try:
            print(line, flush=True)
        except UnicodeEncodeError:                       # pragma: no cover - legacy consoles
            print(line.encode("utf-8", "replace").decode("ascii", "replace"), flush=True)

    def detail(self, msg: str) -> None:
        if self.verbose:
            self("  " + msg)


def js_literal_decode(lit: str) -> str:
    """Decode the body of a JS single-quoted string literal into real text.

    WHY: talent.deepseek.com inlines its job catalogue as
    `JSON.parse('{"crawledAt":...}')`; the literal uses \\' and \\" escapes that
    json.loads() cannot read on its own.
    """
    simple = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f",
              "'": "'", '"': '"', "\\": "\\", "/": "/"}
    out, i = [], 0
    while i < len(lit):
        c = lit[i]
        if c == "\\" and i + 1 < len(lit):
            nxt = lit[i + 1]
            if nxt == "u":
                out.append(lit[i:i + 6])
                i += 6
                continue
            out.append(simple.get(nxt, nxt))
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def first_of(row: dict, keys, default=""):
    """First non-empty value among `keys` — how one normalizer serves many APIs.

    WHY: Tencent returns RecruitPostName/PostURL while ByteDance returns
    title/url. Looking up a fixed key list is what silently turned a working
    Tencent feed into an 'empty' channel before.
    """
    for k in keys:
        val = (row or {}).get(k)
        if val not in (None, "", [], {}):
            return val
    return default


def http_get(url, *, timeout=25, headers=None, accept=None, cfg=None, log=None,
             retries=2, data=None, method="GET"):
    """HTTP with exponential backoff + jitter. Returns (status, bytes, content_type)."""
    cfg = cfg or {}
    http_cfg = cfg.get("http") or DEFAULT_CONFIG["http"]
    hdrs = {
        "User-Agent": http_cfg.get("userAgent", UA),
        "Accept": accept or "application/json, text/html;q=0.9, application/xml;q=0.8, */*;q=0.7",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
    }
    if headers:
        hdrs.update(headers)

    ctx = ssl.create_default_context()
    last_err = None
    for attempt in range(max(1, retries + 1)):
        try:
            req = urllib.request.Request(url, headers=hdrs, data=data, method=method)
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                body = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    body = gzip.decompress(body)
                return resp.status, body, resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (403, 408, 425, 429, 500, 502, 503, 504) and attempt < retries:
                pass
            else:
                raise
        except (urllib.error.URLError, socket.timeout, ssl.SSLError, ConnectionError, OSError) as e:
            last_err = e
            if attempt >= retries:
                break
        base = float(http_cfg.get("backoffBase", 1.6))
        jitter = float(http_cfg.get("jitter", 0.35))
        delay = (base ** attempt) + random.uniform(0, jitter * (base ** attempt))
        if log:
            log(f"retry {attempt + 1}/{retries} in {delay:.1f}s ({type(last_err).__name__})", "warn")
        time.sleep(delay)
    raise last_err if last_err else RuntimeError("request failed")


def http_json(url, **kw):
    _status, body, _ct = http_get(url, **kw)
    return json.loads(body.decode("utf-8", "replace"))


def strip_html(s) -> str:
    if not s:
        return ""
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", str(s))
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def clean_text(s, limit: int = 1200) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", strip_html(s)).strip()[:limit]


def parse_ts(value):
    if value in (None, "", 0, "0"):
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e12:
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(CST)
        except (OverflowError, OSError, ValueError):
            return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"   # Z means UTC, not +20:00
    cn = re.match(r"^(\d{4})年(\d{1,2})月(\d{1,2})日", s)          # 腾讯招聘 LastUpdateTime
    if cn:
        try:
            return datetime(int(cn.group(1)), int(cn.group(2)), int(cn.group(3)), tzinfo=CST)
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(s)
        return dt.astimezone(CST) if dt.tzinfo else dt.replace(tzinfo=CST)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d",
                "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.astimezone(CST) if dt.tzinfo else dt.replace(tzinfo=CST)
        except ValueError:
            continue
    return None


TRACKING_PARAMS = re.compile(
    r"^(utm_|spm|ref$|ref_|from$|source$|share_|share$|scene$|src$|fbclid|gclid|"
    r"mc_cid|mc_eid|_hsenc|_hsmi|yclid|abbucket|ivk_sa|s_r$|share_token|"
    r"loginfrom|_t$|hmsr|hmpl|hmcu|hmkw|hmci|weibo_id|timestamp$)", re.I)


def canonical_url(u: str) -> str:
    if not u:
        return ""
    u = str(u).strip()
    if u.startswith("//"):
        u = "https:" + u
    try:
        parts = urllib.parse.urlsplit(u)
    except ValueError:
        return u
    if not parts.netloc:
        return ""
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=False)
             if not TRACKING_PARAMS.match(k)]
    path = re.sub(r"(arxiv\.org/(?:abs|pdf)/\d{4}\.\d{4,5})v\d+", r"\1", parts.path.rstrip("/") or "/")
    if path.endswith(".pdf"):
        path = path[:-4]
    return urllib.parse.urlunsplit(
        (parts.scheme or "https", parts.netloc.lower().replace("www.", ""), path,
         urllib.parse.urlencode(query), ""))


def norm_title(t: str) -> str:
    if not t:
        return ""
    t = strip_html(t).lower()
    t = re.sub(r"[\s\u3000]+", " ", t)
    return re.sub(r"[^\w\u4e00-\u9fff ]+", "", t).strip()


def sha1(s: str) -> str:
    return hashlib.sha1(str(s).encode("utf-8", "replace")).hexdigest()


def stable_id(source: str, external: str) -> str:
    return sha1(f"{source}::{external}")[:16]


def title_key(t: str) -> str:
    n = norm_title(t)
    return sha1(n)[:16] if n else ""


_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")


def simhash(text: str, bits: int = 64) -> int:
    tokens = _TOKEN_RE.findall((text or "").lower())
    if not tokens:
        return 0
    grams = [" ".join(tokens[i:i + 3]) for i in range(max(1, len(tokens) - 2))]
    vec = [0] * bits
    for g in grams:
        h = int(hashlib.md5(g.encode("utf-8", "replace")).hexdigest(), 16)
        for i in range(bits):
            vec[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i in range(bits):
        if vec[i] > 0:
            out |= (1 << i)
    return out


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


# ============================================================================
# 4. CHANNEL COLLECTORS — each returns a list of raw dicts; raising is allowed
#    (the runner isolates failures per channel).
# ============================================================================
ARXIV_NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def _arxiv_default_terms(cfg):
    """Build OR-queries from the most distinctive english keywords per category."""
    terms = []
    for cid, c in cfg["categories"].items():
        kws = [k for k in c.get("keywords", [])
               if len(k) > 3 and re.match(r"^[a-z0-9][a-z0-9\- ]*$", k)][:3]
        if kws:
            terms.append(" OR ".join(f'all:"{k}"' for k in kws))
    return terms[:6]


def collect_arxiv(cfg, log, limit):
    out = []
    acfg = cfg.get("arxiv", {})
    terms = acfg.get("queryTerms") or _arxiv_default_terms(cfg)
    max_q = int(acfg.get("maxPerQuery") or limit or 25)
    cutoff = now_cst() - timedelta(days=int(acfg.get("lookbackDays", 10)))
    for term in terms:
        url = ("http://export.arxiv.org/api/query?search_query=" +
               urllib.parse.quote(term, safe="") +
               f"&start=0&max_results={max_q}&sortBy=submittedDate&sortOrder=descending")
        try:
            _s, body, _ct = http_get(url, timeout=CHANNEL_SPECS["arxiv"]["timeout"],
                                     retries=CHANNEL_SPECS["arxiv"]["retries"], cfg=cfg, log=log,
                                     accept="application/atom+xml, application/xml;q=0.9, */*;q=0.8")
            root = ET.fromstring(body)
        except Exception as e:
            log(f"arxiv query failed ({term[:40]}): {e}", "warn")
            continue
        got = 0
        for entry in root.findall("a:entry", ARXIV_NS):
            title = clean_text(entry.findtext("a:title", "", ARXIV_NS), 400)
            link = (entry.findtext("a:id", "", ARXIV_NS) or "").strip()
            if not title or not link:
                continue
            published = parse_ts(entry.findtext("a:published", "", ARXIV_NS))
            updated = parse_ts(entry.findtext("a:updated", "", ARXIV_NS))
            if published and published < cutoff:
                continue
            summary = clean_text(entry.findtext("a:summary", "", ARXIV_NS), 1800)
            cats = [c.attrib.get("term", "") for c in entry.findall("a:category", ARXIV_NS)]
            prim = entry.find("arxiv:primary_category", ARXIV_NS)
            primary = prim.attrib.get("term", "") if prim is not None else (cats[0] if cats else "")
            comment = clean_text(entry.findtext("arxiv:comment", "", ARXIV_NS), 240)
            out.append({
                "sourceId": "arxiv", "channel": "arxiv",
                "externalId": link.rsplit("/", 1)[-1],
                "title": title, "summary": summary,
                "url": link.replace("http://", "https://"),
                "publishedAt": iso(published or updated or now_cst()),
                "authors": [clean_text(a.findtext("a:name", "", ARXIV_NS), 60)
                            for a in entry.findall("a:author", ARXIV_NS)][:12],
                "tags": ([primary] if primary else []) + cats[:4],
                "venue": (comment.split(".")[0][:60] if comment else "arXiv"),
                "peerReviewed": False,
                "codeAvailable": bool(re.search(r"github|code|open-?source", summary, re.I)),
                "lang": "en",
            })
            got += 1
        log.detail(f"arxiv '{term[:36]}' -> {got}")
        time.sleep(float((cfg.get("http") or {}).get("delayBetween", 0.4)))
    return out


def collect_hf_papers(cfg, log, limit):
    out = []
    data = http_json("https://huggingface.co/api/daily_papers?limit=%d" % min(max(limit, 10) * 2, 100),
                     cfg=cfg, log=log, retries=2)
    for row in data if isinstance(data, list) else []:
        p = row.get("paper") or row
        title = clean_text(p.get("title", ""), 400)
        if not title:
            continue
        pid = str(p.get("id") or title_key(title))
        up = int(p.get("upvotes") or row.get("upvotes") or 0)
        out.append({
            "sourceId": "hf_papers", "channel": "hf_papers", "externalId": pid,
            "title": title, "summary": clean_text(p.get("summary", ""), 1800),
            "url": f"https://huggingface.co/papers/{pid}",
            "canonicalUrl": (f"https://arxiv.org/abs/{pid}"
                             if re.match(r"^\d{4}\.\d{4,5}$", pid) else None),
            "publishedAt": iso(parse_ts(p.get("publishedAt") or row.get("publishedAt")) or now_cst()),
            "authors": [a.get("name", "") for a in (p.get("authors") or [])][:12],
            "upvotes": up, "qualitySignals": {"upvotes": up}, "lang": "en",
        })
    return out


def collect_hf_models(cfg, log, limit):
    """HuggingFace model releases, with a popularity floor.

    Why the floor: without it this channel was the single largest source of junk
    in the library. A corpus audit found 80 low-value cards from here - random
    community uploads such as `BabyLM-community/babylm-multimodal-baseline-git`
    (score 31) and several duplicate `...-MLX` / `...-NVF` re-uploads of the same
    uncensored model. They are technically "models" but carry no signal about the
    field. A downloads/likes threshold keeps the models people actually use.

    Only models that clear BOTH a download floor and a like floor, or are very
    recent and already popular, are accepted.
    """
    out = []
    qcfg = cfg.get("hfModels") or {}
    min_downloads = int(qcfg.get("minDownloads", 2000))
    min_likes = int(qcfg.get("minLikes", 15))
    dropped = 0

    for term in ["vision-language", "multimodal", "text-to-video", "world-model",
                 "video-generation", "vision-language-action"]:
        url = ("https://huggingface.co/api/models?search=" + urllib.parse.quote(term) +
               "&sort=downloads&direction=-1&limit=%d" % min(max(10, limit), 25) +
               "&full=false&config=false")
        try:
            data = http_json(url, cfg=cfg, log=log, retries=1)
        except Exception as e:
            log(f"hf models '{term}' failed: {e}", "warn")
            continue
        for m in data if isinstance(data, list) else []:
            mid = m.get("modelId") or m.get("id")
            if not mid:
                continue
            dl = int(m.get("downloads") or 0)
            likes = int(m.get("likes") or 0)
            if dl < min_downloads and likes < min_likes:
                dropped += 1
                continue
            out.append({
                "sourceId": "hf_models", "channel": "hf_models", "externalId": mid,
                "title": mid,
                # State the numbers so the reader can judge, and so the relevance
                # scorer has real text to work with instead of a bare identifier.
                "summary": (f"HuggingFace 模型 {mid}：下载 {dl}、点赞 {likes}。"
                            f"搜索词「{term}」。标签：{', '.join((m.get('tags') or [])[:6]) or '无'}。"
                            f"模型页含用法与权重，适合作为复现或微调的起点。"),
                "url": f"https://huggingface.co/{mid}",
                "publishedAt": iso(parse_ts(m.get("lastModified") or m.get("createdAt")) or now_cst()),
                "tags": ((m.get("tags") or [])[:10] + [term]),
                "qualitySignals": {"downloads": dl, "likes": likes},
                "codeAvailable": True,      # a model repo is deployable material
                "lang": "en",
            })
        time.sleep(0.3)
    if dropped:
        log(f"  hf_models: dropped {dropped} models below the popularity floor "
            f"(downloads<{min_downloads} and likes<{min_likes})", "warn")
    return out


def collect_github(cfg, log, limit):
    out = []
    gcfg = cfg.get("github", {})
    queries = gcfg.get("queries") or [
        "multimodal llm", "vision language model", "post-training llm", "rlhf dpo grpo",
        "world model reinforcement learning", "diffusion video generation",
        "llm agent framework", "llm inference engine",
    ]
    min_stars = int(gcfg.get("minStars", 40))
    since = (now_cst() - timedelta(days=int(gcfg.get("lookbackDays", 30)))).strftime("%Y-%m-%d")
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for q in queries[:8]:
        url = ("https://api.github.com/search/repositories?q=" +
               urllib.parse.quote(f"{q} stars:>{min_stars} pushed:>{since}") +
               "&sort=stars&order=desc&per_page=%d" % min(max(5, limit), 20))
        try:
            data = http_json(url, headers=headers, cfg=cfg, log=log,
                             retries=CHANNEL_SPECS["github"]["retries"],
                             timeout=CHANNEL_SPECS["github"]["timeout"])
        except Exception as e:
            log(f"github '{q}' failed: {e}", "warn")
            continue
        for r in (data.get("items") or []) if isinstance(data, dict) else []:
            name = r.get("full_name")
            if not name:
                continue
            desc = clean_text(r.get("description") or "", 600)
            stars = r.get("stargazers_count", 0)
            out.append({
                "sourceId": "github", "channel": "github", "externalId": name,
                "title": f"{name} - {desc}".strip(" -"),
                "summary": desc, "url": r.get("html_url"),
                "publishedAt": iso(parse_ts(r.get("pushed_at") or r.get("created_at")) or now_cst()),
                "authors": [(r.get("owner") or {}).get("login", "")],
                "tags": (r.get("topics") or [])[:8] + ([r.get("language")] if r.get("language") else []),
                "stars": stars,
                "qualitySignals": {"stars": stars, "forks": r.get("forks_count", 0), "codeAvailable": True},
                "codeAvailable": True, "lang": "en",
            })
        # unauthenticated GitHub search is limited to 10 requests/minute
        time.sleep(1.0 if token else 6.5)
    return out


def _gh_trending_from_html(text: str, limit: int):
    """Parse the trending page by CARD, because the markup carries many attributes.

    WHY the regex changed: GitHub now renders
      <h2 class="h3 lh-condensed">
        <a data-hydro-click="..." data-hydro-click-hmac="..." href="/owner/repo" ...>
    i.e. `href` is no longer the first attribute of the anchor, so the previous
    pattern `<h2 class="h3 lh-condensed">\\s*<a href="/...` matched 0 of 17 cards
    while the request itself was a perfectly healthy 200. Verified 2026-10-01:
    the card regex below matches 17/17 cards, and all 17 also expose a
    description, a total star count, a "stars today" count and a language.
    """
    out = []
    card_re = re.compile(r'<article class="Box-row">(.*?)</article>', re.S)
    repo_re = re.compile(r'<h2 class="h3 lh-condensed">\s*<a[^>]*?href="/([^"]+)"')
    desc_re = re.compile(r'<p class="col-9 color-fg-muted my-1[^"]*">\s*(.*?)\s*</p>', re.S)
    stars_re = re.compile(r'/stargazers"[^>]*>\s*(?:<[^>]+>\s*)*([\d,\.k]+)')
    today_re = re.compile(r'([\d,\.k]+)\s+stars?\s+today')
    lang_re = re.compile(r'itemprop="programmingLanguage">\s*([^<]+?)\s*<')

    def to_int(txt):
        txt = (txt or "").replace(",", "").strip().lower()
        try:
            return int(float(txt[:-1]) * 1000) if txt.endswith("k") else int(float(txt))
        except ValueError:
            return None

    for block in card_re.findall(text):
        m = repo_re.search(block)
        if not m:
            continue
        full = m.group(1).strip()
        if full.count("/") != 1:                 # trending also links orgs/topics
            continue
        desc = clean_text(desc_re.search(block).group(1), 300) if desc_re.search(block) else ""
        stars = to_int(stars_re.search(block).group(1)) if stars_re.search(block) else None
        today = to_int(today_re.search(block).group(1)) if today_re.search(block) else None
        lang = clean_text(lang_re.search(block).group(1), 40) if lang_re.search(block) else ""
        out.append({
            "sourceId": "gh_trending", "channel": "gh_trending", "externalId": full,
            "title": f"{full} - {desc}".strip(" -") if desc else f"GitHub Trending: {full}",
            "summary": desc or "项目进入今日 GitHub 趋势榜。",
            "url": f"https://github.com/{full}",
            "publishedAt": iso(now_cst()),
            "tags": [t for t in ([lang] if lang else []) + ["trending"] if t],
            "stars": stars,
            "qualitySignals": {"codeAvailable": True, "stars": stars,
                               "starsToday": today, "language": lang},
            "codeAvailable": True, "lang": "en",
        })
        if len(out) >= limit:
            break
    return out


def _gh_trending_from_rest(cfg, log, limit, lookback_days=7):
    """备用来源: GitHub REST search for repositories created in the last N days.

    Verified 2026-10-01: HTTP 200 JSON (12.6M matches for a plain date filter).
    Used only when the trending page changes shape again; unauthenticated search
    is rate limited to ~10 requests/minute, so this costs exactly one request.
    """
    since = (now_cst() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    url = ("https://api.github.com/search/repositories?q=" +
           urllib.parse.quote(f"created:>{since}") +
           "&sort=stars&order=desc&per_page=%d" % min(max(5, limit), 30))
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = http_json(url, headers=headers, cfg=cfg, log=log, retries=1, timeout=25)
    out = []
    for r in (data.get("items") or []) if isinstance(data, dict) else []:
        name = r.get("full_name")
        if not name:
            continue
        desc = clean_text(r.get("description") or "", 300)
        out.append({
            "sourceId": "gh_trending", "channel": "gh_trending", "externalId": name,
            "title": f"{name} - {desc}".strip(" -") if desc else f"GitHub Trending: {name}",
            "summary": desc or f"近 {lookback_days} 天新建的高星仓库（GitHub 趋势备用来源）。",
            "url": r.get("html_url") or f"https://github.com/{name}",
            "publishedAt": iso(parse_ts(r.get("created_at")) or now_cst()),
            "tags": (r.get("topics") or [])[:6] + ["trending-rest"],
            "stars": r.get("stargazers_count", 0),
            "qualitySignals": {"codeAvailable": True, "stars": r.get("stargazers_count", 0)},
            "codeAvailable": True, "lang": "en",
        })
        if len(out) >= limit:
            break
    return out


def collect_gh_trending(cfg, log, limit):
    """GitHub Trending, parsed from the server-rendered cards.

    Primary: https://github.com/trending?since=daily (200, server-rendered HTML,
    robots.txt's generic section does not disallow /trending).
    备用来源: the REST search endpoint above, for when the markup changes again.
    """
    limit = max(1, int(limit or 1))
    out, err = [], None
    try:
        _s, body, _ct = http_get("https://github.com/trending?since=daily", timeout=20,
                                 cfg=cfg, log=log, retries=1)
        out = _gh_trending_from_html(body.decode("utf-8", "replace"), limit)
    except Exception as e:
        err = e
        log(f"gh_trending html failed: {e}", "warn")
    if not out:
        try:
            out = _gh_trending_from_rest(cfg, log, limit)
            if out:
                log("gh_trending 使用备用来源 GitHub REST search", "warn")
        except Exception as e:
            log(f"gh_trending rest fallback failed: {e}", "warn")
            if err:
                raise err
    return out


def collect_openreview(cfg, log, limit):
    """OpenReview — DISABLED (see DISABLED_CHANNELS), code kept for reference.

    Measured 2026-10-01: api2 AND the legacy api1 `/notes` endpoints both answer
    HTTP 200 with `text/html` — the page titled "Verifying your browser |
    OpenReview" — i.e. an interstitial that only a real browser passes. Earlier
    runs saw the JSON form of the same wall (403 ChallengeRequiredError). No
    public alternative exists, and arXiv + s2 already cover the paper signal.
    """
    out = []
    for venue in ["ICLR.cc/2026/Conference", "NeurIPS.cc/2025/Conference", "ICML.cc/2025/Conference"]:
        url = ("https://api2.openreview.net/notes?content.venue=" + urllib.parse.quote(venue) +
               "&limit=%d&details=replyCount&sort=cdate:desc" % min(max(5, limit), 30))
        try:
            data = http_json(url, cfg=cfg, log=log, retries=1, timeout=30)
        except Exception as e:
            log(f"openreview '{venue}' failed: {e}", "warn")
            continue
        for n in (data.get("notes") or []) if isinstance(data, dict) else []:
            c = n.get("content") or {}
            title = clean_text((c.get("title") or {}).get("value", ""), 400)
            if not title:
                continue
            nid = str(n.get("id") or title_key(title))
            short = venue.split("/")[0]
            out.append({
                "sourceId": "openreview", "channel": "openreview", "externalId": nid,
                "title": title,
                "summary": clean_text((c.get("abstract") or {}).get("value", ""), 1800),
                "url": f"https://openreview.net/forum?id={nid}",
                "publishedAt": iso(parse_ts(n.get("cdate")) or now_cst()),
                "authors": (c.get("authors") or {}).get("value", []) or [],
                "venue": short, "peerReviewed": True,
                "qualitySignals": {"peerReviewed": True, "venue": short,
                                   "replies": n.get("replyCount", 0)},
                "tags": (c.get("keywords") or {}).get("value", []) or [],
                "lang": "en",
            })
        time.sleep(0.6)
    return out


S2_FIELDS = ("title,abstract,url,publicationDate,authors,venue,citationCount,externalIds")


def _s2_bulk(cfg, log, limit):
    """Primary S2 transport: /paper/search/bulk.

    Verified 2026-10-01: /paper/search answered HTTP 429, while
    /paper/search/bulk answered 200 with total=367696 — and 429/200/429 again
    inside the same minute, which is why `retries=2` and the two 备用来源 below
    both matter. Bulk ignores `limit` and always returns up to 1000 rows, so we
    sort by publicationDate desc, slice to `limit`, and pay one ~1-2MB body per
    day for abstracts that are actually worth scoring.
    """
    lookback = (now_cst() - timedelta(days=45)).strftime("%Y-%m-%d")
    query = '"large language model" OR multimodal OR "world model" OR "reinforcement learning"'
    url = ("https://api.semanticscholar.org/graph/v1/paper/search/bulk?query=" +
           urllib.parse.quote(query) + f"&fields={S2_FIELDS}" +
           f"&sort=publicationDate:desc&publicationDateOrYear={lookback}:")
    # retries=2 because the 429s are transient: in one measured minute the same
    # bulk URL answered 200, 429, 200. The backoff in http_get covers it, and
    # OpenAlex is still waiting as the next 备用来源 if it does not recover.
    data = http_json(url, cfg=cfg, log=log, retries=2, timeout=40)
    future_cutoff = now_cst() + timedelta(days=120)
    out = []
    for p in (data.get("data") or []) if isinstance(data, dict) else []:
        title = clean_text(p.get("title", ""), 400)
        if not title:
            continue
        stamp = parse_ts(p.get("publicationDate"))
        if stamp and stamp > future_cutoff:
            continue          # S2 carries scheduled issue dates far in the future
        ext = p.get("externalIds") or {}
        out.append({
            "sourceId": "s2", "channel": "s2",
            "externalId": str(p.get("paperId") or title_key(title)),
            "title": title, "summary": clean_text(p.get("abstract") or "", 1600),
            "url": p.get("url") or (f"https://arxiv.org/abs/{ext['ArXiv']}" if ext.get("ArXiv") else ""),
            "publishedAt": iso(stamp or now_cst()),
            "authors": [a.get("name", "") for a in (p.get("authors") or [])][:12],
            "venue": p.get("venue") or "", "peerReviewed": bool(p.get("venue")),
            "qualitySignals": {"citations": p.get("citationCount", 0), "venue": p.get("venue") or "",
                               "via": "semanticscholar-bulk"},
            "lang": "en",
        })
        if len(out) >= limit:
            break
    return out


def _openalex_abstract(inverted):
    """OpenAlex ships abstracts as a word -> positions map; rebuild the text."""
    if not isinstance(inverted, dict):
        return ""
    positions = {}
    for word, idxs in inverted.items():
        for i in idxs or []:
            positions[i] = word
    return " ".join(positions[k] for k in sorted(positions))


def _s2_openalex(cfg, log, limit):
    """备用来源 1: OpenAlex. Generous, no key, verified 200 with 25 rows."""
    url = ("https://api.openalex.org/works?search=" +
           urllib.parse.quote("multimodal large language model") +
           "&per-page=%d&sort=publication_date:desc&mailto=workbench@example.com" % min(max(5, limit), 50))
    data = http_json(url, cfg=cfg, log=log, retries=1, timeout=30,
                     headers={"Accept": "application/json"})
    out = []
    for w in (data.get("results") or []) if isinstance(data, dict) else []:
        title = clean_text(w.get("title") or w.get("display_name") or "", 400)
        if not title:
            continue
        venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
        out.append({
            "sourceId": "s2", "channel": "s2",
            "externalId": str(w.get("id") or title_key(title)),
            "title": title,
            "summary": clean_text(_openalex_abstract(w.get("abstract_inverted_index")), 1600),
            "url": w.get("doi") or w.get("id") or "",
            "publishedAt": iso(parse_ts(w.get("publication_date")) or now_cst()),
            "authors": [(a.get("author") or {}).get("display_name", "")
                        for a in (w.get("authorships") or [])][:12],
            "venue": venue, "peerReviewed": bool(venue),
            "qualitySignals": {"citations": w.get("cited_by_count", 0), "venue": venue,
                               "via": "openalex"},
            "lang": "en",
        })
    return out


def _s2_crossref(cfg, log, limit):
    """备用来源 2: Crossref. Verified 200 with 20 rows; abstract is JATS XML."""
    url = ("https://api.crossref.org/works?query=" +
           urllib.parse.quote("multimodal large language model") +
           "&rows=%d&sort=published&order=desc" % min(max(5, limit), 50) +
           "&select=DOI,title,abstract,URL,published,author,container-title,type")
    data = http_json(url, cfg=cfg, log=log, retries=1, timeout=30,
                     headers={"Accept": "application/json"})
    items = (((data or {}).get("message") or {}).get("items")) or []
    out = []
    for it in items:
        title = clean_text((it.get("title") or [""])[0], 400)
        if not title:
            continue
        published = ((it.get("published") or {}).get("date-parts") or [[None]])[0]
        stamp = None
        if published and published[0]:
            try:
                stamp = datetime(int(published[0]), int(published[1] or 1), int(published[2] or 1), tzinfo=timezone.utc)
            except (TypeError, ValueError):
                stamp = None
            if stamp and stamp > now_cst() + timedelta(days=30):
                continue                      # Crossref carries a few absurd future dates
        out.append({
            "sourceId": "s2", "channel": "s2",
            "externalId": str(it.get("DOI") or title_key(title)),
            "title": title, "summary": clean_text(it.get("abstract") or "", 1600),
            "url": it.get("URL") or (f"https://doi.org/{it['DOI']}" if it.get("DOI") else ""),
            "publishedAt": iso(stamp or now_cst()),
            "authors": [clean_text(f"{a.get('given', '')} {a.get('family', '')}", 80)
                        for a in (it.get("author") or [])][:12],
            "venue": clean_text((it.get("container-title") or [""])[0], 120),
            "peerReviewed": True,
            "qualitySignals": {"peerReviewed": True, "via": "crossref"},
            "lang": "en",
        })
    return out


def collect_s2(cfg, log, limit):
    """Semantic Scholar + ordered 备用来源 (OpenAlex, Crossref).

    The legacy /paper/search endpoint is still attempted first only when the
    caller opts in via config; by default we go straight to the endpoints that
    were verified working, because a burst of 429s every morning is noise.
    """
    for label, fn in (("semanticscholar-bulk", _s2_bulk),
                      ("openalex", _s2_openalex),
                      ("crossref", _s2_crossref)):
        try:
            rows = fn(cfg, log, max(1, int(limit or 1)))
        except Exception as e:
            log(f"s2 {label} failed: {e}", "warn")
            continue
        if rows:
            if label != "semanticscholar-bulk":
                log(f"s2 使用备用来源 {label}", "warn")
            return rows
    return []


def collect_hn(cfg, log, limit):
    out = []
    for q in ["multimodal LLM", "post-training RLHF", "world model", "diffusion model",
              "LLM agent", "GRPO", "vision language model", "inference optimization"]:
        url = ("https://hn.algolia.com/api/v1/search?query=" + urllib.parse.quote(q) +
               f"&tags=story&hitsPerPage={min(max(3, limit), 10)}&numericFilters=points>20")
        try:
            data = http_json(url, cfg=cfg, log=log, retries=1)
        except Exception as e:
            log(f"hn '{q}' failed: {e}", "warn")
            continue
        for h in (data.get("hits") or []) if isinstance(data, dict) else []:
            title = clean_text(h.get("title") or "", 300)
            if not title:
                continue
            oid = str(h.get("objectID"))
            pts = h.get("points", 0)
            out.append({
                "sourceId": "hn", "channel": "hn", "externalId": oid,
                "title": title, "summary": clean_text(h.get("story_text") or "", 800),
                "url": h.get("url") or f"https://news.ycombinator.com/item?id={oid}",
                "canonicalUrl": f"https://news.ycombinator.com/item?id={oid}",
                "publishedAt": iso(parse_ts(h.get("created_at")) or now_cst()),
                "authors": [h.get("author") or ""], "upvotes": pts,
                "qualitySignals": {"upvotes": pts, "comments": h.get("num_comments", 0)},
                "lang": "en",
            })
        time.sleep(0.3)
    return out


def collect_reddit(cfg, log, limit):
    """Reddit — DISABLED (see DISABLED_CHANNELS), code kept for re-enabling.

    Reachability as measured on 2026-10-01: the legacy JSON endpoint
    /r/<sub>/top.json answers HTTP 403, while the Atom feed
    /r/<sub>/top/.rss?t=day&limit=N answers 200 with 5 entries. We still do NOT
    collect it: https://www.reddit.com/robots.txt is `User-agent: * /
    Disallow: /`, and honouring robots.txt is a hard rule for this collector.
    lobste.rs has the same blanket Disallow, so there is no drop-in substitute
    either; Hacker News (`hn`) already carries that community signal.
    """
    out = []
    for sub in ["MachineLearning", "LocalLLaMA", "comfyui"]:
        try:
            out += _collect_rss(
                f"https://www.reddit.com/r/{sub}/top/.rss?t=day&limit={min(max(3, limit), 15)}",
                "reddit", cfg, log, min(max(3, limit), 15), [sub])
        except Exception as e:
            log(f"reddit r/{sub} failed: {e}", "warn")
        time.sleep(0.6)
    return out


def _collect_rss(url, source_id, cfg, log, limit, tags=None):
    out = []
    _s, body, _ct = http_get(url, timeout=20, cfg=cfg, log=log, retries=1,
                             accept="application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8")
    root = ET.fromstring(body)
    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for it in items[:limit]:

        def tx(tag, _it=it):
            el = _it.find(tag)
            if el is None:
                el = _it.find("{http://www.w3.org/2005/Atom}" + tag)
            return (el.text or "").strip() if el is not None and el.text else ""

        title = clean_text(tx("title"), 300)
        link = tx("link")
        if not link:
            le = it.find("{http://www.w3.org/2005/Atom}link")
            link = le.attrib.get("href", "") if le is not None else ""
        if not title or not link:
            continue
        out.append({
            "sourceId": source_id, "channel": source_id, "externalId": link,
            "title": title,
            "summary": clean_text(tx("description") or tx("summary") or tx("content"), 900),
            "url": link,
            "publishedAt": iso(parse_ts(tx("pubDate") or tx("published") or tx("updated")) or now_cst()),
            "tags": list(tags or []),
            "lang": "zh" if re.search(r"[\u4e00-\u9fff]", title) else "en",
        })
    return out


def collect_machineheart(cfg, log, limit):
    """机器之心 — DISABLED (see DISABLED_CHANNELS), code kept for re-enabling.

    Measured 2026-10-01: https://www.jiqizhixin.com/rss and /feed both answer
    HTTP 200 but with the HTML landing page 机器之心·数据服务 instead of XML;
    /rss/articles is 404; the only reachable RSSHub mirror 404s on
    /jiqizhixin/daily. The publisher retired the feed, so the Chinese-AI-media
    slot is served by `collect_leiphone` (雷锋网) instead.
    """
    return _collect_rss("https://www.jiqizhixin.com/rss", "machineheart", cfg, log, limit, ["资讯"])


def collect_leiphone(cfg, log, limit):
    """雷锋网 — the replacement Chinese AI/tech media feed for 机器之心.

    备用来源 requirement: 量子位 (qbitai) is the other live Chinese AI feed, and
    CHANNEL_SPECS marks it as this channel's backup. Verified 2026-10-01:
    https://www.leiphone.com/feed answers 200 application/rss+xml with 20 items,
    the newest stamped the same day, and 算法/工程师 appear across the titles.
    robots.txt disallows /dynamic/, /search/ and friends but not /feed.
    """
    return _collect_rss("https://www.leiphone.com/feed", "leiphone", cfg, log, limit,
                        ["资讯", "AI", "中文媒体"])


def collect_qbitai(cfg, log, limit):
    return _collect_rss("https://www.qbitai.com/feed", "qbitai", cfg, log, limit, ["资讯"])


def collect_hf_blog_rss(cfg, log, limit):
    return _collect_rss("https://huggingface.co/blog/feed.xml", "hf_blog_rss", cfg, log, limit, ["blog"])


def collect_openai_rss(cfg, log, limit):
    return _collect_rss("https://openai.com/news/rss.xml", "openai_rss", cfg, log, limit, ["blog"])


RSSHUB_MIRRORS = [
    # Ordered by measured health on 2026-10-01. WHY the order: rsshub.app is
    # behind a Cloudflare interstitial (403 "Just a moment...") and
    # rsshub.rssforever.com answers 503, so the community mirror is the primary.
    "https://rss.injahow.cn",
    "https://rsshub.rssforever.com",
    "https://rsshub.app",
]


def collect_rsshub(cfg, log, limit):
    """RSSHub bridge — DISABLED (see DISABLED_CHANNELS), code kept for re-enabling.

    Measured 2026-10-01: rsshub.app 403 (Cloudflare), rsshub.rssforever.com 503,
    rsshub.ktachibana.party 404/503, rsshub.pseudoyu.com TLS error. The only
    reachable mirror serves /zhihu/hotlist (already consumed by `zhihu`) and
    /solidot; every other route tested (github/trending/daily/any, 36kr, v2ex,
    hackernews, sspai) answered 503. Kept so it can be re-enabled when the
    public instances recover.
    """
    out = []
    for route in ["zhihu/hotlist", "github/trending/daily/any"]:
        for base in RSSHUB_MIRRORS:
            try:
                rows = _collect_rss(f"{base}/{route}", "rsshub", cfg, log,
                                    max(5, limit // 2), ["rsshub"])
            except Exception as e:
                log(f"rsshub {base}/{route} failed: {e}", "warn")
                continue
            if rows:
                out += rows
                break
    return out


def collect_zhihu(cfg, log, limit):
    """知乎热榜 via a public RSSHub mirror.

    WHY a mirror: the first-party endpoints are login-walled —
    https://www.zhihu.com/api/v4/search/top_search answers 403
    {"error":{"need_login":true,...}} and https://www.zhihu.com/hot answers 403.
    We never log in; we read the public bridge instead.
    Verified 2026-10-01: https://rss.injahow.cn/zhihu/hotlist -> 200
    application/xml with 40 items.
    """
    last = None
    for base in RSSHUB_MIRRORS:
        try:
            rows = _collect_rss(f"{base}/zhihu/hotlist", "zhihu", cfg, log, limit, ["知乎", "热榜"])
        except Exception as e:
            last = e
            log(f"zhihu mirror {base} failed: {e}", "warn")
            continue
        if rows:
            if base != RSSHUB_MIRRORS[0]:
                log(f"zhihu 使用备用镜像 {base}", "warn")
            return rows
    if last:
        raise last
    return []


def collect_nowcoder(cfg, log, limit):
    """Nowcoder public discussion pages.

    WHY the regex changed: the listing is server-rendered, but each title sits
    inside nested <span>s —
      <a href="/discuss/933114179207069696?sourceSSR=home" ... class="po">
        <span ...><span ...>机械工程相关题目</span></span></a>
    so the old `href="(/discuss/\\d+...)"[^>]*>\\s*([^<]{8,120})<` matched 0 of 20
    links while the page itself was a healthy 200. Verified 2026-10-01: the
    tag-tolerant pattern below yields 10 (href, title) pairs including 面经/实习
    threads. robots.txt disallows /search, /nccommon and /ab/ab-test-flow only.
    """
    out = []
    link_re = re.compile(r'<a[^>]*href="(/discuss/\d+)[^"]*"[^>]*>(.*?)</a>', re.S)
    for url, kind in [("https://www.nowcoder.com/discuss?type=0&order=0", "discuss"),
                      ("https://www.nowcoder.com/discuss?type=2&order=0", "job")]:
        try:
            _s, body, _ct = http_get(url, timeout=20, cfg=cfg, log=log, retries=1)
            text = body.decode("utf-8", "replace")
        except Exception as e:
            log(f"nowcoder {kind} failed: {e}", "warn")
            continue
        found, seen = 0, set()
        for m in link_re.finditer(text):
            href, inner = m.group(1), m.group(2)
            title = clean_text(re.sub(r"<[^>]+>", " ", inner), 200)
            if not title or len(title) < 6 or href in seen:
                continue
            seen.add(href)
            out.append({
                "sourceId": "nowcoder", "channel": "nowcoder", "externalId": href,
                "title": title,
                "summary": "牛客社区公开讨论页，可能包含面经或招聘信息。",
                "url": "https://www.nowcoder.com" + href,
                "publishedAt": iso(now_cst()),
                "tags": ["牛客", "面经"], "lang": "zh",
            })
            found += 1
            if found >= limit:
                break
        log.detail(f"nowcoder {kind} -> {found}")
        time.sleep(0.8)
    return out


def _jobs_common(source_id, rows, cfg):
    """Normalize heterogeneous job payloads into one item shape.

    WHY the key lists are long: Tencent's API returns RecruitPostName / PostURL /
    LocationName / LastUpdateTime, while ByteDance-style payloads use
    title / url / city / publishTime. Looking up a single field name is exactly
    what made a 200-OK, 339-opening Tencent feed report as `empty`.
    """
    out = []
    for r in rows if isinstance(rows, list) else []:
        title = clean_text(first_of(r, ("title", "name", "jobName", "RecruitPostName",
                                        "positionName", "postName", "jobTitle")), 200)
        if not title or not re.search(r"算法|模型|多模态|大模型|AI|machine learning|algorithm|research",
                                      title, re.I):
            continue
        desc_keys = ("description", "requirement", "Responsibility", "jobDescription",
                     "descriptionHtml", "city", "cityName", "workCity", "LocationName",
                     "workLocation", "category", "jobCategory", "CategoryName",
                     "ProductName", "BGName")
        desc_bits = [clean_text(r.get(k), 240) for k in desc_keys if r.get(k)]
        url = first_of(r, ("url", "jobUrl", "postUrl", "PostURL", "detailUrl",
                           "positionUrl", "redirectUrl", "submitUrl"))
        out.append({
            "sourceId": source_id, "channel": source_id,
            "externalId": str(first_of(r, ("id", "code", "RecruitPostId", "PostId",
                                           "positionId", "jobId")) or title_key(title)),
            "title": title,
            "summary": clean_text(" | ".join(b for b in desc_bits if b), 600),
            "url": url,
            "publishedAt": iso(parse_ts(first_of(r, ("publishTime", "updateTime", "releaseTime",
                                                     "LastUpdateTime", "publishDate"))) or now_cst()),
            "tags": ["招聘"] + [t for t in (clean_text(first_of(r, ("city", "cityName",
                                                                   "workCity", "LocationName")), 40),) if t],
            "lang": "zh",
        })
    return out


def collect_jobs_bytedance(cfg, log, limit):
    url = ("https://jobs.bytedance.com/api/v1/search/job/posts?keyword=" +
           urllib.parse.quote("算法实习") + "&limit=20&offset=0&job_category_id_list=&tag_id_list="
           "&location_code_list=&subject_id_list=&recruitment_id_list=1&portal_type=6")
    data = http_json(url, cfg=cfg, log=log, retries=1, timeout=30,
                     headers={"Referer": "https://jobs.bytedance.com/experienced/position"})
    rows = ((data or {}).get("data") or {}).get("job_post_list") or []
    return _jobs_common("jobs_bytedance", rows, cfg)


def collect_jobs_tencent(cfg, log, limit):
    """腾讯招聘 — worked all along; the bug was on our side.

    Verified 2026-10-01: HTTP 200 JSON,
    {"Code":200,"Data":{"Count":339,"Posts":[... 20 rows ...]}}, each row
    carrying RecruitPostName / PostURL / LastUpdateTime / LocationName /
    Responsibility. `pageSize=10` and `pageSize=20` both answer at once, so the
    channel previously reported `empty` only because _jobs_common looked up
    title/name/jobName and never saw RecruitPostName.
    """
    url = ("https://careers.tencent.com/tencentcareer/api/post/Query?timestamp=0&countryId=&cityId="
           "&bgId=&bgIds=&productId=&categoryId=&parentCategoryId=&attrId=&keyword=" +
           urllib.parse.quote("算法") + "&pageIndex=1&pageSize=%d&language=zh-cn&area=cn"
           % min(max(20, limit), 50))
    data = http_json(url, cfg=cfg, log=log, retries=1, timeout=30)
    rows = ((data or {}).get("Data") or {}).get("Posts") or []
    return _jobs_common("jobs_tencent", rows, cfg)


def collect_jobs_alibaba(cfg, log, limit):
    """阿里招聘 — DISABLED (see DISABLED_CHANNELS); endpoint kept for reference.

    The old /api/job/search path is a 404 Whitelabel page. The API the live SPA
    actually calls is POST https://talent.alibaba.com/position/search (its JS
    bundle maps `/position/search` and `/searchCondition/list`), but GET answers
    405, POST without a CSRF token answers 403, and POST with the CSRF token the
    public page itself sets answers 200 `{"success":true,"datas":null,
    "totalCount":0}` for every payload shape tried. The backend wants a token
    only Alibaba's baxia browser script can mint, so this stays blocked rather
    than turning into a redirect-chasing exercise.
    """
    url = ("https://talent.alibaba.com/api/job/search?keyword=" + urllib.parse.quote("算法") +
           "&pageSize=20&pageNo=1&language=zh")
    data = http_json(url, cfg=cfg, log=log, retries=1, timeout=30)
    rows = data.get("data") or (data.get("content") or {}).get("datas") or []
    if isinstance(rows, dict):
        rows = rows.get("list") or []
    return _jobs_common("jobs_alibaba", rows, cfg)


def _generic_jobs_html(source_id, url, cfg, log, limit):
    """For career pages without a public API: extract only visible job links."""
    out = []
    _s, body, _ct = http_get(url, timeout=25, cfg=cfg, log=log, retries=1)
    text = body.decode("utf-8", "replace")
    seen = set()
    for m in re.finditer(r'href="([^"]{4,200})"[^>]*>([^<]{6,90})<', text):
        href, label = m.group(1), clean_text(m.group(2), 90)
        if not label or label in seen:
            continue
        if not re.search(r"算法|模型|实习|多模态|大模型|AI|研究", label):
            continue
        seen.add(label)
        full = href if href.startswith("http") else urllib.parse.urljoin(url, href)
        out.append({
            "sourceId": source_id, "channel": source_id, "externalId": full,
            "title": label, "summary": f"{CHANNEL_NAMES.get(source_id, source_id)} 招聘页公开条目",
            "url": full, "publishedAt": iso(now_cst()), "tags": ["招聘"], "lang": "zh",
        })
        if len(out) >= limit:
            break
    return out


def collect_jobs_zhipu(cfg, log, limit):
    """智谱招聘 — DISABLED (see DISABLED_CHANNELS), code kept for reference.

    zhipuai.cn/joinus answers 200 with 783KB of Next.js RSC payload, but it is a
    marketing page: 算法/校招 appear only as i18n category labels, there is no
    per-job data, no ATS host (only generic feishu.cn form links) and none of the
    15 referenced _next chunks calls a job API.
    """
    return _generic_jobs_html("jobs_zhipu", "https://zhipuai.cn/joinus", cfg, log, limit)


def collect_jobs_moonshot(cfg, log, limit):
    """月之暗面 — DISABLED (see DISABLED_CHANNELS), code kept for reference.

    www.moonshot.cn/careers answers 200 with 95KB and zero job keywords, and now
    delegates to careers.kimi.com, which is an 11.6KB JS shell with only three
    RSC pushes, no embedded data (/jobs and /positions are 404) and no API path
    in its chunks.
    """
    return _generic_jobs_html("jobs_moonshot", "https://www.moonshot.cn/careers", cfg, log, limit)


def collect_jobs_deepseek(cfg, log, limit):
    """DeepSeek 招聘 — 备用来源 is the Moka ATS snapshot baked into the site bundle.

    WHY this shape: https://www.deepseek.com/careers is a hard 404 (the homepage
    links to https://talent.deepseek.com/ instead). That host is a 588-byte SPA
    shell whose own API needs a browser, but its production bundle
    /static/main.<hash>.js ships a build-time snapshot of the Moka listing as a
    literal `JSON.parse('{"crawledAt":...,"sourceUrl":"https://app.mokahr.com/
    social-recruitment/high-flyer/140576","total":N,"jobs":[...]}')` — the exact
    data the page renders from. Verified 2026-10-01: 34 jobs, including
    预训练/后训练/多模态理解 研究员 and 大模型训练/推理框架工程师.
    """
    _s, body, _ct = http_get("https://talent.deepseek.com/", timeout=25, cfg=cfg, log=log, retries=1)
    page = body.decode("utf-8", "replace")
    m = (re.search(r'<script[^>]+src="(/static/main[^"]+\.js)"', page)
         or re.search(r'"(/static/main\.[0-9a-z]+\.js)"', page))
    if not m:
        log("deepseek: main bundle not referenced by the landing page", "warn")
        return []
    _s, js_body, _ct = http_get("https://talent.deepseek.com" + m.group(1),
                                timeout=30, cfg=cfg, log=log, retries=1)
    js = js_body.decode("utf-8", "replace")
    lit = re.search(r"JSON\.parse\('(\{\"crawledAt\".*?)'\)", js, re.S)
    if not lit:
        log("deepseek: embedded job catalogue literal not found", "warn")
        return []
    try:
        data = json.loads(js_literal_decode(lit.group(1)))
    except Exception as e:
        raise ValueError(f"deepseek catalogue literal unreadable: {e}") from e
    out = []
    for job in (data.get("jobs") or [])[:max(1, int(limit or 1))]:
        title = clean_text(job.get("title") or "", 200)
        if not title:
            continue
        detail = job.get("detailUrl") or data.get("sourceUrl") or "https://talent.deepseek.com/"
        out.append({
            "sourceId": "jobs_deepseek", "channel": "jobs_deepseek",
            "externalId": str(job.get("id") or title_key(title)),
            "title": title,
            "summary": clean_text(" | ".join(
                x for x in [job.get("functionName"),
                            "、".join(job.get("locations") or []),
                            clean_text(job.get("descriptionHtml") or "", 400)] if x), 600),
            "url": detail,
            "publishedAt": iso(parse_ts(data.get("crawledAt")) or now_cst()),
            "tags": ["招聘", "DeepSeek"] + [t for t in (job.get("functionName"),) if t],
            "qualitySignals": {"via": "moka-ats-snapshot", "crawledAt": data.get("crawledAt"),
                               "sourceUrl": data.get("sourceUrl")},
            "lang": "zh",
        })
    if not out:
        log("deepseek: catalogue contained no jobs", "warn")
    return out


def collect_jobs_minimax(cfg, log, limit):
    """MiniMax — DISABLED (see DISABLED_CHANNELS), code kept for reference.

    minimaxi.com/careers renders an embedded Feishu ATSX portal
    (vrfi1sk8a0.jobs.feishu.cn, robots.txt disallows /api/). The portal index is
    a 126KB shell with no job rows and its API answers 405 exactly like
    ByteDance's, so there is nothing to parse without a browser.
    """
    return _generic_jobs_html("jobs_minimax", "https://www.minimaxi.com/careers", cfg, log, limit)


def collect_jobs_shailab(cfg, log, limit):
    """上海 AI Lab — DISABLED (see DISABLED_CHANNELS), code kept for reference.

    /joinus, /joinus/social and /joinus/campus all return the same 70KB
    marketing page with no job rows; openings arrive over JS and no ATS/API
    endpoint is referenced anywhere in the page or its scripts.
    """
    return _generic_jobs_html("jobs_shailab", "https://www.shlab.org.cn/joinus", cfg, log, limit)


def collect_inbox(cfg, log, limit):
    """Human-in-the-loop import.

    Reads only local files produced by scripts/inbox.py from web/data/inbox/.
    This makes login-walled channels (Xiaohongshu, BOSS Zhipin, Lagou, Shixiseng)
    usable WITHOUT ever making a network request to them - which is both the
    legally correct behaviour and the only stable one.

    Re-reads every run so edits to the source rows are picked up; the deduper
    collapses repeats, so re-importing is free.
    """
    out = []
    inbox = DATA_DIR / "inbox"
    if not inbox.exists():
        return out
    for path in sorted(inbox.glob("normalized-*.json")):
        try:
            payload = json.loads(path.read_text("utf-8"))
        except Exception as e:
            log(f"inbox: {path.name} unreadable ({e})", "warn")
            continue
        rows = payload.get("items") if isinstance(payload, dict) else payload
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            raw = dict(row)
            raw["sourceId"] = "inbox"
            raw["channel"] = "inbox"
            out.append(raw)
    if out:
        log.detail(f"inbox -> {len(out)} rows from {inbox.name}/*.json")
    return out


# ============================================================================
# 4b. ALGORITHM KNOWLEDGE BASES (knowledgeBase channels)
#
# WHY THESE EXIST: the reader's complaint was specific - the workbench should
# accumulate hand-writing problems, written-test questions, interview write-ups
# and 八股 knowledge, and that material predates today. A `newest-first` feed can
# never deliver it: 代码随想录 / 卡码笔记 publish a fixed, growing knowledge base,
# so their pages are reference material whose value does NOT decay with age.
#
# They are therefore collected differently from every other channel:
#   * the work list comes from the site's own sitemap.xml, not from a feed;
#   * a deterministic daily window rotates through the whole list, so the backlog
#     ("过往的也可以整理") is absorbed over weeks instead of demanding a 600-request
#     burst today;
#   * each page is fetched once for its real <title>/<h1> and meta description -
#     no fabricated summaries;
#   * `knowledgeBase: True` in CHANNEL_SPECS gives them a scoring component that
#     is explicitly independent of publication date (see score_item).
#
# About WeChat 公众号: 代码随想录 / 卡码笔记 / 万诺coding all publish through
# 公众号, and 公众号 has no public RSS or API. Rather than scrape a login-walled
# mirror, this uses the SAME AUTHORS' own web properties (their sites and GitHub
# repositories) - same content, first-party, and allowed by their robots.txt.
# ============================================================================

KB_SITES = {
    "programmercarl": {
        "sitemap": "https://programmercarl.com/sitemap.xml",
        # NOTE ON `suffix`: it is appended to the page title, so it must be either a
        # keyword of the category the page genuinely belongs to, or neutral. A
        # knowledge-type word that happens to be another category's keyword
        # ("知识点" -> exam) hijacks the classifier, because a title hit weighs 3x
        # a body hit. Families whose home is not a tracked category therefore use a
        # neutral suffix ("大模型笔记") and let the page's own words decide.
        "families": {
            "/algo/":      {"suffix": "题解", "tags": ["算法题", "题解", "leetcode", "手撕"]},
            "/hot100/":    {"suffix": "题解", "tags": ["leetcode", "hot100", "题解", "算法题"]},
            "/kamacoder/": {"suffix": "题解", "tags": ["算法题", "题解", "笔试", "卡码网"]},
            "/llm/":       {"suffix": "大模型笔记", "tags": ["大模型", "llm", "知识点"]},
            "/ke/":        {"suffix": "课程笔记", "tags": ["课程", "知识点"]},
        },
    },
    "kamacoder_notes": {
        "sitemap": "https://notes.kamacoder.com/sitemap.xml",
        # `/cpp/` `/java/` `/go/`（246 页语言特性问答）刻意不收：那是**后端岗**的八股，
        # 这个工作台服务的是算法实习。`/base/` 收，因为操作系统/网络/数据库这些
        # 计算机基础是任何技术岗面试都会问的「八股」，与岗位族无关。
        "families": {
            "/interview/": {"suffix": "面试题", "tags": ["面试题", "面经", "八股"]},
            "/base/":      {"suffix": "八股", "tags": ["八股", "知识点", "基础"]},
            "/llm/":       {"suffix": "大模型笔记", "tags": ["大模型", "llm", "知识点"]},
            "/ke/":        {"suffix": "课程笔记", "tags": ["课程", "知识点"]},
        },
    },
    "xiaolincoding": {
        "sitemap": "https://www.xiaolincoding.com/sitemap.xml",
        # 只收计算机基础与面试题。`/backend_interview/`（51 页银行/后端面经）、
        # `/mysql/` `/redis/` `/project/` `/salary/` 不收 —— 那是后端岗内容。
        "families": {
            "/network/":   {"suffix": "八股", "tags": ["八股", "知识点", "计算机网络"]},
            "/os/":        {"suffix": "八股", "tags": ["八股", "知识点", "操作系统"]},
            "/cs_learn/":  {"suffix": "八股", "tags": ["八股", "知识点", "计算机基础"]},
            "/openai/":    {"suffix": "大模型笔记", "tags": ["大模型", "llm", "知识点"]},
        },
    },
}

# 知识库站内的「整块不收录」路径。
#
# 为什么需要：这些站的 family 划分是按**章节**的，而章节里会掺进与该章节主题无关、
# 且与求职学习完全无关的页面。实测漏进来的三条（都因为 knowledgeBase=True 绕过了
# 全部质量闸门）：
#   xiaolincoding  /openai/gpt.html            「2026年最新ChatGPT充值教程…」
#   programmercarl /llm/plus/0001.gptpay.html  「怎么给ChatGPT充值？…」
#   programmercarl /llm/plus/0002.claudepay.html「Claude Pro怎么充值？…」
#   xiaolincoding  /cs_learn/pdf.html          「小林图解全系列PDF+1000道…真题PDF下载」
# 光靠 knowledge_quality 的 paid-guide / download-bait 规则也能拦（已加），但这里是
# **源头**过滤：页面根本不会被请求，省一次网络往返，也不会在 sitemap 窗口里占位。
KB_PATH_DENY = [
    r"/llm/plus/",          # 代码随想录 · 充值/订阅攻略
    r"/openai/",            # 小林coding · ChatGPT 充值教程
    r"/cs_learn/pdf",       # 小林coding · 资料包下载页
    r"pay\.html$", r"/pay(?:ment)?/",
    r"/(?:shop|mall|vip|sell)/", r"/salary/",
    r"/pdf(?:\.html)?$",
]

# 大厂真实高频面试题（CodeTop）。数值是**被考频度**，也就是"这道题真的被考过多少次"。
#
# 为什么这是最贴合需求的一个源：用户要的是"直接和大厂面试笔试题相关"的东西，
# 而 CodeTop 把"公司 × 题号 × 频度"做成了公开 JSON API（22 家公司、1158 道题）。
# 它回答的不是"最近有什么新题"，而是"字节/腾讯/美团真的反复在考哪些题" ——
# 这正是参考资料型的价值，与发布日期无关。
CODETOP_COMPANIES = ("字节跳动", "腾讯", "阿里巴巴", "美团", "百度", "快手", "京东",
                     "微软", "滴滴", "华为", "拼多多", "网易", "商汤", "旷视", "小米",
                     "携程", "蚂蚁", "亚马逊")

# Curated algorithm / OJ knowledge repositories.
#
# A fixed list rather than a star-count search: these are the canonical, still
# maintained references for exactly what the reader asked for (LeetCode 题解、
# 算法竞赛知识库、笔试模板). Being in this list is not a claim about freshness -
# `OI-wiki` and `labuladong/fucking-algorithm` are worth collecting precisely
# because they are stable references.
ALGO_REPOS = [
    ("youngyangyang04/leetcode-master", ["leetcode", "题解", "刷题攻略", "算法题"], "coding"),
    ("youngyangyang04/kamacoder-solutions", ["题解", "算法题", "卡码网", "笔试"], "coding"),
    ("labuladong/fucking-algorithm", ["leetcode", "算法", "题解", "手撕"], "coding"),
    ("doocs/leetcode", ["leetcode", "题解", "多语言", "算法题"], "coding"),
    ("halfrost/LeetCode-Go", ["leetcode", "题解", "golang", "算法题"], "coding"),
    ("azl397985856/leetcode", ["leetcode", "题解", "算法题"], "coding"),
    ("SharingSource/LogicStack-LeetCode", ["leetcode", "题解", "算法题"], "coding"),
    ("afatcoder/LeetcodeTop", ["leetcode", "高频面试题", "算法题", "题解"], "coding"),
    ("krahets/hello-algo", ["数据结构", "算法", "教程", "知识点"], "foundation"),
    ("OI-wiki/OI-wiki", ["算法竞赛", "知识库", "动态规划", "图论"], "foundation"),
    ("EndlessCheng/codeforces-go", ["算法竞赛", "模板", "codeforces", "笔试"], "coding"),
    # --- 算法岗「手撕」实现题（本方向的稀缺资源：不是力扣原题，而是手写算子/结构）---
    ("duoan/TorchCode", ["pytorch", "手撕", "深度学习", "实现题"], "coding"),
    ("Exorust/TorchLeet", ["pytorch", "手撕", "深度学习", "实现题"], "coding"),
    # --- 机器学习/深度学习面试知识点 + 代码实现 ---
    ("NLP-LOVE/ML-NLP", ["机器学习", "深度学习", "八股", "知识点"], "posttraining"),
    ("CyC2018/CS-Notes", ["八股", "知识点", "操作系统", "计算机网络"], "foundation"),
    ("0voice/interview_internal_reference", ["面试题", "八股", "知识点"], "exam"),
    ("forthespada/InterviewGuide", ["面试题", "八股", "知识点", "校招"], "exam"),
]


def _kb_sitemap(url, cfg, log, timeout=30):
    """Return [(loc, lastmod|None)] from a sitemap.xml."""
    _s, body, _ct = http_get(url, timeout=timeout, cfg=cfg, log=log, retries=2)
    text = body.decode("utf-8", "replace")
    out = []
    for m in re.finditer(r"<url>\s*<loc>(.*?)</loc>(?:\s*<lastmod>(.*?)</lastmod>)?", text, re.S):
        out.append((html.unescape(m.group(1).strip()), (m.group(2) or "").strip() or None))
    if not out:
        out = [(html.unescape(u.strip()), None) for u in re.findall(r"<loc>(.*?)</loc>", text, re.S)]
    return out


def _kb_page_meta(url, cfg, log, timeout=20):
    """Fetch one page and return (title, description). Never raises."""
    try:
        _s, body, _ct = http_get(url, timeout=timeout, cfg=cfg, log=log, retries=1)
        text = body.decode("utf-8", "replace")
    except Exception:
        return None, None
    title = None
    m = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.S | re.I)
    if m:
        title = clean_text(html.unescape(re.sub(r"<[^>]+>", " ", m.group(1))).lstrip("# ").strip(), 200)
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
        if m:
            raw = html.unescape(re.sub(r"<[^>]+>", " ", m.group(1))).strip()
            # Titles carry the whole site tagline; the first segment is the page.
            title = clean_text(re.split(r"\s*[|｜]\s*", raw)[0], 200)
    desc = None
    for pat in (r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
                r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']',
                r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']'):
        m = re.search(pat, text, re.S | re.I)
        if m:
            desc = clean_text(html.unescape(m.group(1)), 700)
            break
    return title, desc


def _collect_kb_site(cid, cfg, log, limit):
    """Sitemap-driven collector for a first-party algorithm knowledge base."""
    site = KB_SITES.get(cid) or {}
    try:
        entries = _kb_sitemap(site["sitemap"], cfg, log)
    except Exception as e:
        raise RuntimeError(f"{cid} sitemap fetch failed: {e}") from e

    fams = site["families"]
    pool = []
    denied = 0
    for loc, lastmod in entries:
        path = urllib.parse.urlsplit(loc).path
        if path.endswith("/"):
            continue                       # directory index, not a page
        if any(re.search(p, path, re.I) for p in KB_PATH_DENY):
            denied += 1
            continue                       # 充值/订阅/资料包等整块路径，见 KB_PATH_DENY
        for fam, meta in fams.items():
            if path.startswith(fam):
                pool.append((loc, lastmod, meta, fam))
                break
    if not pool:
        raise RuntimeError(f"{cid}: sitemap yielded no pages in the tracked families")

    pool.sort(key=lambda t: t[0])
    # Interleave the families before rotating. Sorting by URL puts every /go/ page
    # together, so a 60-page window could land inside a single family - measured:
    # the exam bucket grew 15 cards all opening with "go", which the redundancy
    # check (correctly) flagged as title-prefix saturation. Round-robin across
    # families makes every window a mix of 题解 / 八股 / 面试题 / 大模型笔记.
    by_fam: dict[str, list] = {}
    for entry in pool:
        by_fam.setdefault(entry[3], []).append(entry)
    ordered: list = []
    depth = max((len(v) for v in by_fam.values()), default=0)
    for i in range(depth):
        for fam in sorted(by_fam):
            if len(by_fam[fam]) > i:
                ordered.append(by_fam[fam][i])
    # Deterministic rotation: each day advances the window by `limit`, so the whole
    # backlog is absorbed over weeks and two runs never fight over the same slice.
    day_index = int(now_cst().strftime("%j"))
    start = (day_index * max(1, limit)) % len(ordered)
    window = (ordered[start:] + ordered[:start])[:limit]

    out = []
    for loc, lastmod, meta, fam in window:
        title, desc = _kb_page_meta(loc, cfg, log)
        if not title:
            continue
        title = f"{title} · {meta['suffix']}"
        ts = parse_ts(lastmod) if lastmod else None
        out.append({
            "sourceId": cid, "channel": cid,
            "externalId": urllib.parse.urlsplit(loc).path,
            "title": title,
            "summary": desc or "",
            "summarySource": "page-meta-description" if desc else None,
            "url": loc,
            "publishedAt": iso(ts) if ts else None,
            "tags": list(meta["tags"]) + [fam.strip("/")],
            "lang": "zh",
            "codeAvailable": True,          # every one of these pages ships code
            "peerReviewed": False,
            "qualitySignals": {"source": "knowledge-base", "family": fam},
        })
        time.sleep(max(0.7, float((cfg.get("http") or {}).get("delayBetween", 0.4))))
        log.detail(f"{cid} + {title[:70]}")
    log(f"{cid} sitemap={len(entries)} pool={len(pool)} window={start}.. fetched={len(out)}"
        + (f" deny={denied}" if denied else ""))
    return out


def collect_programmercarl(cfg, log, limit):
    """代码随想录官方站（563 页：/algo/ 298 · /hot100/ 48 · /kamacoder/ 49 · /llm/ 26）."""
    return _collect_kb_site("programmercarl", cfg, log, limit)


def collect_kamacoder_notes(cfg, log, limit):
    """卡码笔记（525 页：/interview/ 74 · /base/ 74 · /llm/ 127 · 语言八股 172）."""
    return _collect_kb_site("kamacoder_notes", cfg, log, limit)


def collect_gh_algokb(cfg, log, limit):
    """Curated LeetCode / OJ / algorithm-competition repositories via the GitHub API.

    One entry per repository, refreshed each run (the stable id de-duplicates it),
    so star counts and activity stay current without re-importing anything.
    """
    out = []
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    for full_name, tags, cat in ALGO_REPOS[:max(1, limit)]:
        try:
            data = http_json(f"https://api.github.com/repos/{full_name}", headers=headers, cfg=cfg)
        except Exception as e:
            log(f"    gh_algokb {full_name}: {e}", "warn")
            continue
        if not isinstance(data, dict) or not data.get("full_name"):
            continue
        desc = clean_text(data.get("description") or "", 500)
        topics = [str(t) for t in (data.get("topics") or [])][:8]
        stars = data.get("stargazers_count")
        lang = data.get("language") or ""
        bits = [b for b in (desc, f"语言 {lang}" if lang else "",
                            f"{stars} stars" if stars else "",
                            "，".join(topics)) if b]
        out.append({
            "sourceId": "gh_algokb", "channel": "gh_algokb",
            "externalId": full_name,
            "title": f"{full_name} · 算法题解/知识库",
            "summary": clean_text(" | ".join(bits), 600),
            "summarySource": "github-repo",
            "url": data.get("html_url") or f"https://github.com/{full_name}",
            "publishedAt": iso(parse_ts(data.get("pushed_at"))) if data.get("pushed_at") else None,
            "tags": tags + ["github"] + [t for t in topics[:4]],
            "lang": "en",
            "stars": stars,
            "codeAvailable": True,
            "qualitySignals": {"stars": stars, "forks": data.get("forks_count"),
                               "codeAvailable": True, "curatedFor": cat},
        })
        time.sleep(float((cfg.get("http") or {}).get("delayBetween", 0.4)))
    log(f"gh_algokb curated repos -> {len(out)}")
    return out


def collect_codetop(cfg, log, limit):
    """CodeTop — 大厂真实高频面试题及其**被考频度**。

    WHAT IT PROVIDES: for each company it gives the questions that were actually
    asked, ordered by how often. That is the closest thing to "真实笔试/面试真题"
    that is available as structured data, and unlike a feed it does not decay: the
    fact that 字节 asks 「无重复字符的最长子串」 hundreds of times is as true next
    year as today.

    WHAT IT DELIBERATELY DOES NOT TAKE: the `content` field (the full LeetCode
    problem statement). That text is LeetCode's, this workbench publishes to the
    open web, and re-publishing whole problem statements is not ours to do. Only
    factual metadata is used - question number, title, difficulty, frequency,
    company - plus a link to the problem's own page.

    Requests per run: 1 (companies) + one per tracked company.
    """
    base = "https://codetop.cc/api"
    try:
        comps = http_json(f"{base}/companies/", cfg=cfg,
                          headers={"Accept": "application/json"})
    except Exception as e:
        raise RuntimeError(f"codetop companies failed: {e}") from e
    if not isinstance(comps, list):
        raise RuntimeError("codetop companies: unexpected payload")
    ids = {c.get("name"): c.get("id") for c in comps
           if isinstance(c, dict) and c.get("name") in CODETOP_COMPANIES}
    if not ids:
        raise RuntimeError("codetop: none of the tracked companies are present")

    merged: dict[str, dict] = {}
    for name, cid in sorted(ids.items()):
        try:
            d = http_json(f"{base}/questions/?company={cid}&page=1&page_size=20", cfg=cfg,
                          headers={"Accept": "application/json"})
        except Exception as e:
            log(f"    codetop {name}: {e}", "warn")
            continue
        for row in (d.get("list") or []):
            lc = row.get("leetcode") or {}
            qid = lc.get("frontend_question_id") or lc.get("question_id")
            title = clean_text(lc.get("title") or "", 200)
            if not qid or not title:
                continue
            rec = merged.setdefault(str(qid), {
                "qid": str(qid), "title": title, "level": lc.get("level"),
                "slug": lc.get("slug_title") or "", "companies": [],
            })
            rec["companies"].append({
                "name": name, "value": int(row.get("value") or 0),
                "lastSeen": str(row.get("time") or "")[:10],
            })
        time.sleep(max(0.5, float((cfg.get("http") or {}).get("delayBetween", 0.4))))

    pool = sorted(merged.values(),
                  key=lambda r: -max((c["value"] for c in r["companies"]), default=0))
    if not pool:
        raise RuntimeError("codetop: no questions collected")
    day_index = int(now_cst().strftime("%j"))
    start = (day_index * max(1, limit)) % len(pool)
    window = (pool[start:] + pool[:start])[:limit]

    out = []
    for rec in window:
        comps_sorted = sorted(rec["companies"], key=lambda c: -c["value"])
        top = comps_sorted[0]
        total = sum(c["value"] for c in comps_sorted)
        last_seen = max((c.get("lastSeen") or "" for c in comps_sorted), default="")
        lvl = {1: "简单", 2: "中等", 3: "困难"}.get(rec.get("level"), "")
        bits = [f"{c['name']} {c['value']} 次" for c in comps_sorted[:6]]
        out.append({
            "sourceId": "codetop", "channel": "codetop",
            "externalId": rec["qid"],
            "title": f"{rec['title']}（LeetCode {rec['qid']}）· 大厂高频手撕题",
            "summary": clean_text(
                "被大厂真实考过的高频手撕题：" + "、".join(bits)
                + (f"（共 {total} 次）" if total else "")
                + (f"；难度 {lvl}" if lvl else "")
                + f"；最近一次出现 {last_seen}" if last_seen else "", 600),
            "summarySource": "codetop-api",
            "url": (f"https://leetcode.cn/problems/{rec['slug']}/" if rec.get("slug")
                    else f"https://leetcode.cn/problemset/"),
            "publishedAt": parse_ts(last_seen) and iso(parse_ts(last_seen)) or None,
            "tags": ["leetcode", "手撕", "算法题", "高频面试题"] + [c["name"] for c in comps_sorted[:3]],
            "lang": "zh",
            "codeAvailable": False,
            "qualitySignals": {"topValue": top["value"], "totalValue": total,
                               "companyCount": len(comps_sorted), "difficulty": lvl,
                               "source": "codetop"},
        })
    log(f"codetop companies={len(ids)} pool={len(pool)} window={start}.. -> {len(out)}")
    return out


COLLECTORS = {
    "arxiv": collect_arxiv, "hf_papers": collect_hf_papers, "hf_models": collect_hf_models,
    "github": collect_github, "gh_trending": collect_gh_trending,
    "openreview": collect_openreview, "s2": collect_s2, "hn": collect_hn, "reddit": collect_reddit,
    "machineheart": collect_machineheart, "qbitai": collect_qbitai, "leiphone": collect_leiphone,
    "hf_blog_rss": collect_hf_blog_rss, "openai_rss": collect_openai_rss,
    "rsshub": collect_rsshub, "zhihu": collect_zhihu, "nowcoder": collect_nowcoder,
    "programmercarl": collect_programmercarl, "kamacoder_notes": collect_kamacoder_notes,
    "xiaolincoding": lambda cfg, log, limit: _collect_kb_site("xiaolincoding", cfg, log, limit),
    "gh_algokb": collect_gh_algokb, "codetop": collect_codetop,
    "jobs_bytedance": collect_jobs_bytedance, "jobs_tencent": collect_jobs_tencent,
    "jobs_alibaba": collect_jobs_alibaba, "jobs_zhipu": collect_jobs_zhipu,
    "jobs_moonshot": collect_jobs_moonshot, "jobs_deepseek": collect_jobs_deepseek,
    "jobs_minimax": collect_jobs_minimax, "jobs_shailab": collect_jobs_shailab,
    "inbox": collect_inbox,
}


# ============================================================================
# 5. CONFIG
# ============================================================================
def deep_merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: Path, log: Logger) -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))          # deep copy
    cats = json.loads(json.dumps(DEFAULT_CATEGORIES))
    if path.exists():
        try:
            user = json.loads(path.read_text("utf-8"))
            user_cats = user.pop("categories", {}) or {}
            for cid, c in user_cats.items():
                if cid in cats:
                    merged = dict(cats[cid])
                    merged.update({k: v for k, v in c.items() if k != "keywords"})
                    extra = [k for k in (c.get("keywords") or []) if k not in merged.get("keywords", [])]
                    merged["keywords"] = list(merged.get("keywords", [])) + extra
                    # keywordRemove lets the self-tuning pass DELETE a built-in
                    # keyword. The list above can only ever append, so without an
                    # explicit removal channel a keyword proven to be too broad
                    # ("review", "theory") could never be retired.
                    rm = {str(k).lower() for k in (c.get("keywordRemove") or [])}
                    if rm:
                        merged["keywords"] = [k for k in merged["keywords"] if str(k).lower() not in rm]
                    cats[cid] = merged
                else:
                    cats[cid] = c
            cfg = deep_merge(cfg, user)
            log(f"config loaded: {path}")
        except Exception as e:
            log(f"config parse failed, using defaults: {e}", "warn")
    else:
        log(f"config not found at {path}, using built-in defaults", "warn")
    cfg["categories"] = cats
    for c in cfg["categories"].values():
        c["keywords"] = [str(k).lower() for k in (c.get("keywords") or [])]
    return cfg


def save_default_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), "utf-8")


# ============================================================================
# 6. CLASSIFY + SCORE
# ============================================================================
def _kw_match(kw: str, text: str) -> bool:
    """Does `kw` appear in `text` as a real token rather than a substring?

    WHY THIS MATTERS (a real classification defect, found by the deep-read agent):
    the classifier used plain substring containment, so short English keywords
    matched unrelated words inside longer ones and dragged nonsense into the corpus:

        'dit'    matched  audit, traditional, conditions
        'intern' matched  international, internal
        'ppo'    matched  Opportunities
        'review' matched  reviewed, preview
        '基础'   matched  BYD/Guoxuan battery-industry news (a real substring, but
                          irrelevant to the 'foundation' ML category)

    Evidence from one run: an education-assessment paper and a psychiatry survey
    were scored into 'generative', a UN speech into 'job', a law white-paper ranked
    FIRST in 'rl'. Cleaning that up by hand was a daily chore.

    Rule: keywords containing only ASCII word characters are matched on word
    boundaries. Keywords containing CJK (or punctuation) keep substring matching,
    because Chinese has no word boundaries and '多模态' must match inside
    '多模态大模型'. Short ASCII keywords (<4 chars) also require a boundary, which
    is exactly the 'dit'/'ppo' case.
    """
    if not kw:
        return False
    if not kw.isascii():
        return kw in text
    # Escape the keyword, then require non-word characters (or the string edges).
    return re.search(r"(?<![0-9a-z])" + re.escape(kw) + r"(?![0-9a-z])", text) is not None


def classify(item: dict, cfg: dict):
    blob = " ".join([str(item.get("title") or ""), str(item.get("summary") or ""),
                     " ".join(item.get("tags") or []), str(item.get("venue") or "")]).lower()
    title_blob = str(item.get("title") or "").lower()
    interests = cfg.get("interests") or {}
    scores, hits = {}, {}
    for cid, c in cfg["categories"].items():
        w = float(c.get("weight", 0.8)) * float(interests.get(cid, 0.8))
        sc, h = 0.0, []
        for kw in c.get("keywords") or []:
            if not kw:
                continue
            if _kw_match(kw, title_blob):
                sc += 3.0
                h.append(kw)
            elif _kw_match(kw, blob):
                sc += 1.0
                h.append(kw)
        for ac in (c.get("arxiv") or []):
            if ac and ac in (item.get("tags") or []):
                sc += 1.5
        if sc > 0:
            scores[cid] = sc * w
            hits[cid] = h
    if not scores:
        # Zero keyword hits. Previously this silently became "trend", which is how
        # a grammar/pragmatics paper with an EMPTY categoryHits ended up in the
        # trend queue. A weak match on nothing is not a trend - it is unclassified.
        return "unclassified", []
    best = max(scores.items(), key=lambda kv: (kv[1], kv[0]))
    return best[0], (hits.get(best[0]) or [])[:12]


def score_item(item, cfg, tier, cat_hits):
    sc = cfg.get("scoring") or {}
    parts = {}
    parts["category"] = min(40.0, 8.0 * len(cat_hits))
    # An item that matched NO category keyword already loses the whole 40-point
    # category component (len(cat_hits) == 0). Apply one more explicit penalty so
    # unclassified items rank below every genuinely classified item instead of
    # merely tying with the weakest matches. They stay searchable, but they cannot
    # crowd the dashboard or the digest.
    if not cat_hits:
        parts["unclassified"] = -12.0

    hl = float(sc.get("freshnessHalfLifeDays", 7.0))
    ts = parse_ts(item.get("publishedAt"))
    if ts and hl > 0:
        age = max(0.0, (now_cst() - ts).total_seconds() / 86400.0)
        parts["freshness"] = 30.0 * (0.5 ** (age / hl))
    else:
        parts["freshness"] = 6.0

    parts["source"] = 12.0 * float((sc.get("sourceTierWeight") or {}).get(tier, 0.7))

    q = item.get("qualitySignals") or {}
    boost = float(sc.get("qualityBoost", 8.0))
    qs = 0.0
    if item.get("peerReviewed"):
        qs += boost
    stars = item.get("stars") or q.get("stars") or 0
    if stars:
        qs += min(boost, 0.8 * (float(stars) ** 0.5))
    up = item.get("upvotes") or q.get("upvotes") or 0
    if up:
        qs += min(boost * 0.75, float(up) ** 0.65 / 2.0)
    if item.get("codeAvailable") or q.get("codeAvailable"):
        qs += 2.0
    parts["quality"] = min(boost * 2.2, qs)

    parts["content"] = min(9.0, len(str(item.get("summary") or "")) / 220.0 * 9.0)

    # --- knowledge-quality component ---------------------------------------
    # The reader asked explicitly: do not let something in just because it is
    # "the latest" or "related". Recency already has its own 30-point component
    # above; this one answers a different question - "is this ACCUMULABLE
    # knowledge?" - using the shared judgement in knowledge_quality.py.
    #
    # materiality 0.5 is the neutral point: above adds, below subtracts, and the
    # amplitude lives in collector.config.json (`knowledge.scoreMaterialityWeight`)
    # so the policy can be retuned without touching the scoring code.
    if KQ is not None:
        mat = item.get("materiality")
        if mat is None:
            mat = KQ.materiality(item)
        w = float(KQ_POLICY.get("scoreMaterialityWeight", 10.0))
        parts["materiality"] = round(w * (float(mat) - 0.5), 1)
        if (item.get("kind") or "") == "news":
            parts["ephemeral"] = -float(KQ_POLICY.get("scoreEphemeralPenalty", 8.0))

        # --- 求职可用性分量 -------------------------------------------------
        # 读者要求：「把手撕算法、各领域核心工作或问题等求职面试能直接用上的信息
        # 提高采集优先级」。相关度回答的是「和我的方向有没有关系」，材料性回答的是
        # 「能不能积累」，都不回答「离面试有多近」—— 所以再加这一个。
        #
        # 实测为什么要加：codetop 的高频手撕题摘要只有一行「百度 16 次、阿里巴巴
        # 12 次…」的元数据，材料性只有 0.5 上下，相关度也吃不满；不补这一分量时
        # 它会排在一篇摘要很长的外围论文后面，而它恰恰是最该先深读的东西。
        # 幅度由 config 的 `knowledge.scoreCareerWeight` 控制，改口径不用改代码。
        parts["career"] = round(
            float(KQ_POLICY.get("scoreCareerWeight", 15.0)) * KQ.career_usability(item), 1)

    # --- knowledge-base reference material ---------------------------------
    # 代码随想录 / 卡码笔记 / 算法题解仓库 publish a fixed, growing knowledge base:
    # a 2021 题解 is exactly as useful today as a 2026 one. This material must NOT
    # be scored by the feed rule "newer is better", so it gets its own component
    # instead of having the freshness number silently fudged. It is capped and
    # tunable (`scoring.knowledgeBaseBoost`) - the per-channel and per-category
    # intake caps still decide how much of it can land in one run.
    if (CHANNEL_SPECS.get(item.get("channel")) or {}).get("knowledgeBase"):
        parts["knowledgeBase"] = float(sc.get("knowledgeBaseBoost", 22.0))

    total = sum(parts.values())
    if item.get("lang") == "zh":
        total *= 1.04
    return round(min(100.0, total), 1), {k: round(v, 1) for k, v in parts.items()}


def explain(item, hits, cfg):
    """'Why it matters' is composed ONLY from observed signals, never inferred."""
    czh = (cfg["categories"].get(item.get("category")) or {}).get("zh", "综合趋势")
    bits = []
    if item.get("kind"):
        bits.append("类型：" + KQ.KIND_ZH.get(item["kind"], item["kind"]))
    if hits:
        bits.append("命中关键词 " + "、".join(hits[:5]))
    if item.get("peerReviewed"):
        bits.append(f"同行评审 ({item.get('venue') or 'conference'})")
    if item.get("stars"):
        bits.append(f"GitHub {item['stars']} stars")
    if item.get("upvotes"):
        bits.append(f"社区热度 {item['upvotes']}")
    if item.get("codeAvailable"):
        bits.append("疑似附带开源实现")
    if item.get("lang") == "zh":
        bits.append("中文来源，贴近国内求职语境")
    return f"归属「{czh}」方向" + ("；" + "；".join(bits) if bits else "；待人工复核相关性")


# ============================================================================
# 7. NORMALIZE + DEDUPE
# ============================================================================
def _sources_of(item):
    srcs = []
    if item.get("url"):
        srcs.append({"url": item["url"], "name": item.get("sourceId") or item.get("channel")})
    if item.get("canonicalUrl") and item["canonicalUrl"] != item.get("url"):
        srcs.append({"url": item["canonicalUrl"], "name": "canonical"})
    return srcs


def normalize(raw, cfg, tier):
    if not isinstance(raw, dict):
        return None
    title = clean_text(raw.get("title") or "", 400)
    if not title:
        return None
    url = canonical_url(raw.get("url") or "")
    canon = canonical_url(raw.get("canonicalUrl") or "")
    if not url and not canon:
        return None
    item = {
        "sourceId": raw.get("sourceId") or raw.get("channel") or "unknown",
        "channel": raw.get("channel") or raw.get("sourceId") or "unknown",
        "externalId": str(raw.get("externalId") or title_key(title)),
        "title": title,
        "summary": clean_text(raw.get("summary") or "", 2000),
        "url": url or canon,
        "canonicalUrl": canon or None,
        "authors": [clean_text(a, 80) for a in (raw.get("authors") or []) if a][:14],
        "publishedAt": raw.get("publishedAt"),
        "fetchedAt": iso(now_cst()),
        "lang": raw.get("lang") or ("zh" if re.search(r"[\u4e00-\u9fff]", title) else "en"),
        "tags": [clean_text(t, 40) for t in (raw.get("tags") or []) if t][:12],
        "venue": raw.get("venue") or None,
        "ccf": raw.get("ccf") or None,
        "peerReviewed": bool(raw.get("peerReviewed")),
        "codeAvailable": bool(raw.get("codeAvailable") or (raw.get("qualitySignals") or {}).get("codeAvailable")),
        "stars": raw.get("stars"),
        "upvotes": raw.get("upvotes"),
        "qualitySignals": raw.get("qualitySignals") or {},
        "difficulty": raw.get("difficulty"),
        "collectorVersion": COLLECTOR_VERSION,
        "contentHash": sha1(f"{title}|{raw.get('summary') or ''}")[:16],
    }
    item["id"] = stable_id(item["sourceId"], item["externalId"])
    cat, hits = classify(item, cfg)
    item["category"] = cat
    item["categoryHits"] = hits
    # Knowledge type / materiality / direction fit. Computed BEFORE scoring so the
    # score can use them, and stored on the item so the deep-read planner, the
    # pruner, the self-check and the UI all read the same judgement instead of
    # each re-deriving it with their own rules.
    if KQ is not None:
        item["kind"] = KQ.classify_kind(item)
        item["materiality"] = KQ.materiality(item, item["kind"])
        item["directionFit"] = KQ.direction_fit(item)
        _flags = KQ.noise_ids(item)
        if _flags:
            item["qualityFlags"] = _flags
    # Stamp reference material so every consumer can tell a knowledge-base card from
    # a feed card without re-deriving it. Their summaries are short BY CONSTRUCTION
    # (a 题解 page's meta description is one sentence; a CodeTop card is metadata),
    # so measuring "thin cards" over both populations at once is meaningless.
    if (CHANNEL_SPECS.get(item.get("channel")) or {}).get("knowledgeBase"):
        item["knowledgeBase"] = True
    rel, breakdown = score_item(item, cfg, tier, hits)
    item["relevanceScore"] = rel
    item["relevanceBreakdown"] = breakdown
    item["sources"] = _sources_of(item)
    item["why"] = explain(item, hits, cfg)
    return item


class Deduper:
    """Layered de-duplication: stable id -> canonical url -> title -> simhash."""

    def __init__(self, state, cfg):
        d = cfg.get("dedupe") or {}
        self.bits = int(d.get("simhashBits", 64))
        self.threshold = int(d.get("hammingThreshold", 3))
        self.by_key = state.setdefault("byKey", {})
        self.by_url = state.setdefault("byUrl", {})
        self.by_title = state.setdefault("byTitle", {})
        self.hashes = state.setdefault("hashes", [])

    def lookup(self, item):
        uid = f"{item.get('sourceId')}::{item.get('externalId')}"
        if uid in self.by_key:
            return self.by_key[uid]
        cu = item.get("canonicalUrl") or item.get("url") or ""
        if cu and cu in self.by_url:
            return self.by_url[cu]
        tk = title_key(item.get("title") or "")
        if tk and tk in self.by_title:
            return self.by_title[tk]
        h = simhash(f"{item.get('title')} {item.get('summary')}"[:1500], self.bits)
        item["_simhash"] = h
        if h:
            for other, cid in self.hashes:
                if hamming(h, other) <= self.threshold:
                    return cid
        return None

    def register(self, item, canonical_id):
        self.by_key[f"{item.get('sourceId')}::{item.get('externalId')}"] = canonical_id
        cu = item.get("canonicalUrl") or item.get("url") or ""
        if cu:
            self.by_url[cu] = canonical_id
        tk = title_key(item.get("title") or "")
        if tk:
            self.by_title[tk] = canonical_id
        h = item.pop("_simhash", None) or simhash(
            f"{item.get('title')} {item.get('summary')}"[:1500], self.bits)
        if h:
            self.hashes.append([h, canonical_id])

    def prune(self, max_entries=40000):
        if len(self.hashes) > max_entries:
            self.hashes = self.hashes[-max_entries:]
        for store, cap in ((self.by_key, 60000), (self.by_url, 60000), (self.by_title, 60000)):
            if len(store) > cap:
                for k in list(store.keys())[:len(store) - cap]:
                    store.pop(k, None)


def merge_duplicate(existing, incoming):
    """Same content seen on several channels: keep the richest field, keep all sources."""
    out = dict(existing)
    for field in ("title", "summary"):
        if len(str(incoming.get(field) or "")) > len(str(out.get(field) or "")):
            out[field] = incoming[field]
    for field in ("authors", "tags"):
        merged = list(dict.fromkeys(list(out.get(field) or []) + list(incoming.get(field) or [])))
        if merged:
            out[field] = merged[:16]
    qs = dict(out.get("qualitySignals") or {})
    for k, v in (incoming.get("qualitySignals") or {}).items():
        if isinstance(v, (int, float)) and isinstance(qs.get(k), (int, float)):
            qs[k] = max(qs[k], v)
        else:
            qs.setdefault(k, v)
    if qs:
        out["qualitySignals"] = qs
    out["peerReviewed"] = bool(out.get("peerReviewed") or incoming.get("peerReviewed"))
    out["codeAvailable"] = bool(out.get("codeAvailable") or incoming.get("codeAvailable"))
    srcs = list(out.get("sources") or [])
    have = {s.get("url") for s in srcs}
    for s in _sources_of(incoming):
        if s.get("url") and s["url"] not in have:
            srcs.append(s)
            have.add(s["url"])
    out["sources"] = srcs[:6]
    if incoming.get("publishedAt") and (not out.get("publishedAt")
                                       or incoming["publishedAt"] < out["publishedAt"]):
        out["publishedAt"] = incoming["publishedAt"]
    out["mergedFrom"] = list(dict.fromkeys(list(out.get("mergedFrom") or []) + [incoming.get("sourceId")]))
    out["updatedAt"] = iso(now_cst())
    return out


# ============================================================================
# 8. STORAGE
# ============================================================================
def atomic_write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    pretty = path.name == "runs.json"
    data = json.dumps(payload, ensure_ascii=False,
                      indent=1 if pretty else None,
                      separators=None if pretty else (",", ":"))
    tmp.write_text(data, "utf-8")
    if tmp.stat().st_size < 2:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"refusing to write a suspiciously small file: {path}")
    os.replace(tmp, path)          # atomic on the same volume


def read_json(path: Path, fallback):
    try:
        if path.exists():
            return json.loads(path.read_text("utf-8"))
    except Exception:
        pass
    return fallback


def refresh_kq_fields(item, cfg=None, rescore=False):
    """Recompute the knowledge-quality judgement (kind / materiality / flags) on an item.

    WHY this runs over the WHOLE corpus every day, not only on freshly fetched items:
    these fields are *derived*, not observed. When a rule changes - today: news channels
    now classify as `news`, and paid-guide / download-bait are hard-drop - the stored
    value on thousands of older cards would stay stale. Measured before this pass:
    `ingest_reject()` (which recomputes) and the published index (which stores) disagreed
    about the same card, because the index still said `kind: notes` for items that are
    now `news`. That is exactly the "same card, three conclusions" drift
    knowledge_quality.py exists to prevent, so the refresh belongs on the daily path.

    `rescore=True` also recomputes relevanceScore. Needed whenever the judgement feeds
    the score (it does: materiality and the new career component), otherwise "raise the
    priority of interview-usable content" would only apply to cards collected after the
    change and the existing library would keep the old ranking forever.
    """
    if KQ is None:
        return item
    item["kind"] = KQ.classify_kind(item)
    item["materiality"] = KQ.materiality(item, item["kind"])
    item["directionFit"] = KQ.direction_fit(item)
    _flags = KQ.noise_ids(item)
    if _flags:
        item["qualityFlags"] = _flags
    else:
        item.pop("qualityFlags", None)
    if (CHANNEL_SPECS.get(item.get("channel")) or {}).get("knowledgeBase"):
        item["knowledgeBase"] = True
    else:
        item.pop("knowledgeBase", None)
    if rescore and cfg is not None:
        spec = CHANNEL_SPECS.get(item.get("sourceId"),
                                 CHANNEL_SPECS.get(item.get("channel"), {"tier": "P2"}))
        rel, breakdown = score_item(item, cfg, spec.get("tier", "P2"),
                                    item.get("categoryHits") or [])
        item["relevanceScore"] = rel
        item["relevanceBreakdown"] = breakdown
    return item


def build_all_items(state, fresh, cfg=None):
    canonical = state.get("canonical") or {}
    merged = dict(canonical)
    for item in fresh:
        merged[item["id"]] = {**merged.get(item["id"], {}), **item}
    keep = ("id", "sourceId", "channel", "externalId", "category", "title", "summary",
            # summarySource records HOW a summary was obtained (feed vs page meta
            # tag). Without it in this whitelist the provenance was silently
            # dropped on every rebuild, so nothing could tell an original abstract
            # from a backfilled description.
            "summarySource",
            # relevanceBreakdown exposes WHY an item scored what it did, including
            # the learning-signal bonus. It must survive the rebuild or the ranking
            # change is invisible and unauditable.
            "relevanceBreakdown",
            "keyPoints", "why", "url", "canonicalUrl", "sources", "authors", "publishedAt",
            "fetchedAt", "lang", "tags", "entities", "difficulty", "relevanceScore",
            # Knowledge-quality judgement (scripts/knowledge_quality.py): what KIND of
            # content this is (paper / repo / interview / problem / notes / job /
            # news), how durable its knowledge is, and how well it fits the target
            # directions. Published so the UI, the self-check and the proposals all
            # reason about the corpus with the same numbers.
            "kind", "materiality", "directionFit", "qualityFlags", "knowledgeBase",
            "qualitySignals", "venue", "ccf", "peerReviewed", "codeAvailable", "stars",
            "upvotes", "firstSeen", "lastSeen", "contentHash", "categoryHits")
    # Honour the blocklist here as well as on the ingest path.
    #
    # Two gates are needed, not one. Filtering only the incoming raw items stops
    # NEW imports, but state["canonical"] already holds whatever was imported
    # before, so items that slipped in during an earlier run would stay published
    # forever. Rebuilding from `canonical` is exactly how that happened: the
    # library sat at 763 with 209 human-removed items still listed.
    blocked_ids = set(state.get("blockedIds") or [])
    # Drop `unclassified` items from the published corpus.
    #
    # WHY: an item with an empty `categoryHits` matched NO keyword for any tracked
    # direction, so it cannot serve any of them - measured, that bucket is off-topic
    # news (BYD industry pieces, a chemistry response model, a location-tracking CLI,
    # Cursor plugin specs, EU AI Act commentary). The reader asked explicitly for
    # "no news unrelated to job-hunting, interview prep or real technical topics", and
    # these were 85 of 720 items while also being 11.8% of all attention.
    #
    # They are dropped from the OUTPUT only, not from `state["canonical"]`. That
    # matters: if keywords improve later, `--rescore` reclassifies the stored items
    # and the good ones come back automatically. The cost of keeping them in state is
    # a few hundred KB, which is cheap insurance against an irreversible decision.
    drop_unclassified = bool((((cfg or {}).get("limits")) or {}).get("dropUnclassified", True))
    out = []
    for item in merged.values():
        if blocked_ids and item.get("id") in blocked_ids:
            continue
        if drop_unclassified and item.get("category") == "unclassified":
            continue
        # Keep the derived judgement in step with the current rules (see
        # refresh_kq_fields): without this, a rule change leaves thousands of older
        # cards with stale kind/materiality/score and the whole "one authority"
        # contract silently breaks.
        refresh_kq_fields(item, cfg, rescore=True)
        row = {k: item.get(k) for k in keep if item.get(k) is not None}
        row.setdefault("sources", [])
        row["date"] = str(item.get("firstSeen") or item.get("fetchedAt") or "")[:10]
        out.append(row)
    out.sort(key=lambda x: -(x.get("relevanceScore") or 0))
    return out


def compute_stats(items):
    by_cat, by_ch = {}, {}
    for i in items:
        by_cat[i.get("category", "trend")] = by_cat.get(i.get("category", "trend"), 0) + 1
        by_ch[i.get("channel", "unknown")] = by_ch.get(i.get("channel", "unknown"), 0) + 1
    return {"byCategory": by_cat, "byChannel": by_ch,
            "zhShare": round(sum(1 for i in items if i.get("lang") == "zh") / max(1, len(items)), 3)}


# ============================================================================
# 9. RUN
# ============================================================================
# Ordering for the human-facing channel table: things that worked first, then
# empty, then broken, then blocked, then never-verified.
STATE_RANK = {"ok": 0, "partial": 1, "empty": 2, "error": 3, "parse_error": 4,
              "blocked": 5, "unknown": 6}
TIER_RANK = {"P0": 0, "P1": 1, "P2": 2, "MANUAL": 3}


def write_proposals(cfg, results, fresh, all_items, log) -> dict:
    """Deterministic self-iteration output.

    The LLM deep-read layer can write richer proposals, but it needs a
    credential and is therefore optional. This function makes the
    observe -> propose step unconditional: every run leaves a reviewable file
    containing only *mechanically derived* suggestions (no model inference, no
    guesses). A human still approves anything before it takes effect.

    Signals used (all observable without an LLM):
      * channels that keep failing / are blocked / returned parse errors
      * categories that received no items at all
      * categories that got items historically but none this run
      * configured keywords that never hit anything (dead weight)
      * source hosts outside the known-host list (possible junk ingestion)
    """
    proposals_dir = DATA_DIR / "proposals"
    day = date_key(now_cst())

    runs = read_json(RUNS_PATH, [])
    if not isinstance(runs, list):
        runs = []
    fail_streak: dict = {}
    for r in runs[:8]:
        for part in str(r.get("notes") or "").split(";"):
            part = part.strip()
            m = re.match(r"^([\w\-]+)=(error|blocked|parse_error|empty)$", part)
            if m and m.group(2) in ("error", "blocked", "parse_error"):
                fail_streak[m.group(1)] = fail_streak.get(m.group(1), 0) + 1

    channel_health = []
    for cid, rec in sorted(results.items()):
        status = str(rec.get("status"))
        if status == "ok":
            continue
        streak = fail_streak.get(cid, 0) + (1 if status in ("error", "blocked", "parse_error") else 0)
        action = {
            "blocked": "确认是否已被反爬或已下线；如需继续，改为人工导入或寻找替代源",
            "error": "检查接口变更或凭据；连续 3 次失败应降级到备用源",
            "parse_error": "响应格式变了，需要更新解析逻辑（这是我们的问题，不是站点的问题）",
            "empty": "查询式可能过窄，考虑放宽关键词或时间窗口",
        }.get(status, "人工复核")
        channel_health.append({
            "id": cid, "nameZh": rec.get("nameZh") or cid, "status": status,
            "streak": streak, "lastError": rec.get("error"),
            "suggestedAction": action, "escalate": streak >= 3,
        })
    channel_health.sort(key=lambda c: (-int(c["escalate"]), -c["streak"], c["id"]))

    got: dict = {}
    for it in all_items:
        got[it.get("category")] = got.get(it.get("category"), 0) + 1
    got_fresh: dict = {}
    for it in fresh:
        got_fresh[it.get("category")] = got_fresh.get(it.get("category"), 0) + 1
    # 有些分类「为空」是**设计如此**，不是缺陷，不该每天出现在待办里：
    #   · unclassified —— dropUnclassified 开启时它必须为空，非空才是有问题；
    #   · paper / trend —— 泛化兜底桶。真正方向内的论文会被 multimodal /
    #     posttraining / generative / worldmodel 接走；它们空着说明分类健康。
    # 只有「有实质意义的方向分类」为空才值得人看（例如 exam 长期为空 = 采集盲区）。
    by_design_empty = {"unclassified", "paper", "trend"}
    empty_categories = [cid for cid in cfg["categories"]
                        if not got.get(cid) and cid not in by_design_empty]
    quiet_categories = [cid for cid in cfg["categories"] if got.get(cid) and not got_fresh.get(cid)]

    hits_counter: dict = {}
    for it in all_items:
        for kw in (it.get("categoryHits") or []):
            hits_counter[kw] = hits_counter.get(kw, 0) + 1
    dead_keywords: dict = {}
    for cid, c in cfg["categories"].items():
        kws = c.get("keywords") or []
        dead = [k for k in kws if k not in hits_counter and len(k) > 4]
        if dead and len(dead) > max(3, len(kws) // 2):
            dead_keywords[cid] = dead[:15]

    suspicious_hosts: dict = {}
    for it in all_items:
        h = urllib.parse.urlsplit(it.get("url") or "").netloc.lower().replace("www.", "")
        if h and not any(h == k or h.endswith("." + k) for k in KNOWN_HOSTS):
            suspicious_hosts[h] = suspicious_hosts.get(h, 0) + 1
    suspicious_hosts = dict(sorted(suspicious_hosts.items(), key=lambda kv: -kv[1])[:12])

    # ------------------------------------------------------------------
    # New-channel proposals.
    #
    # This field existed but was hardcoded to an empty list, so the workbench could
    # never propose a new source - the "channel-add" rule in the design (a domain
    # that keeps showing up in manual imports but is not collected automatically)
    # had no implementation.
    #
    # Signal used: domains that appear in HUMAN-IMPORTED items (channel == "inbox")
    # and are not in KNOWN_HOSTS. That is the strongest available evidence that a
    # source is worth collecting: the reader went and fetched it by hand, 5+ times.
    # Nothing is fetched or enabled automatically - this only produces a proposal
    # that the deep-read agent verifies (API/RSS availability, robots.txt) before a
    # human approves it.
    # ------------------------------------------------------------------
    new_channel_proposals = []
    try:
        imported_hosts: dict = {}
        for it in all_items:
            if it.get("channel") != "inbox":
                continue
            h = urllib.parse.urlsplit(it.get("url") or "").netloc.lower().replace("www.", "")
            if not h:
                continue
            if any(h == k or h.endswith("." + k) for k in KNOWN_HOSTS):
                continue
            rec = imported_hosts.setdefault(h, {"count": 0, "samples": [], "categories": {}})
            rec["count"] += 1
            if len(rec["samples"]) < 3:
                rec["samples"].append(str(it.get("title") or "")[:90])
            c = it.get("category") or "trend"
            rec["categories"][c] = rec["categories"].get(c, 0) + 1
        for h, rec in sorted(imported_hosts.items(), key=lambda kv: -kv[1]["count"]):
            if rec["count"] < 5:
                continue
            top_cat = max(rec["categories"].items(), key=lambda kv: kv[1])[0]
            new_channel_proposals.append({
                "domain": h,
                "importedCount": rec["count"],
                "dominantCategory": top_cat,
                "sampleTitles": rec["samples"],
                "suggestedMode": "rss-or-api",
                "reason": (f"你手工导入了 {rec['count']} 条来自 {h} 的内容，但它不在采集渠道里。"
                           f"若该站 robots.txt 允许且有 RSS/API，建议加入渠道自动采集。"),
                "requiresHumanApproval": True,
                "verificationSteps": [
                    "检查 robots.txt 是否允许抓取",
                    "确认是否有官方 RSS 或公开 API（优先）",
                    "若无 API/RSS，评估 HTML 解析的稳定性与限速要求",
                    "批准后在 CHANNEL_SPECS 与 config 中登记，并跑一次 --probe 实测",
                ],
            })
    except Exception as e:
        log(f"new-channel proposal scan failed: {e}", "warn")

    # ------------------------------------------------------------------
    # Knowledge-quality proposals (the "self-organising" half of self-iteration).
    #
    # WHY: the deep-read agent can propose keyword changes, but it needs a
    # credential and runs only when configured. The reader's core requirement -
    # "the library should be accumulating core/algorithm/interview/八股 knowledge,
    # not just whatever is newest" - must be MEASURED and acted on every day, even
    # on a run where the LLM layer is skipped.
    #
    # What it derives deterministically:
    #   * channels whose output is mostly news / low-signal -> propose demotion
    #     (channel tier changes need human approval)
    #   * knowledge kinds that are under-accumulating (手撕题 / 八股 / 面经) -> these
    #     become keyword proposals, which ARE the one auto-applicable change class
    #   * target directions whose items are mostly news rather than knowledge
    # ------------------------------------------------------------------
    queue: list = []
    kq_summary: dict = {}
    quality_channel_proposals: list = []
    kind_gap: list = []
    try:
        if KQ is not None:
            enrich = read_json(DATA_DIR / "enrichment.json", {}) or {}
            kq = KQ.quality_report(all_items, enrich.get("byId") or {})
            kq_summary = {
                "byKind": kq["byKind"],
                "kindShare": kq["kindShare"],
                "materiality": kq["materiality"],
                "newsShare": kq["newsShare"],
                "lowSignalShare": kq["lowSignalShare"],
                "offDirectionShare": kq.get("offDirectionShare"),
                "career": kq["career"],
                "directions": kq["directions"],
            }
            for row in kq["channelQuality"]:
                # 5 is deliberate: a channel with only 7 items that are 100% boilerplate
                # (the hf_blog RSS feed returns the site tagline as every summary) is a
                # real defect worth surfacing, and it would be hidden by a threshold of 8.
                if row["total"] < 5:
                    continue
                # Knowledge bases are reference material: their summaries are short
                # meta descriptions by nature, so "low signal" is expected and
                # proposing to demote them would contradict why they were added.
                if (CHANNEL_SPECS.get(row["channel"]) or {}).get("knowledgeBase"):
                    continue
                # A channel that is already switched off cannot be demoted further.
                if (CHANNEL_SPECS.get(row["channel"]) or {}).get("disabled") \
                        or row["channel"] in DISABLED_CHANNELS:
                    continue
                bad = row["newsShare"] + row["lowSignalShare"]
                if bad < 60:
                    continue
                quality_channel_proposals.append({
                    "id": row["channel"],
                    "totalItems": row["total"],
                    "newsShare": row["newsShare"],
                    "lowSignalShare": row["lowSignalShare"],
                    "suggestedAction": "降级到 P2，或收窄该渠道的抓取范围（只取高材料性内容）",
                    "reason": (f"{row['channel']} 的产出里 {row['newsShare']}% 是资讯、"
                               f"{row['lowSignalShare']}% 是低材料性内容，"
                               f"对本工作台的知识积累贡献很低"),
                    "requiresHumanApproval": True,
                })
            # 求职知识资产的缺口 -> 直接给关键词建议（唯一允许自动生效的一类改动）
            kind_kw = {
                "problem": {"category": "coding",
                            "add": ["题解", "leetcode", "hot 100", "手撕代码", "算法题解",
                                    "笔试真题", "编程题"]},
                "notes": {"category": "exam",
                          "add": ["八股", "面试高频", "知识点总结", "原理详解",
                                  "面经八股", "常见问题"]},
                "interview": {"category": "coding",
                              "add": ["一面", "二面", "三面", "面试复盘", "面试记录"]},
            }
            for kind, target in kind_kw.items():
                n = int((kq["career"] or {}).get(kind, 0))
                if n >= 8:
                    continue
                kind_gap.append({
                    "kind": kind, "kindZh": KQ.KIND_ZH.get(kind, kind),
                    "currentCount": n, "target": 8,
                    "category": target["category"],
                    "proposedKeywords": target["add"],
                    "reason": (f"「{KQ.KIND_ZH.get(kind, kind)}」只有 {n} 条，"
                               f"低于 8 条的积累下限 —— 这是采集盲区，不是内容稀缺"),
                })
                queue.append(
                    f"「{KQ.KIND_ZH.get(kind, kind)}」类内容只积累了 {n} 条（目标 ≥8）："
                    f"建议给分类 {target['category']} 补充关键词 "
                    f"{'、'.join(target['add'][:4])} 等")
            for cat, d in sorted((kq["directions"] or {}).items(),
                                 key=lambda kv: -(kv[1].get("news", 0))):
                if d["total"] < 10 or not d["news"]:
                    continue
                if d["news"] / d["total"] >= 0.25:
                    queue.append(f"分类 {cat} 有 {d['news']}/{d['total']} 条是资讯，"
                                 f"知识型内容偏少：建议收紧该方向的新闻类关键词")
    except Exception as e:
        log(f"knowledge-quality proposal scan failed: {e}", "warn")

    escalated = [c for c in channel_health if c["escalate"]]
    if escalated:
        queue.append("以下渠道已连续 3 轮以上失败，请确认是永久下线还是需要换源："
                     + "，".join(f"{c['id']}({c['status']}×{c['streak']})" for c in escalated))
    if empty_categories:
        queue.append("以下分类至今没有任何条目，请确认关键词是否过窄或渠道是否缺失："
                     + "，".join(empty_categories))
    if dead_keywords:
        queue.append("以下分类有过半关键词从未命中，建议精简或改写："
                     + "，".join(f"{k}({len(v)} 个)" for k, v in dead_keywords.items()))
    if len(suspicious_hosts) > 8:
        queue.append("出现较多未知来源域名，请抽查是否误抓：" + "，".join(list(suspicious_hosts)[:6]))

    payload = {
        "date": day,
        "generatedAt": iso(now_cst()),
        "generatedBy": "collect.py deterministic layer (no LLM required)",
        "reviewPolicy": {
            "autoApplicable": ["单个关键词权重 ≤10% 的微调"],
            "requiresHumanApproval": ["分类增删改名", "渠道增删与升降级", "评分公式与权重",
                                      "去重阈值", "blocklist", "robots.txt 状态变化"],
        },
        "channelHealth": channel_health,
        "coverage": {
            "categoriesWithItems": sorted(got.keys()),
            "categoriesEmpty": empty_categories,
            "categoriesQuietThisRun": quiet_categories,
            "byCategoryTotal": got,
            "byCategoryFresh": got_fresh,
        },
        "keywordProposals": [
            {"category": cid, "remove": kws,
             "reason": "这些关键词在全部已入库条目中从未命中，占用匹配与打分开销"}
            for cid, kws in dead_keywords.items()
        ] + [
            {"category": g["category"], "add": g["proposedKeywords"],
             "reason": g["reason"],
             "autoApplicable": True,
             "kindGap": g["kind"]}
            for g in kind_gap
        ],
        "newChannelProposals": new_channel_proposals,
        # 知识质量：库里积累的到底是什么（类型分布 / 材料性 / 方向覆盖 / 求职资产）。
        # 这张表是「每日更新」从"抓到了多少"转向"积累了什么"的度量。
        "knowledgeQuality": kq_summary,
        "channelQualityProposals": quality_channel_proposals,
        "kindGapProposals": kind_gap,
        "noiseReport": {
            "unknownHosts": suspicious_hosts,
            "unknownHostItemShare": round(sum(suspicious_hosts.values()) / max(1, len(all_items)), 3),
            "newsShare": kq_summary.get("newsShare"),
            "lowSignalShare": kq_summary.get("lowSignalShare"),
            "offDirectionShare": kq_summary.get("offDirectionShare"),
            "career": kq_summary.get("career"),
        },
        "humanReviewQueue": queue,
        "stats": {
            "totalItems": len(all_items),
            "freshThisRun": len(fresh),
            "channelsRan": len(results),
            "channelsOk": sum(1 for r in results.values() if r.get("status") == "ok"),
        },
    }

    atomic_write_json(proposals_dir / f"{day}.json", payload)
    atomic_write_json(proposals_dir / "latest.json", payload)
    if queue:
        log(f"proposals/{day}.json: {len(queue)} 条待人工复核", "warn")
    else:
        log(f"proposals/{day}.json: 无需人工介入", "ok")
    return payload


def classify_failure(exc_text: str) -> str:
    """Turn an exception repr into a status the operator can act on.

    `parse_error` exists so that "the host answered and our parser choked" is
    never confused with `empty` ("the host answered with nothing"): the first is
    our bug and must be logged as such, the second is normal for a quiet day.
    """
    low = (exc_text or "").lower()
    if any(k in low for k in ("403", "401", "451", "forbidden", "unauthorized")):
        return "blocked"
    if "429" in low or "too many requests" in low:
        return "blocked"
    if any(k in low for k in ("parseerror", "jsondecode", "not well-formed", "syntaxerror",
                              "mismatched tag", "undefined entity", "unreadable", "xml")):
        return "parse_error"
    return "error"


def build_channel_result(cid, spec, status, count, err, dur, risk_note="",
                         backup_used=None, backup_attempts=None):
    return {
        "id": cid, "nameZh": CHANNEL_NAMES.get(cid, cid), "tier": spec.get("tier", "P2"),
        "mode": spec.get("mode", "api"), "authRequired": bool(spec.get("auth")),
        "status": status, "count": count, "error": err, "durationSec": round(dur, 2),
        "backup": spec.get("backup", []),
        # `backup` above documents the alternatives; these two record what the
        # runner actually DID this pass, so the UI can show a real fallback chain
        # instead of a promise. Surviving only as a label was a genuine gap.
        "backupUsed": backup_used,
        "backupAttempts": backup_attempts or [],
        "riskNote": risk_note or None,
        "disabled": cid in DISABLED_CHANNELS,
        "checkedAt": iso(now_cst()), "lastChecked": iso(now_cst()),
    }


def collect_channels(wanted, cfg, per_channel, log):
    """Run the requested collectors, isolating every failure.

    Executes each channel's declared `backup` chain for real: when the primary
    collector raises or returns nothing, the alternatives in
    CHANNEL_SPECS[cid]["backup"] are tried in order until one yields items. That
    turns the reliability spec's "备用来源" from documentation into behaviour.
    Returns (results, raw_items).
    """
    results, raw_items = {}, []

    # Per-channel allowance. A flat cap fought the reader's stated priority: 面经 and
    # 算法题 arrive mostly through `nowcoder`, and capping it at the global 12 kept
    # `coding` at 56 items while `agent` grew to 130 - even though interview material
    # is the most perishable content here and the reader wants relatively more of it.
    # `channelIntakeOverride` lets a scarce, high-value source deliver more per run
    # without raising the global limit (which would let the bulk research feeds flood
    # the corpus again).
    overrides = cfg.get("channelIntakeOverride") or {}
    caps = {cid: int(overrides.get(cid, per_channel) or per_channel) for cid in wanted}

    def task(cid):
        t = time.time()
        attempts: list = []
        n_cap = caps.get(cid, per_channel)
        try:
            rows = COLLECTORS[cid](cfg, log, n_cap) or []
            primary_err = None
        except Exception as e:
            rows, primary_err = [], f"{type(e).__name__}: {e}"

        backup_used = None
        if not rows:
            for bid in (CHANNEL_SPECS.get(cid, {}).get("backup") or []):
                if bid not in COLLECTORS:
                    attempts.append({"id": bid, "result": "not_implemented"})
                    continue
                log(f"    {cid}: 主源无结果，尝试备用源 {bid}", "warn")
                try:
                    alt = COLLECTORS[bid](cfg, log, caps.get(bid, per_channel)) or []
                except Exception as e:                              # noqa: BLE001
                    attempts.append({"id": bid, "result": f"error: {type(e).__name__}: {e}"})
                    continue
                if alt:
                    rows = alt
                    backup_used = bid
                    attempts.append({"id": bid, "result": "ok", "count": len(alt)})
                    log(f"    {cid}: 备用源 {bid} 生效，取得 {len(alt)} 条", "ok")
                    break
                attempts.append({"id": bid, "result": "empty"})

        return cid, rows, primary_err, time.time() - t, backup_used, attempts

    with futures.ThreadPoolExecutor(max_workers=min(6, max(1, len(wanted)))) as pool:
        futs = {pool.submit(task, cid): cid for cid in wanted}
        for fut in futures.as_completed(futs):
            cid = futs[fut]
            try:
                cid, rows, err, dur, backup_used, attempts = fut.result()
            except Exception as e:                                  # noqa: BLE001
                rows, err, dur, backup_used, attempts = [], f"{type(e).__name__}: {e}", 0.0, None, []
            spec = CHANNEL_SPECS.get(cid, {"tier": "P2"})
            if err is None and rows:
                status = "ok"
            elif rows:
                # Primary failed but a backup produced items: still a success for
                # the reader, yet the log must show the degradation.
                status = "ok"
            elif err is None:
                status = "empty"
            else:
                status = classify_failure(err)
            results[cid] = build_channel_result(cid, spec, status, len(rows), err, dur,
                                                backup_used=backup_used, backup_attempts=attempts)
            label = CHANNEL_NAMES.get(cid, cid)
            via = f" [via {backup_used}]" if backup_used else ""
            if status == "ok":
                log(f"{label:<16} {len(rows):>4} items ({dur:.1f}s){via}", "ok")
            elif status == "empty":
                log(f"{label:<16} empty (host answered, no items)", "warn")
            elif status == "parse_error":
                log(f"{label:<16} PARSE ERROR (shape changed, not an empty feed): {err}", "err")
            elif status == "blocked":
                log(f"{label:<16} blocked: {err}", "err")
            else:
                log(f"{label:<16} {err}", "warn")
            raw_items += rows
    return results, raw_items


def run_probe(args) -> int:
    """--probe: one pass over the channels, print a health table, write nothing.

    WHY separate from --dry-run: --dry-run still normalizes, scores and dedupes
    the whole corpus and prints a run record; when you only want to know which
    upstream moved, that is wasted work and a lot of output. For the deep,
    evidence-carrying probe (candidate endpoints, robots.txt, regex diagnosis)
    use scripts/probe-channels.py.
    """
    log = Logger(args.verbose)
    cfg = load_config(CONFIG_PATH, log)
    if args.limit:
        cfg["limits"]["perChannel"] = args.limit
    per_channel = int(args.limit or 3)

    if args.only:
        wanted = [c.strip() for c in args.only.split(",") if c.strip() in COLLECTORS]
    else:
        wanted = [c for c, s in CHANNEL_SPECS.items() if s["mode"] != "manual"]
        wanted = [c for c in wanted if c in COLLECTORS and c not in DISABLED_CHANNELS]

    log(f"probe: {len(wanted)} channels, limit={per_channel}, nothing will be written", "step")
    results, _raw = collect_channels(wanted, cfg, per_channel, log)

    rows = []
    for cid in sorted(DISABLED_CHANNELS) if not args.only else []:
        spec = CHANNEL_SPECS.get(cid, {"tier": "P2"})
        rows.append(build_channel_result(cid, spec, "blocked", 0, None, 0.0, DISABLED_CHANNELS[cid]))
    rows += [results[c] for c in wanted if c in results]

    safe_print("")
    safe_print(f"{'channel':<18}{'status':<13}{'items':>6}{'sec':>7}  first item / error")
    safe_print("-" * 116)
    for r in sorted(rows, key=lambda x: (x["status"] != "ok", x["id"])):
        extra = r.get("error") or r.get("riskNote") or ""
        safe_print(f"{r['id']:<18}{r['status']:<13}{r['count']:>6}{r['durationSec']:>7}  {str(extra)[:62]}")
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    safe_print("")
    safe_print(f"probe summary: {counts}")
    safe_print(f"disabled (not attempted): {', '.join(sorted(DISABLED_CHANNELS))}")
    safe_print("deeper evidence: python scripts/probe-channels.py")
    return 0


def enrich_missing_summaries(items, cfg, log, cap=90, budget_sec=120, state=None):
    """Fetch a page's meta description for items that arrived with no summary.

    Why this exists: a card whose entire content is a title plus a link cannot be
    explained, scored, or deep-read - which is exactly the complaint that some
    cards have "只有摘要或链接". Two real causes were measured on 2026-10-01:

      * `huggingface.co/blog/feed.xml` carries NO content element at all: its
        entries are only title/pubDate/link/guid (verified across 870 entries),
        so all 23 HuggingFace blog cards had an empty summary.
      * Semantic Scholar's bulk endpoint returns `abstract: null` for a large
        share of records (14 of 37 s2 cards), and the landing page is then the
        only accessible place the abstract exists.

    Bounded three ways. The unbounded first version made a daily run take
    24 minutes (measured: 1455s, dominated by waiting on dead URLs), which is
    unacceptable for a scheduled task, so:
      * `cap`        - at most this many fetches per run
      * `budget_sec` - stop once this much wall time is spent, whatever the cap
      * `state`      - remember URLs that already failed and stop retrying after
                       3 attempts. Several sources (old Nowcoder discussion pages,
                       dead DOIs) genuinely have no meta description, and
                       re-attempting them every day is pure waste.

    Failures persist in `state["summaryFetchFails"]` so the next run skips them.
    Anything still summary-less is treated as low importance by prune_items.py
    rather than quietly passing as knowledge.
    """
    targets = [it for it in items if len(str(it.get("summary") or "").strip()) < 80]
    if not targets:
        return 0, 0
    fails = (state or {}).get("summaryFetchFails") or {}
    started = time.time()
    tried = 0
    filled = 0
    gave_up = 0
    for it in targets:
        if tried >= cap:
            break
        if time.time() - started > budget_sec:
            log(f"  summary backfill: stopped at the {budget_sec}s budget "
                f"(filled {filled} of {tried} attempted)", "warn")
            break
        url = str(it.get("url") or "")
        if not url.startswith("http"):
            continue
        if int(fails.get(url, 0)) >= 3:
            gave_up += 1
            continue
        tried += 1
        try:
            _s, body, _ct = http_get(url, timeout=8, cfg=cfg, log=lambda *a, **k: None,
                                     retries=0, accept="text/html,*/*;q=0.8")
        except Exception:
            if state is not None:
                fails[url] = int(fails.get(url, 0)) + 1
            continue
        if not body:
            if state is not None:
                fails[url] = int(fails.get(url, 0)) + 1
            continue
        # http_get may hand back bytes; the regexes below need str.
        if isinstance(body, (bytes, bytearray)):
            try:
                body = body.decode("utf-8", "replace")
            except Exception:
                body = str(body)
        head = body[:200000]
        desc = ""
        for pat in (
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']{40,})["\']',
            r'<meta[^>]+content=["\']([^"\']{40,})["\'][^>]+property=["\']og:description["\']',
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']{40,})["\']',
            r'<meta[^>]+content=["\']([^"\']{40,})["\'][^>]+name=["\']description["\']',
            r'<meta[^>]+name=["\']citation_abstract["\'][^>]+content=["\']([^"\']{40,})["\']',
        ):
            m = re.search(pat, head, re.I | re.S)
            if m:
                desc = m.group(1)
                break
        if not desc:
            m = re.search(
                r'<p[^>]*class=["\'][^"\']*(?:abstract|summary)[^"\']*["\'][^>]*>(.{60,1200}?)</p>',
                head, re.I | re.S)
            if m:
                desc = m.group(1)
        desc = clean_text(desc, 900)
        if len(desc) >= 60:
            it["summary"] = desc
            it["summarySource"] = "page-meta-description"
            filled += 1
        elif state is not None:
            fails[url] = int(fails.get(url, 0)) + 1
        time.sleep(0.15)
    if gave_up:
        log(f"  summary backfill: skipped {gave_up} url(s) that already failed 3+ times", "info")
    if state is not None:
        state["summaryFetchFails"] = fails
    return filled, tried


def compose_summary(fresh, all_items, results, cfg, prev_summary=None) -> dict:
    """Build the day's digest summary — a deterministic "TL;DR" for humans.

    Deliberately mechanical: it selects and orders what is already in the data
    (highest relevance, most-reported categories, which channels delivered) and
    states counts. It does not paraphrase abstracts and it never asserts
    anything that is not derivable from the stored fields, so it stays honest
    even when the optional LLM layer is switched off. The agent layer can
    overwrite `headline`/`highlights` with richer prose afterwards.

    `prev_summary` matters for the `--rescore` path, which has no run results to
    report: without it the channel lists would be silently emptied and the
    headline would read "0/0 channels produced items".
    """
    prev_summary = prev_summary or {}
    top = sorted(fresh or [], key=lambda x: -(x.get("relevanceScore") or 0))[:6]

    # Diversify the "look at this first" list.
    #
    # Observed problem: a raw relevance sort put 3 job listings in the top 3 for
    # the day, crowding out the technical content the reader actually studies.
    # Job posts have high keyword match AND freshness, so they win that race.
    # Taking at most one item per category (then filling from the remainder)
    # keeps the summary about the day's breadth instead of one noisy channel.
    diversified: list = []
    seen_cats: set = set()
    for it in (fresh or []):
        cat = it.get("category")
        if cat in seen_cats:
            continue
        if len(diversified) >= 5:
            break
        diversified.append(it)
        seen_cats.add(cat)
    picked_ids = {it.get("id") for it in diversified}
    for it in sorted(fresh or [], key=lambda x: -(x.get("relevanceScore") or 0)):
        if len(diversified) >= 6:
            break
        if it.get("id") not in picked_ids:
            diversified.append(it)
            picked_ids.add(it.get("id"))
    top = diversified[:6]
    cat_fresh: dict = {}
    for it in fresh:
        cat_fresh[it.get("category")] = cat_fresh.get(it.get("category"), 0) + 1
    cat_total: dict = {}
    for it in all_items:
        cat_total[it.get("category")] = cat_total.get(it.get("category"), 0) + 1
    zh = sum(1 for it in fresh if it.get("lang") == "zh")
    with_code = sum(1 for it in fresh if it.get("codeAvailable"))
    peer = sum(1 for it in fresh if it.get("peerReviewed"))
    ok_channels = sorted(r["id"] for r in results.values() if r.get("status") == "ok")
    bad_channels = sorted(f"{r['id']}({r['status']})" for r in results.values()
                          if r.get("status") not in ("ok",))
    if not results:
        # No run data (the --rescore path): carry the previous observation over
        # rather than reporting a misleading zero.
        ok_channels = list(prev_summary.get("channelsWithItems") or [])
        bad_channels = list(prev_summary.get("channelsWithoutItems") or [])

    top_cat = sorted(cat_fresh.items(), key=lambda kv: -kv[1])[:3]
    headline = (f"本轮新增 {len(fresh)} 条，累计 {len(all_items)} 条；"
                + (f"集中在 " + "、".join(f"{(cfg['categories'].get(c) or {}).get('zh', c)} {n} 条"
                                          for c, n in top_cat) if top_cat else "本轮无新增条目")
                + (f"；{len(ok_channels)}/{len(ok_channels) + len(bad_channels)} 个渠道有产出。"
                   if (ok_channels or bad_channels) else "。"))

    highlights = []
    if top:
        highlights.append("最高相关：" + "；".join(
            f"{it.get('title', '')[:52]}({it.get('relevanceScore')})" for it in top[:3]))
    if peer:
        highlights.append(f"其中 {peer} 条来自同行评审渠道（OpenReview/会议），可信度更高")
    if with_code:
        highlights.append(f"{with_code} 条疑似附带开源实现，适合挑一个动手复现")
    if zh:
        highlights.append(f"{zh} 条为中文来源，与国内求职语境更贴近（牛客/知乎/量子位/雷锋网）")
    if bad_channels:
        highlights.append("未产出渠道：" + "，".join(bad_channels[:8])
                          + ("…" if len(bad_channels) > 8 else ""))

    return {
        "headline": headline,
        "highlights": highlights,
        "topItemIds": [it.get("id") for it in top],
        "counts": {
            "fresh": len(fresh),
            "total": len(all_items),
            "zhSources": zh,
            "peerReviewed": peer,
            "codeAvailable": with_code,
        },
        "byCategoryFresh": cat_fresh,
        "byCategoryTotal": cat_total,
        "channelsWithItems": ok_channels,
        "channelsWithoutItems": bad_channels,
        "generatedBy": "collect.py deterministic summarizer",
    }


def run(args) -> int:
    t0 = time.time()
    log = Logger(args.verbose)
    started = now_cst()
    log(f"Future daily collector v{COLLECTOR_VERSION}", "step")
    log(f"run time (Asia/Shanghai): {iso(started)}")

    cfg = load_config(CONFIG_PATH, log)
    if args.limit:
        cfg["limits"]["perChannel"] = args.limit
    if getattr(args, "kb_backfill", 0):
        # One-off backlog absorption. The daily window (15 pages/site) clears the
        # combined ~860-page knowledge base in about a month; this mode lets the
        # reader pull in a bigger slice in a single run when they want the backlog
        # visible now. It raises the per-channel allowance and the run cap, nothing
        # else - classification, gates and de-duplication are unchanged.
        n = int(args.kb_backfill)
        ovr = cfg.setdefault("channelIntakeOverride", {})
        kb_ids = [cid for cid, spec in CHANNEL_SPECS.items() if spec.get("knowledgeBase")]
        for cid in kb_ids:
            ovr[cid] = n
        cfg["limits"]["maxNewPerRun"] = max(int(cfg["limits"].get("maxNewPerRun", 96)),
                                            n * len(kb_ids) + 60)
        log(f"--kb-backfill {n}: pulling up to {n} pages per knowledge base this run "
            f"(maxNewPerRun raised to {cfg['limits']['maxNewPerRun']})", "warn")
    if not CONFIG_PATH.exists() and not args.dry_run:
        save_default_config(CONFIG_PATH)
        log(f"wrote default config template: {CONFIG_PATH}")

    if args.only:
        # A subset run is by definition a partial check, so mark it narrow unless
        # the caller explicitly asked for a full-replacement digest.
        args.narrow = True
        wanted = [c.strip() for c in args.only.split(",") if c.strip() in COLLECTORS]
        log("--only given: disabled channels run too, on purpose, for re-testing", "warn")
        log("--only also implies --narrow: today's digest keeps its previous items", "warn")
    else:
        wanted = [cid for cid, spec in CHANNEL_SPECS.items() if spec["mode"] != "manual"]
        wanted = [c for c in wanted if c in COLLECTORS]
        # Channels switched off by config (e.g. the login-channel inbox while it
        # is paused) are treated like blocked ones: reported, never requested.
        opt_out = [c for c in wanted
                   if c in DISABLED_CHANNELS or CHANNEL_SPECS[c].get("disabled")]
        if CHANNEL_SPECS.get("inbox", {}).get("disabled") and not cfg.get("enableInbox"):
            opt_out = sorted(set(opt_out) | {"inbox"})
        wanted = [c for c in wanted if c not in DISABLED_CHANNELS
                  and not CHANNEL_SPECS[c].get("disabled")]
        if CHANNEL_SPECS.get("inbox", {}).get("disabled") and not cfg.get("enableInbox"):
            wanted = [c for c in wanted if c != "inbox"]
        blocked = [c for c in opt_out if c in DISABLED_CHANNELS]
        off = [c for c in opt_out if c not in DISABLED_CHANNELS]
        if blocked:
            log(f"DISABLED_CHANNELS not attempted ({len(blocked)}): {', '.join(sorted(blocked))}", "warn")
        if off:
            log(f"switched off by config, not attempted ({len(off)}): {', '.join(sorted(off))}", "warn")

    log(f"channels to run ({len(wanted)}): {', '.join(wanted)}", "step")
    if MANUAL_ONLY:
        log(f"skipping login-walled channels (human import only): {', '.join(sorted(MANUAL_ONLY))}", "warn")

    per_channel = int((cfg.get("limits") or {}).get("perChannel", 30))
    results, raw_items = collect_channels(wanted, cfg, per_channel, log)

    # Blocked channels are REPORTED but never requested: the run log and
    # web/data/sources.json must show why a channel is dark, or the next reader
    # will "fix" it again from scratch.
    for cid in (DISABLED_CHANNELS if not args.only else {}):
        if cid in COLLECTORS:
            spec = CHANNEL_SPECS.get(cid, {"tier": "P2"})
            results[cid] = build_channel_result(cid, spec, "blocked", 0, None, 0.0,
                                                DISABLED_CHANNELS[cid])

    log(f"raw items: {len(raw_items)} -> normalizing / scoring / deduping", "step")

    # State is loaded HERE, before the summary pass, because the pass both reads
    # the canonical store (to find cards whose summary is missing) and records
    # failed URLs into it. Loading it later made the gap scan reference an
    # undefined name.
    state = read_json(STATE_PATH, {})
    state.setdefault("version", 1)

    # Fill in summaries for content-less items BEFORE scoring, so relevance is
    # computed on real text rather than on a bare title.
    #
    # Priority matters as much as the pass itself. With a plain first-N cap, the
    # 40 fetch slots went to whatever the feed happened to return first, while the
    # genuinely summary-less cards already in the library were never reached -
    # which is why a pass reporting "28/40 filled" still left 19 empty cards.
    # Canonical entries with a missing/empty summary are therefore put at the
    # FRONT of the queue, so every run makes progress on the real backlog.
    summary_gaps: list = []
    if not args.no_enrich:
        try:
            canon_for_gaps = state.get("canonical") or {}
            raw_ids = {r.get("id") for r in raw_items}
            for cid, entry in canon_for_gaps.items():
                if not isinstance(entry, dict):
                    continue
                if len(str(entry.get("summary") or "").strip()) >= 80:
                    continue
                # Reuse the raw item when the same entry is in this batch, so the
                # improved summary flows through the normal ingest path; otherwise
                # synthesise a minimal record whose url we can fetch.
                match = next((r for r in raw_items
                              if r.get("id") == cid
                              or title_key(r.get("title")) == title_key(entry.get("title"))), None)
                summary_gaps.append(match or {
                    "id": cid, "title": entry.get("title"), "url": entry.get("url"),
                    "summary": "", "sourceId": entry.get("channel"),
                })
            if summary_gaps:
                log(f"summary gaps: {len(summary_gaps)} library card(s) have no usable "
                    f"description; queued for page fetch first", "warn")
        except Exception as e:
            log(f"summary gap scan failed: {e}", "warn")

    if not args.no_enrich:
        try:
            filled, tried = enrich_missing_summaries(summary_gaps + raw_items, cfg, log,
                                                     state=state)
            if tried:
                log(f"summary backfill: {filled}/{tried} items got a description "
                    f"from their page's meta tag", "info" if filled else "warn")
        except Exception as e:
            log(f"summary backfill skipped: {e}", "warn")

    deduper = Deduper(state, cfg)

    # ------------------------------------------------------------------
    # Learning signals — close the feedback loop with the workbench UI.
    #
    # Stars, reading status and mastery live in the browser's localStorage, which
    # this process cannot read. Without a bridge, ranking can only ever use
    # keyword heuristics and never adapts to what the reader actually studies -
    # which is the difference between "a feed" and "a workbench that helps me".
    # The progress page therefore offers 「写出学习信号」, which writes
    # web/data/feedback.json; here we apply it as a small, capped multiplier.
    #
    # Deliberately gentle: the bonus is capped so a burst of stars on one topic
    # cannot drown out the other directions, and it never overrides the relevance
    # gate. It nudges, it does not steer.
    # ------------------------------------------------------------------
    feedback = read_json(DATA_DIR / "feedback.json", {}) or {}
    fb_cat = feedback.get("byCategory") or {}
    fb_chan = feedback.get("byChannel") or {}
    if fb_cat or fb_chan:
        top_cat = sorted(fb_cat.items(), key=lambda kv: -kv[1])[:5]
        log(f"learning signals: {feedback.get('starredCount', 0)} starred / "
            f"{len(fb_cat)} categories engaged (top: "
            f"{', '.join(f'{k}×{v}' for k, v in top_cat) or '—'})", "info")
    else:
        log("learning signals: none yet — use 「写出学习信号」on the progress page "
            "to let ranking follow your interests", "info")

    def signal_bonus(cat: str, chan: str) -> float:
        """A capped ±bonus from the reader's own behaviour (0 when no signals)."""
        if not (fb_cat or fb_chan):
            return 0.0
        max_cat = max(fb_cat.values()) if fb_cat else 1
        max_chan = max(fb_chan.values()) if fb_chan else 1
        b = 0.0
        if cat and cat in fb_cat:
            b += 8.0 * (fb_cat[cat] / max_cat)      # up to +8 points
        if chan and chan in fb_chan:
            b += 4.0 * (fb_chan[chan] / max_chan)   # up to +4 points
        return round(b, 2)

    seen_ids = set(state.get("seenIds") or [])
    first_seen = state.setdefault("firstSeen", {})
    last_seen = state.setdefault("lastSeen", {})
    canonical = state.setdefault("canonical", {})

    # ------------------------------------------------------------------
    # Reconcile previously-applied learning bonuses.
    #
    # A bonus is baked into relevanceScore when an item is imported, so an item that
    # received one keeps that score forever - including after the reader deletes
    # feedback.json or their interests change. Measured: removing the file left 5
    # items still boosted. That is a silent, permanent distortion of the ranking.
    #
    # Fix: when a stored item carries a learningSignalBonus, remove exactly that
    # amount and recompute the bonus for the current signals. Self-correcting, and
    # idempotent because the stored bonus is always subtracted first.
    # ------------------------------------------------------------------
    rebased = 0
    for cid, entry in canonical.items():
        if not isinstance(entry, dict):
            continue
        bd = entry.get("relevanceBreakdown")
        prev = 0.0
        if isinstance(bd, dict):
            try:
                prev = float(bd.get("learningSignalBonus") or 0)
            except (TypeError, ValueError):
                prev = 0.0
        if not prev:
            continue
        base = float(entry.get("relevanceScore") or 0) - prev
        now_bonus = signal_bonus(entry.get("category"), entry.get("channel"))
        entry["relevanceScore"] = round(max(0.0, min(100.0, base + now_bonus)), 2)
        if isinstance(bd, dict):
            if now_bonus:
                bd["learningSignalBonus"] = now_bonus
            else:
                bd.pop("learningSignalBonus", None)
        rebased += 1
    if rebased:
        log(f"learning signals: rebased {rebased} previously boosted item(s) "
            f"(removes stale interest bonuses)", "info")

    # ------------------------------------------------------------------
    # Blocklist: items a human (or prune_items.py / dedupe_deep.py) removed.
    #
    # Without this check the whole cleaning effort silently undid itself: the
    # pruner archived 165 items and recorded their ids in state["blockedIds"], but
    # nothing read that list, so the very next collection re-imported them and the
    # library jumped straight back from 554 to 763. Enforcing it here is what makes
    # the blocklist actually mean something.
    #
    # Matched on BOTH the stable id and the canonical URL, so a re-published item
    # that gets a new id is still recognised.
    # ------------------------------------------------------------------
    blocked_ids = set(state.get("blockedIds") or [])
    blocked_title_keys = set(state.get("blockedTitleKeys") or [])
    blocked_urls = {str(u).lower().rstrip("/") for u in (state.get("blockedUrls") or [])}

    fresh, updated, dup_count, dropped, blocked = [], [], 0, 0, 0
    unclassified_dropped = 0
    low_value_dropped = 0
    min_rel = float((cfg.get("scoring") or {}).get("minRelevance", 0) or 0)
    # Default True: keep unclassified items out of the corpus (see the gate below).
    drop_unclassified = bool((cfg.get("limits") or {}).get("dropUnclassified", True))

    for raw in raw_items:
        spec = CHANNEL_SPECS.get(raw.get("sourceId"), {"tier": "P2"})
        item = normalize(raw, cfg, spec["tier"])
        if not item:
            dropped += 1
            continue
        # Apply the reader's own learning signals before the gates, and record the
        # adjustment in the breakdown so the change is auditable in the UI rather
        # than a mysterious score drift.
        bonus = signal_bonus(item.get("category"), item.get("channel"))
        if bonus:
            item["relevanceScore"] = round(min(100.0, float(item["relevanceScore"]) + bonus), 2)
            bd = item.setdefault("relevanceBreakdown", {})
            if isinstance(bd, dict):
                bd["learningSignalBonus"] = bonus
        # --- blocklist gate ---
        if blocked_ids and item.get("id") in blocked_ids:
            blocked += 1
            continue
        if blocked_title_keys and title_key(item.get("title")) in blocked_title_keys:
            blocked += 1
            continue
        if blocked_urls:
            cu = str(item.get("canonicalUrl") or item.get("url") or "").lower().rstrip("/")
            if cu and cu in blocked_urls:
                blocked += 1
                continue
        if item["relevanceScore"] < min_rel:
            dropped += 1
            continue
        # `unclassified` never enters the corpus.
        #
        # An item that matched no category keyword cannot serve any tracked direction,
        # and letting them in wasted part of the 120k-entry de-duplication budget on
        # content that is invisible anyway (build_all_items drops it from the output).
        # Dropping at ingest is what makes "we do not keep unclassified cards" true
        # rather than cosmetic. Counted separately so the log distinguishes
        # "not good enough" from "matched nothing".
        if drop_unclassified and item.get("category") == "unclassified":
            unclassified_dropped += 1
            continue
        # --- knowledge-quality gate ---------------------------------------
        # The reader's complaint was concrete: "a lot of news and papers get in
        # just because they are recent or tangentially related". The gate itself now
        # lives in ONE place - KQ.ingest_reject() - so the collector and the pruner
        # cannot disagree about the same card. It refuses, in order:
        #   · 付费充值教程 / 内推码 / 卖课引流 / 资源包下载（材料性再高也不收）；
        #   · 泛 AI 资讯（没有公式/推导/实验/数据集这类技术实质）与材料性过低的资讯；
        #   · 命中其它硬噪音规则且没有实质内容的条目；
        #   · 方向不贴合的论文 / 仓库 / 课程。
        # 论文 / 仓库 / 课程这一支与 importance() 的分档调用**同一个**函数，所以不可能
        # 出现「采集放进来、清理又要删」的自相矛盾。理由一并记进日志，便于复核。
        if KQ is not None:
            _kind = item.get("kind") or ""
            _rej = KQ.ingest_reject(item, KQ_POLICY)
            if _rej:
                low_value_dropped += 1
                log.detail(f"reject [{_kind}] {str(item.get('title'))[:60]}  <- {_rej}")
                continue
        cid = deduper.lookup(item)
        if cid:
            dup_count += 1
            last_seen[cid] = iso(now_cst())
            if canonical.get(cid):
                canonical[cid] = merge_duplicate(canonical[cid], item)
                updated.append(canonical[cid])
            continue
        item["firstSeen"] = iso(now_cst())
        item["lastSeen"] = item["firstSeen"]
        item["learning"] = {"status": "unread", "starred": False, "mastery": 0}
        canonical[item["id"]] = item
        first_seen[item["id"]] = item["firstSeen"]
        last_seen[item["id"]] = item["lastSeen"]
        seen_ids.add(item["id"])
        deduper.register(item, item["id"])
        fresh.append(item)
        log.detail(f"+ [{item['category']:<13}] {item['relevanceScore']:>5} {item['title'][:70]}")

    fresh.sort(key=lambda x: -x["relevanceScore"])
    cap = int((cfg.get("limits") or {}).get("maxNewPerRun", 400))
    if len(fresh) > cap:
        fresh = fresh[:cap]

    # ------------------------------------------------------------------
    # Per-category intake cap.
    #
    # The reader asked for depth over volume: 2-10 deeply-analysed items per
    # direction per day beats 40 shallow ones, and a lopsided corpus is what made
    # 'agent' hold 24% of everything. Without a cap a single chatty channel or a
    # broad keyword set can push one category far ahead of the others, which both
    # drowns the digest and starves the categories that matter (multimodal /
    # post-training / world models).
    #
    # Only the FRESH intake is capped - the existing library is never truncated, so
    # nothing already curated is lost. Items over the cap stay in the corpus from a
    # previous run and simply do not grow further this run.
    # ------------------------------------------------------------------
    per_cat_cap = int((cfg.get("limits") or {}).get("perCategoryPerRun", 0) or 0)
    if per_cat_cap > 0:
        # The cap is per category, but the reader wants a specific MIX: interview
        # write-ups and algorithm problems matter more, and they decay fastest (a 2024
        # 面经 is nearly worthless for a 2026 application). `categoryIntakeWeight`
        # scales each category's ceiling, so the desired mix is expressed as data in
        # collector.config.json and can be retuned without touching this code.
        intake_w = cfg.get("categoryIntakeWeight") or {}
        caps = {}
        for cid in cfg["categories"]:
            w = float(intake_w.get(cid, 1.0) or 0.0)
            caps[cid] = int(round(per_cat_cap * w))
        kept, used, trimmed = [], {}, 0
        for it in fresh:
            c = it.get("category") or "trend"
            # Knowledge-base channels are exempt from this cap. The cap exists to
            # stop a talkative FEED from flooding one category; a 题解 page has no
            # "talkative day", and trimming it would defeat the point of keeping a
            # reference library. Their volume is already bounded by the per-channel
            # allowance, and they never crowd out a feed because feeds are scored
            # separately.
            if (CHANNEL_SPECS.get(it.get("channel")) or {}).get("knowledgeBase"):
                used[c] = used.get(c, 0) + 1
                kept.append(it)
                continue
            if used.get(c, 0) >= caps.get(c, per_cat_cap):
                trimmed += 1
                continue
            used[c] = used.get(c, 0) + 1
            kept.append(it)
        # Always report the caps, even when nothing was trimmed.
        #
        # WHY unconditional: a monitor reads this line to confirm the intake mix is
        # still being enforced. Logging only on a trim made the line's ABSENCE
        # ambiguous - "caps applied and nothing hit them" and "the cap code never ran"
        # looked identical in the log, so the daily check could not actually verify
        # anything. `DROPPED 0` is the useful, unambiguous form.
        over = sorted(((c, n) for c, n in used.items()
                       if n >= caps.get(c, per_cat_cap)), key=lambda kv: -kv[1])[:5]
        log(f"per-category intake caps {json.dumps(caps, ensure_ascii=False)}: "
            f"dropped {trimmed} item(s)"
            + (f"; busiest: {', '.join(f'{c}={n}' for c, n in over)}" if over else ""),
            "info")
        # The categories the reader explicitly prioritises, so it is visible whether
        # the interview/algorithm mix is actually being fed.
        for cid in ("coding", "job", "exam"):
            if caps.get(cid):
                log(f"  {cid}: {used.get(cid, 0)}/{caps[cid]} 条", "info")
        fresh = kept

    deduper.prune()
    state["seenIds"] = list(seen_ids)[-120000:]
    state["lastRunAt"] = iso(now_cst())
    state["byKey"], state["byUrl"], state["byTitle"] = deduper.by_key, deduper.by_url, deduper.by_title
    state["hashes"] = deduper.hashes

    log(f"deduped: new={len(fresh)} updated={len(updated)} duplicate_hits={dup_count} "
        f"dropped={dropped} blocklisted={blocked} unclassified={unclassified_dropped} "
        f"low_value={low_value_dropped}", "ok")
    if blocked:
        log(f"  {blocked} item(s) skipped by the blocklist (removed earlier by "
            f"prune_items.py / dedupe_deep.py); they will not come back", "info")
    if unclassified_dropped:
        log(f"  {unclassified_dropped} item(s) matched NO category keyword and were not "
            f"stored (off-topic news cannot serve any direction)", "info")
    if low_value_dropped:
        log(f"  {low_value_dropped} item(s) dropped by the knowledge-quality gate "
            f"(pure news / flagged content with nothing material behind it, "
            f"or a 论文/仓库 whose direction fit failed — see KQ.technical_reject)", "info")

    duration = round(time.time() - t0, 1)
    ok_channels = sum(1 for r in results.values() if r["status"] == "ok")
    status = "ok" if ok_channels == len(results) and results else ("partial" if ok_channels else "error")

    # Reconcile backfilled summaries into the canonical store.
    #
    # Why this is needed: enrich_missing_summaries() improves the RAW items, but
    # for an item that already exists the deduper takes the `merge_duplicate`
    # branch, which keeps whatever summary the canonical record already had - i.e.
    # still empty. Measured effect: the pass reported "28/40 filled" while the
    # library still showed 19 summary-less cards afterwards. Writing the improved
    # text into canonical (and refreshing lastSeen) is what makes it stick.
    backfilled = 0
    if not args.no_enrich:
        # Collect every improved summary in this run, then push it into the
        # canonical record. Note the canonical store keeps whatever it already
        # had when the deduper takes the merge_duplicate branch, so without this
        # step an improved summary is computed and then thrown away.
        improved = {}
        for src in (summary_gaps + raw_items):
            s = str(src.get("summary") or "").strip()
            if len(s) >= 80 and src.get("summarySource") == "page-meta-description":
                for key in (src.get("id"), title_key(src.get("title"))):
                    if key:
                        improved[key] = s
        for cid, entry in (canonical or {}).items():
            if not isinstance(entry, dict):
                continue
            cur = str(entry.get("summary") or "").strip()
            if len(cur) >= 80:
                continue
            cand = improved.get(cid) or improved.get(title_key(entry.get("title")))
            if cand and len(cand) > len(cur):
                entry["summary"] = cand
                entry["summarySource"] = "page-meta-description"
                backfilled += 1
        log(f"summary reconcile: {backfilled} existing card(s) updated in place "
            f"(improved candidates in this run: {len(improved)})", "ok" if backfilled else "info")

    run_record = {
        "startedAt": iso(started), "finishedAt": iso(now_cst()), "status": status,
        # Distinguish an automatic 18:00 run from a human/dev invocation. Without
        # this the run history is ambiguous: during development there were many
        # manual runs in one afternoon, which looks exactly like "the schedule is
        # firing repeatedly" when reading logs/runs.json.
        "trigger": getattr(args, "trigger", "manual"),
        "narrowRun": bool(getattr(args, "narrow", False)),
        "durationSec": duration, "channelsOk": ok_channels, "channelsTotal": len(results),
        "channelsBlocked": sum(1 for r in results.values() if r["status"] == "blocked"),
        "channelsEmpty": sum(1 for r in results.values() if r["status"] == "empty"),
        "channelsParseError": sum(1 for r in results.values() if r["status"] == "parse_error"),
        "newItems": len(fresh), "updatedItems": len(updated), "duplicates": dup_count,
        "rawItems": len(raw_items), "collectorVersion": COLLECTOR_VERSION,
        "itemsFile": f"digest/{date_key(started)}.json",
        "notes": "; ".join(f"{r['id']}={r['status']}" for r in results.values()
                           if r["status"] != "ok") or "all channels reported items",
        "blockedChannels": {r["id"]: r.get("riskNote") for r in results.values()
                            if r["status"] == "blocked"},
    }

    if args.dry_run:
        log("--dry-run: nothing written", "warn")
        safe_print(json.dumps({"run": run_record, "newSample": [i["title"] for i in fresh[:10]]},
                              ensure_ascii=False, indent=2))
        return 0

    day = date_key(started)
    all_items = build_all_items(state, fresh, cfg)
    stats = compute_stats(all_items)
    # A narrowed run (`--only a,b`) exists to test or re-check specific channels.
    #
    # It must not be mistaken for the day's research. Replacing digest/today.json
    # with a 2-item subset made the optional agent layer believe the day had
    # almost no content (observed: it fell back to "top 12 from the whole index"),
    # and it made the 每日更新流 render a subset. So a narrow run unions the
    # previous digest's items into today's, fresh items first.
    narrow = bool(getattr(args, "narrow", False))
    if narrow:
        prior = read_json(DIGEST_DIR / "today.json", None)
        prior_items = (prior or {}).get("items") or []
        seen_ids_digest = {i.get("id") for i in fresh}
        carried = [i for i in prior_items if i.get("id") not in seen_ids_digest]
        if carried:
            log(f"narrow run: carried {len(carried)} items forward from the previous digest "
                f"so the day is not reduced to this subset", "warn")
            fresh = fresh + carried

    # Same-day RE-RUN guard.
    #
    # Why this exists: the 18:00 automation and a later retry invocation of the same
    # day both run the deterministic layer. The later run legitimately collects 0 new
    # items (everything is already in the index), but writing the digest from `fresh`
    # alone replaced that day's digest with an EMPTY item list - the 每日速览 page then
    # claimed the day had no content at all.
    #
    # Observed: 2026-10-06 had an automatic 18:00 run (new=67) and a 21:09 retry
    # (new=0); digest/2026-10-06.json ended with items=[] and the built site showed an
    # empty 今日速览. This is the same failure mode the narrow-run guard above fixes,
    # so it gets the same treatment: carry the earlier same-day digest forward.
    #
    # The counts stay honest: run.newItems keeps the real 0, and the summary headline
    # is rewritten to say "no new items THIS run" instead of quoting the carried count.
    carried_same_day: list = []
    if not narrow and not fresh:
        prior = read_json(DIGEST_DIR / f"{day}.json", None) or read_json(DIGEST_DIR / "today.json", None)
        if (prior or {}).get("date") == day:
            carried_same_day = [i for i in ((prior or {}).get("items") or []) if i and i.get("id")]
            if carried_same_day:
                log(f"same-day re-run with no new items: carried {len(carried_same_day)} item(s) "
                    f"forward from the earlier {day} digest so 今日速览 is not emptied", "warn")

    summary = compose_summary(fresh, all_items, results, cfg)
    if carried_same_day:
        # highlights/topItemIds point at the day's actual content; the headline states
        # the truth about THIS run so the two never contradict each other.
        top_ids = [i.get("id") for i in
                   sorted(carried_same_day, key=lambda x: -(x.get("relevanceScore") or 0))[:6]]
        summary["topItemIds"] = top_ids
        summary["carriedForward"] = len(carried_same_day)
        summary["headline"] = (
            f"本次运行无新增条目；本日更早的运行已采集 {len(carried_same_day)} 条，"
            f"已保留在今日速览；累计 {len(all_items)} 条。")
        notes = summary.get("highlights") or []
        summary["highlights"] = [
            f"本日速览沿用 {day} 早些时候采集的 {len(carried_same_day)} 条内容（本次为同日重跑）。"
        ] + notes
    fresh = fresh + carried_same_day
    digest = {
        "date": day, "generatedAt": iso(now_cst()), "run": run_record, "stats": stats,
        "summary": summary,
        "narrowRun": narrow,
        "items": fresh,
        "updated": [{"id": u.get("id"), "title": u.get("title"), "sources": u.get("sources")}
                    for u in updated[:80]],
    }
    atomic_write_json(DIGEST_DIR / f"{day}.json", digest)
    atomic_write_json(DIGEST_DIR / "today.json", digest)

    index = {"generatedAt": iso(now_cst()), "count": len(all_items), "items": all_items}
    atomic_write_json(INDEX_DIR / "index.json", index)
    atomic_write_json(DATA_DIR / "items.json", index)

    # Next scheduled run, derived from the fixed 18:00 Asia/Shanghai cadence, so
    # the UI never has to hard-code it (and stays right if the schedule moves).
    now = now_cst()
    nxt = now.replace(hour=18, minute=0, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)

    manifest = {
        "generatedAt": iso(now_cst()), "lastRunAt": iso(now_cst()), "date": day,
        "collectorVersion": COLLECTOR_VERSION, "channelsOk": run_record["channelsOk"],
        "channelsTotal": run_record["channelsTotal"], "newItems": len(fresh),
        # Count what is actually PUBLISHED. `all_items` is the stored corpus, which
        # still holds `unclassified` entries (kept in state so a later keyword change
        # can bring the good ones back), but the index drops them - so reporting the
        # stored count made selfcheck warn "manifest.totalItems=720 but index has 635".
        "totalItems": len(build_all_items(state, [], cfg)),
        "storedItems": len(all_items), "durationSec": duration,
        "targetDate": cfg.get("targetDate"), "targetLabel": cfg.get("targetLabel"),
        "status": status, "itemsFile": f"digest/{day}.json", "stats": stats,
        "summary": summary,
        "schedule": {
            "cron": "0 18 * * *",
            "timezone": "Asia/Shanghai",
            "nextRunAt": iso(nxt),
            "taskName": "Future-Workbench-Daily-18",
            "runner": "scripts/run-daily.ps1",
        },
        "health": {
            "channelsWithItems": len(summary["channelsWithItems"]),
            "channelsWithoutItems": len(summary["channelsWithoutItems"]),
            "zhShare": stats.get("zhShare"),
            "emptySummaryItems": sum(1 for i in all_items if not (i.get("summary") or "").strip()),
            "itemsMissingUrl": sum(1 for i in all_items if not i.get("url")),
        },
    }
    atomic_write_json(DATA_DIR / "manifest.json", manifest)

    runs = read_json(RUNS_PATH, [])
    if not isinstance(runs, list):
        runs = []
    runs.insert(0, run_record)
    atomic_write_json(RUNS_PATH, runs[:120])

    # Channels + taxonomy doc for the 采集与运行 / 知识分类 views. Categories are
    # merged with whatever the (possibly richer) research registry already has.
    existing_sources = read_json(DATA_DIR / "sources.json", {}) or {}
    tax_by_id = {c.get("id"): c for c in (existing_sources.get("categories") or []) if c.get("id")}
    merged_cats = []
    for cid, c in cfg["categories"].items():
        base = tax_by_id.get(cid, {})
        merged_cats.append({
            "id": cid,
            "nameZh": base.get("nameZh") or c["zh"],
            "nameEn": base.get("nameEn") or c["en"],
            "description": base.get("description") or c.get("desc", ""),
            "collectionGoal": base.get("collectionGoal") or c.get("goal", ""),
            "updateCadence": base.get("updateCadence") or "每日 18:00 (Asia/Shanghai)",
            "relevanceWeight": c.get("weight", 0.8),
            "keywordsZh": [k for k in c["keywords"] if re.search(r"[\u4e00-\u9fff]", k)][:12],
            "keywordsEn": [k for k in c["keywords"] if not re.search(r"[\u4e00-\u9fff]", k)][:18],
            "arxivCategories": c.get("arxiv", []),
        })
    for cid, base in tax_by_id.items():
        if cid not in {c["id"] for c in merged_cats}:
            merged_cats.append(base)

    sources_doc = dict(existing_sources)

    # MERGE the channel registry instead of replacing it.
    #
    # Why: a run with `--only arxiv,hf_papers` (or any subset) used to overwrite
    # the whole `channels` array, so ~90 previously known channel records vanished
    # from the 采集与运行 view. Now a channel that did not run this pass keeps its
    # previous record with `staleSince` set, and the response explicitly reports
    # how many were observed this time versus carried over.
    prior_channels = {
        c.get("id"): c for c in (existing_sources.get("channels") or [])
        if isinstance(c, dict) and c.get("id")
    }
    ran_ids = set(results.keys())
    # Start from previously known records (breadth), then let this run's observed
    # results overwrite them one by one.
    merged_channel_store: dict = {cid: dict(rec) for cid, rec in prior_channels.items()}
    for cid, rec in results.items():
        merged_channel_store[cid] = dict(rec)

    for cid, prior in prior_channels.items():
        if cid in ran_ids:
            continue
        # Carried over: keep the previous observation but make the staleness explicit.
        entry = merged_channel_store[cid]
        entry["notRunThisPass"] = True
        entry["staleSince"] = entry.get("lastChecked") or existing_sources.get("generatedAt")

    sources_doc.update({
        "generatedAt": iso(now_cst()),
        "collectorVersion": COLLECTOR_VERSION,
        "categories": merged_cats,
        "channels": sorted(merged_channel_store.values(),
                           key=lambda c: (STATE_RANK.get(str(c.get("status")), 9),
                                          TIER_RANK.get(str(c.get("tier")), 9),
                                          str(c.get("id")))),
        "channelsObservedThisRun": sorted(ran_ids),
        "channelsRanCount": len(ran_ids),
        "channelsKnownCount": len(merged_channel_store),
        "manualChannels": [
            {"id": cid, "nameZh": CHANNEL_NAMES.get(cid, cid), "authRequired": True, "mode": "manual",
             "howTo": "人工登录后导出 CSV/JSON 放入 web/data/inbox/，下次运行时自动合并。"}
            for cid in sorted(MANUAL_ONLY)
        ],
        "scoring": cfg.get("scoring"), "dedupe": cfg.get("dedupe"),
        "limits": cfg.get("limits"),
        # NOTE: deliberately NOT setting `lastRunAt` here. A stale `lastRunAt`
        # field can be inherited from dict(existing_sources) and would contradict
        # manifest.json; that field is owned by manifest only.
        "runCounts": {
            "ok": sum(1 for r in results.values() if r.get("status") == "ok"),
            "empty": sum(1 for r in results.values() if r.get("status") == "empty"),
            "error": sum(1 for r in results.values() if r.get("status") == "error"),
            "blocked": sum(1 for r in results.values() if r.get("status") == "blocked"),
            "parse_error": sum(1 for r in results.values() if r.get("status") == "parse_error"),
        },
    })
    # Remove any inherited stale runs list / lastRunAt so the UI reads one source.
    for stale_key in ("lastRunAt", "runs", "notes", "build"):
        sources_doc.pop(stale_key, None)
    atomic_write_json(DATA_DIR / "sources.json", sources_doc)

    # Deterministic self-iteration: write a proposal file every run so the loop
    # produces output even when the optional LLM deep-read layer is skipped.
    write_proposals(cfg, results, fresh, all_items, log)

    taxonomy = {"generatedAt": iso(now_cst()), "source": "collect.py", "categories": merged_cats}
    atomic_write_json(DATA_DIR / "taxonomy.json", taxonomy)
    atomic_write_json(STATE_PATH, state)

    log(f"wrote digest/{day}.json, items/index.json, manifest.json, sources.json, logs/runs.json", "ok")
    log(f"done in {duration}s | status={status} | new={len(fresh)} | total={len(all_items)}", "ok")
    return 0


# ============================================================================
# 10. CLI
# ============================================================================
def build_parser():
    p = argparse.ArgumentParser(
        prog="collect.py",
        description="Future workbench - daily public-source research collector (stdlib only)",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--only", help="comma-separated channel ids, e.g. arxiv,github,hf_papers")
    p.add_argument("--narrow", action="store_true",
                   help="treat this as a partial check: keep the previous digest items so the "
                        "day is not reduced to this subset (implied by --only)")
    p.add_argument("--trigger", default="manual",
                   choices=["scheduled", "manual", "debug"],
                   help="how this run was started; recorded in logs/runs.json so the history "
                        "distinguishes the 18:00 schedule from human runs")
    p.add_argument("--no-enrich", action="store_true",
                   help="skip the page-fetch pass that fills summaries for items whose feed "
                        "carried no content (faster, but leaves title-only cards)")
    p.add_argument("--limit", type=int, help="max items per channel (overrides config)")
    p.add_argument("--dry-run", action="store_true", help="print results, write nothing")
    p.add_argument("--probe", action="store_true",
                   help="one lightweight pass over the channels, print a health table, write nothing")
    p.add_argument("--init-config", action="store_true", help="write the config template and exit")
    p.add_argument("--rescore", action="store_true",
                   help="re-apply classification + scoring to every stored item, then exit "
                        "(use after tuning keyword weights or the scoring formula)")
    p.add_argument("--kb-backfill", type=int, metavar="N", default=0,
                   help="one-off: absorb N pages per algorithm knowledge base "
                        "(代码随想录 / 卡码笔记) to clear the historical backlog faster "
                        "than the daily rotating window. Still bounded by the per-run cap.")
    p.add_argument("-v", "--verbose", action="store_true", help="trace every accepted item")
    return p


def rescore_all(cfg, log) -> int:
    """Re-apply classification and scoring to every stored item.

    Needed because relevanceScore is computed at ingest time and stored. After
    tuning keyword weights (for example, lowering 岗位与招聘 so job listings stop
    dominating the daily summary) the existing corpus keeps its old scores until
    it is rescored. Category assignment is refreshed too, so a keyword change
    also reclassifies items.
    """
    state = read_json(STATE_PATH, {})
    canonical = state.get("canonical") or {}
    if not canonical:
        log("no stored items to rescore", "warn")
        return 1

    changed_cat = changed_score = 0
    before_top = sorted(canonical.values(), key=lambda x: -(x.get("relevanceScore") or 0))[:5]

    for item in canonical.values():
        spec = CHANNEL_SPECS.get(item.get("sourceId"), {"tier": "P2"})
        cat, hits = classify(item, cfg)
        if cat != item.get("category"):
            changed_cat += 1
        item["category"] = cat
        item["categoryHits"] = hits
        # Refresh the knowledge-quality judgement too. Without this, items ingested
        # before a rule changed would keep stale kind/materiality values and the
        # score, the planner and the pruner would disagree about the same card.
        if KQ is not None:
            item["kind"] = KQ.classify_kind(item)
            item["materiality"] = KQ.materiality(item, item["kind"])
            item["directionFit"] = KQ.direction_fit(item)
            _flags = KQ.noise_ids(item)
            if _flags:
                item["qualityFlags"] = _flags
            else:
                item.pop("qualityFlags", None)
            if (CHANNEL_SPECS.get(item.get("channel")) or {}).get("knowledgeBase"):
                item["knowledgeBase"] = True
            else:
                item.pop("knowledgeBase", None)
        rel, breakdown = score_item(item, cfg, spec["tier"], hits)
        if abs(float(rel) - float(item.get("relevanceScore") or 0)) > 0.05:
            changed_score += 1
        item["relevanceScore"] = rel
        item["relevanceBreakdown"] = breakdown
        item["why"] = explain(item, hits, cfg)

    state["lastRescoreAt"] = iso(now_cst())
    atomic_write_json(STATE_PATH, state)

    # A keyword/weight change alters the taxonomy's derived fields, so regenerate it
    # here too - otherwise the taxonomy silently disagrees with the index after every
    # rescore (see write_taxonomy's docstring).
    write_taxonomy(cfg)

    all_items = build_all_items(state, [], cfg)
    atomic_write_json(INDEX_DIR / "index.json",
                      {"generatedAt": iso(now_cst()), "count": len(all_items), "items": all_items})
    atomic_write_json(DATA_DIR / "items.json",
                      {"generatedAt": iso(now_cst()), "count": len(all_items), "items": all_items})

    # Keep the digest's summary consistent with the new scores.
    digest_path = DIGEST_DIR / "today.json"
    digest = read_json(digest_path, None)
    if isinstance(digest, dict):
        fresh_ids = {i.get("id") for i in (digest.get("items") or [])}
        fresh = [canonical[i] for i in fresh_ids if i in canonical]
        digest["summary"] = compose_summary(fresh, all_items, {}, cfg,
                                            prev_summary=digest.get("summary"))
        digest["rescoredAt"] = iso(now_cst())
        atomic_write_json(digest_path, digest)
        day = digest.get("date")
        if day:
            atomic_write_json(DIGEST_DIR / f"{day}.json", digest)

    log(f"rescored {len(canonical)} items: {changed_cat} reclassified, "
        f"{changed_score} score changes", "ok")
    after_top = sorted(canonical.values(), key=lambda x: -(x.get("relevanceScore") or 0))[:5]
    log("top 5 before -> after:", "info")
    for b, a in zip(before_top, after_top):
        log(f"  {(b.get('category') or ''):<13} {b.get('relevanceScore')} -> "
            f"{(a.get('category') or ''):<13} {a.get('relevanceScore')}", "info")
        log(f"     {str(a.get('title'))[:70]}", "info")
    return 0


def write_taxonomy(cfg: dict) -> None:
    """(Re)generate web/data/taxonomy.json from the effective category config.

    WHY this is a function and not inlined: the taxonomy was only written by the full
    collect path, so `--rescore` (the command you run right after changing keywords or
    weights) left taxonomy.json stale. That is how a category added to
    DEFAULT_CATEGORIES appeared in items/index.json but not in the taxonomy, and
    selfcheck then reported "85 items use a category not in taxonomy.json" - a warning
    that was both true and entirely an artefact of a missing write.
    """
    existing_sources = read_json(DATA_DIR / "sources.json", {}) or {}
    tax_by_id = {c.get("id"): c for c in (existing_sources.get("categories") or [])
                 if c.get("id")}
    merged: list[dict] = []
    for cid, c in cfg["categories"].items():
        base = tax_by_id.get(cid, {})
        merged.append({
            "id": cid,
            "nameZh": base.get("nameZh") or c["zh"],
            "nameEn": base.get("nameEn") or c["en"],
            "description": base.get("description") or c.get("desc", ""),
            "collectionGoal": base.get("collectionGoal") or c.get("goal", ""),
            "updateCadence": base.get("updateCadence") or "每日 18:00 (Asia/Shanghai)",
            "relevanceWeight": c.get("weight", 0.8),
            "keywordsZh": [k for k in c["keywords"] if re.search(r"[\u4e00-\u9fff]", k)][:12],
            "keywordsEn": [k for k in c["keywords"] if not re.search(r"[\u4e00-\u9fff]", k)][:18],
            "arxivCategories": c.get("arxiv", []),
        })
    for cid, base in tax_by_id.items():
        if cid not in {c["id"] for c in merged}:
            merged.append(base)
    atomic_write_json(DATA_DIR / "taxonomy.json",
                      {"generatedAt": iso(now_cst()), "source": "collect.py",
                       "categories": merged})


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.init_config:
        save_default_config(CONFIG_PATH)
        print(f"wrote {CONFIG_PATH}")
        return 0
    try:
        if args.rescore:
            log = Logger(args.verbose)
            return rescore_all(load_config(CONFIG_PATH, log), log)
        return run_probe(args) if args.probe else run(args)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
