"""Read-only Meta listings: campaigns and ad sets, as one JSON object on stdout.

Standalone usage (from the repo root, under the repo venv):
    python -m scripts.meta_list campaigns
    python -m scripts.meta_list adsets --campaign-id 120210000000000000

Mirrors scripts/meta_upload.py's init pattern (.env at repo root, Graph API
v21.0) but makes ONLY read calls — no object is ever created or mutated.
Output shapes match the meta-pipeline app's CLI-bridge contract:
    campaigns → {"ok": true, "account_id", "campaigns": [{id, name, status,
                 objective, created_time}]}
    adsets    → {"ok": true, "campaign_id", "adsets": [{id, name, status,
                 optimization_goal, daily_budget}]}   (daily_budget int or null)
Errors → {"ok": false, "error": "..."} (access tokens are scrubbed).
"""
import argparse
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Page size per Graph API call; cursors auto-page, this just bounds each fetch.
PAGE_LIMIT = 200

_TOKEN_RE = re.compile(r"(access_token=)[^&\s'\"]+|EAA[0-9A-Za-z]{20,}")


def scrub(text: str) -> str:
    """Never let an access token reach stdout, even inside SDK error dumps."""
    return _TOKEN_RE.sub(r"\1<redacted>", str(text))


def emit(obj, code=0):
    print(json.dumps(obj))
    sys.exit(code)


def die(message):
    emit({"ok": False, "error": scrub(message)}, code=1)


def init_api() -> str:
    """Init the SDK from .env (same as meta_upload.py) and return act_<id>."""
    import os
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")

    from facebook_business.api import FacebookAdsApi
    token = os.getenv("META_ACCESS_TOKEN", "")
    if not token:
        die("META_ACCESS_TOKEN not set in .env")
    app_id = os.getenv("META_APP_ID", "")
    app_secret = os.getenv("META_APP_SECRET", "")
    FacebookAdsApi.init(app_id=app_id or None, app_secret=app_secret or None,
                        access_token=token, api_version="v21.0")
    account_id = os.getenv("META_AD_ACCOUNT_ID", "")
    if not account_id:
        die("META_AD_ACCOUNT_ID not set in .env")
    return account_id if account_id.startswith("act_") else f"act_{account_id}"


def list_campaigns():
    account_id = init_api()
    from facebook_business.adobjects.adaccount import AdAccount
    fields = ["id", "name", "status", "objective", "created_time"]
    cursor = AdAccount(account_id).get_campaigns(
        fields=fields, params={"limit": PAGE_LIMIT})
    campaigns = [{f: c.get(f) for f in fields} for c in cursor]
    emit({"ok": True, "account_id": account_id, "campaigns": campaigns})


def list_adsets(campaign_id: str):
    init_api()
    from facebook_business.adobjects.campaign import Campaign
    fields = ["id", "name", "status", "optimization_goal", "daily_budget"]
    cursor = Campaign(campaign_id).get_ad_sets(
        fields=fields, params={"limit": PAGE_LIMIT})
    adsets = []
    for a in cursor:
        row = {f: a.get(f) for f in fields}
        # Graph returns budgets as string cents; contract wants int or null.
        row["daily_budget"] = int(row["daily_budget"]) if row.get("daily_budget") else None
        adsets.append(row)
    emit({"ok": True, "campaign_id": campaign_id, "adsets": adsets})


def main():
    ap = argparse.ArgumentParser(description="Read-only Meta campaign/ad-set lister")
    ap.add_argument("what", choices=["campaigns", "adsets"])
    ap.add_argument("--campaign-id", default="")
    args = ap.parse_args()

    try:
        if args.what == "campaigns":
            list_campaigns()
        else:
            if not args.campaign_id:
                die("--campaign-id is required for adsets")
            list_adsets(args.campaign_id)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 — SDK errors must still yield JSON
        die(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
