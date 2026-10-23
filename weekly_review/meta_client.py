"""Read-only Meta Graph API client (requests-based, like scripts/metrics_sync.py).

STRICTLY GET requests. Never POST — CLAUDE.md Rule 0 / read-only mandate.
All errors/logs pass through redact() so no EAA token ever leaks.
"""

from __future__ import annotations

import json
import time

import requests

from .common import redact

MAX_RETRIES = 6


class MetaClient:
    def __init__(self, cfg: dict, token: str, account_id: str):
        if not token or not account_id:
            raise RuntimeError("Missing META_ACCESS_TOKEN / META_AD_ACCOUNT_ID in env")
        if not account_id.startswith("act_"):
            account_id = f"act_{account_id}"
        self.base = f"https://graph.facebook.com/{cfg['graph_api_version']}"
        self.token = token
        self.account_id = account_id

    def get(self, path: str, params: dict | None = None) -> dict:
        """GET with retry/backoff on 429 and Graph error code 17 (rate limit)."""
        params = dict(params or {})
        params["access_token"] = self.token
        url = f"{self.base}/{path.lstrip('/')}"
        last_err = "unknown"
        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.get(url, params=params, timeout=120)
            except requests.RequestException as e:
                last_err = redact(repr(e))
                time.sleep(5 * (2 ** attempt))
                continue
            if resp.status_code == 429:
                wait = 30 * (2 ** attempt)
                print(f"    rate limited (429); waiting {wait}s "
                      f"(attempt {attempt + 1}/{MAX_RETRIES})")
                time.sleep(wait)
                continue
            try:
                body = resp.json()
            except ValueError:
                body = {}
            err = body.get("error") or {}
            if err.get("code") == 17 or err.get("code") == 32 or (
                    resp.status_code >= 400 and "User request limit" in str(err.get("message", ""))):
                wait = min(60 * (2 ** attempt), 600)
                print(f"    rate limited (code {err.get('code')}); waiting {wait}s "
                      f"(attempt {attempt + 1}/{MAX_RETRIES})")
                time.sleep(wait)
                last_err = redact(json.dumps(err))
                continue
            if resp.status_code >= 400:
                raise RuntimeError(f"Graph API error {resp.status_code}: "
                                   f"{redact(json.dumps(err) or resp.text[:300])}")
            return body
        raise RuntimeError(f"Graph API GET failed after {MAX_RETRIES} retries "
                           f"({redact(url)}): {last_err}")

    def get_all(self, path: str, params: dict, page_hook=None,
                start_after: str | None = None) -> list[dict]:
        """Cursor-based pagination. page_hook(rows, after_cursor) is called after
        each page for resumable caching. Never logs paging URLs (contain token)."""
        rows: list[dict] = []
        after = start_after
        while True:
            p = dict(params)
            if after:
                p["after"] = after
            body = self.get(path, p)
            data = body.get("data", [])
            rows.extend(data)
            cursors = (body.get("paging") or {}).get("cursors") or {}
            has_next = bool((body.get("paging") or {}).get("next"))
            after = cursors.get("after")
            if page_hook:
                page_hook(data, after if has_next else None)
            if not has_next or not after:
                return rows

    def get_by_ids(self, ids: list[str], fields: str, chunk: int = 50) -> dict:
        """Batch object reads via ?ids=... field expansion. Falls back to
        per-id GETs (tolerant of dead ids) if a chunk fails."""
        out: dict[str, dict] = {}
        ids = sorted(set(ids))
        for i in range(0, len(ids), chunk):
            batch = ids[i:i + chunk]
            try:
                body = self.get("", {"ids": ",".join(batch), "fields": fields})
                out.update({k: v for k, v in body.items() if isinstance(v, dict)})
            except RuntimeError as e:
                print(f"    batch of {len(batch)} failed ({redact(e)}); "
                      f"falling back to singles")
                for oid in batch:
                    try:
                        out[oid] = self.get(oid, {"fields": fields})
                    except RuntimeError as e2:
                        print(f"    skip {oid}: {redact(e2)}")
        return out
