# server.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
import traceback

from agent.agent import run_agent
from agent.scheduler import scheduler
from auth.google_oauth import router as auth_router
from auth.token_store import refresh_token_if_needed
from config.settings import settings, PROVIDER_PRESETS
import logging
logging.basicConfig(level=logging.INFO)
app = FastAPI(title="PhoneAgent API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_ngrok_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["ngrok-skip-browser-warning"] = "true"
    return response

app.include_router(auth_router)


# ── Scheduler lifecycle ──────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    scheduler.set_notify_callback(_on_task_complete)
    scheduler.start()


@app.on_event("shutdown")
async def shutdown():
    scheduler.stop()


async def _on_task_complete(session_id: str, task_id: str, description: str, result: str):
    """
    Called by the scheduler when a task fires.

    Phase 1 (now): Store the result so it surfaces on the user's next message.
    Phase 2 (later): Replace with FCM push notification or WebSocket push.
    """
    from agent.task_store import TASK_DIR
    import json
    from pathlib import Path
    from datetime import datetime

    notifications_file = TASK_DIR / "notifications.json"
    try:
        if notifications_file.exists():
            with open(notifications_file) as f:
                notifs = json.load(f)
        else:
            notifs = []

        notifs.append({
            "session_id":  session_id,
            "task_id":     task_id,
            "description": description,
            "result":      result,
            "at":          datetime.utcnow().isoformat(),
            "surfaced":    False,
        })

        with open(notifications_file, "w") as f:
            json.dump(notifs, f, indent=2)
    except Exception as e:
        import logging
        logging.getLogger("scheduler").error("Failed to store notification: %s", e)


# ── Request / Response models ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    provider: str = "sarvam"
    api_key: str
    model: Optional[str] = None
    base_url: Optional[str] = None
    user_id: str = "default_user"

class ChatResponse(BaseModel):
    reply: str
    actions_taken: list = []
    alarm_data: Optional[dict] = None
    requires_confirmation: bool = False
    iterations: int = 0
    # Completed task notifications delivered alongside this reply
    task_notifications: list = []


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/")
async def health():
    from auth.token_store import get_token
    token = get_token("default_user")
    return {
        "status": "running",
        "version": "1.0.0",
        "google_connected": token is not None,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(400, "Message cannot be empty")
    if not req.api_key.strip():
        raise HTTPException(401, "API key is required")

    google_token = refresh_token_if_needed(req.user_id)

    # Pull any completed task notifications for this session before running agent
    notifications = _pop_notifications(req.session_id)

    # If there are completed notifications, prepend them to the user message
    # so the LLM can naturally reference them in its reply
    effective_message = req.message
    if notifications:
        notif_lines = "\n".join(
            f"[Completed task: {n['description']} → {n['result']}]"
            for n in notifications
        )
        effective_message = f"{notif_lines}\n\n{req.message}"

    try:
        result = await run_agent(
            user_message=effective_message,
            session_id=req.session_id,
            provider=req.provider,
            api_key=req.api_key,
            model=req.model,
            base_url=req.base_url,
            google_token=google_token,
        )
        return ChatResponse(
            **result,
            task_notifications=notifications,
        )
    except Exception as e:
        print("FULL ERROR:")
        traceback.print_exc()
        raise HTTPException(500, f"Agent error: {str(e)}")


@app.delete("/chat/history/{session_id}")
async def clear_history(session_id: str):
    from agent.memory import clear_history
    clear_history(session_id)
    return {"status": "cleared", "session_id": session_id}


@app.get("/tasks/{session_id}")
async def list_session_tasks(session_id: str):
    """Debug endpoint — see all pending tasks for a session."""
    from agent.task_store import get_pending_tasks
    return {"tasks": get_pending_tasks(session_id)}


@app.get("/providers")
async def list_providers():
    return PROVIDER_PRESETS


# ── Helpers ──────────────────────────────────────────────────────────────────

def _pop_notifications(session_id: str) -> list:
    """
    Fetch unsurfaced notifications for this session, mark them as surfaced.
    Returns list of notification dicts.
    """
    from agent.task_store import TASK_DIR
    import json

    notifications_file = TASK_DIR / "notifications.json"
    if not notifications_file.exists():
        return []

    try:
        with open(notifications_file) as f:
            all_notifs = json.load(f)

        mine = [n for n in all_notifs if n["session_id"] == session_id and not n["surfaced"]]

        # Mark as surfaced
        for n in all_notifs:
            if n["session_id"] == session_id and not n["surfaced"]:
                n["surfaced"] = True

        with open(notifications_file, "w") as f:
            json.dump(all_notifs, f, indent=2)

        return mine
    except Exception:
        return []


if __name__ == "__main__":
    uvicorn.run("server:app", host=settings.host, port=settings.port, reload=settings.debug)