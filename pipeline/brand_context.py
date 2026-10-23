from pathlib import Path

import pdfplumber

from .config import BRAND_DIR


# ── Brand instructions loader ─────────────────────────────────────────────

_brand_instructions: dict | None = None


def _parse_instructions(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current_key is not None:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = line[3:].strip()
            current_lines = []
        elif current_key is not None:
            current_lines.append(line)
    if current_key is not None:
        sections[current_key] = "\n".join(current_lines).strip()
    return sections


def load_brand_instructions() -> dict[str, str]:
    global _brand_instructions
    if _brand_instructions is None:
        path = BRAND_DIR / "instructions.md"
        if not path.exists():
            raise FileNotFoundError(f"Brand instructions not found: {path}")
        _brand_instructions = _parse_instructions(path.read_text(encoding="utf-8"))
    return _brand_instructions


def _get_copy_rules(language: str) -> str:
    instructions = load_brand_instructions()
    lang_key = f"COPY RULES ({language.upper()})"
    return instructions.get(lang_key) or instructions.get("COPY RULES", "")


def _get_copy_style(language: str) -> str:
    instructions = load_brand_instructions()
    lang_key = f"COPY STYLE GUIDELINES ({language.upper()})"
    return instructions.get(lang_key) or instructions.get("COPY STYLE GUIDELINES", "")


# ── Brand context loader ──────────────────────────────────────────────────

def extract_pdf_text(pdf_path: str) -> str:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n\n".join(pages)


def load_brand_context(language: str = "en") -> str:
    instructions = load_brand_instructions()

    # Try language-specific doc list first, fall back to English list
    lang_key = f"BRAND DOCS ({language.upper()})"
    doc_list = instructions.get(lang_key) or instructions.get("BRAND DOCS", "")
    doc_files = [f.strip() for f in doc_list.splitlines() if f.strip()]

    sections = []
    for doc_file in doc_files:
        doc_stem = Path(doc_file).stem
        if language != "en":
            # Match by stem in language subfolder — handles extension differences (e.g. .pdf → .txt)
            lang_dir = BRAND_DIR / language
            lang_matches = list(lang_dir.glob(f"{doc_stem}.*")) if lang_dir.exists() else []
            doc_path = lang_matches[0] if lang_matches else BRAND_DIR / doc_file
        else:
            doc_path = BRAND_DIR / doc_file

        if not doc_path.exists():
            continue

        if doc_path.suffix.lower() == ".pdf":
            content = extract_pdf_text(str(doc_path))
        else:
            content = doc_path.read_text(encoding="utf-8")

        section_name = doc_path.stem.upper().replace("-", " ").replace("_", " ")
        sections.append(f"=== {section_name} ===\n\n{content}")

    return "\n\n".join(sections)


def _brand_context_block(brand_context: str) -> dict:
    return {
        "type": "text",
        "text": f"## BRAND CONTEXT\n\n{brand_context}",
        "cache_control": {"type": "ephemeral"},
    }


def _language_directive(language: str) -> str:
    if language == "es":
        instructions = load_brand_instructions()
        brand_id = instructions.get("BRAND IDENTITY", "").split(",")[0].strip() or "the brand"
        return (
            "\n\n## LANGUAGE\n"
            "Write ALL output text in Spanish (Latin American). "
            "Use natural, conversational Latin American Spanish — not literal translations from English. "
            f"Keep the brand name '{brand_id}' untranslated."
        )
    return ""


def _brand_identity() -> str:
    instructions = load_brand_instructions()
    return instructions.get("BRAND IDENTITY", "this brand")


# ── Pass 1: Describe ──────────────────────────────────────────────────────

def build_describe_system(brand_context: str, language: str = "en") -> list[dict]:
    lang_block = _language_directive(language)
    brand_id = _brand_identity()
    return [
        {
            "type": "text",
            "text": f"""\
You are an expert direct-response advertising analyst working for {brand_id}.

## YOUR TASK
Describe what you see in each ad creative. You may receive either:
- A single **image** (jpg/png/webp)
- **Video frames** (3 keyframes extracted from a video) along with a **transcript** of the audio

Your description will be used by a strategist to discover natural concept groupings across all creatives.

Be precise and analytical:
- **visual_elements**: Describe exactly what's shown — people, products, text overlays, colors, layout, UGC vs studio, screenshot vs lifestyle, etc. For videos, note the progression across frames and any on-screen text/captions.
- **emotional_tone**: What feeling does this creative evoke? (e.g., vulnerable, empowered, clinical, playful, raw/confessional, aspirational)
- **implied_message**: What is this creative trying to communicate to the viewer? What belief is it building or what objection is it overcoming? For videos, incorporate what the speaker says (from the transcript) into your analysis.
- **target_awareness_level**: Using the brand's belief framework, where does this creative meet the prospect? (early belief-building, mid-funnel, conversion-ready)
- **transcript_summary**: (Videos only) Summarize the key message and selling points from the audio transcript in 1-2 sentences. Leave empty for images.

Think like a media buyer analyzing creatives for pattern recognition.{lang_block}""",
            "cache_control": {"type": "ephemeral"},
        },
        _brand_context_block(brand_context),
    ]


# ── Pass 1 (Static): Describe Static Ad Creatives ────────────────────────

def build_describe_static_system(brand_context: str, language: str = "en") -> list[dict]:
    lang_block = _language_directive(language)
    brand_id = _brand_identity()
    return [
        {
            "type": "text",
            "text": f"""\
You are an expert direct-response advertising analyst working for {brand_id}.

## YOUR TASK
Describe what you see in each STATIC ad creative (jpg/png/webp). These are designed graphic ads — not UGC video frames. They typically contain text overlays such as headlines, body copy, calls-to-action, captions, or taglines baked directly into the image.

Your description will be used by a strategist to discover natural concept groupings and to write complementary ad copy.

Be precise and analytical:
- **visual_elements**: Describe exactly what's shown — people, products, colors, layout, design style (text-heavy graphic, lifestyle photo with overlay, product hero, before/after, etc.). Note any design hierarchy (what the eye is drawn to first).
- **emotional_tone**: What feeling does this creative evoke? (e.g., vulnerable, empowered, clinical, playful, aspirational, bold, intimate)
- **implied_message**: What is this creative trying to communicate to the viewer? What belief is it building or what objection is it overcoming?
- **target_awareness_level**: Using the brand's belief framework, where does this creative meet the prospect?
- **overlay_copy**: READ ALL VISIBLE TEXT on the image verbatim — headlines, subheadlines, body copy, CTAs, captions, hashtags, ingredient callouts, guarantees, social proof snippets, anything printed on the creative. Quote it exactly as written. If there is no visible text, leave empty.
- **transcript_summary**: Leave empty — this field is for video audio transcripts only.

Think like a media buyer AND a copywriter analyzing creatives for pattern recognition and copy strategy.{lang_block}""",
            "cache_control": {"type": "ephemeral"},
        },
        _brand_context_block(brand_context),
    ]


# ── Pass 2: Discover Categories ───────────────────────────────────────────

def build_discover_system(brand_context: str, language: str = "en") -> list[dict]:
    lang_block = _language_directive(language)
    brand_id = _brand_identity()
    return [
        {
            "type": "text",
            "text": f"""\
You are a world-class direct-response strategist and creative analyst. You work for {brand_id}.

## YOUR TASK
Given text descriptions of all ad creatives in a batch, discover the natural creative concept categories that emerge. This is NOT about imposing categories top-down — it's about recognizing the distinct strategic approaches present in the actual creatives.

## YOUR METHODOLOGY
Use the brand's belief framework (from the brand context) to map each category to the belief it installs in the prospect's mind. Categories should reflect distinct strategic entry points — different beliefs, different awareness levels, different emotional angles.

### Category Discovery Rules
1. Look for NATURAL clusters — creatives that share a strategic approach, not just visual similarity
2. Each category should map to a specific belief from the brand's belief framework
3. Categories should be MECE (mutually exclusive, collectively exhaustive) for this batch
4. Aim for 6-12 categories. Be GRANULAR — split broad themes into specific angles
5. **HARD CONSTRAINT: No single category may contain more than 20% of the total images.** If a category is too large, split it into more specific sub-angles
6. Name categories with descriptive snake_case slugs
7. Each category must have a clear strategic purpose — "why would a media buyer group these together?"

## OUTPUT
Provide your reasoning for how you arrived at the categories, then list each category with:
- A snake_case name and human-readable display name
- A description of what unifies creatives in this category
- Which sophistication stage or awareness level it targets (use the brand's framework)
- Which belief(s) it builds
- Which images from the batch belong here{lang_block}""",
            "cache_control": {"type": "ephemeral"},
        },
        _brand_context_block(brand_context),
    ]


# ── Pass 2b: Discover Video Hook Categories ──────────────────────────────

def build_discover_video_system(brand_context: str, language: str = "en") -> list[dict]:
    lang_block = _language_directive(language)
    brand_id = _brand_identity()
    return [
        {
            "type": "text",
            "text": f"""\
You are a world-class direct-response strategist and UGC video analyst for {brand_id}.

## YOUR TASK
Given text descriptions of UGC video ad creatives (including their opening hook transcripts), discover natural VIDEO HOOK categories. These categories are based on the OPENING HOOK — the first thing the viewer sees and hears in the first 5-10 seconds. The hook is what stops the scroll and determines ad performance.

## IMPORTANT
- Categorize by the OPENING HOOK ANGLE, not by the overall content or mechanism discussed later
- Most UGC videos share product talking points — that's not what makes hooks strategically distinct
- The hook is the scroll-stopper: different emotional or curiosity entry points are different categories even if videos later converge on similar messaging

## CATEGORY DISCOVERY RULES
1. Look for distinct HOOK PATTERNS — what emotional/curiosity entry point does each video use?
2. Categories should be MECE for this batch of videos
3. Aim for 2-5 categories (fewer videos = fewer categories)
4. Name categories with descriptive snake_case slugs that reflect the hook angle
5. Map each category to the belief it targets and the awareness level it enters at{lang_block}""",
            "cache_control": {"type": "ephemeral"},
        },
        _brand_context_block(brand_context),
    ]


# ── Pass 3: Classify ──────────────────────────────────────────────────────

def build_classify_system(brand_context: str, categories: list[dict], language: str = "en") -> list[dict]:
    category_list = "\n".join(
        f"- **{cat['name']}** ({cat['display_name']}): {cat['description']}"
        for cat in categories
    )
    lang_block = _language_directive(language)
    brand_id = _brand_identity()

    return [
        {
            "type": "text",
            "text": f"""\
You are an expert direct-response advertising analyst for {brand_id}.

## YOUR TASK
Classify each ad creative into exactly ONE of the following creative concept categories. The creative may be an image or a video thumbnail (with an optional transcript excerpt for context). These categories were discovered from analysis of this specific batch of creatives.

## CATEGORIES
{category_list}

## HOW TO CLASSIFY
Use the brand's foundational documents (from the brand context) to inform your decision:

1. **Match the belief being built**: Each category maps to a belief in the brand's framework. Ask: "Which belief is this creative primarily trying to build in the prospect's mind?"
2. **Read the avatar**: Use the avatar sheet to understand the emotional state and language the creative is speaking to.
3. **Consider the offer angle**: Use the offer brief to understand which part of the brand story this creative supports.
4. **Awareness level**: Where does this creative meet the prospect?

## RULES
- Choose the single BEST category for each image
- Provide clear reasoning that references which belief, avatar pain point, or offer angle drove your decision
- If a creative could fit multiple categories, choose the one that best represents its PRIMARY strategic intent{lang_block}""",
            "cache_control": {"type": "ephemeral"},
        },
        _brand_context_block(brand_context),
    ]


# ── Pass 3b: Visual Sub-grouping ─────────────────────────────────────────

def build_subgroup_system() -> list[dict]:
    return [
        {
            "type": "text",
            "text": """\
You are an expert visual creative analyst specializing in ad creative production for Meta (Facebook/Instagram) advertising.

## YOUR TASK
You will receive all images belonging to a single creative concept group. These images already share a strategic message/belief — your job is to cluster them by **visual similarity** so that visually coherent images can be grouped into a single flexible ad (dynamic creative) on Meta.

## CLUSTERING CRITERIA (Visual Only)
Cluster images based on these visual attributes — NOT by message, copy, or strategic intent (that's already handled):

1. **Format/Layout**: UGC selfie vs studio product shot vs screenshot vs lifestyle photo vs text overlay graphic vs comparison chart
2. **Visual Style**: Raw/amateur vs polished/professional, dark moody vs bright clean, minimalist vs busy
3. **Color Palette**: Warm tones vs cool tones, brand-colored vs neutral, high contrast vs muted
4. **Subject Matter**: Person close-up vs product close-up vs scene/environment vs text-heavy
5. **Composition**: Single subject centered vs multi-element collage vs before/after split vs full-bleed image

## RULES
- Target sub-groups of 2-10 images each
- Images that don't visually match anything else get their own sub-group of 1
- Every image MUST be assigned to exactly one sub-group — no duplicates, no omissions
- Name each sub-group with a descriptive snake_case slug (e.g. "ugc_selfie_closeup", "product_studio_bright", "text_overlay_comparison")
- Provide clear reasoning for WHY these images look similar enough to rotate within one ad
- A viewer scrolling through a Meta feed should see any image from the sub-group and feel visual consistency""",
            "cache_control": {"type": "ephemeral"},
        },
    ]


# ── Pass 3b: Label Sub-groups with Strategic Concepts ────────────────────

def build_label_subgroup_system(brand_context: str, categories: list[dict], language: str = "en") -> list[dict]:
    category_list = "\n".join(
        f"- **{cat['name']}** ({cat['display_name']}): {cat['description']}"
        for cat in categories
    )
    lang_block = _language_directive(language)
    brand_id = _brand_identity()

    return [
        {
            "type": "text",
            "text": f"""\
You are an expert direct-response advertising analyst for {brand_id}.

## YOUR TASK
You will receive a visual sub-group of ad creatives — images that have already been clustered together because they look visually similar. Your job is to assign this sub-group to exactly ONE strategic concept category.

## CATEGORIES
{category_list}

## HOW TO LABEL
Use the brand's foundational documents (from the brand context) to inform your decision:

1. **Look at the representative images**: What belief are these creatives primarily building?
2. **Consider the sub-group as a whole**: The entire sub-group should map to one strategic concept.
3. **Match the belief being built**: Each category maps to a belief in the brand's framework.
4. **Awareness level**: Where do these creatives meet the prospect?

## RULES
- Choose the single BEST category for the entire sub-group
- All images in the sub-group get the same label
- If images could fit multiple categories, choose the one that best represents their PRIMARY strategic intent
- Provide clear reasoning that references which belief, avatar pain point, or offer angle drove your decision{lang_block}""",
            "cache_control": {"type": "ephemeral"},
        },
        _brand_context_block(brand_context),
    ]


# ── Pass 4: Copy Generation ──────────────────────────────────────────────

def build_copygen_system(brand_context: str, categories: list[dict], language: str = "en") -> list[dict]:
    category_context = "\n\n".join(
        f"### {cat['display_name']} (`{cat['name']}`)\n"
        f"{cat['description']}\n"
        f"Schwartz sophistication: {cat['schwartz_sophistication']}\n"
        f"Builds belief: {cat['belief_mapping']}"
        for cat in categories
    )
    brand_id = _brand_identity()
    copy_rules = _get_copy_rules(language)
    copy_style = _get_copy_style(language)

    return [
        {
            "type": "text",
            "text": f"""\
You are an expert direct-response copywriter for {brand_id}.

## CREATIVE CONCEPT CATEGORIES (Discovered for This Batch)
{category_context}

## COPY RULES
{copy_rules}

## COPY STYLE GUIDELINES
{copy_style}""",
            "cache_control": {"type": "ephemeral"},
        },
        _brand_context_block(brand_context),
    ]


# ── Pass 4 (Static): Copy Generation for Static Ads ─────────────────────

def build_copygen_static_system(brand_context: str, categories: list[dict], language: str = "en") -> list[dict]:
    """Copy generation aware of existing overlay text on static ad creatives.

    Static ads already have copy baked into the image. The generated copy
    (primary_text, headline, description) is the AD BODY — it lives in the
    post caption area alongside the image, not on the image itself.
    """
    category_context = "\n\n".join(
        f"### {cat['display_name']} (`{cat['name']}`)\n"
        f"{cat['description']}\n"
        f"Schwartz sophistication: {cat['schwartz_sophistication']}\n"
        f"Builds belief: {cat['belief_mapping']}"
        for cat in categories
    )
    brand_id = _brand_identity()
    copy_rules = _get_copy_rules(language)
    copy_style = _get_copy_style(language)

    return [
        {
            "type": "text",
            "text": f"""\
You are an expert direct-response copywriter for {brand_id}.

## CREATIVE CONCEPT CATEGORIES (Discovered for This Batch)
{category_context}

## STATIC AD CONTEXT
These are static graphic ads — copy is already printed on the image itself.
The copy you're generating is the POST BODY: the Facebook/Instagram caption that appears alongside the image, NOT text on the image.

### Key rules for static ads:
- **DO NOT restate** what the image already says — assume the prospect has already read it
- **EXTEND** the image's message: add more context, more proof, a deeper story, or a complementary emotional angle
- If the image has a strong headline, the generated `headline` must be DIFFERENT — a distinct angle on the same concept
- If the image has a CTA, the copy can reinforce it or give additional reasons to click

## COPY RULES
{copy_rules}

## COPY STYLE GUIDELINES
{copy_style}""",
            "cache_control": {"type": "ephemeral"},
        },
        _brand_context_block(brand_context),
    ]


# ── Legacy compatibility ──────────────────────────────────────────────────

def build_system_messages(brand_context: str) -> list[dict]:
    return build_describe_system(brand_context)
