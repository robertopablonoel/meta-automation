# weekly_review — deterministic core of the weekly Meta ads review

Spec: `DESIGN.md` (Cole-approved 2026-07-31). READ-ONLY against Meta — this
package only issues GET requests (CLAUDE.md Rule 0). No LLM calls; same inputs
produce byte-identical `week.json`.

## Run

```
venv/bin/python -m weekly_review.run --week 2026-W31 --stage all
venv/bin/python -m weekly_review.run --week 2026-W31 --stage pull --force
```

Stages (each reads the previous stage's cached artifact):

| Stage | Input | Output (in `weekly_review/data/<week>/`) |
|---|---|---|
| `pull` | Graph API v21.0 (GET only) | `raw_campaigns.json`, `raw_insights.json`, `raw_ads.json`, `raw_adsets.json`, `raw_lifetime.json` |
| `join` | raw_* + `output/consolidated_*.json` | `joined.json` |
| `compute` | `joined.json` | `week.json` (canonical), `summary.txt` |
| `publish` | — | **stub** (Drive/Sheets is Stage 2; needs user OAuth + template sheet) |

- Review window is **Fri–Thu**: for `YYYY-Www`, the Thursday of that ISO week
  back to the previous Friday (2026-W31 → 2026-07-24..2026-07-30).
- `pull` skips anything already cached unless `--force`. The lifetime pull
  (`date_preset=maximum`) is tolerant and resumable: partial progress is saved
  with its paging cursor and resumed on the next run.
- Credentials come from `.env` (`META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`),
  loaded ONLY via explicit absolute dotenv paths (bare `load_dotenv()` crashes
  under `-m` execution). Tokens (`EAA…`) are redacted from all output.

## What compute does

Per DESIGN.md: per-creative aggregation, prospecting-vs-retargeting percentile
pools, Tier 1 scale winners (≥$100, ≥3 purchases, ROAS > breakeven 1.40 —
config), Tier 2 F2-Medium creative winners over six signal paths
(hook/hold/ctr/efficiency/intent/algorithm-favorite, each with its own data
floor), inclusion = 2+ paths OR any single p90 signal, Design-D diagnosis grid,
and concept/hook/batch/ad-set/campaign rollups.

Config lives in `config.json` — breakeven, floors, percentile levels,
retargeting name patterns, attribution windows, field lists. Tuning levers
(p75→p85, floors) are config edits, not code edits.

### Decisions made where the spec was ambiguous

- **Aggregation key is `(pool, ad_name)`** — a creative running in both
  prospecting and retargeting becomes one row per pool, because percentile
  pools are mandated to be separate (RT hook/hold inflation).
- **p90 single-signal inclusion** applies to the five measurable paths
  (hook/hold/ctr/efficiency/intent) with their floors; algorithm-favorite is a
  binary rule with no p90 variant. Efficiency p90 additionally requires ≥1
  purchase.
- **Algorithm-favorite median** = median per-creative aggregate spend within
  the pool; "missed scale bar" enforced.
- **Diagnosis grid**: high = ≥ pool p75 (path floor met), low = < pool p50;
  weak CVR = zero purchases or CVR < pool median. The "hold rising → trending"
  flag requires a prior `data/<prev-week>/week.json` and stays off otherwise.
- **Hook/hold paths are video-only** (per the "≥500 imps (video)" floor);
  statics still qualify via ctr/efficiency/intent/algorithm-favorite.
- `reach`/`frequency` on aggregates are summed/recomputed across instances
  (cross-ad audience overlap is not dedupable from the API).
