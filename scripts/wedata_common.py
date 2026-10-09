"""Shared helpers for the web/data static-layer builders.

Every builder writes UTF-8 *without BOM* and with LF newlines, so that
``json.load(open(p, encoding='utf-8'))`` always succeeds and no Windows
PowerShell BOM ever leaks into a data file.
"""

from __future__ import annotations

import io
import json
import os
import sys
from datetime import datetime, timedelta, timezone

# Asia/Shanghai has no DST, so a fixed +08:00 offset is exact.
CST = timezone(timedelta(hours=8))

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "web", "data")
RESEARCH = os.path.join(ROOT, "research")
SCRIPTS = HERE

DATA_SUBDIRS = ["", "logs", "digest", "items", "state"]

SEED_COLLECTOR_VERSION = "0.0.0-seed"


def now_iso() -> str:
    """ISO-8601 local (Asia/Shanghai) timestamp, second precision."""
    return datetime.now(CST).isoformat(timespec="seconds")


def load_json(path: str, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: str, obj) -> int:
    """Write UTF-8 / no BOM / LF, 2-space indent. Returns byte size."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return os.path.getsize(path)


def ensure_dirs() -> None:
    for sub in DATA_SUBDIRS:
        os.makedirs(os.path.join(DATA, sub), exist_ok=True)


def utf8_stdout() -> None:
    """Make Chinese output survive a legacy cp936 console."""
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover - already wrapped / no buffer
        pass


def pick(*vals):
    """Mirror of core.js `pick()`: first defined, non-null, non-empty value."""
    for v in vals:
        if v is not None and v != "":
            return v
    return None


def arr(v):
    """Mirror of core.js `arr()`: always a list."""
    if isinstance(v, list):
        return v
    if v is None or v == "":
        return []
    return [v]


def import_collect():
    """Import the sibling `collect.py` so the static layer reuses the collector's
    own taxonomy / channel / scoring definitions instead of inventing copies."""
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    import collect  # noqa: E402  (stdlib-only module with a __main__ guard)
    return collect
