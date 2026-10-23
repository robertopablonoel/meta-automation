"""Shared helpers: config, env, week-window math, IO, redaction, percentiles."""

from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta

REPO_ROOT = "/Users/colefreeman/Desktop/meta-automation"
PKG_DIR = os.path.join(REPO_ROOT, "weekly_review")
CONFIG_PATH = os.path.join(PKG_DIR, "config.json")

_TOKEN_RE = re.compile(r"EAA[0-9A-Za-z]+")


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_env(cfg: dict) -> None:
    """Load dotenv ONLY with explicit absolute paths (bare load_dotenv()
    crashes under stdin/module execution — find_dotenv assertion)."""
    from dotenv import load_dotenv

    for p in cfg["dotenv_paths"]:
        if os.path.exists(p):
            load_dotenv(p)


def redact(text: str) -> str:
    """Strip any Meta access token (EAA...) from a string before print/log."""
    return _TOKEN_RE.sub("EAA...[REDACTED]", str(text))


def week_window(week: str) -> tuple[str, str]:
    """Fri-Thu review window for an ISO week label 'YYYY-Www'.

    Convention: window ENDS on the Thursday of the given ISO week
    (Mon+3) and starts the previous Friday (Thu-6).
    2026-W31 -> since=2026-07-24 (Fri), until=2026-07-30 (Thu).
    """
    m = re.fullmatch(r"(\d{4})-W(\d{2})", week)
    if not m:
        raise ValueError(f"Bad week label {week!r}; expected YYYY-Www")
    year, wk = int(m.group(1)), int(m.group(2))
    monday = date.fromisocalendar(year, wk, 1)
    thursday = monday + timedelta(days=3)
    friday = thursday - timedelta(days=6)
    return friday.isoformat(), thursday.isoformat()


def prev_week_label(week: str) -> str:
    m = re.fullmatch(r"(\d{4})-W(\d{2})", week)
    monday = date.fromisocalendar(int(m.group(1)), int(m.group(2)), 1)
    prev_monday = monday - timedelta(days=7)
    y, w, _ = prev_monday.isocalendar()
    return f"{y}-W{w:02d}"


def week_dir(cfg: dict, week: str) -> str:
    d = os.path.join(REPO_ROOT, cfg["data_dir"], week)
    os.makedirs(d, exist_ok=True)
    return d


def save_json(path: str, obj) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def load_json(path: str):
    with open(path) as f:
        return json.load(f)


def percentile(values: list[float], p: float) -> float | None:
    """Deterministic linear-interpolation percentile (numpy 'linear' method).

    p in [0, 100]. Returns None on empty input.
    """
    if not values:
        return None
    vals = sorted(values)
    if len(vals) == 1:
        return float(vals[0])
    k = (len(vals) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(vals) - 1)
    frac = k - lo
    return float(vals[lo] + (vals[hi] - vals[lo]) * frac)


def r6(x) -> float | None:
    """Round to 6 decimals for stable output."""
    if x is None:
        return None
    return round(float(x), 6)


def action_value(items, action_type: str) -> float:
    """Pull the default 'value' for an action_type from an actions-style list.

    With action_attribution_windows=['7d_click','1d_view'] the default
    'value' field is 7d_click + 1d_view (account convention).
    """
    for it in items or []:
        if it.get("action_type") == action_type:
            try:
                return float(it.get("value", 0) or 0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def first_action_value(items, action_types: list[str]) -> float:
    """First present action_type wins (e.g. omni_ variant, then legacy)."""
    present = {it.get("action_type") for it in (items or [])}
    for at in action_types:
        if at in present:
            return action_value(items, at)
    return 0.0
