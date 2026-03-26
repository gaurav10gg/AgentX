from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from .memory_store import append_utg_edge, remember_task_flow


def record_transition(app_package: str, from_signature: str, action_key: str, to_signature: str, success: bool):
    append_utg_edge(
        app_package,
        {
            "from": from_signature,
            "action": action_key,
            "to": to_signature,
            "success": success,
            "at": datetime.utcnow().isoformat(),
        },
    )


def store_exploration_flow(task_key: str, flow: List[Dict[str, object]], confidence: float = 0.7):
    remember_task_flow(task_key, flow, confidence=confidence)
