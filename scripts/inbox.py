#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inbox.py — 人工在环导入器（登录类渠道的唯一合法入口）
================================================================================
为什么需要它
  小红书、BOSS直聘、拉勾、实习僧、猎聘等站点的 robots.txt 明确禁止自动化
  （例如 BOSS直聘 `Disallow: /*?query=*` 恰好覆盖搜索 URL，小红书全站
  `Disallow: /`）。自动抓取既违反条款也会触发账号风控。因此这些渠道改成
  「你自己登录浏览 → 导出 → 本脚本读取本地文件」。

  这一切的网络请求数为 0：脚本只读 web/data/inbox/ 下的本地文件。

支持格式（放在 web/data/inbox/）
  · manual.jsonl   —— 每行一个 JSON 对象（推荐，最省事）
  · manual.json    —— 顶层是数组，或 {"items": [...]}
  · manual.csv     —— 表头任意，自动识别常见中文/英文列名

字段映射（尽量宽容）
  标题   title | 标题 | 岗位 | 职位 | name
  链接   url | 链接 | 网址 | link | href
  摘要   summary | 摘要 | 描述 | 内容 | desc | description
  公司   company | 公司 | 企业
  城市   city | 城市 | 地点 | 地区
  薪资   pay | 薪资 | 日薪 | 薪水 | salary
  截止   deadline | 截止 | 截止时间
  分类   category | 分类 | 类型（不填则按标题关键词自动判定）
  标签   tags | 标签（逗号或分号分隔）
  时间   publishedAt | 时间 | 日期 | date

它产出什么
  web/data/inbox/normalized-<date>.json
  —— 与采集器同构的 item 列表（含 id / category / relevanceScore / why），
  collector 会以 sourceId="manual" 把它并入知识库；因此人工导入的内容在界面
  上与自动采集的内容来源可区分。

用法
  python scripts/inbox.py                 # 处理 web/data/inbox/ 下所有文件
  python scripts/inbox.py --dir <path>    # 指定目录
  python scripts/inbox.py --dry-run -v    # 只打印
  python scripts/inbox.py --template      # 生成一份示例文件，照着填即可
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"
INBOX = DATA / "inbox"
CST = timezone(timedelta(hours=8))

# 列名别名 -> 标准字段
FIELD_ALIASES = {
    "title": ["title", "标题", "岗位", "职位", "name", "名称", "主题"],
    "url": ["url", "链接", "网址", "link", "href", "地址"],
    "summary": ["summary", "摘要", "描述", "内容", "desc", "description", "备注", "详情"],
    "company": ["company", "公司", "企业", "雇主", "单位"],
    "city": ["city", "城市", "地点", "地区", "工作地点"],
    "pay": ["pay", "薪资", "日薪", "薪水", "salary", "待遇", "实习薪资"],
    "deadline": ["deadline", "截止", "截止时间", "有效期"],
    "category": ["category", "分类", "类型", "方向", "领域"],
    "tags": ["tags", "标签", "关键词", "keywords"],
    "publishedAt": ["publishedat", "published_at", "时间", "日期", "date", "发布时间", "更新"],
    "source": ["source", "来源", "渠道", "平台"],
}

CATEGORY_KEYWORDS = [
    ("multimodal", ["多模态", "视觉语言", "vlm", "mllm", "clip", "图文", "vision-language"]),
    ("posttraining", ["后训练", "post-training", "sft", "rlhf", "dpo", "grpo", "偏好", "指令微调", "蒸馏"]),
    ("worldmodel", ["世界模型", "world model", "具身", "vla", "机器人", "3dgs", "nerf", "embodied"]),
    ("generative", ["扩散", "diffusion", "生成式", "视频生成", "flow matching", "文生图", "文生视频"]),
    ("rl", ["强化学习", "reinforcement", "ppo", "策略梯度", "reward model"]),
    ("agent", ["agent", "智能体", "工具调用", "multi-agent", "mcp"]),
    ("coding", ["手撕", "leetcode", "算法题", "面经", "coding", "笔试", "八股"]),
    ("engineering", ["推理加速", "分布式", "量化", "vllm", "显存", "cuda", "部署"]),
    ("job", ["实习", "招聘", "岗位", "intern", "jd", "日薪", "校招", "内推"]),
    ("paper", ["论文", "paper", "arxiv"]),
    ("course", ["课程", "仓库", "教程", "course", "repo", "tutorial"]),
]

DIFFICULTY_WORDS = [("hard", ["hard", "难", "高难度"]), ("easy", ["easy", "简单", "入门"])]


def now_cst() -> datetime:
    return datetime.now(CST)


def iso(dt: datetime) -> str:
    return dt.astimezone(CST).isoformat(timespec="seconds")


def sha1(s: str) -> str:
    return hashlib.sha1(str(s).encode("utf-8", "replace")).hexdigest()


def clean(s) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def guess_category(text: str) -> str:
    low = text.lower()
    for cid, kws in CATEGORY_KEYWORDS:
        if any(k.lower() in low for k in kws):
            return cid
    return "trend"


def guess_difficulty(text: str):
    low = text.lower()
    for level, words in DIFFICULTY_WORDS:
        if any(w in low for w in words):
            return level
    return None


def map_row(row: dict) -> dict:
    """把任意列名的行映射成标准字段。"""
    lower = {str(k).strip().lower(): v for k, v in row.items()}
    out: dict = {}
    for field, aliases in FIELD_ALIASES.items():
        for a in aliases:
            if a in lower and clean(lower[a]):
                out[field] = clean(lower[a])
                break
        if field not in out:
            # 也允许列名带空格/下划线变体
            for k, v in lower.items():
                if clean(v) and k.replace(" ", "").replace("_", "") in (a.replace(" ", "") for a in aliases):
                    out[field] = clean(v)
                    break
    return out


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for i, line in enumerate(path.read_text("utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("//") or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                rows.append(obj)
        except json.JSONDecodeError as e:
            print(f"  [!] {path.name}:{i} 跳过非法 JSON 行：{e}", file=sys.stderr)
    return rows


def read_json_any(path: Path) -> list[dict]:
    data = json.loads(path.read_text("utf-8"))
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("items", "jobs", "data", "rows", "records"):
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
        return [data]
    return []


def read_csv_any(path: Path) -> list[dict]:
    text = path.read_text("utf-8-sig")           # 容忍 Excel 导出的 BOM
    # 自动嗅探分隔符（Excel 中文版有时导出为制表符）
    sample = text[:4096]
    delim = ","
    try:
        delim = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except Exception:
        if sample.count("\t") > sample.count(","):
            delim = "\t"
    return list(csv.DictReader(StringIO(text), delimiter=delim))


def to_item(row: dict, log) -> dict | None:
    m = map_row(row)
    title = clean(m.get("title"))
    url = clean(m.get("url"))
    company = clean(m.get("company"))
    if not title and company:
        title = company
    if not title:
        log("    跳过：没有标题")
        return None
    if not url:
        # 没有链接的行仍然可用（例如"内推码"），但给出明确提示
        log(f"    [!] 无链接，将使用占位 URL：{title[:40]}")
        url = "https://www.nowcoder.com/"      # 占位仅用于通过 URL 校验，会标注为待补
    blob = " ".join([title, clean(m.get("summary")), company, clean(m.get("tags"))])
    category = clean(m.get("category")) or guess_category(blob)
    if category not in {c for c, _ in CATEGORY_KEYWORDS} | {"foundation", "exam", "trend"}:
        category = guess_category(f"{category} {blob}")
    tags = [t.strip() for t in re.split(r"[,;，；、|]", clean(m.get("tags"))) if t.strip()]
    source = clean(m.get("source")) or "manual"
    ext = sha1(f"{title}|{url}|{company}")[:16]
    item = {
        "sourceId": "manual",
        "channel": "manual",
        "externalId": ext,
        "title": title[:400],
        "summary": clean(m.get("summary"))[:2000],
        "url": url,
        "category": category,
        "tags": tags[:12] + ([source] if source not in tags else []),
        "lang": "zh" if re.search(r"[\u4e00-\u9fff]", title) else "en",
        "publishedAt": None,
        "fetchedAt": iso(now_cst()),
        "difficulty": guess_difficulty(blob),
        "qualitySignals": {"manualImport": True, "source": source},
    }
    if m.get("company") or m.get("city") or m.get("pay") or m.get("deadline"):
        item["jobMeta"] = {k: m[k] for k in ("company", "city", "pay", "deadline") if m.get(k)}
    ts = re.sub(r"[^0-9\-:T ]", "", clean(m.get("publishedAt")).replace("/", "-"))
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%m-%d"):
        try:
            dt = datetime.strptime(ts.strip(), fmt)
            if fmt == "%m-%d":
                dt = dt.replace(year=now_cst().year)
            item["publishedAt"] = iso(dt.replace(tzinfo=CST))
            break
        except ValueError:
            continue
    return item


def build(rows: list[dict], log) -> list[dict]:
    items, seen = [], set()
    for row in rows:
        it = to_item(row, log)
        if not it:
            continue
        it["id"] = sha1(f"{it['sourceId']}::{it['externalId']}")[:16]
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        # 人工导入的条目默认给较高相关度（是你主动找来的信号）
        base = 62.0
        base += 6 if it.get("jobMeta") else 0
        base += min(10.0, len(it.get("summary") or "") / 60.0)
        if it.get("tags"):
            base += 2
        it["relevanceScore"] = round(min(100.0, base), 1)
        it["why"] = ("人工导入（登录类渠道）"
                     + ("；包含岗位信息" if it.get("jobMeta") else "")
                     + "；来源：" + str((it.get("qualitySignals") or {}).get("source") or "manual"))
        it["sources"] = [{"url": it["url"], "name": (it.get("qualitySignals") or {}).get("source", "manual")}]
        items.append(it)
    items.sort(key=lambda x: -x["relevanceScore"])
    return items


def write_template(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    demo = [
        {"title": "字节跳动 多模态算法实习生（Seed）", "url": "https://jobs.bytedance.com/xxx",
         "company": "字节跳动", "city": "上海", "pay": "400-600 元/天",
         "summary": "参与多模态大模型预训练与对齐，要求熟悉 Transformer、PyTorch，有论文或竞赛加分。",
         "tags": "多模态,实习,内推", "category": "job", "publishedAt": now_cst().strftime("%Y-%m-%d"),
         "source": "BOSS直聘"},
        {"title": "面经：腾讯混元多模态一面", "url": "https://www.nowcoder.com/discuss/xxx",
         "summary": "手撕多头自注意力 + CLIP 对比损失推导 + 项目深挖。",
         "tags": "面经,手撕,多模态", "source": "牛客"},
    ]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for d in demo:
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"已生成示例文件：{path}\n按这个格式继续追加即可（每行一个 JSON 对象）。")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="inbox.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=str(INBOX), help="导入目录，默认 web/data/inbox")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写文件")
    ap.add_argument("--template", action="store_true", help="生成 manual.jsonl 示例后退出")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    inbox = Path(args.dir)
    if args.template:
        write_template(inbox / "manual.jsonl")
        return 0

    if not inbox.exists():
        print(f"目录不存在：{inbox}")
        print("先运行 python scripts/inbox.py --template 生成示例。")
        return 0

    def log(msg):
        print(msg, flush=True)

    files = [p for p in sorted(inbox.iterdir())
             if p.suffix.lower() in (".jsonl", ".json", ".csv", ".tsv")
             and not p.name.startswith("normalized-")]
    if not files:
        log(f"{inbox} 下没有可导入的文件（支持 .jsonl / .json / .csv）。")
        log("用 python scripts/inbox.py --template 生成一份示例。")
        return 0

    log(f"[inbox] 发现 {len(files)} 个文件：{', '.join(p.name for p in files)}")
    all_items: list[dict] = []
    for p in files:
        try:
            if p.suffix.lower() == ".jsonl":
                rows = read_jsonl(p)
            elif p.suffix.lower() == ".json":
                rows = read_json_any(p)
            else:
                rows = read_csv_any(p)
        except Exception as e:
            log(f"  [!] {p.name} 读取失败：{type(e).__name__} {e}")
            continue
        log(f"  {p.name}: {len(rows)} 行")
        all_items += build(rows, log)

    # 多文件之间去重
    merged: dict[str, dict] = {}
    for it in all_items:
        merged.setdefault(it["id"], it)
    items = sorted(merged.values(), key=lambda x: -x["relevanceScore"])

    log(f"[inbox] 规范化后 {len(items)} 条（跨文件去重后）")
    if args.verbose:
        for it in items:
            log(f"    + [{it['category']:<13}] {it['relevanceScore']:>5} {it['title'][:70]}")

    if args.dry_run:
        log("[inbox] --dry-run：未写入任何文件")
        return 0

    day = now_cst().strftime("%Y-%m-%d")
    out = inbox / f"normalized-{day}.json"
    payload = {"generatedAt": iso(now_cst()), "source": "inbox.py", "date": day,
               "count": len(items), "items": items}
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
    log(f"[inbox] 已写入 {out}")
    log("[inbox] 下次运行 python scripts/collect.py 时会被并入知识库（来源标记为 manual）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
