"""COMPUTE stage: per-creative aggregation, pool-split percentiles, two-tier
winners (Scale / F2 Medium creative), diagnosis grid, rollups.

Writes data/<week>/week.json (canonical, deterministic — no timestamps except
the window dates) and summary.txt (human-readable).

Decisions codified here (spec ambiguities, documented in README):
- Aggregation key is (pool, ad_name): the same creative name running in both
  prospecting and retargeting is evaluated once per pool, because DESIGN.md
  mandates separate percentile pools (RT hook/hold runs +10-15pp inflated).
- 'Any single top-decile (p90) signal' applies to the five measurable-metric
  paths (hook/hold/ctr/efficiency/intent), each still gated by its data floor;
  algorithm-favorite is a rule, not a distribution, so it has no p90 variant.
- 'Median ad spend this week' for algorithm-favorite = median of per-creative
  aggregate spend within the pool.
- Diagnosis: high = metric >= pool p75 (floor met), low = metric < pool p50;
  weak CVR = zero purchases, or CVR below the pool median CVR. The
  'hold rising -> trending' flag needs a prior week; it fires only if
  data/<prev-week>/week.json exists.
"""

from __future__ import annotations

import os

from .common import (load_json, percentile, prev_week_label, r6, save_json,
                     week_dir, week_window, REPO_ROOT)

POOLS = ("prospecting", "retargeting", "graveyard")
PATH_ORDER = ("hook", "hold", "ctr", "efficiency", "intent", "algorithm_favorite")

# Evolve buckets (see DESIGN.md / CHANGE 1). Order = Review Board order.
BUCKET_ORDER = ("breakthrough", "spend_winner", "kpi_winner", "loser")


# ------------------------------------------------------------------ aggregate

def aggregate(rows: list[dict]) -> list[dict]:
    """Aggregate per (pool, ad_name) across campaigns; keep instances."""
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        groups.setdefault((row["pool"], row["ad_name"]), []).append(row)

    aggs = []
    for (pool, name), members in sorted(groups.items()):
        members = sorted(members, key=lambda m: (-(m["metrics"]["spend"] or 0), m["ad_id"]))
        sums = {k: 0.0 for k in ("spend", "impressions", "reach", "video_3s_views",
                                 "video_p50_watched", "video_p100_watched", "thruplays",
                                 "purchases", "revenue", "atc", "initiated_checkout",
                                 "link_clicks")}
        watch_num = 0.0
        lt = {"spend": 0.0, "purchases": 0.0, "revenue": 0.0}
        lt_any = False
        for m in members:
            mm = m["metrics"]
            for k in sums:
                sums[k] += mm.get(k) or 0
            watch_num += (mm.get("avg_watch_seconds") or 0) * (mm.get("video_3s_views") or 0)
            if m.get("lifetime"):
                lt_any = True
                for k in lt:
                    lt[k] += m["lifetime"].get(k) or 0

        spend, imps = sums["spend"], sums["impressions"]
        v3s, p50 = sums["video_3s_views"], sums["video_p50_watched"]
        lead = members[0]
        agg = {
            "key": f"{pool}::{name}",
            "ad_name": name,
            "pool": pool,
            "is_video": any(m["is_video"] for m in members),
            "n_instances": len(members),
            "campaigns": sorted({m["campaign_name"] for m in members if m["campaign_name"]}),
            "batches": sorted({m["batch"] for m in members if m["batch"] is not None}),
            "retarget_creators": sorted({m["retarget_creator"] for m in members
                                         if m["retarget_creator"]}),
            "name_parsed": lead["name_parsed"],
            "transcript_match": lead["transcript_match"],
            "preview_link": lead["preview_link"],
            "instagram_permalink_url": lead["instagram_permalink_url"],
            "thumbnail_url": lead["thumbnail_url"],
            "video_id": lead["video_id"],
            "metrics": {
                "spend": r6(spend),
                "impressions": int(imps),
                "reach": int(sums["reach"]),  # summed across instances (approx; overlaps not dedupable)
                "frequency": r6(imps / sums["reach"]) if sums["reach"] > 0 else None,
                "video_3s_views": r6(v3s),
                "video_p50_watched": r6(p50),
                "video_p100_watched": r6(sums["video_p100_watched"]),
                "thruplays": r6(sums["thruplays"]),
                "avg_watch_seconds": r6(watch_num / v3s) if v3s > 0 else None,
                "purchases": r6(sums["purchases"]),
                "revenue": r6(sums["revenue"]),
                "atc": r6(sums["atc"]),
                "initiated_checkout": r6(sums["initiated_checkout"]),
                "link_clicks": r6(sums["link_clicks"]),
                "roas": r6(sums["revenue"] / spend) if spend > 0 else None,
                "cpa": r6(spend / sums["purchases"]) if sums["purchases"] > 0 else None,
                "thumbstop": r6(v3s / imps) if imps > 0 else None,
                "hold_rate": r6(p50 / v3s) if v3s > 0 else None,
                "link_ctr": r6(100.0 * sums["link_clicks"] / imps) if imps > 0 else None,
                "intent_rate": r6((sums["atc"] + sums["initiated_checkout"]) / spend)
                               if spend > 0 else None,
                "cvr": r6(sums["purchases"] / sums["link_clicks"])
                       if sums["link_clicks"] > 0 else None,
            },
            "lifetime": ({
                "spend": r6(lt["spend"]),
                "purchases": r6(lt["purchases"]),
                "revenue": r6(lt["revenue"]),
                "roas": r6(lt["revenue"] / lt["spend"]) if lt["spend"] > 0 else None,
            } if lt_any else None),
            "instances": [{
                "ad_id": m["ad_id"],
                "campaign_id": m["campaign_id"],
                "campaign_name": m["campaign_name"],
                "adset_id": m["adset_id"],
                "adset_name": m["adset_name"],
                "batch": m["batch"],
                "retarget_creator": m["retarget_creator"],
                "status": m["status"],
                "metrics": m["metrics"],
                "lifetime": m["lifetime"],
            } for m in members],
        }
        aggs.append(agg)
    return aggs


# ------------------------------------------------------------------ floors

def meets_floor(agg: dict, path_cfg: dict) -> bool:
    if path_cfg.get("video_only") and not agg["is_video"]:
        return False
    m = agg["metrics"]
    for field, minimum in (path_cfg.get("floor") or {}).items():
        if (m.get(field) or 0) < minimum:
            return False
    # metric must be computable
    metric = path_cfg.get("metric")
    if metric and m.get(metric) is None:
        return False
    return True


# ------------------------------------------------------------------ thresholds

def pool_thresholds(aggs: list[dict], cfg: dict) -> dict:
    """Per-pool percentile thresholds over the floor-gated sets."""
    pcts = cfg["percentiles"]
    total_acct_spend = sum(a["metrics"]["spend"] or 0 for a in aggs)
    out = {}
    for pool in POOLS:
        pool_aggs = [a for a in aggs if a["pool"] == pool]
        med_floor = cfg["paths"]["algorithm_favorite"].get("median_min_spend", 0.0)
        spends = sorted(a["metrics"]["spend"] for a in pool_aggs
                        if a["metrics"]["spend"] >= med_floor)
        pool_spend = sum(a["metrics"]["spend"] or 0 for a in pool_aggs)
        th = {"n_creatives": len(pool_aggs),
              "median_spend": r6(percentile(spends, 50)) if spends else None,
              "spend": r6(pool_spend),
              "spend_share": r6(pool_spend / total_acct_spend) if total_acct_spend > 0 else None,
              "paths": {}}
        for pname, pcfg in cfg["paths"].items():
            if pcfg["type"] == "rule":
                continue
            gated = [a["metrics"][pcfg["metric"]] for a in pool_aggs
                     if meets_floor(a, pcfg)]
            th["paths"][pname] = {
                "n_gated": len(gated),
                "p75": r6(percentile(gated, pcts["path_threshold"])),
                "p90": r6(percentile(gated, pcts["top_decile"])),
                "p50": r6(percentile(gated, pcts["diagnosis_low"])),
            }
        cvrs = [a["metrics"]["cvr"] for a in pool_aggs
                if a["metrics"]["cvr"] is not None]
        th["cvr_median"] = r6(percentile(cvrs, 50))
        out[pool] = th
    return out


# ------------------------------------------------------------------ scoring

def score(aggs: list[dict], thresholds: dict, cfg: dict, prev_holds: dict) -> None:
    be = cfg["breakeven_roas"]
    sr = cfg["scaling_roas"]
    st = cfg["scale_tier"]
    f2 = cfg["f2_inclusion"]
    fnd = cfg["funded"]
    routes = cfg["routes"]

    for a in aggs:
        m = a["metrics"]
        th = thresholds[a["pool"]]
        roas = m["roas"]
        spend = m["spend"] or 0
        purch = m["purchases"] or 0

        # ---- FUNDED axis: account-relative "Meta is feeding it above the pack".
        # NOT a literal 10%-of-account spend cutoff (breaks for a 500-ad account
        # where no single ad reaches 10%); reuse the algorithm_favorite logic:
        # funded = pool median spend > 0 AND spend >= 3x pool median AND >= $50.
        med = th["median_spend"]
        funded = (med is not None and med > 0
                  and spend >= fnd["spend_multiple_of_median"] * med
                  and spend >= fnd["min_spend_abs"])

        # ---- SIGNAL BADGES (unchanged machinery; now ride on top of any bucket,
        # they no longer define a tier). Keep is_scale only as a legacy input to
        # algorithm_favorite's "missed scale bar" gate.
        is_scale_legacy = (spend >= st["min_spend"] and purch >= st["min_purchases"]
                           and (roas or 0) > be)
        paths_hit, top_decile_hit = [], []
        for pname in PATH_ORDER:
            pcfg = cfg["paths"][pname]
            if pcfg["type"] == "rule":  # algorithm favorite
                bar = max(pcfg["spend_multiple_of_median"] * (med or 0),
                          pcfg.get("min_spend_abs", 0.0))
                hit = (med is not None and med > 0 and not is_scale_legacy
                       and bar > 0 and spend >= bar)
                if hit:
                    paths_hit.append(pname)
                continue
            if not meets_floor(a, pcfg):
                continue
            val = m[pcfg["metric"]]
            pth = th["paths"][pname]
            if pcfg["type"] == "percentile":
                hit = pth["p75"] is not None and val >= pth["p75"]
            else:  # fixed
                hit = True
                if "min_purchases" in pcfg:
                    hit = hit and purch >= pcfg["min_purchases"]
                if "min_roas" in pcfg:
                    hit = hit and (roas or 0) >= pcfg["min_roas"]
                if "min_value" in pcfg:
                    hit = hit and val >= pcfg["min_value"]
            if hit:
                paths_hit.append(pname)
            if (pname in f2["top_decile_paths"] and pth["p90"] is not None
                    and val is not None and val >= pth["p90"]):
                ok = True
                if pcfg["type"] == "fixed" and "min_purchases" in pcfg:
                    ok = purch >= pcfg["min_purchases"]
                if ok:
                    top_decile_hit.append(pname)

        has_signal = (len(paths_hit) >= f2["min_paths"]
                      or (f2["any_top_decile"] and bool(top_decile_hit)))
        has_meaningful_spend = spend >= fnd["min_spend_abs"]

        # ---- BUCKET logic (two axes: FUNDED? and hits scaling KPI?).
        bleeder = False
        if funded and roas is not None and roas >= sr:
            bucket = "breakthrough"
        elif funded and roas is not None and be <= roas < sr:
            bucket = "spend_winner"
        elif funded and (roas is None or roas < be):
            bucket = "loser"          # funded but unprofitable — urgent, pull it
            bleeder = True
        elif (not funded) and roas is not None and roas >= sr and purch >= st["min_purchases"]:
            bucket = "kpi_winner"
        elif has_meaningful_spend and (has_signal or (roas is not None and roas < be)):
            # non-funded, not a KPI winner, but spent real money with either a
            # signal to mine or a below-breakeven result -> a LOSER worth review.
            bucket = "loser"
        else:
            bucket = None             # small-and-fine: off the board, in All Ads

        route = routes.get(bucket or "none", routes["none"])

        a["funded"] = funded
        a["bucket"] = bucket
        a["bleeder"] = bleeder
        a["route"] = route
        a["signal_badges"] = paths_hit
        a["paths"] = paths_hit
        a["top_decile"] = top_decile_hit
        a["diagnosis"] = diagnose(a, th, prev_holds)


def diagnose(a: dict, th: dict, prev_holds: dict) -> dict:
    """Design-D grid, earliest-failing-stage logic."""
    m = a["metrics"]
    hp, op, cp = th["paths"]["hook"], th["paths"]["hold"], th["paths"]["ctr"]

    def hi(val, p):
        return val is not None and p["p75"] is not None and val >= p["p75"]

    def lo(val, p):
        return val is not None and p["p50"] is not None and val < p["p50"]

    hook_hi, hook_lo = hi(m["thumbstop"], hp), lo(m["thumbstop"], hp)
    hold_hi, hold_lo = hi(m["hold_rate"], op), lo(m["hold_rate"], op)
    ctr_hi = hi(m["link_ctr"], cp)
    weak_cvr = ((m["purchases"] or 0) == 0
                or (m["cvr"] is not None and th["cvr_median"] is not None
                    and m["cvr"] < th["cvr_median"]))

    text, verdict_hint = None, None
    if a["is_video"] and hook_hi and hold_lo:
        text = "Hook works, body loses them — rewrite middle, keep opener"
        verdict_hint = "Iterate-body"
    elif a["is_video"] and hook_lo and hold_hi:
        text = "Great body nobody sees — rebuild first 1.5s"
        verdict_hint = "Iterate-hook"
    elif hook_hi and ctr_hi and weak_cvr:
        text = "Ad works, page/offer doesn't"
        verdict_hint = "Build-LP"
    elif ctr_hi and (m["purchases"] or 0) == 0:
        text = "High CTR, no purchases — offer/LP problem, not creative"
        verdict_hint = "Build-LP"

    trending = False
    if hold_hi:
        prev = prev_holds.get(a["key"])
        if prev is not None and m["hold_rate"] is not None and m["hold_rate"] > prev:
            trending = True
            if text is None:
                text = "Hold ≥ p75 & rising — leading indicator (CPA follows hold by ~5-7d)"
    return {"text": text, "verdict_hint": verdict_hint, "trending": trending}


# ------------------------------------------------------------------ rollups

def _roll(rows: list[dict], key_fn, label_fn=None) -> list[dict]:
    groups: dict = {}
    for a in rows:
        k = key_fn(a)
        if k is None:
            continue
        groups.setdefault(k, []).append(a)
    out = []
    for k, members in sorted(groups.items(), key=lambda kv: str(kv[0])):
        spend = sum(a["metrics"]["spend"] or 0 for a in members)
        imps = sum(a["metrics"]["impressions"] or 0 for a in members)
        purch = sum(a["metrics"]["purchases"] or 0 for a in members)
        rev = sum(a["metrics"]["revenue"] or 0 for a in members)
        out.append({
            "key": k if isinstance(k, (str, int)) else list(k),
            "label": label_fn(members[0]) if label_fn else None,
            "n_creatives": len(members),
            "spend": r6(spend),
            "impressions": imps,
            "purchases": r6(purch),
            "revenue": r6(rev),
            "roas": r6(rev / spend) if spend > 0 else None,
            "cpa": r6(spend / purch) if purch > 0 else None,
            "n_breakthrough": sum(1 for a in members if a.get("bucket") == "breakthrough"),
            "n_spend_winner": sum(1 for a in members if a.get("bucket") == "spend_winner"),
            "n_kpi_winner": sum(1 for a in members if a.get("bucket") == "kpi_winner"),
            "n_loser": sum(1 for a in members if a.get("bucket") == "loser"),
        })
    out.sort(key=lambda x: (-(x["spend"] or 0), str(x["key"])))
    return out


def instance_rollup(rows: list[dict], key_fn, label_fn) -> list[dict]:
    """Rollup over per-instance rows (adset / campaign grain)."""
    groups: dict = {}
    for r in rows:
        k = key_fn(r)
        if k is None:
            continue
        groups.setdefault(k, []).append(r)
    out = []
    for k, members in sorted(groups.items(), key=lambda kv: str(kv[0])):
        spend = sum(m["metrics"]["spend"] or 0 for m in members)
        imps = sum(m["metrics"]["impressions"] or 0 for m in members)
        purch = sum(m["metrics"]["purchases"] or 0 for m in members)
        rev = sum(m["metrics"]["revenue"] or 0 for m in members)
        out.append({
            "key": k,
            "label": label_fn(members[0]),
            "n_ads": len(members),
            "spend": r6(spend),
            "impressions": imps,
            "purchases": r6(purch),
            "revenue": r6(rev),
            "roas": r6(rev / spend) if spend > 0 else None,
            "cpa": r6(spend / purch) if purch > 0 else None,
        })
    out.sort(key=lambda x: (-(x["spend"] or 0), str(x["key"])))
    return out


# ------------------------------------------------------------------ stage

def run(cfg: dict, week: str) -> None:
    d = week_dir(cfg, week)
    since, until = week_window(week)
    joined = load_json(os.path.join(d, "joined.json"))
    rows = joined["rows"]

    aggs = aggregate(rows)
    thresholds = pool_thresholds(aggs, cfg)

    # prior-week hold rates for the 'trending' flag (optional input)
    prev_holds: dict[str, float] = {}
    prev_path = os.path.join(REPO_ROOT, cfg["data_dir"], prev_week_label(week), "week.json")
    if os.path.exists(prev_path):
        prev = load_json(prev_path)
        for a in prev.get("creatives", []):
            hr = (a.get("metrics") or {}).get("hold_rate")
            if hr is not None:
                prev_holds[a["key"]] = hr

    score(aggs, thresholds, cfg, prev_holds)

    total_spend = sum(a["metrics"]["spend"] or 0 for a in aggs)
    total_purch = sum(a["metrics"]["purchases"] or 0 for a in aggs)
    total_rev = sum(a["metrics"]["revenue"] or 0 for a in aggs)

    # literal spend_share per aggregate (display/transparency only — the FUNDED
    # axis uses the account-relative 3x-pool-median test, not this share).
    for a in aggs:
        s = a["metrics"]["spend"] or 0
        a["spend_share"] = r6(s / total_spend) if total_spend > 0 else None

    # "one loser per batch" (Evolve): flag the highest-spend loser in each batch
    # as the batch's review pick. Batch = first parsed batch on the aggregate.
    losers_by_batch: dict = {}
    for a in aggs:
        a["batch_loser_pick"] = False
        if a["bucket"] == "loser":
            b = a["batches"][0] if a["batches"] else None
            cur = losers_by_batch.get(b)
            if cur is None or (a["metrics"]["spend"] or 0) > (cur["metrics"]["spend"] or 0):
                losers_by_batch[b] = a
    for a in losers_by_batch.values():
        a["batch_loser_pick"] = True

    bucket_rank = {b: i for i, b in enumerate(BUCKET_ORDER)}
    aggs.sort(key=lambda a: (bucket_rank.get(a["bucket"], len(BUCKET_ORDER)),
                             -(a["metrics"]["spend"] or 0), a["key"]))

    by_bucket = {b: [a for a in aggs if a["bucket"] == b] for b in BUCKET_ORDER}
    path_counts = {p: sum(1 for a in aggs if p in a["paths"]) for p in PATH_ORDER}
    board = [a for a in aggs if a["bucket"]]
    winner_path_counts = {p: sum(1 for a in board if p in a["paths"])
                          for p in PATH_ORDER}

    week_obj = {
        "week": week,
        "window": {"since": since, "until": until},
        "config": cfg,
        "totals": {
            "ads_with_spend": len(rows),
            "unique_creatives": len(aggs),
            "spend": r6(total_spend),
            "purchases": r6(total_purch),
            "revenue": r6(total_rev),
            "roas": r6(total_rev / total_spend) if total_spend > 0 else None,
        },
        "pools": thresholds,
        "tiers": {b: [a["key"] for a in by_bucket[b]] for b in BUCKET_ORDER},
        "counts": {
            "breakthrough": len(by_bucket["breakthrough"]),
            "spend_winner": len(by_bucket["spend_winner"]),
            "kpi_winner": len(by_bucket["kpi_winner"]),
            "loser": len(by_bucket["loser"]),
            "bleeders": sum(1 for a in aggs if a.get("bleeder")),
            "review_rows": len(board),
            "paths_all": path_counts,
            "paths_board": winner_path_counts,
        },
        "creatives": aggs,
        "rollups": {
            "concept": _roll(aggs,
                             lambda a: (a["name_parsed"]["concept"] or "(unparsed)"),
                             lambda a: a["name_parsed"]["concept"] or "(unparsed)"),
            # hook keyed by (concept, hook): 'Var1'-style variant names collide
            # across concepts if keyed on hook text alone
            "hook": _roll(aggs,
                          lambda a: ((a["name_parsed"]["concept"] or "?"),
                                     (a["name_parsed"]["hook"] or "?")),
                          lambda a: f'{a["name_parsed"]["concept"] or "?"} · '
                                    f'{a["name_parsed"]["hook"] or "?"}'),
            "batch": _roll(aggs, lambda a: a["batches"][0] if a["batches"] else None,
                           lambda a: f"Batch {a['batches'][0]}"),
            "adset": instance_rollup(rows, lambda r: r["adset_id"],
                                     lambda r: r["adset_name"]),
            "campaign": instance_rollup(rows, lambda r: r["campaign_id"],
                                        lambda r: r["campaign_name"]),
        },
    }
    save_json(os.path.join(d, "week.json"), week_obj)
    write_summary(os.path.join(d, "summary.txt"), week_obj)
    cnt = week_obj["counts"]
    print(f"[compute] {len(aggs)} creatives | breakthrough {cnt['breakthrough']} | "
          f"spend_winner {cnt['spend_winner']} | kpi_winner {cnt['kpi_winner']} | "
          f"loser {cnt['loser']} (bleeders {cnt['bleeders']}) | "
          f"wrote week.json + summary.txt")


def write_summary(path: str, w: dict) -> None:
    L = []
    t = w["totals"]
    L.append(f"WEEKLY REVIEW {w['week']}  ({w['window']['since']} .. {w['window']['until']}, Fri-Thu)")
    L.append("=" * 78)
    L.append(f"Ads with spend: {t['ads_with_spend']}   unique creatives: {t['unique_creatives']}")
    roas = f"{t['roas']:.2f}" if t["roas"] is not None else "-"
    L.append(f"Spend ${t['spend']:,.2f}   purchases {t['purchases']:.0f}   "
             f"revenue ${t['revenue']:,.2f}   account-attributed ROAS {roas}")
    L.append("")
    c = w["counts"]
    be = w["config"]["breakeven_roas"]
    sr = w["config"]["scaling_roas"]
    L.append(f"FUNDED = pool median>0 AND spend >= 3x pool median AND spend >= $50")
    L.append(f"  BREAKTHROUGHS (funded, ROAS >= {sr}):       {c['breakthrough']}")
    L.append(f"  SPEND WINNERS (funded, {be} <= ROAS < {sr}): {c['spend_winner']}")
    L.append(f"  KPI WINNERS   (not funded, ROAS >= {sr}):    {c['kpi_winner']}")
    L.append(f"  LOSERS        (funded-bleeder or spent+weak): {c['loser']}"
             f"  (bleeders: {c['bleeders']})")
    L.append(f"REVIEW ROWS TOTAL: {c['review_rows']}")
    L.append("")
    L.append("Signal badges (on-board / all creatives):")
    for p, n in c["paths_board"].items():
        L.append(f"  {p:<20} {n:>4} / {c['paths_all'][p]}")
    L.append("")
    for pool, th in w["pools"].items():
        L.append(f"Pool {pool}: {th['n_creatives']} creatives, "
                 f"median spend ${th['median_spend'] or 0:.2f}")
        for pname, pv in th["paths"].items():
            p75 = f"{pv['p75']:.4f}" if pv["p75"] is not None else "-"
            p90 = f"{pv['p90']:.4f}" if pv["p90"] is not None else "-"
            L.append(f"  {pname:<12} gated n={pv['n_gated']:<4} p75={p75}  p90={p90}")
    L.append("")
    L.append("TOP ROWS (bucket -> spend):")
    hdr = (f"{'bucket':<13}{'pool':<12}{'spend':>9}{'purch':>7}{'roas':>7}"
           f"{'thumb':>7}{'hold':>7}{'ctr':>7}  badges | name")
    L.append(hdr)
    L.append("-" * len(hdr))
    shown = [a for a in w["creatives"] if a["bucket"]][:50]
    for a in shown:
        m = a["metrics"]
        def fmt(v, pct=False):
            if v is None:
                return "-"
            return f"{v * 100:.1f}" if pct else f"{v:.2f}"
        tag = a["bucket"] + ("*" if a.get("bleeder") else "")
        L.append(f"{tag:<13}{a['pool']:<12}{m['spend']:>9.2f}"
                 f"{(m['purchases'] or 0):>7.0f}{fmt(m['roas']):>7}"
                 f"{fmt(m['thumbstop'], True):>7}{fmt(m['hold_rate'], True):>7}"
                 f"{fmt(m['link_ctr']):>7}  "
                 f"{','.join(a['signal_badges']) or '-'}"
                 f"{' [p90:' + ','.join(a['top_decile']) + ']' if a['top_decile'] else ''}"
                 f" | {a['ad_name'][:60]}")
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")
