# auth/google_oauth.py
import httpx
from fastapi import APIRouter, HTTPException, Query
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

# Store state in memory for CSRF protection and user routing
_states = {}

@router.get("/login")
async def login(user_id: str = Query("default_user")):
    state = secrets.token_urlsafe(16)
    _states[state] = user_id

    params = "&".join([
        "response_type=code",
        f"client_id={settings.google_client_id}",
        f"redirect_uri={settings.google_redirect_uri}",
        f"scope={SCOPES.replace(' ', '%20')}",
        "access_type=offline",
        "prompt=consent",
        f"state={state}",
    ])
    auth_url = f"https://accounts.google.com/o/oauth2/auth?{params}"
    return RedirectResponse(auth_url)

@router.get("/callback")
async def callback(code: str, state: str = None):
    if not state or state not in _states:
        raise HTTPException(status_code=400, detail="Invalid or missing OAuth state")

    user_id = _states.pop(state)

    # Exchange code for tokens manually — no PKCE
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code":          code,
                "client_id":     settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri":  settings.google_redirect_uri,
                "grant_type":    "authorization_code",
            }
        )

    token_json = response.json()

    if "error" in token_json:
        return JSONResponse({"status": "error", "detail": token_json}, status_code=400)

    token_data = {
        "access_token":  token_json["access_token"],
        "refresh_token": token_json.get("refresh_token"),
        "token_uri":     "https://oauth2.googleapis.com/token",
        "client_id":     settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "scopes":        token_json.get("scope", SCOPES).split(),
    }
    save_token(user_id, token_data)

    return JSONResponse({
        "status": "success",
        "message": "Google account connected! You can close this tab.",
        "scopes_granted": token_data["scopes"]
    })

@router.get("/status")
async def status(user_id: str = Query("default_user")):
    token = get_token(user_id)
    if token:
        return {"connected": True, "scopes": token.get("scopes", [])}
    return {"connected": False}

@router.delete("/logout")
async def logout(user_id: str = Query("default_user")):
    delete_token(user_id)
    return {"status": "logged out"}
