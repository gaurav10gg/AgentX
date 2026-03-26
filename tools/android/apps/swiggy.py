from __future__ import annotations

import re
from typing import Dict, List, Optional


SWIGGY_PACKAGE = "in.swiggy.android"
PRICE_PATTERN = re.compile(r"(?:₹|rs\.?|inr)\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
RATING_PATTERN = re.compile(r"\b(\d(?:\.\d)?)\b")
DELIVERY_TIME_PATTERN = re.compile(r"(\d{1,3})\s*(?:mins?|minutes?)", re.IGNORECASE)
FOOD_TERMS = ("biryani", "pizza", "burger", "meal", "rice", "roll", "chicken", "paneer", "thali", "fries")
CHECKOUT_TERMS = ("checkout", "place order", "proceed to pay", "continue to payment")
POPUP_DISMISS_TERMS = ("not now", "skip", "close", "maybe later")
POPUP_ALLOW_TERMS = ("allow", "continue", "ok")


def is_swiggy_package(package_name: Optional[str]) -> bool:
    return (package_name or "").lower() == SWIGGY_PACKAGE


def detect_screen_type(elements: List[Dict[str, object]]) -> str:
    labels = " ".join(str(element.get("label", "")).lower() for element in elements)
    if any(term in labels for term in CHECKOUT_TERMS):
        return "checkout"
    if "cart" in labels:
        return "cart"
    if "search" in labels:
        return "search"
    if any(term in labels for term in ("delivery to", "restaurants", "food")):
        return "home"
    return "unknown"


def extract_candidates(elements: List[Dict[str, object]]) -> List[Dict[str, object]]:
    candidates: List[Dict[str, object]] = []
    for element in elements:
        label = str(element.get("label", "")).strip()
        lowered = label.lower()
        if not label:
            continue
        if not bool(element.get("clickable")):
            continue
        if not any(term in lowered for term in FOOD_TERMS):
            continue

        price = _extract_float(PRICE_PATTERN, label)
        rating = _extract_rating(label)
        delivery_time = _extract_int(DELIVERY_TIME_PATTERN, label)
        candidates.append(
            {
                "element_id": element.get("id"),
                "label": label,
                "price": price,
                "rating": rating,
                "delivery_time": delivery_time,
                "source": "swiggy_adapter",
            }
        )
    return _dedupe(candidates)


def infer_anchors(elements: List[Dict[str, object]]) -> List[str]:
    anchors: List[str] = []
    labels = [str(element.get("label", "")).lower() for element in elements]
    if any("search" in label for label in labels):
        anchors.append("search")
    if any("cart" in label for label in labels):
        anchors.append("cart")
    if any(any(term in label for term in CHECKOUT_TERMS) for label in labels):
        anchors.append("checkout")
    if any(any(term in label for term in POPUP_DISMISS_TERMS + POPUP_ALLOW_TERMS) for label in labels):
        anchors.append("popup")
    return sorted(set(anchors))


def choose_popup_action(elements: List[Dict[str, object]]) -> Optional[Dict[str, object]]:
    for terms, reason in ((POPUP_DISMISS_TERMS, "dismiss_popup"), (POPUP_ALLOW_TERMS, "accept_popup")):
        for element in elements:
            label = str(element.get("label", "")).lower()
            if not bool(element.get("clickable")):
                continue
            if any(term in label for term in terms):
                return {"element_id": element.get("id"), "reason": reason, "label": element.get("label")}
    return None


def choose_search_input(elements: List[Dict[str, object]]) -> Optional[str]:
    for element in elements:
        label = str(element.get("label", "")).lower()
        resource_id = str(element.get("resource_id", "")).lower()
        if bool(element.get("editable")) and ("search" in label or "search" in resource_id):
            return str(element.get("id"))
    return None


def choose_checkout_action(elements: List[Dict[str, object]]) -> Optional[str]:
    for element in elements:
        label = str(element.get("label", "")).lower()
        if bool(element.get("clickable")) and any(term in label for term in CHECKOUT_TERMS):
            return str(element.get("id"))
    return None


def _extract_float(pattern: re.Pattern[str], value: str) -> Optional[float]:
    match = pattern.search(value)
    return float(match.group(1)) if match else None


def _extract_int(pattern: re.Pattern[str], value: str) -> Optional[int]:
    match = pattern.search(value)
    return int(match.group(1)) if match else None


def _extract_rating(value: str) -> Optional[float]:
    lowered = value.lower()
    if not any(token in lowered for token in ("rating", "rated", "star", "stars")):
        return None
    match = RATING_PATTERN.search(value)
    return float(match.group(1)) if match else None


def _dedupe(candidates: List[Dict[str, object]]) -> List[Dict[str, object]]:
    seen = set()
    unique: List[Dict[str, object]] = []
    for candidate in candidates:
        key = (candidate.get("element_id"), candidate.get("label"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique
