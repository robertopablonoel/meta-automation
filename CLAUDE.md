# Meta Pipeline — Operator Protocol (PRECEDENCE PROTOCOL)

This file is the standing instruction set for Claude sessions operating the Meta
ads pipeline in this repo. It was written 2026-07-06 with Cole, after building
the full three-campaign system end to end. **This is the current protocol. Do
not invent a new one.** If anything here conflicts with what you find in the
live ad account, the live account wins — that is the core rule.

## Rule 0 — Precedence: the LIVE account is the template, always

Before ANY upload of new creatives:

1. **SDK-read the current state first.** Read the destination campaign, its ad
   sets, and 2–3 of its currently-running ads *including creatives* before
   building anything. Model every payload off what is ACTUALLY RUNNING, not off
   docs, memory, this file's examples, or prior configs.
2. **Read-shape ≠ write-shape.** What the API returns for a working ad is not
   necessarily what you POST to create one (partnership sponsor fields, thumbnail
   hash-vs-url, promoted_object variants have all bitten us). When a write fails
   against a read-derived payload, suspect the payload shape before permissions.
3. **Verify by read-back after every run**: ad count, url_tags present,
   identity (page/IG) correct, statuses. An upload isn't done until read back.

Practical reads (venv python, repo root):
- `python -m scripts.meta_list campaigns` / `adsets --campaign-id X` (read-only)
- Direct SDK/Graph reads for ad-set targeting and creative fields — see
  `scripts/meta_upload_partnership.py` docstrings for field lists.

## The three-campaign lifecycle (Cole's operating model)

New creatives flow: **test → winners → distribution**. Never skip stage 1.
**Only stage 1 (Campaign #5 testing) receives raw new batches.** Campaigns #4
and #6 receive ONLY proven winners, cycled in deliberately later — never a whole
fresh batch (Cole-confirmed 2026-07-08). Video note: uploads dedupe via
`output/video_upload_cache.json` (Meta re-ingests videos every upload); run the
testing/upload that does the real video upload first, later runs reuse cached
video_ids. `create_ad_video` can 413 on some large files (~100MB+) — ffmpeg
re-encode (crf 28) and retry; a post-upload poll disconnect ≠ upload failure.

1. **TESTING — CBO broad** (`Campaign #5 - CBO - 7dc - Broad - English`,
   id 120248135757060467). Every new creative batch goes here first, as ONE new
   STAT ad set (naming: `Ad Set #NN - STAT - Broad - All Purchases`, NN =
   account-wide next number). Template: Advantage+ audience ON, exclude
   custom audience "Klaviyo - Purchasers in Last 30d" (120232389795780467),
   US 18–65 frequently_in/home/recent, PURCHASE pixel 2641325006045972,
   7d-click, brand identity creatives. Meta ad cap is ~75 ads/set: fill the
   current STAT set until ~66–75, then start the next-numbered set (don't
   restart learning on a full set). Cole's go-forward CBO floor: each STAT set
   gets a **10% minimum-spend** target. It is NOT settable via
   `min_budget_spend_percentage` alone (Meta 400 subcode 3858462 "must include
   the total limit value"). Write the ABSOLUTE target = 10% of the campaign
   daily budget, e.g. campaign daily $1000 → `daily_min_spend_target: 10000`
   (cents); send it TOGETHER with `min_budget_spend_percentage: 10` in one
   AdSet.api_update so both the target and the % display populate (matches #18).
   The uploader doesn't set this — apply it via SDK post-create, then read back.
2. **WINNERS → INTEREST ABO** (`Campaign #6 - ABO - 7dc - Interest Testing -
   English`, id 120248135927330467). Proven creatives cycle into its 5
   women-only interest ad sets (Personal Development / Broad / Health &
   wellness / Online Shopping / Motherhood & Parenting). ABO: budgets live on
   ad sets, each set needs `bid_strategy: LOWEST_COST_WITHOUT_CAP`; an ABO
   campaign create requires `is_adset_budget_sharing_enabled: false`.
3. **WINNERS → CREATOR RETARGETING CBO** (`Campaign #4 - CBO - 7dc -
   Retargeting - English`, id 120248131065590467). Winners also upload as
   PARTNERSHIP ads: one ad set per creator (`<handle> - AT`), audiences
   IG 365 (120239391225220467) + FB 365 (120239391228920467) +
   `UGC Eng 365 (<handle>)`, Advantage+ OFF with relaxation disabled. CBO here
   is deliberate: it prioritizes the best-performing creator. (Cole may later
   move this to ABO for guaranteed per-creator coverage — that would be a NEW
   Cole-ordered change, not something to do proactively.)

## Upload procedure (every run, no exceptions)

1. sha256 + `.bak` copy of `output/meta_upload_config.json` before editing it.
2. Surgically edit the config (campaign_name / ad_set_name / ad_set_spec /
   partnership block). The uploader is `scripts/meta_upload_partnership.py`
   (handles brand + partnership statics; `meta_upload.py` is the legacy
   video-only path — leave it untouched).
3. **Dry-run first, show Cole the target lines.** Dry-run verifies audiences
   via SDK reads and prints exactly what will be created.
4. **No real upload without Cole's explicit, current instruction.** One full
   real run per ad set (`--campaign-id` to reuse a campaign, `--adset-id` to
   fill an existing set; never chain --limit into a full run).
5. Read-back verification (count / url_tags / identity / status), then report
   with the `upload_log_*.json` path.
6. Everything lands PAUSED at the AD level, and that per-ad status is the ONLY
   spend gate — do NOT assume campaigns are paused. As of 2026-07-08 Campaigns
   #4/#5/#6 are LIVE and spending; new ads land PAUSED *inside live campaigns*
   and sit inert until individually activated. Always SDK-read real
   campaign/ad-set/ad status (Rule 0) instead of trusting creation-time state;
   verify configured status == PAUSED on read-back (effective IN_PROCESS just
   means ad review). Meta also auto-activates ad sets on create (known quirk).

## Partnership ads (creator identity) — validated recipe

- Creator registry: `GET /17841459852690609/branded_content_ad_permissions`
  (our brand IG) → per creator: `creator_ig_id`, `creator_fb_page_id`,
  `permission_status`. Only use `Approved` creators.
- Creative payload: `object_story_spec.page_id` = **creator's own FB page**,
  `instagram_user_id` = **creator's IG**, plus BOTH sponsor declarations:
  `instagram_branded_content: {"sponsor_id": "17841459852690609"}` and
  `facebook_branded_content: {"sponsor_page_id": "116804498178903"}`, plus
  `branded_content: {"ad_format": 3}` and the full url_tags. The sponsor fields
  are what route authorization through the creator's grant — without them you
  get 1815199/1341012 regardless of token scopes.
- Creator **eligibility is enforced at publish time** (error 3867089 blaming
  page_id) even when the grant reads Approved — a new creator's first run is
  their eligibility test. Not fixable from our side.
- Do NOT assign creator pages/IGs in Business Manager — they're the creators'
  own assets; the grant is the access mechanism.

## Invariants (verify against live ads if in doubt — Rule 0)

- url_tags, exactly:
  `utm_source=facebook&utm_medium=paid&utm_campaign={{campaign.name}}&utm_term={{adset.name}}&utm_content={{ad.name}}&fbadid={{ad.id}}&tw_source={{site_source_name}}&tw_adid={{ad.id}}`
- Brand identity: page 116804498178903 + IG 17841459852690609 (spicycubes.co).
- Ad naming: `<label>//<concept>//<hook-or-variant>//PDP` (label = creator
  handle for partnership, `STAT` for brand statics).
- Objective OUTCOME_SALES, CTA SHOP_NOW → LANDING_PAGE_URL from `.env`.
- Do not send `degrees_of_freedom_spec` (API rejects; Meta defaults apply).
- Credentials: system-user token ("meta-pipeline", app "static-ad-pipeline",
  never expires, has instagram branded-content scopes since 2026-07-06). Redact
  every token (`EAA…`) from anything printed or logged.

## Error decoder (all personally encountered 2026-07-06)

| Error | Meaning | Fix |
|---|---|---|
| 1815199 "Ad account has no access to IG account" | normal-identity check ran against a creator IG | add sponsor fields (partnership payload) |
| 1341012 "No permission to access this profile" | token/system-user can't act as that page, or partnership not declared | sponsor fields; check asset assignment only for OUR pages |
| 3867089 "isn't in compliance with eligibility" | creator account ineligible for partnership ads | creator-side problem; pick another creator |
| 1885183 "app in development mode" | app can't create dark posts | app must be Live (historical; static-ad-pipeline is Live) |
| code 17 "too many API calls" | ad-account rate limit | back off ≥5 min; batch reads with field expansion |
| "is_adset_budget_sharing_enabled" required | ABO campaign create | send `false` |
| "Bid Amount ... Required" on ad set | ABO ad set without bid strategy | `bid_strategy: LOWEST_COST_WITHOUT_CAP` |
| 1504040 "Attribution Window Update ... No Longer Supported" | attribution_spec is IMMUTABLE after ad-set creation | replace: new ad set with right attribution, recreate ads (reuse creative ids), delete old set after verify |

## Standing constraints

- Meta API writes ONLY as part of a Cole-ordered upload; reads are free.
- Never delete/overwrite the KEEP set (`renamed_videos/`, `consolidated_*.json`,
  `meta_upload_config.json`, `upload_log_*.json`, `_archive/`).
- `scripts/meta_upload_partnership.py` is the operator uploader (uncommitted as
  of 2026-07-06 — baseline-commit before editing it, precedent c58b17f).
- Session history of how all this was derived: wiki + upload logs 1783375301
  (diaries), 1783375578 (crave), 1783376346 (broad CBO), 1783377394 (ABO).
