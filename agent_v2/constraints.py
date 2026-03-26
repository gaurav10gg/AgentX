from __future__ import annotations

import re
from typing import Dict, List

from .schemas import ConstraintSet, NormalizedScreen


PRICE_RE = re.compile(r"(?:under|below|<=?|max)\s*(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
RATING_RE = re.compile(r"(\d(?:\.\d)?)\s*\+?\s*(?:rating|rated|stars?)", re.IGNORECASE)
COD_RE = re.compile(r"\b(?:cod|cash on delivery)\b", re.IGNORECASE)
DELIVERY_TIME_RE = re.compile(r"(?:under|within|max)\s*(\d{1,3})\s*(?:mins?|minutes?)", re.IGNORECASE)


def extract_constraints(message: str) -> ConstraintSet:
    text = message or ""
    constraints = ConstraintSet()

    price_match = PRICE_RE.search(text)
    if price_match:
        constraints.price_max = float(price_match.group(1))
        constraints.hard.append("price_max")

    rating_match = RATING_RE.search(text)
    if rating_match:
        constraints.rating_min = float(rating_match.group(1))
        constraints.hard.append("rating_min")

    if COD_RE.search(text):
        constraints.payment = "cod"
        constraints.hard.append("payment")

    delivery_time_match = DELIVERY_TIME_RE.search(text)
    if delivery_time_match:
        constraints.delivery_time_max_min = int(delivery_time_match.group(1))
        constraints.hard.append("delivery_time_max_min")

    lowered = text.lower()
    for keyword in ("biryani", "pizza", "burger", "chicken", "veg", "paneer"):
        if keyword in lowered:
            constraints.item_query = keyword if constraints.item_query is None else constraints.item_query
            if keyword in ("chicken", "veg", "paneer"):
                constraints.cuisine = keyword
                constraints.soft.append("cuisine")

    if "best rated" in lowered or "highest rated" in lowered:
        constraints.soft.append("best_rated")
    if "fast delivery" in lowered or "quick delivery" in lowered:
        constraints.soft.append("fast_delivery")

    return constraints


def score_candidate(candidate: Dict[str, object], constraints: ConstraintSet) -> float:
    score = 0.0
    price = _to_float(candidate.get("price"))
    rating = _to_float(candidate.get("rating"))
    label = str(candidate.get("label", "")).lower()

    if constraints.item_query and constraints.item_query.lower() in label:
        score += 4.0
    if constraints.cuisine and constraints.cuisine.lower() in label:
        score += 1.5
    if price is not None:
        score += max(0.0, 3.0 - (price / 200.0))
    if rating is not None:
        score += rating
    if "best_rated" in constraints.soft and rating is not None:
        score += rating * 0.5
    if "fast_delivery" in constraints.soft and candidate.get("delivery_time"):
        score += 1.0
    if (
        constraints.delivery_time_max_min is not None
        and candidate.get("delivery_time") is not None
    ):
        score += max(0.0, 2.0 - (int(candidate["delivery_time"]) / 30.0))
    return score


def filter_candidates(screen: NormalizedScreen, constraints: ConstraintSet) -> List[Dict[str, object]]:
    candidates: List[Dict[str, object]] = []
    for candidate in screen.candidates:
        price = _to_float(candidate.get("price"))
        rating = _to_float(candidate.get("rating"))
        delivery_time = candidate.get("delivery_time")

        if constraints.price_max is not None and price is not None and price > constraints.price_max:
            continue
        if constraints.rating_min is not None and rating is not None and rating < constraints.rating_min:
            continue
        if (
            constraints.delivery_time_max_min is not None
            and delivery_time is not None
            and int(delivery_time) > constraints.delivery_time_max_min
        ):
            continue

        enriched = dict(candidate)
        enriched["score"] = score_candidate(enriched, constraints)
        candidates.append(enriched)

    candidates.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    return candidates


def has_hard_constraint_conflict(candidates: List[Dict[str, object]], constraints: ConstraintSet) -> bool:
    hard_fields = set(constraints.hard)
    return bool(hard_fields) and not candidates


def _to_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        match = re.search(r"(\d+(?:\.\d+)?)", str(value))
        return float(match.group(1)) if match else None
