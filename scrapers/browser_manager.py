import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, BrowserContext, Page
from config import USER_DATA_DIR, ZOMATO_LOGIN_URL, ZOMATO_BASE_URL


class BrowserManager:
    """Manages persistent browser sessions for Google Login and scraping."""

    def __init__(self, user_data_dir: Path = USER_DATA_DIR, headless: bool = False):
        self.user_data_dir = str(user_data_dir)
        self.headless = headless
        self.playwright = None
        self.context: BrowserContext = None
        self._named_pages = {}

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def start(self) -> BrowserContext:
        """Launches a persistent browser context with anti-detection args for Google Auth."""
        self.playwright = sync_playwright().start()

        # Stealth browser arguments to prevent Google from blocking automated login
        args = [
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--disable-extensions",
        ]

        # Try to use Google Chrome if installed, otherwise fallback to default chromium
        try:
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=self.headless,
                channel="chrome",
                args=args,
                ignore_default_args=["--enable-automation"],
                no_viewport=True,
            )
        except Exception:
            # Fallback to standard chromium
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=self.headless,
                args=args,
                ignore_default_args=["--enable-automation"],
                no_viewport=True,
            )

        return self.context

    def get_page(self) -> Page:
        """Returns the primary active page or creates a new one."""
        if not self.context:
            self.start()
        if self.context.pages:
            return self.context.pages[0]
        return self.context.new_page()

    def get_named_page(self, name: str) -> Page:
        """
        Returns or creates a dedicated named page/window (e.g. 'zomato', 'swiggy').
        Opens platforms in two distinct Chrome windows using the same persistent user data profile.
        """
        if not self.context:
            self.start()

        if name in self._named_pages:
            page = self._named_pages[name]
            try:
                if not page.is_closed():
                    return page
            except Exception:
                pass

        if name == "zomato":
            # Use primary window
            page = self.context.pages[0] if self.context.pages else self.context.new_page()
            self._named_pages[name] = page
            return page

        # For swiggy (or other platforms), launch in a separate distinct Chrome window
        primary_page = self.context.pages[0] if self.context.pages else self.context.new_page()
        try:
            with primary_page.expect_popup(timeout=5000) as popup_info:
                primary_page.evaluate("() => window.open('about:blank', '_blank', 'popup=yes,width=1366,height=868,left=150,top=100')")
            page = popup_info.value
        except Exception:
            page = self.context.new_page()

        self._named_pages[name] = page
        return page

    def interactive_login(self, target_url: str = ZOMATO_LOGIN_URL, timeout_sec: int = 180):
        """
        Opens the browser in headed mode to let the user log in.
        Supports both interactive CLI (with Enter key) and headless/Web UI background threads (auto-polling login state).
        """
        is_swiggy = "swiggy" in target_url.lower()
        plat_name = "Swiggy Partner" if is_swiggy else "Zomato Google"

        print("\n" + "=" * 60)
        print(f"  {plat_name.upper()} LOGIN & SESSION SETUP")
        print("=" * 60)
        print(f"Opening browser to: {target_url}")
        print(f"Please log in to your {plat_name} account in the opened browser window.")
        print("Your session will be saved automatically for future automated runs.")
        print("-" * 60)

        page = self.get_page()
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass

        # Check if running in an interactive terminal (stdin is a TTY)
        is_tty = False
        try:
            is_tty = sys.stdin and sys.stdin.isatty()
        except Exception:
            is_tty = False

        if is_tty:
            print("\n>>> Waiting for login. You can log in and press ENTER here to save session...")
            try:
                input(">>> After logging in to the dashboard, press ENTER here to continue... ")
            except (EOFError, KeyboardInterrupt):
                pass
        else:
            # Non-interactive mode (Web UI / server background thread)
            print(f"[*] Monitoring login state for up to {timeout_sec} seconds...")
            import time
            start_t = time.time()
            logged_in = False

            while time.time() - start_t < timeout_sec:
                try:
                    if page.is_closed():
                        print("[!] Browser page was closed by user.")
                        break

                    curr_url = page.url.lower()
                    # Check for successful redirection to dashboard or internal pages
                    if is_swiggy:
                        if ("business-metrics" in curr_url or "finance" in curr_url or "orders" in curr_url or "dashboard" in curr_url) and "login" not in curr_url and "signin" not in curr_url:
                            logged_in = True
                            break
                    else:
                        if ("reporting" in curr_url or "finance" in curr_url or "dashboard" in curr_url) and "login" not in curr_url and "signin" not in curr_url:
                            logged_in = True
                            break

                    for f in page.frames:
                        try:
                            txt = f.evaluate("() => document.body ? document.body.innerText : ''").lower()
                            if is_swiggy and any(k in txt for k in ["business metrics", "past payouts", "item total", "growth", "performance"]):
                                logged_in = True
                                break
                            elif not is_swiggy and any(k in txt for k in ["reporting", "payouts", "delivered orders", "net order value"]):
                                logged_in = True
                                break
                        except Exception:
                            pass

                    if logged_in:
                        break
                except Exception:
                    pass

                try:
                    page.wait_for_timeout(2000)
                except Exception:
                    break

            if logged_in:
                print(f"[✓] Successfully detected active {plat_name} session!")
            else:
                print(f"[*] Login monitor completed. Profile saved to {self.user_data_dir}.")

        print("Session saved successfully to:", self.user_data_dir)

    def close(self):
        """Closes browser context and playwright."""
        if self.context:
            try:
                self.context.close()
            except Exception:
                pass
            self.context = None
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
            self.playwright = None
