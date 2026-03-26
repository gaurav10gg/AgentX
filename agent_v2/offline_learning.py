from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from .memory_store import append_utg_edge, remember_task_flow


SAFE_EXPLORATION_ACTIONS = ("tap_element", "scroll", "press_back", "wait_for")


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


def build_safe_exploration_plan(screen_signature: str, candidate_actions: List[Dict[str, object]]) -> List[Dict[str, object]]:
    plan: List[Dict[str, object]] = []
    for candidate in candidate_actions:
        action = str(candidate.get("action", ""))
        if action not in SAFE_EXPLORATION_ACTIONS:
            continue
        plan.append(
            {
                "screen_signature": screen_signature,
                "action": action,
                "target": candidate.get("target"),
                "reason": candidate.get("reason", "offline_exploration"),
            }
        )
    return plan[:8]
