#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Seed the placeholder data files so the workbench renders before the first
collector run.

Writes:
  web/data/manifest.json    status="seed", no run yet, target window from collect.py
  web/data/logs/runs.json   []   (an empty run history)
  web/data/formulas.json    formulas: []  -> the front-end falls back to FORMULA_SEED

`targetDate` / `targetLabel` are read from scripts/collect.py's DEFAULT_CONFIG so
the seed can never disagree with the collector about the application window.

Usage:
    python scripts/build_seed_placeholders.py
"""

from __future__ import annotations

import os
import sys
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wedata_common import (  # noqa: E402
    DATA,
    SEED_COLLECTOR_VERSION,
    ensure_dirs,
    import_collect,
    now_iso,
    utf8_stdout,
    write_json,
)

MANIFEST_DST = os.path.join(DATA, "manifest.json")
RUNS_DST = os.path.join(DATA, "logs", "runs.json")
FORMULAS_DST = os.path.join(DATA, "formulas.json")


def main():
    utf8_stdout()
    ensure_dirs()
    collect = import_collect()
    cfg = collect.DEFAULT_CONFIG
    generated_at = now_iso()

    manifest = OrderedDict(
        [
            ("generatedAt", generated_at),
            ("lastRunAt", None),
            ("date", None),
            ("collectorVersion", SEED_COLLECTOR_VERSION),
            ("channelsOk", 0),
            ("channelsTotal", 0),
            ("newItems", 0),
            ("totalItems", 0),
            ("durationSec", 0),
            ("targetDate", cfg.get("targetDate")),
            ("targetLabel", cfg.get("targetLabel")),
            ("status", "seed"),
            ("itemsFile", None),
            (
                "stats",
                OrderedDict(
                    [
                        ("byCategory", {}),
                        ("byChannel", {}),
                        ("zhShare", 0),
                    ]
                ),
            ),
        ]
    )

    formulas = OrderedDict(
        [
            ("generatedAt", generated_at),
            ("source", "seed"),
            ("formulas", []),
        ]
    )

    m_size = write_json(MANIFEST_DST, manifest)
    r_size = write_json(RUNS_DST, [])
    f_size = write_json(FORMULAS_DST, formulas)

    print("[ok] wrote %s (%d bytes)" % (MANIFEST_DST, m_size))
    print("[ok] wrote %s (%d bytes)" % (RUNS_DST, r_size))
    print("[ok] wrote %s (%d bytes)" % (FORMULAS_DST, f_size))
    print("     targetDate=%s targetLabel=%s" % (manifest["targetDate"], manifest["targetLabel"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
