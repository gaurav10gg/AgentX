# agent/task_store.py
# Persistent store for scheduled tasks — separate from conversation memory.
# Tasks survive across messages. Memory does not.
#
# SECURITY: google_token is stored in memory only during the scheduler's
# execution window. It is NEVER written to disk. At save time the token is
# stripped from the record; at execution time the scheduler fetches a fresh
# token from token_store (which lives in .tokens/ — gitignored).

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

TASK_DIR = Path(".tasks")
TASK_DIR.mkdir(exist_ok=True)

TASK_FILE = TASK_DIR / "pending_tasks.json"

# In-memory token cache: task_id -> google_token dict.
# Populated when a task is added, cleared when the task is done/cancelled.
# Never touches disk.
_token_cache: dict = {}


def _load() -> list:
    if not TASK_FILE.exists():
        return []
    try:
        with open(TASK_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def _save(tasks: list):
    # Strip any google_token that may have leaked into a record before writing.
    # Belt-and-suspenders guard — tokens should never be in the list,
    # but if a bug causes one to appear we don't want it written to disk.
    clean = [{k: v for k, v in t.items() if k != "google_token"} for t in tasks]
    with open(TASK_FILE, "w") as f:
        json.dump(clean, f, indent=2)


def add_task(
    session_id: str,
    user_id: str,
    tool_name: str,
    tool_args: dict,
    execute_at: datetime,
    description: str,
    google_token: Optional[dict] = None,
) -> str:
    """
    Save a scheduled task. Returns the task_id.

    google_token is held in _token_cache (memory only) and never written to disk.
    """
    tasks = _load()
    task_id = str(uuid.uuid4())[:8]

    if google_token:
        _token_cache[task_id] = google_token

    tasks.append({
        "task_id":     task_id,
        "session_id":  session_id,
        "user_id":     user_id,
        "tool_name":   tool_name,
        "tool_args":   tool_args,
        "execute_at":  execute_at.isoformat(),
        "description": description,
        "status":      "pending",
        "result":      None,
        "created_at":  datetime.utcnow().isoformat(),
        # google_token intentionally omitted
    })
    _save(tasks)
    return task_id


def get_token_for_task(task: dict) -> Optional[dict]:
    """
    Retrieve the in-memory token for a task.
    Falls back to token_store (refreshed from disk) if not in cache —
    handles server restarts after the task was saved.
    """
    task_id = task["task_id"]
    if task_id in _token_cache:
        return _token_cache[task_id]
    try:
        from auth.token_store import refresh_token_if_needed
        return refresh_token_if_needed(task.get("user_id", "default_user"))
    except Exception:
        return None


def get_pending_tasks(session_id: Optional[str] = None) -> list:
    """Return all pending tasks, optionally filtered by session_id."""
    tasks = _load()
    now = datetime.utcnow()
    return [
        t for t in tasks
        if t["status"] == "pending"
        and (session_id is None or t["session_id"] == session_id)
        and datetime.fromisoformat(t["execute_at"]) > now
    ]


def get_due_tasks() -> list:
    """
    Return all pending tasks whose execute_at has passed.
    Also resets tasks stuck in 'running' with no completed_at
    (crash recovery — prevents permanent stuck tasks on server restart).
    """
    tasks = _load()
    now = datetime.utcnow()
    due = []
    changed = False
    for t in tasks:
        if t["status"] == "pending" and datetime.fromisoformat(t["execute_at"]) <= now:
            due.append(t)
        elif t["status"] == "running" and not t.get("completed_at"):
            t["status"] = "pending"
            changed = True
            due.append(t)
    if changed:
        _save(tasks)
    return due


def mark_task(task_id: str, status: str, result: Optional[str] = None):
    """Update a task's status and result. Clears token cache on completion."""
    tasks = _load()
    for t in tasks:
        if t["task_id"] == task_id:
            t["status"] = status
            t["result"] = result
            t["completed_at"] = datetime.utcnow().isoformat()
            break
    _save(tasks)
    if status in ("done", "failed", "cancelled"):
        _token_cache.pop(task_id, None)


def cancel_task(task_id: str, session_id: str) -> bool:
    """Cancel a pending task. Returns True if found and cancelled."""
    tasks = _load()
    for t in tasks:
        if t["task_id"] == task_id and t["session_id"] == session_id and t["status"] == "pending":
            t["status"] = "cancelled"
            _save(tasks)
            _token_cache.pop(task_id, None)
            return True
    return False


def cleanup_old_notifications(days: int = 7):
    """Remove notifications older than N days."""
    from datetime import timedelta
    notifications_file = TASK_DIR / "notifications.json"
    if not notifications_file.exists():
        return
    cutoff = datetime.utcnow() - timedelta(days=days)
    with open(notifications_file) as f:
        all_notifs = json.load(f)
    fresh = [n for n in all_notifs if datetime.fromisoformat(n["at"]) > cutoff]
    with open(notifications_file, "w") as f:
        json.dump(fresh, f, indent=2)


def format_pending_for_prompt(session_id: str) -> Optional[str]:
    """
    Returns pending tasks for injection into the system prompt.
    Includes tasks due within the next 60s (labelled 'executing soon')
    so the LLM doesn't re-schedule them during the scheduler's tick window.
    """
    tasks = _load()
    now = datetime.utcnow()
    lines = []

    for t in tasks:
        if t["status"] != "pending":
            continue
        if session_id and t["session_id"] != session_id:
            continue

        execute_at = datetime.fromisoformat(t["execute_at"])
        total_s = int((execute_at - now).total_seconds())

        if total_s < 0:
            time_str = "executing now"
        elif total_s < 60:
            time_str = "executing soon"
        elif total_s < 3600:
            time_str = f"in {total_s // 60} min"
        else:
            h, m = total_s // 3600, (total_s % 3600) // 60
            time_str = f"in {h}h {m}min"

        lines.append(f"  - [{t['task_id']}] {t['description']} ({time_str})")

    if not lines:
        return None

    return "PENDING TASKS (do not re-schedule these, they are already queued):\n" + "\n".join(lines)
