#!/usr/bin/env python3
"""Guard tests for scripts/meta_upload.py's optional adset_id (existing-ad-set
mode), run entirely against a mocked facebook_business SDK — zero network, no
credentials used.

Run:  python3 tests/test_meta_upload_adset.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PY = sys.executable

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        print(f"  ✗ {name}  {detail}")


def build_mock_sdk(root: Path):
    """Fake dotenv + the three facebook_business entry points the dry-run path
    touches. AdSet.api_get behavior is driven by MOCK_ADSET_MODE/DATA env."""
    root.mkdir(parents=True)
    (root / "dotenv.py").write_text("def load_dotenv(*a, **k):\n    pass\n")
    fb = root / "facebook_business"
    (fb / "adobjects").mkdir(parents=True)
    (fb / "__init__.py").write_text("")
    (fb / "api.py").write_text(
        "class FacebookAdsApi:\n"
        "    @staticmethod\n"
        "    def init(*a, **k):\n        pass\n")
    (fb / "adobjects" / "__init__.py").write_text("")
    (fb / "adobjects" / "adaccount.py").write_text(
        "class AdAccount:\n"
        "    def __init__(self, _id):\n        self._id = _id\n")
    (fb / "adobjects" / "adset.py").write_text(
        "import json, os\n"
        "class _Row(dict):\n"
        "    def export_all_data(self):\n        return dict(self)\n"
        "class AdSet:\n"
        "    def __init__(self, _id):\n        self._id = _id\n"
        "    def api_get(self, fields=None):\n"
        "        if os.environ.get('MOCK_ADSET_MODE') == 'missing':\n"
        "            raise Exception('Unsupported get request. (#100)')\n"
        "        return _Row(json.loads(os.environ['MOCK_ADSET_DATA']))\n")


def run_upload(config: dict, mode="ok", adset_data=None, tmp=None):
    cfg = tmp / "config.json"
    cfg.write_text(json.dumps(config))
    env = dict(os.environ,
               PYTHONPATH=str(tmp / "mock"),
               MOCK_ADSET_MODE=mode,
               MOCK_ADSET_DATA=json.dumps(adset_data or {}),
               META_ACCESS_TOKEN="mock-token",
               META_AD_ACCOUNT_ID="123",
               META_PAGE_ID="1", META_INSTAGRAM_ACTOR_ID="",
               LANDING_PAGE_URL="https://example.com")
    proc = subprocess.run([PY, "-m", "scripts.meta_upload",
                           "--config", str(cfg), "--dry-run"],
                          cwd=str(BASE), env=env, capture_output=True,
                          text=True, timeout=60)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main():
    print("\n[meta_upload adset_id guards — mocked SDK, dry-run]")
    with tempfile.TemporaryDirectory(prefix="metaupload_mock_") as td:
        tmp = Path(td)
        build_mock_sdk(tmp / "mock")
        base_cfg = {
            "campaign_name": "QA", "ad_set_name": "Ad Set #9 - QA - Broad - X",
            "daily_budget": 20000,
            "ads": [{"creative_concept": "c", "video_filename": "v.mp4",
                     "primary_text": "p", "headline": "h", "description": "d"}],
        }

        # omit path — AdSet must never be consulted (mode=missing would raise)
        rc, log = run_upload(dict(base_cfg), mode="missing", tmp=tmp)
        check("omit: exit 0, creates NEW ad set, AdSet never read",
              rc == 0 and "Target: would create NEW ad set 'Ad Set #9 - QA - Broad - X'" in log
              and "existing ad set" not in log, detail=log[-300:])

        # non-numeric adset_id → hard fail before anything
        rc, log = run_upload(dict(base_cfg, adset_id="12ab!"), tmp=tmp)
        check("non-numeric adset_id → exit 1 before any dry-create",
              rc == 1 and "must be a numeric string" in log
              and "Would create" not in log, detail=log[-300:])

        # nonexistent ad set → hard fail before campaign/media
        rc, log = run_upload(dict(base_cfg, adset_id="42"), mode="missing", tmp=tmp)
        check("nonexistent adset → exit 1 before campaign/media",
              rc == 1 and "could not be read" in log
              and "Would create" not in log, detail=log[-300:])

        # ad set from a different campaign than config.campaign_id → hard fail
        rc, log = run_upload(dict(base_cfg, adset_id="42", campaign_id="111"),
                             adset_data={"id": "42", "name": "Mock Set",
                                         "status": "PAUSED",
                                         "effective_status": "PAUSED",
                                         "campaign_id": "999"}, tmp=tmp)
        check("campaign mismatch → exit 1 before media",
              rc == 1 and "belongs to campaign 999" in log
              and "Would create" not in log, detail=log[-300:])

        # matching campaign, PAUSED → proceeds, no warning, explicit target
        rc, log = run_upload(dict(base_cfg, adset_id="42", campaign_id="999"),
                             adset_data={"id": "42", "name": "Mock Set",
                                         "status": "PAUSED",
                                         "effective_status": "PAUSED",
                                         "campaign_id": "999"}, tmp=tmp)
        check("existing PAUSED adset → exit 0, no create_ad_set, no warning",
              rc == 0 and "Target: existing ad set 42 ('Mock Set', PAUSED)" in log
              and "Would create ad set" not in log and "WARNING" not in log
              and "Would create ad:" in log, detail=log[-400:])

        # ACTIVE ad set → proceeds with a loud warning
        rc, log = run_upload(dict(base_cfg, adset_id="42"),
                             adset_data={"id": "42", "name": "Mock Set",
                                         "status": "ACTIVE",
                                         "effective_status": "ACTIVE",
                                         "campaign_id": "999"}, tmp=tmp)
        check("ACTIVE adset → exit 0 with warning, ads still created PAUSED",
              rc == 0 and "is ACTIVE" in log and "still land PAUSED" in log
              and "Target: existing ad set 42 ('Mock Set', ACTIVE)" in log,
              detail=log[-400:])

        # no campaign is ever created in existing-adset mode
        rc, log = run_upload(dict(base_cfg, adset_id="42"),
                             adset_data={"id": "42", "name": "Mock Set",
                                         "status": "PAUSED",
                                         "effective_status": "PAUSED",
                                         "campaign_id": "999"}, tmp=tmp)
        check("existing-adset mode adopts the set's campaign (no create)",
              rc == 0 and "Would create campaign" not in log
              and "Using campaign of existing ad set: 999" in log, detail=log[-300:])

    print(f"\n{'='*40}\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


def test_meta_upload_adset_guards():
    """Pytest entry point."""
    # main() exits non-zero on failure; surface that as an assert
    try:
        main()
    except SystemExit as e:
        assert e.code == 0, f"{failed} guard checks failed (see stdout)"


if __name__ == "__main__":
    main()
