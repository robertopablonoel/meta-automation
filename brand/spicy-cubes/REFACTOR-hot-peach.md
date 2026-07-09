# Brand Pack Refactor — Pineapple Dailies → Hot Peach (2026-07-08)

We stopped advertising **Spicy Cubes Dailies (Pineapple)** on Meta and repurposed
this pipeline for the **Spicy Cubes Hot Peach Edition** product. This is the record
of the copy-instruction refactor.

## Where the pipeline is instructed to write product copy (the path)
`brand/spicy-cubes/instructions.md` → its `## BRAND DOCS` list → those files are
text-extracted (PDF for EN historically, `es/*.txt` for ES) and concatenated into
the copy-gen system prompt, alongside the parsed `## COPY RULES` and
`## COPY STYLE GUIDELINES` sections. `pipeline/brand_context.py::load_brand_context`
does the assembly; `_get_copy_rules`/`_get_copy_style` inject the parsed sections.

**Important mechanics discovered:** for EN the loader read `BRAND_DIR/<doc>` where the
BRAND DOCS list named the **`.pdf`** files — so editing the `.md` files did nothing
until BRAND DOCS was repointed to `.md`. It now points to `.md` (text-editable).

## What the OLD (Pineapple) pack said — preserved in git
Full old brand pack is at commit **a4f541d** (branch `brand-agnostic-refactor`),
files `brand/spicy-cubes/{instructions,03-avatar-sheet,04-offer-brief,05-necessary-beliefs}.md`
(+ `.pdf` + `es/*.txt`). Its product story: a **daily enzyme-based gummy** built on
"clinical doses / you were underdosed / 600mg fenugreek + 500mg tribulus + 30mg
saffron + 120mg bromelain + 12mg ginger / oversized 6g gummy 3x bigger / no
probiotics / 365-day guarantee / 4.8★ 35+–350+ reviews." None of that is true for
Hot Peach.

## Hot Peach product facts (source: spicycubes.com/products/spicy-cubes-hot-peach-edition)
- On-demand **botanical aphrodisiac cube** (peach-flavored), taken ~30 min before
  intimacy; effect ~1–3 hrs; also builds with consistent use (Cole-confirmed keep
  the cumulative angle). Max 1 cube/day.
- 4 botanicals, **no disclosed mg doses**: **Chili Pepper** (endorphin rush),
  **Muira Puama** (libido), **Maca Root** (energy/vitality), **Epimedium** (desire).
- **4.5 stars / 273 reviews**, **30-day returns**, free shipping, cancel anytime,
  discreet shipping.

## What changed in this refactor
- **instructions.md — REWRITTEN** (EN + ES): brand identity, headline/description
  examples, style guidelines, ingredient guidance — all Hot Peach, all dose-claim /
  enzyme / probiotic / 90-365-day / 4.8-350 language removed. This file drives the
  bulk of generation quality. BRAND DOCS repointed `.pdf`→`.md`.
- **03-avatar-sheet.md — LIGHT FIX**: avatar psychology kept (product-agnostic —
  "the woman who lost her spark"); one product-claim line ("wants clinical doses
  listed") neutralized. Her *past attempts* (tried fenugreek/probiotics) kept — that's
  her real history, not a product claim.
- **04-offer-brief.md + 05-necessary-beliefs.md — PENDING FULL REWRITE** from a real
  Hot Peach brief (Cole supplying). Temporarily removed from BRAND DOCS so their
  Pineapple mechanism can't feed the model in the interim. Re-add once rewritten.
- ES mirror (`es/*.txt`) still Pineapple — out of Meta scope for now; rewrite when
  the EN briefs are done if ES generation is needed again.

## Interim generation state (safe)
EN copy currently generates from: rewritten instructions.md + avatar sheet only.
Accurate but thinner context until the two briefs are rebuilt.
