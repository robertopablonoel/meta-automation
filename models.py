from pydantic import BaseModel


# ── Pass 1: Image Description ─────────────────────────────────────────────

class ImageDescription(BaseModel):
    """Describe what's in an ad creative image or video."""
    visual_elements: str       # What's literally shown: people, products, text overlays, colors
    emotional_tone: str        # The feeling/mood the image evokes
    implied_message: str       # What the image is trying to communicate to the viewer
    target_awareness_level: str  # Schwartz awareness level: unaware / problem-aware / solution-aware / product-aware / most-aware
    transcript_summary: str = ""  # Empty for images; populated for videos with audio transcript summary


# ── Pass 2: Category Discovery ─────────────────────────────────────────────

class DiscoveredCategory(BaseModel):
    """A single creative concept category discovered from the image set."""
    name: str                    # Snake_case slug, e.g. "mechanism_education"
    display_name: str            # Human-readable, e.g. "Mechanism Education"
    description: str             # What this category represents
    schwartz_sophistication: str # Which market sophistication stage this targets (1-5)
    belief_mapping: str          # Which Necessary Belief(s) this category builds
    example_images: list[str]    # Filenames of images that belong here


class CategoryDiscoveryResult(BaseModel):
    """The full set of discovered categories for this image batch."""
    reasoning: str                          # How you arrived at these categories
    categories: list[DiscoveredCategory]    # The discovered categories


# ── Pass 3: Classification ─────────────────────────────────────────────────

class ImageClassification(BaseModel):
    """Classify a single image into a discovered creative concept."""
    creative_concept: str     # Must match a discovered category name
    concept_reasoning: str


# ── Pass 3b: Visual Sub-grouping ─────────────────────────────────────────

class VisualSubGroup(BaseModel):
    """A cluster of visually similar images within a concept."""
    sub_group_name: str       # e.g. "ugc_selfie_testimonials"
    reasoning: str            # Why these images belong together visually
    image_filenames: list[str]  # 2-10 images in this sub-group


class ConceptSubGroupResult(BaseModel):
    """All visual sub-groups for a single concept."""
    sub_groups: list[VisualSubGroup]


# ── Pass 4: Copy Generation ───────────────────────────────────────────────

class AdCopyVariation(BaseModel):
    """A single ad copy variation."""
    primary_text: str   # 2-4 sentences, DR style
    headline: str       # Under 40 chars, benefit-focused tagline
    description: str    # 40-80 chars, social proof / offer / guarantee


class ConceptCopyResult(BaseModel):
    """Generate copy for an entire concept group."""
    variations: list[AdCopyVariation]  # Exactly 5
