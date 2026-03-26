from __future__ import annotations

import re

from .app_registry import resolve_app
from .constraints import extract_constraints
from .schemas import IntentKind, IntentResult


REMINDER_RE = re.compile(r"\b(remind me|alarm|wake me|alert me)\b", re.IGNORECASE)
FUTURE_RE = re.compile(r"\b(in \d+|tomorrow|tonight|later|after \d+)\b", re.IGNORECASE)
OPEN_APP_RE = re.compile(r"\b(open|launch)\s+([a-zA-Z ]+)", re.IGNORECASE)


def classify_intent(message: str) -> IntentResult:
    raw = (message or "").strip()
    lowered = raw.lower()
    constraints = extract_constraints(raw)

    open_match = OPEN_APP_RE.search(raw)
    if open_match:
        app = resolve_app(open_match.group(2))
        if app:
            return IntentResult(
                kind=IntentKind.UI_AUTOMATION,
                task=f"open {app['name']}",
                app=str(app["name"]),
                target_package=str(app["package"]),
                constraints=constraints,
                requires_llm=False,
            )

    app = resolve_app(raw)
    if app:
        return IntentResult(
            kind=IntentKind.UI_AUTOMATION,
            task=raw,
            app=str(app["name"]),
            target_package=str(app["package"]),
            constraints=constraints,
            requires_llm=False,
        )

    if REMINDER_RE.search(raw):
        kind = IntentKind.SCHEDULED_UI_AUTOMATION if FUTURE_RE.search(raw) and "swiggy" in lowered else IntentKind.SIMPLE_LOCAL
        return IntentResult(
            kind=kind,
            task=raw,
            app="Swiggy" if "swiggy" in lowered else None,
            target_package="in.swiggy.android" if "swiggy" in lowered else None,
            constraints=constraints,
            requires_llm=False,
        )

    if any(token in lowered for token in ("swiggy", "order food", "order ", "checkout", "cart", "biryani", "pizza", "burger")):
        app = resolve_app("swiggy")
        return IntentResult(
            kind=IntentKind.UI_AUTOMATION,
            task=raw,
            app=str(app["name"]) if app else "Swiggy",
            target_package=str(app["package"]) if app else "in.swiggy.android",
            constraints=constraints,
            requires_llm=True,
            extracted_query=constraints.item_query,
        )

    if any(token in lowered for token in ("email", "gmail", "calendar", "event", "contact")):
        return IntentResult(
            kind=IntentKind.API_TOOL,
            task=raw,
            constraints=constraints,
            requires_llm=True,
        )

    return IntentResult(
        kind=IntentKind.UI_AUTOMATION,
        task=raw,
        app="Swiggy" if constraints.item_query else None,
        target_package="in.swiggy.android" if constraints.item_query else None,
        constraints=constraints,
        requires_llm=True,
        extracted_query=constraints.item_query,
    )
