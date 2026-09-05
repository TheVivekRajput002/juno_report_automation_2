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

    def interactive_login(self, target_url: str = ZOMATO_LOGIN_URL):
        """
        Opens the browser in headed mode to let the user log in with Google.
        Waits until the user completes login and presses Enter in terminal.
        """
        print("\n" + "=" * 60)
        print("  GOOGLE LOGIN & SESSION SETUP")
        print("=" * 60)
        print(f"Opening browser to: {target_url}")
        print("Please log in using your Google account in the opened browser.")
        print("Your session will be saved automatically for future automated runs.")
        print("-" * 60)

        page = self.get_page()
        page.goto(target_url)

        input("\n>>> Once you have successfully logged in to the dashboard, press ENTER here to save session... ")
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
