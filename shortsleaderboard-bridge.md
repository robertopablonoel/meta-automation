# Plan: Organic → Paid Ads Bridge

  ## Context

  We want to feed best-performing organic TikTok/IG videos and TikTok Shop videos into Meta Ads as partnership ads. Weekly workflow: creators tag posts as
  ad-eligible, brand approves top performers in a dashboard, approved videos get downloaded and run through the full Claude pipeline (describe → classify
  → copygen → upload) as partnership ads with per-creator `instagram_user_id`.

  Two separate systems involved:
  - **shortsleaderboard** (React + Fastify + Supabase) — creator/content management
  - **meta-automation** (Python pipeline) — ad copy generation + Meta upload

  Architecture: Approval UI lives in shortsleaderboard. A bridge script in meta-automation fetches approved videos, downloads them, and feeds them into
  the existing pipeline with a new `--partnership` flag.

  ---

  ## Phase 1: Supabase Schema (shortsleaderboard)

  Add to shortsleaderboard Supabase:

  **New column on `creator_posts`:**
  - `ad_eligible BOOLEAN DEFAULT FALSE` — creator toggles this per-post

  **New column on `social_handles`:**
  - `instagram_user_id TEXT` — their IG user ID for partnership ads (brand fills in or creator provides)

  **New table `ad_candidates`:**
  ```sql
  CREATE TABLE ad_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID REFERENCES creator_posts(id),
    status TEXT DEFAULT 'pending',  -- pending | approved | rejected | uploaded
    approved_at TIMESTAMPTZ,
    batch_id UUID REFERENCES ad_batches(id),
    meta_ad_id TEXT,  -- filled after upload
    created_at TIMESTAMPTZ DEFAULT now()
  );
  ```

  **New table `ad_batches`:**
  ```sql
  CREATE TABLE ad_batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT,
    status TEXT DEFAULT 'draft',  -- draft | approved | processing | uploaded | failed
    created_at TIMESTAMPTZ DEFAULT now(),
    processed_at TIMESTAMPTZ,
    campaign_id TEXT  -- Meta campaign ID after upload
  );
  ```

  **File:** `shortsleaderboard/supabase/migrations/YYYYMMDD_ad_pipeline.sql`

  ---

  ## Phase 2: Creator "Ad Eligible" Toggle (shortsleaderboard frontend)

  Add a toggle/checkbox on the creator's post management UI so they can mark individual posts as `ad_eligible = true`.

  **Where:** Creator member dashboard — find existing post list component, add a toggle column.

  **File:** New component in `shortsleaderboard/apps/frontend/src/components/` or inline in existing posts page.

  ---

  ## Phase 3: Approval Dashboard (shortsleaderboard frontend)

  New tab/page in the **brand dashboard** (`BrandDashboard.tsx` already has a tab pattern).

  **"Ad Candidates" tab shows:**
  - All posts where `ad_eligible = true` OR (TikTok Shop posts above performance threshold)
  - Filterable by: platform, creator, views, engagement
  - Sortable by views/engagement
  - Each row: thumbnail, creator name, platform, metrics (views, likes, shares), caption preview
  - Bulk select + "Approve for Ads" button → creates `ad_candidates` rows with status `approved`, groups into an `ad_batch`
  - Batch history table showing past batches + their status

  **Key files:**
  - `shortsleaderboard/apps/frontend/src/pages/brand/BrandDashboard.tsx` — add new tab
  - New: `shortsleaderboard/apps/frontend/src/components/brand/AdCandidatesTable.tsx`
  - New: `shortsleaderboard/apps/frontend/src/components/brand/BatchHistory.tsx`

  **API routes needed (Fastify backend):**
  - `GET /api/ad-candidates` — returns eligible posts with metrics + creator info
  - `POST /api/ad-candidates/approve` — bulk approve selected posts into a batch
  - `GET /api/ad-batches` — list batches with status
  - New file: `shortsleaderboard/apps/backend/src/routes/ad-candidates.ts`

  ---

  ## Phase 4: Bridge Script (meta-automation)

  **New file: `scripts/fetch_approved.py`**

  This script connects to shortsleaderboard's Supabase, fetches approved batches, downloads videos, and prepares them for the pipeline.

  ```
  Flow:
  1. Query ad_candidates WHERE status = 'approved' (optionally filter by batch_id)
  2. Join with creator_posts + social_handles to get: post_url, platform, instagram_user_id, creator name
  3. Download each video via yt-dlp to input_images/
  4. Write creator_metadata.json mapping filename → creator info
  5. Update ad_candidates status to 'processing'
  6. Invoke pipeline: python -m pipeline.run --partnership
  7. On success, update batch status to 'uploaded', write back meta_ad_id
  ```

  **`creator_metadata.json` format:**
  ```json
  {
    "video_abc.mp4": {
      "creator_name": "Jane",
      "instagram_user_id": "17841400123456",
      "tiktok_handle": "@jane",
      "post_url": "https://tiktok.com/...",
      "post_caption": "Try this amazing...",
      "organic_views": 150000,
      "organic_likes": 12000
    }
  }
  ```

  **Environment:** Needs `SHORTS_SUPABASE_URL` + `SHORTS_SUPABASE_KEY` in `.env` (shortsleaderboard Supabase credentials).

  **Dependencies:** `yt-dlp` (add to requirements.txt)

  ---

  ## Phase 5: Pipeline Modifications (meta-automation)

  ### 5a. New `--partnership` flag in `pipeline/run.py`

  - Reads `creator_metadata.json` from output dir (or input dir)
  - Sets `partnership_mode = True` in pipeline context
  - Passes creator metadata through to meta_uploader

  ### 5b. Update `pipeline/meta_uploader.py`

  **Current:** Uses global `META_INSTAGRAM_ACTOR_ID` for all ads.

  **Change:** When `partnership_mode = True`:
  - Each video ad uses the creator's `instagram_user_id` from metadata
  - Falls back to `META_INSTAGRAM_ACTOR_ID` if not provided
  - Partnership ads only get 1 copy variation (Meta limitation for partnership video ads — uses `variations[0]`)

  **Key change in `_create_ads_parallel`:**
  - Currently builds 7-element tuples: `(ad_set_id, ad_name, creative_spec, status, ad_set_name, concept_name, is_video)`
  - Add `instagram_user_id` as optional 8th element (default `None` for backward compat)
  - In `object_story_spec`, use per-video `instagram_user_id` when provided

  ### 5c. Update `pipeline/config.py`

  - Add `CREATOR_METADATA_FILE = OUTPUT_DIR / "creator_metadata.json"`
  - Add `PARTNERSHIP_MODE` flag (default `False`, set by CLI arg)

  ### 5d. Copy generation awareness

  In `pipeline/copy_generator.py`, when partnership mode:
  - Include creator handle / organic caption in the prompt context so Claude can reference the creator's voice
  - Still generate copy variations, but only `variations[0]` will be used per ad

  ---

  ## Phase 6: Backward Compatibility

  - All existing pipeline flows unchanged when `--partnership` is not passed
  - `meta_uploader.py` tuple handling: check tuple length, use global `META_INSTAGRAM_ACTOR_ID` for 7-element tuples
  - `creator_metadata.json` is only read when `--partnership` flag is set
  - No changes to existing checkpoint files or formats

  ---

  ## Implementation Order

  1. Phase 1 — Supabase migration in shortsleaderboard
  2. Phase 2 — Creator ad-eligible toggle UI
  3. Phase 3 — Brand approval dashboard + API routes
  4. Phase 4 — Bridge script (`scripts/fetch_approved.py`)
  5. Phase 5 — Pipeline `--partnership` flag + per-video `instagram_user_id`
  6. Phase 6 — Test end-to-end

  ## Files Modified/Created

  **shortsleaderboard (new):**
  - `supabase/migrations/YYYYMMDD_ad_pipeline.sql`
  - `apps/frontend/src/components/brand/AdCandidatesTable.tsx`
  - `apps/frontend/src/components/brand/BatchHistory.tsx`
  - `apps/frontend/src/pages/brand/BrandDashboard.tsx` (add tab)
  - `apps/backend/src/routes/ad-candidates.ts`

  **meta-automation (new):**
  - `scripts/fetch_approved.py`

  **meta-automation (modified):**
  - `pipeline/run.py` — `--partnership` arg + metadata loading
  - `pipeline/config.py` — new constants
  - `pipeline/meta_uploader.py` — per-video `instagram_user_id`, 1 variation for partnership
  - `pipeline/copy_generator.py` — creator context in prompts
  - `requirements.txt` — add `yt-dlp`

  ## Verification

  1. Run migration in shortsleaderboard Supabase
  2. Test creator toggle sets `ad_eligible` on a post
  3. Test approval dashboard shows eligible posts and creates batches
  4. Test bridge script downloads a video and writes `creator_metadata.json`
  5. Test `python -m pipeline.run --partnership` with a downloaded video
