# auth/google_oauth.py
import httpx
import time
import asyncio
from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse, JSONResponse
from config.settings import settings
from auth.token_store import save_token, get_token, delete_token
import secrets

router = APIRouter(prefix="/auth", tags=["auth"])

SCOPES = " ".join([
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/contacts.readonly",
])

# state -> {user_id, expires}
_states: dict = {}
_STATE_TTL = 600        # 10 minutes per state entry
_CLEANUP_INTERVAL = 300 # clean every 5 minutes


def _clean_states():
    """Remove expired CSRF state entries."""
    now = time.time()
    expired = [k for k, v in _states.items() if v["expires"] < now]
    for k in expired:
        del _states[k]


async def _cleanup_loop():
    """Background task — runs forever, cleans stale states every 5 min."""
    while True:
        await asyncio.sleep(_CLEANUP_INTERVAL)
        before = len(_states)
        _clean_states()
        after = len(_states)
        if before != after:
            import logging
            logging.getLogger("auth").info(
                "CSRF cleanup: removed %d stale states", before - after
            )


def start_cleanup_task():
    """Call this once from server startup."""
    asyncio.create_task(_cleanup_loop())


@router.get("/login")
async def login(user_id: str = Query(default="default_user")):
    _clean_states()

    if len(_states) > 500:
        _clean_states()
        if len(_states) > 500:
            return JSONResponse(
                {"status": "error", "detail": "Too many pending auth flows"},
                status_code=429,
            )

    state = secrets.token_urlsafe(32)
    _states[state] = {"user_id": user_id, "expires": time.time() + _STATE_TTL}

    params = "&".join([
        "response_type=code",
        f"client_id={settings.google_client_id}",
        f"redirect_uri={settings.google_redirect_uri}",
        f"scope={SCOPES.replace(' ', '%20')}",
        "access_type=offline",
        "prompt=consent",
        f"state={state}",
    ])
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/auth?{params}")


@router.get("/callback")
async def callback(code: str, state: str = None):
    if not state:
        return JSONResponse(
            {"status": "error", "detail": "Missing state parameter"},
            status_code=400,
        )

    _clean_states()
    state_data = _states.pop(state, None)

    if not state_data:
        return JSONResponse(
            {"status": "error", "detail": "Invalid or expired state. Please login again."},
            status_code=400,
        )

    user_id = state_data["user_id"]

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code":          code,
                "client_id":     settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri":  settings.google_redirect_uri,
                "grant_type":    "authorization_code",
            },
            timeout=10,
        )

    token_json = response.json()
    if "error" in token_json:
        return JSONResponse({"status": "error", "detail": token_json}, status_code=400)

    save_token(user_id, {
        "access_token":  token_json["access_token"],
        "refresh_token": token_json.get("refresh_token"),
        "token_uri":     "https://oauth2.googleapis.com/token",
        "client_id":     settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "scopes":        token_json.get("scope", SCOPES).split(),
    })

    return JSONResponse({
        "status":         "success",
        "user_id":        user_id,
        "message":        "Google account connected! You can close this tab.",
        "scopes_granted": token_json.get("scope", "").split(),
    })


@router.get("/status")
async def status(user_id: str = Query(default="default_user")):
    token = get_token(user_id)
    if token:
        return {"connected": True, "user_id": user_id, "scopes": token.get("scopes", [])}
    return {"connected": False, "user_id": user_id}


@router.delete("/logout")
async def logout(user_id: str = Query(default="default_user")):
    delete_token(user_id)
    return {"status": "logged out", "user_id": user_id}