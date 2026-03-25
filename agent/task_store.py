# agent/task_store.py
# Persistent store for scheduled tasks.
# Token cache is now SQLite-backed (survives restarts) with Fernet encryption.
# Tokens are NEVER written to the tasks JSON — only to the encrypted token table.

import json
import uuid
import sqlite3
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

TASK_DIR = Path(".tasks")
TASK_DIR.mkdir(exist_ok=True)
TASK_FILE = TASK_DIR / "pending_tasks.json"

DB_PATH = Path(".data/memory.db")
DB_PATH.parent.mkdir(exist_ok=True)

# ── Encryption setup ──────────────────────────────────────────────────────────
# Key is stored in .data/token.key (gitignored). Generated once on first run.

def _get_fernet():
    from cryptography.fernet import Fernet
    key_path = Path(".data/token.key")
    if key_path.exists():
        key = key_path.read_bytes()
    else:
        key = Fernet.generate_key()
        key_path.write_bytes(key)
    return Fernet(key)


# ── DB helpers ────────────────────────────────────────────────────────────────

def _conn():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS task_tokens (
            task_id   TEXT PRIMARY KEY,
            token_enc TEXT NOT NULL,
            created   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.commit()
    return con


# ── Token cache (persistent + encrypted) ─────────────────────────────────────

def _save_token(task_id: str, token: dict):
    f = _get_fernet()
    encrypted = f.encrypt(json.dumps(token).encode()).decode()
    with _conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO task_tokens (task_id, token_enc) VALUES (?,?)",
            (task_id, encrypted)
        )

def _load_token(task_id: str) -> Optional[dict]:
    with _conn() as con:
        row = con.execute(
            "SELECT token_enc FROM task_tokens WHERE task_id=?", (task_id,)
        ).fetchone()
    if not row:
        return None
    try:
        f = _get_fernet()
        return json.loads(f.decrypt(row[0].encode()).decode())
    except Exception:
        return None

def _delete_token(task_id: str):
    with _conn() as con:
        con.execute("DELETE FROM task_tokens WHERE task_id=?", (task_id,))


# ── Task file helpers ─────────────────────────────────────────────────────────

def _load() -> list:
    if not TASK_FILE.exists():
        return []
    try:
        with open(TASK_FILE) as f:
            return json.load(f)
    except Exception:
        return []

def _save(tasks: list):
    clean = [{k: v for k, v in t.items() if k != "google_token"} for t in tasks]
    with open(TASK_FILE, "w") as f:
        json.dump(clean, f, indent=2)


# ── Public API ────────────────────────────────────────────────────────────────

def add_task(
    session_id: str,
    tool_name: str,
    tool_args: dict,
    execute_at: datetime,
    description: str,
    google_token: Optional[dict] = None,
) -> str:
    tasks = _load()
    task_id = str(uuid.uuid4())[:8]

    if google_token:
        _save_token(task_id, google_token)

    tasks.append({
        "task_id":    task_id,
        "session_id": session_id,
        "tool_name":  tool_name,
        "tool_args":  tool_args,
        "execute_at": execute_at.isoformat(),
        "description": description,
        "status":     "pending",
        "result":     None,
        "created_at": datetime.utcnow().isoformat(),
    })
    _save(tasks)
    return task_id


def get_token_for_task(task_id: str) -> Optional[dict]:
    token = _load_token(task_id)
    if token:
        return token
    # Fallback: refresh from disk token store (handles pre-migration tasks)
    try:
        from auth.token_store import refresh_token_if_needed
        return refresh_token_if_needed("default_user")
    except Exception:
        return None


def get_pending_tasks(session_id: Optional[str] = None) -> list:
    tasks = _load()
    now = datetime.utcnow()
    return [
        t for t in tasks
        if t["status"] == "pending"
        and (session_id is None or t["session_id"] == session_id)
        and datetime.fromisoformat(t["execute_at"]) > now
    ]


def get_due_tasks() -> list:
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
    tasks = _load()
    for t in tasks:
        if t["task_id"] == task_id:
            t["status"] = status
            t["result"] = result
            t["completed_at"] = datetime.utcnow().isoformat()
            break
    _save(tasks)
    if status in ("done", "failed", "cancelled"):
        _delete_token(task_id)


def cancel_task(task_id: str, session_id: str) -> bool:
    tasks = _load()
    for t in tasks:
        if t["task_id"] == task_id and t["session_id"] == session_id and t["status"] == "pending":
            t["status"] = "cancelled"
            _save(tasks)
            _delete_token(task_id)
            return True
    return False


def cleanup_old_notifications(days: int = 7):
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