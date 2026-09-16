from typing import Optional
from playwright.sync_api import Page
from config import SWIGGY_BASE_URL, SWIGGY_DASHBOARD_URL, SWIGGY_LOGIN_URL


class SwiggyAuth:
    """
    Handles authentication status verification and session liveness checks for Swiggy Partner portal.
    """

    def __init__(self, page: Optional[Page] = None):
        self.page = page

    def check_login_status(self) -> bool:
        """Checks if the user session is active on Swiggy Partner portal."""
        if not self.page:
            return False
        try:
            print("[*] Checking Swiggy Partner session...")
            self.page.goto(SWIGGY_DASHBOARD_URL, wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(3000)
            current_url = self.page.url.lower()

            # Redirected to login/signin/auth
            if "login" in current_url or "signin" in current_url or "auth" in current_url:
                print("[!] Swiggy redirected to login page.")
                return False

            # Check if login form text / mobile prompt is visible in any frame
            combined_body_text = ""
            for f in self.page.frames:
                try:
                    txt = f.evaluate("() => document.body ? document.body.innerText : ''")
                    if len(txt) > len(combined_body_text):
                        combined_body_text = txt
                except Exception:
                    pass

            unauth_signals = [
                "enter restaurant id / mobile number",
                "enter a mobile number or restaurant id",
                "partner with swiggy!",
                "get your restaurant delivery-ready",
                "enter a valid mobile number",
                "enter otp",
                "send otp",
            ]
            if any(sig in combined_body_text.lower() for sig in unauth_signals):
                print("[!] Swiggy login form detected.")
                return False

            # Check if authenticated dashboard elements / navigation are present
            dashboard_keywords = [
                "Business metrics",
                "Growth",
                "Finance",
                "Orders",
                "Menu",
                "Payouts",
                "Performance",
                "Reports",
                "Past Payouts",
            ]
            for kw in dashboard_keywords:
                try:
                    elem = self.page.get_by_text(kw, exact=False).first
                    if elem.is_visible(timeout=1000):
                        return True
                except Exception:
                    pass

            if any(k.lower() in combined_body_text.lower() for k in ["business metrics", "past payouts", "item total", "growth investments"]):
                return True

            # Check if user icon or outlet selector is present
            header_selectors = [
                "[data-testid*='outlet']",
                "[class*='outlet-select']",
                "[class*='user-profile']",
                "[class*='Header']",
                "header",
            ]
            for sel in header_selectors:
                try:
                    el = self.page.locator(sel).first
                    if el.is_visible(timeout=1000):
                        return True
                except Exception:
                    pass

            return False
        except Exception as e:
            print(f"[!] Notice checking Swiggy login status: {e}")
            return False

    def wait_for_login(self, timeout_sec: int = 90) -> bool:
        """
        Actively monitors and waits up to `timeout_sec` seconds for user to complete login in the opened browser.
        Returns True once an authenticated dashboard or partner page is detected.
        """
        if not self.page:
            return False
        import time
        print(f"[*] Waiting up to {timeout_sec}s for Swiggy Partner login (enter your mobile & OTP in browser)...")
        start = time.time()
        while time.time() - start < timeout_sec:
            try:
                if self.page.is_closed():
                    return False
                current_url = self.page.url.lower()
                if "login" not in current_url and "signin" not in current_url and "auth" not in current_url:
                    if self.check_login_status():
                        print("[✓] Swiggy Partner session detected active!")
                        return True
            except Exception:
                pass
            try:
                self.page.wait_for_timeout(2500)
            except Exception:
                break
        return self.check_login_status()

