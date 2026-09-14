import re
from typing import Dict, Any, Optional, List, Tuple
from playwright.sync_api import Page, Locator


class BaseZomatoScraper:
    """
    Base class providing common utilities for Playwright DOM navigation,
    multi-frame querying, modal handling, and network interception across Zomato portal tabs.
    """

    def __init__(self, page: Optional[Page] = None):
        self.page = page
        self.intercepted_data: Dict[str, Any] = {}
        if self.page:
            self._setup_network_interception()

    def _setup_network_interception(self):
        """Intercepts internal JSON responses for reporting, payouts, and settlements."""
        def handle_response(response):
            try:
                url = response.url.lower()
                if any(kw in url for kw in ["api", "settlement", "report", "payout", "performance", "metric", "finance"]):
                    content_type = response.headers.get("content-type", "")
                    if "json" in content_type:
                        data = response.json()
                        self.intercepted_data[response.url] = data
            except Exception:
                pass

        self.page.on("response", handle_response)

    def find_clickable(self, candidates: List[str], timeout_ms: int = 2000) -> Optional[Locator]:
        """Tries multiple selectors safely across main page and all frames and returns the first visible one."""
        if not self.page:
            return None
        for sel in candidates:
            try:
                elem = self.page.locator(sel).first
                if elem.is_visible(timeout=timeout_ms):
                    return elem
            except Exception:
                pass
            for f in self.page.frames:
                try:
                    elem = f.locator(sel).first
                    if elem.is_visible(timeout=timeout_ms // 2):
                        return elem
                except Exception:
                    pass
        return None

    def close_all_drawers_and_modals(self):
        """Closes any open side-drawers, modals, or dialog backdrops."""
        if not self.page:
            return
        try:
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(300)
            for f in [self.page.main_frame] + self.page.frames:
                try:
                    f.evaluate("""() => {
                        const closeBtns = Array.from(document.querySelectorAll('[aria-label="close"], [aria-label="Close"], button[class*="close"], [class*="close-icon"], [class*="CloseIcon"], svg[class*="close"]'));
                        for (const b of closeBtns) {
                            try { b.click(); } catch(e) {}
                        }
                    }""")
                except Exception:
                    pass
            self.page.wait_for_timeout(300)
        except Exception:
            pass

    @staticmethod
    def parse_outlet_label(text: str) -> Tuple[Optional[str], Optional[str]]:
        """Parses restaurant name and ID from outlet labels like 'The Spice Meridian (Id: 22663260)' or 'The Paneer Story\\nShankar Nagar, Raipur | ID: 22749423'."""
        if not text:
            return None, None

        # Extract ID first
        res_id = None
        m_id = re.search(r"\b(?:[Ii][Dd]|Id|ID)[:\s#]+(\d{6,10})", text)
        if m_id:
            res_id = m_id.group(1).strip()

        # Extract clean name (first line or before address / pipe / ID)
        first_line = text.strip().split("\n")[0].strip()
        clean = re.sub(r"\s*\(?\b[Ii][Dd]\b:?\s*\d+\)?.*$", "", first_line, flags=re.I)
        clean = re.sub(r"\s*\|.*$", "", clean).strip()
        clean = re.sub(r"\s*-\s*\d+.*$", "", clean).strip()
        if clean.endswith("(") or clean.endswith("-"):
            clean = clean[:-1].strip()

        name = clean if clean and not clean.isdigit() else None
        if not res_id and text.strip().isdigit():
            res_id = text.strip()

        return name, res_id
