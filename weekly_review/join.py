"""JOIN stage: parse ad names, batch numbers, attach metadata + transcripts,
derive per-instance metrics. Writes data/<week>/joined.json (deterministic).
"""

from __future__ import annotations

import difflib
import glob
import os
import re

from .common import (REPO_ROOT, action_value, first_action_value, load_json,
                     r6, save_json, week_dir, week_window)

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


# ---------------------------------------------------------------- name parsing

def parse_ad_name(name: str) -> dict:
    """Primary: 'label//concept//hook//PDP' (label = creator handle or STAT/VID).
    Fallback: JML names like
    'Jul26EvergreenBrandTOFSpicy CubesJordanStaticBold Headline'
    -> date prefix, author, format, trailing concept. Best-effort only."""
    out = {"parser": None, "label": None, "concept": None, "hook": None,
           "pdp": None, "author": None, "format": None, "date_prefix": None}
    if "//" in name:
        parts = [p.strip() for p in name.split("//")]
        out["parser"] = "standard"
        out["label"] = parts[0] or None
        if len(parts) > 1:
            out["concept"] = parts[1] or None
        if len(parts) > 2:
            out["hook"] = parts[2] or None
        if len(parts) > 3:
            out["pdp"] = parts[3] or None
        return out

    m = re.match(rf"^({'|'.join(MONTHS)})(\d{{1,2}})", name)
    if m:
        out["parser"] = "jml"
        out["label"] = "JML"
        out["date_prefix"] = m.group(0)
        rest = name[m.end():]
        # strip brand token if present
        rest = rest.replace("Spicy Cubes", "\x00").replace("SpicyCubes", "\x00")
        after_brand = rest.split("\x00")[-1]
        fm = re.search(r"([A-Z][a-z]+)?(Static|Video|UGC)(.*)$", after_brand)
        if fm:
            out["author"] = fm.group(1)
            out["format"] = fm.group(2)
            concept = fm.group(3).strip()
            out["concept"] = concept or None
        return out

    out["parser"] = "unparsed"
    return out


def parse_adset(adset_name: str) -> dict:
    """'Ad Set #22 - VID' -> batch 22; '<handle> - AT' -> creator retargeting."""
    out = {"batch": None, "retarget_creator": None}
    if not adset_name:
        return out
    m = re.search(r"#\s*(\d+)", adset_name)
    if m:
        out["batch"] = int(m.group(1))
        return out
    m = re.match(r"^(.*\S)\s*-\s*AT$", adset_name)
    if m:
        out["retarget_creator"] = m.group(1).strip()
    return out


# ---------------------------------------------------------------- transcripts

def _norm(s: str) -> str:
    return re.sub(r"[\W_]+", " ", (s or "").lower()).strip()


def load_transcripts() -> list[dict]:
    entries = []
    for path in sorted(glob.glob(os.path.join(REPO_ROOT, "output", "consolidated_*.json"))):
        try:
            data = load_json(path)
        except (ValueError, OSError):
            continue
        if not isinstance(data, list):
            continue
        for e in data:
            fn = e.get("ad_filename") or ""
            stem = re.sub(r"\.[A-Za-z0-9]+$", "", fn)
            concept, _, hook = stem.partition("-")
            entries.append({
                "source": os.path.basename(path),
                "ad_filename": fn,
                "concept_norm": _norm(concept),
                "hook_norm": _norm(hook),
                "transcript": e.get("transcript"),
            })
    entries.sort(key=lambda e: (e["source"], e["ad_filename"]))
    return entries


def match_transcript(concept: str | None, hook: str | None,
                     entries: list[dict], threshold: float) -> dict | None:
    """Concept must match (normalized equality/containment); hook prefix scored
    with difflib ratio. Deterministic: best score, ties broken by filename."""
    if not concept or not hook:
        return None
    cn, hn = _norm(concept), _norm(hook)
    if not cn or not hn:
        return None
    best = None
    for e in entries:
        if not e["concept_norm"]:
            continue
        if not (e["concept_norm"] == cn or cn in e["concept_norm"]
                or e["concept_norm"] in cn):
            continue
        k = min(len(hn), len(e["hook_norm"])) or 1
        score = difflib.SequenceMatcher(None, hn[:k + 10], e["hook_norm"][:k + 10]).ratio()
        if score >= threshold:
            key = (-score, e["ad_filename"])
            if best is None or key < best[0]:
                best = (key, e, score)
    if best is None:
        return None
    _, e, score = best
    return {"ad_filename": e["ad_filename"], "source": e["source"],
            "match_score": r6(score), "transcript": e["transcript"]}


# ---------------------------------------------------------------- metrics

def derive_metrics(row: dict) -> dict:
    spend = float(row.get("spend") or 0)
    imps = float(row.get("impressions") or 0)
    actions = row.get("actions") or []
    action_values = row.get("action_values") or []

    v3s = action_value(actions, "video_view")  # 3s views
    purchases = first_action_value(actions, ["omni_purchase", "purchase"])
    revenue = first_action_value(action_values, ["omni_purchase", "purchase"])
    atc = first_action_value(actions, ["omni_add_to_cart", "add_to_cart"])
    ic = first_action_value(actions, ["omni_initiated_checkout", "initiate_checkout"])
    link_clicks = action_value(actions, "link_click")
    p50 = action_value(row.get("video_p50_watched_actions") or [], "video_view")
    p100 = action_value(row.get("video_p100_watched_actions") or [], "video_view")
    thruplays = action_value(row.get("video_thruplay_watched_actions") or [], "video_view")
    avg_watch = action_value(row.get("video_avg_time_watched_actions") or [], "video_view")

    return {
        "spend": r6(spend),
        "impressions": int(imps),
        "reach": int(float(row.get("reach") or 0)),
        "frequency": r6(row.get("frequency")),
        "cpm": r6(row.get("cpm")),
        "video_3s_views": r6(v3s),
        "video_p50_watched": r6(p50),
        "video_p100_watched": r6(p100),
        "thruplays": r6(thruplays),
        "avg_watch_seconds": r6(avg_watch),
        "purchases": r6(purchases),
        "revenue": r6(revenue),
        "atc": r6(atc),
        "initiated_checkout": r6(ic),
        "link_clicks": r6(link_clicks),
        "roas": r6(revenue / spend) if spend > 0 else None,
        "cpa": r6(spend / purchases) if purchases > 0 else None,
        "thumbstop": r6(v3s / imps) if imps > 0 else None,
        "hold_rate": r6(p50 / v3s) if v3s > 0 else None,
        "link_ctr": r6(100.0 * link_clicks / imps) if imps > 0 else None,
        "intent_rate": r6((atc + ic) / spend) if spend > 0 else None,
        "cvr": r6(purchases / link_clicks) if link_clicks > 0 else None,
    }


def classify_pool(campaign_name: str, cfg: dict) -> str:
    pc = cfg["pool_classification"]
    cn = (campaign_name or "").lower()
    # Graveyard/Zombie CBO: its own pool so dying ads don't drag down the
    # prospecting percentile distribution. Checked first (a graveyard campaign
    # named "...Retargeting..." would still be a graveyard).
    for p in pc.get("graveyard_campaign_name_contains", []):
        if p.lower() in cn:
            return "graveyard"
    for p in pc["retargeting_campaign_name_contains"]:
        if p.lower() in cn:
            return "retargeting"
    return pc["default_pool"]


# ---------------------------------------------------------------- stage

def run(cfg: dict, week: str) -> None:
    d = week_dir(cfg, week)
    since, until = week_window(week)
    insights = load_json(os.path.join(d, "raw_insights.json"))
    ads_meta = load_json(os.path.join(d, "raw_ads.json"))
    adsets_meta = load_json(os.path.join(d, "raw_adsets.json"))
    lt_path = os.path.join(d, "raw_lifetime.json")
    lifetime = {}
    lifetime_complete = False
    if os.path.exists(lt_path):
        lt = load_json(lt_path)
        lifetime_complete = bool(lt.get("complete"))
        for r in lt.get("rows", []):
            lifetime[r["ad_id"]] = r

    entries = load_transcripts()
    threshold = cfg["join"]["hook_similarity_threshold"]
    print(f"[join] {len(insights)} insight rows; {len(entries)} transcript entries; "
          f"lifetime {'complete' if lifetime_complete else 'partial/missing'} "
          f"({len(lifetime)} ads)")

    rows = []
    matched_transcripts = 0
    parser_counts: dict[str, int] = {}
    for r in insights:
        ad_id = r["ad_id"]
        name = r.get("ad_name") or ""
        meta = ads_meta.get(ad_id) or {}
        adset = adsets_meta.get(r.get("adset_id")) or {}
        parsed = parse_ad_name(name)
        parser_counts[parsed["parser"]] = parser_counts.get(parsed["parser"], 0) + 1
        adset_parsed = parse_adset(r.get("adset_name") or adset.get("name") or "")
        creative = meta.get("creative") or {}
        metrics = derive_metrics(r)
        is_video = bool(creative.get("video_id")) or (metrics["video_3s_views"] or 0) > 0

        tr = match_transcript(parsed["concept"], parsed["hook"], entries, threshold)
        if tr:
            matched_transcripts += 1

        lt_row = lifetime.get(ad_id)
        lt_metrics = None
        if lt_row:
            lt_spend = float(lt_row.get("spend") or 0)
            lt_rev = first_action_value(lt_row.get("action_values") or [],
                                        ["omni_purchase", "purchase"])
            lt_purch = first_action_value(lt_row.get("actions") or [],
                                          ["omni_purchase", "purchase"])
            lt_metrics = {
                "spend": r6(lt_spend),
                "purchases": r6(lt_purch),
                "revenue": r6(lt_rev),
                "roas": r6(lt_rev / lt_spend) if lt_spend > 0 else None,
            }

        rows.append({
            "ad_id": ad_id,
            "ad_name": name,
            "adset_id": r.get("adset_id"),
            "adset_name": r.get("adset_name") or adset.get("name"),
            "campaign_id": r.get("campaign_id"),
            "campaign_name": r.get("campaign_name"),
            "pool": classify_pool(r.get("campaign_name") or "", cfg),
            "status": meta.get("status"),
            "adset_status": adset.get("status"),
            "adset_daily_budget": adset.get("daily_budget"),
            "preview_link": meta.get("preview_shareable_link"),
            "creative_id": creative.get("id"),
            "video_id": creative.get("video_id"),
            "thumbnail_url": creative.get("thumbnail_url"),
            "instagram_permalink_url": creative.get("instagram_permalink_url"),
            "is_video": is_video,
            "name_parsed": parsed,
            "batch": adset_parsed["batch"],
            "retarget_creator": adset_parsed["retarget_creator"],
            "transcript_match": tr,
            "metrics": metrics,
            "lifetime": lt_metrics,
        })

    rows.sort(key=lambda x: x["ad_id"])
    out = {
        "week": week,
        "window": {"since": since, "until": until},
        "lifetime_complete": lifetime_complete,
        "parser_counts": dict(sorted(parser_counts.items())),
        "transcripts_matched": matched_transcripts,
        "rows": rows,
    }
    save_json(os.path.join(d, "joined.json"), out)
    print(f"[join] wrote joined.json: {len(rows)} rows, parsers {out['parser_counts']}, "
          f"{matched_transcripts} transcript matches")
