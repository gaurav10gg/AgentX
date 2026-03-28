from __future__ import annotations

import hashlib

from .schemas import NormalizedScreen


def compute_screen_signature(screen: NormalizedScreen) -> str:
    fingerprint = []
    fingerprint.append(screen.app_package or "unknown")
    fingerprint.append(screen.title or "")
    fingerprint.extend(
        f"{item.role}|{item.label}|{item.resource_id or ''}|{int(item.clickable)}|{int(item.editable)}"
        for item in screen.elements[:40]
    )
    raw = "||".join(fingerprint).encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()[:16]


def compute_structural_signature(screen: NormalizedScreen) -> str:
    """
    Stagnation-only signature.
    Ignores element IDs/paths and focuses on stable, user-visible structure.
    """
    fingerprint = []
    fingerprint.append(screen.app_package or "unknown")
    fingerprint.append(screen.title or "")

    sorted_elements = sorted(screen.elements[:40], key=lambda item: item.label.lower())
    for item in sorted_elements:
        fingerprint.append(
            f"{item.role}|{item.label}|{int(item.clickable)}|{int(item.editable)}|{int(item.scrollable)}"
        )

    fingerprint.extend(sorted(screen.anchors))
    raw = "||".join(fingerprint).encode("utf-8", errors="ignore")
    return hashlib.sha1(raw).hexdigest()[:16]
