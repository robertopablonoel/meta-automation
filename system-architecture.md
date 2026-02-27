# System Architecture

End-to-end architecture for the Meta Ads automation system. Two creative sources feed a single pipeline, with a performance feedback loop that compounds over time.

```
                    ┌─────────────────────┐
                    │   CREATIVE SOURCES   │
                    └─────────┬───────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
   ┌──────────▼──────────┐       ┌────────────▼────────────┐
   │  Organic Content    │       │  AI-Generated Content    │
   │  (shortsleaderboard)│       │  (pipeline + ai_brief)   │
   │                     │       │                          │
   │  fetch_organic.py   │       │  feedback_generator.py   │
   │  ↓ yt-dlp download  │       │  ↓ reads metrics_cache   │
   └──────────┬──────────┘       └────────────┬────────────┘
              │                               │
              └───────────────┬───────────────┘
                              │
                     input_images/
                              │
              ┌───────────────▼───────────────┐
              │         PIPELINE              │
              │  Pass 0 → 1 → 2/2b → 3 → 4   │
              │  python -m pipeline.run       │
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │        META ADS               │
              │  CBO Campaign                 │
              │  1 Ad Set per Concept          │
              │  1 Ad per Media Item           │
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │      METRICS SYNC             │
              │  metrics_sync.py              │
              │  → Supabase metrics_cache     │
              │  → daily_snapshots            │
              └───────────────┬───────────────┘
                              │
              ┌───────────────▼───────────────┐
              │       DASHBOARD               │
              │  KPI benchmarks + confidence  │
              │  Winner/Trending/Kill classify │
              └───────────────┬───────────────┘
                              │
                              │ feedback_generator.py
                              │ reads winners/losers
                              │ writes ai_brief.json
                              │
                              └──────────► back to AI-Generated
```

**Weekly cadence:** fetch organic → generate AI brief → drop media into `input_images/` → run pipeline → upload to Meta → sync metrics → repeat.


---

## 1. Creative Source: Organic Content

Proven short-form content auto-selected from shortsleaderboard by performance thresholds.

### Selection Criteria

| Filter        | Threshold                |
|---------------|--------------------------|
| Views         | >= 50,000                |
| Engagement    | >= 4%                    |
| Recency       | Last 30 days             |

### Script: `scripts/fetch_organic.py` (new)

Queries the shortsleaderboard Supabase instance (separate from the dashboard Supabase):

1. Query `creator_posts` table with threshold filters
2. Filter out already-processed posts via `organic_manifest.json`
3. Download videos via `yt-dlp`
4. Copy to `input_images/`
5. Append to `output/organic_manifest.json` for dedup across runs

### Design Decisions

- **No creator tagging.** Organic content runs as standard brand ads, not partnership/creator ads. This avoids the complexity of creator permissions, approval flows, and partnership ad APIs.
- **No approval UI.** Thresholds act as the quality gate. Content that clears 50k views + 4% engagement has already been validated by audience behavior.
- **Standard ads only.** No `branded_content_sponsor_page_id`, no creator identity on the ad. The content stands on its own.

### Environment Variables

| Variable              | Purpose                               |
|-----------------------|---------------------------------------|
| `SHORTS_SUPABASE_URL` | shortsleaderboard Supabase project URL |
| `SHORTS_SUPABASE_KEY` | shortsleaderboard Supabase anon key    |


---

## 2. Creative Source: AI-Generated Content

The existing pipeline IS the AI content engine. The feedback loop makes it smarter over time.

### Script: `scripts/feedback_generator.py` (new)

Reads performance data from Supabase and writes a structured brief that influences the next pipeline run.

**Flow:**
1. Query `metrics_cache` for all ads with sufficient spend (> $10)
2. Parse ad names (`concept/sub_group/filename`) for concept attribution
3. Classify each ad: winner / trending / kill (using same logic as dashboard)
4. Aggregate by concept: win rate, avg CPA, avg CTR, best copy excerpts
5. Write `brand/ai_brief.json`

### `brand/ai_brief.json` Schema

```json
{
  "iteration": 3,
  "generated_at": "2026-02-27T12:00:00Z",
  "winning_concepts": [
    {
      "name": "mechanism_education",
      "win_rate": 0.67,
      "avg_cpa": 52.30,
      "avg_ctr": 4.2,
      "top_copy": ["Best performing primary text...", "..."]
    }
  ],
  "losing_concepts": [
    {
      "name": "social_proof_stack",
      "kill_rate": 0.80,
      "avg_cpa": 145.00,
      "avg_ctr": 1.1
    }
  ],
  "top_headlines": ["Headline 1", "Headline 2"],
  "top_primary_texts": ["Primary text excerpt 1", "..."],
  "notes": "Mechanism education outperforming social proof 3:1 on CPA"
}
```

### Integration: `pipeline/brand_context.py`

When `brand/ai_brief.json` exists, `brand_context.py` loads it automatically (no flag needed) and injects the feedback into:

- **Pass 3 (Discover Categories):** Winning concepts become soft priors — the model is told which strategic angles have worked and which have failed. It can still discover new concepts, but has performance context.
- **Pass 4 (Copy Generation):** Top-performing copy excerpts and headlines are provided as style references. The model sees what language patterns drove conversions.

The brief acts as a soft prior, not a hard constraint. The pipeline can still discover new concepts and generate novel copy — it just has performance context.


---

## 3. The Pipeline (Passes 0–4)

Both creative sources drop media into `input_images/`. The pipeline runs identically regardless of source.

### Pass Table

| Pass | Name               | Input                        | Output                      | Checkpoint                   |
|------|--------------------|------------------------------|-----------------------------|------------------------------|
| 0    | Preprocess Videos  | `.mp4`, `.mov` files         | 3 JPEG frames + transcript  | `video_preprocessed.json`    |
| 1    | Describe Media     | Images + video thumbnails    | Visual descriptions          | `descriptions.json`          |
| 2    | Global Sub-group   | Image descriptions           | Visual clusters (8/batch)    | `global_subgroups.json`      |
| 2b   | Discover Video Hooks | Video descriptions          | Video hook categories        | `video_categories.json`      |
| 3    | Discover Concepts  | Image descriptions           | 6–12 strategic concepts      | `categories.json`            |
| 3b   | Label Sub-groups   | Sub-groups + concepts        | Concept → sub-group mapping  | `subgroup_labels.json`       |
| 3c   | Classify Videos    | Video descriptions + concepts| Video → concept mapping      | `video_classifications.json` |
| 4    | Generate Copy      | Grouped media + concepts     | 5 variations per concept     | `ad_copy_output.json`        |

### Key Pipeline Details

- **Visual-first clustering:** Images are clustered by CLIP visual similarity BEFORE concept classification. Sub-groups are then labeled with strategic concepts.
- **Video separate flow:** Videos get their own hook category discovery (2b) and classification (3c), then merge into the same ad set structure.
- **Checkpoint resume:** Each pass saves a JSON checkpoint. Pipeline resumes from last completed pass.
- **Model:** `claude-sonnet-4-5`, 10 concurrent API calls (configurable via `MAX_CONCURRENT`)
- **Discovery constraints:** 6–12 categories, no single category > 20% of images

### Upload Structure

```
Campaign (CBO, PAUSED, $200/day, lowest_cost_without_cap, outcome_sales)
├── Ad Set: "Ad Set - {concept_name}"
│   └── 1 ad per image in that concept
├── Ad Set: "Ad Set - {concept_name} (Video)"
│   └── 1 ad per video in that concept
└── ...repeat for each concept
```

- **Status:** PAUSED (manual review before go-live)
- **Targeting:** US, Women, 18–65, Advantage+ audience OFF
- **Attribution:** 7-day click, 1-day view, 1-day engaged view
- **Advantage+ creative:** `text_optimizations: OPT_IN`, all others `OPT_OUT`
- **CTA:** SHOP_NOW

### Ad Naming Convention

```
concept/sub_group/filename
```

This structural key is critical — it enables performance attribution back to concepts. Parsed by `parseAdName()` in `dashboard/lib/meta-fields.ts`.

### CLI Flags

```bash
python -m pipeline.run                  # Full pipeline (passes 0-4)
python -m pipeline.run --upload         # Full pipeline + upload to Meta
python -m pipeline.run --upload-only    # Upload existing output only
python -m pipeline.run --publish        # Publish to Supabase after pipeline
python -m pipeline.run --publish-only   # Publish to Supabase only
python -m pipeline.run --force          # Ignore checkpoints, re-run everything
python -m pipeline.run --subgroup-copy  # Unique copy per sub-group (default: per concept)
python -m pipeline.run --preprocess-only
python -m pipeline.run --describe-only
python -m pipeline.run --subgroup-only
python -m pipeline.run --discover-only
python -m pipeline.run --classify-only
python -m pipeline.run --generate-copy  # Pass 4 only
```


---

## 4. Performance Tracking

### Metrics Sync: `scripts/metrics_sync.py`

Syncs Meta Ads performance data to Supabase for the dashboard and feedback loop.

```bash
venv/bin/python scripts/metrics_sync.py                      # All active campaigns
venv/bin/python scripts/metrics_sync.py --campaign-id 12345  # Specific campaign
```

**Tables written:**

| Table             | Purpose                          | Key Fields                                              |
|-------------------|----------------------------------|---------------------------------------------------------|
| `metrics_cache`   | Current aggregate metrics        | entity_type, entity_id, campaign_id, name, insights     |
| `daily_snapshots` | Daily time-series (last 30 days) | entity_type, entity_id, date, insights                  |
| `sync_log`        | Execution audit trail            | status, campaigns/adsets/ads synced, error_message       |

**Insights fields:** impressions, clicks, spend, cpc, cpm, ctr, reach, frequency, actions, action_values, cost_per_action_type, video_avg_time_watched_actions, video_p50_watched_actions, video_p75_watched_actions

**Attribution windows:** 7-day click, 1-day view

### KPI Benchmarks

From `dashboard/lib/benchmarks.ts`:

**Soft benchmarks** (targeting + guidance):

| KPI        | Target   | Direction    |
|------------|----------|--------------|
| CTR        | > 3%     | Higher better |
| CPC        | < $1.50  | Lower better  |
| CPM        | $40–$50  | Range         |
| Hook Rate  | > 50%    | Higher better |
| Hold Rate  | > 25%    | Higher better |
| Frequency  | < 1.5    | Lower better  |

**Hard benchmarks** (conversion + profitability):

| KPI             | Target   | Direction    | Notes                        |
|-----------------|----------|--------------|------------------------------|
| CVR             | 3–5%     | Range        | Purchases / link clicks      |
| ATC Rate        | > 10%    | Higher better| Add-to-cart / link clicks    |
| ATC → Purchase  | > 30%    | Higher better| Purchases / ATC              |
| CPA             | < AOV    | Lower better | Dynamic: ~$70 for Spicy Cubes |

### Confidence Intervals

- **Proportions** (CTR, CVR, ATC, hook/hold): Wilson Score Interval (95% CI, z=1.96)
  - `none` (< 100 trials) → `low` (relative width > 100%) → `medium` (> 50%) → `high` (≤ 50%)
- **Monetary** (CPC, CPA, CPM, frequency): CLT-based (SE = mean / √count)
  - `none` (< 10) → `low` (< 30) → `medium` (< 100) → `high` (≥ 100)

### Ad Classification

From `dashboard/lib/winners.ts` and `dashboard/lib/recommendations.ts`:

**Recommendations:**

| Action    | Criteria                                                                   |
|-----------|----------------------------------------------------------------------------|
| Kill      | 0 purchases + spent > 3× CPA target ($210)                                |
| Kill      | 0 purchases + spent > 2× CPA target ($140) + 30+ link clicks              |
| Kill      | 1–4 purchases at CPA > 2× target                                          |
| Kill      | 5+ purchases but ROAS < 0.8                                               |
| Scale     | 3+ purchases + ROAS ≥ 1.0 + CPA ≤ 1.5× target ($105)                     |
| Watch     | Mixed signals, accumulating data (spend > $3 or 100+ impressions)          |
| Starving  | < 2% of campaign spend OR < $3 spend / < 100 impressions                  |

**Classifications:**

| Label    | Criteria                                                                          |
|----------|-----------------------------------------------------------------------------------|
| Winner   | Scale recommendation OR (3+ KPIs confidently passing + 0 failing + spend > $20)   |
| Trending | Watch + 3+ KPIs passing at point estimate + 0 hard KPIs failing + low/medium confidence + spend > $10 |
| Kill     | Everything else with sufficient spend                                              |


---

## 5. The Feedback Loop

The system improves each iteration through a numbered weekly sequence.

### Weekly Cycle

```
Week N:
  1. metrics_sync.py          → fresh performance data in Supabase
  2. feedback_generator.py    → brand/ai_brief.json (iteration N)
  3. fetch_organic.py         → new organic content in input_images/
  4. python -m pipeline.run   → pipeline reads ai_brief.json automatically
  5. --upload                 → new ads live on Meta (PAUSED for review)
  6. Review + unpause         → ads enter auction
  7. Wait for data            → metrics accumulate

Week N+1:
  Repeat from step 1 with new performance data
```

### What Improves Over Time

| Component            | How It Improves                                                    |
|----------------------|---------------------------------------------------------------------|
| Concept taxonomy     | Winning concepts reinforced, losing concepts deprioritized          |
| Copy patterns        | Top-performing text styles become style references for new copy     |
| Organic thresholds   | Can be tightened as we learn which organic signals predict ad success |
| Visual clustering    | CLIP distance threshold tunable based on which clusters produce winners |

### Source Competition

Both organic and AI-generated content compete in the same ad sets, organized by concept. This surfaces which source wins per concept:

- Organic content that clears performance thresholds gets concept-classified alongside AI content
- If organic content consistently wins within a concept, the feedback loop steers AI generation toward similar styles
- If AI content wins, organic thresholds can be adjusted


---

## 6. System Components & Files

### File Reference

| File                            | Type     | Purpose                                        |
|---------------------------------|----------|-------------------------------------------------|
| `pipeline/run.py`              | Existing | Main orchestrator, CLI entry point (Passes 0–4) |
| `pipeline/copy_generator.py`   | Existing | Claude API calls for all passes                 |
| `pipeline/meta_uploader.py`    | Existing | Facebook Marketing API upload                   |
| `pipeline/video_preprocessor.py` | Existing | ffmpeg + faster-whisper for video processing   |
| `pipeline/image_embedder.py`   | Existing | CLIP embeddings + agglomerative clustering      |
| `pipeline/config.py`           | Existing | Environment vars, paths, constants              |
| `pipeline/models.py`           | Existing | Pydantic models for structured output           |
| `pipeline/brand_context.py`    | Existing | PDF extraction + system prompt builders (+ ai_brief) |
| `pipeline/publisher.py`        | Existing | Publish pipeline output to Supabase             |
| `scripts/metrics_sync.py`      | Existing | Sync Meta Ads metrics to Supabase               |
| `scripts/fetch_organic.py`     | **New**  | Fetch organic content from shortsleaderboard     |
| `scripts/feedback_generator.py`| **New**  | Generate ai_brief.json from performance data     |
| `brand/ai_brief.json`          | **New**  | Performance feedback for pipeline (auto-generated) |
| `brand/03-avatar-sheet.pdf`    | Existing | Customer avatar + pain points                   |
| `brand/04-offer-brief.pdf`     | Existing | Product positioning + differentiation           |
| `brand/05-necessary-beliefs.pdf` | Existing | Strategic beliefs to establish                 |

### Dashboard Files

| File                                  | Purpose                                    |
|---------------------------------------|---------------------------------------------|
| `dashboard/lib/benchmarks.ts`         | KPI benchmark definitions + color thresholds |
| `dashboard/lib/winners.ts`            | Ad classification (winner/trending)          |
| `dashboard/lib/recommendations.ts`    | Kill/Watch/Scale/Starving logic              |
| `dashboard/lib/confidence.ts`         | Wilson Score + monetary confidence intervals |
| `dashboard/lib/metrics.ts`            | Compute metrics from raw Meta insights       |
| `dashboard/lib/meta-api.ts`           | Meta Ads API fetch logic                     |
| `dashboard/lib/meta-fields.ts`        | Fields, action types, `parseAdName()`        |
| `dashboard/lib/types.ts`             | TypeScript interfaces                        |
| `dashboard/lib/supabase.ts`          | Lazy Supabase client                         |

### Supabase Tables

**Dashboard Supabase (read-write):**

| Table             | Written By          | Purpose                         |
|-------------------|---------------------|---------------------------------|
| `pipeline_runs`   | publisher.py        | Campaign execution history       |
| `concepts`        | publisher.py        | Discovered creative concepts     |
| `ad_descriptions` | publisher.py        | Media descriptions               |
| `copy_variations` | publisher.py        | Generated ad copy                |
| `ad_mappings`     | publisher.py        | Ad name → concept/subgroup/file  |
| `metrics_cache`   | metrics_sync.py     | Current aggregate metrics        |
| `daily_snapshots` | metrics_sync.py     | Daily time-series metrics        |
| `sync_log`        | metrics_sync.py     | Sync execution log               |

**shortsleaderboard Supabase (read-only):**

| Table            | Read By            | Purpose                         |
|------------------|--------------------|----------------------------------|
| `creator_posts`  | fetch_organic.py   | Organic content with metrics     |

### Environment Variables

| Variable                      | Used By                    | Purpose                          |
|-------------------------------|----------------------------|----------------------------------|
| `ANTHROPIC_API_KEY`           | pipeline                   | Claude API                       |
| `META_APP_ID`                 | pipeline, metrics_sync     | Meta app credentials             |
| `META_APP_SECRET`             | pipeline, metrics_sync     | Meta app credentials             |
| `META_ACCESS_TOKEN`           | pipeline, metrics_sync, dashboard | Meta API access            |
| `META_AD_ACCOUNT_ID`          | pipeline, metrics_sync, dashboard | Ad account (auto-prefixed `act_`) |
| `META_PAGE_ID`                | pipeline                   | Facebook page for ads            |
| `META_INSTAGRAM_ACTOR_ID`     | pipeline                   | Instagram account (optional)     |
| `META_PIXEL_ID`               | pipeline                   | Conversion pixel                 |
| `META_CUSTOM_CONVERSION_ID`   | pipeline                   | Custom conversion for purchases  |
| `META_CUSTOM_EVENT_TYPE`      | pipeline                   | Event type (default: PURCHASE)   |
| `LANDING_PAGE_URL`            | pipeline                   | Ad destination URL               |
| `MAX_CONCURRENT`              | pipeline                   | Concurrent API calls (default: 10) |
| `CLIP_DISTANCE_THRESHOLD`     | pipeline                   | Visual similarity (default: 0.35) |
| `SUPABASE_URL`                | publisher, metrics_sync, dashboard | Dashboard Supabase URL     |
| `SUPABASE_KEY`                | publisher, metrics_sync, dashboard | Dashboard Supabase key     |
| `SHORTS_SUPABASE_URL`         | fetch_organic.py           | shortsleaderboard Supabase URL   |
| `SHORTS_SUPABASE_KEY`         | fetch_organic.py           | shortsleaderboard Supabase key   |


---

## 7. Implementation Roadmap

### Phase 1: `scripts/fetch_organic.py`

- Connect to shortsleaderboard Supabase (read-only)
- Query `creator_posts` with threshold filters (views >= 50k, engagement >= 4%, last 30 days)
- Download via yt-dlp to `input_images/`
- Write `output/organic_manifest.json` for dedup
- Test with dry-run flag

### Phase 2: `scripts/feedback_generator.py`

- Read `metrics_cache` from dashboard Supabase
- Parse ad names for concept attribution via `concept/sub_group/filename` format
- Apply winner/trending/kill classification (mirror dashboard logic)
- Aggregate by concept: win rate, avg CPA, avg CTR
- Extract top-performing copy from `copy_variations` table
- Write `brand/ai_brief.json`

### Phase 3: `pipeline/brand_context.py` ai_brief integration

- Load `brand/ai_brief.json` when present (file existence check, no flag)
- Inject winning/losing concept context into `build_discover_system()` (Pass 3)
- Inject top copy excerpts into `build_copygen_system()` (Pass 4)
- Soft priors only — model can still discover new concepts

### Phase 4: Scheduling

- Shell script or cron job for the weekly cycle:
  1. `venv/bin/python scripts/metrics_sync.py`
  2. `venv/bin/python scripts/feedback_generator.py`
  3. `venv/bin/python scripts/fetch_organic.py`
  4. `venv/bin/python -m pipeline.run --upload --publish`
- Consider: error handling, notifications, logging
