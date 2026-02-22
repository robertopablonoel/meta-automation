#!/usr/bin/env python3
"""
Sync Meta Ads metrics to Supabase metrics_cache table.

Fetches campaign, adset, and ad-level insights from Meta's Graph API
and upserts them to Supabase. Dashboard reads from Supabase instead
of hitting Meta directly (faster, no rate limits).

Usage:
    venv/bin/python scripts/metrics_sync.py                          # Sync all active campaigns
    venv/bin/python scripts/metrics_sync.py --campaign-id 12345      # Sync specific campaign
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Meta API config
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_AD_ACCOUNT_ID = os.getenv("META_AD_ACCOUNT_ID", "")
if META_AD_ACCOUNT_ID and not META_AD_ACCOUNT_ID.startswith("act_"):
    META_AD_ACCOUNT_ID = f"act_{META_AD_ACCOUNT_ID}"

BASE_URL = "https://graph.facebook.com/v21.0"

# Must match dashboard/lib/meta-fields.ts exactly
INSIGHTS_FIELDS = ",".join([
    "impressions", "clicks", "spend", "cpc", "cpm", "ctr",
    "reach", "frequency", "actions", "action_values",
    "cost_per_action_type", "video_avg_time_watched_actions",
    "video_p50_watched_actions", "video_p75_watched_actions",
])
ADSET_FIELDS = "name,status,campaign_id"
AD_FIELDS = "name,status,adset_id,creative{id}"

# Rate limiting
BATCH_SLEEP_SECONDS = 2
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 5  # seconds


def meta_fetch(url: str) -> dict:
    """Fetch from Meta Graph API with retry on rate limit."""
    for attempt in range(MAX_RETRIES):
        resp = requests.get(url, timeout=30)
        if resp.status_code == 429:
            wait = RETRY_BACKOFF_BASE * (2 ** attempt)
            logger.warning(f"Rate limited (429), waiting {wait}s (attempt {attempt + 1}/{MAX_RETRIES})")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"Failed after {MAX_RETRIES} retries: {url[:100]}...")


def meta_fetch_all(url: str) -> list[dict]:
    """Paginate through all results from a Meta list endpoint."""
    results = []
    while url:
        data = meta_fetch(url)
        results.extend(data.get("data", []))
        url = data.get("paging", {}).get("next")
    return results


def list_campaigns() -> list[dict]:
    url = f"{BASE_URL}/{META_AD_ACCOUNT_ID}/campaigns?fields=name,status,created_time&limit=100&access_token={META_ACCESS_TOKEN}"
    return meta_fetch_all(url)


def get_campaign_insights(campaign_id: str) -> dict | None:
    url = f"{BASE_URL}/{campaign_id}/insights?fields={INSIGHTS_FIELDS}&date_preset=maximum&access_token={META_ACCESS_TOKEN}"
    data = meta_fetch(url)
    items = data.get("data", [])
    return items[0] if items else None


def get_daily_insights(entity_id: str) -> list[dict]:
    """Fetch daily breakdowns for the last 30 days."""
    url = (f"{BASE_URL}/{entity_id}/insights"
           f"?fields={INSIGHTS_FIELDS}"
           f"&time_increment=1&date_preset=last_30d"
           f"&access_token={META_ACCESS_TOKEN}")
    data = meta_fetch(url)
    return data.get("data", [])


def get_adsets(campaign_id: str) -> list[dict]:
    url = f"{BASE_URL}/{campaign_id}/adsets?fields={ADSET_FIELDS},insights.fields({INSIGHTS_FIELDS}).date_preset(maximum)&limit=100&access_token={META_ACCESS_TOKEN}"
    return meta_fetch_all(url)


def get_ads(adset_id: str) -> list[dict]:
    url = f"{BASE_URL}/{adset_id}/ads?fields={AD_FIELDS},insights.fields({INSIGHTS_FIELDS}).date_preset(maximum)&limit=200&access_token={META_ACCESS_TOKEN}"
    return meta_fetch_all(url)


def sync(campaign_ids: list[str] | None = None):
    """Sync metrics from Meta to Supabase."""
    try:
        from supabase import create_client
    except ImportError:
        logger.error("supabase not installed. Run: venv/bin/pip install supabase")
        sys.exit(1)

    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = (
        os.environ.get("SUPABASE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    )
    if not url or not key:
        logger.error("Missing SUPABASE_URL / SUPABASE_KEY in .env")
        sys.exit(1)
    if not META_ACCESS_TOKEN or not META_AD_ACCOUNT_ID:
        logger.error("Missing META_ACCESS_TOKEN / META_AD_ACCOUNT_ID in .env")
        sys.exit(1)

    sb = create_client(url, key)

    # Create sync_log entry
    log_resp = sb.table("sync_log").insert({"status": "running"}).execute()
    sync_log_id = log_resp.data[0]["id"]
    logger.info(f"Sync started (log id: {sync_log_id})")

    try:
        # Determine campaigns to sync
        if campaign_ids:
            campaigns = [{"id": cid} for cid in campaign_ids]
        else:
            all_campaigns = list_campaigns()
            campaigns = [c for c in all_campaigns if c.get("status") == "ACTIVE"]
            logger.info(f"Found {len(campaigns)} active campaigns out of {len(all_campaigns)} total")

        total_campaigns = 0
        total_adsets = 0
        total_ads = 0

        for campaign in campaigns:
            cid = campaign["id"]
            cname = campaign.get("name", cid)
            logger.info(f"Syncing campaign: {cname} ({cid})")

            # Campaign insights
            insights = get_campaign_insights(cid)
            sb.table("metrics_cache").upsert({
                "entity_type": "campaign",
                "entity_id": cid,
                "parent_id": None,
                "campaign_id": cid,
                "name": cname,
                "status": campaign.get("status"),
                "insights": insights,
                "extra_fields": None,
            }, on_conflict="entity_type,entity_id").execute()
            total_campaigns += 1

            # Daily snapshots (last 30 days)
            daily_rows = get_daily_insights(cid)
            for day in daily_rows:
                sb.table("daily_snapshots").upsert({
                    "entity_type": "campaign",
                    "entity_id": cid,
                    "campaign_id": cid,
                    "date": day["date_start"],
                    "insights": day,
                }, on_conflict="entity_type,entity_id,date").execute()
            logger.info(f"  {len(daily_rows)} daily snapshots")

            # Adsets
            adsets = get_adsets(cid)
            logger.info(f"  {len(adsets)} adsets")

            for adset in adsets:
                adset_insights = adset.get("insights", {}).get("data", [None])[0]
                sb.table("metrics_cache").upsert({
                    "entity_type": "adset",
                    "entity_id": adset["id"],
                    "parent_id": cid,
                    "campaign_id": cid,
                    "name": adset.get("name"),
                    "status": adset.get("status"),
                    "insights": adset_insights,
                    "extra_fields": None,
                }, on_conflict="entity_type,entity_id").execute()
                total_adsets += 1

            # Ads per adset (with rate limiting between batches)
            for i, adset in enumerate(adsets):
                adset_id = adset["id"]
                ads = get_ads(adset_id)
                logger.info(f"  Adset {adset.get('name', adset_id)}: {len(ads)} ads")

                for ad in ads:
                    ad_insights = ad.get("insights", {}).get("data", [None])[0]
                    sb.table("metrics_cache").upsert({
                        "entity_type": "ad",
                        "entity_id": ad["id"],
                        "parent_id": adset_id,
                        "campaign_id": cid,
                        "name": ad.get("name"),
                        "status": ad.get("status"),
                        "insights": ad_insights,
                        "extra_fields": {
                            "creative": ad.get("creative"),
                            "adset_id": adset_id,
                        },
                    }, on_conflict="entity_type,entity_id").execute()
                    total_ads += 1

                # Rate limit between adset batches (not after last one)
                if i < len(adsets) - 1:
                    time.sleep(BATCH_SLEEP_SECONDS)

        # Mark sync complete
        sb.table("sync_log").update({
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "campaigns_synced": total_campaigns,
            "adsets_synced": total_adsets,
            "ads_synced": total_ads,
        }).eq("id", sync_log_id).execute()

        logger.info(f"Sync complete: {total_campaigns} campaigns, {total_adsets} adsets, {total_ads} ads")

    except Exception as e:
        sb.table("sync_log").update({
            "status": "failed",
            "error_message": str(e),
        }).eq("id", sync_log_id).execute()
        logger.error(f"Sync failed: {e}")
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Sync Meta Ads metrics to Supabase"
    )
    parser.add_argument(
        "--campaign-id",
        type=str,
        default=None,
        help="Sync a specific campaign (default: all active campaigns)",
    )
    args = parser.parse_args()

    campaign_ids = [args.campaign_id] if args.campaign_id else None
    sync(campaign_ids)


if __name__ == "__main__":
    main()
