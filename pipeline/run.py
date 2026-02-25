#!/usr/bin/env python3
"""
Meta Ad Copy Automation Pipeline for Spicy Cubes Dailies.

Visual-first pipeline — sub-groups creatives by visual similarity BEFORE strategic classification:
  Pass 0  — Preprocess videos: extract frames + audio transcripts (ffmpeg + faster-whisper)
  Pass 1  — Describe each image/video (visual elements, tone, awareness level)
  Pass 2  — Global visual sub-grouping: cluster ALL images by visual similarity
  Pass 2b — Discover video hook categories from video descriptions
  Pass 3  — Discover creative concept categories from image descriptions
  Pass 3b — Label each visual sub-group with a strategic concept
  Pass 3c — Classify videos into hook categories
  Pass 4  — Generate 5 copy variations per concept (shared across sub-groups)

Passes 1, 2, 3b, 3c, and 4 run API calls concurrently (controlled by MAX_CONCURRENT in config).
Each pass saves intermediate results — re-running skips completed passes automatically.

Usage:
    python -m pipeline.run                     # Full pipeline (all passes, resumes from last checkpoint)
    python -m pipeline.run --preprocess-only   # Pass 0 only: extract video frames + transcripts
    python -m pipeline.run --describe-only     # Pass 0 + 1
    python -m pipeline.run --subgroup-only     # Pass 0 + 1 + 2 (global visual sub-grouping)
    python -m pipeline.run --discover-only     # Pass 0 + 1 + 2 + 2b + 3
    python -m pipeline.run --classify-only     # Pass 0 + 1 + 2 + 2b + 3 + 3b + 3c (everything except copy)
    python -m pipeline.run --generate-copy     # Pass 4 only (uses existing sub-groups)
    python -m pipeline.run --subgroup-copy     # Generate unique copy per sub-group (default: per concept)
    python -m pipeline.run --upload            # Full pipeline + upload to Meta
    python -m pipeline.run --upload-only       # Upload existing output to Meta
    python -m pipeline.run --force             # Re-run everything from scratch (ignore checkpoints)
"""

import argparse
import asyncio
import csv
import json
import logging
import shutil
import sys
from pathlib import Path

import anthropic

from .config import (
    ANTHROPIC_API_KEY,
    INPUT_DIR,
    OUTPUT_DIR,
    OUTPUT_JSON,
    OUTPUT_CSV,
    SUPPORTED_IMAGE_EXTENSIONS,
    SUPPORTED_VIDEO_EXTENSIONS,
    VIDEO_PREPROCESSED_DIR,
    VIDEO_PREPROCESSED_JSON,
    VIDEO_CATEGORIES_JSON,
    VIDEO_CLASSIFICATIONS_JSON,
    GLOBAL_SUBGROUPS_JSON,
    SUBGROUP_LABELS_JSON,
    USE_CLIP_SUBGROUPING,
    CLIP_DISTANCE_THRESHOLD,
    CLIP_MODEL_NAME,
    CLIP_EMBEDDINGS_CACHE_DIR,
)
from .brand_context import (
    load_brand_context,
    build_describe_system,
    build_discover_system,
    build_discover_video_system,
    build_classify_system,
    build_subgroup_system,
    build_label_subgroup_system,
    build_copygen_system,
)
from .copy_generator import (
    describe_all_media,
    discover_categories,
    discover_video_categories,
    classify_all_media,
    subgroup_all_global,
    label_all_subgroups,
    generate_all_concept_copy,
    generate_all_subgroup_copy,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

CONCEPT_DIR = OUTPUT_DIR / "by_concept"
DESCRIPTIONS_JSON = OUTPUT_DIR / "descriptions.json"
CATEGORIES_JSON = OUTPUT_DIR / "categories.json"
CLASSIFICATIONS_JSON = OUTPUT_DIR / "classifications.json"
SUBGROUPS_JSON = OUTPUT_DIR / "subgroups.json"


def scan_media(input_dir: Path) -> tuple[list[Path], list[Path]]:
    """Scan input directory for supported image and video files.

    Returns (image_paths, video_paths), each sorted by name.
    """
    image_paths = sorted(
        p for p in input_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    )
    video_paths = sorted(
        p for p in input_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS
    )
    return image_paths, video_paths


def organize_into_subgroup_folders(subgroups_data: dict):
    """Copy images/videos into output/by_concept/{concept}/{sub_group}/ folders."""
    if CONCEPT_DIR.exists():
        shutil.rmtree(CONCEPT_DIR)

    for concept, sgs in subgroups_data.items():
        for sg in sgs:
            sg_folder = CONCEPT_DIR / concept / sg["sub_group_name"]
            sg_folder.mkdir(parents=True, exist_ok=True)

            for img in sg["images"]:
                filename = img["image_filename"]
                # For videos, copy the original video file; for images, copy the image
                if img.get("media_type") == "video":
                    src = INPUT_DIR / filename
                else:
                    src = Path(img["image_path"])

                if src.exists():
                    dst = sg_folder / filename
                    shutil.copy2(src, dst)

            logger.info(f"  {concept}/{sg['sub_group_name']}/  ({len(sg['images'])} items)")


def save_json(output, output_path: Path):
    """Save structured output to JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    logger.info(f"Saved JSON to {output_path}")


def load_json(path: Path):
    """Load JSON from file."""
    with open(path) as f:
        return json.load(f)


def save_csv(output: dict, output_path: Path):
    """Export a flat CSV: one row per sub-group x variation."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for concept_data in output["concepts"]:
        concept = concept_data["creative_concept"]
        for sg in concept_data.get("sub_groups", []):
            sg_name = sg["sub_group_name"]
            images = ", ".join(sg["images"])
            for i, var in enumerate(sg["variations"], 1):
                rows.append({
                    "creative_concept": concept,
                    "sub_group_name": sg_name,
                    "images": images,
                    "variation_number": i,
                    "primary_text": var["primary_text"],
                    "headline": var["headline"],
                    "description": var["description"],
                })

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "creative_concept",
            "sub_group_name",
            "images",
            "variation_number",
            "primary_text",
            "headline",
            "description",
        ])
        writer.writeheader()
        writer.writerows(rows)

    logger.info(f"Saved CSV to {output_path} ({len(rows)} rows)")


def print_summary(output: dict, meta_summary: dict | None = None):
    """Print a human-readable summary."""
    print("\n" + "=" * 60)
    print("PIPELINE SUMMARY")
    print("=" * 60)

    total_media = 0
    total_subgroups = 0
    total_variations = 0
    for c in output["concepts"]:
        for sg in c.get("sub_groups", []):
            total_media += len(sg["images"])
            total_subgroups += 1
            total_variations += len(sg["variations"])

    # Count images vs videos from descriptions if available
    n_images = sum(1 for d in output.get("descriptions", []) if d.get("media_type") != "video")
    n_videos = sum(1 for d in output.get("descriptions", []) if d.get("media_type") == "video")
    if n_images or n_videos:
        print(f"\nMedia processed: {n_images} image(s) + {n_videos} video(s) = {n_images + n_videos} total")
    else:
        print(f"\nMedia processed: {total_media}")
    print(f"Concept groups: {len(output['concepts'])}")
    print(f"Visual sub-groups: {total_subgroups}")
    print(f"Total copy variations: {total_variations}")

    if output.get("categories"):
        print(f"\nDiscovered categories:")
        for cat in output["categories"]:
            print(f"  {cat['display_name']} ({cat['name']})")
            print(f"    Schwartz: {cat['schwartz_sophistication']}")
            print(f"    Belief:   {cat['belief_mapping']}")

    print(f"\nOrganized folders: output/by_concept/")
    for concept_data in output["concepts"]:
        concept = concept_data["creative_concept"]
        for sg in concept_data.get("sub_groups", []):
            sg_name = sg["sub_group_name"]
            n_items = len(sg["images"])
            n_vars = len(sg["variations"])
            print(f"  {concept}/{sg_name} — {n_items} creative(s), {n_vars} copy variation(s)")
            for img in sg["images"]:
                print(f"    {img}")

    if total_variations > 0:
        print("\nSample copy (first variation per sub-group):")
        for concept_data in output["concepts"]:
            for sg in concept_data.get("sub_groups", []):
                if sg["variations"]:
                    var = sg["variations"][0]
                    print(f"\n  [{concept_data['creative_concept']}/{sg['sub_group_name']}]")
                    print(f"  Headline:    {var['headline']}")
                    print(f"  Description: {var['description']}")
                    primary = var["primary_text"]
                    print(f"  Primary:     {primary[:120]}{'...' if len(primary) > 120 else ''}")

    if meta_summary:
        print(f"\nMeta Ads Upload:")
        print(f"  Campaign: {meta_summary['campaign_name']} (ID: {meta_summary['campaign_id']})")
        print(f"  Total ads: {meta_summary['total_ads']} across {len(meta_summary['ad_sets'])} ad sets")
        for concept, info in meta_summary["ad_sets"].items():
            print(f"  Ad Set '{concept}': {info['ad_count']} ads")
    elif total_variations > 0:
        print("\nMeta upload: skipped (use --upload to enable)")

    print("=" * 60 + "\n")


def _init_client() -> anthropic.AsyncAnthropic:
    """Initialize the async Anthropic client."""
    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set. Add it to .env and try again.")
        sys.exit(1)
    return anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)


def _load_media() -> tuple[list[Path], list[Path]]:
    """Scan input directory for images and videos."""
    logger.info(f"Scanning {INPUT_DIR} for media...")
    image_paths, video_paths = scan_media(INPUT_DIR)
    if not image_paths and not video_paths:
        logger.error(f"No media found in {INPUT_DIR}. Add image/video files and try again.")
        sys.exit(1)
    logger.info(f"Found {len(image_paths)} image(s) and {len(video_paths)} video(s)")
    return image_paths, video_paths


def _load_video_infos(force: bool = False) -> list[dict]:
    """Load preprocessed video info from checkpoint, or return empty list."""
    if not force and VIDEO_PREPROCESSED_JSON.exists():
        video_infos = load_json(VIDEO_PREPROCESSED_JSON)
        logger.info(f"Loaded {len(video_infos)} preprocessed video(s) from cache")
        return video_infos
    return []


def _build_filename_map(descriptions: list[dict]) -> dict[str, str]:
    """Build a mapping from visual_path (image_path) -> original filename.

    For videos, image_path is the thumbnail frame but image_filename is the original video name.
    For images, these are consistent so the map only includes entries where they differ.
    """
    fmap = {}
    for d in descriptions:
        visual_path = d.get("image_path", "")
        original_name = d.get("image_filename", "")
        if original_name and visual_path and Path(visual_path).name != original_name:
            fmap[visual_path] = original_name
    return fmap


def _build_media_items_for_classify(
    image_paths: list[Path],
    descriptions: list[dict],
    video_infos: list[dict],
) -> list[dict]:
    """Build unified media item list for classification.

    Each item has: visual_path, original_filename, media_type, transcript.
    """
    # Build lookup from description filename -> description
    desc_lookup = {d["image_filename"]: d for d in descriptions}

    # Build video transcript lookup
    video_transcript = {vi["video_filename"]: vi.get("transcript", "") for vi in video_infos}

    items = []
    # Images
    for img_path in image_paths:
        items.append({
            "visual_path": str(img_path),
            "original_filename": img_path.name,
            "media_type": "image",
            "transcript": "",
        })

    # Videos (use thumbnail from descriptions)
    for vi in video_infos:
        vname = vi["video_filename"]
        desc = desc_lookup.get(vname)
        visual_path = desc["image_path"] if desc else vi["frame_paths"][0]
        items.append({
            "visual_path": visual_path,
            "original_filename": vname,
            "media_type": "video",
            "transcript": video_transcript.get(vname, ""),
        })

    return items


# ── Pass 0: Video Preprocessing ─────────────────────────────────────────

def run_preprocess_videos(video_paths: list[Path], force: bool = False) -> list[dict]:
    """Pass 0: Preprocess all videos (extract frames + transcripts). Skips if cached."""
    if not video_paths:
        logger.info("Pass 0: No videos to preprocess")
        return []

    if not force and VIDEO_PREPROCESSED_JSON.exists():
        video_infos = load_json(VIDEO_PREPROCESSED_JSON)
        logger.info(f"Pass 0: Loaded {len(video_infos)} cached video preprocessed results")
        return video_infos

    from .video_preprocessor import preprocess_all_videos

    logger.info(f"Pass 0: Preprocessing {len(video_paths)} video(s) (frames + transcripts)...")
    video_infos = preprocess_all_videos(video_paths, VIDEO_PREPROCESSED_DIR)

    save_json(video_infos, VIDEO_PREPROCESSED_JSON)
    return video_infos


# ── Pass 1: Describe ──────────────────────────────────────────────────────

async def run_describe(
    client: anthropic.AsyncAnthropic,
    image_paths: list[Path],
    video_infos: list[dict],
    force: bool = False,
) -> list[dict]:
    """Pass 1: Describe all images and videos (concurrent). Skips if descriptions.json exists."""
    if not force and DESCRIPTIONS_JSON.exists():
        descriptions = load_json(DESCRIPTIONS_JSON)
        logger.info(f"Pass 1: Loaded {len(descriptions)} cached descriptions from {DESCRIPTIONS_JSON}")
        return descriptions

    logger.info("Loading brand context from PDFs...")
    brand_context = load_brand_context()
    system_messages = build_describe_system(brand_context)
    logger.info(f"Brand context loaded ({len(brand_context):,} chars)")

    total = len(image_paths) + len(video_infos)
    logger.info(f"Pass 1: Describing {total} media items ({len(image_paths)} images, {len(video_infos)} videos)...")
    descriptions = await describe_all_media(client, system_messages, image_paths, video_infos)

    save_json(descriptions, DESCRIPTIONS_JSON)
    return descriptions


# ── Pass 2: Global Visual Sub-grouping ────────────────────────────────────

async def run_global_subgroup(
    client: anthropic.AsyncAnthropic,
    image_paths: list[Path],
    descriptions: list[dict],
    force: bool = False,
) -> list[dict]:
    """Pass 2: Sub-group ALL images globally by visual similarity.

    Returns a flat list of sub-group dicts, each with
    'sub_group_name', 'reasoning', and 'images' (list of {image_filename, image_path, media_type}).

    Uses CLIP embeddings + agglomerative clustering when USE_CLIP_SUBGROUPING is True,
    otherwise falls back to Claude vision API batching.
    """
    if not force and GLOBAL_SUBGROUPS_JSON.exists():
        global_subgroups = load_json(GLOBAL_SUBGROUPS_JSON)
        total_items = sum(len(sg["images"]) for sg in global_subgroups)
        logger.info(f"Pass 2: Loaded {len(global_subgroups)} cached global sub-groups ({total_items} images)")
        return global_subgroups

    if not image_paths:
        logger.info("Pass 2: No images to sub-group")
        return []

    # Build filename -> description lookup for enrichment
    desc_lookup = {d["image_filename"]: d for d in descriptions if d.get("media_type") != "video"}

    if USE_CLIP_SUBGROUPING:
        # ── CLIP path: local embeddings + agglomerative clustering ──
        from .image_embedder import cluster_images_by_visual_similarity

        logger.info(f"Pass 2: CLIP visual sub-grouping of {len(image_paths)} images...")
        clip_results = cluster_images_by_visual_similarity(
            image_paths=image_paths,
            descriptions=descriptions,
            cache_dir=CLIP_EMBEDDINGS_CACHE_DIR,
            model_name=CLIP_MODEL_NAME,
            distance_threshold=CLIP_DISTANCE_THRESHOLD,
        )

        # Convert CLIP results to enriched sub-group format
        global_subgroups = []
        for sg in clip_results:
            images = []
            for fname in sg["image_filenames"]:
                desc = desc_lookup.get(fname)
                if desc:
                    images.append({
                        "image_filename": fname,
                        "image_path": desc["image_path"],
                        "media_type": "image",
                    })
                else:
                    matching = [p for p in image_paths if p.name == fname]
                    if matching:
                        images.append({
                            "image_filename": fname,
                            "image_path": str(matching[0]),
                            "media_type": "image",
                        })
                    else:
                        logger.warning(f"  Sub-group '{sg['sub_group_name']}' references unknown: {fname}")

            global_subgroups.append({
                "sub_group_name": sg["sub_group_name"],
                "reasoning": sg["reasoning"],
                "images": images,
            })
    else:
        # ── Legacy Claude vision path ──
        system_messages = build_subgroup_system()

        logger.info(f"Pass 2: Global visual sub-grouping of {len(image_paths)} images (Claude vision)...")
        result = await subgroup_all_global(client, system_messages, image_paths)

        global_subgroups = []
        for sg in result.sub_groups:
            images = []
            for fname in sg.image_filenames:
                desc = desc_lookup.get(fname)
                if desc:
                    images.append({
                        "image_filename": fname,
                        "image_path": desc["image_path"],
                        "media_type": "image",
                    })
                else:
                    matching = [p for p in image_paths if p.name == fname]
                    if matching:
                        images.append({
                            "image_filename": fname,
                            "image_path": str(matching[0]),
                            "media_type": "image",
                        })
                    else:
                        logger.warning(f"  Sub-group '{sg.sub_group_name}' references unknown: {fname}")

            global_subgroups.append({
                "sub_group_name": sg.sub_group_name,
                "reasoning": sg.reasoning,
                "images": images,
            })

    # Deduplicate: if an image was assigned to multiple sub-groups, keep first occurrence
    seen = set()
    for sg_item in global_subgroups:
        deduped = []
        for img in sg_item["images"]:
            if img["image_filename"] not in seen:
                seen.add(img["image_filename"])
                deduped.append(img)
            else:
                logger.warning(f"  Duplicate '{img['image_filename']}' in '{sg_item['sub_group_name']}', removing")
        sg_item["images"] = deduped

    # Remove empty sub-groups after dedup
    global_subgroups = [sg_item for sg_item in global_subgroups if sg_item["images"]]

    # Validate all images are accounted for
    assigned = set()
    for sg_item in global_subgroups:
        for img in sg_item["images"]:
            assigned.add(img["image_filename"])
    expected = {p.name for p in image_paths}
    missing = expected - assigned
    if missing:
        logger.warning(f"  {len(missing)} images not assigned to any sub-group: {missing}")
        catch_all_images = []
        for fname in sorted(missing):
            desc = desc_lookup.get(fname)
            if desc:
                catch_all_images.append({
                    "image_filename": fname,
                    "image_path": desc["image_path"],
                    "media_type": "image",
                })
            else:
                matching = [p for p in image_paths if p.name == fname]
                if matching:
                    catch_all_images.append({
                        "image_filename": fname,
                        "image_path": str(matching[0]),
                        "media_type": "image",
                    })
        if catch_all_images:
            global_subgroups.append({
                "sub_group_name": "unassigned",
                "reasoning": "Images not assigned during visual clustering",
                "images": catch_all_images,
            })

    save_json(global_subgroups, GLOBAL_SUBGROUPS_JSON)
    total_items = sum(len(sg_item["images"]) for sg_item in global_subgroups)
    logger.info(f"Pass 2: {len(global_subgroups)} global sub-groups covering {total_items} images")

    return global_subgroups


# ── Pass 2b: Discover Video Hook Categories ──────────────────────────────

async def run_discover_video(
    client: anthropic.AsyncAnthropic,
    descriptions: list[dict],
    video_infos: list[dict],
    force: bool = False,
) -> dict:
    """Pass 2b: Discover video hook categories from VIDEO descriptions only."""
    if not force and VIDEO_CATEGORIES_JSON.exists():
        categories_output = load_json(VIDEO_CATEGORIES_JSON)
        logger.info(f"Pass 2b: Loaded {len(categories_output['categories'])} cached video categories from {VIDEO_CATEGORIES_JSON}")
        return categories_output

    if not video_infos:
        logger.info("Pass 2b: No videos to discover categories for")
        return {"reasoning": "", "categories": []}

    video_descriptions = [d for d in descriptions if d.get("media_type") == "video"]

    logger.info("Loading brand context from PDFs...")
    brand_context = load_brand_context()
    system_messages = build_discover_video_system(brand_context)

    logger.info(f"Pass 2b: Discovering video hook categories from {len(video_descriptions)} videos (streaming)...")
    result = await discover_video_categories(client, system_messages, video_descriptions, video_infos)

    categories_output = {
        "reasoning": result.reasoning,
        "categories": [cat.model_dump() for cat in result.categories],
    }

    save_json(categories_output, VIDEO_CATEGORIES_JSON)

    logger.info(f"Discovered {len(result.categories)} video hook categories:")
    for cat in result.categories:
        logger.info(f"  {cat.display_name} ({cat.name}) — {len(cat.example_images)} items")

    return categories_output


# ── Pass 3: Discover Image Categories ────────────────────────────────────

async def run_discover(client: anthropic.AsyncAnthropic, descriptions: list[dict], force: bool = False) -> dict:
    """Pass 3: Discover categories from IMAGE descriptions only. Skips if categories.json exists."""
    if not force and CATEGORIES_JSON.exists():
        categories_output = load_json(CATEGORIES_JSON)
        logger.info(f"Pass 3: Loaded {len(categories_output['categories'])} cached image categories from {CATEGORIES_JSON}")
        return categories_output

    image_descriptions = [d for d in descriptions if d.get("media_type") != "video"]

    logger.info("Loading brand context from PDFs...")
    brand_context = load_brand_context()
    system_messages = build_discover_system(brand_context)

    logger.info(f"Pass 3: Discovering image concept categories from {len(image_descriptions)} images (streaming)...")
    result = await discover_categories(client, system_messages, image_descriptions)

    categories_output = {
        "reasoning": result.reasoning,
        "categories": [cat.model_dump() for cat in result.categories],
    }

    save_json(categories_output, CATEGORIES_JSON)

    logger.info(f"Discovered {len(result.categories)} image categories:")
    for cat in result.categories:
        logger.info(f"  {cat.display_name} ({cat.name}) — {len(cat.example_images)} items")

    return categories_output


# ── Pass 3b: Label Sub-groups with Concepts ──────────────────────────────

async def run_label_subgroups(
    client: anthropic.AsyncAnthropic,
    global_subgroups: list[dict],
    categories_output: dict,
    force: bool = False,
) -> list[dict]:
    """Pass 3b: Label each visual sub-group with a strategic concept category.

    Returns list of {sub_group_name, creative_concept, concept_reasoning}.
    """
    if not force and SUBGROUP_LABELS_JSON.exists():
        labels = load_json(SUBGROUP_LABELS_JSON)
        logger.info(f"Pass 3b: Loaded {len(labels)} cached sub-group labels")
        return labels

    brand_context = load_brand_context()
    system_messages = build_label_subgroup_system(brand_context, categories_output["categories"])
    category_names = [cat["name"] for cat in categories_output["categories"]]

    logger.info(f"Pass 3b: Labeling {len(global_subgroups)} sub-groups into {len(category_names)} concepts...")
    labels = await label_all_subgroups(client, system_messages, global_subgroups, category_names)

    save_json(labels, SUBGROUP_LABELS_JSON)

    for label in labels:
        logger.info(f"  {label['sub_group_name']} -> {label['creative_concept']}")

    return labels


# ── Pass 3c: Classify Videos ────────────────────────────────────────────

async def run_classify_videos(
    client: anthropic.AsyncAnthropic,
    video_categories_output: dict,
    descriptions: list[dict],
    video_infos: list[dict],
    force: bool = False,
) -> list[dict]:
    """Pass 3c: Classify videos individually into video hook categories."""
    if not force and VIDEO_CLASSIFICATIONS_JSON.exists():
        video_cls = load_json(VIDEO_CLASSIFICATIONS_JSON)
        logger.info(f"Pass 3c: Loaded {len(video_cls)} cached video classifications")
        return video_cls

    if not video_infos:
        logger.info("Pass 3c: No videos to classify")
        return []

    video_cats = video_categories_output.get("categories", [])
    if not video_cats:
        logger.warning("Pass 3c: No video categories discovered, skipping")
        return []

    brand_context = load_brand_context()
    video_system = build_classify_system(brand_context, video_cats)
    video_category_names = [cat["name"] for cat in video_cats]

    video_items = _build_media_items_for_classify([], descriptions, video_infos)
    logger.info(f"Pass 3c: Classifying {len(video_items)} videos into video hook categories...")
    video_cls = await classify_all_media(client, video_system, video_items, video_category_names)

    save_json(video_cls, VIDEO_CLASSIFICATIONS_JSON)
    return video_cls


# ── Assemble final subgroups_data ────────────────────────────────────────

def _assemble_subgroups_data(
    global_subgroups: list[dict],
    labels: list[dict],
    video_cls: list[dict],
) -> dict:
    """Combine image sub-groups (with labels) + video classifications into final structure.

    Returns dict mapping concept -> list of sub-group dicts.
    """
    label_lookup = {l["sub_group_name"]: l["creative_concept"] for l in labels}

    subgroups_data: dict[str, list[dict]] = {}
    for sg in global_subgroups:
        concept = label_lookup.get(sg["sub_group_name"], "uncategorized")
        subgroups_data.setdefault(concept, []).append(sg)

    # Each video becomes its own sub-group entry within its hook concept
    for vcls in video_cls:
        concept = vcls["creative_concept"]
        fname = vcls["image_filename"]
        sg = {
            "sub_group_name": fname.replace(".", "_"),
            "reasoning": vcls.get("concept_reasoning", ""),
            "images": [{
                "image_filename": fname,
                "image_path": vcls["image_path"],
                "media_type": "video",
            }],
        }
        subgroups_data.setdefault(concept, []).append(sg)

    return subgroups_data


# ── Pass 4: Copy Generation ──────────────────────────────────────────────

async def run_generation(
    client: anthropic.AsyncAnthropic,
    subgroups_data: dict,
    categories_output: dict,
    video_categories_output: dict | None = None,
    per_subgroup: bool = False,
) -> dict:
    """Pass 4: Generate copy (concurrent).

    Args:
        per_subgroup: If True, generate unique copy per sub-group.
                      If False (default), generate copy per concept and share across sub-groups.
    """
    # Merge image + video categories for copy gen context
    all_categories = list(categories_output["categories"])
    if video_categories_output and video_categories_output.get("categories"):
        all_categories.extend(video_categories_output["categories"])

    logger.info("Loading brand context from PDFs...")
    brand_context = load_brand_context()
    system_messages = build_copygen_system(brand_context, all_categories)

    cat_lookup = {cat["name"]: cat for cat in all_categories}

    if per_subgroup:
        total_sg = sum(len(sgs) for sgs in subgroups_data.values())
        logger.info(f"Pass 4: Generating copy for {total_sg} sub-groups across {len(subgroups_data)} concepts...")
        concept_results = await generate_all_subgroup_copy(client, system_messages, subgroups_data, cat_lookup)
    else:
        # Generate copy at concept level, then distribute to sub-groups
        # Build concept-level groups (flatten sub-group images into one list per concept)
        groups: dict[str, list[dict]] = {}
        for concept, sgs in subgroups_data.items():
            items = []
            for sg in sgs:
                items.extend(sg["images"])
            groups[concept] = items

        logger.info(f"Pass 4: Generating copy for {len(groups)} concepts (shared across sub-groups)...")
        raw_results = await generate_all_concept_copy(client, system_messages, groups, cat_lookup)

        # Reshape: attach concept-level variations to each sub-group
        concept_variations = {r["creative_concept"]: r["variations"] for r in raw_results}
        concept_results = []
        for concept, sgs in subgroups_data.items():
            variations = concept_variations.get(concept, [])
            concept_results.append({
                "creative_concept": concept,
                "sub_groups": [
                    {
                        "sub_group_name": sg["sub_group_name"],
                        "images": [img["image_filename"] for img in sg["images"]],
                        "variations": variations,
                    }
                    for sg in sgs
                ],
            })

    output = {
        "categories": all_categories,
        "category_reasoning": categories_output["reasoning"],
        "concepts": list(concept_results),
    }

    save_json(output, OUTPUT_JSON)
    save_csv(output, OUTPUT_CSV)

    return output


# ── Full Pipeline ─────────────────────────────────────────────────────────

async def run_full_pipeline(
    client: anthropic.AsyncAnthropic,
    force: bool = False,
    per_subgroup: bool = False,
) -> dict:
    """Run all passes end-to-end, resuming from last checkpoint."""
    image_paths, video_paths = _load_media()
    video_infos = run_preprocess_videos(video_paths, force=force)
    descriptions = await run_describe(client, image_paths, video_infos, force=force)

    # Pass 2: Global visual sub-grouping (images only)
    global_subgroups = await run_global_subgroup(client, image_paths, descriptions, force=force)

    # Pass 2b + 3: Discover categories
    video_categories_output = await run_discover_video(client, descriptions, video_infos, force=force)
    categories_output = await run_discover(client, descriptions, force=force)

    # Pass 3b + 3c: Label sub-groups + classify videos
    labels = await run_label_subgroups(client, global_subgroups, categories_output, force=force)
    video_cls = await run_classify_videos(
        client, video_categories_output, descriptions, video_infos, force=force,
    )

    # Assemble final structure
    subgroups_data = _assemble_subgroups_data(global_subgroups, labels, video_cls)
    save_json(subgroups_data, SUBGROUPS_JSON)

    logger.info("Organizing media into sub-group folders...")
    organize_into_subgroup_folders(subgroups_data)

    # Log summary
    for concept, sgs in subgroups_data.items():
        total = sum(len(sg["images"]) for sg in sgs)
        logger.info(f"  {concept}: {len(sgs)} sub-groups, {total} items")

    # Pass 4: Copy generation
    output = await run_generation(
        client, subgroups_data, categories_output, video_categories_output, per_subgroup=per_subgroup,
    )
    return output


# ── Meta Upload ───────────────────────────────────────────────────────────

def _get_media_type_lookup(descriptions_path: Path, subgroups_path: Path) -> dict[str, str]:
    """Build a filename -> media_type lookup from available data."""
    lookup = {}

    # Try descriptions first
    if descriptions_path.exists():
        for d in load_json(descriptions_path):
            lookup[d["image_filename"]] = d.get("media_type", "image")

    # Subgroups may also carry media_type
    if subgroups_path.exists():
        for sgs in load_json(subgroups_path).values():
            for sg in sgs:
                for img in sg.get("images", []):
                    if "media_type" in img:
                        lookup[img["image_filename"]] = img["media_type"]

    return lookup


def run_upload(output: dict) -> dict:
    """Run the Meta upload pipeline (sync — uses facebook-business SDK).

    Creates 1 campaign -> 1 ad set/concept -> 1 ad per media item.
    Image ads use AdImage + link_data; video ads use AdVideo + video_data.
    """
    from .meta_uploader import upload_to_meta
    from .config import META_ACCESS_TOKEN

    if not META_ACCESS_TOKEN:
        logger.error("META_ACCESS_TOKEN not set. Add it to .env and try again.")
        sys.exit(1)

    # Build media_type lookup
    media_type_lookup = _get_media_type_lookup(DESCRIPTIONS_JSON, SUBGROUPS_JSON)

    # Build results in the sub-group-aware format
    results = []
    for concept_data in output["concepts"]:
        concept = concept_data["creative_concept"]
        for sg in concept_data["sub_groups"]:
            images = []
            for fname in sg["images"]:
                mt = media_type_lookup.get(fname, "image")
                images.append({
                    "image_filename": fname,
                    "image_path": str(INPUT_DIR / fname),
                    "media_type": mt,
                })
            results.append({
                "creative_concept": concept,
                "sub_group_name": sg["sub_group_name"],
                "images": images,
                "variations": sg["variations"],
            })

    logger.info("Starting Meta Ads upload...")
    summary = upload_to_meta(results)
    return summary


# ── Main (single event loop) ─────────────────────────────────────────────

async def async_main(args):
    """Single async entry point — one event loop, one client."""
    force = args.force

    # Publish-only: just push existing data to Supabase
    if args.publish_only:
        from .publisher import publish, get_campaign_id
        campaign_id = get_campaign_id(None)
        publish(campaign_id)
        return

    # Pass 0: preprocess videos (sync, no API client needed)
    if args.preprocess_only:
        _image_paths, video_paths = _load_media()
        video_infos = run_preprocess_videos(video_paths, force=force)
        print(f"\nPreprocessed {len(video_infos)} video(s). Saved to {VIDEO_PREPROCESSED_JSON}")
        print("Next step: python -m pipeline.run --describe-only")
        return

    client = _init_client()
    meta_summary = None

    try:
        if args.describe_only:
            image_paths, video_paths = _load_media()
            video_infos = run_preprocess_videos(video_paths, force=force)
            descriptions = await run_describe(client, image_paths, video_infos, force=force)
            print(f"\nDescribed {len(descriptions)} media items. Saved to {DESCRIPTIONS_JSON}")
            print("Next step: python -m pipeline.run --subgroup-only")
            return

        elif args.subgroup_only:
            image_paths, video_paths = _load_media()
            video_infos = run_preprocess_videos(video_paths, force=force)
            descriptions = await run_describe(client, image_paths, video_infos, force=force)
            global_subgroups = await run_global_subgroup(client, image_paths, descriptions, force=force)
            total_items = sum(len(sg["images"]) for sg in global_subgroups)
            print(f"\nCreated {len(global_subgroups)} global visual sub-groups covering {total_items} images")
            print("Next step: python -m pipeline.run --discover-only")
            return

        elif args.discover_only:
            image_paths, video_paths = _load_media()
            video_infos = run_preprocess_videos(video_paths, force=force)
            descriptions = await run_describe(client, image_paths, video_infos, force=force)
            global_subgroups = await run_global_subgroup(client, image_paths, descriptions, force=force)
            categories_output = await run_discover(client, descriptions, force=force)
            video_categories_output = await run_discover_video(client, descriptions, video_infos, force=force)
            all_cats = list(categories_output["categories"]) + video_categories_output.get("categories", [])
            output = {"categories": all_cats, "concepts": []}
            print(f"\nDiscovered {len(categories_output['categories'])} image + {len(video_categories_output.get('categories', []))} video categories")
            print("Next step: python -m pipeline.run --classify-only")
            print_summary(output)
            return

        elif args.classify_only:
            image_paths, video_paths = _load_media()
            video_infos = run_preprocess_videos(video_paths, force=force)
            descriptions = await run_describe(client, image_paths, video_infos, force=force)
            global_subgroups = await run_global_subgroup(client, image_paths, descriptions, force=force)
            categories_output = await run_discover(client, descriptions, force=force)
            video_categories_output = await run_discover_video(client, descriptions, video_infos, force=force)
            labels = await run_label_subgroups(client, global_subgroups, categories_output, force=force)
            video_cls = await run_classify_videos(
                client, video_categories_output, descriptions, video_infos, force=force,
            )

            subgroups_data = _assemble_subgroups_data(global_subgroups, labels, video_cls)
            save_json(subgroups_data, SUBGROUPS_JSON)

            logger.info("Organizing media into sub-group folders...")
            organize_into_subgroup_folders(subgroups_data)

            # Build summary output
            all_cats = list(categories_output["categories"]) + video_categories_output.get("categories", [])
            output = {
                "categories": all_cats,
                "concepts": [
                    {
                        "creative_concept": concept,
                        "sub_groups": [
                            {
                                "sub_group_name": sg["sub_group_name"],
                                "images": [img["image_filename"] for img in sg["images"]],
                                "variations": [],
                            }
                            for sg in sgs
                        ],
                    }
                    for concept, sgs in subgroups_data.items()
                ],
            }
            print_summary(output)
            print("Next step: python -m pipeline.run --generate-copy")
            return

        elif args.generate_copy:
            # Load from checkpoints
            if not SUBGROUPS_JSON.exists():
                logger.error(f"No sub-groups found at {SUBGROUPS_JSON}. Run --classify-only first.")
                sys.exit(1)
            if not CATEGORIES_JSON.exists():
                logger.error(f"No categories found at {CATEGORIES_JSON}. Run --discover-only first.")
                sys.exit(1)
            subgroups_data = load_json(SUBGROUPS_JSON)
            categories_output = load_json(CATEGORIES_JSON)
            video_categories_output = load_json(VIDEO_CATEGORIES_JSON) if VIDEO_CATEGORIES_JSON.exists() else {"categories": []}
            output = await run_generation(
                client, subgroups_data, categories_output, video_categories_output,
                per_subgroup=args.subgroup_copy,
            )
            if args.upload:
                meta_summary = run_upload(output)

        elif args.upload_only:
            if not OUTPUT_JSON.exists():
                logger.error(f"No existing output at {OUTPUT_JSON}. Run generation first.")
                sys.exit(1)
            output = load_json(OUTPUT_JSON)
            logger.info(f"Loaded {len(output['concepts'])} concept groups from {OUTPUT_JSON}")
            meta_summary = run_upload(output)

        else:
            # Default: full pipeline (all passes, resumes from checkpoints)
            output = await run_full_pipeline(client, force=force, per_subgroup=args.subgroup_copy)
            if args.upload:
                meta_summary = run_upload(output)

        print_summary(output, meta_summary)

        # Publish to Supabase if requested
        if args.publish:
            from .publisher import publish, get_campaign_id
            campaign_id = get_campaign_id(None)
            publish(campaign_id)

    finally:
        await client.close()


def main():
    parser = argparse.ArgumentParser(
        description="Meta Ad Copy Automation Pipeline for Spicy Cubes Dailies"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--preprocess-only",
        action="store_true",
        help="Pass 0 only: extract video frames + audio transcripts",
    )
    group.add_argument(
        "--describe-only",
        action="store_true",
        help="Pass 0 + 1: preprocess videos and describe all media",
    )
    group.add_argument(
        "--subgroup-only",
        action="store_true",
        help="Pass 0 + 1 + 2: describe + global visual sub-grouping",
    )
    group.add_argument(
        "--discover-only",
        action="store_true",
        help="Pass 0 + 1 + 2 + 2b + 3: through category discovery",
    )
    group.add_argument(
        "--classify-only",
        action="store_true",
        help="Pass 0 + 1 + 2 + 2b + 3 + 3b + 3c: everything except copy generation",
    )
    group.add_argument(
        "--generate-copy",
        action="store_true",
        help="Pass 4 only: generate copy using existing sub-groups + categories",
    )
    group.add_argument(
        "--upload-only",
        action="store_true",
        help="Skip generation, upload existing output to Meta",
    )
    group.add_argument(
        "--publish-only",
        action="store_true",
        help="Publish existing output to Supabase for dashboard (no generation)",
    )
    parser.add_argument(
        "--subgroup-copy",
        action="store_true",
        help="Generate unique copy per visual sub-group (default: shared copy per concept)",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload generated ads to Meta after copy generation",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run all passes from scratch, ignoring cached checkpoints",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish pipeline output to Supabase for dashboard (runs after all passes)",
    )
    args = parser.parse_args()

    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
