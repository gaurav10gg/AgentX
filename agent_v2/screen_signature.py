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
