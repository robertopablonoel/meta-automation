import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = BASE_DIR / "input_images"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_JSON = OUTPUT_DIR / "ad_copy_output.json"
OUTPUT_CSV = OUTPUT_DIR / "ad_copy_output.csv"

# Brand doc PDFs
AVATAR_SHEET_PDF = BASE_DIR / "brand" / "03-avatar-sheet.pdf"
OFFER_BRIEF_PDF = BASE_DIR / "brand" / "04-offer-brief.pdf"
NECESSARY_BELIEFS_PDF = BASE_DIR / "brand" / "05-necessary-beliefs.pdf"

# ── Anthropic ──────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL_NAME = "claude-sonnet-4-5"
VARIATIONS_PER_CONCEPT = 5

# ── Meta Marketing API ─────────────────────────────────────────────────────
META_APP_ID = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
_raw_ad_account_id = os.getenv("META_AD_ACCOUNT_ID", "")
META_AD_ACCOUNT_ID = _raw_ad_account_id if _raw_ad_account_id.startswith("act_") else f"act_{_raw_ad_account_id}"
META_PAGE_ID = os.getenv("META_PAGE_ID", "")
META_INSTAGRAM_ACTOR_ID = os.getenv("META_INSTAGRAM_ACTOR_ID", "")
META_PIXEL_ID = os.getenv("META_PIXEL_ID", "")
META_CUSTOM_CONVERSION_ID = os.getenv("META_CUSTOM_CONVERSION_ID", "")
META_CUSTOM_EVENT_TYPE = os.getenv("META_CUSTOM_EVENT_TYPE", "PURCHASE")
LANDING_PAGE_URL = os.getenv("LANDING_PAGE_URL", "")

# ── Supported media extensions ─────────────────────────────────────────────
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov"}
SUPPORTED_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS | SUPPORTED_VIDEO_EXTENSIONS

# ── Video preprocessing ──────────────────────────────────────────────────
VIDEO_PREPROCESSED_DIR = OUTPUT_DIR / "video_preprocessed"
VIDEO_PREPROCESSED_JSON = OUTPUT_DIR / "video_preprocessed.json"
VIDEO_CATEGORIES_JSON = OUTPUT_DIR / "video_categories.json"
VIDEO_CLASSIFICATIONS_JSON = OUTPUT_DIR / "video_classifications.json"
GLOBAL_SUBGROUPS_JSON = OUTPUT_DIR / "global_subgroups.json"
SUBGROUP_LABELS_JSON = OUTPUT_DIR / "subgroup_labels.json"

# ── Concurrency ───────────────────────────────────────────────────────────
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT", "10"))

# ── CLIP sub-grouping ────────────────────────────────────────────────────
USE_CLIP_SUBGROUPING = True
CLIP_DISTANCE_THRESHOLD = float(os.getenv("CLIP_DISTANCE_THRESHOLD", "0.35"))
CLIP_MODEL_NAME = "clip-ViT-B-32"
CLIP_EMBEDDINGS_CACHE_DIR = OUTPUT_DIR / "clip_cache"

# ── Discovery settings ────────────────────────────────────────────────────
# Max images to send as thumbnails in the category discovery prompt
MAX_DISCOVERY_IMAGES = 20
