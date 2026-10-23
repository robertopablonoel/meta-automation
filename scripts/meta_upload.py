"""
Upload ads to Meta from a dashboard-exported config file.

Usage:
    python -m scripts.meta_upload
    python -m scripts.meta_upload --config output/meta_upload_config.json
    python -m scripts.meta_upload --dry-run
    python -m scripts.meta_upload --limit 1

Schema confirmed from live API testing 2026-05-05.

Config may carry an optional "adset_id" (numeric string): ads are then created
inside that EXISTING ad set (verified up front; create_ad_set is skipped, and
no campaign is created either — the ad set's own campaign is adopted). Omitted
→ the classic path: a NEW ad set named ad_set_name. Ads land PAUSED on both
paths, unconditionally.
"""

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
RENAMED_VIDEOS_DIR = OUTPUT_DIR / "renamed_videos"
DEFAULT_CONFIG = OUTPUT_DIR / "meta_upload_config.json"

PIXEL_ID = "2641325006045972"
URL_TAGS = (
    "utm_source=facebook&utm_medium=paid"
    "&utm_campaign={{campaign.name}}"
    "&utm_term={{adset.name}}"
    "&utm_content={{ad.name}}"
    "&fbadid={{ad.id}}"
)
DEGREES_OF_FREEDOM = {
    "creative_features_spec": {
        "advantage_plus_creative": {"enroll_status": "OPT_IN"},
        "standard_enhancements": {"enroll_status": "OPT_IN"},
    }
}


def init_api():
    import os
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")

    from facebook_business.api import FacebookAdsApi
    app_id = os.getenv("META_APP_ID", "")
    app_secret = os.getenv("META_APP_SECRET", "")
    token = os.getenv("META_ACCESS_TOKEN", "")
    if not token:
        logger.error("META_ACCESS_TOKEN not set in .env")
        sys.exit(1)
    FacebookAdsApi.init(app_id=app_id or None, app_secret=app_secret or None, access_token=token, api_version='v21.0')
    return os.getenv("META_AD_ACCOUNT_ID", ""), os.getenv("META_PAGE_ID", ""), \
           os.getenv("META_INSTAGRAM_ACTOR_ID", ""), os.getenv("LANDING_PAGE_URL", "")


def upload_video(account, video_path: Path, dry_run: bool) -> str:
    if dry_run:
        return f"DRY_RUN_VIDEO_ID[{video_path.name}]"
    from facebook_business.adobjects.advideo import AdVideo
    logger.info(f"  Uploading video: {video_path.name}")
    video = account.create_ad_video(params={"filename": str(video_path)})
    video_id = video["id"]
    # Poll until ready
    for attempt in range(30):
        time.sleep(10)
        v = AdVideo(video_id).api_get(fields=["status"])
        data = v.export_all_data()
        video_status = data.get("status", {}).get("video_status", "")
        logger.info(f"    [{attempt+1}] {video_status}")
        if video_status == "ready":
            break
    else:
        raise RuntimeError(f"Video {video_path.name} did not reach ready state")
    return video_id


def get_preferred_thumbnail(video_id: str, account_id: str, dry_run: bool) -> dict:
    """Download Meta's preferred thumbnail, upload as AdImage, return hash + stable URL."""
    if dry_run:
        return {"hash": f"DRY_RUN_HASH[{video_id}]", "url": f"DRY_RUN_URL[{video_id}]"}
    import tempfile, requests as req
    from facebook_business.adobjects.advideo import AdVideo
    from facebook_business.adobjects.adimage import AdImage
    v = AdVideo(video_id).api_get(fields=["thumbnails"])
    data = v.export_all_data()
    thumbs = data.get("thumbnails", {}).get("data", [])
    preferred = next((t for t in thumbs if t.get("is_preferred")), thumbs[0] if thumbs else {})
    uri = preferred.get("uri", "")
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(req.get(uri, timeout=30).content)
        tmp_path = f.name
    from facebook_business.adobjects.adaccount import AdAccount
    image = AdImage(parent_id=f"act_{account_id}")
    image[AdImage.Field.filename] = tmp_path
    image.remote_create()
    img_hash = image[AdImage.Field.hash]
    images = AdAccount(f"act_{account_id}").get_ad_images(
        fields=["hash", "url"], params={"hashes": [img_hash]}
    )
    img_url = images[0]["url"] if images else ""
    return {"hash": img_hash, "url": img_url}


def create_campaign(account, name: str, daily_budget: int, dry_run: bool) -> str:
    if dry_run:
        logger.info(f"[DRY RUN] Would create campaign: {name} (${daily_budget/100:.0f}/day)")
        return "DRY_RUN_CAMPAIGN_ID"
    from facebook_business.adobjects.campaign import Campaign
    c = account.create_campaign(params={
        Campaign.Field.name: name,
        Campaign.Field.objective: Campaign.Objective.outcome_sales,
        Campaign.Field.status: Campaign.Status.paused,
        Campaign.Field.bid_strategy: Campaign.BidStrategy.lowest_cost_without_cap,
        Campaign.Field.daily_budget: daily_budget,
        Campaign.Field.special_ad_categories: [],
        Campaign.Field.buying_type: "AUCTION",
    })
    return c["id"]


def resolve_existing_ad_set(adset_id: str, campaign_id_override) -> dict:
    """Read the target ad set (SDK read only — safe in dry-run) and hard-fail
    BEFORE any media upload if it doesn't exist or, when the config also pins a
    campaign_id, if it belongs to a different campaign."""
    from facebook_business.adobjects.adset import AdSet
    try:
        data = AdSet(adset_id).api_get(
            fields=["id", "name", "status", "effective_status", "campaign_id"]
        ).export_all_data()
    except Exception as e:
        logger.error(f"adset_id {adset_id} could not be read (does it exist?): {e}")
        sys.exit(1)
    if campaign_id_override and str(data.get("campaign_id")) != str(campaign_id_override):
        logger.error(
            f"adset_id {adset_id} belongs to campaign {data.get('campaign_id')}, "
            f"not the config's campaign_id {campaign_id_override} — aborting before any upload")
        sys.exit(1)
    status = data.get("effective_status") or data.get("status") or "UNKNOWN"
    if status == "ACTIVE":
        logger.warning(
            f"Target ad set {adset_id} ('{data.get('name')}') is ACTIVE — new ads "
            "still land PAUSED, but they go inside a live, delivering ad set "
            "(delivery/learning-phase implications are real).")
    return data


def create_ad_set(account, campaign_id: str, name: str, dry_run: bool) -> str:
    if dry_run:
        logger.info(f"[DRY RUN] Would create ad set: {name}")
        return "DRY_RUN_ADSET_ID"
    from facebook_business.adobjects.adset import AdSet
    adset = account.create_ad_set(params={
        AdSet.Field.name: name,
        AdSet.Field.campaign_id: campaign_id,
        AdSet.Field.status: AdSet.Status.paused,
        AdSet.Field.optimization_goal: AdSet.OptimizationGoal.offsite_conversions,
        AdSet.Field.billing_event: AdSet.BillingEvent.impressions,
        AdSet.Field.targeting: {
            "age_min": 18,
            "age_max": 65,
            "geo_locations": {
                "countries": ["US"],
                "location_types": ["home", "recent"],
            },
            "targeting_automation": {"advantage_audience": 1},
        },
        AdSet.Field.promoted_object: {"pixel_id": PIXEL_ID, "custom_event_type": "PURCHASE"},
    })
    return adset["id"]


def create_creative(account, video_id: str, thumb: dict, ad: dict,
                    page_id: str, ig_id: str, landing_url: str, dry_run: bool) -> str:
    name = ad["video_filename"].replace(".mp4", "").replace(".mov", "")
    if dry_run:
        logger.info(f"[DRY RUN] Would create creative for: {name} | hash: {thumb['hash']}")
        logger.info(f"  primary_text: {ad['primary_text'][:60]}...")
        logger.info(f"  headline: {ad['headline']}")
        logger.info(f"  description: {ad.get('description', '')}")
        return "DRY_RUN_CREATIVE_ID"
    from facebook_business.adobjects.adcreative import AdCreative
    video_data = {
        "video_id": video_id,
        "image_hash": thumb["hash"],
        "call_to_action": {
            "type": "SHOP_NOW",
            "value": {"link": landing_url, "link_caption": "spicycubes.com"},
        },
        "message": ad["primary_text"],
        "title": ad["headline"],
        "link_description": ad.get("description", ""),
    }
    spec = {"page_id": page_id, "video_data": video_data}
    if ig_id:
        spec["instagram_user_id"] = ig_id
    creative = account.create_ad_creative(params={
        AdCreative.Field.name: f"Creative - {name}",
        AdCreative.Field.object_story_spec: spec,
        AdCreative.Field.url_tags: URL_TAGS,
    })
    return creative["id"]


def create_ad(account, adset_id: str, creative_id: str, name: str, dry_run: bool) -> str:
    if dry_run:
        logger.info(f"[DRY RUN] Would create ad: {name}")
        return "DRY_RUN_AD_ID"
    from facebook_business.adobjects.ad import Ad
    ad = account.create_ad(params={
        Ad.Field.name: name,
        Ad.Field.adset_id: adset_id,
        Ad.Field.status: Ad.Status.paused,
        Ad.Field.creative: {"creative_id": creative_id},
    })
    return ad["id"]


def main():
    parser = argparse.ArgumentParser(description="Upload ads to Meta from dashboard config")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to meta_upload_config.json")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen without calling API")
    parser.add_argument("--limit", type=int, default=0, help="Max ads to create (0 = all)")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        logger.error(f"Config not found: {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    campaign_name = config.get("campaign_name", "Spicy Cubes Hot Peach - Auto Generated")
    campaign_id_override = config.get("campaign_id")
    ad_set_name = config.get("ad_set_name", "Batch #1")
    daily_budget = config.get("daily_budget", 20000)
    ads = config.get("ads", [])

    # Optional: target an EXISTING ad set. Omitted → today's create-new path,
    # byte-identical. Present → skip create_ad_set and create ads inside it.
    adset_id_override = config.get("adset_id")
    if adset_id_override is not None and not str(adset_id_override).isdigit():
        logger.error(f"config adset_id must be a numeric string, got: {adset_id_override!r}")
        sys.exit(1)

    if not ads:
        logger.error("No ads in config file")
        sys.exit(1)

    if args.limit:
        ads = ads[: args.limit]

    logger.info(f"Config: {len(ads)} ads | campaign: {campaign_name} | ad set: {ad_set_name}")
    if args.dry_run:
        logger.info("--- DRY RUN MODE ---")

    ad_account_id, page_id, ig_id, landing_url = init_api()
    ad_account_id = ad_account_id if ad_account_id.startswith("act_") else f"act_{ad_account_id}"

    from facebook_business.adobjects.adaccount import AdAccount
    account = AdAccount(ad_account_id)

    # Existing-ad-set mode: verify the target up front (SDK read) so a bad id
    # hard-fails before any campaign create or media upload — dry-run included.
    existing_ad_set = None
    if adset_id_override:
        existing_ad_set = resolve_existing_ad_set(str(adset_id_override), campaign_id_override)

    # Use existing campaign if campaign_id provided, otherwise create new.
    # When targeting an existing ad set, never create a campaign either — the
    # ad set already lives in one; adopt its campaign for the log/summary.
    if adset_id_override:
        campaign_id = campaign_id_override or existing_ad_set.get("campaign_id")
        logger.info(f"Using campaign of existing ad set: {campaign_id}")
    elif campaign_id_override:
        campaign_id = campaign_id_override
        logger.info(f"Using existing campaign: {campaign_name} (id: {campaign_id})")
    else:
        logger.info(f"Creating campaign: {campaign_name}")
        campaign_id = create_campaign(account, campaign_name, daily_budget, args.dry_run)
        logger.info(f"  campaign_id: {campaign_id}")

    summary = {"campaign_id": campaign_id, "ad_sets": [], "total_ads": 0, "errors": []}

    # Single ad set for all ads: the config's existing one, or a new one
    if adset_id_override:
        adset_id = str(adset_id_override)
        adset_display_name = existing_ad_set.get("name") or ad_set_name
        adset_status = existing_ad_set.get("effective_status") or existing_ad_set.get("status") or "UNKNOWN"
        logger.info(f"\nAd set: existing ad set {adset_id} ('{adset_display_name}', {adset_status}) "
                    f"({len(ads)} ads)")
        if args.dry_run:
            logger.info(f"[DRY RUN] Target: existing ad set {adset_id} "
                        f"('{adset_display_name}', {adset_status})")
    else:
        adset_display_name = ad_set_name
        logger.info(f"\nAd set: {ad_set_name} ({len(ads)} ads)")
        if args.dry_run:
            logger.info(f"[DRY RUN] Target: would create NEW ad set '{ad_set_name}'")
        adset_id = create_ad_set(account, campaign_id, ad_set_name, args.dry_run)
        logger.info(f"  adset_id: {adset_id}")

    adset_summary = {"name": adset_display_name, "adset_id": adset_id, "ads": []}

    # Derive label from the ad set's name: "Ad Set #13 - UGC - Broad - …" -> "UGC"
    # (the real container's name in existing-ad-set mode; the config's otherwise)
    ad_set_label = adset_display_name.split(" - ")[1] if " - " in adset_display_name else "UGC"

    for ad in ads:
        filename = ad["video_filename"]
        video_path = RENAMED_VIDEOS_DIR / filename

        if not video_path.exists() and not args.dry_run:
            logger.warning(f"  Video not found, skipping: {video_path}")
            summary["errors"].append(f"File not found: {filename}")
            continue

        try:
            video_id = upload_video(account, video_path, args.dry_run)
            logger.info(f"  video_id: {video_id}")

            thumb = get_preferred_thumbnail(video_id, ad_account_id.replace("act_", ""), args.dry_run)
            logger.info(f"  thumb_hash: {thumb['hash']} url: {thumb['url'][:60]}...")

            creative_id = create_creative(
                account, video_id, thumb, ad, page_id, ig_id, landing_url, args.dry_run
            )
            logger.info(f"  creative_id: {creative_id}")

            # Ad name: {Label}//{concept}//{hook_from_filename}//PDP
            concept = ad["creative_concept"]
            hook = filename.replace(".mp4", "").replace(".mov", "").split("-", 1)[-1]
            ad_name = f"{ad_set_label}//{concept}//{hook}//PDP"
            ad_id = create_ad(account, adset_id, creative_id, ad_name, args.dry_run)
            logger.info(f"  ad_id: {ad_id} | name: {ad_name}")

            adset_summary["ads"].append({"filename": filename, "ad_id": ad_id})
            summary["total_ads"] += 1

        except Exception as e:
            logger.error(f"  Failed for {filename}: {e}")
            summary["errors"].append(f"{filename}: {e}")

    summary["ad_sets"].append(adset_summary)

    # Save log
    log_path = OUTPUT_DIR / f"upload_log_{int(time.time())}.json"
    if not args.dry_run:
        with open(log_path, "w") as f:
            json.dump(summary, f, indent=2)
        logger.info(f"\nLog saved: {log_path}")

    logger.info(f"\n=== DONE: {summary['total_ads']} ads created, {len(summary['errors'])} errors ===")
    if summary["errors"]:
        for e in summary["errors"]:
            logger.error(f"  {e}")


if __name__ == "__main__":
    main()
