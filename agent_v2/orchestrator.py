from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
from uuid import uuid4

from config.settings import settings
from providers.index import get_provider

from .app_registry import resolve_app
from .decision import decide_next_action
from .intent import (
    classify_intent,
    refine_intent_with_llm,
    should_reclassify_on_context_change,
    should_use_llm_classifier,
)
from .memory_store import (
    get_task_flow,
    list_task_states,
    load_task_state,
    remember_navigation,
    save_snapshot,
    save_task_state,
)
from .normalize import normalize_observation
from .offline_learning import record_transition
from .schemas import (
    ActionResultRequest,
    AgentAction,
    DeviceObservation,
    IntentKind,
    ObserveResponse,
    V2ChatRequest,
    V2ChatResponse,
    V2TaskState,
)


async def handle_chat(req: V2ChatRequest) -> V2ChatResponse:
    existing = _load_state_model(req.session_id)
    if existing and _is_action_confirmation(existing, req.message):
        return _resume_action_after_confirmation(existing, req)

    intent = classify_intent(req.message)
    now = datetime.utcnow().isoformat()

    task_state = existing or V2TaskState(
        session_id=req.session_id,
        user_id=req.user_id,
        device_id=req.device_id,
        created_at=now,
        updated_at=now,
    )
    previous_message = task_state.message
    task_state.message = req.message
    task_state.classifier_calls = 0 if previous_message != req.message else task_state.classifier_calls
    if should_use_llm_classifier(intent):
        intent = await refine_intent_with_llm(intent, req.message, req.provider, req.api_key, req.model, req.base_url)
        if intent.classification_source == "llm":
            task_state.classifier_calls += 1
    task_state.intent = intent
    task_state.device_id = req.device_id
    task_state.user_id = req.user_id
    task_state.updated_at = now
    task_state.mode = intent.kind.value
    task_state.status = "active"
    task_state.current_app = intent.app
    task_state.current_package = intent.target_package

    if intent.kind == IntentKind.SIMPLE_LOCAL:
        task_state.reply = (
            "This request is best handled by the lightweight local/API path. "
            "Use V1 /chat for alarms and direct utilities while V2 automation focuses on app control."
        )
        task_state.pending_action = None
        _persist_state(task_state)
        return V2ChatResponse(mode=task_state.mode, reply=task_state.reply, task_state=task_state)

    if intent.kind == IntentKind.API_TOOL:
        task_state.reply = (
            "This task maps to API-native tools rather than app automation. "
            "Use V1 /chat for Gmail, Calendar, and contacts while V2 focuses on UI execution."
        )
        task_state.pending_action = None
        _persist_state(task_state)
        return V2ChatResponse(mode=task_state.mode, reply=task_state.reply, task_state=task_state)

    if not task_state.latest_observation:
        if "llm_hallucinated_package" in intent.ambiguity_reasons:
            task_state.status = "awaiting_user"
            task_state.pending_action = None
            task_state.reply = (
                "I could not safely map the app to a supported package. "
                "Please name the target app exactly (for example: Swiggy, WhatsApp, Settings)."
            )
            _persist_state(task_state)
            return V2ChatResponse(mode=task_state.mode, reply=task_state.reply, task_state=task_state)
        app = resolve_app(intent.app) if intent.app else None
        package_name = intent.target_package or (str(app["package"]) if app else None)
        if not package_name:
            task_state.pending_action = None
            task_state.reply = (
                "I need either a supported target app or a fresh device screen to continue. "
                "Open the app you want to automate, then send the current screen."
            )
            _persist_state(task_state)
            return V2ChatResponse(mode=task_state.mode, reply=task_state.reply, task_state=task_state)
        next_action = AgentAction(
            id=f"act_{uuid4().hex[:8]}",
            action="open_app",
            package_name=package_name,
            reason_code="bootstrap_open_target_app",
        )
        task_state.pending_action = next_action
        task_state.reply = (
            f"Starting V2 automation for {intent.app or 'the target app'}. "
            "Open the app on device and send the first observation."
        )
        _persist_state(task_state)
        return V2ChatResponse(
            mode=task_state.mode,
            reply=task_state.reply,
            task_state=task_state,
            requires_device_action=True,
            next_action=next_action,
        )

    response = await _decide_from_screen(task_state, req)
    if response.task_state:
        _persist_state(response.task_state)
    return response


async def handle_observation(
    observation: DeviceObservation,
    provider: str = "sarvam",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> ObserveResponse:
    task_state = _load_state_model(observation.session_id) or V2TaskState(
        session_id=observation.session_id,
        user_id=observation.user_id,
        device_id=observation.device_id,
        created_at=datetime.utcnow().isoformat(),
        updated_at=datetime.utcnow().isoformat(),
    )
    original_fingerprint = _state_persistence_fingerprint(task_state)

    normalized = normalize_observation(observation)
    save_snapshot(normalized.screen_id, normalized.model_dump())

    previous_signature = task_state.latest_screen.screen_signature if task_state.latest_screen else None
    previous_structural = task_state.latest_screen.structural_signature if task_state.latest_screen else None
    if previous_signature and task_state.pending_action:
        remember_navigation(
            app_package=normalized.app_package or task_state.current_package or "unknown",
            screen_signature=previous_signature,
            action_key=_action_to_key(task_state.pending_action),
            next_screen_signature=normalized.screen_signature,
            success=True,
        )
        record_transition(
            app_package=normalized.app_package or task_state.current_package or "unknown",
            from_signature=previous_signature,
            action_key=_action_to_key(task_state.pending_action),
            to_signature=normalized.screen_signature,
            success=True,
        )

    executed_action = task_state.pending_action
    was_scroll_action = bool(executed_action and executed_action.action == "scroll")
    task_state.latest_observation = observation
    task_state.latest_screen = normalized
    task_state.current_package = normalized.app_package or task_state.current_package
    task_state.updated_at = datetime.utcnow().isoformat()
    task_state.recovery_attempts = 0
    task_state.last_error = None
    task_state.history.append(
        {
            "at": task_state.updated_at,
            "type": "observation",
            "foreground_app": observation.foreground_app,
            "screen_signature": normalized.screen_signature,
            "structural_signature": normalized.structural_signature,
            "anchors": normalized.anchors,
        }
    )
    task_state.history = task_state.history[-50:]

    if executed_action and executed_action.action == "request_observation":
        task_state.history.append(
            {
                "at": task_state.updated_at,
                "type": "observation_refresh",
                "reason_code": executed_action.reason_code,
                "screen_signature": normalized.screen_signature,
            }
        )
        task_state.history = task_state.history[-50:]

    if was_scroll_action:
        if previous_structural and previous_structural == normalized.structural_signature:
            task_state.stagnant_scrolls += 1
        else:
            task_state.stagnant_scrolls = 0
    elif not was_scroll_action:
        task_state.stagnant_scrolls = 0

    skip_reclassification = _is_expected_open_app_transition(task_state, observation.foreground_app)
    if task_state.intent and not skip_reclassification and should_reclassify_on_context_change(task_state.intent, observation.foreground_app):
        if task_state.classifier_calls < settings.v2_max_classifier_calls_per_task:
            refreshed = classify_intent(task_state.message)
            if should_use_llm_classifier(refreshed):
                refreshed = await refine_intent_with_llm(
                    refreshed,
                    task_state.message,
                    provider,
                    api_key,
                    model,
                    base_url,
                )
                if refreshed.classification_source == "llm":
                    task_state.classifier_calls += 1
            task_state.intent = refreshed
            task_state.current_app = refreshed.app or task_state.current_app
            task_state.current_package = refreshed.target_package or task_state.current_package
            task_state.history.append(
                {
                    "at": task_state.updated_at,
                    "type": "context_reclassification",
                    "foreground_app": observation.foreground_app,
                    "new_target_package": task_state.current_package,
                    "source": refreshed.classification_source,
                }
            )
        else:
            task_state.history.append(
                {
                    "at": task_state.updated_at,
                    "type": "context_reclassification_skipped",
                    "reason": "classifier_budget_reached",
                    "foreground_app": observation.foreground_app,
                }
            )
    task_state.history = task_state.history[-50:]

    reply = "Observation received."
    next_action = None
    if task_state.intent:
        decision_response = await _decide_from_screen(
            task_state,
            V2ChatRequest(
                message=task_state.message,
                session_id=task_state.session_id,
                user_id=task_state.user_id,
                provider=provider,
                api_key=api_key,
                model=model,
                base_url=base_url,
                device_id=task_state.device_id,
            ),
        )
        task_state = decision_response.task_state or task_state
        reply = decision_response.reply
        next_action = decision_response.next_action

    _persist_state_if_changed(task_state, original_fingerprint)
    return ObserveResponse(
        reply=reply,
        task_state=task_state,
        normalized_screen=normalized,
        next_action=next_action,
        requires_device_action=next_action is not None and next_action.action not in ("complete", "ask_user"),
    )


async def handle_action_result(
    req: ActionResultRequest,
    provider: str = "sarvam",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> ObserveResponse:
    task_state = _load_state_model(req.session_id)
    if not task_state:
        task_state = V2TaskState(
            session_id=req.session_id,
            user_id=req.user_id,
            device_id=req.device_id,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat(),
        )

    task_state.history.append(
        {
            "at": datetime.utcnow().isoformat(),
            "type": "action_result",
            "action": req.action.model_dump(),
            "success": req.success,
            "result": req.result,
        }
    )
    task_state.history = task_state.history[-50:]
    task_state.pending_action = None
    task_state.updated_at = datetime.utcnow().isoformat()

    if not req.success and task_state.latest_screen:
        task_state.recovery_attempts += 1
        task_state.last_error = req.result or "Device action failed."
        remember_navigation(
            app_package=task_state.current_package or task_state.latest_screen.app_package or "unknown",
            screen_signature=task_state.latest_screen.screen_signature,
            action_key=_action_to_key(req.action),
            next_screen_signature=task_state.latest_screen.screen_signature,
            success=False,
        )
        record_transition(
            app_package=task_state.current_package or task_state.latest_screen.app_package or "unknown",
            from_signature=task_state.latest_screen.screen_signature,
            action_key=_action_to_key(req.action),
            to_signature=task_state.latest_screen.screen_signature,
            success=False,
        )
        if task_state.recovery_attempts > settings.v2_max_recovery_attempts:
            task_state.status = "awaiting_user"
            task_state.reply = (
                "I hit repeated automation failures on this screen. "
                "Please adjust the app manually or send a fresh screen state."
            )
            _persist_state(task_state)
            return ObserveResponse(reply=task_state.reply, task_state=task_state)

    if req.observation:
        return await handle_observation(
            req.observation,
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
        )

    task_state.reply = req.result or ("Action succeeded." if req.success else "Action failed.")
    _persist_state(task_state)
    return ObserveResponse(reply=task_state.reply, task_state=task_state)


def get_tasks(session_id: Optional[str] = None):
    tasks = [_load_state_model(item["session_id"]) for item in list_task_states()]
    filtered = [task for task in tasks if task]
    if session_id:
        filtered = [task for task in filtered if task.session_id == session_id]
    return filtered


def cancel_task(session_id: str, reason: str = "user_cancelled") -> Optional[V2TaskState]:
    task_state = _load_state_model(session_id)
    if not task_state:
        return None
    task_state.status = "cancelled"
    task_state.pending_action = None
    task_state.reply = "Automation stopped."
    task_state.updated_at = datetime.utcnow().isoformat()
    task_state.history.append(
        {
            "at": task_state.updated_at,
            "type": "task_cancelled",
            "reason": reason,
        }
    )
    task_state.history = task_state.history[-50:]
    _persist_state(task_state)
    return task_state


async def _decide_from_screen(task_state: V2TaskState, req: V2ChatRequest) -> V2ChatResponse:
    screen = task_state.latest_screen
    if not task_state.intent or not screen:
        task_state.reply = "Need a fresh device observation before deciding the next automation step."
        return V2ChatResponse(mode=task_state.mode, reply=task_state.reply, task_state=task_state)

    flow_hint = get_task_flow(_task_key(task_state))
    memory_note = f"Known flow confidence: {flow_hint['confidence']:.2f}" if flow_hint else None
    next_action, explanation = decide_next_action(task_state.intent, screen)

    if task_state.intent.requires_llm and _should_use_llm(task_state, next_action):
        llm_action = await _ask_llm_for_action(task_state, req)
        if llm_action is not None:
            next_action = llm_action

    if next_action and next_action.action == "scroll" and task_state.stagnant_scrolls >= 3:
        next_action = AgentAction(
            id=f"act_{uuid4().hex[:8]}",
            action="ask_user",
            reason_code="scroll_exhausted_no_progress",
            metadata={
                "message": (
                    "I tried scrolling but the screen did not change twice in a row. "
                    "Please open a different section/filter or confirm how to proceed."
                )
            },
        )
        explanation = "Stopped automatic scrolling because the UI did not progress."

    task_state.pending_action = next_action
    task_state.reply = explanation or _default_reply(task_state, next_action, memory_note)
    if next_action is None:
        if task_state.intent and "llm_hallucinated_package" in task_state.intent.ambiguity_reasons:
            task_state.status = "awaiting_user"
            task_state.reply = (
                "I couldn't verify the app package from the model output. "
                "Please confirm the app name so I can continue safely."
            )
        else:
            task_state.status = "idle"
    elif next_action.action == "complete":
        task_state.status = "completed"
    elif next_action.action == "ask_user":
        task_state.status = "awaiting_user"
    else:
        task_state.status = "active"

    return V2ChatResponse(
        mode=task_state.mode,
        reply=task_state.reply,
        task_state=task_state,
        requires_device_action=next_action is not None and next_action.action not in ("complete", "ask_user"),
        next_action=next_action,
    )


async def _ask_llm_for_action(task_state: V2TaskState, req: V2ChatRequest) -> Optional[AgentAction]:
    if not req.api_key:
        return None
    if task_state.llm_calls >= settings.v2_max_llm_calls_per_task:
        task_state.reply = "LLM planning budget reached for this task. Need a more explicit screen or a simpler instruction."
        return None
    if task_state.estimated_llm_tokens >= settings.v2_llm_token_budget:
        task_state.reply = "Token budget reached for this task. Please narrow the request or resend from the current screen."
        return None

    llm = get_provider(provider=req.provider, api_key=req.api_key, model=req.model, base_url=req.base_url)
    screen = task_state.latest_screen
    system_prompt = (
        "You are AgentX V2. Return only valid JSON with keys: "
        "id, action, element_id, input_text, package_name, direction, timeout_ms, reason_code. "
        "Choose one action from: open_app, tap_element, type_text, scroll, press_back, press_home, request_observation, wait_for, complete."
    )
    user_prompt = {
        "task": task_state.message,
        "app": task_state.current_app,
        "package": task_state.current_package,
        "constraints": task_state.intent.constraints.model_dump(),
        "anchors": screen.anchors,
        "elements": [element.model_dump() for element in screen.elements[:25]],
        "html": screen.html[:4000],
    }

    try:
        estimated_tokens = _estimate_tokens(user_prompt["html"]) + _estimate_tokens(task_state.message)
        content = await llm.chat(
            messages=[{"role": "user", "content": json.dumps(user_prompt)}],
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=300,
        )
        task_state.llm_calls += 1
        task_state.estimated_llm_tokens += estimated_tokens + _estimate_tokens(content)
        parsed = json.loads(content)
        return AgentAction(**parsed)
    except Exception:
        return None


def _default_reply(task_state: V2TaskState, next_action: Optional[AgentAction], memory_note: Optional[str]) -> str:
    if next_action is None:
        return "No device action available yet."
    if next_action.action == "complete":
        return str(next_action.metadata.get("message", "Task completed."))
    if next_action.action == "ask_user":
        return str(next_action.metadata.get("message", "Need clarification from user."))
    base = f"Prepared next action: {next_action.action}."
    return f"{base} {memory_note}" if memory_note else base


def _persist_state(task_state: V2TaskState):
    save_task_state(task_state.model_dump(mode="json"))


def _persist_state_if_changed(task_state: V2TaskState, previous_fingerprint: str):
    if _state_persistence_fingerprint(task_state) != previous_fingerprint:
        _persist_state(task_state)


def _load_state_model(session_id: str) -> Optional[V2TaskState]:
    raw = load_task_state(session_id)
    return V2TaskState.model_validate(raw) if raw else None


def _action_to_key(action: AgentAction) -> str:
    if action.action == "tap_element":
        return f"tap:{action.element_id}"
    if action.action == "type_text":
        return f"type:{action.element_id}:{action.input_text or ''}"
    if action.action == "scroll":
        return f"scroll:{action.direction or 'down'}"
    if action.action == "open_app":
        return f"open:{action.package_name or ''}"
    return action.action


def _task_key(task_state: V2TaskState) -> str:
    app = task_state.current_package or task_state.current_app or "generic"
    query = task_state.intent.constraints.item_query if task_state.intent else None
    return f"{app}::{query or task_state.mode}"


def _should_use_llm(task_state: V2TaskState, next_action: Optional[AgentAction]) -> bool:
    if next_action is None:
        return True
    if task_state.last_error:
        return True
    if task_state.recovery_attempts > 0:
        return True
    if next_action.action == "request_observation" and _recent_observation_requests(task_state) >= 2:
        return True
    if next_action.action == "wait_for":
        return True
    if next_action.action == "scroll" and _recent_scrolls(task_state) >= 2:
        return True
    if next_action.action == "ask_user" and task_state.intent and task_state.intent.extracted_query:
        return True
    screen_type = (task_state.latest_screen.metadata.get("screen_type") if task_state.latest_screen else None)
    if next_action.action == "tap_element" and screen_type == "unknown":
        return True
    return False


def _recent_scrolls(task_state: V2TaskState) -> int:
    return sum(1 for item in task_state.history[-5:] if item.get("type") == "action_result" and item.get("action", {}).get("action") == "scroll")


def _recent_observation_requests(task_state: V2TaskState) -> int:
    recent_history = task_state.history[-8:]
    return sum(
        1
        for item in recent_history
        if (
            (item.get("type") == "action_result" and item.get("action", {}).get("action") == "request_observation")
            or item.get("type") == "observation_refresh"
        )
    )


def _estimate_tokens(value) -> int:
    text = value if isinstance(value, str) else json.dumps(value)
    return max(1, len(text) // 4)


def _state_persistence_fingerprint(task_state: V2TaskState) -> str:
    signature = task_state.latest_screen.screen_signature if task_state.latest_screen else None
    fingerprint_payload = {
        "status": task_state.status,
        "mode": task_state.mode,
        "message": task_state.message,
        "intent": task_state.intent.model_dump(mode="json") if task_state.intent else None,
        "current_app": task_state.current_app,
        "current_package": task_state.current_package,
        "pending_action": task_state.pending_action.model_dump(mode="json") if task_state.pending_action else None,
        "reply": task_state.reply,
        "llm_calls": task_state.llm_calls,
        "classifier_calls": task_state.classifier_calls,
        "recovery_attempts": task_state.recovery_attempts,
        "stagnant_scrolls": task_state.stagnant_scrolls,
        "last_error": task_state.last_error,
        "screen_signature": signature,
    }
    return json.dumps(fingerprint_payload, sort_keys=True)


def _is_expected_open_app_transition(task_state: V2TaskState, foreground_app: Optional[str]) -> bool:
    if not task_state.intent or not task_state.pending_action:
        return False
    if task_state.pending_action.action != "open_app":
        return False
    target_package = task_state.pending_action.package_name or task_state.intent.target_package
    if not target_package:
        return False
    return foreground_app != target_package


def _is_action_confirmation(task_state: V2TaskState, message: str) -> bool:
    if task_state.status != "awaiting_user":
        return False
    if not task_state.pending_action or task_state.pending_action.action != "ask_user":
        return False
    if task_state.pending_action.reason_code not in {"safety_checkout_boundary", "safety_irreversible_action"}:
        return False
    lowered = (message or "").strip().lower()
    return lowered in {"yes", "y", "confirm", "continue", "proceed", "go ahead", "ok", "okay"}


def _resume_action_after_confirmation(task_state: V2TaskState, req: V2ChatRequest) -> V2ChatResponse:
    confirm_action = (task_state.pending_action.metadata or {}).get("confirm_action") if task_state.pending_action else None
    if not isinstance(confirm_action, dict):
        task_state.reply = "Checkout confirmation noted, but I could not find the target button. Please send a fresh screen."
        _persist_state(task_state)
        return V2ChatResponse(mode=task_state.mode, reply=task_state.reply, task_state=task_state)

    action_name = str(confirm_action.get("action", "tap_element"))
    if action_name not in {"tap_element", "type_text", "scroll", "request_observation", "wait_for", "press_back", "press_home", "open_app"}:
        action_name = "tap_element"
    next_action = AgentAction(
        id=f"act_{uuid4().hex[:8]}",
        action=action_name,
        element_id=confirm_action.get("element_id"),
        input_text=confirm_action.get("input_text"),
        package_name=confirm_action.get("package_name"),
        direction=confirm_action.get("direction"),
        timeout_ms=confirm_action.get("timeout_ms"),
        reason_code=str(confirm_action.get("reason_code", "user_confirm_checkout")),
    )
    task_state.status = "active"
    task_state.pending_action = next_action
    task_state.reply = "Confirmed. Continuing checkout flow now."
    task_state.updated_at = datetime.utcnow().isoformat()
    task_state.history.append(
        {
            "at": task_state.updated_at,
            "type": "user_confirmation",
            "message": req.message,
            "reason": task_state.pending_action.reason_code if task_state.pending_action else "safety_confirmation",
        }
    )
    task_state.history = task_state.history[-50:]
    _persist_state(task_state)
    return V2ChatResponse(
        mode=task_state.mode,
        reply=task_state.reply,
        task_state=task_state,
        requires_device_action=True,
        next_action=next_action,
    )
