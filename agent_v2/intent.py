from __future__ import annotations

import json
import re
from typing import Optional

from config.settings import settings
from providers.index import get_provider

from .app_registry import find_matching_apps, resolve_app
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
        candidates = find_matching_apps(open_match.group(2))
        if len(candidates) == 1:
            app = candidates[0]
            return _ui_intent(raw, app["name"], app["package"], constraints, requires_llm=False, confidence=0.97)
        if len(candidates) > 1:
            return _ambiguous_ui(raw, constraints, reasons=["multiple_app_candidates"])

    app_match = find_matching_apps(raw)
    if len(app_match) == 1:
        app = app_match[0]
        return _ui_intent(raw, app["name"], app["package"], constraints, requires_llm=False, confidence=0.95)
    if len(app_match) > 1:
        return _ambiguous_ui(raw, constraints, reasons=["multiple_app_candidates"])

    if REMINDER_RE.search(raw):
        is_ui_reminder = FUTURE_RE.search(raw) and _looks_like_app_automation(lowered, constraints)
        return IntentResult(
            raw_message=raw,
            kind=IntentKind.SCHEDULED_UI_AUTOMATION if is_ui_reminder else IntentKind.SIMPLE_LOCAL,
            task=raw,
            app="Swiggy" if is_ui_reminder else None,
            target_package="in.swiggy.android" if is_ui_reminder else None,
            constraints=constraints,
            requires_llm=False,
            extracted_query=constraints.item_query,
            confidence=0.94 if is_ui_reminder else 0.96,
            ambiguity_reasons=[],
            classification_source="heuristic",
        )

    if API_RE.search(raw):
        return IntentResult(
            raw_message=raw,
            kind=IntentKind.API_TOOL,
            task=raw,
            constraints=constraints,
            requires_llm=True,
            confidence=0.9,
            ambiguity_reasons=[],
            classification_source="heuristic",
        )

    if _looks_like_app_automation(lowered, constraints):
        app = resolve_app("swiggy") if any(token in lowered for token in ("swiggy", "food", "biryani", "pizza", "burger")) else None
        if app:
            return IntentResult(
                raw_message=raw,
                kind=IntentKind.UI_AUTOMATION,
                task=raw,
                app=str(app["name"]),
                target_package=str(app["package"]),
                constraints=constraints,
                requires_llm=True,
                extracted_query=constraints.item_query,
                confidence=0.86 if constraints.item_query else 0.8,
                ambiguity_reasons=[] if constraints.item_query else ["implicit_food_task"],
                classification_source="heuristic",
            )
        return _ambiguous_ui(raw, constraints, reasons=["food_task_without_app"])

    return _ambiguous_ui(raw, constraints, reasons=["no_app_food_or_tool_signal"])


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
    if not should_use_llm_classifier(base):
        return base

    llm = get_provider(provider=provider, api_key=api_key, model=model, base_url=base_url)
    system_prompt = (
        "Classify the user request into strict JSON with keys: "
        "kind, task, app, target_package, requires_llm, extracted_query, confidence, ambiguity_reasons. "
        "kind must be one of: simple_local, api_tool, ui_automation, scheduled_ui_automation. "
        "target_package must be null unless app is one of known apps. Return JSON only."
    )
    user_prompt = {
        "message": message,
        "known_apps": [
            {"name": "Swiggy", "package": "in.swiggy.android"},
            {"name": "WhatsApp", "package": "com.whatsapp"},
            {"name": "Settings", "package": "com.android.settings"},
        ],
        "constraints": base.constraints.model_dump(),
        "base_intent": base.model_dump(),
    }

    try:
        content = await llm.chat(
            messages=[{"role": "user", "content": json.dumps(user_prompt)}],
            system_prompt=system_prompt,
            temperature=settings.v2_classifier_temperature,
            max_tokens=220,
        )
        parsed = json.loads(content)
        kind_value = parsed.get("kind", base.kind.value)
        if kind_value not in {item.value for item in IntentKind}:
            return base.model_copy(update={"ambiguity_reasons": _merge_list(base.ambiguity_reasons, ["llm_invalid_kind"])})

        app_name = parsed.get("app")
        app = resolve_app(app_name)
        llm_pkg = parsed.get("target_package")
        hallucinated_package = bool(llm_pkg and (not app or str(app.get("package")) != str(llm_pkg)))

        if hallucinated_package:
            # Hard rule: never trust package names that do not normalize through registry.
            return base.model_copy(
                update={
                    "ambiguity_reasons": _merge_list(base.ambiguity_reasons, ["llm_hallucinated_package"]),
                    "classification_source": "llm",
                    "confidence": min(base.confidence, 0.7),
                }
            )

        merged_constraints = _merge_constraints(base.constraints, extract_constraints(message))
        return IntentResult(
            raw_message=message,
            kind=IntentKind(kind_value),
            task=str(parsed.get("task") or base.task),
            app=str(app["name"]) if app else base.app,
            target_package=str(app["package"]) if app else base.target_package,
            constraints=merged_constraints,
            requires_llm=bool(parsed.get("requires_llm", True)),
            time_context=base.time_context,
            extracted_query=parsed.get("extracted_query") or base.extracted_query or merged_constraints.item_query,
            confidence=float(parsed.get("confidence", base.confidence)),
            ambiguity_reasons=_merge_list(base.ambiguity_reasons, parsed.get("ambiguity_reasons") or []),
            classification_source="llm",
        )
    except Exception:
        return base.model_copy(update={"ambiguity_reasons": _merge_list(base.ambiguity_reasons, ["llm_classifier_failed"])})


def should_use_llm_classifier(intent: IntentResult) -> bool:
    if intent.classification_source == "llm":
        return False
    if intent.confidence < settings.v2_intent_confidence_accept_threshold:
        return True
    if intent.ambiguity_reasons:
        return True
    if intent.target_package is None and intent.kind == IntentKind.UI_AUTOMATION:
        return True
    return False


def should_reclassify_on_context_change(intent: IntentResult, foreground_app: Optional[str]) -> bool:
    if not foreground_app:
        return False
    if intent.target_package is None:
        return True
    return foreground_app != intent.target_package


def _ui_intent(
    raw_message: str,
    app_name: object,
    package_name: object,
    constraints: ConstraintSet,
    requires_llm: bool,
    confidence: float,
) -> IntentResult:
    return IntentResult(
        raw_message=raw_message,
        kind=IntentKind.UI_AUTOMATION,
        task=raw_message,
        app=str(app_name),
        target_package=str(package_name),
        constraints=constraints,
        requires_llm=requires_llm,
        extracted_query=constraints.item_query,
        confidence=confidence,
        ambiguity_reasons=[],
        classification_source="heuristic",
    )


def _ambiguous_ui(raw_message: str, constraints: ConstraintSet, reasons: list[str]) -> IntentResult:
    return IntentResult(
        raw_message=raw_message,
        kind=IntentKind.UI_AUTOMATION,
        task=raw_message,
        constraints=constraints,
        requires_llm=True,
        extracted_query=constraints.item_query,
        confidence=0.45,
        ambiguity_reasons=reasons,
        classification_source="heuristic",
    )


def _looks_like_app_automation(lowered: str, constraints: ConstraintSet) -> bool:
    return bool(
        FOOD_RE.search(lowered)
        or constraints.item_query
        or any(token in lowered for token in ("swiggy", "checkout", "cart", "delivery", "restaurant"))
    )


def _merge_constraints(primary: ConstraintSet, secondary: ConstraintSet) -> ConstraintSet:
    # Deterministic numeric extraction takes precedence over model-inferred values.
    return ConstraintSet(
        price_max=primary.price_max if primary.price_max is not None else secondary.price_max,
        rating_min=primary.rating_min if primary.rating_min is not None else secondary.rating_min,
        payment=primary.payment or secondary.payment,
        cuisine=primary.cuisine or secondary.cuisine,
        item_query=primary.item_query or secondary.item_query,
        distance_max_km=primary.distance_max_km if primary.distance_max_km is not None else secondary.distance_max_km,
        delivery_time_max_min=(
            primary.delivery_time_max_min
            if primary.delivery_time_max_min is not None
            else secondary.delivery_time_max_min
        ),
        hard=list(dict.fromkeys(primary.hard + secondary.hard)),
        soft=list(dict.fromkeys(primary.soft + secondary.soft)),
    )


def _merge_list(base: list[str], extra: list[str]) -> list[str]:
    return list(dict.fromkeys([str(item) for item in base + extra if str(item).strip()]))
