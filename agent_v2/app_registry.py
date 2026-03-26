from __future__ import annotations

from typing import Dict, List, Optional


APP_REGISTRY: Dict[str, Dict[str, object]] = {
    "swiggy": {
        "name": "Swiggy",
        "package": "in.swiggy.android",
        "capabilities": ["search", "browse_cards", "cart", "checkout"],
        "aliases": ["swiggy", "food", "order food", "order on swiggy"],
    },
    "whatsapp": {
        "name": "WhatsApp",
        "package": "com.whatsapp",
        "capabilities": ["messaging", "chat_search"],
        "aliases": ["whatsapp", "wa"],
    },
    "settings": {
        "name": "Settings",
        "package": "com.android.settings",
        "capabilities": ["system_navigation"],
        "aliases": ["settings", "android settings"],
    },
}


def resolve_app(app_name: Optional[str]) -> Optional[Dict[str, object]]:
    if not app_name:
        return None

    needle = app_name.strip().lower()
    for app in APP_REGISTRY.values():
        aliases = [str(alias).lower() for alias in app.get("aliases", [])]
        if needle == str(app["name"]).lower() or needle in aliases:
            return app

    for app in APP_REGISTRY.values():
        aliases = [str(alias).lower() for alias in app.get("aliases", [])]
        if any(alias in needle or needle in alias for alias in aliases):
            return app

    return None


def list_apps() -> List[Dict[str, object]]:
    return [
        {
            "id": app_id,
            **app,
        }
        for app_id, app in APP_REGISTRY.items()
    ]
