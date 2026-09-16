import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from playwright.sync_api import BrowserContext, Page

from config import SWIGGY_SESSION_FILE


class SwiggySessionManager:
    """
    Manages Swiggy Partner portal auth (access_token + cookies) from Playwright.
    Swiggy uses access_token header for GraphQL — not browser cookies.
    """

    LOCAL_STORAGE_KEYS = (
        "access_token",
        "accessToken",
        "token",
        "authToken",
        "swiggy_access_token",
    )

    @staticmethod
    def extract_cookies_from_page(page: Page) -> List[Dict[str, Any]]:
        if not page or not page.context:
            return []
        try:
            return page.context.cookies()
        except Exception:
            return page.context.cookies(urls=["https://partner.swiggy.com", "https://www.swiggy.com"])

    @staticmethod
    def extract_access_token_from_page(page: Page) -> Optional[str]:
        if not page:
            return None
        try:
            token = page.evaluate("""() => {
                const keys = ['access_token', 'accessToken', 'token', 'authToken', 'swiggy_access_token'];
                for (const k of keys) {
                    const v = localStorage.getItem(k) || sessionStorage.getItem(k);
                    if (v && v.length > 10) return v;
                }
                return null;
            }""")
            if token:
                return str(token)
        except Exception:
            pass
        return None

    @staticmethod
    def extract_access_token_from_capture_entries(entries: List[Dict[str, Any]]) -> Optional[str]:
        for entry in reversed(entries):
            headers = entry.get("request_headers") or {}
            for key, value in headers.items():
                if key.lower() == "access_token" and value and len(str(value)) > 10:
                    return str(value)
        return None

    @staticmethod
    def cookies_to_dict(cookies: List[Dict[str, Any]]) -> Dict[str, str]:
        return {c["name"]: c["value"] for c in cookies if c.get("name")}

    @staticmethod
    def save_session(
        access_token: Optional[str] = None,
        cookies: Optional[List[Dict[str, Any]]] = None,
        path: Optional[str] = None,
    ) -> str:
        save_path = str(path or SWIGGY_SESSION_FILE)
        cookies = cookies or []
        payload = {
            "saved_at": datetime.now().isoformat(),
            "source": "playwright",
            "access_token": access_token or "",
            "cookies": cookies,
            "cookie_dict": SwiggySessionManager.cookies_to_dict(cookies),
        }
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        token_status = "yes" if access_token else "no"
        print(f"[Swiggy Session] Saved session (access_token: {token_status}, cookies: {len(cookies)}) -> {save_path}")
        return save_path

    @staticmethod
    def save_from_page(page: Page, capture_entries: Optional[List[Dict[str, Any]]] = None, path: Optional[str] = None) -> str:
        token = (
            SwiggySessionManager.extract_access_token_from_page(page)
            or SwiggySessionManager.extract_access_token_from_capture_entries(capture_entries or [])
        )
        cookies = SwiggySessionManager.extract_cookies_from_page(page)
        return SwiggySessionManager.save_session(access_token=token, cookies=cookies, path=path)

    @staticmethod
    def load(path: Optional[str] = None) -> Dict[str, Any]:
        load_path = path or SWIGGY_SESSION_FILE
        try:
            with open(load_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def load_access_token(path: Optional[str] = None) -> str:
        return SwiggySessionManager.load(path).get("access_token") or ""

    @staticmethod
    def load_cookie_dict(path: Optional[str] = None) -> Dict[str, str]:
        data = SwiggySessionManager.load(path)
        if data.get("cookie_dict"):
            return data["cookie_dict"]
        return SwiggySessionManager.cookies_to_dict(data.get("cookies", []))

    @staticmethod
    def apply_to_context(context: BrowserContext, path: Optional[str] = None) -> bool:
        data = SwiggySessionManager.load(path)
        cookies = data.get("cookies", [])
        if not cookies:
            return False
        context.add_cookies(cookies)
        return True
