# server.py
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import uvicorn
import traceback
import re
from pathlib import Path
from datetime import datetime
import json
import time
import threading

from agent.agent import run_agent
from agent.scheduler import scheduler
from agent_v2.router import router as v2_router
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
app.include_router(v2_router)

MAX_ACTIVE_NOTIFICATIONS = 1000
MAX_SURFACED_PER_SESSION = 50
MAX_ARCHIVE_NOTIFICATIONS = 10000
CHAT_RATE_WINDOW_SECONDS = 60
CHAT_RATE_MAX_PER_IP = 30
CHAT_RATE_MAX_PER_SESSION = 20
_CHAT_RATE_LOCK = threading.Lock()
_CHAT_RATE_EVENTS = {
    "ip": {},
    "session": {},
}


# ── Scheduler lifecycle ──────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    from auth.google_oauth import start_cleanup_task
    start_cleanup_task()                    # ← add this
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

    notifications_file = TASK_DIR / "notifications.json"
    archive_file = TASK_DIR / "notifications_archive.json"
    try:
        notifs = _read_json_list(notifications_file)

        notifs.append({
            "session_id":  session_id,
            "task_id":     task_id,
            "description": _fix_mojibake_text(description),
            "result":      _fix_mojibake_text(result),
            "at":          datetime.utcnow().isoformat(),
            "surfaced":    False,
        })

        compacted, archived = _compact_notifications(notifs)
        _write_json_list(notifications_file, compacted)
        if archived:
            _append_archive(archive_file, archived)
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
    actions_taken: list = Field(default_factory=list)
    alarm_data: Optional[dict] = None
    requires_confirmation: bool = False
    iterations: int = 0
    # Completed task notifications delivered alongside this reply
    task_notifications: list = Field(default_factory=list)


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/")
async def health(user_id: str = Query("default_user")):
    from auth.token_store import get_token
    token = get_token(user_id)
    return {
        "status": "running",
        "version": "1.0.0",
        "google_connected": token is not None,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request):
    if not req.message.strip():
        raise HTTPException(400, "Message cannot be empty")
    if not req.api_key.strip():
        raise HTTPException(401, "API key is required")
    _enforce_chat_rate_limit(request=request, session_id=req.session_id)

    google_token = refresh_token_if_needed(req.user_id)

    # Fallback execution path: run one scheduler tick on each chat request.
    # This ensures due tasks are not stuck if background scheduling is paused.
    try:
        await scheduler._tick()
    except Exception:
        pass

    # Recovery path: if callback-based notifications were missed, reconstruct them
    # from completed tasks so user can still see task outcomes in chat.
    _backfill_notifications_from_tasks(req.session_id)

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
            user_id=req.user_id,
            provider=req.provider,
            api_key=req.api_key,
            model=req.model,
            base_url=req.base_url,
            google_token=google_token,
        )
        result = _sanitize_payload_text(result)
        notifications = _sanitize_payload_text(notifications)

        # Deterministic UX: always surface completed task notifications in reply text.
        # This avoids cases where the LLM ignores completion lines and switches topics.
        if notifications:
            summary = _format_notifications_summary(notifications)
            reply = result.get("reply", "")
            result["reply"] = f"{summary}\n\n{reply}" if reply else summary

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

    notifications_file = TASK_DIR / "notifications.json"
    archive_file = TASK_DIR / "notifications_archive.json"
    if not notifications_file.exists():
        return []

    try:
        all_notifs = _read_json_list(notifications_file)

        mine = [n for n in all_notifs if n["session_id"] == session_id and not n["surfaced"]]

        # Mark as surfaced
        for n in all_notifs:
            if n["session_id"] == session_id and not n["surfaced"]:
                n["surfaced"] = True

        compacted, archived = _compact_notifications(all_notifs)
        _write_json_list(notifications_file, compacted)
        if archived:
            _append_archive(archive_file, archived)

        return mine
    except Exception:
        return []


def _backfill_notifications_from_tasks(session_id: str):
    from agent.task_store import TASK_DIR

    task_file = TASK_DIR / "pending_tasks.json"
    notifications_file = TASK_DIR / "notifications.json"
    archive_file = TASK_DIR / "notifications_archive.json"

    if not task_file.exists():
        return

    try:
        with open(task_file) as f:
            tasks = json.load(f)
    except Exception:
        return

    notifs = _read_json_list(notifications_file)

    existing_task_ids = {n.get("task_id") for n in notifs}
    changed = False

    for t in tasks:
        if t.get("session_id") != session_id:
            continue
        if t.get("status") not in ("done", "failed"):
            continue
        task_id = t.get("task_id")
        if task_id in existing_task_ids:
            continue

        notifs.append({
            "session_id": session_id,
            "task_id": task_id,
            "description": t.get("description", "Scheduled task"),
            "result": t.get("result", ""),
            "at": t.get("completed_at") or datetime.utcnow().isoformat(),
            "surfaced": False,
        })
        changed = True

    compacted, archived = _compact_notifications(notifs)
    if changed or len(compacted) != len(notifs):
        _write_json_list(notifications_file, compacted)
        if archived:
            _append_archive(archive_file, archived)


def _read_json_list(path: Path) -> list:
    if not path.exists():
        return []
    try:
        with open(path) as f:
            value = json.load(f)
        return value if isinstance(value, list) else []
    except Exception:
        return []


def _write_json_list(path: Path, rows: list):
    with open(path, "w") as f:
        json.dump(rows, f, indent=2)


def _append_archive(path: Path, new_rows: list):
    if not new_rows:
        return
    existing = _read_json_list(path)
    merged = existing + [row for row in new_rows if isinstance(row, dict)]

    def _ts(item: dict) -> str:
        return str(item.get("at") or "")

    merged.sort(key=_ts, reverse=True)
    _write_json_list(path, merged[:MAX_ARCHIVE_NOTIFICATIONS])


def _compact_notifications(notifs: list) -> tuple[list, list]:
    """
    Keep notifications bounded to prevent file growth/slow backfill scans.
    - Keep all unsurfaced items.
    - Keep only recent surfaced items per session.
    - Enforce global MAX_ACTIVE_NOTIFICATIONS cap.
    Returns: (compacted, archived)
    """
    sanitized = [n for n in notifs if isinstance(n, dict) and n.get("session_id") and n.get("task_id")]
    if not sanitized:
        return [], []

    def _ts(item: dict) -> str:
        return str(item.get("at") or "")

    unsurfaced = [n for n in sanitized if not bool(n.get("surfaced"))]
    surfaced = [n for n in sanitized if bool(n.get("surfaced"))]

    per_session_keep: list[dict] = []
    surfaced_by_session: dict[str, list[dict]] = {}
    for item in surfaced:
        sid = str(item.get("session_id"))
        surfaced_by_session.setdefault(sid, []).append(item)
    for session_items in surfaced_by_session.values():
        session_items.sort(key=_ts, reverse=True)
        per_session_keep.extend(session_items[:MAX_SURFACED_PER_SESSION])

    kept = unsurfaced + per_session_keep
    kept.sort(key=_ts, reverse=True)

    if len(kept) <= MAX_ACTIVE_NOTIFICATIONS:
        archived_candidates = [n for n in sanitized if n not in kept]
        return kept, archived_candidates

    trimmed = kept[:MAX_ACTIVE_NOTIFICATIONS]
    archived_candidates = [n for n in sanitized if n not in trimmed]
    return trimmed, archived_candidates


def _format_notifications_summary(notifications: list) -> str:
    lines = ["Completed tasks:"]
    for n in notifications:
        lines.append(f"- {n['description']}: {n['result']}")
    return "\n".join(lines)


def _enforce_chat_rate_limit(request: Request, session_id: str):
    client_ip = (request.client.host if request.client else None) or "unknown"
    now = time.monotonic()

    with _CHAT_RATE_LOCK:
        ip_events = _CHAT_RATE_EVENTS["ip"].setdefault(client_ip, [])
        session_events = _CHAT_RATE_EVENTS["session"].setdefault(session_id, [])

        ip_events[:] = [t for t in ip_events if now - t <= CHAT_RATE_WINDOW_SECONDS]
        session_events[:] = [t for t in session_events if now - t <= CHAT_RATE_WINDOW_SECONDS]

        if len(ip_events) >= CHAT_RATE_MAX_PER_IP:
            raise HTTPException(429, f"Rate limit exceeded for this IP. Try again in a few seconds.")
        if len(session_events) >= CHAT_RATE_MAX_PER_SESSION:
            raise HTTPException(429, f"Rate limit exceeded for this session. Slow down and retry.")

        ip_events.append(now)
        session_events.append(now)


def _sanitize_payload_text(value):
    if isinstance(value, str):
        return _fix_mojibake_text(value)
    if isinstance(value, list):
        return [_sanitize_payload_text(v) for v in value]
    if isinstance(value, dict):
        return {k: _sanitize_payload_text(v) for k, v in value.items()}
    return value


def _fix_mojibake_text(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text

    cleaned = text
    looks_mojibake = any(marker in cleaned for marker in ("Ã", "â", "Â", "ð"))
    if looks_mojibake:
        try:
            repaired = cleaned.encode("latin-1").decode("utf-8")
            if repaired and repaired.count("�") <= cleaned.count("�"):
                cleaned = repaired
        except Exception:
            pass

    replacements = {
        "â€™": "’",
        "â€˜": "‘",
        "â€œ": "“",
        "â€": "”",
        "â€“": "–",
        "â€”": "—",
        "â€¦": "…",
        "â€¢": "•",
        "â†’": "->",
        "â€¯": " ",
        "Â ": " ",
        "Â": "",
    }
    for bad, good in replacements.items():
        cleaned = cleaned.replace(bad, good)

    # Collapse accidental runs of odd spacing after replacement.
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned


if __name__ == "__main__":
    uvicorn.run("server:app", host=settings.host, port=settings.port, reload=settings.debug)
