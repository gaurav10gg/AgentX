from __future__ import annotations

from typing import Optional

from .constraints import filter_candidates, has_hard_constraint_conflict
from .memory_store import get_best_navigation_action, get_element_hint, remember_element
from .schemas import AgentAction, IntentResult, NormalizedScreen


def decide_next_action(
    intent: IntentResult,
    screen: NormalizedScreen,
    memory_threshold: float = 0.82,
):
    if intent.kind.value == "ui_automation" and intent.target_package and not screen.app_package:
        return AgentAction(id="open_target_app", action="open_app", package_name=intent.target_package), None

    filtered = filter_candidates(screen, intent.constraints)
    if has_hard_constraint_conflict(filtered, intent.constraints):
        return AgentAction(
            id="ask_constraints",
            action="ask_user",
            reason_code="constraint_no_match",
            metadata={"message": "No option meets all hard constraints right now."},
        ), "No option meets all hard constraints right now."

    memory_action = get_best_navigation_action(screen.app_package, screen.screen_signature)
    if memory_action and memory_action["confidence"] >= memory_threshold:
        parsed = _parse_action_key(memory_action["action_key"])
        if parsed:
            return parsed, "Using memory shortcut for this screen."

    search_hint = get_element_hint(screen.app_package, screen.screen_signature, "search")
    query = intent.extracted_query or intent.constraints.item_query
    if search_hint and query:
        return AgentAction(
            id="type_search_from_memory",
            action="type_text",
            element_id=search_hint["element_id"],
            input_text=query,
            reason_code="memory_search_input",
        ), None

    for element in screen.elements:
        lowered = element.label.lower()
        if query and element.editable and ("search" in lowered or "search" in (element.resource_id or "").lower()):
            remember_element(screen.app_package or "", screen.screen_signature, "search", element.id)
            return AgentAction(
                id="type_search",
                action="type_text",
                element_id=element.id,
                input_text=query,
                reason_code="heuristic_search_input",
            ), None

    if filtered:
        best = filtered[0]
        return AgentAction(
            id="tap_best_candidate",
            action="tap_element",
            element_id=str(best["element_id"]),
            reason_code="constraint_best_candidate",
            metadata={"candidate": best},
        ), None

    for element in screen.elements:
        lowered = element.label.lower()
        if "checkout" in lowered or "place order" in lowered:
            return AgentAction(
                id="stop_before_checkout",
                action="complete",
                reason_code="safety_checkout_boundary",
                metadata={"message": "Reached checkout boundary. Waiting for explicit confirmation."},
            ), "Reached checkout boundary and stopped for safety."

    for element in screen.elements:
        if element.scrollable:
            return AgentAction(
                id="scroll_for_more",
                action="scroll",
                element_id=element.id,
                direction="down",
                reason_code="explore_more_options",
            ), None

    return AgentAction(
        id="wait_for_screen",
        action="wait_for",
        timeout_ms=1500,
        reason_code="waiting_for_ui_stability",
    ), None


def _parse_action_key(action_key: str) -> Optional[AgentAction]:
    if not action_key:
        return None
    parts = action_key.split(":", 2)
    action = parts[0]
    if action == "tap" and len(parts) >= 2:
        return AgentAction(id="memory_tap", action="tap_element", element_id=parts[1], reason_code="memory_navigation")
    if action == "type" and len(parts) == 3:
        return AgentAction(
            id="memory_type",
            action="type_text",
            element_id=parts[1],
            input_text=parts[2],
            reason_code="memory_navigation",
        )
    if action == "scroll":
        return AgentAction(id="memory_scroll", action="scroll", direction="down", reason_code="memory_navigation")
    if action == "open" and len(parts) >= 2:
        return AgentAction(
            id="memory_open_app",
            action="open_app",
            package_name=parts[1],
            reason_code="memory_navigation",
        )
    return None
