from typing import Optional
from playwright.sync_api import Page
from config import ZOMATO_DASHBOARD_URL


class ZomatoAuth:
    """
    Handles authentication status verification and session liveness checks for Zomato Partner portal.
    """

    def __init__(self, page: Optional[Page] = None):
        self.page = page

    def check_login_status(self) -> bool:
        """Checks if the user session is active on Zomato Partner portal."""
        if not self.page:
            return False
        try:
            self.page.goto(ZOMATO_DASHBOARD_URL, wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(3000)
            current_url = self.page.url

            # Redirected to login/signin
            if "login" in current_url or "signin" in current_url:
                return False

            # Check if any nav element or body text is present
            keywords = ["Reporting", "Finance", "Orders", "Menu", "Payouts", "Business reports"]
            for kw in keywords:
                try:
                    elem = self.page.get_by_text(kw, exact=False).first
                    if elem.is_visible(timeout=1000):
                        return True
                except Exception:
                    pass

            for f in self.page.frames:
                try:
                    body_text = f.evaluate("() => document.body ? document.body.innerText : ''")
                    if any(k.lower() in body_text.lower() for k in ["reporting", "finance", "payouts", "orders", "delivered"]):
                        return True
                except Exception:
                    pass

            return False
        except Exception:
            return False

    def wait_for_login(self, timeout_sec: int = 90) -> bool:
        """
        Actively monitors and waits up to `timeout_sec` seconds for user to complete login in the opened browser.
        Returns True once an authenticated dashboard or partner page is detected.
        """
        if not self.page:
            return False
        import time
        print(f"[*] Waiting up to {timeout_sec}s for Zomato Google login in opened browser...")
        start = time.time()
        while time.time() - start < timeout_sec:
            try:
                if self.page.is_closed():
                    return False
                current_url = self.page.url.lower()
                if "login" not in current_url and "signin" not in current_url:
                    if self.check_login_status():
                        print("[✓] Zomato session detected active!")
                        return True
            except Exception:
                pass
            try:
                self.page.wait_for_timeout(2500)
            except Exception:
                break
        return self.check_login_status()

