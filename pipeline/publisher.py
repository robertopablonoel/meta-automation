#!/usr/bin/env python3
"""
Publish pipeline output data to Supabase for the dashboard.

Reads pipeline output files and campaign_log.json, upserts everything to Supabase
so the dashboard can join Meta metrics with pipeline metadata.

Usage:
    python publisher.py                          # Publish latest campaign
    python publisher.py --campaign-id 12345      # Publish specific campaign
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from .config import OUTPUT_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Output files
CAMPAIGN_LOG = OUTPUT_DIR / "campaign_log.json"
AD_COPY_OUTPUT = OUTPUT_DIR / "ad_copy_output.json"
DESCRIPTIONS_JSON = OUTPUT_DIR / "descriptions.json"
CATEGORIES_JSON = OUTPUT_DIR / "categories.json"
SUBGROUPS_JSON = OUTPUT_DIR / "subgroups.json"
VIDEO_CATEGORIES_JSON = OUTPUT_DIR / "video_categories.json"
VIDEO_CLASSIFICATIONS_JSON = OUTPUT_DIR / "video_classifications.json"


def load_json(path: Path) -> dict | list | None:
    if not path.exists():
        logger.warning(f"File not found: {path}")
        return None
    with open(path) as f:
        return json.load(f)


def get_campaign_id(explicit_id: str | None) -> str:
    """Get campaign ID from CLI arg or latest campaign_log entry."""
    if explicit_id:
        return explicit_id

    log = load_json(CAMPAIGN_LOG)
    if not log or not isinstance(log, list) or len(log) == 0:
        logger.error("No campaign_log.json found. Run pipeline with --upload first, or pass --campaign-id.")
        sys.exit(1)

    latest = log[-1]
    campaign_id = latest["campaign_id"]
    logger.info(f"Using latest campaign: {latest['campaign_name']} ({campaign_id})")
    return campaign_id


def get_campaign_name(campaign_id: str) -> str | None:
    log = load_json(CAMPAIGN_LOG)
    if log and isinstance(log, list):
        for entry in log:
            if entry.get("campaign_id") == campaign_id:
                return entry.get("campaign_name")
    return None


def publish(campaign_id: str):
    """Publish all pipeline data to Supabase."""
    try:
        from supabase import create_client
    except ImportError:
        logger.error("supabase not installed. Run: venv/bin/pip install supabase")
        sys.exit(1)

    url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")

    if not url or not key:
        logger.error("Missing SUPABASE_URL / SUPABASE_KEY in environment. Add to .env")
        sys.exit(1)

    sb = create_client(url, key)
    campaign_name = get_campaign_name(campaign_id)

    # 1. Upsert pipeline_runs
    logger.info("Publishing pipeline_runs...")
    sb.table("pipeline_runs").upsert({
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
    }, on_conflict="campaign_id").execute()

    # 2. Upsert concepts from categories.json + video_categories.json
    logger.info("Publishing concepts...")
    all_categories = []

    categories = load_json(CATEGORIES_JSON)
    if categories and "categories" in categories:
        all_categories.extend(categories["categories"])

    video_cats = load_json(VIDEO_CATEGORIES_JSON)
    if video_cats and "categories" in video_cats:
        all_categories.extend(video_cats["categories"])

    # Also grab from ad_copy_output.json in case they differ
    ad_copy = load_json(AD_COPY_OUTPUT)
    if ad_copy and "categories" in ad_copy:
        existing_names = {c["name"] for c in all_categories}
        for cat in ad_copy["categories"]:
            if cat["name"] not in existing_names:
                all_categories.append(cat)

    for cat in all_categories:
        sb.table("concepts").upsert({
            "campaign_id": campaign_id,
            "name": cat["name"],
            "display_name": cat.get("display_name"),
            "description": cat.get("description"),
            "schwartz_sophistication": cat.get("schwartz_sophistication"),
            "belief_mapping": cat.get("belief_mapping"),
        }, on_conflict="campaign_id,name").execute()

    logger.info(f"  Published {len(all_categories)} concepts")

    # 3. Upsert ad_descriptions from descriptions.json
    logger.info("Publishing ad_descriptions...")
    descriptions = load_json(DESCRIPTIONS_JSON)
    if descriptions and isinstance(descriptions, list):
        for desc in descriptions:
            sb.table("ad_descriptions").upsert({
                "campaign_id": campaign_id,
                "filename": desc["image_filename"],
                "media_type": desc.get("media_type", "image"),
                "visual_elements": desc.get("visual_elements"),
                "emotional_tone": desc.get("emotional_tone"),
                "implied_message": desc.get("implied_message"),
                "target_awareness_level": desc.get("target_awareness_level"),
                "transcript_summary": desc.get("transcript_summary"),
            }, on_conflict="campaign_id,filename").execute()
        logger.info(f"  Published {len(descriptions)} descriptions")

    # 4. Upsert copy_variations + ad_mappings from ad_copy_output.json
    logger.info("Publishing copy_variations and ad_mappings...")
    variation_count = 0
    mapping_count = 0

    if ad_copy and "concepts" in ad_copy:
        for concept_data in ad_copy["concepts"]:
            concept_name = concept_data["creative_concept"]
            for sg in concept_data.get("sub_groups", []):
                sg_name = sg["sub_group_name"]
                images = sg.get("images", [])

                # Copy variations
                for i, var in enumerate(sg.get("variations", []), start=1):
                    sb.table("copy_variations").upsert({
                        "campaign_id": campaign_id,
                        "concept_name": concept_name,
                        "sub_group_name": sg_name,
                        "variation_number": i,
                        "primary_text": var.get("primary_text"),
                        "headline": var.get("headline"),
                        "description": var.get("description"),
                    }, on_conflict="campaign_id,concept_name,sub_group_name,variation_number").execute()
                    variation_count += 1

                # Ad name mappings
                # Pipeline creates ads as "concept/sub_group/filename"
                for filename in images:
                    ad_name = f"{concept_name}/{sg_name}/{filename}"
                    media_type = "video" if any(
                        filename.lower().endswith(ext) for ext in (".mp4", ".mov", ".avi", ".mkv")
                    ) else "image"

                    sb.table("ad_mappings").upsert({
                        "campaign_id": campaign_id,
                        "ad_name": ad_name,
                        "concept_name": concept_name,
                        "sub_group_name": sg_name,
                        "filename": filename,
                        "media_type": media_type,
                    }, on_conflict="campaign_id,ad_name").execute()
                    mapping_count += 1

    logger.info(f"  Published {variation_count} copy variations")
    logger.info(f"  Published {mapping_count} ad mappings")

    # Also handle video classifications → ad mappings
    video_classifications = load_json(VIDEO_CLASSIFICATIONS_JSON)
    if video_classifications and isinstance(video_classifications, list):
        for vc in video_classifications:
            filename = vc["image_filename"]
            concept_name = vc["creative_concept"]
            # Videos are uploaded individually, ad name = "concept/filename/filename"
            ad_name = f"{concept_name}/{filename}/{filename}"
            sb.table("ad_mappings").upsert({
                "campaign_id": campaign_id,
                "ad_name": ad_name,
                "concept_name": concept_name,
                "sub_group_name": filename,  # videos use filename as sub_group
                "filename": filename,
                "media_type": "video",
            }, on_conflict="campaign_id,ad_name").execute()
            mapping_count += 1

    logger.info(f"Done! Published all pipeline data for campaign {campaign_id}")


def main():
    parser = argparse.ArgumentParser(
        description="Publish pipeline output to Supabase for dashboard"
    )
    parser.add_argument(
        "--campaign-id",
        type=str,
        default=None,
        help="Meta campaign ID (default: latest from campaign_log.json)",
    )
    args = parser.parse_args()

    campaign_id = get_campaign_id(args.campaign_id)
    publish(campaign_id)


if __name__ == "__main__":
    main()
