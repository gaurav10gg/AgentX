# agent/task_store.py
# Persistent store for scheduled tasks — separate from conversation memory.
# Tasks survive across messages. Memory does not.

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

TASK_DIR = Path(".tasks")
TASK_DIR.mkdir(exist_ok=True)

TASK_FILE = TASK_DIR / "pending_tasks.json"


def _load() -> list:
    if not TASK_FILE.exists():
        return []
    try:
        with open(TASK_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def _save(tasks: list):
    with open(TASK_FILE, "w") as f:
        json.dump(tasks, f, indent=2)


def add_task(
    session_id: str,
    tool_name: str,
    tool_args: dict,
    execute_at: datetime,
    description: str,
    google_token: Optional[dict] = None,
) -> str:
    """
    Save a scheduled task. Returns the task_id.

    Args:
        session_id:   which user/session created this task
        tool_name:    which tool to call (e.g. "send_email", "set_alarm")
        tool_args:    the arguments to pass to that tool
        execute_at:   when to execute (UTC datetime)
        description:  human-readable label shown in pending task list
        google_token: snapshot of the google token at time of scheduling
    """
    tasks = _load()
    task_id = str(uuid.uuid4())[:8]
    tasks.append({
        "task_id":     task_id,
        "session_id":  session_id,
        "tool_name":   tool_name,
        "tool_args":   tool_args,
        "execute_at":  execute_at.isoformat(),
        "description": description,
        "status":      "pending",      # pending | running | done | failed
        "result":      None,
        "created_at":  datetime.utcnow().isoformat(),
        "google_token": google_token,  # snapshot so token refresh can happen at exec time
    })
    _save(tasks)
    return task_id


def get_pending_tasks(session_id: Optional[str] = None) -> list:
    """
    Return all pending tasks, optionally filtered by session_id.
    Only returns tasks whose execute_at is in the future.
    """
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
    Called by the scheduler every tick.
    """
    tasks = _load()
    now = datetime.utcnow()
    return [
        t for t in tasks
        if t["status"] == "pending"
        and datetime.fromisoformat(t["execute_at"]) <= now
    ]


def mark_task(task_id: str, status: str, result: Optional[str] = None):
    """Update a task's status and result."""
    tasks = _load()
    for t in tasks:
        if t["task_id"] == task_id:
            t["status"] = status
            t["result"] = result
            t["completed_at"] = datetime.utcnow().isoformat()
            break
    _save(tasks)


def cancel_task(task_id: str, session_id: str) -> bool:
    """
    Cancel a pending task. Returns True if found and cancelled.
    Only cancels tasks belonging to the given session.
    """
    tasks = _load()
    for t in tasks:
        if t["task_id"] == task_id and t["session_id"] == session_id and t["status"] == "pending":
            t["status"] = "cancelled"
            _save(tasks)
            return True
    return False

def cleanup_old_notifications(days: int = 7):
    """Remove notifications older than N days regardless of surfaced status."""
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
    Returns a short string describing pending tasks for injection into the system prompt.
    Returns None if there are no pending tasks for this session.

    Example output:
        PENDING TASKS (do not re-schedule these):
        - [a1b2c3d4] Send email to dr.sharma@nitpy.ac.in at 14:32 IST (in 4 min)
        - [e5f6g7h8] Alarm: Wake up at 07:00 IST (in 6 hr 12 min)
    """
    pending = get_pending_tasks(session_id)
    if not pending:
        return None

    now = datetime.utcnow()
    lines = ["PENDING TASKS (do not re-schedule these, they are already queued):"]
    for t in pending:
        execute_at = datetime.fromisoformat(t["execute_at"])
        delta = execute_at - now
        total_seconds = int(delta.total_seconds())

        if total_seconds < 60:
            time_str = f"in {total_seconds}s"
        elif total_seconds < 3600:
            time_str = f"in {total_seconds // 60} min"
        else:
            h = total_seconds // 3600
            m = (total_seconds % 3600) // 60
            time_str = f"in {h}h {m}min"

        lines.append(f"  - [{t['task_id']}] {t['description']} ({time_str})")

    return "\n".join(lines)