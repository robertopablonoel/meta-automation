"""Google auth for the weekly review publisher.

Uses Cole's own OAuth Desktop client (weekly_review/client_secret.json,
project 535172639040). Token cached at weekly_review/token.json (gitignored);
auto-refreshes. Run `python -m weekly_review.gauth` to (re-)consent.
"""
from __future__ import annotations

import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from .common import PKG_DIR

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]
CLIENT_SECRET = os.path.join(PKG_DIR, "client_secret.json")
TOKEN_PATH = os.path.join(PKG_DIR, "token.json")


def get_credentials(interactive: bool = False) -> Credentials:
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save(creds)
            return creds
        except Exception:
            # refresh token revoked/expired — fall through to re-consent
            creds = None
    if not interactive:
        raise RuntimeError(
            "No valid Google token. Run: venv/bin/python -m weekly_review.gauth")
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent",
                                  authorization_prompt_message="")
    _save(creds)
    return creds


def _save(creds: Credentials) -> None:
    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
    os.chmod(TOKEN_PATH, 0o600)


if __name__ == "__main__":
    c = get_credentials(interactive=True)
    print("Token OK; scopes:", " ".join(c.scopes or []))
