from __future__ import annotations

import json
import re
from typing import Optional

from providers.index import get_provider

from .app_registry import resolve_app
from .constraints import extract_constraints
from .schemas import ConstraintSet, IntentKind, IntentResult


REMINDER_RE = re.compile(r"\b(remind me|alarm|wake me|alert me|ping me|notify me)\b", re.IGNORECASE)
FUTURE_RE = re.compile(r"\b(in \d+|tomorrow|tonight|later|after \d+|next )\b", re.IGNORECASE)
OPEN_APP_RE = re.compile(r"\b(open|launch|start)\s+([a-zA-Z ]+)", re.IGNORECASE)
FOOD_RE = re.compile(r"\b(order|buy|get|search|find)\b.*\b(food|meal|biryani|pizza|burger|roll|rice)\b", re.IGNORECASE)
API_RE = re.compile(r"\b(email|gmail|calendar|event|contact|contacts|schedule meeting)\b", re.IGNORECASE)


def classify_intent(message: str) -> IntentResult:
    raw = (message or "").strip()
    lowered = raw.lower()
    constraints = extract_constraints(raw)

    open_match = OPEN_APP_RE.search(raw)
    if open_match:
        app = resolve_app(open_match.group(2))
        if app:
            return _ui_intent(raw, app["name"], app["package"], constraints, requires_llm=False)

    app = resolve_app(raw)
    if app:
        return _ui_intent(raw, app["name"], app["package"], constraints, requires_llm=False)

    if REMINDER_RE.search(raw):
        is_ui_reminder = FUTURE_RE.search(raw) and _looks_like_app_automation(lowered, constraints)
        return IntentResult(
            kind=IntentKind.SCHEDULED_UI_AUTOMATION if is_ui_reminder else IntentKind.SIMPLE_LOCAL,
            task=raw,
            app="Swiggy" if is_ui_reminder else None,
            target_package="in.swiggy.android" if is_ui_reminder else None,
            constraints=constraints,
            requires_llm=False,
            extracted_query=constraints.item_query,
        )

    if API_RE.search(raw):
        return IntentResult(
            kind=IntentKind.API_TOOL,
            task=raw,
            constraints=constraints,
            requires_llm=True,
        )

    if _looks_like_app_automation(lowered, constraints):
        app = resolve_app("swiggy") if any(token in lowered for token in ("swiggy", "food", "biryani", "pizza", "burger")) else None
        return IntentResult(
            kind=IntentKind.UI_AUTOMATION,
            task=raw,
            app=str(app["name"]) if app else None,
            target_package=str(app["package"]) if app else None,
            constraints=constraints,
            requires_llm=True,
            extracted_query=constraints.item_query,
        )

    return IntentResult(
        kind=IntentKind.UI_AUTOMATION,
        task=raw,
        app=None,
        target_package=None,
        constraints=constraints,
        requires_llm=True,
        extracted_query=constraints.item_query,
    )


async def refine_intent_with_llm(
    base: IntentResult,
    message: str,
    provider: str,
    api_key: Optional[str],
    model: Optional[str],
    base_url: Optional[str],
) -> IntentResult:
    if not api_key:
        return base
    if not _is_ambiguous(base):
        return base

    llm = get_provider(provider=provider, api_key=api_key, model=model, base_url=base_url)
    system_prompt = (
        "Classify the user request into JSON with keys: "
        "kind, task, app, requires_llm, extracted_query. "
        "kind must be one of: simple_local, api_tool, ui_automation, scheduled_ui_automation. "
        "If the task is food ordering on Android, prefer app='Swiggy'. Return JSON only."
    )
    user_prompt = {
        "message": message,
        "known_apps": ["Swiggy", "WhatsApp", "Settings"],
        "constraints": base.constraints.model_dump(),
    }

    try:
        content = await llm.chat(
            messages=[{"role": "user", "content": json.dumps(user_prompt)}],
            system_prompt=system_prompt,
            temperature=0.0,
            max_tokens=180,
        )
        parsed = json.loads(content)
        app = resolve_app(parsed.get("app"))
        kind_value = parsed.get("kind", base.kind.value)
        return IntentResult(
            kind=IntentKind(kind_value),
            task=str(parsed.get("task") or base.task),
            app=str(app["name"]) if app else parsed.get("app") or base.app,
            target_package=str(app["package"]) if app else base.target_package,
            constraints=_merge_constraints(base.constraints, extract_constraints(message)),
            requires_llm=bool(parsed.get("requires_llm", True)),
            time_context=base.time_context,
            extracted_query=parsed.get("extracted_query") or base.extracted_query or base.constraints.item_query,
        )
    except Exception:
        return base


def _ui_intent(task: str, app_name: object, package_name: object, constraints: ConstraintSet, requires_llm: bool) -> IntentResult:
    return IntentResult(
        kind=IntentKind.UI_AUTOMATION,
        task=task,
        app=str(app_name),
        target_package=str(package_name),
        constraints=constraints,
        requires_llm=requires_llm,
        extracted_query=constraints.item_query,
    )


def _looks_like_app_automation(lowered: str, constraints: ConstraintSet) -> bool:
    return bool(
        FOOD_RE.search(lowered)
        or constraints.item_query
        or any(token in lowered for token in ("swiggy", "checkout", "cart", "delivery", "restaurant"))
    )


def _is_ambiguous(intent: IntentResult) -> bool:
    if intent.kind in (IntentKind.SIMPLE_LOCAL, IntentKind.API_TOOL):
        return False
    return intent.app is None or intent.target_package is None or intent.extracted_query is None


def _merge_constraints(primary: ConstraintSet, secondary: ConstraintSet) -> ConstraintSet:
    return ConstraintSet(
        price_max=primary.price_max or secondary.price_max,
        rating_min=primary.rating_min or secondary.rating_min,
        payment=primary.payment or secondary.payment,
        cuisine=primary.cuisine or secondary.cuisine,
        item_query=primary.item_query or secondary.item_query,
        distance_max_km=primary.distance_max_km or secondary.distance_max_km,
        delivery_time_max_min=primary.delivery_time_max_min or secondary.delivery_time_max_min,
        hard=list(dict.fromkeys(primary.hard + secondary.hard)),
        soft=list(dict.fromkeys(primary.soft + secondary.soft)),
    )
