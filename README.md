# Spicy Cubes Dailies — Meta Ad Copy Automation Pipeline

Takes a folder of ad creative images and videos, analyzes each one against 3 brand foundational documents, clusters images by visual similarity using CLIP embeddings, discovers strategic concept categories, generates 5 direct-response copy variations per concept, and uploads everything to Meta Ads as a structured campaign.

## Pipeline Architecture

```
  input_images/
  ├── *.jpg, *.png, *.webp  (images)
  └── *.mp4, *.mov          (videos)
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PASS 0: VIDEO PREPROCESSING                    video_preprocessor.py  │
│                                                                         │
│  *.mp4 ──► ffmpeg ──► 3 JPEG frames (10%, 50%, 85%)                    │
│            ffmpeg ──► audio.wav ──► faster-whisper ──► transcript text   │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PASS 1: DESCRIBE ALL MEDIA                      copy_generator.py     │
│                                                                         │
│  Each image/video ──► Claude Vision API (concurrent, max 10)            │
│                                                                         │
│  Returns per item:                                                      │
│    • visual_elements    • emotional_tone                                │
│    • implied_message    • target_awareness_level                        │
│    • transcript_summary (videos only)                                   │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ├──────────────────────────┐
        ▼ (images only)           ▼ (videos only)
┌────────────────────────┐  ┌────────────────────────────────────────────┐
│  PASS 2: CLIP          │  │  PASS 2b: DISCOVER VIDEO HOOK CATEGORIES  │
│  SUBGROUPING           │  │                                            │
│   image_embedder.py    │  │  Video descriptions + transcripts          │
│                        │  │  ──► Claude API ──► 2-5 hook categories    │
│  CLIP ViT-B/32         │  └────────────────────────────────────────────┘
│  ──► 512-dim embeddings│
│  ──► cosine distance   │
│  ──► agglomerative     │
│      clustering        │
│  ──► auto-named from   │
│      Pass 1 keywords   │
│                        │
│  ~30 sub-groups        │
│  (2-10 images each)    │
│  Zero API calls        │
└────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PASS 3: DISCOVER IMAGE CONCEPT CATEGORIES       copy_generator.py     │
│                                                                         │
│  All descriptions ──► Claude API (streaming)                            │
│  Schwartz framework ──► 6-14 MECE concept categories                   │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ├──────────────────────────┐
        ▼                          ▼
┌────────────────────────┐  ┌────────────────────────────────────────────┐
│  PASS 3b: LABEL        │  │  PASS 3c: CLASSIFY VIDEOS                 │
│  SUB-GROUPS            │  │                                            │
│                        │  │  Each video ──► Claude Vision              │
│  Each sub-group:       │  │  (thumbnail + hook transcript)             │
│  sample images         │  │  ──► assigned to one hook category         │
│  ──► Claude Vision     │  └────────────────────────────────────────────┘
│  ──► assigned to one   │
│      concept category  │
└────────────────────────┘
        │                          │
        └────────┬─────────────────┘
                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  PASS 4: COPY GENERATION                         copy_generator.py     │
│                                                                         │
│  Per concept: sample images + description ──► Claude Vision             │
│  ──► 5 DR ad copy variations (primary_text, headline, description)      │
└─────────────────────────────────────────────────────────────────────────┘
        │
        ▼ (--upload flag)
┌─────────────────────────────────────────────────────────────────────────┐
│  META UPLOAD                                     meta_uploader.py      │
│                                                                         │
│  1 Campaign ──► 1 Ad Set per concept ──► 1 Ad per media item           │
│  Images: AdImage + link_data                                            │
│  Videos: AdVideo + video_data (upload + encoding wait)                  │
│  Copy variations via Advantage+ text_optimizations                      │
└─────────────────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

**Visual-first pipeline** — Images are clustered by visual similarity *before* strategic classification. This means visually identical creatives always stay together in the same ad set, regardless of what concept they're assigned to.

**CLIP embeddings for sub-grouping** — Pass 2 uses `clip-ViT-B-32` via `sentence-transformers` to embed all images into a 512-dim space, then agglomerative clustering groups them by cosine distance. This replaced a Claude Vision batching approach that required 22+ API calls and a lossy text-only merge pass. The CLIP path runs in ~30s with zero API calls.

**Videos have a separate flow** — Videos are preprocessed into 3 keyframes + audio transcript, then flow through the pipeline as thumbnails. They get their own hook-based categories (Pass 2b) and individual classification (Pass 3c), and each video becomes its own sub-group/ad in the final upload.

**Checkpoint resume** — Every pass saves intermediate JSON. Re-running the pipeline skips completed passes automatically. Use `--force` to re-run from scratch.

## Brand Foundation

Three PDFs extracted via `pdfplumber` and injected into every Claude call as cached system messages:

| PDF | What It Contains |
|---|---|
| `brand/03-avatar-sheet.pdf` | Target avatar — women 28-42, identity loss, medical dismissal, relationship strain |
| `brand/04-offer-brief.pdf` | Product details — enzyme-based gummies, Big Idea, UMP/UMS, objection handling |
| `brand/05-necessary-beliefs.pdf` | 6 beliefs the prospect must hold before buying |

Prompt caching (`cache_control: {"type": "ephemeral"}`) saves ~90% on the ~38K chars of brand context that repeats across all API calls.

## Project Structure

```
meta-automation/
├── pipeline/                    # Python package — all pipeline code
│   ├── __init__.py
│   ├── run.py                   # Main orchestrator — CLI entry point, checkpoint logic
│   ├── config.py                # Env vars, paths, model config, feature flags
│   ├── models.py                # Pydantic models for structured output
│   ├── brand_context.py         # PDF extraction + system prompt builders (one per pass)
│   ├── copy_generator.py        # Claude API calls (describe, discover, classify, label, copygen)
│   ├── image_embedder.py        # CLIP embeddings + agglomerative clustering for visual sub-grouping
│   ├── video_preprocessor.py    # ffmpeg frame extraction + faster-whisper transcription
│   └── meta_uploader.py         # Facebook Marketing API (campaign → ad sets → ads)
├── scripts/                     # Operational scripts
│   ├── publisher.py             # Publish pipeline output to Supabase for dashboard
│   ├── metrics_sync.py          # Sync Meta Ads metrics to Supabase
│   └── report.mjs               # CLI report — pull campaign performance from Meta API
├── brand/                       # Brand foundation docs
│   ├── 03-avatar-sheet.pdf
│   ├── 04-offer-brief.pdf
│   └── 05-necessary-beliefs.pdf
├── dashboard/                   # Next.js app (App Router + Tailwind + shadcn/ui)
│   └── ...
├── .env                         # API keys (gitignored)
├── requirements.txt
├── input_images/                # Drop ad creatives here (.jpg, .png, .webp, .mp4, .mov)
└── output/                      # Generated artifacts
    ├── descriptions.json        # Pass 1: per-media descriptions
    ├── global_subgroups.json    # Pass 2: CLIP visual sub-groups
    ├── video_categories.json    # Pass 2b: video hook categories
    ├── categories.json          # Pass 3: discovered concept categories
    ├── subgroup_labels.json     # Pass 3b: sub-group → concept mapping
    ├── video_classifications.json # Pass 3c: video → hook mapping
    ├── subgroups.json           # Assembled final structure
    ├── ad_copy_output.json      # Pass 4: final output with copy
    ├── ad_copy_output.csv       # Flat export (one row per concept × variation)
    ├── clip_cache/              # Cached CLIP embeddings (.npz)
    ├── video_preprocessed/      # Extracted video frames
    └── by_concept/              # Media organized into folders
        ├── {concept_a}/{sub_group}/
        └── ...
```

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install sentence-transformers scikit-learn   # for CLIP sub-grouping
```

For video support, install ffmpeg:
```bash
brew install ffmpeg  # macOS
```

Add your API key to `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
```

Drop ad creative images and videos into `input_images/`.

## Usage

```bash
source venv/bin/activate

# Full pipeline (all passes, resumes from last checkpoint)
python -m pipeline.run

# Step-by-step (inspect between passes)
python -m pipeline.run --preprocess-only   # Pass 0: video frames + transcripts
python -m pipeline.run --describe-only     # Pass 0+1: describe all media
python -m pipeline.run --subgroup-only     # Pass 0+1+2: visual sub-grouping
python -m pipeline.run --discover-only     # Through Pass 3: category discovery
python -m pipeline.run --classify-only     # Through Pass 3c: labeling + classification
python -m pipeline.run --generate-copy     # Pass 4 only (uses existing checkpoints)

# Copy mode
python -m pipeline.run --subgroup-copy     # Unique copy per sub-group (default: shared per concept)

# Meta upload
python -m pipeline.run --upload            # Full pipeline + upload to Meta
python -m pipeline.run --upload-only       # Upload existing output to Meta

# Re-run from scratch
python -m pipeline.run --force             # Ignore all checkpoints

# Operational scripts
python scripts/publisher.py               # Publish pipeline output to Supabase
python scripts/metrics_sync.py            # Sync Meta metrics to Supabase
node scripts/report.mjs                   # Pull campaign performance report
```

## Configuration

Key settings in `pipeline/config.py` and environment variables:

| Setting | Default | Description |
|---|---|---|
| `USE_CLIP_SUBGROUPING` | `True` | Use CLIP embeddings for Pass 2 (set `False` for legacy Claude vision) |
| `CLIP_DISTANCE_THRESHOLD` | `0.35` | Cosine distance threshold for clustering (env: `CLIP_DISTANCE_THRESHOLD`) |
| `CLIP_MODEL_NAME` | `clip-ViT-B-32` | Sentence-transformers model for image embeddings |
| `MAX_CONCURRENT` | `10` | Max concurrent Claude API calls (env: `MAX_CONCURRENT`) |
| `VARIATIONS_PER_CONCEPT` | `5` | Copy variations generated per concept group |

**Tuning CLIP clustering:**
- Too many small groups → increase threshold to `0.4`-`0.5`
- Too few large groups → decrease threshold to `0.25`-`0.3`

## Meta Upload

Requires Meta credentials in `.env`:

```
META_APP_ID=your-meta-app-id
META_APP_SECRET=your-meta-app-secret
META_ACCESS_TOKEN=your-meta-access-token
META_AD_ACCOUNT_ID=act_your-ad-account-id
META_PAGE_ID=your-page-id
META_INSTAGRAM_ACTOR_ID=your-instagram-actor-id
META_PIXEL_ID=your-pixel-id
LANDING_PAGE_URL=https://your-landing-page-url.com
```

When activated:
- Uploads all images (hashes cached) and videos (encoding wait)
- Creates 1 paused campaign (OUTCOME_SALES)
- Creates 1 ad set per concept (Advantage+ creative, text_optimizations OPT_IN)
- Creates 1 ad per media item with 5 copy variations
- Everything created in PAUSED status for review

## Tech Details

| | |
|---|---|
| **Model** | `claude-sonnet-4-5` via `client.messages.parse()` |
| **Structured output** | Pydantic models → `output_format` parameter |
| **Retry** | Exponential backoff on 429s and 5xx (up to 5 retries) |
| **Caching** | Ephemeral prompt caching on brand context blocks |
| **CLIP** | `sentence-transformers` (`clip-ViT-B-32`), embeddings cached as `.npz` |
| **Clustering** | `scikit-learn` AgglomerativeClustering, cosine distance, average linkage |
| **Video** | `ffmpeg` for frames, `faster-whisper` for transcription |
| **Meta SDK** | `facebook-business` — sequential uploads, 15s pause between ad sets |

## Copy Output Format

Each concept group gets 5 variations:
- **primary_text**: 2-4 sentences, DR style, avatar's language, builds the mapped belief
- **headline**: Under 40 chars, bold, scroll-stopping
- **description**: Under 30 chars, reinforces headline or adds urgency

## Planned: Test → Graduate → Iterate Loop (v2)

The current pipeline generates many concepts and uploads them as separate ad sets for broad testing. The next version closes the feedback loop:

1. **Test** — Pipeline generates concepts, uploads 1 ad set per concept, runs for ~1 week
2. **Graduate** — `--graduate` flag (or standalone script) reads performance data from Supabase/Meta, identifies winning ads by custom ROAS/CPA, and creates a new consolidated campaign with 1-2 ad sets containing only proven winners at higher budget
3. **Iterate** — Next test round feeds winning concept names + performance data back into `pipeline/brand_context.py` so Claude generates new creative variations that riff on proven angles rather than starting from scratch

This turns the pipeline from a one-shot generator into a continuous creative optimization loop: test broadly → scale winners → generate new variations of what works → repeat.
