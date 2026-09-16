import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import SWIGGY_API_DISCOVERY_DIR


class SwiggyApiDiscovery:
    """
    Persists and loads Swiggy API capture sessions for endpoint cataloguing.
    All files live under .user_data/swiggy_api_discovery/ — never touches Zomato paths.
    """

    CATALOG_FILE = "endpoint_catalog.json"

    @staticmethod
    def persist_capture(
        entries: List[Dict[str, Any]],
        summary: Dict[str, Any],
        session_cookies: Optional[List[Dict[str, Any]]] = None,
        label: Optional[str] = None,
    ) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"capture_{label or 'session'}_{timestamp}.json"
        filepath = SWIGGY_API_DISCOVERY_DIR / filename

        payload = {
            "captured_at": datetime.now().isoformat(),
            "label": label or "session",
            "summary": summary,
            "entries": entries,
            "session_cookies_count": len(session_cookies or []),
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)

        SwiggyApiDiscovery._update_catalog(entries)
        print(f"[Swiggy API Discovery] Saved capture to {filepath}")
        return str(filepath)

    @staticmethod
    def _update_catalog(entries: List[Dict[str, Any]]) -> None:
        catalog_path = SWIGGY_API_DISCOVERY_DIR / SwiggyApiDiscovery.CATALOG_FILE
        catalog: Dict[str, Any] = {}
        if catalog_path.exists():
            try:
                with open(catalog_path, "r", encoding="utf-8") as f:
                    catalog = json.load(f)
            except json.JSONDecodeError:
                catalog = {}

        endpoints: Dict[str, Any] = catalog.get("endpoints", {})
        for entry in entries:
            url = entry.get("url")
            if not url:
                continue
            endpoints[url] = {
                "url": url,
                "method": entry.get("method"),
                "category": entry.get("category"),
                "last_status": entry.get("status"),
                "last_seen": entry.get("captured_at") or datetime.now().isoformat(),
                "has_request_body": bool(entry.get("request_body")),
                "sample_request_body": entry.get("request_body"),
            }

        catalog["updated_at"] = datetime.now().isoformat()
        catalog["endpoints"] = endpoints
        with open(catalog_path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2, default=str)

    @staticmethod
    def load_latest_capture() -> Optional[Dict[str, Any]]:
        files = sorted(SWIGGY_API_DISCOVERY_DIR.glob("capture_*.json"), reverse=True)
        if not files:
            return None
        try:
            with open(files[0], "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    @staticmethod
    def load_catalog() -> Dict[str, Any]:
        catalog_path = SWIGGY_API_DISCOVERY_DIR / SwiggyApiDiscovery.CATALOG_FILE
        if not catalog_path.exists():
            return {"endpoints": {}}
        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"endpoints": {}}

    @staticmethod
    def get_endpoints_by_category(category: str) -> List[Dict[str, Any]]:
        catalog = SwiggyApiDiscovery.load_catalog()
        return [
            ep for ep in catalog.get("endpoints", {}).values()
            if ep.get("category") == category
        ]
