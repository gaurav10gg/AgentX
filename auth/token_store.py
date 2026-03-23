# auth/token_store.py
import json
from typing import Optional
from pathlib import Path

TOKEN_DIR = Path(".tokens")
TOKEN_DIR.mkdir(exist_ok=True)

def _path(user_id: str) -> Path:
    return TOKEN_DIR / f"{user_id}.json"

def save_token(user_id: str, token_data: dict):
    with open(_path(user_id), "w") as f:
        json.dump(token_data, f, indent=2)

def get_token(user_id: str) -> Optional[dict]:
    p = _path(user_id)
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)

def delete_token(user_id: str):
    p = _path(user_id)
    if p.exists():
        p.unlink()

def refresh_token_if_needed(user_id: str) -> Optional[dict]:
    token = get_token(user_id)
    if not token:
        return None
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        creds = Credentials(
            token=token["access_token"],
            refresh_token=token.get("refresh_token"),
            token_uri=token.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token.get("client_id"),
            client_secret=token.get("client_secret"),
            scopes=token.get("scopes"),
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token["access_token"] = creds.token
            save_token(user_id, token)
        return token
    except Exception:
        # Token refresh failed — user needs to re-login
        return token