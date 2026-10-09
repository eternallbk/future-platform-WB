#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
频道健康探针 / Channel reliability probe
================================================================================
Why this file exists
  scripts/collect.py fans out over ~30 public channels; when a run comes back
  "partial" the log only says `empty` or an exception repr, which is not enough
  to choose between four very different repairs:

    * the endpoint is fine but the HTML/JSON shape changed  -> fix the parser
    * the endpoint moved or was retired                      -> find a new one
    * the host answers 403 / a bot challenge / robots.txt    -> stop trying
    * the request timed out or we were rate limited          -> transient

  This probe answers that with evidence: it drives the REAL code path in
  scripts/collect.py (imported by file path, never copied), records the HTTP
  status each collector actually observed, and then re-tests a curated list of
  candidate replacement endpoints for the channels that failed. Every number in
  the emitted report comes from a request made during the probe run.

Design notes
  * stdlib only, because the collector is stdlib only and the probe must run on
    a bare Windows Python 3.12 install.
  * Politeness: at least 1s between two requests to the same host, robots.txt
    fetched once per host and honoured through urllib.robotparser, and a
    disallowed path is reported as `robots_disallowed` instead of requested.
  * Login-walled sites are never probed past their public landing page; the
    probe records "login required" and stops. No challenge is ever solved.
  * One failing channel or candidate never aborts the run.
  * Output: a compact table on stdout, a machine-readable report written to
    research/channel_probe.json (UTF-8, no BOM), plus --json for piping.

Usage
  python scripts/probe-channels.py                    # everything
  python scripts/probe-channels.py --only s2,reddit   # subset
  python scripts/probe-channels.py --json             # machine readable stdout
  python scripts/probe-channels.py --skip-channels    # candidate endpoints only
"""
from __future__ import annotations

import argparse
import http.cookiejar
import importlib.util
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
COLLECT_PATH = HERE / "collect.py"
REPORT_PATH = ROOT / "research" / "channel_probe.json"

PROBE_VERSION = "1.0.0"
CST = timezone(timedelta(hours=8))
UA_BROWSER = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 FutureWorkbench/1.0")
UA_PLAIN = "future-workbench-probe/1.0 (+personal academic research; contact: local)"
MIN_HOST_INTERVAL = 1.0          # seconds between two requests to the same host
DEFAULT_TIMEOUT = 25


def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def safe_print(text: str = "") -> None:
    """Print Chinese to a GBK console without ever raising UnicodeEncodeError."""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "ascii"
        try:
            sys.stdout.write(str(text).encode(enc, "replace").decode(enc, "replace") + "\n")
            sys.stdout.flush()
        except Exception:
            pass


def load_collect():
    """Import scripts/collect.py by path so the probe exercises the real code."""
    spec = importlib.util.spec_from_file_location("collect_mod", str(COLLECT_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def clean(s) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()[:200]


def js_literal_decode(lit: str) -> str:
    """Decode the body of a JS single-quoted string literal into real text.

    Needed because talent.deepseek.com embeds its job catalogue as
    `JSON.parse('{"crawledAt":...}')`; the literal uses \\' and \\" escapes that
    plain json.loads() cannot read.
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


# ============================================================================
# 1. POLITE FETCHER — per-host spacing, robots.txt, cookies, observed statuses
# ============================================================================
class PoliteFetcher:
    """One HTTP client for the whole probe: pacing, robots, and full evidence.

    Why a class instead of bare urllib calls: pacing, robots and error capture
    are cross-cutting concerns, and repeating them at every call site is exactly
    how a collector silently drifts out of politeness. The cookie jar matters
    because some public pages hand out an XSRF token that their own API requires.
    """

    def __init__(self):
        self.ctx = ssl.create_default_context()
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    # -- pacing ------------------------------------------------------------
    def _pace(self, host: str) -> None:
        prev = self._last.get(host)
        if prev is not None:
            wait = MIN_HOST_INTERVAL - (time.time() - prev)
            if wait > 0:
                time.sleep(wait)
        self._last[host] = time.time()

    # -- robots ------------------------------------------------------------
    def robots_for(self, host: str):
        if host in self._robots:
            return self._robots[host]
        parser = None
        try:
            self._pace(host)
            req = urllib.request.Request(f"https://{host}/robots.txt",
                                         headers={"User-Agent": UA_BROWSER, "Accept": "text/plain,*/*"})
            with self.opener.open(req, timeout=10) as resp:
                body = resp.read().decode("utf-8", "replace")
            if "<html" not in body[:400].lower():
                parser = urllib.robotparser.RobotFileParser()
                parser.parse(body.splitlines())
        except Exception:
            parser = None            # absent/unreadable robots.txt == no restriction
        self._robots[host] = parser
        return parser

    def robots_rules(self, host: str) -> dict:
        parser = self.robots_for(host)
        if parser is None:
            return {"available": False, "disallow": [], "crawlDelay": None}
        # CPython 3.12 keeps the `User-agent: *` group in `default_entry` and
        # leaves `entries` empty, so both places have to be read or the report
        # claims "no rules" for hosts that in fact disallow everything.
        entries = list(getattr(parser, "entries", []) or [])
        default = getattr(parser, "default_entry", None)
        if default is not None:
            entries.append(default)
        disallow, agents = [], []
        for e in entries:
            uas = getattr(e, "useragents", []) or []
            agents.extend(uas)
            if not uas or "*" in uas:
                lines = getattr(e, "rulelines", None) or getattr(e, "rules", []) or []
                disallow.extend([(getattr(r, "path", "") or "")
                                 for r in lines if not getattr(r, "allowance", True)])
        return {"available": True,
                "agents": sorted(set(agents))[:12],
                "disallow": sorted({d for d in disallow})[:20],
                "crawlDelay": getattr(parser, "crawl_delay", lambda *_: None)(UA_BROWSER)}

    def allowed(self, url: str, ua: str = UA_BROWSER) -> bool:
        host = urllib.parse.urlsplit(url).netloc
        parser = self.robots_for(host)
        if parser is None:
            return True
        try:
            return parser.can_fetch(ua, url)
        except Exception:
            return True

    def cookie_header(self, host: str) -> str:
        out = []
        for c in self.jar:
            if host.endswith(c.domain.lstrip(".")) or c.domain.lstrip(".") in host:
                out.append(f"{c.name}={c.value}")
        return "; ".join(out)

    def cookie(self, name: str) -> str:
        for c in self.jar:
            if c.name == name:
                return c.value
        return ""

    # -- request -----------------------------------------------------------
    def request(self, url, *, method="GET", headers=None, data=None, ua=UA_BROWSER,
                timeout=DEFAULT_TIMEOUT, honour_robots=True) -> dict:
        host = urllib.parse.urlsplit(url).netloc
        rec = {"url": url, "method": method, "status": None, "contentType": "", "bytes": 0,
               "elapsedMs": 0, "error": None, "shape": "none", "itemCount": 0,
               "firstTitle": "", "robotsAllowed": None, "finalUrl": None,
               "preview": "", "note": "", "_body": b""}
        if honour_robots:
            ok = self.allowed(url, ua)
            rec["robotsAllowed"] = ok
            if not ok:
                rec["error"] = "robots.txt disallows this path for our user-agent"
                rec["shape"] = "skipped"
                return rec
        hdrs = {
            "User-Agent": ua,
            "Accept": "application/json, application/xml, text/xml, text/html;q=0.9, */*;q=0.7",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
        }
        if headers:
            hdrs.update(headers)
        self._pace(host)
        t0 = time.time()
        body = b""
        try:
            req = urllib.request.Request(url, headers=hdrs, data=data, method=method)
            with self.opener.open(req, timeout=timeout) as resp:
                body = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    body = gzip.decompress(body)
                rec["status"] = resp.status
                rec["contentType"] = resp.headers.get("Content-Type", "")
                rec["finalUrl"] = resp.geturl()
        except urllib.error.HTTPError as e:
            try:
                body = e.read()
            except Exception:
                body = b""
            rec["status"] = e.code
            rec["contentType"] = (e.headers.get("Content-Type", "") if e.headers else "")
            rec["error"] = f"HTTP {e.code}"
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"
        rec["elapsedMs"] = int((time.time() - t0) * 1000)
        rec["bytes"] = len(body)
        rec["_body"] = body
        self._describe(rec, body)
        return rec

    @staticmethod
    def _describe(rec: dict, body: bytes) -> None:
        """Fill shape / itemCount / firstTitle / preview from the raw body."""
        text = body.decode("utf-8", "replace")
        rec["preview"] = re.sub(r"\s+", " ", text[:300]).strip()
        if not body:
            rec["shape"] = "empty"
            return
        head = text.lstrip()[:200]
        if head[:1] in "{[":
            rec["shape"] = "json"
            try:
                data = json.loads(text)
            except Exception as e:
                rec["shape"] = "json_invalid"
                rec["note"] = str(e)[:90]
                return
            rows = extract_rows(data)
            rec["itemCount"] = len(rows)
            rec["firstTitle"] = first_title(rows)
            return
        if re.match(r"<\?xml|<rss|<feed", head, re.I):
            rec["shape"] = "xml"
            rec["itemCount"] = len(re.findall(r"<item[\s>]", text)) + len(re.findall(r"<entry[\s>]", text))
            titles = re.findall(r"<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", text, re.S)
            if titles:
                rec["firstTitle"] = clean(titles[1] if len(titles) > 1 else titles[0])
            return
        rec["shape"] = "html"
        rec["itemCount"] = count_html_items(text)
        m = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
        rec["firstTitle"] = clean(m.group(1)) if m else ""

    def body_text(self, rec: dict) -> str:
        return (rec.get("_body") or b"").decode("utf-8", "replace")


def extract_rows(data):
    """Best-effort list of records inside an unknown JSON payload.

    WHY the generic descent: every API names its list differently — Tencent uses
    {"Data": {"Posts": [...]}}, Crossref {"message": {"items": [...]}}, OpenAlex
    {"results": [...]}, S2 {"data": [...]}. A fixed key list silently reports
    "0 items" (i.e. `empty_json`) for the ones it does not know, which is exactly
    the kind of wrong conclusion this probe exists to prevent.
    """
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    for key in ("data", "results", "items", "Posts", "hits", "notes", "jobs", "posts",
                "datas", "list", "records", "Data", "message", "content"):
        val = data.get(key)
        if isinstance(val, list):
            return val
        if isinstance(val, dict):
            nested = extract_rows(val)
            if nested:
                return nested
    return []


def first_title(rows) -> str:
    for r in rows[:1]:
        if isinstance(r, dict):
            for key in ("title", "name", "RecruitPostName", "positionName", "jobName",
                        "display_name", "full_name", "modelId", "id"):
                if r.get(key):
                    return clean(r[key])
    return ""


def count_html_items(text: str) -> int:
    if 'class="Box-row"' in text:
        return len(re.findall(r'<article class="Box-row"', text)) or text.count("Box-row")
    if 'href="/discuss/' in text:
        return len(re.findall(r'href="/discuss/\d+', text))
    return 0


def sanitize(obj):
    """Drop raw bodies before the report is written."""
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [sanitize(v) for v in obj]
    return obj


# ============================================================================
# 2. CHANNEL-LEVEL PROBE — drive the real collectors from collect.py
# ============================================================================
def classify(status, count: int, err, http_statuses) -> str:
    """ok | empty | blocked | parse_error | dead | error  (first match wins)."""
    if err is None:
        return "ok" if count > 0 else "empty"
    low = (err or "").lower()
    codes = [s for s in (http_statuses or []) if isinstance(s, int)]
    if any(c in (401, 403, 451) for c in codes) or "403" in low or "401" in low:
        return "blocked"
    if any(c == 429 for c in codes) or "429" in low:
        return "blocked"
    if any(k in low for k in ("parseerror", "jsondecode", "not well-formed", "syntaxerror",
                              "mismatched tag", "undefined entity")):
        return "parse_error"
    if any(k in low for k in ("404", "not found", "nodename", "name or service",
                              "connection refused", "certificate", "sslerror", "timeout",
                              "timed out", "urlopen error", "remote end closed")):
        return "dead"
    return "error"


class QuietLogger:
    """Same call surface as collect.Logger, but records lines instead of printing."""

    def __init__(self):
        self.lines: list[str] = []
        self.verbose = False

    def __call__(self, msg, level="info"):
        self.lines.append(f"[{level}] {msg}")

    def detail(self, msg):
        self.lines.append(f"[detail] {msg}")


def probe_channel(mod, cid, cfg, limit: int) -> dict:
    """Run one channel through the real collector, recording observed HTTP statuses."""
    observed: list[dict] = []
    original = mod.http_get

    def recording_http_get(url, **kw):
        try:
            status, body, ct = original(url, **kw)
            observed.append({"url": str(url)[:300], "status": status,
                             "bytes": len(body) if body is not None else 0, "contentType": ct})
            return status, body, ct
        except urllib.error.HTTPError as e:
            observed.append({"url": str(url)[:300], "status": e.code, "bytes": 0,
                             "contentType": "", "error": f"HTTP {e.code}"})
            raise
        except Exception as e:
            observed.append({"url": str(url)[:300], "status": None, "bytes": 0,
                             "contentType": "", "error": f"{type(e).__name__}: {e}"})
            raise

    log = QuietLogger()
    mod.http_get = recording_http_get
    t0 = time.time()
    err, rows = None, []
    try:
        rows = mod.COLLECTORS[cid](cfg, log, limit) or []
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    finally:
        mod.http_get = original
    dur = round(time.time() - t0, 2)

    statuses = [o["status"] for o in observed if o.get("status") is not None]
    first = ""
    for r in rows:
        if isinstance(r, dict) and r.get("title"):
            first = clean(r["title"])
            break
    status = classify(statuses[-1] if statuses else None, len(rows), err, statuses)
    spec = mod.CHANNEL_SPECS.get(cid, {})
    return {
        "id": cid,
        "nameZh": mod.CHANNEL_NAMES.get(cid, cid),
        "tier": spec.get("tier", "P2"),
        "mode": spec.get("mode", "api"),
        "disabled": cid in (getattr(mod, "DISABLED_CHANNELS", {}) or {}),
        "status": status,
        "count": len(rows),
        "durationSec": dur,
        "firstTitle": first,
        "error": err,
        "httpStatuses": statuses,
        "httpCalls": observed,
        "collectorLog": log.lines[-25:],
        "riskNote": (getattr(mod, "DISABLED_CHANNELS", {}) or {}).get(cid, ""),
    }


# ============================================================================
# 3. CANDIDATE ENDPOINTS — ordered alternatives for the failing channels
# ============================================================================
def github_created_url(days: int = 7) -> str:
    since = (datetime.now(CST) - timedelta(days=days)).strftime("%Y-%m-%d")
    return ("https://api.github.com/search/repositories?q=" + urllib.parse.quote(f"created:>{since}") +
            "&sort=stars&order=desc&per_page=5")


BYTEDANCE_BODY = json.dumps({
    "keyword": "算法实习", "limit": 20, "offset": 0, "job_category_id_list": [],
    "tag_id_list": [], "location_code_list": [], "subject_id_list": [],
    "recruitment_id_list": [], "portal_type": 6}, ensure_ascii=False).encode("utf-8")

TENCENT_20 = ("https://careers.tencent.com/tencentcareer/api/post/Query?timestamp=0&countryId=&cityId="
              "&bgId=&bgIds=&productId=&categoryId=&parentCategoryId=&attrId=&keyword=%E7%AE%97%E6%B3%95"
              "&pageIndex=1&pageSize=20&language=zh-cn&area=cn")
TENCENT_10 = TENCENT_20.replace("pageSize=20", "pageSize=10")

ALIBABA_PAGE = "https://talent.alibaba.com/off-campus/position-list"

# WHY these candidates: each was either named in the task brief or discovered by
# reading the page/JS bundle that the broken channel used to call.
CANDIDATES: dict[str, list[dict]] = {
    "openreview": [
        {"label": "api2 notes", "url": "https://api2.openreview.net/notes?limit=5", "kind": "json"},
        {"label": "api1 (legacy) notes", "url": "https://api.openreview.net/notes?limit=5", "kind": "json"},
        {"label": "api2 venue filter",
         "url": "https://api2.openreview.net/notes?content.venueid=ICLR.cc%2F2026%2FConference&limit=5",
         "kind": "json"},
    ],
    "gh_trending": [
        {"label": "trending HTML (primary)", "url": "https://github.com/trending?since=daily",
         "htmlLinks": True},
        {"label": "trending/python HTML", "url": "https://github.com/trending/python?since=daily"},
        {"label": "REST search created:>7d", "url": github_created_url(7), "kind": "json"},
    ],
    "s2": [
        {"label": "graph search (legacy)",
         "url": "https://api.semanticscholar.org/graph/v1/paper/search?query=multimodal%20large%20language"
                "%20model&limit=5&fields=title,abstract,url,publicationDate", "kind": "json"},
        {"label": "graph search after 5s wait",
         "url": "https://api.semanticscholar.org/graph/v1/paper/search?query=post-training%20preference"
                "%20optimization&limit=5&fields=title,publicationDate", "kind": "json", "preDelay": 5.0},
        {"label": "graph search/bulk",
         "url": "https://api.semanticscholar.org/graph/v1/paper/search/bulk?query=multimodal"
                "&fields=title,url,publicationDate,authors,venue,citationCount,externalIds"
                "&sort=publicationDate:desc", "kind": "json"},
        {"label": "OpenAlex works",
         "url": "https://api.openalex.org/works?search=multimodal%20large%20language%20model&per-page=5"
                "&sort=publication_date:desc&mailto=workbench%40example.com", "kind": "json"},
        {"label": "Crossref works",
         "url": "https://api.crossref.org/works?query=multimodal+large+language+model&rows=5"
                "&sort=published&order=desc&select=DOI,title,abstract,URL,published,author,container-title",
         "kind": "json"},
    ],
    "reddit": [
        {"label": "top.json (legacy)", "url": "https://www.reddit.com/r/MachineLearning/top.json?t=day&limit=5",
         "ua": UA_PLAIN, "kind": "json"},
        {"label": "top .rss feed", "url": "https://www.reddit.com/r/MachineLearning/top/.rss?t=day&limit=5",
         "ua": UA_PLAIN},
        {"label": "robots.txt", "url": "https://www.reddit.com/robots.txt", "kind": "text"},
        {"label": "substitute: HN front page",
         "url": "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=5", "kind": "json"},
        {"label": "substitute: lobste.rs rss (robots-checked)", "url": "https://lobste.rs/rss"},
        {"label": "substitute: lobste.rs robots.txt", "url": "https://lobste.rs/robots.txt", "kind": "text"},
    ],
    "zhihu": [
        {"label": "api/v4 top_search", "url": "https://www.zhihu.com/api/v4/search/top_search", "kind": "json",
         "note": "zhihu robots.txt blocks /api/ for us; a direct request on 2026-10-01 (outside this probe) "
                 "answered 403 {\"error\":{\"need_login\":true}}"},
        {"label": "www.zhihu.com/hot page", "url": "https://www.zhihu.com/hot",
         "note": "direct request on 2026-10-01 answered 403 with an anti-bot page"},
        {"label": "mirror rss.injahow.cn hotlist", "url": "https://rss.injahow.cn/zhihu/hotlist"},
        {"label": "mirror rsshub.rssforever.com hotlist", "url": "https://rsshub.rssforever.com/zhihu/hotlist"},
        {"label": "mirror rsshub.app hotlist", "url": "https://rsshub.app/zhihu/hotlist"},
    ],
    "xiaohongshu": [
        {"label": "explore page (login-walled?)", "url": "https://www.xiaohongshu.com/explore"},
    ],
    "boss": [
        {"label": "zhipin home (login-walled?)", "url": "https://www.zhipin.com/"},
        {"label": "job search results (login-walled?)",
         "url": "https://www.zhipin.com/web/geek/job?query=%E7%AE%97%E6%B3%95&city=101010100",
         "note": "unauthenticated; a redirect to /web/user/ or an anti-bot page is the expected evidence"},
    ],
    "lagou": [
        {"label": "lagou home (login-walled?)", "url": "https://www.lagou.com/"},
        {"label": "job list (login-walled?)",
         "url": "https://www.lagou.com/wn/jobs?kd=%E7%AE%97%E6%B3%95&city=%E5%8C%97%E4%BA%AC",
         "note": "unauthenticated; a login redirect is the expected evidence"},
    ],
    "shixiseng": [
        {"label": "shixiseng home (login-walled?)", "url": "https://www.shixiseng.com/"},
        {"label": "internship search (login-walled?)",
         "url": "https://www.shixiseng.com/interns?keyword=%E7%AE%97%E6%B3%95",
         "note": "unauthenticated; a login redirect is the expected evidence"},
    ],
    "machineheart": [
        {"label": "site rss (was the primary)", "url": "https://www.jiqizhixin.com/rss"},
        {"label": "site rss/articles", "url": "https://www.jiqizhixin.com/rss/articles"},
        {"label": "site /feed", "url": "https://www.jiqizhixin.com/feed"},
        {"label": "rsshub.app jiqizhixin/daily", "url": "https://rsshub.app/jiqizhixin/daily"},
        {"label": "rss.injahow.cn jiqizhixin/daily", "url": "https://rss.injahow.cn/jiqizhixin/daily"},
        {"label": "substitute 雷锋网 feed", "url": "https://www.leiphone.com/feed"},
        {"label": "substitute InfoQ feed", "url": "https://www.infoq.cn/feed"},
        {"label": "substitute Solidot feed", "url": "https://www.solidot.org/index.rss"},
        {"label": "substitute OSChina feed", "url": "https://www.oschina.net/news/rss"},
    ],
    "rsshub": [
        {"label": "rsshub.app zhihu/hotlist", "url": "https://rsshub.app/zhihu/hotlist"},
        {"label": "rsshub.rssforever.com zhihu/hotlist", "url": "https://rsshub.rssforever.com/zhihu/hotlist"},
        {"label": "rss.injahow.cn zhihu/hotlist", "url": "https://rss.injahow.cn/zhihu/hotlist"},
        {"label": "rss.injahow.cn github/trending/daily/any",
         "url": "https://rss.injahow.cn/github/trending/daily/any"},
        {"label": "rss.injahow.cn solidot", "url": "https://rss.injahow.cn/solidot"},
        {"label": "rsshub.ktachibana.party zhihu/hotlist",
         "url": "https://rsshub.ktachibana.party/zhihu/hotlist"},
    ],
    "nowcoder": [
        {"label": "discuss list page", "url": "https://www.nowcoder.com/discuss?type=0&order=0"},
        {"label": "api/discuss/list", "url": "https://www.nowcoder.com/api/discuss/list?page=1&pageSize=10",
         "kind": "json"},
        {"label": "robots.txt", "url": "https://www.nowcoder.com/robots.txt", "kind": "text"},
    ],
    "jobs_bytedance": [
        {"label": "POST api/v1/search/job/posts", "method": "POST",
         "url": "https://jobs.bytedance.com/api/v1/search/job/posts", "data": BYTEDANCE_BODY,
         "headers": {"Content-Type": "application/json", "Accept": "application/json",
                     "Referer": "https://jobs.bytedance.com/", "Origin": "https://jobs.bytedance.com"},
         "kind": "json"},
        {"label": "GET api/v1/search/job/posts?keyword=",
         "url": "https://jobs.bytedance.com/api/v1/search/job/posts?keyword=%E7%AE%97%E6%B3%95%E5%AE%9E%E4%B9%A0"
                "&limit=20&offset=0&job_category_id_list=&tag_id_list=&location_code_list="
                "&subject_id_list=&recruitment_id_list=&portal_type=6", "kind": "json"},
        {"label": "experienced/position page", "url": "https://jobs.bytedance.com/experienced/position"},
        {"label": "robots.txt", "url": "https://jobs.bytedance.com/robots.txt", "kind": "text"},
    ],
    "jobs_tencent": [
        {"label": "post/Query pageSize=20", "url": TENCENT_20, "kind": "json"},
        {"label": "post/Query pageSize=10", "url": TENCENT_10, "kind": "json"},
        {"label": "robots.txt", "url": "https://careers.tencent.com/robots.txt", "kind": "text"},
    ],
    "jobs_alibaba": [
        {"label": "off-campus/position-list page (sets XSRF-TOKEN)", "url": ALIBABA_PAGE},
        {"label": "api/job/search (old endpoint)",
         "url": "https://talent.alibaba.com/api/job/search?keyword=%E7%AE%97%E6%B3%95&pageSize=20&pageNo=1"
                "&language=zh", "kind": "json"},
        {"label": "GET /position/search (real path, wrong verb)",
         "url": "https://talent.alibaba.com/position/search?keyword=%E7%AE%97%E6%B3%95", "kind": "json"},
        {"label": "POST /position/search with the page's own CSRF token", "method": "POST",
         "url": "https://talent.alibaba.com/position/search",
         "data": json.dumps({"channel": "off-campus", "language": "zh", "pageIndex": 1, "pageSize": 20,
                             "key": "算法", "categoryType": "social", "corpCode": "", "batchId": "",
                             "aliStar": ""}, ensure_ascii=False).encode("utf-8"),
         "headers": {"Content-Type": "application/json;charset=UTF-8", "Accept": "application/json",
                     "Origin": "https://talent.alibaba.com", "Referer": ALIBABA_PAGE},
         "alibabaCsrf": True, "kind": "json"},
    ],
    "jobs_zhipu": [
        {"label": "zhipuai.cn/joinus", "url": "https://zhipuai.cn/joinus"},
        {"label": "robots.txt", "url": "https://zhipuai.cn/robots.txt", "kind": "text"},
    ],
    "jobs_moonshot": [
        {"label": "moonshot.cn/careers", "url": "https://www.moonshot.cn/careers"},
        {"label": "careers.kimi.com (new host)", "url": "https://careers.kimi.com/"},
        {"label": "careers.kimi.com/jobs", "url": "https://careers.kimi.com/jobs"},
        {"label": "careers.kimi.com/positions", "url": "https://careers.kimi.com/positions"},
    ],
    "jobs_deepseek": [
        {"label": "www.deepseek.com/careers (config URL)", "url": "https://www.deepseek.com/careers"},
        {"label": "talent.deepseek.com (real host)",
         "url": "https://talent.deepseek.com/", "followUp": "deepseek"},
        {"label": "robots.txt", "url": "https://talent.deepseek.com/robots.txt", "kind": "text"},
    ],
    "jobs_minimax": [
        {"label": "minimaxi.com/careers", "url": "https://www.minimaxi.com/careers"},
        {"label": "Feishu ATSX portal", "url": "https://vrfi1sk8a0.jobs.feishu.cn/index/"},
        {"label": "Feishu ATSX api (POST)", "method": "POST",
         "url": "https://vrfi1sk8a0.jobs.feishu.cn/api/v1/search/job/posts",
         "data": json.dumps({"keyword": "算法", "limit": 10, "offset": 0,
                             "portal_type": 6}).encode("utf-8"),
         "headers": {"Content-Type": "application/json", "Accept": "application/json"}, "kind": "json"},
        {"label": "robots.txt", "url": "https://www.minimaxi.com/robots.txt", "kind": "text"},
    ],
    "jobs_shailab": [
        {"label": "shlab.org.cn/joinus", "url": "https://www.shlab.org.cn/joinus"},
        {"label": "shlab.org.cn/joinus/social", "url": "https://www.shlab.org.cn/joinus/social"},
        {"label": "shlab.org.cn/joinus/campus", "url": "https://www.shlab.org.cn/joinus/campus"},
    ],
}

GITHUB_TRENDING_REGEXES = [
    {"label": "shipped before this fix (broken)",
     "pattern": r'<h2 class="h3 lh-condensed">\s*<a href="/([^"]+)"'},
    {"label": "candidate A: h2 class lh-condensed, attributes allowed before href",
     "pattern": r'<h2 class="h3 lh-condensed">\s*<a[^>]*?href="/([^"]+)"'},
    {"label": "candidate B: any h2 whose inner <a> is owner/repo",
     "pattern": r'<h2[^>]*>\s*<a[^>]*?href="/([^"/]+/[^"/]+)"'},
    {"label": "candidate C: article card boundary",
     "pattern": r'<article class="Box-row">'},
    {"label": "card piece: description paragraph",
     "pattern": r'<p class="col-9 color-fg-muted my-1[^"]*">\s*(.*?)\s*</p>'},
    {"label": "card piece: total stars",
     "pattern": r'/stargazers"[^>]*>\s*(?:<[^>]+>\s*)*([\d,\.k]+)'},
    {"label": "card piece: stars today",
     "pattern": r'([\d,\.k]+)\s+stars?\s+today'},
    {"label": "card piece: language",
     "pattern": r'itemprop="programmingLanguage">\s*([^<]+?)\s*<'},
]


def verdict_for(rec: dict, spec: dict) -> str:
    if rec.get("robotsAllowed") is False:
        return "robots_disallowed"
    final = (rec.get("finalUrl") or "")
    if final and "login" in final.lower() and final != rec.get("url"):
        return "login_walled"
    st = rec.get("status")
    if st is None:
        return "unreachable"
    if st in (401, 403, 451):
        return "blocked"
    if st == 429:
        return "rate_limited"
    if st in (405, 501):
        return "wrong_method"
    if st == 404:
        return "dead"
    if st >= 500:
        return "server_error"
    if st == 200:
        shape = rec.get("shape")
        if spec.get("kind") == "text":
            return "works"
        if shape == "xml":
            return "works" if rec.get("itemCount") else "empty_feed"
        if shape == "json":
            if rec.get("itemCount"):
                return "works"
            if "success" in (rec.get("preview") or "").lower():
                return "works_but_empty"
            return "empty_json"
        if spec.get("kind") == "json" and shape == "html":
            return "not_json"
        if rec.get("itemCount"):
            return "works"
        return "empty_html"
    return "unexpected"


def probe_candidates(specs, fetcher: PoliteFetcher) -> list[dict]:
    """Test every candidate endpoint for one channel, in the declared order."""
    results = []
    for spec in specs:
        if spec.get("preDelay"):
            time.sleep(float(spec["preDelay"]))
        headers = dict(spec.get("headers") or {})
        url = spec["url"]
        if spec.get("alibabaCsrf"):
            # The public page sets XSRF-TOKEN; the API requires it as ?_csrf=.
            # This is normal CSRF handling for a public endpoint, not an auth bypass.
            csrf = fetcher.cookie("XSRF-TOKEN")
            host = urllib.parse.urlsplit(url).netloc
            if csrf:
                url = url + ("&" if "?" in url else "?") + "_csrf=" + urllib.parse.quote(csrf)
            cookie = fetcher.cookie_header(host)
            if cookie:
                headers["Cookie"] = cookie
        rec = fetcher.request(url, method=spec.get("method", "GET"), headers=headers,
                              data=spec.get("data"), ua=spec.get("ua", UA_BROWSER),
                              timeout=spec.get("timeout", DEFAULT_TIMEOUT))
        rec["label"] = spec.get("label", spec["url"])
        rec["verdict"] = verdict_for(rec, spec)
        if spec.get("note"):
            rec["note"] = "; ".join(x for x in (rec.get("note"), spec["note"]) if x)
        if spec.get("htmlLinks"):
            rec["note"] = (rec.get("note") or "") + f" | trending cards={rec.get('itemCount')}"
        if spec.get("followUp") == "deepseek":
            extraction = deepseek_bundle_extract(fetcher, rec)
            rec["extraction"] = extraction
            if extraction.get("jobCount"):
                # The landing page is an empty shell; the evidence lives one hop
                # deeper, in the bundle. Report the hop, not the shell.
                rec["verdict"] = "works_via_bundle"
                rec["itemCount"] = extraction["jobCount"]
                rec["firstTitle"] = (extraction.get("titles") or [""])[0]
                rec["note"] = (rec.get("note") or "") + \
                    f" | bundle {extraction.get('bundleUrl')} carries {extraction['jobCount']} jobs" \
                    f" (crawledAt {extraction.get('crawledAt')})"
            else:
                rec["verdict"] = "empty_html"
        results.append(rec)
    return results


def deepseek_bundle_extract(fetcher: PoliteFetcher, page_rec: dict) -> dict:
    """Pull the job catalogue that talent.deepseek.com inlines into its JS bundle.

    WHY: the SPA front page is only 588 bytes and its API needs a browser, but the
    production bundle ships a build-time snapshot of the Moka ATS listing as a
    literal `JSON.parse('{"crawledAt":...,"jobs":[...]}')`. That literal is public,
    server-provided data and is exactly what the site itself renders from.
    """
    out = {"why": "site inlines a build-time job catalogue as JSON.parse(<literal>) in main.js"}
    text = fetcher.body_text(page_rec)
    m = (re.search(r'<script[^>]+src="(/static/main[^"]+\.js)"', text)
         or re.search(r'"(/static/main\.[0-9a-z]+\.js)"', text))
    if not m:
        out["error"] = "main bundle not referenced by the landing page"
        return out
    js_url = "https://talent.deepseek.com" + m.group(1)
    js_rec = fetcher.request(js_url, timeout=30)
    out["bundleUrl"] = js_url
    out["bundleStatus"] = js_rec["status"]
    out["bundleBytes"] = js_rec["bytes"]
    js = fetcher.body_text(js_rec)
    m2 = re.search(r"JSON\.parse\('(\{\"crawledAt\".*?)'\)", js, re.S)
    if not m2:
        out["error"] = "JSON.parse catalogue literal not found in the bundle"
        return out
    try:
        data = json.loads(js_literal_decode(m2.group(1)))
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        return out
    jobs = data.get("jobs") or []
    out.update({
        "crawledAt": data.get("crawledAt"),
        "sourceUrl": data.get("sourceUrl"),
        "total": data.get("total"),
        "jobCount": len(jobs),
        "withDescription": sum(1 for j in jobs if j.get("descriptionHtml")),
        "functionCategories": [c.get("name") or c.get("label") for c in (data.get("functionCategories") or [])],
        "titles": [j.get("title") for j in jobs][:10],
    })
    return out


def test_github_regexes(fetcher: PoliteFetcher) -> dict:
    """Fetch today's trending page and report which regex really matches its markup."""
    url = "https://github.com/trending?since=daily"
    rec = fetcher.request(url, timeout=30)
    out = {"url": url, "fetch": sanitize(rec), "region": "", "regexes": [], "cardFields": {}}
    text = fetcher.body_text(rec)
    if rec["status"] != 200 or not text:
        return out
    m = re.search(r'<article class="Box-row">', text)
    if m:
        out["region"] = text[m.start():m.start() + 600]
    for spec in GITHUB_TRENDING_REGEXES:
        found = re.findall(spec["pattern"], text, re.S)
        out["regexes"].append({
            "label": spec["label"], "pattern": spec["pattern"], "matchCount": len(found),
            "sample": [clean(x) if isinstance(x, str) else clean(x[0]) for x in found[:5]],
        })
    art = re.compile(r'<article class="Box-row">(.*?)</article>', re.S)
    repo = re.compile(r'<h2 class="h3 lh-condensed">\s*<a[^>]*?href="/([^"]+)"')
    desc = re.compile(r'<p class="col-9 color-fg-muted my-1[^"]*">\s*(.*?)\s*</p>', re.S)
    stars = re.compile(r'/stargazers"[^>]*>\s*(?:<[^>]+>\s*)*([\d,\.k]+)')
    today = re.compile(r'([\d,\.k]+)\s+stars?\s+today')
    lang = re.compile(r'itemprop="programmingLanguage">\s*([^<]+?)\s*<')
    cards = []
    for block in art.findall(text):
        rp = repo.search(block)
        if not rp:
            continue
        cards.append({
            "fullName": rp.group(1).strip(),
            "description": clean(re.sub(r"<[^>]+>", " ", desc.search(block).group(1))) if desc.search(block) else "",
            "stars": stars.search(block).group(1) if stars.search(block) else "",
            "starsToday": today.search(block).group(1) if today.search(block) else "",
            "language": lang.search(block).group(1) if lang.search(block) else "",
        })
    out["cardFields"] = {"cards": len(cards), "sample": cards[:5],
                         "cardsWithDescription": sum(1 for c in cards if c["description"]),
                         "cardsWithStars": sum(1 for c in cards if c["stars"])}
    return out


# ============================================================================
# 4. REPORT + TABLE
# ============================================================================
def print_channel_table(rows: list[dict]) -> None:
    safe_print("")
    safe_print("CHANNELS (real collectors from scripts/collect.py)")
    safe_print(f"{'channel':<18}{'status':<13}{'items':>6}{'sec':>8}  {'http':<10}first item / error")
    safe_print("-" * 118)
    for r in rows:
        http = ",".join(str(s) for s in (r.get("httpStatuses") or [])[-3:]) or "-"
        extra = r.get("error") or r.get("firstTitle") or r.get("riskNote") or ""
        safe_print(f"{r['id']:<18}{r['status']:<13}{r['count']:>6}{r['durationSec']:>8}  {http:<10}{extra[:58]}")


def print_candidate_table(cands: dict) -> None:
    safe_print("")
    safe_print("CANDIDATE ENDPOINTS")
    safe_print(f"{'channel':<16}{'verdict':<19}{'st':>4}{'bytes':>9} {'shape':<11}{'items':>6}  label")
    safe_print("-" * 132)
    for cid, rows in cands.items():
        for r in rows:
            safe_print(f"{cid:<16}{r['verdict']:<19}{str(r.get('status')):>4}{r.get('bytes', 0):>9} "
                       f"{str(r.get('shape')):<11}{r.get('itemCount', 0):>6}  {r['label'][:54]}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="probe-channels.py",
        description="Probe every collector channel and candidate replacement endpoint (stdlib only)")
    ap.add_argument("--only", help="comma-separated channel ids")
    ap.add_argument("--json", action="store_true", help="print the machine-readable report to stdout")
    ap.add_argument("--limit", type=int, default=3, help="item cap passed to each collector (default 3)")
    ap.add_argument("--skip-channels", action="store_true", help="only test candidate endpoints")
    ap.add_argument("--skip-candidates", action="store_true", help="only run the collectors")
    ap.add_argument("--robots-only", action="store_true",
                    help="refresh just the robots.txt section of an existing report (19 cheap requests)")
    ap.add_argument("--out", default=str(REPORT_PATH), help="report path (default research/channel_probe.json)")
    args = ap.parse_args(argv)

    t0 = time.time()
    robots_only = args.robots_only
    if robots_only:
        args.skip_channels = args.skip_candidates = True
    try:
        mod = load_collect()
    except Exception as e:
        if not robots_only:
            raise
        safe_print(f"collect.py not importable ({type(e).__name__}); --robots-only continues")
        mod = None
    fetcher = PoliteFetcher()
    only = {c.strip() for c in (args.only or "").split(",") if c.strip()}

    safe_print(f"probe v{PROBE_VERSION} | collect.py v{getattr(mod, 'COLLECTOR_VERSION', '?')} | {now_iso()}")

    cfg = mod.load_config(mod.CONFIG_PATH, mod.Logger(False)) if mod else {}
    cfg.setdefault("limits", {})["perChannel"] = args.limit
    cfg.setdefault("arxiv", {})["maxPerQuery"] = args.limit          # keep the probe quick
    cfg.setdefault("github", {})["queries"] = ["multimodal llm", "llm inference engine"]

    disabled = (getattr(mod, "DISABLED_CHANNELS", {}) or {}) if mod else {}
    channel_rows: list[dict] = []
    if not args.skip_channels:
        wanted = [c for c in mod.COLLECTORS if (not only or c in only)]
        for cid in wanted:
            if cid in disabled:
                spec = mod.CHANNEL_SPECS.get(cid, {})
                channel_rows.append({
                    "id": cid, "nameZh": mod.CHANNEL_NAMES.get(cid, cid),
                    "tier": spec.get("tier", "P2"), "mode": spec.get("mode", "api"),
                    "disabled": True, "status": "blocked", "count": 0, "durationSec": 0.0,
                    "firstTitle": "", "error": None, "httpStatuses": [], "httpCalls": [],
                    "collectorLog": [], "riskNote": disabled.get(cid, ""),
                })
                safe_print(f"  [skip] {cid:<16} DISABLED_CHANNELS: {disabled.get(cid, '')[:74]}")
                continue
            try:
                row = probe_channel(mod, cid, cfg, args.limit)
            except Exception as e:                      # one bad channel must not kill the probe
                row = {"id": cid, "nameZh": cid, "tier": "P2", "mode": "?", "disabled": False,
                       "status": "error", "count": 0, "durationSec": 0.0, "firstTitle": "",
                       "error": f"probe harness: {type(e).__name__}: {e}", "httpStatuses": [],
                       "httpCalls": [], "collectorLog": [], "riskNote": ""}
            channel_rows.append(row)
            safe_print(f"  {row['status']:<12} {cid:<16} {row['count']:>4} items {row['durationSec']:>6.1f}s "
                       f"http={row['httpStatuses'][-3:]} {(row.get('error') or row.get('firstTitle') or '')[:46]}")

    cands: dict[str, list[dict]] = {}
    if not args.skip_candidates:
        for cid, specs in CANDIDATES.items():
            if only and cid not in only:
                continue
            try:
                cands[cid] = probe_candidates(specs, fetcher)
            except Exception as e:
                cands[cid] = [{"label": "harness failure", "url": "", "verdict": "error", "status": None,
                               "bytes": 0, "shape": "none", "itemCount": 0,
                               "note": f"{type(e).__name__}: {e}", "_body": b""}]
            safe_print(f"  candidates {cid}: " +
                       ", ".join(f"{r['label'][:26]}={r['verdict']}" for r in cands[cid]))

    gh_regex: dict = {}
    if not args.skip_candidates:
        safe_print("  testing GitHub Trending regexes against today's markup ...")
        try:
            gh_regex = test_github_regexes(fetcher)
            for r in gh_regex.get("regexes", []):
                safe_print(f"    {r['matchCount']:>4} matches  {r['label'][:64]}")
            cf = gh_regex.get("cardFields", {})
            safe_print(f"    shipped card parser: {cf.get('cards')} cards, "
                       f"{cf.get('cardsWithDescription')} with description, {cf.get('cardsWithStars')} with stars")
        except Exception as e:
            gh_regex = {"error": f"{type(e).__name__}: {e}"}

    robots = {}
    for host in ("github.com", "api.github.com", "api.semanticscholar.org", "api.openalex.org",
                 "api.crossref.org", "www.reddit.com", "lobste.rs", "www.nowcoder.com",
                 "careers.tencent.com", "talent.deepseek.com", "talent.alibaba.com",
                 "www.leiphone.com", "www.jiqizhixin.com", "rss.injahow.cn", "zhipuai.cn",
                 "www.moonshot.cn", "www.shlab.org.cn", "www.minimaxi.com", "jobs.bytedance.com"):
        try:
            robots[host] = fetcher.robots_rules(host)
        except Exception as e:
            robots[host] = {"available": False, "error": f"{type(e).__name__}: {e}"}

    summary: dict[str, int] = {}
    for r in channel_rows:
        summary[r["status"]] = summary.get(r["status"], 0) + 1

    out_path = Path(args.out)
    report = {
        "generatedAt": now_iso(),
        "probeVersion": PROBE_VERSION,
        "collectorVersion": getattr(mod, "COLLECTOR_VERSION", "?") if mod else "?",
        "durationSec": round(time.time() - t0, 1),
        "limit": args.limit,
        "policy": {
            "minSecondsBetweenSameHost": MIN_HOST_INTERVAL,
            "robotsTxt": "fetched once per host, honoured via urllib.robotparser; disallowed paths are not requested",
            "loginWalled": "no login, no challenge solving, no paywall bypass; login-walled channels stay manual-only",
        },
        "summary": summary,
        "disabledChannels": disabled,
        "manualOnly": [
            {"id": cid, "nameZh": mod.CHANNEL_NAMES.get(cid, cid),
             "why": "login-walled; a human export -> import flow feeds it instead of a scraper"}
            for cid in sorted(getattr(mod, "MANUAL_ONLY", set()))
        ],
        "channels": channel_rows,
        "candidates": cands,
        "robots": robots,
        "githubTrending": gh_regex,
    }
    if robots_only:
        # Patch only the robots section so refreshing robots health does not cost
        # a full re-probe (and does not require collect.py to be importable).
        if not out_path.exists():
            safe_print(f"--robots-only needs an existing report at {out_path}")
            return 2
        report = json.loads(out_path.read_text("utf-8"))
        report["robots"] = robots
        report["robotsRefreshedAt"] = now_iso()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(sanitize(report), ensure_ascii=False, indent=1), "utf-8")

    if args.json:
        safe_print(json.dumps(sanitize(report), ensure_ascii=False, indent=1))
        return 0

    print_channel_table(channel_rows)
    print_candidate_table(cands)
    if gh_regex:
        safe_print("")
        safe_print("GITHUB TRENDING REGEX EVIDENCE")
        for r in gh_regex.get("regexes", []):
            safe_print(f"  {r['matchCount']:>4} x {r['label']}")
            safe_print(f"        {r['pattern']}")
            if r["sample"]:
                safe_print(f"        sample: {r['sample'][:3]}")
        safe_print("  first 600 chars of the region containing repository links:")
        safe_print("  " + (gh_regex.get("region") or "(not captured)")[:600].replace("\n", " "))
    safe_print("")
    safe_print("ROBOTS.TXT (generic user-agent section)")
    for host, rules in robots.items():
        if isinstance(rules, dict) and rules.get("available"):
            safe_print(f"  {host:<26} disallow={rules.get('disallow')}")
        else:
            safe_print(f"  {host:<26} no robots.txt / unreadable -> unrestricted")
    safe_print("")
    safe_print(f"summary: {summary}")
    safe_print(f"report : {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
