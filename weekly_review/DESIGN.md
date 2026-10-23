# Weekly Meta Review — Agreed Design (Stage 1, signed off 2026-07-31)

Cole-approved 2026-07-31 via ask_cole: **F2 Medium formula · Fri–Thu window · 6-verdict set ·
Drive-hosted videos.** This doc is the build spec for Stage 2. Read-only against Meta, always
(CLAUDE.md Rule 0 applies to reads too: discover live campaigns, never hardcode).

## Purpose

Creative feedback loop, not a reporting dashboard. "There's no point in knowing what worked if
you don't know why it worked." Reviewing last week's ads IS deciding next week's ads. The
artifact supplies the Friday meeting (Cole, Gabe, Alex, Roberto): people talk over it, assign
verdicts, leave with next week's creative direction.

## Scope

Account `act_1862723677525967`, ALL live campaigns discovered at runtime (currently #4
Retargeting, #5 Testing, #6 Interest, JML Scale, JML Graveyard). Ad-level + ad-set-level.
~530 ads with spend / ~$22k per week as of 2026-07-31.

## Review window

**Fri–Thu (last 7 full days), built Friday morning.** Attribution 7d-click + 1d-view (account
convention, matches metrics_sync.py). Late-Thursday conversions may restate; each weekly run
re-pulls a 28-day lookback and updates prior weeks' raw data tabs (Meta restates conversions).

## Two-tier winners

### Tier 1 — Scale winners
≥$100 spend + ≥3 purchases + ROAS > breakeven. "Scale THIS ad."
**Breakeven is a CONFIG value: 1.40 as of 2026-07-31 (Cole; supersedes the 1.47 used in the
07-27 winners-collect).** ROAS gates ONLY this tier — sub-breakeven ads still surface as
creative winners via non-ROAS paths (hook/hold/CTR/intent/algorithm-favorite); that is the
point of the two-tier design (Cole re-confirmed 2026-07-31).

### Tier 2 — Creative winners (F2 Medium, Cole-approved)
Signal worth the creative team's attention even if not scalable as-is.

**Universal gate:** not already a scale winner; per-creative aggregation (dedupe the same
creative name across campaigns — evaluate the aggregate, show per-campaign in drill-down).

**Six signal paths** (percentiles = account-relative, recomputed weekly over the gated pool;
computed SEPARATELY for prospecting vs retargeting — retargeting hook/hold runs +10–15pp
inflated, so #4 and other RT ads compare only against each other):

| Path | Rule | Data floor |
|---|---|---|
| Hook | thumbstop (3s views/imps) ≥ acct p75 | ≥500 imps (video) |
| Hold | p50-watched/3s views ≥ acct p75 | ≥300 3s views |
| CTR | link CTR ≥ acct p75 | ≥1,000 imps |
| Efficiency | ≥1 purchase AND ROAS ≥ 2.0 | ≥500 imps |
| Intent | (ATC+IC)/spend ≥ 0.4 | ≥$15 spend |
| Algorithm favorite | ad spend ≥ 3× median ad spend this week, missed scale bar | — |

**Inclusion (F2): 2+ paths, OR any single top-decile (p90) signal.** Last-7d dry run: 10 scale
+ ~32 creative winners ≈ 42 review rows.

**Tuning levers, in order (the weekly conversation with Cole):** per-path percentile (p75→p85),
data floors, top-N cap, variant-dedupe to best variant. Badges on every row show WHICH paths
fired, so dilution is self-evident and tunable by feel.

**Rationale notes:** account thumbstop p50 ≈ 45% vs industry "good" 30% — fixed industry
thresholds would flood; percentiles self-calibrate. Research consensus: percentile > z-score
on fat-tailed ad metrics; avoid single weighted-score inclusion (averages away spiky
specialists — exactly what a creative team wants to see). Weighted score used ONLY as a sort
key within tier, never for inclusion.

## Auto-diagnosis column (Design-D grid; the "why" operationalized)

Earliest-failing-stage logic, per row:
- High hook + low hold → "Hook works, body loses them — rewrite middle, keep opener" (→ Iterate-body)
- Low hook + high hold → "Great body nobody sees — rebuild first 1.5s" (highest-ROI quadrant → Iterate-hook)
- High hook + high CTR + weak CVR → "Ad works, page/offer doesn't" (→ Build-LP candidate)
- High CTR + no purchases → offer/LP problem, not creative
- Hold ≥ p75 & rising → leading indicator (hold moves ~5–7 days ahead of CPA) → "trending" flag

## Verdicts (6, colored chips)

**Scale / Adapt / Build-LP / Iterate-hook / Iterate-body / Kill.** Verdicts + notes + owner are
the human touchpoint; read back after the meeting → next-week briefs for Gabe/Alex. Next week's
sheet includes a "Last Week's Verdicts → what happened" tab (accountability loop).

## Integration with the Team Growth Guide (AD ROADMAP) — added 2026-07-31

The creative team's working doc is the **"Team Growth Guide (Spicy Cubes)"** sheet
(`1ztbbZ8hC9zhYUrhP0MWTJ-dbT4smMJcowgA955qjzD8`), AD ROADMAP tab: one row per
concept/brief — STATUS ×2, UPVOTE, BATCH #, dates, AUTHOR (Gabe), EXECUTOR (Alex),
AD CONCEPT, DESIRE/CORE AVATAR, SUB AVATAR, ANGLE(S), BREAKTHROUGH MEMO (why/what/how),
AWARENESS LEVEL (Schwartz), FILE TYPE, AD TYPE (Iteration/new), LINK TO BRIEF (Milanote),
LINK TO AD (FB), RESULTS, LEARNINGS. Master Fields dropdowns include RESULTS values
"Winning Ad Found" and "Poor Spend Great CPA" — their taxonomy already anticipates the
two-tier split. The weekly review is the roadmap's RESULTS/LEARNINGS engine:

1. **Join keys:** BATCH # ↔ ad-set/batch numbers; AD CONCEPT ↔ ad-name concept segment.
   Weekly review adds a **per-batch rollup** (spend/purch/ROAS/tier counts per BATCH #) —
   the grain the team ships in.
2. **Roadmap Feed section in the Meeting Brief:** per matched roadmap row, paste-ready
   RESULTS (in their vocabulary: Breakthrough / Winning Ad Found / Poor Spend Great CPA /
   no-signal) + a drafted LEARNINGS line (diagnosis + key numbers + hook text). Gabe
   pastes/edits — we do NOT write into their working doc unasked (v1; direct write via
   Drive is an opt-in later).
3. **Verdicts → draft roadmap rows:** each Adapt/Iterate-hook/Iterate-body/Build-LP verdict
   generates a pre-filled candidate AD ROADMAP row (AD TYPE = Iteration, BREAKTHROUGH MEMO
   drafted from diagnosis + data, LINK TO AD = FB preview/IG permalink, concept/avatar
   fields carried from the source ad). "Reviewing IS deciding next week's ads," literally.
4. **Column vocabulary alignment:** Review Board carries Batch #, Awareness Level and
   Angle where derivable (from roadmap join; else blank), plus an auto "Roadmap result"
   column mapping tiers → their RESULTS labels. FB ad links (preview_shareable_link /
   IG permalink) included so executors get LINK TO AD for free.
5. **Taxonomy seeding (offer, not scope):** our transcript+concept corpus can help
   populate their SUB AVATARS/ANGLES and DESIRES tabs (being built now).
NOTE: verdicts NEVER auto-execute against Meta. Pausing/scaling is Cole's manual act (ad-level
pause doesn't hold; $447 scar; observe-never-touch).

## Artifact structure

Drive: `Spicy Cubes — Weekly Reviews / 2026-Wnn (Mon dd–dd) /`
- **Review Sheet** (copied from hand-built template — colored verdict chips can't be created
  via API; template holds chips, conditional formats, frozen panes; values written via gspread)
- `videos/` — review-tier creatives only, deduped across weeks via manifest (creative/video_id
  → Drive file ID). Folder = permanent archive + grid-browse view. Anyone-with-link-view
  (required for IMAGE() thumbnails).
- `archive/` — raw pull JSON, consolidated_*.json snapshot, transcripts. After this step runs,
  clearing output/ locally is always safe.

Sheet tabs:
1. **Meeting Brief** — auto-written narrative: week vs last week, tier clearances, movers,
   policy blocks, fatigue warnings, suggested agenda.
2. **Review Board** — one row per review-tier creative: thumbnail
   (`=HYPERLINK(drive_video_url, IMAGE("https://drive.google.com/thumbnail?id=…&sz=w400",4,120,214))`
   — click → Drive streaming player), tier + path badges, hook text, concept, KPIs (spend,
   purch, ROAS, CPA, thumbstop, hold, CTR, avg watch, freq), transcript excerpt, auto-diagnosis,
   Verdict/Notes/Owner. Sorted tier → spend. IG permalink column for partnership ads.
3. **Concepts & Hooks** — rollups by concept and hook across campaigns (the unfair advantage),
   plus per-BATCH # rollup (the team's shipping grain, joins to AD ROADMAP).
4. **Ad Sets & Campaigns** — ad-set + campaign rollups incl. JML.
5. **All Ads** — full drill-down, every ad with spend.
6. **Last Week's Verdicts** — decision follow-through.

## Backend / write path (decided)

- Python in this repo (`weekly-review/` scripts), facebook_business SDK / Graph v21+.
- Insights: async report job pattern (singer-io tap-facebook style: backoff, poll, 28-day
  lookback), `level=ad`, fields incl. video_p25–p100, thruplay, avg_time, outbound_clicks,
  actions/action_values, purchase_roas. 3s views = actions[video_view].
- Creative join: `/ads?fields=creative{thumbnail_url,video_id,instagram_permalink_url,…}` —
  thumbnail_urls EXPIRE in days → download bytes at build time, host in Drive.
- Concept/hook join: parse `label//concept//hook//PDP` (521/530 ads); fallback parser for JML
  naming (`Jul26Evergreen…`); transcripts from consolidated_*.json + weekly transcript manifest.
- **Sheets writes: gspread under Cole's USER OAuth** (service accounts have 0 Drive quota —
  cannot create files even in shared folders; consumer Gmail, no Workspace/Shared Drives).
  One-time browser consent, cached token. gspread values + raw batch_update for extras;
  template copy carries chip formatting. Batch all writes (quota 60 write req/min).
- Video uploads to Drive: same user OAuth.
- Architecture cron-ready: single `run_weekly_review.py` entrypoint so a scheduled Friday agent
  can drive it later.

## Weekly runbook

1. (Fri am) Read-only pull: insights last Fri–Thu + 28d lookback restatement; ad/creative
   metadata; discover live campaigns.
2. Join concept/hook/transcript; aggregate per creative; compute tiers, paths, diagnosis.
3. Archive: snapshot consolidated_*.json + raw pull to Drive `archive/`; upload new
   review-tier videos (dedupe manifest).
4. Copy template → fill tabs → write Meeting Brief.
5. Friday meeting: team assigns verdicts in-sheet.
6. (Post-meeting) Read verdicts back → generate next-week creative brief + draft AD ROADMAP
   rows for Adapt/Iterate/Build-LP verdicts + paste-ready RESULTS/LEARNINGS lines for
   matched roadmap rows; append to verdict log.

## One-time setup (Stage 2 prerequisites)

- Cole: user-OAuth consent for Sheets+Drive scopes.
- Hand-build the template sheet once (colored chip dropdowns are UI-only).
- Transcript recovery pass for cleared EN batches: videos still in Meta → re-download source,
  Whisper, rebuild transcript manifest for review-tier ads. (Cole picked "Full: Drive-hosted";
  recovery pass proposed as fast-follow — confirm before spending the compute.)

## Data-survival facts (verified 2026-07-31)

- consolidated_en.json gone from output/ (March statics version tracked in git
  `PrevConsolidated/`); 50-video hot-peach transcript archive gone; winners_collect JSON gone.
- Survives: `~/Desktop/Send/spicy-cubes-winners-2026-07-14/` (12 winners + media),
  consolidated_es.json (current 13), renamed_videos/ (26 current files).
- Ad names carry concept/hook independently of local files — the join is durable.
- Meta API retention limits (2026): 6–13 months on some breakdowns; our weekly Drive archive is
  the durable history.
