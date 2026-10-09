#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
seed_formulas.py — build web/data/formulas.json from the front-end's built-in
formula library (web/assets/js/views2.part.js, `const FORMULA_SEED = [...]`).

Why read the JS instead of duplicating the content here: the six worked
formulas (attention, DPO, GRPO, DDPM, RoPE, CLIP) are the front-end's fallback
when the data layer has no formulas yet. Seeding the data layer FROM that array
keeps a single source of truth, so the two can never drift.

After seeding, the daily agent layer appends new formulas to the same file
(deduped by id), and the front-end merges both.

Usage: python scripts/seed_formulas.py [--force]
"""
from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "web" / "assets" / "js" / "views2.part.js"
OUT = ROOT / "web" / "data" / "formulas.json"
CST = timezone(timedelta(hours=8))

# Hand-written LaTeX for the built-in library.
#
# Why this exists: the front-end seed carries a hand-formatted HTML variant per
# formula, which is verbose and unusable anywhere else. Pairing each with LaTeX
# means ONE renderer (tex() in core.part.js) produces the display, so a formula on
# a knowledge card and the same formula on the 公式剖析 page finally look the same.
LATEX = {
    "f-attention": r"\mathrm{Attention}(Q,K,V) = \mathrm{softmax}\left(\frac{QK^\top}{\sqrt{d_k}}\right)V",
    "f-dpo": (r"\mathcal{L}_{\mathrm{DPO}} = -\mathbb{E}_{(x, y_w, y_l)}"
              r"\left[\log \sigma\left(\beta \log \frac{\pi_\theta(y_w \mid x)}{\pi_{\mathrm{ref}}(y_w \mid x)}"
              r" - \beta \log \frac{\pi_\theta(y_l \mid x)}{\pi_{\mathrm{ref}}(y_l \mid x)}\right)\right]"),
    "f-grpo": (r"A_i = \frac{r_i - \mathrm{mean}(r_1, \ldots, r_G)}{\mathrm{std}(r_1, \ldots, r_G)}"
               r"\qquad \mathcal{J} = \mathbb{E}\left[\frac{1}{G}\sum_{i=1}^{G}"
               r"\min\left(\rho_i A_i,\ \mathrm{clip}(\rho_i, 1-\epsilon, 1+\epsilon) A_i\right)\right]"),
    "f-ddpm": (r"\mathcal{L}_{\mathrm{simple}} = \mathbb{E}_{t, x_0, \epsilon}"
               r"\left[\left\| \epsilon - \epsilon_\theta\left(\sqrt{\bar{\alpha}_t}\, x_0"
               r" + \sqrt{1-\bar{\alpha}_t}\, \epsilon,\ t\right) \right\|^2\right]"),
    "f-rope": (r"f(x, m) = R_{\Theta, m} x \quad \Longrightarrow \quad "
               r"\langle f(q, m), f(k, n) \rangle = g(q, k, m - n)"),
    "f-clip": (r"\mathcal{L} = -\frac{1}{2N}\left[\sum_{i=1}^{N} \log "
               r"\frac{\exp(s_{ii}/\tau)}{\sum_{j=1}^{N} \exp(s_{ij}/\tau)}"
               r" + \sum_{i=1}^{N} \log \frac{\exp(s_{ii}/\tau)}{\sum_{j=1}^{N} \exp(s_{ji}/\tau)}\right]"),
}


def extract_array_text(src: str) -> str:
    """Return the literal text of `const FORMULA_SEED = [ ... ];`."""
    start = src.index("const FORMULA_SEED")
    bracket = src.index("[", start)
    # Match brackets while skipping strings and template literals.
    depth = 0
    i = bracket
    state = "code"
    while i < len(src):
        c = src[i]
        if state == "code":
            if c == "/" and src[i + 1:i + 2] == "/":
                while i < len(src) and src[i] != "\n":
                    i += 1
                continue
            if c == "/" and src[i + 1:i + 2] == "*":
                i += 2
                while i < len(src) and not (src[i] == "*" and src[i + 1:i + 2] == "/"):
                    i += 1
                i += 2
                continue
            if c in "\"'":
                q = c
                i += 1
                while i < len(src) and src[i] != q:
                    i += 2 if src[i] == "\\" else 1
                i += 1
                continue
            if c == "`":
                state = "template"
                i += 1
                continue
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    return src[bracket:i + 1]
            i += 1
            continue
        if state == "template":
            if c == "\\":
                i += 2
                continue
            if c == "`":
                state = "code"
                i += 1
                continue
            if c == "$" and src[i + 1:i + 2] == "{":
                d = 1
                i += 2
                while i < len(src) and d > 0:
                    ch = src[i]
                    if ch == "\\":
                        i += 2
                        continue
                    if ch == "`":
                        i += 1
                        while i < len(src) and src[i] != "`":
                            i += 2 if src[i] == "\\" else 1
                        i += 1
                        continue
                    if ch == "{":
                        d += 1
                    elif ch == "}":
                        d -= 1
                    i += 1
                continue
            i += 1
            continue
        i += 1
    raise ValueError("FORMULA_SEED array never closed")


def jsonify_js_array(text: str) -> str:
    """Convert a JS array literal into JSON.

    Handles the three constructs actually used in FORMULA_SEED: single-quoted
    strings, backtick template literals (no ${} inside), and unquoted keys.
    """
    # 1. Backtick template literals -> JSON strings (escape newlines/quotes).
    def bt(m):
        body = m.group(1)
        body = body.replace("\\", "\\\\").replace('"', '\\"')
        body = body.replace("\n", "\\n").replace("\r", "")
        return '"' + body + '"'

    text = re.sub(r"`([^`]*)`", bt, text, flags=re.S)

    # 2. Single-quoted strings -> double-quoted.
    def sq(m):
        body = m.group(1)
        body = body.replace("\\'", "'").replace('"', '\\"')
        return '"' + body + '"'

    text = re.sub(r"'((?:[^'\\]|\\.)*)'", sq, text, flags=re.S)

    # 3. Quote bare object keys: `key:` -> `"key":` at the start of a property.
    text = re.sub(r"([{,]\s*)([A-Za-z_$][\w$]*)(\s*:)", r'\1"\2"\3', text)

    # 4. Remove trailing commas before } or ].
    text = re.sub(r",(\s*[}\]])", r"\1", text)

    return text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="seed_formulas.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true",
                    help="overwrite existing formulas instead of merging")
    args = ap.parse_args(argv)

    if not SRC.exists():
        print(f"source not found: {SRC}", file=sys.stderr)
        return 1

    src = SRC.read_text("utf-8")
    try:
        arr_text = extract_array_text(src)
    except ValueError as e:
        print(f"extract failed: {e}", file=sys.stderr)
        return 1

    as_json = jsonify_js_array(arr_text)
    try:
        formulas = json.loads(as_json)
    except json.JSONDecodeError as e:
        print(f"converted text is not valid JSON: {e}", file=sys.stderr)
        print(as_json[:400], file=sys.stderr)
        return 1

    print(f"extracted {len(formulas)} formulas: {', '.join(f.get('id', '?') for f in formulas)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if OUT.exists():
        # ALWAYS merge, even with --force.
        #
        # Learning this the hard way: --force used to skip this read and the file
        # was rewritten with only the six built-in formulas, silently deleting the
        # agent-generated ones. --force now means "the built-in set wins on id
        # collisions", not "discard everything else".
        try:
            payload = json.loads(OUT.read_text("utf-8"))
            for f in (payload.get("formulas") or []):
                if isinstance(f, dict) and f.get("id"):
                    existing[f["id"]] = f
        except Exception:
            existing = {}

    merged = dict(existing)
    added = 0
    for f in formulas:
        fid = f.get("id")
        if not fid:
            continue
        # Overlay the LaTeX so one renderer drives every surface, and drop the
        # hand-formatted HTML so there is a single source of truth.
        if fid in LATEX:
            f["latex"] = LATEX[fid]
            f.pop("html", None)
        if fid not in merged:
            added += 1
        merged[fid] = f           # the front-end seed is authoritative for these ids

    out = {
        "generatedAt": datetime.now(CST).isoformat(timespec="seconds"),
        "source": "seed_formulas.py (front-end built-in library)",
        "count": len(merged),
        "formulas": list(merged.values()),
    }
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)

    print(f"wrote {OUT} ({OUT.stat().st_size} bytes): {len(existing)} existing + {added} new = {len(merged)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
