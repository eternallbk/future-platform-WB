# -*- coding: utf-8 -*-
"""_gen_model_drills.py — 总装：合并五组内容集，exec 验证全部代码，
写出 research/model_drill_analysis.json。

产物形状：
    {"generatedAt", "source", "drills": {<题库键>: {"tldr","why",
     "teaching","diagram","concepts","problem"}}}

build_problem_bank.merge_drill_analysis() 会把每个 drill 并进对应
题库实体（填补缺失、drill 独有层直接写入）。合并规则见该函数 docstring。
"""

from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _drills_helpers import run_all          # noqa: E402
import _drills_set1                          # noqa: E402
import _drills_set2                          # noqa: E402
import _drills_set3                          # noqa: E402
import _drills_set4                          # noqa: E402
import _drills_set5                          # noqa: E402

OUT = HERE.parent.parent / "research" / "model_drill_analysis.json"
CST = timezone(timedelta(hours=8))

EXPECTED_KEYS = {
    "curated-mha-implementation",
    "curated-kv-cache-memory",
    "curated-dpo-loss",
    "curated-gae-and-grpo",
    "curated-softmax-stable",
    "curated-top-k-top-p-sampling",
    "curated-cross-entropy-backward",
    "curated-flashattention-concept",
    "curated-layernorm-rmsnorm",
    "curated-rope-implementation",
    "curated-lora-implementation",
    "curated-ddpm-sampling",
    "curated-clip-contrastive-loss",
    "curated-batchnorm",
    "curated-transformer-block",
}

REQUIRED_LAYERS = ("tldr", "why", "teaching", "diagram", "concepts", "problem")


def main() -> int:
    drills: dict = {}
    for mod in (_drills_set1, _drills_set2, _drills_set3,
                _drills_set4, _drills_set5):
        dup = drills.keys() & mod.D.keys()
        if dup:
            raise SystemExit(f"[fatal] 跨文件重复的 drill 键: {sorted(dup)}")
        drills.update(mod.D)

    missing = EXPECTED_KEYS - set(drills)
    extra = set(drills) - EXPECTED_KEYS
    if missing:
        print(f"[warn] 计划内但缺失的键: {sorted(missing)}", file=sys.stderr)
    if extra:
        print(f"[warn] 计划外的键: {sorted(extra)}", file=sys.stderr)

    # 逐层完整性检查
    bad = []
    for key, d in drills.items():
        for layer in REQUIRED_LAYERS:
            if not d.get(layer):
                bad.append(f"{key} 缺 {layer}")
        prob = d.get("problem") or {}
        for field in ("statement", "approach", "solution", "keyPoints",
                      "pitfalls", "variants", "comparison", "interviewScript"):
            if field not in prob:
                bad.append(f"{key} problem 缺 {field}")
        if len(prob.get("pitfalls") or []) < 5:
            bad.append(f"{key} pitfalls < 5")
        if len(prob.get("keyPoints") or []) < 5:
            bad.append(f"{key} keyPoints < 5")
        if not (prob.get("variants")):
            bad.append(f"{key} 无 variants（模型赛道要求有对比实现）")
        if not (prob.get("comparison")):
            bad.append(f"{key} 无 comparison（模型赛道要求有对比表）")
    if bad:
        for b in bad:
            print("[fatal] " + b, file=sys.stderr)
        return 1

    # 全部代码 exec + assert 验证（写进库里的就是跑过的那段）
    run_all(drills)

    doc = {
        "generatedAt": datetime.now(CST).isoformat(timespec="seconds"),
        "source": "_gen_model_drills.py（作者工具；全部实现 exec+assert 验证后入库）",
        "drills": drills,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(drills)} drills)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
