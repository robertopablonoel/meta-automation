# Meta Ads Dashboard — Instructions for Claude

## What This Is
A standalone HTML dashboard that displays Meta ad copy organized by creative concept category, pulled from the pipeline output at:
`/Users/colefreeman/Desktop/meta-automation/output/consolidated.json`

## How to Run It
The dashboard is a **single self-contained HTML file** — no server needed.
Just open it in a browser:
```
open /Users/colefreeman/Desktop/meta-automation/dashboard/meta-ads-dashboard.html
```

## Data Structure (consolidated.json)
Each entry in the JSON has:
- `filename` — the video file (e.g., `Kamila1.mov`)
- `creative_concept` — the category this video belongs to
- `sub_group` — a slug version of the filename
- `ad_copy_variations` — array of 5 objects, each with:
  - `primary_text`
  - `headline`
  - `description`

**Key insight:** All videos in the same `creative_concept` share the same 5 ad copy variations. The dashboard deduplicates — it shows the copy once per category and lists all video names in that category.

## Current Categories (as of March 2026)
| Category Key | Display Name | Videos |
|---|---|---|
| `comparacion_producto_superior` | Comparación: Producto Superior | Kamila1, Kamila3, Kamila8, Kamila11 |
| `testimonio_resultados_confrontacional` | Testimonio: Resultados Confrontacional | Kamila4, Kamila7, Kamila9, Kamila10 |
| `perdida_identidad_maternal` | Pérdida de Identidad Maternal | Kamila6, Kamila12 |
| `secreto_insider_revelado` | Secreto Insider Revelado | Kamila2, Kamila5 |

## Dashboard Features
- **Tabbed variations** — click Variación 1–5 to switch between ad copy variants
- **Individual copy buttons** — per field (Primary Text, Headline, Description)
- **"Copiar Todo" button** — copies all 3 fields formatted for easy pasting into Meta Ads Manager
- **Color theme** — Spicy Cubes brand palette (`#faf1e0` cream bg, `#7b1c14` maroon, `#ff473b` red-orange, `#FCA5A5` peach)

## If consolidated.json Changes
The dashboard has the data **hardcoded** in the `<script>` block. If the pipeline reruns and produces new output, you'll need to:
1. Re-read `/Users/colefreeman/Desktop/meta-automation/output/consolidated.json`
2. Extract categories, videos, and ad copy variations
3. Update the `data` array in `meta-ads-dashboard.html`

A quick way to re-extract:
```bash
python3 -c "
import json
from collections import defaultdict
with open('/Users/colefreeman/Desktop/meta-automation/output/consolidated.json') as f:
    data = json.load(f)
groups = defaultdict(list)
for item in data:
    groups[item['creative_concept']].append(item['filename'])
for concept, videos in groups.items():
    print(concept, videos)
"
```

## Related Files
- `consolidated.json` → `/Users/colefreeman/Desktop/meta-automation/output/consolidated.json`
- `ad_copy_output.json` → `/Users/colefreeman/Desktop/meta-automation/output/ad_copy_output.json`
- Pipeline scripts → `/Users/colefreeman/Desktop/meta-automation/scripts/`
- This dashboard → `/Users/colefreeman/Desktop/meta-automation/dashboard/meta-ads-dashboard.html`

## Context
Cole is doing a Miami internship at a startup. This pipeline processes creator UGC videos → transcripts → organizes by theme/hook → generates Meta ad copy. Cole runs the pipeline and uses this dashboard to identify which videos map to which ad groups for upload into Meta Ads Manager.
