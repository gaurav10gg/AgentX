from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


DB_PATH = Path(".data/memory.db")
DB_PATH.parent.mkdir(exist_ok=True)

V2_DIR = Path(".data/v2")
V2_DIR.mkdir(parents=True, exist_ok=True)
TASK_FILE = V2_DIR / "tasks.json"
SNAPSHOT_DIR = V2_DIR / "snapshots"
SNAPSHOT_DIR.mkdir(exist_ok=True)
UTG_DIR = V2_DIR / "utg"
UTG_DIR.mkdir(exist_ok=True)


def _conn():
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS v2_navigation_memory (
            app_package TEXT NOT NULL,
            screen_signature TEXT NOT NULL,
            action_key TEXT NOT NULL,
            next_screen_signature TEXT,
            success INTEGER NOT NULL DEFAULT 1,
            confidence REAL NOT NULL DEFAULT 0.5,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (app_package, screen_signature, action_key)
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS v2_task_memory (
            task_key TEXT PRIMARY KEY,
            flow_json TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.5,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS v2_element_memory (
            app_package TEXT NOT NULL,
            screen_signature TEXT NOT NULL,
            semantic_key TEXT NOT NULL,
            element_id TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.5,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (app_package, screen_signature, semantic_key)
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS v2_task_states (
            session_id TEXT PRIMARY KEY,
            state_json TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.commit()
    return con


def get_best_navigation_action(app_package: Optional[str], screen_signature: Optional[str]) -> Optional[Dict[str, Any]]:
    if not app_package or not screen_signature:
        return None
    with _conn() as con:
        row = con.execute(
            """
            SELECT action_key, next_screen_signature, confidence
            FROM v2_navigation_memory
            WHERE app_package=? AND screen_signature=?
            ORDER BY confidence DESC, last_seen DESC
            LIMIT 1
            """,
            (app_package, screen_signature),
        ).fetchone()
    if not row:
        return None
    return {
        "action_key": row[0],
        "next_screen_signature": row[1],
        "confidence": float(row[2]),
    }


def remember_navigation(
    app_package: str,
    screen_signature: str,
    action_key: str,
    next_screen_signature: Optional[str],
    success: bool,
):
    confidence = 0.85 if success else 0.2
    with _conn() as con:
        con.execute(
            """
            INSERT INTO v2_navigation_memory (
                app_package, screen_signature, action_key, next_screen_signature, success, confidence, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(app_package, screen_signature, action_key)
            DO UPDATE SET
                next_screen_signature=excluded.next_screen_signature,
                success=excluded.success,
                confidence=excluded.confidence,
                last_seen=excluded.last_seen
            """,
            (
                app_package,
                screen_signature,
                action_key,
                next_screen_signature,
                1 if success else 0,
                confidence,
                datetime.utcnow().isoformat(),
            ),
        )


def remember_task_flow(task_key: str, flow: List[Dict[str, Any]], confidence: float = 0.75):
    with _conn() as con:
        con.execute(
            """
            INSERT INTO v2_task_memory (task_key, flow_json, confidence, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(task_key)
            DO UPDATE SET flow_json=excluded.flow_json, confidence=excluded.confidence, updated_at=excluded.updated_at
            """,
            (task_key, json.dumps(flow), confidence, datetime.utcnow().isoformat()),
        )


def get_task_flow(task_key: str) -> Optional[Dict[str, Any]]:
    with _conn() as con:
        row = con.execute(
            "SELECT flow_json, confidence FROM v2_task_memory WHERE task_key=?",
            (task_key,),
        ).fetchone()
    if not row:
        return None
    return {"flow": json.loads(row[0]), "confidence": float(row[1])}


def remember_element(app_package: str, screen_signature: str, semantic_key: str, element_id: str, confidence: float = 0.8):
    with _conn() as con:
        con.execute(
            """
            INSERT INTO v2_element_memory (app_package, screen_signature, semantic_key, element_id, confidence, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(app_package, screen_signature, semantic_key)
            DO UPDATE SET element_id=excluded.element_id, confidence=excluded.confidence, updated_at=excluded.updated_at
            """,
            (app_package, screen_signature, semantic_key, element_id, confidence, datetime.utcnow().isoformat()),
        )


def get_element_hint(app_package: Optional[str], screen_signature: Optional[str], semantic_key: str) -> Optional[Dict[str, Any]]:
    if not app_package or not screen_signature:
        return None
    with _conn() as con:
        row = con.execute(
            """
            SELECT element_id, confidence
            FROM v2_element_memory
            WHERE app_package=? AND screen_signature=? AND semantic_key=?
            """,
            (app_package, screen_signature, semantic_key),
        ).fetchone()
    if not row:
        return None
    return {"element_id": row[0], "confidence": float(row[1])}


def save_task_state(task_state: Dict[str, Any]):
    _migrate_task_file_if_needed()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO v2_task_states (session_id, state_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(session_id)
            DO UPDATE SET state_json=excluded.state_json, updated_at=excluded.updated_at
            """,
            (
                task_state["session_id"],
                json.dumps(task_state),
                datetime.utcnow().isoformat(),
            ),
        )


def load_task_state(session_id: str) -> Optional[Dict[str, Any]]:
    _migrate_task_file_if_needed()
    with _conn() as con:
        row = con.execute(
            "SELECT state_json FROM v2_task_states WHERE session_id=?",
            (session_id,),
        ).fetchone()
    if not row:
        return None
    return json.loads(row[0])


def list_task_states() -> List[Dict[str, Any]]:
    _migrate_task_file_if_needed()
    with _conn() as con:
        rows = con.execute("SELECT state_json FROM v2_task_states ORDER BY updated_at DESC").fetchall()
    return [json.loads(row[0]) for row in rows]


def save_snapshot(screen_id: str, payload: Dict[str, Any]):
    path = SNAPSHOT_DIR / f"{screen_id.replace(':', '_')}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def append_utg_edge(app_package: str, edge: Dict[str, Any]):
    path = UTG_DIR / f"{app_package.replace('.', '_')}.json"
    existing: List[Dict[str, Any]] = []
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = []
    existing.append(edge)
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def _load_task_states() -> Dict[str, Dict[str, Any]]:
    if not TASK_FILE.exists():
        return {}
    try:
        return json.loads(TASK_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _migrate_task_file_if_needed():
    if not TASK_FILE.exists():
        return
    tasks = _load_task_states()
    if not tasks:
        TASK_FILE.unlink(missing_ok=True)
        return
    with _conn() as con:
        for session_id, task_state in tasks.items():
            con.execute(
                """
                INSERT OR IGNORE INTO v2_task_states (session_id, state_json, updated_at)
                VALUES (?, ?, ?)
                """,
                (session_id, json.dumps(task_state), datetime.utcnow().isoformat()),
            )
    TASK_FILE.unlink(missing_ok=True)
