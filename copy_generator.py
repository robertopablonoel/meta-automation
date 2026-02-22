import asyncio
import base64
import json
import logging
import time
from pathlib import Path

import anthropic

from config import MODEL_NAME, VARIATIONS_PER_CONCEPT, MAX_CONCURRENT
from models import (
    ImageDescription,
    CategoryDiscoveryResult,
    ImageClassification,
    ConceptSubGroupResult,
    ConceptCopyResult,
)

logger = logging.getLogger(__name__)


def _fix_schema_for_api(schema: dict) -> dict:
    """Recursively add additionalProperties: false to all object types in a JSON schema.

    The Anthropic structured output API requires this on every object.
    Pydantic's model_json_schema() doesn't include it by default.
    """
    schema = schema.copy()

    # Process $defs (Pydantic puts nested model schemas here)
    if "$defs" in schema:
        schema["$defs"] = {
            k: _fix_schema_for_api(v) for k, v in schema["$defs"].items()
        }

    if schema.get("type") == "object":
        schema["additionalProperties"] = False
        if "properties" in schema:
            schema["properties"] = {
                k: _fix_schema_for_api(v) for k, v in schema["properties"].items()
            }

    # Handle arrays with object items
    if schema.get("type") == "array" and "items" in schema:
        schema["items"] = _fix_schema_for_api(schema["items"])

    # Handle anyOf / allOf / oneOf
    for key in ("anyOf", "allOf", "oneOf"):
        if key in schema:
            schema[key] = [_fix_schema_for_api(s) for s in schema[key]]

    return schema

# Map file extensions to MIME types
MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

# Max images to include in the concept copy generation call
MAX_CONCEPT_IMAGES = 6


def _encode_image(image_path: Path) -> tuple[str, str]:
    """Read an image file and return (base64_data, media_type)."""
    suffix = image_path.suffix.lower()
    media_type = MIME_TYPES.get(suffix, "image/jpeg")
    with open(image_path, "rb") as f:
        data = base64.standard_b64encode(f.read()).decode("utf-8")
    return data, media_type


async def _async_api_call_with_retry(fn, *, label: str, max_retries: int = 5, base_delay: float = 2.0):
    """Wrap an async API call with exponential backoff retry on rate limits / 5xx / connection errors."""
    last_exception = None
    for attempt in range(max_retries):
        try:
            return await fn()
        except anthropic.RateLimitError as e:
            last_exception = e
            delay = base_delay * (2 ** attempt)
            logger.warning(f"  Rate limited ({label}), retry {attempt + 1}/{max_retries} in {delay:.1f}s")
            await asyncio.sleep(delay)
        except anthropic.APIConnectionError as e:
            last_exception = e
            delay = base_delay * (2 ** attempt)
            logger.warning(f"  Connection error ({label}), retry {attempt + 1}/{max_retries} in {delay:.1f}s")
            await asyncio.sleep(delay)
        except anthropic.APIStatusError as e:
            if e.status_code >= 500:
                last_exception = e
                delay = base_delay * (2 ** attempt)
                logger.warning(f"  Server error ({label}), retry {attempt + 1}/{max_retries} in {delay:.1f}s")
                await asyncio.sleep(delay)
            else:
                raise
    raise last_exception


def _log_usage(label: str, usage):
    """Log token usage and cache stats."""
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
    logger.info(
        f"  [{label}] tokens: input={usage.input_tokens}, "
        f"output={usage.output_tokens}, "
        f"cache_read={cache_read}, cache_create={cache_create}"
    )


# ── Pass 1: Image Description ─────────────────────────────────────────────


async def describe_image(
    client: anthropic.AsyncAnthropic,
    system_messages: list[dict],
    image_path: Path,
    semaphore: asyncio.Semaphore,
    index: int,
    total: int,
) -> dict:
    """Describe a single image for downstream category discovery."""
    async with semaphore:
        logger.info(f"Describing image {index}/{total}: {image_path.name}")
        image_data, media_type = _encode_image(image_path)

        user_message = {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": image_data,
                    },
                },
                {
                    "type": "text",
                    "text": (
                        f"Describe this ad creative image ({image_path.name}).\n\n"
                        f"Provide your analysis of the visual elements, emotional tone, "
                        f"implied message, and target awareness level."
                    ),
                },
            ],
        }

        async def call():
            return await client.messages.parse(
                model=MODEL_NAME,
                max_tokens=1024,
                system=system_messages,
                messages=[user_message],
                output_format=ImageDescription,
            )

        response = await _async_api_call_with_retry(call, label=f"describe:{image_path.name}")
        _log_usage(f"describe:{image_path.name}", response.usage)
        desc = response.parsed_output

        logger.info(f"  -> {image_path.name}: awareness={desc.target_awareness_level}, tone={desc.emotional_tone}")

        return {
            "image_filename": image_path.name,
            "image_path": str(image_path),
            "media_type": "image",
            "visual_elements": desc.visual_elements,
            "emotional_tone": desc.emotional_tone,
            "implied_message": desc.implied_message,
            "target_awareness_level": desc.target_awareness_level,
            "transcript_summary": "",
        }


async def describe_all_images(
    client: anthropic.AsyncAnthropic,
    system_messages: list[dict],
    image_paths: list[Path],
) -> list[dict]:
    """Pass 1: Describe all images concurrently."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    total = len(image_paths)

    tasks = [
        describe_image(client, system_messages, path, semaphore, i, total)
        for i, path in enumerate(image_paths, 1)
    ]

    results = await asyncio.gather(*tasks)
    # Return in original order (gather preserves order)
    return list(results)


async def describe_video(
    client: anthropic.AsyncAnthropic,
    system_messages: list[dict],
    video_info: dict,
    semaphore: asyncio.Semaphore,
    index: int,
    total: int,
) -> dict:
    """Describe a video using its extracted frames + audio transcript."""
    async with semaphore:
        video_filename = video_info["video_filename"]
        logger.info(f"Describing video {index}/{total}: {video_filename}")

        # Build content blocks: 3 frames as images + transcript as text
        content_blocks = []
        for frame_path in video_info["frame_paths"]:
            image_data, media_type = _encode_image(Path(frame_path))
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_data,
                },
            })

        transcript = video_info.get("transcript", "")
        # Truncate very long transcripts to stay within token limits
        if len(transcript) > 3000:
            transcript = transcript[:3000] + "..."

        content_blocks.append({
            "type": "text",
            "text": (
                f"Describe this ad creative VIDEO ({video_filename}, "
                f"{video_info.get('duration_seconds', 0):.0f}s).\n\n"
                f"Above are 3 keyframes extracted at 10%, 50%, and 85% of the video.\n\n"
                f"## AUDIO TRANSCRIPT\n{transcript}\n\n"
                f"Analyze the visual elements across frames, emotional tone, "
                f"implied message, target awareness level, and provide a transcript_summary "
                f"(1-2 sentence summary of what the speaker says and the key selling points)."
            ),
        })

        user_message = {"role": "user", "content": content_blocks}

        async def call():
            return await client.messages.parse(
                model=MODEL_NAME,
                max_tokens=1024,
                system=system_messages,
                messages=[user_message],
                output_format=ImageDescription,
            )

        response = await _async_api_call_with_retry(call, label=f"describe:{video_filename}")
        _log_usage(f"describe:{video_filename}", response.usage)
        desc = response.parsed_output

        logger.info(f"  -> {video_filename}: awareness={desc.target_awareness_level}, tone={desc.emotional_tone}")

        return {
            "image_filename": video_filename,
            "image_path": video_info["frame_paths"][0],  # thumbnail for downstream vision
            "media_type": "video",
            "video_path": video_info["video_path"],
            "visual_elements": desc.visual_elements,
            "emotional_tone": desc.emotional_tone,
            "implied_message": desc.implied_message,
            "target_awareness_level": desc.target_awareness_level,
            "transcript_summary": desc.transcript_summary,
        }


async def describe_all_media(
    client: anthropic.AsyncAnthropic,
    system_messages: list[dict],
    image_paths: list[Path],
    video_infos: list[dict],
) -> list[dict]:
    """Pass 1: Describe all images and videos concurrently."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    total = len(image_paths) + len(video_infos)

    tasks = []
    # Image tasks
    for i, path in enumerate(image_paths, 1):
        tasks.append(describe_image(client, system_messages, path, semaphore, i, total))

    # Video tasks
    offset = len(image_paths)
    for i, vinfo in enumerate(video_infos, 1):
        tasks.append(describe_video(client, system_messages, vinfo, semaphore, offset + i, total))

    results = await asyncio.gather(*tasks)
    return list(results)


# ── Pass 2: Category Discovery ─────────────────────────────────────────────


async def discover_categories(
    client: anthropic.AsyncAnthropic,
    system_messages: list[dict],
    descriptions: list[dict],
) -> CategoryDiscoveryResult:
    """Pass 2: Analyze all image descriptions to discover natural concept categories.

    Single call — sends all descriptions as text (no images) along with brand context.
    """
    desc_text = ""
    for d in descriptions:
        media_label = "VIDEO" if d.get("media_type") == "video" else "IMAGE"
        desc_text += (
            f"\n### {d['image_filename']} [{media_label}]\n"
            f"- **Visual Elements**: {d['visual_elements']}\n"
            f"- **Emotional Tone**: {d['emotional_tone']}\n"
            f"- **Implied Message**: {d['implied_message']}\n"
            f"- **Awareness Level**: {d['target_awareness_level']}\n"
        )
        if d.get("transcript_summary"):
            desc_text += f"- **Transcript Summary**: {d['transcript_summary']}\n"

    user_message = {
        "role": "user",
        "content": (
            f"Here are descriptions of {len(descriptions)} ad creative images for Spicy Cubes Dailies.\n\n"
            f"## IMAGE DESCRIPTIONS\n{desc_text}\n\n"
            f"Analyze these creatives and discover the natural concept categories that emerge. "
            f"Apply Eugene Schwartz's market sophistication framework and map each category "
            f"to the brand's Necessary Beliefs.\n\n"
            f"Remember:\n"
            f"- Categories should be MECE for THIS batch\n"
            f"- Each category needs a clear strategic purpose\n"
            f"- Assign each image to its best-fit category in `example_images`\n"
            f"- Aim for 6-12 categories — be granular, split broad themes into specific angles\n"
            f"- No single category should contain more than 20% of the total images"
        ),
    }

    async def call():
        # Use streaming to keep connection alive — this is a large payload
        async with client.messages.stream(
            model=MODEL_NAME,
            max_tokens=16384,
            system=system_messages,
            messages=[user_message],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": _fix_schema_for_api(CategoryDiscoveryResult.model_json_schema()),
                }
            },
        ) as stream:
            response = await stream.get_final_message()
        return response

    response = await _async_api_call_with_retry(call, label="discover_categories")
    _log_usage("discover_categories", response.usage)

    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            f"Discover call hit max_tokens ({response.usage.output_tokens} output tokens). "
            f"Increase max_tokens or reduce the number of images."
        )

    # Parse the streamed JSON text into the Pydantic model
    raw_text = response.content[0].text
    return CategoryDiscoveryResult.model_validate_json(raw_text)


# ── Pass 2b: Video Hook Category Discovery ──────────────────────────────────

HOOK_TRANSCRIPT_CHARS = 200  # First ~200 chars captures the opening hook


async def discover_video_categories(
    client: anthropic.AsyncAnthropic,
    system_messages: list[dict],
    video_descriptions: list[dict],
    video_infos: list[dict],
) -> CategoryDiscoveryResult:
    """Pass 2b: Discover hook-based categories from video descriptions.

    Uses video descriptions + first ~200 chars of transcript (the hook).
    """
    # Build transcript lookup
    transcript_lookup = {vi["video_filename"]: vi.get("transcript", "") for vi in video_infos}

    desc_text = ""
    for d in video_descriptions:
        fname = d["image_filename"]
        transcript = transcript_lookup.get(fname, "")
        hook = transcript[:HOOK_TRANSCRIPT_CHARS] + ("..." if len(transcript) > HOOK_TRANSCRIPT_CHARS else "")
        desc_text += (
            f"\n### {fname} [VIDEO]\n"
            f"- **Visual Elements**: {d['visual_elements']}\n"
            f"- **Emotional Tone**: {d['emotional_tone']}\n"
            f"- **Implied Message**: {d['implied_message']}\n"
            f"- **Awareness Level**: {d['target_awareness_level']}\n"
            f"- **Opening Hook Transcript**: {hook}\n"
        )
        if d.get("transcript_summary"):
            desc_text += f"- **Full Transcript Summary**: {d['transcript_summary']}\n"

    user_message = {
        "role": "user",
        "content": (
            f"Here are descriptions of {len(video_descriptions)} UGC video ad creatives for Spicy Cubes Dailies.\n\n"
            f"## VIDEO DESCRIPTIONS (with opening hooks)\n{desc_text}\n\n"
            f"Discover the natural VIDEO HOOK categories that emerge from these creatives. "
            f"Focus on the opening hook angle — what stops the scroll in the first 5-10 seconds.\n\n"
            f"Remember:\n"
            f"- Categories should be MECE for THIS batch of videos\n"
            f"- Each category needs a clear hook pattern\n"
            f"- Assign each video to its best-fit category in `example_images`\n"
            f"- Aim for 2-5 categories"
        ),
    }

    async def call():
        async with client.messages.stream(
            model=MODEL_NAME,
            max_tokens=8192,
            system=system_messages,
            messages=[user_message],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": _fix_schema_for_api(CategoryDiscoveryResult.model_json_schema()),
                }
            },
        ) as stream:
            response = await stream.get_final_message()
        return response

    response = await _async_api_call_with_retry(call, label="discover_video_categories")
    _log_usage("discover_video_categories", response.usage)

    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            f"Video category discovery hit max_tokens ({response.usage.output_tokens} output tokens)."
        )

    raw_text = response.content[0].text
    return CategoryDiscoveryResult.model_validate_json(raw_text)


# ── Pass 3: Classification ─────────────────────────────────────────────────


async def classify_media_item(
    client: anthropic.AsyncAnthropic,
    system_messages: list[dict],
    image_path: Path,
    category_names: list[str],
    semaphore: asyncio.Semaphore,
    index: int,
    total: int,
    *,
    original_filename: str = "",
    media_type_label: str = "image",
    transcript: str = "",
) -> dict:
    """Classify a single media item (image or video thumbnail) into one of the discovered categories."""
    async with semaphore:
        display_name = original_filename or image_path.name
        logger.info(f"Classifying {media_type_label} {index}/{total}: {display_name}")
        image_data, mime = _encode_image(image_path)

        categories_str = ", ".join(category_names)

        content_blocks = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime,
                    "data": image_data,
                },
            },
        ]

        if transcript:
            # Only use the opening hook (~200 chars) for video classification
            hook_excerpt = transcript[:200] + ("..." if len(transcript) > 200 else "")
            text = (
                f"Classify this ad creative VIDEO ({display_name}) "
                f"into exactly ONE of these categories: {categories_str}\n\n"
                f"IMPORTANT: Classify based on the video's OPENING HOOK — the first thing "
                f"the viewer sees and hears. What belief or angle does the hook lead with? "
                f"Do NOT classify based on mechanism language that appears later in the video "
                f"(most videos eventually mention enzymes vs probiotics — that's not what "
                f"makes them strategically distinct).\n\n"
                f"Opening hook transcript:\n{hook_excerpt}\n\n"
                f"Return the category name and your reasoning."
            )
        else:
            text = (
                f"Classify this ad creative ({display_name}) "
                f"into exactly ONE of these categories: {categories_str}\n\n"
                f"Return the category name and your reasoning."
            )

        content_blocks.append({"type": "text", "text": text})

        user_message = {"role": "user", "content": content_blocks}

        async def call():
            return await client.messages.parse(
                model=MODEL_NAME,
                max_tokens=1024,
                system=system_messages,
                messages=[user_message],
                output_format=ImageClassification,
            )

        response = await _async_api_call_with_retry(call, label=f"classify:{display_name}")
        _log_usage(f"classify:{display_name}", response.usage)
        classification = response.parsed_output

        concept = classification.creative_concept
        if concept not in category_names:
            logger.warning(
                f"  {display_name} classified as '{concept}' "
                f"which is not in discovered categories. Keeping as-is."
            )

        logger.info(f"  -> {display_name}: {concept}")

        return {
            "image_filename": original_filename or image_path.name,
            "image_path": str(image_path),
            "media_type": media_type_label,
            "creative_concept": concept,
            "concept_reasoning": classification.concept_reasoning,
        }


async def classify_all_media(
    client: anthropic.AsyncAnthropic,
    system_messages: list[dict],
    media_items: list[dict],
    category_names: list[str],
) -> list[dict]:
    """Pass 3: Classify all media items concurrently into discovered categories.

    Each media_item dict has:
        - visual_path: Path to image or video thumbnail
        - original_filename: Original media filename
        - media_type: "image" or "video"
        - transcript: Audio transcript (videos only, empty for images)
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    total = len(media_items)

    tasks = [
        classify_media_item(
            client, system_messages,
            Path(item["visual_path"]),
            category_names, semaphore, i, total,
            original_filename=item["original_filename"],
            media_type_label=item.get("media_type", "image"),
            transcript=item.get("transcript", ""),
        )
        for i, item in enumerate(media_items, 1)
    ]

    results = await asyncio.gather(*tasks)
    return list(results)


# ── Pass 3b: Visual Sub-grouping ───────────────────────────────────────────

# Max images to send in a single sub-grouping call
MAX_SUBGROUP_BATCH = 20       # Concept-scoped (fewer, usually < 20)
MAX_GLOBAL_SUBGROUP_BATCH = 8 # Global batches (more images, larger payloads)


async def subgroup_concept(
    client: anthropic.AsyncAnthropic,
    system_messages: list[dict],
    concept: str,
    image_paths: list[Path],
    semaphore: asyncio.Semaphore,
    filename_map: dict[str, str] | None = None,
) -> ConceptSubGroupResult:
    """Sub-group media items within a single concept by visual similarity.

    For concepts with >MAX_SUBGROUP_BATCH items, batches them and
    does a text-only merge pass to combine sub-groups across batches.
    """
    async with semaphore:
        if len(image_paths) <= MAX_SUBGROUP_BATCH:
            return await _subgroup_batch(client, system_messages, concept, image_paths, filename_map)

        # Batch into groups of MAX_SUBGROUP_BATCH
        batches = [
            image_paths[i:i + MAX_SUBGROUP_BATCH]
            for i in range(0, len(image_paths), MAX_SUBGROUP_BATCH)
        ]
        logger.info(f"  Concept '{concept}' has {len(image_paths)} items, splitting into {len(batches)} batches")

        batch_results = []
        for batch_idx, batch in enumerate(batches):
            result = await _subgroup_batch(client, system_messages, concept, batch, filename_map)
            batch_results.append(result)
            logger.info(f"    Batch {batch_idx + 1}/{len(batches)}: {len(result.sub_groups)} sub-groups")

        # Merge pass: combine sub-groups from different batches
        return await _merge_subgroups(client, concept, batch_results)


async def _subgroup_batch(
    client: anthropic.AsyncAnthropic,
    system_messages: list[dict],
    concept: str | None,
    image_paths: list[Path],
    filename_map: dict[str, str] | None = None,
) -> ConceptSubGroupResult:
    """Send a batch of images/thumbnails to Claude for visual sub-grouping.

    Args:
        concept: If provided, scopes to a concept. If None, global sub-grouping.
        filename_map: Optional mapping from visual_path -> original_filename.
                      Used for videos where the visual is a thumbnail frame.
    """
    label = f"'{concept}'" if concept else "global"
    logger.info(f"  Sub-grouping {label} ({len(image_paths)} media items)...")

    content_blocks = []
    display_names = []
    for img_path in image_paths:
        image_data, media_type = _encode_image(img_path)
        content_blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": image_data,
            },
        })
        display_name = (filename_map or {}).get(str(img_path), img_path.name)
        display_names.append(display_name)
        content_blocks.append({
            "type": "text",
            "text": f"Filename: {display_name}",
        })

    filenames = ", ".join(display_names)
    if concept:
        context_line = f"These {len(image_paths)} creatives all belong to the '{concept}' creative concept."
    else:
        context_line = f"These {len(image_paths)} ad creatives are from the same brand's creative library."
    content_blocks.append({
        "type": "text",
        "text": (
            f"{context_line}\n\n"
            f"Filenames: {filenames}\n\n"
            f"Cluster them into visual sub-groups based on visual similarity "
            f"(layout, style, color palette, format, composition). "
            f"Every item must be assigned to exactly one sub-group. "
            f"Target sub-groups of 2-10 items. Solo items that don't match anything get their own sub-group."
        ),
    })

    user_message = {"role": "user", "content": content_blocks}

    async def call():
        return await client.messages.parse(
            model=MODEL_NAME,
            max_tokens=4096,
            system=system_messages,
            messages=[user_message],
            output_format=ConceptSubGroupResult,
        )

    api_label = f"subgroup:{concept or 'global'}"
    response = await _async_api_call_with_retry(call, label=api_label)
    _log_usage(api_label, response.usage)

    result = response.parsed_output
    logger.info(f"    -> {label}: {len(result.sub_groups)} visual sub-groups")
    return result


async def _merge_subgroups(
    client: anthropic.AsyncAnthropic,
    concept: str,
    batch_results: list[ConceptSubGroupResult],
) -> ConceptSubGroupResult:
    """Text-only merge pass: combine sub-groups from different batches that should be together."""
    # Build a description of all sub-groups from all batches
    all_subgroups_text = ""
    for batch_idx, result in enumerate(batch_results):
        all_subgroups_text += f"\n## Batch {batch_idx + 1}\n"
        for sg in result.sub_groups:
            all_subgroups_text += (
                f"- **{sg.sub_group_name}**: {sg.reasoning}\n"
                f"  Images: {', '.join(sg.image_filenames)}\n"
            )

    user_message = {
        "role": "user",
        "content": (
            f"I sub-grouped images from the '{concept}' concept in multiple batches. "
            f"Some sub-groups across batches may describe the same visual style and should be merged.\n\n"
            f"{all_subgroups_text}\n\n"
            f"Review these sub-groups and merge any that describe the same visual style. "
            f"Keep sub-groups that are truly distinct. Return the final set of sub-groups "
            f"with all their images consolidated. Every image must appear exactly once."
        ),
    }

    # Estimate needed output tokens: ~60 chars per image filename × num_images + overhead
    total_images = sum(len(sg.image_filenames) for r in batch_results for sg in r.sub_groups)
    merge_max_tokens = max(8192, min(16384, total_images * 80))

    async def call():
        return await client.messages.parse(
            model=MODEL_NAME,
            max_tokens=merge_max_tokens,
            system=[{
                "type": "text",
                "text": (
                    "You are a visual creative analyst. Merge visually similar sub-groups "
                    "from different batches into a consolidated set. Keep sub-groups that "
                    "are truly visually distinct. Every image must appear in exactly one sub-group."
                ),
            }],
            messages=[user_message],
            output_format=ConceptSubGroupResult,
        )

    response = await _async_api_call_with_retry(call, label=f"merge_subgroups:{concept}")
    _log_usage(f"merge_subgroups:{concept}", response.usage)

    result = response.parsed_output
    logger.info(f"    -> '{concept}' merged: {len(result.sub_groups)} final sub-groups")
    return result


async def subgroup_all_concepts(
    client: anthropic.AsyncAnthropic,
    system_messages: list[dict],
    concept_images: dict[str, list[Path]],
    filename_map: dict[str, str] | None = None,
) -> dict[str, ConceptSubGroupResult]:
    """Pass 3b: Sub-group all concepts concurrently."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def _sg_one(concept: str, paths: list[Path]) -> tuple[str, ConceptSubGroupResult]:
        result = await subgroup_concept(client, system_messages, concept, paths, semaphore, filename_map)
        return concept, result

    tasks = [_sg_one(concept, paths) for concept, paths in concept_images.items()]
    results = await asyncio.gather(*tasks)
    return dict(results)


# ── Global Visual Sub-grouping (before classification) ───────────────────


async def subgroup_all_global(
    client: anthropic.AsyncAnthropic,
    system_messages: list[dict],
    image_paths: list[Path],
    filename_map: dict[str, str] | None = None,
) -> ConceptSubGroupResult:
    """Sub-group ALL images globally by visual similarity (before classification).

    Batches images and merges sub-groups across batches if needed.
    """
    if len(image_paths) <= MAX_GLOBAL_SUBGROUP_BATCH:
        return await _subgroup_batch(client, system_messages, None, image_paths, filename_map)

    batches = [
        image_paths[i:i + MAX_GLOBAL_SUBGROUP_BATCH]
        for i in range(0, len(image_paths), MAX_GLOBAL_SUBGROUP_BATCH)
    ]
    logger.info(f"  Global sub-grouping {len(image_paths)} images in {len(batches)} batches")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def _process_batch(batch_idx: int, batch: list[Path]) -> ConceptSubGroupResult:
        async with semaphore:
            result = await _subgroup_batch(client, system_messages, None, batch, filename_map)
            logger.info(f"    Batch {batch_idx + 1}/{len(batches)}: {len(result.sub_groups)} sub-groups")
            return result

    tasks = [_process_batch(i, batch) for i, batch in enumerate(batches)]
    batch_results = await asyncio.gather(*tasks)

    return await _merge_subgroups(client, "global", batch_results)


# ── Sub-group Labeling (assign concept to each sub-group) ────────────────


async def label_subgroup(
    client: anthropic.AsyncAnthropic,
    system_messages: list[dict],
    sub_group: dict,
    category_names: list[str],
    semaphore: asyncio.Semaphore,
    index: int,
    total: int,
) -> dict:
    """Label a single visual sub-group with a strategic concept category.

    Sends up to 4 representative images from the sub-group.
    """
    async with semaphore:
        sg_name = sub_group["sub_group_name"]
        images = sub_group["images"]

        logger.info(f"Labeling sub-group {index}/{total}: {sg_name} ({len(images)} items)")

        # Send up to 4 representative images
        sample = images[:4]
        content_blocks = []
        for item in sample:
            image_data, mime = _encode_image(Path(item["image_path"]))
            content_blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": mime, "data": image_data},
            })

        categories_str = ", ".join(category_names)
        filenames = ", ".join(img["image_filename"] for img in images)

        content_blocks.append({
            "type": "text",
            "text": (
                f"This visual sub-group '{sg_name}' contains {len(images)} creatives: {filenames}\n\n"
                f"Above are {len(sample)} representative images from this sub-group.\n\n"
                f"Sub-group visual description: {sub_group.get('reasoning', '')}\n\n"
                f"Assign this sub-group to exactly ONE of these strategic concept categories: {categories_str}\n\n"
                f"Return the category name and your reasoning."
            ),
        })

        user_message = {"role": "user", "content": content_blocks}

        async def call():
            return await client.messages.parse(
                model=MODEL_NAME,
                max_tokens=1024,
                system=system_messages,
                messages=[user_message],
                output_format=ImageClassification,
            )

        response = await _async_api_call_with_retry(call, label=f"label:{sg_name}")
        _log_usage(f"label:{sg_name}", response.usage)
        classification = response.parsed_output

        concept = classification.creative_concept
        if concept not in category_names:
            logger.warning(
                f"  {sg_name} labeled as '{concept}' which is not in discovered categories."
            )

        logger.info(f"  -> {sg_name}: {concept}")

        return {
            "sub_group_name": sg_name,
            "creative_concept": concept,
            "concept_reasoning": classification.concept_reasoning,
        }


async def label_all_subgroups(
    client: anthropic.AsyncAnthropic,
    system_messages: list[dict],
    sub_groups: list[dict],
    category_names: list[str],
) -> list[dict]:
    """Label all visual sub-groups with strategic concept categories concurrently."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    total = len(sub_groups)

    tasks = [
        label_subgroup(client, system_messages, sg, category_names, semaphore, i, total)
        for i, sg in enumerate(sub_groups, 1)
    ]

    results = await asyncio.gather(*tasks)
    return list(results)


# ── Pass 4: Copy Generation per concept group ─────────────────────────────


async def generate_concept_copy(
    client: anthropic.AsyncAnthropic,
    system_messages: list[dict],
    concept: str,
    concept_description: str,
    image_paths: list[Path],
    semaphore: asyncio.Semaphore,
    filename_map: dict[str, str] | None = None,
) -> ConceptCopyResult:
    """Generate copy for a concept group.

    Args:
        filename_map: Optional mapping from visual_path -> original_filename.
    """
    async with semaphore:
        logger.info(f"  Generating copy for '{concept}' ({len(image_paths)} creatives)...")
        sample_paths = image_paths[:MAX_CONCEPT_IMAGES]

        content_blocks = []
        for img_path in sample_paths:
            image_data, media_type = _encode_image(img_path)
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_data,
                },
            })

        fmap = filename_map or {}
        display_names = [fmap.get(str(p), p.name) for p in image_paths]
        media_list = ", ".join(display_names)
        has_videos = any(n.endswith(".mp4") or n.endswith(".mov") for n in display_names)
        video_note = " Some are video thumbnails — copy should work for both image and video ads." if has_videos else ""

        content_blocks.append({
            "type": "text",
            "text": (
                f"These {len(image_paths)} creative(s) belong to the "
                f"'{concept}' creative concept: {media_list}\n\n"
                f"**Concept description**: {concept_description}\n\n"
                f"Generate exactly {VARIATIONS_PER_CONCEPT} direct-response ad copy variations "
                f"for this concept group. The copy should work well paired with ANY of these creatives.{video_note}\n\n"
                f"Each variation needs:\n"
                f"- primary_text: 2-4 sentences, DR style\n"
                f"- headline: under 40 characters\n"
                f"- description: under 30 characters\n\n"
                f"Vary the emotional angle across variations — mix hooks, tones, and "
                f"belief angles within the '{concept}' concept."
            ),
        })

        user_message = {"role": "user", "content": content_blocks}

        async def call():
            return await client.messages.parse(
                model=MODEL_NAME,
                max_tokens=4096,
                system=system_messages,
                messages=[user_message],
                output_format=ConceptCopyResult,
            )

        response = await _async_api_call_with_retry(call, label=f"copygen:{concept}")
        _log_usage(f"copygen:{concept}", response.usage)

        result = response.parsed_output
        logger.info(f"    -> '{concept}': {len(result.variations)} variations generated")
        return result


async def generate_all_concept_copy(
    client: anthropic.AsyncAnthropic,
    system_messages: list[dict],
    groups: dict[str, list[dict]],
    cat_lookup: dict[str, dict],
    filename_map: dict[str, str] | None = None,
) -> list[dict]:
    """Pass 4: Generate copy for all concept groups concurrently."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def _gen_one(concept: str, items: list[dict]) -> dict:
        img_paths = [Path(c["image_path"]) for c in items]
        concept_desc = cat_lookup.get(concept, {}).get("description", concept)
        copy_result = await generate_concept_copy(
            client, system_messages, concept, concept_desc, img_paths, semaphore, filename_map,
        )
        return {
            "creative_concept": concept,
            "images": [c["image_filename"] for c in items],
            "variations": [v.model_dump() for v in copy_result.variations],
        }

    tasks = [_gen_one(concept, items) for concept, items in groups.items()]
    return await asyncio.gather(*tasks)


async def generate_all_subgroup_copy(
    client: anthropic.AsyncAnthropic,
    system_messages: list[dict],
    subgroups_data: dict,
    cat_lookup: dict[str, dict],
) -> list[dict]:
    """Pass 4 (sub-group aware): Generate copy per sub-group within each concept.

    Args:
        subgroups_data: Dict with concept names as keys, each containing a list of sub-groups
                        with 'sub_group_name' and 'images' (list of dicts with image_path/image_filename).
        cat_lookup: Category metadata lookup.

    Returns a list of concept dicts, each with sub_groups containing variations.
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def _gen_subgroup(
        concept: str,
        sub_group_name: str,
        image_items: list[dict],
    ) -> dict:
        img_paths = [Path(item["image_path"]) for item in image_items]
        concept_desc = cat_lookup.get(concept, {}).get("description", concept)

        # Build filename_map for items that have original filenames different from visual path
        fmap = {}
        for item in image_items:
            visual = item["image_path"]
            orig = item.get("image_filename", Path(visual).name)
            if orig != Path(visual).name:
                fmap[visual] = orig

        copy_result = await generate_concept_copy(
            client, system_messages, f"{concept}/{sub_group_name}",
            concept_desc, img_paths, semaphore, fmap or None,
        )
        return {
            "sub_group_name": sub_group_name,
            "images": [item["image_filename"] for item in image_items],
            "variations": [v.model_dump() for v in copy_result.variations],
        }

    # Flatten all sub-groups into concurrent tasks, then reassemble by concept
    tasks = []
    task_concepts = []

    for concept, sg_list in subgroups_data.items():
        for sg in sg_list:
            tasks.append(_gen_subgroup(concept, sg["sub_group_name"], sg["images"]))
            task_concepts.append(concept)

    results = await asyncio.gather(*tasks)

    # Reassemble into concept-grouped structure
    concept_order = list(dict.fromkeys(task_concepts))  # Preserve order, dedupe
    concept_subgroups: dict[str, list[dict]] = {c: [] for c in concept_order}
    for concept, result in zip(task_concepts, results):
        concept_subgroups[concept].append(result)

    return [
        {
            "creative_concept": concept,
            "sub_groups": sgs,
        }
        for concept, sgs in concept_subgroups.items()
    ]
