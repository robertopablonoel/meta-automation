"""
One-off operator uploader: PARTNERSHIP ADS from a dashboard-exported config.

Usage:
    python -m scripts.meta_upload_partnership --dry-run
    python -m scripts.meta_upload_partnership --dry-run --limit 1
    python -m scripts.meta_upload_partnership            # real run (gated by operator)

Differences from scripts/meta_upload.py (which stays untouched):
- REQUIRES config "partnership" block: {handle, instagram_user_id, branded_content}.
  Every creative gets object_story_spec.instagram_user_id = the partner's IG
  account id plus branded_content (ad_format 3) — the exact encoding read from
  the live 'diariesofspicycubes - AT' ads on 2026-07-06.
- REQUIRES config "ad_set_spec" block: full ad-set config (optimization, billing,
  attribution_spec, destination_type, promoted_object, targeting incl. custom
  audiences) replicated from the template ad set. No hardcoded broad targeting.
- STATIC IMAGE ads: media files are uploaded as AdImage and the creative uses
  link_data {image_hash, ...}. (The stock uploader is video-only.)
- Always creates a NEW campaign (config campaign_name, CBO via campaign-level
  daily_budget) and ONE new ad set. One ad set per run, by design.
- Everything lands PAUSED, unconditionally: campaign, ad set, ads.
- Dry-run makes ONLY SDK reads (custom-audience verification) — no writes.
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
RENAMED_VIDEOS_DIR = OUTPUT_DIR / "renamed_videos"
DEFAULT_CONFIG = OUTPUT_DIR / "meta_upload_config.json"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov"}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
# Cross-run video dedupe: Meta dedupes re-uploaded IMAGES by content hash but
# re-ingests VIDEOS every time. With one batch fanned out to many ad sets, the
# cache uploads each video once and reuses video_id + thumb hash everywhere.
VIDEO_CACHE_PATH = OUTPUT_DIR / "video_upload_cache.json"

# Exact parity with the Campaign-3 partnership ads (incl. Triple Whale params)
URL_TAGS = (
    "utm_source=facebook&utm_medium=paid"
    "&utm_campaign={{campaign.name}}"
    "&utm_term={{adset.name}}"
    "&utm_content={{ad.name}}"
    "&fbadid={{ad.id}}"
    "&tw_source={{site_source_name}}"
    "&tw_adid={{ad.id}}"
)


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
    FacebookAdsApi.init(app_id=app_id or None, app_secret=app_secret or None,
                        access_token=token, api_version='v21.0')
    return os.getenv("META_AD_ACCOUNT_ID", ""), os.getenv("META_PAGE_ID", ""), \
           os.getenv("LANDING_PAGE_URL", "")


def verify_custom_audiences(targeting: dict):
    """SDK reads only — hard-fail before any write if an audience is unreadable."""
    from facebook_business.adobjects.customaudience import CustomAudience
    for ca in targeting.get("custom_audiences", []) + targeting.get("excluded_custom_audiences", []):
        ca_id = str(ca.get("id", ""))
        try:
            data = CustomAudience(ca_id).api_get(
                fields=["id", "name", "delivery_status"]).export_all_data()
        except Exception as e:
            logger.error(f"custom audience {ca_id} could not be read: {e}")
            sys.exit(1)
        ds = (data.get("delivery_status") or {}).get("code")
        logger.info(f"  audience OK: {data.get('name')} ({ca_id}) delivery_status={ds}")


def create_campaign(account, name: str, daily_budget: int, abo: bool, dry_run: bool) -> str:
    """CBO (default): budget + bid strategy on the campaign. ABO (abo=True):
    NO campaign budget/bid — each ad set carries its own daily_budget
    (mirrors 'Campaign #2 - ABO - 7dc - Interest Testing - English')."""
    if dry_run:
        mode = "ABO (budgets on ad sets)" if abo else f"CBO ${daily_budget/100:.0f}/day"
        logger.info(f"[DRY RUN] Target: would create NEW campaign '{name}' "
                    f"({mode}, OUTCOME_SALES, PAUSED)")
        return "DRY_RUN_CAMPAIGN_ID"
    from facebook_business.adobjects.campaign import Campaign
    params = {
        Campaign.Field.name: name,
        Campaign.Field.objective: Campaign.Objective.outcome_sales,
        Campaign.Field.status: Campaign.Status.paused,
        Campaign.Field.special_ad_categories: [],
        Campaign.Field.buying_type: "AUCTION",
    }
    if abo:
        # required by the API for non-CBO campaigns; False = classic ABO
        params["is_adset_budget_sharing_enabled"] = False
    else:
        params[Campaign.Field.bid_strategy] = Campaign.BidStrategy.lowest_cost_without_cap
        params[Campaign.Field.daily_budget] = daily_budget
    c = account.create_campaign(params=params)
    return c["id"]


def create_ad_set(account, campaign_id: str, name: str, spec: dict, dry_run: bool) -> str:
    targeting = dict(spec["targeting"])
    # api_get returns names inside (excluded_)custom_audiences; create wants [{"id": ...}]
    for key in ("custom_audiences", "excluded_custom_audiences"):
        if key in targeting:
            targeting[key] = [{"id": str(ca["id"])} for ca in targeting[key]]
    params = {
        "name": name,
        "campaign_id": campaign_id,
        "status": "PAUSED",
        "optimization_goal": spec["optimization_goal"],
        "billing_event": spec["billing_event"],
        "destination_type": spec.get("destination_type", "WEBSITE"),
        "attribution_spec": spec["attribution_spec"],
        "promoted_object": spec["promoted_object"],
        "targeting": targeting,
    }
    # ABO: the ad set carries its own budget + bid strategy (absent under CBO)
    if spec.get("daily_budget"):
        params["daily_budget"] = int(spec["daily_budget"])
        params["bid_strategy"] = spec.get("bid_strategy", "LOWEST_COST_WITHOUT_CAP")
    if dry_run:
        ca_names = ", ".join(
            f"{ca.get('name','?')} ({ca['id']})"
            for ca in spec["targeting"].get("custom_audiences", []))
        budget_note = (f", ${int(spec['daily_budget'])/100:.0f}/day ad-set budget"
                       if spec.get("daily_budget") else "")
        logger.info(f"[DRY RUN] Target: would create NEW ad set '{name}' (PAUSED{budget_note})")
        logger.info(f"[DRY RUN]   audiences: {ca_names}")
        aa = (spec["targeting"].get("targeting_automation") or {}).get("advantage_audience")
        excl = ", ".join(f"{ca.get('name','?')} ({ca['id']})"
                         for ca in spec["targeting"].get("excluded_custom_audiences", []))
        logger.info(f"[DRY RUN]   advantage_audience={'ON' if aa else 'OFF'}, "
                    f"excluded: [{excl}], geo=US "
                    f"{spec['targeting']['geo_locations']['location_types']}, "
                    f"attribution={spec['attribution_spec']}")
        return "DRY_RUN_ADSET_ID"
    adset = account.create_ad_set(params=params)
    return adset["id"]


def load_video_cache() -> dict:
    if VIDEO_CACHE_PATH.exists():
        return json.loads(VIDEO_CACHE_PATH.read_text())
    return {}


def save_video_cache(cache: dict):
    VIDEO_CACHE_PATH.write_text(json.dumps(cache, indent=1))


def upload_video(account, video_path: Path, dry_run: bool) -> str:
    """Upload + poll until 'ready'. Poll via export_all_data() — comparing the
    raw SDK VideoStatus object to a string silently never matches (May bug)."""
    if dry_run:
        return f"DRY_RUN_VIDEO_ID[{video_path.name}]"
    import time as _time
    from facebook_business.adobjects.advideo import AdVideo
    logger.info(f"  Uploading video: {video_path.name}")
    video = account.create_ad_video(params={"filename": str(video_path)})
    video_id = video["id"]
    for attempt in range(60):
        _time.sleep(10)
        v = AdVideo(video_id).api_get(fields=["status"])
        status = v.export_all_data().get("status", {}).get("video_status", "")
        if status == "ready":
            logger.info(f"    ready after {attempt+1} polls")
            break
        if status == "error":
            raise RuntimeError(f"video {video_path.name} failed processing")
    else:
        raise RuntimeError(f"video {video_path.name} never reached ready")
    return video_id


def get_preferred_thumbnail(video_id: str, account_id_bare: str, dry_run: bool) -> str:
    """Meta auto-generates thumbnails post-upload; fetch the preferred one and
    re-upload it as an AdImage -> stable image_hash for video_data."""
    if dry_run:
        return f"DRY_RUN_THUMB[{video_id}]"
    import tempfile
    import requests as req
    from facebook_business.adobjects.advideo import AdVideo
    from facebook_business.adobjects.adimage import AdImage
    v = AdVideo(video_id).api_get(fields=["thumbnails"])
    thumbs = v.export_all_data().get("thumbnails", {}).get("data", [])
    if not thumbs:
        raise RuntimeError(f"no thumbnails for video {video_id}")
    preferred = next((t for t in thumbs if t.get("is_preferred")), thumbs[0])
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(req.get(preferred["uri"], timeout=30).content)
        tmp_path = f.name
    image = AdImage(parent_id=f"act_{account_id_bare}")
    image[AdImage.Field.filename] = tmp_path
    image.remote_create()
    return image[AdImage.Field.hash]


def upload_image(account_id: str, image_path: Path, dry_run: bool) -> str:
    if dry_run:
        return f"DRY_RUN_IMAGE_HASH[{image_path.name}]"
    from facebook_business.adobjects.adimage import AdImage
    logger.info(f"  Uploading image: {image_path.name}")
    image = AdImage(parent_id=account_id)
    image[AdImage.Field.filename] = str(image_path)
    image.remote_create()
    return image[AdImage.Field.hash]


def create_partnership_creative(account, image_hash: str, ad: dict, partnership: dict,
                                landing_url: str, dry_run: bool) -> str:
    """Validated 2026-07-06 (creative 1782162012945380 probe): partnership dark post =
    creator's own page + IG in object_story_spec, brand declared via the two
    *_branded_content sponsor fields. The sponsor fields are what route Meta's
    authorization through the creator's partnership grant instead of the
    ad account's owned-identity check (which fails with 1815199/1341012)."""
    name = Path(ad["video_filename"]).stem
    is_partnership = bool(partnership and partnership.get("creator_fb_page_id"))
    # Multi-headline / multi-body support (Cole 2026-08-04): headlines/bodies
    # LISTS override the single headline/primary_text. >1 of either on a VIDEO
    # => Advantage+ asset_feed_spec (Meta's native multiple-text-option feature;
    # Meta rotates/optimizes) instead of single-title video_data. A single entry
    # falls back to the original object_story_spec path (back-compat).
    headlines = [h for h in (ad.get("headlines") or [ad.get("headline")]) if h]
    bodies = [b for b in (ad.get("bodies") or [ad.get("primary_text")]) if b]
    description = ad.get("description", "") or ""
    is_video = isinstance(image_hash, dict) and bool(image_hash.get("video_id"))
    multi = len(headlines) > 1 or len(bodies) > 1
    if dry_run:
        kind = "PARTNERSHIP" if is_partnership else "BRAND"
        fmt = "asset_feed_spec MULTI" if multi else "single-title"
        logger.info(f"[DRY RUN] Would create {kind} creative [{fmt}] for: {name}")
        if is_partnership:
            logger.info(f"  creator: {partnership.get('handle','?')} "
                        f"(ig {partnership['instagram_user_id']}, page {partnership['creator_fb_page_id']}) "
                        f"| sponsors: ig {partnership['sponsor_instagram_id']}, page {partnership['sponsor_page_id']}")
        logger.info(f"  bodies({len(bodies)}): {bodies[0][:55]}...")
        logger.info(f"  headlines({len(headlines)}): {headlines}")
        return "DRY_RUN_CREATIVE_ID"
    from facebook_business.adobjects.adcreative import AdCreative
    page_id = (str(partnership["creator_fb_page_id"]) if is_partnership
               else str(partnership["page_id"]))
    ig_id = str(partnership["instagram_user_id"])
    if multi:
        # Advantage+ / "Standard Enhancements" multi-text on a STANDARD ad:
        # the BASE creative (media + link/CTA) lives in object_story_spec
        # (video_data for video, link_data for a static image) — this is what
        # carries the destination link; asset_feed_spec media assets have no link
        # field, hence error 2061015 if the base is omitted. asset_feed_spec then
        # supplies the multiple title/body OPTIONS with optimization_type=
        # DEGREES_OF_FREEDOM (FLEX, not Dynamic Creative -> runs in a non-dynamic
        # ad set, multiple ads per set OK). Validated live: video 2026-08-05.
        if is_video:
            story_data_key = "video_data"
            base_story = {
                "video_id": image_hash["video_id"],
                "image_hash": image_hash["thumb_hash"],
                "title": headlines[0],
                "message": bodies[0],
                "link_description": description,
                "call_to_action": {"type": "SHOP_NOW", "value": {"link": landing_url}},
            }
        else:
            story_data_key = "link_data"
            base_story = {
                "link": landing_url,
                "name": headlines[0],
                "message": bodies[0],
                "description": description,
                "image_hash": image_hash,
                "call_to_action": {"type": "SHOP_NOW", "value": {"link": landing_url}},
            }
        afs = {
            "optimization_type": "DEGREES_OF_FREEDOM",
            "titles": [{"text": h} for h in headlines],
            "bodies": [{"text": b} for b in bodies],
        }
        if description:
            afs["descriptions"] = [{"text": description}]
        params = {
            AdCreative.Field.name: f"Creative - {name}",
            AdCreative.Field.object_story_spec: {"page_id": page_id,
                                                 "instagram_user_id": ig_id,
                                                 story_data_key: base_story},
            "asset_feed_spec": afs,
            AdCreative.Field.url_tags: URL_TAGS,
        }
    else:
        # single-title path (unchanged): video -> video_data, image -> link_data
        if is_video:
            story_data_key = "video_data"
            story_data = {
                "video_id": image_hash["video_id"],
                "image_hash": image_hash["thumb_hash"],
                "title": headlines[0],
                "message": bodies[0],
                "link_description": description,
                "call_to_action": {"type": "SHOP_NOW", "value": {"link": landing_url}},
            }
        else:
            story_data_key = "link_data"
            story_data = {
                "link": landing_url,
                "message": bodies[0],
                "description": description,
                "image_hash": image_hash,
                "call_to_action": {"type": "SHOP_NOW", "value": {"link": landing_url}},
            }
            if headlines:  # headline optional (BOF statics carry the hook in-image)
                story_data["name"] = headlines[0]
        params = {
            AdCreative.Field.name: f"Creative - {name}",
            AdCreative.Field.object_story_spec: {"page_id": page_id,
                                                 "instagram_user_id": ig_id,
                                                 story_data_key: story_data},
            AdCreative.Field.url_tags: URL_TAGS,
        }
    if is_partnership:
        params["instagram_branded_content"] = {"sponsor_id": str(partnership["sponsor_instagram_id"])}
        params["facebook_branded_content"] = {"sponsor_page_id": str(partnership["sponsor_page_id"])}
        params["branded_content"] = partnership.get("branded_content") or {"ad_format": 3}
    creative = account.create_ad_creative(params=params)
    return creative["id"]


def create_ad(account, adset_id: str, creative_id: str, name: str, dry_run: bool) -> str:
    if dry_run:
        logger.info(f"[DRY RUN] Would create ad: {name} (PAUSED)")
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
    parser = argparse.ArgumentParser(description="Partnership-ad uploader (one-off operator script)")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Max ads to create (0 = all)")
    parser.add_argument("--campaign-id", default="",
                        help="Reuse an EXISTING campaign (skip create) — retry path")
    parser.add_argument("--adset-id", default="",
                        help="Reuse an EXISTING ad set (skip create) — retry path")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        logger.error(f"Config not found: {config_path}")
        sys.exit(1)
    with open(config_path) as f:
        config = json.load(f)

    # partnership block OPTIONAL: present = partnership dark posts (creator identity
    # + sponsor fields); absent = plain brand-identity ads (env page + IG actor).
    partnership = config.get("partnership")
    ad_set_spec = config.get("ad_set_spec")
    if partnership:
        for key in ("instagram_user_id", "creator_fb_page_id",
                    "sponsor_instagram_id", "sponsor_page_id"):
            if not str(partnership.get(key, "")).isdigit():
                logger.error(f"config.partnership.{key} (numeric) is required")
                sys.exit(1)
    # ad_set_spec is only needed to CREATE a new ad set. When --adset-id targets
    # an existing set, we skip create_ad_set entirely, so the spec is optional.
    if not args.adset_id and (not ad_set_spec or not ad_set_spec.get("targeting")):
        logger.error("config.ad_set_spec.targeting is required (creating a new ad set)")
        sys.exit(1)

    campaign_name = config["campaign_name"]
    ad_set_name = config["ad_set_name"]
    daily_budget = int(config.get("daily_budget", 20000))
    ads = config.get("ads", [])
    if not ads:
        logger.error("No ads in config file")
        sys.exit(1)
    if args.limit:
        ads = ads[: args.limit]

    non_media = [a["video_filename"] for a in ads
                 if Path(a["video_filename"]).suffix.lower() not in MEDIA_EXTENSIONS]
    if non_media:
        logger.error(f"Unsupported media extensions: {non_media}")
        sys.exit(1)
    missing = [a["video_filename"] for a in ads
               if not (RENAMED_VIDEOS_DIR / a["video_filename"]).exists()]
    if missing:
        logger.error(f"Media missing from renamed_videos/: {missing}")
        sys.exit(1)

    partner_desc = (f"{partnership.get('handle')} ({partnership['instagram_user_id']})"
                    if partnership else "NONE (brand identity)")
    logger.info(f"Config: {len(ads)} ads | campaign: {campaign_name} | ad set: {ad_set_name} "
                f"| partner: {partner_desc}")
    if args.dry_run:
        logger.info("--- DRY RUN MODE ---")

    ad_account_id, env_page_id, landing_url = init_api()
    ad_account_id = ad_account_id if ad_account_id.startswith("act_") else f"act_{ad_account_id}"
    # config landing_url override (e.g. a language-specific lander instead of the
    # env PDP); falls back to LANDING_PAGE_URL from .env.
    if config.get("landing_url"):
        landing_url = config["landing_url"]
        logger.info(f"  landing_url override: {landing_url}")
    if not landing_url:
        logger.error("LANDING_PAGE_URL missing from .env and config")
        sys.exit(1)
    if partnership:
        logger.info(f"  creative identity: creator page {partnership['creator_fb_page_id']} "
                    f"/ ig {partnership['instagram_user_id']} ({partnership.get('handle','?')})")
    else:
        import os
        env_ig_id = os.getenv("META_INSTAGRAM_ACTOR_ID", "")
        if not env_page_id or not env_ig_id:
            logger.error("brand mode needs META_PAGE_ID and META_INSTAGRAM_ACTOR_ID in .env")
            sys.exit(1)
        brand_identity = {"page_id": env_page_id, "instagram_user_id": env_ig_id}
        logger.info(f"  creative identity: BRAND page {env_page_id} / ig {env_ig_id} (no partnership)")

    from facebook_business.adobjects.adaccount import AdAccount
    account = AdAccount(ad_account_id)

    if ad_set_spec and ad_set_spec.get("targeting") and not args.adset_id:
        logger.info("Verifying custom audiences (SDK reads)...")
        verify_custom_audiences(ad_set_spec["targeting"])

    abo = bool(config.get("abo"))
    if args.campaign_id:
        campaign_id = args.campaign_id
        logger.info(f"  REUSING existing campaign: {campaign_id}")
    else:
        campaign_id = create_campaign(account, campaign_name, daily_budget, abo, args.dry_run)
        logger.info(f"  campaign_id: {campaign_id}")

    if args.adset_id:
        adset_id = args.adset_id
        from facebook_business.adobjects.adset import AdSet
        data = AdSet(adset_id).api_get(
            fields=["id", "name", "status", "campaign_id"]).export_all_data()
        if str(data.get("campaign_id")) != str(campaign_id):
            logger.error(f"--adset-id {adset_id} belongs to campaign "
                         f"{data.get('campaign_id')}, not {campaign_id} — aborting")
            sys.exit(1)
        logger.info(f"  REUSING existing ad set: {adset_id} "
                    f"('{data.get('name')}', {data.get('status')})")
    else:
        adset_id = create_ad_set(account, campaign_id, ad_set_name, ad_set_spec, args.dry_run)
        logger.info(f"  adset_id: {adset_id}")

    summary = {"campaign_id": campaign_id, "partnership": partnership,
               "ad_sets": [{"name": ad_set_name, "adset_id": adset_id, "ads": []}],
               "total_ads": 0, "errors": []}

    if partnership:
        label = partnership.get("handle", "AT")
        identity = partnership
    else:
        # "Ad Set #17 - STAT - Broad - All Purchases" -> "STAT" (pipeline convention)
        label = ad_set_name.split(" - ")[1] if " - " in ad_set_name else "STAT"
        identity = dict(brand_identity)
    video_cache = load_video_cache()
    for ad in ads:
        filename = ad["video_filename"]
        image_path = RENAMED_VIDEOS_DIR / filename
        is_video = image_path.suffix.lower() in VIDEO_EXTENSIONS
        try:
            if is_video:
                if filename in video_cache:
                    media = video_cache[filename]
                    logger.info(f"  video CACHE HIT: {filename} -> {media['video_id']}")
                else:
                    vid = upload_video(account, image_path, args.dry_run)
                    thumb = get_preferred_thumbnail(
                        vid, ad_account_id.replace("act_", ""), args.dry_run)
                    media = {"video_id": vid, "thumb_hash": thumb}
                    if not args.dry_run:
                        video_cache[filename] = media
                        save_video_cache(video_cache)
                    logger.info(f"  video_id: {vid} thumb: {thumb}")
                image_hash = media
            else:
                image_hash = upload_image(ad_account_id, image_path, args.dry_run)
                logger.info(f"  image_hash: {image_hash}")
            creative_id = create_partnership_creative(
                account, image_hash, ad, identity, landing_url, args.dry_run)
            logger.info(f"  creative_id: {creative_id}")
            hook = Path(filename).stem.split("-", 1)[-1].strip("_") or "Var1"
            # ad_name override (new naming schemes, e.g. Batch #2_..._Alex_V1);
            # falls back to the label//concept//hook//PDP convention.
            ad_name = ad.get("ad_name") or f"{label}//{ad.get('creative_concept','')}//{hook}//PDP"
            ad_id = create_ad(account, adset_id, creative_id, ad_name, args.dry_run)
            logger.info(f"  ad_id: {ad_id} | name: {ad_name}")
            summary["ad_sets"][0]["ads"].append({"filename": filename, "ad_id": ad_id})
            summary["total_ads"] += 1
        except Exception as e:
            logger.error(f"  Failed for {filename}: {e}")
            summary["errors"].append(f"{filename}: {e}")

    if not args.dry_run:
        log_path = OUTPUT_DIR / f"upload_log_{int(time.time())}.json"
        with open(log_path, "w") as f:
            json.dump(summary, f, indent=2)
        logger.info(f"\nLog saved: {log_path}")

    logger.info(f"\n=== DONE: {summary['total_ads']} ads created, {len(summary['errors'])} errors ===")
    for e in summary["errors"]:
        logger.error(f"  {e}")


if __name__ == "__main__":
    main()
