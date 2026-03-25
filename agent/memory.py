# agent/memory.py
import sqlite3
import json
from pathlib import Path
from typing import List, Dict
from config.settings import settings

DB_PATH = Path(".data/memory.db")
DB_PATH.parent.mkdir(exist_ok=True)

def _conn():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            session   TEXT NOT NULL,
            role      TEXT NOT NULL,
            content   TEXT NOT NULL,
            ts        DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.commit()
    return con

def get_history(session_id: str) -> List[Dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT role, content FROM messages WHERE session=? ORDER BY id DESC LIMIT ?",
            (session_id, settings.conversation_memory_length)
        ).fetchall()
    return [{"role": r, "content": c} for r, c in reversed(rows)]

def add_message(session_id: str, role: str, content: str):
    with _conn() as con:
        con.execute(
            "INSERT INTO messages (session, role, content) VALUES (?,?,?)",
            (session_id, role, content)
        )

def clear_history(session_id: str):
    with _conn() as con:
        con.execute("DELETE FROM messages WHERE session=?", (session_id,))

def get_all_sessions() -> List[str]:
    with _conn() as con:
        rows = con.execute("SELECT DISTINCT session FROM messages").fetchall()
    return [r[0] for r in rows]