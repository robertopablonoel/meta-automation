"""PULL stage: read-only Graph API pulls, cached to weekly_review/data/<week>/.

Artifacts:
  raw_campaigns.json  — all campaigns (live ones discovered at runtime, never hardcoded)
  raw_insights.json   — ad-level insights, review window (Fri-Thu), spend>0
  raw_ads.json        — ad metadata + creative{...} for ads seen in insights
  raw_adsets.json     — ad-set metadata for ad sets seen in insights
  raw_lifetime.json   — lifetime (date_preset=maximum) ad-level insights; tolerant+resumable

Cache semantics: existing complete artifacts are skipped unless --force.
"""

from __future__ import annotations

import json
import os

from .common import load_json, save_json, week_dir, week_window
from .meta_client import MetaClient


def _strip_paging(rows: list[dict]) -> list[dict]:
    for r in rows:
        r.pop("paging", None)
    return rows


def run(cfg: dict, client: MetaClient, week: str, force: bool = False) -> None:
    since, until = week_window(week)
    d = week_dir(cfg, week)
    pull_cfg = cfg["pull"]
    print(f"[pull] week {week} window {since}..{until} account {client.account_id}")

    # 1) Discover campaigns (live account is the template; never hardcode).
    campaigns_path = os.path.join(d, "raw_campaigns.json")
    if force or not os.path.exists(campaigns_path):
        campaigns = client.get_all(
            f"{client.account_id}/campaigns",
            {"fields": "id,name,status,effective_status,objective,daily_budget,created_time",
             "limit": 200})
        campaigns.sort(key=lambda c: c["id"])
        save_json(campaigns_path, campaigns)
    else:
        campaigns = load_json(campaigns_path)
    active = [c for c in campaigns if c.get("status") == "ACTIVE"]
    print(f"[pull] campaigns: {len(campaigns)} total, {len(active)} ACTIVE:")
    for c in active:
        print(f"    {c['id']}  {c.get('name')}")

    # 2) Ad-level insights for the review window (account-level so any ad that
    #    spent inside the window is captured; campaign labels ride along).
    insights_path = os.path.join(d, "raw_insights.json")
    if force or not os.path.exists(insights_path):
        rows = client.get_all(
            f"{client.account_id}/insights",
            {"level": "ad",
             "fields": ",".join(pull_cfg["insights_fields"]),
             "time_range": json.dumps({"since": since, "until": until}),
             "action_attribution_windows": json.dumps(cfg["attribution_windows"]),
             "filtering": json.dumps(
                 [{"field": "spend", "operator": "GREATER_THAN", "value": 0}]),
             "limit": pull_cfg["insights_limit"]})
        rows = _strip_paging(rows)
        rows.sort(key=lambda r: r["ad_id"])
        save_json(insights_path, rows)
    else:
        rows = load_json(insights_path)
    print(f"[pull] insights rows (ads with spend in window): {len(rows)}")

    ad_ids = sorted({r["ad_id"] for r in rows})
    adset_ids = sorted({r["adset_id"] for r in rows if r.get("adset_id")})

    # 3) Ad metadata (batched ?ids= reads, only for ads seen in insights).
    ads_path = os.path.join(d, "raw_ads.json")
    if force or not os.path.exists(ads_path):
        ads = client.get_by_ids(ad_ids, pull_cfg["ad_fields"],
                                chunk=pull_cfg["batch_ids_chunk"])
        save_json(ads_path, ads)
    else:
        ads = load_json(ads_path)
    print(f"[pull] ad metadata: {len(ads)}/{len(ad_ids)}")

    # 4) Ad-set metadata.
    adsets_path = os.path.join(d, "raw_adsets.json")
    if force or not os.path.exists(adsets_path):
        adsets = client.get_by_ids(adset_ids, pull_cfg["adset_fields"],
                                   chunk=pull_cfg["batch_ids_chunk"])
        save_json(adsets_path, adsets)
    else:
        adsets = load_json(adsets_path)
    print(f"[pull] ad-set metadata: {len(adsets)}/{len(adset_ids)}")

    # 5) Lifetime insights (date_preset=maximum), one paginated account-level
    #    pull instead of ~530 per-ad calls. Tolerant + resumable: partial pages
    #    are cached with the paging cursor and resumed on the next run.
    lt_path = os.path.join(d, "raw_lifetime.json")
    state = {"complete": False, "after": None, "rows": []}
    if os.path.exists(lt_path) and not force:
        state = load_json(lt_path)
    if state.get("complete"):
        print(f"[pull] lifetime insights: cached complete ({len(state['rows'])} rows)")
    else:
        def hook(page_rows, after):
            state["rows"].extend(_strip_paging(page_rows))
            state["after"] = after
            state["complete"] = after is None
            save_json(lt_path, state)

        try:
            client.get_all(
                f"{client.account_id}/insights",
                {"level": "ad",
                 "fields": ",".join(pull_cfg["lifetime_fields"]),
                 "date_preset": "maximum",
                 "action_attribution_windows": json.dumps(cfg["attribution_windows"]),
                 "filtering": json.dumps(
                     [{"field": "spend", "operator": "GREATER_THAN", "value": 0}]),
                 "limit": pull_cfg["insights_limit"]},
                page_hook=hook,
                start_after=state.get("after"))
            # de-dupe (resume can overlap a page), keep last occurrence
            dedup = {}
            for r in state["rows"]:
                dedup[r["ad_id"]] = r
            state["rows"] = sorted(dedup.values(), key=lambda r: r["ad_id"])
            state["complete"] = True
            save_json(lt_path, state)
            print(f"[pull] lifetime insights: complete ({len(state['rows'])} rows)")
        except RuntimeError as e:
            from .common import redact
            print(f"[pull] lifetime insights: PARTIAL ({len(state['rows'])} rows) — "
                  f"{redact(e)}; will resume next run. Continuing.")
    print("[pull] done")
