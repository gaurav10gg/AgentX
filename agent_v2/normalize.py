from __future__ import annotations

import re
from typing import Dict, List, Optional

from .schemas import DeviceObservation, NormalizedElement, NormalizedScreen, RawUiNode
from .screen_signature import compute_screen_signature


PRICE_PATTERN = re.compile(r"(?:₹|rs\.?|inr)\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
RATING_PATTERN = re.compile(r"\b(\d(?:\.\d)?)\b")
DELIVERY_TIME_PATTERN = re.compile(r"(\d{1,3})\s*(?:mins?|minutes?)", re.IGNORECASE)
FOOD_HINTS = ("biryani", "pizza", "burger", "meal", "rice", "roll", "chicken", "paneer", "thali", "fries")


def normalize_observation(observation: DeviceObservation) -> NormalizedScreen:
    roots = observation.ui_tree_list[:]
    if observation.ui_tree:
        roots.insert(0, observation.ui_tree)

    elements: List[NormalizedElement] = []
    candidates: List[Dict[str, object]] = []
    anchors: List[str] = []
    html_lines: List[str] = []

    for root_index, root in enumerate(roots):
        _walk_node(
            node=root,
            path=f"{root_index}",
            depth=0,
            elements=elements,
            anchors=anchors,
            html_lines=html_lines,
            candidates=candidates,
        )

    app_package = observation.foreground_app or next(
        (element.package_name for element in elements if element.package_name),
        None,
    )
    provisional = NormalizedScreen(
        screen_id=observation.timestamp or "screen",
        app_package=app_package,
        title=observation.screen_title,
        screen_signature="pending",
        html="\n".join(html_lines),
        elements=elements,
        anchors=sorted(set(anchors)),
        candidates=_dedupe_candidates(candidates),
    )
    provisional.screen_signature = compute_screen_signature(provisional)
    provisional.screen_id = f"{provisional.app_package or 'screen'}::{provisional.screen_signature}"
    return provisional


def _walk_node(
    node: RawUiNode,
    path: str,
    depth: int,
    elements: List[NormalizedElement],
    anchors: List[str],
    html_lines: List[str],
    candidates: List[Dict[str, object]],
):
    if not node.visible:
        return

    label = _node_label(node)
    role = _node_role(node)
    actionable = bool(label or node.clickable or node.editable or node.scrollable)

    if actionable:
        element = NormalizedElement(
            id=node.native_id,
            native_id=node.native_id,
            role=role,
            label=label or node.class_name.split(".")[-1],
            text=node.text,
            package_name=node.package_name,
            resource_id=node.resource_id,
            clickable=node.clickable,
            editable=node.editable,
            scrollable=node.scrollable,
            path=path,
            score=_base_score(node),
            meta={"depth": depth},
        )
        elements.append(element)
        html_lines.append(_element_to_html(element))
        anchors.extend(_detect_anchors(element))

        candidate = _maybe_extract_candidate(element)
        if candidate:
            candidates.append(candidate)

    for index, child in enumerate(node.children):
        _walk_node(
            node=child,
            path=f"{path}.{index}",
            depth=depth + 1,
            elements=elements,
            anchors=anchors,
            html_lines=html_lines,
            candidates=candidates,
        )


def _node_label(node: RawUiNode) -> str:
    parts = [node.text or "", node.content_description or ""]
    text = " ".join(part.strip() for part in parts if part and part.strip())
    return re.sub(r"\s+", " ", text).strip()


def _node_role(node: RawUiNode) -> str:
    class_name = (node.class_name or "").lower()
    if node.editable or "edittext" in class_name:
        return "input"
    if node.scrollable or "recyclerview" in class_name or "scrollview" in class_name:
        return "scroll"
    if node.clickable or "button" in class_name:
        return "button"
    if "textview" in class_name:
        return "text"
    return "node"


def _base_score(node: RawUiNode) -> float:
    score = 0.0
    if node.clickable:
        score += 2.0
    if node.editable:
        score += 3.0
    if node.content_description:
        score += 0.5
    if node.resource_id:
        score += 0.5
    return score


def _element_to_html(element: NormalizedElement) -> str:
    label = _escape(element.label)
    if element.role == "input":
        return f'<input id="{element.id}" label="{label}" />'
    if element.role == "scroll":
        return f'<scroll id="{element.id}" label="{label}" />'
    if element.role == "button":
        return f'<button id="{element.id}">{label}</button>'
    return f'<node id="{element.id}" role="{element.role}">{label}</node>'


def _detect_anchors(element: NormalizedElement) -> List[str]:
    label = element.label.lower()
    anchors = []
    if "search" in label:
        anchors.append("search")
    if "cart" in label:
        anchors.append("cart")
    if "checkout" in label or "place order" in label:
        anchors.append("checkout")
    if "add" in label:
        anchors.append("add")
    return anchors


def _maybe_extract_candidate(element: NormalizedElement) -> Optional[Dict[str, object]]:
    label = element.label.strip()
    lowered = label.lower()
    if not label:
        return None

    price = _extract_number(PRICE_PATTERN, label)
    rating = _extract_rating(label)
    delivery_time = _extract_int(DELIVERY_TIME_PATTERN, label)

    looks_like_food_card = (
        element.clickable
        and len(label.split()) >= 2
        and not element.editable
        and any(term in lowered for term in FOOD_HINTS)
    )
    if not looks_like_food_card:
        return None

    return {
        "element_id": element.id,
        "label": label,
        "price": price,
        "rating": rating,
        "delivery_time": delivery_time,
    }


def _extract_number(pattern: re.Pattern[str], value: str) -> Optional[float]:
    match = pattern.search(value)
    return float(match.group(1)) if match else None


def _extract_int(pattern: re.Pattern[str], value: str) -> Optional[int]:
    match = pattern.search(value)
    return int(match.group(1)) if match else None


def _extract_rating(label: str) -> Optional[float]:
    lowered = label.lower()
    if not any(token in lowered for token in ("rating", "rated", "star", "stars")):
        return None
    match = RATING_PATTERN.search(label)
    return float(match.group(1)) if match else None


def _dedupe_candidates(candidates: List[Dict[str, object]]) -> List[Dict[str, object]]:
    seen = set()
    deduped = []
    for candidate in candidates:
        key = (candidate.get("element_id"), candidate.get("label"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
