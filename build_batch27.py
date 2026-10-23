"""Batch 27 uploader: JML static board -> ONE combined STAT ad set in Campaign #5.
Each ad = one concept-creative with BOTH aspect ratios auto-placed via placement
asset customization (asset_customization_rules; square->feeds, vertical->stories/reels).
Per-category copy from output/batch27_selections.json (single headline/body). PAUSED.

Usage:
  venv/bin/python build_batch27.py --dry-run
  venv/bin/python build_batch27.py --limit=1                 # probe: create set + 1 ad
  venv/bin/python build_batch27.py --adset-id=<id> --skip=1  # rest into existing set
"""
import os, json, sys, time, re
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(".env")
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adimage import AdImage
from facebook_business.adobjects.adcreative import AdCreative
from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.adset import AdSet

APP=os.getenv("META_APP_ID"); SEC=os.getenv("META_APP_SECRET"); TOK=os.getenv("META_ACCESS_TOKEN")
FacebookAdsApi.init(app_id=APP, app_secret=SEC, access_token=TOK, api_version="v21.0")
ACCT="act_"+os.getenv("META_AD_ACCOUNT_ID","").replace("act_","")
PAGE=os.getenv("META_PAGE_ID"); IG=os.getenv("META_INSTAGRAM_ACTOR_ID"); LANDING=os.getenv("LANDING_PAGE_URL")
C5="120248135757060467"
URL_TAGS=("utm_source=facebook&utm_medium=paid&utm_campaign={{campaign.name}}"
          "&utm_term={{adset.name}}&utm_content={{ad.name}}&fbadid={{ad.id}}"
          "&tw_source={{site_source_name}}&tw_adid={{ad.id}}")

DRY   = "--dry-run" in sys.argv
LIMIT = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--limit=")), 0) or 0)
SKIP  = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--skip=")), 0) or 0)
ADSET = next((a.split("=")[1] for a in sys.argv if a.startswith("--adset-id=")), "")

media_map   = json.load(open("output/batch27_media_map.json"))
selections  = json.load(open("output/batch27_selections.json"))
consolidated= json.load(open("output/consolidated_en.json"))
concept_by_slug = {r["filename"]: r.get("creative_concept") for r in consolidated}

IMG_CACHE_P="output/batch27_image_cache.json"
img_cache = json.load(open(IMG_CACHE_P)) if os.path.exists(IMG_CACHE_P) else {}
def upload_image(path):
    if path in img_cache: return img_cache[path]
    im=AdImage(parent_id=ACCT); im[AdImage.Field.filename]=path; im.remote_create()
    h=im[AdImage.Field.hash]; img_cache[path]=h
    json.dump(img_cache, open(IMG_CACHE_P,"w")); return h

# placement customization: square = catch-all (platforms, no positions); vertical overrides story/reels
SQUARE_SPEC={"publisher_platforms":["facebook","instagram","audience_network","messenger"]}
VERT_SPEC={"publisher_platforms":["facebook","instagram"],
           "facebook_positions":["story","facebook_reels"],
           "instagram_positions":["story","reels"]}

BROAD={"geo_locations":{"countries":["US"],"location_types":["frequently_in","home","recent"]},
       "age_min":18,"age_max":65,"user_age_unknown":True,
       "targeting_automation":{"advantage_audience":1},
       "excluded_custom_audiences":[{"id":"120232389795780467"}],
       "brand_safety_content_filter_levels":["FACEBOOK_RELAXED","AN_RELAXED"]}
PROMO={"pixel_id":"2641325006045972","custom_event_type":"PURCHASE","smart_pse_enabled":False}
ATTR=[{"event_type":"CLICK_THROUGH","window_days":7}]
ADSET_NAME="Ad Set #27 - JML-static-board - STAT - Broad - All Purchases"

def build_ads():
    ads=[]
    for slug, info in media_map.items():
        concept=concept_by_slug.get(slug)
        sel=selections.get(concept)
        if not sel:
            print("  SKIP (no selection):", slug, concept); continue
        code=info.get("concept_code","SC")
        variant=re.sub(r"[^A-Za-z0-9]+","_", info.get("title", slug)).strip("_")[:40]
        ads.append({"slug":slug,"concept":concept,"code":code,"variant":variant,
                    "square":info["base_1x1"],"vertical":(info["ratios_9x16"] or [info["base_1x1"]])[0],
                    "headline":sel["headline"],"body":sel["primary_text"],"desc":sel["description"]})
    ads.sort(key=lambda a:a["slug"])
    return ads

def make_creative(ad):
    sq=upload_image(ad["square"]); vt=upload_image(ad["vertical"])
    afs={"images":[{"hash":sq,"adlabels":[{"name":"square"}]},
                   {"hash":vt,"adlabels":[{"name":"vertical"}]}],
         "bodies":[{"text":ad["body"]}],
         "titles":[{"text":ad["headline"]}],
         "ad_formats":["SINGLE_IMAGE"],
         "call_to_action_types":["SHOP_NOW"],
         "link_urls":[{"website_url":LANDING}],
         "asset_customization_rules":[
             {"customization_spec":SQUARE_SPEC,"image_label":{"name":"square"}},
             {"customization_spec":VERT_SPEC,"image_label":{"name":"vertical"}}]}
    if ad["desc"]: afs["descriptions"]=[{"text":ad["desc"]}]
    params={AdCreative.Field.name:f"Creative - {ad['code']} {ad['variant']}",
            AdCreative.Field.object_story_spec:{"page_id":PAGE,"instagram_user_id":IG},
            "asset_feed_spec":afs, AdCreative.Field.url_tags:URL_TAGS}
    cr=AdAccount(ACCT).create_ad_creative(params=params); return cr["id"]

def main():
    acct=AdAccount(ACCT)
    ads=build_ads()
    if SKIP: ads=ads[SKIP:]
    if LIMIT: ads=ads[:LIMIT]
    print(f"batch27: {len(ads)} ads | page {PAGE} ig {IG} | landing set={bool(LANDING)}")
    if DRY:
        for a in ads[:5]:
            print(f"  [{a['code']}] {a['concept']} :: H={a['headline']!r} sq={Path(a['square']).name!r} vt={Path(a['vertical']).name!r}")
        print("  ...(dry run, no writes)"); return
    # ad set
    existing_names=set()
    if ADSET:
        adset_id=ADSET; print("REUSING ad set", adset_id)
        for ad in AdSet(adset_id).get_ads(fields=["name"], params={"limit":200}):
            existing_names.add(ad.export_all_data().get("name"))
        print(f"  {len(existing_names)} ads already in set (will skip duplicates)")
    else:
        params={"name":ADSET_NAME,"campaign_id":C5,"status":"PAUSED",
                "optimization_goal":"OFFSITE_CONVERSIONS","billing_event":"IMPRESSIONS",
                "destination_type":"WEBSITE","attribution_spec":ATTR,"promoted_object":PROMO,
                "targeting":BROAD}
        adset_id=acct.create_ad_set(params=params)["id"]; print("adset_id:", adset_id)
    log={"adset_id":adset_id,"ads":[],"errors":[]}
    logp=f"output/batch27_upload_{int(time.time())}.json"
    for a in ads:
        name=f"STAT//{a['concept']}//{a['code']}_{a['variant']}//PDP"[:180]
        if name in existing_names:
            print("  skip (exists):", name); continue
        for attempt in range(4):
            try:
                cid=make_creative(a)
                ad=acct.create_ad(params={Ad.Field.name:name,Ad.Field.adset_id:adset_id,
                    Ad.Field.status:Ad.Status.paused,Ad.Field.creative:{"creative_id":cid}})
                log["ads"].append({"ad_id":ad["id"],"name":name,"slug":a["slug"]})
                print(f"  ad {ad['id']} | {name}")
                break
            except Exception as e:
                msg=str(e)
                if "too many" in msg.lower() or "#17" in msg or "error_subcode': 2446079" in msg:
                    print(f"  rate-limited, backoff 300s (attempt {attempt+1})"); time.sleep(300); continue
                log["errors"].append({"slug":a["slug"],"err":msg[:300]}); print(f"  FAILED {a['slug']}: {msg[:200]}"); break
        json.dump(log, open(logp,"w"), indent=2)
        time.sleep(2)
    print(f"DONE: {len(log['ads'])} ads, {len(log['errors'])} errors | log {logp}")

if __name__=="__main__": main()
