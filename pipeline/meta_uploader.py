import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.campaign import Campaign
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.adcreative import AdCreative
from facebook_business.adobjects.adimage import AdImage
from facebook_business.adobjects.advideo import AdVideo

from pipeline.config import (
    META_ACCESS_TOKEN,
    META_APP_ID,
    META_APP_SECRET,
    META_AD_ACCOUNT_ID,
    META_PAGE_ID,
    META_INSTAGRAM_ACTOR_ID,
    META_PIXEL_ID,
    META_CUSTOM_EVENT_TYPE,
    META_CUSTOM_CONVERSION_ID,
    LANDING_PAGE_URL,
    OUTPUT_DIR,
)

logger = logging.getLogger(__name__)

IMAGE_HASHES_CACHE = OUTPUT_DIR / "image_hashes.json"
VIDEO_IDS_CACHE = OUTPUT_DIR / "video_ids.json"
CAMPAIGN_LOG = OUTPUT_DIR / "campaign_log.json"


def init_meta_api():
    """Initialize the Facebook/Meta Marketing API."""
    FacebookAdsApi.init(META_APP_ID, META_APP_SECRET, META_ACCESS_TOKEN)
    logger.info("Meta Marketing API initialized")


# ── Image Upload ─────────────────────────────────────────────────────────

def upload_image(image_path: Path, max_retries: int = 3) -> str:
    """Upload an image to Meta and return the image hash. Retries on transient errors."""
    for attempt in range(max_retries):
        try:
            image = AdImage(parent_id=META_AD_ACCOUNT_ID)
            image[AdImage.Field.filename] = str(image_path)
            image.remote_create()
            image_hash = image[AdImage.Field.hash]
            logger.info(f"  Uploaded image {image_path.name} -> hash={image_hash}")
            return image_hash
        except Exception as e:
            if attempt < max_retries - 1:
                delay = 5 * (2 ** attempt)
                logger.warning(f"  Upload failed for {image_path.name} (attempt {attempt + 1}): {e}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                raise


def _load_image_hash_cache() -> dict[str, str]:
    """Load cached image hashes from disk."""
    if IMAGE_HASHES_CACHE.exists():
        with open(IMAGE_HASHES_CACHE) as f:
            cache = json.load(f)
        logger.info(f"  Loaded {len(cache)} cached image hashes")
        return cache
    return {}


def _save_image_hash_cache(cache: dict[str, str]):
    """Save image hashes to disk for reuse across runs."""
    IMAGE_HASHES_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(IMAGE_HASHES_CACHE, "w") as f:
        json.dump(cache, f, indent=2)
    logger.info(f"  Saved {len(cache)} image hashes to cache")


# ── Video Upload ─────────────────────────────────────────────────────────

def upload_video(video_path: Path, max_retries: int = 3, poll_interval: int = 10, max_wait: int = 600) -> str:
    """Upload a video to Meta and return the video ID.

    Waits for video encoding to complete (polls status).

    Args:
        video_path: Path to the video file.
        max_retries: Number of upload retry attempts.
        poll_interval: Seconds between encoding status checks.
        max_wait: Maximum seconds to wait for encoding.

    Returns:
        Video ID string.
    """
    for attempt in range(max_retries):
        try:
            video = AdVideo(parent_id=META_AD_ACCOUNT_ID)
            video[AdVideo.Field.filepath] = str(video_path)
            video.remote_create()
            video_id = video["id"]
            logger.info(f"  Uploaded video {video_path.name} -> id={video_id}")

            # Wait for encoding to complete
            logger.info(f"  Waiting for video encoding ({video_path.name})...")
            elapsed = 0
            while elapsed < max_wait:
                time.sleep(poll_interval)
                elapsed += poll_interval

                video_obj = AdVideo(video_id)
                video_obj.api_get(fields=["status"])
                status = video_obj.get("status", {})
                encoding_status = status.get("video_status", "processing")

                if encoding_status == "ready":
                    logger.info(f"  Video {video_path.name} encoding complete ({elapsed}s)")
                    return video_id
                elif encoding_status == "error":
                    raise RuntimeError(f"Video encoding failed for {video_path.name}: {status}")

                logger.info(f"  Video {video_path.name} still encoding ({elapsed}s)...")

            raise TimeoutError(f"Video encoding timed out after {max_wait}s for {video_path.name}")
        except (TimeoutError, RuntimeError):
            raise
        except Exception as e:
            if attempt < max_retries - 1:
                delay = 10 * (2 ** attempt)
                logger.warning(f"  Video upload failed for {video_path.name} (attempt {attempt + 1}): {e}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                raise


def _load_video_id_cache() -> dict[str, str]:
    """Load cached video IDs from disk."""
    if VIDEO_IDS_CACHE.exists():
        with open(VIDEO_IDS_CACHE) as f:
            cache = json.load(f)
        logger.info(f"  Loaded {len(cache)} cached video IDs")
        return cache
    return {}


def _save_video_id_cache(cache: dict[str, str]):
    """Save video IDs to disk for reuse across runs."""
    VIDEO_IDS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(VIDEO_IDS_CACHE, "w") as f:
        json.dump(cache, f, indent=2)
    logger.info(f"  Saved {len(cache)} video IDs to cache")


# ── Campaign & Ad Set ────────────────────────────────────────────────────

def create_campaign(name: str, daily_budget: int = 20000) -> str:
    """Create a paused CBO campaign. Returns campaign ID.

    daily_budget is in cents (default $200.00).
    """
    account = AdAccount(META_AD_ACCOUNT_ID)
    campaign = account.create_campaign(params={
        Campaign.Field.name: name,
        Campaign.Field.objective: Campaign.Objective.outcome_sales,
        Campaign.Field.status: Campaign.Status.paused,
        Campaign.Field.special_ad_categories: [],
        Campaign.Field.daily_budget: daily_budget,
        Campaign.Field.bid_strategy: Campaign.BidStrategy.lowest_cost_without_cap,
    })

    campaign_id = campaign["id"]
    logger.info(f"Created campaign: {name} (ID: {campaign_id}, ${daily_budget/100:.0f}/day CBO)")
    return campaign_id


def _build_promoted_object() -> dict:
    """Build the promoted_object dict for conversion optimization.

    Uses custom_conversion_id when available, falls back to pixel + custom_event_type.
    """
    if META_CUSTOM_CONVERSION_ID:
        return {
            "custom_conversion_id": META_CUSTOM_CONVERSION_ID,
        }
    return {
        "pixel_id": META_PIXEL_ID,
        "custom_event_type": META_CUSTOM_EVENT_TYPE,
    }


def create_ad_set(campaign_id: str, concept_name: str) -> str:
    """Create a paused ad set for a creative concept. Returns ad set ID.

    Uses broad targeting:
    - US, 18-65, Women only
    - Advantage+ audience OFF (gender is a hard constraint)
    - No ad set budget (uses campaign CBO)
    - Optimizes for PURCHASE via pixel + custom event
    """
    account = AdAccount(META_AD_ACCOUNT_ID)
    ad_set = account.create_ad_set(params={
        AdSet.Field.name: f"Ad Set - {concept_name}",
        AdSet.Field.campaign_id: campaign_id,
        AdSet.Field.billing_event: AdSet.BillingEvent.impressions,
        AdSet.Field.optimization_goal: AdSet.OptimizationGoal.offsite_conversions,
        AdSet.Field.promoted_object: _build_promoted_object(),
        AdSet.Field.targeting: {
            "geo_locations": {
                "countries": ["US"],
                "location_types": ["home", "recent"],
            },
            "age_min": 18,
            "age_max": 65,
            "genders": [2],  # Women only (Meta API: 1=male, 2=female)
            "targeting_automation": {
                "advantage_audience": 0,  # Off — gender must be a hard constraint
            },
        },
        AdSet.Field.status: AdSet.Status.paused,
        # 7-day click, 1-day view, 1-day engaged view attribution window
        "attribution_spec": [
            {"event_type": "CLICK_THROUGH", "window_days": 7},
            {"event_type": "VIEW_THROUGH", "window_days": 1},
            {"event_type": "ENGAGED_VIDEO_VIEW", "window_days": 1},
        ],
    })

    ad_set_id = ad_set["id"]
    logger.info(f"  Created ad set: {concept_name} (ID: {ad_set_id})")
    return ad_set_id


# ── URL Parameters ────────────────────────────────────────────────────────

URL_TAGS = (
    "utm_source=facebook"
    "&utm_medium=paid"
    "&utm_campaign={{campaign.name}}"
    "&utm_term={{adset.name}}"
    "&utm_content={{ad.name}}"
    "&fbadid={{ad.id}}"
    "&tw_source={{site_source_name}}"
    "&tw_adid={{ad.id}}"
)


# ── Ad Creation ──────────────────────────────────────────────────────────

def create_ad_with_text_variations(
    ad_set_id: str,
    image_hash: str,
    variations: list[dict],
    ad_name: str,
) -> str:
    """Create an image ad with 1 image and multiple text variations.

    Uses asset_feed_spec for text variations + degrees_of_freedom_spec
    for Advantage+ creative optimizations.
    """
    account = AdAccount(META_AD_ACCOUNT_ID)

    object_story_spec = {
        "page_id": META_PAGE_ID,
        "link_data": {
            "image_hash": image_hash,
            "link": LANDING_PAGE_URL,
            "call_to_action": {
                "type": "SHOP_NOW",
                "value": {"link": LANDING_PAGE_URL},
            },
        },
    }
    if META_INSTAGRAM_ACTOR_ID:
        object_story_spec["instagram_user_id"] = META_INSTAGRAM_ACTOR_ID

    asset_feed_spec = {
        "images": [{"hash": image_hash}],
        "bodies": [{"text": v["primary_text"]} for v in variations],
        "titles": [{"text": v["headline"]} for v in variations],
        "descriptions": [{"text": v["description"]} for v in variations],
        "link_urls": [{"website_url": LANDING_PAGE_URL}],
        "call_to_action_types": ["SHOP_NOW"],
        "ad_formats": ["AUTOMATIC_FORMAT"],
        "optimization_type": "DEGREES_OF_FREEDOM",
    }

    degrees_of_freedom_spec = {
        "creative_features_spec": {
            "text_optimizations": {"enroll_status": "OPT_IN"},
            "enhance_cta": {"enroll_status": "OPT_OUT"},
            "show_summary": {"enroll_status": "OPT_OUT"},
            "image_touchups": {"enroll_status": "OPT_OUT"},
            "audio": {"enroll_status": "OPT_OUT"},
            "image_animation": {"enroll_status": "OPT_OUT"},
            "image_uncrop": {"enroll_status": "OPT_OUT"},
            "image_brightness_and_contrast": {"enroll_status": "OPT_OUT"},
        },
    }

    for attempt in range(3):
        try:
            creative = account.create_ad_creative(params={
                AdCreative.Field.name: f"Creative - {ad_name}",
                AdCreative.Field.object_story_spec: object_story_spec,
                AdCreative.Field.asset_feed_spec: asset_feed_spec,
                AdCreative.Field.degrees_of_freedom_spec: degrees_of_freedom_spec,
                AdCreative.Field.url_tags: URL_TAGS,
            })

            ad = account.create_ad(params={
                Ad.Field.name: f"Ad - {ad_name}",
                Ad.Field.adset_id: ad_set_id,
                Ad.Field.status: Ad.Status.paused,
                Ad.Field.creative: {"creative_id": creative["id"]},
            })

            ad_id = ad["id"]
            logger.info(f"    Created image ad '{ad_name}' (ID: {ad_id})")
            return ad_id
        except Exception as e:
            if attempt < 2:
                delay = 5 * (2 ** attempt)
                logger.warning(f"    Ad creation failed for '{ad_name}' (attempt {attempt + 1}): {e}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                raise


def create_video_ad_with_text_variations(
    ad_set_id: str,
    video_id: str,
    thumbnail_hash: str,
    variations: list[dict],
    ad_name: str,
) -> str:
    """Create a video ad with 1 text variation.

    Partnership ads (with instagram_user_id) only support a single
    body/title/description — uses the first variation only.
    """
    account = AdAccount(META_AD_ACCOUNT_ID)

    # Partnership ads only support 1 text variation
    v = variations[0]

    object_story_spec = {
        "page_id": META_PAGE_ID,
        "video_data": {
            "video_id": video_id,
            "image_hash": thumbnail_hash,
            "call_to_action": {
                "type": "SHOP_NOW",
                "value": {"link": LANDING_PAGE_URL},
            },
        },
    }
    if META_INSTAGRAM_ACTOR_ID:
        object_story_spec["instagram_user_id"] = META_INSTAGRAM_ACTOR_ID

    asset_feed_spec = {
        "videos": [{"video_id": video_id, "thumbnail_hash": thumbnail_hash}],
        "bodies": [{"text": v["primary_text"]}],
        "titles": [{"text": v["headline"]}],
        "descriptions": [{"text": v["description"]}],
        "link_urls": [{"website_url": LANDING_PAGE_URL}],
        "call_to_action_types": ["SHOP_NOW"],
        "ad_formats": ["AUTOMATIC_FORMAT"],
        "optimization_type": "DEGREES_OF_FREEDOM",
    }

    degrees_of_freedom_spec = {
        "creative_features_spec": {
            "text_optimizations": {"enroll_status": "OPT_IN"},
            "enhance_cta": {"enroll_status": "OPT_OUT"},
            "show_summary": {"enroll_status": "OPT_OUT"},
            "video_auto_crop": {"enroll_status": "OPT_OUT"},
            "audio": {"enroll_status": "OPT_OUT"},
            "video_filtering": {"enroll_status": "OPT_OUT"},
            "image_animation": {"enroll_status": "OPT_OUT"},
            "image_uncrop": {"enroll_status": "OPT_OUT"},
            "image_brightness_and_contrast": {"enroll_status": "OPT_OUT"},
        },
    }

    for attempt in range(3):
        try:
            creative = account.create_ad_creative(params={
                AdCreative.Field.name: f"Creative - {ad_name}",
                AdCreative.Field.object_story_spec: object_story_spec,
                AdCreative.Field.asset_feed_spec: asset_feed_spec,
                AdCreative.Field.degrees_of_freedom_spec: degrees_of_freedom_spec,
                AdCreative.Field.url_tags: URL_TAGS,
            })

            ad = account.create_ad(params={
                Ad.Field.name: f"Ad - {ad_name}",
                Ad.Field.adset_id: ad_set_id,
                Ad.Field.status: Ad.Status.paused,
                Ad.Field.creative: {"creative_id": creative["id"]},
            })

            ad_id = ad["id"]
            logger.info(f"    Created video ad '{ad_name}' (ID: {ad_id})")
            return ad_id
        except Exception as e:
            if attempt < 2:
                delay = 5 * (2 ** attempt)
                logger.warning(f"    Video ad creation failed for '{ad_name}' (attempt {attempt + 1}): {e}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                raise


# ── Parallel Ad Creation Helper ───────────────────────────────────────────

def _create_ads_parallel(ad_set_id: str, tasks: list[tuple], max_workers: int = 5) -> list[str]:
    """Create ads in parallel for a given ad set.

    Each task tuple: (kind, vid_id, thumb_hash, img_hash, variations, ad_name)
    Returns list of created ad IDs.
    """
    ad_ids = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for task in tasks:
            kind, vid_id, thumb_hash, img_hash, variations, ad_name = task
            if kind == "video":
                fut = executor.submit(
                    create_video_ad_with_text_variations,
                    ad_set_id=ad_set_id, video_id=vid_id,
                    thumbnail_hash=thumb_hash, variations=variations,
                    ad_name=ad_name,
                )
            else:
                fut = executor.submit(
                    create_ad_with_text_variations,
                    ad_set_id=ad_set_id, image_hash=img_hash,
                    variations=variations, ad_name=ad_name,
                )
            futures[fut] = ad_name

        for fut in as_completed(futures):
            ad_name = futures[fut]
            try:
                ad_id = fut.result()
                ad_ids.append(ad_id)
            except Exception as e:
                logger.error(f"    Failed to create ad '{ad_name}': {e}")

    return ad_ids


# ── Campaign Log ──────────────────────────────────────────────────────────

def _load_campaign_log() -> list[dict]:
    if CAMPAIGN_LOG.exists():
        with open(CAMPAIGN_LOG) as f:
            return json.load(f)
    return []


def _save_campaign_log(log: list[dict]):
    CAMPAIGN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CAMPAIGN_LOG, "w") as f:
        json.dump(log, f, indent=2)


def _next_campaign_name(base_name: str) -> str:
    log = _load_campaign_log()
    # Count how many campaigns share this base name
    count = sum(1 for entry in log if entry.get("base_name") == base_name)
    run_number = count + 1
    return f"{base_name} #{run_number}"


def _log_campaign(base_name: str, campaign_name: str, campaign_id: str):
    log = _load_campaign_log()
    log.append({
        "base_name": base_name,
        "campaign_name": campaign_name,
        "campaign_id": campaign_id,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    _save_campaign_log(log)
    logger.info(f"  Logged campaign: {campaign_name} -> {campaign_id}")


# ── Full Upload Flow ─────────────────────────────────────────────────────

def upload_to_meta(
    results: list[dict],
    campaign_name: str = "Spicy Cubes Dailies - Auto Generated",
    daily_budget: int = 20000,
) -> dict:
    """Full upload flow: media -> campaign (CBO) -> ad sets -> ads with text variations.

    Structure: 1 CBO campaign -> 1 ad set per concept -> 1 ad per media item.
    Image ads use AdImage + link_data; video ads use AdVideo + video_data.
    Both coexist in the same ad sets.

    All created PAUSED for review before going live.

    Args:
        results: List of dicts with creative_concept, sub_group_name, images, variations.
                 Each 'images' is a list of {image_filename, image_path, media_type}.
        campaign_name: Name for the campaign.
        daily_budget: Campaign daily budget in cents (default $200.00).

    Returns summary dict with IDs and counts.
    """
    init_meta_api()

    # 1. Upload all unique images (with disk cache)
    logger.info("Step 1: Uploading images to Meta...")
    image_hashes = _load_image_hash_cache()
    uploaded_image_count = 0
    for result in results:
        for img in result["images"]:
            if img.get("media_type") == "video":
                continue  # Videos handled separately
            filename = img["image_filename"]
            if filename in image_hashes:
                continue
            image_path = Path(img["image_path"])
            if image_path.exists():
                image_hashes[filename] = upload_image(image_path)
                uploaded_image_count += 1
                if uploaded_image_count % 20 == 0:
                    _save_image_hash_cache(image_hashes)
    _save_image_hash_cache(image_hashes)
    logger.info(f"  {uploaded_image_count} new image uploads, {len(image_hashes)} total cached")

    # 1b. Upload all unique videos (with disk cache)
    logger.info("Step 1b: Uploading videos to Meta...")
    video_ids = _load_video_id_cache()
    uploaded_video_count = 0
    for result in results:
        for img in result["images"]:
            if img.get("media_type") != "video":
                continue
            filename = img["image_filename"]
            if filename in video_ids:
                continue
            video_path = Path(img["image_path"])
            if video_path.exists():
                video_ids[filename] = upload_video(video_path)
                uploaded_video_count += 1
                _save_video_id_cache(video_ids)
    _save_video_id_cache(video_ids)
    logger.info(f"  {uploaded_video_count} new video uploads, {len(video_ids)} total cached")

    # 1c. Upload video thumbnails as images for video_data.image_hash
    logger.info("Step 1c: Uploading video thumbnails...")
    from pipeline.config import VIDEO_PREPROCESSED_JSON
    video_thumbnail_hashes: dict[str, str] = {}
    if VIDEO_PREPROCESSED_JSON.exists():
        with open(VIDEO_PREPROCESSED_JSON) as f:
            video_preprocessed = json.load(f)
        for vinfo in video_preprocessed:
            vname = vinfo["video_filename"]
            thumb_key = f"_thumb_{vname}"
            # Check if thumbnail already in image cache
            if thumb_key in image_hashes:
                video_thumbnail_hashes[vname] = image_hashes[thumb_key]
                continue
            # Upload first frame as thumbnail
            frame_path = Path(vinfo["frame_paths"][0])
            if frame_path.exists():
                thumb_hash = upload_image(frame_path)
                image_hashes[thumb_key] = thumb_hash
                video_thumbnail_hashes[vname] = thumb_hash
        _save_image_hash_cache(image_hashes)
    logger.info(f"  {len(video_thumbnail_hashes)} video thumbnails ready")

    # 2. Create CBO campaign with incrementing name
    logger.info("Step 2: Creating campaign...")
    numbered_name = _next_campaign_name(campaign_name)
    campaign_id = create_campaign(numbered_name, daily_budget=daily_budget)
    _log_campaign(campaign_name, numbered_name, campaign_id)

    # 3. Group results by creative concept
    concept_groups: dict[str, list[dict]] = {}
    for result in results:
        concept = result["creative_concept"]
        concept_groups.setdefault(concept, []).append(result)

    # 4. Create ad sets (1 per concept for images, 1 per concept for videos) with 1 ad per media item
    logger.info("Step 3: Creating ad sets and ads...")
    summary = {
        "campaign_id": campaign_id,
        "campaign_name": numbered_name,
        "ad_sets": {},
        "total_ads": 0,
    }

    max_workers = 5  # Concurrent ad creations per ad set
    concept_list = list(concept_groups.items())

    # Split each concept into image tasks and video tasks
    ad_set_index = 0
    for concept, group_results in concept_list:
        image_tasks = []
        video_tasks = []

        for result in group_results:
            sg_name = result["sub_group_name"]
            variations = result["variations"]

            for img in result["images"]:
                filename = img["image_filename"]
                media_type = img.get("media_type", "image")
                ad_name = f"{concept}/{sg_name}/{filename}"

                if media_type == "video":
                    vid_id = video_ids.get(filename)
                    if not vid_id:
                        logger.warning(f"    No video ID for '{filename}', skipping")
                        continue
                    thumb_hash = video_thumbnail_hashes.get(filename)
                    if not thumb_hash:
                        logger.warning(f"    No thumbnail hash for '{filename}', skipping")
                        continue
                    video_tasks.append(("video", vid_id, thumb_hash, None, variations, ad_name))
                else:
                    img_hash = image_hashes.get(filename)
                    if not img_hash:
                        logger.warning(f"    No hash for '{filename}', skipping")
                        continue
                    image_tasks.append(("image", None, None, img_hash, variations, ad_name))

        # Create image ad set if there are images
        if image_tasks:
            if ad_set_index > 0:
                logger.info("  Pausing 15s between ad sets...")
                time.sleep(15)
            ad_set_id = create_ad_set(campaign_id, concept)
            ad_set_index += 1

            ad_ids = _create_ads_parallel(ad_set_id, image_tasks, max_workers)
            summary["ad_sets"][concept] = {
                "ad_set_id": ad_set_id,
                "ad_count": len(ad_ids),
                "ad_ids": ad_ids,
            }
            summary["total_ads"] += len(ad_ids)
            logger.info(f"  {concept}: {len(ad_ids)} image ads created")

        # Create separate video ad set if there are videos
        if video_tasks:
            if ad_set_index > 0:
                logger.info("  Pausing 15s between ad sets...")
                time.sleep(15)
            video_ad_set_id = create_ad_set(campaign_id, f"{concept} (Video)")
            ad_set_index += 1

            ad_ids = _create_ads_parallel(video_ad_set_id, video_tasks, max_workers)
            summary["ad_sets"][f"{concept} (Video)"] = {
                "ad_set_id": video_ad_set_id,
                "ad_count": len(ad_ids),
                "ad_ids": ad_ids,
            }
            summary["total_ads"] += len(ad_ids)
            logger.info(f"  {concept} (Video): {len(ad_ids)} video ads created")

    logger.info(f"Upload complete: {summary['total_ads']} total ads across {len(summary['ad_sets'])} ad sets (all PAUSED)")
    return summary
